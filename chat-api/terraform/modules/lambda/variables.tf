# Lambda Module Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "lambda_role_arn" {
  description = "ARN of the Lambda execution role"
  type        = string
}

variable "lambda_package_path" {
  description = "Path to Lambda deployment packages"
  type        = string
  default     = "../../lambda-packages"
}

variable "runtime" {
  description = "Lambda runtime"
  type        = string
  default     = "python3.11"
}

variable "common_env_vars" {
  description = "Common environment variables for all Lambda functions"
  type        = map(string)
  default     = {}
}

variable "function_env_vars" {
  description = "Function-specific environment variables"
  type        = map(map(string))
  default     = {}
}

variable "dlq_arn" {
  description = "ARN of the dead letter queue"
  type        = string
}


variable "chat_processing_queue_arn" {
  description = "ARN of the chat processing SQS queue"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 7
}

variable "reserved_concurrency" {
  description = "Reserved concurrent executions per function"
  type        = map(number)
  default     = {}
}

variable "sqs_batch_window" {
  description = "Maximum batching window for SQS in seconds"
  type        = number
  default     = 10
}

variable "sqs_max_concurrency" {
  description = "Maximum concurrent executions for SQS processor"
  type        = number
  default     = 2
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}