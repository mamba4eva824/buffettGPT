# Token Limiter System - Development Plan

A token-based usage limiting system for the BuffettGPT follow-up agent using Bedrock's ConverseStream API.

## Overview

This system tracks and limits token consumption per user on a monthly basis, with:
- Hard cutoff at token limit (initially 50,000 tokens for testing)
- Notifications at 80% and 90% thresholds
- User-facing usage dashboard with progress bar
- Monthly reset aligned with subscription billing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Token Limiter System                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐ │
│  │   Frontend   │     │   Backend API    │     │      DynamoDB            │ │
│  │              │     │                  │     │                          │ │
│  │ Settings Page│◀───▶│ GET /usage       │◀───▶│ token-usage table        │ │
│  │ Progress Bar │     │                  │     │ - input_tokens           │ │
│  │ Reset Date   │     │                  │     │ - output_tokens          │ │
│  └──────────────┘     └────────┬─────────┘     │ - total_tokens           │ │
│                                │               │ - token_limit (50,000)   │ │
│                                ▼               │ - notified_80/90         │ │
│  ┌──────────────────────────────────────┐     │ - last_request_at        │ │
│  │       ConverseStream Handler         │     └──────────────────────────┘ │
│  │                                      │                                   │
│  │  1. Check token limit BEFORE request │                                   │
│  │  2. Stream response from Bedrock     │                                   │
│  │  3. Extract token counts from        │                                   │
│  │     metadata.usage in stream         │                                   │
│  │  4. Update DynamoDB atomically       │                                   │
│  │  5. Trigger notifications at 80/90%  │                                   │
│  └──────────────────────────────────────┘                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## DynamoDB Schema (Already Deployed)

Table: `buffett-chat-api-{env}-token-usage`

| Attribute | Type | Description |
|-----------|------|-------------|
| `user_id` | S (PK) | User identifier from JWT |
| `month` | S (SK) | Year-month format "YYYY-MM" |
| `input_tokens` | N | Total input tokens consumed |
| `output_tokens` | N | Total output tokens consumed |
| `total_tokens` | N | Sum of input + output tokens |
| `request_count` | N | Number of API requests made |
| `token_limit` | N | Monthly limit for this user |
| `notified_80` | BOOL | True if 80% notification sent |
| `notified_90` | BOOL | True if 90% notification sent |
| `limit_reached_at` | S | ISO timestamp when limit hit |
| `last_request_at` | S | ISO timestamp of last request |

**Schema Location:** `chat-api/terraform/modules/dynamodb/token_usage.tf`

---

## Development Phases

### Phase 1: Backend Token Tracking Service

**Create:** `chat-api/backend/src/utils/token_usage_tracker.py`

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 1.1 | Create TokenUsageTracker class | DynamoDB client initialization, table name from env |
| 1.2 | Implement `check_limit(user_id)` | Pre-request validation, returns allowance status |
| 1.3 | Implement `record_usage()` | Atomic update with ADD operation |
| 1.4 | Implement `get_usage(user_id)` | Returns current month usage + reset date |
| 1.5 | Implement notification triggers | Check thresholds after each update |
| 1.6 | Add unit tests | Mock DynamoDB with moto |

#### API Design

```python
class TokenUsageTracker:
    def __init__(self, table_name: str = None):
        """Initialize with DynamoDB table name from env or parameter."""

    def check_limit(self, user_id: str) -> dict:
        """
        Check if user can make a request.

        Returns:
            {
                "allowed": bool,
                "total_tokens": int,
                "token_limit": int,
                "percent_used": float,
                "remaining_tokens": int
            }
        """

    def record_usage(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> dict:
        """
        Record token usage atomically.

        Returns:
            {
                "total_tokens": int,
                "token_limit": int,
                "percent_used": float,
                "threshold_reached": str | None  # "80%" or "90%" or "100%" or None
            }
        """

    def get_usage(self, user_id: str) -> dict:
        """
        Get current usage statistics for user.

        Returns:
            {
                "input_tokens": int,
                "output_tokens": int,
                "total_tokens": int,
                "token_limit": int,
                "percent_used": float,
                "request_count": int,
                "reset_date": str,  # ISO format, 1st of next month
                "last_request_at": str | None
            }
        """

    def set_user_limit(self, user_id: str, token_limit: int) -> None:
        """Set custom token limit for a user (admin function)."""
```

#### Key Implementation Details

