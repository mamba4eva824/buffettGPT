# IAM module for Bedrock Knowledge Base and Agent
# Creates service roles and policies based on reverse-engineered configuration

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Data source for current AWS region
data "aws_region" "current" {}

# Knowledge Base Service Role
resource "aws_iam_role" "knowledge_base_role" {
  name = var.knowledge_base_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.tags, {
    Name      = var.knowledge_base_role_name
    Purpose   = "Bedrock Knowledge Base Service Role"
    Component = "Bedrock Knowledge Base"
  })
}

# Knowledge Base Policy
resource "aws_iam_policy" "knowledge_base_policy" {
  name        = var.knowledge_base_policy_name
  description = "Policy for Bedrock Knowledge Base to access required resources"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeTitanEmbeddings"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-embed-text-v2:0"
      },
      {
        Sid    = "ReadSourceDocs"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = var.source_bucket_arn != "" ? [
          var.source_bucket_arn,
          "${var.source_bucket_arn}/*"
        ] : ["*"]
      },
      {
        Sid    = "ReadPineconeSecret"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = "${var.pinecone_secret_arn}*"
      }
    ]
  })

  tags = merge(var.tags, {
    Name      = var.knowledge_base_policy_name
    Purpose   = "Bedrock Knowledge Base Permissions"
    Component = "Bedrock Knowledge Base"
  })
}

# Attach Knowledge Base Policy to Role
resource "aws_iam_role_policy_attachment" "knowledge_base_policy_attachment" {
  role       = aws_iam_role.knowledge_base_role.name
  policy_arn = aws_iam_policy.knowledge_base_policy.arn
}

# Agent Service Role
resource "aws_iam_role" "agent_role" {
  name = var.agent_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "bedrock.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.tags, {
    Name      = var.agent_role_name
    Purpose   = "Bedrock Agent Service Role"
    Component = "Bedrock Agent"
  })
}

# Agent Policy
resource "aws_iam_policy" "agent_policy" {
  name        = var.agent_policy_name
  description = "Policy for Bedrock Agent to access required resources"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeFoundationModels"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/${var.foundation_model_id}"
        ]
      },
      {
        Sid    = "InvokeInferenceProfiles"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:GetInferenceProfile"
        ]
        Resource = [
          "arn:aws:bedrock:*::inference-profile/us.anthropic.*",
          "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*"
        ]
      },
      {
        Sid    = "AccessKnowledgeBase"
        Effect = "Allow"
        Action = [
          "bedrock:Retrieve",
          "bedrock:RetrieveAndGenerate"
        ]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"
      },
      {
        Sid    = "UseGuardrails"
        Effect = "Allow"
        Action = [
          "bedrock:ApplyGuardrail"
        ]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:guardrail/*"
      }
    ]
  })

  tags = merge(var.tags, {
    Name      = var.agent_policy_name
    Purpose   = "Bedrock Agent Permissions"
    Component = "Bedrock Agent"
  })
}

# Attach Agent Policy to Role
resource "aws_iam_role_policy_attachment" "agent_policy_attachment" {
  role       = aws_iam_role.agent_role.name
  policy_arn = aws_iam_policy.agent_policy.arn
}

# Optional: Attach AWS managed Bedrock Full Access policy
resource "aws_iam_role_policy_attachment" "agent_bedrock_full_access" {
  count      = var.attach_bedrock_full_access ? 1 : 0
  role       = aws_iam_role.agent_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}