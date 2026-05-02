# Staging Environment Outputs
# These values are used by CI/CD and for sharing access with testers
# Updated 2026-03: Added market intelligence, removed landing page and deprecated outputs

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

output "analysis_api_endpoint" {
  description = "Analysis REST API endpoint URL (for streaming analysis)"
  value       = module.api_gateway.analysis_api_endpoint
}

# WebSocket API outputs - REMOVED (2026-02)
# websocket_api_id and websocket_api_endpoint deprecated

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

output "market_intel_chat_url" {
  description = "Market Intelligence chat Lambda function URL"
  value       = module.lambda.market_intel_chat_url
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
# Bedrock Outputs (removed 2026-05)
# ================================================
# bedrock_agent_id and bedrock_agent_alias_id removed alongside the follow-up
# Bedrock Agent + ReportResearch action group cleanup. The follow-up agent now
# runs on Bedrock Runtime converse_stream + inline tools — no Bedrock Agent.

# ================================================
# Access Instructions Output
# ================================================

output "staging_access_info" {
  description = "Information for accessing the staging environment"
  value = {
    environment  = "staging"
    frontend_url = module.cloudfront.cloudfront_url
    http_api_url = module.api_gateway.http_api_endpoint
    research_url = module.lambda.investment_research_docker_function_url
    instructions = "Share the frontend URL with friends and family for testing."
  }
}
