# Root Terraform configuration for Bedrock + Pinecone setup
# Orchestrates all modules to replicate existing configuration

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.25"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# Local variables
locals {
  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "Terraform"
    Component   = "Bedrock-Pinecone"
  }
}

# Secrets Manager module for Pinecone API key
module "secrets" {
  source = "./modules/secrets"

  secret_name             = var.pinecone_secret_name
  secret_description      = var.pinecone_secret_description
  pinecone_api_key        = var.pinecone_api_key
  recovery_window_days    = var.secret_recovery_window_days
  tags                    = local.common_tags
}

# IAM module for service roles and policies
module "iam" {
  source = "./modules/iam"

  knowledge_base_role_name    = var.knowledge_base_role_name
  knowledge_base_policy_name  = var.knowledge_base_policy_name
  agent_role_name            = var.agent_role_name
  agent_policy_name          = var.agent_policy_name
  source_bucket_arn          = var.source_bucket_arn
  pinecone_secret_arn        = module.secrets.secret_arn
  foundation_model_id        = var.foundation_model_id
  attach_bedrock_full_access = var.attach_bedrock_full_access
  tags                       = local.common_tags

  depends_on = [module.secrets]
}

# Knowledge Base module
module "knowledge_base" {
  source = "./modules/knowledge-base"

  knowledge_base_name               = var.knowledge_base_name
  knowledge_base_description        = var.knowledge_base_description
  knowledge_base_role_arn          = module.iam.knowledge_base_role_arn
  embedding_model_arn              = var.embedding_model_arn
  pinecone_connection_string       = var.pinecone_connection_string
  pinecone_credentials_secret_arn  = module.secrets.secret_arn
  pinecone_metadata_field          = var.pinecone_metadata_field
  pinecone_text_field              = var.pinecone_text_field
  pinecone_namespace               = var.pinecone_namespace
  create_data_source               = var.create_data_source
  data_source_name                 = var.data_source_name
  data_source_description          = var.data_source_description
  source_bucket_arn                = var.source_bucket_arn
  inclusion_prefixes               = var.inclusion_prefixes
  enable_chunking_configuration    = var.enable_chunking_configuration
  chunking_strategy                = var.chunking_strategy
  max_tokens_per_chunk             = var.max_tokens_per_chunk
  chunk_overlap_percentage         = var.chunk_overlap_percentage
  tags                             = local.common_tags

  depends_on = [module.iam]
}

# Guardrails module
module "guardrails" {
  count  = var.enable_guardrails ? 1 : 0
  source = "./modules/guardrails"

  guardrail_name                        = var.guardrail_name
  guardrail_description                 = var.guardrail_description
  blocked_input_messaging               = var.blocked_input_messaging
  blocked_outputs_messaging             = var.blocked_outputs_messaging
  enable_content_policy                 = var.enable_content_policy
  enable_sensitive_information_policy   = var.enable_sensitive_information_policy
  enable_topic_policy                   = var.enable_topic_policy
  enable_word_policy                    = var.enable_word_policy
  enable_contextual_grounding          = var.enable_contextual_grounding
  content_filters                      = var.content_filters
  pii_entities                         = var.pii_entities
  custom_regexes                       = var.custom_regexes
  denied_topics                        = var.denied_topics
  managed_word_lists                   = var.managed_word_lists
  custom_word_filters                  = var.custom_word_filters
  contextual_grounding_filters         = var.contextual_grounding_filters
  tags                                 = local.common_tags
}

# ================================================
# NOTE: Main BuffettGPT-Investment-Advisor agent deprecated on 2024-12-20
# The ensemble expert agents are now the primary agents for dev.
# Staging environment retains the original advisor agent.
# ================================================

# ================================================
# Expert Agents for Ensemble Analysis
# ================================================

module "debt_expert_agent" {
  source = "./modules/agent"

  agent_name              = "${var.project_name}-${var.environment}-debt-expert"
  agent_description       = "Value investor debt analysis expert (Buffett/Graham principles)"
  agent_role_arn          = module.iam.agent_role_arn
  foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # Upgraded from Claude 3.5 Haiku
  agent_instruction       = file("${path.module}/prompts/value_investor_debt_v5.txt")
  idle_session_ttl        = var.idle_session_ttl

  # No knowledge base association for expert agents
  associate_knowledge_base = false
  knowledge_base_id        = ""

  # No guardrails for expert agents (main agent has them)
  guardrail_configuration = null

  # Simpler agent config - no prompt override needed
  enable_prompt_override  = false
  create_agent_version    = false  # Route alias to DRAFT (which has action groups)
  agent_alias_name        = "live"
  agent_alias_description = "Live alias for debt expert agent"

  tags = local.common_tags

  depends_on = [module.iam]
}

module "cashflow_expert_agent" {
  source = "./modules/agent"

