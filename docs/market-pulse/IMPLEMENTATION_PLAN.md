# Market Pulse: Architecture Evolution Plan

> **Status:** Draft — Sprint backlog candidate
> **Created:** 2026-04-07
> **Feature:** Daily AI-curated investment research reports (5-10/day)

## Context

Inspired by ProCap Insights, this plan evolves Buffett's investment research system to produce 5-10 high-quality AI-generated reports daily covering the top market events — earnings surprises, breaking news, and emerging trends. The key insight at this scale: **curation happens before generation**, not after. An "Editor Agent" picks the day's best topics, then only those get generated.

---

## Current Architecture Summary

| Layer | What Exists | Key Limitation |
|-------|-------------|----------------|
| **Report Types** | Single-ticker fundamental only (19 sections, v5.2 prompt) | No thematic, earnings recap, or event-reactive reports |
| **Data Sources** | FMP API only (financials, earnings, estimates) | No news feeds |
| **Generation** | Claude Code mode (manual, human-in-the-loop) | Cannot automate daily |
| **Storage** | DynamoDB PK=`ticker`, SK=`section_id` | One report per ticker, no multi-ticker reports |
| **Distribution** | Pull-only (user visits app) | No push delivery |
| **Pipelines** | EOD candles + earnings updates (EventBridge Scheduler) | Detect changes but don't trigger reports |

---

## Core Design: The Daily Editor Agent

Instead of an event bus routing hundreds of events to a generation pipeline, a single **Editor Agent** runs twice daily and makes editorial decisions:

```
Morning run (7:30 AM ET — before market open):
  1. Scan overnight earnings releases (from existing earnings_update data)
  2. Scan top financial news headlines (from news API)
  3. Pick 3-5 best topics for today's reports
  4. Determine report type for each (earnings_recap, thematic, event_reactive)
  5. Trigger generation for each

Evening run (5:30 PM ET — after market close):
  1. Scan after-hours earnings (from existing post-close earnings_update)
  2. Scan day's market-moving events
  3. Pick 2-5 best topics for overnight/next-morning reports
  4. Trigger generation
```

**Why this works at 5-10/day:** The expensive decision is *what to write about*, not *how fast to write it*. A Bedrock Sonnet call with today's earnings + news headlines (~3K tokens in, ~1K out) returns a ranked topic list in seconds. Then you generate only winners.

---

## Phase 1: Report Type System + Storage (Weeks 1-2)

### New DynamoDB Table: `research-reports-v3-{env}`

```
PK: report_id       (ULID — globally unique, time-sortable)
SK: section_id       ("00_executive", "06_growth", etc.)

Attributes:
  report_type:       "single_ticker" | "thematic" | "earnings_recap" | "event_reactive"
  tickers:           ["AAPL"] or ["AAPL","MSFT","GOOGL"]
  title:             "Apple Q2 Earnings: AI Spending Pays Off" 
  status:            "draft" | "published"
  tags:              ["earnings", "tech", "AI"]
  generated_at, ttl (90 days), prompt_version, model

GSIs:
  report-type-index:    PK=report_type, SK=generated_at
  status-date-index:    PK=status, SK=generated_at
```

**Ticker Mapping Table:** `report-ticker-mapping-{env}` (PK=`ticker`, SK=`report_id`) — "all reports mentioning AAPL."

**Migration:** v2 stays active. FastAPI checks v3 first, falls back to v2.

### Report Type Abstraction

New module: `chat-api/backend/investment_research/report_types/`

```python
class BaseReportType(ABC):
    report_type: str
    max_tokens: int
    preferred_model: str  # "sonnet" or "opus"

    @abstractmethod
    def get_section_definitions(self) -> List[SectionDefinition]: ...
    @abstractmethod  
    def prepare_data(self, **kwargs) -> Dict[str, Any]: ...
    @abstractmethod
    def get_prompt_template(self) -> str: ...
```

