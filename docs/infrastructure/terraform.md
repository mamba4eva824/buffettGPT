# Terraform Infrastructure

This document covers the Terraform module structure and deployment workflow for BuffettGPT.

## Overview

BuffettGPT infrastructure is defined in Terraform with:

- **Remote State**: S3 backend with DynamoDB locking
- **Modular Design**: Reusable modules for each component
- **Environment Separation**: dev/staging/prod configurations

## Directory Structure

```
chat-api/terraform/
├── backend-setup/              # Remote state backend
│   ├── main.tf
│   └── outputs.tf
├── environments/
│   ├── dev/                    # Development environment
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── staging/                # Staging environment
│   └── prod/                   # Production environment
└── modules/
    ├── core/                   # KMS, IAM, SQS
    ├── dynamodb/               # DynamoDB tables
    ├── lambda/                 # Lambda functions
    ├── api-gateway/            # HTTP and WebSocket APIs
    ├── auth/                   # OAuth infrastructure
    ├── bedrock/                # AI agent configuration
    ├── cloudfront-static-site/ # CDN and S3
    ├── rate-limiting/          # Rate limit infrastructure
    └── monitoring/             # CloudWatch dashboards
```

## Modules

### Core Module

Foundational resources shared across the application:

```hcl
module "core" {
  source = "../../modules/core"

  environment = var.environment
  project     = var.project
}
```

**Resources**:
- KMS encryption key
- IAM roles and policies
- SQS FIFO queue for message processing

### DynamoDB Module

Database tables for the application:

```hcl
module "dynamodb" {
  source = "../../modules/dynamodb"

  environment = var.environment
  kms_key_arn = module.core.kms_key_arn
}
```

**Tables** (8 total):
- `chat-sessions`
- `chat-messages`
- `conversations`
- `websocket-connections`
- `enhanced-rate-limits`
- `usage-tracking`
- `anonymous-sessions`
- `users`

### Lambda Module

Serverless function deployment:

```hcl
module "lambda" {
  source = "../../modules/lambda"

  environment     = var.environment
  lambda_role_arn = module.core.lambda_role_arn
  kms_key_arn     = module.core.kms_key_arn
}
```

**Functions** (9 handlers):
- `chat_http_handler`
- `chat_processor`
- `websocket_connect`
- `websocket_message`
- `websocket_disconnect`
- `auth_callback`
- `auth_verify`
- `conversations_handler`
- `search_handler`

### API Gateway Module

HTTP and WebSocket API configuration:

```hcl
module "api_gateway" {
  source = "../../modules/api-gateway"

  environment           = var.environment
  lambda_functions      = module.lambda.functions
  authorizer_lambda_arn = module.lambda.auth_verify_arn
}
```

## Deployment Workflow

### 1. Initialize Backend (First Time)

```bash
cd chat-api/terraform/backend-setup
terraform init
terraform apply
```

### 2. Initialize Environment

```bash
cd chat-api/terraform/environments/dev
terraform init
```

### 3. Validate Configuration

```bash
terraform validate
```

### 4. Plan Changes

```bash
terraform plan -out=tfplan
```

### 5. Apply Changes

```bash
terraform apply tfplan
```

## State Management

### Remote State Configuration

```hcl
terraform {
  backend "s3" {
    bucket         = "buffett-terraform-state"
    key            = "dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "buffett-terraform-locks"
    encrypt        = true
  }
}
```

### State Locking

DynamoDB table prevents concurrent modifications:

| Attribute | Type | Purpose |
|-----------|------|---------|
| `LockID` | String | Unique lock identifier |

## Variables

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `environment` | Environment name | - |
| `project` | Project name | `buffett-chat-api` |
| `aws_region` | AWS region | `us-east-1` |

### Sensitive Variables

Store in `terraform.tfvars` (gitignored):

```hcl
google_client_id     = "your-client-id"
google_client_secret = "your-client-secret"
jwt_secret           = "your-jwt-secret"
```

## Best Practices

### 1. Always Plan Before Apply

```bash
terraform plan -out=tfplan
terraform apply tfplan
```

### 2. Use Workspaces for Environments

```bash
terraform workspace select dev
terraform workspace select prod
```

### 3. Lock Module Versions

```hcl
module "lambda" {
  source  = "../../modules/lambda"
  version = "~> 1.0"
}
```

### 4. Tag All Resources

```hcl
tags = {
  Environment = var.environment
  Project     = var.project
  ManagedBy   = "terraform"
}
```

## Troubleshooting

### State Lock Issues

```bash
# Force unlock (use with caution)
terraform force-unlock LOCK_ID
```

### Module Changes

```bash
# Reinitialize after module changes
terraform init -upgrade
```

### Import Existing Resources

```bash
terraform import aws_dynamodb_table.example table-name
```
