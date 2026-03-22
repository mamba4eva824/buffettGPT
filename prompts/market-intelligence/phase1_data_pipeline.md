# Phase 1: S&P 500 Data Ingestion Pipeline — GSD Prompt

Use this prompt to plan and implement the batch data pipeline that ingests 5 years of quarterly financial data for all ~500 S&P 500 constituents into DynamoDB.

---

## Goal

Build a batch ingestion pipeline that fetches financial data for all S&P 500 companies via the FMP API and stores structured metrics in the existing `metrics-history-{env}` DynamoDB table. Include a placeholder scheduler triggered by the FMP earnings calendar endpoint.

---

## GSD Step 1: Audit Snapshot

### Knowns / Evidence

| What | Where | Details |
|------|-------|---------|
| FMP client with caching + retries | `chat-api/backend/src/utils/fmp_client.py` | `get_financial_data(ticker)` fetches 3 statements, caches in `financial-data-cache` table with 90-day TTL. Handles currency conversion, rate limit retries (429 backoff). |
| Feature extractor | `chat-api/backend/src/utils/feature_extractor.py` | `prepare_metrics_for_cache()` transforms raw financials → 9-category DynamoDB items (1 per quarter). 163 features total. |
| metrics-history table | `chat-api/terraform/modules/dynamodb/ml_tables.tf` | PK: `ticker` (S), SK: `fiscal_date` (S). TTL enabled. 90-day expiry. PAY_PER_REQUEST. |
| Existing S&P 500 ticker list | `sp500_analysis/config.py` | 498 tickers hardcoded (FMP `/stable/sp500-constituent` returns 402 on Starter tier). |
| Partial ticker list in backend | `chat-api/backend/investment_research/index_tickers.py` | Only 10 test SP500 tickers. Needs full 498-ticker list. |
| FMP API rate limit | `sp500_analysis/config.py` | Starter tier: 300 calls/min. Each company requires 3 API calls (income, cashflow, balance) if not cached. |
| Batch generation CLI | `chat-api/backend/investment_research/batch_generation/batch_cli.py` | Existing pattern for batch-processing tickers with progress tracking. |
| 498 companies already fetched | `sp500_analysis/data/company_financials/` | JSON files with raw financials — can be used for initial backfill without API calls. |
| FMP earnings calendar endpoint | `sp500_analysis/config.py` | `/stable/earnings-calendar` is available on Starter tier. Returns upcoming earnings dates per ticker. |

### Unknowns / Gaps

1. **Execution environment for batch job**: Lambda has 15-min timeout. 500 companies × ~3 API calls each = ~1500 calls. At 300/min, that's ~5 minutes of API time + processing. Might fit in one Lambda, or might need Step Functions / SQS fan-out.
2. **Idempotency**: What happens if the pipeline runs mid-way and fails? Need to track which tickers succeeded.
3. **Initial backfill vs incremental**: First run needs all 500 companies. Subsequent runs only need companies that reported new earnings.
4. **Earnings calendar granularity**: Does `/stable/earnings-calendar` give us enough info to know when new quarterly data is available on FMP?

### Constraints

- FMP Starter tier: 300 calls/min, `/stable/` endpoints only.
- All infrastructure via Terraform — no manual AWS changes.
- Lambda packages in `chat-api/backend/build/`.
- Reuse existing `fmp_client.py` and `feature_extractor.py` — no duplicate data logic.

### Risks

1. **Lambda timeout**: 500 companies might exceed 15-min Lambda limit → mitigate with SQS fan-out pattern.
2. **FMP rate limiting**: Aggressive batching could trigger 429s → existing retry logic handles this, but pipeline should respect batch pacing.
3. **DynamoDB write throughput**: 500 tickers × 20 quarters × 1 item = 10,000 batch writes → PAY_PER_REQUEST handles this, but use batch_write_item for efficiency.

---

## GSD Step 2: PRD — Acceptance Criteria

