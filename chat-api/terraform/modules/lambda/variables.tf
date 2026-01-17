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

# Debt Analyzer Variables
variable "cloudfront_url" {
  description = "CloudFront URL for CORS configuration"
  type        = string
  default     = ""
}

variable "debt_analyzer_image_tag" {
  description = "Docker image tag for debt analyzer Lambda"
  type        = string
  default     = "latest"
}

variable "model_s3_bucket" {
  description = "S3 bucket containing ML models"
  type        = string
  default     = ""
}

variable "debt_analyzer_model_version" {
  description = "Version of the debt analyzer ML model"
  type        = string
  default     = "1"
}

variable "financial_cache_table" {
  description = "DynamoDB table name for financial data cache"
  type        = string
  default     = ""
}

variable "idempotency_table" {
  description = "DynamoDB table name for idempotency tracking"
  type        = string
  default     = ""
}

variable "kms_key_arn" {
  description = "KMS key ARN for encryption"
  type        = string
  default     = ""
}

variable "debt_analyzer_provisioned_concurrency" {
  description = "Provisioned concurrency for debt analyzer Lambda"
  type        = number
  default     = 0
}

# Function URL CORS Configuration
variable "cors_allowed_origins" {
  description = "Allowed origins for Lambda Function URL CORS"
  type        = list(string)
  default     = ["http://localhost:3000", "http://localhost:5173"]
}

# Prediction Ensemble Variables
variable "prediction_ensemble_image_tag" {
  description = "Docker image tag for prediction ensemble Lambda"
  type        = string
  default     = "latest"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for ConverseStream API (Claude Haiku 4.5 via US cross-region inference profile)"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

# Investment Research Variables
variable "investment_research_image_tag" {
  description = "Docker image tag for investment research Lambda"
  type        = string
  default     = "v1.0.0"
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