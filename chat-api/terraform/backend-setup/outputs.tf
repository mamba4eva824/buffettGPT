# Outputs for Terraform Backend Infrastructure
# Values needed for configuring backend in other Terraform configurations

output "s3_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.bucket
}

output "s3_bucket_arn" {
  description = "ARN of the S3 bucket for Terraform state"
  value       = aws_s3_bucket.terraform_state.arn
}

output "s3_bucket_region" {
  description = "Region of the S3 bucket"
  value       = aws_s3_bucket.terraform_state.region
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.terraform_state_locks.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table for state locking"
  value       = aws_dynamodb_table.terraform_state_locks.arn
}

output "kms_key_id" {
  description = "ID of the KMS key for encryption"
  value       = aws_kms_key.terraform_state.key_id
}

output "kms_key_arn" {
  description = "ARN of the KMS key for encryption"
  value       = aws_kms_key.terraform_state.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key"
  value       = aws_kms_alias.terraform_state.name
}

# IAM Role ARNs for team access
output "terraform_admin_role_arn" {
  description = "ARN of the Terraform admin role"
  value       = aws_iam_role.terraform_admin.arn
}

output "terraform_developer_role_arn" {
  description = "ARN of the Terraform developer role"
  value       = aws_iam_role.terraform_developer.arn
}

output "terraform_readonly_role_arn" {
  description = "ARN of the Terraform read-only role"
  value       = aws_iam_role.terraform_readonly.arn
}

# CloudTrail outputs (conditional)
output "cloudtrail_name" {
  description = "Name of the CloudTrail for audit logging"
  value       = var.enable_audit_trail ? aws_cloudtrail.terraform_state_audit[0].name : null
}

output "cloudtrail_s3_bucket" {
  description = "S3 bucket for CloudTrail logs"
  value       = var.enable_audit_trail ? aws_s3_bucket.cloudtrail_logs[0].bucket : null
}

# SNS Topic (conditional)
output "sns_topic_arn" {
  description = "ARN of SNS topic for state notifications"
  value       = var.enable_state_notifications ? aws_sns_topic.terraform_state_notifications[0].arn : null
}

# Backend Configuration Template
output "backend_config" {
  description = "Backend configuration for use in other Terraform configurations"
  value = {
    bucket         = aws_s3_bucket.terraform_state.bucket
    region         = var.aws_region
    encrypt        = true
    kms_key_id     = aws_kms_key.terraform_state.arn
    dynamodb_table = aws_dynamodb_table.terraform_state_locks.name
  }
}

# HCL Backend Configuration (for copy-paste)
output "backend_config_hcl" {
  description = "Backend configuration in HCL format"
  value = <<-EOT
    terraform {
      backend "s3" {
        bucket         = "${aws_s3_bucket.terraform_state.bucket}"
        key            = "ENVIRONMENT/terraform.tfstate"  # Replace ENVIRONMENT with dev/staging/prod
        region         = "${var.aws_region}"
        encrypt        = true
        kms_key_id     = "${aws_kms_key.terraform_state.arn}"
        dynamodb_table = "${aws_dynamodb_table.terraform_state_locks.name}"
      }
    }
    EOT
}