# Phase 4A: Google OAuth Setup Guide

## Overview

This guide walks you through setting up Google OAuth authentication for your Buffett Chat API development environment. The authentication system is **disabled by default** to keep development simple, but can be easily enabled when you're ready.

## Current Status

✅ **Infrastructure Created**: All Terraform configurations and Lambda functions are ready
❌ **Authentication Disabled**: Set to `enable_authentication = false` for development
🔧 **Configuration Needed**: Google OAuth credentials and JWT secret

## Prerequisites

1. **Google Cloud Console Account** - You'll need access to create OAuth credentials
2. **Domain or localhost setup** - For OAuth redirect URLs
3. **Secure JWT Secret** - A 256-bit secret for JWT signing

## Step 1: Google Cloud Console Setup

### 1.1 Create/Select Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing:
   - **Project Name**: `buffett-financial-advisor` 
   - **Project ID**: `buffett-advisor-dev` (or similar)

### 1.2 Enable Required APIs
Navigate to **APIs & Services > Library** and enable:
- **Google+ API** (Legacy - required for user info)
- **Google Identity Toolkit API** (Optional - for advanced features)

### 1.3 Configure OAuth 2.0 Credentials
1. Go to **APIs & Services > Credentials**
2. Click **"+ CREATE CREDENTIALS"** > **"OAuth 2.0 Client IDs"**
3. Configure as **Web Application**:

```yaml
Application Type: Web Application
Name: Buffett Financial Advisor Chat (Dev)

Authorized JavaScript Origins:
  - http://localhost:3000
  - http://localhost:5173
  - http://localhost:8000

Authorized Redirect URIs:
  - http://localhost:3000/auth/callback
  - http://localhost:5173/auth/callback
  - http://localhost:8000/auth/callback
```

4. **Save and Download** the credentials
5. **Note down**:
   - **Client ID**: `123456789-abcdefgh.apps.googleusercontent.com`
   - **Client Secret**: `GOCSPX-xxxxxxxxxxxxxxxxxxxx`

## Step 2: Generate JWT Secret

Generate a secure 256-bit secret for JWT signing:

```bash
# Option 1: Using OpenSSL (recommended)
openssl rand -base64 32

# Option 2: Using Python
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Option 3: Using Node.js
node -e "console.log(require('crypto').randomBytes(32).toString('base64'))"
```

**Example output**: `YourSecure256BitSecretKeyHere123456789ABCDEF=`

## Step 3: Configure terraform.tfvars

Add these variables to your `chat-api/terraform.tfvars` file:

```hcl
# Phase 4A: Google OAuth Configuration
# ==================================

# Google OAuth Credentials (from Step 1)
google_client_id     = "123456789-abcdefgh.apps.googleusercontent.com"
google_client_secret = "GOCSPX-xxxxxxxxxxxxxxxxxxxx"

# JWT Secret (from Step 2) - KEEP THIS SECRET!
jwt_secret = "YourSecure256BitSecretKeyHere123456789ABCDEF="

# Authentication Settings
enable_authentication = false  # Set to true when ready to test

# Optional: Security Configuration
security_alert_email = "your-email@example.com"
```

## Step 4: Verify Configuration (Authentication Disabled)

With authentication still **disabled**, verify everything is configured correctly:

```bash
cd chat-api

# Check Terraform plan
terraform plan

# You should see output indicating auth module is disabled
# Look for: "module.auth will not be created (disabled)"
```

## Step 5: Test Without Authentication

Your existing development workflow continues unchanged:

```bash
# Deploy infrastructure (auth disabled)
terraform apply

# Your APIs work as before
curl https://your-api-endpoint.com/dev/test

# WebSocket connections work as before (no auth required)
```

## Step 6: Enable Authentication (When Ready)

When you're ready to test OAuth authentication:

### 6.1 Enable in terraform.tfvars
```hcl
enable_authentication = true
```

### 6.2 Deploy Authentication Infrastructure
```bash
terraform plan   # Review what will be created
terraform apply  # Deploy auth infrastructure
```

### 6.3 Verify Authentication Resources
```bash
# Check terraform outputs
terraform output auth_module_enabled        # Should show: true
terraform output auth_endpoints            # Shows Lambda function names
terraform output auth_tables               # Shows DynamoDB table names
terraform output phase_4_setup_instructions # Shows next steps
```

## What Gets Created (When Enabled)

### DynamoDB Tables
- `buffett-chat-api-dev-users` - User profiles and preferences
- `buffett-chat-api-dev-sessions` - User sessions with TTL
- `buffett-chat-api-dev-security-events` - Security audit trail

