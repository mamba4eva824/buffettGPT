# AWS Bedrock Agent Deployment Guide

## Overview
This guide documents the complete deployment process for AWS Bedrock agents with version management, including the challenges with AWS Bedrock's versioning system and our orchestration solution.

## Table of Contents
1. [Architecture Overview](#architecture-overview)
2. [The Version Management Challenge](#the-version-management-challenge)
3. [Deployment Components](#deployment-components)
4. [Step-by-Step Deployment](#step-by-step-deployment)
5. [Troubleshooting](#troubleshooting)
6. [Best Practices](#best-practices)

## Architecture Overview

### Components
- **AWS Bedrock Agent**: AI agent using Claude models for conversational AI
- **Pinecone Vector Store**: External vector database for knowledge base
- **AWS Lambda Functions**: Process chat messages and WebSocket connections
- **Terraform**: Infrastructure as code for resource management
- **Python Scripts**: Orchestration tools for version management

### Data Flow
```
User → API Gateway → Lambda → Bedrock Agent → Knowledge Base (Pinecone) → Response
```

## The Version Management Challenge

### AWS Bedrock Limitations
1. **Immutable Versions**: Once created, numbered versions (1, 2, 3...) cannot be modified
2. **DRAFT Version**: Only mutable version where changes can be made
3. **No Direct API**: AWS doesn't provide API to programmatically create numbered versions
4. **Manual Process**: Version creation requires AWS Console or prepare_agent operation

### Why This Matters
- Lambda functions reference agents via environment variables
- Aliases route traffic to specific versions
- Terraform can only manage DRAFT configuration
- Production deployments need stable, versioned configurations

## Deployment Components

### 1. Terraform Configuration (`terraform/`)
```
terraform/
├── modules/
│   ├── bedrock/          # Agent, KB, Guardrails
│   ├── lambda/           # Function definitions
│   └── core/             # IAM, KMS, SQS
└── environments/
    └── dev/
        └── main.tf       # Environment config
```

### 2. Python Management Script (`bedrock_agent_manager.py`)
Key functions:
- `get_agent_status()`: Check current configuration
- `list_versions()`: Show all agent versions
- `update_agent()`: Modify DRAFT configuration
- `prepare_agent()`: Trigger version creation
- `update_alias()`: Route traffic to new version

### 3. Deployment Orchestration Script (`deploy_agent_version.sh`)
Coordinates:
1. Terraform deployment
2. Agent version creation
3. Alias updates
4. Lambda environment variable updates

## Step-by-Step Deployment

### Prerequisites
```bash
# Required tools
aws --version          # AWS CLI
terraform --version    # Terraform >= 1.0
python3 --version      # Python 3.x

# Set environment variables
export AWS_REGION=us-east-1
export BEDROCK_AGENT_ID=P82I6ITJGO
```

### 1. Update Agent Configuration

#### Via Terraform (Recommended)
```bash
cd terraform/environments/dev

# Modify configuration
vim main.tf

# Update agent instruction, model, etc.
```

#### Via Python Script
```bash
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  update \
  --model "anthropic.claude-3-haiku-20240307-v1:0" \
  --instruction "You are Warren Buffett's AI advisor..."
```

### 2. Deploy Infrastructure

#### Automated Deployment
```bash
# Run orchestration script
./deploy_agent_version.sh dev

# Script will:
# 1. Validate environment
# 2. Run terraform plan
# 3. Apply changes
# 4. Create agent version
# 5. Update aliases
# 6. Update Lambda env vars
```

#### Manual Deployment
```bash
# Step 1: Deploy with Terraform
cd terraform/environments/dev
terraform init
terraform plan
terraform apply

# Step 2: Prepare agent (may create version)
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  prepare

# Step 3: Check versions
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  list-versions

# Step 4: Update alias to new version
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  update-alias \
  --alias-id TSTALIASID \
  --version 3

# Step 5: Update Lambda environment variables
aws lambda update-function-configuration \
  --function-name buffett-dev-chat-processor \
  --environment Variables="{BEDROCK_AGENT_ALIAS=TSTALIASID}"
```

### 3. Associate Knowledge Base

```bash
# Associate KB with specific version
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  associate-kb \
  --kb-id YTLJVSWGF9 \
  --version DRAFT

# Verify association
python3 bedrock_agent_manager.py \
  --agent-id P82I6ITJGO \
  list-versions
```

### 4. Test Deployment

```bash
# Test via AWS CLI
aws bedrock-agent-runtime invoke-agent \
  --agent-id P82I6ITJGO \
  --agent-alias-id TSTALIASID \
  --session-id test-session \
  --input-text "What are Warren Buffett's investment principles?"

# Check Lambda logs
aws logs tail /aws/lambda/buffett-dev-chat-processor --follow
```

## Troubleshooting

### Common Issues

#### 1. Version Not Created
**Symptom**: `prepare_agent` doesn't create new version
**Cause**: No significant changes detected
**Solution**:
```bash
# Make a minor change to force version creation
python3 bedrock_agent_manager.py update \
  --description "Updated at $(date)"
```

#### 2. Lambda Using Old Configuration
**Symptom**: Lambda still using old agent version
**Cause**: Environment variables not updated
**Solution**:
```bash
# Get current alias
aws bedrock-agent list-agent-aliases \
  --agent-id P82I6ITJGO \
  --query "agentAliasSummaries[?agentAliasName=='dev']"

# Update Lambda
aws lambda update-function-configuration \
  --function-name buffett-dev-chat-processor \
  --environment Variables="{BEDROCK_AGENT_ALIAS=<ALIAS_ID>}"
```

#### 3. Knowledge Base Not Associated
**Symptom**: Agent can't access knowledge base
**Cause**: KB not associated with current version
**Solution**:
```bash
python3 bedrock_agent_manager.py associate-kb \
  --kb-id YTLJVSWGF9 \
  --version DRAFT
```

#### 4. Terraform State Issues
**Symptom**: Terraform shows drift or conflicts
**Solution**:
```bash
# Import existing resources
terraform import module.bedrock.module.agent.aws_bedrockagent_agent.this P82I6ITJGO

# Refresh state
terraform refresh
```

### Debug Commands

```bash
# Check agent status
python3 bedrock_agent_manager.py --agent-id P82I6ITJGO status

# List all versions and their KB associations
python3 bedrock_agent_manager.py --agent-id P82I6ITJGO list-versions

# Check alias routing
aws bedrock-agent get-agent-alias \
  --agent-id P82I6ITJGO \
  --agent-alias-id TSTALIASID

# View Lambda environment
aws lambda get-function-configuration \
  --function-name buffett-dev-chat-processor \
  --query 'Environment.Variables'
```

## Best Practices

### 1. Version Management
- Always test in DRAFT before creating versions
- Document changes in version descriptions
- Use semantic versioning in alias names (dev, staging, prod)

### 2. Deployment Process
- Use orchestration script for consistency
- Always run `terraform plan` before `apply`
- Keep Lambda env vars in sync with aliases

### 3. Testing
- Test each version before updating aliases
- Monitor CloudWatch logs during deployment
- Maintain rollback procedures

### 4. Security
- Use IAM roles with least privilege
- Encrypt secrets in Secrets Manager
- Enable GuardRails for content filtering

### 5. Monitoring
```bash
# Set up CloudWatch alarms
aws cloudwatch put-metric-alarm \
  --alarm-name bedrock-agent-errors \
  --metric-name InvocationErrors \
  --namespace AWS/Bedrock \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

## Environment-Specific Configurations

### Development
- Model: Claude 3 Haiku (cost-optimized)
- Alias: TSTALIASID (test alias)
- Guardrails: Basic content filtering
- Logging: DEBUG level

### Production
- Model: Claude 3.5 Sonnet (performance-optimized)
- Alias: Production alias with versioning
- Guardrails: Full security policies
- Logging: INFO level with retention

## CI/CD Integration

### GitHub Actions Example
```yaml
name: Deploy Bedrock Agent
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: hashicorp/setup-terraform@v2

      - name: Deploy Agent
        run: |
          cd chat-api/backend/scripts
          ./deploy_agent_version.sh prod
        env:
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
```

## Rollback Procedures

### Quick Rollback
```bash
# List available versions
python3 bedrock_agent_manager.py list-versions

# Update alias to previous version
python3 bedrock_agent_manager.py update-alias \
  --alias-id TSTALIASID \
  --version 2

# Update Lambda env vars
./deploy_agent_version.sh dev --rollback
```

### Emergency Recovery
```bash
# Bypass alias, use specific version directly
aws lambda update-function-configuration \
  --function-name buffett-dev-chat-processor \
  --environment Variables="{BEDROCK_AGENT_ID=P82I6ITJGO,BEDROCK_AGENT_ALIAS=1}"
```

## Additional Resources
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest)
- [Pinecone Integration Guide](./bedrock-knowledge-base-pinecone-setup.md)
- [Project README](../README.md)

## Support
For issues or questions:
1. Check CloudWatch logs
2. Review Terraform state
3. Verify AWS permissions
4. Contact DevOps team