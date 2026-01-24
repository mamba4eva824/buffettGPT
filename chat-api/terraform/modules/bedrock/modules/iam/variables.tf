# Variables for IAM module

variable "create_knowledge_base_resources" {
  description = "Whether to create Knowledge Base IAM resources (deprecated - set to false)"
  type        = bool
  default     = false
}

variable "knowledge_base_role_name" {
  description = "Name of the Knowledge Base service role (deprecated)"
  type        = string
  default     = "bedrock-kb-service-role"
}

variable "knowledge_base_policy_name" {
  description = "Name of the Knowledge Base policy (deprecated)"
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

variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source documents"
  type        = string
}

variable "pinecone_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Pinecone API key"
  type        = string
}

variable "foundation_model_id" {
  description = "Foundation model ID for the agent"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "attach_bedrock_full_access" {
  description = "Whether to attach AmazonBedrockFullAccess managed policy to agent role"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}