# CloudFront Static Site Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "price_class" {
  description = "CloudFront distribution price class"
  type        = string
  default     = "PriceClass_100" # US, Canada, Europe
  validation {
    condition     = contains(["PriceClass_100", "PriceClass_200", "PriceClass_All"], var.price_class)
    error_message = "Price class must be one of: PriceClass_100, PriceClass_200, PriceClass_All"
  }
}

variable "wait_for_deployment" {
  description = "Wait for CloudFront distribution deployment to complete"
  type        = bool
  default     = true
}

variable "site_name" {
  description = "Short name to distinguish this site (e.g., 'app' or 'landing')"
  type        = string
  default     = "frontend"
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}