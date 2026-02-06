Using the RALF workflow, implement Phase 5 from docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md.

CONSTRAINT: Do NOT modify any Phase 1 files: tests/performance/conftest.py, tests/performance/utils/mock_stripe_events.py, tests/performance/utils/metrics_collector.py. If you need a helper that doesn't exist, define it locally in your test file.

Read these files first:
- docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md (full implementation guide)
- src/handlers/subscription_handler.py (subscription API endpoints)
- src/handlers/stripe_webhook_handler.py (webhook endpoint)
- src/utils/stripe_service.py (Stripe service layer)
- chat-api/terraform/modules/api-gateway/main.tf (search for "subscription" and "stripe" to find route definitions)
- frontend/src/api/stripeApi.js (how frontend calls the API)

FILE 1: chat-api/backend/tests/performance/locustfile.py

Create Locust load test classes:

Class 1 - SubscriptionUser(HttpUser):
- wait_time = between(0.1, 0.5)
- on_start: Set up auth headers (mock JWT token)
- Task create_checkout (weight=2): POST /subscription/checkout with success_url and cancel_url. Include Authorization header.
- Task create_portal (weight=1): POST /subscription/portal. Include Authorization header.
- Task get_status (weight=5): GET /subscription/status. Include Authorization header. This is the most common operation.

Class 2 - WebhookUser(HttpUser):
- wait_time = between(0.05, 0.2) (webhooks come fast)
- Task send_checkout_webhook (weight=3): POST /stripe/webhook with checkout.session.completed payload. Include Stripe-Signature header.
- Task send_invoice_paid_webhook (weight=3): POST /stripe/webhook with invoice.payment_succeeded payload.
- Task send_subscription_updated_webhook (weight=2): POST /stripe/webhook with customer.subscription.updated payload.
- Task send_duplicate_webhook (weight=1): POST /stripe/webhook with a repeated event ID to test idempotency.

Configuration:
- Include a WebhookPayloadMixin or helper that generates realistic payloads with random user/customer/subscription IDs
- Add custom event listeners to log failures with details
- Add tag-based system so users can run: locust --tags webhook or locust --tags subscription

FILE 2: chat-api/backend/scripts/run_performance_tests.sh

Create an executable bash script:

The script should:
1. Parse arguments: --locust (run Locust tests), --phase N (run specific phase), --all (default)
2. Check prerequisites: Python 3.11, pip, required packages
3. Install performance dependencies if missing: pip install -r requirements-performance.txt
4. Create reports directory: tests/performance/reports/
5. Run pytest performance tests based on flags:
   --phase 2: pytest tests/performance/test_webhook_concurrency.py tests/performance/test_idempotency_stress.py -v -s
   --phase 3: pytest tests/performance/test_dynamodb_throughput.py -v -s
   --phase 4: pytest tests/performance/test_spike_scenarios.py -v -s
   --all: Run all pytest performance tests
6. If --locust flag: Run Locust in headless mode (100 users, spawn rate 10/s, duration 60s), save HTML report to tests/performance/reports/locust_report.html, requires --host argument or PERF_TEST_HOST env var
7. Print summary table of results (pass/fail per test file, total duration)
8. Exit non-zero if any test failed

Make the script executable with chmod +x.

FILE 3: chat-api/backend/.gitignore

Create or append (do not overwrite existing content):
tests/performance/reports/

Verification Gate:
cd chat-api/backend
python -c "from tests.performance.locustfile import SubscriptionUser, WebhookUser; print('locust classes OK')"
bash scripts/run_performance_tests.sh --help

Both commands must succeed. If any fail, debug and fix before marking complete.
