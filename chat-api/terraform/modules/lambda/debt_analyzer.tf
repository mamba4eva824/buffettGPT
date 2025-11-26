# ============================================================================
# Debt Analyzer Lambda - ECR Container Deployment
# Separate from .zip-based Lambda functions for ML inference workloads
# ============================================================================

# ============================================================================
# ECR Repository
# ============================================================================

resource "aws_ecr_repository" "debt_analyzer" {
  name                 = "${var.project_name}/debt-analyzer"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }

  tags = merge(var.common_tags, {
    Name    = "debt-analyzer-ecr"
    Service = "ml-inference"
  })
}

# Lifecycle policy to keep only last 3 versions
resource "aws_ecr_lifecycle_policy" "debt_analyzer" {
  repository = aws_ecr_repository.debt_analyzer.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep last 3 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 3
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}

# ============================================================================
# Lambda Function (Container)
# ============================================================================

resource "aws_lambda_function" "debt_analyzer" {
  function_name = "${var.project_name}-${var.environment}-debt-analyzer"
  role          = aws_iam_role.debt_analyzer_role.arn

  # ⚠️  CRITICAL: Must set publish = true for versioning (required for Provisioned Concurrency)
  publish      = true
  package_type = "Image"
  image_uri    = "${aws_ecr_repository.debt_analyzer.repository_url}:${var.debt_analyzer_image_tag}"

  # Performance configuration
  timeout     = 20   # 20 seconds (cold start + S3 download + inference)
  memory_size = 1536 # 1.5 GB (CPU-optimized for gradient boosting)

  ephemeral_storage {
    size = 512 # MB
  }

  environment {
    variables = {
      ENVIRONMENT = var.environment

      # Model configuration
      MODEL_S3_BUCKET  = var.model_s3_bucket
      MODEL_S3_KEY     = "debt-analyzer/v${var.debt_analyzer_model_version}/debt_analyzer_model.pkl"
      MODEL_VERSION    = var.debt_analyzer_model_version
      MODEL_LOCAL_PATH = "/tmp/debt_analyzer_model.pkl"

      # DynamoDB tables
      FINANCIAL_CACHE_TABLE = var.financial_cache_table
      IDEMPOTENCY_TABLE     = var.idempotency_table

      # Perplexity API (from Secrets Manager)
      PERPLEXITY_API_KEY = data.aws_secretsmanager_secret_version.perplexity.secret_string
      PERPLEXITY_TIMEOUT = "25"
      MAX_RETRIES        = "2"

      # Logging
      LOG_LEVEL = var.environment == "prod" ? "INFO" : "DEBUG"
    }
  }

  # X-Ray tracing
  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name         = "debt-analyzer-lambda"
    ModelVersion = var.debt_analyzer_model_version
    ImageTag     = var.debt_analyzer_image_tag
    Service      = "ml-inference"
  })

  # Ensure image exists before deploying
  depends_on = [aws_ecr_repository.debt_analyzer]

  # Lifecycle to prevent replacement on version changes
  lifecycle {
    ignore_changes = [image_uri]
  }
}

# ============================================================================
# Lambda Alias (Required for Provisioned Concurrency)
# ============================================================================

resource "aws_lambda_alias" "debt_analyzer_live" {
  name             = var.environment
  description      = "Live alias for ${var.environment} environment"
  function_name    = aws_lambda_function.debt_analyzer.function_name
  function_version = aws_lambda_function.debt_analyzer.version

  # Lifecycle to prevent version conflicts
  lifecycle {
    ignore_changes = [function_version]
  }
}

# ============================================================================
# Provisioned Concurrency (Eliminates Cold Starts)
# ============================================================================

resource "aws_lambda_provisioned_concurrency_config" "debt_analyzer" {
  count = var.debt_analyzer_provisioned_concurrency > 0 ? 1 : 0

  function_name                     = aws_lambda_function.debt_analyzer.function_name
  provisioned_concurrent_executions = var.debt_analyzer_provisioned_concurrency
  qualifier                         = aws_lambda_alias.debt_analyzer_live.name

  # Lifecycle to allow version updates
  lifecycle {
    ignore_changes = [provisioned_concurrent_executions]
  }

  depends_on = [aws_lambda_alias.debt_analyzer_live]
}

# ============================================================================
# CloudWatch Log Group (7-day retention for dev, 30-day for prod)
# ============================================================================

resource "aws_cloudwatch_log_group" "debt_analyzer" {
  name              = "/aws/lambda/${aws_lambda_function.debt_analyzer.function_name}"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(var.common_tags, {
    Name    = "debt-analyzer-logs"
    Service = "ml-inference"
  })
}

