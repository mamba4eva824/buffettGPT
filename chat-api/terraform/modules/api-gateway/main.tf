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
    allow_credentials = false
    allow_headers = [
      "content-type",
      "x-amz-date",
      "authorization",
      "x-api-key",
      "x-amz-security-token",
      "x-amz-user-agent",
      "x-session-id"
    ]
    allow_methods = [
      "GET",
      "POST", 
      "OPTIONS"
    ]
    allow_origins = [
      "*"  # For development - restrict in production
    ]
    expose_headers = [
      "x-session-id",
      "x-request-id"
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
  count                             = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
  api_id                            = aws_apigatewayv2_api.http_api.id
  authorizer_type                   = "REQUEST"
  authorizer_uri                    = var.authorizer_function_arn
  name                              = "${local.resource_prefix}-http-jwt-authorizer"
  authorizer_payload_format_version = "2.0"
  enable_simple_responses           = true
  identity_sources                  = ["$request.header.Authorization"]
}

resource "aws_apigatewayv2_authorizer" "websocket_jwt_authorizer" {
  count                      = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
  api_id                     = aws_apigatewayv2_api.websocket_api.id
  authorizer_type            = "REQUEST"
  authorizer_uri             = var.authorizer_function_arn
  name                       = "${local.resource_prefix}-websocket-jwt-authorizer"
  identity_sources           = ["route.request.header.Authorization", "route.request.querystring.token"]
  authorizer_credentials_arn = aws_iam_role.authorizer_invocation_role[0].arn
}

# IAM Role for Authorizer Invocation (WebSocket)
resource "aws_iam_role" "authorizer_invocation_role" {
  count = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
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
  count = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
  name  = "${local.resource_prefix}-authorizer-invocation-policy"
  role  = aws_iam_role.authorizer_invocation_role[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "lambda:InvokeFunction"
        Resource = var.authorizer_function_arn
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

# Routes
resource "aws_apigatewayv2_route" "chat_post_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = var.enable_authorization && var.authorizer_function_arn != null ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization && var.authorizer_function_arn != null ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
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

  authorization_type = var.enable_authorization && var.authorizer_function_arn != null ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization && var.authorizer_function_arn != null ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
}

resource "aws_apigatewayv2_route" "chat_options_route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "OPTIONS /chat"
  target    = "integrations/${aws_apigatewayv2_integration.chat_lambda_integration.id}"

  authorization_type = "NONE"
}

# ================================================
# Auth Callback Routes and Integration
# ================================================

# Auth Callback Integration (conditional)
resource "aws_apigatewayv2_integration" "auth_callback_integration" {
  count            = var.auth_callback_function_arn != null ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_uri        = var.auth_callback_function_arn
  payload_format_version = "2.0"
}

# POST /auth/callback route
resource "aws_apigatewayv2_route" "auth_callback_post_route" {
  count     = var.auth_callback_function_arn != null ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /auth/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_callback_integration[0].id}"

  authorization_type = "NONE"  # No auth for the callback itself
}

# OPTIONS /auth/callback route for CORS
resource "aws_apigatewayv2_route" "auth_callback_options_route" {
  count     = var.auth_callback_function_arn != null ? 1 : 0
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

  authorization_type = var.enable_authorization && var.authorizer_function_arn != null ? "CUSTOM" : "NONE"
  authorizer_id      = var.enable_authorization && var.authorizer_function_arn != null ? aws_apigatewayv2_authorizer.websocket_jwt_authorizer[0].id : null
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
  count         = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
  statement_id  = "AllowHTTPAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id}"
}

resource "aws_lambda_permission" "websocket_authorizer_permission" {
  count         = var.enable_authorization && var.authorizer_function_arn != null ? 1 : 0
  statement_id  = "AllowWebSocketAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.authorizer_function_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/authorizers/${aws_apigatewayv2_authorizer.websocket_jwt_authorizer[0].id}"
}