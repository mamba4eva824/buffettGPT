# Token Usage Tracker Integration Tests

## Overview

This document describes the integration test suites for the `TokenUsageTracker` module, which implements anniversary-based billing for token consumption tracking.

**Test Files**:
- `chat-api/backend/tests/integration/test_token_tracker_integration.py` - Module-level integration tests
- `chat-api/backend/tests/integration/test_api_token_limit.py` - API-level end-to-end tests

## Test Infrastructure

| Component | Value |
|-----------|-------|
| Test Table (Module Tests) | `buffett-test-token-usage-integration` |
| Test Table (API Tests) | `token-usage-dev-buffett` (production dev) |
| Test User Prefix | `integration-test-{uuid}` |
| Default Test Limit | 10,000 tokens |
| Cleanup | Automatic after each test |

The module-level tests create a dedicated DynamoDB table with the correct schema (`billing_period` as sort key). The API-level tests use the production dev table to verify end-to-end behavior.

## Running the Tests

```bash
# Run all integration tests
cd chat-api/backend
pytest tests/integration/test_token_tracker_integration.py -v -s

# Run specific test class
pytest tests/integration/test_token_tracker_integration.py::TestIntegrationBasicOperations -v -s

# Run specific test
pytest tests/integration/test_token_tracker_integration.py::TestIntegrationEdgeCases::test_concurrent_requests_atomic_add -v -s

# Manual cleanup (if needed)
python -c "from tests.integration.test_token_tracker_integration import manual_cleanup; manual_cleanup()"
```

## Test Results Summary

**Status**: All 22 tests passing
**Execution Time**: ~25 seconds

## Test Scenarios

### 1. Basic Operations (4 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | `test_new_user_gets_billing_day_set` | New user's `billing_day` is set to current day | PASS |
| 2 | `test_token_accumulation_multiple_calls` | Multiple `record_usage` calls accumulate correctly | PASS |
| 3 | `test_check_limit_returns_false_when_over_limit` | `check_limit` returns `allowed=False` when exceeded | PASS |
| 4 | `test_check_limit_returns_true_when_under_limit` | `check_limit` returns `allowed=True` when under limit | PASS |

### 2. Threshold Notifications (4 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 5 | `test_80_percent_threshold_triggers` | Triggers notification at 80% usage | PASS |
| 6 | `test_90_percent_threshold_triggers` | Triggers notification at 90% usage | PASS |
| 7 | `test_100_percent_threshold_triggers` | Sets `limit_reached_at` when limit hit | PASS |
| 8 | `test_threshold_only_triggers_once` | Thresholds only fire once per period | PASS |

### 3. Anniversary-Based Reset (3 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 9 | `test_billing_period_key_format` | Key uses `YYYY-MM-DD` format | PASS |
| 10 | `test_usage_isolated_by_billing_period` | Different periods don't mix usage | PASS |
| 11 | `test_get_usage_returns_correct_period_data` | `get_usage` returns current period only | PASS |

### 4. Edge Cases (5 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 12 | `test_concurrent_requests_atomic_add` | 10 parallel requests - no token loss | PASS |
| 13 | `test_missing_user_check_limit_graceful` | Returns `allowed=True` with defaults | PASS |
| 14 | `test_missing_user_get_usage_graceful` | Returns empty response gracefully | PASS |
| 15 | `test_invalid_billing_day_recovery` | Handles corrupted data (value 99) | PASS |
| 16 | `test_zero_token_usage` | Zero tokens recorded correctly | PASS |

### 5. Admin Operations (3 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 17 | `test_set_user_limit_persists` | Custom limit persists across calls | PASS |
| 18 | `test_reset_notifications_clears_flags` | Clears notification flags | PASS |
| 19 | `test_set_user_limit_for_nonexistent_creates_record` | Creates record for new user | PASS |

### 6. Timestamps (3 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 20 | `test_last_request_at_updates` | Updates on each request | PASS |
| 21 | `test_subscribed_at_immutable` | Only set once, never changes | PASS |
| 22 | `test_reset_date_format` | Valid ISO format with Z suffix | PASS |

## Key Findings

### Concurrency Safety
The atomic ADD operation in DynamoDB ensures no token loss under concurrent requests. Test #12 confirms 10 parallel requests all accumulate correctly.

### Edge Case Handling
- Missing users are handled gracefully (fail-open for availability)
- Invalid `billing_day` values are clamped internally (1-31)
- Zero token usage is recorded correctly

### Schema Migration (Completed February 2026)
The production table has been migrated from `buffett-dev-token-usage` (with `month` sort key) to `token-usage-dev-buffett` (with `billing_period` sort key). This migration enables anniversary-based billing where token limits reset on the user's subscription day rather than calendar month boundaries.

