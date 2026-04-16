# Market Intelligence — Changelog

All notable changes to the Market Intelligence feature are documented here.

---

## [Unreleased]

### Force-Refresh FMP Cache on Earnings Day (2026-04-16)

**Fixed**
- `earnings_update` Lambda was ingesting stale financial statements for just-reported tickers because `utils/fmp_client.get_financial_data()` served cached FMP data (90-day TTL) instead of fetching the newly-available 10-Q numbers
- Tonight's confirmation: NFLX/PLD/SCHW all got `[FMP_DEBUG] CACHE HIT` from a cache entry written 2026-02-07 — 68 days stale — so no Q1 2026 row landed in `metrics-history-dev` despite FMP's `/income-statement`, `/balance-sheet-statement`, and `/cash-flow-statement` endpoints already having the Q1 2026 data

**Added**
- `force_refresh: bool = False` kwarg on `utils.fmp_client.get_financial_data()` — when `True`, the DynamoDB cache read is skipped and FMP is fetched fresh. Fresh response is still written to cache for subsequent readers
- `earnings_update._process_ticker` now passes `force_refresh=True` unconditionally — every ticker processed by the Lambda bypasses the stale cache
- Propagation-lag guard: after the fresh FMP fetch, if `raw_financials.income_statement[0].date` is more than 10 days older than `earnings_date`, `_process_ticker` returns early with `status='fmp_propagation_lag'` rather than writing the stale snapshot back to cache (preserves correctness if FMP's inter-endpoint lag means calendar data is ahead of statement data)
- New response field `propagation_lag: [ticker, ...]` surfaces lagged tickers in the Lambda response + SNS summary for operator visibility
- 4 regression tests in `tests/unit/test_earnings_update.py::TestForceRefreshAndPropagationLag`:
  - `test_process_ticker_passes_force_refresh_true`
  - `test_propagation_lag_returns_early_with_lag_status`
  - `test_no_lag_guard_when_earnings_date_none`
  - `test_handler_surfaces_propagation_lag_in_response`
- 1 new test file `tests/unit/test_fmp_client.py::test_force_refresh_skips_cache` verifies: cache read skipped, fresh FMP call made, cache still written after fetch

**Design decisions**
- **`force_refresh` default is `False`** — preserves zero-behavior-change for `action_group_handler.get_financial_analysis` (user-facing Bedrock expert agents — latency-critical), `report_generator.prepare_data` (local Claude Code mode), and `sp500_pipeline` (batch ingestion). Verified all call sites use positional args only, cannot accidentally trigger
- **Kwarg in `fmp_client.py`** (not handler-side cache bust) — keeps cache-key construction (`v3:{ticker}:{fiscal_year}`) encapsulated in one place. Protects against `CACHE_VERSION` drift silently breaking a handler-side hardcode
- **Propagation-lag guard over aggressive retries** — rather than polling FMP or rolling back cache writes, we defer to the next scheduled run (earnings_update fires twice daily). Worst case: one Lambda cycle delay
- **No Terraform or IAM change** — existing Lambda role already has `DeleteItem` on `buffett-dev-*` tables via wildcard (not currently used by this change, but ready for future follow-up)

**Backfill**
- Pre-deploy stale cache entries for NFLX/PLD/SCHW (cached 2026-02-07) explicitly deleted before re-invoking `earnings_update` in manual mode
- Post-backfill verification: `metrics-history-dev` rows with `fiscal_date='2026-03-31'` present for all three tickers with all 7 categorized buckets populated

**Files modified**
- `chat-api/backend/src/utils/fmp_client.py` (+18 / -9 lines across `get_financial_data`)
- `chat-api/backend/src/handlers/earnings_update.py` (+36 / -3 lines: signature change, propagation-lag guard, response surfacing)
- `chat-api/backend/tests/unit/test_earnings_update.py` (+121 lines, 4 new tests, 0 weakened assertions)
- `chat-api/backend/tests/unit/test_fmp_client.py` (NEW, 45 lines)

**Verification**
- 22/22 targeted unit tests pass (17 pre-existing + 4 new + 1 new fmp_client)
- 421/421 broader unit subtree passes (no regressions in other `get_financial_data` callers)
- 5/5 FMP integration tests pass (live FMP + DynamoDB)
- All 13 Lambda zips rebuild cleanly (`utils/fmp_client.py` is copied into every function package)
- Manual-mode `{"tickers":[...]}` invocation for NFLX/PLD/SCHW produces fresh Q1 2026 rows in `metrics-history-dev`

**Future-feature enablement**
- This fix is the data-pipeline prerequisite for the planned "AI-generated earnings summary + user push notifications on earnings day" feature. That feature will read directly from `metrics-history-dev` on earnings day to produce plain-English summaries and flag anomalous signals (margin expansion, FCF inflection, leverage changes, capex spikes)

### After-Hours Earnings Reporter Fix (2026-04-16)

**Fixed**
- Afternoon EventBridge run of `earnings_update` Lambda was silently skipping after-hours reporters (NFLX, PLD, SCHW on 2026-04-16) and writing stale prior-cycle values into `buffett-dev-sp500-aggregates` (EARNINGS_RECENT rows)
- Root cause: `_already_updated_since_earnings` compared epoch `cached_at > local-midnight(earnings_date)`, which was already "after" the earnings date during the 13:30 UTC morning run. The only guard (`eps_actual is not None`) passed because the prior cycle's actual was still on the latest metrics-history row
- Side-effect: `_ensure_feed_record` then copied the prior-cycle eps values into an aggregate row keyed under today's `earnings_date`, surfacing stale numbers on the Earnings Tracker dashboard

**Changed**
- Freshness check now gates on FMP's own `epsActual` field (authoritative "quarter has been reported" signal) — no more `cached_at` epoch math
- `_already_updated_since_earnings(ticker, earnings_date, fmp_eps_actual)` skips only when all three hold: (1) FMP has eps_actual populated, (2) stored `earnings_events.earnings_date[:10]` matches the announced cycle, (3) stored `eps_actual` is not None
- Three-way skip loop in `lambda_handler`: `fmp_eps_actual is None` → `skipped_awaiting_fmp` (no feed-record write); cycle already captured → `skipped_fresh` (safe to ensure feed record); else → process
- `_ensure_feed_record` hardened with an `earnings_date[:10]` equality guard that WARN-logs and refuses to write a stale aggregate row when the latest metrics-history row belongs to a prior cycle

**Added**
- `skipped_awaiting_fmp` list in Lambda response JSON alongside `skipped_already_processed`
- 6 regression tests in `tests/unit/test_earnings_update.py`:
  - `TestAlreadyUpdatedSinceEarnings` (4 tests): happy path, FMP `epsActual=None` defer, stored-date mismatch process, time-suffix normalization
  - `TestEnsureFeedRecord` (2 tests): refuse on date mismatch, write on date match

**Backfill**
- NFLX, PLD, SCHW re-processed via manual-mode invocation `{"tickers":["NFLX","PLD","SCHW"]}` post-deploy to correct the stale `EARNINGS_RECENT#2026-04-16#<ticker>` aggregate rows

**Files modified**
- `chat-api/backend/src/handlers/earnings_update.py` (+42 / -26 lines across 5 functions)
- `chat-api/backend/tests/unit/test_earnings_update.py` (+128 / -3 lines, 1 test signature updated for 3-arg `side_effect`, 2 new test classes)

**Verification**
- 17/17 unit tests in `test_earnings_update.py` pass
- 416/416 unit subtree tests pass (no regressions)
- `build/earnings_update.zip` packages cleanly
- Manual-mode bypass preserved — manual invocation cannot reach either freshness check or feed-record guard

### getHistoricalValuation Market Intel Tool (2026-04-10)

**Added**
- New inline Bedrock tool `getHistoricalValuation` in market intelligence chatbot — answers "is this stock cheap vs its own history?" in a single call
- 9 frontend-parity valuation metrics with per-metric statistics (min/max/mean/median/percentile/z-score):
  - Lower-is-cheaper: `pe_ratio`, `pb_ratio`, `ev_to_ebitda`, `price_to_fcf`
  - Higher-is-cheaper: `earnings_yield`, `fcf_yield`, `roic`, `roe`, `roa`
- `VALUATION_METRIC_META` constant in [market_intel_tools.py](../../chat-api/backend/src/utils/market_intel_tools.py) with `label`, `plain_english`, `source`, `direction` per metric — retail-friendly translation lives inside tool responses, not the system prompt
- `_compute_metric_stats` helper — pure function computing statistics, polarity-aware assessment (cheap/fair/expensive), and retail-friendly verdict strings using direction-specific phrasing ("Cheaper than X%" for multiples, "Higher than X% (good for the investor)" for yields/returns)
- `_derive_pb_ratio` helper — computes P/B from `market_valuation.market_cap / balance_sheet.total_equity` (not stored directly in metrics-history)
- Sector-relative context in responses: sector name, company count, sector medians from `buffett-dev-sp500-aggregates`
- System prompt: one line added to market intel supervisor's tool bullet list (zero translation instructions — all plain-English carried in tool response to keep baseline inference cheap)
- 7 unit tests in `TestGetHistoricalValuation` covering happy path, polarity inversion, sparse history, missing ticker, pb_ratio derivation with `total_equity=0` edge case, and price_to_fcf derivation
- Executive + technical overview doc: [docs/market-intelligence/historical-valuation-tool.md](./historical-valuation-tool.md)

**Design decisions**
- **S&P 500 only.** No FMP fallback — entirely served from `metrics-history-{env}` and `sp500-aggregates` DynamoDB tables (zero FMP quota consumed per call)
- **price_to_fcf derivation.** Derived as `100 / fcf_yield` rather than stored, since `fcf_yield` is already in the historical backfill while `price_to_fcf` only exists on the latest quarter
- **`ev_to_sales` and `ev_to_fcf` intentionally dropped** — not shown on frontend Valuation tab, and not computed historically by `sp500_backfill.compute_quarterly_valuations`
- **Quarters clamped to [1, 20]** — prevents `quarters=0` Python slice quirk and negative values
- **Graceful sparse-history handling** — if `market_valuation` hasn't been backfilled for a ticker, `pe_ratio`/`ev_to_ebitda`/yields return `assessment: "insufficient_history"` with a clear verdict instead of erroring out. `roic`/`roe`/`roa` are always historically available since they're per-quarter features.

**Token cost**
- Tool spec adds ~337 tokens to baseline inference (paid on every chat turn)
- Tool response avg ~1,260 tokens (paid only when tool is actually called)
- Per-query cost at Claude Haiku 4.5 pricing: ~$0.0016

**Files modified**
- `chat-api/backend/src/utils/market_intel_tools.py` (+240 lines: constant, 2 helpers, handler, dispatcher entry)
- `chat-api/backend/src/handlers/market_intel_chat.py` (toolSpec + 1-line system prompt bullet)
- `chat-api/backend/src/utils/unified_tool_executor.py` (`MARKET_INTEL_TOOL_NAMES` set entry)
- `chat-api/backend/tests/unit/test_market_intel_tools.py` (new `TestGetHistoricalValuation` class)

**Verification**
- 410 Python unit tests pass (includes 27 in `test_market_intel_tools.py`, 7 new)
- Terraform validate: PASS
- Lambda build: PASS (all 20+ zips rebuilt)
- Sample queries against real dev DynamoDB confirmed for AAPL, MSFT, NVDA

### EOD Ingest Date Fix + Schedule Change (2026-04-09)

**Fixed**
- EOD ingest Lambda was using yesterday's date (computed in UTC) instead of today's date in Eastern time
- Since the schedule runs after market close, today's closing prices are already available
- Now uses `zoneinfo.ZoneInfo("America/New_York")` to compute the correct trading day

**Changed**
- Moved EOD ingest schedule from 6 PM ET to 5 PM ET (`cron(0 17 ? * MON-FRI *)`)

### Dynamic Market Holiday Calendar (2026-04-06)

**Fixed**
- Replaced hardcoded `US_MARKET_HOLIDAYS_MMDD` set with dynamic `_us_market_holidays(year)` computation
- Good Friday 2026 (Apr 3) was missed because calendar was stuck on 2025 dates (`04-18`)
- All 10 NYSE holidays now computed algorithmically: floating holidays via nth-weekday, Good Friday via Anonymous Gregorian Easter algorithm
- Fixed-date holidays (New Year's, Juneteenth, July 4th, Christmas) include Saturday→Friday / Sunday→Monday observed-date shifts
- Results cached per year for warm Lambda performance

### EventBridge Scheduler Migration + Pipeline Notifications (2026-04-05)

**Changed**
- Migrated all 3 EventBridge schedules from `aws_cloudwatch_event_rule` (fixed UTC) to `aws_scheduler_schedule` with `America/New_York` timezone — eliminates DST drift
- EOD ingest: `cron(0 18 ? * MON-FRI *)` at 6 PM ET (was 10 PM UTC)
- Earnings post-close: `cron(0 17 ? * MON-FRI *)` at 5 PM ET (was 9 PM UTC)
- Earnings post-open: `cron(30 11 ? * MON-FRI *)` at 11:30 AM ET (was 4:30 PM UTC)

**Added**
- `aws_scheduler_schedule_group` for market data pipelines (`{project}-{env}-market-data`)
- Dedicated IAM execution role for EventBridge Scheduler (`scheduler.amazonaws.com`)
- Earnings update DLQ: SQS queue + CloudWatch alarm (mirrors EOD ingest pattern)
- SNS email notifications on pipeline success, skip, and failure for both Lambdas
- DLQ CloudWatch alarms wired to SNS alerts topic for crash notifications
- `sns:Publish` IAM permission for Lambda execution role
- Enabled monitoring module in CI/CD pipeline (`enable_monitoring=true`)
- `ALERT_EMAIL` GitHub secret for SNS subscription

**Removed**
- Legacy `aws_cloudwatch_event_rule`, `aws_cloudwatch_event_target`, `aws_lambda_permission` resources

### S&P 500 Daily EOD Price Pipeline (2026-04-03)

**Added**
- `sp500_eod_ingest` Lambda: fetches 4-hour OHLCV candles for all S&P 500 tickers from FMP
- EventBridge schedule: `cron(0 22 ? * MON-FRI *)` — runs daily at 10 PM UTC (6 PM ET)
- DynamoDB table `stock-data-4h-{env}` with DateIndex GSI for cross-ticker queries
- `backfill_4h_prices.py` script for local/ad-hoc historical data loading
- `value_insights_handler` extended with `latest_price` from 4h table
- ValuationPanel: "Last Close" banner with live P/E computed from current price + TTM earnings
- Weekend + US market holiday detection to skip unnecessary API calls
- 365-day TTL (`expires_at`) on ingested records
- Ticker format conversion (`BRK.B` → `BRK-B`) for FMP API compatibility
- Executive documentation: `docs/infrastructure/eventbridge-eod-pipeline.md`
- `reserved_concurrent_executions = 1` to prevent duplicate parallel Lambda runs
- SQS dead letter queue + CloudWatch alarm on DLQ depth for failure alerting
- Lambda Powertools: structured JSON logs (`Logger`) + custom CloudWatch metrics (`Metrics`)
- `aws-lambda-powertools` added to shared dependencies layer
- 58 tests (42 unit + 16 integration) covering full pipeline
- `sp500_eod_ingest` upgraded to fetch daily EOD from `/stable/historical-price-eod/full` (close, change, changePercent, vwap)
- Daily records stored with `DAILY#` SK prefix for clean separation from 4h candle data
- `backfill_eod_prices.py` script for bulk daily EOD historical loading
- `backfill_q4_earnings.py` script for targeted earnings updates via FMP `/stable/earnings` API
- `_get_latest_price()` now queries `DAILY#` prefix for accurate daily close + change %

**Fixed**
- `feature_extractor._align_earnings_to_quarters`: upcoming earnings (no epsActual) no longer claim quarter slots over already-reported earnings
- 609 S&P 500 quarters updated with Q4 2025 reported earnings (beat/miss data)
- FMP rate limit delay increased to 0.5s (safe for 300 calls/min Starter tier)
- `sp500_pipeline._batch_write_items` replaced with `_update_items` using `update_item` instead of `put_item` — preserves existing attributes (especially `market_valuation`) on each pipeline run
- New `fetch_ttm_valuations()` in `fmp_client.py` — fetches `/stable/key-metrics-ttm` and attaches fresh P/E, EV/EBITDA, market_cap to the latest quarter

### Earnings Performance Tab (2026-04-03)

**Added**
- New "Earnings" tab on Value Insights dashboard between Valuation and Cash Flow
- Latest Earnings card: beat/miss badge, EPS + revenue surprise %
- Post-Earnings Price Reaction: 1-day, 5-day, 30-day % change after announcement
- Earnings History table: 12-16 quarters of beats/misses with price performance columns
- EPS Surprise Trend sparkline chart over time
- Track Record sidebar: beat rate, avg surprise %, avg 1-day post-earnings move
- Next Earnings countdown with consensus EPS estimate
- Backend: `_fetch_daily_prices_from_fmp()` fetches 5yr daily prices, `_compute_post_earnings()` calculates price reactions around each earnings date
- 63 tests (42 unit + 21 integration) all passing

### Automated Earnings Update Pipeline (2026-04-04)

**Added**
- `earnings_update` Lambda: checks FMP earnings calendar for recently reported S&P 500 companies, fetches full financials + earnings + dividends + TTM valuations, writes via `update_item`
- EventBridge 2x daily schedule: 9 PM UTC (6 PM ET) post-close + 4:30 PM UTC (11:30 AM ET) post-open
- Auto mode (checks calendar) + manual mode (`{"tickers": ["AAPL"]}`) for on-demand processing
- Structured response for future notifications: `tickers_updated`, `eps_beat`, `eps_surprise_pct`, `upcoming` earnings
- `fetch_ttm_valuations()` in `fmp_client.py` — `/stable/key-metrics-ttm` for live P/E, EV/EBITDA, market_cap
- 12 new unit tests for earnings_update handler

**Removed**
- `sp500_pipeline` Lambda (bulk 498 tickers) — moved to local-only script for ad-hoc full refreshes
- `sp500_backfill` Lambda — already local
- `earnings_calendar_checker` Lambda — functionality merged into `earnings_update`

**Fixed**
- `sp500_pipeline._batch_write_items` replaced with `_update_items` using `update_item` — preserves `market_valuation` on all pipeline runs
- 95 tests passing (12 earnings_update + 43 eod_ingest + 21 pipeline + 21 value_insights)

### Staging Environment + Stripe Subscription Fix (2026-03-24)

**Added**
- Staging Terraform brought to full parity with dev environment
- Stripe + Email (Resend) modules added to staging
- All API Gateway routes enabled (analysis, research, market intelligence, subscriptions)
- Market Intelligence Lambda Function URL output for staging CI/CD
- `VITE_MARKET_INTEL_URL` added to staging frontend build
- CloudFront URL added to CORS allowed origins for Lambda Function URLs
- DynamoDB data copied from dev to staging (10,025 metrics + 27 aggregates)

**Fixed**
- Stripe subscription webhook: `user_id` now passed in `subscription_data.metadata` so `customer.subscription.created` webhook can activate Plus tier automatically
- AWS provider upgraded from ~> 5.0 to ~> 6.25 in staging
- Bedrock agent output references fixed (`agent_id` → `followup_agent_id`)
- Removed stale Docker Lambda references (analysis_followup migrated to zip)
- Restored missing `waitlistApi.js` (deleted in prior commit, broke frontend build)
- Cleaned up 14 orphaned Terraform state resources

**Removed**
- Deprecated WebSocket, SQS, chat_processor references from staging
- Landing page CloudFront module and CI/CD jobs
- `followup-action` and `analysis-followup` from Docker build matrix (not Docker Lambdas)

---

### Token Enforcement + Response Save Fix (2026-03-23)

**Fixed**
- Added `check_limit()` gate to `market_intel_chat.py` — blocks requests when monthly token limit exceeded
- Fixed `record_usage` race condition: new billing period records now look up user tier from users table, preventing Plus users from getting Free-tier limits when request arrives before Stripe webhook
- Fixed `DEFAULT_LIMITS` to match Stripe webhook values: `free=100,000`, `plus=2,000,000` (was `free=0`, `plus=1,000,000`)
- Fixed `DEFAULT_TOKEN_LIMIT` fallback from 50K to 100K
- Fixed empty assistant messages in DynamoDB for multi-turn queries — now captures text from all converse turns, not just the final `end_turn`

**Modified Files**
- `market_intel_chat.py` — token limit gate + text capture from all turns
- `token_usage_tracker.py` — `_get_user_tier_limit()` method, updated constants
- `test_token_usage_tracker.py` — updated assertions for new limits

---

### Valuation Multiples + Historical P/E Tracking (2026-03-22)

**Added**
- TTM valuation data: P/E, EV/EBITDA, EV/Sales, EV/FCF, market cap, enterprise value for 490 tickers
- Historical annual valuations: 5-6 years of P/E, EV/EBITDA per ticker mapped to quarterly items
- `fetch_sp500_valuations.py` — FMP TTM key-metrics fetcher
- `fetch_sp500_historical_valuations.py` — FMP annual key-metrics fetcher (5+ years)
- 9 new metrics in METRIC_MAP: pe_ratio, ev_to_ebitda, ev_to_sales, ev_to_fcf, price_to_fcf, market_cap, enterprise_value, earnings_yield, fcf_yield
- Valuation metrics in sector aggregates (median P/E, EV/EBITDA per sector)
- Pre-computed rankings for cheapest P/E and EV/EBITDA
- `sort` parameter on getTopCompanies (asc/desc) for "cheapest by P/E" queries

**Bug Fixes**
- Fixed `__init__.py` to handle missing `anthropic` module (try/except import)
- Fixed JWT auth to use Secrets Manager (`JWT_SECRET_ARN`) instead of env var
- Fixed Lambda to use non-streaming response (Python 3.11 generator limitation)
- Fixed CORS to allow localhost:8000
- Fixed frontend to parse double-encoded Lambda Function URL response
- Fixed aggregator `ProjectionExpression` to include `market_valuation`
- Fixed `compareCompanies` and `getCompanyProfile` to include `market_valuation` category
- Updated tests for non-streaming handler path

**Queries Now Supported**
- "What is NVDA's P/E ratio?" — returns 35.0x with sector context
- "Top 10 cheapest stocks by P/E" — ascending sort, pre-computed ranking
- "Compare tech vs healthcare valuations" — sector median P/E and EV/EBITDA
- "NVDA P/E over 5 years — discount?" — historical trend with 6 annual data points
- "Is AAPL trading at a premium to its historical EV/EBITDA?" — historical comparison

---

### Phase 4: API Gateway + Plus Subscription Gating (2026-03-22)

**Added**
- Plus subscription check in `market_intel_chat.py` — queries DynamoDB users table for `subscription_tier`
- API Gateway REST API route: `POST /market-intel/chat` with HTTP_PROXY → Lambda Function URL (SSE streaming)
- CORS OPTIONS preflight for `/market-intel/chat`
- CUSTOM JWT authorizer (reuses existing `analysis_jwt`)
- 10 unit tests for subscription gating + handler routing

**Architecture**
- Market Intelligence is included in the **Plus tier** — no new Stripe product/price needed
- Auth flow: JWT validates identity → DynamoDB checks `subscription_tier == 'plus'` → allow/deny
- Free users get 403 "Plus subscription required for Market Intelligence"
- JWT `subscription_tier` is NOT trusted (may be stale) — DynamoDB is authoritative source

**Key Decision: No Stripe Changes**
- Original Phase 4 planned a separate $10/mo subscription
- Changed to: Market Intelligence included in existing Plus tier
- Eliminated: new Stripe product, webhook handler changes, subscription_handler changes

**Modified Files**
- `market_intel_chat.py` — added `_get_subscription_tier()` + DynamoDB users table lookup
- `analysis_streaming.tf` — added `/market-intel/chat` resources (POST + OPTIONS + integration)
- `api-gateway/variables.tf` — added `enable_market_intelligence_api` + `market_intelligence_function_url`
- `environments/dev/main.tf` — wired function URL + enabled market intelligence API

---

### Performance Optimization: Pre-computed Rankings + Scan Cache (2026-03-21)

**Added**
- In-memory TTL cache (5 min) for `_get_latest_per_ticker()` — multi-tool queries scan DynamoDB once instead of N times
- Pre-computed RANKING items in sp500-aggregates (12 metrics × top 50 companies each)
- `_read_ranking()` helper for sub-second ranking reads
- `getTopCompanies` and `getEarningsSurprises` try pre-computed rankings first, fall back to scan

**Performance Results**
| Query Type | Before | After | Improvement |
|------------|--------|-------|-------------|
| getTopCompanies (no sector filter) | 23s | 0.32s | 72x faster |
| getEarningsSurprises | 23s | 0.09s | 256x faster |
| screenStocks (cache hit) | 23s | 0.00s | instant |
| Multi-tool query (6 tools) | ~114s scan time | ~18s (1 scan + 5 cache) | 6x faster |

**Modified Files**
- `market_intel_tools.py` — added cache + ranking reads
- `sp500_aggregator.py` — added `_compute_rankings()` with 12 key metrics
- `sp500-aggregates` DynamoDB — 12 new RANKING items (24 total items in table)

---

### Phase 3: Bedrock Converse API Agent (2026-03-21)

**Added**
- `market_intel_chat.py` — Lambda handler using `converse_stream` with 9 inline tools, SSE streaming, JWT auth, token counting
- `market_intel_tools.py` — Tool executor with 9 tools querying metrics-history + sp500-aggregates
- Tools: `screenStocks`, `getSectorOverview`, `getTopCompanies`, `getIndexSnapshot`, `getCompanyProfile`, `compareCompanies`, `getMetricTrend`, `getEarningsSurprises`, `compareSectors`
- Terraform: Lambda function (120s/512MB) + Function URL with RESPONSE_STREAM
- 20 unit tests for tool executor
- Evaluation: 10 queries against Claude Haiku 4.5 — avg 6,944 tokens/query, $0.0073/query, $10/mo covers ~1,371 queries

**Architecture Decision**
- Uses Bedrock Converse API (`converse_stream`) with inline `toolSpec` definitions — NOT Bedrock Agents (`invoke_agent`)
- Matches `analysis_followup.py` architecture for SSE streaming + token counting
- Model: `us.anthropic.claude-haiku-4-5-20251001-v1:0`

---

### Phase 2: Aggregate Analytics (2026-03-21)

**Added**
- `sp500_aggregator.py` — Lambda that computes sector + index-level aggregates from metrics-history
- `market_intelligence_tables.tf` — DynamoDB table `sp500-aggregates` (PK: aggregate_type, SK: aggregate_key)
- 12 items: 11 sector aggregates + 1 index overview
- Per-sector: medians for 14 metrics, top 5 by revenue/FCF/growth, earnings surprise %, dividend coverage
- Index-level: sector weights, top-10 concentration (25.8%), overall earnings/dividend stats
- Optional trigger from `sp500_pipeline.py` via `{"run_aggregator": true}`
- 15 unit tests for aggregator

**Terraform Reorg**
- Moved `forex_rate_cache`, `metrics_history_cache`, `sp500_aggregates` from `ml_tables.tf` to `market_intelligence_tables.tf`

---

### Phase 1: Data Pipeline (2026-03-21)

**Added**
- `index_tickers.py` — Full 498-ticker S&P 500 list with `SP500_SECTORS` mapping (11 sectors, industry, company name)
- `sp500_pipeline.py` — Lambda for sequential ticker processing via FMP API (900s timeout, skip_fresh support)
- `sp500_backfill.py` — One-time local JSON backfill script (zero API calls)
- `earnings_calendar_checker.py` — Placeholder Lambda for FMP earnings calendar scheduling
- `fetch_sp500_earnings.py` — Script to fetch earnings surprise data from FMP API
- Terraform: 4 new Lambdas (pipeline, backfill, earnings checker, aggregator)
- 19 unit tests for pipeline + backfill + earnings checker

**Data Populated**
- 10,025 items in `metrics-history-dev` (498 tickers × ~20 quarters)
- 79 metrics per quarter across 9 categories: revenue_profit, cashflow, balance_sheet, debt_leverage, earnings_quality, dilution, valuation, earnings_events, dividend
- 343 tickers with dividend data (69%), 488 with earnings events (97%)

**Earnings Data**
- Fetched via FMP `/stable/earnings` endpoint for all 498 tickers
- 498 local JSON files in `sp500_analysis/data/company_earnings/`
- Includes: eps_actual, eps_estimated, eps_surprise_pct, eps_beat, revenue_actual, revenue_estimated
