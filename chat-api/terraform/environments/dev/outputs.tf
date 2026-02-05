# Development Environment Outputs

# API Endpoints
output "http_api_endpoint" {
  description = "HTTP API endpoint URL"
  value       = module.api_gateway.http_api_endpoint
}

# websocket_api_endpoint - REMOVED (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md

output "analysis_api_endpoint" {
  description = "Analysis REST API endpoint URL (for streaming analysis)"
  value       = module.api_gateway.analysis_api_endpoint
}

# Lambda Functions
output "lambda_functions" {
  description = "Deployed Lambda function names"
  value       = module.lambda.function_names
}

# DynamoDB Tables
output "dynamodb_tables" {
  description = "DynamoDB table names"
  value       = module.dynamodb.table_summary
}

# Authentication Endpoints (if enabled)
output "auth_endpoints" {
  description = "Authentication endpoints"
  value = var.enable_authentication ? {
    status = "Authentication enabled"
  } : {
    status = "Authentication disabled"
  }
}

# Environment Summary
output "environment_summary" {
  description = "Environment configuration summary"
  value = {
    environment = "dev"
    project     = var.project_name
    region      = var.aws_region
    
    features = {
      authentication = var.enable_authentication
      monitoring     = var.enable_monitoring
      vpc_enabled    = false
      pitr_enabled   = false
    }
    
    resource_count = {
      lambda_functions = length(module.lambda.function_names)
      dynamodb_tables  = length(keys(module.dynamodb.table_summary.conversations)) + length(keys(module.dynamodb.table_summary.ml_cache)) + length(keys(module.dynamodb.table_summary.investment_research))
    }
    
    urls = {
      http_api = module.api_gateway.http_api_endpoint
      frontend = var.frontend_url
    }
  }
}