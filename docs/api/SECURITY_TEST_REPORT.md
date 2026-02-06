# Security Test Report — AWS Dev Environment

> **Date**: 2026-02-05
> **Environment**: AWS Dev (`us-east-1`)
> **Tester**: Automated via Claude Code
> **Scope**: Live penetration tests against CRIT-1 (identity spoofing) and CRIT-2 (Function URL bypass) from [SECURITY_REVIEW.md](SECURITY_REVIEW.md)

---

## Executive Summary

Live security tests were executed against the AWS dev environment to validate the findings from the authentication security review. **All paid/protected endpoints correctly reject unauthenticated and spoofed requests.** One non-critical bug was discovered during initial testing (BUG-1: `analysis_followup` Function URL returned HTTP 200 with a serialization error instead of HTTP 401) and has since been fixed and verified.

| Finding | Live Test Result | Severity |
|---------|-----------------|----------|
| CRIT-1: Identity spoofing via forged JWT | **BLOCKED** by API Gateway authorizer | Mitigated at gateway layer |
| CRIT-1: Identity spoofing via `x-user-id` header | **BLOCKED** — 401 Unauthorized | Mitigated at gateway layer |
| CRIT-1: Identity spoofing via `?user_id=` query param | **BLOCKED** — 401 Unauthorized | Mitigated at gateway layer |
| CRIT-2: analysis_followup Function URL (no JWT) | **BLOCKED** — 401 Unauthorized | Pass (fixed) |
| CRIT-2: analysis_followup Function URL (forged JWT) | **BLOCKED** — 401 Unauthorized | Pass (fixed) |
| CRIT-2: investment_research `/followup` (no JWT) | **BLOCKED** — 401 Unauthorized | Pass |
| CRIT-2: investment_research `/report/*` (no JWT) | **ACCESSIBLE** — returns cached report data | By design (public read-only) |

---

## Endpoints Tested

| Endpoint | Type | URL |
|----------|------|-----|
| HTTP API (conversations, subscriptions) | API Gateway v2 | `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev` |
| REST API (analysis/research) | API Gateway REST | `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/analysis` |
| analysis_followup | Lambda Function URL | `https://buef5xunrsdmsyrhdpb37nyuuu0uhglg.lambda-url.us-east-1.on.aws/` |
| investment_research | Lambda Function URL | `https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/` |

---

## CRIT-1: Identity Spoofing Tests

These tests target `GET /conversations` on the HTTP API to verify that an attacker cannot access another user's data.

### Test 1: Forged JWT with Spoofed user_id

**Vector**: Craft a JWT with valid structure (`header.payload.signature`) containing `user_id: "ATTACKER-SPOOFED-ID"` but an invalid signature. Send via `Authorization: Bearer` header.

```
curl -H "Authorization: Bearer <forged-jwt>" \
  https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/conversations
```

**Response**:
```json
{"message": "Forbidden"}
```
**HTTP Status**: 403

**Result**: **PASS** — The API Gateway Lambda REQUEST authorizer validates the JWT signature before the request reaches the handler. The forged token is rejected at the gateway layer.

---

### Test 2: Spoofed x-user-id Header

**Vector**: Send a request with `x-user-id: ATTACKER-SPOOFED-ID` header and no JWT.

```
curl -H "x-user-id: ATTACKER-SPOOFED-ID" \
  https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/conversations
```

**Response**:
```json
{"message": "Unauthorized"}
```
**HTTP Status**: 401

**Result**: **PASS** — No valid JWT present, authorizer denies the request before the handler can read the spoofed header.

---

### Test 3: Spoofed user_id Query Parameter

**Vector**: Send a request with `?user_id=ATTACKER-SPOOFED-ID` and no JWT.

```
curl "https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/conversations?user_id=ATTACKER-SPOOFED-ID"
```

**Response**:
```json
{"message": "Unauthorized"}
```
**HTTP Status**: 401

**Result**: **PASS** — No valid JWT present, authorizer denies the request before the handler can read the spoofed parameter.

---

### CRIT-1 Assessment

The API Gateway Lambda authorizer is the primary defense and correctly blocks all three spoofing vectors. The handler-level code fix (removing unsigned JWT fallback, query param, and header acceptance) provides **defense in depth** for scenarios where:
- A route is misconfigured with `authorization_type = "NONE"`
- The authorizer is temporarily disabled (e.g., `enable_authorization = false` during testing)
- A new route is added without auth configuration

---

## CRIT-2: Lambda Function URL Direct Access Tests

These tests target the Lambda Function URLs directly, bypassing API Gateway entirely.

### Test 4: analysis_followup — No JWT

**Vector**: POST directly to the Function URL without any Authorization header.

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"question":"What is AAPL revenue?","ticker":"AAPL"}' \
  https://buef5xunrsdmsyrhdpb37nyuuu0uhglg.lambda-url.us-east-1.on.aws/
```

**Response**:
```json
{
  "statusCode": 401,
  "headers": {"Content-Type": "application/json"},
  "body": "{\"success\": false, \"error\": \"Unauthorized - valid JWT token required\", \"timestamp\": \"2026-02-06T01:59:57.558689Z\"}"
}
```
**HTTP Status**: 401

**CloudWatch Log**: `[WARNING] Unauthorized request - invalid or missing JWT token`

**Result**: **PASS** — The handler detects the missing JWT, logs the rejection, and returns HTTP 401 with a structured error response. No Bedrock invocation occurs, no user data is returned.

---

### Test 5: analysis_followup — Forged JWT

**Vector**: POST with a forged JWT (valid structure, invalid signature).

```
curl -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer <forged-jwt>" \
  -d '{"question":"What is AAPL revenue?","ticker":"AAPL"}' \
  https://buef5xunrsdmsyrhdpb37nyuuu0uhglg.lambda-url.us-east-1.on.aws/
