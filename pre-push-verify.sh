#!/bin/bash

# Pre-Push Security Verification Script
# Checks for sensitive data before pushing to GitHub
# Run this before: git push

set -e

echo "=========================================="
echo "  GitHub Pre-Push Security Verification"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track if we found any issues
ISSUES_FOUND=0

# 1. Check for secrets in staged files
echo "🔍 [1/5] Checking for secrets in staged files..."
SECRET_PATTERNS="(password|secret|api[_-]?key|token|credential|AKIA|ASIA|GOCSPX-|sk-|pk-|pcsk-|jsT88Vam|QIYVUYRITH)"

if git diff --cached | grep -iE "$SECRET_PATTERNS" > /dev/null 2>&1; then
  echo -e "${RED}⚠️  WARNING: Potential secrets found in staged changes!${NC}"
  echo "   Review the following matches:"
  git diff --cached | grep -iE "$SECRET_PATTERNS" --color=always | head -10
  ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
  echo -e "${GREEN}✅ No obvious secrets detected in staged files${NC}"
fi
echo ""

# 2. Verify critical files are gitignored
echo "🔒 [2/5] Verifying sensitive files are gitignored..."
SENSITIVE_FILES=(
  "chat-api/terraform/environments/dev/dev.auto.tfvars"
  "chat-api/terraform/environments/dev/terraform.tfvars"
  "frontend/.env.development"
  "frontend/.env.production"
  "frontend/.env.staging"
)

for file in "${SENSITIVE_FILES[@]}"; do
  if [ -f "$file" ]; then
    if git check-ignore -q "$file"; then
      echo -e "${GREEN}✅ $file is gitignored${NC}"
    else
      echo -e "${RED}⚠️  $file EXISTS but NOT gitignored!${NC}"
      ISSUES_FOUND=$((ISSUES_FOUND + 1))
    fi
  fi
done
echo ""

# 3. Check for accidentally staged sensitive files
echo "📋 [3/5] Checking for accidentally staged sensitive files..."
STAGED_FILES=$(git diff --cached --name-only)

if echo "$STAGED_FILES" | grep -E "(\.tfvars$|\.env\.|secrets|credentials|\.key$|\.pem$)" > /dev/null 2>&1; then
  echo -e "${RED}⚠️  WARNING: Potentially sensitive files are staged!${NC}"
  echo "$STAGED_FILES" | grep -E "(\.tfvars$|\.env\.|secrets|credentials|\.key$|\.pem$)" | while read file; do
    echo -e "   ${YELLOW}→ $file${NC}"
  done
  ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
  echo -e "${GREEN}✅ No sensitive file patterns in staged files${NC}"
fi
echo ""

# 4. Verify Terraform state backups are not staged
echo "💾 [4/5] Checking for Terraform state backups..."
if echo "$STAGED_FILES" | grep -E "(terraform\.tfstate|state-backup.*\.json)" > /dev/null 2>&1; then
  echo -e "${RED}⚠️  WARNING: Terraform state files are staged!${NC}"
  echo "$STAGED_FILES" | grep -E "(terraform\.tfstate|state-backup.*\.json)"
  ISSUES_FOUND=$((ISSUES_FOUND + 1))
else
  echo -e "${GREEN}✅ No Terraform state files staged${NC}"
fi
echo ""

# 5. Check for hardcoded AWS account IDs (informational only)
echo "🔑 [5/5] Scanning for hardcoded AWS account IDs..."
if git diff --cached | grep -oE "[0-9]{12}" | head -1 > /dev/null 2>&1; then
  echo -e "${YELLOW}ℹ️  Note: AWS account IDs detected (informational only)${NC}"
  echo "   This is usually fine for infrastructure code"
else
  echo -e "${GREEN}✅ No AWS account IDs detected${NC}"
fi
echo ""

# Final summary
echo "=========================================="
if [ $ISSUES_FOUND -eq 0 ]; then
  echo -e "${GREEN}✅ PASSED: Pre-push verification complete!${NC}"
  echo -e "${GREEN}   Safe to push to GitHub${NC}"
  echo "=========================================="
  exit 0
else
  echo -e "${RED}❌ FAILED: $ISSUES_FOUND issue(s) found${NC}"
  echo ""
  echo "Action required:"
  echo "1. Review the warnings above"
  echo "2. Unstage sensitive files: git reset HEAD <file>"
  echo "3. Remove secrets from code"
  echo "4. Update .gitignore if needed"
  echo "5. Run this script again"
  echo "=========================================="
  exit 1
fi