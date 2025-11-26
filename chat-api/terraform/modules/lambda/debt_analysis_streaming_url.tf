# ============================================================================
# Lambda Function URL for Streaming Debt Analysis
# Enables SSE (Server-Sent Events) streaming without API Gateway
# ============================================================================

resource "aws_lambda_function_url" "debt_analysis_streaming" {
  function_name      = aws_lambda_function.functions["debt_analysis_agent_handler"].function_name
  authorization_type = "NONE"  # Public access with CORS protection

  # Use RESPONSE_STREAM mode for TRUE real-time streaming
  # Lambda handler returns generator that yields chunks as they arrive from Bedrock
  # Python 3.11 runtime includes awslambdaric library for streaming support
  invoke_mode = "RESPONSE_STREAM"

  cors {
    allow_credentials = true
    allow_origins     = concat(
      # Production origins
      var.cloudfront_url != "" ? [var.cloudfront_url] : [],
      # Development origins (only in dev/staging)
      var.environment == "prod" ? [] : [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:5173",
        "http://localhost:5174"
      ]
    )
    allow_methods = ["POST"]
    allow_headers = ["content-type", "authorization", "x-session-id"]
    expose_headers = ["x-session-id"]
    max_age       = 86400  # 24 hours
  }
}

# ============================================================================
# CloudWatch Log Group for Function URL Access Logs (Optional)
# ============================================================================

resource "aws_cloudwatch_log_group" "debt_analysis_streaming_access" {
  name              = "/aws/lambda-url/${aws_lambda_function.functions["debt_analysis_agent_handler"].function_name}"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(var.common_tags, {
    Name    = "debt-analysis-streaming-access-logs"
    Purpose = "Function URL access logs"
  })
}

# ============================================================================
# Output for Frontend Configuration
# ============================================================================

output "debt_analysis_streaming_url" {
  description = "Lambda Function URL for SSE streaming debt analysis"
  value       = aws_lambda_function_url.debt_analysis_streaming.function_url
}

output "debt_analysis_streaming_url_id" {
  description = "Lambda Function URL ID"
  value       = aws_lambda_function_url.debt_analysis_streaming.url_id
}