```
AC-1: Given the full S&P 500 ticker list, when the pipeline runs, then metrics-history table
      contains ≥490 tickers with ≥20 quarters (5 years) of data each (allowing for newly listed
      companies with shorter history).

AC-2: Given a ticker that already has cached data in financial-data-cache (TTL not expired),
      when the pipeline processes that ticker, then no FMP API calls are made (cache hit).

AC-3: Given the pipeline processes AAPL, when querying metrics-history for AAPL, then 9
      categories (revenue_profit, cashflow, balance_sheet, debt_leverage, earnings_quality,
      dilution, valuation, earnings_events, dividend) are present per quarter.

AC-4: Given a pipeline run fails mid-way at ticker #250, when restarted, then it resumes
      from the last unprocessed ticker (skip already-completed tickers).

AC-5: Given the FMP earnings calendar shows AAPL reported Q1 earnings on 2026-01-30,
      when the scheduler checks the calendar, then AAPL is added to the refresh queue
      (placeholder: log the tickers to refresh, actual scheduling is a future phase).

AC-6: Given the pipeline completes, when checking CloudWatch, then a summary metric is
      logged: total tickers processed, cache hits, API calls made, failures.
```

---

## GSD Step 3: Implementation Plan

### Objective
Build a batch Lambda + SQS fan-out pipeline that ingests S&P 500 financials into the metrics-history table, with a placeholder earnings-calendar-based scheduler.

### Approach Summary
Create an orchestrator Lambda that reads the S&P 500 ticker list, checks which tickers need refresh, and fans out work to an SQS queue. A worker Lambda processes individual tickers using the existing `fmp_client.get_financial_data()` → `feature_extractor.prepare_metrics_for_cache()` → DynamoDB write pipeline. A separate small Lambda reads the FMP earnings calendar to determine which tickers have new quarterly data (placeholder for future EventBridge scheduling).

### Steps

1. **Consolidate S&P 500 ticker list**
   - Move the full 498-ticker list from `sp500_analysis/config.py` into `chat-api/backend/investment_research/index_tickers.py`
   - Include sector mapping from company profiles for later use

2. **Create SQS queue for ticker processing**
   - Terraform: new SQS queue `buffett-{env}-sp500-ingestion`
   - Dead-letter queue for failed tickers
   - Visibility timeout: 300s (5 min per ticker is generous)

3. **Create orchestrator Lambda: `sp500_orchestrator.py`**
   - Reads full ticker list
   - Checks metrics-history for each ticker's last `fiscal_date`
   - Sends tickers needing refresh to SQS queue
   - Logs summary: total, queued, already-fresh

4. **Create worker Lambda: `sp500_worker.py`**
   - Triggered by SQS
   - Per ticker: `fmp_client.get_financial_data()` → `feature_extractor.extract_quarterly_trends()` → `feature_extractor.prepare_metrics_for_cache()` → batch DynamoDB write
   - Error handling: catch per-ticker failures, let SQS retry (max 3 attempts before DLQ)

5. **Create earnings calendar checker: `earnings_calendar_checker.py`**
   - Fetches `/stable/earnings-calendar` for a date range
   - Cross-references with S&P 500 ticker list
   - Logs which tickers have upcoming/recent earnings (placeholder — does not trigger pipeline yet)
   - Future: EventBridge rule to run daily, triggers orchestrator for stale tickers

6. **Add to Terraform**
   - SQS queue + DLQ in `chat-api/terraform/modules/sqs/`
   - Lambda definitions in `chat-api/terraform/modules/lambda/`
   - IAM policies: DynamoDB (metrics-history, financial-data-cache), SQS, Secrets Manager (FMP key), CloudWatch
   - EventBridge rule (disabled placeholder) for daily schedule

7. **Add to build pipeline**
   - Add `sp500_orchestrator.py`, `sp500_worker.py`, `earnings_calendar_checker.py` to `build_lambdas.sh`

8. **Initial backfill strategy**
   - Option A: Run orchestrator Lambda which fans out to worker
   - Option B: Use existing JSON files in `sp500_analysis/data/company_financials/` for faster backfill (one-time script that reads local JSON → transforms → writes to DynamoDB)

### Files to Modify

