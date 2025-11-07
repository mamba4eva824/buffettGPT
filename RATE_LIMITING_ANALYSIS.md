# BuffettGPT Rate Limiting & Pricing Architecture Analysis

## Executive Summary
The system currently implements a **dual-layer rate limiting strategy** combining:
1. **Application-level** DynamoDB-backed rate limiting for authenticated/anonymous users
2. **API Gateway-level** token bucket throttling 
3. **Client-side** rate limiting in the frontend

There is **basic user subscription infrastructure** but **NO pricing/payment logic** implemented yet.

---

## 1. CURRENT RATE LIMITING IMPLEMENTATION

### 1.1 Application-Level Rate Limiting (DynamoDB-backed)

**Location:** `/chat-api/backend/src/utils/rate_limiter.py`

**Mechanism:**
- **Device Fingerprinting** for anonymous users (IP + User-Agent + CloudFront headers)
- **JWT-based user identification** for authenticated users
- **Monthly reset windows** on 1st of each month
- **Grace period system** for new devices (1 hour default)

**Current Limits (Configurable via Environment Variables):**
```python
ANONYMOUS_MONTHLY_LIMIT = 5           # Monthly limit for anonymous users
AUTHENTICATED_MONTHLY_LIMIT = 500     # Monthly limit for authenticated users
ENABLE_DEVICE_FINGERPRINTING = true   # Device fingerprinting enabled
ENABLE_RATE_LIMITING = true           # Can be disabled globally
RATE_LIMIT_GRACE_PERIOD_HOURS = 1    # Grace period for new devices
```

**Storage:** Two DynamoDB tables:
- `buffett-chat-api-dev-rate-limits` - Monthly aggregates
- `buffett-chat-api-dev-usage-tracking` - Individual usage records (with 3-month TTL)

**Response Headers:**
```
X-RateLimit-Limit: <limit>
X-RateLimit-Remaining: <remaining>
X-RateLimit-Reset: <YYYY-MM-DD>
```

**Error Response (429):**
```json
{
  "error": "Rate limit exceeded",
  "message": "You have exceeded your limit of X requests per month...",
  "limit": X,
  "current": Y,
  "reset_date": "YYYY-MM-DD",
  "type": "RATE_LIMIT_EXCEEDED"
}
```

### 1.2 Tiered Rate Limiting System (Advanced)

**Location:** `/chat-api/backend/src/utils/tiered_rate_limiter.py`

**Tier Limits Structure:**
```python
TIER_LIMITS = {
    'anonymous': {
        'daily': 5,
        'hourly': 3,
        'per_minute': 2,
        'burst': 2,  # Max requests in quick succession
        'message_history': False,
        'session_ttl_hours': 2,
    },
    'authenticated': {
        'daily': 20,
        'hourly': 10,
        'per_minute': 5,
        'burst': 3,
        'message_history': True,
        'session_ttl_hours': 168,  # 7 days
    },
    'premium': {
        'daily': 1000,
        'hourly': 100,
        'per_minute': 20,
        'burst': 10,
        'message_history': True,
        'session_ttl_hours': 720,  # 30 days
    },
    'enterprise': {
        'daily': 10000,
        'hourly': 1000,
        'per_minute': 100,
        'burst': 50,
        'message_history': True,
        'session_ttl_hours': 2160,  # 90 days
    }
}
```

**Subscription Mapping:**
```python
'free' -> 'authenticated'
'basic' -> 'authenticated'
'premium' -> 'premium'
'pro' -> 'premium'
'enterprise' -> 'enterprise'
```

**Status:** ⚠️ **DEFINED BUT NOT ACTIVELY USED** - Currently only basic RateLimiter is deployed

### 1.3 API Gateway-Level Rate Limiting

**Location:** `/chat-api/terraform/modules/api-gateway/main.tf`

**Mechanism:** Token bucket throttling at API Gateway stage level

