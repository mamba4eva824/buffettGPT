# =============================================================================
# SNS Publish Permission — Pipeline Notifications
# =============================================================================
# Allows Lambda functions to publish run summaries to the alerts SNS topic.

resource "aws_iam_role_policy" "pipeline_sns_publish" {
  count = var.alerts_sns_topic_arn != "" ? 1 : 0

  name = "${var.project_name}-${var.environment}-pipeline-sns-publish"
  role = element(split("/", var.lambda_role_arn), length(split("/", var.lambda_role_arn)) - 1)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = var.alerts_sns_topic_arn
      }
    ]
  })
}

# =============================================================================
# Dead Letter Queue — S&P 500 EOD Ingest Pipeline
# =============================================================================
# Captures failed Lambda invocations after EventBridge retries are exhausted.
# CloudWatch alarm fires when any message lands in the queue.

resource "aws_sqs_queue" "eod_ingest_dlq" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  name                      = "${var.project_name}-${var.environment}-eod-ingest-dlq"
  message_retention_seconds = 1209600  # 14 days

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-eod-ingest-dlq"
      Purpose = "Dead letter queue for failed sp500_eod_ingest invocations"
    }
  )
}

# Allow the Lambda to send messages to the DLQ
resource "aws_iam_role_policy" "eod_ingest_dlq_send" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  name = "${var.project_name}-${var.environment}-eod-ingest-dlq-send"
  role = element(split("/", var.lambda_role_arn), length(split("/", var.lambda_role_arn)) - 1)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.eod_ingest_dlq[0].arn
      }
    ]
  })
}

# Attach DLQ to the sp500_eod_ingest Lambda
resource "aws_lambda_function_event_invoke_config" "eod_ingest_dlq_config" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  function_name = aws_lambda_function.functions["sp500_eod_ingest"].function_name

  destination_config {
    on_failure {
      destination = aws_sqs_queue.eod_ingest_dlq[0].arn
    }
  }
}

# =============================================================================
# CloudWatch Alarm — DLQ Depth
# =============================================================================
# Fires when any message arrives in the DLQ (threshold >= 1).

resource "aws_cloudwatch_metric_alarm" "eod_ingest_dlq_depth" {
  count = var.enable_eod_ingest_schedule ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-eod-ingest-dlq-depth"
  alarm_description   = "S&P 500 EOD ingest failed — message in DLQ"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alerts_sns_topic_arn != "" ? [var.alerts_sns_topic_arn] : []

  dimensions = {
    QueueName = aws_sqs_queue.eod_ingest_dlq[0].name
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-eod-ingest-dlq-alarm"
      Purpose = "Alert on failed EOD price ingestion"
    }
  )
}

# =============================================================================
# Dead Letter Queue — Earnings Update Pipeline
# =============================================================================
# Captures failed Lambda invocations after EventBridge Scheduler retries are exhausted.
# CloudWatch alarm fires when any message lands in the queue.

resource "aws_sqs_queue" "earnings_update_dlq" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  name                      = "${var.project_name}-${var.environment}-earnings-update-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-earnings-update-dlq"
      Purpose = "Dead letter queue for failed earnings_update invocations"
    }
  )
}

# Allow the Lambda to send messages to the DLQ
resource "aws_iam_role_policy" "earnings_update_dlq_send" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  name = "${var.project_name}-${var.environment}-earnings-update-dlq-send"
  role = element(split("/", var.lambda_role_arn), length(split("/", var.lambda_role_arn)) - 1)

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sqs:SendMessage"]
        Resource = aws_sqs_queue.earnings_update_dlq[0].arn
      }
    ]
  })
}

# Attach DLQ to the earnings_update Lambda
resource "aws_lambda_function_event_invoke_config" "earnings_update_dlq_config" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  function_name = aws_lambda_function.functions["earnings_update"].function_name

  destination_config {
    on_failure {
      destination = aws_sqs_queue.earnings_update_dlq[0].arn
    }
  }
}

# =============================================================================
# CloudWatch Alarm — Earnings Update DLQ Depth
# =============================================================================
# Fires when any message arrives in the DLQ (threshold >= 1).

resource "aws_cloudwatch_metric_alarm" "earnings_update_dlq_depth" {
  count = var.enable_earnings_update_schedule ? 1 : 0

  alarm_name          = "${var.project_name}-${var.environment}-earnings-update-dlq-depth"
  alarm_description   = "Earnings update failed — message in DLQ"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alerts_sns_topic_arn != "" ? [var.alerts_sns_topic_arn] : []

  dimensions = {
    QueueName = aws_sqs_queue.earnings_update_dlq[0].name
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-earnings-update-dlq-alarm"
      Purpose = "Alert on failed earnings update"
    }
  )
}
