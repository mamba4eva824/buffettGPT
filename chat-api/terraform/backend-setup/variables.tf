# Variables for Terraform Backend Infrastructure
# Configurable parameters for S3 backend setup

variable "project_name" {
  description = "Name of the project - used as prefix for all resources"
  type        = string
  default     = "buffett-chat"

  validation {
    condition     = can(regex("^[a-z0-9-]+$", var.project_name))
    error_message = "Project name must contain only lowercase letters, numbers, and hyphens."
  }
}

variable "aws_region" {
  description = "AWS region for backend resources"
  type        = string
  default     = "us-east-1"
}

variable "common_tags" {
  description = "Common tags to be applied to all resources"
  type        = map(string)
  default = {
    Environment = "shared"
    Project     = "buffett-chat"
    ManagedBy   = "Terraform"
    Purpose     = "Backend Infrastructure"
  }
}

variable "state_version_retention_days" {
  description = "Number of days to retain old versions of state files"
  type        = number
  default     = 30

  validation {
    condition     = var.state_version_retention_days >= 1 && var.state_version_retention_days <= 365
    error_message = "State version retention days must be between 1 and 365."
  }
}

variable "enable_deletion_protection" {
  description = "Enable deletion protection for DynamoDB table"
  type        = bool
  default     = true
}

variable "enable_audit_trail" {
  description = "Enable CloudTrail for audit logging"
  type        = bool
  default     = true
}

variable "enable_state_notifications" {
  description = "Enable SNS notifications for state changes"
  type        = bool
  default     = false
}

variable "enable_monitoring" {
  description = "Enable CloudWatch monitoring and alarms"
  type        = bool
  default     = true
}

variable "sns_topic_arn" {
  description = "ARN of existing SNS topic for notifications (optional)"
  type        = string
  default     = ""
}