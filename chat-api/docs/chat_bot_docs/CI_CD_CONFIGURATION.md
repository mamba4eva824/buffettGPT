# CI/CD Pipeline Configuration Guide

## Overview

This document describes the end-to-end CI/CD pipeline configuration for BuffettGPT staging environment deployment using GitHub Actions, Terraform, and AWS services.

## Architecture

```
┌─────────────────┐
│  GitHub Push    │
│   to main       │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│        GitHub Actions Workflow              │
│     (.github/workflows/deploy-staging.yml)  │
└────────┬────────────────────────────────────┘
         │
         ├──────────────────────────────────┐
         │                                  │
         ▼                                  ▼
┌─────────────────┐              ┌──────────────────┐
│ Backend Build   │              │ Infrastructure   │
│  (Python/Zip)   │              │   (Terraform)    │
└────────┬────────┘              └────────┬─────────┘
         │                                │
         │                                ├─→ Lambda Functions
         │                                ├─→ API Gateway
         │                                ├─→ DynamoDB Tables
         │                                ├─→ CloudFront + S3
         │                                └─→ Bedrock Agent
         │
         ▼
┌─────────────────────────────────────────────┐
│           Frontend Build & Deploy            │
│  1. Build React/Vite with staging config     │
│  2. Sync to S3 with cache headers           │
│  3. Invalidate CloudFront cache             │
└─────────────────────────────────────────────┘
```

## Pipeline Components

### 1. Trigger Configuration

**File:** `.github/workflows/deploy-staging.yml`

```yaml
on:
  push:
    branches:
      - main
  workflow_dispatch:
```

- **Automatic**: Triggers on every push to `main` branch
- **Manual**: Can be triggered via GitHub Actions UI

### 2. Environment Variables

```yaml
env:
  AWS_REGION: us-east-1
  ENVIRONMENT: staging
  NODE_VERSION: 18
  PYTHON_VERSION: 3.11
```

### 3. Required GitHub Secrets

#### AWS Credentials
- `AWS_ACCESS_KEY_ID` - IAM user access key for Terraform/AWS CLI
- `AWS_SECRET_ACCESS_KEY` - IAM user secret key

#### Google OAuth
- `GOOGLE_CLIENT_ID` - Google OAuth client ID (used in frontend)
- `GOOGLE_CLIENT_SECRET` - Google OAuth client secret (stored in AWS Secrets Manager)

#### Application Secrets
- `JWT_SECRET` - JWT signing secret for authentication tokens
- `PINECONE_API_KEY` - Vector database API key for Bedrock knowledge base

#### Monitoring
- `ALERT_EMAIL` - Email for CloudWatch alerts (optional)

