# Staging Environment Outputs
# These values are used by CI/CD and for sharing access with testers
# Updated 2025-01: Removed CloudFront, deprecated DynamoDB, and Knowledge Base outputs

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

output "investment_research_function_url" {
  description = "Investment research Lambda function URL"
  value       = module.lambda.investment_research_docker_function_url
}

output "analysis_followup_function_url" {
  description = "Analysis followup Lambda function URL"
  value       = module.lambda.analysis_followup_function_url
}

# ================================================
# DynamoDB Outputs
# ================================================

output "conversations_table_name" {
  description = "Name of the conversations table"
  value       = module.dynamodb.conversations_table_name
}

output "dynamodb_tables" {
  description = "DynamoDB table names"
  value       = module.dynamodb.table_summary
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
# Access Instructions Output
# ================================================

output "staging_access_info" {
  description = "Information for accessing the staging environment"
  value = {
    environment    = "staging"
    frontend_url   = module.cloudfront.cloudfront_url
    http_api_url   = module.api_gateway.http_api_endpoint
    websocket_url  = module.api_gateway.websocket_api_endpoint
    instructions   = "Share the frontend URL with friends and family for testing."
  }
}

# ================================================
# DEPRECATED OUTPUTS (Removed 2025-01)
# ================================================
# The following outputs were removed as part of RAG chatbot deprecation:
# - chat_messages_table_name (table removed)
# - bedrock_knowledge_base_id (KB removed)
# - cloudfront_distribution_id (module removed)
# - cloudfront_url (module removed)
# - cloudfront_domain_name (module removed)
# - s3_bucket_name (module removed)
# ================================================
