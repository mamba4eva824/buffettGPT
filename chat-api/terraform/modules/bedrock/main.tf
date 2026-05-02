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
# Follow-up Agent + ReportResearch action group removed (2026-05).
# The live follow-up agent runs on Bedrock Runtime converse_stream with
# inline tools (chat-api/backend/src/handlers/analysis_followup.py).
# The Bedrock Agent definition, ReportResearch action group, and the
# followup-action Docker Lambda were all unused.
# ================================================
