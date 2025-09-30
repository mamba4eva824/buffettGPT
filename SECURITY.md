# 🔒 Security Guidelines for BuffettGPT

## Overview
This document outlines security best practices for the BuffettGPT project, particularly for CI/CD pipelines and GitHub workflows.

---

## 🚨 Pre-Push Security Verification

### **Always Run Before Pushing to GitHub:**

```bash
# Run the pre-push verification script
./pre-push-verify.sh

# If it passes, you're safe to push
git push origin <branch>
```

The script checks for:
- Exposed secrets in staged files
- Accidentally staged sensitive files
- Terraform state backups
- Hardcoded credentials

---

## 🔐 Sensitive Files & .gitignore

### **NEVER Commit These Files:**

#### **Terraform Variables:**
```
❌ terraform.tfvars
❌ *.auto.tfvars
❌ dev.auto.tfvars
❌ secrets.tfvars
❌ *.secret.tfvars
```

#### **Environment Files:**
```
❌ .env
❌ .env.local
❌ .env.development
❌ .env.production
❌ .env.staging
```

#### **State & Config:**
```
❌ terraform.tfstate
❌ terraform.tfstate.backup
❌ state-backup-*.json
❌ backend-config.json
```

#### **Credentials:**
```
❌ credentials.json
❌ secrets.json
❌ *_credentials.json
❌ *.pem
❌ *.key
```

### **Safe to Commit (Examples Only):**
```
✅ .env.example
✅ terraform.tfvars.example
✅ .env.local.example
✅ bedrock_config.json (resource IDs only)
✅ pinecone_config.json (public config)
```

---

## 🔑 Secrets Management

### **Current Secrets in Project:**

1. **Google OAuth Credentials**
   - Client ID: Semi-public (in frontend)
   - Client Secret: ⚠️ **CRITICAL** - Never commit
   - Stored in: AWS Secrets Manager (`buffett-dev-google-oauth`)

2. **JWT Signing Secret**
   - ⚠️ **CRITICAL** - Authentication security
   - Stored in: AWS Secrets Manager (`buffett-dev-jwt-secret`)

3. **Pinecone API Key**
   - ⚠️ **CRITICAL** - Vector database access
   - Stored in: AWS Secrets Manager (`buffett-dev-pinecone-api-key`)

4. **AWS Credentials**
   - ⚠️ **CRITICAL** - Infrastructure access
   - Stored in: GitHub Actions Secrets

### **Where Secrets Should Live:**

| Environment | Storage Location | Access Method |
|-------------|------------------|---------------|
| **Local Dev** | AWS Secrets Manager | AWS CLI / IAM |
| **CI/CD Pipeline** | GitHub Actions Secrets | Workflow env vars |
| **Lambda Functions** | Environment Variables | Terraform injection |
| **Terraform** | `.tfvars` (gitignored) | Local file |

---

## 🔄 Secret Rotation Procedures

### **If Secrets Are Accidentally Committed:**

#### **1. Google OAuth Secret**
```bash
# 1. Go to Google Cloud Console
# 2. Credentials → OAuth 2.0 Client IDs
# 3. Delete compromised secret
# 4. Generate new secret
# 5. Update AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id buffett-dev-google-oauth \
  --secret-string '{"client_id":"YOUR_CLIENT_ID","client_secret":"NEW_SECRET"}'
```

#### **2. JWT Secret**
```bash
# Generate new JWT secret
NEW_JWT=$(openssl rand -base64 48)

# Update AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id buffett-dev-jwt-secret \
  --secret-string "$NEW_JWT"

# Note: All users will need to re-authenticate
```

#### **3. Pinecone API Key**
```bash
# 1. Log into Pinecone dashboard
# 2. Regenerate API key
# 3. Update AWS Secrets Manager
aws secretsmanager update-secret \
  --secret-id buffett-dev-pinecone-api-key \
  --secret-string "NEW_PINECONE_KEY"
```

#### **4. AWS Access Keys**
```bash
# List current keys
aws iam list-access-keys --user-name github-actions-cicd

# Delete compromised key
aws iam delete-access-key \
  --access-key-id <OLD_KEY_ID> \
  --user-name github-actions-cicd

# Create new key
aws iam create-access-key --user-name github-actions-cicd

# Update GitHub Actions Secrets with new keys
```

---

## 🛡️ GitHub Actions Security

### **Required Secrets in GitHub Repository:**

Navigate to: **Settings** → **Secrets and variables** → **Actions**

#### **Tier 1: Critical AWS Credentials**
```
AWS_ACCESS_KEY_ID          - IAM access key for deployments
AWS_SECRET_ACCESS_KEY      - IAM secret key
AWS_REGION                 - us-east-1
AWS_ACCOUNT_ID             - 430118826061
```

