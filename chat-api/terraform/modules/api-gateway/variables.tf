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

variable "authorizer_function_name" {
  description = "Name of the authorizer Lambda function"
  type        = string
  default     = null
}

variable "authorizer_function_arn_for_iam" {
  description = "Actual function ARN for IAM policies (not invoke ARN)"
  type        = string
  default     = null
}

variable "auth_callback_function_arn" {
  description = "ARN of the auth callback Lambda function"
  type        = string
  default     = null
}

variable "enable_conversations_routes" {
  description = "Enable conversation management routes"
  type        = bool
  default     = true
}

variable "enable_auth_routes" {
  description = "Enable auth callback routes"
  type        = bool
  default     = true
}

variable "enable_search" {
  description = "Enable AI search routes"
  type        = bool
  default     = false
}

variable "cloudfront_url" {
  description = "CloudFront URL to add to CORS allowed origins"
  type        = string
  default     = ""
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# ============================================================================
# Analysis Streaming API Variables
# ============================================================================

variable "enable_analysis_api" {
  description = "Enable the REST API for streaming analysis"
  type        = bool
  default     = false
}

variable "prediction_ensemble_invoke_arn" {
  description = "Invoke ARN of the prediction ensemble Lambda"
  type        = string
  default     = null
}

variable "prediction_ensemble_function_name" {
  description = "Name of the prediction ensemble Lambda function"
  type        = string
  default     = null
}

variable "auth_verify_invoke_arn" {
  description = "Invoke ARN of the auth_verify Lambda (from auth module)"
  type        = string
  default     = null
}

variable "auth_verify_function_name" {
  description = "Name of the auth_verify Lambda function (for permissions)"
  type        = string
  default     = null
}

variable "prediction_ensemble_function_url" {
  description = "Function URL for the prediction ensemble Lambda (for HTTP_PROXY integration)"
  type        = string
  default     = ""
}