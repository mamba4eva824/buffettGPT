# Lambda Function URLs for SSE Streaming Handlers
# These bypass API Gateway to enable response streaming (SSE)

# NOTE: Prediction Ensemble Function URL is defined in prediction_ensemble_docker.tf (Docker-based)

# Analysis Followup Function URL
# SECURITY NOTE: authorization_type is NONE because this is an HTTP_PROXY target
# for API Gateway REST API, which handles JWT auth via its own TOKEN authorizer.
# The Lambda handler ALSO validates JWT independently (analysis_followup.py:794)
# so direct Function URL access without a valid JWT returns 401.
# See docs/api/SECURITY_REVIEW.md CRIT-2 for full analysis.
resource "aws_lambda_function_url" "analysis_followup" {
  function_name      = aws_lambda_function.functions["analysis_followup"].function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["POST"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }
}

# Market Intelligence Chat Function URL
# Same pattern as analysis_followup: NONE auth (JWT validated inside Lambda),
# RESPONSE_STREAM for SSE streaming via Python generator.
resource "aws_lambda_function_url" "market_intel_chat" {
  function_name      = aws_lambda_function.functions["market_intel_chat"].function_name
  authorization_type = "NONE"
  invoke_mode        = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = var.cors_allowed_origins
    allow_methods     = ["POST"]
    allow_headers     = ["content-type", "authorization"]
    expose_headers    = ["content-type"]
    max_age           = 86400
  }
}
