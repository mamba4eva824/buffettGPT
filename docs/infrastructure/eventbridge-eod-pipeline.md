# S&P 500 Daily Stock Price Pipeline

## Executive Summary

The S&P 500 Daily Stock Price Pipeline is a fully automated, serverless data ingestion system that captures end-of-day closing prices for all S&P 500 companies after US market close. Running every weekday evening via Amazon EventBridge, it fetches official closing prices from Financial Modeling Prep (FMP), stores them in DynamoDB, and serves them to the Value Insights dashboard -- giving retail investors current stock price context alongside quarterly fundamental analysis.

### Why It Exists

The Value Insights dashboard analyzes companies using quarterly financial data (revenue, earnings, margins, etc.), but investors also need to know *what the stock costs today*. Without current prices, valuation metrics like P/E ratio and earnings yield can't be computed against the live market. This pipeline bridges the gap between quarterly fundamentals and daily market prices.

### Key Facts

| Metric | Value |
|--------|-------|
| Frequency | Daily, Monday--Friday |
| Trigger time | 10:00 PM UTC (6:00 PM Eastern) |
| Data source | FMP `/stable/historical-price-eod/full` |
| Tickers covered | ~503 S&P 500 companies |
| Records per run | ~481 (17 tickers typically empty) |
| Execution time | ~4 minutes |
| Monthly cost | < $0.05 (excluding FMP API plan) |

---

## Architecture

```
                     Amazon EventBridge
                     cron(0 22 ? * MON-FRI *)
                     10 PM UTC / 6 PM Eastern
                            |
                            v
              +----------------------------+
              |   sp500_eod_ingest Lambda   |
              |   (900s timeout, 512 MB)    |
              +----------------------------+
                  |                    |
                  v                    v
           AWS Secrets Manager    FMP REST API
           (FMP API key)         /stable/historical-price-eod/full
                                    |
                                    v
                            For each of ~503 tickers:
                            - Fetch daily OHLCV data
                            - 0.5s delay between calls
                            - Rate limit: <300 calls/min
                                    |
                                    v
              +----------------------------+
              |  DynamoDB: stock-data-4h    |
              |  PK: TICKER#AAPL           |
              |  SK: DAILY#2026-04-02      |
              |  TTL: 365 days             |
              +----------------------------+
                            |
                            v
              +----------------------------+
              |  value_insights_handler    |
              |  GET /insights/{ticker}    |
              |  → latest_price: $255.92   |
              +----------------------------+
                            |
                            v
              +----------------------------+
              |  Value Insights Dashboard   |
              |  Executive Summary: $255.92 |
              |  Valuation tab: Live P/E    |
              +----------------------------+
```

---

## How It Works (Step by Step)

### 1. EventBridge Fires the Trigger

Every weekday at 10:00 PM UTC (6:00 PM Eastern), Amazon EventBridge invokes the `sp500_eod_ingest` Lambda function. The 2-hour delay after market close (4:00 PM ET) ensures FMP has processed and published the official closing prices.

**Terraform**: `chat-api/terraform/modules/lambda/eventbridge.tf`

| Property | Value |
|----------|-------|
| Schedule | `cron(0 22 ? * MON-FRI *)` |
| Retry policy | 2 retries, max event age 1 hour |
| Feature flag | `enable_eod_ingest_schedule` |

### 2. Lambda Checks Guards

Before doing any work, the Lambda checks two conditions:

- **Market holiday guard**: Skips weekends and known US market holidays (New Year's, MLK Day, Presidents' Day, Good Friday, Memorial Day, Independence Day, Labor Day, Thanksgiving, Christmas). These are hardcoded as MM-DD values and need annual review for floating holidays.

- **Idempotency guard**: Queries DynamoDB for `TICKER#AAPL` with `SK = DAILY#{target_date}`. If AAPL already has data for this date, the entire run is skipped. This prevents duplicate writes on EventBridge retries.

Both guards can be overridden with `"force": true` in the event payload.

### 3. Lambda Fetches Prices from FMP

