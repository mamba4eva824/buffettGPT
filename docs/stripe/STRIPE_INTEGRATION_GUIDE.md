# Stripe Payment Integration - GSD Implementation Guide

> **Version:** 1.4
> **Created:** 2026-02-01
> **Updated:** 2026-02-02
> **Status:** Phase E Complete (Frontend Integration)

### Changelog
- v1.4: Phase E complete - Frontend components for subscription management
- v1.3: Phase D complete - Created Stripe product and price via MCP
- v1.2: Added MCP server integration (Stripe MCP + Terraform MCP) for assisted implementation
- v1.1: Updated secrets naming convention to `{service}-{key-type}-{env}` pattern
- v1.0: Initial GSD implementation guide

---

## Executive Summary

Integrate Stripe payment processing to enable users to purchase the **BuffettGPT Plus** subscription in exchange for **2,000,000 tokens/month** for the follow-up analysis agent.

### Product Offering

| Plan | Price | Token Limit | Features |
|------|-------|-------------|----------|
| Free | $0 | 0 | Investment reports only (no follow-up) |
| Plus | $10/month | 2,000,000 | Follow-up questions, message history, priority |

---

## GSD PHASE 1: Audit Snapshot

### Knowns / Evidence

1. **Token tracking system exists** - `TokenUsageTracker` in [token_usage_tracker.py](../../src/utils/token_usage_tracker.py)
2. **Anniversary-based billing** - Users' usage resets on subscription day, not calendar month
3. **DynamoDB tables exist** - `token-usage`, `users` tables ready for extension
4. **Tier system implemented** - `subscription_tier` field already in schema
5. **Auth flow works** - Google OAuth → JWT with user claims
6. **Terraform modules structured** - Easy to add new `stripe` module

### Unknowns / Gaps

| Gap | Resolution Strategy |
|-----|---------------------|
| Stripe account setup | Use Stripe MCP to create products/prices |
| Webhook signature verification | Use `stripe` Python library |
| Proration handling | Let Stripe handle automatically |
| Failed payment grace period | Configure in Stripe subscription settings |
| Refund policy | Define in AC (suggest: no partial refunds) |

### Constraints

- **Terraform-first deployment** - All infrastructure via IaC
- **Lambda build path** - All zips to `chat-api/backend/build/`
- **Python 3.11** - Must match existing runtime
- **No API mode for reports** - Stripe integration is backend only

### Risks

| Risk | Mitigation |
|------|------------|
| Webhook delivery failures | Implement idempotency keys, retry logic |
| Race condition on tier update | Use DynamoDB conditional writes |
| Stripe API key exposure | Store in Secrets Manager, never in code |

---

## GSD PHASE 2: Product Requirements Document (PRD)

### Acceptance Criteria

#### AC-1: Checkout Flow
```
GIVEN a logged-in free user
WHEN they click "Upgrade to Plus" and complete Stripe Checkout
THEN their subscription_tier becomes "plus" within 5 seconds
AND their token_limit is set to 2,000,000
AND their billing_day is set to today's date
```

#### AC-2: Token Limit Enforcement
```
GIVEN a Plus subscriber with 2,000,000 token limit
WHEN they use the follow-up agent
THEN tokens are tracked correctly (input + output)
AND they receive 80%/90%/100% threshold notifications
AND requests are blocked when limit exceeded
```

#### AC-3: Webhook Processing
```
GIVEN Stripe sends a webhook event
WHEN the event is checkout.session.completed
THEN the user's subscription is activated
AND the webhook returns 200 within 30 seconds
AND duplicate webhooks are handled idempotently
```

#### AC-4: Subscription Cancellation
```
GIVEN an active Plus subscriber
WHEN they cancel via Customer Portal
THEN they retain access until period end
AND subscription_tier reverts to "free" after period end
AND token_limit becomes 0 for next billing period
```

#### AC-5: Monthly Renewal
```
GIVEN an active Plus subscriber on billing day
WHEN Stripe charges successfully (invoice.payment_succeeded)
THEN token usage resets for new billing period
AND billing_day remains unchanged (anniversary-based)
```

#### AC-6: Failed Payment Handling
```
GIVEN a Plus subscriber with failed payment
WHEN payment fails (invoice.payment_failed)
THEN subscription_status becomes "past_due"
AND user retains access for 7-day grace period
AND user receives notification to update payment
```

#### AC-7: Customer Portal Access
```
GIVEN a Plus subscriber
WHEN they click "Manage Subscription"
THEN they are redirected to Stripe Customer Portal
AND they can update payment method
AND they can cancel subscription
```

#### AC-8: Frontend Usage Display
```
GIVEN any authenticated user
WHEN they view the app
THEN they see their current plan (Free/Plus)
AND Plus users see token usage bar
AND Free users see upgrade prompt
```

