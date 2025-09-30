# Root Terraform configuration for Bedrock + Pinecone setup
# Orchestrates all modules to replicate existing configuration

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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

# Agent module
module "agent" {
  source = "./modules/agent"

  agent_name                        = var.agent_name
  agent_description                 = var.agent_description
  agent_role_arn                   = module.iam.agent_role_arn
  foundation_model                 = var.foundation_model_id
  agent_instruction                = var.agent_instruction
  idle_session_ttl                 = var.idle_session_ttl
  enable_prompt_override           = var.enable_prompt_override
  orchestration_prompt_template    = file("${path.module}/prompts/orchestration_formatted.txt")
  kb_response_prompt_template      = file("${path.module}/prompts/kb_response.txt")
  post_processing_prompt_template  = var.post_processing_prompt_template
  pre_processing_prompt_template   = var.pre_processing_prompt_template
  max_response_length              = var.max_response_length
  stop_sequences                   = var.stop_sequences
  temperature                      = var.temperature
  top_k                           = var.top_k
  top_p                           = var.top_p
  parser_mode                     = var.parser_mode
  prompt_creation_mode            = var.prompt_creation_mode
  orchestration_prompt_state      = var.orchestration_prompt_state
  associate_knowledge_base        = var.associate_knowledge_base
  knowledge_base_id               = module.knowledge_base.knowledge_base_id
  kb_association_description      = var.kb_association_description
  knowledge_base_state            = var.knowledge_base_state
  agent_alias_name                = var.agent_alias_name
  agent_alias_description         = var.agent_alias_description
  # Pass guardrails configuration to agent
  guardrail_configuration = var.enable_guardrails ? {
    guardrail_identifier = module.guardrails[0].guardrail_id
    guardrail_version    = module.guardrails[0].guardrail_version
  } : null
  create_agent_version            = var.create_agent_version
  tags                            = local.common_tags

  depends_on = [module.knowledge_base, module.guardrails]
}