# =============================================================================
# Stripe Module - Outputs
# =============================================================================

# -----------------------------------------------------------------------------
# Secret ARNs (for Lambda environment variables)
# -----------------------------------------------------------------------------
output "stripe_secret_key_arn" {
  description = "ARN of the Stripe secret key secret"
  value       = aws_secretsmanager_secret.stripe_secret_key.arn
}

output "stripe_webhook_secret_arn" {
  description = "ARN of the Stripe webhook secret"
  value       = aws_secretsmanager_secret.stripe_webhook_secret.arn
}

output "stripe_plus_price_id_arn" {
  description = "ARN of the Stripe Plus price ID secret"
  value       = aws_secretsmanager_secret.stripe_plus_price_id.arn
}

output "stripe_publishable_key_arn" {
  description = "ARN of the Stripe publishable key secret"
  value       = aws_secretsmanager_secret.stripe_publishable_key.arn
}

# -----------------------------------------------------------------------------
# Secret Names (for reference)
# -----------------------------------------------------------------------------
output "stripe_secret_key_name" {
  description = "Name of the Stripe secret key secret"
  value       = aws_secretsmanager_secret.stripe_secret_key.name
}

output "stripe_webhook_secret_name" {
  description = "Name of the Stripe webhook secret"
  value       = aws_secretsmanager_secret.stripe_webhook_secret.name
}

output "stripe_plus_price_id_name" {
  description = "Name of the Stripe Plus price ID secret"
  value       = aws_secretsmanager_secret.stripe_plus_price_id.name
}

output "stripe_publishable_key_name" {
  description = "Name of the Stripe publishable key secret"
  value       = aws_secretsmanager_secret.stripe_publishable_key.name
}

# -----------------------------------------------------------------------------
# IAM Policy (for Lambda role attachment)
# -----------------------------------------------------------------------------
output "stripe_secrets_policy_arn" {
  description = "ARN of the IAM policy for Stripe secrets access"
  value       = aws_iam_policy.stripe_secrets_access.arn
}

# -----------------------------------------------------------------------------
# Token Configuration
# -----------------------------------------------------------------------------
output "token_limit_plus" {
  description = "Token limit for Plus subscribers"
  value       = var.token_limit_plus
}
