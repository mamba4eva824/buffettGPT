# CI/CD Troubleshooting Guide

## Overview

This document chronicles every error encountered during the staging environment CI/CD pipeline setup, the root causes, and the solutions applied. Use this as a reference for debugging similar issues.

---

## Error 1: Terraform Version Incompatibility

### Deployment Run
**Commit:** `76155bd` - "fix(ci/cd): upgrade Terraform version to 1.9.1 for state compatibility"

### Error Message
```
Error: unsupported checkable object kind 'var'
```

### Context
- **Job:** Deploy Infrastructure with Terraform
- **Step:** Terraform Plan
- **Exit Code:** 1

### Root Cause
The Terraform state file was created locally with version 1.9.1, but the GitHub Actions workflow was using version 1.5.0. Terraform 1.5.0 cannot read state files created by newer versions.

### Investigation
```bash
# Local version check
$ terraform version
Terraform v1.9.1

# GitHub Actions was using
terraform_version: 1.5.0
```

### Solution Applied
Updated `.github/workflows/deploy-staging.yml`:

```yaml
# Before:
terraform_version: 1.5.0

# After:
terraform_version: 1.9.1
```

**Why This Works:**
- Terraform state files have a version-specific format
- Newer versions can read older state files (forward compatible)
- Older versions cannot read newer state files (not backward compatible)
- Keeping CI/CD and local development on the same version prevents issues

### Prevention
- Document required Terraform version in README
- Use `.terraform-version` file for version pinning
- Keep local and CI/CD Terraform versions synchronized

---

## Error 2: CloudFront Module Not Found

### Deployment Run
**Commit:** `a6f31f5` - "feat(terraform): add import block for existing S3 bucket"

### Error Message
```
Error: Unreadable module directory
Unable to evaluate directory symlink: lstat ../../modules/cloudfront-static-site:
no such file or directory
```

### Context
- **Job:** Deploy Infrastructure with Terraform
- **Step:** Terraform Init
- **Exit Code:** 1

### Root Cause
The CloudFront Terraform module was created locally but never committed to the repository. When GitHub Actions checked out the code, the module directory didn't exist.

### Investigation
```bash
# Check git status
$ git status
Untracked files:
  chat-api/terraform/modules/cloudfront-static-site/

# Verify module exists locally
$ ls chat-api/terraform/modules/cloudfront-static-site/
main.tf  outputs.tf  variables.tf  README.md
```

### Solution Applied
```bash
git add chat-api/terraform/modules/cloudfront-static-site/
git commit -m "feat(terraform): add CloudFront static site module"
git push origin main
```

### Files Added
- `main.tf` - CloudFront distribution + S3 bucket resources
- `outputs.tf` - Module outputs (distribution ID, URL, bucket name)
- `variables.tf` - Module inputs (project_name, environment, price_class)
- `README.md` - Module documentation

**Why This Works:**
Terraform `module` blocks reference local paths. If the path doesn't exist, `terraform init` fails because it can't load the module definition.

### Prevention
- Always check `git status` before committing Terraform changes
- Use `git add -A` cautiously - review what's being staged
- Run `terraform validate` locally before pushing

---

## Error 3: S3 Bucket Already Exists

### Deployment Run
**Commit:** `6414bd2` - "fix(terraform): remove CloudFront module from staging config"

### Error Message
```
Error: error creating S3 bucket (buffett-staging-frontend): BucketAlreadyOwnedByYou
```

### Context
- **Job:** Deploy Infrastructure with Terraform
- **Step:** Terraform Apply
- **Exit Code:** 1

### Root Cause
The S3 bucket `buffett-staging-frontend` was created manually before Terraform was configured to manage it. When Terraform tried to create it, AWS returned an error because the bucket already existed.

Additionally, the bucket contained frontend files, so deletion would fail with `BucketNotEmpty` error.

### Investigation
```bash
# Check if bucket exists
$ aws s3 ls | grep buffett-staging-frontend
buffett-staging-frontend

# Check bucket contents
$ aws s3 ls s3://buffett-staging-frontend/
2025-09-30 index.html
2025-09-30 assets/
```

### Solution Applied - Attempt 1 (Failed)
Initially tried to remove CloudFront module from Terraform:

