# Phase 2: S&P 500 Aggregate Analytics Table — GSD Prompt

Use this prompt to plan and implement the pre-computed sector and index-level aggregate table that powers cross-company analytics for the Market Intelligence agent.

---

## Goal

Create a new DynamoDB table `sp500-aggregates-{env}` that stores pre-computed sector-level and index-level analytics. A Lambda computes these aggregates from the per-company data in `metrics-history-{env}` after each pipeline run.

---

## GSD Step 1: Audit Snapshot

### Knowns / Evidence

| What | Where | Details |
|------|-------|---------|
| metrics-history table | `chat-api/terraform/modules/dynamodb/ml_tables.tf` | Per-ticker, per-quarter data. PK: `ticker`, SK: `fiscal_date`. 9 categories embedded per item. |
| 11 GICS sectors in S&P 500 | Standard | Technology, Healthcare, Financials, Consumer Discretionary, Communication Services, Industrials, Consumer Staples, Energy, Utilities, Real Estate, Materials |
| Company profiles with sector | `sp500_analysis/data/company_profiles/` | Each profile has `sector` and `industry` fields from FMP |
| DynamoDB table patterns | `chat-api/terraform/modules/dynamodb/` | PAY_PER_REQUEST, KMS encryption, TTL-based expiry. Consistent naming: `{project}-{env}-{resource}` |
| Feature extractor metrics | `chat-api/backend/src/utils/feature_extractor.py` | 9 categories: revenue_profit, cashflow, balance_sheet, debt_leverage, earnings_quality, dilution, valuation, earnings_events, dividend |
| Annual aggregation logic | `feature_extractor.py:aggregate_annual_data()` | Flow metrics summed, point-in-time uses latest quarter. Already handles this for individual companies. |

### Unknowns / Gaps

1. **Sector classification source**: RESOLVED — `SP500_SECTORS` dict exists in `index_tickers.py` with 498 tickers mapped to FMP sector names (Technology, Healthcare, Financial Services, Consumer Cyclical, Consumer Defensive, Communication Services, Industrials, Energy, Utilities, Real Estate, Basic Materials).
2. **How to handle companies reporting in different fiscal quarters**: AAPL reports Oct-Dec as Q1, MSFT reports Oct-Dec as Q2. Sector aggregates should use calendar quarters for consistency.
3. **Market cap weighting**: Should sector aggregates be equal-weighted or cap-weighted? Cap-weighted is more representative but requires current market cap data.
4. **Refresh timing**: Aggregates should recompute after the pipeline ingests new data. Trigger from `sp500_pipeline.py` (single Lambda, no SQS).

### Constraints

- All infrastructure via Terraform.
- Aggregates must be fast to query (agent tools need sub-second response).
- No additional FMP API calls — compute entirely from data already in DynamoDB.

### Risks

1. **Stale aggregates**: If pipeline partially completes, aggregates may reflect mixed quarters.
2. **Large DynamoDB scans**: Reading all 500 tickers × 20 quarters = 10,000 items for a full recompute. Should batch scan and compute incrementally.
3. **Calendar quarter alignment**: Different fiscal year-ends make naive aggregation misleading.

---

## GSD Step 2: PRD — Acceptance Criteria

```
AC-1: Given all S&P 500 data in metrics-history, when aggregates Lambda runs, then
      sp500-aggregates table contains one "INDEX" item with overall S&P 500 metrics
      (median revenue growth, avg margins, total market cap proxy).

AC-2: Given S&P 500 data, when aggregates Lambda runs, then sp500-aggregates table
      contains one item per FMP sector (11 sectors: Technology, Healthcare, Financial Services,
      Consumer Cyclical, Consumer Defensive, Communication Services, Industrials, Energy,
      Utilities, Real Estate, Basic Materials) with sector-level medians for key metrics:
      revenue_growth_yoy, gross_margin, operating_margin, net_margin, fcf_margin,
      debt_to_equity, roe, roic, eps_surprise_pct, dividend_yield.

AC-3: Given sector aggregates computed, when querying "Technology" sector, then response
      includes: number of companies, top 5 by revenue, top 5 by FCF margin, median
      metrics for the latest available quarter.

AC-4: Given aggregates table populated, when any item is read, then it contains
      a `computed_at` timestamp and `data_coverage` field indicating how many tickers
      contributed to the aggregate.

AC-5: Given a company changes sector (rare), when aggregates recompute, then the
      company appears in its new sector and not the old one.
```

---

## GSD Step 3: Implementation Plan

### Objective
Create the sp500-aggregates DynamoDB table and a Lambda that computes sector + index-level analytics from metrics-history data.

### Approach Summary
Add a new DynamoDB table with a flexible PK/SK schema: PK = `aggregate_type` (e.g., "SECTOR", "INDEX"), SK = `aggregate_key` (e.g., "Technology", "OVERALL"). The aggregate Lambda scans metrics-history for the latest quarter per ticker, joins with a sector mapping, and computes percentiles/medians/rankings per sector and overall. It runs after the Phase 1 pipeline completes (triggered by orchestrator or manually).

### Steps

1. **Sector mapping data — ALREADY DONE (Phase 1)**
   - `SP500_SECTORS` dict exists in `index_tickers.py` with 498 entries
   - Helpers: `get_sp500_by_sector()`, `get_sp500_sectors()`, `to_fmp_format()`

2. **Create DynamoDB table via Terraform**
   - Table: `buffett-{env}-sp500-aggregates`
   - PK: `aggregate_type` (S) — values: "SECTOR", "INDEX", "RANKING"
   - SK: `aggregate_key` (S) — values: sector name, "OVERALL", metric name
   - TTL: `expires_at` (7 days — recomputed weekly or on pipeline run)
   - GSI: `computed-at-index` for freshness checks

