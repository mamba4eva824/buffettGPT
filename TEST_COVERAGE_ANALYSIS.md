# Test Coverage Analysis — BuffettGPT

**Date**: 2026-02-14
**Branch**: `claude/analyze-test-coverage-UgfNk`

## Current State (Actual Test Run Results)

### Backend Unit Tests (251 collected)
- **43 pass**, 146 fail, 62 error
- `test_token_usage_tracker.py`: **43/43 pass**
- `test_analysis_followup.py`: 0/38 — all ERROR (cryptography/cffi dep broken)
- `test_tool_executor.py`: 6 routing FAIL, 24 DynamoDB ERROR (cffi)
- `test_stripe_webhook_handler.py`: 0/61 — all FAIL (moto cffi dep broken)
- `test_stripe_service.py`: 0/19 — all FAIL (moto cffi dep broken)
- `test_subscription_handler.py`: 0/38 — all FAIL (moto cffi dep broken)

### Backend Integration Tests (70 collected)
- **16 pass**, 31 fail, 22 skipped, 3 collection errors
- `test_research_flow.py`: 16/17 pass
- All Stripe integration tests: FAIL (moto/cffi issue)

### Frontend Tests (225 collected)
- **214 pass**, 11 fail
- 8/11 test files pass cleanly
- 3 test files fail: `integration.test.jsx`, `StreamingIndicator.test.jsx`, `ReportDisplay.test.jsx`

### Root Cause for Backend Failures
`pyo3_runtime.PanicException` from `cryptography` / `_cffi_backend` causes ~80% of failures. Fixing this single dependency would restore ~200 tests.

---

## Priority 1: Fix Broken Test Environment

The `moto` → `cryptography` → `cffi` dependency chain is broken. Fix:
```bash
pip install cffi cryptography --force-reinstall
```
This would restore ~200 existing tests immediately.

---

## Priority 2: Untested Security-Critical Handlers

| Handler | Lines | Coverage | Risk |
|---------|-------|----------|------|
| `auth_callback.py` | 112 | **0%** | OAuth flow, JWT issuance |
| `auth_verify.py` | 129 | **0%** | JWT verification, token expiry |
| `conversations_handler.py` | 323 | **~10%** | Core CRUD API |
| `search_handler.py` | 104 | **0%** | Experimental |

### Recommended Tests for `auth_callback.py`
- Valid OAuth callback with correct state parameter
- Invalid/missing state parameter
- User creation on first login
- JWT token structure and claims
- Token expiry behavior

### Recommended Tests for `auth_verify.py`
- Valid JWT passes verification
- Expired JWT is rejected
- Tampered JWT signature is rejected
- Missing authorization header returns 401
- Malformed Bearer token handling

---

## Priority 3: Untested Utility Modules

| Utility | Lines | Coverage | Risk |
|---------|-------|----------|------|
| `rate_limiter.py` | 132 | **0%** | Abuse protection |
| `tiered_rate_limiter.py` | 123 | **0%** | Free vs. paid enforcement |
| `device_fingerprint.py` | 114 | **0%** | Header-based fingerprinting |
| `feature_extractor.py` | 688 | **0%** | Financial metric extraction |
| `currency.py` | 88 | **0%** | Currency conversion |
| `conversation_updater.py` | 55 | **0%** | Conversation state |
| `fmp_client.py` | 359 | **0%** | External API client |

### Recommended Tests for Rate Limiting Stack
- Device fingerprint extraction from various header combinations
- Rate limit check with fresh vs. exhausted quota
- Tiered limits: free user blocked, paid user allowed
- Edge case: missing headers, IPv6 addresses
- DynamoDB error → fail-open behavior

### Recommended Tests for `feature_extractor.py`
- Standard financial statement parsing
- Missing fields / null values
- Division by zero in ratio calculations
- Negative revenue / earnings edge cases
- Empty or malformed input data

---

