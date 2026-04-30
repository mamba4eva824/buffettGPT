# EventBridge Earnings Update Pipeline

## Executive Summary

The Earnings Update Pipeline is a serverless automation that detects when S&P 500 companies release quarterly earnings and immediately updates the `metrics-history` DynamoDB table with full financial data, earnings beat/miss results, dividends, and TTM valuation ratios. The pipeline runs twice daily via Amazon EventBridge — once after market close and once after market open — to capture both after-hours and pre-market earnings announcements within hours of release.

This pipeline replaces the previous bulk `sp500_pipeline` Lambda (which processed all 498 tickers) with a targeted approach that only processes the 5-40 companies that reported that day.

---

## Architecture

```
EventBridge Scheduler (2x daily, Mon-Fri, America/New_York timezone)
    |
    |-- Post-close:  5:00 PM ET  cron(0 17 ? * MON-FRI *)
    |-- Post-open:  11:30 AM ET  cron(30 11 ? * MON-FRI *)
    |
    v
Lambda: earnings_update (300s timeout, 512 MB)
    |
    |-- Auto Mode (default):
    |   1. GET /stable/earnings-calendar (last 48 hours + next 7 days)
    |   2. Filter to S&P 500 tickers
    |   3. Identify recently reported companies
    |
    |-- Manual Mode ({"tickers": ["AAPL"]}):
    |   1. Skip calendar check
    |   2. Process specified tickers directly
    |
    |-- Per ticker (5-40 typically):
    |   1. GET /stable/income-statement, /cash-flow-statement, /balance-sheet-statement
    |   2. extract_quarterly_trends() -> 78 metrics across 7 categories
    |   3. prepare_metrics_for_cache() -> 20 items (1 per quarter)
    |   4. GET /stable/earnings -> beat/miss data (earnings_events)
    |   5. GET /stable/dividends -> dividend history
    |   6. GET /stable/key-metrics-ttm -> market_valuation (P/E, EV/EBITDA, market_cap)
    |   7. update_item() per quarter -> DynamoDB (preserves existing attributes)
    |
    v
DynamoDB: metrics-history-{env}
    PK: ticker (e.g., "AAPL")
    SK: fiscal_date (e.g., "2025-12-27")
    Categories updated: revenue_profit, cashflow, balance_sheet, debt_leverage,
                        earnings_quality, dilution, valuation,
                        earnings_events, dividend, market_valuation
```

### Relationship to EOD Price Pipeline

The Earnings Update Pipeline works alongside the [EOD Stock Price Pipeline](eventbridge-eod-pipeline.md) but serves a different purpose:

| | EOD Price Pipeline | Earnings Update Pipeline |
|---|---|---|
| **Schedule** | 6:00 PM ET daily | 5:00 PM + 11:30 AM ET daily |
| **What it fetches** | Daily closing prices | Full quarterly financials + earnings + TTM |
| **Tickers per run** | All 498 S&P 500 | Only 5-40 that recently reported |
| **DynamoDB table** | `stock-data-4h-{env}` | `metrics-history-{env}` |
| **FMP endpoints** | `/stable/historical-price-eod/full` | 6 endpoints per ticker (see below) |
| **Purpose** | Powers "Last Close" banner + price charts | Powers all fundamental analysis + earnings beat/miss |

Together they ensure: when a company reports earnings, the financial results appear in the dashboard within hours, and the stock price reaction is captured the following trading day.

---

## Schedule Timing

```
US Market Day Timeline (Eastern Time)
|
|  6:00 AM  Pre-market earnings announced
|  9:30 AM  Market opens
| 11:30 AM  ---- earnings_update (post-open) runs ----
|           Catches pre-market announcements
|  4:00 PM  Market closes
|  4:10 PM  After-hours earnings announced (typical window: 4:10-4:30 PM)
|  5:00 PM  ---- earnings_update (post-close) AND sp500_eod_ingest run ----
|           Catches after-hours announcements + captures closing prices
|           Captures closing prices for all tickers
|
```

All schedules use EventBridge Scheduler with `America/New_York` timezone, so cron times automatically adjust for EDT/EST with no DST drift. The 1-2 hour delays after market events give FMP time to process the SEC filings.

---

## Infrastructure Components

### EventBridge Scheduler Schedules

| Schedule | Cron (ET) | Eastern Time | Purpose |
|----------|-----------|--------------|---------|
| Post-close | `cron(0 17 ? * MON-FRI *)` | 5:00 PM | After-hours earnings |
| Post-open | `cron(30 11 ? * MON-FRI *)` | 11:30 AM | Pre-market earnings |

