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

**Severity**: CRITICAL
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

**Severity**: CRITICAL -> **MITIGATED** (downgraded to LOW after investigation)
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
| 1 | Remove unsigned JWT fallback in conversations + search handlers | S | CRIT-1 |
| 2 | Remove `x-user-id` header / `user_id` query param acceptance | S | CRIT-1 |
| 3 | Consolidate JWT verification into shared `utils/jwt_utils.py` | M | HIGH-1 |
| 4 | Secure Lambda Function URLs (add `AWS_IAM` or in-handler JWT validation) | M | CRIT-2 |
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