3. **Create aggregate computation Lambda: `sp500_aggregator.py`**
   - **Step A**: Scan metrics-history to get latest quarter per ticker (batch scan with FilterExpression)
   - **Step B**: Join with sector mapping from `index_tickers.py`
   - **Step C**: Compute per-sector aggregates:
     - Count of companies
     - Median, P25, P75 for: revenue_growth_yoy, gross_margin, operating_margin, net_margin, fcf_margin, debt_to_equity, roe, roic, current_ratio
     - Earnings surprise: median eps_surprise_pct, % of companies that beat EPS estimates
     - Dividends: median dividend_yield, % of dividend payers, median fcf_payout_ratio
     - Top 5 companies by: revenue, net_income, fcf_margin, revenue_growth_yoy
     - Sector total: aggregate revenue, aggregate net income
   - **Step D**: Compute index-level aggregates:
     - Same metrics as sector but across all 500 companies
     - Sector weights (% of total revenue by sector)
     - Concentration metrics (top 10 companies' share of total)
   - **Step E**: Batch write all items to sp500-aggregates table
   - Note: Skip pre-computed rankings (simplest 80% version). Rankings can be computed at query time by the agent Lambda from sector data.

4. **Add Terraform infrastructure**
   - DynamoDB table definition
   - Lambda definition + IAM policies (read metrics-history, write sp500-aggregates)
   - Add to build pipeline

5. **Wire trigger from sp500_pipeline.py**
   - At end of `sp500_pipeline.lambda_handler()`, optionally invoke aggregator Lambda
   - Controlled by event param `{"run_aggregator": true}` (default: false)
   - Can also be invoked manually or on a separate schedule

### Files to Modify

| File | Change |
|------|--------|
| `chat-api/backend/src/handlers/sp500_aggregator.py` | **NEW** — aggregate computation Lambda |
| `chat-api/terraform/modules/dynamodb/ml_tables.tf` | Add sp500-aggregates table |
| `chat-api/terraform/modules/dynamodb/outputs.tf` | Add table name/ARN outputs |
| `chat-api/terraform/modules/lambda/main.tf` | Add aggregator Lambda (follows sp500_pipeline pattern) |
| `chat-api/terraform/environments/dev/main.tf` | Wire new table + Lambda |
| `chat-api/backend/scripts/build_lambdas.sh` | Add aggregator to build (sp500_* pattern already handles investment_research copy) |
| `chat-api/backend/src/handlers/sp500_pipeline.py` | Add optional aggregator invocation at end of pipeline run |

### Verification Commands

```bash
# Unit tests
cd chat-api/backend && make test

# Terraform validation
cd chat-api/terraform/environments/dev && terraform validate && terraform plan

# Manual test: invoke aggregator
aws lambda invoke --function-name buffett-dev-sp500-aggregator --payload '{}' /dev/stdout

# Check aggregates table
aws dynamodb query --table-name buffett-dev-sp500-aggregates \
  --key-condition-expression "aggregate_type = :t" \
  --expression-attribute-values '{":t": {"S": "SECTOR"}}' \
  --select COUNT
```

---

## GSD Step 4: Task Graph

```
Task 1: Create sp500-aggregates DynamoDB table in Terraform
  Dependencies: none
  Files: modules/dynamodb/ml_tables.tf, modules/dynamodb/outputs.tf
  Verify: terraform validate

Task 2: Create sp500_aggregator.py Lambda handler
  Dependencies: none (SP500_SECTORS already exists from Phase 1)
  Files: src/handlers/sp500_aggregator.py
  Verify: make test
  Notes: Include earnings_events aggregates (median eps_surprise_pct, % beat)
         and dividend aggregates (median yield, % payers, median payout ratio)

Task 3: Add Terraform Lambda + IAM + build pipeline
  Dependencies: Task 1, Task 2
  Files: modules/lambda/main.tf, scripts/build_lambdas.sh
  Verify: terraform validate && terraform plan && build zips

Task 4: Write unit tests for aggregator
  Dependencies: Task 2
  Files: tests/unit/test_sp500_aggregator.py
  Verify: make test (all existing + new tests pass)

Task 5: Run aggregator locally against live metrics-history-dev and verify output
  Dependencies: Task 2
  Files: none (manual verification)
  Verify: query sp500-aggregates-dev for SECTOR and INDEX items

Task 6: Wire optional aggregator trigger from sp500_pipeline.py
  Dependencies: Task 2, Phase 1 sp500_pipeline.py exists
  Files: src/handlers/sp500_pipeline.py
  Verify: make test
```

---

## GSD Step 5: Self-Critique / Red Team

### Fragile assumptions
- **Calendar quarter alignment**: Companies with Jan, Mar, Jun, Sep fiscal year-ends will have data for different dates. Using "latest available quarter" per ticker means we're comparing Q4'25 for some companies with Q1'26 for others. Acceptable for sector-level medians, but document the limitation.

### Failure modes
- **Full metrics-history scan**: 10,000 items is manageable but should use parallel scan segments for speed. DynamoDB parallel scan with 4 segments keeps it under 30 seconds.
- **Partial data**: Some S&P 500 companies (recently added) may have <20 quarters. Aggregates should use `data_coverage` to indicate sample size.

### Simplest 80% version
Skip rankings and concentration metrics. Just compute per-sector medians and an index-level summary. Rankings can be computed at query time by the agent Lambda from the sector data. This reduces the aggregator to a single straightforward computation.
