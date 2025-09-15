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

# Anonymous Sessions Table (conditional)
output "anonymous_sessions_table_name" {
  description = "Name of the anonymous sessions table"
  value       = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].name : null
}

output "anonymous_sessions_table_arn" {
  description = "ARN of the anonymous sessions table"
  value       = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].arn : null
}

# Summary Output
output "table_summary" {
  description = "Summary of all DynamoDB tables"
  value = {
    core_tables = {
      chat_sessions        = aws_dynamodb_table.chat_sessions.name
      chat_messages        = aws_dynamodb_table.chat_messages.name
      websocket_connections = aws_dynamodb_table.websocket_connections.name
    }
    rate_limiting = {
      enhanced_rate_limits = aws_dynamodb_table.enhanced_rate_limits.name
    }
    optional = {
      anonymous_sessions = var.enable_anonymous_sessions ? aws_dynamodb_table.anonymous_sessions[0].name : "disabled"
    }
  }
}