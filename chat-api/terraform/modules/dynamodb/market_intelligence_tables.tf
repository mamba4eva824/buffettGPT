# =============================================================================
# Market Intelligence Tables
# =============================================================================
# Tables supporting the Market Intelligence feature:
# - Forex rate caching for multi-currency S&P 500 data
# - Per-company quarterly metrics (shared with follow-up agent)
# - S&P 500 sector and index-level aggregates

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

# =============================================================================
# Metrics History Cache - Pre-computed metrics for follow-up agent
# =============================================================================
# Optimized quarter-based schema for getMetricsHistory action group:
# - 20 items per ticker (one per quarter) instead of 140
# - All 9 metric categories embedded in each item
# - fiscal_date sort key for human-readable chronological queries
# - No GSIs needed - simple ticker + fiscal_date queries
# - TTL matches financial-data-cache (90 days)
#
# Schema:
#   PK: ticker (e.g., "AAPL")
#   SK: fiscal_date (e.g., "2025-09-27") - sorts chronologically
#
# Item structure:
#   {
#     "ticker": "AAPL",
#     "fiscal_date": "2025-09-27",
#     "fiscal_year": 2025,
#     "fiscal_quarter": "Q3",
#     "revenue_profit": { revenue, net_income, margins, ... },
#     "cashflow": { operating_cash_flow, free_cash_flow, ... },
#     "balance_sheet": { total_debt, cash_position, ... },
#     "debt_leverage": { debt_to_equity, current_ratio, ... },
#     "earnings_quality": { gaap_net_income, sbc_actual, ... },
#     "dilution": { basic_shares, diluted_shares, ... },
#     "valuation": { roa, roic, roe, ... },
#     "earnings_events": { eps_actual, eps_estimated, eps_surprise_pct, ... },
#     "dividend": { dps, dividend_yield, frequency, ... },
#   }

resource "aws_dynamodb_table" "metrics_history_cache" {
  name         = "metrics-history-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "ticker"
  range_key = "fiscal_date"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "fiscal_date"
    type = "S"
  }

  # No GSIs needed - simple queries by ticker with fiscal_date ordering

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
      Name    = "metrics-history-${var.environment}"
      Purpose = "Pre-computed metrics by quarter for follow-up agent and market intelligence"
      TTL     = "90 days"
    }
  )
}

# =============================================================================
# S&P 500 Aggregates - Pre-computed sector and index-level analytics
# =============================================================================
# Stores sector medians, index snapshots, and cross-company analytics
# for the Market Intelligence agent.
#
# Schema:
#   PK: aggregate_type (e.g., "SECTOR", "INDEX")
#   SK: aggregate_key  (e.g., "Technology", "OVERALL")
#
# Item structure:
#   {
#     "aggregate_type": "SECTOR",
#     "aggregate_key": "Technology",
#     "company_count": 87,
#     "metrics": { median_revenue_growth, median_margins, ... },
#     "top_companies": { by_revenue: [...], by_fcf_margin: [...] },
#     "earnings_summary": { median_eps_surprise, pct_beat, ... },
#     "dividend_summary": { median_yield, pct_payers, ... },
#     "computed_at": "2026-03-21T...",
#     "data_coverage": 87,
#   }

resource "aws_dynamodb_table" "sp500_aggregates" {
  name         = "${var.project_name}-${var.environment}-sp500-aggregates"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "aggregate_type"
  range_key = "aggregate_key"

  attribute {
    name = "aggregate_type"
    type = "S"
  }

  attribute {
    name = "aggregate_key"
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
      Name    = "${var.project_name}-${var.environment}-sp500-aggregates"
      Purpose = "SP500 sector and index-level aggregate analytics"
      TTL     = "7 days"
    }
  )
}
