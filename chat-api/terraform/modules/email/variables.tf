# =============================================================================
# Email Module - Variables
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

variable "resend_secret_name" {
  description = "Name of the existing Resend API key secret in Secrets Manager"
  type        = string
  default     = "resend_dev_key"
}

variable "resend_from_email" {
  description = "Email address to send from (requires verified domain in production)"
  type        = string
  default     = "onboarding@resend.dev"
}
