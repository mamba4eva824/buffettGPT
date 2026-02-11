# REST API for Investment Research
# Provides SSE streaming with centralized JWT authentication
# NOTE: Analysis/ensemble routes were removed and archived (2025-01)

locals {
  analysis_resource_prefix = "${var.project_name}-${var.environment}"
}

# REST API

resource "aws_api_gateway_rest_api" "analysis" {
  count       = var.enable_analysis_api ? 1 : 0
  name        = "${local.analysis_resource_prefix}-analysis-api"
  description = "Streaming API for investment research"

  endpoint_configuration {
    types = ["REGIONAL"]  # Direct regional deployment in us-east-1, no CloudFront
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.analysis_resource_prefix}-analysis-api"
      Purpose = "Streaming Research REST API"
      Service = "API Gateway"
    }
  )
}

# ============================================================================
# JWT Authorizer (reuses existing auth_verify Lambda)
# ============================================================================

resource "aws_api_gateway_authorizer" "analysis_jwt" {
  count                            = var.enable_analysis_api && var.enable_authorization ? 1 : 0
  name                             = "${local.analysis_resource_prefix}-analysis-jwt-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.analysis[0].id
  type                             = "TOKEN"
  authorizer_uri                   = var.auth_verify_invoke_arn
  authorizer_credentials           = aws_iam_role.authorizer_invocation_role[0].arn
  identity_source                  = "method.request.header.Authorization"
  authorizer_result_ttl_in_seconds = 300  # Cache auth results for 5 minutes
}

# ============================================================================
# Deployment and Stage
# ============================================================================

resource "aws_api_gateway_deployment" "analysis" {
  count       = var.enable_analysis_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id

  triggers = {
    redeployment = sha1(jsonencode([
      # Gateway responses
      aws_api_gateway_gateway_response.analysis_default_4xx[0].id,
      aws_api_gateway_gateway_response.analysis_default_5xx[0].id,
      # Investment Research API resources (conditional)
      try(aws_api_gateway_resource.research[0].id, ""),
      try(aws_api_gateway_resource.research_report[0].id, ""),
      try(aws_api_gateway_resource.research_report_ticker[0].id, ""),
      try(aws_api_gateway_resource.research_report_stream[0].id, ""),
      try(aws_api_gateway_method.research_stream_get[0].id, ""),
      try(aws_api_gateway_integration.research_stream_lambda[0].id, ""),
      try(aws_api_gateway_integration.research_stream_lambda[0].uri, ""),
      try(aws_api_gateway_method.research_stream_options[0].id, ""),
      try(aws_api_gateway_integration.research_stream_options[0].id, ""),
      # Research Follow-up API resources
      try(aws_api_gateway_resource.research_followup[0].id, ""),
      try(aws_api_gateway_method.research_followup_post[0].id, ""),
      try(aws_api_gateway_integration.research_followup_lambda[0].id, ""),
      try(aws_api_gateway_integration.research_followup_lambda[0].uri, ""),
      try(aws_api_gateway_method.research_followup_options[0].id, ""),
      try(aws_api_gateway_integration.research_followup_options[0].id, ""),
      # Research Status API resources
      try(aws_api_gateway_resource.research_report_status[0].id, ""),
      try(aws_api_gateway_method.research_status_get[0].id, ""),
      try(aws_api_gateway_integration.research_status_lambda[0].id, ""),
      try(aws_api_gateway_integration.research_status_lambda[0].uri, ""),
      try(aws_api_gateway_method.research_status_options[0].id, ""),
      try(aws_api_gateway_integration.research_status_options[0].id, ""),
      # Research Section API resources
      try(aws_api_gateway_resource.research_report_section[0].id, ""),
      try(aws_api_gateway_resource.research_report_section_id[0].id, ""),
      try(aws_api_gateway_method.research_section_get[0].id, ""),
      try(aws_api_gateway_integration.research_section_lambda[0].id, ""),
      try(aws_api_gateway_integration.research_section_lambda[0].uri, ""),
      try(aws_api_gateway_method.research_section_options[0].id, ""),
      try(aws_api_gateway_integration.research_section_options[0].id, ""),
      # Research Batch Sections API resources
      try(aws_api_gateway_resource.research_report_sections_batch[0].id, ""),
      try(aws_api_gateway_method.research_sections_batch_post[0].id, ""),
      try(aws_api_gateway_integration.research_sections_batch_lambda[0].id, ""),
      try(aws_api_gateway_integration.research_sections_batch_lambda[0].uri, ""),
      try(aws_api_gateway_method.research_sections_batch_options[0].id, ""),
      try(aws_api_gateway_integration.research_sections_batch_options[0].id, ""),
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_gateway_response.analysis_default_4xx,
    aws_api_gateway_gateway_response.analysis_default_5xx,
    aws_api_gateway_integration.research_stream_lambda,
    aws_api_gateway_integration.research_stream_options,
    aws_api_gateway_integration.research_followup_lambda,
    aws_api_gateway_integration.research_followup_options,
    aws_api_gateway_integration.research_status_lambda,
    aws_api_gateway_integration.research_status_options,
    aws_api_gateway_integration.research_section_lambda,
    aws_api_gateway_integration.research_section_options,
    aws_api_gateway_integration.research_sections_batch_lambda,
    aws_api_gateway_integration.research_sections_batch_options
  ]
}

resource "aws_api_gateway_stage" "analysis" {
  count         = var.enable_analysis_api ? 1 : 0
  deployment_id = aws_api_gateway_deployment.analysis[0].id
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  stage_name    = var.environment

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.analysis_resource_prefix}-analysis-stage"
      Purpose = "Streaming Analysis API Stage"
      Service = "API Gateway"
    }
  )
}

