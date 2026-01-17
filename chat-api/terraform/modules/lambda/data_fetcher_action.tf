# =============================================================================
# Ensemble Prediction Data Fetcher Action Lambda
# =============================================================================
# Purpose: Handle Bedrock action group invocations for financial data + ML inference
# Key: NO Lambda Web Adapter, NO FastAPI - returns exact Bedrock JSON format
# =============================================================================

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "ensemble_prediction_data_fetcher_action" {
  function_name = "${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
  description   = "Bedrock action group handler - fetches financial data and runs ML inference (pure Python, no LWA)"

  # Use zip package (NOT Docker) - simpler for pure Python handler
  filename         = "${var.lambda_package_path}/ensemble_prediction_data_fetcher_action.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/ensemble_prediction_data_fetcher_action.zip")

  handler = "handler.lambda_handler"
  runtime = var.runtime

  timeout     = 120  # 2 minutes for FMP API + ML inference
  memory_size = 1024 # Sufficient for XGBoost models

  role = aws_iam_role.ensemble_prediction_data_fetcher_action.arn

  # Use both dependencies layer and ML layer for inference
  layers = [
    aws_lambda_layer_version.dependencies.arn,
    aws_lambda_layer_version.ml_dependencies.arn
  ]

  environment {
    variables = merge(
      var.common_env_vars,
      {
        ENVIRONMENT                = var.environment
        FMP_SECRET_NAME            = "buffett-${var.environment}-fmp"
        FMP_API_KEY_ARN            = data.aws_secretsmanager_secret.fmp_api_key.arn
        FINANCIAL_DATA_CACHE_TABLE = "${var.project_name}-${var.environment}-financial-data-cache"
        TICKER_LOOKUP_TABLE        = "${var.project_name}-${var.environment}-ticker-lookup"
        ML_MODELS_BUCKET           = var.model_s3_bucket
        MODEL_S3_PREFIX            = "ensemble/v1"
        USE_VALUE_INVESTOR_FORMAT  = "true"
        LOG_LEVEL                  = "INFO"
      }
    )
  }

  # X-Ray tracing
  tracing_config {
    mode = "Active"
  }

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
    Service     = "bedrock-action-group"
    Purpose     = "data-fetcher"
    Description = "Pure Python Lambda for Bedrock action groups - no LWA/FastAPI"
  })

  depends_on = [
    aws_cloudwatch_log_group.ensemble_prediction_data_fetcher_action,
    aws_iam_role_policy.ensemble_prediction_data_fetcher_action,
    aws_lambda_layer_version.ml_dependencies
  ]
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ensemble_prediction_data_fetcher_action" {
  name = "${var.project_name}-${var.environment}-data-fetcher-action-role"

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
    Name        = "${var.project_name}-${var.environment}-data-fetcher-action-role"
    Environment = var.environment
  })
}

# -----------------------------------------------------------------------------
# IAM Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "ensemble_prediction_data_fetcher_action" {
  name = "${var.project_name}-${var.environment}-data-fetcher-action-policy"
  role = aws_iam_role.ensemble_prediction_data_fetcher_action.id

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
      # Secrets Manager (FMP API Key)
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = data.aws_secretsmanager_secret.fmp_api_key.arn
      },
      # S3 (ML Models)
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.model_s3_bucket}",
          "arn:aws:s3:::${var.model_s3_bucket}/*"
        ]
      },
      # DynamoDB (Financial Data Cache and Ticker Lookup)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query"
        ]
        Resource = [
          "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-financial-data-cache",
          "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-ticker-lookup"
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
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey"
        ]
        Resource = var.kms_key_arn
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "ensemble_prediction_data_fetcher_action" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
  retention_in_days = var.log_retention_days

  tags = merge(var.common_tags, {
    Name        = "${var.project_name}-${var.environment}-data-fetcher-action-logs"
    Environment = var.environment
    Service     = "bedrock-action-group"
  })
}

# -----------------------------------------------------------------------------
# Bedrock Permission (allows Bedrock to invoke this Lambda)
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "bedrock_invoke_data_fetcher" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ensemble_prediction_data_fetcher_action.function_name
  principal     = "bedrock.amazonaws.com"

  # Allow any Bedrock agent in this account to invoke
  # Can be restricted to specific agent ARNs if needed
}

# -----------------------------------------------------------------------------
# Outputs (defined inline for this standalone resource)
# -----------------------------------------------------------------------------
output "ensemble_prediction_data_fetcher_action_arn" {
  description = "ARN of the ensemble prediction data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.arn
}

output "ensemble_prediction_data_fetcher_action_name" {
  description = "Name of the ensemble prediction data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.function_name
}

output "ensemble_prediction_data_fetcher_action_invoke_arn" {
  description = "Invoke ARN of the ensemble prediction data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.invoke_arn
}