| Report Type | Use Case | Sections | Tokens |
|-------------|----------|----------|--------|
| `single_ticker` | Deep-dive (existing) | 19 | ~12K |
| `earnings_recap` | Post-earnings analysis | 7 (results, surprise, guidance, comparison, outlook, verdict, triggers) | ~6K |
| `thematic` | Multi-stock trend | 9 (theme + N stocks + comparison + verdict) | ~8K |
| `event_reactive` | Breaking news impact | 5 (what happened, market impact, affected stocks, action items, watch list) | ~4K |

`single_ticker.py` wraps existing `report_generator.py` logic. `section_parser.py` generalized to accept per-type section definitions.

### Files
- New: `chat-api/terraform/modules/dynamodb/research_reports_v3.tf`
- New: `chat-api/backend/investment_research/report_types/{base,single_ticker,earnings_recap,thematic,event_reactive}.py`
- Modify: `chat-api/backend/investment_research/section_parser.py` — parameterize section definitions
- Modify: `chat-api/backend/lambda/investment_research/services/report_service.py` — v3 table support

---

## Phase 2: Data Sources + Editor Agent (Weeks 3-4)

### Data Sources

#### FMP News API (available on current Starter tier — no upgrade needed)

Project confirmed on FMP Starter ($22/mo, 300 calls/min) per rate limit in `sp500_eod_ingest.py:50`.

- **General news:** `GET /stable/news/general-latest?from=2026-04-07&to=2026-04-07&page=0&limit=50`
  - Query params: `from` (date), `to` (date), `page` (number), `limit` (number)
  - Returns: `title`, `text` (snippet/summary), `url`, `publishedDate`, `site`, `symbol`
- **Stock-specific:** `GET /stable/stock-news?tickers=AAPL&limit=20`
- **Search by keyword:** `GET /stable/search-stock-news?query=tariffs&limit=20`

Note: `text` field is a snippet, not full article. Sufficient for editor agent ranking and report context.

#### FRED API v2 (completely free — 120 requests/min, no daily cap)

Free API key registration at fred.stlouisfed.org. Store in Secrets Manager: `buffett-{env}-fred-api-key`

| Indicator | Series ID | Frequency |
|-----------|-----------|-----------|
| GDP | `GDP` | Quarterly |
| CPI | `CPIAUCSL` | Monthly |
| Unemployment | `UNRATE` | Monthly |
| Fed Funds Rate | `FEDFUNDS` | Monthly |
| 10-Year Treasury | `DGS10` | Daily |
| 2-Year Treasury | `DGS2` | Daily |
| Yield Curve (10Y-2Y) | `T10Y2Y` | Daily |
| VIX | `VIXCLS` | Daily |
| Consumer Sentiment | `UMCSENT` | Monthly |
| PCE Price Index | `PCEPI` | Monthly |

Example: `GET https://api.stlouisfed.org/fred/series/observations?series_id=CPIAUCSL&api_key=KEY&file_type=json&sort_order=desc&limit=12`

**Use cases:**
- Editor agent uses latest readings to detect macro shifts (CPI spike, yield curve inversion, VIX surge)
- Macro/thematic reports include FRED data as supporting context
- `event_reactive` reports reference economic indicators when relevant

### News + Economic Data Ingestion

**Lambda: `news_ingest`**
- Schedule: Every 2 hours during market hours (9 AM - 6 PM ET), via EventBridge Scheduler
- Calls FMP `/stable/news/general-latest` with `from`/`to` for current day, `limit=50`
- Stores in `news-headlines-{env}` table:
  - PK: `date` (YYYY-MM-DD), SK: `published_at#source_id`
  - Attributes: `title`, `summary`, `tickers` (list), `source`, `url`
  - TTL: 7 days

**Lambda: `economic_data_ingest`**
- Schedule: Daily at 8 AM ET (before market open, after most FRED releases)
- Fetches latest values for all 10 series above
- Stores in `economic-indicators-{env}` table:
  - PK: `series_id` (e.g., `CPIAUCSL`), SK: `date`
  - Attributes: `value`, `frequency`, `units`
  - TTL: 90 days
