# Market Intelligence — Changelog

All notable changes to the Market Intelligence feature are documented here.

---

## [Unreleased]

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
- 58 tests (42 unit + 16 integration) covering full pipeline

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