**Current Configuration:**
```
Development Environment:
  throttling_burst_limit = 500
  throttling_rate_limit = 100 requests/sec

Production Environment:
  throttling_burst_limit = 2000
  throttling_rate_limit = 1000 requests/sec
```

**Applies to:**
- HTTP API Gateway stage
- WebSocket API Gateway stage

### 1.4 Client-Side Rate Limiting

**Location:** `/frontend/src/App.jsx`

**Mechanism:** In-memory counter with localStorage persistence

**Current Limit:**
```javascript
const DAILY_QUERY_LIMIT = 10;
```

**Storage:**
```javascript
localStorage['chat.ai.dailyQueries']    // Query count
localStorage['chat.ai.queryDate']       // Date for daily reset
```

**Status:** ⚠️ **CLIENT-SIDE ONLY** - Can be bypassed by disabling JavaScript or clearing localStorage

---

## 2. DEVICE FINGERPRINTING

**Location:** `/chat-api/backend/src/utils/device_fingerprint.py`

**Components Used (with weights):**
```
ip_address: 0.3       (30%)
user_agent: 0.25      (25%)
accept_language: 0.15 (15%)
accept_encoding: 0.1  (10%)
cf_country: 0.1       (10%)
cf_ray: 0.05          (5%)
cf_protocol: 0.05     (5%)
```

**Additional Signals:**
- CloudFront device type (desktop/mobile/tablet)
- TLS version
- HTTP version
- Browser/OS detection from User-Agent

**Hash Algorithm:** SHA-256 (first 16 characters)

**Fallback Fingerprint:** MD5 hash of IP + User-Agent (when primary fails)

**Prefix Format:**
- Primary: `anon_<16-char-hash>`
- Fallback: `anon_fb_<12-char-hash>`

---

## 3. AUTHENTICATION & AUTHORIZATION

### 3.1 Google OAuth Integration

**Location:** `/chat-api/backend/src/handlers/auth_callback.py`

**Flow:**
1. Frontend sends Google ID token to `/auth/callback`
2. Backend verifies token with Google
3. Creates/updates user record in DynamoDB
4. Issues JWT token with 7-day expiry

**User Record Structure:**
```python
{
    'user_id': '<google_sub>',
    'email': '<email>',
    'name': '<name>',
    'picture': '<url>',
    'provider': 'google',
    'created_at': '<ISO>',
    'updated_at': '<ISO>',
    'last_login': '<ISO>',
    'subscription_tier': 'free',  # Default
    'status': 'active'
}
```

**JWT Payload:**
```python
{
    'user_id': '<user_id>',
    'email': '<email>',
    'name': '<name>',
    'subscription_tier': '<tier>',
    'exp': <unix_timestamp>,
    'iat': <unix_timestamp>,
    'iss': 'buffett-chat-api'
}
```

### 3.2 JWT Verification

**Location:** `/chat-api/backend/src/handlers/auth_verify.py`

**Authorization Logic:**
- **HTTP API:** Requires valid JWT token (denies if missing/invalid)
- **WebSocket:** Allows anonymous connections (treats missing token as unauthenticated)

**User Identification:**
- Authenticated: JWT `user_id` claim
- Anonymous: Device fingerprint

### 3.3 API Endpoints Protected with Rate Limiting

**Currently Protected:**
- `POST /chat` - Chat message endpoint (using `@rate_limit_decorator`)

**Not Protected:**
- WebSocket endpoints (`$connect`, `$disconnect`, WebSocket message handling)
- Conversation management endpoints
- Health check endpoints

---

## 4. USER SUBSCRIPTION INFRASTRUCTURE

### 4.1 User Tier Storage

**DynamoDB Table:** `buffett-chat-api-dev-users`

**Schema:**
```
Partition Key: user_id (String)
Global Secondary Index: email-index
```

**User Fields:**
- `subscription_tier`: 'free', 'basic', 'premium', 'pro', 'enterprise'
- Status tracking
- Login/registration dates