```

**Response**: Same 401 response as Test 4.
**HTTP Status**: 401

**CloudWatch Log**: `[WARNING] Unauthorized request - invalid or missing JWT token`

**Result**: **PASS** — JWT signature verification rejects the forged token. Returns clean HTTP 401.

---

### Test 6: investment_research — `/followup` Without JWT (Protected)

**Vector**: POST to the `/followup` endpoint (invokes Claude Haiku, paid service) without JWT.

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"question":"What is AAPL growth rate?","ticker":"AAPL"}' \
  https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/followup
```

**Response**:
```json
{
  "success": false,
  "error": "Unauthorized",
  "detail": "Missing Authorization header",
  "timestamp": "2026-02-06T01:35:56.934907Z"
}
```
**HTTP Status**: 401

**Result**: **PASS** — FastAPI `JWTAuthMiddleware` correctly blocks unauthenticated access to the paid endpoint with a clean 401 response.

---

### Test 7: investment_research — `/report/AAPL/stream` Without JWT (Public)

**Vector**: GET cached report data without JWT.

```
curl https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/report/AAPL/stream
```

**Response**: Full SSE stream of cached AAPL investment report (35KB).
**HTTP Status**: 200

**Result**: **ACCESSIBLE (by design)** — The `/report/*` and `/reports/v2/*` paths are intentionally public per `app.py:177-178`:
```python
PUBLIC_PATH_PREFIXES = ("/report/", "/reports/v2/")
```
These serve pre-cached DynamoDB data only. No AI model is invoked, no per-request cost is incurred. This is a deliberate product decision to make report data accessible without authentication (lead generation for free tier).

---

### Test 8: analysis_followup — Via API Gateway Without JWT

**Vector**: POST to the API Gateway REST API endpoint (normal user flow) without JWT.

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"question":"What is AAPL revenue?","ticker":"AAPL"}' \
  https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/analysis/research/followup
```

**Response**:
```json
{"message": "Missing Authentication Token"}
```
**HTTP Status**: 403

**Result**: **PASS** — REST API TOKEN authorizer blocks the request before it reaches the Lambda.

---

## Bugs Discovered

### BUG-1: analysis_followup Auth Error Returns HTTP 200 Instead of 401 — FIXED

**Location**: `chat-api/backend/src/handlers/analysis_followup.py:795-797`

**Description**: When the `analysis_followup` Lambda was invoked directly via its Function URL (not through API Gateway) and JWT validation failed, the handler returned a Python generator object intended for SSE streaming. The Lambda runtime could not serialize the generator in non-streaming mode, resulting in HTTP 200 + `Runtime.MarshalError` instead of HTTP 401.

**Root cause**: The auth error path checked `is_function_url and not is_api_gateway` and returned an `auth_error_stream()` generator. When the Function URL invocation didn't use streaming mode, the Lambda runtime failed to marshal the generator.

**Fix applied** (2026-02-05): Replaced the branching auth error logic (generator for Function URL, dict for API Gateway) with a single `error_response(401, ...)` call that returns a plain dict for all invocation modes. Deployed to dev and verified via live tests — both no-JWT and forged-JWT requests now return HTTP 401.

**Commit**: `analysis_followup.py` — removed `auth_error_stream()` generator, unified on `error_response()` helper

---

## Security Control Validation Matrix

| Control | Layer | Status | Evidence |
|---------|-------|--------|----------|
| JWT signature verification | API Gateway (authorizer) | **Active** | Tests 1-3: forged JWT → 403 |
| JWT signature verification | analysis_followup (in-handler) | **Active** | Tests 4-5: missing/forged JWT → 401 |
| JWT signature verification | investment_research (middleware) | **Active** | Test 6: missing JWT → 401 |
| Authorization required on HTTP API routes | API Gateway v2 | **Active** | Tests 2-3: no JWT → 401 |
| Authorization required on REST API routes | API Gateway REST | **Active** | Test 8: no JWT → 403 |
| Paid endpoint protection | investment_research `/followup` | **Active** | Test 6: 401 without JWT |
| Public report data (intentional) | investment_research `/report/*` | **By design** | Test 7: accessible without JWT |

---

## Recommendations

### Immediate (Pre-Production)

1. ~~**Fix BUG-1**: Return plain dict error response for auth failures in `analysis_followup.py` instead of generator~~ **DONE** (2026-02-05)
2. **Deploy CRIT-1 code fix**: Push the handler-level unsigned JWT removal for defense-in-depth (local changes ready, tests passing)

### Short-Term

3. **Deploy AWS WAF** on both API Gateways and Function URLs to add rate-based DDoS protection
4. **Evaluate `/report/*` public access policy** — confirm this is the desired product behavior for production. If reports should be gated by tier, move `/report/` from `PUBLIC_PATH_PREFIXES` to protected paths.

### Monitoring

5. **Add CloudWatch alarm** for high invocation counts on Function URLs without corresponding API Gateway requests (indicates direct URL access attempts)
