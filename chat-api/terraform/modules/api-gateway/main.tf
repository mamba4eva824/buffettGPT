# API Gateway Module
# Manages HTTP API Gateway resources (WebSocket removed 2026-02)

locals {
  resource_prefix = "${var.project_name}-${var.environment}"
}

# ================================================
# HTTP API Gateway
# ================================================

resource "aws_apigatewayv2_api" "http_api" {
  name          = "${local.resource_prefix}-http-api"
  protocol_type = "HTTP"
  description   = "HTTP API for ${var.project_name} chat functionality"

  cors_configuration {
    allow_credentials = true  # Required for authenticated requests
    allow_headers = [
      "content-type",
      "x-amz-date",
      "authorization",
      "x-api-key",
      "x-amz-security-token",
      "x-amz-user-agent",
      "x-session-id",
      "x-conversation-id"
    ]
    allow_methods = [
      "GET",
      "POST",
      "PUT",
      "DELETE",
      "OPTIONS"
    ]
    allow_origins = concat(
      var.cloudfront_url != "" ? [var.cloudfront_url] : [],
      var.environment == "prod" ? [] : [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:5174",  # Alternative Vite port
        "http://localhost:3000",  # Alternative dev port
        "http://localhost:4173",  # Vite preview
        "http://localhost:8000",  # Alternative dev port
        "http://127.0.0.1:5173", # Alternative localhost
        "http://127.0.0.1:8000"  # Alternative localhost
      ]
    )
    expose_headers = [
      "x-session-id",
      "x-request-id",
      "x-conversation-id"
    ]
    max_age = 86400  # 24 hours
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-http-api"
      Purpose = "Chat HTTP API Gateway"
      Service = "API Gateway"
    }
  )
}

# HTTP API Stage
resource "aws_apigatewayv2_stage" "http_api_stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = var.environment
  auto_deploy = true

  default_route_settings {
    detailed_metrics_enabled = true
    logging_level            = "INFO"
    data_trace_enabled       = var.environment != "prod"
    throttling_burst_limit   = var.environment == "prod" ? 2000 : 500
    throttling_rate_limit    = var.environment == "prod" ? 1000 : 100
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway_logs.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip               = "$context.identity.sourceIp"
      caller           = "$context.identity.caller"
      user             = "$context.identity.user"
      requestTime      = "$context.requestTime"
      httpMethod       = "$context.httpMethod"
      resourcePath     = "$context.resourcePath"
      status           = "$context.status"
      protocol         = "$context.protocol"
      responseLength   = "$context.responseLength"
      error            = "$context.error.message"
      integrationError = "$context.integration.error"
    })
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-http-api-stage"
      Purpose = "Chat HTTP API Stage"
      Service = "API Gateway"
    }
  )
}

# ================================================
# WebSocket API Gateway - REMOVED (2026-02)
# ================================================
# WebSocket infrastructure deprecated per WEBSOCKET_DEPRECATION_PLAN.md
# All chat functionality now uses REST+SSE via Research and Follow-up APIs

# ================================================
# CloudWatch Log Groups
# ================================================

resource "aws_cloudwatch_log_group" "api_gateway_logs" {
  name              = "/aws/apigateway/${local.resource_prefix}-http-api"
  retention_in_days = var.environment == "prod" ? 90 : 30

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-api-gateway-logs"
      Purpose = "HTTP API Gateway access logs"
      Service = "CloudWatch Logs"
    }
  )
}

# WebSocket API logs - REMOVED (2026-02)

# ================================================
# Authorizers (if authentication is enabled)
# ================================================

resource "aws_apigatewayv2_authorizer" "http_jwt_authorizer" {
  count                             = var.enable_authorization ? 1 : 0
  api_id                            = aws_apigatewayv2_api.http_api.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = var.authorizer_function_arn
  name                              = "${local.resource_prefix}-http-jwt-authorizer"
  authorizer_payload_format_version = "2.0"
  authorizer_credentials_arn        = aws_iam_role.authorizer_invocation_role[0].arn
  identity_sources                  = ["$request.header.Authorization"]
  enable_simple_responses           = true
}

# WebSocket JWT authorizer - REMOVED (2026-02)

# IAM Role for Authorizer Invocation (HTTP API)
resource "aws_iam_role" "authorizer_invocation_role" {
  count = var.enable_authorization ? 1 : 0
  name  = "${local.resource_prefix}-authorizer-invocation-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-authorizer-invocation-role"
      Purpose = "HTTP API authorizer invocation"
      Service = "IAM"
    }
  )
}

resource "aws_iam_role_policy" "authorizer_invocation_policy" {
  count = var.enable_authorization ? 1 : 0
  name  = "${local.resource_prefix}-authorizer-invocation-policy"
  role  = aws_iam_role.authorizer_invocation_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = var.authorizer_function_arn_for_iam
      }
    ]
  })
}

# ================================================
# HTTP API Routes and Integrations
# ================================================

# Chat HTTP handler integration - REMOVED (2026-02)
# chat_http_handler deprecated - chat functionality uses Research + Follow-up APIs