# ============================================================================
# IAM Role for Debt Analyzer Lambda
# ============================================================================

resource "aws_iam_role" "debt_analyzer_role" {
  name = "${var.project_name}-${var.environment}-debt-analyzer-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = merge(var.common_tags, {
    Name    = "debt-analyzer-lambda-role"
    Service = "ml-inference"
  })
}

# ============================================================================
# IAM Policy: CloudWatch Logs (Function-Specific)
# ============================================================================

resource "aws_iam_role_policy" "debt_analyzer_cloudwatch_logs" {
  name = "cloudwatch-logs"
  role = aws_iam_role.debt_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        # ⚠️  Restrict to this function's log group only
        Resource = "${aws_cloudwatch_log_group.debt_analyzer.arn}:*"
      }
    ]
  })
}

# ============================================================================
# IAM Policy: S3 Model Download (Prefix-Only)
# ============================================================================

resource "aws_iam_role_policy" "debt_analyzer_s3_model_access" {
  name = "s3-model-access"
  role = aws_iam_role.debt_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3ModelDownload"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:GetObjectVersion"
        ]
        # ⚠️  Restrict to debt-analyzer prefix only
        Resource = "arn:aws:s3:::${var.model_s3_bucket}/debt-analyzer/*"
      },
      {
        Sid    = "S3ListBucket"
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.model_s3_bucket}"
        Condition = {
          StringLike = {
            "s3:prefix" = "debt-analyzer/*"
          }
        }
      }
    ]
  })
}

# ============================================================================
# IAM Policy: DynamoDB Cache Access (Table-Only)
# ============================================================================

resource "aws_iam_role_policy" "debt_analyzer_dynamodb_cache" {
  name = "dynamodb-cache-access"
  role = aws_iam_role.debt_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBFinancialCache"
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DescribeTable"
        ]
        # ⚠️  Restrict to specific table only
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.financial_cache_table}"
      },
      {
        Sid    = "DynamoDBIdempotencyCache"
        Effect = "Allow"
        Action = [
          "dynamodb:Query",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DescribeTable"
        ]
        # ⚠️  Restrict to specific table only
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.idempotency_table}"
      }
    ]
  })
}

# ============================================================================
# IAM Policy: KMS Decrypt (for DynamoDB encryption)
# ============================================================================

resource "aws_iam_role_policy" "debt_analyzer_kms_decrypt" {
  name = "kms-decrypt-access"
  role = aws_iam_role.debt_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "KMSDecrypt"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey"
        ]
        # Allow decrypt for DynamoDB table encryption keys
        Resource = var.kms_key_arn
      }
    ]
  })
}

# ============================================================================
# IAM Policy: Secrets Manager (Perplexity API Key)
# ============================================================================

data "aws_secretsmanager_secret" "perplexity" {
  name = "buffett-dev-sonar"
}

data "aws_secretsmanager_secret_version" "perplexity" {
  secret_id = data.aws_secretsmanager_secret.perplexity.id
}

resource "aws_iam_role_policy" "debt_analyzer_secrets_manager" {
  name = "secrets-manager-access"
  role = aws_iam_role.debt_analyzer_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SecretsManagerPerplexity"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        # ⚠️  Restrict to specific secret only
        Resource = data.aws_secretsmanager_secret.perplexity.arn
      }
    ]
  })
}

# ============================================================================
# IAM Policy: X-Ray Tracing
# ============================================================================

resource "aws_iam_role_policy_attachment" "debt_analyzer_xray" {
  role       = aws_iam_role.debt_analyzer_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

# ============================================================================
# Data Sources
# ============================================================================

data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ============================================================================
# Outputs
# ============================================================================

output "debt_analyzer_function_arn" {
  description = "ARN of the debt analyzer Lambda function"
  value       = aws_lambda_function.debt_analyzer.arn
}

output "debt_analyzer_function_name" {
  description = "Name of the debt analyzer Lambda function"
  value       = aws_lambda_function.debt_analyzer.function_name
}

output "debt_analyzer_function_version" {
  description = "Published version of the debt analyzer Lambda function"
  value       = aws_lambda_function.debt_analyzer.version
}

output "debt_analyzer_alias_arn" {
  description = "ARN of the debt analyzer Lambda alias"
  value       = aws_lambda_alias.debt_analyzer_live.arn
}

output "debt_analyzer_ecr_repository_url" {
  description = "URL of the debt analyzer ECR repository"
  value       = aws_ecr_repository.debt_analyzer.repository_url
}

output "debt_analyzer_role_arn" {
  description = "ARN of the debt analyzer IAM role"
  value       = aws_iam_role.debt_analyzer_role.arn
}
