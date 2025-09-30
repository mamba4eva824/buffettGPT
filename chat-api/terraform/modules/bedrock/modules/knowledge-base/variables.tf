# Variables for Knowledge Base module

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

variable "knowledge_base_role_arn" {
  description = "ARN of the service role for the Knowledge Base"
  type        = string
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

variable "pinecone_credentials_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Pinecone API key"
  type        = string
  default     = "arn:aws:secretsmanager:us-east-1:430118826061:secret:buffett_key-RIDuOz"
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

variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source documents"
  type        = string
  default     = "arn:aws:s3:::buffet-training-data"
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
  description = "Chunking strategy (FIXED_SIZE, SEMANTIC, NONE)"
  type        = string
  default     = "SEMANTIC"

  validation {
    condition     = contains(["FIXED_SIZE", "SEMANTIC", "NONE"], var.chunking_strategy)
    error_message = "Chunking strategy must be either FIXED_SIZE, SEMANTIC, or NONE."
  }
}

variable "max_tokens_per_chunk" {
  description = "Maximum number of tokens per chunk"
  type        = number
  default     = 300
}

variable "chunk_overlap_percentage" {
  description = "Overlap percentage between chunks"
  type        = number
  default     = 20
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}