- Compares current vs previous reading; flags significant changes (e.g., CPI delta > 0.3pp)

### Editor Agent Lambda

**Lambda: `daily_editor`** — the brain of the system.

```
Input: { "run_type": "morning" | "evening" }

Steps:
  1. Gather context:
     - Query news-headlines table for last 12 hours (FMP general news)
     - Query existing earnings_update data for new earnings releases
     - Query economic-indicators table for any flagged significant changes (FRED)
     - Query research-reports-v3 status-date-index for today's already-published reports (avoid duplicates)
  
  2. Call Bedrock converse() with editor prompt:
     "You are the editorial director of an investment research desk.
      Given today's earnings releases, news headlines, and economic data shifts,
      pick the top 3-5 topics that would be most valuable to retail investors.
      For each, specify: report_type, tickers, title, and a 1-sentence brief.
      Prioritize: earnings surprises >10%, major policy shifts, sector-moving
      events, and significant economic indicator changes."
  
  3. Parse response → list of ReportRequest objects
  
  4. For each ReportRequest:
     - Invoke report_generation Lambda (async)
     - Log to daily-editorial-log-{env} table
  
  5. SNS notification: "Editor selected N topics for generation"
```

**Schedule:**
- Morning: 7:30 AM ET Mon-Fri (after pre-market earnings + overnight news)
- Evening: 5:30 PM ET Mon-Fri (after market close + after-hours earnings)

**Cost:** 2 Bedrock Sonnet calls/day for editorial decisions = ~$0.02/day (negligible)

### Report Generation Lambda

**Lambda: `report_generation`** — generates a single report via Bedrock API.

```
Input: {
  "report_type": "earnings_recap",
  "tickers": ["AAPL"],
  "title": "Apple Q2 Earnings: AI Spending Pays Off",
  "brief": "Apple beat estimates on services revenue..."
}

Steps:
  1. Instantiate ReportType subclass (e.g., EarningsRecap)
  2. Call prepare_data(tickers=["AAPL"], brief=brief)
     - FMP data (reuse existing fmp_client.py)
     - Recent news headlines for ticker (from news-headlines table)
     - Relevant FRED indicators (from economic-indicators table) for macro context
     - Existing report data if refreshing (from v3 table)
  3. Call Bedrock converse() with report type's prompt template + data
     - Model: Sonnet 4 (fast, cost-effective for daily volume)
     - max_tokens: per report type budget
  4. Parse sections via report type's parser
  5. Write to research-reports-v3 with status: "published"
  6. Write ticker mappings to report-ticker-mapping table
  7. Emit SNS notification: "Report published: {title}"
```

**Timeout:** 120 seconds (Bedrock generation + DynamoDB writes)
**Memory:** 512 MB
**Concurrency:** Reserved concurrency = 5 (never more than 5 generating at once)

### Cost at 5-10 Reports/Day
- Earnings recap (~6K tokens out): ~$0.24/report
- Thematic (~8K tokens out): ~$0.32/report  
- Event reactive (~4K tokens out): ~$0.16/report
- **Daily total: ~$1.50-3.00/day = ~$45-90/month**
- Editor agent: ~$0.60/month
- FMP News API: $0 incremental (already on Starter tier)
- FRED API: $0 (free)

### Files
- New: `chat-api/backend/src/handlers/daily_editor.py`
- New: `chat-api/backend/src/handlers/report_generation.py`
- New: `chat-api/backend/src/data_sources/news_source.py` (FMP news client)
- New: `chat-api/backend/src/data_sources/fred_source.py` (FRED API client)
- New: `chat-api/backend/investment_research/prompts/editor_prompt_v1.txt`
- New: `chat-api/backend/investment_research/prompts/{earnings_recap,thematic,event_reactive}_v1.txt`
- New: `chat-api/terraform/modules/dynamodb/news_headlines.tf`
- New: `chat-api/terraform/modules/dynamodb/economic_indicators.tf`
- Modify: `chat-api/terraform/modules/lambda/eventbridge.tf` — add editor + news + FRED schedules
- Reuse: `chat-api/backend/src/utils/fmp_client.py` — unchanged

