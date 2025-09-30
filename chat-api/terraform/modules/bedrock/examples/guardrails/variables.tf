# Variables for Guardrails example

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
  default     = "buffett-chat-ai-guardrails"
}

variable "pinecone_api_key" {
  description = "The Pinecone API key value"
  type        = string
  sensitive   = true
}

variable "pinecone_connection_string" {
  description = "Pinecone connection string/endpoint"
  type        = string
  default     = "https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io"
}

variable "source_bucket_arn" {
  description = "ARN of the S3 bucket containing source documents"
  type        = string
  default     = "arn:aws:s3:::buffet-training-data"
}