# DynamoDB Table for Terraform State Locking
# Provides concurrent access control for Terraform operations

resource "aws_dynamodb_table" "terraform_state_locks" {
  name           = "${var.project_name}-terraform-state-locks"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  # Enable point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }

  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_arn = aws_kms_key.terraform_state.arn
  }

  # Deletion protection for production
  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-terraform-state-locks"
    Purpose = "Terraform State Locking"
  })
}

# CloudWatch Alarms for DynamoDB Table
resource "aws_cloudwatch_metric_alarm" "dynamodb_read_throttle" {
  count = var.enable_monitoring ? 1 : 0

  alarm_name          = "${var.project_name}-terraform-locks-read-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ReadThrottledEvents"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors read throttle events on Terraform state locks table"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    TableName = aws_dynamodb_table.terraform_state_locks.name
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_metric_alarm" "dynamodb_write_throttle" {
  count = var.enable_monitoring ? 1 : 0

  alarm_name          = "${var.project_name}-terraform-locks-write-throttle"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "WriteThrottledEvents"
  namespace           = "AWS/DynamoDB"
  period              = "300"
  statistic           = "Sum"
  threshold           = "0"
  alarm_description   = "This metric monitors write throttle events on Terraform state locks table"
  alarm_actions       = var.sns_topic_arn != "" ? [var.sns_topic_arn] : []

  dimensions = {
    TableName = aws_dynamodb_table.terraform_state_locks.name
  }

  tags = var.common_tags
}