# Staging Environment Deployment Guide

## Overview
This document describes the staging environment setup for BuffettGPT chat application, designed for friends and family testing without requiring a custom domain.

## What Was Created

### 1. Terraform Configuration
**Location**: `chat-api/terraform/environments/staging/`

Files created:
- `main.tf` - Main infrastructure configuration
- `variables.tf` - Variable definitions with staging-specific defaults
- `backend.hcl` - S3 backend configuration for Terraform state
- `outputs.tf` - Outputs for API endpoints and resource IDs
- `terraform.tfvars.example` - Template for sensitive values

**Key Differences from Dev**:
- Environment: `staging`
- LOG_LEVEL: `INFO` (less verbose than dev's DEBUG)
- Log Retention: 14 days (vs 7 days in dev)
- PITR Enabled: `true` (point-in-time recovery for data safety)
- Reserved Concurrency: 5 (vs 2 in dev, to support multiple testers)
- Authentication: Enabled (required for friends & family)
- Monitoring: Enabled

### 2. GitHub Actions Workflow
**Location**: `.github/workflows/deploy-staging.yml`

**Workflow Jobs**:
1. **build-backend**: Builds Lambda layer and function packages
2. **deploy-infrastructure**: Deploys AWS infrastructure with Terraform
3. **build-frontend**: Builds React frontend with staging API endpoints
4. **deployment-summary**: Prints deployment information

**Secrets Management**:
The workflow creates staging-specific secrets in AWS Secrets Manager:
- `buffett-staging-google-oauth` - Google OAuth credentials
- `buffett-staging-jwt-secret` - JWT signing key
- `buffett-staging-pinecone-api-key` - Pinecone API key

These are populated from GitHub Secrets during deployment.

### 3. Frontend Configuration
**Location**: `frontend/.env.staging`

The GitHub Actions workflow dynamically creates this file with actual API endpoints from Terraform outputs during the build process.

## GitHub Secrets Required

The following secrets must be configured in GitHub (Settings → Secrets and variables → Actions):

| Secret Name | Description | Source |
|-------------|-------------|--------|
| `AWS_ACCESS_KEY_ID` | AWS credentials | AWS IAM |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials | AWS IAM |
| `GOOGLE_CLIENT_ID` | Google OAuth | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | Google OAuth | Google Cloud Console |
| `JWT_SECRET` | JWT signing key | Generate: `openssl rand -base64 48` |
| `PINECONE_API_KEY` | Pinecone vector DB | Pinecone dashboard |
| `BEDROCK_AGENT_ID` | Bedrock agent | From dev: `QTFYZ6BBSE` |
| `BEDROCK_AGENT_ALIAS` | Bedrock alias | From dev: `WNW1OMPUEW` |
| `ALERT_EMAIL` (optional) | Email for alerts | Your email |

## Deployment Process

### Initial Deployment

1. **Ensure all GitHub secrets are configured** (see table above)

2. **Push to main branch** (or trigger manually):
   ```bash
   git add .
   git commit -m "feat: add staging environment configuration"
   git push origin main
   ```

3. **Monitor GitHub Actions**:
   - Go to: https://github.com/YOUR_USERNAME/buffett_chat_api/actions
   - Watch the "Deploy to Staging" workflow
   - Check for any errors in each job

4. **Retrieve API Endpoints**:
   After successful deployment, endpoints are shown in the "deployment-summary" job output.

### Manual Deployment (Local)

If you need to deploy manually from your local machine:

```bash
# Navigate to staging directory
cd chat-api/terraform/environments/staging

# Initialize Terraform
terraform init -backend-config=backend.hcl

# Create a terraform.tfvars file (use terraform.tfvars.example as template)
# Fill in all required values

# Plan deployment
terraform plan

# Apply deployment
terraform apply
```

## Infrastructure Details

### Resources Created

**Compute**:
- 7+ Lambda functions (chat handlers, WebSocket handlers, auth handlers)
- Lambda Layer (shared dependencies)

**API**:
- HTTP API Gateway (REST endpoints)
- WebSocket API Gateway (real-time chat)

**Storage**:
- DynamoDB tables:
  - `buffett-staging-conversations` - Conversation metadata
  - `buffett-staging-chat-messages` - Message history
  - `buffett-staging-chat-sessions` - Session tracking
  - `buffett-staging-websocket-connections` - WebSocket connections
  - `buffett-staging-enhanced-rate-limits` - Rate limiting
  - `buffett-staging-anonymous-sessions` - Anonymous user sessions

**AI/ML**:
- Bedrock Agent (reuses dev agent for now)
- Bedrock Knowledge Base (reuses dev knowledge base)

**Security**:
- KMS keys for encryption
- IAM roles and policies
- AWS Secrets Manager secrets

**Monitoring**:
- CloudWatch Log Groups (14-day retention)
- CloudWatch Alarms (if email configured)

### Cost Estimates

**Monthly costs during active testing** (100 chats/day):
- Lambda: ~$5-10
- API Gateway: ~$0.35
- DynamoDB: ~$3-5
- Bedrock (Claude Haiku): ~$20-40
- **Total**: ~$30-55/month

**Idle costs** (no usage):
- DynamoDB: ~$1-2/month
- **Total**: ~$1-2/month

## Testing the Deployment

### 1. Verify Infrastructure

```bash
# Check API health endpoint
curl https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/staging/health

# Expected response: {"status": "healthy", "environment": "staging"}
```

### 2. Test WebSocket Connection

Open browser console and test WebSocket:
```javascript
const ws = new WebSocket('wss://YOUR_WS_API_ID.execute-api.us-east-1.amazonaws.com/staging');
ws.onopen = () => console.log('Connected!');
ws.onmessage = (event) => console.log('Message:', event.data);
```

### 3. Check CloudWatch Logs

```bash
# View Lambda logs
aws logs tail /aws/lambda/buffett-staging-chat-http-handler --follow

# View all staging logs
aws logs tail --filter-pattern "staging" --follow
```

## Sharing with Friends & Family

### Access Instructions Template

```markdown
# BuffettGPT Chat - Staging Access

Hi! You've been invited to test BuffettGPT Chat.

## How to Access
1. Visit: [CloudFront URL will be added once frontend deployment is complete]
2. Click "Sign in with Google"
3. Use your Google account to authenticate
4. Start chatting with the AI financial advisor!

## What to Test
- Send various investment and financial planning questions
- Test conversation history
- Try switching between conversations
- Report any bugs or unexpected behavior

## Known Issues
- Using AWS-provided URLs (no custom domain yet)
- May have occasional latency
- This is a test environment - data may be reset

## Feedback
Please report issues or feedback to: [YOUR_EMAIL]

Thank you for helping test BuffettGPT! 🚀
```

## Monitoring & Maintenance

### CloudWatch Dashboards

Monitor your staging environment:
1. Go to AWS Console → CloudWatch → Dashboards
2. Look for `buffett-staging-dashboard` (if monitoring is enabled)

### Cost Monitoring

```bash
# Check current month costs
aws ce get-cost-and-usage \
  --time-period Start=2024-01-01,End=2024-01-31 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://cost-filter.json
```

### Updating the Staging Environment

To deploy updates:
```bash
# Make changes to code
git add .
git commit -m "feat: your update description"
git push origin main

# GitHub Actions automatically deploys to staging
```

## Rollback Procedure

If deployment fails or causes issues:

### Option 1: Revert via Git
```bash
git revert HEAD
git push origin main
# GitHub Actions deploys previous version
```

### Option 2: Manual Terraform Rollback
```bash
cd chat-api/terraform/environments/staging
terraform plan -destroy
terraform destroy  # Only if you want to tear down completely
```

### Option 3: Restore from Terraform State
```bash
# Terraform state is versioned in S3
aws s3 ls s3://buffett-chat-terraform-state-430118826061/staging/ --recursive

# Download previous state
aws s3 cp s3://buffett-chat-terraform-state-430118826061/staging/terraform.tfstate terraform.tfstate.backup
```

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| GitHub Actions fails on Terraform | Check AWS credentials in GitHub Secrets |
| Lambda timeout errors | Check Lambda logs in CloudWatch |
| WebSocket connection fails | Verify API Gateway WebSocket endpoint is correct |
| Frontend can't connect | Check CORS configuration in API Gateway |
| Bedrock errors | Verify Bedrock agent ID and alias are correct |

### Debug Commands

```bash
# List all staging Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `staging`)].FunctionName'

# Check DynamoDB tables
aws dynamodb list-tables --query 'TableNames[?contains(@, `staging`)]'

# View recent Lambda errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/buffett-staging-chat-http-handler \
  --filter-pattern "ERROR"
```

## Next Steps

After staging is stable:

1. **Add Frontend S3 + CloudFront deployment** (TODO in GitHub Actions)
2. **Test with friends and family for 2-4 weeks**
3. **Collect feedback and fix bugs**
4. **Monitor costs and performance**
5. **Create production environment** (once staging is validated)
6. **Purchase custom domain** (for production)
7. **Set up Route 53 DNS** (for custom domain)

## Support

For issues or questions:
- Check CloudWatch logs first
- Review GitHub Actions workflow output
- Check AWS Console for resource status
- Contact: [YOUR_EMAIL]