```python
# Atomic update using ADD operation
response = table.update_item(
    Key={'user_id': user_id, 'month': current_month},
    UpdateExpression='''
        ADD input_tokens :input,
            output_tokens :output,
            total_tokens :total,
            request_count :one
        SET last_request_at = :now,
            token_limit = if_not_exists(token_limit, :default_limit)
    ''',
    ExpressionAttributeValues={
        ':input': input_tokens,
        ':output': output_tokens,
        ':total': input_tokens + output_tokens,
        ':one': 1,
        ':now': datetime.utcnow().isoformat(),
        ':default_limit': DEFAULT_TOKEN_LIMIT  # 50,000 for testing
    },
    ReturnValues='ALL_NEW'
)
```

#### Month/Reset Date Calculation

```python
from datetime import datetime
from dateutil.relativedelta import relativedelta

def get_current_month() -> str:
    """Returns 'YYYY-MM' format."""
    return datetime.utcnow().strftime('%Y-%m')

def get_reset_date() -> str:
    """Returns ISO timestamp of 1st of next month."""
    today = datetime.utcnow()
    first_of_next_month = (today.replace(day=1) + relativedelta(months=1))
    return first_of_next_month.isoformat() + 'Z'
```

---

### Phase 2: ConverseStream Integration

**Modify:** Handler that calls Bedrock's ConverseStream API

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 2.1 | Pre-request limit check | Reject request if user over limit |
| 2.2 | Parse ConverseStream metadata | Extract token counts from stream |
| 2.3 | Post-request usage recording | Update DynamoDB after stream completes |
| 2.4 | Error handling | Handle partial streams, timeouts |

#### ConverseStream Token Extraction

The ConverseStream API returns a metadata event at the end of the stream:

```python
async def process_converse_stream(response_stream, user_id: str):
    """Process ConverseStream and extract token usage."""

    input_tokens = 0
    output_tokens = 0

    for event in response_stream:
        # Content blocks for streaming text
        if 'contentBlockDelta' in event:
            delta = event['contentBlockDelta']['delta']
            if 'text' in delta:
                yield delta['text']

        # Metadata contains token usage (arrives at end of stream)
        if 'metadata' in event:
            usage = event['metadata'].get('usage', {})
            input_tokens = usage.get('inputTokens', 0)
            output_tokens = usage.get('outputTokens', 0)

    # Record usage after stream completes
    tracker = TokenUsageTracker()
    result = tracker.record_usage(user_id, input_tokens, output_tokens)

    # Check for threshold notifications
    if result.get('threshold_reached'):
        await send_threshold_notification(user_id, result['threshold_reached'])
```

#### Pre-Request Validation

```python
# In the follow-up handler, before calling ConverseStream
tracker = TokenUsageTracker()
limit_check = tracker.check_limit(user_id)

if not limit_check['allowed']:
    return {
        'statusCode': 429,
        'body': json.dumps({
            'error': 'token_limit_exceeded',
            'message': 'Monthly token limit reached',
            'usage': {
                'total_tokens': limit_check['total_tokens'],
                'token_limit': limit_check['token_limit'],
                'reset_date': get_reset_date()
            }
        })
    }
```

---

### Phase 3: Usage API Endpoint

**Create:** New endpoint in `chat-api/backend/src/handlers/`

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 3.1 | Create usage handler | New Lambda function or add to existing |
| 3.2 | Add API Gateway route | `GET /usage` endpoint |
| 3.3 | JWT authentication | Extract user_id from token |
| 3.4 | Terraform updates | Lambda + API Gateway config |

#### Handler Implementation

**File:** `chat-api/backend/src/handlers/usage_handler.py`

```python
import json
import os
from src.utils.token_usage_tracker import TokenUsageTracker
from src.utils.auth import get_user_from_token

def handler(event, context):
    """GET /usage - Return token usage for authenticated user."""

    # Extract user from JWT
    auth_header = event.get('headers', {}).get('authorization', '')
    user = get_user_from_token(auth_header)

    if not user:
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Unauthorized'})
        }

    # Get usage data
    tracker = TokenUsageTracker()
    usage = tracker.get_usage(user['user_id'])

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(usage)
    }
```

#### API Response Format

```json
{
  "inputTokens": 12500,
  "outputTokens": 8700,
  "totalTokens": 21200,
  "tokenLimit": 50000,
  "percentUsed": 42.4,
  "remainingTokens": 28800,
  "requestCount": 47,
  "resetDate": "2026-02-01T00:00:00Z",
  "lastRequestAt": "2026-01-28T14:30:00Z"
}
```

#### Terraform Configuration

Add to `chat-api/terraform/modules/lambda/`:

