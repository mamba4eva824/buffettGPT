# Waitlist Landing Page - Testing Report

**Date:** February 12, 2026
**Author:** Engineering
**Scope:** Backend unit tests, E2E tests against live API, and infrastructure deployment

---

## Executive Summary

The waitlist/referral system has been fully validated through two layers of testing: a 41-test unit suite (98% code coverage) and a 24-test E2E suite that hits the live dev API and real DynamoDB. The testing effort uncovered two issues that would have caused production failures:

1. **Bug (unit tests):** A missing expression attribute in the referral credit logic would have silently prevented all early access auto-promotions.
2. **IAM gap (E2E tests):** The DynamoDB table rename from `buffett-dev-waitlist` to `waitlist-dev-buffett` broke the Lambda's IAM policy, since the existing wildcard pattern (`buffett-dev-*`) did not match the new naming convention. This would have caused 500 errors on every signup and status request in production.

Both issues were caught and fixed before reaching users. The E2E suite now serves as a regression safety net that validates the full request path: API Gateway -> Lambda -> DynamoDB and back.

---

## Deployment Verification

| Check | Status | Details |
|-------|--------|---------|
| CI/CD Pipeline | Pass | Latest deploy `14f1629` succeeded on `dev` branch |
| Lambda Function | Deployed | `buffett-dev-waitlist-handler`, last updated 2026-02-12 04:35 UTC |
| API Gateway | Live | `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev` |
| POST /waitlist/signup | Pass | Returns 201 with referral code, position, tier data |
| GET /waitlist/status | Pass | Returns 200 with dashboard data (email+code auth) |
| Duplicate detection | Pass | Returns 409 with existing referral code on re-signup |
| DynamoDB Table | Live | `waitlist-dev-buffett` (renamed from `buffett-dev-waitlist`, deployed 2026-02-12) |
| IAM Policy | Updated | Added `waitlist-dev-buffett` ARNs to Lambda role policy |

---

## Unit Test Results

**File:** `chat-api/backend/tests/test_waitlist_handler.py`
**Framework:** pytest + moto (mocked DynamoDB, zero real AWS calls)
**Execution time:** 0.67 seconds

### Coverage

| Metric | Value |
|--------|-------|
| Total tests | 41 |
| Passed | 41 |
| Failed | 0 |
| Line coverage | 98% (178/182 statements) |

### Test Breakdown by Class

| Class | Tests | Area Covered |
|-------|-------|-------------|
| TestLambdaRouting | 4 | OPTIONS CORS, POST/GET routing, 404 unknown routes |
| TestSignupHappyPath | 5 | Valid signup, referral credit, auto-promotion, queue position, referral link |
| TestSignupValidation | 4 | Invalid JSON, empty/bad email format, disposable email blocking |
| TestRateLimiting | 4 | 429 at limit, under-limit succeeds, unknown IP bypass, TTL on rate records |
| TestDuplicateHandling | 1 | 409 response with existing referral code recovery |
| TestReferralSystem | 5 | Code format (BUFF-XXXX), invalid/self referral handling, collision retry, 6-char fallback |
| TestStatusEndpoint | 5 | Dashboard data, 400/404/403 error responses |
| TestTierCalculation | 3 | Zero referrals, at threshold, between tiers |
| TestEdgeCases | 10 | Email normalization, Decimal encoding, IP extraction, 6 DynamoDB error paths |

### Uncovered Lines (4 lines, acceptable)

| Line | Reason |
|------|--------|
| 70 | `DecimalEncoder` superclass fallback for non-Decimal types |
| 176 | Double-failure fallback: duplicate check + subsequent GetItem both fail |
| 374-375 | Rate limit count check (covered via full handler flow, not isolated function) |

---

## Bug Found and Fixed

**Severity:** High (would have broken early access auto-promotion in production)

**Location:** `waitlist_handler.py:293`

**Issue:** The `_credit_referrer` function's conditional update to promote users to `early_access` status used `ConditionExpression='#s = :waitlisted'` but `:waitlisted` was missing from `ExpressionAttributeValues`. This would cause a `KeyError` in DynamoDB on every referral credit attempt, silently swallowing the error and never promoting referrers.

**Fix:** Added `':waitlisted': 'waitlisted'` to the `ExpressionAttributeValues` dictionary.

**Before:**
```python
ExpressionAttributeValues={':status': 'early_access'},
ConditionExpression='#s = :waitlisted',
```

**After:**
```python
ExpressionAttributeValues={':status': 'early_access', ':waitlisted': 'waitlisted'},
ConditionExpression='#s = :waitlisted',
```

