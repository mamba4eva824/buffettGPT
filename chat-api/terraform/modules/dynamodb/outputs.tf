# DynamoDB Module Outputs

# Chat Sessions Table
output "chat_sessions_table_name" {
  description = "Name of the chat sessions table"
  value       = aws_dynamodb_table.chat_sessions.name
}

output "chat_sessions_table_arn" {
  description = "ARN of the chat sessions table"
  value       = aws_dynamodb_table.chat_sessions.arn
}

# Chat Messages Table
output "chat_messages_table_name" {
  description = "Name of the chat messages table"
  value       = aws_dynamodb_table.chat_messages.name
}

output "chat_messages_table_arn" {
  description = "ARN of the chat messages table"
  value       = aws_dynamodb_table.chat_messages.arn
}

# WebSocket Connections Table
output "websocket_connections_table_name" {
  description = "Name of the WebSocket connections table"
  value       = aws_dynamodb_table.websocket_connections.name
}

output "websocket_connections_table_arn" {
  description = "ARN of the WebSocket connections table"
  value       = aws_dynamodb_table.websocket_connections.arn
}

# Enhanced Rate Limits Table
output "enhanced_rate_limits_table_name" {
  description = "Name of the enhanced rate limits table"
  value       = aws_dynamodb_table.enhanced_rate_limits.name
}

output "enhanced_rate_limits_table_arn" {
  description = "ARN of the enhanced rate limits table"
  value       = aws_dynamodb_table.enhanced_rate_limits.arn
}

# Conversations Table
output "conversations_table_name" {
  description = "Name of the conversations table"
  value       = aws_dynamodb_table.conversations.name
}

output "conversations_table_arn" {
  description = "ARN of the conversations table"
  value       = aws_dynamodb_table.conversations.arn
}

# Anonymous Sessions Table (conditional)
output "anonymous_sessions_table_name" {
  description = "Name of the anonymous sessions table"
  value       = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].name : null
}

output "anonymous_sessions_table_arn" {
  description = "ARN of the anonymous sessions table"
  value       = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].arn : null
}

# ML Tables
output "financial_data_cache_table_name" {
  description = "Name of the financial data cache table"
  value       = aws_dynamodb_table.financial_data_cache.name
}

output "financial_data_cache_table_arn" {
  description = "ARN of the financial data cache table"
  value       = aws_dynamodb_table.financial_data_cache.arn
}

output "ticker_lookup_table_name" {
  description = "Name of the ticker lookup cache table"
  value       = aws_dynamodb_table.ticker_lookup_cache.name
}

output "ticker_lookup_table_arn" {
  description = "ARN of the ticker lookup cache table"
  value       = aws_dynamodb_table.ticker_lookup_cache.arn
}

# Forex Rate Cache Table
output "forex_cache_table_name" {
  description = "Name of the forex rate cache table"
  value       = aws_dynamodb_table.forex_rate_cache.name
}

output "forex_cache_table_arn" {
  description = "ARN of the forex rate cache table"
  value       = aws_dynamodb_table.forex_rate_cache.arn
}

# Investment Reports Table (v1 - single blob)
output "investment_reports_table_name" {
  description = "Name of the investment reports table"
  value       = aws_dynamodb_table.investment_reports.name
}

output "investment_reports_table_arn" {
  description = "ARN of the investment reports table"
  value       = aws_dynamodb_table.investment_reports.arn
}

# Investment Reports v2 Table (section-per-item schema)
output "investment_reports_v2_table_name" {
  description = "Name of the investment reports v2 table (section-based)"
  value       = aws_dynamodb_table.investment_reports_v2.name
}

output "investment_reports_v2_table_arn" {
  description = "ARN of the investment reports v2 table (section-based)"
  value       = aws_dynamodb_table.investment_reports_v2.arn
}

# Summary Output
output "table_summary" {
  description = "Summary of all DynamoDB tables"
  value = {
    core_tables = {
      chat_sessions        = aws_dynamodb_table.chat_sessions.name
      chat_messages        = aws_dynamodb_table.chat_messages.name
      websocket_connections = aws_dynamodb_table.websocket_connections.name
      conversations        = aws_dynamodb_table.conversations.name
    }
    rate_limiting = {
      enhanced_rate_limits = aws_dynamodb_table.enhanced_rate_limits.name
    }
    investment_research = {
      investment_reports    = aws_dynamodb_table.investment_reports.name
      investment_reports_v2 = aws_dynamodb_table.investment_reports_v2.name
      forex_cache           = aws_dynamodb_table.forex_rate_cache.name
    }
    optional = {
      anonymous_sessions = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].name : "disabled"
    }
  }
}