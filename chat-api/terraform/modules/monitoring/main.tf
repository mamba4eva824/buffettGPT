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

# WebSocket Connect Function Monitoring
resource "aws_cloudwatch_metric_alarm" "websocket_connect_errors" {
  alarm_name          = "${local.resource_prefix}-websocket-connect-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "WebSocket connect function error rate is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "websocket_connect")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-connect-errors"
      Purpose = "Monitor WebSocket connect errors"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "websocket_connect_duration" {
  alarm_name          = "${local.resource_prefix}-websocket-connect-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Average"
  threshold           = "10000"  # 10 seconds
  alarm_description   = "WebSocket connect function duration is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "websocket_connect")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-connect-duration"
      Purpose = "Monitor WebSocket connect duration"
      Service = "CloudWatch"
    }
  )
}

# WebSocket Message Function Monitoring
resource "aws_cloudwatch_metric_alarm" "websocket_message_errors" {
  alarm_name          = "${local.resource_prefix}-websocket-message-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "WebSocket message function error rate is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "websocket_message")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-message-errors"
      Purpose = "Monitor WebSocket message errors"
      Service = "CloudWatch"
    }
  )
}

# Chat Processor Function Monitoring
resource "aws_cloudwatch_metric_alarm" "chat_processor_errors" {
  alarm_name          = "${local.resource_prefix}-chat-processor-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Chat processor function error rate is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "chat_processor")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-chat-processor-errors"
      Purpose = "Monitor chat processor errors"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "chat_processor_duration" {
  alarm_name          = "${local.resource_prefix}-chat-processor-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Average"
  threshold           = "20000"  # 20 seconds
  alarm_description   = "Chat processor function duration is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "chat_processor")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-chat-processor-duration"
      Purpose = "Monitor chat processor duration"
      Service = "CloudWatch"
    }
  )
}

resource "aws_cloudwatch_metric_alarm" "chat_processor_throttles" {
  alarm_name          = "${local.resource_prefix}-chat-processor-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "Chat processor function is being throttled"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = var.lambda_function_names[index(var.lambda_function_names, "chat_processor")]
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-chat-processor-throttles"
      Purpose = "Monitor chat processor throttles"
      Service = "CloudWatch"
    }
  )
}

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
    FunctionName = var.lambda_function_names[0]  # Monitor first function as representative
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

# WebSocket API 4xx Errors
resource "aws_cloudwatch_metric_alarm" "websocket_api_4xx_errors" {
  alarm_name          = "${local.resource_prefix}-websocket-api-4xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "4XXError"
  namespace           = "AWS/ApiGateway"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "WebSocket API 4xx error rate is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = var.websocket_api_id
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-api-4xx-errors"
      Purpose = "Monitor WebSocket API 4xx errors"
      Service = "CloudWatch"
    }
  )
}

# WebSocket API 5xx Errors
resource "aws_cloudwatch_metric_alarm" "websocket_api_5xx_errors" {
  alarm_name          = "${local.resource_prefix}-websocket-api-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = "60"
  statistic           = "Sum"
  threshold           = "5"
  alarm_description   = "WebSocket API 5xx error rate is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  ok_actions          = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = var.websocket_api_id
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-api-5xx-errors"
      Purpose = "Monitor WebSocket API 5xx errors"
      Service = "CloudWatch"
    }
  )
}

# WebSocket API Integration Latency
resource "aws_cloudwatch_metric_alarm" "websocket_api_integration_latency" {
  alarm_name          = "${local.resource_prefix}-websocket-api-integration-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "IntegrationLatency"
  namespace           = "AWS/ApiGateway"
  period              = "60"
  statistic           = "Average"
  threshold           = "5000"  # 5 seconds
  alarm_description   = "WebSocket API integration latency is too high"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = var.websocket_api_id
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-websocket-api-integration-latency"
      Purpose = "Monitor WebSocket API latency"
      Service = "CloudWatch"
    }
  )
}

# ================================================
# SQS Queue Monitoring
# ================================================

# Processing Queue Depth
resource "aws_cloudwatch_metric_alarm" "processing_queue_depth" {
  alarm_name          = "${local.resource_prefix}-processing-queue-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "100"
  alarm_description   = "Processing queue has too many messages"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = "${local.resource_prefix}-chat-processing-queue"
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-processing-queue-depth"
      Purpose = "Monitor SQS queue depth"
      Service = "CloudWatch"
    }
  )
}

# Processing Queue Age
resource "aws_cloudwatch_metric_alarm" "processing_queue_age" {
  alarm_name          = "${local.resource_prefix}-processing-queue-age"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "300"  # 5 minutes
  alarm_description   = "Processing queue messages are too old"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = "${local.resource_prefix}-chat-processing-queue"
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-processing-queue-age"
      Purpose = "Monitor SQS message age"
      Service = "CloudWatch"
    }
  )
}

# DLQ Messages
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name          = "${local.resource_prefix}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = "60"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "Messages in dead letter queue"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = "${local.resource_prefix}-chat-dlq"
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-dlq-messages"
      Purpose = "Monitor DLQ messages"
      Service = "CloudWatch"
    }
  )
}

# ================================================
# DynamoDB Monitoring
# ================================================

# Connections Table Throttles
resource "aws_cloudwatch_metric_alarm" "connections_table_throttles" {
  alarm_name          = "${local.resource_prefix}-connections-table-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "UserErrors"
  namespace           = "AWS/DynamoDB"
  period              = "60"
  statistic           = "Sum"
  threshold           = "10"
  alarm_description   = "DynamoDB connections table is being throttled"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  treat_missing_data  = "notBreaching"

  dimensions = {
    TableName = "${local.resource_prefix}-websocket-connections"
  }

  tags = merge(
    var.common_tags,
    {
      Name    = "${local.resource_prefix}-connections-table-throttles"
      Purpose = "Monitor DynamoDB throttles"
      Service = "CloudWatch"
    }
  )
}

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
    FunctionName = var.lambda_function_names[0]  # Monitor first function as representative
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
    FunctionName = var.lambda_function_names[0]  # Monitor first function as representative
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