---

## Infrastructure Changes (Deployed)

| Change | File | Status |
|--------|------|--------|
| DynamoDB table rename: `buffett-dev-waitlist` -> `waitlist-dev-buffett` | `waitlist.tf` | **Deployed** (Terraform apply, 2026-02-12) |
| Handler fallback default updated to match new table name | `waitlist_handler.py` | **Deployed** |
| IAM policy: added `waitlist-dev-buffett` ARNs | `core/main.tf` | **Deployed** (Terraform apply, 2026-02-12) |

---

## E2E Test Results

**File:** `chat-api/backend/tests/e2e/test_waitlist_e2e.py`
**Framework:** pytest + requests (live HTTP calls) + boto3 (DynamoDB cleanup)
**Target:** `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev`
**Execution time:** 8.37 seconds

### Why E2E Tests Matter

Unit tests validate logic in isolation with mocked AWS services. E2E tests validate the full production path: a real HTTP request through API Gateway, invoking the real Lambda, reading/writing to the real DynamoDB table, and returning through the real response pipeline. This catches integration issues that unit tests cannot:

- **IAM permissions** -- The table rename broke the Lambda's DynamoDB access. Unit tests (which mock DynamoDB) would never catch this; only a real AWS call reveals `AccessDeniedException`.
- **API Gateway routing** -- Verifies that routes are correctly wired, payload format version 2.0 is parsed correctly, and query parameters reach the handler.
- **Data consistency** -- A referral chain test (User A signs up, User B signs up with A's code) confirms that the atomic DynamoDB update, the referral credit, and the auto-promotion all work together end-to-end in a single flow.
- **Response contract** -- Validates that the JSON shapes returned to the frontend match expectations (field names, types, tier structure).

### Coverage

| Metric | Value |
|--------|-------|
| Total tests | 24 |
| Passed | 24 |
| Failed | 0 |

### Test Breakdown by Class

| Class | Tests | What It Validates |
|-------|-------|-------------------|
| TestSignupHappyPath | 5 | 201 response, referral code format, position, tiers, referral link |
| TestDuplicateSignup | 1 | 409 with existing code on re-signup |
| TestReferralChain | 4 | Referral credit increments, early_access auto-promotion, tier assignment, referred user isolation |
| TestStatusEndpoint | 3 | Position, tier progress, referral link in dashboard response |
| TestValidationErrors | 4 | Missing email (400), bad format (400), disposable domain (400), invalid JSON (400) |
| TestStatusNotFound | 1 | Unknown email returns 404 |
| TestStatusForbidden | 2 | Wrong code returns 403, missing params returns 400 |
| TestCORSPreflight | 3 | OPTIONS /signup (200), OPTIONS /status (200), CORS body content |
| TestInvalidReferralCode | 1 | Invalid referral code silently ignored, signup succeeds |

### Test Design Decisions

- **UUID-based emails** (`e2e-a-{uuid}@testbuffett.com`) ensure no collisions between test runs or with real data.
- **Module-scoped fixtures** sign up users once and share across test classes, keeping total signups to 3 (under the 5/hr rate limit).
- **Automatic cleanup** via a `cleanup_entries` fixture that deletes all test records from DynamoDB after the module completes, even on test failure.
- **No JWT required** -- the waitlist API is public, so tests need no secret management.

---

## IAM Policy Bug Found During E2E Testing

**Severity:** High (would have caused 500 errors on every waitlist API call in production)

**Root cause:** The Lambda IAM policy in `core/main.tf` granted DynamoDB access using the wildcard pattern `buffett-dev-*`. When the table was renamed from `buffett-dev-waitlist` to `waitlist-dev-buffett`, the new name no longer matched the wildcard. Every DynamoDB operation (`GetItem`, `PutItem`, `Query`, `Scan`) returned `AccessDeniedException`.

**Why unit tests missed it:** Unit tests use moto to mock DynamoDB in-process. No real IAM evaluation occurs. Only a real AWS call reveals permission issues.

**Fix:** Added explicit ARN entries for `waitlist-${var.environment}-${var.project_name}` (table + index) to the DynamoDB policy in `chat-api/terraform/modules/core/main.tf`.

**Lesson:** When adopting a new DynamoDB naming convention (`resource-env-project` instead of `project-env-resource`), the IAM policy wildcards must be updated to match. E2E tests are essential for catching infrastructure-level issues like this.

---

## What's Next

| Item | Priority |
|------|----------|
| Frontend feature flag activation (`VITE_ENABLE_WAITLIST=true`) | Medium |
| Staging/prod environment wiring | Medium |
