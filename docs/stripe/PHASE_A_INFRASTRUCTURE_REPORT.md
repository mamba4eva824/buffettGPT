# Phase A: Stripe Infrastructure Foundation

## Executive Summary

Phase A establishes the secure infrastructure foundation for Stripe payment integration in BuffettGPT. This phase creates a dedicated Terraform module that provisions AWS Secrets Manager resources for storing Stripe credentials and defines IAM policies for secure Lambda access.

**Completion Status**: All tasks (A1-A3) completed and verified.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Terraform Stripe Module                       │
│                  chat-api/terraform/modules/stripe/              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   main.tf    │    │ variables.tf │    │  secrets.tf  │       │
│  │  (locals)    │    │  (inputs)    │    │  (secrets)   │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐                           │
│  │    iam.tf    │    │  outputs.tf  │                           │
│  │  (policies)  │    │  (exports)   │                           │
│  └──────────────┘    └──────────────┘                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AWS Secrets Manager                           │
├─────────────────────────────────────────────────────────────────┤
│  stripe-secret-key-{env}      │  Stripe API Secret Key (sk_*)   │
│  stripe-webhook-secret-{env}  │  Webhook Signing Secret (whsec_)│
│  stripe-plus-price-id-{env}   │  Plus Plan Price ID (price_*)   │
│  stripe-publishable-key-{env} │  Publishable Key (pk_*)         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      IAM Policy                                  │
├─────────────────────────────────────────────────────────────────┤
│  stripe-secrets-access-{env}                                     │
│  - secretsmanager:GetSecretValue                                 │
│  - secretsmanager:DescribeSecret                                 │
│  Resources: [stripe-secret-key, stripe-webhook-secret,           │
│              stripe-plus-price-id]                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Task A1: Module Structure & Configuration

### File: `main.tf`

**Purpose**: Establishes the module foundation with local variables for consistent secret naming.

**Key Implementation**:
```hcl
locals {
  stripe_secret_key_name      = "stripe-secret-key-${var.environment}"
  stripe_webhook_secret_name  = "stripe-webhook-secret-${var.environment}"
  stripe_plus_price_id_name   = "stripe-plus-price-id-${var.environment}"
  stripe_publishable_key_name = "stripe-publishable-key-${var.environment}"
}
```

**Why This Matters**:
- Follows BuffettGPT's established naming convention: `{service}-{key-type}-{env}`
- Ensures consistency across dev/staging/prod environments
- Centralizes naming logic for easy maintenance

### File: `variables.tf`

**Purpose**: Defines all input variables for the module with appropriate defaults and sensitivity markers.

**Variables**:

| Variable | Type | Required | Description |
|----------|------|----------|-------------|
| `environment` | string | Yes | Environment name (dev/staging/prod) |
| `common_tags` | map(string) | No | Tags applied to all resources |
| `stripe_secret_key` | string | No | Stripe API secret key (sensitive) |
| `stripe_webhook_secret` | string | No | Webhook signing secret (sensitive) |
| `stripe_plus_price_id` | string | No | Plus plan price ID (sensitive) |
| `stripe_publishable_key` | string | No | Publishable key for frontend |
| `token_limit_plus` | number | No | Token limit for Plus tier (default: 2,000,000) |

**Security Design**:
- All secret variables marked `sensitive = true` to prevent exposure in logs
- Optional values allow infrastructure deployment before secrets are populated
- Defaults to empty strings, enabling phased secret population

---

## Task A2: Secrets Manager Resources

### File: `secrets.tf`

**Purpose**: Creates AWS Secrets Manager secrets for all Stripe credentials with conditional secret version creation.

**Secrets Created**:

1. **stripe-secret-key-{env}**
   - Contains: Stripe API secret key (`sk_test_*` or `sk_live_*`)
   - Used by: Backend Lambda handlers for Stripe API calls
   - Criticality: **HIGH** - Required for all Stripe operations

2. **stripe-webhook-secret-{env}**
   - Contains: Webhook signing secret (`whsec_*`)
   - Used by: Webhook handler for signature verification
   - Criticality: **HIGH** - Prevents webhook spoofing attacks

3. **stripe-plus-price-id-{env}**
   - Contains: Price ID for BuffettGPT Plus subscription (`price_*`)
   - Used by: Checkout session creation
   - Criticality: **MEDIUM** - Required for checkout flow

