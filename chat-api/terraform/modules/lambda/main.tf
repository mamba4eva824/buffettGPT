# Lambda Module - Simplified Management for Core Functions
# Based on Phase 1 analysis: 5 core Lambda functions (auth handled separately)

locals {
  # Core Lambda function configurations
  # Updated 2026-02: Removed WebSocket handlers and chat_http_handler (deprecated)
  # WebSocket infrastructure deprecated per WEBSOCKET_DEPRECATION_PLAN.md
  lambda_configs = {
    conversations_handler = {
      handler     = "conversations_handler.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "Conversations management API handler"
    }
    search_handler = {
      handler     = "search_handler.lambda_handler"
      timeout     = 60
      memory_size = 256
      description = "AI search handler with streaming support"
    }
    analysis_followup = {
      handler     = "analysis_followup.lambda_handler"
      timeout     = 60
      memory_size = 256
      description = "Follow-up question handler with session memory"
    }
    stripe_webhook_handler = {
      handler     = "stripe_webhook_handler.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "Stripe webhook event processor"
    }
    subscription_handler = {
      handler     = "subscription_handler.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "Subscription checkout, portal, and status API"
    }
    waitlist_handler = {
      handler     = "waitlist_handler.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "Waitlist signup and referral tracking API"
    }
  }
}

# ================================================
# Lambda Layer for Shared Dependencies
# ================================================

resource "aws_lambda_layer_version" "dependencies" {
  filename         = "${var.lambda_package_path}/dependencies-layer.zip"
  layer_name       = "${var.project_name}-${var.environment}-dependencies"
  description      = "Shared Python dependencies for Lambda functions"

  compatible_runtimes = [var.runtime]

  source_code_hash = filebase64sha256("${var.lambda_package_path}/dependencies-layer.zip")

  lifecycle {
    create_before_destroy = true
  }
}

# ================================================
# ML Dependencies Layer (ARCHIVED - 2025-01)
# ================================================
# NOTE: ML dependencies layer was removed when prediction ensemble was archived.
# It was stored in S3 (layers/ml-layer.zip) and contained numpy, scikit-learn,
# xgboost, scipy for XGBoost inference. See: archived/prediction_ensemble/

# ================================================
# Lambda Functions
# ================================================

resource "aws_lambda_function" "functions" {
  for_each = local.lambda_configs

  filename         = "${var.lambda_package_path}/${each.key}.zip"
  function_name    = "${var.project_name}-${var.environment}-${replace(each.key, "_", "-")}"
  role            = var.lambda_role_arn
  handler         = each.value.handler
  runtime         = var.runtime
  timeout         = each.value.timeout
  memory_size     = each.value.memory_size
  description     = each.value.description

  # Use source_code_hash for proper updates
  source_code_hash = filebase64sha256("${var.lambda_package_path}/${each.key}.zip")

  # Use the dependencies layer
  layers = [aws_lambda_layer_version.dependencies.arn]

  environment {
    variables = merge(
      var.common_env_vars,
      lookup(var.function_env_vars, each.key, {})
    )
  }

  # dead_letter_config - REMOVED (2026-02) - SQS infrastructure deprecated

  # Reserved concurrent executions (optional)
  reserved_concurrent_executions = lookup(var.reserved_concurrency, each.key, -1)

  tags = merge(
    var.common_tags,
    {
      Name     = "${var.project_name}-${var.environment}-${replace(each.key, "_", "-")}"
      Function = each.key
      Type     = "HTTP"
    }
  )

  depends_on = [aws_cloudwatch_log_group.lambda_logs]
}

# ================================================
# CloudWatch Log Groups
# ================================================

resource "aws_cloudwatch_log_group" "lambda_logs" {
  for_each = local.lambda_configs

  name              = "/aws/lambda/${var.project_name}-${var.environment}-${replace(each.key, "_", "-")}"
  retention_in_days = var.log_retention_days

  tags = merge(
    var.common_tags,
    {
      Name     = "${var.project_name}-${var.environment}-${replace(each.key, "_", "-")}-logs"
      Function = each.key
    }
  )
}

# ================================================
# Lambda Permissions for API Gateway
# ================================================
# Note: Lambda permissions are managed by the API Gateway module
# to avoid circular dependencies and duplicate permissions

# ================================================
# SQS Event Source Mapping - REMOVED (2026-02)
# ================================================
# chat_processor and SQS queue deprecated per WEBSOCKET_DEPRECATION_PLAN.md