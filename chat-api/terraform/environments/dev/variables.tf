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
  default     = "http://localhost:3000"
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
  # Note: Claude 4.5 Sonnet (anthropic.claude-sonnet-4-5-20250929-v1:0) is not compatible
  # with KB response generation prompt override. Using Claude 3.5 Haiku for now.
  # IMPORTANT: Must use inference profile (us. prefix) for on-demand throughput
  default     = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
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