# AWS Bedrock Knowledge Base Configuration with Pinecone Vector Store
## A Complete RAG Implementation Guide Using Terraform

### Date: September 26, 2025
### Author: Configuration Session Documentation

---

## Executive Summary

This document details the complete configuration and deployment of an AWS Bedrock Knowledge Base integrated with Pinecone as the vector store, implementing a Retrieval-Augmented Generation (RAG) architecture. The setup ingests Warren Buffett's shareholder letters from S3, processes them with semantic chunking, generates embeddings using AWS Titan Text Embeddings v2, and stores the vectors in Pinecone for efficient similarity search.

## Architecture Overview

### Core Components

1. **AWS Bedrock Knowledge Base**: Central orchestrator for the RAG pipeline
2. **Pinecone Vector Database**: High-performance vector storage and similarity search
3. **Amazon S3**: Document storage for source materials
4. **AWS Titan Text Embeddings v2**: 1024-dimensional embedding model
5. **Semantic Chunking**: Intelligent document splitting with 300 token limits
6. **Terraform Infrastructure**: Fully automated infrastructure as code

## Configuration Parameters

### Pinecone Specifications

```yaml
Vector Store Configuration:
  Host URL: https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io
  Region: us-east-1
  Dimensions: 1024
  Metric: Cosine Similarity
  Type: Dense (FLOAT32)

Field Mapping:
  Vector Field: "text"  # Note: Bedrock manages this internally
  Text Field: "text"
  Metadata Field: "metadata"
  Namespace: "" (default namespace)
```

### AWS Resources

```yaml
S3 Bucket:
  ARN: arn:aws:s3:::buffet-training-data
  Purpose: Source document storage
  Content: 46 Warren Buffett shareholder letters

Secrets Manager:
  ARN: arn:aws:secretsmanager:us-east-1:430118826061:secret:buffett_key-RIDuOz
  Content: Pinecone API key

IAM Roles:
  Knowledge Base Role: bedrock-kb-service-role
  Agent Role: bedrock-agent-service-role
```

### Embedding Configuration

```yaml
Model: Amazon Titan Text Embeddings v2
ARN: arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0
Specifications:
  Dimensions: 1024
  Data Type: FLOAT32
  Vector Normalization: Automatic
```

### Chunking Strategy

```yaml
Strategy: SEMANTIC
Parameters:
  Max Tokens: 300
  Breakpoint Percentile Threshold: 95
  Buffer Size: 1
  Purpose: Intelligently splits documents at semantic boundaries
```

## Terraform Implementation

### Module Structure

```
terraform/
├── environments/
│   └── dev/
│       ├── main.tf           # Environment configuration
│       └── variables.tf       # Environment variables
└── modules/
    └── bedrock/
        ├── main.tf            # Bedrock module orchestration
        ├── variables.tf       # Module variables with defaults
        └── modules/
            ├── knowledge-base/
            │   ├── main.tf    # Knowledge base and data source
            │   └── variables.tf
            ├── iam/               # IAM roles and policies
            └── secrets/           # Secrets management
```

### Key Terraform Configurations

#### 1. Knowledge Base Resource

```hcl
resource "aws_bedrockagent_knowledge_base" "main" {
  name        = "buffett-investment-kb-dev"
  description = "Development knowledge base for Warren Buffett investment wisdom"
  role_arn    = var.knowledge_base_role_arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"

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
      connection_string      = "https://buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io"
      credentials_secret_arn = "arn:aws:secretsmanager:us-east-1:430118826061:secret:buffett_key-RIDuOz"

      field_mapping {
        metadata_field = "metadata"
        text_field     = "text"
      }
    }
  }
}
```

#### 2. Data Source with Semantic Chunking

```hcl
resource "aws_bedrockagent_data_source" "main" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "buffett-shareholder-letters"
  description       = "Warren Buffett shareholder letters from S3"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = "arn:aws:s3:::buffet-training-data"
      # inclusion_prefixes conditionally set only if not empty
      inclusion_prefixes = length(var.inclusion_prefixes) > 0 ? var.inclusion_prefixes : null
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "SEMANTIC"

      semantic_chunking_configuration {
        max_token                      = 300
        buffer_size                    = 1
        breakpoint_percentile_threshold = 95
      }
    }
  }
}
```

#### 3. Module Variables with Smart Defaults

```hcl
# In modules/bedrock/modules/knowledge-base/variables.tf
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

variable "chunking_strategy" {
  description = "Chunking strategy (FIXED_SIZE, SEMANTIC, NONE)"
  type        = string
  default     = "SEMANTIC"

  validation {
    condition     = contains(["FIXED_SIZE", "SEMANTIC", "NONE"], var.chunking_strategy)
    error_message = "Chunking strategy must be either FIXED_SIZE, SEMANTIC, or NONE."
  }
}
```

## Deployment Process

### Step 1: Environment Configuration

```hcl
# environments/dev/main.tf
module "bedrock" {
  source = "../../modules/bedrock"

  # Essential overrides only
  create_data_source            = true
  enable_chunking_configuration = true
  chunking_strategy            = "SEMANTIC"
  max_tokens_per_chunk         = 300
  pinecone_api_key            = var.pinecone_api_key

  # Let module defaults handle the rest
}
```

