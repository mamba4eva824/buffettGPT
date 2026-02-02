# =============================================================================
# Stripe Secrets Manager Resources
# Naming convention: {service}-{key-type}-{environment}
# =============================================================================

# -----------------------------------------------------------------------------
# Stripe Secret Key (sk_test_xxx / sk_live_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_secret_key" {
  name        = local.stripe_secret_key_name
  description = "Stripe API secret key for ${var.environment} environment"

  tags = merge(local.module_tags, {
    Name        = local.stripe_secret_key_name
    Environment = var.environment
  })
}

# Note: Secret value must be set manually or via CI/CD
# Do not store actual keys in Terraform state
resource "aws_secretsmanager_secret_version" "stripe_secret_key" {
  count         = var.stripe_secret_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_secret_key.id
  secret_string = var.stripe_secret_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Webhook Secret (whsec_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_webhook_secret" {
  name        = local.stripe_webhook_secret_name
  description = "Stripe webhook signing secret for ${var.environment} environment"

  tags = merge(local.module_tags, {
    Name        = local.stripe_webhook_secret_name
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_webhook_secret" {
  count         = var.stripe_webhook_secret != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_webhook_secret.id
  secret_string = var.stripe_webhook_secret

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Plus Price ID (price_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_plus_price_id" {
  name        = local.stripe_plus_price_id_name
  description = "Stripe Plus plan price ID for ${var.environment} environment"

  tags = merge(local.module_tags, {
    Name        = local.stripe_plus_price_id_name
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_plus_price_id" {
  count         = var.stripe_plus_price_id != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_plus_price_id.id
  secret_string = var.stripe_plus_price_id

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Publishable Key (pk_test_xxx / pk_live_xxx)
# This is public, but stored in Secrets Manager for consistency
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_publishable_key" {
  name        = local.stripe_publishable_key_name
  description = "Stripe publishable key for ${var.environment} environment"

  tags = merge(local.module_tags, {
    Name        = local.stripe_publishable_key_name
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_publishable_key" {
  count         = var.stripe_publishable_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_publishable_key.id
  secret_string = var.stripe_publishable_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}
