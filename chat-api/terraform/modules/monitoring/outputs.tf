# Monitoring Module Outputs

output "sns_topic_arn" {
  description = "ARN of the SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "alarm_arns" {
  description = "ARNs of all CloudWatch alarms"
  value = {
    websocket_connect_errors                 = aws_cloudwatch_metric_alarm.websocket_connect_errors.arn
    websocket_connect_duration               = aws_cloudwatch_metric_alarm.websocket_connect_duration.arn
    websocket_message_errors                  = aws_cloudwatch_metric_alarm.websocket_message_errors.arn
    chat_processor_errors                     = aws_cloudwatch_metric_alarm.chat_processor_errors.arn
    chat_processor_duration                   = aws_cloudwatch_metric_alarm.chat_processor_duration.arn
    chat_processor_throttles                  = aws_cloudwatch_metric_alarm.chat_processor_throttles.arn
    lambda_init_duration_high                 = aws_cloudwatch_metric_alarm.lambda_init_duration_high.arn
    websocket_api_4xx_errors                  = aws_cloudwatch_metric_alarm.websocket_api_4xx_errors.arn
    websocket_api_5xx_errors                  = aws_cloudwatch_metric_alarm.websocket_api_5xx_errors.arn
    websocket_api_integration_latency         = aws_cloudwatch_metric_alarm.websocket_api_integration_latency.arn
    processing_queue_depth                    = aws_cloudwatch_metric_alarm.processing_queue_depth.arn
    processing_queue_age                      = aws_cloudwatch_metric_alarm.processing_queue_age.arn
    dlq_messages                              = aws_cloudwatch_metric_alarm.dlq_messages.arn
    connections_table_throttles               = aws_cloudwatch_metric_alarm.connections_table_throttles.arn
    rate_limit_exceeded                       = aws_cloudwatch_metric_alarm.rate_limit_exceeded.arn
    anonymous_usage_spike                     = aws_cloudwatch_metric_alarm.anonymous_usage_spike.arn
    provisioned_concurrency_utilization_high  = aws_cloudwatch_metric_alarm.provisioned_concurrency_utilization_high.arn
    provisioned_concurrency_spillover_high    = aws_cloudwatch_metric_alarm.provisioned_concurrency_spillover_high.arn
  }
}

output "dashboard_urls" {
  description = "URLs to CloudWatch dashboards"
  value = {
    chat_api_dashboard       = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.chat_api_dashboard.dashboard_name}"
    enhanced_rate_limiting   = "https://console.aws.amazon.com/cloudwatch/home?region=${data.aws_region.current.name}#dashboards:name=${aws_cloudwatch_dashboard.enhanced_rate_limiting.dashboard_name}"
  }
}

output "log_group_names" {
  description = "Names of CloudWatch log groups"
  value = {
    rate_limiting_logs           = aws_cloudwatch_log_group.rate_limiting_logs.name
    enhanced_rate_limiting_logs  = aws_cloudwatch_log_group.enhanced_rate_limiting_logs.name
    provisioned_concurrency_logs = aws_cloudwatch_log_group.provisioned_concurrency_logs.name
  }
}

# Data source for current region
data "aws_region" "current" {}