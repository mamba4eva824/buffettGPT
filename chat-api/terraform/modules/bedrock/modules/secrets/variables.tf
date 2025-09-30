# Variables for Secrets Manager module

variable "secret_name" {
  description = "Name of the Pinecone API key secret"
  type        = string
  default     = "buffett_key"
}

variable "secret_description" {
  description = "Description of the Pinecone API key secret"
  type        = string
  default     = "API key for Pinecone vector database used by Bedrock Knowledge Base"
}

variable "pinecone_api_key" {
  description = "The Pinecone API key value"
  type        = string
  sensitive   = true
}

variable "recovery_window_days" {
  description = "Number of days for secret recovery window (0 for immediate deletion)"
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}