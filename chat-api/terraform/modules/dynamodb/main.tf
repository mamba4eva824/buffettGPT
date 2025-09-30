# DynamoDB Module - Consolidated Table Management
# Based on Phase 1 analysis: 8 tables to keep, 2 to remove

# ================================================
# Core Chat Tables
# ================================================

resource "aws_dynamodb_table" "chat_sessions" {
  name           = "${var.project_name}-${var.environment}-chat-sessions"
  billing_mode   = var.billing_mode
  hash_key       = "conversation_id"
  range_key      = "timestamp"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-conversations-index"
    hash_key        = "user_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-chat-sessions"
      Purpose = "Chat session management"
    }
  )
}

resource "aws_dynamodb_table" "chat_messages" {
  name           = "${var.project_name}-${var.environment}-chat-messages"
  billing_mode   = var.billing_mode
  hash_key       = "conversation_id"
  range_key      = "message_id"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "message_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  local_secondary_index {
    name            = "timestamp-index"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-chat-messages"
      Purpose = "Chat message storage"
    }
  )
}

# ================================================
# WebSocket Connection Management
# ================================================

resource "aws_dynamodb_table" "websocket_connections" {
  name           = "${var.project_name}-${var.environment}-websocket-connections"
  billing_mode   = var.billing_mode
  hash_key       = "connection_id"

  attribute {
    name = "connection_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "session_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-connections-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "session-connections-index"
    hash_key        = "session_id"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-websocket-connections"
      Purpose = "WebSocket connection state management"
    }
  )
}

# ================================================
# Enhanced Rate Limiting (Consolidated)
# ================================================

resource "aws_dynamodb_table" "enhanced_rate_limits" {
  name           = "${var.project_name}-${var.environment}-enhanced-rate-limits"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "identifier"
  range_key      = "window"

  attribute {
    name = "identifier"
    type = "S"
  }

  attribute {
    name = "window"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-enhanced-rate-limits"
      Purpose = "Enhanced rate limiting with device fingerprinting"
    }
  )
}

# ================================================
# Anonymous Sessions (To be merged with chat_sessions in future)
# ================================================

resource "aws_dynamodb_table" "anonymous_sessions" {
  count = var.enable_anonymous_sessions ? 1 : 0
  
  name           = "${var.project_name}-${var.environment}-anon-sessions"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "device_fingerprint"
  range_key      = "created_at"

  attribute {
    name = "device_fingerprint"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "N"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  global_secondary_index {
    name            = "user-id-index"
    hash_key        = "user_id"
    projection_type = "ALL"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-anon-sessions"
      Purpose = "Anonymous session tracking"
      Note    = "To be merged with chat_sessions"
    }
  )
}

# ================================================
# NOTE: The following tables are managed by the auth module:
# - users
# - sessions (auth sessions)  
# - security_events
# 
# The following tables will be REMOVED (not included here):
# - rate_limits (replaced by enhanced_rate_limits)
# - usage_tracking (replaced by enhanced_rate_limits)
# ================================================