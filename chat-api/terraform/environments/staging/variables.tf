# Staging Environment Variables

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
# Only provide values if using an existing agent (not recommended for staging)
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
  default     = true # Enable auth for staging (friends & family testing)
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
  default     = true # Enable monitoring for staging
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
  default     = "BuffettGPT-Investment-Advisor-Staging"
}

variable "bedrock_agent_description" {
  description = "Description of the Bedrock agent"
  type        = string
  default     = "Staging: Intelligent investment advisor agent based on Warren Buffett's investment philosophy"
}

variable "bedrock_foundation_model" {
  description = "Foundation model for Bedrock agent"
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "basic_auth_credentials" {
  description = "Base64-encoded username:password for staging basic auth"
  type        = string
  sensitive   = true
}

variable "bedrock_agent_instruction" {
  description = "System instruction for the Bedrock agent"
  type        = string
  default     = "You are Warren Buffett's AI investment advisor. You answer questions about his investment philosophy, strategies, and insights using his shareholder letters and proven investment principles."
}

# ================================================
# REMOVED VARIABLES (2025-01 Cleanup)
# ================================================
# The following variables were removed as part of RAG chatbot deprecation:
# - bedrock_knowledge_base_name, bedrock_knowledge_base_description
# - bedrock_embedding_model_arn, bedrock_source_bucket_arn
# - pinecone_connection_string, pinecone_api_key
# - enable_bedrock_guardrails, bedrock_guardrail_name, bedrock_guardrail_description
# - bedrock_content_filters, bedrock_pii_entities, bedrock_custom_regexes
# ================================================