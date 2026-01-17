# ================================================
# ML Agent Tables
# ================================================
# Tables to support ML agent infrastructure:
# - Financial data caching (90-day TTL)
# - Idempotency handling (24-hour TTL)

resource "aws_dynamodb_table" "financial_data_cache" {
  name           = "${var.project_name}-${var.environment}-financial-data-cache"
  billing_mode   = "PAY_PER_REQUEST"  # On-demand for unpredictable ML query patterns
  hash_key       = "cache_key"        # ticker:fiscal_year

  attribute {
    name = "cache_key"
    type = "S"
  }

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "cached_at"
    type = "N"
  }

  # GSI for querying by ticker (all years for a company)
  global_secondary_index {
    name            = "ticker-index"
    hash_key        = "ticker"
    range_key       = "cached_at"
    projection_type = "ALL"
  }

  # GSI for cache expiration queries
  global_secondary_index {
    name            = "cached-at-index"
    hash_key        = "cached_at"
    projection_type = "KEYS_ONLY"
  }

  # TTL: 90 days (financial data doesn't change frequently)
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
      Name    = "${var.project_name}-${var.environment}-financial-data-cache"
      Purpose = "Financial data cache for ML agents"
      TTL     = "90 days"
    }
  )
}

# Ticker Lookup Cache - maps company names to ticker symbols
resource "aws_dynamodb_table" "ticker_lookup_cache" {
  name           = "${var.project_name}-${var.environment}-ticker-lookup"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "company_name"  # Lowercase normalized company name

  attribute {
    name = "company_name"
    type = "S"
  }

  # TTL: 30 days (company name → ticker rarely changes)
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
      Name    = "${var.project_name}-${var.environment}-ticker-lookup"
      Purpose = "Company name to ticker symbol cache"
      TTL     = "30 days"
    }
  )
}

# Forex Rate Cache - caches exchange rates for multi-currency support
resource "aws_dynamodb_table" "forex_rate_cache" {
  name           = "${var.project_name}-${var.environment}-forex-cache"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "currency_pair"  # e.g., "DKKUSD", "EURUSD"

  attribute {
    name = "currency_pair"
    type = "S"
  }

  # TTL: 24 hours (forex rates change daily)
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
      Name    = "${var.project_name}-${var.environment}-forex-cache"
      Purpose = "Forex rate cache for multi-currency financial reports"
      TTL     = "24 hours"
    }
  )
}

resource "aws_dynamodb_table" "idempotency_cache" {
  name           = "${var.project_name}-${var.environment}-idempotency-cache"
  billing_mode   = "PAY_PER_REQUEST"  # On-demand for unpredictable request patterns
  hash_key       = "idempotency_key"  # SHA256 hash of request parameters

  attribute {
    name = "idempotency_key"
    type = "S"
  }

  attribute {
    name = "cached_at"
    type = "N"
  }

  # GSI for cache expiration queries
  global_secondary_index {
    name            = "cached-at-index"
    hash_key        = "cached_at"
    projection_type = "KEYS_ONLY"
  }

  # TTL: 24 hours (idempotency window)
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
      Name    = "${var.project_name}-${var.environment}-idempotency-cache"
      Purpose = "Idempotency cache for ML agent requests"
      TTL     = "24 hours"
    }
  )
}
