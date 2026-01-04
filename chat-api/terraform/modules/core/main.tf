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
          "arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.project_name}-${var.environment}-*/index/*"
        ]
      },
      # SQS Access
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl"
        ]
        Resource = [
          aws_sqs_queue.chat_processing_queue.arn,
          aws_sqs_queue.chat_dlq.arn
        ]
      },
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
      # API Gateway WebSocket Management
      {
        Effect = "Allow"
        Action = [
          "execute-api:ManageConnections"
        ]
        Resource = "arn:aws:execute-api:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*/*/*/*"
      },
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
# SQS Queues
# ================================================
resource "aws_sqs_queue" "chat_processing_queue" {
  name                       = "${var.project_name}-${var.environment}-chat-processing"
  visibility_timeout_seconds = 720  # 12 minutes (6x Lambda timeout)
  message_retention_seconds  = 86400  # 1 day
  max_message_size          = 262144  # 256 KB
  receive_wait_time_seconds = 20  # Long polling
  
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.chat_dlq.arn
    maxReceiveCount     = 3
  })

  kms_master_key_id                 = aws_kms_key.chat_api_key.id
  kms_data_key_reuse_period_seconds = 300

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-chat-processing"
      Purpose = "Chat message processing queue"
    }
  )
}

resource "aws_sqs_queue" "chat_dlq" {
  name                      = "${var.project_name}-${var.environment}-chat-processing-dlq"
  message_retention_seconds = 1209600  # 14 days

  kms_master_key_id                 = aws_kms_key.chat_api_key.id
  kms_data_key_reuse_period_seconds = 300

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-chat-processing-dlq"
      Purpose = "Dead letter queue for failed messages"
    }
  )
}

# ================================================
# Data Sources
# ================================================
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}