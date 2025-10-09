# Development Environment Variables

variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "buffett"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# Bedrock Configuration
variable "bedrock_agent_id" {
  description = "Bedrock agent ID"
  type        = string
}

variable "bedrock_agent_alias" {
  description = "Bedrock agent alias"
  type        = string
}

variable "bedrock_region" {
  description = "Bedrock region"
  type        = string
  default     = "us-east-1"
}

# Search Configuration
# Note: Search API key is now stored in AWS Secrets Manager
# The secret is created by Terraform but the value is populated manually
# Secret ARN is automatically provided via module output

# Authentication Configuration
variable "enable_authentication" {
  description = "Enable authentication module"
  type        = bool
  default     = false  # Temporarily disabled for conversations table deployment
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
  default     = "791748543155-4a5ad31ahdd90ifv1rqjsikurotas819.apps.googleusercontent.com"
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
  default     = ""  # Must be provided via tfvars or env var
}

variable "frontend_url" {
  description = "Frontend application URL"
  type        = string
  default     = "http://localhost:5173"
}

variable "jwt_secret" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
  default     = ""  # Must be provided via tfvars or env var
}

# Monitoring Configuration
variable "enable_monitoring" {
  description = "Enable monitoring module"
  type        = bool
  default     = false  # Disabled for dev
}

variable "alert_email" {
  description = "Email for alerts"
  type        = string
  default     = ""
}

# ================================================
# Bedrock Configuration
# ================================================

# Agent Configuration
variable "bedrock_agent_name" {
  description = "Name of the Bedrock agent"
  type        = string
  default     = "BuffettGPT-Investment-Advisor"
}

variable "bedrock_agent_description" {
  description = "Description of the Bedrock agent"
  type        = string
  default     = "Intelligent investment advisor agent based on Warren Buffett's investment philosophy"
}

variable "bedrock_foundation_model" {
  description = "Foundation model for Bedrock agent"
  type        = string
  default     = "anthropic.claude-3-5-haiku-20241022-v1:0"
}

variable "bedrock_agent_instruction" {
  description = "System instruction for the Bedrock agent"
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

# Knowledge Base Configuration
variable "bedrock_knowledge_base_name" {
  description = "Name of the Bedrock knowledge base"
  type        = string
  default     = "buffett-investment-kb"
}

variable "bedrock_knowledge_base_description" {
  description = "Description of the Bedrock knowledge base"
  type        = string
  default     = "Knowledge base containing Warren Buffett's investment wisdom and market analysis"
}

variable "bedrock_embedding_model_arn" {
  description = "ARN of the embedding model for the knowledge base"
  type        = string
  default     = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "bedrock_source_bucket_arn" {
  description = "S3 bucket ARN containing knowledge base documents (leave empty to skip data source creation)"
  type        = string
  default     = "arn:aws:s3:::buffet-training-data"
}

# Pinecone Configuration
variable "pinecone_connection_string" {
  description = "Pinecone connection string"
  type        = string
  default     = "https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io"
}

variable "pinecone_api_key" {
  description = "Pinecone API key"
  type        = string
  sensitive   = true
  default     = ""
}

# Guardrails Configuration
variable "enable_bedrock_guardrails" {
  description = "Enable Bedrock guardrails"
  type        = bool
  default     = true
}

variable "bedrock_guardrail_name" {
  description = "Name of the Bedrock guardrail"
  type        = string
  default     = "buffett-investment-guardrails"
}

variable "bedrock_guardrail_description" {
  description = "Description of the Bedrock guardrail"
  type        = string
  default     = "Safety guardrails for BuffettGPT investment advisor to ensure responsible financial advice"
}

# Content Filters Configuration
variable "bedrock_content_filters" {
  description = "Content filters configuration for guardrails"
  type = object({
    hate = optional(object({
      input_strength  = string
      output_strength = string
    }))
    violence = optional(object({
      input_strength  = string
      output_strength = string
    }))
    sexual = optional(object({
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
    violence = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    sexual = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    misconduct = {
      input_strength  = "MEDIUM"
      output_strength = "MEDIUM"
    }
    prompt_attack = {
      input_strength  = "HIGH"
      output_strength = "NONE"
    }
  }
}

# PII Entities Configuration
variable "bedrock_pii_entities" {
  description = "PII entities configuration for guardrails"
  type = list(object({
    action = string
    type   = string
  }))
  default = [
    {
      action = "BLOCK"
      type   = "EMAIL"
    },
    {
      action = "BLOCK"
      type   = "PHONE"
    },
    {
      action = "BLOCK"
      type   = "SSN"
    },
    {
      action = "BLOCK"
      type   = "CREDIT_DEBIT_CARD_NUMBER"
    }
  ]
}

# Custom Regexes Configuration
variable "bedrock_custom_regexes" {
  description = "Custom regex patterns for guardrails"
  type = list(object({
    action      = string
    description = string
    name        = string
    pattern     = string
  }))
  default = [
    {
      action      = "BLOCK"
      description = "Block financial account numbers"
      name        = "financial-account-numbers"
      pattern     = "\\b\\d{8,17}\\b"
    }
  ]
}