4. **stripe-publishable-key-{env}**
   - Contains: Publishable key (`pk_test_*` or `pk_live_*`)
   - Used by: Frontend Stripe.js initialization
   - Criticality: **LOW** - Safe for client-side exposure

**Key Design Patterns**:

```hcl
# Conditional secret version creation
resource "aws_secretsmanager_secret_version" "stripe_secret_key" {
  count         = var.stripe_secret_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_secret_key.id
  secret_string = var.stripe_secret_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}
```

**Why This Pattern**:
- `count = var.stripe_secret_key != "" ? 1 : 0`: Only creates version if value provided
- `ignore_changes`: Prevents Terraform from overwriting manually-updated secrets
- Enables infrastructure deployment before secrets are available
- Supports manual AWS Console population for sensitive credentials

---

## Task A3: IAM Policy for Lambda Access

### File: `iam.tf`

**Purpose**: Creates a restrictive IAM policy allowing Lambda functions to read Stripe secrets.

**Policy Definition**:
```hcl
data "aws_iam_policy_document" "stripe_secrets_access" {
  statement {
    sid    = "ReadStripeSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [
      aws_secretsmanager_secret.stripe_secret_key.arn,
      aws_secretsmanager_secret.stripe_webhook_secret.arn,
      aws_secretsmanager_secret.stripe_plus_price_id.arn,
    ]
  }
}
```

**Security Principles Applied**:

1. **Least Privilege**: Only grants `GetSecretValue` and `DescribeSecret` - no write permissions
2. **Resource Scoping**: Explicitly lists only the required secret ARNs
3. **No Wildcards**: Avoids `*` in resources, preventing access to unrelated secrets
4. **Publishable Key Excluded**: Not included in Lambda policy (frontend-only)

### File: `outputs.tf`

**Purpose**: Exports module values for consumption by other Terraform modules.

**Outputs**:

| Output | Value | Consumers |
|--------|-------|-----------|
| `stripe_secret_key_arn` | Secret ARN | Lambda IAM roles |
| `stripe_webhook_secret_arn` | Secret ARN | Lambda IAM roles |
| `stripe_plus_price_id_arn` | Secret ARN | Lambda IAM roles |
| `stripe_publishable_key_arn` | Secret ARN | Frontend build |
| `stripe_*_name` | Secret names | Lambda environment variables |
| `stripe_secrets_policy_arn` | IAM Policy ARN | Lambda execution roles |
| `token_limit_plus` | 2000000 | Lambda environment variables |

---

## Integration Points

### With Lambda Module
The IAM policy ARN is attached to Lambda execution roles:
```hcl
# In modules/lambda/main.tf
resource "aws_iam_role_policy_attachment" "stripe_secrets" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = module.stripe.stripe_secrets_policy_arn
}
```

### With Environment Configuration
Secret names are passed as Lambda environment variables:
```hcl
# In environments/dev/main.tf
module "stripe" {
  source      = "../../modules/stripe"
  environment = var.environment
  common_tags = local.common_tags
}
```

---

## Verification Gates Passed

| Gate | Command | Status |
|------|---------|--------|
| Terraform Validate | `terraform validate` | PASSED |
| Module Structure | File existence check | PASSED |
| IAM Policy Syntax | Policy document validation | PASSED |

---

## Security Considerations

1. **Secret Rotation**: Secrets can be rotated via AWS Console without Terraform changes (due to `ignore_changes`)
2. **Environment Isolation**: Each environment has its own set of secrets
3. **Audit Trail**: AWS CloudTrail logs all secret access attempts
4. **No Hardcoded Values**: All secrets are managed externally, never in code

---

## Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `modules/stripe/main.tf` | 15 | Module configuration and locals |
| `modules/stripe/variables.tf` | 65 | Input variable definitions |
| `modules/stripe/secrets.tf` | 75 | Secrets Manager resources |
| `modules/stripe/iam.tf` | 30 | IAM policy for Lambda access |
| `modules/stripe/outputs.tf` | 85 | Module output exports |

**Total**: 5 files, ~270 lines of Terraform HCL

---

## Next Steps (Phase C)

Phase A infrastructure is ready for:
1. Integration into `environments/dev/main.tf`
2. Lambda execution role policy attachment
3. Manual secret population via AWS Console or CI/CD
