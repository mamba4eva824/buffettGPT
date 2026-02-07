# Authentication & Security Review

> **Date**: 2026-02-05
> **Scope**: AWS Dev environment — auth handlers, Terraform infrastructure, CI/CD, frontend
> **Purpose**: Identify critical vulnerabilities and hardening recommendations for MVP production launch (free + paid tier)

---

## Table of Contents

- [Audit Snapshot](#audit-snapshot)
- [Architecture Overview](#architecture-overview)
- [Critical Vulnerabilities](#critical-vulnerabilities)
- [High Severity Findings](#high-severity-findings)
- [Medium Severity Findings](#medium-severity-findings)
- [Low Severity Findings](#low-severity-findings)
- [Hardening Recommendations](#hardening-recommendations)
- [Free vs Paid Tier Considerations](#free-vs-paid-tier-considerations)

---

## Audit Snapshot

### Knowns / Evidence

- Authentication uses Google OAuth -> JWT (HS256, 7-day expiry) stored in `localStorage`
- All secrets stored in AWS Secrets Manager, fetched at runtime via ARN
- Two API Gateways: HTTP API (main app) + REST API (analysis/research)
- Lambda Function URLs with `authorization_type = "NONE"` are publicly accessible
- Single shared IAM role across most Lambda functions
- Three separate rate-limiting implementations exist; none fully wired into handlers
- Stripe webhook signature verification is correctly implemented
- No WAF, no VPC, no CloudTrail integration

### Unknowns / Gaps

- Authorizer result caching TTL on HTTP API (could allow revoked tokens to persist)
- CloudFront security headers (CSP, X-Frame-Options) not configured
- DynamoDB PITR/deletion protection status in prod

### Top 3 Risks

1. **Unsigned JWT fallback** in conversations/search handlers allows identity spoofing
2. **Public Lambda Function URLs** bypass API Gateway auth entirely
3. **Over-permissioned shared IAM role** gives all Lambdas access to all secrets/tables

---

## Architecture Overview

```
                          ┌──────────────┐
                          │   Google     │
                          │   OAuth      │
                          └──────┬───────┘
                                 │
                                 ▼
┌──────────┐  Bearer JWT  ┌─────────────────┐  Lambda Authorizer  ┌──────────────────┐
│  React   │─────────────▶│  API Gateway    │───────────────────▶│  auth_verify.py  │
│ Frontend │              │  (HTTP API)     │                     └──────────────────┘
└──────────┘              └────────┬────────┘
                                   │
                    ┌──────────────┼──────────────────┐
                    ▼              ▼                   ▼
            ┌────────────┐ ┌─────────────┐  ┌──────────────────┐
            │ conversa-  │ │ subscription│  │ stripe_webhook   │
            │ tions      │ │ _handler    │  │ _handler         │
            └────────────┘ └─────────────┘  └──────────────────┘
                                                  │
                                          Stripe Signature
                                          Verification

┌──────────┐              ┌─────────────────┐  TOKEN Authorizer  ┌──────────────────┐
│  React   │─────────────▶│  API Gateway    │───────────────────▶│  auth_verify.py  │
│ Frontend │              │  (REST API)     │                     └──────────────────┘
└──────────┘              └────────┬────────┘
                                   │
                                   ▼
                          ┌──────────────────┐
                          │ analysis_followup│◀── Also has PUBLIC Function URL
                          └──────────────────┘    (authorization_type = "NONE")
```

**Key auth mechanisms:**

| Mechanism | Used By | Notes |
|-----------|---------|-------|
| Google OAuth + JWT | All authenticated routes | HS256, 7-day expiry, 32-char min secret |
| Lambda REQUEST authorizer | HTTP API routes | Validates JWT, extracts user context |
| Lambda TOKEN authorizer | REST API routes | 300s result cache TTL |
| Stripe signature verification | `POST /stripe/webhook` | `stripe.Webhook.construct_event()` |
| Device fingerprinting | Anonymous users | SHA-256 of IP + User-Agent + CF headers |

---

## Critical Vulnerabilities

### CRIT-1: Unsigned JWT Payload Extraction

**Severity**: CRITICAL -> **VERIFIED FIXED** (re-tested 2026-02-06)
**Location**: `chat-api/backend/src/handlers/conversations_handler.py:183-204`, `chat-api/backend/src/handlers/search_handler.py:98-113`

**Description**: Both handlers contain a fallback path that base64-decodes the JWT payload **without verifying the signature**. When the API Gateway authorizer context is missing but an `Authorization` header is present, the code splits the JWT on `.`, base64-decodes the middle segment, and trusts whatever `user_id` / `sub` is in the claims.

**Attack scenario**:
```
1. Attacker crafts a JWT: header.{"user_id": "victim-user-123"}.fake-signature
2. Sends request with Authorization: Bearer <crafted-token>
3. Handler falls back to unsigned decode
4. Attacker reads victim's conversation history
```

**Additionally**: `conversations_handler.py:210-214` accepts `user_id` from query parameters and `x-user-id` header without verification — trivially spoofable.

**Impact**: Complete identity spoofing. Any user's data can be accessed by forging a JWT payload.

**Remediation**:
- Remove the unsigned base64 decode fallback entirely
- Only trust `user_id` from the verified authorizer context (`requestContext.authorizer`)
- Remove acceptance of `user_id` query parameter and `x-user-id` header

---

### CRIT-2: Public Lambda Function URLs Bypass API Gateway Auth

**Severity**: CRITICAL -> **VERIFIED FIXED** (re-tested 2026-02-06, originally mitigated 2026-02-05)
**Location**: `chat-api/terraform/modules/lambda/function_urls.tf:9`, `chat-api/terraform/modules/lambda/investment_research_docker.tf:143`

**Description**: Two Lambda Function URLs are created with `authorization_type = "NONE"`:
- `analysis_followup` — handles follow-up Q&A via Bedrock agents
- `investment_research_docker` — runs investment research via Bedrock

These URLs are publicly accessible on the internet. While API Gateway normally sits in front and validates JWT, the Function URLs can be invoked directly, bypassing API Gateway auth.

**Mitigation Status (2026-02-05)**:
Both Lambda handlers independently validate JWT tokens before processing any request:
- `analysis_followup.py:794` — calls `verify_jwt_token(event)`, returns 401 if invalid
- `lambda/investment_research/app.py:181,353` — `JWTAuthMiddleware` enforces JWT on all protected endpoints with 32-char secret validation, HS256 algorithm pinning

Direct Function URL access without a valid JWT returns 401 from both handlers. A serialization bug in `analysis_followup` that caused HTTP 200 instead of 401 for auth errors was fixed on 2026-02-05 (see BUG-1 in [SECURITY_TEST_REPORT.md](SECURITY_TEST_REPORT.md)). The residual risk is Lambda invocation cost (each unauthenticated request still triggers a cold/warm start before being rejected).

**Residual risk**: DDoS cost exposure — unauthenticated requests are rejected but still incur Lambda billing. AWS WAF rate limiting on Function URLs would further mitigate this.

**Remaining recommendation**:
- Add AWS WAF rate limiting on Function URLs to prevent cost-based DDoS
- Terraform comments updated to document the in-handler JWT validation

---

## High Severity Findings

### HIGH-1: Duplicate JWT Verification with Weaker Validation

**Severity**: HIGH
**Location**: `chat-api/backend/src/handlers/analysis_followup.py:46-59`

**Description**: `analysis_followup.py` contains its own `get_jwt_secret()` and `verify_jwt_token()` implementations that **do not enforce the 32-character minimum** on the JWT secret. The fallback path accepts any non-empty `JWT_SECRET` environment variable. Bug fixes applied to `auth_verify.py` will not propagate here.

**Remediation**: Consolidate all JWT verification into a single shared module (`src/utils/jwt_utils.py`). All handlers should import from this single source of truth.

---

### HIGH-2: Over-Permissioned Shared IAM Role

**Severity**: HIGH
**Location**: `chat-api/terraform/modules/core/main.tf:57-147`

**Description**: A single IAM role (`buffett-dev-lambda-role`) is shared across all Lambda functions except `followup_action`. Every Lambda can:

| Permission | Scope | Issue |
|-----------|-------|-------|
| DynamoDB read/write | All project tables (`*-dev-*`) | `search_handler` can write to `users` table |
| Bedrock invoke | `Resource = "*"` | `conversations_handler` can invoke any model |
| Secrets Manager | All project secrets | `search_handler` can read Stripe API keys |
| KMS | Encrypt/Decrypt/GenerateDataKey | Full crypto operations for all functions |

**Positive exception**: `followup_action` has its own dedicated role with narrower permissions.

**Remediation**: Create per-function IAM roles. At minimum:
- Stripe secrets: only `subscription_handler` + `stripe_webhook_handler`
- Bedrock invoke: only `analysis_followup` + `investment_research`
- User table write: only `auth_callback` + `stripe_webhook_handler`

---

### HIGH-3: No WAF Protection

**Severity**: HIGH

**Description**: No AWS WAF is deployed in front of either API Gateway. Endpoints are directly internet-facing without protection against:
- SQL injection / XSS patterns
- Bot traffic and credential stuffing
- Geographic IP blocking
- Per-IP rate limiting
- Known malicious IP lists (AWS managed threat intel)

**Remediation**: Attach AWS WAF v2 to both API Gateways with:
- `AWSManagedRulesCommonRuleSet`
- `AWSManagedRulesBotControlRuleSet`
- Rate-based rule (e.g., 1000 requests per 5 minutes per IP)
- Geographic restrictions if user base is known

---

## Medium Severity Findings

### MED-1: Wildcard CORS in Lambda Handlers

**Severity**: MEDIUM
**Location**: `chat-api/backend/src/handlers/subscription_handler.py:356`, `chat-api/backend/src/handlers/search_handler.py:199-204`

**Description**: Multiple handlers set `Access-Control-Allow-Origin: *` while the API Gateway is configured with `allow_credentials = true` and environment-specific origin allowlists. Handler-level headers can override API Gateway CORS in certain configurations.

**Remediation**: Remove all handler-level CORS headers. Rely solely on API Gateway CORS configuration, which already has proper environment-based origin allowlists.

---

### MED-2: Information Leakage in Error Responses

**Severity**: MEDIUM
**Location**: `conversations_handler.py:117`, `search_handler.py:352`, `analysis_followup.py:1075`

**Description**: Raw `str(e)` is returned in 500 error response bodies, potentially exposing:
- DynamoDB table names and structure
- Internal stack traces
- AWS SDK error details
- Architecture information useful for further attacks

**Positive exception**: `auth_callback.py` and `subscription_handler.py` correctly return generic error messages.

**Remediation**: Replace `str(e)` with generic messages (e.g., `"Internal server error"`). Log full exception details server-side via CloudWatch.

---

### MED-3: Frontend JWT in localStorage

**Severity**: MEDIUM
**Location**: `frontend/src/auth.jsx:90-92`

**Description**: JWT token, user object, and expiration time are stored in `localStorage`. Any XSS vulnerability would allow an attacker to steal the token and impersonate the user for up to 7 days.

**Mitigating factors**: Bearer token auth provides implicit CSRF protection. No known XSS vectors in the current frontend.

**Remediation**:
- **Short-term**: Add Content-Security-Policy headers via CloudFront response headers policy to limit XSS attack surface
- **Long-term**: Migrate to `httpOnly` cookies with `SameSite=Strict` and `Secure` flags

---

### MED-4: Rate Limiting Not Wired Into Handlers

**Severity**: MEDIUM

**Description**: Three separate rate-limiting systems exist in the codebase:

| System | File | Status |
|--------|------|--------|
| Monthly request-count limiting | `rate_limiter.py` | Not imported by any handler |
| Multi-granularity tiered limiting | `tiered_rate_limiter.py` | Not imported by any handler |
| Token-based usage tracking | `token_usage_tracker.py` | Used by `analysis_followup` only |

The DynamoDB rate-limits table was removed in a cleanup. All three systems fail-open when DynamoDB is unavailable. The only active protection is API Gateway stage-level throttling (100 req/s dev, 1000 req/s prod).

**Remediation**:
- Choose one rate-limiting approach and wire it into all public handlers
- Decide fail-open vs fail-closed policy for production
- For paid tier: enforce token usage limits via `token_usage_tracker` on all AI endpoints

---

### MED-5: REST API CORS Wildcard on Error Responses

**Severity**: MEDIUM
**Location**: `chat-api/terraform/modules/api-gateway/analysis_streaming.tf:138,150`

**Description**: REST API gateway responses for 4XX and 5XX errors use `Access-Control-Allow-Origin = "'*'"` regardless of environment. This sends a wildcard CORS origin on all error responses, allowing any origin to observe error details.

**Remediation**: Replace wildcard with `var.cloudfront_url` in gateway response headers.

---

## Low Severity Findings

### LOW-1: CI/CD Uses Long-Lived AWS Access Keys

**Location**: `.github/workflows/deploy-dev.yml`, `deploy-staging.yml`, `deploy-prod.yml`

**Description**: All workflows use static `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` from GitHub secrets. These keys do not rotate automatically and could be compromised via GitHub breach.

**Remediation**: Migrate to GitHub OIDC federation using `aws-actions/configure-aws-credentials` with `role-to-assume`.

---

### LOW-2: Shared JWT Secret Across Dev/Staging

**Description**: Dev and staging workflows both reference `${{ secrets.JWT_SECRET }}`. A token minted in dev is valid in staging.

**Remediation**: Use environment-specific JWT secrets (`DEV_JWT_SECRET`, `STAGING_JWT_SECRET`).

---

### LOW-3: Unrestricted Bedrock Lambda Invoke Permission

**Location**: `chat-api/terraform/modules/lambda/followup_action_docker.tf:254-264`

**Description**: The Lambda permission for Bedrock invocation uses `principal = "bedrock.amazonaws.com"` without a `source_arn` constraint. Any Bedrock agent in the account (including other projects) can invoke this function.

**Remediation**: Add `source_arn` to restrict invocation to the specific follow-up agent ARN.

---

### LOW-4: Hardcoded Dev API URL in Frontend

**Location**: `frontend/src/auth.jsx:11`

**Description**: `AUTH_CONFIG` contains a hardcoded fallback API URL (`https://4onfe7pbpc.execute-api.us-east-1.amazonaws.com/dev`). While only used as a default, it exposes the dev API endpoint in source code.

**Remediation**: Remove the hardcoded URL. Require `VITE_REST_API_URL` to be set explicitly.

---

### LOW-5: No Backend Tests in CI/CD Pipeline

**Description**: No Python test step exists in any GitHub Actions workflow. The dev workflow has a smoke test step but it runs after deployment, not before. Frontend tests are disabled (`if: false`).

**Remediation**: Add `make test` step before deployment in all workflows. Gate deployment on test passage.

---

## Hardening Recommendations

### Tier 1: Must-Fix Before Production Launch

| # | Action | Effort | Addresses |
|---|--------|--------|-----------|
| 1 | ~~Remove unsigned JWT fallback in conversations + search handlers~~ | S | CRIT-1 — **DONE** (verified 2026-02-06) |
| 2 | ~~Remove `x-user-id` header / `user_id` query param acceptance~~ | S | CRIT-1 — **DONE** (verified 2026-02-06) |
| 3 | Consolidate JWT verification into shared `utils/jwt_utils.py` | M | HIGH-1 |
| 4 | ~~Secure Lambda Function URLs (add `AWS_IAM` or in-handler JWT validation)~~ | M | CRIT-2 — **DONE** (verified 2026-02-06) |
| 5 | Sanitize error responses (replace `str(e)` with generic messages) | S | MED-2 |
| 6 | Deploy AWS WAF with managed rule groups on both API Gateways | M | HIGH-3 |
| 7 | Wire rate limiting into all public-facing handlers | M | MED-4 |

### Tier 2: Should-Fix for Production Hardening

| # | Action | Effort | Addresses |
|---|--------|--------|-----------|
| 8 | Per-function IAM roles (separate Stripe, Bedrock, DynamoDB access) | L | HIGH-2 |
| 9 | Standardize CORS (remove handler-level headers, rely on API Gateway) | S | MED-1, MED-5 |
| 10 | Add CloudFront security headers (CSP, X-Frame-Options, HSTS) | S | MED-3 |
| 11 | Separate JWT secrets per environment | S | LOW-2 |
| 12 | Add auth failure alarms (CloudWatch alarm on 401/403 spike) | S | Monitoring |
| 13 | Enable DynamoDB PITR + deletion protection in prod | S | Data recovery |
| 14 | Add `make test` to CI/CD pipelines, gate deployments on pass | S | LOW-5 |

### Tier 3: Best Practice (Post-Launch)

| # | Action | Effort | Addresses |
|---|--------|--------|-----------|
| 15 | Migrate CI/CD to OIDC (eliminate static AWS keys) | M | LOW-1 |
| 16 | Add token refresh mechanism (shorter token lifetime) | M | MED-3 |
| 17 | Move JWT to httpOnly cookies with SameSite=Strict | L | MED-3 |
| 18 | Enable CloudTrail for API audit logging | M | Forensics |
| 19 | Add VPC for Lambda functions | L | Network isolation |
| 20 | Restrict Bedrock Lambda invoke permission with source_arn | S | LOW-3 |

**Effort key**: S = < 1 day, M = 1-3 days, L = 3+ days

---

## Free vs Paid Tier Considerations

### Access Control

- **Subscription tier must come from JWT claims** (already present as `subscription_tier` in the token payload), never from client-supplied headers or query parameters
- All handlers that gate features by tier should extract tier from the verified authorizer context only
- Stripe webhook handler correctly updates subscription status server-side — verify that downgrade/cancellation flows revoke Plus access immediately (not deferred to next token refresh)

### Usage Enforcement

| Tier | Recommended Limits | Enforcement Point |
|------|-------------------|-------------------|
| Free | 5 messages/month, no follow-up agent access | `rate_limiter.py` + handler-level checks |
| Plus | 1M tokens/month, full follow-up agent access | `token_usage_tracker.py` on all AI endpoints |
| Both | API Gateway stage throttle (1000 req/s) | Terraform `api-gateway` module |
| Both | WAF rate-based rule (1000 req/5min per IP) | AWS WAF (to be deployed) |

### Billing Security

- Stripe webhook idempotency is correctly implemented (event ID tracking with 7-day TTL)
- Webhook handler verifies user existence before updating records (prevents orphan creation)
- Open redirect protection on checkout URLs is properly implemented with test coverage
- **Gap**: No mechanism to detect or alert on subscription fraud patterns (e.g., rapid subscribe/cancel cycling)

---

## What's Working Well

Not all findings are negative. These security patterns are correctly implemented:

1. **JWT secret management** — Fetched from Secrets Manager via ARN, 32-char minimum enforced (in `auth_verify.py`), `@lru_cache` for performance
2. **Algorithm pinning** — HS256 hardcoded in JWT decode, preventing algorithm confusion attacks
3. **Stripe webhook verification** — Proper signature validation + idempotency + user existence checks
4. **KMS encryption** — Customer-managed key with rotation enabled, used for all DynamoDB tables and Terraform state
5. **Open redirect prevention** — `_validate_redirect_url()` in subscription handler with thorough test coverage
6. **Production deploy approval** — GitHub environment protection requires manual approval for prod
7. **Sensitive variable handling** — Terraform `sensitive = true` on all secret variables, `lifecycle { ignore_changes }` on secret values
8. **Dedicated IAM role for followup_action** — Demonstrates the per-function role pattern that should be extended

---

## Appendix: Files Audited

### Backend Handlers
- `chat-api/backend/src/handlers/auth_callback.py`
- `chat-api/backend/src/handlers/auth_verify.py`
- `chat-api/backend/src/handlers/conversations_handler.py`
- `chat-api/backend/src/handlers/subscription_handler.py`
- `chat-api/backend/src/handlers/stripe_webhook_handler.py`
- `chat-api/backend/src/handlers/analysis_followup.py`
- `chat-api/backend/src/handlers/search_handler.py`

### Backend Utilities
- `chat-api/backend/src/utils/rate_limiter.py`
- `chat-api/backend/src/utils/tiered_rate_limiter.py`
- `chat-api/backend/src/utils/token_usage_tracker.py`
- `chat-api/backend/src/utils/device_fingerprint.py`
- `chat-api/backend/src/utils/stripe_service.py`

### Terraform Modules
- `chat-api/terraform/modules/core/main.tf` (IAM, KMS)
- `chat-api/terraform/modules/auth/` (OAuth secrets, policies)
- `chat-api/terraform/modules/api-gateway/main.tf` (CORS, authorizers, routes)
- `chat-api/terraform/modules/api-gateway/analysis_streaming.tf` (REST API)
- `chat-api/terraform/modules/lambda/function_urls.tf` (Function URLs)
- `chat-api/terraform/modules/lambda/followup_action_docker.tf` (Dedicated IAM)
- `chat-api/terraform/modules/rate-limiting/main.tf`
- `chat-api/terraform/modules/monitoring/main.tf`
- `chat-api/terraform/modules/stripe/secrets.tf`
- `chat-api/terraform/environments/dev/main.tf`

### CI/CD
- `.github/workflows/deploy-dev.yml`
- `.github/workflows/deploy-staging.yml`
- `.github/workflows/deploy-prod.yml`

### Frontend
- `frontend/src/auth.jsx`

### Tests
- `chat-api/backend/tests/unit/test_subscription_handler.py`
- `chat-api/backend/tests/conftest.py`

---

## Changelog

| Date | Change | Finding |
|------|--------|---------|
| 2026-02-05 | Initial security review | All findings |
| 2026-02-05 | Fixed BUG-1: `analysis_followup` auth error now returns HTTP 401 instead of HTTP 200 + `Runtime.MarshalError`. Replaced `auth_error_stream()` generator with `error_response()` dict. Deployed to dev, verified via live tests. | CRIT-2 |
| 2026-02-06 | Re-test of CRIT-1 and CRIT-2 remediation — all 8 acceptance criteria passed. See [Re-test Results](#re-test-results-2026-02-06) below. CRIT-1: **VERIFIED FIXED**. CRIT-2: **VERIFIED FIXED**. | CRIT-1, CRIT-2 |

---

## Re-test Results (2026-02-06)

> **Tester**: Claude Code (automated security re-test)
> **Date**: 2026-02-06T23:14Z
> **Scope**: CRIT-1 and CRIT-2 remediation verification — static code audit + live endpoint tests against dev environment

### Summary

| Finding | Original Status | Re-test Status | Evidence |
|---------|----------------|----------------|----------|
| CRIT-1: Unsigned JWT Payload Extraction | CRITICAL | **VERIFIED FIXED** | Code audit: no base64 JWT decode paths in conversations/search handlers. Live test: forged JWT returns 403. |
| CRIT-2: Public Lambda Function URLs | MITIGATED | **VERIFIED FIXED** | Code audit: `error_response()` returns dict. Live tests: all Function URLs return 401 for invalid/missing JWT. |

### Acceptance Criteria Results

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| AC-1 | No `base64`/`b64decode` JWT extraction in `conversations_handler.py` or `search_handler.py` | **PASS** | Grep for `base64\|b64decode` in `src/handlers/` found only `analysis_followup.py:401` (request body decoding for `isBase64Encoded`, not JWT extraction). Both handlers extract `user_id` solely from `requestContext.authorizer`. |
| AC-2 | No `x-user-id` header or `user_id` query param extraction in `conversations_handler.py` | **PASS** | Grep for `x-user-id\|user_id.*query` returned only security comments at `conversations_handler.py:177` and `search_handler.py:94`. `get_user_id()` returns `None` (conversations) or `'anonymous'` (search) when authorizer context is missing. |
| AC-3 | `analysis_followup.py` `verify_jwt_token()` returns proper `error_response()` dict (not generator) | **PASS** | `error_response()` at line 1058-1071 returns `Dict[str, Any]` with `statusCode`, `headers`, `body`. Auth gate at line 794-797: `return error_response(401, ...)`. No generator/yield in the auth path. |
| AC-4 | POST to analysis_followup Function URL with invalid JWT returns HTTP 401 JSON | **PASS** | `curl POST https://buef5xunrsdmsyrhdpb37nyuuu0uhglg.lambda-url.us-east-1.on.aws/` with `Authorization: Bearer invalid.jwt.token` → **HTTP 401**, body: `{"success": false, "error": "Unauthorized - valid JWT token required", "timestamp": "2026-02-06T23:14:52.571727Z"}` |
| AC-5 | POST to analysis_followup Function URL with NO auth header returns HTTP 401 JSON | **PASS** | `curl POST` (no Authorization header) → **HTTP 401**, body: `{"success": false, "error": "Unauthorized - valid JWT token required", "timestamp": "2026-02-06T23:14:55.800591Z"}` |
| AC-6 | POST to Docker Lambda Function URL with invalid JWT returns HTTP 401 | **PASS** | `curl POST https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/followup` with `Authorization: Bearer invalid.jwt.token` → **HTTP 401**, body: `{"success": false, "error": "Unauthorized", "detail": "Invalid token", "timestamp": "2026-02-06T23:15:01.412982Z"}` |
| AC-7 | POST to Docker Lambda Function URL with NO auth header returns HTTP 401 | **PASS** | `curl POST` (no Authorization header) → **HTTP 401**, body: `{"success": false, "error": "Unauthorized", "detail": "Missing Authorization header", "timestamp": "2026-02-06T23:15:09.652741Z"}` |
| AC-8 | GET /conversations via API Gateway with crafted unsigned JWT returns 401/403 (not victim data) | **PASS** | Forged JWT: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidmljdGltLXVzZXItMTIzNDUi...}.fake-signature-not-valid` → **HTTP 403** `{"message":"Forbidden"}`. API Gateway Lambda authorizer rejected the token before it reached the handler. No victim data returned. |

### REST API Gateway — Investment Research Endpoints

The investment research Docker Lambda serves the follow-up agent endpoints that users interact with to ask questions about investment reports. These endpoints are accessed through the REST API Gateway (`t5wvlwfo5b`), which uses a TOKEN authorizer for JWT validation. The Docker Lambda also has a direct Function URL (tested in AC-6/AC-7 above). Both paths must reject unauthenticated requests.

**Endpoints tested** (via REST API Gateway `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev`):

| Endpoint | Test | HTTP Status | Response |
|----------|------|-------------|----------|
| `POST /followup` | Invalid JWT (`Bearer invalid.jwt.token`) | **403** | `{"message":"Invalid key=value pair (missing equal-sign) in Authorization header..."}` |
| `POST /followup` | No Authorization header | **403** | `{"message":"Missing Authentication Token"}` |
| `GET /report/AAPL/stream` | Invalid JWT | **403** | `{"message":"Invalid key=value pair (missing equal-sign) in Authorization header..."}` |
| `GET /report/AAPL/stream` | No Authorization header | **403** | `{"message":"Missing Authentication Token"}` |

**Result**: All four requests rejected at the API Gateway TOKEN authorizer level — the request never reaches the Lambda handler. This confirms the primary auth gate for the user-facing follow-up agent flow is working correctly.

**Defense in depth**: Even if the REST API Gateway authorizer were bypassed (e.g., via direct Function URL), the in-handler `JWTAuthMiddleware` provides a second layer of protection (verified in AC-6/AC-7).

### Docker Lambda Reachability Proof

The Docker Lambda Function URL health endpoint confirms the URL is live and accepting requests:
- `GET https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/health` → **HTTP 200**, body: `{"status": "healthy", "timestamp": "2026-02-06T23:15:12.483405Z", "environment": "dev", "service": "investment-research"}`

### Terraform Security Documentation

Both Function URL Terraform resources have security comments documenting the in-handler JWT validation:
- `function_urls.tf:7-11` — Documents that `analysis_followup.py:794` validates JWT independently
- `investment_research_docker.tf:140-145` — Documents that `JWTAuthMiddleware` (`app.py:181,353`) validates JWT with 32-char secret validation

### Notes

- **AC-8 returns 403 (not 401)**: This is the expected behavior for AWS API Gateway HTTP API Lambda authorizers. When the authorizer Lambda returns a deny policy or throws an error, API Gateway returns 403 Forbidden. The critical security property — that no victim data is returned for a forged JWT — is confirmed.
- **REST API Gateway returns 403 for auth failures**: The TOKEN authorizer on the REST API returns 403 with descriptive messages (`"Missing Authentication Token"` or `"Invalid key=value pair..."`) rather than 401. This is standard AWS API Gateway REST API behavior.
- **HTTP API Gateway URL updated**: The HTTP API endpoint is now `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev` (previously documented as `4onfe7pbpc` which is no longer active).
