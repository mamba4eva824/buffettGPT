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