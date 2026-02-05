# Phase C: Terraform Integration & Deployment

## Executive Summary

Phase C completes the Stripe payment integration by deploying all infrastructure via Terraform. This phase integrates the Stripe module into the dev environment, configures Lambda function definitions for the webhook and subscription handlers, establishes API Gateway routes for all subscription endpoints, and deploys the complete payment infrastructure to AWS.

**Completion Status**: All tasks (C1-C5) completed and verified.

**Deployment Date**: February 2, 2026

**Deployment Result**: 22 resources added, 15 resources changed, 1 destroyed

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Deployed Stripe Infrastructure                          │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │           Frontend (React)            │
                    │     https://dev.buffettgpt.com       │
                    └──────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
    ┌──────────────────────────────┐    ┌──────────────────────────────┐
    │      HTTP API Gateway         │    │      Stripe Dashboard        │
    │  yn9nj0b654.execute-api...   │    │    (Webhook Events)          │
    └──────────────────────────────┘    └──────────────────────────────┘
                    │                               │
    ┌───────────────┴───────────────┐               │
    ▼                               ▼               ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  /subscription  │    │  /stripe        │    │  Webhook URL    │
│  /checkout      │    │  /webhook       │    │  (POST)         │
│  /portal        │    │  (No Auth)      │────│                 │
│  /status        │    │                 │    │                 │
│  (JWT Auth)     │    │                 │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│ subscription_   │    │ stripe_webhook_ │
│ handler         │    │ handler         │
│ (Lambda)        │    │ (Lambda)        │
└─────────────────┘    └─────────────────┘
        │                       │
        └───────────┬───────────┘
                    ▼
    ┌──────────────────────────────┐
    │      AWS Secrets Manager      │
    ├──────────────────────────────┤
    │  stripe-secret-key-dev       │
    │  stripe-webhook-secret-dev   │
    │  stripe-plus-price-id-dev    │
    │  stripe-publishable-key-dev  │
    └──────────────────────────────┘
```

---

## Deployed Endpoints

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/subscription/checkout` | POST | Create Stripe Checkout session | JWT |
| `/subscription/portal` | POST | Create Customer Portal session | JWT |
| `/subscription/status` | GET | Get subscription status | JWT |
| `/stripe/webhook` | POST | Receive Stripe webhook events | None (Stripe Signature) |

**Base URL**: `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev`

**Webhook URL**: `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/stripe/webhook`

---

## Task C1: Lambda Module Configuration

### File: `chat-api/terraform/modules/lambda/main.tf`

**Purpose**: Define Lambda function configurations for Stripe handlers.

**Functions Added**:

```hcl
stripe_webhook_handler = {
  handler     = "stripe_webhook_handler.lambda_handler"
  timeout     = 30
  memory_size = 256
  description = "Stripe webhook event processor"
}
subscription_handler = {
  handler     = "subscription_handler.lambda_handler"
  timeout     = 30
  memory_size = 256
  description = "Subscription checkout, portal, and status API"
}
```

**Configuration Details**:

| Setting | Value | Rationale |
|---------|-------|-----------|
| Timeout | 30s | Allows time for Stripe API calls |
| Memory | 256 MB | Sufficient for Python runtime + boto3 |
| Runtime | Python 3.11 | Matches existing Lambda functions |

### File: `chat-api/terraform/modules/lambda/outputs.tf`

**New Outputs**:

```hcl
output "stripe_webhook_handler_arn" {
  description = "ARN of the Stripe webhook handler function"
  value       = try(aws_lambda_function.functions["stripe_webhook_handler"].arn, null)
}

output "subscription_handler_arn" {
  description = "ARN of the subscription handler function"
  value       = try(aws_lambda_function.functions["subscription_handler"].arn, null)
}
```

**Why `try()` wrapper**: Allows graceful handling when functions are disabled in certain environments.

---

## Task C2: API Gateway Routes

### File: `chat-api/terraform/modules/api-gateway/variables.tf`

**New Variables**:

```hcl
variable "enable_subscription_routes" {
  description = "Enable subscription management routes (checkout, portal, status)"
  type        = bool
  default     = false
}

variable "enable_stripe_webhook" {
  description = "Enable Stripe webhook endpoint"
  type        = bool
  default     = false
}
```

### File: `chat-api/terraform/modules/api-gateway/main.tf`

**Subscription Handler Integration**:

```hcl
resource "aws_apigatewayv2_integration" "subscription_handler_integration" {
  count            = var.enable_subscription_routes ? 1 : 0
  api_id           = aws_apigatewayv2_api.http_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["subscription_handler"]
  payload_format_version = "2.0"
  timeout_milliseconds   = 30000
}
```

**Routes Created**:

| Route | Auth | Purpose |
|-------|------|---------|
| `POST /subscription/checkout` | JWT | Create checkout session |
| `POST /subscription/portal` | JWT | Create portal session |
| `GET /subscription/status` | JWT | Get subscription status |
| `OPTIONS /subscription/checkout` | None | CORS preflight |
| `OPTIONS /subscription/portal` | None | CORS preflight |
| `OPTIONS /subscription/status` | None | CORS preflight |
| `POST /stripe/webhook` | None | Webhook endpoint |

