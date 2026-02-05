# Core Module Outputs

# KMS Outputs
output "kms_key_id" {
  description = "ID of the KMS key"
  value       = aws_kms_key.chat_api_key.id
}

output "kms_key_arn" {
  description = "ARN of the KMS key"
  value       = aws_kms_key.chat_api_key.arn
}

output "kms_key_alias" {
  description = "Alias of the KMS key"
  value       = aws_kms_alias.chat_api_key_alias.name
}

# IAM Outputs
output "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  value       = aws_iam_role.lambda_role.arn
}

output "lambda_role_name" {
  description = "Name of the Lambda execution role"
  value       = aws_iam_role.lambda_role.name
}

output "lambda_policy_arn" {
  description = "ARN of the Lambda policy"
  value       = aws_iam_policy.lambda_policy.arn
}

# SQS Outputs - REMOVED (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md

# Account Information
output "account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "region" {
  description = "AWS region"
  value       = data.aws_region.current.name
}