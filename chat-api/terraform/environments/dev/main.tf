# Development Environment Configuration
# Orchestrates all modules for the dev environment

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
  # Backend configuration for state management
  # Using local backend - uncomment S3 backend when bucket is created
  # backend "s3" {
  #   bucket = "buffett-chat-terraform-state"
  #   key    = "dev/terraform.tfstate"
  #   region = "us-east-1"
  #   # Enable state locking
  #   dynamodb_table = "terraform-state-locks"
  # }
}

provider "aws" {
  region = var.aws_region
}

# ================================================
# Local Variables
# ================================================

locals {
  environment  = "dev"
  project_name = var.project_name
  
  common_tags = {
    Environment = local.environment
    Project     = local.project_name
    ManagedBy   = "Terraform"
    Module      = "Consolidated"
  }
  
  # Lambda environment variables
  lambda_common_env_vars = {
    ENVIRONMENT                = local.environment
    PROJECT_NAME              = local.project_name
    LOG_LEVEL                 = "DEBUG"
    CHAT_SESSIONS_TABLE       = module.dynamodb.chat_sessions_table_name
    CHAT_MESSAGES_TABLE       = module.dynamodb.chat_messages_table_name
    CONVERSATIONS_TABLE       = module.dynamodb.conversations_table_name
    WEBSOCKET_CONNECTIONS_TABLE = module.dynamodb.websocket_connections_table_name
    ENHANCED_RATE_LIMITS_TABLE = module.dynamodb.enhanced_rate_limits_table_name
    KMS_KEY_ID                = module.core.kms_key_id
    CHAT_PROCESSING_QUEUE_URL = module.core.chat_processing_queue_url
    
    # Bedrock Configuration
    BEDROCK_AGENT_ID    = var.bedrock_agent_id
    BEDROCK_AGENT_ALIAS = var.bedrock_agent_alias
    BEDROCK_REGION      = var.bedrock_region

    # WebSocket endpoint for API Gateway Management API (needed by multiple functions)
    # Format: {api-id}.execute-api.{region}.amazonaws.com/{stage}
    WEBSOCKET_API_ENDPOINT = try("${module.api_gateway.websocket_api_id}.execute-api.us-east-1.amazonaws.com/${local.environment}", "")
  }
  
  # Function-specific environment variables
  lambda_function_env_vars = {
    websocket_connect = {
      ANONYMOUS_SESSIONS_TABLE = module.dynamodb.anonymous_sessions_table_name
      USERS_TABLE             = ""  # Auth disabled for dev
      RATE_LIMITS_TABLE       = module.dynamodb.enhanced_rate_limits_table_name
    }
    chat_processor = {
      # Additional environment variables can be added here if needed
    }
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
  kms_deletion_window = 7  # Shorter for dev
  enable_vpc          = false  # No VPC for dev
}

# ================================================
# DynamoDB Module - Consolidated Tables
# ================================================

module "dynamodb" {
  source = "../../modules/dynamodb"
  
  project_name               = local.project_name
  environment                = local.environment
  billing_mode               = "PAY_PER_REQUEST"  # On-demand for dev
  kms_key_arn               = module.core.kms_key_arn
  enable_pitr               = false  # No PITR for dev
  enable_deletion_protection = false  # Allow deletion in dev
  enable_anonymous_sessions  = true   # Keep for now, merge later
  common_tags               = local.common_tags
}

# ================================================
# Lambda Module - Core Functions
# ================================================

module "lambda" {
  source = "../../modules/lambda"
  
  project_name              = local.project_name
  environment               = local.environment
  lambda_role_arn           = module.core.lambda_role_arn
  lambda_package_path       = "/Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api/backend/build"
  runtime                   = "python3.11"
  common_env_vars           = local.lambda_common_env_vars
  function_env_vars         = local.lambda_function_env_vars
  dlq_arn                   = module.core.chat_dlq_arn
  chat_processing_queue_arn = module.core.chat_processing_queue_arn
  log_retention_days        = 7  # Short retention for dev
  
  reserved_concurrency = {
    chat_processor = 2  # Low concurrency for dev
  }
  
  sqs_batch_window    = 10
  sqs_max_concurrency = 2
  common_tags         = local.common_tags
}

# ================================================
# API Gateway Module (placeholder - to be created)
# ================================================

module "api_gateway" {
  source = "../../modules/api-gateway"

  project_name = local.project_name
  environment  = local.environment

  # Lambda integrations
  lambda_arns = module.lambda.function_arns

  # API configuration
  enable_cors           = true
  enable_authorization  = var.enable_authentication
  authorizer_function_arn = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  authorizer_function_name = var.enable_authentication ? module.auth[0].auth_verify_function_name : null
  authorizer_function_arn_for_iam = var.enable_authentication ? module.auth[0].auth_verify_function_arn : null
  auth_callback_function_arn = var.enable_authentication ? module.auth[0].auth_callback_function_arn : null

  common_tags = local.common_tags
}

# ================================================
# Authentication Module (conditional)
# ================================================

module "auth" {
  source = "../../modules/auth"
  count  = var.enable_authentication ? 1 : 0

  project_name = local.project_name
  environment  = local.environment

  # OAuth Configuration
  google_client_id     = var.google_client_id
  google_client_secret = var.google_client_secret
  frontend_url         = var.frontend_url
  jwt_secret           = var.jwt_secret

  # Dependencies
  lambda_role_arn           = module.core.lambda_role_arn
  api_gateway_execution_arn = module.api_gateway.http_api_execution_arn

  common_tags = local.common_tags
}

# ================================================
# Rate Limiting Module (using enhanced version)
# ================================================

module "rate_limiting" {
  source = "../../modules/rate-limiting"
  
  project_name = local.project_name
  environment  = local.environment
  
  enable_advanced_features = false
  
  common_tags = local.common_tags
}

# ================================================
# Monitoring Module (optional for dev)
# ================================================

module "monitoring" {
  source = "../../modules/monitoring"
  count  = var.enable_monitoring ? 1 : 0
  
  project_name = local.project_name
  environment  = local.environment
  
  # Resources to monitor
  lambda_function_names = module.lambda.function_names
  api_gateway_id       = module.api_gateway.http_api_id
  websocket_api_id     = module.api_gateway.websocket_api_id
  
  # Alert configuration
  alert_email      = var.alert_email
  
  common_tags = local.common_tags
}

# ================================================
# Post-Deployment Configuration
# ================================================
# Note: The WebSocket endpoint for the chat_processor Lambda is set
# through the common environment variables to avoid circular dependency.
# The chat_processor function will receive WEBSOCKET_API_ENDPOINT
# as an environment variable once both modules are deployed.