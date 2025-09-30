#!/bin/bash

# Cleanup Script: Remove Tracked Sensitive Files from Git
# This script removes files from Git tracking but keeps them locally
# Safe to run - will not delete your local files

set -e

echo "=========================================="
echo "  Cleanup: Remove Tracked Sensitive Files"
echo "=========================================="
echo ""
echo "This script will:"
echo "  1. Remove sensitive files from Git tracking"
echo "  2. Keep the files on your local filesystem"
echo "  3. Add them to .gitignore (already done)"
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
  echo "Aborted."
  exit 1
fi

# Files to untrack (but keep locally)
FILES_TO_UNTRACK=(
  "frontend/.env.development"
  "frontend/.env.production"
)

echo ""
echo "Removing files from Git tracking..."
for file in "${FILES_TO_UNTRACK[@]}"; do
  if git ls-files --error-unmatch "$file" > /dev/null 2>&1; then
    echo "  → Untracking: $file"
    git rm --cached "$file" 2>/dev/null || true
  else
    echo "  ✓ Already untracked: $file"
  fi
done

echo ""
echo "=========================================="
echo "✅ Cleanup complete!"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Commit the removal: git commit -m 'chore: remove sensitive files from tracking'"
echo "  3. Verify: ./pre-push-verify.sh"
echo "  4. Push when ready: git push origin <branch>"
echo ""
echo "Note: Your local .env files are still on disk"
echo "      They are now gitignored and won't be tracked"
echo "=========================================="