# Waitlist Table - Viral waitlist with referral tracking
# Stores email signups, referral codes, and referral counts

resource "aws_dynamodb_table" "waitlist" {
  name         = "waitlist-${var.environment}-${var.project_name}"
  billing_mode = var.billing_mode

  # Primary key
  hash_key = "email"

  attribute {
    name = "email"
    type = "S"
  }

  attribute {
    name = "referral_code"
    type = "S"
  }

  # GSI for looking up referrer by referral code
  global_secondary_index {
    name            = "referral-code-index"
    hash_key        = "referral_code"
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

  # TTL for rate limiting entries
  ttl {
    enabled        = true
    attribute_name = "ttl"
  }

  tags = merge(
    var.common_tags,
    {
      Name        = "waitlist-${var.environment}-${var.project_name}"
      Type        = "Waitlist"
      Description = "Viral waitlist with referral tracking"
    }
  )

  lifecycle {
    prevent_destroy = false
  }
}
