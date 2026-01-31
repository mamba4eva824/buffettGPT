# Variables for Bedrock Agents configuration
# Updated 2025-01: Removed Pinecone, Knowledge Base, and Guardrails variables

variable "aws_region" {
  description = "AWS region for resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "buffett-chat-ai"
}

# ================================================
# IAM Variables
# ================================================

variable "agent_role_name" {
  description = "Name of the Agent service role"
  type        = string
  default     = "bedrock-agent-service-role"
}

variable "agent_policy_name" {
  description = "Name of the Agent policy"
  type        = string
  default     = "bedrock-agent-policy"
}

variable "attach_bedrock_full_access" {
  description = "Whether to attach AmazonBedrockFullAccess managed policy to agent role"
  type        = bool
  default     = true
}

# S3 Variables (still needed for IAM policy, even though KB is removed)
variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source documents"
  type        = string
  default     = "arn:aws:s3:::buffet-training-data"
}

# ================================================
# Agent Variables
# ================================================

variable "agent_name" {
  description = "Name of the Bedrock Agent"
  type        = string
  default     = "buffett-advisor-agent"
}

variable "agent_description" {
  description = "Description of the Bedrock Agent"
  type        = string
  default     = "AI agent that answers questions about Warren Buffett's investment philosophy"
}

variable "foundation_model_id" {
  description = "Foundation model for the agent (use inference profile for on-demand)"
  type        = string
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "agent_instruction" {
  description = "Instructions for the agent"
  type        = string
  default     = <<-EOT
You are an AI financial and investment advisor that follows Warren Buffett's investment philosophies.

Guidelines:
- Ground your responses in Warren Buffett's documented investment philosophy
- Apply Buffett's timeless investment principles to current situations
- Maintain Buffett's plainspoken style and thoughtful reasoning
- Be honest when questions fall outside Buffett's documented philosophy
EOT
}

variable "idle_session_ttl" {
  description = "Idle session TTL in seconds"
  type        = number
  default     = 1800
}

variable "enable_prompt_override" {
  description = "Whether to enable prompt override configuration"
  type        = bool
  default     = true
}

variable "create_agent_version" {
  description = "Whether to create a version snapshot of the agent after deployment"
  type        = bool
  default     = false
}

# ================================================
# Followup Agent Action Group Variables
# ================================================
# NOTE: Expert agent action group variables (action_group_lambda_arn,
# action_group_lambda_function_name, enable_action_groups) were removed
# when the prediction ensemble was archived (2025-01)

variable "enable_followup_action_group" {
  description = "Whether to create action group for followup agent"
  type        = bool
  default     = false
}

variable "followup_action_lambda_arn" {
  description = "ARN of the Lambda function that handles followup action group invocations"
  type        = string
  default     = null
}

variable "followup_action_lambda_function_name" {
  description = "Name of the Lambda function that handles followup action group invocations"
  type        = string
  default     = null
}

# ================================================
# REMOVED VARIABLES (2025-01 Cleanup)
# ================================================
# The following variables were removed as part of RAG chatbot deprecation:
#
# Pinecone/Secrets:
# - pinecone_secret_name, pinecone_secret_description, pinecone_api_key
# - secret_recovery_window_days
# - pinecone_connection_string, pinecone_metadata_field, pinecone_text_field, pinecone_namespace
#
# Knowledge Base:
# - knowledge_base_role_name, knowledge_base_policy_name
# - knowledge_base_name, knowledge_base_description
# - embedding_model_arn
# - create_data_source, data_source_name, data_source_description
# - inclusion_prefixes
# - enable_chunking_configuration, chunking_strategy, max_tokens_per_chunk, chunk_overlap_percentage
# - associate_knowledge_base, kb_association_description, knowledge_base_state
#
# Guardrails:
# - enable_guardrails, guardrail_name, guardrail_description
# - blocked_input_messaging, blocked_outputs_messaging
# - enable_content_policy, enable_sensitive_information_policy
# - enable_topic_policy, enable_word_policy, enable_contextual_grounding
# - content_filters, pii_entities, custom_regexes
# - denied_topics, managed_word_lists, custom_word_filters
# - contextual_grounding_filters
#
# Prompt Override (simplified):
# - orchestration_prompt_template, kb_response_prompt_template
# - post_processing_prompt_template, pre_processing_prompt_template
# - max_response_length, stop_sequences, temperature, top_k, top_p
# - parser_mode, prompt_creation_mode, orchestration_prompt_state
# - agent_alias_name, agent_alias_description
# ================================================