### 4.2 Subscription Tiers Defined

**In Code:**
```
'free' -> 20 daily queries, 10 hourly, message history
'basic' -> 20 daily (same as free, needs differentiation)
'premium' -> 1000 daily (essentially unlimited)
'enterprise' -> 10000 daily (essentially unlimited)
```

### 4.3 Current Status

⚠️ **INFRASTRUCTURE EXISTS BUT NO IMPLEMENTATION:**
- ❌ No payment processing
- ❌ No pricing page
- ❌ No upgrade UI
- ❌ No billing/invoicing
- ❌ No subscription management APIs
- ❌ No automatic tier enforcement in API calls

---

## 5. USAGE TRACKING

### 5.1 Token Counting

**Location:** `/chat-api/backend/src/handlers/chat_processor.py`

**Current Method:**
```python
# Rough approximation: 1 token ≈ 4 characters
estimated_input_tokens = len(user_message) // 4
estimated_output_tokens = len(ai_response) // 4
```

**Status:** 
- ⚠️ Estimates only, not actual Claude token counts
- 📊 Stored with message records but not aggregated

### 5.2 Usage Recording

**Method:**
- Individual requests tracked in `usage_tracking` table
- Monthly aggregates in `rate_limits` table
- TTL: 3 months (auto-cleanup via DynamoDB TTL)

**No Usage Querying APIs:**
- ❌ No endpoint to get user usage statistics
- ❌ No usage dashboard
- ❌ No warning before limit reached

---

## 6. GAPS & WEAKNESSES

### Critical Issues

1. **Client-Side Rate Limiting Bypassed:**
   - Frontend limit (10/day) can be bypassed
   - No server-side enforcement at that granularity
   - Actual server limits are much higher (5/month anonymous, 500/month authenticated)

2. **Tiered System Not Activated:**
   - Advanced tier limits defined but not used
   - No way to trigger premium tier checks
   - Subscription tier field exists but never checked on API calls

3. **WebSocket Not Rate Limited:**
   - WebSocket message handler has no rate limiting
   - Real-time chat could be abused
   - $connect handlers don't check subscription tier

4. **No Usage Query API:**
   - Users can't see their usage
   - No remaining quota information
   - No warning before hitting limits

5. **Token Counting Inaccurate:**
   - Uses 4-char-per-token approximation
   - Not actual Claude token counts
   - No token-based pricing possible

6. **Subscription Enforcement Missing:**
   - Subscription tier stored but never checked
   - No enforcement of tier-specific features
   - Message history available to all (not tier-gated)

### Moderate Issues

7. **Grace Period Allows Bypass:**
   - 1-hour grace period for new devices
   - Could be exploited by creating new fingerprints
   - Device fingerprinting can be circumvented

8. **Monthly Reset Only:**
   - No daily/hourly granularity at application level
   - API Gateway throttles but different boundaries
   - Gap between 429 responses and rate limit errors

9. **No Usage Dashboard:**
   - Frontend shows remaining queries (client-side only)
   - No server-side query count visibility
   - No usage history

10. **Secrets Management Gap:**
    - JWT secret stored in Secrets Manager
    - Secret caching in Lambda (1-hour default)
    - No automatic rotation mechanism visible

### Design Issues

11. **Double Limits:**
    - API Gateway has separate throttling (100-1000/sec)
    - Application has monthly limits (5-500/month)
    - Unclear interaction/priority

12. **Inconsistent User Type Detection:**
    - Multiple sources: JWT, device fingerprint, query params
    - Priority not clearly defined
    - Fallback logic could lead to unexpected behavior

13. **No Pricing Model:**
    - Tiers defined but no price points
    - No cost calculation
    - No billing integration

---

## 7. ARCHITECTURE SUMMARY

