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

# WebSocket API outputs - REMOVED (2026-02)
# websocket_api_id and websocket_api_endpoint deprecated

output "analysis_api_endpoint" {
  description = "Analysis REST API endpoint URL (for streaming analysis)"
  value       = module.api_gateway.analysis_api_endpoint
}

output "research_api_endpoint" {
  description = "Research REST API endpoint URL"
  value       = module.api_gateway.research_api_endpoint
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
  value       = module.lambda.analysis_followup_url
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
  value       = module.bedrock.followup_agent_id
}

output "bedrock_agent_alias_id" {
  description = "The alias ID of the Bedrock agent"
  value       = module.bedrock.followup_agent_alias_id
}

# ================================================
# Access Instructions Output
# ================================================

output "landing_cloudfront_url" {
  description = "CloudFront URL for the landing page"
  value       = module.cloudfront_landing.cloudfront_url
}

output "landing_s3_bucket_name" {
  description = "S3 bucket name for the landing page"
  value       = module.cloudfront_landing.s3_bucket_name
}

output "landing_cloudfront_distribution_id" {
  description = "CloudFront distribution ID for the landing page"
  value       = module.cloudfront_landing.cloudfront_distribution_id
}

output "staging_access_info" {
  description = "Information for accessing the staging environment"
  value = {
    environment    = "staging"
    app_url        = module.cloudfront.cloudfront_url
    landing_url    = module.cloudfront_landing.cloudfront_url
    http_api_url   = module.api_gateway.http_api_endpoint
    research_url   = module.lambda.investment_research_docker_function_url
    instructions   = "Share the landing URL for new signups. Share the app URL with testers."
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
