# BuffettGPT MVP Launch Implementation Guide

**Last Updated:** February 11, 2026

This document tracks what's been built, what's remaining, and the execution plan for launching the BuffettGPT MVP.

---

## Table of Contents

1. [Completed Work](#1-completed-work)
2. [Waitlist & Referral System — Remaining Work](#2-waitlist--referral-system--remaining-work)
3. [Batch Report Generation — S&P 500 & Nasdaq](#3-batch-report-generation--sp-500--nasdaq)
4. [Content Marketing — S&P 500 Blog Post](#4-content-marketing--sp-500-blog-post)
5. [Pre-Launch Checklist](#5-pre-launch-checklist)
6. [Post-Launch Roadmap](#6-post-launch-roadmap)

---

## 1. Completed Work

### 1.1 Stripe Payment Integration
**Status: COMPLETE** (unit, E2E, integration, and security tests passing)

| Component | File | Notes |
|-----------|------|-------|
| Subscription handler | `chat-api/backend/src/handlers/subscription_handler.py` | Manages Free / Plus tiers |
| Webhook handler | `chat-api/backend/src/handlers/stripe_webhook_handler.py` | checkout.session.completed, invoice events, cancellation |
| Secrets Manager | `stripe-secret-key-{env}`, `stripe-webhook-secret-{env}`, `stripe-plus-price-id-{env}` | Separate secrets per key |
| Terraform wiring | Lambda, API Gateway routes, IAM policies | All deployed to dev |

### 1.2 Token Usage & Limiting
**Status: COMPLETE** (tested)

| Component | File | Notes |
|-----------|------|-------|
| Token usage tracker | `chat-api/backend/src/utils/token_usage_tracker.py` | Anniversary-based billing periods (YYYY-MM-DD SK) |
| DynamoDB table | `token-usage-dev-buffett` | PK: `user_id`, SK: `billing_period` |
| Rate limiting | Built into chat flow | Anonymous: 5/mo, Authenticated: 500/mo, Plus: higher |
| Monthly reset | Automatic | New billing period = new DynamoDB item, zero usage |

### 1.3 Core Chat API & Infrastructure
**Status: COMPLETE**

- 7 Lambda handlers deployed (auth, chat, conversations, subscription, webhook, analysis, search)
- API Gateway (HTTP) with CORS
- DynamoDB tables: messages, conversations, users, rate-limits, usage, sessions, investment-reports-v2, metrics-history
- Amazon Bedrock (Claude Haiku) + Knowledge Bases + Guardrails
- Google OAuth + JWT auth
- CloudFront + S3 static site
- CI/CD: dev (auto), staging (auto), prod (manual approval)

### 1.4 Investment Research Reports
**Status: COMPLETE** (pipeline ready, batch execution pending)

- `ReportGenerator` class (2,163 lines) — Claude Code mode, no API key needed
- Prompt v5.1 (latest): revenue stickiness, margin waterfall, operating leverage, decision triggers
- Metrics caching: 7 categories x N quarters → `metrics-history-dev`
- Follow-up Agent (Bedrock): Q&A using cached metrics
- Section parser + DynamoDB V2: 12 items per report (1 executive + 11 sections)

### 1.5 Waitlist Landing Page & Referral System
**Status: COMPLETE (code), IN PROGRESS (testing & security)**

- **Backend:** `waitlist_handler.py` (414 lines) — signup, status, referral tracking, rate limiting, disposable email blocking
- **Infrastructure:** DynamoDB waitlist table (KMS, GSI, TTL), Lambda, API Gateway (feature-flagged)
- **Frontend:** `WaitlistPage.jsx` (617 lines) + `TierProgress.jsx` — signup form, dashboard, sample report preview, social sharing
- **Referral tiers:** 1 ref → Early Access, 3 → 1mo Free Plus, 10 → 3mo Free Plus

---

## 2. Waitlist & Referral System — Remaining Work

**Priority:** High
**What's left:** Testing, security hardening, and environment configuration.

### 2.1 Referral System E2E Testing

**Goal:** Verify the full flow works end-to-end in the deployed dev environment.

**Test scenarios:**
1. Fresh signup (no referral) → receives `BUFF-XXXX` code, position in queue
2. Signup with referral code → referrer's `referral_count` increments atomically
3. Duplicate email → 409 with existing code recovery
4. Rate limiting → 6th signup from same IP within 1 hour → 429
5. Disposable email → signup with `tempmail.com` → 400 rejection
6. Self-referral → signup with own referral code → referral not counted
7. Status check → correct position, referral count, tier display
8. Social sharing → referral link generates correct `?ref=CODE` URL

**Files to test against:**
- `chat-api/backend/src/handlers/waitlist_handler.py`
- `frontend/src/components/waitlist/WaitlistPage.jsx`
- `frontend/src/api/waitlistApi.js`

### 2.2 Security Patching

**Known areas to audit:**
- Rate limit bypass via header spoofing (X-Forwarded-For manipulation)
- Referral code enumeration (brute-force `BUFF-XXXX` space is small — 36^4 = 1.7M combinations)
- Email normalization (gmail dot trick: `j.doe@gmail.com` vs `jdoe@gmail.com`)
- Queue position scan performance under load (currently O(N), acceptable <50K)

### 2.3 Backend Unit Tests

**File to create:** `chat-api/backend/tests/test_waitlist_handler.py`

Test coverage needed:
- Signup happy path (mock DynamoDB with moto)
- Referral code generation uniqueness
- Referral credit atomic increment
- Rate limit enforcement
- Disposable email blocking
- Self-referral prevention
- Status endpoint with various states

### 2.4 Environment Configuration

| Task | Current Value | Required Value |
|------|--------------|----------------|
| `FRONTEND_URL` in waitlist handler | `http://localhost:3000` | CloudFront distribution URL |
| `VITE_ENABLE_WAITLIST` in frontend build | Not set (defaults false) | `true` |
| Staging env waitlist wiring | Not configured | Mirror dev config |
| Prod env waitlist wiring | Not configured | Mirror dev config |

---

## 3. Batch Report Generation — S&P 500 & Nasdaq

**Priority:** High
**What's left:** Update defaults, expand ticker lists, execute batch runs, deploy to prod.

### 3.1 Current State

All batch generation scripts are **code-complete and tested**:

| Script | Purpose |
|--------|---------|
| `batch_cli.py` | Unified CLI: prepare, parallel, verify, stale, status |
| `prepare_batch_data.py` | Pre-fetch FMP data, save JSON, cache metrics |
| `run_parallel_reports.sh` | 5 parallel tmux sessions for automated generation |
| `run_simulation.sh` | Test run with 1-2 tickers |
| `open_parallel_terminals.sh` | macOS Terminal.app alternative |
| `check_stale_reports.py` | Detect reports needing refresh |
| `verify_reports.py` | Confirm reports exist in DynamoDB |

**Location:** `chat-api/backend/investment_research/batch_generation/`

### 3.2 Ticker Lists

**File:** `chat-api/backend/investment_research/index_tickers.py`

| Index | Current State | Target |
|-------|--------------|--------|
| DJIA | 30 tickers (complete) | 30 — ready |
| S&P 500 | 10 tickers (testing subset) | ~500 — needs full constituent list |
| Nasdaq 100 | Not defined | ~100 — needs ticker list added |

**Action required:** Expand `SP500_TICKERS` to the full S&P 500 constituent list and add `NASDAQ100_TICKERS`. The S&P 500 constituent list already exists in `sp500_analysis/config.py` (498 symbols) — reuse or import it.

### 3.3 Default Prompt Version Update

Scripts currently default to **v4.8**. Must update to **v5.1** (latest):

| File | Line | Current | Target |
|------|------|---------|--------|
| `batch_cli.py` | ~175 | `default='4.8'` | `default='5.1'` |
| `run_parallel_reports.sh` | ~33 | `PROMPT_VERSION="4.8"` | `PROMPT_VERSION="5.1"` |
| `run_simulation.sh` | ~26 | `PROMPT_VERSION="4.8"` | `PROMPT_VERSION="5.1"` |
| `open_parallel_terminals.sh` | ~34 | `PROMPT_VERSION="4.8"` | `PROMPT_VERSION="5.1"` |

### 3.4 Execution Plan

**Step 1: Update defaults + ticker lists**
- Update prompt version defaults to 5.1
- Import full S&P 500 list from `sp500_analysis/config.py` into `index_tickers.py`
- Add Nasdaq 100 ticker list

**Step 2: Simulation run**
```bash
cd chat-api/backend
./investment_research/batch_generation/run_simulation.sh --prompt-version 5.1 --tickers AAPL,MSFT,NFLX
```

**Step 3: Batch prepare (FMP data fetch + metrics cache)**
```bash
python -m investment_research.batch_generation.batch_cli prepare --prompt-version 5.1
```
- ~7-8 FMP API calls per ticker
- S&P 500: ~3,500 calls, ~12 min at 300 calls/min rate limit
- Also populates `metrics-history-dev` as a side effect

**Step 4: Batch generate (parallel Claude sessions)**
```bash
./investment_research/batch_generation/run_parallel_reports.sh --prompt-version 5.1
```
- 5 tmux sessions, each handling a batch of tickers
- Each ticker: load prepared data → Claude generates report → save to DynamoDB

**Step 5: Verify**
```bash
python -m investment_research.batch_generation.batch_cli verify
python -m investment_research.batch_generation.batch_cli verify --env prod
```

**Step 6: Deploy to production**
- Re-run prepare + generate against prod DynamoDB tables
- Or implement a dev→prod data copy script

### 3.5 Scale Considerations

| Index | Tickers | FMP Calls | Est. Prepare Time | Est. Generate Time |
|-------|---------|-----------|--------------------|--------------------|
| DJIA | 30 | ~240 | ~1 min | ~2-3 hrs (5 parallel) |
| S&P 500 | ~500 | ~3,500 | ~12 min | ~30-50 hrs (5 parallel) |
| Nasdaq 100 | ~100 | ~700 | ~3 min | ~6-10 hrs (5 parallel) |

For S&P 500 at scale, consider increasing parallelism (10+ sessions) or batching over multiple days.

---

## 4. Content Marketing — S&P 500 Blog Post

**Priority:** Medium
**Status:** In progress (analysis complete, writing blog)

### 4.1 Completed

- FMP data pipeline: `sp500_analysis/fetch_sp500_data.py` — 498 companies, 20 quarters, 59 MB
- DataFrame transform: `sp500_analysis/build_dataset.py` — 4 Parquet files
- Analysis report: `sp500_analysis/SP500_SILVERBLATT_REPORT.md` — 6 Silverblatt sections
- Refinements: `sp500_analysis/REPORT_REFINEMENTS.md` — breadth, 4% Rule, Dividend Aristocrats
- Elevator pitch: `buffett_elevator_pitch.md` — messaging framework

### 4.2 Remaining

- [ ] Write Medium blog post from analysis
- [ ] Write LinkedIn article (can be shorter version of Medium post)
- [ ] Include BuffettGPT waitlist link + referral codes in posts
- [ ] Add charts/visualizations from Parquet data for blog

---

## 5. Pre-Launch Checklist

### Must Have

- [x] Stripe subscription integration (Free / Plus tiers)
- [x] Token usage tracking and enforcement
- [x] Unit, E2E, integration, and security tests for subscription/webhook
- [x] Waitlist handler + DynamoDB + API Gateway deployed to dev
- [x] Waitlist frontend (signup, dashboard, referral, social sharing)
- [x] Investment research report pipeline (v5.1 prompt)
- [x] S&P 500 market analysis data pipeline
- [ ] **Waitlist E2E testing** — full referral flow smoke test
- [ ] **Waitlist security patching** — abuse vectors, rate limit edge cases
- [ ] **Waitlist backend unit tests** — `test_waitlist_handler.py`
- [ ] **Set `FRONTEND_URL`** — update from `localhost:3000` to CloudFront URL
- [ ] **Set `VITE_ENABLE_WAITLIST=true`** — activate landing page
- [ ] **Update batch scripts to v5.1** — 4 files need default version bump
- [ ] **Expand ticker lists** — full S&P 500 + Nasdaq 100 in `index_tickers.py`
- [ ] **Run batch generation (S&P 500)** — dev + prod DynamoDB
- [ ] **Run batch generation (Nasdaq 100)** — dev + prod DynamoDB

### Should Have

- [ ] Post-deploy smoke test script (curl-based)
- [ ] Staging/prod environment wiring for waitlist
- [ ] Medium blog post published
- [ ] LinkedIn article published

### Nice to Have

- [ ] Email notifications via SES (waitlist confirmation, tier upgrades)
- [ ] Admin dashboard (signups, referral leaderboard)
- [ ] Analytics events (conversion tracking)
- [ ] Stale report auto-detection and refresh pipeline
- [ ] Dev → prod report data copy script (avoid regenerating)

---

## 6. Post-Launch Roadmap

### 6.1 Financial Metrics Comparison Tool

**Priority:** Medium | **Complexity:** Medium

Add a tool to the Bedrock follow-up agent that lets users compare metrics across multiple companies. Leverages cached data in `metrics-history-{env}`.

**Key files:**
- `chat-api/backend/src/handlers/analysis_followup.py` — add tool definition to `FOLLOWUP_TOOLS`
- New utility function to query metrics for multiple tickers and format comparison

### 6.2 UI Collapsible Orchestrator Responses

**Priority:** Medium | **Complexity:** Medium

Enhance the analysis view to show collapsible agent responses. Foundation exists (`ResearchContext.jsx` has `collapsedFollowUpIds`, `SectionCard.jsx` has collapse).

**Key files:**
- `frontend/src/contexts/ResearchContext.jsx` — add orchestrator collapse state
- New component: `CollapsibleAgentResponse.jsx`

### 6.3 Lambda Concurrency Tuning

**Priority:** Low (pre-production)

- `analysis_followup`: increase reserved concurrency for prod traffic
- `chat_processor`: deprecated, keep concurrency low or remove

### 6.4 Deprecate Chat Processor Lambda

**Priority:** Low

The `chat_processor` Lambda (RAG chatbot architecture) has been superseded by `analysis_followup` (orchestrator pattern). Safe to remove once all traffic is migrated.

**Steps:** Remove from Lambda module → remove SQS mapping → remove from build script → archive source.

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │     CloudFront + S3 (React)      │
                    │  Landing Page / Waitlist / App    │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │     API Gateway (HTTP API)       │
                    │  /chat  /auth  /conversations    │
                    │  /subscription  /stripe/webhook  │
                    │  /waitlist/signup  /status        │
                    └──────────────┬──────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
     ┌────────▼────────┐ ┌────────▼────────┐ ┌─────────▼─────────┐
     │  Auth Lambdas   │ │  Chat Lambdas   │ │ Billing Lambdas   │
     │  (OAuth, JWT)   │ │  (Bedrock, KB)  │ │ (Stripe, Tokens)  │
     └────────┬────────┘ └────────┬────────┘ └─────────┬─────────┘
              │                    │                     │
     ┌────────▼────────┐ ┌────────▼────────┐ ┌─────────▼─────────┐
     │  Waitlist       │ │  Follow-up      │ │  Report Gen       │
     │  Lambda         │ │  Agent          │ │  (Batch CLI)      │
     └────────┬────────┘ └────────┬────────┘ └─────────┬─────────┘
              │                    │                     │
              └────────────────────┼─────────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │          DynamoDB Tables          │
                    │  messages | conversations | users │
                    │  rate-limits | token-usage        │
                    │  investment-reports-v2 | metrics  │
                    │  waitlist                         │
                    └──────────────────────────────────┘
```

---

## Key File Reference

| Area | Key Files |
|------|-----------|
| **Lambda Handlers** | `chat-api/backend/src/handlers/*.py` (7+1 waitlist) |
| **Report Generator** | `chat-api/backend/investment_research/report_generator.py` |
| **Batch Generation** | `chat-api/backend/investment_research/batch_generation/batch_cli.py` |
| **Batch Scripts** | `batch_generation/run_parallel_reports.sh`, `run_simulation.sh` |
| **Ticker Lists** | `chat-api/backend/investment_research/index_tickers.py` |
| **S&P 500 Constituents** | `sp500_analysis/config.py` (498 symbols) |
| **Prompts** | `investment_research/prompts/investment_report_prompt_v5_1.txt` |
| **Waitlist Frontend** | `frontend/src/components/waitlist/WaitlistPage.jsx` |
| **Waitlist API** | `frontend/src/api/waitlistApi.js` |
| **Referral Docs** | `docs/referral/executive-summary.md` |
| **S&P 500 Blog** | `sp500_analysis/SP500_SILVERBLATT_REPORT.md` |
| **Elevator Pitch** | `buffett_elevator_pitch.md` |
| **Terraform (dev)** | `chat-api/terraform/environments/dev/main.tf` |
| **CI/CD** | `.github/workflows/deploy-{dev,staging,prod}.yml` |
