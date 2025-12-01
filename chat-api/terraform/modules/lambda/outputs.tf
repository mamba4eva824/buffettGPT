# Lambda Module Outputs

# Dependencies Layer ARN
output "dependencies_layer_arn" {
  description = "ARN of the dependencies Lambda layer"
  value       = aws_lambda_layer_version.dependencies.arn
}

# Function ARNs
output "function_arns" {
  description = "Map of Lambda function ARNs"
  value       = { for k, v in aws_lambda_function.functions : k => v.arn }
}

# Function Names
output "function_names" {
  description = "Map of Lambda function names"
  value       = { for k, v in aws_lambda_function.functions : k => v.function_name }
}

# Function Invoke ARNs
output "function_invoke_arns" {
  description = "Map of Lambda function invoke ARNs"
  value       = { for k, v in aws_lambda_function.functions : k => v.invoke_arn }
}

# Individual Function Outputs for Easy Reference
output "chat_http_handler_arn" {
  description = "ARN of the chat HTTP handler function"
  value       = try(aws_lambda_function.functions["chat_http_handler"].arn, null)
}

output "websocket_connect_arn" {
  description = "ARN of the WebSocket connect function"
  value       = try(aws_lambda_function.functions["websocket_connect"].arn, null)
}

output "websocket_disconnect_arn" {
  description = "ARN of the WebSocket disconnect function"
  value       = try(aws_lambda_function.functions["websocket_disconnect"].arn, null)
}

output "websocket_message_arn" {
  description = "ARN of the WebSocket message function"
  value       = try(aws_lambda_function.functions["websocket_message"].arn, null)
}

output "chat_processor_arn" {
  description = "ARN of the chat processor function"
  value       = try(aws_lambda_function.functions["chat_processor"].arn, null)
}

output "conversations_handler_arn" {
  description = "ARN of the conversations handler function"
  value       = try(aws_lambda_function.functions["conversations_handler"].arn, null)
}

# Log Groups
output "log_groups" {
  description = "Map of CloudWatch log group names"
  value       = { for k, v in aws_cloudwatch_log_group.lambda_logs : k => v.name }
}

# Summary
output "lambda_summary" {
  description = "Summary of Lambda functions"
  value = {
    total_functions = length(aws_lambda_function.functions)
    functions       = keys(aws_lambda_function.functions)
    http_functions  = [for k, v in aws_lambda_function.functions : k if contains(["chat_http_handler"], k)]
    websocket_functions = [for k, v in aws_lambda_function.functions : k if contains(["websocket_connect", "websocket_disconnect", "websocket_message"], k)]
    processor_functions = [for k, v in aws_lambda_function.functions : k if contains(["chat_processor"], k)]
  }
}

# Secrets
output "search_api_key_arn" {
  description = "ARN of the Perplexity API key secret"
  value       = aws_secretsmanager_secret.search_api_key.arn
}

output "fmp_api_key_arn" {
  description = "ARN of the FMP API key secret"
  value       = data.aws_secretsmanager_secret.fmp_api_key.arn
}

output "fmp_api_key_name" {
  description = "Name of the FMP API key secret"
  value       = data.aws_secretsmanager_secret.fmp_api_key.name
}

# ================================================
# Lambda Function URL Outputs (for SSE streaming)
# ================================================

output "ensemble_analyzer_url" {
  description = "Function URL for the ensemble analyzer (SSE streaming)"
  value       = try(aws_lambda_function_url.ensemble_analyzer.function_url, null)
}

output "analysis_followup_url" {
  description = "Function URL for analysis followup (SSE streaming)"
  value       = try(aws_lambda_function_url.analysis_followup.function_url, null)
}