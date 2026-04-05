# Admin Dashboard — Implementation Guide

## Overview

The admin dashboard provides runtime-configurable settings for the Buffett app without code changes or redeployment. Settings are stored in a DynamoDB `admin-config` table. Lambda functions read from DynamoDB first, falling back to environment variables and hardcoded defaults.

---

## 1. Configurable Settings Inventory

### 1.1 Token Limits

| Setting | Current Value | Source | File |
|---------|--------------|--------|------|
| Plus tier monthly limit | 2,000,000 | env var `TOKEN_LIMIT_PLUS` | `src/utils/stripe_service.py:34` |
| Free tier monthly limit | 100,000 | env var `TOKEN_LIMIT_FREE` | `src/utils/stripe_service.py:35` |
| Default fallback limit | 50,000 (overridden per env) | env var `DEFAULT_TOKEN_LIMIT` | `src/utils/token_usage_tracker.py:79` |
| Anonymous access | 0 | hardcoded `DEFAULT_LIMITS` | `src/utils/token_usage_tracker.py:58` |
| Free follow-up access | 0 | hardcoded `DEFAULT_LIMITS` | `src/utils/token_usage_tracker.py:59` |
| Plus follow-up access | 1,000,000 | hardcoded `DEFAULT_LIMITS` | `src/utils/token_usage_tracker.py:60` |

**Environment overrides** (via Terraform `main.tf`):
- Dev: `DEFAULT_TOKEN_LIMIT = 100,000`
- Staging: `DEFAULT_TOKEN_LIMIT = 500,000`
- Prod: `DEFAULT_TOKEN_LIMIT = 2,000,000`

### 1.2 Rate Limits

#### Monthly Request Limits

| Setting | Current Value | Source | File |
|---------|--------------|--------|------|
| Anonymous monthly | 5 | env var `ANONYMOUS_MONTHLY_LIMIT` | `src/utils/rate_limiter.py:40` |
| Authenticated monthly | 500 | env var `AUTHENTICATED_MONTHLY_LIMIT` | `src/utils/rate_limiter.py:41` |
| Premium monthly | 2,000 (4x authenticated) | computed | `src/utils/rate_limiter.py:181` |
| Grace period hours | 1 | env var `RATE_LIMIT_GRACE_PERIOD_HOURS` | `src/utils/rate_limiter.py:43` |
| Rate limiting enabled | true | env var `ENABLE_RATE_LIMITING` | `src/utils/rate_limiter.py:44` |
| Device fingerprinting | true | env var `ENABLE_DEVICE_FINGERPRINTING` | `src/utils/rate_limiter.py:42` |

#### Tiered Rate Limits (Hardcoded)

Source: `src/utils/tiered_rate_limiter.py:29-66`

| Tier | Daily | Hourly | Per Minute | Burst | Session TTL |
|------|-------|--------|------------|-------|-------------|
| anonymous | 5 | 3 | 2 | 2 | 2 hours |
| authenticated | 20 | 10 | 5 | 3 | 7 days |
| premium | 1,000 | 100 | 20 | 10 | 30 days |
| enterprise | 10,000 | 1,000 | 100 | 50 | 90 days |

### 1.3 Model Configuration

| Setting | Current Value | Source | File |
|---------|--------------|--------|------|
| Follow-up model ID | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | env var `FOLLOWUP_MODEL_ID` | `src/handlers/analysis_followup.py:111` |
| Follow-up temperature | 0.7 | hardcoded | `src/handlers/analysis_followup.py:625,1073` |
| Follow-up maxTokens | 2,048 | hardcoded | `src/handlers/analysis_followup.py:1073` |
| Market intel model ID | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | env var `MARKET_INTEL_MODEL_ID` | `src/handlers/market_intel_chat.py:81` |
| Market intel temperature | 0.3 | hardcoded | `src/handlers/market_intel_chat.py:557,738` |
| Market intel maxTokens | 2,048 | hardcoded | `src/handlers/market_intel_chat.py` |
| Max orchestration turns | 10 | hardcoded | `src/handlers/market_intel_chat.py` |

**Note**: Model IDs remain in Terraform/env vars (require IAM validation). Only temperature, maxTokens, and orchestration turns move to admin config.

### 1.4 Feature Flags

