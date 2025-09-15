# Staging Environment

## Status: Not Yet Configured

This directory is reserved for the staging environment Terraform configuration.

## When Ready to Configure:
1. Copy structure from `../dev/` as a starting point
2. Modify environment-specific values:
   - S3 backend for state management
   - Staging-specific resource sizing
   - Enable monitoring and PITR
   - Configure staging URLs and endpoints

## Key Differences from Dev:
- S3 remote state backend (not local)
- Point-in-time recovery enabled
- Authentication enabled by default
- Monitoring enabled
- Production-like resource sizing
