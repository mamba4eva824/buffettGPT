# =============================================================================
# EventBridge Scheduler — Market Data Pipelines
# =============================================================================
# Uses EventBridge Scheduler (not legacy CloudWatch Event Rules) for native
# timezone support. All schedules run in America/New_York so cron times
# automatically adjust for EDT/EST — no DST drift.
#
# Schedules:
#   1. S&P 500 EOD 4h candle ingest — 5:00 PM ET Mon-Fri
#   2. Earnings update post-close   — 5:00 PM ET Mon-Fri
#   3. Earnings update post-open    — 11:30 AM ET Mon-Fri

# =============================================================================
# IAM Role — EventBridge Scheduler Execution
# =============================================================================
# Scheduler assumes this role to invoke Lambda targets and deliver to DLQs.

data "aws_iam_policy_document" "scheduler_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_execution" {
  count = (var.enable_eod_ingest_schedule || var.enable_earnings_update_schedule) ? 1 : 0

  name               = "${var.project_name}-${var.environment}-scheduler-execution"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume_role.json

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-scheduler-execution"
      Purpose = "EventBridge Scheduler execution role for market data pipelines"
    }
  )
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  count = (var.enable_eod_ingest_schedule || var.enable_earnings_update_schedule) ? 1 : 0

  name = "${var.project_name}-${var.environment}-scheduler-invoke-lambda"
  role = aws_iam_role.scheduler_execution[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        Resource = [
          aws_lambda_function.functions["sp500_eod_ingest"].arn,
          aws_lambda_function.functions["earnings_update"].arn,
        ]
      },
      {
        Effect = "Allow"
        Action = ["sqs:SendMessage"]
        Resource = compact([
          var.enable_eod_ingest_schedule ? aws_sqs_queue.eod_ingest_dlq[0].arn : "",
          var.enable_earnings_update_schedule ? aws_sqs_queue.earnings_update_dlq[0].arn : "",
        ])
      }
    ]
  })
}

# =============================================================================
# Schedule Group
# =============================================================================

resource "aws_scheduler_schedule_group" "market_data" {
  count = (var.enable_eod_ingest_schedule || var.enable_earnings_update_schedule) ? 1 : 0

  name = "${var.project_name}-${var.environment}-market-data"

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-market-data"
      Purpose = "Schedule group for market data pipelines"
    }
  )
}

# =============================================================================
# Schedule — S&P 500 EOD 4-Hour Candle Ingestion
# =============================================================================
# 5:00 PM ET Mon-Fri (~1 hour after market close at 4 PM ET).

resource "aws_scheduler_schedule" "sp500_eod_ingest" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  name        = "${var.project_name}-${var.environment}-sp500-eod-4h-ingest"
  group_name  = aws_scheduler_schedule_group.market_data[0].name
  description = "Daily S&P 500 EOD price ingestion (5:00 PM ET, ~1h after market close)"

  schedule_expression          = "cron(0 17 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.functions["sp500_eod_ingest"].arn
    role_arn = aws_iam_role.scheduler_execution[0].arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.eod_ingest_dlq[0].arn
    }
  }
}

# =============================================================================
# Schedule — Earnings Update Post-Close
# =============================================================================
# 5:00 PM ET Mon-Fri — catches after-hours earnings reported shortly after close.

resource "aws_scheduler_schedule" "earnings_update_post_close" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  name        = "${var.project_name}-${var.environment}-earnings-update-post-close"
  group_name  = aws_scheduler_schedule_group.market_data[0].name
  description = "Earnings update after market close (5:00 PM ET)"

  schedule_expression          = "cron(0 17 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.functions["earnings_update"].arn
    role_arn = aws_iam_role.scheduler_execution[0].arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.earnings_update_dlq[0].arn
    }
  }
}

# =============================================================================
# Schedule — Earnings Update Post-Open
# =============================================================================
# 11:30 AM ET Mon-Fri — catches pre-market earnings reported before/after open.

resource "aws_scheduler_schedule" "earnings_update_post_open" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  name        = "${var.project_name}-${var.environment}-earnings-update-post-open"
  group_name  = aws_scheduler_schedule_group.market_data[0].name
  description = "Earnings update after market open (11:30 AM ET)"

  schedule_expression          = "cron(30 11 ? * MON-FRI *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.functions["earnings_update"].arn
    role_arn = aws_iam_role.scheduler_execution[0].arn
    input    = jsonencode({})

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }

    dead_letter_config {
      arn = aws_sqs_queue.earnings_update_dlq[0].arn
    }
  }
}