| File | Change |
|------|--------|
| `chat-api/backend/investment_research/index_tickers.py` | Add full 498-ticker SP500 list with sectors |
| `chat-api/backend/src/handlers/sp500_orchestrator.py` | **NEW** — orchestrator Lambda |
| `chat-api/backend/src/handlers/sp500_worker.py` | **NEW** — SQS worker Lambda |
| `chat-api/backend/src/handlers/earnings_calendar_checker.py` | **NEW** — earnings calendar placeholder |
| `chat-api/terraform/modules/sqs/main.tf` | Add ingestion queue + DLQ |
| `chat-api/terraform/modules/lambda/main.tf` | Add 3 new Lambda definitions |
| `chat-api/terraform/modules/lambda/variables.tf` | Add new Lambda variables |
| `chat-api/terraform/environments/dev/main.tf` | Wire new modules |
| `chat-api/backend/scripts/build_lambdas.sh` | Add 3 new Lambda packages |

### Verification Commands

```bash
# Unit tests
cd chat-api/backend && make test

# Terraform validation
cd chat-api/terraform/environments/dev && terraform validate && terraform plan

# Lambda packaging
cd chat-api/backend && ./scripts/build_lambdas.sh

# Manual test: invoke orchestrator
aws lambda invoke --function-name buffett-dev-sp500-orchestrator --payload '{}' /dev/stdout

# Check metrics-history population
aws dynamodb scan --table-name metrics-history-dev --select COUNT
```

---

## GSD Step 4: Task Graph

Tasks should be created via `TodoWrite` when executing this phase:

```
Task 1: Consolidate SP500 ticker list into index_tickers.py
  Dependencies: none
  Files: index_tickers.py
  Verify: python -c "from investment_research.index_tickers import SP500_TICKERS; assert len(SP500_TICKERS) >= 490"

Task 2: Create SQS queue Terraform module
  Dependencies: none
  Files: modules/sqs/main.tf, modules/sqs/variables.tf, modules/sqs/outputs.tf
  Verify: terraform validate

Task 3: Create sp500_orchestrator.py Lambda handler
  Dependencies: Task 1
  Files: src/handlers/sp500_orchestrator.py
  Verify: make test

Task 4: Create sp500_worker.py Lambda handler
  Dependencies: Task 1
  Files: src/handlers/sp500_worker.py
  Verify: make test

Task 5: Create earnings_calendar_checker.py placeholder
  Dependencies: none
  Files: src/handlers/earnings_calendar_checker.py
  Verify: make test

Task 6: Add Terraform definitions for 3 new Lambdas + SQS + IAM
  Dependencies: Task 2, Task 3, Task 4, Task 5
  Files: modules/lambda/main.tf, environments/dev/main.tf
  Verify: terraform validate && terraform plan

Task 7: Add new Lambdas to build_lambdas.sh
  Dependencies: Task 3, Task 4, Task 5
  Files: scripts/build_lambdas.sh
  Verify: ./scripts/build_lambdas.sh (check build/ output)

Task 8: Write unit tests for orchestrator + worker
  Dependencies: Task 3, Task 4
  Files: tests/test_sp500_orchestrator.py, tests/test_sp500_worker.py
  Verify: make test
```

---

## GSD Step 5: Self-Critique / Red Team

### Fragile assumptions
- **Lambda 15-min timeout may not be enough for orchestrator** if it checks metrics-history freshness for all 500 tickers synchronously. Mitigation: batch DynamoDB scans, or just queue all tickers and let the worker skip fresh ones.
- **SQS message size limit (256KB)** is fine — each message is just a ticker string.

### Failure modes
- FMP API goes down during batch run → workers fail, SQS retries 3x, then DLQ. Orchestrator can be re-invoked to catch stragglers.
- DynamoDB throttling on batch writes → PAY_PER_REQUEST should handle, but add exponential backoff on batch_write_item.

### Simplest 80% version
Skip SQS entirely — have a single Lambda process all 500 tickers sequentially with the 15-min timeout. At ~1.5 seconds per cached ticker (DynamoDB read + write), 500 tickers = ~12.5 minutes. Only add SQS fan-out if the simple version times out.
