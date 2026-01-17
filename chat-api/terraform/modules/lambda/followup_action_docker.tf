# ============================================================================
# Followup Action Lambda - Bedrock Action Group Handler
# Docker-based deployment for handling action group invocations
# from the Follow-up Research Assistant Bedrock agent.
#
# NO Lambda Web Adapter - returns Bedrock action group JSON format directly.
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "followup_action" {
  name                 = "${var.project_name}/followup-action"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.common_tags, {
    Name    = "followup-action-ecr"
    Service = "bedrock-action-group"
  })
}

# Lifecycle policy to keep only the latest version
resource "aws_ecr_lifecycle_policy" "followup_action" {
  repository = aws_ecr_repository.followup_action.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only the latest tagged image"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["v"]
          countType     = "imageCountMoreThan"
          countNumber   = 1
        }
        action = {
          type = "expire"
        }
      },
      {
        rulePriority = 2
        description  = "Expire untagged images older than 1 day"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 1
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================================
# IAM Role (separate from shared Lambda role for least privilege)
# ============================================================================

resource "aws_iam_role" "followup_action" {
  name = "${var.project_name}-${var.environment}-followup-action-role"

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

  tags = merge(var.common_tags, {
    Name    = "followup-action-role"
    Service = "bedrock-action-group"
  })
}

# ============================================================================
# IAM Policy
# ============================================================================

resource "aws_iam_role_policy" "followup_action" {
  name = "${var.project_name}-${var.environment}-followup-action-policy"
  role = aws_iam_role.followup_action.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # DynamoDB - Investment Reports V2 (read-only)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query",
          "dynamodb:Scan"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-investment-reports-v2",
          "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-investment-reports-v2/index/*"
        ]
      },
      # DynamoDB - Financial Data Cache (read-only, for future metrics history)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:Query"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-financial-data-cache"
        ]
      },
      # X-Ray Tracing
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords"
        ]
        Resource = "*"
      },
      # KMS (for DynamoDB encryption)
      {
        Effect = "Allow"
        Action = [
          "kms:Decrypt"
        ]
        Resource = var.kms_key_arn
      }
    ]
  })
}

# ============================================================================
# Lambda Function (Container)
# ============================================================================

resource "aws_lambda_function" "followup_action" {
  function_name = "${var.project_name}-${var.environment}-followup-action"
  role          = aws_iam_role.followup_action.arn

  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.followup_action.repository_url}:${var.followup_action_image_tag}"

  # Performance configuration (lightweight - just DynamoDB reads)
  timeout     = 30   # 30 seconds
  memory_size = 512  # 512 MB

  environment {
    variables = merge(
      var.common_env_vars,
      {
        INVESTMENT_REPORTS_TABLE_V2 = "${var.project_name}-${var.environment}-investment-reports-v2"
        FINANCIAL_DATA_CACHE_TABLE  = "${var.project_name}-${var.environment}-financial-data-cache"
        LOG_LEVEL                   = "INFO"
      }
    )
  }

  # X-Ray tracing
  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name    = "followup-action-lambda"
    Service = "bedrock-action-group"
  })

  depends_on = [
    aws_ecr_repository.followup_action,
    aws_cloudwatch_log_group.followup_action,
    aws_iam_role_policy.followup_action
  ]

  # Lifecycle to prevent replacement on version changes
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ============================================================================
# CloudWatch Log Group
# ============================================================================

resource "aws_cloudwatch_log_group" "followup_action" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-followup-action"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name    = "followup-action-logs"
    Service = "bedrock-action-group"
  })
}

# ============================================================================
# Bedrock Permission (allows Bedrock to invoke this Lambda)
# ============================================================================

resource "aws_lambda_permission" "bedrock_invoke_followup_action" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.followup_action.function_name
  principal     = "bedrock.amazonaws.com"

  # Allow any Bedrock agent in this account to invoke
  # Can be restricted to specific agent ARNs via source_arn if needed
}