| Setting | Current Value | Source | File |
|---------|--------------|--------|------|
| Rate limiting enabled | true | env var `ENABLE_RATE_LIMITING` | `src/utils/rate_limiter.py:44` |
| Device fingerprinting | true | env var `ENABLE_DEVICE_FINGERPRINTING` | `src/utils/rate_limiter.py:42` |

**Infrastructure flags (remain in Terraform — not admin-configurable)**:
- `enable_search`, `enable_analysis_api`, `enable_research_api`, `enable_market_intelligence_api`
- `enable_subscription_routes`, `enable_stripe_webhook`, `enable_waitlist_routes`

### 1.5 Notification Thresholds

| Setting | Current Value | Source | File |
|---------|--------------|--------|------|
| Warning threshold | 80% | hardcoded | `src/utils/token_usage_tracker.py:493-552` |
| Critical threshold | 90% | hardcoded | `src/utils/token_usage_tracker.py:493-552` |

DynamoDB flags: `notified_80`, `notified_90`, `limit_reached_at`

### 1.6 Referral Tiers

Source: `src/handlers/subscription_handler.py:43-46`

| Referral Count | Trial Days | Description |
|----------------|------------|-------------|
| 5+ | 90 | 3 Months Free Plus |
| 3+ | 30 | 1 Month Free Plus |

---

## 2. DynamoDB Admin Config Data Model

**Table**: `{project_name}-{environment}-admin-config`
**PK**: `config_key` (String)
**Billing**: PAY_PER_REQUEST

### Item Examples

```json
{
  "config_key": "token_limits",
  "plus": 2000000,
  "free": 100000,
  "default_fallback": 100000,
  "followup_access": {
    "anonymous": 0,
    "free": 0,
    "plus": 1000000
  },
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "rate_limits",
  "anonymous_monthly": 5,
  "authenticated_monthly": 500,
  "grace_period_hours": 1,
  "tiered": {
    "anonymous": { "daily": 5, "hourly": 3, "per_minute": 2, "burst": 2, "session_ttl_hours": 2 },
    "authenticated": { "daily": 20, "hourly": 10, "per_minute": 5, "burst": 3, "session_ttl_hours": 168 },
    "premium": { "daily": 1000, "hourly": 100, "per_minute": 20, "burst": 10, "session_ttl_hours": 720 },
    "enterprise": { "daily": 10000, "hourly": 1000, "per_minute": 100, "burst": 50, "session_ttl_hours": 2160 }
  },
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "model_config",
  "followup_temperature": 0.7,
  "followup_max_tokens": 2048,
  "market_intel_temperature": 0.3,
  "market_intel_max_tokens": 2048,
  "max_orchestration_turns": 10,
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "feature_flags",
  "enable_rate_limiting": true,
  "enable_device_fingerprinting": true,
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "notification_thresholds",
  "warning_percent": 80,
  "critical_percent": 90,
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "referral_tiers",
  "tiers": [
    { "threshold": 5, "trial_days": 90 },
    { "threshold": 3, "trial_days": 30 }
  ],
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "admin@example.com"
}

{
  "config_key": "admin_emails",
  "emails": ["your@email.com"],
  "updated_at": "2026-03-24T12:00:00Z",
  "updated_by": "system"
}
```

---

## 3. API Contract

### GET /admin/settings

Returns all config categories.

**Auth**: Requires JWT with `is_admin: true`

**Response** (200):
```json
{
  "token_limits": { "plus": 2000000, "free": 100000, "default_fallback": 100000, "followup_access": { ... } },
  "rate_limits": { "anonymous_monthly": 5, "authenticated_monthly": 500, "tiered": { ... } },
  "model_config": { "followup_temperature": 0.7, "followup_max_tokens": 2048, ... },
  "feature_flags": { "enable_rate_limiting": true, ... },
  "notification_thresholds": { "warning_percent": 80, "critical_percent": 90 },
  "referral_tiers": { "tiers": [ ... ] }
}
```

**Error responses**:
- `401` — Missing or invalid JWT
- `403` — User is not an admin

### PUT /admin/settings/{category}

Updates a single config category.

**Auth**: Requires JWT with `is_admin: true`

**Path**: `category` is one of: `token_limits`, `rate_limits`, `model_config`, `feature_flags`, `notification_thresholds`, `referral_tiers`