#### **Tier 2: Application Secrets**
```
GOOGLE_CLIENT_ID           - OAuth client ID
GOOGLE_CLIENT_SECRET       - OAuth client secret (CRITICAL)
JWT_SECRET                 - JWT signing secret (CRITICAL)
PINECONE_API_KEY          - Vector DB API key (CRITICAL)
```

#### **Tier 3: Infrastructure Config**
```
TF_STATE_BUCKET           - S3 state bucket name
TF_STATE_DYNAMODB_TABLE   - DynamoDB locks table
TF_STATE_KMS_KEY_ID       - KMS key ARN
BEDROCK_AGENT_ID          - Bedrock agent ID
BEDROCK_AGENT_ALIAS       - Bedrock agent alias
```

#### **Tier 4: Environment URLs**
```
VITE_WEBSOCKET_URL_DEV
VITE_REST_API_URL_DEV
VITE_WEBSOCKET_URL_STAGING
VITE_REST_API_URL_STAGING
VITE_WEBSOCKET_URL_PROD
VITE_REST_API_URL_PROD
```

---

## 🔍 Secret Scanning

### **Manual Verification:**

```bash
# Check for secrets before committing
git diff --cached | grep -iE "(password|secret|api[_-]?key|token|credential|AKIA|ASIA|GOCSPX-)"

# Check specific file
git show HEAD:path/to/file.tf | grep -i secret

# Search all tracked files
git grep -iE "(password|secret|api[_-]?key|token|credential)"
```

### **Automated Scanning:**

The `pre-push-verify.sh` script automatically scans for:
- AWS access keys (AKIA/ASIA patterns)
- Google OAuth secrets (GOCSPX- pattern)
- Common secret keywords
- Terraform state files
- Environment files

---

## 📊 Security Checklist

### **Before Every Git Push:**

- [ ] Run `./pre-push-verify.sh`
- [ ] Verify `.gitignore` is up to date
- [ ] Check no `.tfvars` files are staged
- [ ] Check no `.env` files are staged
- [ ] Verify no state backups are staged
- [ ] Review `git status --ignored` output

### **For CI/CD Setup:**

- [ ] All secrets configured in GitHub Actions
- [ ] Secrets Manager policies are restrictive
- [ ] IAM roles follow principle of least privilege
- [ ] MFA enabled for AWS root/admin accounts
- [ ] CloudTrail logging enabled
- [ ] Secrets rotation schedule documented

### **For Production Deployments:**

- [ ] All production secrets unique (not copied from dev)
- [ ] Logging disabled in production frontend
- [ ] Backend LOG_LEVEL set to ERROR
- [ ] API rate limiting enabled
- [ ] WAF rules configured
- [ ] Monitoring and alerts active

---

## 🚀 Quick Reference Commands

```bash
# Verify what will be pushed
git status
git diff --cached --name-only

# Check if file is gitignored
git check-ignore -v path/to/file

# Unstage a sensitive file
git reset HEAD path/to/sensitive/file

# Remove file from Git history (if accidentally pushed)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch path/to/sensitive/file" \
  --prune-empty --tag-name-filter cat -- --all

# Or use BFG Repo-Cleaner (recommended)
# https://rtyley.github.io/bfg-repo-cleaner/

# Force push after cleaning history (DANGEROUS - coordinate with team)
git push origin --force --all
git push origin --force --tags
```

---

## 📝 Incident Response

### **If Secrets Are Leaked to GitHub:**

1. **Immediate Action (Within 5 minutes):**
   - Rotate ALL compromised secrets immediately
   - Revoke access keys/tokens
   - Change passwords
   - Notify security team

2. **Containment (Within 30 minutes):**
   - Remove secrets from Git history
   - Force push cleaned history
   - Verify removal with `git log -p | grep SECRET_PATTERN`
   - Contact GitHub support if needed

3. **Recovery (Within 24 hours):**
   - Update all systems with new secrets
   - Monitor for unauthorized access
   - Review CloudTrail logs
   - Update incident documentation

4. **Lessons Learned:**
   - Document what went wrong
   - Update procedures
   - Improve automated scanning
   - Train team members

---

## 📞 Security Contacts

- **AWS Support**: [AWS Console](https://console.aws.amazon.com/support/)
- **GitHub Security**: [GitHub Security](https://github.com/security)
- **Google Cloud Support**: [Google Cloud Console](https://console.cloud.google.com/support/)

---

## 📚 Additional Resources

- [GitHub Secret Scanning](https://docs.github.com/en/code-security/secret-scanning)
- [AWS Secrets Manager Best Practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Terraform Sensitive Data](https://www.terraform.io/docs/language/values/variables.html#suppressing-values-in-cli-output)

---

**Last Updated**: 2025-01-12
**Maintained By**: BuffettGPT Security Team