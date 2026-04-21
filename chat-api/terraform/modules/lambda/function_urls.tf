# Lambda Function URLs for SSE Streaming Handlers
# These bypass API Gateway to enable response streaming (SSE)

# NOTE: Prediction Ensemble Function URL is defined in prediction_ensemble_docker.tf (Docker-based)

# Analysis Followup Function URL moved to analysis_followup_docker.tf
# (Docker+LWA migration: Python zip runtime can't serialize generators).

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
