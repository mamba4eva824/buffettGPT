# =============================================================================
# Email Module - Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# Secret ARN (for Lambda environment variables)
# -----------------------------------------------------------------------------
output "resend_api_key_arn" {
  description = "ARN of the Resend API key secret"
  value       = data.aws_secretsmanager_secret.resend_api_key.arn
}

# -----------------------------------------------------------------------------
# From Email (for Lambda environment variables)
# -----------------------------------------------------------------------------
output "resend_from_email" {
  description = "Email address to send from"
  value       = var.resend_from_email
}

# -----------------------------------------------------------------------------
# IAM Policy (for Lambda role attachment)
# -----------------------------------------------------------------------------
output "resend_secrets_policy_arn" {
  description = "ARN of the IAM policy for Resend secrets access"
  value       = aws_iam_policy.resend_secrets_access.arn
}
