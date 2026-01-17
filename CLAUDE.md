# BuffettGPT - AI Assistant Documentation

## Project Overview

BuffettGPT is a full-stack serverless financial chat application built on AWS. It provides a Warren Buffett-themed AI advisor that answers investment and financial planning questions using Amazon Bedrock (Claude Haiku) with knowledge bases and guardrails.

---

## Repository Structure

```
buffettGPT/
├── chat-api/                          # Backend API and infrastructure
│   ├── backend/                       # Lambda functions and utilities
│   │   ├── src/
│   │   │   ├── handlers/              # 9 Lambda handler functions
│   │   │   └── utils/                 # Utilities (rate limiting, logging)
│   │   ├── layer/                     # Lambda layer dependencies
│   │   ├── scripts/                   # Build scripts
│   │   ├── tests/                     # Python tests
│   │   └── build/                     # Generated Lambda .zip files
│   ├── terraform/                     # Infrastructure as Code
│   │   ├── backend-setup/             # Remote state backend
│   │   ├── environments/              # Environment configs (dev/staging/prod)
│   │   └── modules/                   # Reusable Terraform modules
│   ├── scripts/                       # Deployment scripts
│   └── events/                        # Sample Lambda events
├── frontend/                          # React + Vite frontend
│   ├── src/
│   │   ├── components/                # React components
│   │   ├── hooks/                     # Custom hooks
│   │   ├── api/                       # API client utilities
│   │   └── utils/                     # Logger and helpers
│   └── public/                        # Static assets
├── search-api/                        # Experimental search APIs
│   ├── search.py                      # Perplexity API integration
│   └── model_comparison.py            # Model comparison tools
└── .github/workflows/                 # CI/CD pipelines
```

---

## Technology Stack

### Backend
- **Runtime**: Python 3.11
- **Cloud**: AWS Lambda, API Gateway (HTTP + WebSocket), DynamoDB, SQS
- **AI**: Amazon Bedrock (Claude Haiku), Knowledge Bases, Guardrails
- **Auth**: Google OAuth, JWT tokens
- **IaC**: Terraform 1.9.1+

### Frontend
- **Framework**: React 18.2.0
- **Build Tool**: Vite 5.0.8
- **Styling**: Tailwind CSS 3.3.6
- **Auth**: Google OAuth

### Infrastructure
- **State Management**: S3 backend with DynamoDB locking
- **Encryption**: KMS for all sensitive data
- **CDN**: CloudFront for static site delivery

---

## Lambda Functions

Located in `chat-api/backend/src/handlers/`:

| Handler | Purpose |
|---------|---------|
| `chat_http_handler.py` | HTTP endpoint for chat requests (POST /chat, GET /health) |
| `chat_processor.py` | Async SQS consumer, processes with Bedrock agent |
| `websocket_connect.py` | WebSocket connection handler |
| `websocket_message.py` | WebSocket message handler, enqueues to SQS |
| `websocket_disconnect.py` | WebSocket disconnection cleanup |
| `auth_callback.py` | Google OAuth callback, issues JWT tokens |
| `auth_verify.py` | JWT verification authorizer |
| `conversations_handler.py` | Chat history management (GET /conversations) |
| `search_handler.py` | Experimental search functionality |

---

## Terraform Modules

Located in `chat-api/terraform/modules/`:

| Module | Purpose |
|--------|---------|
| `core` | KMS encryption, IAM roles, SQS queues |
| `dynamodb` | 8 DynamoDB tables (sessions, messages, connections, etc.) |
| `lambda` | Lambda function deployment with layers |
| `api-gateway` | HTTP and WebSocket API configuration |
| `auth` | OAuth authentication infrastructure |
| `bedrock` | AI agent, knowledge base, guardrails |
| `cloudfront-static-site` | CDN and S3 static hosting |
| `rate-limiting` | Device fingerprinting and quotas |
| `monitoring` | CloudWatch dashboards and alerts |

---

## DynamoDB Tables

| Table | Purpose |
|-------|---------|
| `chat-sessions` | Session metadata with TTL |
| `chat-messages` | Message history |
| `conversations` | Conversation details |
| `websocket-connections` | Active WebSocket connections |
| `enhanced-rate-limits` | Device fingerprint rate limiting |
| `usage-tracking` | Monthly usage tracking |
| `anonymous-sessions` | Anonymous user sessions |
| `users` | User profile data |

---

## Development Workflows

### Backend Development

```bash
# Setup virtual environment
cd chat-api/backend
make venv
make dev-install

# Run tests
make test

# Build Lambda packages
./scripts/build_layer.sh
./scripts/build_lambdas.sh

# Test HTTP handler locally
make run-http
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev          # Start dev server on port 3000
npm run build        # Production build
npm run lint         # ESLint (0 warnings policy)
```

### Terraform Deployment

```bash
cd chat-api/terraform/environments/dev

# Initialize (first time or after module changes)
terraform init

# Validate configuration
terraform validate

# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan
```

---

## Environment Configuration