# ============================================================================
# Gateway Responses (CORS on errors)
# Required for browsers to receive error responses from API Gateway
# ============================================================================

resource "aws_api_gateway_gateway_response" "analysis_default_4xx" {
  count       = var.enable_analysis_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  response_type = "DEFAULT_4XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
  }
}

resource "aws_api_gateway_gateway_response" "analysis_default_5xx" {
  count       = var.enable_analysis_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  response_type = "DEFAULT_5XX"

  response_parameters = {
    "gatewayresponse.header.Access-Control-Allow-Origin"  = "'*'"
    "gatewayresponse.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token'"
    "gatewayresponse.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
  }
}

# ============================================================================
# CloudWatch Logging for REST API
# ============================================================================

resource "aws_cloudwatch_log_group" "analysis_api_logs" {
  count             = var.enable_analysis_api ? 1 : 0
  name              = "/aws/apigateway/${local.analysis_resource_prefix}-analysis-api"
  retention_in_days = var.environment == "prod" ? 90 : 30

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.analysis_resource_prefix}-analysis-api-logs"
      Purpose = "Analysis API Gateway access logs"
      Service = "CloudWatch Logs"
    }
  )
}

# ============================================================================
# API Gateway Execution Logging (for debugging)
# Requires account-level IAM role for CloudWatch access
# ============================================================================

# IAM Role for API Gateway CloudWatch Logging
resource "aws_iam_role" "api_gateway_cloudwatch" {
  count = var.enable_analysis_api ? 1 : 0
  name  = "${local.analysis_resource_prefix}-apigw-cloudwatch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "apigateway.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  count      = var.enable_analysis_api ? 1 : 0
  role       = aws_iam_role.api_gateway_cloudwatch[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

# Account-level API Gateway CloudWatch settings
# Note: This is a singleton resource - only one per AWS account per region
resource "aws_api_gateway_account" "main" {
  count               = var.enable_analysis_api ? 1 : 0
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch[0].arn

  depends_on = [aws_iam_role_policy_attachment.api_gateway_cloudwatch]
}

# Enable execution logging for all methods
resource "aws_api_gateway_method_settings" "analysis" {
  count       = var.enable_analysis_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  stage_name  = aws_api_gateway_stage.analysis[0].stage_name
  method_path = "*/*"

  settings {
    logging_level      = "INFO"
    data_trace_enabled = true
    metrics_enabled    = true
  }

  depends_on = [aws_api_gateway_account.main]
}

# ============================================================================
# Lambda Permissions
# ============================================================================

# Note: Lambda invoke permission is NOT needed for HTTP_PROXY integration.
# HTTP_PROXY routes directly to the Lambda Function URL, which handles its own auth.
# The Function URL is public but effectively protected by the API Gateway JWT authorizer
# sitting in front of it.

# DEPRECATED - kept for reference:
# resource "aws_lambda_permission" "analysis_api_invoke" {
#   count         = var.enable_analysis_api ? 1 : 0
#   statement_id  = "AllowAPIGatewayInvokeAnalysis"
#   action        = "lambda:InvokeFunction"
#   function_name = var.ensemble_analyzer_function_name
#   principal     = "apigateway.amazonaws.com"
#   source_arn    = "${aws_api_gateway_rest_api.analysis[0].execution_arn}/*/*"
# }

# Permission for API Gateway to invoke authorizer Lambda
resource "aws_lambda_permission" "analysis_authorizer_invoke" {
  count         = var.enable_analysis_api && var.enable_authorization ? 1 : 0
  statement_id  = "AllowRESTAPIAuthorizerInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.auth_verify_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.analysis[0].execution_arn}/authorizers/${aws_api_gateway_authorizer.analysis_jwt[0].id}"
}

# ============================================================================
# Investment Research API Resources
# ============================================================================
# Provides SSE streaming for cached investment reports from DynamoDB.
# Uses the same JWT authorization as the analysis endpoints.
# ============================================================================

# /research resource
resource "aws_api_gateway_resource" "research" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_rest_api.analysis[0].root_resource_id
  path_part   = "research"
}

# /research/report resource
resource "aws_api_gateway_resource" "research_report" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research[0].id
  path_part   = "report"
}

