Using the RALF workflow, implement Phase 4 from docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md.

CONSTRAINT: Do NOT modify any Phase 1 files: tests/performance/conftest.py, tests/performance/utils/mock_stripe_events.py, tests/performance/utils/metrics_collector.py. If you need a helper that doesn't exist, define it locally in your test file.

Read these files first:
- tests/performance/conftest.py (shared fixtures)
- tests/performance/utils/mock_stripe_events.py (event payload generators)
- tests/performance/utils/metrics_collector.py (metrics collection)
- src/handlers/stripe_webhook_handler.py (handler under test)

FILE: chat-api/backend/tests/performance/test_spike_scenarios.py

Create tests using concurrent.futures.ThreadPoolExecutor, time.sleep for pacing, and moto @mock_aws:

- test_spike_0_to_100_in_5s: Ramp load from 0 to 100 concurrent webhooks over 5 seconds (20/sec ramp rate). Pre-seed 100 users. Use MetricsCollector to record latency per time window (second-by-second). Print a table showing latency at each second of the ramp. Verify all events processed.

- test_sustained_load_60s: Submit webhooks at ~50/second for 60 seconds (~3000 total). Use a loop with time.sleep(0.02) pacing to control rate. Pre-seed 200 users and cycle through them. Track latency in 10-second windows. Print: overall p50/p95/p99, per-window throughput, total events processed, error count. Verify latency stays stable (p95 of last window within 2x of first window).

- test_spike_recovery_pattern: Three phases: (1) Spike: 100 concurrent events in 1 second, (2) Calm: 10 events/second for 5 seconds, (3) Spike: 100 concurrent events in 1 second. Track latency separately for each phase. Verify the second spike performs similarly to the first (recovery confirmation). Print comparison table.

- test_mixed_event_storm: Generate 100 events: ~17 of each of the 6 types (round to 100). Submit all concurrently. Verify each event type was handled by its correct handler. Use a shared counter dict to track how many of each type processed. Print distribution table.

- test_error_rate_under_load: Generate 90 valid events + 10 events with invalid data (e.g., missing required fields like client_reference_id, or nonexistent user_ids). Submit all 100 concurrently. Verify ~90 succeed and ~10 return 500. Calculate and report error rate. Verify error rate matches expected ~10%.

Requirements for all tests:
- Use @pytest.mark.performance marker
- Use MetricsCollector from tests.performance.utils.metrics_collector
- Use event generators from tests.performance.utils.mock_stripe_events
- Mock stripe_service.verify_webhook_signature to bypass signature checks
- Use moto @mock_aws for DynamoDB
- Pre-seed users table with enough users for the test (at least 200)
- Each test must print a detailed summary with: total events submitted, total events processed successfully, error count and rate, latency p50/p95/p99, throughput events/second (overall and per-window where applicable)

Verification Gate:
cd chat-api/backend && pytest tests/performance/test_spike_scenarios.py -v -s

All tests must pass. The sustained load test may take ~60 seconds — that is expected. If any fail, debug and fix before marking complete.