# Conversations Handler Integration
resource "aws_apigatewayv2_integration" "conversations_handler_integration" {
  count            = var.enable_conversations_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["conversations_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# Search Handler Integration
resource "aws_apigatewayv2_integration" "search_integration" {
  count            = var.enable_search ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["search_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000  # API Gateway max is 30000ms (30 seconds)

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# Chat routes - REMOVED (2026-02)
# POST /chat, GET /health, GET /api/v1/chat/history routes deprecated
# Chat functionality now uses /research and /analysis/followup endpoints

# ================================================
# Conversations API Routes
# ================================================

# GET /conversations - List all conversations
resource "aws_apigatewayv2_route" "list_conversations" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /conversations"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# POST /conversations - Create new conversation
resource "aws_apigatewayv2_route" "create_conversation" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /conversations"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# GET /conversations/{conversation_id} - Get specific conversation
resource "aws_apigatewayv2_route" "get_conversation" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /conversations/{conversation_id}"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# PUT /conversations/{conversation_id} - Update conversation
resource "aws_apigatewayv2_route" "update_conversation" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "PUT /conversations/{conversation_id}"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# DELETE /conversations/{conversation_id} - Delete conversation
resource "aws_apigatewayv2_route" "delete_conversation" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "DELETE /conversations/{conversation_id}"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# GET /conversations/{conversation_id}/messages - Get conversation messages
resource "aws_apigatewayv2_route" "get_conversation_messages" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /conversations/{conversation_id}/messages"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# POST /conversations/{conversation_id}/messages - Save message to conversation
resource "aws_apigatewayv2_route" "save_conversation_message" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /conversations/{conversation_id}/messages"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# OPTIONS /conversations - CORS preflight
resource "aws_apigatewayv2_route" "conversations_options" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /conversations"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /conversations/{conversation_id} - CORS preflight
resource "aws_apigatewayv2_route" "conversation_options" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /conversations/{conversation_id}"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = "NONE"
}

# ================================================
# Search API Routes
# ================================================

# POST /search - AI-powered search
resource "aws_apigatewayv2_route" "search" {
  count     = var.enable_search ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /search"
  target    = "integrations/${aws_apigatewayv2_integration.search_integration[0].id}"

  authorization_type = "NONE"  # No auth required for dev
}

# OPTIONS /search - CORS preflight
resource "aws_apigatewayv2_route" "search_options" {
  count     = var.enable_search ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /search"
  target    = "integrations/${aws_apigatewayv2_integration.search_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /conversations/{conversation_id}/messages - CORS preflight
resource "aws_apigatewayv2_route" "conversation_messages_options" {
  count     = var.enable_conversations_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /conversations/{conversation_id}/messages"
  target    = "integrations/${aws_apigatewayv2_integration.conversations_handler_integration[0].id}"

  authorization_type = "NONE"
}

# ================================================
# Auth Callback Routes and Integration
# ================================================

# Auth Callback Integration (conditional)
resource "aws_apigatewayv2_integration" "auth_callback_integration" {
  count            = var.enable_auth_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_uri        = var.auth_callback_function_arn
  payload_format_version = "2.0"
}

# POST /auth/callback route
resource "aws_apigatewayv2_route" "auth_callback_post_route" {
  count     = var.enable_auth_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /auth/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_callback_integration[0].id}"

  authorization_type = "NONE"  # No auth for the callback itself
}

# OPTIONS /auth/callback route for CORS
resource "aws_apigatewayv2_route" "auth_callback_options_route" {
  count     = var.enable_auth_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /auth/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_callback_integration[0].id}"

  authorization_type = "NONE"
}

# ================================================
# WebSocket Routes and Integrations - REMOVED (2026-02)
# ================================================
# All WebSocket infrastructure deprecated per WEBSOCKET_DEPRECATION_PLAN.md

# ================================================
# Lambda Permissions
# ================================================

# HTTP API chat_http_handler permission - REMOVED (2026-02)

# Conversations Handler Lambda Permission
resource "aws_lambda_permission" "conversations_api_permission" {
  count         = var.enable_conversations_routes ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPIConversations"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["conversations_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# Search Handler Lambda Permission
resource "aws_lambda_permission" "search_api_permission" {
  count         = var.enable_search ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPISearch"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["search_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# WebSocket Lambda permissions - REMOVED (2026-02)

# Authorizer permissions
resource "aws_lambda_permission" "http_authorizer_permission" {
  count         = var.enable_authorization ? 1 : 0
  statement_id  = "AllowHTTPAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id}"
}

# WebSocket authorizer permission - REMOVED (2026-02)

# ================================================
# Subscription API Routes and Integrations
# ================================================

# Subscription Handler Integration
resource "aws_apigatewayv2_integration" "subscription_handler_integration" {
  count            = var.enable_subscription_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["subscription_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# POST /subscription/checkout - Create Stripe Checkout session
resource "aws_apigatewayv2_route" "subscription_checkout" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /subscription/checkout"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# POST /subscription/portal - Create Stripe Customer Portal session
resource "aws_apigatewayv2_route" "subscription_portal" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /subscription/portal"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# GET /subscription/status - Get subscription status
resource "aws_apigatewayv2_route" "subscription_status" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /subscription/status"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

# OPTIONS /subscription/checkout - CORS preflight
resource "aws_apigatewayv2_route" "subscription_checkout_options" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /subscription/checkout"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /subscription/portal - CORS preflight
resource "aws_apigatewayv2_route" "subscription_portal_options" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /subscription/portal"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /subscription/status - CORS preflight
resource "aws_apigatewayv2_route" "subscription_status_options" {
  count     = var.enable_subscription_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /subscription/status"
  target    = "integrations/${aws_apigatewayv2_integration.subscription_handler_integration[0].id}"

  authorization_type = "NONE"
}

# Subscription Handler Lambda Permission
resource "aws_lambda_permission" "subscription_api_permission" {
  count         = var.enable_subscription_routes ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPISubscription"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["subscription_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# ================================================
# Stripe Webhook Route and Integration
# ================================================

# Stripe Webhook Handler Integration
resource "aws_apigatewayv2_integration" "stripe_webhook_integration" {
  count            = var.enable_stripe_webhook ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["stripe_webhook_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# POST /stripe/webhook - Stripe webhook endpoint (NO AUTH - Stripe signs requests)
resource "aws_apigatewayv2_route" "stripe_webhook" {
  count     = var.enable_stripe_webhook ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /stripe/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.stripe_webhook_integration[0].id}"

  # No authorization - Stripe uses webhook signature verification
  authorization_type = "NONE"
}

# Stripe Webhook Handler Lambda Permission
resource "aws_lambda_permission" "stripe_webhook_api_permission" {
  count         = var.enable_stripe_webhook ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPIStripeWebhook"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["stripe_webhook_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# ================================================
# Waitlist API Routes and Integration
# ================================================

# Waitlist Handler Integration
resource "aws_apigatewayv2_integration" "waitlist_handler_integration" {
  count            = var.enable_waitlist_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["waitlist_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# POST /waitlist/signup - Sign up for waitlist (NO AUTH - public)
resource "aws_apigatewayv2_route" "waitlist_signup" {
  count     = var.enable_waitlist_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /waitlist/signup"
  target    = "integrations/${aws_apigatewayv2_integration.waitlist_handler_integration[0].id}"

  authorization_type = "NONE"
}

# GET /waitlist/status - Get waitlist position and referral dashboard (NO AUTH - email+code based)
resource "aws_apigatewayv2_route" "waitlist_status" {
  count     = var.enable_waitlist_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /waitlist/status"
  target    = "integrations/${aws_apigatewayv2_integration.waitlist_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /waitlist/signup - CORS preflight
resource "aws_apigatewayv2_route" "waitlist_signup_options" {
  count     = var.enable_waitlist_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /waitlist/signup"
  target    = "integrations/${aws_apigatewayv2_integration.waitlist_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /waitlist/status - CORS preflight
resource "aws_apigatewayv2_route" "waitlist_status_options" {
  count     = var.enable_waitlist_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /waitlist/status"
  target    = "integrations/${aws_apigatewayv2_integration.waitlist_handler_integration[0].id}"

  authorization_type = "NONE"
}

# GET /waitlist/unsubscribe - Email unsubscribe (NO AUTH - token-verified)
resource "aws_apigatewayv2_route" "waitlist_unsubscribe" {
  count     = var.enable_waitlist_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /waitlist/unsubscribe"
  target    = "integrations/${aws_apigatewayv2_integration.waitlist_handler_integration[0].id}"

  authorization_type = "NONE"
}

# Waitlist Handler Lambda Permission
resource "aws_lambda_permission" "waitlist_api_permission" {
  count         = var.enable_waitlist_routes ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPIWaitlist"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["waitlist_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# ================================================
# Value Insights API Routes and Integration
# ================================================

# Value Insights Handler Integration
resource "aws_apigatewayv2_integration" "value_insights_handler_integration" {
  count            = var.enable_value_insights_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["value_insights_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

# GET /insights/{ticker} - Get financial metrics and ratings
resource "aws_apigatewayv2_route" "value_insights_get" {
  count     = var.enable_value_insights_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /insights/{ticker}"
  target    = "integrations/${aws_apigatewayv2_integration.value_insights_handler_integration[0].id}"

  authorization_type = "NONE"
}

# OPTIONS /insights/{ticker} - CORS preflight
resource "aws_apigatewayv2_route" "value_insights_options" {
  count     = var.enable_value_insights_routes ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /insights/{ticker}"
  target    = "integrations/${aws_apigatewayv2_integration.value_insights_handler_integration[0].id}"

  authorization_type = "NONE"
}

# Value Insights Handler Lambda Permission
resource "aws_lambda_permission" "value_insights_api_permission" {
  count         = var.enable_value_insights_routes ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPIValueInsights"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["value_insights_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}