```hcl
# Commented out CloudFront module
# module "cloudfront" {
#   source = "../../modules/cloudfront-static-site"
#   ...
# }
```

**Problem:** This defeated the purpose of Infrastructure as Code.

### Solution Applied - Attempt 2 (Success)
Used Terraform `import` block to adopt the existing S3 bucket:

```hcl
# Import existing S3 bucket into Terraform state
import {
  to = module.cloudfront.aws_s3_bucket.frontend
  id = "buffett-staging-frontend"
}

module "cloudfront" {
  source = "../../modules/cloudfront-static-site"
  # ... configuration
}
```

**Why This Works:**
- Terraform 1.9+ supports declarative `import` blocks
- The import block tells Terraform: "This resource already exists in AWS, adopt it"
- During `terraform apply`, Terraform imports the resource into state
- No destruction/recreation needed - existing bucket and files preserved
- Future deployments can manage the bucket via Terraform

### Prevention
- Use Terraform for all infrastructure from the start
- Document manual resource creation if unavoidable
- Import existing resources before adding them to Terraform config

---

## Error 4: NPM Package Lock Missing

### Deployment Run
**Commit:** `37a84a5` - "fix(ci/cd): remove npm cache from frontend build"

### Error Message
```
Error: Some specified paths were not resolved, unable to cache dependencies
```

### Context
- **Job:** Build Frontend
- **Step:** Setup Node.js
- **Exit Code:** 1

### Root Cause
The GitHub Actions workflow attempted to cache npm dependencies using `package-lock.json`, but this file was in `.gitignore` and not tracked in the repository.

### Investigation
```bash
# Check if package-lock.json exists locally
$ ls frontend/package-lock.json
package-lock.json  # Exists locally

# Check if tracked in git
$ git ls-files | grep package-lock.json
# No output - not tracked

# Check .gitignore
$ grep package-lock .gitignore
package-lock.json
```

### Solution Applied
Removed npm caching from workflow:

```yaml
# Before:
- name: Setup Node.js
  uses: actions/setup-node@v4
  with:
    node-version: ${{ env.NODE_VERSION }}
    cache: 'npm'
    cache-dependency-path: frontend/package-lock.json

# After:
- name: Setup Node.js
  uses: actions/setup-node@v4
  with:
    node-version: ${{ env.NODE_VERSION }}
    # Removed cache configuration
```

**Why This Works:**
- Without `cache` parameter, `setup-node` doesn't attempt to cache
- Slightly slower builds (no cache hit), but no failure
- `npm install` still works normally

### Alternative Solutions
1. **Remove from .gitignore** (recommended for consistency):
   ```bash
   # Remove package-lock.json from .gitignore
   git add frontend/package-lock.json
   git commit -m "chore: track package-lock.json for consistent installs"
   ```

2. **Use yarn instead** (has yarn.lock tracked by default)

### Prevention
- Include `package-lock.json` in repository for reproducible builds
- If excluding lock files, don't configure npm caching
- Document dependency management strategy in README

---

## Error 5: NPM CI Requires Lock File

### Deployment Run
**Commit:** `a9d6409` - "fix(ci/cd): use npm install instead of npm ci"

### Error Message
```
npm error The `npm ci` command can only install with an existing package-lock.json
or npm-shrinkwrap.json with lockfileVersion >= 1
```

### Context
- **Job:** Build Frontend
- **Step:** Install dependencies
- **Exit Code:** 1

### Root Cause
The workflow used `npm ci` (clean install) which requires a `package-lock.json` file. Since the lock file wasn't tracked in git, `npm ci` failed.

### Investigation
```bash
# npm ci requirements
# - Requires package-lock.json
# - Faster than npm install
# - Deletes node_modules and reinstalls from lock file

# Our situation
# - No package-lock.json in repo
# - npm ci cannot proceed
```

### Solution Applied
Changed from `npm ci` to `npm install`:

```yaml
# Before:
- name: Install dependencies
  working-directory: frontend
  run: npm ci

# After:
- name: Install dependencies
  working-directory: frontend
  run: npm install
```

**Why This Works:**
- `npm install` works with or without lock file
- Creates `package-lock.json` if missing (but not committed)
- Installs dependencies based on `package.json`
- Slightly less deterministic than `npm ci`

