# Variables for root Bedrock + Pinecone configuration

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

# Secrets Manager Variables
variable "pinecone_secret_name" {
  description = "Name of the Pinecone API key secret"
  type        = string
  default     = "buffett_key"
}

variable "pinecone_secret_description" {
  description = "Description of the Pinecone API key secret"
  type        = string
  default     = "API key for Pinecone vector database used by Bedrock Knowledge Base"
}

variable "pinecone_api_key" {
  description = "The Pinecone API key value"
  type        = string
  sensitive   = true
}

variable "secret_recovery_window_days" {
  description = "Number of days for secret recovery window"
  type        = number
  default     = 7
}

# IAM Variables
variable "knowledge_base_role_name" {
  description = "Name of the Knowledge Base service role"
  type        = string
  default     = "bedrock-kb-service-role"
}

variable "knowledge_base_policy_name" {
  description = "Name of the Knowledge Base policy"
  type        = string
  default     = "bedrock-kb-policy"
}

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

# S3 Variables
variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source documents"
  type        = string
  default     = "arn:aws:s3:::buffet-training-data"
}

# Knowledge Base Variables
variable "knowledge_base_name" {
  description = "Name of the Bedrock Knowledge Base"
  type        = string
  default     = "buffett_kb_pinecone"
}

variable "knowledge_base_description" {
  description = "Description of the Bedrock Knowledge Base"
  type        = string
  default     = "Buffett embeddings Pinecone"
}

