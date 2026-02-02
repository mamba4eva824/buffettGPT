# =============================================================================
# Stripe Module - IAM Policies
# Provides Lambda access to Stripe secrets in Secrets Manager
# =============================================================================

# -----------------------------------------------------------------------------
# IAM Policy Document - Stripe Secrets Read Access
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "stripe_secrets_access" {
  statement {
    sid    = "ReadStripeSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      aws_secretsmanager_secret.stripe_secret_key.arn,
      aws_secretsmanager_secret.stripe_webhook_secret.arn,
      aws_secretsmanager_secret.stripe_plus_price_id.arn,
    ]
  }
}

# -----------------------------------------------------------------------------
# IAM Policy - Stripe Secrets Access
# Attach this policy to Lambda execution roles that need Stripe API access
# -----------------------------------------------------------------------------
resource "aws_iam_policy" "stripe_secrets_access" {
  name        = "stripe-secrets-access-${var.environment}"
  description = "Allow Lambda functions to read Stripe secrets from Secrets Manager"
  policy      = data.aws_iam_policy_document.stripe_secrets_access.json

  tags = merge(local.module_tags, {
    Name        = "stripe-secrets-access-${var.environment}"
    Environment = var.environment
  })
}