**Request body** (example for token_limits):
```json
{
  "plus": 3000000,
  "free": 200000,
  "default_fallback": 100000
}
```

**Response** (200):
```json
{
  "category": "token_limits",
  "values": { "plus": 3000000, "free": 200000, "default_fallback": 100000 },
  "updated_at": "2026-03-24T12:30:00Z",
  "updated_by": "admin@example.com"
}
```

**Validation rules**:

| Category | Field | Min | Max |
|----------|-------|-----|-----|
| token_limits | plus, free, default_fallback | 1,000 | 100,000,000 |
| rate_limits | anonymous_monthly | 0 | 1,000 |
| rate_limits | authenticated_monthly | 0 | 100,000 |
| model_config | *_temperature | 0.0 | 1.0 |
| model_config | *_max_tokens | 256 | 8,192 |
| model_config | max_orchestration_turns | 1 | 50 |
| notification_thresholds | *_percent | 1 | 99 |
| referral_tiers | threshold | 1 | 100 |
| referral_tiers | trial_days | 1 | 365 |

**Error responses**:
- `400` — Validation error (with field-level details)
- `401` — Missing or invalid JWT
- `403` — User is not an admin
- `404` — Unknown category

---

## 4. Auth Flow Changes

### Current JWT payload
```json
{
  "user_id": "google-sub-id",
  "email": "user@example.com",
  "name": "User Name",
  "subscription_tier": "free",
  "exp": 1711900800,
  "iat": 1711296000,
  "iss": "buffett-chat-api"
}
```

### New JWT payload (added field)
```json
{
  "user_id": "google-sub-id",
  "email": "user@example.com",
  "name": "User Name",
  "subscription_tier": "free",
  "is_admin": false,
  "exp": 1711900800,
  "iat": 1711296000,
  "iss": "buffett-chat-api"
}
```

### Auth callback changes (`auth_callback.py`)

After Google token verification (~line 140):
1. Read `admin_emails` config key from admin-config DynamoDB table
2. Check if user's email is in the list
3. Set `is_admin` in JWT payload and response user object

### Authorizer changes (`auth_verify.py`)

In `create_policy()` (~line 197), add `is_admin` from decoded JWT claims to authorizer context:
```python
response["context"] = {
    "user_id": user_id,
    "is_admin": str(claims.get("is_admin", False)).lower(),
    "environment": ENVIRONMENT,
    "project": PROJECT_NAME
}
```

### Admin handler authorization check
```python
def _is_admin(event):
    context = event.get('requestContext', {}).get('authorizer', {}).get('lambda', {})
    return context.get('is_admin') == 'true'
```

---

## 5. ConfigLoader Interface

**File**: `chat-api/backend/src/utils/config_loader.py`

```python
class ConfigLoader:
    """Reads settings from DynamoDB admin-config table.
    Falls back to env vars then hardcoded defaults."""

    _cache = {}           # category -> dict of settings
    _cache_ttl = 300      # 5 minutes
    _last_refresh = 0     # epoch timestamp

    @classmethod
    def get(cls, category: str, key: str, default=None):
        """Get a single config value.

        Example: ConfigLoader.get('token_limits', 'plus', 2000000)
        """

    @classmethod
    def get_category(cls, category: str) -> dict:
        """Get all values for a config category.

        Example: ConfigLoader.get_category('rate_limits')
        """

    @classmethod
    def _maybe_refresh(cls):
        """Refresh cache if older than _cache_ttl."""

    @classmethod
    def _load_from_dynamodb(cls):
        """Scan admin-config table, populate _cache.
        No-op if ADMIN_CONFIG_TABLE env var is not set."""
```

### Fallback chain
1. DynamoDB admin-config table (if `ADMIN_CONFIG_TABLE` env var is set)
2. Environment variable (e.g., `TOKEN_LIMIT_PLUS`)
3. Hardcoded default in the calling code

### Integration pattern
```python
# Before (rate_limiter.py:40)
ANONYMOUS_LIMIT = int(os.environ.get('ANONYMOUS_MONTHLY_LIMIT', '5'))

# After
from utils.config_loader import ConfigLoader
ANONYMOUS_LIMIT = ConfigLoader.get('rate_limits', 'anonymous_monthly',
                                    int(os.environ.get('ANONYMOUS_MONTHLY_LIMIT', '5')))
```