| Environment | Old Table | New Table |
|-------------|-----------|-----------|
| dev | `buffett-dev-token-usage` | `token-usage-dev-buffett` |
| staging | `buffett-staging-token-usage` | `token-usage-staging-buffett` |
| prod | `buffett-prod-token-usage` | `token-usage-prod-buffett` |

**Migration Script**: `chat-api/backend/scripts/migrate_token_usage.py`

---

# Handler-Level Token Limit Tests

## Overview

In addition to the integration tests above, handler-level tests verify that the Lambda handler correctly enforces token limits and returns proper HTTP responses.

**Test File**: `chat-api/backend/tests/unit/test_analysis_followup.py`

## Test Coverage Matrix

| Test Level | What It Verifies | Status |
|------------|------------------|--------|
| Module Test (TokenUsageTracker) | `check_limit()` returns `allowed=False` | ✅ Tested |
| Handler Test (analysis_followup) | Handler returns HTTP 429 | ✅ Tested |
| Integration Test (API Gateway → Lambda) | Full API rejects request | ✅ Tested |

## Handler Tests (7 tests)

### Core Token Limit Tests (4 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | `test_returns_429_when_token_limit_exceeded` | API Gateway path returns 429 with correct headers/body | PASS |
| 2 | `test_streaming_returns_error_when_token_limit_exceeded` | Streaming path returns SSE error event | PASS |
| 3 | `test_records_token_usage_after_successful_request` | Usage recorded with correct token counts | PASS |
| 4 | `test_threshold_notification_included_in_response` | 80%/90% thresholds included in response | PASS |

### Edge Case Tests (3 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 5 | `test_bedrock_not_called_when_limit_exceeded` | Cost protection: Bedrock API not called when 429 | PASS |
| 6 | `test_streaming_bedrock_not_called_when_limit_exceeded` | Cost protection: Streaming path doesn't call Bedrock | PASS |
| 7 | `test_limit_check_exception_returns_500` | Exception handling: DynamoDB errors return 500 | PASS |

## Running Handler Tests

```bash
cd chat-api/backend

# Run all token limit tests
pytest tests/unit/test_analysis_followup.py -v -k "token_limit or bedrock_not_called or limit_check_exception"

# Run all handler tests
pytest tests/unit/test_analysis_followup.py -v
```

## Key Handler Behaviors

### HTTP 429 Response Format
When token limit is exceeded, the API Gateway path returns:

```json
{
    "statusCode": 429,
    "headers": {
        "Content-Type": "application/json",
        "X-RateLimit-Limit": "50000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "2026-02-01T00:00:00Z"
    },
    "body": {
        "success": false,
        "error": "token_limit_exceeded",
        "message": "Monthly token limit reached...",
        "usage": {
            "total_tokens": 50000,
            "token_limit": 50000,
            "percent_used": 100.0,
            "reset_date": "2026-02-01T00:00:00Z"
        }
    }
}
```

### Streaming SSE Error Event
When token limit is exceeded, the streaming path yields:

```
event: error
data: {"type": "token_limit_exceeded", "error": "token_limit_exceeded", "message": "Monthly token limit reached...", ...}
```

### Cost Protection
Both code paths verify that Bedrock is **never called** when the limit check fails:
- `mock_boto3['bedrock_runtime'].converse.assert_not_called()`
- `mock_boto3['bedrock_runtime'].converse_stream.assert_not_called()`

### Exception Handling
The handler uses `limit_check.get('allowed', True)` which means:
- If `check_limit()` succeeds but missing `allowed` key → defaults to **allowed** (fail-open)
- If `check_limit()` throws exception → handler crashes with 500 error (fail-closed)

**Note**: No try/except wrapper exists around the limit check (lines 848-849 in `analysis_followup.py`).

## Code Locations

| Location | Purpose |
|----------|---------|
| `analysis_followup.py:848-865` | API Gateway token limit check |
| `analysis_followup.py:427-435` | Streaming token limit check |
| `analysis_followup.py:352-371` | Error response formatting |
| `test_analysis_followup.py:611` | 429 response test |
| `test_analysis_followup.py:655` | Streaming error test |

---

# API-Level Integration Tests (End-to-End)

## Overview

These tests verify token limit enforcement through the deployed API Gateway → Lambda pipeline, ensuring the full production stack correctly returns 429 responses when users exceed their token limits.

**Test File**: `chat-api/backend/tests/integration/test_api_token_limit.py`

## Test Infrastructure

