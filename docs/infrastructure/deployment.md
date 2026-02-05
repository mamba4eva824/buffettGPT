# Deployment

This document covers the CI/CD pipelines and deployment processes for BuffettGPT.

## Overview

BuffettGPT uses GitHub Actions for automated deployments:

| Environment | Trigger | Approval |
|-------------|---------|----------|
| Development | Push to `dev` branch | Automatic |
| Staging | Push to `staging` branch | Automatic |
| Production | Manual workflow dispatch | Required |

## Pipeline Structure

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Build     │────▶│   Deploy    │────▶│   Verify    │
│  Lambdas    │     │ Terraform   │     │   Health    │
└─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Build     │────▶│  Deploy S3  │────▶│ Invalidate  │
│  Frontend   │     │   + Assets  │     │ CloudFront  │
└─────────────┘     └─────────────┘     └─────────────┘
```

## GitHub Actions Workflows

### deploy-dev.yml

**Trigger**: Push to `dev` branch

```yaml
name: Deploy to Dev

on:
  push:
    branches: [dev]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build Lambda packages
        run: |
          cd chat-api/backend
          ./scripts/build_layer.sh
          ./scripts/build_lambdas.sh

      - name: Deploy infrastructure
        run: |
          cd chat-api/terraform/environments/dev
          terraform init
          terraform apply -auto-approve

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build

      - name: Deploy to S3
        run: |
          aws s3 sync frontend/dist s3://$BUCKET_NAME

      - name: Invalidate CloudFront
        run: |
          aws cloudfront create-invalidation \
            --distribution-id $CF_DISTRIBUTION \
            --paths "/*"
```

### deploy-staging.yml

Similar to dev with staging-specific configuration.

### deploy-prod.yml

**Trigger**: Manual workflow dispatch with approval

```yaml
name: Deploy to Production

on:
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # Requires approval
    steps:
      # Same steps with production secrets
```

## Lambda Build Process

### 1. Build Dependencies Layer

```bash
./scripts/build_layer.sh
```

Creates `dependencies-layer.zip` with Python packages.

### 2. Build Lambda Packages

```bash
./scripts/build_lambdas.sh
```

Creates individual `.zip` files for each handler.

### Output Structure

```
chat-api/backend/build/
├── dependencies-layer.zip
├── chat_http_handler.zip
├── chat_processor.zip
├── websocket_connect.zip
├── websocket_message.zip
├── websocket_disconnect.zip
├── auth_callback.zip
├── auth_verify.zip
├── conversations_handler.zip
└── search_handler.zip
```

## Terraform Deployment

### Standard Workflow

```bash
cd chat-api/terraform/environments/dev

# Initialize
terraform init

# Validate
terraform validate

# Plan
terraform plan -out=tfplan

# Apply
terraform apply tfplan
```

### CI/CD Workflow

In CI/CD, use `-auto-approve` with caution:

```bash
terraform apply -auto-approve
```

## Frontend Deployment

### 1. Build Production Bundle

```bash
cd frontend
npm ci
npm run build
```

### 2. Deploy to S3

```bash
aws s3 sync dist/ s3://$BUCKET_NAME \
  --delete \
  --cache-control "max-age=31536000"
```

### 3. Invalidate CloudFront

```bash
aws cloudfront create-invalidation \
  --distribution-id $CF_DISTRIBUTION \
  --paths "/*"
```

## Environment Variables

### GitHub Secrets

| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | AWS credentials |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials |
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `JWT_SECRET` | JWT signing secret |

### Environment-Specific Variables

Stored in GitHub Environments:

- `dev`: Development configuration
- `staging`: Staging configuration
- `production`: Production configuration (with approval)

## Rollback Procedures

### Terraform Rollback

```bash
# View state history
terraform state list

# Revert to previous state
terraform apply -target=module.lambda
```

### Lambda Rollback

Use AWS CLI to deploy previous version:

```bash
aws lambda update-function-code \
  --function-name buffett-chat-api-dev-chat-http \
  --s3-bucket $LAMBDA_BUCKET \
  --s3-key previous/chat_http_handler.zip
```

### Frontend Rollback

Deploy previous build from S3:

```bash
aws s3 sync s3://$BUCKET_NAME-backup s3://$BUCKET_NAME
aws cloudfront create-invalidation \
  --distribution-id $CF_DISTRIBUTION \
  --paths "/*"
```

## Monitoring Deployments

### CloudWatch Logs

Monitor Lambda logs after deployment:

```bash
aws logs tail /aws/lambda/buffett-chat-api-dev-chat-http --follow
```

### Health Checks

Verify deployment health:

```bash
curl https://api-dev.your-domain.com/health
```

## Best Practices

1. **Always test in dev first** before promoting to staging/prod
2. **Use Terraform plan** to review changes before applying
3. **Monitor CloudWatch** after deployments for errors
4. **Keep rollback artifacts** for quick recovery
5. **Use GitHub Environment protection** for production
