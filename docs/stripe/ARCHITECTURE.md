# Stripe & Token Limiting Architecture

This document provides a deep dive into how the Stripe subscription system and Token Limiting system integrate across the frontend and backend.

## System Overview

BuffettGPT uses a **server-side subscription model** where Stripe handles payment collection, and the backend manages user state and token limits in DynamoDB.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                                │
│  ┌──────────────────┐   ┌─────────────────────┐   ┌──────────────────────┐  │
│  │ stripeApi.js     │   │ SubscriptionMgmt   │   │ TokenUsageDisplay    │  │
│  │ - checkout()     │◄──│ - handleUpgrade()   │   │ - percent_used       │  │
│  │ - portal()       │   │ - handleManage()    │   │ - remaining_tokens   │  │
│  │ - status()       │   │ - fetchStatus()     │   │ - reset_date         │  │
│  └────────┬─────────┘   └─────────────────────┘   └──────────────────────┘  │
│           │ Bearer Token (JWT)                                               │
└───────────┼─────────────────────────────────────────────────────────────────┘
            │ VITE_REST_API_URL
            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          API GATEWAY (HTTP API)                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ JWT Authorizer (auth_verify Lambda)                                    │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  Routes:                                                                     │
│  • POST /subscription/checkout  → subscription_handler                      │
│  • POST /subscription/portal    → subscription_handler                      │
│  • GET  /subscription/status    → subscription_handler                      │
│  • POST /stripe/webhook         → stripe_webhook_handler (NO AUTH)          │
└─────────────────────────────────────────────────────────────────────────────┘
            │
            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND (Lambda)                                   │
│  ┌─────────────────────┐         ┌─────────────────────────────────────────┐│
│  │ subscription_handler│         │ stripe_webhook_handler                  ││
│  │ - checkout session  │         │ - checkout.session.completed            ││
│  │ - portal session    │         │ - invoice.payment_succeeded             ││
│  │ - status + usage    │         │ - customer.subscription.deleted         ││
│  └──────────┬──────────┘         └──────────────────┬──────────────────────┘│
│             │                                        │                       │
│             ▼                                        ▼                       │
│  ┌─────────────────────┐         ┌──────────────────────────────────────┐   │
│  │ stripe_service.py   │         │ token_usage_tracker.py               │   │
│  │ • Secrets Manager   │         │ • Anniversary billing                │   │
│  │ • Stripe SDK        │         │ • Atomic DynamoDB updates            │   │
│  └──────────┬──────────┘         └──────────────────┬───────────────────┘   │
└─────────────┼────────────────────────────────────────┼──────────────────────┘
              │                                        │
              ▼                                        ▼
        ┌───────────┐                          ┌─────────────┐
        │  Stripe   │                          │  DynamoDB   │
        │   API     │                          │ • users     │
        └───────────┘                          │ • token-usage│
                                               └─────────────┘
```

---

## Flow 1: User Upgrades to Plus

When a user clicks "Upgrade to Plus", the following sequence occurs:

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌────────┐
│ Frontend │     │ API Gateway  │     │   Lambda    │     │ Stripe │
└────┬─────┘     └──────┬───────┘     └──────┬──────┘     └───┬────┘
     │                  │                    │                │
     │ 1. Click "Upgrade"                    │                │
     │─────────────────>│                    │                │
     │                  │ POST /subscription/checkout         │
     │                  │───────────────────>│                │
     │                  │                    │ 2. Create session
     │                  │                    │───────────────>│
     │                  │                    │<───────────────│
     │                  │<───────────────────│ checkout_url   │
     │<─────────────────│                    │                │
     │ 3. Redirect to Stripe                 │                │
     │────────────────────────────────────────────────────────>│
     │                  │                    │                │
     │    [User completes payment on Stripe-hosted page]      │
     │                  │                    │                │
     │<────────────────────────────────────────────────────────│
     │ 4. Redirect back │                    │                │
     │   ?subscription=success               │                │
```

### Key Code Paths

**Frontend** (`frontend/src/components/SubscriptionManagement.jsx:88-104`):
```javascript
const handleUpgrade = async () => {
  await stripeApi.redirectToCheckout(token, {
    successUrl: `${window.location.origin}?subscription=success`,
    cancelUrl: `${window.location.origin}?subscription=canceled`
  });
};
```

**Backend** (`chat-api/backend/src/handlers/subscription_handler.py:135-146`):
```python
result = create_checkout_session(
    user_id=user_id,
    user_email=email,
    success_url=success_url,
    cancel_url=cancel_url,
    customer_id=customer_id
)
return _response(200, result)  # Returns {checkout_url: "https://checkout.stripe.com/..."}
```

---

