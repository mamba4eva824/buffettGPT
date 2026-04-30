# Lambda Function URLs for SSE Streaming Handlers
# These bypass API Gateway to enable response streaming (SSE)

# NOTE: Prediction Ensemble Function URL is defined in prediction_ensemble_docker.tf (Docker-based)

# Analysis Followup Function URL — zip variant (used when create_analysis_followup_docker=false).
# Docker variant lives in analysis_followup_docker.tf. Python zip runtime can't serialize
# generators for true streaming; staging keeps zip until ECR image is pushed.
resource "aws_lambda_function_url" "analysis_followup" {
  count              = var.create_analysis_followup_docker ? 0 : 1
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
# NONE auth (JWT validated inside Lambda), RESPONSE_STREAM for SSE streaming via Python generator.
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