Both schedules:
- Timezone: `America/New_York` (auto-adjusts for EDT/EST)
- Schedule group: `{project}-{env}-market-data`
- Retry policy: 2 attempts, max event age 1 hour
- Dead letter queue: SQS `{project}-{env}-earnings-update-dlq` with CloudWatch alarm
- Feature flag: `enable_earnings_update_schedule` (per environment)
- Input: `{}` (auto mode)
- IAM: Dedicated scheduler execution role (not Lambda resource-based policy)

**Terraform**: `chat-api/terraform/modules/lambda/eventbridge.tf`

### Lambda Function

| Property | Value |
|----------|-------|
| Name | `{project}-{env}-earnings-update` |
| Handler | `earnings_update.lambda_handler` |
| Runtime | Python 3.11 |
| Timeout | 300 seconds (5 minutes) |
| Memory | 512 MB |

**Source**: `chat-api/backend/src/handlers/earnings_update.py`

**Environment Variables**:
- `FMP_SECRET_NAME` - Secrets Manager key for FMP API credentials
- `METRICS_HISTORY_CACHE_TABLE` - DynamoDB table name for quarterly metrics
- `ENVIRONMENT` - dev/staging/prod
- `LOG_LEVEL` - Logging verbosity
- `SNS_TOPIC_ARN` - SNS topic for email notifications (success/skip/failure summaries)

### FMP API Calls Per Ticker

| Endpoint | Purpose | Calls |
|----------|---------|-------|
| `/stable/earnings-calendar` | Identify who reported (auto mode only) | 1 per run |
| `/stable/income-statement` | Income statement (20 quarters) | 1 |
| `/stable/cash-flow-statement` | Cash flow statement | 1 |
| `/stable/balance-sheet-statement` | Balance sheet | 1 |
| `/stable/earnings` | EPS actual vs estimated, beat/miss | 1 |
| `/stable/dividends` | Dividend history | 1 |
| `/stable/key-metrics-ttm` | TTM valuations (P/E, EV/EBITDA, market_cap) | 1 |

**Total**: 1 calendar call + ~6 calls per ticker. At 20 tickers = ~121 FMP calls per run.

### DynamoDB Write Pattern

The pipeline uses `update_item` (not `put_item`) for all writes. This is critical:

- **`update_item`**: Only modifies specified attributes. Preserves existing data like `market_valuation` that was populated by other pipelines.
- **`put_item`** (old approach): Replaces the entire item, erasing any attributes not in the new write.

Each quarterly item gets up to 10 categories SET individually:

```python
UpdateExpression = "SET #revenue_profit = :rp, #cashflow = :cf, #balance_sheet = :bs,
                        #debt_leverage = :dl, #earnings_quality = :eq, #dilution = :di,
                        #valuation = :val, #earnings_events = :ee, #dividend = :div,
                        #market_valuation = :mv, #cached_at = :ca, #expires_at = :exp"
```

---

## Event Payload Options

### Auto Mode (default — EventBridge sends `{}`)

```json
{}
```

Checks FMP earnings calendar for the last 48 hours, filters to S&P 500, processes recently reported tickers.

### Manual Mode (specific tickers)

```json
{"tickers": ["AAPL", "MSFT", "GOOGL"]}
```

Skips calendar check, processes specified tickers directly. Useful for:
- Testing after deployment
- Re-processing a ticker after a pipeline fix
- Forcing an update outside the normal schedule

### Custom Lookback

```json
{"lookback_days": 7}
```

Check earnings calendar further back than the default 2 days. Useful after a holiday weekend or outage.

---

## Response Structure

The Lambda response is designed to support future notification features:

```json
{
  "mode": "auto",
  "started_at": "2026-04-04T21:00:01.234567",
  "completed_at": "2026-04-04T21:02:15.789012",
  "tickers_checked": 12,
  "tickers_updated": ["AAPL", "MSFT"],
  "total_updated": 2,
  "total_failures": 0,
  "results": [
    {
      "ticker": "AAPL",
      "status": "success",
      "quarters_written": 20,
      "latest_fiscal_date": "2025-12-27",
      "latest_fiscal_quarter": "Q4",
      "earnings_date": "2026-01-29",
      "eps_actual": 2.84,
      "eps_estimated": 2.67,
      "eps_beat": true,
      "eps_surprise_pct": 6.37,
      "has_market_valuation": true
    }
  ],
  "upcoming": [
    {
      "ticker": "STZ",
      "earnings_date": "2026-04-08",
      "eps_estimated": 1.74
    }
  ],
  "failures": []
}
```

