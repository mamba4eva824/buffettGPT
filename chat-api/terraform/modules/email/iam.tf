# =============================================================================
# Email Module - IAM Policies
# Provides Lambda access to Resend API key in Secrets Manager
# =============================================================================

# -----------------------------------------------------------------------------
# IAM Policy Document - Resend Secret Read Access
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "resend_secrets_access" {
  statement {
    sid    = "ReadResendSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      data.aws_secretsmanager_secret.resend_api_key.arn,
    ]
  }
}

# -----------------------------------------------------------------------------
# IAM Policy - Resend Secrets Access
# Attach this policy to Lambda execution roles that need email sending
# -----------------------------------------------------------------------------
resource "aws_iam_policy" "resend_secrets_access" {
  name        = "resend-secrets-access-${var.environment}"
  description = "Allow Lambda functions to read Resend API key from Secrets Manager"
  policy      = data.aws_iam_policy_document.resend_secrets_access.json

  tags = merge(local.module_tags, {
    Name        = "resend-secrets-access-${var.environment}"
    Environment = var.environment
  })
}