**Webhook Security Note**:

```hcl
resource "aws_apigatewayv2_route" "stripe_webhook" {
  count     = var.enable_stripe_webhook ? 1 : 0
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST /stripe/webhook"
  target    = "integrations/${aws_apigatewayv2_integration.stripe_webhook_integration[0].id}"

  # No authorization - Stripe uses webhook signature verification
  authorization_type = "NONE"
}
```

**Why No Auth**: Stripe webhooks are authenticated via cryptographic signature verification in the Lambda handler, not API Gateway authorization.

**Lambda Permissions**:

```hcl
resource "aws_lambda_permission" "subscription_api_permission" {
  count         = var.enable_subscription_routes ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPISubscription"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["subscription_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

resource "aws_lambda_permission" "stripe_webhook_api_permission" {
  count         = var.enable_stripe_webhook ? 1 : 0
  statement_id  = "AllowExecutionFromHTTPAPIStripeWebhook"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["stripe_webhook_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}
```

---

## Task C3: Environment Integration

### File: `chat-api/terraform/environments/dev/main.tf`

**Stripe Module Integration**:

```hcl
module "stripe" {
  source = "../../modules/stripe"

  environment = local.environment
  common_tags = local.common_tags

  # Token limit for Plus subscribers (2M tokens/month)
  token_limit_plus = 2000000

  # Secrets are set manually in AWS Console after initial deployment
  # See: docs/stripe/STRIPE_INTEGRATION_GUIDE.md for manual secret setup
}
```

**Lambda Environment Variables**:

```hcl
lambda_function_env_vars = {
  # ... existing configs ...

  stripe_webhook_handler = {
    STRIPE_SECRET_KEY_ARN      = module.stripe.stripe_secret_key_arn
    STRIPE_WEBHOOK_SECRET_ARN  = module.stripe.stripe_webhook_secret_arn
    STRIPE_PLUS_PRICE_ID_ARN   = module.stripe.stripe_plus_price_id_arn
    TOKEN_LIMIT_PLUS           = tostring(module.stripe.token_limit_plus)
    USERS_TABLE                = var.enable_authentication ? module.auth[0].users_table_name : ""
  }

  subscription_handler = {
    STRIPE_SECRET_KEY_ARN      = module.stripe.stripe_secret_key_arn
    STRIPE_PLUS_PRICE_ID_ARN   = module.stripe.stripe_plus_price_id_arn
    STRIPE_PUBLISHABLE_KEY_ARN = module.stripe.stripe_publishable_key_arn
    USERS_TABLE                = var.enable_authentication ? module.auth[0].users_table_name : ""
  }
}
```

**Environment Variable Summary**:

| Handler | Variable | Source |
|---------|----------|--------|
| webhook | `STRIPE_SECRET_KEY_ARN` | Secrets Manager |
| webhook | `STRIPE_WEBHOOK_SECRET_ARN` | Secrets Manager |
| webhook | `STRIPE_PLUS_PRICE_ID_ARN` | Secrets Manager |
| webhook | `TOKEN_LIMIT_PLUS` | Module output (2000000) |
| webhook | `USERS_TABLE` | Auth module |
| subscription | `STRIPE_SECRET_KEY_ARN` | Secrets Manager |
| subscription | `STRIPE_PLUS_PRICE_ID_ARN` | Secrets Manager |
| subscription | `STRIPE_PUBLISHABLE_KEY_ARN` | Secrets Manager |
| subscription | `USERS_TABLE` | Auth module |

---

## Task C4: IAM Policy Attachment

### File: `chat-api/terraform/environments/dev/main.tf`

**Secrets Access Policy**:

```hcl
resource "aws_iam_role_policy_attachment" "lambda_stripe_secrets" {
  role       = module.core.lambda_role_name
  policy_arn = module.stripe.stripe_secrets_policy_arn
}
```

**Policy Grants**:

| Permission | Resources |
|------------|-----------|
| `secretsmanager:GetSecretValue` | stripe-secret-key-dev, stripe-webhook-secret-dev, stripe-plus-price-id-dev |
| `secretsmanager:DescribeSecret` | stripe-secret-key-dev, stripe-webhook-secret-dev, stripe-plus-price-id-dev |

**Security Note**: Publishable key is NOT included in the Lambda policy (frontend-only).

---

## Task C5: API Gateway Module Update

### File: `chat-api/terraform/environments/dev/main.tf`

**Module Configuration**:

```hcl
module "api_gateway" {
  source = "../../modules/api-gateway"

  # ... existing configuration ...

  # Subscription/Stripe API (checkout, portal, status, webhook)
  enable_subscription_routes = true
  enable_stripe_webhook      = true

  common_tags = local.common_tags
}
```

---

## Deployment Summary

### Build Phase

```bash
cd chat-api/backend
./scripts/build_lambdas.sh
```

**Build Output**:
```
chat-api/backend/build/
├── stripe_webhook_handler.zip    (58K)
└── subscription_handler.zip      (57K)
```

### Terraform Apply

**Command**: `terraform apply -auto-approve`