## Priority 4: Frontend Coverage Gaps

### Currently Untested (0% coverage)

| Module | Lines | Type |
|--------|-------|------|
| `App.jsx` | 1,500+ | Root app shell |
| `auth.jsx` | 300+ | OAuth/JWT provider |
| `conversationsApi.js` | 194 | API client |
| `stripeApi.js` | 166 | Payment API |
| `ConversationList.jsx` | 276 | UI component |
| `SubscriptionManagement.jsx` | 202 | UI component |
| `UpgradeModal.jsx` | 210 | UI component |
| `WaitlistPage.jsx` | 541 | UI component |
| `useConversations.js` | 234 | Data hook |
| `useCompanySearch.js` | 90 | Data hook |

### Recommended Frontend Tests
1. **API modules** (`conversationsApi.js`, `stripeApi.js`) — MSW is already configured; mock HTTP calls and verify request/response handling
2. **`auth.jsx`** — Test OAuth callback, token storage, AuthProvider context value
3. **`useConversations.js`** — Test pagination, sorting, CRUD operations with MSW mocks

---

## Priority 5: CI/CD Pipeline Gaps

Tests exist but are **not running in CI/CD**:

| What | Status |
|------|--------|
| Backend `pytest tests/unit` | **Not in pipeline** |
| Backend `pytest tests/integration` | **Not in pipeline** |
| Frontend `npm run test:run` | **Disabled** (`if: false`) |
| Frontend `npm run lint` | **Not in pipeline** |
| Security `pytest tests/security` | **Not in pipeline** |

### Recommended CI/CD Additions
Add to `deploy-dev.yml` before infrastructure deployment:
```yaml
- name: Run backend tests
  working-directory: chat-api/backend
  run: |
    pip install -r requirements-dev.txt
    pytest tests/unit -v --cov=src --cov-report=term
    pytest tests/integration -v -m integration

- name: Run frontend tests
  working-directory: frontend
  run: |
    npm ci
    npm run test:run
    npm run lint

- name: Run security scan
  working-directory: chat-api/backend
  run: pytest tests/security -v
```

---

## Priority 6: Test Infrastructure Improvements

1. **Add `.coveragerc`** — set minimum 70% threshold per file
2. **Add coverage to CI** — fail build if coverage drops below threshold
3. **Migrate `critical-fixes.spec.js`** — uses Jest API but project uses Vitest
4. **Fix `test_message_persistence.py`** — hits real DynamoDB at import time instead of using moto
5. **Standardize mocking** — some tests use `moto`, others use `MagicMock` for AWS services

---

## Priority 7: Investment Research Module

| Module | Lines | Coverage |
|--------|-------|----------|
| `multi_agent/orchestrator.py` | ~400 | **0%** |
| `multi_agent/task_state.py` | ~200 | **0%** |
| `earnings_tracker.py` | ~150 | **0%** |
| `company_names.py` | ~100 | **0%** |
| `index_tickers.py` | ~150 | **0%** |

---

## Priority 8: Terraform / Infrastructure Testing

Currently only `terraform validate` and `terraform plan` run. Missing:
- Security policy scanning (checkov/tfsec)
- Module-level tests (terratest)
- Cost estimation checks

---

## Summary: Quick Wins vs. Larger Efforts

### Quick Wins (workflow changes only, no new test code)
1. Fix cffi/cryptography dependency → restores ~200 tests
2. Enable existing tests in CI/CD → catches regressions
3. Enable frontend tests in CI/CD → remove `if: false`
4. Add `.coveragerc` → prevent coverage regression

### Larger Efforts (new test code required)
1. `auth_callback.py` + `auth_verify.py` unit tests — security-critical
2. Rate limiting stack tests — billing integrity
3. Frontend API module tests — data layer
4. `feature_extractor.py` tests — 688 lines of numerical code
5. Infrastructure security scanning — add checkov to CI/CD
