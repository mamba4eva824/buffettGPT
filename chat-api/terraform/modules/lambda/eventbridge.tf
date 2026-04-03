# =============================================================================
# EventBridge Schedule - S&P 500 EOD 4-Hour Candle Ingestion
# =============================================================================
# Triggers the sp500_eod_ingest Lambda after US market close.
# Schedule: 10 PM UTC Mon-Fri (6 PM ET, ~2 hours after market close)
# This delay ensures FMP has processed and published the day's 4h candles.

resource "aws_cloudwatch_event_rule" "sp500_eod_ingest_schedule" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  name                = "${var.project_name}-${var.environment}-sp500-eod-4h-ingest"
  description         = "Daily S&P 500 4-hour candle ingestion after market close (10 PM UTC / 6 PM ET)"
  schedule_expression = "cron(0 22 ? * MON-FRI *)"

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-sp500-eod-4h-ingest"
      Purpose = "Trigger daily 4h stock data ingestion"
    }
  )
}

resource "aws_cloudwatch_event_target" "sp500_eod_ingest_target" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  rule      = aws_cloudwatch_event_rule.sp500_eod_ingest_schedule[0].name
  target_id = "sp500-eod-ingest-lambda"
  arn       = aws_lambda_function.functions["sp500_eod_ingest"].arn
  input     = jsonencode({})

  retry_policy {
    maximum_retry_attempts       = 2
    maximum_event_age_in_seconds = 3600
  }
}

resource "aws_lambda_permission" "allow_eventbridge_eod_ingest" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.functions["sp500_eod_ingest"].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sp500_eod_ingest_schedule[0].arn
}