---

## GSD PHASE 3: Implementation Plan

### Objective
Implement Stripe subscription payments to monetize the follow-up analysis feature with a 2M token/month Plus plan.

### Approach Summary
Create a new Stripe Terraform module for infrastructure, add webhook and subscription Lambda handlers, extend the users table schema, and update the frontend with upgrade flows. Use Stripe MCP tools for product/price creation in test mode.

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           STRIPE INTEGRATION                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  FRONTEND (React)                                                       │
│  ┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    │
│  │ UpgradeBanner   │───▶│ PricingModal     │───▶│ Stripe Checkout │    │
│  │ (token limit)   │    │ (Plus $10/mo)  │    │ (hosted page)   │    │
│  └─────────────────┘    └──────────────────┘    └────────┬────────┘    │
│                                                           │             │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                           │             │
│  API GATEWAY                                              │             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ POST /subscription/checkout    → subscription_handler.py        │   │
│  │ POST /subscription/portal      → subscription_handler.py        │   │
│  │ GET  /subscription/status      → subscription_handler.py        │   │
│  │ POST /stripe/webhook           → stripe_webhook_handler.py      │◀──┘   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                          │                              │
│  ═══════════════════════════════════════════════════════════════════   │
│                                          │                              │
│  LAMBDA HANDLERS                         ▼                              │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ stripe_webhook_handler.py                                         │  │
│  │ ├── verify_signature(payload, sig_header, webhook_secret)        │  │
│  │ ├── handle_checkout_completed(session) → activate subscription   │  │
│  │ ├── handle_invoice_paid(invoice) → reset token usage             │  │
│  │ ├── handle_invoice_failed(invoice) → set past_due status         │  │
│  │ └── handle_subscription_deleted(sub) → downgrade to free         │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                          │                              │
│  ═══════════════════════════════════════════════════════════════════   │
│                                          ▼                              │
│  DYNAMODB                                                               │
│  ┌────────────────────────┐    ┌────────────────────────────────────┐  │
│  │ users                  │    │ token-usage                         │  │
│  │ + stripe_customer_id   │    │ (existing - no schema changes)      │  │
│  │ + stripe_subscription_id│    │ token_limit updated via code        │  │
│  │ + subscription_tier    │    │ billing_day set on activation       │  │
│  │ + subscription_status  │    └────────────────────────────────────┘  │
│  │ + billing_day          │                                            │
│  └────────────────────────┘                                            │
│                                                                         │
│  ═══════════════════════════════════════════════════════════════════   │
│                                                                         │
│  SECRETS MANAGER                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ stripe-secret-key-{env}       (sk_live_... / sk_test_...)       │   │
│  │ stripe-webhook-secret-{env}   (whsec_...)                       │   │
│  │ stripe-plus-price-id-{env}    (price_xxx)                       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Files to Create/Modify

