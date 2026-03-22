# DynamoDB Module Outputs
# Updated 2025-01: Removed deprecated RAG chatbot table outputs

# ================================================
# Conversations Table (ACTIVE)
# ================================================
output "conversations_table_name" {
  description = "Name of the conversations table"
  value       = aws_dynamodb_table.conversations.name
}

output "conversations_table_arn" {
  description = "ARN of the conversations table"
  value       = aws_dynamodb_table.conversations.arn
}

# ================================================
# Chat Messages Table (ACTIVE)
# ================================================
output "chat_messages_table_name" {
  description = "Name of the chat messages table"
  value       = aws_dynamodb_table.chat_messages.name
}

output "chat_messages_table_arn" {
  description = "ARN of the chat messages table"
  value       = aws_dynamodb_table.chat_messages.arn
}

# ================================================
# ML/Cache Tables (ACTIVE)
# ================================================
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

output "forex_cache_table_name" {
  description = "Name of the forex rate cache table"
  value       = aws_dynamodb_table.forex_rate_cache.name
}

output "forex_cache_table_arn" {
  description = "ARN of the forex rate cache table"
  value       = aws_dynamodb_table.forex_rate_cache.arn
}

# Idempotency Cache (ARCHIVED - 2025-01)
# NOTE: idempotency_cache outputs were removed when prediction ensemble was archived.
# See: archived/prediction_ensemble/

# ================================================
# Investment Research Tables (ACTIVE)
# ================================================
# NOTE: investment_reports (v1) table has been removed

output "investment_reports_v2_table_name" {
  description = "Name of the investment reports v2 table (section-based)"
  value       = aws_dynamodb_table.investment_reports_v2.name
}

output "investment_reports_v2_table_arn" {
  description = "ARN of the investment reports v2 table (section-based)"
  value       = aws_dynamodb_table.investment_reports_v2.arn
}

output "metrics_history_cache_table_name" {
  description = "Name of the metrics history cache table"
  value       = aws_dynamodb_table.metrics_history_cache.name
}

output "metrics_history_cache_table_arn" {
  description = "ARN of the metrics history cache table"
  value       = aws_dynamodb_table.metrics_history_cache.arn
}

# ================================================
# S&P 500 Aggregates Table (ACTIVE)
# ================================================
output "sp500_aggregates_table_name" {
  description = "Name of the S&P 500 aggregates table"
  value       = aws_dynamodb_table.sp500_aggregates.name
}

output "sp500_aggregates_table_arn" {
  description = "ARN of the S&P 500 aggregates table"
  value       = aws_dynamodb_table.sp500_aggregates.arn
}

# ================================================
# Token Usage Table (ACTIVE)
# ================================================
output "token_usage_table_name" {
  description = "Name of the token usage tracking table"
  value       = aws_dynamodb_table.token_usage.name
}

output "token_usage_table_arn" {
  description = "ARN of the token usage tracking table"
  value       = aws_dynamodb_table.token_usage.arn
}

# ================================================
# Waitlist Table (ACTIVE)
# ================================================
output "waitlist_table_name" {
  description = "Name of the waitlist table"
  value       = aws_dynamodb_table.waitlist.name
}

output "waitlist_table_arn" {
  description = "ARN of the waitlist table"
  value       = aws_dynamodb_table.waitlist.arn
}

# ================================================
# Summary Output
# ================================================
output "table_summary" {
  description = "Summary of all active DynamoDB tables"
  value = {
    conversations = {
      conversations  = aws_dynamodb_table.conversations.name
      chat_messages  = aws_dynamodb_table.chat_messages.name
    }
    ml_cache = {
      financial_data_cache = aws_dynamodb_table.financial_data_cache.name
      ticker_lookup        = aws_dynamodb_table.ticker_lookup_cache.name
      forex_cache          = aws_dynamodb_table.forex_rate_cache.name
      # idempotency_cache removed (2025-01) - prediction ensemble archived
    }
    investment_research = {
      investment_reports_v2 = aws_dynamodb_table.investment_reports_v2.name
      metrics_history_cache = aws_dynamodb_table.metrics_history_cache.name
      sp500_aggregates      = aws_dynamodb_table.sp500_aggregates.name
    }
    token_tracking = {
      token_usage = aws_dynamodb_table.token_usage.name
    }
    waitlist = {
      waitlist = aws_dynamodb_table.waitlist.name
    }
  }
}

# ================================================
# DEPRECATED OUTPUTS (Removed 2025-01)
# ================================================
# The following outputs were removed as part of RAG chatbot deprecation:
# - chat_sessions_table_name/arn
# - websocket_connections_table_name/arn
# - enhanced_rate_limits_table_name/arn
# - anonymous_sessions_table_name/arn
# - investment_reports_table_name/arn (v1)
#
# NOTE: chat_messages_table was re-added (2025-01) for Research report history
# ================================================
