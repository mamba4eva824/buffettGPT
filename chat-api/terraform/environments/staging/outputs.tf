# Staging Environment Outputs
# These values are used by CI/CD and for sharing access with testers

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

output "bedrock_knowledge_base_id" {
  description = "The ID of the Bedrock knowledge base"
  value       = module.bedrock.knowledge_base_id
}

# ================================================
# Access Instructions Output
# ================================================

output "staging_access_info" {
  description = "Information for accessing the staging environment"
  value = {
    environment    = "staging"
    http_api_url   = module.api_gateway.http_api_endpoint
    websocket_url  = module.api_gateway.websocket_api_endpoint
    instructions   = "Share these URLs with friends and family for testing. Frontend will be deployed separately to CloudFront."
  }
}