# /research/report/{ticker} resource
resource "aws_api_gateway_resource" "research_report_ticker" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report[0].id
  path_part   = "{ticker}"
}

# /research/report/{ticker}/stream resource
resource "aws_api_gateway_resource" "research_report_stream" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report_ticker[0].id
  path_part   = "stream"
}

# ============================================================================
# GET Method with JWT Authorization
# ============================================================================

resource "aws_api_gateway_method" "research_stream_get" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_stream[0].id
  http_method   = "GET"
  authorization = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id = var.enable_authorization ? aws_api_gateway_authorizer.analysis_jwt[0].id : null

  request_parameters = {
    "method.request.path.ticker"          = true
    "method.request.header.Authorization" = false
    "method.request.header.Accept"        = false
  }
}

# ============================================================================
# HTTP_PROXY Integration to Investment Research Lambda Function URL
# ============================================================================

resource "aws_api_gateway_integration" "research_stream_lambda" {
  count                   = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.research_report_stream[0].id
  http_method             = aws_api_gateway_method.research_stream_get[0].http_method
  integration_http_method = "GET"
  type                    = "HTTP_PROXY"

  # Point to Investment Research Lambda Function URL
  uri = "${trimsuffix(var.investment_research_function_url, "/")}/report/{ticker}/stream"

  request_parameters = {
    "integration.request.path.ticker"          = "method.request.path.ticker"
    "integration.request.header.Authorization" = "method.request.header.Authorization"
    "integration.request.header.Accept"        = "method.request.header.Accept"
  }

  passthrough_behavior = "WHEN_NO_MATCH"
  timeout_milliseconds = 29000
}

# ============================================================================
# CORS Preflight (OPTIONS) for Research Stream
# ============================================================================

resource "aws_api_gateway_method" "research_stream_options" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_stream[0].id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "research_stream_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_stream[0].id
  http_method = aws_api_gateway_method.research_stream_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "research_stream_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_stream[0].id
  http_method = aws_api_gateway_method.research_stream_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "research_stream_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_stream[0].id
  http_method = aws_api_gateway_method.research_stream_options[0].http_method
  status_code = aws_api_gateway_method_response.research_stream_options[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,Accept'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = var.cloudfront_url != "" ? "'${var.cloudfront_url}'" : "'*'"
  }

  depends_on = [aws_api_gateway_integration.research_stream_options]
}

# ============================================================================
# /research/report/{ticker}/status - GET endpoint for report status check
# ============================================================================
# Used by frontend to check if a report exists and if it has expired.
# Supports efficient conversation loading with reference-only storage.
# ============================================================================

# /research/report/{ticker}/status resource
resource "aws_api_gateway_resource" "research_report_status" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report_ticker[0].id
  path_part   = "status"
}

# GET Method with JWT Authorization
resource "aws_api_gateway_method" "research_status_get" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_status[0].id
  http_method   = "GET"
  authorization = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id = var.enable_authorization ? aws_api_gateway_authorizer.analysis_jwt[0].id : null

  request_parameters = {
    "method.request.path.ticker"          = true
    "method.request.header.Authorization" = false
  }
}

