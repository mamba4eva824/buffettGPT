# Stripe Cancellation & Payment Update Testing Guide

> **Purpose:** E2E integration testing of subscription cancellation and update flows
> **Workflow:** RALF (Review-Audit-Loop-Fix)
> **Tools:** Stripe MCP Server + AWS CLI for DynamoDB verification

---

## Changelog

| Date | Change | Details |
|------|--------|---------|
| 2026-02-04 | **RESOLVED: MCP account mismatch** | Configured local Stripe MCP server (`~/.cursor/mcp.json`) to use API key from Secrets Manager instead of OAuth. |
| 2026-02-04 | **RESOLVED: Tier sync fix** | Added `_sync_subscription_tier()` helper to sync tier to both users and token-usage tables. Updated `handle_subscription_updated()` and `handle_subscription_deleted()`. |
| 2026-02-04 | Added `stripe-customer-index` GSI | Required for webhook handler to find users by `stripe_customer_id`. Added to `chat-api/terraform/modules/auth/main.tf` |
| 2026-02-04 | Created webhook endpoint | Registered webhook endpoint `we_1SxBrKGi2AjXTZZZEaaek0bT` in Stripe account `acct_1SwRZ2Gi2AjXTZZZ` |
| 2026-02-04 | Updated webhook secret | Synced `stripe-webhook-secret-dev` in AWS Secrets Manager with new endpoint secret |
| 2026-02-04 | Documented known issue | `subscription.updated` handler doesn't sync `subscription_tier` - **RESOLVED** |

---

## Prerequisites

### Stripe MCP Server
This guide uses the Stripe MCP tools available in Claude Code. Verify access:
```
mcp__stripe__get_stripe_account_info
```
Expected: Account ID `acct_1SwRZBGtKkLcbRia` ("New business sandbox")

### AWS CLI Access
DynamoDB verification requires AWS CLI with access to:
- Table: `buffett-dev-users`
- Table: `buffett-dev-stripe-events`

### Webhook Configuration
Webhooks must be registered in Stripe Dashboard OR Stripe CLI forwarding active:
- **Endpoint:** `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/stripe/webhook`
- **Events:** `customer.subscription.*`, `invoice.*`, `checkout.session.completed`

---

## Test Data Reference

| Resource | ID | Notes |
|----------|-----|-------|
| Customer | `cus_TuMWxXGA1woFYs` | "Test User Phase F" |
| Product | `prod_TuI3SR1TMzTPFt` | "Buffett Plus" |
| Price | `price_1SwTUiGtKkLcbRiapMRnErLu` | $10/month |

---

## Acceptance Criteria

### AC-1: Cancel at Period End
**Given:** A Plus subscriber with active subscription
**When:** Subscription updated with `cancel_at_period_end=true`
**Then:**
- Webhook `customer.subscription.updated` received
- DynamoDB user: `cancel_at_period_end=true`, `subscription_status=active`
- User retains Plus access until period ends

### AC-2: Immediate Cancellation (subscription.deleted)
**Given:** A Plus subscriber
**When:** Subscription is immediately canceled
**Then:**
- Webhook `customer.subscription.deleted` received
- DynamoDB user: `subscription_tier=free`, `subscription_status=canceled`
- `stripe_subscription_id` removed from user record
- `subscription_canceled_at` timestamp set

> **Important: AC-1 vs AC-2 Timing Distinction**
>
> | Scenario | Tier Change Timing | Webhook Trigger |
> |----------|-------------------|-----------------|
> | **AC-1**: `cancel_at_period_end=true` | Tier stays `plus` until billing period ends | `subscription.deleted` fires automatically when period ends |
> | **AC-2**: `DELETE /subscriptions/{id}` | Tier changes to `free` **immediately** | `subscription.deleted` fires immediately |
>
> To test AC-1's period-end behavior, you would need to either wait for the actual billing period to end, or use [Stripe Test Clocks](https://stripe.com/docs/billing/testing/test-clocks) to simulate time advancement.