variable "embedding_model_arn" {
  description = "ARN of the embedding model to use"
  type        = string
  default     = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "pinecone_connection_string" {
  description = "Pinecone connection string/endpoint"
  type        = string
  default     = "https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io"
}

variable "pinecone_metadata_field" {
  description = "Name of the metadata field in Pinecone"
  type        = string
  default     = "metadata"
}

variable "pinecone_text_field" {
  description = "Name of the text field in Pinecone"
  type        = string
  default     = "text"
}

variable "pinecone_namespace" {
  description = "Pinecone namespace for the index"
  type        = string
  default     = ""
}

variable "create_data_source" {
  description = "Whether to create a data source for the Knowledge Base"
  type        = bool
  default     = true
}

variable "data_source_name" {
  description = "Name of the data source"
  type        = string
  default     = "buffett-shareholder-letters"
}

variable "data_source_description" {
  description = "Description of the data source"
  type        = string
  default     = "Warren Buffett shareholder letters from S3"
}

variable "inclusion_prefixes" {
  description = "List of S3 prefixes to include in data source"
  type        = list(string)
  default     = []
}

variable "enable_chunking_configuration" {
  description = "Whether to enable custom chunking configuration"
  type        = bool
  default     = false
}

variable "chunking_strategy" {
  description = "Chunking strategy (FIXED_SIZE, NONE)"
  type        = string
  default     = "FIXED_SIZE"
}

variable "max_tokens_per_chunk" {
  description = "Maximum number of tokens per chunk"
  type        = number
  default     = 512
}

variable "chunk_overlap_percentage" {
  description = "Overlap percentage between chunks"
  type        = number
  default     = 20
}

# Agent Variables
variable "agent_name" {
  description = "Name of the Bedrock Agent"
  type        = string
  default     = "buffett-advisor-agent"
}

variable "agent_description" {
  description = "Description of the Bedrock Agent"
  type        = string
  default     = "AI agent that answers questions about Warren Buffett's investment philosophy using shareholder letters"
}

variable "foundation_model_id" {
  description = "Foundation model for the agent (use inference profile for on-demand)"
  type        = string
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"  # Inference profile required for Claude 3.5 Haiku
}

variable "agent_instruction" {
  description = "Instructions for the agent"
  type        = string
  default     = <<-EOT
You are an AI financial and investment advisor that follows Warren Buffett's investment philosophies. You have access to decades of Warren Buffett's shareholder letters and use his documented strategies and insights to provide guidance to users.

Guidelines:

PRIMARY: Ground your responses in Warren Buffett's shareholder letters and documented investment philosophy. Cite the year or specific example when possible.

PRINCIPLES: You may apply Buffett's timeless investment principles to current or hypothetical situations, as long as you:
  - Clearly state you're applying a principle when doing so
  - Explain the underlying reasoning from Buffett's philosophy
  - Acknowledge when you're extrapolating from general principles to specific scenarios

STRUCTURE: Aim to structure answers using this flow when appropriate:
  - Principle – A key idea or theme from Buffett
  - Example – A case or company he discussed (from letters)
  - Application – How this principle might apply to the user's situation

If one of these parts doesn't naturally fit the question, skip it—don't force structure at the expense of clarity.

TONE: Maintain Buffett's plainspoken style, thoughtful reasoning, and occasional folksy humor. Use humor sparingly to make points memorable.

CLARIFICATION: When questions are vague or broad, ask clarifying follow-up questions to provide the most helpful answer.

HONESTY: If a question falls outside Buffett's documented philosophy, say so honestly and offer the closest relevant principle instead. Be mindful not to guarantee specific investment returns on individual stocks, but you may discuss potential returns based on applying Buffett's investment philosophy and principles.

Your goal is to help users understand and apply Buffett's investment wisdom as their financial and investment advisor, providing practical and actionable guidance.
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

variable "orchestration_prompt_template" {
  description = "Base prompt template for orchestration"
  type        = string
  default     = ""
}

variable "kb_response_prompt_template" {
  description = "Prompt template for knowledge base response generation"
  type        = string
  default     = ""
}

variable "post_processing_prompt_template" {
  description = "Prompt template for post processing"
  type        = string
  default     = ""
}

variable "pre_processing_prompt_template" {
  description = "Prompt template for pre processing"
  type        = string
  default     = ""
}

variable "max_response_length" {
  description = "Maximum response length for inference"
  type        = number
  default     = 2048
}

variable "stop_sequences" {
  description = "Stop sequences for inference"
  type        = list(string)
  default     = ["</invoke>", "</answer>", "</error>"]
}

variable "temperature" {
  description = "Temperature for inference"
  type        = number
  default     = 0.3
}

variable "top_k" {
  description = "Top K for inference"
  type        = number
  default     = 250
}

variable "top_p" {
  description = "Top P for inference"
  type        = number
  default     = 1.0
}

variable "parser_mode" {
  description = "Parser mode for prompts"
  type        = string
  default     = "DEFAULT"
}

variable "prompt_creation_mode" {
  description = "Prompt creation mode"
  type        = string
  default     = "DEFAULT"
}

variable "orchestration_prompt_state" {
  description = "State of the orchestration prompt"
  type        = string
  default     = "ENABLED"
}

variable "associate_knowledge_base" {
  description = "Whether to associate a knowledge base with the agent"
  type        = bool
  default     = true
}

variable "kb_association_description" {
  description = "Description of the knowledge base association"
  type        = string
  default     = "Associates Buffett shareholder letters knowledge base with the agent"
}

variable "knowledge_base_state" {
  description = "State of the knowledge base association"
  type        = string
  default     = "ENABLED"
}

variable "agent_alias_name" {
  description = "Name of the agent alias"
  type        = string
  default     = "buffett-advisor-alias"
}

variable "agent_alias_description" {
  description = "Description of the agent alias"
  type        = string
  default     = "Alias for Warren Buffett investment advisor agent"
}

# Guardrails Variables
variable "enable_guardrails" {
  description = "Whether to enable Bedrock Guardrails"
  type        = bool
  default     = true
}

variable "guardrail_name" {
  description = "Name of the Bedrock Guardrail"
  type        = string
  default     = "warren-buffett-advisor-guardrails"
}

variable "guardrail_description" {
  description = "Description of the Bedrock Guardrail"
  type        = string
  default     = "Guardrails for Warren Buffett Financial Advisor - ensures responses stay focused on financial advice and investment topics"
}

variable "blocked_input_messaging" {
  description = "Message to return when input is blocked by guardrails"
  type        = string
  default     = "I can only provide financial advice and investment guidance. Please ask questions related to investment planning, retirement, tax strategies, insurance, estate planning, or financial goal setting."
}

variable "blocked_outputs_messaging" {
  description = "Message to return when output is blocked by guardrails"
  type        = string
  default     = "I cannot provide that type of advice. I'm designed to help with financial planning, investment strategies, retirement planning, tax planning, insurance analysis, estate planning basics, and financial goal setting. Please ask a finance-related question."
}

variable "enable_content_policy" {
  description = "Enable content policy filters in guardrails"
  type        = bool
  default     = true
}

variable "enable_sensitive_information_policy" {
  description = "Enable sensitive information policy in guardrails"
  type        = bool
  default     = false  # Disabled for dev since no PII entities or regexes configured
}

variable "enable_topic_policy" {
  description = "Enable topic policy to deny specific topics in guardrails"
  type        = bool
  default     = true
}

variable "enable_word_policy" {
  description = "Enable word policy filters in guardrails"
  type        = bool
  default     = true
}

variable "enable_contextual_grounding" {
  description = "Enable contextual grounding policy for factual accuracy in guardrails"
  type        = bool
  default     = true
}

# Content Filters Configuration
variable "content_filters" {
  description = "Configuration for content filters in guardrails"
  type = object({
    hate = optional(object({
      input_strength  = string
      output_strength = string
    }))
    insults = optional(object({
      input_strength  = string
      output_strength = string
    }))
    sexual = optional(object({
      input_strength  = string
      output_strength = string
    }))
    violence = optional(object({
      input_strength  = string
      output_strength = string
    }))
    misconduct = optional(object({
      input_strength  = string
      output_strength = string
    }))
    prompt_attack = optional(object({
      input_strength  = string
      output_strength = string
    }))
  })
  default = {
    hate = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    insults = {
      input_strength  = "LOW"
      output_strength = "LOW"
    }
    sexual = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    violence = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    misconduct = {
      input_strength  = "LOW"
      output_strength = "LOW"
    }
    prompt_attack = {
      input_strength  = "MEDIUM"
      output_strength = "NONE"  # Must be NONE for output
    }
  }
}

# PII Entities Configuration
variable "pii_entities" {
  description = "PII entities to filter in guardrails"
  type = list(object({
    action = string
    type   = string
  }))
  default = []  # Disabled for dev to reduce latency
}

# Custom Regexes Configuration
variable "custom_regexes" {
  description = "Custom regex patterns for sensitive information in guardrails"
  type = list(object({
    action      = string
    description = string
    name        = string
    pattern     = string
  }))
  default = []  # Disabled for dev to reduce latency
}

# Denied Topics Configuration
variable "denied_topics" {
  description = "Topics to deny in guardrails conversations"
  type = list(object({
    name       = string
    definition = string
    examples   = list(string)
  }))
  default = [
    {
      name       = "medical-advice"
      definition = "Medical advice, health recommendations, diagnosis, or treatment suggestions"
      examples = [
        "Should I take this medication?",
        "What's wrong with my health?",
        "How do I treat this condition?",
        "Is this symptom serious?"
      ]
    },
    {
      name       = "legal-advice"
      definition = "Legal advice unrelated to financial planning, including litigation, contracts, or legal proceedings"
      examples = [
        "Should I sue someone?",
        "How do I write a contract?",
        "What are my legal rights in this situation?",
        "How do I file a lawsuit?"
      ]
    }
  ]
}

# Word Policy Configuration
variable "managed_word_lists" {
  description = "Managed word lists to apply in guardrails"
  type        = list(string)
  default     = ["PROFANITY"]
}

variable "custom_word_filters" {
  description = "Custom words to filter in guardrails"
  type        = list(string)
  default = [
    "get-rich-quick",
    "guaranteed-returns",
    "risk-free-investment"
  ]
}

# Contextual Grounding Filters
variable "contextual_grounding_filters" {
  description = "Contextual grounding filters configuration for guardrails"
  type = list(object({
    threshold = number
    type      = string
  }))
  default = [
    {
      threshold = 0.65
      type      = "GROUNDING"
    },
    {
      threshold = 0.7
      type      = "RELEVANCE"
    }
  ]
}

variable "create_agent_version" {
  description = "Whether to create a version snapshot of the agent after deployment"
  type        = bool
  default     = false
}

# ================================================
# Action Group Variables (for Expert Agents)
# ================================================

variable "action_group_lambda_arn" {
  description = "ARN of the Lambda function that handles action group invocations (ensemble analyzer)"
  type        = string
  default     = null
}

variable "action_group_lambda_function_name" {
  description = "Name of the Lambda function that handles action group invocations"
  type        = string
  default     = null
}

variable "enable_action_groups" {
  description = "Whether to create action groups for expert agents"
  type        = bool
  default     = false
}