| Component | Value |
|-----------|-------|
| Target Table | `token-usage-dev-buffett` (production dev table) |
| Test User Prefix | `integration-test-api-{uuid}` |
| Default Test Limit | 10,000 tokens |
| API Endpoint | `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/research/followup` |
| Cleanup | Automatic after each test |

## Running the Tests

```bash
cd chat-api/backend

# Set required environment variable
export BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id buffett-dev-jwt-secret --query 'SecretString' --output text)

# Run all API integration tests
pytest tests/integration/test_api_token_limit.py -v -s -m integration

# Run specific test
pytest tests/integration/test_api_token_limit.py::TestApiTokenLimitEnforcement::test_api_returns_429_when_limit_exceeded -v -s
```

## Test Results Summary

**Status**: All 4 tests passing
**Execution Time**: ~7 seconds

## Test Scenarios

### API Token Limit Enforcement (4 tests)

| # | Test | Description | Status |
|---|------|-------------|--------|
| 1 | `test_api_returns_429_when_limit_exceeded` | API returns 429 with correct body when user over limit | PASS |
| 2 | `test_api_allows_request_when_under_limit` | API does NOT return 429 when user under limit | PASS |
| 3 | `test_api_returns_401_without_auth` | API returns 401 when no JWT provided | PASS |
| 4 | `test_rate_limit_headers_format` | X-RateLimit headers have correct format | PASS |

## Key Behaviors Verified

### 429 Response Format
When token limit is exceeded, the API returns:

```json
{
    "statusCode": 429,
    "headers": {
        "Content-Type": "application/json",
        "X-RateLimit-Limit": "10000",
        "X-RateLimit-Remaining": "0",
        "X-RateLimit-Reset": "2026-03-01T00:00:00Z"
    },
    "body": "{\"success\": false, \"error\": \"token_limit_exceeded\", ...}"
}
```

### Anniversary-Based Reset Dates
The `X-RateLimit-Reset` header correctly reflects the user's next billing period based on their `billing_day`, not the calendar month end.

Example: User with `billing_day=2` who exceeds limit on Feb 1 gets reset date of March 2.

### Cost Protection
The 429 response is returned **before** Bedrock is invoked, ensuring no API costs are incurred for over-limit requests.

### Response Wrapping
The test handles API Gateway's response wrapping format where the Lambda response body is JSON-encoded as a string inside the outer response object.

## Environment Variables Required

| Variable | Description | Required |
|----------|-------------|----------|
| `BUFFETT_JWT_SECRET` | JWT signing secret from AWS Secrets Manager | Yes |
| `AWS_PROFILE` | AWS credentials profile | Yes |
| `ANALYSIS_FOLLOWUP_URL` | Override API URL (optional) | No |

## Code Locations

| Location | Purpose |
|----------|---------|
| `test_api_token_limit.py:159-210` | Create over-limit user in DynamoDB |
| `test_api_token_limit.py:213-260` | Create under-limit user in DynamoDB |
| `test_api_token_limit.py:263-291` | Cleanup user records |
| `test_api_token_limit.py:340-411` | 429 response test |
| `test_api_token_limit.py:413-468` | Under-limit test |

---

# Security Recommendations for Stripe Integration

When integrating Stripe for token purchases, the following security considerations should be addressed:

## 1. Payment Verification (Critical)

### Issue
Tokens should only be added after verified payment confirmation from Stripe.

### Recommendations
```
- Use Stripe webhooks (not client-side confirmation) to credit tokens
- Verify webhook signatures using STRIPE_WEBHOOK_SECRET
- Implement idempotency keys to prevent duplicate credits
- Store Stripe payment_intent_id with each token credit for audit trail
```

**Example DynamoDB schema addition:**
```python
{
    'user_id': 'user-123',
    'billing_period': '2025-02-01',
    'token_credits': [
        {
            'stripe_payment_intent': 'pi_xxx',
            'tokens_added': 100000,
            'credited_at': '2025-02-01T10:00:00Z',
            'idempotency_key': 'uuid-xxx'
        }
    ]
}
```

## 2. Rate Limiting on Credit Operations

### Issue
Malicious actors could attempt to exploit the token credit system.

### Recommendations
```
- Rate limit token credit API endpoints (separate from usage endpoints)
- Implement maximum credit per transaction limits
- Add cooldown periods between purchases
- Monitor for unusual credit patterns (velocity checks)
```

## 3. Audit Trail & Logging

### Issue
Financial transactions require complete audit trails.

