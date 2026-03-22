# Phase 4: API Routes & Stripe Billing ($10/mo Market Intelligence Tier) — GSD Prompt

Use this prompt to plan and implement the API Gateway routes for the Market Intelligence agent, along with a new $10/month Stripe subscription tier that gates access to authenticated users.

---

## Goal

Create API Gateway routes for the Market Intelligence agent with JWT-authenticated access, and add a new $10/month "Market Intelligence" Stripe subscription tier. Only authenticated users with an active subscription can access the market intelligence endpoints.

---

## GSD Step 1: Audit Snapshot

### Knowns / Evidence

| What | Where | Details |
|------|-------|---------|
| Existing API Gateway | `chat-api/terraform/modules/api-gateway/` | HTTP API (v2) with routes for chat, research, subscription, auth, waitlist. Uses Lambda integrations. |
| JWT auth verifier | `chat-api/backend/src/handlers/auth_verify.py` | Lambda authorizer supporting HTTP API v2 format. Returns `isAuthorized` + context with `user_id`, `email`, `subscription_tier`. |
| Existing Stripe integration | `chat-api/terraform/modules/stripe/` | Secrets Manager for keys. Subscription handler at `/subscription/*`. Webhook handler processes Stripe events. |
| subscription_handler.py | `chat-api/backend/src/handlers/subscription_handler.py` | 3 routes: POST `/checkout`, POST `/portal`, GET `/status`. Creates Checkout sessions, portal sessions, gets subscription status. Uses `stripe_service.py`. |
| stripe_service.py | `chat-api/backend/src/utils/stripe_service.py` | Wraps Stripe API: create_checkout_session, create_portal_session, get_subscription, get_customer_by_email. Defines TOKEN_LIMIT_PLUS. |
| stripe_webhook_handler.py | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | Processes: checkout.session.completed, customer.subscription.updated/deleted, invoice.payment_succeeded/failed. Updates DynamoDB users table. |
| Existing "Plus" tier | subscription_handler.py | Current plan: "Plus" with `stripe-plus-price-id-{env}` secret. Single tier. |
| Follow-up agent Lambda URL | `frontend/src/contexts/ResearchContext.jsx` | Follow-up chat uses Lambda Function URL (not API Gateway) for streaming. `VITE_ANALYSIS_FOLLOWUP_URL`. |
| Frontend Stripe config | `frontend/src/api/stripeApi.js` | Calls `/subscription/checkout` with plan info, handles redirect to Stripe Checkout. |
| Users table | DynamoDB `buffett-{env}-users` | Stores user profile, subscription_tier, stripe_customer_id, subscription data. |

### Unknowns / Gaps

1. **New Stripe Price ID**: Need to create a new Stripe product/price for "Market Intelligence" at $10/month. This is a Stripe dashboard action + Secrets Manager entry.
2. **Tier hierarchy**: Is "Market Intelligence" a separate product from "Plus", or an upgrade? Need to decide: can users have both, or is it one or the other?
3. **Agent invocation pattern**: Should the API route invoke the Bedrock agent directly (like the follow-up agent uses Lambda Function URL), or proxy through API Gateway → Lambda → Bedrock? The follow-up pattern uses a Lambda Function URL for streaming.
4. **Streaming vs synchronous**: Bedrock `invoke_agent` supports streaming responses. The follow-up agent streams via Lambda Function URL + SSE. Market intelligence should follow the same pattern.

### Constraints

- JWT authentication required for all market intelligence endpoints.
- Subscription check must be fast (DynamoDB lookup, not Stripe API call per request).
- All infrastructure via Terraform.
- Stripe product/price creation is manual (Stripe dashboard) — only the secret reference is in Terraform.

### Risks

1. **Subscription check latency**: Adding a DynamoDB read to verify subscription on every request adds ~10ms. Acceptable.
2. **Billing confusion**: Two subscription tiers (Plus + Market Intelligence) could confuse users. Clear UI copy needed.
3. **Free trial abuse**: If offering a trial, need to handle cancellation and re-subscription edge cases.

---

## GSD Step 2: PRD — Acceptance Criteria

