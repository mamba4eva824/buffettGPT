# CloudTrail Configuration for Terraform State Audit Logging
# Provides comprehensive audit trail for all state-related activities

# S3 Bucket for CloudTrail Logs
resource "aws_s3_bucket" "cloudtrail_logs" {
  count  = var.enable_audit_trail ? 1 : 0
  bucket = "${var.project_name}-terraform-cloudtrail-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-terraform-cloudtrail"
    Purpose = "CloudTrail Audit Logs for Terraform State"
  })
}

# CloudTrail Logs Bucket Versioning
resource "aws_s3_bucket_versioning" "cloudtrail_logs" {
  count  = var.enable_audit_trail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id
  versioning_configuration {
    status = "Enabled"
  }
}

# CloudTrail Logs Bucket Encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "cloudtrail_logs" {
  count  = var.enable_audit_trail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.terraform_state.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

# CloudTrail Logs Bucket Public Access Block
resource "aws_s3_bucket_public_access_block" "cloudtrail_logs" {
  count  = var.enable_audit_trail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# CloudTrail Logs Bucket Policy
resource "aws_s3_bucket_policy" "cloudtrail_logs" {
  count  = var.enable_audit_trail ? 1 : 0
  bucket = aws_s3_bucket.cloudtrail_logs[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.cloudtrail_logs[0].arn
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.cloudtrail_logs[0].arn}/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl" = "bucket-owner-full-control"
          }
        }
      }
    ]
  })
}

# CloudTrail for S3 and DynamoDB Audit
resource "aws_cloudtrail" "terraform_state_audit" {
  count                         = var.enable_audit_trail ? 1 : 0
  name                          = "${var.project_name}-terraform-state-audit"
  s3_bucket_name               = aws_s3_bucket.cloudtrail_logs[0].bucket
  s3_key_prefix                = "terraform-state-logs"
  include_global_service_events = false
  is_multi_region_trail        = false
  enable_logging               = true
  enable_log_file_validation   = true
  kms_key_id                   = aws_kms_key.terraform_state.arn

  # Event Selectors for S3 and DynamoDB
  event_selector {
    read_write_type                 = "All"
    include_management_events       = false

    # Monitor S3 state bucket
    data_resource {
      type   = "AWS::S3::Object"
      values = ["${aws_s3_bucket.terraform_state.arn}/*"]
    }

    # Monitor DynamoDB state locks table
    data_resource {
      type   = "AWS::DynamoDB::Table"
      values = [aws_dynamodb_table.terraform_state_locks.arn]
    }
  }

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-terraform-state-audit"
    Purpose = "Terraform State Audit Trail"
  })
}

# SNS Topic for CloudTrail Notifications (optional)
resource "aws_sns_topic" "terraform_state_notifications" {
  count             = var.enable_state_notifications ? 1 : 0
  name              = "${var.project_name}-terraform-state-notifications"
  kms_master_key_id = aws_kms_key.terraform_state.arn

  tags = merge(var.common_tags, {
    Name    = "${var.project_name}-terraform-state-notifications"
    Purpose = "Terraform State Change Notifications"
  })
}

# EventBridge Rule for S3 State Changes
resource "aws_cloudwatch_event_rule" "s3_state_changes" {
  count       = var.enable_state_notifications ? 1 : 0
  name        = "${var.project_name}-s3-state-changes"
  description = "Captures S3 events for Terraform state changes"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created", "Object Deleted"]
    detail = {
      bucket = {
        name = [aws_s3_bucket.terraform_state.bucket]
      }
    }
  })

  tags = var.common_tags
}

# SNS Topic Target for EventBridge Rule
resource "aws_cloudwatch_event_target" "sns" {
  count     = var.enable_state_notifications ? 1 : 0
  rule      = aws_cloudwatch_event_rule.s3_state_changes[0].name
  target_id = "SendToSNS"
  arn       = aws_sns_topic.terraform_state_notifications[0].arn
}