# Production Environment Configuration
# Orchestrates all modules for the production environment

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
  environment  = "prod"
  project_name = var.project_name

  common_tags = {
    Environment = local.environment
    Project     = local.project_name
    ManagedBy   = "Terraform"
    Module      = "Consolidated"
    Purpose     = "Production"
  }

  # Lambda environment variables
  lambda_common_env_vars = {
    ENVIRONMENT                 = local.environment
    PROJECT_NAME                = local.project_name
    LOG_LEVEL                   = "INFO" # Production logging level
    CHAT_SESSIONS_TABLE         = module.dynamodb.chat_sessions_table_name
    CHAT_MESSAGES_TABLE         = module.dynamodb.chat_messages_table_name
    CONVERSATIONS_TABLE         = module.dynamodb.conversations_table_name
    WEBSOCKET_CONNECTIONS_TABLE = module.dynamodb.websocket_connections_table_name
    ENHANCED_RATE_LIMITS_TABLE  = module.dynamodb.enhanced_rate_limits_table_name
    KMS_KEY_ID                  = module.core.kms_key_id
    CHAT_PROCESSING_QUEUE_URL   = module.core.chat_processing_queue_url

    # Bedrock Configuration - Use module outputs when available
    BEDROCK_AGENT_ID    = try(module.bedrock.agent_id, var.bedrock_agent_id)
    BEDROCK_AGENT_ALIAS = try(module.bedrock.agent_alias_id, var.bedrock_agent_alias)
    BEDROCK_REGION      = var.bedrock_region

    # WebSocket endpoint for API Gateway Management API (needed by multiple functions)
    # Format: {api-id}.execute-api.{region}.amazonaws.com/{stage}
    WEBSOCKET_API_ENDPOINT = try("${module.api_gateway.websocket_api_id}.execute-api.us-east-1.amazonaws.com/${local.environment}", "")
  }

  # Function-specific environment variables
  lambda_function_env_vars = {
    websocket_connect = {
      ANONYMOUS_SESSIONS_TABLE = module.dynamodb.anonymous_sessions_table_name
      USERS_TABLE              = "" # Not using users table for now
      RATE_LIMITS_TABLE        = module.dynamodb.enhanced_rate_limits_table_name
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
  kms_deletion_window = 30    # Longer deletion window for production safety
  enable_vpc          = false # No VPC for production (can be enabled later)
}

# ================================================
# DynamoDB Module - Consolidated Tables
# ================================================

module "dynamodb" {
  source = "../../modules/dynamodb"

  project_name               = local.project_name
  environment                = local.environment
  billing_mode               = "PAY_PER_REQUEST" # On-demand for production
  kms_key_arn                = module.core.kms_key_arn
  enable_pitr                = true # Enable point-in-time recovery for production
  enable_deletion_protection = true # Enable deletion protection for production
  enable_anonymous_sessions  = true # Support anonymous sessions
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
  log_retention_days        = 30 # 30 day retention for production

  reserved_concurrency = {
    chat_processor = 10 # Higher concurrency for production
  }

  sqs_batch_window    = 10
  sqs_max_concurrency = 10 # Higher concurrency for production
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
# Bedrock Module - Agent, Knowledge Base, and Guardrails
# ================================================

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

  # Knowledge Base Configuration
  knowledge_base_name        = var.bedrock_knowledge_base_name
  knowledge_base_description = var.bedrock_knowledge_base_description
  create_data_source         = true

  # Pinecone Configuration
  pinecone_api_key           = var.pinecone_api_key
  pinecone_connection_string = var.pinecone_connection_string

  # S3 Data Source Configuration
  source_bucket_arn = "arn:aws:s3:::buffet-training-data"

  # Embedding Model Configuration - AWS Titan Embeddings V2 (1024 dimensions)
  embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"

  # Data Source and Chunking Configuration
  enable_chunking_configuration = true
  chunking_strategy             = "SEMANTIC"
  max_tokens_per_chunk          = 300

  # Disable prompt override to use AWS defaults
  enable_prompt_override = false

  # Guardrails Configuration
  enable_guardrails         = true
  guardrail_name            = var.bedrock_guardrail_name
  guardrail_description     = var.bedrock_guardrail_description
  blocked_input_messaging   = "I can only provide financial advice and investment guidance. Please ask questions related to investment planning, retirement, tax strategies, insurance, estate planning, or financial goal setting."
  blocked_outputs_messaging = "I cannot provide that type of advice. I'm designed to help with financial planning, investment strategies, retirement planning, tax planning, insurance analysis, estate planning basics, and financial goal setting. Please ask a finance-related question."

  # Enable policies for comprehensive guardrails
  enable_content_policy               = true
  enable_sensitive_information_policy = false
  enable_topic_policy                 = true
  enable_word_policy                  = true
  enable_contextual_grounding         = true

  # Agent versioning - set to true to use versioned routing (not DRAFT)
  # This allows the alias to point to numbered versions (1, 2, 3, etc.)
  create_agent_version = true
}

# ================================================
# CloudFront + S3 Frontend Module
# ================================================

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
