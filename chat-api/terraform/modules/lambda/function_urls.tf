# Lambda Function URLs for SSE Streaming Handlers
# These bypass API Gateway to enable response streaming (SSE)

# Ensemble Analyzer Function URL
resource "aws_lambda_function_url" "ensemble_analyzer" {
  function_name      = aws_lambda_function.functions["ensemble_analyzer"].function_name
  authorization_type = "NONE"  # JWT validation handled in Lambda handler
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["POST", "OPTIONS"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }
}

# Analysis Followup Function URL
resource "aws_lambda_function_url" "analysis_followup" {
  function_name      = aws_lambda_function.functions["analysis_followup"].function_name
  authorization_type = "NONE"  # JWT validation handled in Lambda handler
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["POST", "OPTIONS"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }
}
