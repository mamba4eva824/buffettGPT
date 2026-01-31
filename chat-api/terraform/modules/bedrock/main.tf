# Root Terraform configuration for Bedrock Agents
# Updated 2025-01: Removed Knowledge Base (Pinecone), Secrets, and Guardrails
# Updated 2025-01: Archived prediction ensemble (Expert Agents, Supervisor Agent, and their Action Groups)
# Kept: Follow-up Agent for Investment Research

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
    Component   = "Bedrock-Agents"
  }
}

# ================================================
# REMOVED MODULES (2025-01 Cleanup)
# ================================================
# The following modules were removed as part of RAG chatbot deprecation:
# - module "secrets" (Pinecone API key) - no longer needed
# - module "knowledge_base" (Pinecone vector store) - no longer needed
# - module "guardrails" (content filtering) - disabled per user request
#
# The IAM module is simplified to only include agent roles.
# ================================================

# IAM module for Bedrock Agent service roles
# Simplified: Only creates agent role, KB resources deprecated and disabled
# NOTE: Using existing role names to avoid agent recreation (Bedrock forces replacement on role change)
module "iam" {
  source = "./modules/iam"

  # DEPRECATED: Knowledge Base resources no longer created (2025-01)
  create_knowledge_base_resources = false

  # Legacy variable values (only used if create_knowledge_base_resources = true)
  knowledge_base_role_name    = "bedrock-kb-service-role"
  knowledge_base_policy_name  = "bedrock-kb-policy"
  source_bucket_arn           = var.source_bucket_arn
  pinecone_secret_arn         = "arn:aws:secretsmanager:${var.aws_region}:*:secret:placeholder"  # Placeholder - KB not used

  # Active agent configuration
  agent_role_name             = "bedrock-agent-service-role"
  agent_policy_name           = "bedrock-agent-policy"
  foundation_model_id         = var.foundation_model_id
  attach_bedrock_full_access  = var.attach_bedrock_full_access
  tags                        = local.common_tags
}

# ================================================
# NOTE: Main BuffettGPT-Investment-Advisor agent deprecated on 2024-12-20
# Expert Agents (debt, cashflow, growth) and Supervisor Agent archived on 2025-01
# See: archived/prediction_ensemble/ for the archived ensemble system
# ================================================

# ================================================
# Follow-up Agent for Investment Research Questions
# Handles follow-up questions about investment reports
# using action groups to retrieve report sections and metrics
# ================================================

module "followup_agent" {
  source = "./modules/agent"

  agent_name              = "${var.project_name}-${var.environment}-followup"
  agent_description       = "Follow-up research assistant for investment report questions"
  agent_role_arn          = module.iam.agent_role_arn
  foundation_model        = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
  agent_instruction       = file("${path.module}/prompts/followup_agent_v1.txt")
  idle_session_ttl        = var.idle_session_ttl

  # No knowledge base association - uses action groups for data retrieval
  associate_knowledge_base = false
  knowledge_base_id        = ""

  # No guardrails (removed)
  guardrail_configuration = null

  enable_prompt_override  = false
  create_agent_version    = false  # Route alias to DRAFT (which has action groups)
  agent_alias_name        = "live"
  agent_alias_description = "Live alias for followup agent"

  tags = local.common_tags

  depends_on = [module.iam]
}

# Action Group for Follow-up Agent
# Provides access to report sections, ratings, and metrics history
module "followup_agent_action_group" {
  count  = var.enable_followup_action_group ? 1 : 0
  source = "./modules/action-group"

  agent_id          = module.followup_agent.agent_id
  agent_version     = "DRAFT"
  action_group_name = "ReportResearch"
  description       = "Actions for retrieving investment report sections, ratings, and metrics"

  lambda_arn           = var.followup_action_lambda_arn
  lambda_function_name = var.followup_action_lambda_function_name
  agent_arn            = module.followup_agent.agent_arn
  api_schema_content   = file("${path.module}/schemas/followup_action.yaml")

  lambda_permission_statement_id = "AllowBedrockInvokeFollowup"

  depends_on = [module.followup_agent]
}