---

## Phase 3: Serving + Distribution (Weeks 5-6)

### Frontend: Daily Reports Feed

New frontend tab/page: **"Today's Research"** (alongside existing single-ticker reports)

- Query `research-reports-v3` GSI `status-date-index` (PK=`published`, SK desc) for today's reports
- Display as card list: title, report type badge, tickers, generated_at
- Click → same SSE streaming experience (reuse existing streaming infrastructure)
- The FastAPI app at `lambda/investment_research/` gets new endpoints:
  - `GET /reports/daily?date=2026-04-07` → list today's published reports (metadata only)
  - `GET /reports/{report_id}/stream` → stream by report_id (not ticker)
  - `GET /reports/{report_id}/toc` → table of contents

### Email Distribution

**Lambda: `daily_digest`** — runs after evening editor completes (~6:30 PM ET)

```
Steps:
  1. Query all reports published today from v3 table
  2. For each report, pull executive summary section
  3. Render HTML email template:
     - "Today's Research from Buffett" header
     - Card per report: title, type badge, 2-sentence summary, "Read More" link
  4. Query subscribers (users with email_digest_enabled=true)
  5. Send via Resend (reuse existing email_service.py)
```

**Subscriber management:** Add `email_digest_enabled` boolean to existing user record in conversations/auth flow. Simple opt-in toggle on frontend settings page.

No complex preference tables needed at this scale — every subscriber gets the same daily digest with all 5-10 reports.

### Files
- Modify: `chat-api/backend/lambda/investment_research/app.py` — add `/reports/daily`, `/reports/{report_id}/stream`
- Modify: `chat-api/backend/lambda/investment_research/services/report_service.py` — v3 queries by report_id + date
- New: `chat-api/backend/src/handlers/daily_digest.py`
- Reuse: `chat-api/backend/src/utils/email_service.py` — add digest template
- Frontend: New "Today's Research" page/component

---

## Architecture Diagram

```
                         ┌──────────────────────────────────┐
                         │        DATA INGESTION             │
                         │                                    │
  Existing:              │  earnings_update (5PM + 11:30AM)  │
  ───────────────────→   │  sp500_eod_ingest (6PM)           │
                         │                                    │
  New:                   │  news_ingest (every 2h, 9AM-6PM)  │
  ───────────────────→   │  economic_data_ingest (8AM daily)  │
                         └───────────────┬────────────────────┘
                                         │ Data in DynamoDB
                                         ▼
                         ┌──────────────────────────────────┐
                         │       DAILY EDITOR AGENT          │
                         │  (7:30 AM + 5:30 PM ET)           │
                         │                                    │
                         │  Scans: earnings + news + FRED     │
                         │  Picks: top 3-5 topics per run     │
                         │  Output: ReportRequest per topic   │
                         └───────────────┬────────────────────┘
                                         │ Async invoke per topic
                                         ▼
                         ┌──────────────────────────────────┐
                         │      REPORT GENERATION            │
                         │  (per topic, Bedrock Sonnet API)  │
                         │                                    │
                         │  prepare_data() → converse() →     │
                         │  parse_sections() → DynamoDB v3    │
                         └───────────────┬────────────────────┘
                                         │ Published
                                         ▼
                    ┌────────────────────────────────────────────┐
                    │              SERVING + DISTRIBUTION         │
                    │                                              │
                    │  FastAPI SSE ← Frontend "Today's Research"   │
                    │                                              │
                    │  Daily Digest Lambda (6:30 PM ET)            │
                    │  → Resend email to subscribers                │
                    │                                              │
                    │  Follow-up Agent (Bedrock) ← user Q&A        │
                    └──────────────────────────────────────────────┘
```

