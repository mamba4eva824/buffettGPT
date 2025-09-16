# Conversations Table - For organizing chat history
# This table stores conversation metadata and enables chat history features

resource "aws_dynamodb_table" "conversations" {
  name         = "${var.project_name}-${var.environment}-conversations"
  billing_mode = var.billing_mode

  # Primary key
  hash_key = "conversation_id"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "N"
  }

  # Global Secondary Index for querying conversations by user
  global_secondary_index {
    name            = "user-conversations-index"
    hash_key        = "user_id"
    range_key       = "updated_at"
    projection_type = "ALL"
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

  # TTL configuration (optional - for auto-archiving old conversations)
  ttl {
    enabled        = false  # Can be enabled later if needed
    attribute_name = "ttl"
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "${var.project_name}-${var.environment}-conversations"
      Type        = "Conversations"
      Description = "Stores conversation metadata for chat history"
    }
  )

  lifecycle {
    prevent_destroy = false  # Set to true in production
  }
}