  agent_name              = "${var.project_name}-${var.environment}-cashflow-expert"
  agent_description       = "Value investor cashflow analysis expert (Buffett/Graham principles)"
  agent_role_arn          = module.iam.agent_role_arn
  foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # Upgraded from Claude 3.5 Haiku
  agent_instruction       = file("${path.module}/prompts/value_investor_cashflow_v5.txt")
  idle_session_ttl        = var.idle_session_ttl

  associate_knowledge_base = false
  knowledge_base_id        = ""
  guardrail_configuration  = null
  enable_prompt_override   = false
  create_agent_version     = false  # Route alias to DRAFT (which has action groups)
  agent_alias_name         = "live"
  agent_alias_description  = "Live alias for cashflow expert agent"

  tags = local.common_tags

  depends_on = [module.iam]
}

module "growth_expert_agent" {
  source = "./modules/agent"

  agent_name              = "${var.project_name}-${var.environment}-growth-expert"
  agent_description       = "Value investor growth/income analysis expert (Buffett/Graham principles)"
  agent_role_arn          = module.iam.agent_role_arn
  foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # Upgraded from Claude 3.5 Haiku
  agent_instruction       = file("${path.module}/prompts/value_investor_growth_v5.txt")
  idle_session_ttl        = var.idle_session_ttl

  associate_knowledge_base = false
  knowledge_base_id        = ""
  guardrail_configuration  = null
  enable_prompt_override   = false
  create_agent_version     = false  # Route alias to DRAFT (which has action groups)
  agent_alias_name         = "live"
  agent_alias_description  = "Live alias for growth expert agent"

  tags = local.common_tags

  depends_on = [module.iam]
}

# ================================================
# Supervisor Agent (Sonnet 4.5 + Knowledge Base)
# Synthesizes expert analyses with Buffett's wisdom
# ================================================

module "supervisor_agent" {
  source = "./modules/agent"

  agent_name              = "${var.project_name}-${var.environment}-supervisor"
  agent_description       = "Value investor supervisor - synthesizes expert analyses with Buffett's wisdom"
  agent_role_arn          = module.iam.agent_role_arn
  foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
  agent_instruction       = file("${path.module}/prompts/supervisor_instruction_v5.txt")
  idle_session_ttl        = var.idle_session_ttl

  # Knowledge base disabled temporarily
  associate_knowledge_base   = false
  knowledge_base_id          = ""

  # No guardrails for supervisor (can be added later if needed)
  guardrail_configuration = null

  enable_prompt_override  = false
  create_agent_version    = true
  agent_alias_name        = "live"
  agent_alias_description = "Live alias for supervisor agent"

  tags = local.common_tags

  depends_on = [module.iam, module.knowledge_base]
}

# ================================================
# Action Groups for Expert Agents
# Each expert agent gets access to the Value Investor Analysis action
# which provides ML predictions and top 10 value metrics per agent
# ================================================

module "debt_expert_action_group" {
  count  = var.enable_action_groups && var.action_group_lambda_arn != null ? 1 : 0
  source = "./modules/action-group"

  agent_id          = module.debt_expert_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Value investor analysis with ML predictions and top 10 debt metrics (5-year history)"

  lambda_arn           = var.action_group_lambda_arn
  lambda_function_name = var.action_group_lambda_function_name
  agent_arn            = module.debt_expert_agent.agent_arn
  api_schema_content   = file("${path.module}/schemas/value_investor_action.yaml")

  lambda_permission_statement_id = "AllowBedrockInvokeDebtExpert"

  depends_on = [module.debt_expert_agent]
}

module "cashflow_expert_action_group" {
  count  = var.enable_action_groups && var.action_group_lambda_arn != null ? 1 : 0
  source = "./modules/action-group"

  agent_id          = module.cashflow_expert_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Value investor analysis with ML predictions and top 10 cashflow metrics (5-year history)"

  lambda_arn           = var.action_group_lambda_arn
  lambda_function_name = var.action_group_lambda_function_name
  agent_arn            = module.cashflow_expert_agent.agent_arn
  api_schema_content   = file("${path.module}/schemas/value_investor_action.yaml")

  lambda_permission_statement_id = "AllowBedrockInvokeCashflowExpert"

  depends_on = [module.cashflow_expert_agent]
}

module "growth_expert_action_group" {
  count  = var.enable_action_groups && var.action_group_lambda_arn != null ? 1 : 0
  source = "./modules/action-group"

  agent_id          = module.growth_expert_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Value investor analysis with ML predictions and top 10 growth metrics (5-year history)"

  lambda_arn           = var.action_group_lambda_arn
  lambda_function_name = var.action_group_lambda_function_name
  agent_arn            = module.growth_expert_agent.agent_arn
  api_schema_content   = file("${path.module}/schemas/value_investor_action.yaml")

  lambda_permission_statement_id = "AllowBedrockInvokeGrowthExpert"

  depends_on = [module.growth_expert_agent]
}