### Trade-offs
- **npm ci** (with lock file):
  - ✅ Faster
  - ✅ More consistent
  - ✅ Deterministic versions
  - ❌ Requires lock file

- **npm install** (without lock file):
  - ✅ Works without lock file
  - ✅ More flexible
  - ❌ Slower
  - ❌ Less deterministic (uses semver ranges)

### Prevention
- Commit `package-lock.json` for deterministic builds
- Or use `npm install` consistently
- Document npm vs npm ci choice in CI/CD docs

---

## Error 6: CloudFront Distribution Does Not Exist

### Deployment Run
**Commit:** `a9d6409` - First successful pipeline with frontend deployment

### Error Message
```
Error: NoSuchDistribution when calling the CreateInvalidation operation:
The specified distribution does not exist.
```

### Context
- **Job:** Deploy Frontend to S3 + CloudFront
- **Step:** Invalidate CloudFront cache
- **Exit Code:** 254

### Root Cause
The GitHub secret `CLOUDFRONT_DISTRIBUTION_ID` contained an old distribution ID (`E9XUZCDMBX6Z`) that was deleted during a previous failed Terraform apply. The new distribution had a different ID.

### Investigation
```bash
# Check GitHub secret value
CLOUDFRONT_DISTRIBUTION_ID=E9XUZCDMBX6Z

# List actual CloudFront distributions
$ aws cloudfront list-distributions \
    --query "DistributionList.Items[].{ID:Id,Domain:DomainName}"
[
  {
    "ID": "E35BL8R2LQL183",
    "Domain": "d2xq0qjqddoyoh.cloudfront.net"
  }
]

# Old distribution was deleted - new one created by Terraform
```

### Solution Applied
Updated GitHub secrets with new CloudFront information:

```bash
# Get new distribution ID from Terraform output
$ cd chat-api/terraform/environments/staging
$ terraform output cloudfront_distribution_id
"E35BL8R2LQL183"

# Update GitHub secret
$ gh secret set CLOUDFRONT_DISTRIBUTION_ID --body "E35BL8R2LQL183"
$ gh secret set CLOUDFRONT_URL --body "https://d2xq0qjqddoyoh.cloudfront.net"
```

**Why This Works:**
- CloudFront invalidation API requires valid distribution ID
- After Terraform recreated the distribution, the ID changed
- Updating the secret allows invalidation to succeed

### Prevention
- Store CloudFront ID as Terraform output, not hardcoded secret
- Use Terraform outputs in CI/CD where possible
- Add validation step to check if distribution exists before invalidation

---

## Error 7: Missing Google Client ID in Frontend Build

### Deployment Run
**Commit:** `9d2a68f` - "fix(ci/cd): add Google Client ID to frontend build environment"

### Error Message (Browser Console)
```
Error 400: invalid_request
Missing required parameter: client_id
```

### Context
- **Job:** Build Frontend (successful)
- **Runtime:** Browser (Google OAuth initialization)
- **User Impact:** Cannot sign in with Google

### Root Cause
The frontend code expected `VITE_GOOGLE_CLIENT_ID` environment variable, but the CI/CD workflow didn't include it in the `.env.staging` file created during build.

### Investigation
```javascript
// Frontend code (auth.jsx)
const AUTH_CONFIG = {
  GOOGLE_CLIENT_ID: import.meta.env.VITE_GOOGLE_CLIENT_ID,
};

// During build, .env.staging was created but missing VITE_GOOGLE_CLIENT_ID
```

```yaml
# Workflow step created .env.staging
cat > .env.staging << EOF
VITE_REST_API_URL=...
VITE_WEBSOCKET_URL=...
VITE_ENVIRONMENT=staging
VITE_ENABLE_DEBUG_LOGS=true
# Missing: VITE_GOOGLE_CLIENT_ID
EOF
```

### Solution Applied
Added Google Client ID to frontend build environment:

