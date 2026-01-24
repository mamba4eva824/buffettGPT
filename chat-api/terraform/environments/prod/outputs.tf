# Production Environment Outputs
# These values are used by CI/CD and for monitoring production

# ================================================
# API Gateway Outputs
# ================================================

output "http_api_id" {
  description = "The ID of the HTTP API Gateway"
  value       = module.api_gateway.http_api_id
}

output "http_api_endpoint" {
  description = "The HTTP API Gateway endpoint URL"
  value       = module.api_gateway.http_api_endpoint
}

output "websocket_api_id" {
  description = "The ID of the WebSocket API Gateway"
  value       = module.api_gateway.websocket_api_id
}

output "websocket_api_endpoint" {
  description = "The WebSocket API Gateway endpoint URL"
  value       = module.api_gateway.websocket_api_endpoint
}

# ================================================
# Lambda Outputs
# ================================================

output "lambda_function_names" {
  description = "Map of Lambda function names"
  value       = module.lambda.function_names
}

output "lambda_function_arns" {
  description = "Map of Lambda function ARNs"
  value       = module.lambda.function_arns
}

# ================================================
# DynamoDB Outputs
# ================================================

output "conversations_table_name" {
  description = "Name of the conversations table"
  value       = module.dynamodb.conversations_table_name
}

output "chat_messages_table_name" {
  description = "Name of the chat messages table"
  value       = module.dynamodb.chat_messages_table_name
}

# ================================================
# Bedrock Outputs
# ================================================

output "bedrock_agent_id" {
  description = "The ID of the Bedrock agent"
  value       = module.bedrock.agent_id
}

output "bedrock_agent_alias_id" {
  description = "The alias ID of the Bedrock agent"
  value       = module.bedrock.agent_alias_id
}

# ================================================
# CloudFront Outputs
# ================================================

output "cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution"
  value       = module.cloudfront.cloudfront_distribution_id
}

output "cloudfront_url" {
  description = "The CloudFront distribution URL"
  value       = module.cloudfront.cloudfront_url
}

output "cloudfront_domain_name" {
  description = "The CloudFront distribution domain name"
  value       = module.cloudfront.cloudfront_domain_name
}

output "s3_bucket_name" {
  description = "The S3 bucket name for frontend files"
  value       = module.cloudfront.s3_bucket_name
}

# ================================================
# Production Access Info Output
# ================================================

output "production_access_info" {
  description = "Information for accessing the production environment"
  value = {
    environment   = "production"
    frontend_url  = module.cloudfront.cloudfront_url
    http_api_url  = module.api_gateway.http_api_endpoint
    websocket_url = module.api_gateway.websocket_api_endpoint
    instructions  = "This is the production environment. Handle with care."
  }
}
