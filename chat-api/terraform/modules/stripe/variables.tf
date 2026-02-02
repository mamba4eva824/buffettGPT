# =============================================================================
# Stripe Module - Variables
# =============================================================================

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Stripe Secrets (Optional - can be set via CI/CD or manually in AWS Console)
# -----------------------------------------------------------------------------
variable "stripe_secret_key" {
  description = "Stripe API secret key (optional, can be set manually)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret (optional, can be set manually)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_plus_price_id" {
  description = "Stripe Plus plan price ID (optional, can be set manually)"
  type        = string
  default     = ""
}

variable "stripe_publishable_key" {
  description = "Stripe publishable key (optional, can be set manually)"
  type        = string
  default     = ""
}

# -----------------------------------------------------------------------------
# Token Limits
# -----------------------------------------------------------------------------
variable "token_limit_plus" {
  description = "Monthly token limit for Plus subscribers"
  type        = number
  default     = 2000000
}
