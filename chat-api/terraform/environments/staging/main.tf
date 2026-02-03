# Staging Environment Configuration
# Orchestrates all modules for the staging environment (Friends & Family Testing)

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend configuration for state management
  # S3 backend with encryption and state locking
  backend "s3" {
    # Configuration loaded from backend.hcl
    # Use: terraform init -backend-config=backend.hcl
  }
}

provider "aws" {
  region = var.aws_region
}

# ================================================
# Local Variables
# ================================================

locals {
  environment  = "staging"
  project_name = var.project_name

  common_tags = {
    Environment = local.environment
    Project     = local.project_name
    ManagedBy   = "Terraform"
    Module      = "Consolidated"
    Purpose     = "FriendsAndFamilyTesting"
  }

  # Lambda environment variables
  lambda_common_env_vars = {
    ENVIRONMENT                 = local.environment
    PROJECT_NAME                = local.project_name
    LOG_LEVEL                   = "INFO" # Less verbose than dev
    CHAT_MESSAGES_TABLE = module.dynamodb.chat_messages_table_name
    CONVERSATIONS_TABLE = module.dynamodb.conversations_table_name
    KMS_KEY_ID                  = module.core.kms_key_id
    CHAT_PROCESSING_QUEUE_URL   = module.core.chat_processing_queue_url

    # Bedrock Configuration - Use module outputs when available
    BEDROCK_AGENT_ID    = try(module.bedrock.agent_id, var.bedrock_agent_id)
    BEDROCK_AGENT_ALIAS = try(module.bedrock.agent_alias_id, var.bedrock_agent_alias)
    BEDROCK_REGION      = var.bedrock_region

    # WebSocket endpoint for API Gateway Management API (needed by multiple functions)
    # Format: {api-id}.execute-api.{region}.amazonaws.com/{stage}
    WEBSOCKET_API_ENDPOINT = try("${module.api_gateway.websocket_api_id}.execute-api.us-east-1.amazonaws.com/${local.environment}", "")

    # Token Usage Tracking (monthly limits for follow-up agent)
    TOKEN_USAGE_TABLE   = try(module.dynamodb.token_usage_table_name, "")
    DEFAULT_TOKEN_LIMIT = "500000"  # 500K tokens for staging/testing
  }

  # Function-specific environment variables
  # NOTE: Anonymous sessions and rate limits tables removed (2025-01)
  lambda_function_env_vars = {
    websocket_connect = {}
    chat_processor    = {}
  }
}

# ================================================
# Core Module - KMS, IAM, SQS
# ================================================

module "core" {
  source = "../../modules/core"

  project_name        = local.project_name
  environment         = local.environment
  aws_region          = var.aws_region
  common_tags         = local.common_tags
  kms_deletion_window = 14    # Longer than dev for safety
  enable_vpc          = false # No VPC for staging
}

# ================================================
# DynamoDB Module - Consolidated Tables
# ================================================

module "dynamodb" {
  source = "../../modules/dynamodb"

  project_name               = local.project_name
  environment                = local.environment
  billing_mode               = "PAY_PER_REQUEST" # On-demand for cost control
  kms_key_arn                = module.core.kms_key_arn
  enable_pitr                = true  # Enable point-in-time recovery for staging
  enable_deletion_protection = false # Allow deletion in staging
  common_tags                = local.common_tags
}

# ================================================
# Lambda Module - Core Functions
# ================================================

module "lambda" {
  source = "../../modules/lambda"

  project_name              = local.project_name
  environment               = local.environment
  lambda_role_arn           = module.core.lambda_role_arn
  lambda_package_path       = "${path.root}/../../../backend/build"
  runtime                   = "python3.11"
  common_env_vars           = local.lambda_common_env_vars
  function_env_vars         = local.lambda_function_env_vars
  dlq_arn                   = module.core.chat_dlq_arn
  chat_processing_queue_arn = module.core.chat_processing_queue_arn
  log_retention_days        = 14 # 2 week retention for staging

  reserved_concurrency = {
    chat_processor = 5 # Higher than dev for multiple testers
  }

