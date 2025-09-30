# Bedrock + Pinecone Terraform Module

This Terraform module creates AWS Bedrock + Pinecone infrastructure for the Buffett Chat AI assistant.

## Overview

The module creates:
- **Knowledge Base**: `buffett_kb_pinecone` with Pinecone vector store
- **Agent**: `buffett-advisor-agent` with Warren Buffett investment philosophy
- **IAM Roles**: Service roles and policies for Bedrock access
- **Secrets**: Pinecone API key stored in Secrets Manager

## Usage

### Quick Start

1. **Navigate to example:**
   ```bash
   cd examples/complete
   cp terraform.tfvars.example terraform.tfvars
   ```

2. **Add your Pinecone API key:**
   ```hcl
   pinecone_api_key = "your-actual-pinecone-api-key"
   ```

3. **Deploy:**
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

### Integration with Main Project

Use in your main terraform configuration:

```hcl
module "bedrock" {
  source = "./modules/bedrock"

  pinecone_api_key = var.pinecone_api_key
  environment      = local.environment
  project_name     = local.project_name
}
```

## Configuration Details

### Current Production Values
- **Knowledge Base ID**: `D1ZVQ1VWHU`
- **Agent ID**: `P82I6ITJGO`
- **Pinecone Endpoint**: `buffett-embeddings-34d0bay.svc.aped-4627-b74a.pinecone.io`
- **S3 Bucket**: `buffet-training-data`
- **Foundation Model**: `anthropic.claude-3-haiku-20240307-v1:0`

## Outputs

The module outputs all resource identifiers needed for Lambda integration:
- `agent_id` - For BEDROCK_AGENT_ID environment variable
- `knowledge_base_id` - For KNOWLEDGE_BASE_ID environment variable
- `agent_alias_id` - For BEDROCK_AGENT_ALIAS environment variable
