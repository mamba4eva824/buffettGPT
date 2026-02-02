# =============================================================================
# Stripe Module - Main Configuration
# Provides Stripe payment integration infrastructure for BuffettGPT
# =============================================================================

terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

# -----------------------------------------------------------------------------
# Local Values
# -----------------------------------------------------------------------------
locals {
  # Secret names following the convention: {service}-{key-type}-{env}
  stripe_secret_key_name      = "stripe-secret-key-${var.environment}"
  stripe_webhook_secret_name  = "stripe-webhook-secret-${var.environment}"
  stripe_plus_price_id_name   = "stripe-plus-price-id-${var.environment}"
  stripe_publishable_key_name = "stripe-publishable-key-${var.environment}"

  # Common tags for all resources in this module
  module_tags = merge(var.common_tags, {
    Module  = "stripe"
    Service = "stripe"
  })
}