#### New Files
| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/stripe_webhook_handler.py` | Process Stripe webhook events |
| `chat-api/backend/src/handlers/subscription_handler.py` | Checkout/portal/status endpoints |
| `chat-api/backend/src/utils/stripe_service.py` | Stripe API wrapper |
| `chat-api/terraform/modules/stripe/main.tf` | Module entry, locals |
| `chat-api/terraform/modules/stripe/secrets.tf` | Secrets Manager resources |
| `chat-api/terraform/modules/stripe/lambda.tf` | Webhook Lambda |
| `chat-api/terraform/modules/stripe/api-gateway.tf` | Routes |
| `chat-api/terraform/modules/stripe/iam.tf` | IAM policies |
| `chat-api/terraform/modules/stripe/variables.tf` | Module variables |
| `chat-api/terraform/modules/stripe/outputs.tf` | Module outputs |
| `frontend/src/components/UpgradeBanner.jsx` | Upgrade prompt component |
| `frontend/src/components/PricingModal.jsx` | Pricing display |
| `frontend/src/api/subscriptionApi.js` | Subscription API client |

#### Modified Files
| File | Changes |
|------|---------|
| `chat-api/terraform/environments/dev/main.tf` | Add stripe module |
| `chat-api/terraform/modules/lambda/main.tf` | Add new Lambda definitions |
| `chat-api/terraform/modules/api-gateway/main.tf` | Add subscription routes |
| `chat-api/backend/src/utils/token_usage_tracker.py` | Add `update_subscription()` method |
| `chat-api/backend/scripts/build_lambdas.sh` | Add new handlers |
| `frontend/src/App.jsx` | Integrate upgrade banner |
| `frontend/.env.example` | Add VITE_STRIPE_PUBLISHABLE_KEY |

---

## GSD PHASE 4: Task Graph

### Task Breakdown (TodoWrite Format)

```
PHASE A: Infrastructure Foundation [Terraform MCP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
A1. Create Stripe Terraform module structure
    Files: terraform/modules/stripe/*.tf
    MCP: Terraform MCP (get_resource_docs, terraform_fmt)
    Verify: terraform validate

A2. Add Secrets Manager resources for Stripe keys
    Files: stripe/secrets.tf
    MCP: Terraform MCP (suggest_best_practices)
    Verify: terraform plan shows secret resources

A3. Create IAM policies for Stripe Lambda access
    Files: stripe/iam.tf
    MCP: Terraform MCP (terraform_validate)
    Verify: terraform validate

PHASE B: Backend Handlers [Stripe MCP for docs]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
B1. Create stripe_service.py utility
    Files: src/utils/stripe_service.py
    MCP: Stripe MCP (search_stripe_documentation)
    Verify: Unit tests pass

B2. Create stripe_webhook_handler.py
    Files: src/handlers/stripe_webhook_handler.py
    MCP: Stripe MCP (search_stripe_documentation for webhook events)
    Verify: Unit tests pass, handles all event types

B3. Create subscription_handler.py
    Files: src/handlers/subscription_handler.py
    MCP: Stripe MCP (search_stripe_documentation for Checkout Sessions)
    Verify: Unit tests pass

B4. Update token_usage_tracker.py with update_subscription()
    Files: src/utils/token_usage_tracker.py
    MCP: None
    Verify: Unit tests pass, existing tests still pass

B5. Update build_lambdas.sh for new handlers
    Files: scripts/build_lambdas.sh
    MCP: None
    Verify: ./scripts/build_lambdas.sh succeeds

PHASE C: Terraform Integration [Terraform MCP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
C1. Add Lambda definitions for new handlers
    Files: modules/lambda/main.tf
    MCP: Terraform MCP (terraform_validate)
    Verify: terraform validate

C2. Add API Gateway routes for subscription endpoints
    Files: modules/api-gateway/main.tf
    MCP: Terraform MCP (terraform_validate)
    Verify: terraform validate

C3. Integrate stripe module in dev environment
    Files: environments/dev/main.tf
    MCP: Terraform MCP (terraform_plan)
    Verify: terraform plan succeeds

C4. Deploy infrastructure to dev
    MCP: Terraform MCP (terraform_apply)
    Verify: terraform apply succeeds, endpoints respond

PHASE D: Stripe Configuration [Stripe MCP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
D1. Create BuffettGPT Plus product in Stripe
    MCP: Stripe MCP (create_product, list_products)
    Verify: Product visible in Stripe Dashboard

D2. Create $10/month price for Plus product
    MCP: Stripe MCP (create_price, list_prices)
    Verify: Price attached to product

D3. Configure Customer Portal settings
    MCP: Stripe MCP (manual via Dashboard - MCP doesn't support portal config)
    Verify: Portal allows payment update + cancellation

D4. Register webhook endpoint in Stripe
    MCP: Stripe MCP (manual via Dashboard or CLI)
    Verify: Webhook shows "Active" status

PHASE E: Frontend Integration [No MCP]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
E1. Create subscriptionApi.js
    Files: frontend/src/api/subscriptionApi.js
    MCP: None
    Verify: npm run lint passes

E2. Create UpgradeBanner component
    Files: frontend/src/components/UpgradeBanner.jsx
    MCP: None
    Verify: npm run lint passes

E3. Create PricingModal component
    Files: frontend/src/components/PricingModal.jsx
    MCP: None
    Verify: npm run lint passes

E4. Integrate components into App.jsx
    Files: frontend/src/App.jsx
    MCP: None
    Verify: npm run lint && npm run build

PHASE F: Testing & Validation [Stripe MCP for test data]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
F1. Write unit tests for stripe_service.py
    Files: tests/unit/test_stripe_service.py
    MCP: None
    Verify: make test passes

F2. Write unit tests for webhook handler
    Files: tests/unit/test_stripe_webhook.py
    MCP: None
    Verify: make test passes

F3. End-to-end test with Stripe test mode
    MCP: Stripe MCP (create_customer, create_subscription for test data)
    Verify: Full checkout flow works

F4. Test webhook event handling
    MCP: Stripe MCP (trigger test webhooks via CLI)
    Verify: All AC scenarios pass
```

### Dependency Graph

```
A1 ──┬──▶ A2 ──▶ A3 ──┐
     │                │
     └────────────────┴──▶ C1 ──▶ C2 ──▶ C3 ──▶ C4
                                              │
B1 ──▶ B2 ──┬──▶ B3 ──▶ B4 ──▶ B5 ───────────┘
            │                                 │
            └─────────────────────────────────┤
                                              │
D1 ──▶ D2 ──▶ D3 ──▶ D4 ─────────────────────┤
                                              │
E1 ──▶ E2 ──▶ E3 ──▶ E4 ─────────────────────┤
                                              │
                                              ▼
                              F1 ──▶ F2 ──▶ F3 ──▶ F4
```

### Parallelization Opportunities

| Parallel Group | Tasks |
|----------------|-------|
| Group 1 | A1 + B1 + D1 + E1 (no dependencies) |
| Group 2 | A2 + B2 (after A1, B1) |
| Group 3 | E2 + E3 (after E1) |

---

## GSD PHASE 5: Self-Critique (Red Team)

### Fragile Assumptions

| Assumption | Risk | Mitigation |
|------------|------|------------|
| Webhook delivery is reliable | Stripe may retry, causing duplicates | Implement idempotency via event ID |
| User stays on same browser after checkout | Session may be lost | Use `client_reference_id` to link user |
| Token limit update is atomic | Race with concurrent requests | Use DynamoDB conditional expressions |

### Failure Modes

1. **Webhook endpoint unreachable** → Stripe retries for 72 hours, user stuck in "pending"
   - *Mitigation:* Add manual verification endpoint, dashboard status check

2. **Stripe customer creation fails** → User charged but not activated
   - *Mitigation:* Create customer BEFORE checkout session

3. **User cancels but token-usage not updated** → User retains access
   - *Mitigation:* Check subscription status on each API call (belt + suspenders)

### Simplest 80% Value Version

**MVP Scope:**
- Checkout flow only (no customer portal initially)
- Webhook handles only: `checkout.session.completed`, `customer.subscription.deleted`
- No failed payment grace period (immediate downgrade)
- No upgrade banner (just a settings page link)

---

## MCP Server Integration

This implementation uses two MCP servers for AI-assisted development:

### 1. Stripe MCP Server

**Purpose:** Create and manage Stripe resources (products, prices, customers, subscriptions)

**Start Command:**
```bash
cd chat-api && source .env && npx -y @stripe/mcp --tools=all --api-key=$STRIPE_SECRET_KEY
```

**Available Tools:**

| Tool | Purpose | Used In Phase |
|------|---------|---------------|
| `create_product` | Create BuffettGPT Plus product | D1 |
| `create_price` | Create $10/month recurring price | D2 |
| `list_products` / `list_prices` | Verify creation | D1, D2 |
| `create_customer` | Create customer on first checkout | Testing |
| `list_customers` | Debug customer lookups | Testing |
| `create_subscription` | Programmatic subscription creation | Testing |
| `list_subscriptions` | Query subscription status | Testing |
| `cancel_subscription` | Handle cancellations | Testing |
| `update_subscription` | Modify subscription details | Testing |
| `search_stripe_documentation` | Query Stripe docs for implementation help | All |

### 2. Terraform MCP Server

**Purpose:** Assist with Terraform resource creation, validation, and best practices

**Start Command:**
```bash
npx -y @anthropic/terraform-mcp-server
```

**Available Tools:**

| Tool | Purpose | Used In Phase |
|------|---------|---------------|
| `terraform_validate` | Validate Terraform configuration | A1-A3, C1-C3 |
| `terraform_plan` | Preview infrastructure changes | C3, C4 |
| `terraform_apply` | Apply infrastructure changes | C4 |
| `terraform_fmt` | Format Terraform files | A1-A3 |
| `get_resource_docs` | Get Terraform provider documentation | A1-A3 |
| `suggest_best_practices` | Get IaC best practices | A1-A3 |

### MCP Server Requirements

Both servers should be running during RALF execution:

```bash
# Terminal 1: Stripe MCP
cd chat-api && source .env && npx -y @stripe/mcp --tools=all --api-key=$STRIPE_SECRET_KEY

# Terminal 2: Terraform MCP (optional - for assisted Terraform development)
npx -y @anthropic/terraform-mcp-server
```

### Phase-to-MCP Mapping

| Phase | Primary MCP | Secondary MCP |
|-------|-------------|---------------|
| A (Infrastructure) | Terraform MCP | - |
| B (Backend Handlers) | - | Stripe MCP (docs) |
| C (Terraform Integration) | Terraform MCP | - |
| D (Stripe Configuration) | Stripe MCP | - |
| E (Frontend) | - | - |
| F (Testing) | - | Stripe MCP (test data) |

---

## Environment Variables

### Backend (Lambda)
```bash
STRIPE_SECRET_KEY_ARN=arn:aws:secretsmanager:...:stripe-secret-key-dev
STRIPE_WEBHOOK_SECRET_ARN=arn:aws:secretsmanager:...:stripe-webhook-secret-dev
STRIPE_PLUS_PRICE_ID_ARN=arn:aws:secretsmanager:...:stripe-plus-price-id-dev
TOKEN_LIMIT_PLUS=2000000
```

### Frontend
```bash
VITE_STRIPE_PUBLISHABLE_KEY=pk_test_xxx
```

---

## Secrets Manager Naming Convention

### Pattern
```
{service}-{key-type}-{environment}
```

### Stripe Secrets

| Secret Name | Content | Description |
|-------------|---------|-------------|
| `stripe-secret-key-dev` | `sk_test_xxx` | Stripe API secret key (test mode) |
| `stripe-secret-key-prod` | `sk_live_xxx` | Stripe API secret key (live mode) |
| `stripe-webhook-secret-dev` | `whsec_xxx` | Webhook signing secret (test) |
| `stripe-webhook-secret-prod` | `whsec_xxx` | Webhook signing secret (live) |
| `stripe-plus-price-id-dev` | `price_xxx` | Plus plan price ID (test) |
| `stripe-plus-price-id-prod` | `price_xxx` | Plus plan price ID (live) |
| `stripe-publishable-key-dev` | `pk_test_xxx` | Frontend publishable key (test) |
| `stripe-publishable-key-prod` | `pk_live_xxx` | Frontend publishable key (live) |

### Terraform Variable Reference
```hcl
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

# Secret names use simple pattern
locals {
  stripe_secret_key_name      = "stripe-secret-key-${var.environment}"
  stripe_webhook_secret_name  = "stripe-webhook-secret-${var.environment}"
  stripe_plus_price_id_name   = "stripe-plus-price-id-${var.environment}"
  stripe_publishable_key_name = "stripe-publishable-key-${var.environment}"
}
```

### Why This Convention?

1. **Service-first** - Easy to find all Stripe secrets with `stripe-*` prefix
2. **Environment suffix** - Clear separation between dev/staging/prod
3. **No project prefix** - Simpler names, project context implied by AWS account
4. **Consistent pattern** - Same scheme can apply to other services:
   - `fmp-api-key-{env}` (Financial Modeling Prep)
   - `google-oauth-{env}` (Google OAuth)
   - `jwt-secret-{env}` (JWT signing)

---

## Terraform Module Structure

### Directory Layout
```
chat-api/terraform/modules/stripe/
├── main.tf           # Locals, data sources
├── secrets.tf        # Secrets Manager resources
├── iam.tf            # IAM policies for Lambda access
├── variables.tf      # Module inputs
└── outputs.tf        # Module outputs
```

### secrets.tf (Full Implementation)
```hcl
# =============================================================================
# Stripe Secrets Manager Resources
# Naming convention: {service}-{key-type}-{environment}
# =============================================================================

locals {
  stripe_secret_key_name      = "stripe-secret-key-${var.environment}"
  stripe_webhook_secret_name  = "stripe-webhook-secret-${var.environment}"
  stripe_plus_price_id_name   = "stripe-plus-price-id-${var.environment}"
  stripe_publishable_key_name = "stripe-publishable-key-${var.environment}"
}

# -----------------------------------------------------------------------------
# Stripe Secret Key (sk_test_xxx / sk_live_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_secret_key" {
  name        = local.stripe_secret_key_name
  description = "Stripe API secret key for ${var.environment} environment"

  tags = merge(var.common_tags, {
    Name        = local.stripe_secret_key_name
    Service     = "stripe"
    Environment = var.environment
  })
}

# Note: Secret value must be set manually or via CI/CD
# Do not store actual keys in Terraform state
resource "aws_secretsmanager_secret_version" "stripe_secret_key" {
  count         = var.stripe_secret_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_secret_key.id
  secret_string = var.stripe_secret_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Webhook Secret (whsec_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_webhook_secret" {
  name        = local.stripe_webhook_secret_name
  description = "Stripe webhook signing secret for ${var.environment} environment"

  tags = merge(var.common_tags, {
    Name        = local.stripe_webhook_secret_name
    Service     = "stripe"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_webhook_secret" {
  count         = var.stripe_webhook_secret != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_webhook_secret.id
  secret_string = var.stripe_webhook_secret

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Plus Price ID (price_xxx)
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_plus_price_id" {
  name        = local.stripe_plus_price_id_name
  description = "Stripe Plus plan price ID for ${var.environment} environment"

  tags = merge(var.common_tags, {
    Name        = local.stripe_plus_price_id_name
    Service     = "stripe"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_plus_price_id" {
  count         = var.stripe_plus_price_id != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_plus_price_id.id
  secret_string = var.stripe_plus_price_id

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# -----------------------------------------------------------------------------
# Stripe Publishable Key (pk_test_xxx / pk_live_xxx)
# This is public, but stored in Secrets Manager for consistency
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "stripe_publishable_key" {
  name        = local.stripe_publishable_key_name
  description = "Stripe publishable key for ${var.environment} environment"

  tags = merge(var.common_tags, {
    Name        = local.stripe_publishable_key_name
    Service     = "stripe"
    Environment = var.environment
  })
}

resource "aws_secretsmanager_secret_version" "stripe_publishable_key" {
  count         = var.stripe_publishable_key != "" ? 1 : 0
  secret_id     = aws_secretsmanager_secret.stripe_publishable_key.id
  secret_string = var.stripe_publishable_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}
```

### variables.tf
```hcl
variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default     = {}
}

# Optional: Pass secrets via CI/CD or set manually
variable "stripe_secret_key" {
  description = "Stripe API secret key (optional, can be set manually)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_webhook_secret" {
  description = "Stripe webhook signing secret (optional, can be set manually)"
  type        = string
  default     = ""
  sensitive   = true
}

variable "stripe_plus_price_id" {
  description = "Stripe Plus plan price ID (optional, can be set manually)"
  type        = string
  default     = ""
}

variable "stripe_publishable_key" {
  description = "Stripe publishable key (optional, can be set manually)"
  type        = string
  default     = ""
}

variable "token_limit_plus" {
  description = "Monthly token limit for Plus subscribers"
  type        = number
  default     = 2000000
}
```

### outputs.tf
```hcl
output "stripe_secret_key_arn" {
  description = "ARN of the Stripe secret key secret"
  value       = aws_secretsmanager_secret.stripe_secret_key.arn
}

output "stripe_secret_key_name" {
  description = "Name of the Stripe secret key secret"
  value       = aws_secretsmanager_secret.stripe_secret_key.name
}

output "stripe_webhook_secret_arn" {
  description = "ARN of the Stripe webhook secret"
  value       = aws_secretsmanager_secret.stripe_webhook_secret.arn
}

output "stripe_webhook_secret_name" {
  description = "Name of the Stripe webhook secret"
  value       = aws_secretsmanager_secret.stripe_webhook_secret.name
}

output "stripe_plus_price_id_arn" {
  description = "ARN of the Stripe Plus price ID secret"
  value       = aws_secretsmanager_secret.stripe_plus_price_id.arn
}

output "stripe_plus_price_id_name" {
  description = "Name of the Stripe Plus price ID secret"
  value       = aws_secretsmanager_secret.stripe_plus_price_id.name
}

output "stripe_publishable_key_arn" {
  description = "ARN of the Stripe publishable key secret"
  value       = aws_secretsmanager_secret.stripe_publishable_key.arn
}

output "stripe_publishable_key_name" {
  description = "Name of the Stripe publishable key secret"
  value       = aws_secretsmanager_secret.stripe_publishable_key.name
}

output "token_limit_plus" {
  description = "Token limit for Plus subscribers"
  value       = var.token_limit_plus
}
```

### iam.tf
```hcl
# IAM policy for Lambda to access Stripe secrets
data "aws_iam_policy_document" "stripe_secrets_access" {
  statement {
    sid    = "ReadStripeSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret"
    ]
    resources = [
      aws_secretsmanager_secret.stripe_secret_key.arn,
      aws_secretsmanager_secret.stripe_webhook_secret.arn,
      aws_secretsmanager_secret.stripe_plus_price_id.arn,
    ]
  }
}

resource "aws_iam_policy" "stripe_secrets_access" {
  name        = "stripe-secrets-access-${var.environment}"
  description = "Allow Lambda to read Stripe secrets"
  policy      = data.aws_iam_policy_document.stripe_secrets_access.json

  tags = merge(var.common_tags, {
    Name        = "stripe-secrets-access-${var.environment}"
    Service     = "stripe"
    Environment = var.environment
  })
}

output "stripe_secrets_policy_arn" {
  description = "ARN of the IAM policy for Stripe secrets access"
  value       = aws_iam_policy.stripe_secrets_access.arn
}
```

### Usage in environments/dev/main.tf
```hcl
module "stripe" {
  source = "../../modules/stripe"

  environment = var.environment
  common_tags = local.common_tags

  # Secrets can be passed via CI/CD or set manually in AWS Console
  # stripe_secret_key     = var.stripe_secret_key  # From GitHub Secrets
  # stripe_webhook_secret = var.stripe_webhook_secret
  # stripe_plus_price_id  = var.stripe_plus_price_id

  token_limit_plus = 2000000
}

# Attach policy to Lambda execution role
resource "aws_iam_role_policy_attachment" "lambda_stripe_secrets" {
  role       = module.lambda.execution_role_name
  policy_arn = module.stripe.stripe_secrets_policy_arn
}
```

---

## Manual Secret Setup (AWS CLI)

After Terraform creates the empty secrets, populate them manually:

### Dev Environment (Test Mode)
```bash
# Set Stripe secret key (from Stripe Dashboard → API Keys)
aws secretsmanager put-secret-value \
  --secret-id stripe-secret-key-dev \
  --secret-string "sk_test_xxx"

# Set webhook secret (from Stripe Dashboard → Webhooks → Signing secret)
aws secretsmanager put-secret-value \
  --secret-id stripe-webhook-secret-dev \
  --secret-string "whsec_xxx"

# Set Plus price ID (from Stripe MCP or Dashboard → Products)
aws secretsmanager put-secret-value \
  --secret-id stripe-plus-price-id-dev \
  --secret-string "price_xxx"

# Set publishable key (for frontend builds)
aws secretsmanager put-secret-value \
  --secret-id stripe-publishable-key-dev \
  --secret-string "pk_test_xxx"
```

### Prod Environment (Live Mode)
```bash
aws secretsmanager put-secret-value \
  --secret-id stripe-secret-key-prod \
  --secret-string "sk_live_xxx"

aws secretsmanager put-secret-value \
  --secret-id stripe-webhook-secret-prod \
  --secret-string "whsec_xxx"

aws secretsmanager put-secret-value \
  --secret-id stripe-plus-price-id-prod \
  --secret-string "price_xxx"

aws secretsmanager put-secret-value \
  --secret-id stripe-publishable-key-prod \
  --secret-string "pk_live_xxx"
```

### Verify Secrets
```bash
# List all Stripe secrets
aws secretsmanager list-secrets --filters Key=name,Values=stripe

# Verify a specific secret (dev)
aws secretsmanager get-secret-value \
  --secret-id stripe-secret-key-dev \
  --query SecretString --output text
```

---

## Python Lambda Integration

### stripe_service.py (Secret Fetching)
```python
"""
Stripe service utility for Lambda handlers.
Fetches secrets using the {service}-{key-type}-{env} naming convention.
"""

import os
import json
import boto3
from functools import lru_cache
from botocore.exceptions import ClientError

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Secret names following the convention: {service}-{key-type}-{env}
STRIPE_SECRET_KEY_NAME = f"stripe-secret-key-{ENVIRONMENT}"
STRIPE_WEBHOOK_SECRET_NAME = f"stripe-webhook-secret-{ENVIRONMENT}"
STRIPE_PLUS_PRICE_ID_NAME = f"stripe-plus-price-id-{ENVIRONMENT}"

# Initialize clients
secrets_client = boto3.client('secretsmanager')


@lru_cache(maxsize=4)
def get_secret(secret_name: str) -> str:
    """
    Fetch a secret from Secrets Manager with caching.

    Args:
        secret_name: Name of the secret (e.g., 'stripe-secret-key-dev')

    Returns:
        Secret string value

    Raises:
        ClientError: If secret cannot be fetched
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            raise ValueError(f"Secret '{secret_name}' not found")
        raise


def get_stripe_secret_key() -> str:
    """Get Stripe API secret key (sk_test_xxx or sk_live_xxx)."""
    return get_secret(STRIPE_SECRET_KEY_NAME)


def get_stripe_webhook_secret() -> str:
    """Get Stripe webhook signing secret (whsec_xxx)."""
    return get_secret(STRIPE_WEBHOOK_SECRET_NAME)


def get_stripe_plus_price_id() -> str:
    """Get Stripe Plus plan price ID (price_xxx)."""
    return get_secret(STRIPE_PLUS_PRICE_ID_NAME)


# Initialize Stripe with lazy loading
_stripe_initialized = False

def get_stripe():
    """
    Get initialized Stripe module.
    Lazy loads the secret key on first call.
    """
    global _stripe_initialized
    import stripe

    if not _stripe_initialized:
        stripe.api_key = get_stripe_secret_key()
        _stripe_initialized = True

    return stripe
```

### stripe_webhook_handler.py (Signature Verification)
```python
"""
Stripe webhook handler Lambda.
"""

import json
import logging
from stripe_service import get_stripe, get_stripe_webhook_secret

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Handle Stripe webhook events."""
    stripe = get_stripe()

    # Get raw body and signature header
    payload = event.get('body', '')
    sig_header = event['headers'].get('stripe-signature', '')

    # Verify webhook signature
    try:
        webhook_event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            get_stripe_webhook_secret()
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification failed: {e}")
        return {'statusCode': 400, 'body': 'Invalid signature'}
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return {'statusCode': 400, 'body': 'Invalid payload'}

    # Route event to handler
    event_type = webhook_event['type']
    logger.info(f"Received Stripe event: {event_type}")

    handlers = {
        'checkout.session.completed': handle_checkout_completed,
        'invoice.payment_succeeded': handle_invoice_paid,
        'invoice.payment_failed': handle_invoice_failed,
        'customer.subscription.deleted': handle_subscription_deleted,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(webhook_event['data']['object'])
        except Exception as e:
            logger.error(f"Error handling {event_type}: {e}")
            return {'statusCode': 500, 'body': 'Handler error'}
    else:
        logger.info(f"Unhandled event type: {event_type}")

    return {'statusCode': 200, 'body': 'OK'}


def handle_checkout_completed(session):
    """Activate subscription after successful checkout."""
    # Implementation: Update user's subscription_tier to 'plus'
    pass


def handle_invoice_paid(invoice):
    """Reset token usage on successful renewal."""
    # Implementation: Reset token usage for new billing period
    pass


def handle_invoice_failed(invoice):
    """Handle failed payment - set past_due status."""
    # Implementation: Update subscription_status to 'past_due'
    pass


def handle_subscription_deleted(subscription):
    """Downgrade user to free tier on cancellation."""
    # Implementation: Set subscription_tier to 'free', token_limit to 0
    pass
```

---

## Verification Commands

```bash
# Backend tests
cd chat-api/backend && make test

# Frontend lint
cd frontend && npm run lint

# Terraform validation
cd chat-api/terraform/environments/dev && terraform validate

# Build Lambdas
cd chat-api/backend && ./scripts/build_lambdas.sh

# Full deployment
cd chat-api/terraform/environments/dev && terraform plan -out=tfplan && terraform apply tfplan
```

---

## RALF Execution Process

### Pre-Flight Checklist

Before starting RALF execution, ensure:

- [ ] Stripe MCP server is running (`npx -y @stripe/mcp --tools=all --api-key=$STRIPE_SECRET_KEY`)
- [ ] Stripe test mode API key is in `chat-api/.env`
- [ ] AWS credentials are configured (`aws sts get-caller-identity`)
- [ ] Terraform is initialized in dev environment

### Phase A Execution (Infrastructure Foundation)

**Start MCP:** Stripe MCP (already connected)

**Tasks:**
```
A1 → A2 → A3 (sequential - each builds on previous)
```

**RALF Loop for Each Task:**
1. Mark task `in_progress` in TodoWrite
2. Create/modify Terraform files
3. Run `terraform validate` in `chat-api/terraform/modules/stripe/`
4. If validation fails → fix and retry
5. Mark task `completed`

**Verification Gate:**
```bash
cd chat-api/terraform/modules/stripe && terraform validate
```

### Phase D Execution (Stripe Configuration)

**MCP Tools Required:**
- `create_product` - Create BuffettGPT Plus
- `create_price` - Attach $10/month price

**Example MCP Commands:**
```
# D1: Create product
create_product(name="BuffettGPT Plus", description="2,000,000 tokens/month for follow-up analysis")

# D2: Create price
create_price(product="prod_xxx", unit_amount=999, currency="usd", recurring={interval: "month"})
```

**Store Price ID:**
After creating the price, store the `price_xxx` ID for use in:
- AWS Secrets Manager (`stripe-plus-price-id-dev`)
- Frontend checkout flow

---

## Next Steps

1. **User Approval** - Review this guide and approve/adjust
2. **RALF Execution** - Execute task graph with verification loops
3. **Stripe Setup** - Use MCP tools to create product/price in test mode
4. **Deploy & Test** - Full end-to-end validation in dev environment

---

## Stripe Resource IDs (Test Mode)

**Created via Stripe MCP on 2026-02-02**

| Resource | ID | Details |
|----------|-----|---------|
| Product | `prod_TuI3SR1TMzTPFt` | "Buffett Plus" - Premium subscription |
| Price | `price_1SwTUiGtKkLcbRiapMRnErLu` | $10.00/month recurring |

### Notes
- These are **test mode** IDs - production will require separate creation
- Old $9.99 price (`price_1SwTTxGtKkLcbRiafyq4Jm8X`) should be archived in Stripe Dashboard
- To add metadata (tier, token_limit), update via Stripe Dashboard or API directly

### Store Price ID in AWS Secrets Manager
```bash
aws secretsmanager put-secret-value \
  --secret-id stripe-plus-price-id-dev \
  --secret-string "price_1SwTUiGtKkLcbRiapMRnErLu"
```

---

## Sources

- [Stripe MCP Documentation](https://docs.stripe.com/mcp)
- [Stripe Agent Toolkit](https://docs.stripe.com/agents)
- [Portkey Stripe MCP Integration](https://portkey.ai/docs/integrations/mcp-servers/stripe-mcp-server)
- [Composio Stripe MCP Tools](https://mcp.composio.dev/stripe)
