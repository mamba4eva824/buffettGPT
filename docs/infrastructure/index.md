# Infrastructure

This section covers BuffettGPT's AWS infrastructure, Terraform modules, and deployment processes.

## Overview

BuffettGPT runs entirely on AWS with infrastructure managed through Terraform:

- **Compute**: Lambda functions (Python 3.11)
- **API**: API Gateway (HTTP + WebSocket)
- **Database**: DynamoDB (8 tables)
- **Messaging**: SQS FIFO queues
- **AI**: Amazon Bedrock (Claude Haiku)
- **CDN**: CloudFront for static assets
- **Security**: KMS encryption, IAM roles

## Documentation

| Document | Description |
|----------|-------------|
| [Terraform](terraform.md) | Module structure and deployment commands |
| [Lambda Functions](lambda-functions.md) | Handler documentation and triggers |
| [DynamoDB Schema](dynamodb-schema.md) | Table schemas and migration history |
| [Deployment](deployment.md) | CI/CD pipelines and environment promotion |

## Terraform Modules

Located in `chat-api/terraform/modules/`:

| Module | Purpose |
|--------|---------|
| `core` | KMS encryption, IAM roles, SQS queues |
| `dynamodb` | 8 DynamoDB tables |
| `lambda` | Lambda function deployment with layers |
| `api-gateway` | HTTP and WebSocket API configuration |
| `auth` | OAuth authentication infrastructure |
| `bedrock` | AI agent, knowledge base, guardrails |
| `cloudfront-static-site` | CDN and S3 static hosting |
| `rate-limiting` | Device fingerprinting and quotas |
| `monitoring` | CloudWatch dashboards and alerts |

## Environment Configuration

### Environments

| Environment | Purpose | Deployment |
|-------------|---------|------------|
| `dev` | Development and testing | Auto on push to `dev` branch |
| `staging` | Pre-production validation | Auto on push to `staging` branch |
| `prod` | Production | Manual approval required |

### Resource Naming

All AWS resources follow the naming convention:

```
{project-name}-{environment}-{resource-type}
```

Example: `buffett-chat-api-dev-chat-sessions`

## Deployment Workflow

```bash
# Navigate to environment
cd chat-api/terraform/environments/dev

# Initialize Terraform
terraform init

# Validate configuration
terraform validate

# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan
```

## Security

- **Encryption**: KMS for all data at rest
- **Secrets**: AWS Secrets Manager for credentials
- **IAM**: Least-privilege roles for each Lambda
- **Network**: Private subnets where applicable
