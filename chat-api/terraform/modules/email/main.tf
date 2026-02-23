# =============================================================================
# Email Module - Resend Integration
# References existing Resend API key secret and provides IAM access
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
  module_tags = merge(var.common_tags, {
    Module  = "email"
    Service = "resend"
  })
}

# -----------------------------------------------------------------------------
# Data Source: Existing Resend API Key Secret
# The secret was created manually in AWS Secrets Manager.
# -----------------------------------------------------------------------------
data "aws_secretsmanager_secret" "resend_api_key" {
  name = var.resend_secret_name
}
