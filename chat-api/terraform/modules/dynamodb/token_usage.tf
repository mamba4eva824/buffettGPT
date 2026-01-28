# Token Usage Table - Tracks monthly token consumption per user
# Used for enforcing usage limits on the follow-up agent (ConverseStream API)
# Supports hard cutoff at limit with notifications at 80% and 90%

resource "aws_dynamodb_table" "token_usage" {
  name         = "${var.project_name}-${var.environment}-token-usage"
  billing_mode = var.billing_mode

  # Primary key: user_id (hash) + month (range)
  # Allows efficient queries for current month usage and historical data
  hash_key  = "user_id"
  range_key = "month"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "month"
    type = "S"  # Format: "YYYY-MM" (e.g., "2026-01")
  }

  # Encryption at rest using KMS
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  # Point-in-time recovery for data protection
  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "${var.project_name}-${var.environment}-token-usage"
      Type        = "TokenUsage"
      Description = "Monthly token usage tracking for follow-up agent"
    }
  )

  lifecycle {
    prevent_destroy = false  # Set to true in production
  }
}

# Schema documentation:
# ---------------------------------------------------------
# Attribute          | Type   | Description
# ---------------------------------------------------------
# user_id            | S (PK) | User identifier
# month              | S (SK) | Year-month "YYYY-MM"
# input_tokens       | N      | Total input tokens consumed
# output_tokens      | N      | Total output tokens consumed
# total_tokens       | N      | Sum of input + output tokens
# request_count      | N      | Number of API requests made
# token_limit        | N      | Monthly limit for this user
# notified_80        | BOOL   | True if 80% notification sent
# notified_90        | BOOL   | True if 90% notification sent
# limit_reached_at   | S      | ISO timestamp when limit hit (nullable)
# last_request_at    | S      | ISO timestamp of last request
# ---------------------------------------------------------
