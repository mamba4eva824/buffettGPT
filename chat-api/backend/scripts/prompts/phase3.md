Using the RALF workflow, implement Phase 3 from docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md.

CONSTRAINT: Do NOT modify any Phase 1 files: tests/performance/conftest.py, tests/performance/utils/mock_stripe_events.py, tests/performance/utils/metrics_collector.py. If you need a helper that doesn't exist, define it locally in your test file.

Read these files first to understand the codebase:
- tests/performance/conftest.py (shared fixtures)
- tests/performance/utils/metrics_collector.py (metrics collection)
- tests/unit/test_stripe_webhook_handler.py (DynamoDB table creation helpers)
- src/handlers/stripe_webhook_handler.py (functions that interact with DynamoDB: _find_user_by_customer_id, _get_user, _initialize_plus_token_usage, _is_event_processed, _mark_event_processed)
- src/utils/token_usage_tracker.py (token usage operations)

FILE: chat-api/backend/tests/performance/test_dynamodb_throughput.py

Create tests using moto @mock_aws and concurrent.futures.ThreadPoolExecutor:

- test_gsi_query_performance_100: Pre-seed 100 users with stripe_customer_id. Run 100 concurrent GSI queries on stripe-customer-index (via _find_user_by_customer_id). Measure p50/p95/p99 latency per query. Report total throughput.

- test_gsi_vs_scan_comparison: Pre-seed 100 users. Run 50 lookups via GSI query and 50 via table scan. Compare latency distributions. Report the performance difference ratio. This tests the fallback path in _find_user_by_customer_id.

- test_concurrent_user_updates_50: Pre-seed 50 users. Run 50 concurrent update_item calls (simulating webhook handlers updating different users simultaneously). Verify all 50 updates persisted correctly — read back each user and validate fields.

- test_token_usage_write_throughput: Pre-seed 50 users with billing_day. Run 50 concurrent _initialize_plus_token_usage calls. Measure write latency and verify all 50 token-usage records created with correct token_limit=2000000.

- test_conditional_update_contention: Pre-seed 1 user. Run 20 concurrent updates to the SAME user record with conditional expressions (e.g., attribute_exists(user_id)). Count how many succeed vs fail ConditionalCheckFailedException. Report contention rate.

- test_batch_read_write_cycle: Write 100 items to stripe-events table, then read all 100 back. Measure write throughput, read throughput, and total cycle time. Report operations/second for each.

Requirements for all tests:
- Use @pytest.mark.performance marker
- Use MetricsCollector from tests.performance.utils.metrics_collector
- Use moto @mock_aws decorator
- Pre-seed tables with realistic data (use helpers from conftest.py if available, otherwise create locally)
- Each test must print a metrics summary: operation count, p50/p95/p99, throughput (ops/sec)
- Include a final test_dynamodb_summary that prints an aggregate table of all benchmarks

Verification Gate:
cd chat-api/backend && pytest tests/performance/test_dynamodb_throughput.py -v -s

All tests must pass. If any fail, debug and fix before marking complete.
