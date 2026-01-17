# Development Environment Configuration
# Orchestrates all modules for the dev environment

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
  
  # Backend configuration for state management
  # S3 backend with encryption and state locking
  backend "s3" {
    bucket         = "buffett-chat-terraform-state-430118826061"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:us-east-1:430118826061:key/d964f8d5-fe43-45c3-9193-3fe8a7d6e12b"
    dynamodb_table = "buffett-chat-terraform-state-locks"
  }
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

    # Bedrock Configuration - Use module outputs when available
    BEDROCK_AGENT_ID    = try(module.bedrock.agent_id, var.bedrock_agent_id)
    BEDROCK_AGENT_ALIAS = try(module.bedrock.agent_alias_id, var.bedrock_agent_alias)
    BEDROCK_REGION      = var.bedrock_region

    # WebSocket endpoint for API Gateway Management API (needed by multiple functions)
    # Format: {api-id}.execute-api.{region}.amazonaws.com/{stage}
    WEBSOCKET_API_ENDPOINT = try("${module.api_gateway.websocket_api_id}.execute-api.us-east-1.amazonaws.com/${local.environment}", "")

    # S3 Model Configuration (Ensemble Analysis)
    MODEL_S3_BUCKET = module.s3.models_bucket_name
    MODEL_S3_PREFIX = "ensemble/v1"

    # Expert Agent Configuration (Ensemble Analysis)
    # Using TSTALIASID which routes to DRAFT version (has action groups)
    DEBT_AGENT_ID        = try(module.bedrock.debt_agent_id, "")
    DEBT_AGENT_ALIAS     = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)
    CASHFLOW_AGENT_ID    = try(module.bedrock.cashflow_agent_id, "")
    CASHFLOW_AGENT_ALIAS = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)
    GROWTH_AGENT_ID      = try(module.bedrock.growth_agent_id, "")
    GROWTH_AGENT_ALIAS   = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)

    # Supervisor Agent Configuration (Phase 2)
    SUPERVISOR_AGENT_ID    = try(module.bedrock.supervisor_agent_id, "")
    SUPERVISOR_AGENT_ALIAS = try(module.bedrock.supervisor_agent_alias_id, "")
    SUPERVISOR_ENABLED     = "true"
    ORCHESTRATION_MODE     = "supervisor"
    USE_ACTION_GROUP_MODE  = "true"  # Hybrid mode: agents call action groups with skip_inference=true

    # Follow-up Agent Configuration (for investment research follow-up questions)
    FOLLOWUP_AGENT_ID    = try(module.bedrock.followup_agent_id, "")
    FOLLOWUP_AGENT_ALIAS = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)

    # FMP API Configuration (Ensemble Analysis)
    FMP_SECRET_NAME            = "${local.project_name}-${local.environment}-fmp"
    FINANCIAL_DATA_CACHE_TABLE = try(module.dynamodb.financial_data_cache_table_name, "")
    TICKER_LOOKUP_TABLE        = try(module.dynamodb.ticker_lookup_table_name, "")

    # Investment Research Tables
    INVESTMENT_REPORTS_TABLE    = try(module.dynamodb.investment_reports_table_name, "")
    INVESTMENT_REPORTS_V2_TABLE = try(module.dynamodb.investment_reports_v2_table_name, "")

    # JWT Authentication Configuration
    JWT_SECRET_ARN = module.auth[0].jwt_secret_arn
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
# S3 Module - Models Bucket
# ================================================

module "s3" {
  source = "../../modules/s3"

  project_name = local.project_name
  environment  = local.environment
  common_tags  = local.common_tags
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
  log_retention_days        = 7  # Short retention for dev
  
  reserved_concurrency = {
    chat_processor = 2  # Low concurrency for dev
  }
  
  sqs_batch_window    = 10
  sqs_max_concurrency = 2
  common_tags         = local.common_tags

  # ML Models S3 bucket for prediction ensemble
  model_s3_bucket     = module.s3.models_bucket_name

  # KMS key for DynamoDB encryption
  kms_key_arn         = module.core.kms_key_arn

  # Prediction Ensemble Docker image version
  # v2.4.6: Fix race condition - cache verification before agent invocation
  prediction_ensemble_image_tag = "v2.4.6"

