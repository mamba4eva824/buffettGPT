# Core Infrastructure Module
# Manages KMS keys, IAM roles/policies, and SQS queues

# ================================================
# KMS Key for Encryption
# ================================================
resource "aws_kms_key" "chat_api_key" {
  description             = "${var.project_name}-${var.environment} encryption key"
  deletion_window_in_days = var.kms_deletion_window
  enable_key_rotation     = true

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-kms-key"
      Purpose = "Encryption for chat API resources"
    }
  )
}

resource "aws_kms_alias" "chat_api_key_alias" {
  name          = "alias/${var.project_name}-${var.environment}"
  target_key_id = aws_kms_key.chat_api_key.key_id
}

# ================================================
# IAM Role for Lambda Functions
# ================================================
resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-${var.environment}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-lambda-role"
      Purpose = "Lambda execution role"
    }
  )
}

# ================================================
# IAM Policy for Lambda Functions
# ================================================
resource "aws_iam_policy" "lambda_policy" {
  name        = "${var.project_name}-${var.environment}-lambda-policy"
  description = "Policy for Lambda functions in ${var.environment}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # DynamoDB Access
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-*",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-*/index/*",
          # Investment Reports V2 table (non-prefixed naming convention)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/investment-reports-v2-${var.environment}",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/investment-reports-v2-${var.environment}/index/*",
          # Metrics History table (pre-computed metrics by category)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/metrics-history-${var.environment}",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/metrics-history-${var.environment}/index/*",
          # Token Usage table (new naming: resource-env-project)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/token-usage-${var.environment}-${var.project_name}",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/token-usage-${var.environment}-${var.project_name}/index/*",
          # Waitlist table (resource-env-project naming)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/waitlist-${var.environment}-${var.project_name}",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/waitlist-${var.environment}-${var.project_name}/index/*",
          # Stock data 4H table (daily EOD prices)
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/stock-data-4h-${var.environment}",
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/stock-data-4h-${var.environment}/index/*"
        ]
      },
      # SQS Access - REMOVED (2026-02) - chat processing queue deprecated
      # KMS Access
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = aws_kms_key.chat_api_key.arn
      },
      # Bedrock Access
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeAgent",
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      },
      # API Gateway WebSocket Management - REMOVED (2026-02) - WebSocket deprecated
      # CloudWatch Metrics
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      # S3 Access for ML Models (Ensemble Analysis)
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-${var.environment}-models",
          "arn:aws:s3:::${var.project_name}-${var.environment}-models/*"
        ]
      },
      # Secrets Manager Access for FMP API Key and JWT Secret
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-${var.environment}-fmp*",
          "arn:aws:secretsmanager:${var.aws_region}:${data.aws_caller_identity.current.account_id}:secret:${var.project_name}-${var.environment}-jwt-secret*"
        ]
      },
      # ECR Access (pull Docker images for container-based Lambdas)
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:DescribeImages"
        ]
        Resource = [
          "arn:aws:ecr:${var.aws_region}:${data.aws_caller_identity.current.account_id}:repository/${var.project_name}/*"
        ]
      }
    ]
  })
}

# Attach policies to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_vpc_execution" {
  count      = var.enable_vpc ? 1 : 0
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

resource "aws_iam_role_policy_attachment" "lambda_custom_policy" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}

# ================================================
# SQS Queues - REMOVED (2026-02)
# ================================================
# Chat processing queue and DLQ deprecated per WEBSOCKET_DEPRECATION_PLAN.md
# WebSocket chat infrastructure no longer used - all chat via REST+SSE

# ================================================
# Data Sources
# ================================================
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}