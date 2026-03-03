# Staging Environment Configuration
# Orchestrates all modules for the staging environment (Friends & Family Testing)

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
    ENVIRONMENT         = local.environment
    PROJECT_NAME        = local.project_name
    LOG_LEVEL           = "INFO" # Less verbose than dev
    CONVERSATIONS_TABLE = module.dynamodb.conversations_table_name
    CHAT_MESSAGES_TABLE = module.dynamodb.chat_messages_table_name
    KMS_KEY_ID          = module.core.kms_key_id

    # Bedrock Configuration
    BEDROCK_REGION       = var.bedrock_region
    FOLLOWUP_AGENT_ID    = try(module.bedrock.followup_agent_id, "")
    FOLLOWUP_AGENT_ALIAS = "TSTALIASID"  # Test alias routes to DRAFT (has action groups)

    # FMP API Configuration
    FMP_SECRET_NAME            = "${local.project_name}-${local.environment}-fmp"
    FINANCIAL_DATA_CACHE_TABLE = try(module.dynamodb.financial_data_cache_table_name, "")
    TICKER_LOOKUP_TABLE        = try(module.dynamodb.ticker_lookup_table_name, "")

    # Investment Research Tables
    INVESTMENT_REPORTS_V2_TABLE = try(module.dynamodb.investment_reports_v2_table_name, "")
    METRICS_HISTORY_CACHE_TABLE = try(module.dynamodb.metrics_history_cache_table_name, "")

    # Token Usage Tracking (monthly limits for follow-up agent)
    TOKEN_USAGE_TABLE   = try(module.dynamodb.token_usage_table_name, "")
    DEFAULT_TOKEN_LIMIT = "500000"  # 500K tokens for staging/testing

    # JWT Authentication Configuration
    JWT_SECRET_ARN = module.auth[0].jwt_secret_arn

    # Waitlist Table
    WAITLIST_TABLE = module.dynamodb.waitlist_table_name

    # Frontend URL (for referral links - points to landing page)
    FRONTEND_URL = module.cloudfront_landing.cloudfront_url
  }

  # Function-specific environment variables
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

  project_name        = local.project_name
  environment         = local.environment
  lambda_role_arn     = module.core.lambda_role_arn
  lambda_package_path = "${path.root}/../../../backend/build"
  runtime             = "python3.11"
  common_env_vars     = local.lambda_common_env_vars
  function_env_vars   = local.lambda_function_env_vars
  log_retention_days  = 14 # 2 week retention for staging

  reserved_concurrency = {
    analysis_followup = 10
  }

  common_tags = local.common_tags
  kms_key_arn = module.core.kms_key_arn

  # Followup Action Lambda (Bedrock action group handler)
  create_followup_action_lambda = true
  followup_action_image_tag     = "latest"

  # DynamoDB table ARNs for followup-action Lambda IAM policy
  investment_reports_v2_table_arn = module.dynamodb.investment_reports_v2_table_arn
  financial_data_cache_table_arn  = module.dynamodb.financial_data_cache_table_arn

  # DynamoDB table names for followup-action Lambda environment variables
  investment_reports_v2_table_name = module.dynamodb.investment_reports_v2_table_name
  financial_data_cache_table_name  = module.dynamodb.financial_data_cache_table_name

  # Metrics History Cache table for followup-action Lambda
  metrics_history_cache_table_arn  = module.dynamodb.metrics_history_cache_table_arn
  metrics_history_cache_table_name = module.dynamodb.metrics_history_cache_table_name
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
  enable_search                   = false  # Disable AI search for staging
  authorizer_function_arn         = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  authorizer_function_name        = var.enable_authentication ? module.auth[0].auth_verify_function_name : null
  authorizer_function_arn_for_iam = var.enable_authentication ? module.auth[0].auth_verify_function_arn : null
  auth_callback_function_arn      = var.enable_authentication ? module.auth[0].auth_callback_function_arn : null
  cloudfront_url                  = module.cloudfront.cloudfront_url

  # Analysis Streaming API (REST API with JWT auth)
  enable_analysis_api       = true
  auth_verify_invoke_arn    = var.enable_authentication ? module.auth[0].auth_verify_invoke_arn : null
  auth_verify_function_name = var.enable_authentication ? module.auth[0].auth_verify_function_name : null

  # Investment Research API (REST API with JWT auth)
  enable_research_api                 = true
  investment_research_function_url    = module.lambda.investment_research_docker_function_url
  investment_research_function_name   = module.lambda.investment_research_docker_function_name
  analysis_followup_function_url      = module.lambda.analysis_followup_url

  # Subscription/Stripe API (checkout, portal, status, webhook)
  enable_subscription_routes = true
  enable_stripe_webhook      = true

  # Waitlist API (signup, status, referral tracking)
  enable_waitlist_routes = true

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

  # Action Group for Follow-up Agent
  # Uses dedicated followup-action Lambda for report data retrieval
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
  resend_secret_name = "resend_staging_key"
  resend_from_email  = "onboarding@resend.dev"
}

# Attach Resend secrets policy to Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_resend_secrets" {
  role       = module.core.lambda_role_name
  policy_arn = module.email.resend_secrets_policy_arn
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
# CloudFront + S3 Landing Page
# ================================================

module "cloudfront_landing" {
  source = "../../modules/cloudfront-static-site"

  project_name = local.project_name
  environment  = local.environment
  site_name    = "landing"
  price_class  = "PriceClass_100"

  common_tags = local.common_tags
}

# ================================================
# Post-Deployment Configuration
# ================================================
# Note: WebSocket infrastructure deprecated (2026-02) per WEBSOCKET_DEPRECATION_PLAN.md
# All chat functionality now uses REST+SSE via Research and Follow-up APIs