**Result**:
```
Plan: 22 to add, 15 to change, 1 to destroy.

Apply complete! Resources: 22 added, 15 changed, 1 destroyed.
```

### Resources Created

| Resource Type | Count | Examples |
|---------------|-------|----------|
| Lambda Functions | 2 | buffett-dev-stripe-webhook-handler, buffett-dev-subscription-handler |
| CloudWatch Log Groups | 2 | /aws/lambda/buffett-dev-stripe-webhook-handler |
| API Gateway Routes | 7 | POST /subscription/checkout, POST /stripe/webhook |
| API Gateway Integrations | 2 | Subscription handler, Webhook handler |
| Lambda Permissions | 2 | API Gateway invoke permissions |
| Secrets Manager Secrets | 4 | stripe-secret-key-dev, etc. |
| IAM Policy | 1 | stripe-secrets-access-dev |

---

## Verification Gates Passed

| Gate | Command | Status |
|------|---------|--------|
| Terraform Validate | `terraform validate` | PASSED |
| Terraform Plan | `terraform plan` | PASSED (22 add, 15 change) |
| Terraform Apply | `terraform apply` | PASSED |
| Lambda Build | `./scripts/build_lambdas.sh` | PASSED |
| HTTP API Endpoint | API Gateway created | PASSED |

---

## Deployed Lambda Functions

### buffett-dev-stripe-webhook-handler

| Setting | Value |
|---------|-------|
| ARN | `arn:aws:lambda:us-east-1:*:function:buffett-dev-stripe-webhook-handler` |
| Runtime | Python 3.11 |
| Memory | 256 MB |
| Timeout | 30 seconds |
| Handler | `stripe_webhook_handler.lambda_handler` |

### buffett-dev-subscription-handler

| Setting | Value |
|---------|-------|
| ARN | `arn:aws:lambda:us-east-1:*:function:buffett-dev-subscription-handler` |
| Runtime | Python 3.11 |
| Memory | 256 MB |
| Timeout | 30 seconds |
| Handler | `subscription_handler.lambda_handler` |

---

## Files Modified

| File | Action | Description |
|------|--------|-------------|
| `modules/lambda/main.tf` | Modified | Added Stripe Lambda definitions |
| `modules/lambda/outputs.tf` | Modified | Added ARN outputs for new functions |
| `modules/api-gateway/variables.tf` | Modified | Added subscription/webhook enable flags |
| `modules/api-gateway/main.tf` | Modified | Added routes, integrations, permissions |
| `environments/dev/main.tf` | Modified | Integrated Stripe module, added env vars |

**Total Changes**: 5 files, ~200 lines of Terraform HCL

---

## Commit Information

**Commit Hash**: `8d48b4f`

**Commit Message**:
```
feat: Stripe payment integration (Phase A-C)

- Add Stripe Terraform module with Secrets Manager resources
- Create webhook handler for subscription lifecycle events
- Create subscription handler for checkout, portal, and status APIs
- Integrate Stripe module into dev environment
- Add API Gateway routes for subscription endpoints
- Configure Lambda environment variables for Stripe secrets

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
```

**Files Changed**: 14 files, 1,590 additions

---

## Post-Deployment Setup Required

### Manual Secret Population

The following secrets must be populated in AWS Secrets Manager before the integration is functional:

| Secret Name | Value Type | Source |
|-------------|------------|--------|
| `stripe-secret-key-dev` | `sk_test_*` | Stripe Dashboard > API Keys |
| `stripe-webhook-secret-dev` | `whsec_*` | Stripe Dashboard > Webhooks |
| `stripe-plus-price-id-dev` | `price_*` | Stripe Dashboard > Products |
| `stripe-publishable-key-dev` | `pk_test_*` | Stripe Dashboard > API Keys |

### Stripe Dashboard Configuration

1. **Create Webhook Endpoint**:
   - URL: `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/stripe/webhook`
   - Events: `checkout.session.completed`, `invoice.payment_succeeded`, `invoice.payment_failed`, `customer.subscription.deleted`, `customer.subscription.updated`

2. **Create Plus Product**:
   - Name: "BuffettGPT Plus"
   - Price: $9.99/month (or desired amount)
   - Copy Price ID to secrets

3. **Configure Customer Portal**:
   - Enable subscription cancellation
   - Enable payment method updates

---

## Security Considerations

1. **Webhook Security**: No API Gateway authorization; relies on Stripe signature verification
2. **Secret Rotation**: Terraform configured with `ignore_changes` to support manual rotation
3. **Least Privilege**: Lambda only has read access to required secrets
4. **Environment Isolation**: Separate secrets for dev/staging/prod

---

## Phase Summary

| Phase | Focus | Status |
|-------|-------|--------|
| Phase A | Infrastructure Foundation | Complete |
| Phase B | Backend Handlers | Complete |
| **Phase C** | **Terraform Integration** | **Complete** |

---

## Next Steps (Phase D: Frontend Integration)

1. Add Stripe.js to frontend
2. Implement checkout button component
3. Add subscription status display
4. Handle success/cancel redirects
5. Integrate customer portal link
