# BuffettGPT MVP Implementation Guide

**Last Updated:** February 11, 2026

---

## MVP Overview

BuffettGPT is a Warren Buffett-themed AI financial advisor with investment research reports, follow-up Q&A, and a subscription model. The MVP targets launch with:

1. **Core Product** — AI chat + investment research reports (v5.1 prompt)
2. **Monetization** — Stripe subscription (Free / Plus tiers) with token-based usage limits
3. **Growth** — Waitlist landing page with referral system + content marketing blog
4. **Content** — Batch-generated investment reports for S&P 500 and Nasdaq

---

## Workstream Status

### 1. Core Chat API & Infrastructure
**Status: COMPLETE**

| Component | Status | Notes |
|-----------|--------|-------|
| Lambda functions (7 handlers) | Done | auth, chat, conversations, subscription, webhook, analysis, search |
| API Gateway (HTTP) | Done | All routes configured with CORS |
| DynamoDB tables (6+) | Done | Messages, conversations, users, rate limits, usage, sessions |
| Bedrock integration | Done | Claude Haiku + Knowledge Bases + Guardrails |
| Google OAuth | Done | JWT-based auth flow |
| CloudFront + S3 static site | Done | CDN for React frontend |
| CI/CD (3 pipelines) | Done | dev (auto), staging (auto), prod (manual approval) |

### 2. Stripe Subscription & Token Limiting
**Status: COMPLETE**

| Component | Status | Notes |
|-----------|--------|-------|
| Stripe product + pricing | Done | Free / Plus tiers |
| `subscription_handler.py` | Done | Manage subscriptions via API |
| `stripe_webhook_handler.py` | Done | Process Stripe events (checkout, invoice, cancellation) |
| Token usage tracking | Done | DynamoDB `token-usage-dev-buffett` table, anniversary-based billing periods |
| Rate limiting by tier | Done | Anonymous: 5/mo, Free: 500/mo, Plus: higher limits |
| Secrets Manager integration | Done | `stripe-secret-key-{env}`, `stripe-webhook-secret-{env}`, etc. |
| **Testing** | **Done** | Unit tests, E2E tests, integration tests, security tests on API endpoints |

### 3. Investment Research Reports
**Status: COMPLETE (generation pipeline), IN PROGRESS (batch execution)**

| Component | Status | Notes |
|-----------|--------|-------|
| `ReportGenerator` class | Done | 2,163 lines, Claude Code mode (no API key needed) |
| Prompt v5.1 (latest) | Done | Revenue stickiness, margin waterfall, operating leverage, decision triggers |
| Metrics caching to DynamoDB | Done | 7 categories x N quarters → `metrics-history-dev` |
| Follow-up Agent (Bedrock) | Done | Q&A using cached metrics + report context |
| Section parser + DynamoDB V2 | Done | 12 items per report (executive + 11 sections) |
| Multi-currency support | Done | USD, EUR, etc. |
| **Batch generation scripts** | **Done (code)** | CLI, parallel tmux/Terminal runners, verify, stale check |
| **Batch execution (S&P 500 + Nasdaq)** | **NOT STARTED** | Need to run for full coverage — see Workstream 6 |

### 4. Waitlist Landing Page & Referral System
**Status: COMPLETE (code), IN PROGRESS (testing & security)**

