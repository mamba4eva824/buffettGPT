# Token Usage Table - Tracks token consumption per billing period
# Used for enforcing usage limits on the follow-up agent (ConverseStream API)
# Supports anniversary-based billing with hard cutoff at limit
# Notifications at 80% and 90% thresholds

resource "aws_dynamodb_table" "token_usage" {
  # Naming convention: resource-env-project
  name         = "token-usage-${var.environment}-${var.project_name}"
  billing_mode = var.billing_mode

  # Primary key: user_id (hash) + billing_period (range)
  # billing_period uses YYYY-MM-DD format for anniversary-based billing
  # (resets on user's subscription day, not calendar month)
  hash_key  = "user_id"
  range_key = "billing_period"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "billing_period"
    type = "S"  # Format: "YYYY-MM-DD" (billing period start date)
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
      Name        = "token-usage-${var.environment}-${var.project_name}"
      Type        = "TokenUsage"
      Description = "Token usage tracking with anniversary-based billing"
    }
  )

  lifecycle {
    prevent_destroy = false  # Set to true in production
  }
}

# Schema documentation:
# ---------------------------------------------------------
# Attribute            | Type   | Description
# ---------------------------------------------------------
# user_id              | S (PK) | User identifier from JWT
# billing_period       | S (SK) | Billing period start "YYYY-MM-DD"
# billing_day          | N      | Day of month for billing cycle (1-31)
# billing_period_start | S      | ISO timestamp of period start
# billing_period_end   | S      | ISO timestamp of period end (reset date)
# input_tokens         | N      | Total input tokens consumed
# output_tokens        | N      | Total output tokens consumed
# total_tokens         | N      | Sum of input + output tokens
# request_count        | N      | Number of API requests made
# token_limit          | N      | Token limit for this billing period
# notified_80          | BOOL   | True if 80% notification sent
# notified_90          | BOOL   | True if 90% notification sent
# limit_reached_at     | S      | ISO timestamp when limit hit (nullable)
# last_request_at      | S      | ISO timestamp of last request
# subscribed_at        | S      | ISO timestamp of first usage
# subscription_tier    | S      | User tier (free/plus)
# reset_date           | S      | Pre-computed next reset timestamp
# ---------------------------------------------------------
