# Complete example showing how to use the Bedrock + Pinecone modules
# This replicates the exact configuration from your existing deployment

terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

# Use the root module to deploy the complete Bedrock + Pinecone setup
module "buffett_bedrock_pinecone" {
  source = "../.."

  # Environment Configuration
  aws_region      = "us-east-1"
  environment     = "dev"
  project_name    = "buffett-chat-ai"

  # Pinecone Configuration
  pinecone_api_key           = var.pinecone_api_key  # Pass this via tfvars or env var
  pinecone_connection_string = "https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io"

  # S3 Source Bucket
  source_bucket_arn = "arn:aws:s3:::buffet-training-data"

  # Knowledge Base Configuration
  knowledge_base_name        = "buffett_kb_pinecone"
  knowledge_base_description = "Buffett embeddings Pinecone"

  # Agent Configuration
  agent_name                 = "buffett-advisor-agent"
  agent_description          = "AI agent that answers questions about Warren Buffett's investment philosophy using shareholder letters"
  foundation_model_id        = "anthropic.claude-3-haiku-20240307-v1:0"

  # Data Source Configuration
  create_data_source      = true
  data_source_name        = "buffett-shareholder-letters"
  data_source_description = "Warren Buffett shareholder letters from S3"

  # Enable custom chunking for better performance
  enable_chunking_configuration = true
  chunking_strategy            = "FIXED_SIZE"
  max_tokens_per_chunk         = 512
  chunk_overlap_percentage     = 20

  # Agent Alias
  agent_alias_name        = "buffett-advisor-alias"
  agent_alias_description = "Alias for Warren Buffett investment advisor agent"
}