## Flow 2: Stripe Activates Subscription (Webhook)

After successful payment, Stripe sends a webhook to activate the subscription:

```
┌────────┐     ┌─────────────┐     ┌────────────────────┐     ┌──────────┐
│ Stripe │     │ API Gateway │     │ stripe_webhook     │     │ DynamoDB │
└───┬────┘     └──────┬──────┘     └─────────┬──────────┘     └────┬─────┘
    │                 │                      │                     │
    │ 1. checkout.session.completed          │                     │
    │────────────────>│                      │                     │
    │                 │ POST /stripe/webhook │                     │
    │                 │─────────────────────>│                     │
    │                 │                      │ 2. Verify signature │
    │                 │                      │    (stripe_service) │
    │                 │                      │                     │
    │                 │                      │ 3. Update users table
    │                 │                      │────────────────────>│
    │                 │                      │    subscription_tier='plus'
    │                 │                      │    stripe_customer_id
    │                 │                      │    billing_day
    │                 │                      │                     │
    │                 │                      │ 4. Initialize token-usage
    │                 │                      │────────────────────>│
    │                 │                      │    token_limit=2000000
    │                 │                      │    total_tokens=0
    │                 │<─────────────────────│                     │
    │<────────────────│ 200 OK               │                     │
```

### Key Code Paths

**Webhook Handler** (`chat-api/backend/src/handlers/stripe_webhook_handler.py:117-183`):
```python
def handle_checkout_completed(session):
    user_id = session.get('client_reference_id')

    # Verify user exists before updating
    existing_user = _get_user(user_id)
    if not existing_user:
        raise ValueError(f"User {user_id} does not exist")

    # Update user record with conditional check
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='SET subscription_tier = :tier, billing_day = :day ...',
        ExpressionAttributeValues={':tier': 'plus', ':day': billing_day, ...},
        ConditionExpression='attribute_exists(user_id)'
    )

    # Initialize token usage
    _initialize_plus_token_usage(user_id, billing_day)
```

**Token Initialization** (`chat-api/backend/src/handlers/stripe_webhook_handler.py:478-521`):
```python
token_usage_table.put_item(
    Item={
        'user_id': user_id,
        'billing_period': billing_period,  # e.g., "2026-02-03"
        'token_limit': TOKEN_LIMIT_PLUS,   # 2,000,000
        'total_tokens': 0,
        'reset_date': period_end,
    }
)
```

### Handled Webhook Events

| Event | Handler | Action |
|-------|---------|--------|
| `checkout.session.completed` | `handle_checkout_completed` | Activate subscription, set billing_day, init tokens |
| `customer.subscription.created` | `handle_subscription_created` | Activate subscription (API-created subs) |
| `invoice.payment_succeeded` | `handle_invoice_paid` | Reset token usage on renewal |
| `invoice.payment_failed` | `handle_invoice_failed` | Set status to `past_due` |
| `customer.subscription.deleted` | `handle_subscription_deleted` | Downgrade to free tier |
| `customer.subscription.updated` | `handle_subscription_updated` | Sync status changes |

---

## Flow 3: Frontend Fetches Status + Token Usage

The frontend fetches combined subscription and token data in a single call:

```
┌──────────┐     ┌─────────────┐     ┌───────────────────┐     ┌──────────┐
│ Frontend │     │ API Gateway │     │subscription_handler│     │ DynamoDB │
└────┬─────┘     └──────┬──────┘     └─────────┬─────────┘     └────┬─────┘
     │                  │                      │                    │
     │ GET /subscription/status                │                    │
     │─────────────────>│                      │                    │
     │                  │─────────────────────>│                    │
     │                  │                      │ 1. Get user record │
     │                  │                      │───────────────────>│
     │                  │                      │<───────────────────│
     │                  │                      │                    │
     │                  │                      │ 2. Get token usage │
     │                  │                      │───────────────────>│
     │                  │                      │<───────────────────│
     │                  │                      │                    │
     │                  │<─────────────────────│ Combined response  │
     │<─────────────────│                      │                    │
```

### Response Structure

```json
{
  "subscription_tier": "plus",
  "subscription_status": "active",
  "token_limit": 2000000,
  "has_subscription": true,
  "cancel_at_period_end": false,
  "billing_day": 15,
  "token_usage": {
    "total_tokens": 150000,
    "token_limit": 2000000,
    "percent_used": 7.5,
    "remaining_tokens": 1850000,
    "request_count": 42,
    "reset_date": "2026-03-15T00:00:00Z",
    "subscription_tier": "plus"
  }
}
```

### Key Code Paths

