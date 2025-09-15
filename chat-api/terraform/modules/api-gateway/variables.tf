# API Gateway Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "lambda_arns" {
  description = "Map of Lambda function ARNs"
  type        = map(string)
}

variable "enable_cors" {
  description = "Enable CORS for API Gateway"
  type        = bool
  default     = true
}

variable "enable_authorization" {
  description = "Enable authorization for API Gateway"
  type        = bool
  default     = false
}

variable "authorizer_function_arn" {
  description = "ARN of the authorizer Lambda function"
  type        = string
  default     = null
}

variable "auth_callback_function_arn" {
  description = "ARN of the auth callback Lambda function"
  type        = string
  default     = null
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}