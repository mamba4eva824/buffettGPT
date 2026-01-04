# Lambda Function URLs for SSE Streaming Handlers
# These bypass API Gateway to enable response streaming (SSE)

# NOTE: Prediction Ensemble Function URL is defined in prediction_ensemble_docker.tf (Docker-based)

# Analysis Followup Function URL
resource "aws_lambda_function_url" "analysis_followup" {
  function_name      = aws_lambda_function.functions["analysis_followup"].function_name
  authorization_type = "NONE"  # JWT validation handled in Lambda handler
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