### Recommendations
```
- Log all token credit operations to CloudWatch with:
  - user_id, stripe_payment_id, tokens_credited, timestamp, IP
- Store credit history in separate DynamoDB table
- Implement read-only admin endpoints for auditing
- Set up CloudWatch alarms for:
  - Unusual credit volumes
  - Failed webhook verifications
  - Duplicate credit attempts
```

## 4. Webhook Security

### Issue
Stripe webhooks are the source of truth for payments.

### Recommendations
```
- Verify webhook signatures (stripe.Webhook.construct_event)
- Whitelist Stripe IP addresses at WAF level
- Use HTTPS endpoints only
- Implement replay attack prevention:
  - Check webhook timestamp (reject if > 5 minutes old)
  - Store processed webhook IDs to prevent replays
```

**Example verification:**
```python
import stripe

def verify_stripe_webhook(payload, sig_header, webhook_secret):
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )

        # Check timestamp to prevent replay
        if time.time() - event.created > 300:  # 5 minutes
            raise ValueError("Webhook too old")

        return event
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")
```

## 5. Token Balance Integrity

### Issue
Token balances are financial assets that must be protected.

### Recommendations
```
- Use DynamoDB conditional writes to prevent race conditions
- Implement balance check before allowing usage (double-check pattern)
- Store token_limit separately from purchased tokens
- Consider optimistic locking with version numbers
```

**Example conditional write:**
```python
# Only credit if payment hasn't been processed
table.update_item(
    Key={'user_id': user_id, 'billing_period': period},
    UpdateExpression='ADD purchased_tokens :tokens',
    ConditionExpression='attribute_not_exists(processed_payments.#pid)',
    ExpressionAttributeNames={'#pid': payment_intent_id},
    ExpressionAttributeValues={':tokens': token_amount}
)
```

## 6. Separation of Concerns

### Issue
Token usage tracking and payment processing should be decoupled.

### Recommendations
```
- Separate Lambda functions for:
  1. Token usage tracking (existing)
  2. Stripe webhook handler (new)
  3. Token credit service (new)
- Use SQS between webhook handler and credit service for:
  - Retry logic
  - Dead letter queue for failed credits
  - Audit trail
```

## 7. Encryption & Data Protection

### Issue
Payment-related data requires additional protection.

### Recommendations
```
- Encrypt Stripe API keys in AWS Secrets Manager (existing)
- Use KMS encryption for DynamoDB (existing)
- Never store full card numbers (Stripe handles this)
- PII fields should be encrypted at application level
- Implement data retention policies for payment records
```

## 8. Fraud Prevention

### Issue
Token systems are targets for fraud.

### Recommendations
```
- Implement velocity checks:
  - Max purchases per day/week
  - Unusual usage patterns
- Flag accounts for review if:
  - New account + large purchase
  - Multiple failed payment attempts
  - Usage patterns don't match purchase patterns
- Consider requiring email verification before first purchase
```

## 9. Rollback & Recovery

### Issue
Failed transactions or disputes need handling.

### Recommendations
```
- Implement token deduction for:
  - Stripe chargebacks (webhook: charge.dispute.created)
  - Refund requests (webhook: charge.refunded)
- Store sufficient data to reverse any credit
- Alert on disputes immediately
```

## 10. Testing Recommendations

### Issue
Payment integrations need thorough testing.

### Recommendations
```
- Use Stripe test mode for integration tests
- Test webhook signature verification
- Test idempotency (replay same webhook)
- Test concurrent credit attempts
- Load test the credit pathway
- Test failure scenarios:
  - Webhook arrives before payment confirmed
  - DynamoDB write fails after Stripe confirms
  - Partial failures in multi-step processes
```

## Priority Matrix

| Priority | Recommendation | Effort |
|----------|---------------|--------|
| P0 (Critical) | Webhook signature verification | Low |
| P0 (Critical) | Idempotency for credits | Medium |
| P0 (Critical) | Audit logging | Low |
| P1 (High) | Rate limiting on credits | Medium |
| P1 (High) | Conditional writes | Low |
| P1 (High) | Chargeback handling | Medium |
| P2 (Medium) | Fraud velocity checks | High |
| P2 (Medium) | Separation of concerns | High |
| P3 (Low) | Advanced fraud detection | High |

---

## Next Steps

1. ~~**Schema Migration**: Migrate `buffett-dev-token-usage` to use `billing_period` as sort key~~ ✅ **COMPLETED February 2026**
2. **Stripe Integration**: Implement webhook handler with signature verification
3. **Audit Table**: Create `buffett-{env}-token-credits` table for payment audit trail
4. **Monitoring**: Set up CloudWatch dashboards for token credit operations

---

*Last Updated: February 2026*