Settings changes propagate within 5 minutes (cache TTL) without redeployment.

---

## 6. Frontend Components

### AdminDashboard (`frontend/src/components/admin/AdminDashboard.jsx`)

Collapsible card sections matching the sand/warm Tailwind theme:

1. **Token Limits** — Number inputs for Plus, Free, Default fallback, follow-up access per tier
2. **Rate Limits** — Monthly limits + tiered limits table (editable grid)
3. **Model Configuration** — Temperature sliders (0.0–1.0), maxTokens dropdowns, orchestration turns
4. **Feature Flags** — Toggle switches
5. **Notification Thresholds** — Percentage inputs with preview bar
6. **Referral Tiers** — Editable rows (threshold + trial days)

Each section has a Save button that calls `PUT /admin/settings/{category}`.
Success/error toast notifications on save.

### Admin API client (`frontend/src/api/adminApi.js`)

```javascript
export const adminApi = {
  getSettings: async (token) => {
    // GET /admin/settings with Bearer token
  },
  updateSettings: async (token, category, values) => {
    // PUT /admin/settings/{category} with Bearer token + JSON body
  },
};
```

### Navigation (`frontend/src/App.jsx`)

Conditional "Admin" pill in mode toggle (~line 1523):
- Visible only when `user?.is_admin === true`
- Sets `appMode` to `'admin'`
- Renders `<AdminDashboard />` when active (~line 1589)

---

## 7. Files to Create/Modify

| File | Action | Phase |
|------|--------|-------|
| `chat-api/terraform/modules/dynamodb/admin_config.tf` | CREATE | 1 |
| `chat-api/terraform/modules/dynamodb/outputs.tf` | MODIFY | 1 |
| `chat-api/backend/src/utils/config_loader.py` | CREATE | 1 |
| `chat-api/backend/src/handlers/admin_handler.py` | CREATE | 1 |
| `chat-api/backend/src/handlers/auth_callback.py` | MODIFY | 1 |
| `chat-api/backend/src/handlers/auth_verify.py` | MODIFY | 1 |
| `chat-api/terraform/modules/lambda/` | MODIFY | 1 |
| `chat-api/terraform/modules/api-gateway/main.tf` | MODIFY | 1 |
| `chat-api/terraform/modules/api-gateway/variables.tf` | MODIFY | 1 |
| `chat-api/terraform/environments/dev/main.tf` | MODIFY | 1 |
| `chat-api/backend/scripts/build_lambdas.sh` | MODIFY | 1 |
| `chat-api/backend/src/utils/rate_limiter.py` | MODIFY | 1 |
| `chat-api/backend/src/utils/tiered_rate_limiter.py` | MODIFY | 1 |
| `chat-api/backend/src/utils/token_usage_tracker.py` | MODIFY | 1 |
| `chat-api/backend/src/utils/stripe_service.py` | MODIFY | 1 |
| `chat-api/backend/src/handlers/analysis_followup.py` | MODIFY | 1 |
| `chat-api/backend/src/handlers/market_intel_chat.py` | MODIFY | 1 |
| `chat-api/backend/src/handlers/subscription_handler.py` | MODIFY | 1 |
| `frontend/src/auth.jsx` | MODIFY | 2 |
| `frontend/src/components/admin/AdminDashboard.jsx` | CREATE | 2 |
| `frontend/src/api/adminApi.js` | CREATE | 2 |
| `frontend/src/App.jsx` | MODIFY | 2 |

---

## 8. Bootstrap

Seed admin email after deploying the DynamoDB table:

```bash
aws dynamodb put-item --table-name buffett-dev-admin-config \
  --item '{"config_key":{"S":"admin_emails"},"emails":{"L":[{"S":"your@email.com"}]}}'
```

After seeding, log out and back in to get a new JWT with `is_admin: true`.

---

## 9. Settings NOT Admin-Configurable (Remain in Terraform)

- Model IDs (require IAM permissions)
- Infrastructure feature flags (control Lambda/route creation)
- DynamoDB billing mode, PITR, deletion protection
- CloudWatch log retention
- CORS allowed origins
- Secrets Manager ARNs
- KMS key configuration
