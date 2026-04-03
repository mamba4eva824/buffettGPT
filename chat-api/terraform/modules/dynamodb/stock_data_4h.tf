# =============================================================================
# Stock Data 4-Hour Candles Table
# =============================================================================
# Stores 4-hour OHLCV candle data for S&P 500 tickers, ingested daily
# after market close via the sp500_eod_ingest Lambda.
#
# Schema:
#   PK: TICKER#{symbol}           (e.g., "TICKER#AAPL")
#   SK: DATETIME#{timestamp}      (e.g., "DATETIME#2026-04-03 16:00:00")
#
# GSI (DateIndex):
#   GSI_PK: DATE#{YYYY-MM-DD}    (e.g., "DATE#2026-04-03")
#   GSI_SK: TICKER#{symbol}       (e.g., "TICKER#AAPL")
#
# Query patterns:
#   1. Single ticker date range: PK = TICKER#AAPL, SK BETWEEN DATETIME#start AND DATETIME#end
#   2. All tickers for a date:   GSI_PK = DATE#2026-04-03 (DateIndex)

resource "aws_dynamodb_table" "stock_data_4h" {
  name         = "stock-data-4h-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  attribute {
    name = "GSI_PK"
    type = "S"
  }

  attribute {
    name = "GSI_SK"
    type = "S"
  }

  global_secondary_index {
    name            = "DateIndex"
    hash_key        = "GSI_PK"
    range_key       = "GSI_SK"
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
      Name    = "stock-data-4h-${var.environment}"
      Purpose = "4-hour OHLCV candle data for S&P 500 tickers"
    }
  )
}
