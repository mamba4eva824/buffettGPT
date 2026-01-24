# Chat Messages Table - Stores individual messages within conversations
# This table stores message content and enables loading conversation history
# Re-added 2025-01: Required for Research report history retrieval

resource "aws_dynamodb_table" "chat_messages" {
  name         = "${var.project_name}-${var.environment}-chat-messages"
  billing_mode = var.billing_mode

  # Primary key: conversation_id (hash) + timestamp (range)
  # This allows efficient queries for all messages in a conversation, sorted chronologically
  hash_key  = "conversation_id"
  range_key = "timestamp"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "N"
  }

  # Encryption at rest
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  # Point-in-time recovery
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  # TTL configuration (optional - for auto-cleanup of old messages)
  ttl {
    enabled        = false  # Can be enabled later if needed
    attribute_name = "ttl"
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "${var.project_name}-${var.environment}-chat-messages"
      Type        = "ChatMessages"
      Description = "Stores individual messages within conversations"
    }
  )

  lifecycle {
    prevent_destroy = false  # Set to true in production
  }
}
