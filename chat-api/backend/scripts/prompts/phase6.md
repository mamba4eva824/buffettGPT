Using the RALF workflow, implement Phase 6 from docs/stripe/STRIPE_LOAD_PERFORMANCE_TESTING.md.

Prerequisites: Phases 2-5 are complete. These files exist:
- tests/performance/test_webhook_concurrency.py
- tests/performance/test_idempotency_stress.py
- tests/performance/test_dynamodb_throughput.py
- tests/performance/test_spike_scenarios.py
- tests/performance/locustfile.py
- scripts/run_performance_tests.sh

TASK 1: Create Report Generator

FILE: chat-api/backend/tests/performance/generate_report.py

Create a standalone script that:
1. Runs all pytest performance tests capturing stdout
2. Parses the printed metrics summaries (p50, p95, p99, throughput, error rates)
3. Generates a markdown report with:
   - Executive summary (overall PASS/FAIL)
   - Latency table per test scenario vs targets (p50 < 200ms, p95 < 500ms, p99 < 1s)
   - Throughput table (events/second per scenario vs target > 50 RPS)
   - Error rate table per scenario vs target < 1%
   - Bottleneck analysis (identify which tests had highest latency or failures)
   - Recommendations section based on findings
4. Saves report to path specified by --output argument

Usage: python tests/performance/generate_report.py --output docs/stripe/PERFORMANCE_REPORT.md

TASK 2: Run Full Test Suite

Execute all performance tests:
cd chat-api/backend
pip install -r requirements-performance.txt
pytest tests/performance/ -v -s 2>&1 | tee tests/performance/reports/full_run.log

If any tests fail, investigate and fix them. All tests must pass.

TASK 3: Generate Report

Run: python tests/performance/generate_report.py --output docs/stripe/PERFORMANCE_REPORT.md

TASK 4: Review and Enrich

Read the generated docs/stripe/PERFORMANCE_REPORT.md and enhance it with:
- Analysis of any bottlenecks found
- Specific recommendations (e.g., "Add DynamoDB DAX for GSI queries" or "Increase Lambda provisioned concurrency")
- Comparison to the target metrics in the implementation guide
- A "Next Steps" section

Verification Gate:
cd chat-api/backend
pytest tests/performance/ -v -s
test -f docs/stripe/PERFORMANCE_REPORT.md

Both must succeed. The report must contain: latency percentiles, throughput metrics, error rates, and at least 3 recommendations.