```yaml
# Before:
cat > .env.staging << EOF
VITE_REST_API_URL=${{ needs.deploy-infrastructure.outputs.http_api_endpoint }}
VITE_WEBSOCKET_URL=${{ needs.deploy-infrastructure.outputs.websocket_api_endpoint }}
VITE_ENVIRONMENT=staging
VITE_ENABLE_DEBUG_LOGS=true
EOF

# After:
cat > .env.staging << EOF
VITE_REST_API_URL=${{ needs.deploy-infrastructure.outputs.http_api_endpoint }}
VITE_WEBSOCKET_URL=${{ needs.deploy-infrastructure.outputs.websocket_api_endpoint }}
VITE_ENVIRONMENT=staging
VITE_ENABLE_DEBUG_LOGS=true
VITE_GOOGLE_CLIENT_ID=${{ secrets.GOOGLE_CLIENT_ID }}
EOF
```

**Why This Works:**
- Vite reads `.env.staging` at build time
- `import.meta.env.VITE_*` variables are replaced with values during build
- Adding the secret to `.env.staging` makes it available to the frontend
- Google OAuth SDK receives the client ID and initialization succeeds

### Security Considerations
- Google Client ID is **not sensitive** (public OAuth client ID)
- Client Secret is **sensitive** (stored in AWS Secrets Manager, not frontend)
- OK to include client ID in frontend build

### Prevention
- Document all required environment variables for each environment
- Create `.env.example` with all keys (values as placeholders)
- Validate environment variables in build process

---

## Error 8: OAuth Callback URL Mismatch

### Deployment Run
**Commit:** After CloudFront URL change

### Error Message (User Reported)
```
Unable to sign in using Google OAuth
Error: Redirect URI mismatch
```

### Context
- **Component:** Google OAuth Console configuration
- **User Impact:** Sign-in button clicked, but OAuth flow fails

### Root Cause
After CloudFront distribution was recreated, the URL changed from:
- Old: `https://d2bmcia2ei4z1i.cloudfront.net`
- New: `https://d2xq0qjqddoyoh.cloudfront.net`

The Google OAuth Console still had the old URL in Authorized JavaScript Origins and Redirect URIs.

### Investigation
```
Google OAuth Console:
  Authorized JavaScript origins:
    ❌ https://d2bmcia2ei4z1i.cloudfront.net (old)

  Authorized redirect URIs:
    ❌ https://d2bmcia2ei4z1i.cloudfront.net/auth/callback (old)

Actual CloudFront URL:
  ✅ https://d2xq0qjqddoyoh.cloudfront.net
```

### Solution Applied
Updated Google OAuth Console configuration:

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Select OAuth 2.0 Client ID
3. Update Authorized JavaScript origins:
   ```
   https://d2xq0qjqddoyoh.cloudfront.net
   ```
4. Update Authorized redirect URIs:
   ```
   https://d2xq0qjqddoyoh.cloudfront.net/auth/callback
   ```
5. Save changes

**Why This Works:**
- Google validates origin and redirect URI during OAuth flow
- Mismatch = security error (prevents OAuth phishing)
- Updating to correct URL allows OAuth flow to complete

### Prevention
- Use custom domain (CNAME) instead of CloudFront default domain
- Document OAuth URL configuration in deployment guide
- Automate OAuth URL updates via Google OAuth API (if possible)

---

## Common Patterns and Best Practices

### Pattern 1: State File Compatibility
**Problem:** Terraform version mismatch between local and CI/CD
**Solution:** Pin Terraform version in workflow and document in README
**Prevention:** Use `.terraform-version` file

### Pattern 2: Missing Resources in Git
**Problem:** Created locally but not committed
**Solution:** Check `git status` before pushing
**Prevention:** Use pre-commit hooks to validate Terraform modules

### Pattern 3: Hardcoded Values in Secrets
**Problem:** Infrastructure changes invalidate secrets
**Solution:** Use Terraform outputs where possible
**Prevention:** Minimize hardcoded values, prefer dynamic configuration

### Pattern 4: Lock File Management
**Problem:** Lock files in .gitignore cause CI/CD issues
**Solution:** Either commit lock files OR use install command that doesn't require them
**Prevention:** Document lock file strategy in README

### Pattern 5: Environment Variable Injection
**Problem:** Missing environment variables in build
**Solution:** Explicitly define all required variables in CI/CD
**Prevention:** Create `.env.example` as template

---

## Debugging Checklist

When a deployment fails, check:

