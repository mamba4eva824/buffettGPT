# CloudFront + S3 Static Site Module

This module creates a secure, scalable static website hosting solution using Amazon CloudFront and S3.

## Features

- **S3 bucket** with versioning and encryption enabled
- **CloudFront distribution** with Origin Access Control (OAC) for secure S3 access
- **SPA routing support** - 404/403 errors redirect to index.html for client-side routing
- **HTTPS enforcement** - All HTTP requests redirected to HTTPS
- **HTTP/2 and HTTP/3** support for improved performance
- **Gzip compression** enabled for faster content delivery
- **AWS managed cache policies** for optimized static content delivery
- **Complete public access blocking** - S3 bucket only accessible via CloudFront

## Usage

```hcl
module "cloudfront_frontend" {
  source = "../../modules/cloudfront-static-site"

  project_name = "buffett"
  environment  = "staging"
  price_class  = "PriceClass_100"

  common_tags = {
    Environment = "staging"
    Project     = "buffett"
    ManagedBy   = "Terraform"
  }
}
```

## Requirements

| Name | Version |
|------|---------|
| terraform | >= 1.0 |
| aws | ~> 5.0 |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| project_name | Name of the project | `string` | n/a | yes |
| environment | Environment name (dev, staging, prod) | `string` | n/a | yes |
| price_class | CloudFront distribution price class | `string` | `"PriceClass_100"` | no |
| wait_for_deployment | Wait for CloudFront distribution deployment to complete | `bool` | `true` | no |
| common_tags | Common tags to apply to all resources | `map(string)` | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| cloudfront_distribution_id | ID of the CloudFront distribution |
| cloudfront_distribution_arn | ARN of the CloudFront distribution |
| cloudfront_domain_name | Domain name of the CloudFront distribution |
| cloudfront_url | Full HTTPS URL of the CloudFront distribution |
| s3_bucket_name | Name of the S3 bucket |
| s3_bucket_arn | ARN of the S3 bucket |
| s3_bucket_regional_domain_name | Regional domain name of the S3 bucket |

## Security Features

1. **Origin Access Control (OAC)** - Uses AWS's latest security mechanism for CloudFront to S3 access (replaces legacy OAI)
2. **Block Public Access** - S3 bucket has all public access blocked; only CloudFront can access
3. **HTTPS Only** - Viewer protocol policy set to redirect-to-https
4. **TLS 1.2+** - Minimum TLS version set to 1.2
5. **Encryption at Rest** - S3 bucket uses AES-256 encryption

## Cache Behavior

Uses AWS managed cache policy `CachingOptimized` (ID: 658327ea-f89d-4fab-a63d-7e88639e58f6):
- Cache static assets for optimal performance
- Gzip compression enabled
- Query strings and cookies not cached by default

## SPA Routing

The module configures CloudFront to support Single Page Applications (SPAs) like React/Vite:
- 404 errors → Return `/index.html` with 200 status
- 403 errors → Return `/index.html` with 200 status
- This allows client-side routing to work correctly

## Deployment

After applying this module:

1. **Upload frontend files to S3**:
   ```bash
   aws s3 sync ./dist s3://<bucket-name>/ --delete
   ```

2. **Invalidate CloudFront cache**:
   ```bash
   aws cloudfront create-invalidation \
     --distribution-id <distribution-id> \
     --paths "/*"
   ```

## Cost Optimization

The default `PriceClass_100` serves content from:
- United States
- Canada
- Europe

For global reach, use `PriceClass_All` but note increased costs.

## Notes

- CloudFront distributions take ~15 minutes to deploy or update
- S3 bucket versioning is enabled for rollback capability
- Wait for deployment is enabled by default to ensure resources are ready