#### CloudFront Deployment
- `CLOUDFRONT_DISTRIBUTION_ID` - CloudFront distribution ID (E35BL8R2LQL183)
- `CLOUDFRONT_URL` - CloudFront URL (https://d2xq0qjqddoyoh.cloudfront.net)
- `S3_FRONTEND_BUCKET` - S3 bucket name (buffett-staging-frontend)

## Job Breakdown

### Job 1: Build Backend Lambda Functions

**Purpose**: Package Python Lambda functions with dependencies

**Steps:**
1. **Checkout code** - Clone repository
2. **Setup Python 3.11** - Install Python runtime
3. **Build Lambda Layer**
   ```bash
   cd chat-api/backend
   ./scripts/build_layer.sh
   ```
   - Creates shared dependencies layer
   - Reduces individual function package sizes
   - Output: `layer.zip`

4. **Build Lambda packages**
   ```bash
   ./scripts/build_lambdas.sh
   ```
   - Packages each Lambda function
   - Excludes layer dependencies (already in layer)
   - Output: Individual `.zip` files in `build/`

5. **Upload Lambda packages**
   - Stores as GitHub Actions artifacts
   - Available to downstream jobs
   - Retention: 1 day

**Artifacts Created:**
- `lambda-packages` (all `.zip` files from `build/`)

---

### Job 2: Deploy Infrastructure with Terraform

**Purpose**: Deploy all AWS infrastructure using Terraform

**Depends On:** `build-backend`

**Steps:**

1. **Download Lambda packages**
   - Retrieves artifacts from build job
   - Places in correct directory structure

2. **Configure AWS credentials**
   ```yaml
   aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
   aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
   aws-region: us-east-1
   ```

3. **Create/Update Secrets in AWS Secrets Manager**
   ```bash
   aws secretsmanager create-secret --name staging/google_oauth_client_secret
   aws secretsmanager create-secret --name staging/jwt_secret
   ```
   - Stores sensitive values outside Terraform state
   - Uses `ignore_changes` lifecycle to prevent updates
   - Protected with `prevent_destroy` lifecycle

4. **Setup Terraform**
   - Version: `1.9.1` (matches local development)
   - Wrapper: disabled (for output capture)

5. **Terraform Init**
   ```bash
   terraform init -backend-config=backend.hcl
   ```
   - Initializes S3 backend for state storage
   - Downloads required providers:
     - AWS provider (~> 5.0)
   - Loads modules (API Gateway, Lambda, DynamoDB, etc.)

6. **Terraform Validate**
   ```bash
   terraform validate
   ```
   - Validates syntax and configuration
   - Checks module references
   - Ensures required variables are defined

7. **Terraform Plan**
   ```bash
   terraform plan -var-file=terraform.tfvars -out=tfplan
   ```
   - Creates execution plan
   - Shows resources to create/update/destroy
   - Saves plan to file for apply step

8. **Terraform Apply**
   ```bash
   terraform apply tfplan
   ```
   - Executes the plan
   - Creates/updates AWS resources:
     - **Core Module**: KMS keys, IAM roles, SQS queues
     - **DynamoDB Module**: 5 tables (sessions, messages, conversations, connections, rate limits)
     - **Lambda Module**: 6 functions + 1 shared layer
     - **API Gateway Module**: HTTP API + WebSocket API
     - **Auth Module**: OAuth Lambda functions
     - **CloudFront Module**: Distribution + S3 bucket
     - **Bedrock Module**: Agent, Knowledge Base, Guardrails
   - Import existing S3 bucket (if needed)

9. **Get Terraform Outputs**
   ```bash
   terraform output -json > outputs.json
   ```
   - Captures API endpoints for frontend build
   - Stored as environment variables for next job

**Outputs Used by Frontend:**
- `http_api_endpoint` - REST API URL
- `websocket_api_endpoint` - WebSocket API URL

---

### Job 3: Build Frontend

**Purpose**: Build React/Vite application with staging configuration

**Depends On:** `deploy-infrastructure`

**Steps:**

1. **Checkout code**

2. **Setup Node.js 18**
   - No npm caching (package-lock.json not tracked)

3. **Install dependencies**
   ```bash
   cd frontend
   npm install
   ```

4. **Create staging environment file**
   ```bash
   cat > .env.staging << EOF
   VITE_REST_API_URL=${{ needs.deploy-infrastructure.outputs.http_api_endpoint }}
   VITE_WEBSOCKET_URL=${{ needs.deploy-infrastructure.outputs.websocket_api_endpoint }}
   VITE_ENVIRONMENT=staging
   VITE_ENABLE_DEBUG_LOGS=true
   VITE_GOOGLE_CLIENT_ID=${{ secrets.GOOGLE_CLIENT_ID }}
   EOF
   ```
   - Injects API endpoints from Terraform outputs
   - Includes Google Client ID for OAuth
   - Environment-specific flags

5. **Build frontend**
   ```bash
   npm run build -- --mode staging
   ```
   - Vite reads `.env.staging`
   - Bundles JavaScript/CSS
   - Optimizes assets
   - Output: `frontend/dist/`

6. **Upload frontend artifacts**
   - Stores built files for deployment job
   - Contains: HTML, JS, CSS, images

**Artifacts Created:**
- `frontend-dist` (contents of `dist/`)

---

### Job 4: Deploy Frontend to S3 + CloudFront

**Purpose**: Deploy built frontend to S3 and invalidate CloudFront cache

**Depends On:** `build-frontend`

**Steps:**

1. **Download frontend artifacts**
   - Retrieves from build job
   - Restores to `frontend/dist/`

2. **Configure AWS credentials**

3. **Sync HTML files to S3 (no cache)**
   ```bash
   aws s3 sync frontend/dist s3://buffett-staging-frontend/ \
     --exclude "*" \
     --include "*.html" \
     --cache-control "public, max-age=0, must-revalidate" \
     --metadata-directive REPLACE
   ```
   - HTML files always fresh (no browser caching)
   - Ensures users get latest SPA

4. **Sync static assets to S3 (long-term cache)**
   ```bash
   aws s3 sync frontend/dist s3://buffett-staging-frontend/ \
     --exclude "*.html" \
     --cache-control "public, max-age=31536000, immutable" \
     --metadata-directive REPLACE
   ```
   - JavaScript, CSS, images cached for 1 year
   - Vite uses content hashes in filenames
   - Immutable ensures CDN respects cache

5. **Invalidate CloudFront cache**
   ```bash
   aws cloudfront create-invalidation \
     --distribution-id E35BL8R2LQL183 \
     --paths "/*"
   ```
   - Clears CloudFront edge cache
   - Ensures new content served immediately
   - Takes 1-2 minutes to complete

6. **Print deployment URL**
   - Outputs: https://d2xq0qjqddoyoh.cloudfront.net

---

### Job 5: Deployment Summary

**Purpose**: Print deployment information

**Depends On:** All previous jobs

**Steps:**
1. **Print deployment summary**
   - Environment: staging
   - HTTP API endpoint
   - WebSocket endpoint
   - Frontend URL
   - Next steps for testing

## Terraform State Management

### Backend Configuration

**File:** `chat-api/terraform/environments/staging/backend.hcl`

```hcl
bucket         = "buffett-terraform-state"
key            = "staging/terraform.tfstate"
region         = "us-east-1"
encrypt        = true
dynamodb_table = "terraform-state-lock"
```

### State Locking

- **DynamoDB Table**: `terraform-state-lock`
- **Purpose**: Prevents concurrent Terraform runs
- **Consistency**: Ensures state file integrity

### State Encryption

- **S3 Encryption**: AES-256
- **Access**: IAM user credentials only
- **Versioning**: Enabled for state recovery

## Deployment Workflow

### Typical Deployment Timeline

```
Push to main
    │
    ├─→ [0:00] Build Backend Lambda Functions (14-20s)
    │
    ├─→ [0:20] Deploy Infrastructure with Terraform (1m30s-1m50s)
    │      │
    │      ├─→ Secrets Manager update (2s)
    │      ├─→ Terraform init (5s)
    │      ├─→ Terraform plan (15s)
    │      ├─→ Terraform apply (60-90s)
    │      │     ├─→ Lambda functions
    │      │     ├─→ API Gateway routes
    │      │     ├─→ DynamoDB tables
    │      │     ├─→ CloudFront distribution
    │      │     └─→ Bedrock agent
    │      └─→ Capture outputs (1s)
    │
    ├─→ [2:00] Build Frontend (40-60s)
    │      │
    │      ├─→ npm install (25s)
    │      ├─→ Create .env.staging (1s)
    │      └─→ Vite build (15s)
    │
    ├─→ [3:00] Deploy Frontend to S3 + CloudFront (13-16s)
    │      │
    │      ├─→ Download artifacts (2s)
    │      ├─→ Sync HTML to S3 (2s)
    │      ├─→ Sync assets to S3 (3s)
    │      └─→ CloudFront invalidation (5s)
    │
    └─→ [3:15] Deployment Summary (2-4s)

Total: ~3 minutes 15 seconds
```

## Infrastructure Components Deployed

### 1. Core Infrastructure (`core` module)

**KMS Encryption**
- Key for encrypting sensitive data
- Used by: DynamoDB, Secrets Manager, SQS

**IAM Roles**
- Lambda execution role with policies for:
  - DynamoDB access
  - SQS send/receive
  - Bedrock invoke
  - CloudWatch logs
  - Secrets Manager read

**SQS Queues**
- `chat-processing-queue` - Main message queue
- `chat-dlq` - Dead letter queue for failures

### 2. DynamoDB Tables (`dynamodb` module)

1. **chat_sessions** - User session data
2. **chat_messages** - Message history
3. **conversations** - Conversation metadata
4. **websocket_connections** - Active WebSocket connections
5. **enhanced_rate_limits** - Rate limiting data
6. **anonymous_sessions** - Anonymous user sessions

**Configuration:**
- Billing mode: PAY_PER_REQUEST (on-demand)
- Encryption: KMS customer-managed key
- Point-in-time recovery: Enabled
- Deletion protection: Disabled (staging)

### 3. Lambda Functions (`lambda` module)

**Functions:**
1. `websocket_connect` - WebSocket connection handler
2. `websocket_disconnect` - WebSocket disconnect handler
3. `websocket_message` - WebSocket message handler
4. `chat_processor` - SQS-triggered chat processing
5. `chat_http_handler` - REST API chat endpoint
6. `conversations_handler` - Conversation management

**Shared Layer:**
- Dependencies: boto3, requests, etc.
- Reduces deployment package sizes
- Faster cold starts

**Configuration:**
- Runtime: Python 3.11
- Memory: 512MB-1024MB
- Timeout: 30s-900s (varies by function)
- Reserved concurrency: 5 (chat_processor)
- Environment variables: 15+ (DB tables, API endpoints, Bedrock config)

### 4. API Gateway (`api-gateway` module)

**HTTP API:**
- Endpoint: `https://vxz4rbeu79.execute-api.us-east-1.amazonaws.com/staging`
- Routes:
  - `POST /chat` - Send chat message
  - `GET /conversations` - List conversations
  - `POST /conversations` - Create conversation
  - `DELETE /conversations/{id}` - Delete conversation
  - `GET /auth/callback` - OAuth callback

**WebSocket API:**
- Endpoint: `wss://zdff3lht2g.execute-api.us-east-1.amazonaws.com/staging`
- Routes:
  - `$connect` - Connection handler
  - `$disconnect` - Disconnect handler
  - `$default` - Message handler

**CORS Configuration:**
- Allowed origins: CloudFront URL + localhost (dev)
- Allowed methods: GET, POST, DELETE, OPTIONS
- Allowed headers: Content-Type, Authorization
- Max age: 300s

### 5. Authentication (`auth` module)

**Functions:**
- `auth_verify` - JWT verification authorizer
- `auth_callback` - Google OAuth callback handler

**OAuth Flow:**
1. User clicks "Sign in with Google"
2. Redirected to Google OAuth
3. Google redirects to `/auth/callback`
4. Lambda verifies token, creates user, returns JWT
5. Frontend stores JWT in localStorage

### 6. CloudFront + S3 (`cloudfront-static-site` module)

**S3 Bucket:**
- Name: `buffett-staging-frontend`
- Versioning: Enabled
- Encryption: AES-256
- Public access: Blocked (OAC only)

**CloudFront Distribution:**
- ID: `E35BL8R2LQL183`
- Domain: `d2xq0qjqddoyoh.cloudfront.net`
- Origin Access Control: Enabled
- HTTP/2 and HTTP/3: Enabled
- Price class: PriceClass_100 (US, Canada, Europe)
- Default root object: `index.html`
- SPA routing: 404/403 → index.html

**Cache Policies:**
- Default: AWS CachingOptimized
- Origin request: CORS-S3Origin

### 7. AWS Bedrock (`bedrock` module)

**Agent:**
- Name: buffett-chat-staging-agent
- Model: Claude 3.5 Sonnet
- Instruction: Warren Buffett-style investment advice

**Knowledge Base:**
- Name: buffett-embeddings-staging
- Vector store: Pinecone (1024 dimensions)
- Embedding model: Amazon Titan Embeddings V2
- Data source: S3 bucket (buffet-training-data)
- Chunking: Semantic (300 tokens/chunk)

**Guardrails:**
- Content filtering: Enabled
- Topic filtering: Financial advice only
- Word filtering: Enabled
- Contextual grounding: Enabled

## Testing the Deployment

### 1. Backend Health Check

```bash
curl https://vxz4rbeu79.execute-api.us-east-1.amazonaws.com/staging/health
```

### 2. Frontend Access

Open browser to: https://d2xq0qjqddoyoh.cloudfront.net

### 3. WebSocket Connection Test

```javascript
const ws = new WebSocket('wss://zdff3lht2g.execute-api.us-east-1.amazonaws.com/staging');
ws.onopen = () => console.log('Connected');
ws.onmessage = (e) => console.log('Message:', e.data);
```

### 4. OAuth Flow Test

1. Click "Sign in with Google"
2. Authorize application
3. Should redirect back with JWT token
4. User info displayed in UI

## Monitoring and Logging

### CloudWatch Log Groups

- `/aws/lambda/buffett-staging-websocket-connect`
- `/aws/lambda/buffett-staging-websocket-message`
- `/aws/lambda/buffett-staging-chat-processor`
- `/aws/lambda/buffett-staging-chat-http-handler`
- `/aws/lambda/buffett-staging-auth-verify`
- `/aws/lambda/buffett-staging-auth-callback`

**Retention:** 14 days (staging)

### Viewing Logs

```bash
# Tail chat processor logs
aws logs tail /aws/lambda/buffett-staging-chat-processor --follow

# View specific time range
aws logs tail /aws/lambda/buffett-staging-chat-processor \
  --since 1h --format short
```

### GitHub Actions Logs

View deployment logs:
```bash
gh run list --workflow=deploy-staging.yml --limit 5
gh run view <run-id> --log
```

## Rollback Procedure

### 1. Revert Git Commit

```bash
git revert <commit-hash>
git push origin main
```
- Triggers automatic redeployment

### 2. Manual Terraform Rollback

```bash
cd chat-api/terraform/environments/staging
terraform plan -var-file=terraform.tfvars
terraform apply -auto-approve
```

### 3. Frontend-Only Rollback

Re-upload previous frontend build:
```bash
aws s3 sync ./previous-dist s3://buffett-staging-frontend/ --delete
aws cloudfront create-invalidation --distribution-id E35BL8R2LQL183 --paths "/*"
```

## Security Considerations

### Secrets Management

1. **GitHub Secrets** - Encrypted at rest
2. **AWS Secrets Manager** - Runtime secrets (OAuth, JWT)
3. **Terraform Variables** - Never committed to repo
4. **Environment Variables** - Injected at build time

### IAM Permissions

- Least privilege principle
- Separate roles for Lambda, Terraform, CI/CD
- No hardcoded credentials in code

### Network Security

- API Gateway: CORS restrictions
- Lambda: No public internet access (private subnet optional)
- DynamoDB: Encrypted at rest with KMS
- CloudFront: HTTPS only

## Cost Optimization

### Current Configuration

**Free Tier Usage:**
- Lambda: 1M requests/month, 400K GB-seconds
- API Gateway: 1M requests/month
- CloudFront: 1TB data transfer/month (first year)
- DynamoDB: 25GB storage, 25 RCU/WCU

**On-Demand Pricing:**
- DynamoDB: PAY_PER_REQUEST (billed per request)
- Lambda: Billed per invocation + duration
- S3: Standard storage (~$0.023/GB)

### Estimated Monthly Cost (Staging)

- Lambda: $0-5 (within free tier)
- API Gateway: $0-3 (within free tier)
- DynamoDB: $0-10 (low usage)
- CloudFront: $0-5 (first year free)
- S3: $0.50-2
- Bedrock: Pay per request (~$0.03/1K tokens)

**Total: $10-25/month** (varies with usage)

## Troubleshooting

See [CI_CD_TROUBLESHOOTING.md](./CI_CD_TROUBLESHOOTING.md) for detailed error resolutions.

## Maintenance

### Regular Tasks

1. **Update Dependencies**
   - Frontend: `npm update`
   - Backend: Update `requirements.txt`

2. **Rotate Secrets**
   - JWT secret: Every 90 days
   - OAuth credentials: As needed

3. **Review Logs**
   - Check for errors weekly
   - Monitor rate limiting patterns

4. **Cost Analysis**
   - Review AWS Cost Explorer monthly
   - Optimize underused resources

### Terraform State Maintenance

```bash
# Lock state file
terraform force-unlock <lock-id>

# Refresh state from AWS
terraform refresh

# Remove resource from state (manual deletion)
terraform state rm <resource>
```

## Additional Resources

- [Terraform AWS Provider Docs](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [AWS Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [CloudFront Documentation](https://docs.aws.amazon.com/cloudfront/)