1. **Terraform Version**
   - [ ] Local version matches CI/CD version
   - [ ] State file compatible with Terraform version

2. **Git Repository**
   - [ ] All Terraform modules committed
   - [ ] Lock files tracked (if using npm ci/yarn)
   - [ ] .env files not committed (secrets)

3. **GitHub Secrets**
   - [ ] All required secrets set
   - [ ] Secret values up-to-date (not stale)
   - [ ] No typos in secret names

4. **AWS Resources**
   - [ ] Resources exist (not manually deleted)
   - [ ] Resource IDs match configuration
   - [ ] IAM permissions sufficient

5. **Build Dependencies**
   - [ ] package.json and requirements.txt up-to-date
   - [ ] Lock files present (if using ci commands)
   - [ ] Node/Python versions correct

6. **OAuth Configuration**
   - [ ] Client ID in GitHub secrets
   - [ ] Callback URLs in Google Console
   - [ ] Origin URLs match CloudFront domain

---

## Monitoring and Prevention

### Pre-Deployment Validation

Run these commands before pushing:

```bash
# Terraform validation
cd chat-api/terraform/environments/staging
terraform fmt -check
terraform validate

# Frontend build test
cd frontend
npm install
npm run build -- --mode staging

# Check git status
git status
```

### Post-Deployment Verification

```bash
# Check deployment status
gh run list --workflow=deploy-staging.yml --limit 1

# Test endpoints
curl https://vxz4rbeu79.execute-api.us-east-1.amazonaws.com/staging/health

# Test frontend
curl -I https://d2xq0qjqddoyoh.cloudfront.net

# Check CloudFront invalidation status
aws cloudfront get-invalidation \
  --distribution-id E35BL8R2LQL183 \
  --id <invalidation-id>
```

---

## Emergency Procedures

### Pipeline Completely Broken

1. **Check GitHub Actions status page**
   - https://www.githubstatus.com/

2. **Review recent commits**
   ```bash
   git log --oneline -10
   ```

3. **Revert to last known good commit**
   ```bash
   git revert <bad-commit-hash>
   git push origin main
   ```

### Terraform State Locked

1. **Check lock status**
   ```bash
   cd chat-api/terraform/environments/staging
   terraform force-unlock <lock-id>
   ```

2. **If persistent, check DynamoDB**
   ```bash
   aws dynamodb scan --table-name terraform-state-lock
   ```

### CloudFront Not Serving New Content

1. **Create manual invalidation**
   ```bash
   aws cloudfront create-invalidation \
     --distribution-id E35BL8R2LQL183 \
     --paths "/*"
   ```

2. **Check cache headers**
   ```bash
   curl -I https://d2xq0qjqddoyoh.cloudfront.net/index.html
   # Look for: cache-control: public, max-age=0
   ```

---

## Success Metrics

A successful deployment should show:

✅ All 5 jobs completed (green checkmarks)
✅ Total time: 3-4 minutes
✅ Frontend accessible at CloudFront URL
✅ API health check returns 200
✅ WebSocket connections work
✅ Google OAuth sign-in functional
✅ No errors in CloudWatch logs

---

## Continuous Improvement

### Lessons Learned

1. **Terraform Version Consistency**
   - Pin versions explicitly
   - Test locally before CI/CD

2. **Infrastructure as Code**
   - Don't manually create resources
   - Import before managing with Terraform

3. **Environment Variables**
   - Document all required variables
   - Validate in CI/CD

4. **Testing**
   - Test locally before pushing
   - Have rollback plan ready

### Future Enhancements

1. **Pre-Deployment Checks**
   - Add `terraform plan` output review
   - Require manual approval for production

2. **Automated Testing**
   - Add integration tests
   - Test OAuth flow in CI/CD

3. **Monitoring**
   - Add deployment notifications (Slack/Email)
   - CloudWatch alarms for errors

4. **Documentation**
   - Keep this guide updated
   - Document all manual steps

---

## Related Documentation

- [CI_CD_CONFIGURATION.md](./CI_CD_CONFIGURATION.md) - Complete pipeline documentation
- [CLAUDE.md](../CLAUDE.md) - Mandatory deployment rules
- [README.md](../README.md) - Project overview
