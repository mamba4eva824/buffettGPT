# API Gateway Module Outputs

output "http_api_id" {
  description = "ID of the HTTP API Gateway"
  value       = aws_apigatewayv2_api.http_api.id
}

output "http_api_endpoint" {
  description = "Endpoint URL of the HTTP API Gateway"
  value       = aws_apigatewayv2_stage.http_api_stage.invoke_url
}

output "websocket_api_id" {
  description = "ID of the WebSocket API Gateway"
  value       = aws_apigatewayv2_api.websocket_api.id
}

output "websocket_api_endpoint" {
  description = "Endpoint URL of the WebSocket API Gateway"
  value       = replace(aws_apigatewayv2_stage.websocket_stage.invoke_url, "https://", "wss://")
}

output "api_execution_arn" {
  description = "Execution ARN for API Gateway"
  value       = aws_apigatewayv2_api.http_api.execution_arn
}

output "http_api_execution_arn" {
  description = "Execution ARN for HTTP API Gateway"
  value       = aws_apigatewayv2_api.http_api.execution_arn
}

output "websocket_api_execution_arn" {
  description = "Execution ARN for WebSocket API Gateway"
  value       = aws_apigatewayv2_api.websocket_api.execution_arn
}

output "api_gateway_log_groups" {
  description = "CloudWatch Log Groups for API Gateway"
  value = {
    http_api_logs     = aws_cloudwatch_log_group.api_gateway_logs.name
    websocket_api_logs = aws_cloudwatch_log_group.websocket_api_logs.name
  }
}

output "authorizer_ids" {
  description = "IDs of the authorizers"
  value = {
    http_jwt_authorizer      = var.enable_authorization && var.authorizer_function_arn != null ? aws_apigatewayv2_authorizer.http_jwt_authorizer[0].id : null
    websocket_jwt_authorizer = var.enable_authorization && var.authorizer_function_arn != null ? aws_apigatewayv2_authorizer.websocket_jwt_authorizer[0].id : null
  }
}

# ============================================================================
# Analysis Streaming API Outputs
# ============================================================================

output "analysis_api_id" {
  description = "ID of the Analysis REST API Gateway"
  value       = var.enable_analysis_api ? aws_api_gateway_rest_api.analysis[0].id : null
}

output "analysis_api_endpoint" {
  description = "Endpoint URL of the Analysis REST API Gateway"
  value       = var.enable_analysis_api ? "${aws_api_gateway_stage.analysis[0].invoke_url}/analysis" : null
}

output "analysis_api_execution_arn" {
  description = "Execution ARN for Analysis REST API Gateway"
  value       = var.enable_analysis_api ? aws_api_gateway_rest_api.analysis[0].execution_arn : null
}

output "authorizer_invocation_role_arn" {
  description = "ARN of the authorizer invocation IAM role"
  value       = var.enable_authorization ? aws_iam_role.authorizer_invocation_role[0].arn : null
}