
# Knowledge Base module for Bedrock with Pinecone vector store

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Bedrock Knowledge Base
resource "aws_bedrockagent_knowledge_base" "main" {
  name        = var.knowledge_base_name
  description = var.knowledge_base_description
  role_arn    = var.knowledge_base_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = var.embedding_model_arn

      embedding_model_configuration {
        bedrock_embedding_model_configuration {
          dimensions          = 1024
          embedding_data_type = "FLOAT32"
        }
      }
    }
  }

  storage_configuration {
    type = "PINECONE"
    pinecone_configuration {
      connection_string        = var.pinecone_connection_string
      credentials_secret_arn   = var.pinecone_credentials_secret_arn
      namespace                = var.pinecone_namespace
      field_mapping {
        metadata_field = var.pinecone_metadata_field
        text_field     = var.pinecone_text_field
      }
    }
  }

  tags = merge(var.tags, {
    Name      = var.knowledge_base_name
    Purpose   = "Bedrock Knowledge Base with Pinecone Vector Store"
    Component = "Bedrock Knowledge Base"
  })
}

# Data Source for Knowledge Base
resource "aws_bedrockagent_data_source" "main" {
  count             = var.create_data_source ? 1 : 0
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = var.data_source_name
  description       = var.data_source_description

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = var.source_bucket_arn

      # Optional: specify inclusion prefixes (only if not empty)
      inclusion_prefixes = length(var.inclusion_prefixes) > 0 ? var.inclusion_prefixes : null
    }
  }

  # Optional: Configure chunking strategy
  dynamic "vector_ingestion_configuration" {
    for_each = var.enable_chunking_configuration ? [1] : []
    content {
      chunking_configuration {
        chunking_strategy = var.chunking_strategy

        dynamic "fixed_size_chunking_configuration" {
          for_each = var.chunking_strategy == "FIXED_SIZE" ? [1] : []
          content {
            max_tokens = var.max_tokens_per_chunk
            overlap_percentage = var.chunk_overlap_percentage
          }
        }

        dynamic "semantic_chunking_configuration" {
          for_each = var.chunking_strategy == "SEMANTIC" ? [1] : []
          content {
            max_token                      = var.max_tokens_per_chunk
            buffer_size                    = 1
            breakpoint_percentile_threshold = 95
          }
        }
      }
    }
  }

}