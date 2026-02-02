# Lambda Module - Simplified Management for Core Functions
# Based on Phase 1 analysis: 5 core Lambda functions (auth handled separately)

locals {
  # Core Lambda function configurations
  lambda_configs = {
    chat_http_handler = {
      handler     = "chat_http_handler.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "HTTP API chat endpoint handler"
    }
    websocket_connect = {
      handler     = "websocket_connect.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "WebSocket connection handler with auth support"
    }
    websocket_disconnect = {
      handler     = "websocket_disconnect.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "WebSocket disconnection handler"
    }
    websocket_message = {
      handler     = "websocket_message.lambda_handler"
      timeout     = 30
      memory_size = 256
      description = "WebSocket message handler"
    }
    chat_processor = {
      handler     = "chat_processor.lambda_handler"
      timeout     = 120
      memory_size = 512
      description = "Chat message processor with Bedrock integration"
    }
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
    # NOTE: debt_analysis_agent_handler was removed - functionality merged into prediction_ensemble
    # NOTE: prediction_ensemble is now Docker-based (see prediction_ensemble_docker.tf)
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

  dead_letter_config {
    target_arn = var.dlq_arn
  }

  # Reserved concurrent executions (optional)
  reserved_concurrent_executions = lookup(var.reserved_concurrency, each.key, -1)

  tags = merge(
    var.common_tags,
    {
      Name     = "${var.project_name}-${var.environment}-${replace(each.key, "_", "-")}"
      Function = each.key
      Type     = contains(["websocket_connect", "websocket_disconnect", "websocket_message"], each.key) ? "WebSocket" : "HTTP"
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
# SQS Event Source Mapping for Chat Processor
# ================================================

resource "aws_lambda_event_source_mapping" "chat_processor_sqs" {
  count = contains(keys(local.lambda_configs), "chat_processor") ? 1 : 0

  event_source_arn = var.chat_processing_queue_arn
  function_name    = aws_lambda_function.functions["chat_processor"].arn
  
  batch_size                         = 1
  maximum_batching_window_in_seconds = var.sqs_batch_window
  
  scaling_config {
    maximum_concurrency = var.sqs_max_concurrency
  }
  
  function_response_types = ["ReportBatchItemFailures"]
}