### Step 2: Targeted Deployment

```bash
# Initialize Terraform
terraform init

# Plan the knowledge base deployment
terraform plan -target=module.bedrock.module.knowledge_base

# Apply the configuration
terraform apply -target=module.bedrock.module.knowledge_base -auto-approve
```

### Step 3: Data Ingestion

```bash
# Start ingestion job
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id YTLJVSWGF9 \
  --data-source-id VB3AGDILO1

# Monitor ingestion status
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id YTLJVSWGF9 \
  --data-source-id VB3AGDILO1 \
  --ingestion-job-id <JOB_ID>
```

## Challenges and Solutions

### 1. Redundant Configuration

**Problem**: Configuration values duplicated across multiple levels (dev environment, bedrock module, knowledge-base module).

**Solution**: Leverage module defaults and only override when necessary:
- Removed redundant `source_bucket_arn`, `pinecone_connection_string`, and `embedding_model_arn` from dev environment
- Configured smart defaults in the module
- Used comments to document default usage

### 2. Empty Inclusion Prefixes Validation Error

**Problem**: AWS API requires `inclusion_prefixes` to have at least one element if provided.

**Solution**: Conditional inclusion using Terraform's ternary operator:
```hcl
inclusion_prefixes = length(var.inclusion_prefixes) > 0 ? var.inclusion_prefixes : null
```

### 3. Semantic Chunking Configuration

**Problem**: Initial configuration defaulted to FIXED_SIZE chunking instead of SEMANTIC.

**Solution**: Explicitly override in environment configuration:
```hcl
chunking_strategy    = "SEMANTIC"
max_tokens_per_chunk = 300
```

### 4. Vector Field Mapping

**Problem**: Initial attempts to configure `vector_field` in Pinecone field mapping.

**Solution**: AWS Bedrock manages vector field internally; only `text_field` and `metadata_field` are configurable.

## Best Practices Implemented

### 1. Infrastructure as Code
- All resources defined in Terraform
- Version controlled configuration
- Reproducible deployments

### 2. Security
- Credentials stored in AWS Secrets Manager
- IAM roles with least privilege
- Specific S3 bucket permissions (not wildcards)

### 3. Configuration Management
- Smart defaults in modules
- Minimal overrides in environments
- Clear separation of concerns

### 4. Resource Organization
- Modular Terraform structure
- Logical grouping of resources
- Reusable components

## Verification Commands

### Knowledge Base Status
```bash
aws bedrock-agent get-knowledge-base \
  --knowledge-base-id YTLJVSWGF9 \
  --query '{Status:status,Storage:storageConfiguration.type}'
```

### Data Source Configuration
```bash
aws bedrock-agent get-data-source \
  --knowledge-base-id YTLJVSWGF9 \
  --data-source-id VB3AGDILO1 \
  --query '{Status:status,ChunkingStrategy:vectorIngestionConfiguration.chunkingConfiguration.chunkingStrategy}'
```

### Ingestion Job Monitoring
```bash
aws bedrock-agent list-ingestion-jobs \
  --knowledge-base-id YTLJVSWGF9 \
  --data-source-id VB3AGDILO1
```

## Performance Metrics

- **Documents Processed**: 46 shareholder letters
- **Chunking Strategy**: Semantic with 300 token limit
- **Vector Dimensions**: 1024
- **Similarity Metric**: Cosine
- **Ingestion Time**: ~3-5 minutes for full corpus

## Future Enhancements

### 1. Advanced Chunking
- Experiment with different token limits
- Adjust breakpoint percentile thresholds
- Implement hierarchical chunking for long documents

### 2. Monitoring and Observability
- CloudWatch metrics for ingestion jobs
- Pinecone index statistics monitoring
- Query performance tracking

### 3. Multi-Environment Support
- Staging environment with separate Pinecone index
- Production environment with high availability
- Environment-specific chunking strategies

### 4. Content Management
- Automated S3 document updates
- Scheduled re-ingestion jobs
- Version tracking for document changes

## Conclusion

This configuration successfully implements a production-ready RAG architecture combining AWS Bedrock's managed services with Pinecone's high-performance vector database. The use of Terraform ensures reproducible deployments, while semantic chunking and 1024-dimensional embeddings provide optimal retrieval quality for the Warren Buffett investment knowledge base.

The architecture is designed for scalability, security, and maintainability, making it suitable for both development and production environments. The modular approach allows for easy customization and extension as requirements evolve.

## Resources and References

- [AWS Bedrock Knowledge Base Documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)
- [Pinecone Documentation](https://docs.pinecone.io/)
- [Terraform AWS Provider - Bedrock Resources](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/bedrockagent_knowledge_base)
- [Semantic Chunking Best Practices](https://www.pinecone.io/learn/chunking-strategies/)
- [RAG Architecture Patterns](https://www.pinecone.io/learn/retrieval-augmented-generation/)

---

*Document generated during live configuration session on September 26, 2025*
*Configuration successfully deployed with Knowledge Base ID: YTLJVSWGF9 and Data Source ID: VB3AGDILO1*