```hcl
# Lambda function for usage endpoint
resource "aws_lambda_function" "usage_handler" {
  function_name = "${var.project_name}-${var.environment}-usage-handler"
  # ... standard lambda config

  environment {
    variables = {
      TOKEN_USAGE_TABLE = var.token_usage_table_name
      ENVIRONMENT       = var.environment
    }
  }
}

# API Gateway route
resource "aws_apigatewayv2_route" "usage" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "GET /usage"
  target    = "integrations/${aws_apigatewayv2_integration.usage_handler.id}"

  authorization_type = "JWT"
  authorizer_id      = aws_apigatewayv2_authorizer.jwt.id
}
```

---

### Phase 4: Frontend Usage Display

**Create:** Components in `frontend/src/`

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 4.1 | Create useTokenUsage hook | Data fetching with SWR/React Query |
| 4.2 | Create TokenUsageCard component | Progress bar + stats display |
| 4.3 | Create/update Settings page | Add usage section |
| 4.4 | Add API client function | `getTokenUsage()` in conversationsApi.js |
| 4.5 | Add warning banners | Show when approaching limit |

#### API Client

**File:** `frontend/src/api/usageApi.js`

```javascript
const API_URL = import.meta.env.VITE_REST_API_URL;

export async function getTokenUsage(authToken) {
  const response = await fetch(`${API_URL}/usage`, {
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to fetch usage data');
  }

  return response.json();
}
```

#### Custom Hook

**File:** `frontend/src/hooks/useTokenUsage.js`

```javascript
import { useState, useEffect } from 'react';
import { getTokenUsage } from '../api/usageApi';
import { useAuth } from '../contexts/AuthContext';

export function useTokenUsage() {
  const { token } = useAuth();
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }

    async function fetchUsage() {
      try {
        const data = await getTokenUsage(token);
        setUsage(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    fetchUsage();
  }, [token]);

  return { usage, loading, error, refetch: fetchUsage };
}
```

#### Progress Bar Component

**File:** `frontend/src/components/TokenUsageCard.jsx`

```jsx
import React from 'react';
import { useTokenUsage } from '../hooks/useTokenUsage';

export function TokenUsageCard() {
  const { usage, loading, error } = useTokenUsage();

  if (loading) return <div className="animate-pulse h-32 bg-gray-200 rounded-lg" />;
  if (error) return <div className="text-red-500">Failed to load usage data</div>;
  if (!usage) return null;

  const { totalTokens, tokenLimit, percentUsed, resetDate } = usage;

  // Color based on usage percentage
  const getProgressColor = (percent) => {
    if (percent >= 90) return 'bg-red-500';
    if (percent >= 80) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const formatDate = (isoString) => {
    return new Date(isoString).toLocaleDateString('en-US', {
      month: 'long',
      day: 'numeric',
      year: 'numeric'
    });
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold mb-4">Token Usage</h3>

      {/* Progress Bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-600 mb-1">
          <span>{totalTokens.toLocaleString()} tokens used</span>
          <span>{tokenLimit.toLocaleString()} limit</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-4">
          <div
            className={`h-4 rounded-full transition-all ${getProgressColor(percentUsed)}`}
            style={{ width: `${Math.min(percentUsed, 100)}%` }}
          />
        </div>
        <div className="text-right text-sm text-gray-500 mt-1">
          {percentUsed.toFixed(1)}% used
        </div>
      </div>

      {/* Reset Date */}
      <div className="text-sm text-gray-600">
        Resets on <span className="font-medium">{formatDate(resetDate)}</span>
      </div>

      {/* Warning Banner */}
      {percentUsed >= 80 && (
        <div className={`mt-4 p-3 rounded-lg ${
          percentUsed >= 90 ? 'bg-red-100 text-red-800' : 'bg-yellow-100 text-yellow-800'
        }`}>
          {percentUsed >= 100
            ? 'You have reached your monthly token limit.'
            : percentUsed >= 90
            ? 'Warning: You have used 90% of your monthly tokens.'
            : 'Notice: You have used 80% of your monthly tokens.'
          }
        </div>
      )}
    </div>
  );
}
```

#### Settings Page Integration

```jsx
// In Settings.jsx or create new Settings page
import { TokenUsageCard } from '../components/TokenUsageCard';

function SettingsPage() {
  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Settings</h1>

      {/* Token Usage Section */}
      <section className="mb-8">
        <h2 className="text-xl font-semibold mb-4">Usage</h2>
        <TokenUsageCard />
      </section>

      {/* Other settings sections... */}
    </div>
  );
}
```

---

### Phase 5: Notification System (Future Enhancement)

#### Tasks

| ID | Task | Description |
|----|------|-------------|
| 5.1 | In-app notifications | Toast/banner when hitting 80% |
| 5.2 | Email notifications | SES integration for 90% warning |
| 5.3 | Limit reached UX | Clear messaging when at 100% |

