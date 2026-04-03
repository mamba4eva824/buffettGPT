# EventBridge EOD Stock Price Pipeline

## Executive Summary

The EOD (End-of-Day) Stock Price Pipeline is a serverless data ingestion system that automatically fetches 4-hour interval OHLCV (Open, High, Low, Close, Volume) candle data for all S&P 500 companies after US market close. The pipeline runs daily on a cron schedule via Amazon EventBridge and stores results in DynamoDB, providing near-real-time closing prices to the Value Insights dashboard.

---

## Architecture

```
EventBridge Rule (cron: 10 PM UTC Mon-Fri)
    |
    v
Lambda: sp500_eod_ingest (900s timeout, 512 MB)
    |   1. Idempotency check (query AAPL for target date)
    |   2. Load S&P 500 ticker list (498 tickers)
    |   3. For each ticker:
    |      GET /stable/historical-chart/4hour?symbol={ticker}
    |      Filter candles to target trade date
    |   4. BatchWriteItem to DynamoDB
    v
DynamoDB: stock-data-4h-{env}
    PK: TICKER#AAPL       SK: DATETIME#2026-04-02 13:30:00
    GSI (DateIndex):
    GSI_PK: DATE#2026-04-02    GSI_SK: TICKER#AAPL
```

### Data Flow

1. **Trigger**: EventBridge fires at 10 PM UTC (6 PM ET), approximately 2 hours after US market close at 4 PM ET. This delay ensures FMP has processed and published the day's candle data.

2. **Idempotency**: The Lambda checks if AAPL data already exists for the target date. If so, it skips execution (unless `force=true` is passed). This prevents duplicate writes on retries.

3. **Data Fetch**: The Lambda iterates through all 498 S&P 500 tickers, calling the FMP `/stable/historical-chart/4hour` endpoint for each. A 0.35-second delay between calls respects FMP's rate limits (Starter tier: 300 calls/min).

4. **Date Filtering**: The FMP endpoint returns recent candles across multiple days. The Lambda filters to only candles matching the target trade date.

5. **DynamoDB Write**: Candles are written in batches of 25 via `BatchWriteItem` with exponential backoff retry on throttling.

### Typical Daily Run

| Metric | Value |
|--------|-------|
| Tickers processed | ~498 |
| Tickers with data | ~479 |
| Candles per ticker | 2 (9:30 AM and 1:30 PM sessions) |
| Total records written | ~957 |
| Execution time | ~3 minutes |
| FMP API calls | ~498 |

---

## Infrastructure Components

### EventBridge Rule

| Property | Value |
|----------|-------|
| Name | `{project}-{env}-sp500-eod-4h-ingest` |
| Schedule | `cron(0 22 ? * MON-FRI *)` |
| Retry policy | 2 retries, max event age 1 hour |
| Feature flag | `enable_eod_ingest_schedule` (per environment) |

**Terraform**: `chat-api/terraform/modules/lambda/eventbridge.tf`

### Lambda Function

| Property | Value |
|----------|-------|
| Name | `{project}-{env}-sp500-eod-ingest` |
| Handler | `sp500_eod_ingest.lambda_handler` |
| Runtime | Python 3.11 |
| Timeout | 900 seconds (15 minutes) |
| Memory | 512 MB |

**Source**: `chat-api/backend/src/handlers/sp500_eod_ingest.py`

**Environment Variables**:
- `FMP_SECRET_NAME` - Secrets Manager key for FMP API credentials
- `STOCK_DATA_4H_TABLE` - DynamoDB table name
- `ENVIRONMENT` - dev/staging/prod
- `LOG_LEVEL` - Logging verbosity

### DynamoDB Table

| Property | Value |
|----------|-------|
| Name | `stock-data-4h-{env}` |
| Billing | PAY_PER_REQUEST (on-demand) |
| Encryption | KMS (server-side) |
| TTL | `expires_at` (not currently set by ingestion) |

**Key Schema**:
- PK: `TICKER#{symbol}` (e.g., `TICKER#AAPL`)
- SK: `DATETIME#{timestamp}` (e.g., `DATETIME#2026-04-02 13:30:00`)

**GSI (DateIndex)**:
- GSI_PK: `DATE#{YYYY-MM-DD}` (e.g., `DATE#2026-04-02`)
- GSI_SK: `TICKER#{symbol}`

**Terraform**: `chat-api/terraform/modules/dynamodb/stock_data_4h.tf`

### Query Patterns

**Single ticker, date range** (e.g., "AAPL prices last 30 days"):
```
PK = TICKER#AAPL AND SK BETWEEN DATETIME#2026-03-01 AND DATETIME#2026-04-02
```

**All tickers for one date** (e.g., "all closing prices on April 2"):
```
GSI: GSI_PK = DATE#2026-04-02
```

**Latest price for a ticker** (used by Value Insights handler):
```
PK = TICKER#AAPL, ScanIndexForward=False, Limit=1
```

---

## Operational Procedures

### Manual Invocation

```bash
# Single ticker test
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --payload '{"tickers": ["AAPL"], "date": "2026-04-02"}' \
  /dev/stdout

# Full S&P 500, specific date
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --payload '{"date": "2026-04-02"}' \
  /dev/stdout

# Force overwrite existing data
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --payload '{"date": "2026-04-02", "force": true}' \
  /dev/stdout
```

### Local Backfill Script

For bulk historical loading without Lambda:

```bash
cd chat-api/backend

# Latest trading day
python scripts/backfill_4h_prices.py

# Specific date
python scripts/backfill_4h_prices.py --date 2026-04-02

# Specific tickers only
python scripts/backfill_4h_prices.py --tickers AAPL MSFT GOOGL

# Overwrite
python scripts/backfill_4h_prices.py --date 2026-04-02 --force
```