```
AC-1: Given an unauthenticated request to /market-intel/chat, when the request arrives,
      then a 401 Unauthorized response is returned.

AC-2: Given an authenticated user WITHOUT a Market Intelligence subscription, when they
      call /market-intel/chat, then a 403 Forbidden response with message "Market
      Intelligence subscription required" is returned.

AC-3: Given an authenticated user WITH an active Market Intelligence subscription, when
      they call /market-intel/chat with a question, then the Bedrock agent is invoked
      and a streamed response is returned.

AC-4: Given a user subscribes to Market Intelligence via Stripe Checkout ($10/month),
      when the checkout completes, then their users table record is updated with
      subscription_tier "market_intelligence" (or includes it in their tier list).

AC-5: Given a user with Market Intelligence subscription, when they access the Stripe
      Customer Portal, then they can manage/cancel their Market Intelligence subscription.

AC-6: Given the Stripe webhook receives a subscription.deleted event for a Market
      Intelligence subscription, when processed, then the user's access is revoked
      within 1 minute.

AC-7: Given all routes deployed via Terraform, when running terraform plan, then
      API Gateway routes, Lambda integrations, and authorizer are all managed as code.
```

---

## GSD Step 3: Implementation Plan

### Objective
Add API Gateway routes for Market Intelligence chat with JWT auth + subscription tier check, create a new $10/mo Stripe price, and update the webhook handler to manage the new tier.

### Approach Summary
Add a new Lambda handler (`market_intel_api.py`) that receives chat requests, verifies the user's subscription tier, invokes the Bedrock market intelligence agent, and streams the response via SSE (following the same pattern as the follow-up agent). Create a Lambda Function URL for streaming. Add a new Stripe product/price and update the subscription handler to support the new tier. Update the webhook handler to process Market Intelligence subscription events.

### Steps

1. **Create Stripe product and price (manual + Terraform secret)**
   - In Stripe Dashboard: Create product "Buffett Market Intelligence" with $10/month price
   - Store price ID in Secrets Manager: `stripe-market-intel-price-id-{env}`
   - Add Terraform data source for the new secret

2. **Update subscription model for multiple tiers**
   - Current model: single `subscription_tier` field in users table
   - New model: `subscription_tiers` array OR separate boolean fields
   - Decision: Use `subscription_tiers` as a string set in DynamoDB: `{"plus", "market_intelligence"}`
   - Update `auth_verify.py` to pass tier info in authorizer context

3. **Create market_intel_api.py Lambda handler**
   - Route: POST `/market-intel/chat`
   - Accepts: `{ "message": "...", "session_id": "..." }`
   - Flow:
     1. Extract user_id from JWT authorizer context
     2. Check subscription tier in users table (or from authorizer context)
     3. If no market_intelligence tier → 403
     4. Invoke Bedrock agent with `invoke_agent` (streaming)
     5. Stream response back via SSE (chunked transfer encoding)
   - Follow the pattern from `analysis_followup.py` for streaming

4. **Create Lambda Function URL for streaming**
   - Terraform: `aws_lambda_function_url` for market_intel_api Lambda
   - Auth type: NONE (JWT verified inside Lambda, same as follow-up)
   - CORS configuration matching frontend origin

5. **Update subscription_handler.py**
   - Add Market Intelligence checkout flow
   - New route: POST `/subscription/checkout` with `plan: "market_intelligence"`
   - Uses `stripe-market-intel-price-id-{env}` secret
   - Update `/subscription/status` to return all active tiers

6. **Update stripe_webhook_handler.py**
   - Handle Market Intelligence subscription events
   - On checkout.session.completed: check metadata for plan type, update user tiers
   - On subscription.deleted: remove market_intelligence from user's tiers
   - On invoice.payment_failed: handle grace period

7. **Update auth_verify.py**
   - Include subscription tiers in authorizer context response
   - Pass as comma-separated string in context (Bedrock authorizer context is string-only)

8. **Add Terraform infrastructure**
   - API Gateway route: POST `/market-intel/chat` (or Lambda Function URL only)
   - Lambda definition + Function URL
   - IAM: invoke Bedrock agent, read users table, read secrets
   - Environment variables: MARKET_INTEL_AGENT_ID, MARKET_INTEL_AGENT_ALIAS

9. **Add to build pipeline**
   - `market_intel_api.py` in `build_lambdas.sh`

### Files to Create/Modify

| File | Change |
|------|--------|
| `chat-api/backend/src/handlers/market_intel_api.py` | **NEW** — API handler for market intel chat |
| `chat-api/backend/src/handlers/subscription_handler.py` | Add Market Intelligence checkout flow |
| `chat-api/backend/src/handlers/stripe_webhook_handler.py` | Handle market_intelligence tier events |
| `chat-api/backend/src/handlers/auth_verify.py` | Pass subscription tiers in context |
| `chat-api/backend/src/utils/stripe_service.py` | Add market_intelligence price ID support |
| `chat-api/terraform/modules/lambda/main.tf` | Add market_intel_api Lambda + Function URL |
| `chat-api/terraform/modules/api-gateway/main.tf` | Add route (if not using Function URL exclusively) |
| `chat-api/terraform/modules/stripe/main.tf` | Add market-intel price secret reference |
| `chat-api/terraform/environments/dev/main.tf` | Wire new resources + outputs |
| `chat-api/backend/scripts/build_lambdas.sh` | Add market_intel_api |