### Backend Environment Variables
Key variables set by Terraform and CI/CD:
- `ENVIRONMENT` - dev/staging/prod
- `BEDROCK_AGENT_ID` - Bedrock agent identifier
- `BEDROCK_AGENT_ALIAS` - Agent alias name
- `ANONYMOUS_MONTHLY_LIMIT` - Rate limit for anonymous users (default: 5)
- `AUTHENTICATED_MONTHLY_LIMIT` - Rate limit for authenticated users (default: 500)

### Frontend Environment Variables
- `VITE_WEBSOCKET_URL` - WebSocket API endpoint
- `VITE_REST_API_URL` - HTTP API endpoint
- `VITE_GOOGLE_CLIENT_ID` - OAuth client ID
- `VITE_ENVIRONMENT` - Current environment

---

## CI/CD Pipelines

Three GitHub Actions workflows in `.github/workflows/`:

### deploy-dev.yml (auto on push to `dev` branch)
1. Build Lambda packages
2. Deploy infrastructure via Terraform
3. Build frontend with environment config
4. Deploy to S3 + invalidate CloudFront

### deploy-staging.yml (auto on push to `staging` branch)
Same structure as dev with staging-specific configuration.

### deploy-prod.yml (manual approval required)
Same structure with production secrets and GitHub environment approval.

---

## Code Conventions

### Naming
- **AWS Resources**: `{project-name}-{environment}-{resource-type}`
  - Example: `buffett-chat-api-dev-chat-sessions`
- **Terraform Variables**: `snake_case`
- **Environment Variables**: `UPPER_CASE`
- **Python/JS**: Standard language conventions

### Patterns
- **Error Handling**: Catch boto3 ClientError, use custom exceptions
- **Logging**: Environment-controlled log levels
- **Rate Limiting**: Device fingerprint (IP + User-Agent + CloudFront headers)
- **WebSocket**: FIFO message ordering via SQS

---

## Testing

### Python Tests
```bash
cd chat-api/backend
make test            # Run pytest
```

**Dependencies**: pytest, moto (AWS mocking), pytest-cov

### Frontend Linting
```bash
cd frontend
npm run lint         # ESLint with 0 warnings policy
```

---

## Secrets Management

Secrets are stored in AWS Secrets Manager:
- `buffett-{env}-google-oauth` - OAuth credentials
- `buffett-{env}-jwt-secret` - JWT signing secret
- `buffett-{env}-pinecone-api-key` - Vector DB API key

Never commit secrets to the repository. Use `.env.example` files as templates.

---

# MANDATORY DEPLOYMENT RULES

## CRITICAL: TERRAFORM DEPLOYMENT ENFORCEMENT

**ABSOLUTE RULE**: ALL infrastructure changes to dev environment MUST use Terraform.

### Required Terraform Workflow:
1. **Infrastructure as Code** - All changes must be in `.tf` files
2. **Plan before Apply** - Always run `terraform plan` first
3. **State Management** - Use remote state backend
4. **Validation** - Run `terraform validate` before deployment

### Prohibited Actions:
- Direct AWS console changes
- Manual resource creation
- Bypassing Terraform workflows
- Applying without planning

### Mandatory Commands:
```bash
cd chat-api/terraform/environments/dev
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

---

## LAMBDA PACKAGING RULES

**ABSOLUTE RULE**: ALL Lambda deployment packages (.zip files) MUST be placed in:
```
chat-api/backend/build/
```

### Lambda Build Requirements:
1. **Build Directory** - All .zip files go to `chat-api/backend/build/`
2. **Package Structure** - Maintain consistent packaging format
3. **Dependencies** - Lambda layer contains shared dependencies
4. **Cleanup** - Remove old builds before creating new ones

### Build Commands:
```bash
cd chat-api/backend
./scripts/build_layer.sh      # Build dependencies layer
./scripts/build_lambdas.sh    # Package all Lambda functions
```

### Expected Build Output:
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

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `chat-api/terraform/environments/dev/main.tf` | Dev environment root module |
| `chat-api/backend/src/handlers/*.py` | Lambda function handlers |
| `chat-api/backend/src/utils/*.py` | Shared utilities |
| `frontend/src/App.jsx` | Main React application |
| `frontend/src/auth.jsx` | Authentication logic |
| `.github/workflows/*.yml` | CI/CD pipeline definitions |

---

## Common Tasks

### Add a New Lambda Function
1. Create handler in `chat-api/backend/src/handlers/`
2. Add to `build_lambdas.sh` script
3. Define in `chat-api/terraform/modules/lambda/`
4. Add API Gateway route if needed
5. Run build and deploy

### Add a New DynamoDB Table
1. Add table definition in `chat-api/terraform/modules/dynamodb/main.tf`
2. Add output in `chat-api/terraform/modules/dynamodb/outputs.tf`
3. Update Lambda IAM policies if needed
4. Run `terraform plan` then `terraform apply`

### Update Bedrock Agent
1. Modify `chat-api/terraform/modules/bedrock/`
2. Update agent instructions or guardrails as needed
3. Deploy via Terraform

### Debug WebSocket Issues
1. Check CloudWatch logs for `websocket_connect`, `websocket_message`, `chat_processor`
2. Verify DynamoDB `websocket-connections` table
3. Check SQS queue metrics for message backlog
