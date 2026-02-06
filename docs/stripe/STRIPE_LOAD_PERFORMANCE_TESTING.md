# Stripe Load & Performance Testing Implementation Guide

> **Workflow**: GSD (Planning) → RALF (Execution in Phases)
> **Created**: 2026-02-04
> **Status**: Ready for RALF Execution

---

## Executive Summary

This guide defines comprehensive load and performance tests for the BuffettGPT Stripe integration. Tests target webhook processing, subscription endpoints, and DynamoDB operations under concurrent load.

---

## Table of Contents

1. [Audit Snapshot](#1-audit-snapshot)
2. [Acceptance Criteria](#2-acceptance-criteria)
3. [Architecture Overview](#3-architecture-overview)
4. [Implementation Phases](#4-implementation-phases)
5. [File Reference](#5-file-reference)
6. [Test Scenarios](#6-test-scenarios)
7. [Metrics & Reporting](#7-metrics--reporting)
8. [Run Instructions](#8-run-instructions)

---

## 1. Audit Snapshot

### Knowns / Evidence

| Component | Details |
|-----------|---------|
| **API Endpoints** | 3 subscription endpoints + 1 webhook endpoint |
| **Webhook Events** | 6 types: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed` |
| **DynamoDB Tables** | `users`, `token-usage`, `stripe-events` (idempotency) |
| **Identified Bottlenecks** | GSI fallback scan in `_find_user_by_customer_id()`, 2-4 DynamoDB calls per webhook, token usage writes under concurrency |
| **Rate Limits** | API Gateway: 100 req/sec (dev), 1000 req/sec (prod), Lambda timeout: 30s |
| **Existing Tests** | Unit tests exist in `tests/unit/test_stripe_*.py`, no load/performance tests |

### Unknowns / Gaps

- DynamoDB on-demand throttling behavior under burst load
- Lambda cold start frequency under sustained load
- Actual Stripe API rate limits in test mode (~100/sec documented)
- Network latency variance between Lambda and DynamoDB/Stripe

### Constraints

- Must use Stripe test mode (not production)
- Cannot stress-test actual Stripe API (external dependency)
- Load tests should be runnable locally and in CI
- Python 3.11 backend (test framework must match)

### Risks

| Risk | Mitigation |
|------|------------|
| DynamoDB throttling | Monitor consumed capacity, use on-demand billing |
| GSI scan fallback | Test specifically for customer lookup performance |
| Idempotency table writes | Test concurrent writes to stripe-events table |
| Cold starts | Measure and report separately from warm invocations |

---

## 2. Acceptance Criteria

| ID | Criterion | Verification Command |
|----|-----------|---------------------|
| **AC-1** | Load test framework installed and configured | `pip install -r requirements-performance.txt && locust --version` |
| **AC-2** | HTTP load tests simulate 50-100 concurrent requests | Locust report shows concurrent users metric |
| **AC-3** | Webhook load tests simulate 10-20 webhooks within 1 second | Test output shows webhook burst handling timing |
| **AC-4** | Sustained load tests run for 60+ seconds | Locust report shows duration ≥ 60s |
| **AC-5** | Spike scenario tests sudden traffic burst (0→100 in 5s) | Test captures spike response times without failures |
| **AC-6** | Reports capture p50, p95, p99 latencies and throughput | Generated report contains all percentile metrics |
| **AC-7** | Error rates tracked and reported per endpoint | Report shows failure counts and percentages |
| **AC-8** | DynamoDB operations tracked with metrics | Test logs show DB operation counts per test |
| **AC-9** | Idempotency tested with duplicate webhook delivery | Same event ID processed once, duplicates rejected |
| **AC-10** | Concurrent resource access tested (same user) | No race conditions or data corruption detected |
| **AC-11** | Summary report generated with bottleneck analysis | Markdown report exists with recommendations |

---

## 3. Architecture Overview

### Components Under Test

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway                               │
│  POST /subscription/checkout  ──┐                                │
│  POST /subscription/portal    ──┼──► subscription_handler.py     │
│  GET  /subscription/status    ──┘                                │
│  POST /stripe/webhook         ────► stripe_webhook_handler.py    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Lambda Functions                            │
│  ┌─────────────────────┐    ┌─────────────────────────────────┐ │
│  │ subscription_handler │    │ stripe_webhook_handler          │ │
│  │  • create_checkout() │    │  • verify_signature()           │ │
│  │  • create_portal()   │    │  • handle_checkout_completed()  │ │
│  │  • get_status()      │    │  • handle_subscription_created()│ │
│  └──────────┬───────────┘    │  • handle_subscription_updated()│ │
│             │                │  • handle_subscription_deleted()│ │
│             │                │  • handle_invoice_paid()        │ │
│             │                │  • handle_invoice_failed()      │ │
│             │                └──────────────┬──────────────────┘ │
└─────────────┼───────────────────────────────┼────────────────────┘
              │                               │
              ▼                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                        DynamoDB Tables                           │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │ users        │  │ token-usage      │  │ stripe-events     │  │
│  │ (GSI: stripe │  │ (user_id +       │  │ (idempotency)     │  │
│  │  -customer)  │  │  billing_period) │  │                   │  │
│  └──────────────┘  └──────────────────┘  └───────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Critical Paths for Load Testing

1. **Webhook Processing Pipeline**
   ```
   Stripe Event → Signature Verify → Idempotency Check →
   Event Handler → DynamoDB Updates → Response
   ```

2. **Checkout Creation Flow**
   ```
   JWT Auth → User Lookup → Subscription Check →
   Stripe API Call → Response
   ```

3. **Status Retrieval Flow**
   ```
   JWT Auth → User Lookup → Token Usage Query →
   Optional Stripe API Call → Response
   ```

---

## 4. Implementation Phases

### Phase 1: Foundation (RALF Phase 1)

**Goal**: Set up test infrastructure and utilities

| Task | File | Description |
|------|------|-------------|
| 1.1 | `tests/performance/__init__.py` | Package initialization |
| 1.2 | `tests/performance/conftest.py` | Shared fixtures, moto setup, metrics hooks |
| 1.3 | `tests/performance/utils/__init__.py` | Utils package |
| 1.4 | `tests/performance/utils/mock_stripe_events.py` | Generate realistic webhook payloads |
| 1.5 | `tests/performance/utils/metrics_collector.py` | Latency/throughput collection and reporting |
| 1.6 | `requirements-performance.txt` | Dependencies: locust, pytest-benchmark |

**Verification Gate**:
```bash
cd chat-api/backend
pip install -r requirements-performance.txt
python -c "from tests.performance.utils.mock_stripe_events import generate_checkout_completed; print('OK')"
```

---

### Phase 2: Concurrent Webhook Tests (RALF Phase 2)

**Goal**: Test webhook handler under concurrent load

| Task | File | Description |
|------|------|-------------|
| 2.1 | `tests/performance/test_webhook_concurrency.py` | 50-100 concurrent webhook tests |
| 2.2 | `tests/performance/test_idempotency_stress.py` | Duplicate event handling under load |

**Test Scenarios**:
- 50 concurrent `checkout.session.completed` events (different users)
- 100 concurrent mixed webhook events
- 20 webhooks for same user within 1 second
- 50 duplicate event IDs sent concurrently

**Verification Gate**:
```bash
cd chat-api/backend
pytest tests/performance/test_webhook_concurrency.py -v --tb=short
pytest tests/performance/test_idempotency_stress.py -v --tb=short
```

---

### Phase 3: DynamoDB Performance Tests (RALF Phase 3)

**Goal**: Measure DynamoDB operation performance and identify bottlenecks

| Task | File | Description |
|------|------|-------------|
| 3.1 | `tests/performance/test_dynamodb_throughput.py` | DB operation benchmarks |

**Test Scenarios**:
- GSI query performance (stripe-customer-index)
- Fallback scan performance comparison
- Concurrent user updates
- Token usage table write throughput
- Idempotency table read/write performance

**Verification Gate**:
```bash
cd chat-api/backend
pytest tests/performance/test_dynamodb_throughput.py -v --benchmark-only
```

---

### Phase 4: Spike & Stress Tests (RALF Phase 4)

**Goal**: Test system behavior under traffic spikes and sustained load

| Task | File | Description |
|------|------|-------------|
| 4.1 | `tests/performance/test_spike_scenarios.py` | Traffic burst simulation |

**Test Scenarios**:
- Spike: 0 → 100 webhooks in 5 seconds
- Sustained: 50 webhooks/second for 60 seconds
- Recovery: Spike → Normal → Spike pattern
- Mixed load: All 6 event types firing simultaneously

**Verification Gate**:
```bash
cd chat-api/backend
pytest tests/performance/test_spike_scenarios.py -v -s
```

---

### Phase 5: HTTP Load Tests (RALF Phase 5)

**Goal**: Full HTTP endpoint load testing with Locust

| Task | File | Description |
|------|------|-------------|
| 5.1 | `tests/performance/locustfile.py` | Locust HTTP load tests |
| 5.2 | `scripts/run_performance_tests.sh` | Orchestration script |

**Test Scenarios**:
- 50-100 concurrent users hitting subscription endpoints
- Webhook endpoint with realistic payloads
- Mixed read/write workload

**Verification Gate**:
```bash
cd chat-api/backend
locust -f tests/performance/locustfile.py --headless -u 10 -r 2 -t 30s --host=http://localhost:8000
```

**Note**: Requires local server or deployed endpoint for HTTP tests.

---

### Phase 6: Reporting & Analysis (RALF Phase 6)

**Goal**: Generate comprehensive performance report

| Task | File | Description |
|------|------|-------------|
| 6.1 | `tests/performance/generate_report.py` | Report generator script |
| 6.2 | `docs/stripe/PERFORMANCE_REPORT.md` | Final analysis document |

**Report Contents**:
- Executive summary with pass/fail status
- Latency percentiles (p50, p95, p99) per endpoint
- Throughput (RPS) measurements
- Error rate analysis
- Bottleneck identification
- Recommendations

---

### Phase 7: AWS Dev Environment Load Testing (RALF Phase 7)

**Goal**: Run Locust load tests against the deployed AWS dev API Gateway with real JWT authentication and Stripe webhook signatures

**Prerequisites**:
- AWS CLI configured with dev account credentials (`aws sts get-caller-identity` succeeds)
- Dev environment deployed (`https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev`)
- AWS Secrets Manager contains: `buffett-dev-jwt-secret`, `stripe-webhook-secret-dev`

| Task | File | Description |
|------|------|-------------|
| 7.1 | `tests/performance/utils/aws_auth.py` | JWT generation, Stripe signature, and Secrets Manager helpers |
| 7.2 | `tests/performance/utils/seed_test_user.py` | DynamoDB test user seeding and cleanup |
| 7.3 | `tests/performance/locustfile.py` | Modify: conditional real auth via env vars |
| 7.4 | `scripts/run_performance_tests.sh` | Modify: add `--aws` flag with secrets fetching |

**Architecture**:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Local Machine (Locust)                                                  │
│                                                                          │
│  run_performance_tests.sh --aws                                          │
│    1. Fetch JWT secret from Secrets Manager                              │
│    2. Fetch Stripe webhook secret from Secrets Manager                   │
│    3. Seed test users in DynamoDB (prefix: perf-test-)                   │
│    4. Export AWS_JWT_SECRET, AWS_WEBHOOK_SECRET env vars                  │
│    5. Launch Locust → hits real API Gateway                              │
│                                                                          │
│  locustfile.py (enhanced)                                                │
│    if AWS_JWT_SECRET set → generate_jwt() with real HS256 signing        │
│    if AWS_WEBHOOK_SECRET set → generate_stripe_signature() with real key │
│    else → existing mock behavior (backward compatible)                   │
└────────────────────────────────────┬─────────────────────────────────────┘
                                     │ HTTPS
                                     ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  AWS Dev Environment                                                     │
│                                                                          │
│  API Gateway (yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev)        │
│    Rate Limits: 100 req/s steady, 500 burst                             │
│                                                                          │
│  Routes:                                                                 │
│    POST /subscription/checkout  ─── auth_verify → subscription_handler   │
│    POST /subscription/portal    ─── auth_verify → subscription_handler   │
│    GET  /subscription/status    ─── auth_verify → subscription_handler   │
│    POST /stripe/webhook         ─── (no auth) → stripe_webhook_handler   │
│                                                                          │
│  DynamoDB Tables:                                                        │
│    buffett-chat-api-dev-users (GSI: stripe-customer-index)               │
│    buffett-chat-api-dev-token-usage                                      │
│    buffett-chat-api-dev-stripe-processed-events                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**New Files to Create**:

#### 7.1 — `tests/performance/utils/aws_auth.py`

JWT generation and Stripe webhook signature helpers for real AWS testing.

```python
"""
Authentication utilities for AWS dev environment load testing.
Generates real JWT tokens and Stripe webhook signatures using secrets
fetched from AWS Secrets Manager.
"""

import jwt          # PyJWT (already in requirements.txt)
import time
import hmac
import hashlib
import json
import boto3
from functools import lru_cache


@lru_cache(maxsize=8)
def fetch_secret(secret_id: str, region: str = 'us-east-1') -> str:
    """Fetch a secret value from AWS Secrets Manager. Cached per session."""
    client = boto3.client('secretsmanager', region_name=region)
    response = client.get_secret_value(SecretId=secret_id)
    return response['SecretString']


def generate_jwt(
    user_id: str,
    email: str,
    secret: str,
    subscription_tier: str = 'free',
    name: str = 'Perf Test User',
    expiry_hours: int = 1
) -> str:
    """
    Generate a real HS256 JWT token matching the format used by auth_callback.py.

    The JWT payload matches what auth_verify.py expects:
    - user_id, email, name, subscription_tier
    - exp (expiry), iat (issued at), iss (issuer)
    """
    now = int(time.time())
    payload = {
        'user_id': user_id,
        'email': email,
        'name': name,
        'subscription_tier': subscription_tier,
        'exp': now + (expiry_hours * 3600),
        'iat': now,
        'iss': 'buffett-chat-api'
    }
    return jwt.encode(payload, secret, algorithm='HS256')


def generate_stripe_signature(payload: str, secret: str) -> str:
    """
    Generate a valid Stripe webhook signature (v1) for the given payload.

    Stripe signature format: t=<timestamp>,v1=<hmac_sha256>
    The HMAC is computed over: "<timestamp>.<payload>"
    """
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload}"
    signature = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"
```

#### 7.2 — `tests/performance/utils/seed_test_user.py`

Creates identifiable test users in the dev DynamoDB users table before load testing.

```python
"""
Seed and cleanup test users in DynamoDB for AWS dev load testing.
All test users are prefixed with 'perf-test-' for easy identification and cleanup.
"""

import boto3
import uuid
import time

TEST_USER_PREFIX = 'perf-test-'
DEFAULT_TABLE = 'buffett-chat-api-dev-users'
DEFAULT_REGION = 'us-east-1'


def seed_test_users(
    table_name: str = DEFAULT_TABLE,
    region: str = DEFAULT_REGION,
    count: int = 5
) -> list[dict]:
    """
    Create test users in the DynamoDB users table.

    Returns a list of user dicts with user_id, email, and stripe_customer_id.
    Each user is created with:
      - user_id: perf-test-<uuid>
      - email: perf-test-<uuid>@buffettgpt.test
      - subscription_tier: 'free'
      - stripe_customer_id: cus_perftest_<uuid>
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    users = []
    for i in range(count):
        uid = f"{TEST_USER_PREFIX}{uuid.uuid4().hex[:12]}"
        user = {
            'user_id': uid,
            'email': f"{uid}@buffettgpt.test",
            'name': f"Perf Test User {i+1}",
            'subscription_tier': 'free',
            'stripe_customer_id': f"cus_perftest_{uuid.uuid4().hex[:12]}",
            'created_at': int(time.time()),
            'updated_at': int(time.time()),
        }
        table.put_item(Item=user)
        users.append(user)
        print(f"  Seeded user: {uid}")

    return users


def cleanup_test_users(
    table_name: str = DEFAULT_TABLE,
    region: str = DEFAULT_REGION,
    user_ids: list[str] | None = None
) -> int:
    """
    Remove test users from DynamoDB.

    If user_ids is None, scans for all users with the perf-test- prefix.
    Returns the number of users deleted.
    """
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)

    if user_ids is None:
        # Scan for all perf-test- users
        response = table.scan(
            FilterExpression='begins_with(user_id, :prefix)',
            ExpressionAttributeValues={':prefix': TEST_USER_PREFIX},
            ProjectionExpression='user_id'
        )
        user_ids = [item['user_id'] for item in response.get('Items', [])]

    deleted = 0
    for uid in user_ids:
        table.delete_item(Key={'user_id': uid})
        deleted += 1
        print(f"  Cleaned up user: {uid}")

    return deleted


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Seed or cleanup test users')
    parser.add_argument('action', choices=['seed', 'cleanup'], help='Action to perform')
    parser.add_argument('--count', type=int, default=5, help='Number of users to seed')
    parser.add_argument('--table', default=DEFAULT_TABLE, help='DynamoDB table name')
    parser.add_argument('--region', default=DEFAULT_REGION, help='AWS region')
    args = parser.parse_args()

    if args.action == 'seed':
        print(f"Seeding {args.count} test users in {args.table}...")
        users = seed_test_users(args.table, args.region, args.count)
        print(f"Done. {len(users)} users created.")
    else:
        print(f"Cleaning up test users in {args.table}...")
        count = cleanup_test_users(args.table, args.region)
        print(f"Done. {count} users deleted.")
```

#### 7.3 — Modify `tests/performance/locustfile.py`

Add conditional real-auth paths. The existing mock behavior is preserved when env vars are not set.

**Changes required** (do NOT rewrite the whole file — patch these sections):

1. Add imports at the top:
```python
import os
import sys

# Add utils to path for aws_auth imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
```

2. Add auth configuration block after imports:
```python
# --- Auth Configuration ---
# When AWS_JWT_SECRET is set, generate real JWT tokens
# When AWS_WEBHOOK_SECRET is set, generate real Stripe signatures
# Otherwise, use existing mock behavior (backward compatible)
AWS_JWT_SECRET = os.environ.get('AWS_JWT_SECRET')
AWS_WEBHOOK_SECRET = os.environ.get('AWS_WEBHOOK_SECRET')

if AWS_JWT_SECRET or AWS_WEBHOOK_SECRET:
    from tests.performance.utils.aws_auth import generate_jwt, generate_stripe_signature
```

3. In `SubscriptionUser.on_start()`, add real JWT path:
```python
def on_start(self):
    self.user_id = f"perf-test-{uuid.uuid4().hex[:12]}"
    if AWS_JWT_SECRET:
        from tests.performance.utils.aws_auth import generate_jwt
        self.token = generate_jwt(
            user_id=self.user_id,
            email=f"{self.user_id}@buffettgpt.test",
            secret=AWS_JWT_SECRET
        )
    else:
        self.token = f"mock-jwt-token-{self.user_id}"
    self.headers = {"Authorization": f"Bearer {self.token}", ...}
```

4. In `WebhookUser`, add real signature path:
```python
def _send_webhook(self, event_payload):
    body = json.dumps(event_payload)
    if AWS_WEBHOOK_SECRET:
        from tests.performance.utils.aws_auth import generate_stripe_signature
        sig = generate_stripe_signature(body, AWS_WEBHOOK_SECRET)
    else:
        sig = "t=123,v1=mock_signature"
    headers = {"Stripe-Signature": sig, "Content-Type": "application/json"}
    self.client.post("/stripe/webhook", data=body, headers=headers, ...)
```

#### 7.4 — Modify `scripts/run_performance_tests.sh`

Add `--aws` flag that fetches secrets, seeds users, and launches Locust against the dev API.

**Add this block** to the argument parsing and a new `run_aws()` function:

```bash
# --- AWS Dev Environment Mode ---
DEV_API_URL="https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev"

run_aws() {
    echo "=== Phase 7: AWS Dev Environment Load Testing ==="
    echo ""

    # Verify AWS CLI is configured
    if ! aws sts get-caller-identity &>/dev/null; then
        echo "ERROR: AWS CLI not configured. Run 'aws configure' first."
        exit 1
    fi
    echo "[1/5] AWS credentials verified"

    # Fetch secrets from Secrets Manager (NEVER hardcode)
    echo "[2/5] Fetching secrets from AWS Secrets Manager..."
    export AWS_JWT_SECRET=$(aws secretsmanager get-secret-value \
        --secret-id buffett-dev-jwt-secret \
        --query SecretString --output text 2>/dev/null)

    if [ -z "$AWS_JWT_SECRET" ]; then
        echo "ERROR: Could not fetch buffett-dev-jwt-secret"
        exit 1
    fi

    export AWS_WEBHOOK_SECRET=$(aws secretsmanager get-secret-value \
        --secret-id stripe-webhook-secret-dev \
        --query SecretString --output text 2>/dev/null)

    if [ -z "$AWS_WEBHOOK_SECRET" ]; then
        echo "ERROR: Could not fetch stripe-webhook-secret-dev"
        exit 1
    fi
    echo "  Secrets loaded (JWT + Webhook)"

    # Seed test users
    echo "[3/5] Seeding test users in DynamoDB..."
    python -m tests.performance.utils.seed_test_user seed --count 10

    # Run Locust
    HOST="${CUSTOM_HOST:-$DEV_API_URL}"
    echo "[4/5] Launching Locust against $HOST"
    echo ""
    echo "  IMPORTANT: API Gateway rate limits apply"
    echo "    Steady: 100 req/s | Burst: 500 req/s"
    echo "    Recommended: -u 50 -r 5 (stay under limits)"
    echo ""

    locust -f tests/performance/locustfile.py \
        --headless \
        -u "${LOCUST_USERS:-50}" \
        -r "${LOCUST_SPAWN_RATE:-5}" \
        -t "${LOCUST_DURATION:-60s}" \
        --host="$HOST" \
        --html=tests/performance/reports/aws_dev_report.html \
        --csv=tests/performance/reports/aws_dev

    # Cleanup test users
    echo ""
    echo "[5/5] Cleaning up test users..."
    python -m tests.performance.utils.seed_test_user cleanup

    echo ""
    echo "=== AWS Dev Load Test Complete ==="
    echo "Report: tests/performance/reports/aws_dev_report.html"

    # Unset secrets from environment
    unset AWS_JWT_SECRET
    unset AWS_WEBHOOK_SECRET
}

# Add to argument parsing:
# --aws)  run_aws; exit 0 ;;
```

**Rate Limit Awareness**:

| Setting | Dev | Prod |
|---------|-----|------|
| API Gateway steady rate | 100 req/s | 1,000 req/s |
| API Gateway burst | 500 req/s | 2,000 req/s |
| Recommended Locust users | 50 | 200 |
| Recommended spawn rate | 5/s | 20/s |
| Lambda concurrency | Unreserved | Unreserved |

**Verification Gate**:
```bash
cd chat-api/backend

# Quick smoke test (10 users, 30 seconds)
bash scripts/run_performance_tests.sh --aws

# Custom configuration
LOCUST_USERS=20 LOCUST_SPAWN_RATE=2 LOCUST_DURATION=30s \
  bash scripts/run_performance_tests.sh --aws

# Override host (e.g., staging)
CUSTOM_HOST=https://staging-api.example.com \
  bash scripts/run_performance_tests.sh --aws
```

**Key Differences from Local Testing (Phases 1-5)**:

| Aspect | Local (moto) | AWS Dev (Phase 7) |
|--------|-------------|-------------------|
| DynamoDB | moto mock (in-memory) | Real DynamoDB (network latency) |
| Lambda | Direct function call | Cold starts + execution environment |
| Auth | Mock JWT/signatures | Real HS256 JWT + Stripe signatures |
| Rate limits | None | API Gateway: 100/s steady, 500 burst |
| Latency | ~0.5-5ms per operation | ~10-100ms per operation (network) |
| Idempotency | moto conditional writes | Real DynamoDB conditional writes |
| Cost | Free | DynamoDB RCU/WCU + Lambda invocations |

**Cleanup**:

Test users are automatically cleaned up after the run. If a run is interrupted, manually clean up:
```bash
cd chat-api/backend
python -m tests.performance.utils.seed_test_user cleanup
```

**Expected Results**:

Latency will be significantly higher than local moto tests due to network round-trips, Lambda cold starts, and real DynamoDB operations. Target baselines for dev:

| Metric | Local (moto) | AWS Dev Target |
|--------|-------------|----------------|
| p50 Latency | 20-130ms | 100-500ms |
| p95 Latency | 26-450ms | 300-1500ms |
| p99 Latency | 28-456ms | 500-3000ms |
| Throughput | 141-748 RPS | 30-100 RPS |
| Error Rate | 0% | < 1% |
| Cold Start Impact | N/A | First ~5s of run |

---

## 5. File Reference

### New Files to Create

```
chat-api/backend/
├── requirements-performance.txt          # Phase 1
├── tests/
│   └── performance/
│       ├── __init__.py                   # Phase 1
│       ├── conftest.py                   # Phase 1
│       ├── utils/
│       │   ├── __init__.py               # Phase 1
│       │   ├── mock_stripe_events.py     # Phase 1
│       │   ├── metrics_collector.py      # Phase 1
│       │   ├── aws_auth.py              # Phase 7
│       │   └── seed_test_user.py        # Phase 7
│       ├── test_webhook_concurrency.py   # Phase 2
│       ├── test_idempotency_stress.py    # Phase 2
│       ├── test_dynamodb_throughput.py   # Phase 3
│       ├── test_spike_scenarios.py       # Phase 4
│       ├── locustfile.py                 # Phase 5
│       ├── generate_report.py            # Phase 6
│       └── reports/                      # Generated (gitignored)
│           └── .gitkeep
└── scripts/
    └── run_performance_tests.sh          # Phase 5
```

### Existing Files Referenced

| File | Purpose |
|------|---------|
| `src/handlers/stripe_webhook_handler.py` | Primary test target (webhooks) |
| `src/handlers/subscription_handler.py` | Primary test target (API) |
| `src/utils/stripe_service.py` | Stripe API wrapper (mock target) |
| `tests/conftest.py` | Existing fixtures to extend |
| `tests/unit/test_stripe_webhook_handler.py` | Reference for mocking patterns |

---

## 6. Test Scenarios

### Scenario Matrix

| ID | Scenario | Concurrency | Duration | Target Metric |
|----|----------|-------------|----------|---------------|
| **S1** | Checkout Completed Burst | 50 webhooks | 1 second | < 500ms p95 |
| **S2** | Mixed Event Storm | 100 webhooks | 5 seconds | < 1s p99, 0% errors |
| **S3** | Single User Flood | 20 webhooks | 1 second | No race conditions |
| **S4** | Duplicate Event Storm | 50 duplicates | 1 second | 49 rejections, 1 success |
| **S5** | Sustained Load | 50 webhooks/sec | 60 seconds | Stable latency |
| **S6** | Traffic Spike | 0→100→0 | 15 seconds | Recovery < 2s |
| **S7** | GSI Query Load | 100 lookups | 1 second | < 50ms p95 |
| **S8** | Token Usage Updates | 50 concurrent | 1 second | No data loss |

### Webhook Event Payloads

Each webhook test uses realistic Stripe event payloads:

```python
# Example: checkout.session.completed
{
    "id": "evt_test_123",
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": "cs_test_abc",
            "client_reference_id": "user_12345",
            "customer": "cus_test_xyz",
            "subscription": "sub_test_789",
            "mode": "subscription",
            "payment_status": "paid"
        }
    }
}
```

---

## 7. Metrics & Reporting

### Metrics Collected

| Metric | Description | Target |
|--------|-------------|--------|
| **p50 Latency** | Median response time | < 200ms |
| **p95 Latency** | 95th percentile response time | < 500ms |
| **p99 Latency** | 99th percentile response time | < 1000ms |
| **Throughput** | Requests per second processed | > 50 RPS |
| **Error Rate** | Percentage of failed requests | < 1% |
| **DynamoDB Reads** | Read capacity units consumed | Monitor |
| **DynamoDB Writes** | Write capacity units consumed | Monitor |
| **Idempotency Hit Rate** | Duplicate events correctly rejected | 100% |
| **Cold Start %** | Percentage of cold starts (if applicable) | < 10% |

### Report Format

```markdown
# Stripe Performance Test Report

## Summary
- **Status**: PASS / FAIL
- **Date**: YYYY-MM-DD
- **Duration**: X minutes
- **Total Requests**: N

## Latency Metrics

| Endpoint | p50 | p95 | p99 | Target | Status |
|----------|-----|-----|-----|--------|--------|
| webhook (checkout.completed) | Xms | Xms | Xms | <500ms p95 | ✓/✗ |
| webhook (invoice.paid) | Xms | Xms | Xms | <500ms p95 | ✓/✗ |
| ... | ... | ... | ... | ... | ... |

## Throughput

| Test | RPS | Target | Status |
|------|-----|--------|--------|
| Sustained Load | X | >50 | ✓/✗ |
| Spike Peak | X | >100 | ✓/✗ |

## Error Analysis

| Error Type | Count | Percentage |
|------------|-------|------------|
| Timeout | X | X% |
| DynamoDB Throttle | X | X% |
| Signature Invalid | X | X% |

## Bottlenecks Identified

1. **[Component]**: Description and recommendation
2. ...

## Recommendations

1. ...
2. ...
```

---

## 8. Run Instructions

### Prerequisites

```bash
cd chat-api/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-performance.txt
```

### Run Individual Phase Tests

```bash
# Phase 2: Webhook Concurrency
pytest tests/performance/test_webhook_concurrency.py -v -s

# Phase 2: Idempotency
pytest tests/performance/test_idempotency_stress.py -v -s

# Phase 3: DynamoDB
pytest tests/performance/test_dynamodb_throughput.py -v --benchmark-only

# Phase 4: Spike Tests
pytest tests/performance/test_spike_scenarios.py -v -s
```

### Run All Performance Tests

```bash
# Run all with markers
pytest tests/performance/ -v -s -m performance

# Generate HTML report
pytest tests/performance/ -v --html=tests/performance/reports/report.html
```

### Run Locust HTTP Tests

```bash
# Headless mode (CI)
locust -f tests/performance/locustfile.py \
  --headless \
  -u 100 \
  -r 10 \
  -t 60s \
  --host=${API_URL} \
  --html=tests/performance/reports/locust_report.html

# Web UI mode (local development)
locust -f tests/performance/locustfile.py --host=${API_URL}
# Open http://localhost:8089
```

### Run AWS Dev Environment Load Tests (Phase 7)

```bash
# Prerequisites: AWS CLI configured with dev credentials
aws sts get-caller-identity  # Verify access

cd chat-api/backend

# Default run (50 users, 5/s spawn, 60s duration)
bash scripts/run_performance_tests.sh --aws

# Custom user count and duration
LOCUST_USERS=20 LOCUST_SPAWN_RATE=2 LOCUST_DURATION=30s \
  bash scripts/run_performance_tests.sh --aws

# Manual seed/cleanup (if run was interrupted)
python -m tests.performance.utils.seed_test_user seed --count 10
python -m tests.performance.utils.seed_test_user cleanup
```

### Generate Summary Report

```bash
python tests/performance/generate_report.py \
  --input tests/performance/reports/ \
  --output docs/stripe/PERFORMANCE_REPORT.md
```

---

## Appendix A: Dependencies

### requirements-performance.txt

```
# Load testing
locust>=2.20.0

# Benchmarking
pytest-benchmark>=4.0.0

# Async support
pytest-asyncio>=0.23.0

# HTML reports
pytest-html>=4.1.0

# Concurrent execution
aiohttp>=3.9.0

# Statistics
numpy>=1.26.0
```

---

## Appendix B: CI/CD Integration

### GitHub Actions Workflow (Optional)

```yaml
name: Performance Tests

on:
  workflow_dispatch:
  schedule:
    - cron: '0 2 * * 1'  # Weekly Monday 2am

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd chat-api/backend
          pip install -r requirements.txt
          pip install -r requirements-performance.txt

      - name: Run performance tests
        run: |
          cd chat-api/backend
          pytest tests/performance/ -v -s --html=report.html

      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: performance-report
          path: chat-api/backend/report.html
```

---

## Appendix C: Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `ModuleNotFoundError: moto` | Missing test deps | `pip install -r requirements.txt` |
| `DynamoDB throttling in tests` | moto limitation | Use `BillingMode='PAY_PER_REQUEST'` |
| `Locust connection refused` | No server running | Start local server or use deployed URL |
| `Signature verification failed` | Wrong mock secret | Check `STRIPE_WEBHOOK_SECRET` in fixtures |
| `Could not fetch buffett-dev-jwt-secret` | AWS credentials missing/wrong | Run `aws sts get-caller-identity` to verify |
| `429 Too Many Requests` | API Gateway rate limit hit | Reduce `LOCUST_USERS` (try 20) and `LOCUST_SPAWN_RATE` (try 2) |
| `401 Unauthorized` (AWS mode) | JWT secret mismatch | Verify `buffett-dev-jwt-secret` in Secrets Manager matches auth_verify |
| `perf-test- users left in DynamoDB` | Interrupted run | Run `python -m tests.performance.utils.seed_test_user cleanup` |
| High latency on first requests | Lambda cold starts | Normal — first 5-10s will show elevated latency |

### Debug Mode

```bash
# Verbose output with full tracebacks
pytest tests/performance/ -v -s --tb=long

# Run single test with debugging
pytest tests/performance/test_webhook_concurrency.py::test_concurrent_checkouts -v -s --pdb
```

---

## Change Log

| Date | Version | Changes |
|------|---------|---------|
| 2026-02-04 | 1.0.0 | Initial implementation guide |
| 2026-02-05 | 1.1.0 | Add Phase 7: AWS dev environment load testing |
