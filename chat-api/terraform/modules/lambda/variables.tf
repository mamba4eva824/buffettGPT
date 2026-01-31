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

# ================================================
# ML/Ensemble Variables (ARCHIVED - 2025-01)
# ================================================
# NOTE: The following variables were removed when prediction ensemble was archived:
# - cloudfront_url, debt_analyzer_image_tag, model_s3_bucket, debt_analyzer_model_version
# - financial_cache_table, idempotency_table, debt_analyzer_provisioned_concurrency
# - prediction_ensemble_image_tag
# See: archived/prediction_ensemble/

# KMS key ARN for encryption
variable "kms_key_arn" {
  description = "KMS key ARN for encryption"
  type        = string
  default     = ""
}

# Function URL CORS Configuration
variable "cors_allowed_origins" {
  description = "Allowed origins for Lambda Function URL CORS"
  type        = list(string)
  default     = ["http://localhost:3000", "http://localhost:5173"]
}

# Bedrock Model ID for ConverseStream API
variable "bedrock_model_id" {
  description = "Bedrock model ID for ConverseStream API (Claude Haiku 4.5 via US cross-region inference profile)"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

# Investment Research Variables
variable "investment_research_image_tag" {
  description = "Docker image tag for investment research Lambda"
  type        = string
  default     = "v1.1.0"
}

# Followup Action Variables
variable "followup_action_image_tag" {
  description = "Docker image tag for followup action Lambda (Bedrock action group handler)"
  type        = string
  default     = "v1.0.0"
}

variable "create_followup_action_lambda" {
  description = "Whether to create the followup action Lambda. Set to false on first deploy until Docker image is pushed to ECR."
  type        = bool
  default     = false
}

variable "investment_reports_v2_table_arn" {
  description = "ARN of the investment reports v2 DynamoDB table for followup-action Lambda IAM policy"
  type        = string
  default     = ""
}

variable "financial_data_cache_table_arn" {
  description = "ARN of the financial data cache DynamoDB table for followup-action Lambda IAM policy"
  type        = string
  default     = ""
}

variable "investment_reports_v2_table_name" {
  description = "Name of the investment reports v2 DynamoDB table for followup-action Lambda env var"
  type        = string
  default     = ""
}

variable "financial_data_cache_table_name" {
  description = "Name of the financial data cache DynamoDB table for followup-action Lambda env var"
  type        = string
  default     = ""
}

variable "metrics_history_cache_table_arn" {
  description = "ARN of the metrics history cache DynamoDB table for followup-action Lambda IAM policy"
  type        = string
  default     = ""
}

variable "metrics_history_cache_table_name" {
  description = "Name of the metrics history cache DynamoDB table for followup-action Lambda env var"
  type        = string
  default     = ""
}