# HTTP_PROXY Integration to Investment Research Lambda Function URL
resource "aws_api_gateway_integration" "research_status_lambda" {
  count                   = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.research_report_status[0].id
  http_method             = aws_api_gateway_method.research_status_get[0].http_method
  integration_http_method = "GET"
  type                    = "HTTP_PROXY"

  uri = "${trimsuffix(var.investment_research_function_url, "/")}/report/{ticker}/status"

  request_parameters = {
    "integration.request.path.ticker"          = "method.request.path.ticker"
    "integration.request.header.Authorization" = "method.request.header.Authorization"
  }

  passthrough_behavior = "WHEN_NO_MATCH"
  timeout_milliseconds = 10000
}

# CORS Preflight (OPTIONS) for Research Status
resource "aws_api_gateway_method" "research_status_options" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_status[0].id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "research_status_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_status[0].id
  http_method = aws_api_gateway_method.research_status_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "research_status_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_status[0].id
  http_method = aws_api_gateway_method.research_status_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "research_status_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_status[0].id
  http_method = aws_api_gateway_method.research_status_options[0].http_method
  status_code = aws_api_gateway_method_response.research_status_options[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = var.cloudfront_url != "" ? "'${var.cloudfront_url}'" : "'*'"
  }

  depends_on = [aws_api_gateway_integration.research_status_options]
}

# ============================================================================
# /research/report/{ticker}/section/{section_id} - GET endpoint for individual sections
# ============================================================================
# Used by frontend to fetch individual report sections on-demand.
# Enables reference-only storage optimization for conversations.
# ============================================================================

# /research/report/{ticker}/section resource
resource "aws_api_gateway_resource" "research_report_section" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report_ticker[0].id
  path_part   = "section"
}

# /research/report/{ticker}/section/{section_id} resource
resource "aws_api_gateway_resource" "research_report_section_id" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report_section[0].id
  path_part   = "{section_id}"
}

# GET Method with JWT Authorization
resource "aws_api_gateway_method" "research_section_get" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_section_id[0].id
  http_method   = "GET"
  authorization = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id = var.enable_authorization ? aws_api_gateway_authorizer.analysis_jwt[0].id : null

  request_parameters = {
    "method.request.path.ticker"          = true
    "method.request.path.section_id"      = true
    "method.request.header.Authorization" = false
  }
}

# HTTP_PROXY Integration to Investment Research Lambda Function URL
resource "aws_api_gateway_integration" "research_section_lambda" {
  count                   = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.research_report_section_id[0].id
  http_method             = aws_api_gateway_method.research_section_get[0].http_method
  integration_http_method = "GET"
  type                    = "HTTP_PROXY"

  uri = "${trimsuffix(var.investment_research_function_url, "/")}/report/{ticker}/section/{section_id}"

  request_parameters = {
    "integration.request.path.ticker"          = "method.request.path.ticker"
    "integration.request.path.section_id"      = "method.request.path.section_id"
    "integration.request.header.Authorization" = "method.request.header.Authorization"
  }

  passthrough_behavior = "WHEN_NO_MATCH"
  timeout_milliseconds = 10000
}

# CORS Preflight (OPTIONS) for Research Section
resource "aws_api_gateway_method" "research_section_options" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_section_id[0].id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "research_section_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_section_id[0].id
  http_method = aws_api_gateway_method.research_section_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "research_section_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_section_id[0].id
  http_method = aws_api_gateway_method.research_section_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "research_section_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_section_id[0].id
  http_method = aws_api_gateway_method.research_section_options[0].http_method
  status_code = aws_api_gateway_method_response.research_section_options[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = var.cloudfront_url != "" ? "'${var.cloudfront_url}'" : "'*'"
  }

  depends_on = [aws_api_gateway_integration.research_section_options]
}

# ============================================================================
# /research/report/{ticker}/sections - POST endpoint for batch section fetch
# ============================================================================
# Used by frontend to fetch multiple report sections in a single request.
# Replaces N individual GET /section/{id} calls with 1 POST.
# ============================================================================

# /research/report/{ticker}/sections resource
resource "aws_api_gateway_resource" "research_report_sections_batch" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research_report_ticker[0].id
  path_part   = "sections"
}

