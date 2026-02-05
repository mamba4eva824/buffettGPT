# Phase B: Stripe Backend Handlers

## Executive Summary

Phase B implements the Python backend handlers for Stripe payment processing in BuffettGPT. This phase creates three core components: a shared Stripe service utility, a webhook handler for processing Stripe events, and a subscription handler for REST API endpoints. Together, these enable the full subscription lifecycle from checkout to cancellation.

**Completion Status**: All tasks (B1-B5) completed and verified.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Stripe Backend Architecture                        │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌──────────────────────────────────────┐
                    │           Frontend                    │
                    │    (React + Stripe.js)               │
                    └──────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
    ┌──────────────────────────┐    ┌──────────────────────────┐
    │   API Gateway (HTTP)      │    │      Stripe Dashboard     │
    │   /subscription/*         │    │    (Webhook Events)       │
    └──────────────────────────┘    └──────────────────────────┘
                    │                               │
                    ▼                               ▼
    ┌──────────────────────────┐    ┌──────────────────────────┐
    │  subscription_handler.py  │    │ stripe_webhook_handler.py │
    │  - POST /checkout        │    │  - checkout.completed     │
    │  - POST /portal          │    │  - invoice.paid           │
    │  - GET /status           │    │  - invoice.failed         │
    └──────────────────────────┘    │  - subscription.deleted   │
                    │               │  - subscription.updated   │
                    │               └──────────────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    ▼
                    ┌──────────────────────────────┐
                    │      stripe_service.py        │
                    │  - Secret management          │
                    │  - Stripe API wrapper         │
                    │  - Webhook verification       │
                    └──────────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
    ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
    │   Secrets    │    │     DynamoDB      │    │   Stripe API     │
    │   Manager    │    │  - users          │    │  - Checkout      │
    │              │    │  - token-usage    │    │  - Portal        │
    │              │    │  - stripe-events  │    │  - Subscriptions │
    └──────────────┘    └──────────────────┘    └──────────────────┘
```

---

## Task B1: Stripe Service Utility

### File: `chat-api/backend/src/utils/stripe_service.py`

**Purpose**: Centralized utility for all Stripe operations with lazy initialization and secret management.

### Core Functions

#### Secret Management

```python
@lru_cache(maxsize=4)
def get_secret(secret_name: str) -> str:
    """Fetch a secret from Secrets Manager with caching."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return response['SecretString']
```

**Why `@lru_cache`**:
- Secrets are fetched once per Lambda cold start
- Eliminates redundant AWS API calls within a single invocation
- Cache size of 4 covers all Stripe secrets

#### Lazy Stripe Initialization

```python
_stripe_module = None

def get_stripe():
    """Get initialized Stripe module with lazy loading."""
    global _stripe_module
    import stripe

    if _stripe_module is None:
        stripe.api_key = get_stripe_secret_key()
        _stripe_module = stripe
        logger.info("Stripe client initialized")

    return _stripe_module
```

**Why Lazy Loading**:
- Stripe import and initialization only happens when needed
- Reduces Lambda cold start time for non-Stripe requests
- API key is set once and reused for all operations

### API Functions

| Function | Purpose | Returns |
|----------|---------|---------|
| `create_checkout_session()` | Creates Stripe Checkout for Plus upgrade | `{checkout_url, session_id}` |
| `create_portal_session()` | Creates Customer Portal session | `{portal_url}` |
| `get_subscription()` | Retrieves subscription details | Subscription object or None |
| `get_customer_by_email()` | Finds existing Stripe customer | Customer object or None |
| `verify_webhook_signature()` | Validates webhook authenticity | Verified event object |

### Checkout Session Creation

```python
def create_checkout_session(
    user_id: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
    customer_id: Optional[str] = None
) -> Dict[str, Any]:
    session_params = {
        'mode': 'subscription',
        'payment_method_types': ['card'],
        'line_items': [{'price': price_id, 'quantity': 1}],
        'success_url': success_url,
        'cancel_url': cancel_url,
        'client_reference_id': user_id,  # Links session to our user
        'metadata': {'user_id': user_id, 'environment': ENVIRONMENT},
    }
```

**Key Design Decisions**:
- `client_reference_id`: Enables user lookup in webhook handler
- `metadata`: Redundant user_id storage for reliability
- Reuses existing Stripe customers when possible

### Webhook Signature Verification

```python
def verify_webhook_signature(payload: str, sig_header: str) -> Dict[str, Any]:
    stripe = get_stripe()
    webhook_secret = get_stripe_webhook_secret()

    event = stripe.Webhook.construct_event(
        payload,
        sig_header,
        webhook_secret
    )
    return event
```

**Security**: Prevents webhook spoofing by validating Stripe's cryptographic signature.

---

## Task B2: Webhook Handler

### File: `chat-api/backend/src/handlers/stripe_webhook_handler.py`

**Purpose**: Processes Stripe webhook events for subscription lifecycle management.

### Event Routing

```python
handlers = {
    'checkout.session.completed': handle_checkout_completed,
    'invoice.payment_succeeded': handle_invoice_paid,
    'invoice.payment_failed': handle_invoice_failed,
    'customer.subscription.deleted': handle_subscription_deleted,
    'customer.subscription.updated': handle_subscription_updated,
}

handler = handlers.get(event_type)
if handler:
    handler(event_data)
    _mark_event_processed(event_id, event_type)
```

### Event Handlers

#### 1. `checkout.session.completed`

**Triggers**: User completes Stripe Checkout successfully

**Actions**:
```python
def handle_checkout_completed(session: Dict[str, Any]) -> None:
    # 1. Extract identifiers
    user_id = session.get('client_reference_id')
    customer_id = session.get('customer')
    subscription_id = session.get('subscription')

    # 2. Set billing day (anniversary-based)
    billing_day = datetime.now(timezone.utc).day

    # 3. Update user record
    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='''
            SET stripe_customer_id = :customer_id,
                stripe_subscription_id = :subscription_id,
                subscription_tier = :tier,
                subscription_status = :status,
                billing_day = :billing_day,
                subscription_activated_at = :activated_at
        ''',
        ExpressionAttributeValues={
            ':tier': 'plus',
            ':status': 'active',
            ':billing_day': billing_day,
            # ...
        }
    )

    # 4. Initialize token usage for billing period
    _initialize_plus_token_usage(user_id, billing_day)
```

**User Record Changes**:
| Field | Value |
|-------|-------|
| `stripe_customer_id` | `cus_*` |
| `stripe_subscription_id` | `sub_*` |
| `subscription_tier` | `plus` |
| `subscription_status` | `active` |
| `billing_day` | 1-31 (day of signup) |

#### 2. `invoice.payment_succeeded`

**Triggers**: Monthly subscription renewal payment succeeds

**Actions**:
- Resets token usage for new billing period
- Updates `subscription_status` to `active` (in case it was `past_due`)
- Records `last_payment_at` timestamp

**Important**: Skips initial subscription invoices (handled by checkout.completed)

```python
if billing_reason == 'subscription_create':
    logger.info("Skipping - handled by checkout")
    return
```

#### 3. `invoice.payment_failed`

**Triggers**: Payment fails (card declined, expired, etc.)

**Actions**:
- Sets `subscription_status` to `past_due`
- Records `payment_failed_at` timestamp
- User retains access during Stripe's grace period

#### 4. `customer.subscription.deleted`

**Triggers**: Subscription cancelled (immediate or end-of-period)

**Actions**:
- Downgrades `subscription_tier` to `free`
- Sets `subscription_status` to `canceled`
- Removes `stripe_subscription_id` from user record
- Records `subscription_canceled_at` timestamp

#### 5. `customer.subscription.updated`

**Triggers**: Subscription status changes, cancellation scheduled

**Actions**:
- Syncs `subscription_status` with Stripe
- Updates `cancel_at_period_end` flag

### Idempotency

```python
def _is_event_processed(event_id: str) -> bool:
    """Check if webhook event has already been processed."""
    response = processed_events_table.get_item(Key={'event_id': event_id})
    return 'Item' in response

def _mark_event_processed(event_id: str, event_type: str) -> None:
    """Mark webhook event as processed with 7-day TTL."""
    ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)
    processed_events_table.put_item(
        Item={
            'event_id': event_id,
            'event_type': event_type,
            'processed_at': now,
            'ttl': ttl  # Auto-cleanup after 7 days
        }
    )
```

**Why Idempotency Matters**:
- Stripe may retry failed webhooks
- Network issues can cause duplicate deliveries
- Prevents double-activation or double-cancellation

---

## Task B3: Subscription Handler

### File: `chat-api/backend/src/handlers/subscription_handler.py`

**Purpose**: REST API endpoints for subscription management, requiring JWT authentication.

### Endpoints

#### POST `/subscription/checkout`

Creates a Stripe Checkout session for upgrading to Plus.

**Request Flow**:
```
1. Extract user from JWT (user_id, email)
2. Check if already subscribed → 400 error if active
3. Look up existing Stripe customer by email
4. Create checkout session with success/cancel URLs
5. Return checkout_url for frontend redirect
```

**Response**:
```json
{
  "checkout_url": "https://checkout.stripe.com/c/pay/cs_test_...",
  "session_id": "cs_test_..."
}
```

**Edge Cases Handled**:
- Prevents duplicate subscriptions
- Reuses existing Stripe customers
- Accepts optional custom return URLs

#### POST `/subscription/portal`

Creates a Stripe Customer Portal session for self-service management.

**Capabilities**:
- Update payment method
- View billing history
- Cancel subscription

**Response**:
```json
{
  "portal_url": "https://billing.stripe.com/p/session/..."
}
```

**Requirements**:
- User must have `stripe_customer_id` (must have subscribed previously)

#### GET `/subscription/status`

Returns current subscription status for the authenticated user.

**Response**:
```json
{
  "subscription_tier": "plus",
  "subscription_status": "active",
  "token_limit": 2000000,
  "has_subscription": true,
  "cancel_at_period_end": false,
  "billing_day": 15,
  "current_period_end": 1738540800
}
```

**Data Sources**:
- User record in DynamoDB (cached tier, status)
- Live Stripe API (current_period_end, cancel_at_period_end)

### JWT Authentication

```python
def _get_user_from_event(event: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract user info from JWT authorizer context."""
    # Supports multiple API Gateway formats:
    # - Lambda authorizer claims
    # - HTTP API JWT authorizer
    # - Direct claims format
```

**Security**: All endpoints require valid JWT token via API Gateway authorizer.

---

## Task B4: Token Usage Integration

### File: `chat-api/backend/src/utils/token_usage_tracker.py` (Modified)

**New Methods Added**:

#### `update_subscription()`

```python
def update_subscription(
    self,
    user_id: str,
    subscription_tier: str,
    token_limit: Optional[int] = None,
    billing_day: Optional[int] = None
) -> bool:
```

**Purpose**: Updates user's subscription tier and token limit when subscription is activated, renewed, or canceled.

**Behavior**:
- Determines billing day (preserves existing or uses current day)
- Sets token limit based on tier (2,000,000 for Plus, 0 for Free)
- Creates/updates token usage record for current billing period

#### `reset_usage_for_new_period()`

```python
def reset_usage_for_new_period(
    self,
    user_id: str,
    billing_day: Optional[int] = None
) -> bool:
```

**Purpose**: Resets token usage counters when subscription renews.

**Behavior**:
- Creates new billing period record with zero usage
- Preserves user's tier and token limit
- Uses anniversary-based billing period calculation

### Anniversary-Based Billing

```python
def get_current_billing_period(self, billing_day: int) -> Tuple[str, str, str]:
    """Calculate billing period based on user's anniversary date."""
```

**Example**: User signs up on January 15th
- Billing periods: Jan 15 - Feb 14, Feb 15 - Mar 14, etc.
- Token usage resets on the 15th of each month

---

## Task B5: Lambda Build Integration

### File: `chat-api/backend/scripts/build_lambdas.sh` (Modified)

**Changes**:
```bash
FUNCTIONS=(
    # ... existing functions ...
    "stripe_webhook_handler"    # NEW
    "subscription_handler"      # NEW
)
```

**Build Output**:
```
chat-api/backend/build/
├── stripe_webhook_handler.zip  (58K)
└── subscription_handler.zip    (57K)
```

**Package Contents**:
- Handler Python file
- `utils/` directory (includes stripe_service.py, token_usage_tracker.py)
- Excludes `requirements.txt` (dependencies in Lambda Layer)

---

## Data Flow Diagrams

### New Subscription Flow

```
User                Frontend            API Gateway       subscription_handler
 │                     │                     │                     │
 │  Click "Upgrade"    │                     │                     │
 │────────────────────>│                     │                     │
 │                     │  POST /subscription/checkout              │
 │                     │────────────────────>│────────────────────>│
 │                     │                     │                     │
 │                     │                     │  Verify JWT         │
 │                     │                     │<────────────────────│
 │                     │                     │                     │
 │                     │                     │  Create Session     │
 │                     │                     │────────────────────>│
 │                     │                     │                     │──> Stripe API
 │                     │                     │                     │<──
 │                     │  {checkout_url}     │                     │
 │                     │<────────────────────│<────────────────────│
 │                     │                     │                     │
 │  Redirect to Stripe │                     │                     │
 │<────────────────────│                     │                     │
```

### Webhook Processing Flow

```
Stripe              API Gateway     stripe_webhook_handler      DynamoDB
  │                     │                     │                     │
  │  POST /webhook      │                     │                     │
  │  + Stripe-Signature │                     │                     │
  │────────────────────>│────────────────────>│                     │
  │                     │                     │                     │
  │                     │                     │  Verify Signature   │
  │                     │                     │──────────────────>  │
  │                     │                     │                     │
  │                     │                     │  Check Idempotency  │
  │                     │                     │────────────────────>│
  │                     │                     │<────────────────────│
  │                     │                     │                     │
  │                     │                     │  Update User        │
  │                     │                     │────────────────────>│
  │                     │                     │                     │
  │                     │                     │  Init Token Usage   │
  │                     │                     │────────────────────>│
  │                     │                     │                     │
  │                     │                     │  Mark Processed     │
  │                     │                     │────────────────────>│
  │                     │                     │                     │
  │  200 OK             │                     │                     │
  │<────────────────────│<────────────────────│                     │
```

---

## Verification Gates Passed

| Gate | Command | Result |
|------|---------|--------|
| B1 Import | `python -c "from utils.stripe_service import ..."` | PASSED |
| B2 Import | `python -c "from handlers.stripe_webhook_handler import ..."` | PASSED |
| B3 Import | `python -c "from handlers.subscription_handler import ..."` | PASSED |
| B4 Unit Tests | `pytest tests/unit/ --ignore=tests/test_action_group_handler.py` | 43 passed |
| B5 Build | `./scripts/build_lambdas.sh` | 2 new zips created |

---

## Security Considerations

1. **Webhook Signature Verification**: All incoming webhooks validated against Stripe's signing secret
2. **JWT Authentication**: All subscription endpoints require valid tokens
3. **Idempotent Processing**: Duplicate webhooks are safely ignored
4. **Least Privilege**: Lambda only has access to required secrets
5. **No Sensitive Logging**: Customer IDs logged, but no payment details

---

## Files Created/Modified

| File | Action | Lines |
|------|--------|-------|
| `src/utils/stripe_service.py` | Created | 283 |
| `src/handlers/stripe_webhook_handler.py` | Created | 505 |
| `src/handlers/subscription_handler.py` | Created | 303 |
| `src/utils/token_usage_tracker.py` | Modified | +150 |
| `scripts/build_lambdas.sh` | Modified | +2 |

**Total New Code**: ~1,100 lines of Python

---

## Integration Dependencies

### Requires from Phase A:
- Secrets Manager secrets created
- IAM policy for secret access

### Required for Phase C:
- Lambda function definitions in Terraform
- API Gateway routes for `/subscription/*` and `/webhook`
- Environment variables set in Lambda configuration

---

## Next Steps (Phase C)

Phase B handlers are ready for Terraform deployment:
1. Add Lambda function resources for both handlers
2. Configure API Gateway routes
3. Set environment variables (table names, secret names)
4. Attach Stripe secrets IAM policy to execution roles