**Frontend Fetch** (`frontend/src/components/SubscriptionManagement.jsx:40-61`):
```javascript
const fetchSubscriptionStatus = useCallback(async () => {
  const data = await stripeApi.getSubscriptionStatus(token);
  setSubscriptionData(data);

  // Propagate token usage to parent
  if (data.token_usage && onTokenUsageUpdate) {
    onTokenUsageUpdate(data.token_usage);
  }
}, [token, isAuthenticated, onTokenUsageUpdate]);
```

**Backend Response** (`chat-api/backend/src/handlers/subscription_handler.py:222-248`):
```python
# Get token usage data
token_tracker = TokenUsageTracker()
usage_data = token_tracker.get_usage(user_id)

response_data = {
    'subscription_tier': subscription_tier,
    'token_usage': {
        'total_tokens': usage_data.get('total_tokens', 0),
        'token_limit': usage_data.get('token_limit', token_limit),
        'percent_used': usage_data.get('percent_used', 0.0),
        'remaining_tokens': usage_data.get('remaining_tokens', token_limit),
        'reset_date': usage_data.get('reset_date'),
    }
}
```

---

## Flow 4: Token Usage Recording (During Chat)

Token usage is recorded atomically after each chat request:

```
┌──────────┐     ┌─────────────┐     ┌───────────────┐     ┌───────────────────┐
│ Frontend │     │ WebSocket   │     │chat_processor │     │token_usage_tracker│
└────┬─────┘     └──────┬──────┘     └───────┬───────┘     └─────────┬─────────┘
     │                  │                    │                       │
     │ Send message     │                    │                       │
     │─────────────────>│                    │                       │
     │                  │───────────────────>│                       │
     │                  │                    │ 1. Check limit        │
     │                  │                    │──────────────────────>│
     │                  │                    │<──────────────────────│
     │                  │                    │   allowed: true       │
     │                  │                    │                       │
     │                  │                    │ 2. Call Bedrock       │
     │                  │                    │ (get response)        │
     │                  │                    │                       │
     │                  │                    │ 3. Record usage       │
     │                  │                    │──────────────────────>│
     │                  │                    │   input_tokens: 1500  │
     │                  │                    │   output_tokens: 800  │
     │                  │<───────────────────│                       │
     │<─────────────────│ Response + usage   │                       │
```

### Key Code

**Atomic Update** (`chat-api/backend/src/utils/token_usage_tracker.py:365-470`):
```python
# Atomic update using ADD
response = self.table.update_item(
    Key={'user_id': user_id, 'billing_period': billing_period},
    UpdateExpression='''
        ADD input_tokens :input,
            output_tokens :output,
            total_tokens :total,
            request_count :one
    ''',
    ExpressionAttributeValues={
        ':input': input_tokens,
        ':output': output_tokens,
        ':total': total_new_tokens,
        ':one': 1,
    },
    ReturnValues='ALL_NEW'
)
```

---

## DynamoDB Schema

### Users Table (`buffett-{env}-users`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `user_id` | String (PK) | Google OAuth user ID |
| `email` | String | User email |
| `subscription_tier` | String | `free` or `plus` |
| `subscription_status` | String | `active`, `past_due`, `canceled` |
| `stripe_customer_id` | String | Stripe customer ID (GSI) |
| `stripe_subscription_id` | String | Stripe subscription ID |
| `billing_day` | Number | Day of month for billing (1-31) |

**Example Record:**
```json
{
  "user_id": "google-oauth2|12345",
  "email": "user@example.com",
  "subscription_tier": "plus",
  "subscription_status": "active",
  "stripe_customer_id": "cus_abc123",
  "stripe_subscription_id": "sub_xyz789",
  "billing_day": 15
}
```

### Token Usage Table (`buffett-{env}-token-usage`)

| Attribute | Type | Description |
|-----------|------|-------------|
| `user_id` | String (PK) | User identifier |
| `billing_period` | String (SK) | Period start date `YYYY-MM-DD` |
| `billing_day` | Number | User's billing day (1-31) |
| `total_tokens` | Number | Tokens consumed this period |
| `token_limit` | Number | Monthly limit (2M for Plus) |
| `reset_date` | String | ISO timestamp of next reset |
| `subscription_tier` | String | Tier at time of usage |

**Example Record:**
```json
{
  "user_id": "google-oauth2|12345",
  "billing_period": "2026-02-15",
  "billing_day": 15,
  "total_tokens": 150000,
  "token_limit": 2000000,
  "reset_date": "2026-03-15T00:00:00Z",
  "subscription_tier": "plus",
  "request_count": 42
}
```

---

## Anniversary-Based Billing

Token usage resets on the user's **billing anniversary** (the day they subscribed), not the 1st of each month.

**Example:** User subscribes on January 15th
- Period 1: Jan 15 → Feb 15
- Period 2: Feb 15 → Mar 15
- Period 3: Mar 15 → Apr 15