  sqs_batch_window    = 10
  sqs_max_concurrency = 5
  common_tags         = local.common_tags
}

# ================================================
# API Gateway Module
# ================================================

module "api_gateway" {
  source = "../../modules/api-gateway"

  project_name = local.project_name
  environment  = local.environment

  # Lambda integrations
  lambda_arns = module.lambda.function_arns

  # API configuration
  enable_cors                     = true
  enable_authorization            = var.enable_authentication
  authorizer_function_arn         = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  authorizer_function_name        = var.enable_authentication ? module.auth[0].auth_verify_function_name : null
  authorizer_function_arn_for_iam = var.enable_authentication ? module.auth[0].auth_verify_function_arn : null
  auth_callback_function_arn      = var.enable_authentication ? module.auth[0].auth_callback_function_arn : null
  cloudfront_url                  = module.cloudfront.cloudfront_url

  common_tags = local.common_tags
}

# ================================================
# Authentication Module
# ================================================

module "auth" {
  source = "../../modules/auth"
  count  = var.enable_authentication ? 1 : 0

  project_name = local.project_name
  environment  = local.environment

  # OAuth Configuration
  google_client_id     = var.google_client_id
  google_client_secret = var.google_client_secret
  frontend_url         = module.cloudfront.cloudfront_url
  jwt_secret           = var.jwt_secret

  # Dependencies
  lambda_role_arn           = module.core.lambda_role_arn
  api_gateway_execution_arn = module.api_gateway.http_api_execution_arn
  dependencies_layer_arn    = module.lambda.dependencies_layer_arn
  lambda_package_path       = "${path.root}/../../../backend/build"

  common_tags = local.common_tags
}

# ================================================
# Rate Limiting Module
# ================================================

module "rate_limiting" {
  source = "../../modules/rate-limiting"

  project_name = local.project_name
  environment  = local.environment

  enable_advanced_features = false

  common_tags = local.common_tags
}

# ================================================
# Monitoring Module
# ================================================

module "monitoring" {
  source = "../../modules/monitoring"
  count  = var.enable_monitoring ? 1 : 0

  project_name = local.project_name
  environment  = local.environment

  # Resources to monitor
  lambda_function_names = module.lambda.function_names
  api_gateway_id        = module.api_gateway.http_api_id
  websocket_api_id      = module.api_gateway.websocket_api_id

  # Alert configuration
  alert_email = var.alert_email

  common_tags = local.common_tags
}

# ================================================
# Bedrock Module - Agent Configuration
# ================================================
# Note: Knowledge Base, Guardrails, and Pinecone integration removed (2025-01)

module "bedrock" {
  source = "../../modules/bedrock"

  project_name = local.project_name
  environment  = local.environment
  aws_region   = var.aws_region

  # Agent Configuration
  agent_name          = var.bedrock_agent_name
  agent_description   = var.bedrock_agent_description
  foundation_model_id = var.bedrock_foundation_model
  agent_instruction   = var.bedrock_agent_instruction

  # Enable prompt override to customize temperature and instructions
  enable_prompt_override = true

  # Agent versioning - set to true to use versioned routing (not DRAFT)
  # This allows the alias to point to numbered versions (1, 2, 3, etc.)
  create_agent_version = true
}

# ================================================
# CloudFront + S3 Frontend Module
# ================================================

# Import existing S3 bucket into Terraform state
import {
  to = module.cloudfront.aws_s3_bucket.frontend
  id = "buffett-staging-frontend"
}

module "cloudfront" {
  source = "../../modules/cloudfront-static-site"

  project_name = local.project_name
  environment  = local.environment
  price_class  = "PriceClass_100" # US, Canada, Europe

  common_tags = local.common_tags
}

# ================================================
# Post-Deployment Configuration
# ================================================
# Note: The WebSocket endpoint for the chat_processor Lambda is set
# through the common environment variables to avoid circular dependency.
# The chat_processor function will receive WEBSOCKET_API_ENDPOINT
# as an environment variable once both modules are deployed.