### Verification Commands

```bash
# Unit tests
cd chat-api/backend && make test

# Terraform validation
cd chat-api/terraform/environments/dev && terraform validate && terraform plan

# Build
cd chat-api/backend && ./scripts/build_lambdas.sh

# Test auth rejection (no token)
curl -X POST https://<api-url>/market-intel/chat \
  -d '{"message":"test"}' -w "%{http_code}"
# Expected: 401

# Test subscription rejection (valid JWT, no subscription)
curl -X POST https://<api-url>/market-intel/chat \
  -H "Authorization: Bearer <jwt-token>" \
  -d '{"message":"test"}' -w "%{http_code}"
# Expected: 403

# Test Stripe checkout
curl -X POST https://<api-url>/subscription/checkout \
  -H "Authorization: Bearer <jwt-token>" \
  -d '{"plan":"market_intelligence"}'
```

---

## GSD Step 4: Task Graph

```
Task 1: Create Stripe product/price + Secrets Manager entry
  Dependencies: none (manual Stripe dashboard + CLI)
  Files: none (manual action)
  Verify: aws secretsmanager get-secret-value --secret-id stripe-market-intel-price-id-dev

Task 2: Update auth_verify.py to include subscription tiers in context
  Dependencies: none
  Files: src/handlers/auth_verify.py
  Verify: make test

Task 3: Update subscription_handler.py for market_intelligence tier
  Dependencies: Task 1 (price ID exists)
  Files: src/handlers/subscription_handler.py, src/utils/stripe_service.py
  Verify: make test

Task 4: Update stripe_webhook_handler.py for market_intelligence events
  Dependencies: none
  Files: src/handlers/stripe_webhook_handler.py
  Verify: make test

Task 5: Create market_intel_api.py Lambda handler
  Dependencies: Task 2 (auth context), Phase 3 (agent deployed)
  Files: src/handlers/market_intel_api.py
  Verify: make test

Task 6: Add Terraform for Lambda + Function URL + IAM + API Gateway route
  Dependencies: Task 5
  Files: modules/lambda/main.tf, modules/api-gateway/main.tf, environments/dev/main.tf
  Verify: terraform validate && terraform plan

Task 7: Add to build pipeline + write tests
  Dependencies: Task 3, Task 4, Task 5
  Files: scripts/build_lambdas.sh, tests/test_market_intel_api.py, tests/test_subscription_market_intel.py
  Verify: make test && ./scripts/build_lambdas.sh

Task 8: End-to-end test: subscribe → access → query → unsubscribe → deny
  Dependencies: all above + Phases 1-3 deployed
  Files: none (manual/integration testing)
  Verify: manual test flow
```

---

## GSD Step 5: Self-Critique / Red Team

### Fragile assumptions
- **Single subscription per user**: Current model assumes one subscription. Adding a second tier requires careful handling of users who have both Plus and Market Intelligence. Consider: is Market Intelligence a superset of Plus?
- **Stripe metadata routing**: The webhook handler needs to distinguish Plus vs Market Intelligence subscriptions. Must include `plan_type` in checkout session metadata.

### Failure modes
- **Race condition on subscription check**: User's subscription expires between auth check and agent invocation. Low risk — check is fast and subscription state is cached in users table.
- **Webhook delivery delay**: Stripe webhooks can be delayed up to minutes. User might pay but not immediately get access. Mitigate: the checkout success redirect should trigger a status check that updates the users table.

### Simplest 80% version
Use the existing subscription flow with a second price ID. Don't create a separate product — just a new price under the existing Buffett product. The subscription handler already routes by price ID metadata. Add a simple tier check in the market intel Lambda before invoking the agent.

### Key Decision: Tier Model
Recommend discussing with user:
- **Option A**: Market Intelligence is a standalone $10/mo plan (users can have Plus OR Market Intelligence OR both)
- **Option B**: Market Intelligence is included in Plus (upgrade Plus to include it, or create a higher "Pro" tier)
- **Option C**: Market Intelligence replaces Plus at $10/mo (single tier, more features)

This prompt assumes **Option A** (standalone). Adjust if the user prefers differently.