### Notification-Ready Fields

The `results` array contains everything needed for user-facing notifications:

| Field | Use Case |
|-------|----------|
| `ticker` | "AAPL just reported earnings" |
| `eps_beat` | "Beat estimates" / "Missed estimates" |
| `eps_surprise_pct` | "Beat by 6.4%" |
| `eps_actual` / `eps_estimated` | "$2.84 vs $2.67 expected" |
| `earnings_date` | "Reported January 29" |

The `upcoming` array enables "Earnings coming up" alerts for tickers users are tracking.

---

## Email Notifications

After every run, the Lambda publishes a summary to the `{project}-{env}-alerts` SNS topic, which delivers an email to the configured alert address. One email per invocation.

| Scenario | Email Subject |
|----------|--------------|
| Success | `[buffett-dev] Earnings Update: 8 updated` |
| Partial failures | `[buffett-dev] Earnings Update: 8 updated, 2 failed` |
| No tickers reported | `[buffett-dev] Earnings Update: No tickers to process` |
| Lambda crash (DLQ) | CloudWatch alarm notification via same SNS topic |

The email body includes mode (auto/manual), tickers checked, tickers updated (by name), and any failures with ticker and error. If the SNS publish itself fails, it is logged as a warning but does not crash the Lambda.

**Defense in depth**: Two layers of DLQ protection are in place:
- **Scheduler-level DLQ** — catches invocation failures (throttling, IAM issues, function not found)
- **Lambda-level DLQ** (`aws_lambda_function_event_invoke_config`) — catches execution failures within the function

Both route to the same SQS queue (`{project}-{env}-earnings-update-dlq`) with a CloudWatch alarm that triggers an email when any message arrives.

---

## Operational Procedures

### Manual Invocation

```bash
# Test with single ticker
aws lambda invoke \
  --function-name buffett-dev-earnings-update \
  --payload '{"tickers": ["AAPL"]}' \
  /dev/stdout

# Check who reported this week
aws lambda invoke \
  --function-name buffett-dev-earnings-update \
  --payload '{"lookback_days": 7}' \
  /dev/stdout

# Process specific tickers (skip calendar)
aws lambda invoke \
  --function-name buffett-dev-earnings-update \
  --payload '{"tickers": ["AAPL", "MSFT", "GOOGL"]}' \
  /dev/stdout
```

### Local Testing

```bash
cd chat-api/backend
PYTHONPATH=src:. python3 -c "
from handlers.earnings_update import lambda_handler
import json
result = lambda_handler({}, None)  # Auto mode
print(json.dumps(result, indent=2, default=str))
"
```

### Monitoring

Check recent invocations:
```bash
aws logs tail /aws/lambda/buffett-dev-earnings-update --since 1d
```

Check EventBridge Scheduler status:
```bash
aws scheduler get-schedule --name buffett-dev-earnings-update-post-close --group-name buffett-dev-market-data
aws scheduler get-schedule --name buffett-dev-earnings-update-post-open --group-name buffett-dev-market-data
```

Check DLQ depth:
```bash
aws sqs get-queue-attributes \
  --queue-url $(aws sqs get-queue-url --queue-name buffett-dev-earnings-update-dlq --query QueueUrl --output text) \
  --attribute-names ApproximateNumberOfMessagesVisible
```

### Disabling the Schedule

Set `enable_earnings_update_schedule = false` in the environment's `main.tf` and apply, or disable directly:
```bash
aws scheduler update-schedule --name buffett-dev-earnings-update-post-close \
  --group-name buffett-dev-market-data --state DISABLED \
  --flexible-time-window '{"Mode":"OFF"}' \
  --schedule-expression 'cron(0 17 ? * MON-FRI *)' \
  --schedule-expression-timezone America/New_York \
  --target "$(aws scheduler get-schedule --name buffett-dev-earnings-update-post-close --group-name buffett-dev-market-data --query 'Target' --output json)"
```

Or via Terraform (recommended): set the flag and `terraform apply`.

---

## Downstream Consumers

### Value Insights Dashboard — All Tabs

Every tab on the Value Insights dashboard reads from `metrics-history`:

| Tab | Categories Used | Updated By This Pipeline |
|-----|----------------|-------------------------|
| Overview | All categories | Yes |
| Growth | `revenue_profit` | Yes |
| Profitability | `revenue_profit`, `valuation` | Yes |
| Valuation | `valuation`, `market_valuation` | Yes (includes fresh TTM) |
| Earnings | `earnings_events` | Yes (beat/miss data) |
| Cash Flow | `cashflow` | Yes |
| Debt | `debt_leverage`, `balance_sheet` | Yes |
| Earnings Quality | `earnings_quality` | Yes |