**Edge Cases:**
- If billing_day = 31 and month has 30 days → uses day 30
- If billing_day = 31 and month is February → uses day 28/29

---

## File Reference

| Component | File Path |
|-----------|-----------|
| Frontend API Client | `frontend/src/api/stripeApi.js` |
| Subscription UI | `frontend/src/components/SubscriptionManagement.jsx` |
| Token Display | `frontend/src/components/TokenUsageDisplay.jsx` |
| Subscription Handler | `chat-api/backend/src/handlers/subscription_handler.py` |
| Webhook Handler | `chat-api/backend/src/handlers/stripe_webhook_handler.py` |
| Stripe Service | `chat-api/backend/src/utils/stripe_service.py` |
| Token Tracker | `chat-api/backend/src/utils/token_usage_tracker.py` |
| API Gateway Routes | `chat-api/terraform/modules/api-gateway/main.tf` |

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/subscription/checkout` | POST | JWT | Create Stripe Checkout session |
| `/subscription/portal` | POST | JWT | Create Customer Portal session |
| `/subscription/status` | GET | JWT | Get subscription + token usage |
| `/stripe/webhook` | POST | None* | Stripe webhook receiver |

*Webhook uses Stripe signature verification instead of JWT auth.

---

## Webhook Endpoint Configuration

### How Stripe Webhooks Work

Stripe uses **webhooks** to notify your application of events (payments, subscriptions, etc.) in real-time. The flow:

```
┌────────────────┐     ┌───────────────────┐     ┌─────────────────────┐
│  Stripe Event  │     │ Webhook Endpoint  │     │  Lambda Handler     │
│ (subscription  │────>│ (registered URL)  │────>│ (processes event)   │
│   created)     │     │                   │     │                     │
└────────────────┘     └───────────────────┘     └─────────────────────┘
                              │
                              ▼
                       Signature Verification
                       (using webhook secret)
```

**Key Components:**

| Component | Purpose | Location |
|-----------|---------|----------|
| **Webhook Endpoint** | URL Stripe sends events to | Registered in Stripe Dashboard |
| **Webhook Secret** | Signs events for verification | Stripe Dashboard + AWS Secrets Manager |
| **Lambda Handler** | Processes events, updates DynamoDB | `stripe_webhook_handler.py` |

### Webhook Endpoint Registration

A webhook endpoint must be registered in the **same Stripe account** that processes payments. Each endpoint has:
- **URL**: Where Stripe sends POST requests (e.g., `https://your-api.com/stripe/webhook`)
- **Enabled Events**: Which event types to receive
- **Signing Secret**: Unique `whsec_xxx` for signature verification

**Current Dev Endpoint:**
```
Endpoint ID: we_1SxBrKGi2AjXTZZZEaaek0bT
URL: https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/stripe/webhook
Events: customer.subscription.*, invoice.*, checkout.session.completed
Account: acct_1SwRZ2Gi2AjXTZZZ
```

### Signature Verification Flow

Every webhook request includes a `Stripe-Signature` header. The Lambda verifies it:

```python
# stripe_webhook_handler.py
stripe.Webhook.construct_event(
    payload=request_body,
    sig_header=stripe_signature,
    secret=webhook_secret  # From AWS Secrets Manager
)
```

If the secret in Secrets Manager doesn't match the endpoint's signing secret, verification fails with HTTP 400.

### Account Synchronization Requirement

**Critical:** All three must belong to the same Stripe account:
1. API key in `stripe-secret-key-{env}`
2. Webhook endpoint registration
3. Webhook secret in `stripe-webhook-secret-{env}`

If you create a new webhook endpoint (or switch accounts), you **must** update the webhook secret in Secrets Manager:

```bash
# Get new secret from Stripe Dashboard or endpoint creation response
aws secretsmanager update-secret \
  --secret-id stripe-webhook-secret-dev \
  --secret-string "whsec_YOUR_NEW_SECRET"
```

### Webhook Configuration Changes Log

| Date | Change | Reason |
|------|--------|--------|
| 2026-02-04 | Created endpoint `we_1SxBrKGi2AjXTZZZEaaek0bT` | No endpoint existed in account used by Lambdas |
| 2026-02-04 | Updated `stripe-webhook-secret-dev` | Synced with new endpoint's signing secret |

---

## Secrets (AWS Secrets Manager)

| Secret Name | Description |
|-------------|-------------|
| `stripe-secret-key-{env}` | Stripe API secret key |
| `stripe-webhook-secret-{env}` | Webhook signing secret (must match registered endpoint) |
| `stripe-plus-price-id-{env}` | Plus plan price ID |
