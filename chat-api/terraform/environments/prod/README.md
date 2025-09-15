# Production Environment

## Status: Not Yet Configured

This directory is reserved for the production environment Terraform configuration.

## When Ready to Configure:
1. Copy structure from `../dev/` as a starting point
2. Modify environment-specific values:
   - S3 backend with state locking
   - Production-grade resource sizing
   - Full monitoring and alerting
   - Backup and disaster recovery
   - Security hardening

## Key Differences from Dev:
- S3 remote state backend with DynamoDB locking
- Provisioned concurrency for Lambda functions
- VPC with private subnets
- Enhanced monitoring and alerting
- Deletion protection enabled
- Automated backups
- Multi-AZ deployments where applicable
