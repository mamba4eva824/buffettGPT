# Monitoring Module
# Manages CloudWatch alarms, dashboards, and SNS notifications

locals {
  resource_prefix = "${var.project_name}-${var.environment}"
}

# ================================================
# SNS Topic for Alerts
# ================================================

resource "aws_sns_topic" "alerts" {
  name         = "${local.resource_prefix}-alerts"
  display_name = "Chat API Alerts - ${var.environment}"

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-alerts"
      Purpose = "Alert notifications for chat API"
      Service = "SNS"
    }
  )
}

resource "aws_sns_topic_subscription" "alert_email" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# ================================================
# CloudWatch Log Groups for Monitoring
# ================================================

resource "aws_cloudwatch_log_group" "rate_limiting_logs" {
  name              = "/aws/monitoring/${local.resource_prefix}-rate-limiting"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-rate-limiting-logs"
      Purpose = "Rate limiting monitoring logs"
      Service = "CloudWatch Logs"
    }
  )
}

resource "aws_cloudwatch_log_group" "enhanced_rate_limiting_logs" {
  name              = "/aws/monitoring/${local.resource_prefix}-enhanced-rate-limiting"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-enhanced-rate-limiting-logs"
      Purpose = "Enhanced rate limiting monitoring logs"
      Service = "CloudWatch Logs"
    }
  )
}

resource "aws_cloudwatch_log_group" "provisioned_concurrency_logs" {
  name              = "/aws/monitoring/${local.resource_prefix}-provisioned-concurrency"
  retention_in_days = var.environment == "prod" ? 30 : 7

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-provisioned-concurrency-logs"
      Purpose = "Provisioned concurrency monitoring logs"
      Service = "CloudWatch Logs"
    }
  )
}

# ================================================
# Lambda Function Monitoring
# ================================================
# WebSocket and chat_processor alarms REMOVED (2026-02)
# per WEBSOCKET_DEPRECATION_PLAN.md

# Lambda Init Duration Monitoring
resource "aws_cloudwatch_metric_alarm" "lambda_init_duration_high" {
  alarm_name          = "${local.resource_prefix}-lambda-init-duration-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "InitDuration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "3000"  # 3 seconds
  alarm_description   = "Lambda init duration is high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = lookup(var.lambda_function_names, "analysis_followup", values(var.lambda_function_names)[0])
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-lambda-init-duration-high"
      Purpose = "Monitor Lambda cold starts"
      Service = "CloudWatch"
    }
  )
}

# ================================================
# API Gateway Monitoring
# ================================================
# WebSocket API alarms REMOVED (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md

# ================================================
# SQS Queue Monitoring - REMOVED (2026-02)
# ================================================
# SQS alarms deprecated per WEBSOCKET_DEPRECATION_PLAN.md

# ================================================
# DynamoDB Monitoring
# ================================================
# websocket-connections table alarm REMOVED (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md

# ================================================
# Rate Limiting Monitoring
# ================================================

# Rate Limit Exceeded
resource "aws_cloudwatch_metric_alarm" "rate_limit_exceeded" {
  alarm_name          = "${local.resource_prefix}-rate-limit-exceeded"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "RateLimitExceeded"
  namespace           = "ChatAPI/RateLimiting"
  period              = "300"
  statistic           = "Sum"
  threshold           = "50"
  alarm_description   = "Rate limits are being exceeded frequently"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-rate-limit-exceeded"
      Purpose = "Monitor rate limit violations"
      Service = "CloudWatch"
    }
  )
}

# Anonymous Usage Spike
resource "aws_cloudwatch_metric_alarm" "anonymous_usage_spike" {
  alarm_name          = "${local.resource_prefix}-anonymous-usage-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "AnonymousRequests"
  namespace           = "ChatAPI/Usage"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  alarm_description   = "Anonymous usage spike detected"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-anonymous-usage-spike"
      Purpose = "Monitor anonymous usage"
      Service = "CloudWatch"
    }
  )
}

