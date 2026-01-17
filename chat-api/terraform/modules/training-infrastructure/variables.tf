# Variables for the training infrastructure module

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "buffett-chat-ml"
}

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

# DynamoDB Configuration
variable "dynamodb_billing_mode" {
  description = "DynamoDB billing mode"
  type        = string
  default     = "PAY_PER_REQUEST"
}

variable "enable_point_in_time_recovery" {
  description = "Enable point-in-time recovery for DynamoDB tables"
  type        = bool
  default     = true
}

variable "enable_encryption" {
  description = "Enable encryption at rest for DynamoDB tables"
  type        = bool
  default     = true
}

# Data Retention
variable "verification_log_retention_days" {
  description = "Number of days to retain verification logs"
  type        = number
  default     = 90
}

# Training Configuration
variable "sagemaker_instance_type" {
  description = "SageMaker instance type for training jobs"
  type        = string
  default     = "ml.m5.xlarge"
}

variable "max_training_runtime" {
  description = "Maximum runtime for training jobs in seconds"
  type        = number
  default     = 86400  # 24 hours
}

# Model Configuration
variable "model_evaluation_threshold" {
  description = "Minimum accuracy threshold for model deployment"
  type        = number
  default     = 0.85
}

variable "enable_auto_retraining" {
  description = "Enable automatic model retraining"
  type        = bool
  default     = true
}

variable "retraining_schedule" {
  description = "Cron expression for retraining schedule"
  type        = string
  default     = "cron(0 2 ? * MON *)"  # Every Monday at 2 AM
}

# Perplexity API Configuration
variable "perplexity_api_endpoint" {
  description = "Perplexity Sonar Pro API endpoint"
  type        = string
  default     = "https://api.perplexity.ai/v1"
}

variable "max_verification_attempts" {
  description = "Maximum verification attempts per data point"
  type        = number
  default     = 15
}

variable "verification_timeout" {
  description = "Timeout for verification API calls in seconds"
  type        = number
  default     = 30
}

# S3 Configuration
variable "training_data_bucket_name" {
  description = "S3 bucket name for training data"
  type        = string
  default     = ""
}

variable "model_artifacts_bucket_name" {
  description = "S3 bucket name for model artifacts"
  type        = string
  default     = ""
}

# Tags
variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}