### Lambda Functions  
- `buffett-chat-api-dev-auth-verify` - Google OAuth verification
- `buffett-chat-api-dev-jwt-authorizer` - JWT token validation

### AWS Secrets Manager
- `buffett-chat-api-dev-google-oauth` - Google credentials (encrypted)
- `buffett-chat-api-dev-jwt-secret` - JWT signing key (encrypted)

### KMS Key
- `alias/buffett-chat-api-dev-auth` - Encryption key for auth data

## API Endpoints (When Enabled)

### Authentication Endpoint
```
POST https://your-http-api.execute-api.us-east-1.amazonaws.com/dev/auth/google
Content-Type: application/json

{
  "token": "google-oauth-token-from-frontend"
}
```

**Response**:
```json
{
  "token": "jwt-token-for-api-calls",
  "user": {
    "id": "google-user-id",
    "email": "user@example.com",
    "name": "User Name",
    "subscription_tier": "free"
  },
  "session": {
    "id": "session-uuid",
    "expires_at": 1234567890
  }
}
```

### Using JWT Token
```bash
# HTTP API calls
curl -H "Authorization: Bearer jwt-token-here" \\
     https://your-api.execute-api.us-east-1.amazonaws.com/dev/chat

# WebSocket connection
wscat -c "wss://your-ws-api.execute-api.us-east-1.amazonaws.com/dev?token=jwt-token-here"
```

## Frontend Integration Example

```javascript
// Google OAuth login (using Google Sign-In)
const googleLogin = async (googleToken) => {
  const response = await fetch('/api/auth/google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token: googleToken })
  });
  
  const { token, user } = await response.json();
  
  // Store JWT token for API calls
  localStorage.setItem('authToken', token);
  
  // Use token for WebSocket connection
  const ws = new WebSocket(`wss://your-ws-api.com/dev?token=${token}`);
};
```

## Security Features (When Enabled)

### Input Validation
- XSS protection and HTML sanitization
- SQL injection prevention  
- Message length limits (4000 chars)
- Session validation on every request

### Monitoring
- Security events logged to DynamoDB
- Failed auth attempts tracking
- Session hijacking detection
- Token expiration handling

### Data Protection
- All auth data encrypted with KMS
- JWT tokens with secure expiration
- Session TTL and cleanup
- PII data protection

## Cost Estimation

### Development (Auth Disabled)
- **Additional Cost**: $0/month
- **Storage**: Credentials stored in terraform.tfvars only

### Development (Auth Enabled)  
- **Lambda Functions**: ~$2/month (low usage)
- **DynamoDB**: ~$5/month (on-demand)
- **Secrets Manager**: $1.20/month (3 secrets)
- **KMS**: $1/month (1 key)
- **Total**: ~$10/month additional

## Troubleshooting

### Common Issues

**1. Terraform plan fails with auth variables**
```bash
# Solution: Ensure all variables are set in terraform.tfvars
terraform plan -var-file=terraform.tfvars
```

**2. Google OAuth "redirect_uri_mismatch" error**
```
# Solution: Check that your frontend URL matches exactly:
# Google Console: http://localhost:3000/auth/callback
# Your frontend: http://localhost:3000/auth/callback (exact match)
```

**3. JWT secret too short error**
```
# Solution: Ensure JWT secret is at least 32 characters
# Use: openssl rand -base64 32
```

**4. Lambda deployment fails**
```bash
# Solution: Install Lambda dependencies
cd chat-api/lambda-auth/auth-verify
pip install -r requirements.txt -t .
cd ../jwt-authorizer  
pip install -r requirements.txt -t .
```

### Rollback Plan

If issues arise, disable authentication:

```hcl
# terraform.tfvars
enable_authentication = false
```

```bash
terraform apply  # Removes auth infrastructure
```

Your APIs continue working without authentication.

## Next Steps

1. **✅ Complete**: Phase 4A infrastructure ready
2. **🔧 Manual**: Set up Google OAuth credentials  
3. **🔧 Manual**: Configure terraform.tfvars with secrets
4. **⏳ Optional**: Enable authentication when ready to test
5. **⏳ Future**: Phase 4B - WebSocket auth integration
6. **⏳ Future**: Phase 4C - Input validation & WAF

## Support

- **Configuration Issues**: Check this guide's troubleshooting section
- **Google OAuth Help**: [Google OAuth Documentation](https://developers.google.com/identity/protocols/oauth2)
- **Terraform Issues**: Run `terraform plan` to see detailed error messages

---

**Remember**: Authentication starts **disabled** for development convenience. Enable it when you're ready to test the full OAuth flow!