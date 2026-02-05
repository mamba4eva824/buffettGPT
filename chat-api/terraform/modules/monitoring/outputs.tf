# Monitoring Module Outputs

output "sns_topic_arn" {
  description = "ARN of the SNS topic for alerts"
  value       = aws_sns_topic.alerts.arn
}

output "alarm_arns" {
  description = "ARNs of all CloudWatch alarms"
  # Updated 2026-02: Removed WebSocket, chat_processor, SQS alarms per WEBSOCKET_DEPRECATION_PLAN.md
  value = {
    lambda_init_duration_high                = aws_cloudwatch_metric_alarm.lambda_init_duration_high.arn
    rate_limit_exceeded                      = aws_cloudwatch_metric_alarm.rate_limit_exceeded.arn
    anonymous_usage_spike                    = aws_cloudwatch_metric_alarm.anonymous_usage_spike.arn
    provisioned_concurrency_utilization_high = aws_cloudwatch_metric_alarm.provisioned_concurrency_utilization_high.arn
    provisioned_concurrency_spillover_high   = aws_cloudwatch_metric_alarm.provisioned_concurrency_spillover_high.arn
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