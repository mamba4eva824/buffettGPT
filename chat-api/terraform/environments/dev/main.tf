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
  # Updated 2025-01: Removed deprecated RAG chatbot table references
  # Updated 2025-01: Re-added CHAT_MESSAGES_TABLE for Research report history
  # Updated 2026-02: Removed WebSocket and chat processing vars (deprecated)
  lambda_common_env_vars = {
    ENVIRONMENT         = local.environment
    PROJECT_NAME        = local.project_name
    LOG_LEVEL           = "DEBUG"
    CONVERSATIONS_TABLE = module.dynamodb.conversations_table_name
    CHAT_MESSAGES_TABLE = module.dynamodb.chat_messages_table_name
    KMS_KEY_ID          = module.core.kms_key_id

    # Bedrock Configuration
    BEDROCK_REGION = var.bedrock_region

    # Follow-up Agent Configuration (for investment research follow-up questions)
    FOLLOWUP_AGENT_ID    = try(module.bedrock.followup_agent_id, "")
    FOLLOWUP_AGENT_ALIAS = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)

    # FMP API Configuration (Ensemble Analysis)
    FMP_SECRET_NAME            = "${local.project_name}-${local.environment}-fmp"
    FINANCIAL_DATA_CACHE_TABLE = try(module.dynamodb.financial_data_cache_table_name, "")
    TICKER_LOOKUP_TABLE        = try(module.dynamodb.ticker_lookup_table_name, "")

    # Investment Research Tables (v1 removed, only v2 active)
    INVESTMENT_REPORTS_V2_TABLE = try(module.dynamodb.investment_reports_v2_table_name, "")
    METRICS_HISTORY_CACHE_TABLE = try(module.dynamodb.metrics_history_cache_table_name, "")

    # Token Usage Tracking (monthly limits for follow-up agent)
    TOKEN_USAGE_TABLE   = try(module.dynamodb.token_usage_table_name, "")
    DEFAULT_TOKEN_LIMIT = "100000"  # 100K tokens for dev/testing

    # JWT Authentication Configuration
    JWT_SECRET_ARN = module.auth[0].jwt_secret_arn

    # Waitlist Table
    WAITLIST_TABLE = module.dynamodb.waitlist_table_name

    # Frontend URL (for referral links)
    FRONTEND_URL = var.frontend_url
  }

  # Function-specific environment variables
  # Updated 2025-01: Removed deprecated RAG chatbot table references
  # Updated 2026-02: Removed websocket_connect and chat_processor (deprecated)
  lambda_function_env_vars = {
    stripe_webhook_handler = {
      STRIPE_SECRET_KEY_ARN      = module.stripe.stripe_secret_key_arn
      STRIPE_WEBHOOK_SECRET_ARN  = module.stripe.stripe_webhook_secret_arn
      STRIPE_PLUS_PRICE_ID_ARN   = module.stripe.stripe_plus_price_id_arn
      TOKEN_LIMIT_PLUS           = tostring(module.stripe.token_limit_plus)
      USERS_TABLE                = var.enable_authentication ? module.auth[0].users_table_name : ""
    }
    subscription_handler = {
      STRIPE_SECRET_KEY_ARN      = module.stripe.stripe_secret_key_arn
      STRIPE_PLUS_PRICE_ID_ARN   = module.stripe.stripe_plus_price_id_arn
      STRIPE_PUBLISHABLE_KEY_ARN = module.stripe.stripe_publishable_key_arn
      USERS_TABLE                = var.enable_authentication ? module.auth[0].users_table_name : ""
    }
    waitlist_handler = {
      RESEND_API_KEY_ARN = module.email.resend_api_key_arn
      RESEND_FROM_EMAIL  = module.email.resend_from_email
      API_BASE_URL       = module.api_gateway.http_api_endpoint
    }
    sp500_eod_ingest = {
      STOCK_DATA_4H_TABLE              = module.dynamodb.stock_data_4h_table_name
      POWERTOOLS_SERVICE_NAME          = "sp500-eod-ingest"
      POWERTOOLS_METRICS_NAMESPACE     = "SP500EODIngest"
      SNS_TOPIC_ARN                    = var.enable_monitoring ? module.monitoring[0].sns_topic_arn : ""
    }
    earnings_update = {
      SNS_TOPIC_ARN = var.enable_monitoring ? module.monitoring[0].sns_topic_arn : ""
    }
    value_insights_handler = {
      STOCK_DATA_4H_TABLE = module.dynamodb.stock_data_4h_table_name
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
  kms_key_arn                = module.core.kms_key_arn
  enable_pitr                = false  # No PITR for dev
  enable_deletion_protection = false  # Allow deletion in dev
  common_tags                = local.common_tags
}

# ================================================
# S3 Module (ARCHIVED - 2025-01)
# ================================================
# NOTE: S3 models bucket was removed when prediction ensemble was archived.
# It contained ML models (ensemble/v1/) and the ML layer (layers/ml-layer.zip).
# See: archived/prediction_ensemble/terraform/s3/

# ================================================
# Lambda Module - Core Functions
# ================================================

module "lambda" {
  source = "../../modules/lambda"

  project_name        = local.project_name
  environment         = local.environment
  lambda_role_arn     = module.core.lambda_role_arn
  lambda_package_path = "${path.root}/../../../backend/build"
  runtime             = "python3.11"
  common_env_vars     = local.lambda_common_env_vars
  function_env_vars   = local.lambda_function_env_vars
  log_retention_days  = 7  # Short retention for dev

  reserved_concurrency = {
    analysis_followup  = 10  # Increased for production traffic
    sp500_eod_ingest   = 1   # Prevent duplicate parallel runs
  }

  common_tags = local.common_tags

  # KMS key for DynamoDB encryption
  kms_key_arn         = module.core.kms_key_arn

  # NOTE: model_s3_bucket and prediction_ensemble_image_tag removed (2025-01)
  # See: archived/prediction_ensemble/

  # Followup Action Lambda (Bedrock action group handler)
  # Docker image pushed to ECR - enable Lambda creation
  create_followup_action_lambda = true
  followup_action_image_tag     = "latest"

  # DynamoDB table ARNs for followup-action Lambda IAM policy
  # These use the actual table ARNs from the dynamodb module to ensure correct permissions
  investment_reports_v2_table_arn = module.dynamodb.investment_reports_v2_table_arn
  financial_data_cache_table_arn  = module.dynamodb.financial_data_cache_table_arn

  # DynamoDB table names for followup-action Lambda environment variables
  # These use the actual table names from the dynamodb module (not project-prefixed)
  investment_reports_v2_table_name = module.dynamodb.investment_reports_v2_table_name
  financial_data_cache_table_name  = module.dynamodb.financial_data_cache_table_name

  # Metrics History Cache table for followup-action Lambda
  metrics_history_cache_table_arn  = module.dynamodb.metrics_history_cache_table_arn
  metrics_history_cache_table_name = module.dynamodb.metrics_history_cache_table_name

  # EventBridge schedule for daily 4h candle ingestion
  enable_eod_ingest_schedule      = true
  enable_earnings_update_schedule = true

  # SNS topic for pipeline notifications (success + failure emails)
  enable_pipeline_notifications = var.enable_monitoring
  alerts_sns_topic_arn          = var.enable_monitoring ? module.monitoring[0].sns_topic_arn : ""
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
  # NOTE: prediction_ensemble references removed (2025-01) - now only used for investment research
  enable_analysis_api       = true
  auth_verify_invoke_arn    = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  auth_verify_function_name = var.enable_authentication ? module.auth[0].auth_verify_function_name : null

  # Investment Research API (REST API with JWT auth)
  # Uses HTTP_PROXY integration to Lambda Function URL for SSE streaming of cached reports
  enable_research_api                 = true
  investment_research_function_url    = module.lambda.investment_research_docker_function_url
  investment_research_function_name   = module.lambda.investment_research_docker_function_name
  analysis_followup_function_url      = module.lambda.analysis_followup_url

  # Market Intelligence API (REST API with JWT auth + Plus subscription check)
  enable_market_intelligence_api      = true
  market_intelligence_function_url    = module.lambda.market_intel_chat_url

  # Subscription/Stripe API (checkout, portal, status, webhook)
  enable_subscription_routes = true
  enable_stripe_webhook      = true

  # Waitlist API (signup, status, referral tracking)
  enable_waitlist_routes = true

  # Value Insights API (financial metrics and ratings)
  enable_value_insights_routes = true

  # Earnings Feed API (earnings tracker dashboard)
  enable_earnings_feed_routes = true

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
  api_gateway_id        = module.api_gateway.http_api_id
  # websocket_api_id - REMOVED (2026-02) - WebSocket deprecated

  # Alert configuration
  alert_email = var.alert_email

  common_tags = local.common_tags
}

# ================================================
# Bedrock Module - Expert Agents Only
# ================================================
# Updated 2025-01: Removed Knowledge Base, Pinecone, and Guardrails

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

  # Create agent version after deployment
  # Set to true to use versioned routing (prevents DRAFT routing issues)
  create_agent_version = true

  # NOTE: Expert Agent action groups removed (2025-01) - prediction ensemble archived
  # See: archived/prediction_ensemble/

  # Action Group for Follow-up Agent
  # Uses dedicated followup-action Lambda for report data retrieval
  # Docker image pushed to ECR and Lambda creation enabled
  enable_followup_action_group         = true
  followup_action_lambda_arn           = module.lambda.followup_action_arn
  followup_action_lambda_function_name = module.lambda.followup_action_name
}

# ================================================
# Stripe Module - Payment Integration
# ================================================

module "stripe" {
  source = "../../modules/stripe"

  environment = local.environment
  common_tags = local.common_tags

  # Token limit for Plus subscribers (2M tokens/month)
  token_limit_plus = 2000000

  # Secrets are set manually in AWS Console after initial deployment
  # See: docs/stripe/STRIPE_INTEGRATION_GUIDE.md for manual secret setup
}

# Attach Stripe secrets policy to Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_stripe_secrets" {
  role       = module.core.lambda_role_name
  policy_arn = module.stripe.stripe_secrets_policy_arn
}

# ================================================
# Email Module - Resend Integration
# ================================================

module "email" {
  source = "../../modules/email"

  environment        = local.environment
  common_tags        = local.common_tags
  resend_secret_name = "resend_dev_key"
  resend_from_email  = "onboarding@resend.dev"
}

# Attach Resend secrets policy to Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_resend_secrets" {
  role       = module.core.lambda_role_name
  policy_arn = module.email.resend_secrets_policy_arn
}

# ================================================
# Post-Deployment Configuration
# ================================================
# Note: WebSocket infrastructure deprecated (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md
# All chat functionality now uses REST+SSE via Research and Follow-up APIs