| Component | Status | Notes |
|-----------|--------|-------|
| **Backend** | | |
| `waitlist_handler.py` | Done | 414 lines — signup, status, referral tracking |
| Rate limiting (5/IP/hr) | Done | TTL-based cleanup |
| Disposable email blocking | Done | 15 domains blocked |
| Self-referral prevention | Done | |
| `BUFF-XXXX` referral codes | Done | Branded, alphanumeric |
| 3-tier reward system | Done | 1 ref → Early Access, 3 → 1mo Free Plus, 10 → 3mo Free Plus |
| DynamoDB waitlist table | Done | KMS encrypted, GSI on referral_code, TTL enabled |
| **Infrastructure** | | |
| Terraform (table, Lambda, API GW) | Done | Feature-flagged: `enable_waitlist_routes = true` in dev |
| Build script updated | Done | `waitlist_handler` in build list |
| **Frontend** | | |
| `WaitlistPage.jsx` | Done | 617 lines — signup form + dashboard + sample report preview |
| `TierProgress.jsx` | Done | Animated progress bar with milestone markers |
| `waitlistApi.js` | Done | signup() + getStatus() API client |
| App.jsx integration | Done | Lazy-loaded, feature-flagged via `VITE_ENABLE_WAITLIST` |
| Social sharing (X, LinkedIn) | Done | Pre-filled share messages |
| localStorage persistence | Done | Returning visitors see dashboard |
| **Documentation** | | |
| `docs/referral/executive-summary.md` | Done | Architecture, data model, deployment checklist |
| `buffett_elevator_pitch.md` | Done | Messaging framework for marketing |
| **Remaining Work** | | |
| Referral system E2E testing | Not Started | Signup → referral credit → status → sharing flow |
| Security patching (referral) | Not Started | Abuse vectors, rate limit edge cases |
| Backend unit tests | Not Started | `test_waitlist_handler.py` with moto |
| `FRONTEND_URL` env var | Not Done | Defaults to `localhost:3000`, needs CloudFront URL |
| `VITE_ENABLE_WAITLIST=true` | Not Set | Must add to frontend build env |

### 5. Content Marketing — S&P 500 Blog Post
**Status: IN PROGRESS (writing)**

| Component | Status | Notes |
|-----------|--------|-------|
| FMP data pipeline | Done | `fetch_sp500_data.py` — 498 companies, 20 quarters, 59 MB |
| DataFrame transform | Done | `build_dataset.py` — 4 Parquet files, derived Silverblatt columns |
| `SP500_SILVERBLATT_REPORT.md` | Done | 6-section market analysis (buybacks, dividends, earnings, etc.) |
| `REPORT_REFINEMENTS.md` | Done | Advance/decline breadth, 4% Rule watchlist, Dividend Aristocrats |
| **Medium / LinkedIn blog post** | **In Progress** | Writing based on completed analysis |

### 6. Batch Report Generation (S&P 500 + Nasdaq)
**Status: NOT STARTED (scripts ready, execution pending)**

| Component | Status | Notes |
|-----------|--------|-------|
| `prepare_batch_data.py` | Done | Pre-fetches FMP data, saves JSON, caches metrics |
| `batch_cli.py` | Done | Unified CLI: prepare, parallel, verify, stale, status |
| `run_parallel_reports.sh` | Done | 5 parallel tmux sessions |
| `run_simulation.sh` | Done | Test with 1-2 tickers before scaling |
| `open_parallel_terminals.sh` | Done | macOS Terminal.app alternative |
| `check_stale_reports.py` | Done | Detect reports needing refresh (new earnings) |
| `verify_reports.py` | Done | Confirm reports exist in DynamoDB |
| Test suite | Done | 4 test files covering all batch components |
| **Default prompt version** | **Needs Update** | Scripts default to v4.8, should be **v5.1** |
| **S&P 500 batch execution** | **Not Started** | ~500 tickers → dev + prod DynamoDB |
| **Nasdaq batch execution** | **Not Started** | Need ticker list + execution |
| **Prod deployment** | **Not Started** | Reports must be uploaded to production tables too |

**Batch execution workflow:**
```
1. Update default prompt version to 5.1 in all scripts
2. prepare_batch_data.py → fetch FMP data for all tickers
3. run_parallel_reports.sh → 5 tmux sessions generate reports
4. verify_reports.py → confirm all reports saved
5. Repeat for prod environment (--env prod)
```

---

## Deployment Checklist

### Pre-Launch (Must Have)

- [x] Stripe subscription integration (Free / Plus tiers)
- [x] Token usage tracking and enforcement
- [x] Unit, E2E, integration, and security tests for subscription/webhook
- [x] Waitlist Lambda + DynamoDB + API Gateway deployed to dev
- [x] Waitlist frontend components complete
- [x] Referral system (signup, codes, tier rewards, sharing)
- [x] S&P 500 market analysis data pipeline complete
- [ ] **Referral system E2E testing** — full flow smoke test
- [ ] **Referral security patching** — abuse prevention, edge cases
- [ ] **Backend unit tests for waitlist** — `test_waitlist_handler.py`
- [ ] **Set `FRONTEND_URL` env var** — update from localhost to CloudFront URL
- [ ] **Set `VITE_ENABLE_WAITLIST=true`** — activate landing page in build
- [ ] **Update batch scripts to v5.1** — default prompt version in 4 files
- [ ] **Run batch generation for S&P 500** — dev + prod
- [ ] **Run batch generation for Nasdaq** — dev + prod

