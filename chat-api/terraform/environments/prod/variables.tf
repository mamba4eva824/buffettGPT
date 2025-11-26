# Production Environment Variables

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
# Note: These are optional - the Bedrock module will create these resources
# Only provide values if using an existing agent (not recommended for production)
variable "bedrock_agent_id" {
  description = "Bedrock agent ID (optional - will be created by module)"
  type        = string
  default     = ""
}

variable "bedrock_agent_alias" {
  description = "Bedrock agent alias (optional - will be created by module)"
  type        = string
  default     = ""
}

variable "bedrock_region" {
  description = "Bedrock region"
  type        = string
  default     = "us-east-1"
}

# Authentication Configuration
variable "enable_authentication" {
  description = "Enable authentication module"
  type        = bool
  default     = true # Enable auth for production
}

variable "google_client_id" {
  description = "Google OAuth client ID"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth client secret"
  type        = string
  sensitive   = true
}

variable "frontend_url" {
  description = "Frontend application URL (CloudFront distribution)"
  type        = string
  default     = "" # Will be populated after CloudFront is created
}

variable "jwt_secret" {
  description = "JWT signing secret"
  type        = string
  sensitive   = true
}

# Monitoring Configuration
variable "enable_monitoring" {
  description = "Enable monitoring module"
  type        = bool
  default     = true # Enable monitoring for production
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
  default     = "BuffettGPT-Investment-Advisor-Prod"
}

variable "bedrock_agent_description" {
  description = "Description of the Bedrock agent"
  type        = string
  default     = "Production: Intelligent investment advisor agent based on Warren Buffett's investment philosophy"
}

variable "bedrock_foundation_model" {
  description = "Foundation model for Bedrock agent"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "bedrock_agent_instruction" {
  description = "System instruction for the Bedrock agent"
  type        = string
  default     = "You are Warren Buffett's AI investment advisor. You answer questions about his investment philosophy, strategies, and insights using his shareholder letters and proven investment principles."
}

# Knowledge Base Configuration
variable "bedrock_knowledge_base_name" {
  description = "Name of the Bedrock knowledge base"
  type        = string
  default     = "buffett-investment-kb-prod"
}

variable "bedrock_knowledge_base_description" {
  description = "Description of the Bedrock knowledge base"
  type        = string
  default     = "Production: Knowledge base containing Warren Buffett's investment wisdom and market analysis"
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
  default     = "https://buffett-embeddings-prod-34d0bay.svc.aped-4627-b74a.pinecone.io"
}

variable "pinecone_api_key" {
  description = "Pinecone API key"
  type        = string
  sensitive   = true
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
  default     = "buffett-investment-guardrails-prod"
}

variable "bedrock_guardrail_description" {
  description = "Description of the Bedrock guardrail"
  type        = string
  default     = "Production: Safety guardrails for BuffettGPT investment advisor to ensure responsible financial advice"
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
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    violence = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    sexual = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    misconduct = {
      input_strength  = "HIGH"
      output_strength = "HIGH"
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