#### Implementation Notes

- Store notification preferences in user profile
- Use SQS + Lambda for async email sending
- Debounce notifications (only send once per threshold per month)

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TOKEN_USAGE_TABLE` | DynamoDB table name | `buffett-chat-api-{env}-token-usage` |
| `DEFAULT_TOKEN_LIMIT` | Default monthly limit | `50000` |
| `TOKEN_LIMIT_ANONYMOUS` | Limit for anonymous users | `1000` |
| `TOKEN_LIMIT_AUTHENTICATED` | Limit for authenticated users | `50000` |
| `TOKEN_LIMIT_PREMIUM` | Limit for premium users | `500000` |

### Token Limits by Tier

| User Tier | Monthly Token Limit | Notes |
|-----------|---------------------|-------|
| Anonymous | 1,000 | Very limited, encourages sign-up |
| Authenticated (Free) | 50,000 | Testing limit |
| Premium | 500,000 | Paid tier |
| Enterprise | Unlimited | Custom contracts |

---

## Testing Strategy

### Unit Tests

```bash
cd chat-api/backend
pytest tests/unit/test_token_usage_tracker.py -v
```

**Test Cases:**
- `test_check_limit_under_limit` - User within limit
- `test_check_limit_at_limit` - User exactly at limit
- `test_check_limit_over_limit` - User over limit
- `test_record_usage_new_user` - First usage creates record
- `test_record_usage_existing_user` - Atomic increment
- `test_threshold_notifications` - 80% and 90% triggers
- `test_month_rollover` - New month resets count
- `test_get_reset_date` - Correct date calculation

### Integration Tests

```bash
pytest tests/integration/test_token_limiter_integration.py -v
```

**Test Cases:**
- Full flow: check → stream → record → verify
- Concurrent requests (race conditions)
- DynamoDB conditional updates

---

## Deployment Checklist

### Phase 1 (Backend Service) - COMPLETED
- [x] Create `token_usage_tracker.py`
- [x] Add unit tests (36 tests passing)
- [x] Run tests locally with moto
- [ ] Deploy to dev environment

### Phase 2 (ConverseStream Integration) - COMPLETED
- [x] Modify follow-up handler (`analysis_followup.py`)
- [x] Add pre-request limit check
- [x] Add post-request usage recording with actual token counts
- [x] Switch from `invoke_agent` to `converse_stream` API
- [x] Add unit tests for token limiting (28 tests passing)
- [ ] Test with real Bedrock calls

### Phase 3 (API Endpoint)
- [ ] Create usage handler Lambda
- [ ] Add Terraform configuration
- [ ] Deploy API Gateway route
- [ ] Test endpoint authentication

### Phase 4 (Frontend)
- [ ] Create API client function
- [ ] Create useTokenUsage hook
- [ ] Create TokenUsageCard component
- [ ] Add to Settings page
- [ ] Test UI with real data

### Phase 5 (Notifications)
- [ ] Implement in-app notifications
- [ ] Set up SES for email (optional)
- [ ] Test notification triggers

---

## Files to Create/Modify

| Action | File Path |
|--------|-----------|
| CREATE | `chat-api/backend/src/utils/token_usage_tracker.py` |
| CREATE | `chat-api/backend/src/handlers/usage_handler.py` |
| CREATE | `chat-api/backend/tests/unit/test_token_usage_tracker.py` |
| MODIFY | `chat-api/backend/src/handlers/` (follow-up handler) |
| CREATE | `frontend/src/api/usageApi.js` |
| CREATE | `frontend/src/hooks/useTokenUsage.js` |
| CREATE | `frontend/src/components/TokenUsageCard.jsx` |
| CREATE | `frontend/src/pages/Settings.jsx` (if doesn't exist) |
| MODIFY | `chat-api/terraform/modules/lambda/` (new Lambda) |
| MODIFY | `chat-api/terraform/modules/api-gateway/` (new route) |

---

## Related Documentation

- [FOLLOWUP_AGENT.md](FOLLOWUP_AGENT.md) - Follow-up agent that uses ConverseStream
- [RESEARCH_SYSTEM_ARCHITECTURE.md](RESEARCH_SYSTEM_ARCHITECTURE.md) - Overall system architecture
- [Terraform: token_usage.tf](../../terraform/modules/dynamodb/token_usage.tf) - DynamoDB table schema

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-28 | 1.0 | Initial development plan |
| 2026-01-28 | 1.1 | Phase 1 & 2 complete: TokenUsageTracker + ConverseStream integration |
