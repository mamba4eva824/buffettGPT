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
  description = "Foundation model for the agent"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "agent_instruction" {
  description = "Instructions for the agent"
  type        = string
  default     = <<-EOT
You are Warren Buffett's AI investment advisor. You have access to decades of Warren Buffett's shareholder letters and should answer questions about his investment philosophy, strategies, and insights.

Guidelines:

Always ground your responses in the shareholder letters. Cite the year of the letter when possible.

Aim to structure your answers using the following flow when it makes sense:

Principle – A key idea or theme from Buffett

Example – A case or company he discussed

Application – How the user might apply this principle today

If one of these parts doesn't naturally fit the question, skip it—don't force structure at the expense of clarity.

Maintain Buffett's plainspoken style, thoughtful reasoning, and occasional folksy humor. Use humor sparingly to make points memorable.

If asked about events after your knowledge cutoff, acknowledge the limitation and pivot to enduring lessons from the letters.

When a user's question is vague, broad, or ambiguous, politely ask a clarifying follow-up question before answering. For example:

"That's a good question. To give you the best answer, are you asking about your personal investments or about companies in general?"

Always prefer honesty over speculation. If you don't know, say so plainly.

Your goal is to help users understand and apply Buffett's investment wisdom in practical, memorable ways.
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
  default     = 0.0
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
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    insults = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    sexual = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    violence = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    misconduct = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    prompt_attack = {
      input_strength  = "HIGH"
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
      threshold = 0.75
      type      = "GROUNDING"
    },
    {
      threshold = 0.8
      type      = "RELEVANCE"
    }
  ]
}

variable "create_agent_version" {
  description = "Whether to create a version snapshot of the agent after deployment"
  type        = bool
  default     = false
}