  # Followup Action Lambda (Bedrock action group handler)
  # Docker image pushed to ECR - enable Lambda creation
  create_followup_action_lambda = true
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
  enable_cors          = true
  enable_authorization = var.enable_authentication
  enable_search        = true  # Enable AI search for dev environment only
  authorizer_function_arn = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  authorizer_function_name = var.enable_authentication ? module.auth[0].auth_verify_function_name : null
  authorizer_function_arn_for_iam = var.enable_authentication ? module.auth[0].auth_verify_function_arn : null
  auth_callback_function_arn = var.enable_authentication ? module.auth[0].auth_callback_function_arn : null

  # Analysis Streaming API (REST API with JWT auth)
  # Uses HTTP_PROXY integration to Lambda Function URL for SSE streaming
  enable_analysis_api               = true
  prediction_ensemble_invoke_arn    = module.lambda.prediction_ensemble_docker_invoke_arn
  prediction_ensemble_function_name = module.lambda.prediction_ensemble_docker_function_name
  prediction_ensemble_function_url  = module.lambda.prediction_ensemble_docker_function_url
  auth_verify_invoke_arn            = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  auth_verify_function_name         = var.enable_authentication ? module.auth[0].auth_verify_function_name : null

  # Investment Research API (REST API with JWT auth)
  # Uses HTTP_PROXY integration to Lambda Function URL for SSE streaming of cached reports
  enable_research_api                 = true
  investment_research_function_url    = module.lambda.investment_research_docker_function_url
  investment_research_function_name   = module.lambda.investment_research_docker_function_name

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
  lambda_package_path       = "${path.root}/../../../backend/build"
  api_gateway_execution_arn = module.api_gateway.http_api_execution_arn
  dependencies_layer_arn    = module.lambda.dependencies_layer_arn

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
# Bedrock Module - Agent, Knowledge Base, and Guardrails
# ================================================
# Fixed: Circular dependency resolved by using wildcard for knowledge base ARN in IAM policy

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
  # embedding_model_arn - using module default (Titan v2 with 1024 dimensions)
  # source_bucket_arn - using module default (arn:aws:s3:::buffet-training-data)
  create_data_source         = true

  # Pinecone Configuration
  # pinecone_connection_string - using module default (configured Pinecone host)
  pinecone_api_key          = var.pinecone_api_key

  # Data Source and Chunking Configuration
  enable_chunking_configuration = true
  chunking_strategy            = "SEMANTIC"
  max_tokens_per_chunk         = 300

  # Enable prompt override to customize temperature and instructions
  enable_prompt_override = true

  # Create agent version after deployment
  # Set to true to use versioned routing (prevents DRAFT routing issues)
  create_agent_version = true

  # Guardrails Configuration - Enabled for financial advisor safety
  enable_guardrails         = true
  guardrail_name           = var.bedrock_guardrail_name
  guardrail_description    = var.bedrock_guardrail_description
  blocked_input_messaging  = "I can only provide financial advice and investment guidance. Please ask questions related to investment planning, retirement, tax strategies, insurance, estate planning, or financial goal setting."
  blocked_outputs_messaging = "I cannot provide that type of advice. I'm designed to help with financial planning, investment strategies, retirement planning, tax planning, insurance analysis, estate planning basics, and financial goal setting. Please ask a finance-related question."

  # Enable policies for comprehensive guardrails
  enable_content_policy                = true
  enable_sensitive_information_policy  = false  # Disabled since no PII/regex configured
  enable_topic_policy                 = true
  enable_word_policy                  = true
  enable_contextual_grounding         = true

  # Action Groups for Expert Agents
  # Uses dedicated data-fetcher-action Lambda (pure Python, no LWA)
  # This resolves the Bedrock action group response format issue
  # See: docs/TWO_LAMBDA_ARCHITECTURE.md
  enable_action_groups              = true
  action_group_lambda_arn           = module.lambda.ensemble_prediction_data_fetcher_action_arn
  action_group_lambda_function_name = module.lambda.ensemble_prediction_data_fetcher_action_name

  # Action Group for Follow-up Agent
  # Uses dedicated followup-action Lambda for report data retrieval
  # Docker image pushed to ECR and Lambda creation enabled
  enable_followup_action_group         = true
  followup_action_lambda_arn           = module.lambda.followup_action_arn
  followup_action_lambda_function_name = module.lambda.followup_action_name
}

# ================================================
# Post-Deployment Configuration
# ================================================
# Note: The WebSocket endpoint for the chat_processor Lambda is set
# through the common environment variables to avoid circular dependency.
# The chat_processor function will receive WEBSOCKET_API_ENDPOINT
# as an environment variable once both modules are deployed.