```
┌─────────────────┐
│   Frontend      │
│  (Client-side   │
│   limits only)  │
└────────┬────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │      API Gateway (AWS)                         │
    │  ┌──────────────────────────────────────────┐  │
    │  │  Throttling: 100/sec (dev), 1000/sec     │  │
    │  │  (prod) - Token Bucket                   │  │
    │  └──────────────────────────────────────────┘  │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │    Lambda Handlers                            │
    │  ┌──────────────────────────────────────────┐  │
    │  │  Chat HTTP Handler                       │  │
    │  │  @rate_limit_decorator applied           │  │
    │  │  ├─ Anonymous: 5/month                   │  │
    │  │  ├─ Authenticated: 500/month             │  │
    │  │  └─ Grace period: 1 hour                 │  │
    │  │                                          │  │
    │  │  WebSocket Handlers                      │  │
    │  │  (NO rate limiting)                      │  │
    │  │  ├─ Connect: No limits                   │  │
    │  │  ├─ Message: No limits                   │  │
    │  │  └─ Disconnect: No limits                │  │
    │  └──────────────────────────────────────────┘  │
    └────┬──────────────────────────────────────────┘
         │
    ┌────▼──────────────────────────────────────────┐
    │    DynamoDB Tables                            │
    │  ├─ users (subscription_tier field)           │
    │  ├─ rate_limits (monthly aggregates)          │
    │  ├─ usage_tracking (individual records)       │
    │  ├─ chat_messages (token estimates)           │
    │  └─ chat_sessions (conversation storage)      │
    └─────────────────────────────────────────────────┘
```

---

## 8. RECOMMENDATIONS FOR PRICING STRATEGY

### Immediate Actions

1. **Activate Tiered Rate Limiting:**
   - Check `subscription_tier` from users table
   - Apply appropriate limits based on tier
   - Return tier info in API responses

2. **Add Usage Query Endpoint:**
   - GET `/api/v1/usage` - Returns current usage
   - Include: current usage, limits, reset date, remaining quota

3. **Implement WebSocket Rate Limiting:**
   - Apply same limits to WebSocket connections
   - Track per-connection message count
   - Return rate limit info in chat responses

4. **Secure Client-Side Limits:**
   - Accept server-provided limits in responses
   - Display warning at 80% of quota
   - Pre-flight check before message send

### Medium-Term

5. **Accurate Token Counting:**
   - Use Claude's actual token counts from API responses
   - Store in message records for analytics
   - Enable token-based pricing

6. **Implement Pricing Tiers:**
   - Define clear pricing per tier
   - Monthly subscription management
   - Usage-based overage charges (if desired)

7. **Add Billing Integration:**
   - Stripe/payment processor integration
   - Invoice generation
   - Subscription management UI

### Long-Term

8. **Advanced Features per Tier:**
   - Tier-gated features (priority support, custom models, etc.)
   - Feature flags in API responses
   - UI adjustments based on tier

9. **Usage Analytics:**
   - Per-user usage dashboard
   - Aggregate usage reports
   - Churn/retention metrics

10. **Rate Limiting Optimization:**
    - Per-user API keys for higher limits
    - Burst allowance
    - Premium support for limits

---

## 10. DEPLOYMENT NOTES

**Terraform Modules:**
- `modules/rate-limiting/` - Placeholder (actual logic in code)
- `modules/auth/` - Google OAuth, user table
- `modules/dynamodb/` - Rate limit tables
- `modules/api-gateway/` - API throttling

**Environment Variables (Lambda):**
```
RATE_LIMITS_TABLE
USAGE_TRACKING_TABLE
ANONYMOUS_MONTHLY_LIMIT=5
AUTHENTICATED_MONTHLY_LIMIT=500
ENABLE_RATE_LIMITING=true
ENABLE_DEVICE_FINGERPRINTING=true
RATE_LIMIT_GRACE_PERIOD_HOURS=1
```

**Current Deployment Status:**
- ✅ Basic rate limiting active
- ✅ Device fingerprinting active
- ✅ Google OAuth working
- ❌ Tiered system not deployed
- ❌ No pricing/billing
- ❌ No usage querying

