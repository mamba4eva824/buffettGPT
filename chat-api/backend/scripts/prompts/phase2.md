Using the RALF workflow, implement Phase 2 from docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md.

CONSTRAINT: Do NOT modify any Phase 1 files: tests/performance/conftest.py, tests/performance/utils/mock_stripe_events.py, tests/performance/utils/metrics_collector.py. If you need a helper that doesn't exist, define it locally in your test file.

Read these files first to understand the codebase and testing patterns:
- tests/performance/conftest.py (shared fixtures)
- tests/performance/utils/mock_stripe_events.py (event payload generators)
- tests/performance/utils/metrics_collector.py (metrics collection)
- tests/unit/test_stripe_webhook_handler.py (existing mocking patterns)
- src/handlers/stripe_webhook_handler.py (handler under test)

FILE 1: chat-api/backend/tests/performance/test_webhook_concurrency.py

Create tests using concurrent.futures.ThreadPoolExecutor and moto @mock_aws:

- test_concurrent_checkout_completed_50: 50 checkout.session.completed events for 50 different users submitted concurrently. Pre-seed 50 users in the users table. Verify all 50 processed successfully and all users updated to subscription_tier='plus'.

- test_concurrent_mixed_events_100: 100 webhook events across all 6 types submitted concurrently. Verify correct routing (each type handled by correct function) and no exceptions.

- test_single_user_webhook_flood: 20 different event types for the SAME user within 1 second. Verify no race conditions, final user state is consistent, no DynamoDB conditional check failures.

- test_rapid_webhook_burst_20_in_1s: 20 webhooks delivered as fast as possible. Use MetricsCollector to measure individual handler latency. Print p50, p95, p99 at end.

FILE 2: chat-api/backend/tests/performance/test_idempotency_stress.py

Create tests:

- test_duplicate_event_50_concurrent: Generate 1 event with a fixed event_id. Submit it 50 times concurrently. Verify the stripe-events table has exactly 1 record. Verify the handler logic executed exactly once (use a counter or check DynamoDB writes).

- test_idempotency_different_events: 100 unique events submitted concurrently. Verify stripe-events table has exactly 100 records. All processed exactly once.

- test_idempotency_mixed_duplicates: Generate 50 unique events + 50 duplicates (copies of the first 50). Submit all 100 concurrently. Verify exactly 50 records in stripe-events table.

- test_idempotency_table_throughput: Measure raw read/write performance: 200 put_item calls followed by 200 get_item calls to the stripe-events table. Report operations/second.

Requirements for all tests:
- Use @pytest.mark.performance marker
- Use MetricsCollector from tests.performance.utils.metrics_collector
- Mock stripe_service.verify_webhook_signature to return the event directly (bypass crypto)
- Use moto @mock_aws decorator for all DynamoDB operations
- Each test must print a summary: total events, processed count, duplicate count, p50/p95/p99 latency, throughput (events/sec)

Verification Gate:
cd chat-api/backend && pytest tests/performance/test_webhook_concurrency.py tests/performance/test_idempotency_stress.py -v -s

All tests must pass. If any fail, debug and fix before marking complete.