# ================================================
# Provisioned Concurrency Monitoring
# ================================================

resource "aws_cloudwatch_metric_alarm" "provisioned_concurrency_utilization_high" {
  alarm_name          = "${local.resource_prefix}-provisioned-concurrency-utilization-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ProvisionedConcurrencyUtilization"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Average"
  threshold           = "0.8"  # 80%
  alarm_description   = "Provisioned concurrency utilization is high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = lookup(var.lambda_function_names, "analysis_followup", values(var.lambda_function_names)[0])
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-provisioned-concurrency-utilization-high"
      Purpose = "Monitor provisioned concurrency usage"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "provisioned_concurrency_spillover_high" {
  alarm_name          = "${local.resource_prefix}-provisioned-concurrency-spillover-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ProvisionedConcurrencySpilloverInvocations"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "Provisioned concurrency spillover is high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = lookup(var.lambda_function_names, "analysis_followup", values(var.lambda_function_names)[0])
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-provisioned-concurrency-spillover-high"
      Purpose = "Monitor provisioned concurrency spillover"
      Service = "CloudWatch"
    }
  )
}

# ================================================
# CloudWatch Dashboards
# ================================================

resource "aws_cloudwatch_dashboard" "chat_api_dashboard" {
  dashboard_name = "${local.resource_prefix}-chat-api"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/Lambda", "Invocations", { stat = "Sum" }],
            [".", "Errors", { stat = "Sum" }],
            [".", "Duration", { stat = "Average" }],
          ]
          period = 300
          stat   = "Average"
          region = "us-east-1"
          title  = "Lambda Function Metrics"
        }
      },
      {
        type = "metric"
        properties = {
          metrics = [
            ["AWS/ApiGateway", "Count", { stat = "Sum" }],
            [".", "4XXError", { stat = "Sum" }],
            [".", "5XXError", { stat = "Sum" }],
          ]
          period = 300
          stat   = "Sum"
          region = "us-east-1"
          title  = "API Gateway Metrics"
        }
      }
    ]
  })
}

resource "aws_cloudwatch_dashboard" "enhanced_rate_limiting" {
  dashboard_name = "${local.resource_prefix}-enhanced-rate-limiting"

  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric"
        properties = {
          metrics = [
            ["ChatAPI/RateLimiting", "RateLimitExceeded", { stat = "Sum" }],
            ["ChatAPI/Usage", "AnonymousRequests", { stat = "Sum" }],
            ["ChatAPI/Usage", "AuthenticatedRequests", { stat = "Sum" }],
          ]
          period = 300
          stat   = "Sum"
          region = "us-east-1"
          title  = "Rate Limiting Metrics"
        }
      }
    ]
  })
}

# ================================================
# Waitlist Monitoring
# ================================================

resource "aws_cloudwatch_metric_alarm" "waitlist_lambda_errors" {
  count               = contains(keys(var.lambda_function_names), "waitlist_handler") ? 1 : 0
  alarm_name          = "${local.resource_prefix}-waitlist-lambda-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Waitlist Lambda error rate is elevated"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names["waitlist_handler"]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-waitlist-lambda-errors"
      Purpose = "Monitor waitlist Lambda errors"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "waitlist_lambda_throttles" {
  count               = contains(keys(var.lambda_function_names), "waitlist_handler") ? 1 : 0
  alarm_name          = "${local.resource_prefix}-waitlist-lambda-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "Waitlist Lambda is being throttled"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names["waitlist_handler"]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-waitlist-lambda-throttles"
      Purpose = "Monitor waitlist Lambda throttling"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "waitlist_signup_spike" {
  count               = contains(keys(var.lambda_function_names), "waitlist_handler") ? 1 : 0
  alarm_name          = "${local.resource_prefix}-waitlist-signup-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Invocations"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  alarm_description   = "Waitlist signup volume spike detected - possible abuse"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names["waitlist_handler"]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-waitlist-signup-spike"
      Purpose = "Monitor waitlist signup abuse"
      Service = "CloudWatch"
    }
  )
}