### Pre-Launch (Should Have)

- [ ] Post-deploy smoke test script (curl-based)
- [ ] Staging environment wiring for waitlist
- [ ] Production environment wiring for waitlist
- [ ] Medium blog post published (S&P 500 analysis)
- [ ] LinkedIn blog post published

### Post-Launch (Nice to Have)

- [ ] Email notifications via SES (waitlist signup confirmation, tier upgrades)
- [ ] Admin dashboard (view signups, referral leaderboard)
- [ ] Analytics events (conversion tracking)
- [ ] Stale report auto-detection and refresh pipeline

---

## Architecture Summary

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
| **Handlers** | `chat-api/backend/src/handlers/*.py` (7 Lambdas) |
| **Report Gen** | `chat-api/backend/investment_research/report_generator.py` |
| **Batch Gen** | `chat-api/backend/investment_research/batch_generation/batch_cli.py` |
| **Batch Scripts** | `batch_generation/run_parallel_reports.sh`, `run_simulation.sh` |
| **Prompts** | `investment_research/prompts/investment_report_prompt_v5_1.txt` |
| **Waitlist** | `frontend/src/components/waitlist/WaitlistPage.jsx` |
| **Referral Docs** | `docs/referral/executive-summary.md` |
| **S&P 500 Blog** | `sp500_analysis/SP500_SILVERBLATT_REPORT.md` |
| **Terraform** | `chat-api/terraform/environments/dev/main.tf` |
| **CI/CD** | `.github/workflows/deploy-{dev,staging,prod}.yml` |

---

## Batch Report Generation — Execution Plan

### Current State
- All batch generation scripts are **code-complete and tested**
- Default prompt version in scripts is **v4.8** (needs update to **v5.1**)
- Currently only DJIA 30 tickers are hardcoded in scripts
- Need to expand to full **S&P 500** (~500 tickers) and **Nasdaq** (~100+ tickers)
- Reports must be uploaded to both **dev** and **prod** DynamoDB tables

### Execution Steps

1. **Update defaults** — Change prompt version from 4.8 → 5.1 in:
   - `batch_cli.py` (line 175)
   - `run_parallel_reports.sh` (line 33)
   - `run_simulation.sh` (line 26)
   - `open_parallel_terminals.sh` (line 34)

2. **Prepare ticker lists** — Create/update ticker lists for S&P 500 and Nasdaq batches

3. **Run simulation** — Test with 2-3 tickers to validate v5.1 flow end-to-end:
   ```bash
   ./run_simulation.sh --prompt-version 5.1 --tickers AAPL,MSFT
   ```

4. **Batch prepare** — Pre-fetch FMP data + cache metrics for all tickers:
   ```bash
   python -m investment_research.batch_generation.batch_cli prepare --prompt-version 5.1
   ```

5. **Batch generate** — Run parallel tmux sessions:
   ```bash
   ./run_parallel_reports.sh --prompt-version 5.1
   ```

6. **Verify** — Confirm all reports saved:
   ```bash
   python -m investment_research.batch_generation.batch_cli verify
   ```

7. **Deploy to prod** — Re-run verify and any missing reports against prod:
   ```bash
   python -m investment_research.batch_generation.batch_cli verify --env prod
   ```

---

## Content Marketing — Blog Publication Plan

### S&P 500 Silverblatt-Style Analysis

**Data complete.** 498 companies, 20 quarters, 59 MB raw data transformed into analysis-ready Parquet files.

**Report sections written:**
- Monthly Market Attributes (index returns, P/E, sector weights)
- Buyback & Tax Analysis ($1T/year buybacks, Top 20 Rule, SBC dilution)
- Share Count Reduction (4% Rule, top reducers/diluters)
- Operating vs GAAP Earnings (margin trends, quality gap)
- Dividend Dynamics (payout ratios, yield compression)
- Legacy Statistics (5-year returns: +76.3% cumulative, 12.0% annualized)

**Publication targets:**
- [ ] Medium blog post (in progress)
- [ ] LinkedIn article (in progress)
- [ ] Cross-promote with BuffettGPT waitlist link + referral codes
