# API Gateway Module
# Manages HTTP and WebSocket API Gateway resources

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
        "http://127.0.0.1:5173"   # Alternative localhost
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
# WebSocket API Gateway
# ================================================

resource "aws_apigatewayv2_api" "websocket_api" {
  name                       = "${local.resource_prefix}-websocket-api"
  protocol_type              = "WEBSOCKET"
  description                = "WebSocket API for ${var.project_name} real-time chat"
  route_selection_expression = "$request.body.action"

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-api"
      Purpose = "Chat WebSocket API Gateway"
      Service = "API Gateway"
    }
  )
}

# WebSocket API Stage
resource "aws_apigatewayv2_stage" "websocket_stage" {
  api_id      = aws_apigatewayv2_api.websocket_api.id
  name        = var.environment
  auto_deploy = true

  default_route_settings {
    detailed_metrics_enabled = true
    data_trace_enabled       = var.environment != "prod"
    throttling_burst_limit   = var.environment == "prod" ? 2000 : 500
    throttling_rate_limit    = var.environment == "prod" ? 1000 : 100
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-stage"
      Purpose = "Chat WebSocket API Stage"
      Service = "API Gateway"
    }
  )
}

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

resource "aws_cloudwatch_log_group" "websocket_api_logs" {
  name              = "/aws/apigateway/${local.resource_prefix}-websocket-api"
  retention_in_days = var.environment == "prod" ? 90 : 30

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-api-logs"
      Purpose = "WebSocket API Gateway access logs"
      Service = "CloudWatch Logs"
    }
  )
}

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

resource "aws_apigatewayv2_authorizer" "websocket_jwt_authorizer" {
  count                      = var.enable_authorization ? 1 : 0
  api_id                     = aws_apigatewayv2_api.websocket_api.id
  authorizer_type            = "REQUEST"
  authorizer_uri             = var.authorizer_function_arn
  name                       = "${local.resource_prefix}-websocket-jwt-authorizer"
  # Remove identity_sources to ensure authorizer is called for all connections (including anonymous)
  # identity_sources           = ["route.request.header.Authorization", "route.request.querystring.token"]
  authorizer_credentials_arn = aws_iam_role.authorizer_invocation_role[0].arn
}

# IAM Role for Authorizer Invocation (WebSocket)
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
      Purpose = "WebSocket authorizer invocation"
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

# Lambda Integrations
resource "aws_apigatewayv2_integration" "chat_lambda_integration" {
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["chat_http_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000

  request_parameters = {
    "overwrite:header.x-request-id" = "$request.header.x-request-id"
  }
}

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

# Routes
resource "aws_apigatewayv2_route" "chat_post_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

resource "aws_apigatewayv2_route" "health_get_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /health"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "history_get_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /api/v1/chat/history/{session_id}"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

resource "aws_apigatewayv2_route" "chat_options_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = "NONE"
}

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
# WebSocket Routes and Integrations
# ================================================

# WebSocket Integrations
resource "aws_apigatewayv2_integration" "websocket_connect_integration" {
  api_id           = aws_apigatewayv2_api.websocket_api.id
  integration_type = "AWS_PROXY"
  
  integration_method     = "POST"
  integration_uri        = var.lambda_arns["websocket_connect"]
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_integration" "websocket_disconnect_integration" {
  api_id           = aws_apigatewayv2_api.websocket_api.id
  integration_type = "AWS_PROXY"
  
  integration_method     = "POST"
  integration_uri        = var.lambda_arns["websocket_disconnect"]
  payload_format_version = "1.0"
}

resource "aws_apigatewayv2_integration" "websocket_message_integration" {
  api_id           = aws_apigatewayv2_api.websocket_api.id
  integration_type = "AWS_PROXY"
  
  integration_method     = "POST"
  integration_uri        = var.lambda_arns["websocket_message"]
  payload_format_version = "1.0"
}

# WebSocket Routes
resource "aws_apigatewayv2_route" "websocket_connect_route" {
  api_id    = aws_apigatewayv2_api.websocket_api.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_connect_integration.id}"

  authorization_type = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization ? aws_apigatewayv2_authorizer.websocket_jwt_authorizer[0].id : null
}

resource "aws_apigatewayv2_route" "websocket_disconnect_route" {
  api_id    = aws_apigatewayv2_api.websocket_api.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_disconnect_integration.id}"

  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "websocket_message_route" {
  api_id    = aws_apigatewayv2_api.websocket_api.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_message_integration.id}"

  authorization_type = "NONE"
}

resource "aws_apigatewayv2_route" "websocket_ping_route" {
  api_id    = aws_apigatewayv2_api.websocket_api.id
  route_key = "ping"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_message_integration.id}"

  authorization_type = "NONE"
}

# ================================================
# Lambda Permissions
# ================================================

resource "aws_lambda_permission" "http_api_lambda_permission" {
  statement_id  = "AllowExecutionFromHTTPAPI"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["chat_http_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

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

resource "aws_lambda_permission" "websocket_connect_permission" {
  statement_id  = "AllowExecutionFromWebSocketConnect"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["websocket_connect"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "websocket_disconnect_permission" {
  statement_id  = "AllowExecutionFromWebSocketDisconnect"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["websocket_disconnect"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "websocket_message_permission" {
  statement_id  = "AllowExecutionFromWebSocketMessage"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["websocket_message"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/*/*"
}

# Authorizer permissions
resource "aws_lambda_permission" "http_authorizer_permission" {
  count         = var.enable_authorization ? 1 : 0
  statement_id  = "AllowHTTPAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id}"
}

resource "aws_lambda_permission" "websocket_authorizer_permission" {
  count         = var.enable_authorization ? 1 : 0
  statement_id  = "AllowWebSocketAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.websocket_jwt_authorizer[0].id}"
}