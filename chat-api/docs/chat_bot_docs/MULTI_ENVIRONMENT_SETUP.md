# Multi-Environment CI/CD Setup Guide

This document describes how to set up the three-environment SDLC for BuffettGPT.

## Overview

| Branch | Environment | Trigger | Approval Required |
|--------|-------------|---------|-------------------|
| `dev` | Development | Push to `dev` | No |
| `staging` | Staging | Push to `staging` | No |
| `main` | Production | Push to `main` | **Yes** |

## Step 1: Create GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

### Shared Secrets (already configured)

These secrets are shared across all environments:

| Secret Name | Description | Already Exists |
|-------------|-------------|----------------|
| `AWS_ACCESS_KEY_ID` | AWS IAM access key | ✅ Yes |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM secret key | ✅ Yes |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | ✅ Yes |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | ✅ Yes |
| `ALERT_EMAIL` | Email for CloudWatch alerts | ✅ Yes |

### Dev Environment Secrets

The dev workflow reuses your existing staging secrets for authentication. You only need to add **3 new secrets** after the first Terraform deployment:

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `DEV_S3_FRONTEND_BUCKET` | S3 bucket for dev frontend | From Terraform output: `terraform output s3_bucket_name` |
| `DEV_CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID | From Terraform output: `terraform output cloudfront_distribution_id` |
| `DEV_CLOUDFRONT_URL` | CloudFront URL | From Terraform output: `terraform output cloudfront_url` |

**Reused from staging (no action needed):**
- `JWT_SECRET` - Shared with staging
- `PINECONE_API_KEY` - Shared with staging
- `GOOGLE_CLIENT_ID` - Shared
- `GOOGLE_CLIENT_SECRET` - Shared

### Staging Environment Secrets (existing - keep as-is)

The staging workflow currently uses these existing secrets:

| Secret Name | Description |
|-------------|-------------|
| `S3_FRONTEND_BUCKET` | S3 bucket for staging frontend |
| `CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID |
| `CLOUDFRONT_URL` | CloudFront URL |
| `JWT_SECRET` | JWT signing secret |
| `PINECONE_API_KEY` | Pinecone API key |

### Production Environment Secrets (NEW)

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `PROD_S3_FRONTEND_BUCKET` | S3 bucket for prod frontend | Created by Terraform (e.g., `buffett-prod-frontend`) |
| `PROD_CLOUDFRONT_DISTRIBUTION_ID` | CloudFront distribution ID | Created by Terraform |
| `PROD_CLOUDFRONT_URL` | CloudFront URL | Created by Terraform |
| `PROD_JWT_SECRET` | JWT signing secret for prod | Generate: `openssl rand -base64 48` |
| `PROD_PINECONE_API_KEY` | Pinecone API key for prod index | Pinecone dashboard |

## Step 2: Create GitHub Environment for Production Approval

1. Go to GitHub repository → Settings → Environments
2. Click "New environment"
3. Name it: `production`
4. Configure protection rules:
   - Check "Required reviewers"
   - Add yourself (or team members) as reviewers
   - Optionally set "Wait timer" (e.g., 5 minutes)
5. Click "Save protection rules"

## Step 3: Create Branches

Run these commands locally:

```bash
# Ensure you're on main and up to date
git checkout main
git pull origin main

# Create dev branch
git checkout -b dev
git push -u origin dev

# Create staging branch
git checkout main
git checkout -b staging
git push -u origin staging
```

## Step 4: Configure Branch Protection Rules

Go to GitHub repository → Settings → Branches → Add branch protection rule

### For `staging` branch:
- Branch name pattern: `staging`
- Check: "Require a pull request before merging"
- Check: "Require status checks to pass before merging"
- Click "Create"

### For `main` branch:
- Branch name pattern: `main`
- Check: "Require a pull request before merging"
- Check: "Require approvals" → Set to 1
- Check: "Require status checks to pass before merging"
- Check: "Do not allow bypassing the above settings"
- Click "Create"

### For `dev` branch:
- No protection rules needed (allow direct pushes)

## Step 5: Initial Deployment

### Deploy Dev Environment First

1. Push any small change to the `dev` branch:
   ```bash
   git checkout dev
   echo "# Dev branch initialized" >> README.md
   git add README.md
   git commit -m "chore: initialize dev branch"
   git push origin dev
   ```

2. Check GitHub Actions - the "Deploy to Dev" workflow should run
3. Once complete, note the Terraform outputs for CloudFront URL, etc.
4. Add the DEV_* secrets to GitHub with the Terraform output values

### Verify Staging Still Works

1. Push to staging branch:
   ```bash
   git checkout staging
   git push origin staging
   ```

2. The "Deploy to Staging" workflow should trigger
3. Verify the staging environment still works

### Deploy Production

1. Create a PR from `staging` to `main`
2. Approve and merge the PR
3. The "Deploy to Production" workflow will trigger
4. **You will be prompted to approve** the deployment in GitHub
5. Approve the deployment
6. Note the Terraform outputs and add PROD_* secrets

## Workflow Summary

```
Feature Development:
1. Create feature branch from dev
2. Make changes
3. Push to dev branch (direct or PR)
4. Automatic deployment to dev environment

Staging Promotion:
1. Create PR from dev → staging
2. Review and merge
3. Automatic deployment to staging environment

Production Release:
1. Create PR from staging → main
2. Review and approve PR
3. Merge triggers production workflow
4. Approve deployment in GitHub Actions
5. Production deployment proceeds
```

## Rollback Procedures

### Quick Rollback (Git Revert)
```bash
# Revert the last commit on main
git checkout main
git revert HEAD
git push origin main
# New deployment will trigger with reverted code
```

### Lambda Version Rollback
```bash
# Point Lambda alias to previous version
aws lambda update-alias \
  --function-name buffett-prod-chat-processor \
  --name live \
  --function-version <previous-version-number>
```

## Troubleshooting

### Deployment fails with missing secrets
- Verify all required secrets are added in GitHub
- Check secret names match exactly (case-sensitive)

### Terraform state lock error
- Check if another deployment is running
- If stuck, manually release lock in DynamoDB

### Production approval not appearing
- Ensure the `production` GitHub Environment exists
- Ensure "Required reviewers" is configured
- Check you're listed as a reviewer