# POST Method with JWT Authorization
resource "aws_api_gateway_method" "research_sections_batch_post" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method   = "POST"
  authorization = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id = var.enable_authorization ? aws_api_gateway_authorizer.analysis_jwt[0].id : null

  request_parameters = {
    "method.request.path.ticker"          = true
    "method.request.header.Authorization" = false
  }
}

# HTTP_PROXY Integration to Investment Research Lambda Function URL
resource "aws_api_gateway_integration" "research_sections_batch_lambda" {
  count                   = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method             = aws_api_gateway_method.research_sections_batch_post[0].http_method
  integration_http_method = "POST"
  type                    = "HTTP_PROXY"

  uri = "${trimsuffix(var.investment_research_function_url, "/")}/report/{ticker}/sections"

  request_parameters = {
    "integration.request.path.ticker"          = "method.request.path.ticker"
    "integration.request.header.Authorization" = "method.request.header.Authorization"
  }

  passthrough_behavior = "WHEN_NO_MATCH"
  timeout_milliseconds = 10000
}

# CORS Preflight (OPTIONS) for Batch Sections
resource "aws_api_gateway_method" "research_sections_batch_options" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "research_sections_batch_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method = aws_api_gateway_method.research_sections_batch_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "research_sections_batch_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method = aws_api_gateway_method.research_sections_batch_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "research_sections_batch_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_report_sections_batch[0].id
  http_method = aws_api_gateway_method.research_sections_batch_options[0].http_method
  status_code = aws_api_gateway_method_response.research_sections_batch_options[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = var.cloudfront_url != "" ? "'${var.cloudfront_url}'" : "'*'"
  }

  depends_on = [aws_api_gateway_integration.research_sections_batch_options]
}

# ============================================================================
# /research/followup - POST endpoint for follow-up questions
# ============================================================================

# /research/followup resource
resource "aws_api_gateway_resource" "research_followup" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  parent_id   = aws_api_gateway_resource.research[0].id
  path_part   = "followup"
}

# POST Method with JWT Authorization
resource "aws_api_gateway_method" "research_followup_post" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_followup[0].id
  http_method   = "POST"
  authorization = var.enable_authorization ? "CUSTOM" : "NONE"
  authorizer_id = var.enable_authorization ? aws_api_gateway_authorizer.analysis_jwt[0].id : null

  request_parameters = {
    "method.request.header.Authorization" = false
    "method.request.header.Content-Type"  = false
  }
}

# HTTP_PROXY Integration to Lambda Function URL
resource "aws_api_gateway_integration" "research_followup_lambda" {
  count                   = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.research_followup[0].id
  http_method             = aws_api_gateway_method.research_followup_post[0].http_method
  integration_http_method = "POST"
  type                    = "HTTP_PROXY"

  uri = var.analysis_followup_function_url

  request_parameters = {
    "integration.request.header.Authorization" = "method.request.header.Authorization"
    "integration.request.header.Content-Type"  = "method.request.header.Content-Type"
  }

  passthrough_behavior = "WHEN_NO_MATCH"
  timeout_milliseconds = 29000
}

# CORS Preflight (OPTIONS) for Follow-up
resource "aws_api_gateway_method" "research_followup_options" {
  count         = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id   = aws_api_gateway_rest_api.analysis[0].id
  resource_id   = aws_api_gateway_resource.research_followup[0].id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "research_followup_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_followup[0].id
  http_method = aws_api_gateway_method.research_followup_options[0].http_method
  type        = "MOCK"

  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "research_followup_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_followup[0].id
  http_method = aws_api_gateway_method.research_followup_options[0].http_method
  status_code = "200"

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "research_followup_options" {
  count       = var.enable_analysis_api && var.enable_research_api ? 1 : 0
  rest_api_id = aws_api_gateway_rest_api.analysis[0].id
  resource_id = aws_api_gateway_resource.research_followup[0].id
  http_method = aws_api_gateway_method.research_followup_options[0].http_method
  status_code = aws_api_gateway_method_response.research_followup_options[0].status_code

  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization,Accept'"
    "method.response.header.Access-Control-Allow-Methods" = "'POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = var.cloudfront_url != "" ? "'${var.cloudfront_url}'" : "'*'"
  }

  depends_on = [aws_api_gateway_integration.research_followup_options]
}