The Lambda loads the S&P 500 ticker list (from a local Python module, falling back to FMP's constituent API) and iterates through each ticker:

```
GET /stable/historical-price-eod/full?symbol={ticker}&from={date}&to={date}
```

This returns the official end-of-day data: open, high, low, close, volume, change, change percentage, and VWAP.

**Rate limiting**: A 0.5-second delay between calls keeps usage under FMP's 300 calls/minute limit. If FMP returns HTTP 429 (rate limited), the Lambda waits 2 seconds and retries once.

### 4. Lambda Writes to DynamoDB

Each ticker's closing price is stored as a single record:

```json
{
  "PK": "TICKER#AAPL",
  "SK": "DAILY#2026-04-02",
  "GSI_PK": "DATE#2026-04-02",
  "GSI_SK": "TICKER#AAPL",
  "symbol": "AAPL",
  "date": "2026-04-02",
  "close": 255.92,
  "open": 254.20,
  "high": 256.13,
  "low": 250.65,
  "volume": 31289369,
  "change": 0.29,
  "change_percent": 0.11,
  "vwap": 253.84,
  "expires_at": 1775258640,
  "ingested_at": "2026-04-02T22:01:15+00:00"
}
```

Records are written in batches of 25 via `BatchWriteItem` with exponential backoff (up to 5 retries) on DynamoDB throttling.

### 5. Dashboard Reads the Price

When a user visits the Value Insights dashboard, the `value_insights_handler` Lambda queries:

```
PK = "TICKER#AAPL"
ScanIndexForward = False  (descending -- most recent first)
Limit = 1
```

This returns the most recent closing price, which is displayed in the Executive Summary header and used to compute the live P/E ratio on the Valuation tab.

If the price table is unavailable, the frontend falls back to the stock price from the latest quarterly financial data.

### 6. CloudWatch Metrics

After each run, the Lambda emits custom CloudWatch metrics:
- `RecordsWritten` -- total DynamoDB records written
- `TickersProcessed` -- total tickers attempted
- `TickersWithData` -- tickers with successful price data
- `TickersEmpty` -- tickers with no data (delisted, etc.)
- `RecordsFailed` -- DynamoDB write failures

---

## Infrastructure Components

### Lambda Function

| Property | Value |
|----------|-------|
| Name | `buffett-{env}-sp500-eod-ingest` |
| Handler | `sp500_eod_ingest.lambda_handler` |
| Runtime | Python 3.11 |
| Timeout | 900 seconds (15 minutes max) |
| Memory | 512 MB |

**Source**: `chat-api/backend/src/handlers/sp500_eod_ingest.py`

**Environment Variables**:

| Variable | Purpose |
|----------|---------|
| `STOCK_DATA_4H_TABLE` | DynamoDB table name (`stock-data-4h-{env}`) |
| `FMP_SECRET_NAME` | Secrets Manager key for FMP API credentials |
| `ENVIRONMENT` | dev / staging / prod |
| `POWERTOOLS_SERVICE_NAME` | Lambda Powertools service name |
| `POWERTOOLS_METRICS_NAMESPACE` | CloudWatch metrics namespace |

**Terraform**: `chat-api/terraform/modules/lambda/main.tf`

### DynamoDB Table

| Property | Value |
|----------|-------|
| Name | `stock-data-4h-{env}` |
| Billing mode | PAY_PER_REQUEST (on-demand) |
| Partition key (PK) | String -- `TICKER#{symbol}` |
| Sort key (SK) | String -- `DAILY#{YYYY-MM-DD}` |
| TTL attribute | `expires_at` (365 days from ingestion) |
| Encryption | KMS server-side |

**Global Secondary Index (DateIndex)**:

| Property | Value |
|----------|-------|
| GSI partition key | `DATE#{YYYY-MM-DD}` |
| GSI sort key | `TICKER#{symbol}` |
| Projection | ALL |

**Terraform**: `chat-api/terraform/modules/dynamodb/stock_data_4h.tf`

### Query Patterns

| Use Case | Query |
|----------|-------|
| Latest price for a ticker | `PK = TICKER#AAPL, ScanIndexForward=False, Limit=1` |
| Ticker price history | `PK = TICKER#AAPL, SK BETWEEN DAILY#start AND DAILY#end` |
| All S&P 500 prices for a date | `GSI: GSI_PK = DATE#2026-04-02` |

---

## Operational Procedures

### Manual Lambda Invocation

```bash
# Single ticker test
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --cli-binary-format raw-in-base64-out \
  --payload '{"tickers": ["AAPL"], "date": "2026-04-02"}' \
  /dev/stdout

# Full S&P 500, specific date
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --cli-binary-format raw-in-base64-out \
  --payload '{"date": "2026-04-02"}' \
  /dev/stdout

# Force overwrite existing data
aws lambda invoke \
  --function-name buffett-dev-sp500-eod-ingest \
  --cli-binary-format raw-in-base64-out \
  --payload '{"date": "2026-04-02", "force": true}' \
  /dev/stdout
```

### Local Backfill Script

For bulk historical loading without Lambda (runs locally with AWS credentials):

```bash
cd chat-api/backend

# Latest trading day
python scripts/backfill_4h_prices.py

# Specific date
python scripts/backfill_4h_prices.py --date 2026-04-02

# Specific tickers only
python scripts/backfill_4h_prices.py --tickers AAPL MSFT GOOGL

# Overwrite existing
python scripts/backfill_4h_prices.py --date 2026-04-02 --force
```

**Note**: The backfill script uses FMP's lighter `/stable/historical-price-eod/light` endpoint (close + volume only, no OHLCV) to minimize API usage. Records written by the backfill will have fewer fields than Lambda-ingested records.

### Monitoring

```bash
# Check recent Lambda logs
aws logs tail /aws/lambda/buffett-dev-sp500-eod-ingest --since 1d

# Check EventBridge rule status
aws events describe-rule --name buffett-dev-sp500-eod-4h-ingest

# Count records in table
aws dynamodb scan --table-name stock-data-4h-dev --select COUNT
```

### Disabling the Schedule

```bash
# Via Terraform (recommended)
# Set enable_eod_ingest_schedule = false in environments/dev/main.tf, then terraform apply

# Via AWS CLI (immediate)
aws events disable-rule --name buffett-dev-sp500-eod-4h-ingest
```

---

## Downstream Consumers

### Value Insights Dashboard

The `value_insights_handler` Lambda reads from the stock data table to provide:

1. **Stock price in Executive Summary** -- displayed alongside the ticker name and rating counts
2. **Stock price on the Valuation tab** -- "Last Close" banner with price and date
3. **Live P/E ratio** -- computed from current stock price divided by trailing 12-month earnings per share
4. **Price context for all panels** -- available to any panel that accepts the `latestPrice` prop

### Frontend Fallback

If the stock data table is empty or the Lambda can't read from it, the frontend falls back to deriving stock price from the latest quarter's `market_valuation.market_cap / diluted_shares`. This ensures the dashboard always shows a price, though it may be from the last fiscal quarter-end rather than the latest trading day.

---

## Cost Estimate (Monthly)

| Resource | Estimate |
|----------|----------|
| Lambda invocations | ~22 x 4 min x 512 MB = **$0.03** |
| DynamoDB writes | ~481 items/day x 22 days = **$0.01** |
| DynamoDB reads | ~500 reads/day (dashboard queries) = **$0.001** |
| Secrets Manager | ~22 calls/month = **$0.01** |
| EventBridge | Free tier |
| **Total** | **< $0.05/month** (excluding FMP API subscription) |

---

## Known Limitations

### 1. Hardcoded Holiday Calendar

The Lambda uses a static set of MM-DD values for US market holidays. Floating holidays (MLK Day, Presidents' Day, Good Friday, Memorial Day, Labor Day, Thanksgiving) shift each year and need manual updates. The Lambda handles missed holidays gracefully (writes 0 records) but wastes ~503 FMP API calls per holiday.

**Mitigation**: Check FMP's `/stable/is-the-market-open` endpoint before processing, or maintain a year-specific holiday list.

### 2. Ticker Format Mismatch

Two S&P 500 tickers use dot notation (`BRK.B`, `BF.B`) but FMP requires dash notation (`BRK-B`, `BF-B`). The Lambda applies `ticker.replace('.', '-')` but the local ticker list may not match FMP's expected format for all edge cases.

### 3. No Dead Letter Queue

If the Lambda fails after EventBridge's 2 retries, the event is silently dropped. A missed day goes unnoticed until a user sees stale prices.

**Mitigation**: Add an SQS DLQ and a CloudWatch alarm on DLQ depth.

### 4. Table Naming

The table is named `stock-data-4h` (reflecting an earlier design for 4-hour candle data) but now stores daily EOD records with `DAILY#` sort keys. The naming was not updated to avoid a table migration.

---

## File Reference

| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/sp500_eod_ingest.py` | Lambda handler -- fetches and stores daily EOD prices |
| `chat-api/backend/scripts/backfill_4h_prices.py` | Local CLI tool for ad-hoc backfill |
| `chat-api/backend/src/handlers/value_insights_handler.py` | Downstream consumer -- `_get_latest_price()` reads from stock data table |
| `chat-api/terraform/modules/lambda/eventbridge.tf` | EventBridge cron rule and Lambda permission |
| `chat-api/terraform/modules/lambda/main.tf` | Lambda function definition (timeout, memory, env vars) |
| `chat-api/terraform/modules/dynamodb/stock_data_4h.tf` | DynamoDB table schema (keys, GSI, TTL) |
| `frontend/src/hooks/useInsightsData.js` | Frontend hook consuming `latest_price` from API |
| `frontend/src/api/insightsApi.js` | API client calling `GET /insights/{ticker}` |