---

## What Carries Forward vs What's New

### Reuse (existing code, minimal or no changes)
- `fmp_client.py` — financial data for earnings recaps + thematic
- `email_service.py` — Resend integration for digest emails  
- `section_parser.py` — generalized, not rewritten
- `report_generator.py` — becomes `single_ticker` report type
- FastAPI streaming infrastructure — add v3 endpoints alongside v2
- EventBridge Scheduler patterns — add new schedules
- `earnings_update.py` — existing data feeds the editor agent
- Follow-up agent + tool_executor — extend for v3 report queries
- DLQ + SNS notification patterns

### Build New
| Component | Purpose | Effort |
|-----------|---------|--------|
| `research-reports-v3` table | Report-id-keyed multi-type storage | Small (Terraform) |
| `report_types/` module | 4 report type classes | Medium |
| 3 new prompt templates | Earnings recap, thematic, event reactive | Medium |
| `news_source.py` + `news_ingest` Lambda | FMP news ingestion | Small |
| `fred_source.py` + `economic_data_ingest` Lambda | FRED economic data ingestion | Small |
| `economic-indicators` + `news-headlines` tables | New data storage | Small (Terraform) |
| `daily_editor.py` Lambda | Editorial AI picks top topics | Medium |
| `report_generation.py` Lambda | Automated Bedrock generation | Medium |
| `daily_digest.py` Lambda | Email distribution | Small |
| "Today's Research" frontend page | Daily report feed UI | Medium |

---

## Monthly Cost Estimate

| Component | Cost |
|-----------|------|
| Bedrock generation (7 reports/day avg, Sonnet) | ~$60/month |
| Bedrock editor agent (2 calls/day, Sonnet) | ~$1/month |
| FMP News API | $0 (included in Starter tier) |
| FRED API | $0 (free) |
| DynamoDB (incremental, on-demand) | ~$5/month |
| Lambda compute (minimal at this volume) | ~$2/month |
| Resend emails (~100 subscribers) | Free tier |
| **Total incremental** | **~$68/month** |

---

## Implementation Sequence

| Week | Deliverable |
|------|-------------|
| 1 | v3 DynamoDB table + ticker mapping (Terraform) |
| 1 | `report_types/` module: `base.py` + `single_ticker.py` (wrap existing) |
| 2 | `earnings_recap.py` + `thematic.py` + `event_reactive.py` report types |
| 2 | New prompt templates for each report type |
| 3 | `news_source.py` + `news_ingest` Lambda + `news-headlines` table (FMP) |
| 3 | `fred_source.py` + `economic_data_ingest` Lambda + `economic-indicators` table (FRED) |
| 3 | `daily_editor.py` Lambda + editor prompt |
| 4 | `report_generation.py` Lambda (Bedrock converse) |
| 4 | E2E test: editor picks topic → generation → saved to v3 |
| 5 | FastAPI v3 endpoints (`/reports/daily`, `/reports/{id}/stream`) |
| 5 | Frontend "Today's Research" page |
| 6 | `daily_digest.py` Lambda + email template |
| 6 | Full pipeline E2E: ingest → edit → generate → serve → email |

---

## Key Decisions / Open Questions

1. **Editor agent model**: Sonnet 4 recommended — fast, cheap, good at structured ranking tasks. Could use Haiku if editorial decisions prove simple enough.
2. **Should event-reactive reports be truly real-time?** At 5-10/day scale, the twice-daily editor cadence handles most events within hours. True minute-latency reaction would need an EventBridge event bus — worth deferring unless demand emerges.
3. **Subscription gating**: Start with all reports visible to all users. Add tier gating later if the feature drives upgrades.
4. **FRED API key management**: Store in Secrets Manager (`buffett-{env}-fred-api-key`) following existing pattern for FMP key.
