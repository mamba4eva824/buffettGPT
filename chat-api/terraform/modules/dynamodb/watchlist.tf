# Watchlist Table - Per-user stock watchlist with earnings/price tracking
# Stores watched tickers with snapshot data from the quarter they started watching

resource "aws_dynamodb_table" "watchlist" {
  name         = "watchlist-${var.project_name}-${var.environment}"
  billing_mode = var.billing_mode

  # Primary key
  hash_key  = "user_id"
  range_key = "ticker"

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "ticker"
    type = "S"
  }

  # GSI for reverse lookup: "who watches this ticker?"
  global_secondary_index {
    name            = "ticker-index"
    hash_key        = "ticker"
    range_key       = "user_id"
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

  # TTL for auto-expiry of inactive watchlist entries
  ttl {
    enabled        = true
    attribute_name = "expires_at"
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "watchlist-${var.project_name}-${var.environment}"
      Type        = "Watchlist"
      Description = "Per-user stock watchlist with earnings and price tracking"
    }
  )

  lifecycle {
    prevent_destroy = false
  }
}