### Monitoring

Check recent invocations:
```bash
aws logs tail /aws/lambda/buffett-dev-sp500-eod-ingest --since 1d
```

Check EventBridge rule status:
```bash
aws events describe-rule --name buffett-dev-sp500-eod-4h-ingest
```

### Disabling the Schedule

Set `enable_eod_ingest_schedule = false` in the environment's `main.tf` and apply, or disable directly:
```bash
aws events disable-rule --name buffett-dev-sp500-eod-4h-ingest
```

---

## Downstream Consumers

### Value Insights Dashboard

The `value_insights_handler` Lambda queries the 4h table for the most recent candle to provide:
- **Last Close price** displayed as a banner on the Valuation tab
- **Live P/E ratio** computed from current price + last quarter's TTM earnings yield
- **Price delta** showing how the live P/E compares to the last quarterly snapshot

This gives the dashboard near-real-time price context alongside quarterly fundamental data.

---

## Known Gaps and Limitations

### 1. Ticker Format Mismatch

**Issue**: The S&P 500 ticker list uses dot notation (`BRK.B`, `BF.B`) but FMP requires dash notation (`BRK-B`, `BF-B`). These 2 tickers consistently return empty.

**Impact**: Berkshire Hathaway and Brown-Forman missing from daily prices.

**Fix**: Apply `to_fmp_format()` conversion (already exists in `index_tickers.py`) inside `fetch_4h_candles()` before calling the FMP API.

### 2. Stale Ticker List

**Issue**: The `SP500_TICKERS` list in `index_tickers.py` contains 19 companies that have been acquired, delisted, or renamed since the list was compiled:

| Category | Tickers | Examples |
|----------|---------|----------|
| Acquired/delisted | 9 | ATVI (Microsoft), PXD (Exxon), DFS (Capital One), WBA (Sycamore) |
| FMP data gap | 6 | CMA, DAY, FI, IPG, K, MMC |
| Ticker format | 2 | BRK.B, BF.B |

**Impact**: 19 wasted API calls per run, misleading "empty" counts in logs.

**Fix**: Periodic reconciliation of `SP500_TICKERS` against the live S&P 500 index. Could be automated by comparing against FMP's `/stable/sp500-constituent` endpoint quarterly.

### 3. No Market Holiday Awareness

**Issue**: The Lambda runs every weekday. On US market holidays (e.g., July 4th, Thanksgiving), FMP returns no candles. The Lambda handles this gracefully (returns `recordsWritten: 0`) but still consumes an invocation and ~498 API calls.

**Impact**: Wasted FMP API quota on ~10 holidays/year.

**Fix**: Maintain a holiday calendar (static list or FMP's `/stable/is-the-market-open` endpoint) and skip execution on known holidays.

### 4. No Dead Letter Queue

**Issue**: If the Lambda fails after exhausting EventBridge's 2 retries, the event is silently dropped. There is no DLQ or SNS alert.

**Impact**: A failed ingestion day could go unnoticed until a user sees stale prices.

**Fix**: Add an SQS DLQ to the Lambda configuration and a CloudWatch alarm on DLQ depth (pattern already exists in the SAM template design).

### 5. No TTL on Records

**Issue**: Records are written without an `expires_at` attribute. The table will grow indefinitely.

**Impact**: At ~957 records/day, the table would reach ~250K records in one year. Storage cost is minimal (~$0.25/year at PAY_PER_REQUEST) but query performance on large partitions could degrade.

**Fix**: Set `expires_at` to 90 or 365 days from ingestion. The TTL attribute is already enabled on the table in Terraform.

### 6. Single-Region, Single-Source Dependency

**Issue**: The pipeline depends entirely on FMP's `/stable/historical-chart/4hour` endpoint. If FMP is down or rate-limits aggressively, the entire day's ingestion fails.

**Impact**: No price data for the day; Value Insights shows stale last-close.

**Fix**: Consider a fallback data source (e.g., Yahoo Finance via `yfinance`, or Alpha Vantage) or cache the last known good price with a "stale" flag.

---

## Improvement Roadmap

### Short-Term (Low Effort)

1. **Fix BRK.B/BF.B ticker format** - Apply `to_fmp_format()` in `fetch_4h_candles()`. One-line change.
2. **Add TTL to ingested records** - Set `expires_at` to `ingested_at + 365 days`.
3. **Clean stale tickers from SP500_TICKERS list** - Remove 9 acquired companies.

### Medium-Term (Moderate Effort)

4. **Add DLQ + CloudWatch alarm** - SQS queue + alarm on depth > 0, with SNS email notification.
5. **Market holiday skip** - Check FMP market-open endpoint before processing. Saves ~5K API calls/year.
6. **Backfill automation** - Step Function that detects gaps (missing dates) and triggers backfill Lambda invocations.

### Long-Term (Strategic)

7. **Daily close endpoint** - Add a lightweight API route (`GET /prices/{ticker}/latest`) to serve current price directly, reducing frontend coupling to the quarterly metrics API.
8. **Multi-interval support** - Extend the table schema to support 1h, daily, and weekly candles alongside 4h, enabling future charting features.
9. **Real-time price updates** - Replace daily batch with a WebSocket or polling mechanism for intraday price updates during market hours.

---

## Cost Estimate (Monthly)

| Resource | Estimate |
|----------|----------|
| Lambda | ~22 invocations x 3 min x 512 MB = **$0.02** |
| DynamoDB writes | ~957 items/day x 22 days = **$0.01** |
| DynamoDB reads | ~500 reads/day (Value Insights) = **$0.001** |
| Secrets Manager | ~22 calls/month = **$0.01** |
| EventBridge | Free tier |
| **Total** | **< $0.05/month** (excluding FMP API plan) |