### AC-3: Reactivation After Cancellation
**Given:** A canceled subscriber (tier=free)
**When:** New subscription created for same customer
**Then:**
- Webhook `customer.subscription.created` received
- DynamoDB user: `subscription_tier=plus`, `subscription_status=active`
- New token usage record initialized

---

## RALF Execution Tasks

### Task 1: Setup - Create Test User in DynamoDB

Before testing, ensure a test user exists in DynamoDB linked to the Stripe customer.

**Action:** Create/verify test user
```bash
aws dynamodb put-item \
  --table-name buffett-dev-users \
  --item '{
    "user_id": {"S": "test-cancel-flow-user"},
    "email": {"S": "test-phase-f@example.com"},
    "stripe_customer_id": {"S": "cus_TuMWxXGA1woFYs"},
    "subscription_tier": {"S": "free"},
    "created_at": {"S": "2026-02-04T00:00:00Z"}
  }'
```

**Verify:**
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected:** User exists with `subscription_tier=free`

---

### Task 2: Create Test Subscription

**Action:** Use Stripe MCP to create subscription (MCP doesn't have create_subscription, so use bash)

```bash
STRIPE_SECRET_KEY=$(aws secretsmanager get-secret-value \
  --secret-id stripe-secret-key-dev \
  --query SecretString --output text)

curl -s https://api.stripe.com/v1/subscriptions \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "customer=cus_TuMWxXGA1woFYs" \
  -d "items[0][price]=price_1SwTUiGtKkLcbRiapMRnErLu" \
  -d "metadata[user_id]=test-cancel-flow-user"
```

**Verify with MCP:**
```
mcp__stripe__list_subscriptions with customer=cus_TuMWxXGA1woFYs
```

**Expected:** Subscription created with status `active`

**Record subscription ID:** `sub_XXXXXXXXX` (save for later tasks)

---

### Task 3: Verify Subscription Created Webhook

**Action:** Check DynamoDB for user update

```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected Result:**
```json
{
  "user_id": "test-cancel-flow-user",
  "subscription_tier": "plus",
  "subscription_status": "active",
  "stripe_customer_id": "cus_TuMWxXGA1woFYs",
  "stripe_subscription_id": "sub_XXXXXXXXX",
  "billing_day": 4
}
```

**Verify idempotency tracking:**
```bash
aws dynamodb scan \
  --table-name buffett-dev-stripe-events \
  --filter-expression "contains(event_type, :t)" \
  --expression-attribute-values '{":t":{"S":"subscription.created"}}'
```

---

### Task 4: Test AC-1 - Cancel at Period End

**Action:** Update subscription to cancel at period end
```bash
curl -s https://api.stripe.com/v1/subscriptions/sub_XXXXXXXXX \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "cancel_at_period_end=true"
```

**Verify with MCP:**
```
mcp__stripe__fetch_stripe_resources with id="sub_XXXXXXXXX"
```

**Expected:** `cancel_at_period_end: true`, `status: active`

**Verify DynamoDB:**
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected Result:**
```json
{
  "subscription_tier": "plus",
  "subscription_status": "active",
  "cancel_at_period_end": true
}
```

**AC-1 PASS Criteria:**
- [ ] Webhook received (check CloudWatch logs or stripe-events table)
- [ ] `cancel_at_period_end=true` in DynamoDB
- [ ] `subscription_tier` still `plus`
- [ ] `subscription_status` still `active`

---

### Task 5: Test AC-2 - Immediate Cancellation

**Action:** Use Stripe MCP to cancel subscription
```
mcp__stripe__cancel_subscription
  subscription: "sub_XXXXXXXXX"
```

**Verify with MCP:**
```
mcp__stripe__list_subscriptions with status="canceled"
```

**Verify DynamoDB:**
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected Result:**
```json
{
  "subscription_tier": "free",
  "subscription_status": "canceled",
  "subscription_canceled_at": "2026-02-04T...",
  "stripe_customer_id": "cus_TuMWxXGA1woFYs"
}
```

**Note:** `stripe_subscription_id` should be REMOVED (not present in response)

**AC-2 PASS Criteria:**
- [ ] Webhook `subscription.deleted` received
- [ ] `subscription_tier=free`
- [ ] `subscription_status=canceled`
- [ ] `stripe_subscription_id` removed
- [ ] `subscription_canceled_at` timestamp set

---

### Task 6: Test AC-3 - Reactivation

**Action:** Create new subscription for the same customer
```bash
curl -s https://api.stripe.com/v1/subscriptions \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "customer=cus_TuMWxXGA1woFYs" \
  -d "items[0][price]=price_1SwTUiGtKkLcbRiapMRnErLu" \
  -d "metadata[user_id]=test-cancel-flow-user"
```

**Verify DynamoDB:**
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected Result:**
```json
{
  "subscription_tier": "plus",
  "subscription_status": "active",
  "stripe_subscription_id": "sub_NEWXXXXXX"
}
```

**Verify token usage initialized:**
```bash
aws dynamodb query \
  --table-name token-usage-dev-buffett \
  --key-condition-expression "user_id = :uid" \
  --expression-attribute-values '{":uid":{"S":"test-cancel-flow-user"}}' \
  --scan-index-forward false \
  --limit 1
```

**AC-3 PASS Criteria:**
- [ ] Webhook `subscription.created` received
- [ ] `subscription_tier=plus`
- [ ] `subscription_status=active`
- [ ] New `stripe_subscription_id` set
- [ ] Token usage record created with `total_tokens=0`

---

### Task 7: Cleanup

**Action:** Cancel the reactivated subscription to clean up
```
mcp__stripe__cancel_subscription
  subscription: "sub_NEWXXXXXX"
```

**Verify final state:**
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

**Expected:** `subscription_tier=free`, `subscription_status=canceled`

---

## Troubleshooting

### Webhook Not Received

1. **Check Stripe CLI is running:**
   ```bash
   stripe listen --forward-to https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/stripe/webhook
   ```

2. **Check webhook secret matches:**
   - CLI shows `whsec_xxx` on startup
   - Must match `stripe-webhook-secret-dev` in Secrets Manager

3. **Check CloudWatch logs:**
   ```bash
   aws logs tail /aws/lambda/buffett-dev-stripe-webhook-handler --follow
   ```

### Signature Verification Failed (400)

Update the webhook secret in Secrets Manager:
```bash
aws secretsmanager update-secret \
  --secret-id stripe-webhook-secret-dev \
  --secret-string "whsec_YOUR_NEW_SECRET"
```

### User Not Found in Webhook Handler

Ensure the test user exists in DynamoDB with matching `stripe_customer_id`:
```bash
aws dynamodb get-item \
  --table-name buffett-dev-users \
  --key '{"user_id":{"S":"test-cancel-flow-user"}}'
```

---

## Known Issues

### ✅ RESOLVED: `subscription.updated` handler now syncs `subscription_tier`

**Discovered:** 2026-02-04
**Resolved:** 2026-02-04

**Problem (was):** The `handle_subscription_updated()` function in `stripe_webhook_handler.py` only updated `subscription_status` and `cancel_at_period_end`. It did NOT update:
- `subscription_tier` in the users table
- `subscription_tier` in the token-usage table

**Solution Implemented:**
1. Created `_sync_subscription_tier()` helper function for robust dual-table sync
2. Updated `handle_subscription_updated()` to sync tier based on status:
   - `active/trialing` → `plus`
   - `canceled` → `free`
   - `past_due/incomplete` → no change (grace period)
3. Updated `handle_subscription_deleted()` to use the sync helper
4. Added comprehensive unit tests (42 tests, all passing)

**Files Changed:**
- `chat-api/backend/src/handlers/stripe_webhook_handler.py`
- `chat-api/backend/tests/unit/test_stripe_webhook_handler.py`

**Implementation Plan:** See `docs/stripe/SUBSCRIPTION_TIER_SYNC_IMPLEMENTATION.md`

---

### ✅ RESOLVED: Stripe MCP Server Account Mismatch

**Discovered:** 2026-02-04
**Resolved:** 2026-02-04

**Problem (was):** The Stripe MCP server tools used OAuth authentication, connecting to a different Stripe account (`acct_1SwRZBGtKkLcbRia`) than the one in AWS Secrets Manager (`acct_1SwRZ2Gi2AjXTZZZ`).

**Solution Implemented:**
Configured local Stripe MCP server in `~/.cursor/mcp.json` to use API key authentication with the same key from Secrets Manager:
```json
{
  "stripe": {
    "command": "npx",
    "args": ["-y", "@stripe/mcp", "--tools=all"],
    "env": {
      "STRIPE_SECRET_KEY": "sk_test_51SwRZ2Gi2AjXTZZZ..."
    }
  }
}
```

**Action Required:** Restart VS Code/Cursor to reload MCP server configuration.

---

## Test Results - 2026-02-04

**Test User:**
- `user_id`: `test-cancel-flow-user`
- `email`: `test-cancel-flow@example.com`
- `stripe_customer_id`: `cus_Tv1rCLcB1wzOMD`

| Test | Status | Timestamp | Notes |
|------|--------|-----------|-------|
| Task 1: Setup test user | ✅ PASS | 19:34 UTC | Created user with `subscription_tier=free` |
| Task 2: Create subscription | ✅ PASS | 19:34 UTC | `sub_1SxBqQGi2AjXTZZZHnwIYcaX` |
| Task 3: Verify subscription webhook | ✅ PASS | 19:45 UTC | Required GSI fix first (see Changelog) |
| Task 4: AC-1 Cancel at period end | ✅ PASS | 19:52 UTC | `cancel_at_period_end=true`, tier stayed `plus` |
| Task 5: AC-2 Immediate cancellation | ✅ PASS | 19:52 UTC | Tier changed to `free` immediately |
| Task 6: AC-3 Reactivation | ✅ PASS | 19:57 UTC | `sub_1SxCCFGi2AjXTZZZ40pOmzF6`, token usage initialized |
| Task 7: Cleanup | ✅ PASS | 19:57 UTC | Final state: `tier=free`, `status=canceled` |

### Summary
- **All 7 tasks passed**
- **Infrastructure fix required:** Added `stripe-customer-index` GSI to users table
- **Known issue documented:** `subscription.updated` handler doesn't sync `subscription_tier`

---

## Files Referenced

| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/stripe_webhook_handler.py` | Webhook event handlers |
| `chat-api/backend/src/utils/stripe_service.py` | Stripe SDK wrapper |
| `docs/stripe/ARCHITECTURE.md` | System architecture |
| `docs/stripe/PHASE_F_TESTING_REPORT.md` | Previous test results |

---

## Appendix: MCP Tool Reference

### List Subscriptions
```
mcp__stripe__list_subscriptions
  customer: "cus_xxx" (optional)
  status: "active" | "canceled" | "all" (optional)
  limit: 10 (optional)
```

### Cancel Subscription
```
mcp__stripe__cancel_subscription
  subscription: "sub_xxx" (required)
```

### Update Subscription
```
mcp__stripe__update_subscription
  subscription: "sub_xxx" (required)
  items: [...] (optional, for plan changes)
  proration_behavior: "create_prorations" | "none" (optional)
```

### Fetch Resource by ID
```
mcp__stripe__fetch_stripe_resources
  id: "sub_xxx" | "cus_xxx" | etc.
```