### Earnings Performance Tab

The Earnings tab specifically depends on:
- `earnings_events.eps_actual` / `eps_estimated` / `eps_beat` / `eps_surprise_pct` — from this pipeline
- Daily closing prices from the [EOD Price Pipeline](eventbridge-eod-pipeline.md) — for post-earnings stock reaction (1-day, 5-day, 30-day returns)

### Market Intelligence Agent

The Bedrock Market Intelligence agent reads from `metrics-history` for sector analytics and company comparisons. Fresh earnings data improves agent responses during earnings season.

---

## Design Decisions

### Why `update_item` Instead of `put_item`

The previous `sp500_pipeline` used `put_item` (full replace) which caused `market_valuation` data loss. The `market_valuation` field is populated from TTM data and historical price calculations — sources that `prepare_metrics_for_cache()` does not produce. Using `put_item` erased this field silently.

`update_item` only modifies the attributes specified in the `UpdateExpression`, preserving anything else on the item. This is safe for:
- New items (creates them with the specified attributes)
- Existing items (updates specified attributes, leaves others untouched)

### Why 2x Daily Instead of Real-Time

FMP processes earnings data from SEC filings, which takes minutes to hours after the company files. Running more frequently than twice daily would:
- Waste FMP API calls checking tickers that haven't reported yet
- Risk hitting the 300 calls/min rate limit during peak earnings season
- Add complexity (polling state, "already processed" tracking)

The 2x daily schedule provides same-day coverage for 99%+ of earnings announcements.

### Why a Single Lambda Instead of Checker + Processor

The original design had two Lambdas: `earnings_calendar_checker` (find who reported) and a processor (update their data). These were merged because:
- The calendar check takes ~2 seconds — not worth a separate Lambda
- Peak load (50 tickers) fits within one Lambda invocation
- Single log stream simplifies debugging
- Manual mode (`{"tickers": [...]}`) needs to skip the checker anyway

---

## Peak Earnings Season Performance

| Metric | Off-Season | Peak Season (Jan/Apr/Jul/Oct) |
|--------|-----------|-------------------------------|
| Tickers per run | 2-5 | 30-50 |
| FMP API calls | ~15-35 | ~180-300 |
| Execution time | ~15 seconds | ~2-3 minutes |
| DynamoDB writes | ~40-100 | ~600-1000 |

All within Lambda timeout (300s) and FMP rate limits (300 calls/min with 0.5s delay).

---

## Improvement Roadmap

### Short-Term

1. **Idempotency between runs** — Track which tickers were processed in the post-close run to avoid re-processing in the post-open run. Currently harmless (update_item is idempotent) but wastes FMP calls.
2. **Market holiday awareness** — Skip runs on US market holidays (same list as EOD pipeline).

### Medium-Term

3. ~~**SNS notifications**~~ — **Done.** Lambda publishes run summaries to SNS alerts topic after every invocation (2026-04). DLQ alarms also wired to SNS.
4. ~~**DLQ + CloudWatch alarm**~~ — **Done.** SQS dead letter queue + CloudWatch alarm added (2026-04). Both scheduler-level and Lambda-level DLQs are in place.
5. **Earnings quality scoring** — Auto-compute an earnings quality score based on beat rate, surprise consistency, and revenue vs EPS alignment.

### Long-Term

6. **Near-instant updates (V2)** — During the 4-6 PM ET window, poll only today's expected reporters every 15 minutes. ~35 FMP calls total instead of polling all 498 tickers.
7. **User watchlist integration** — When a user's tracked company reports, send a push notification with beat/miss summary and post-earnings price reaction.
8. **Earnings transcript analysis** — Feed earnings call transcripts to Bedrock for AI-generated summary alongside the quantitative data.

---

## Cost Estimate (Monthly)

| Resource | Estimate |
|----------|----------|
| Lambda | ~44 invocations x 1-3 min x 512 MB = **$0.03** |
| DynamoDB writes | ~200-1000 update_items/day x 22 days = **$0.02** |
| FMP API calls | ~100-300/day x 22 days = included in FMP plan |
| Secrets Manager | ~44 calls/month = **$0.02** |
| EventBridge | Free tier |
| SNS notifications | ~44 emails/month = **free tier** |
| **Total** | **< $0.10/month** (excluding FMP API plan) |
