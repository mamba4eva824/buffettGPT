variable "agent_id" {
  description = "The unique identifier of the agent to attach the action group to"
  type        = string
}

variable "agent_version" {
  description = "The version of the agent (use 'DRAFT' for development)"
  type        = string
  default     = "DRAFT"
}

variable "action_group_name" {
  description = "Name for the action group"
  type        = string
}

variable "description" {
  description = "Description of what this action group does"
  type        = string
}

variable "skip_resource_in_use_check" {
  description = "Whether to skip checking if the resource is in use"
  type        = bool
  default     = false
}

variable "lambda_arn" {
  description = "ARN of the Lambda function that executes the action"
  type        = string
}

variable "lambda_function_name" {
  description = "Name of the Lambda function (for permission resource)"
  type        = string
}

variable "agent_arn" {
  description = "ARN of the agent (for Lambda permission source)"
  type        = string
}

variable "api_schema_content" {
  description = "OpenAPI 3.0 schema content defining the action group API"
  type        = string
}

variable "parent_action_group_signature" {
  description = "Parent action group signature if extending another action group"
  type        = string
  default     = null
}

variable "lambda_permission_statement_id" {
  description = "Statement ID for the Lambda permission (must be unique)"
  type        = string
  default     = "AllowBedrockInvoke"
}
