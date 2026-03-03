# Batch Generation

Generate investment reports for all 30 DJIA companies using parallel Claude Code sessions.

## Overview

This system enables efficient batch generation of investment reports by:

- Pre-fetching all financial data from FMP API
- **Automated parallel launch**: Opens 5 Terminal windows with a single command
- Each session handles 6 companies independently in parallel
- Total time reduced from ~75 minutes (sequential) to ~15 minutes (parallel)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Batch Generation Workflow                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐  │
│   │  FMP API     │    │  prepare_batch   │    │ djia_30_batch    │  │
│   │ (11 endpoints│───▶│  _data.py        │───▶│ _data.json       │  │
│   │  × 30 tickers)    │                  │    │                  │  │
│   └──────────────┘    └──────────────────┘    └────────┬─────────┘  │
│                                                         │            │
│                                                         ▼            │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │   open_parallel_terminals.sh (5 Terminal windows in parallel)│   │
│   │                                                              │   │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│   │
│   │  │Terminal1│ │Terminal2│ │Terminal3│ │Terminal4│ │Terminal5││   │
│   │  │ 6 tickers│ │ 6 tickers│ │ 6 tickers│ │ 6 tickers│ │ 6 tickers││   │
│   │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘│   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                              │                                       │
│                              ▼                                       │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │           DynamoDB v2 Table + Metrics History Cache          │   │
│   │    (16 report sections × 30 tickers + 9 metric categories)   │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Step 1: Prepare Financial Data

Fetch all FMP data for the 30 DJIA companies:

```bash
cd chat-api/backend
python -m investment_research.batch_generation.batch_cli prepare
```

This will:

- Call 11 FMP API endpoints for each of 30 tickers (~330 API calls)
- Includes earnings history, earnings calendar, and dividend data (new in v5.2)
- Cache 9 metric categories per ticker to `metrics-history-dev` (including `earnings_events` and `dividend`)
- Save data to `djia_30_batch_data.json`
- Takes approximately 5-7 minutes

### Step 2: Launch Parallel Claude Sessions

**Option A: Automated Terminal Windows (Recommended for macOS)**

```bash
cd chat-api/backend/investment_research/batch_generation
./open_parallel_terminals.sh
```

This automatically:

- Opens 5 visible Terminal.app windows using AppleScript
- Each window is titled with its batch assignment
- Claude CLI is started in each window, ready for prompts

**Batch Assignments:**

| Window | Companies |
|--------|-----------|
| 1 | AAPL, AMGN, AXP, BA, CAT, CRM |
| 2 | CSCO, CVX, DIS, DOW, GS, HD |
| 3 | HON, IBM, INTC, JNJ, JPM, KO |
| 4 | MCD, MMM, MRK, MSFT, NKE, PG |
| 5 | TRV, UNH, V, VZ, WBA, WMT |

### Step 3: Start Report Generation

**Option A: Fully Automated (Recommended)**

Run each batch as a `claude -p` command in a separate terminal. Reports generate sequentially within each terminal, and all 5 terminals run in parallel.

**Template:**

```bash
claude -p "Generate investment reports for: {TICKERS}

You are running in FULLY AUTOMATED mode. Execute every step without waiting for confirmation.

CRITICAL: Do NOT spawn sub-agents or use the Task tool. Generate each report SEQUENTIALLY in this session. Do NOT parallelize.

Instructions:
1. Read the pre-fetched data from chat-api/backend/investment_research/data/djia_30_batch_data.json
2. For each ticker in ({TICKERS}), one at a time sequentially:
   a. Extract its metrics_context from the JSON
   b. Read the system prompt from chat-api/backend/investment_research/prompts/investment_report_prompt_v5_2.txt
   c. Generate a complete investment report following the prompt structure exactly, using the metrics_context as the financial data input
   d. Write the report to /tmp/{TICKER}_report.md
   e. Save to DynamoDB by running:
      cd chat-api/backend && python3 -m investment_research.batch_generation.batch_save_report --ticker {TICKER} --data-file chat-api/backend/investment_research/data/djia_30_batch_data.json --report /tmp/{TICKER}_report.md --prompt-version 5.2
   f. Print 'TICKER saved successfully'
3. Only move to the next ticker after the current one is fully saved

IMPORTANT:
- Do NOT use the Task tool or spawn sub-agents
- Do NOT parallelize — generate reports one at a time
- Replace {TICKER} with the actual ticker symbol in each command
- If a report fails, log the error and continue with the next ticker
- When all reports are saved, print: 'BATCH COMPLETE: {TICKERS}'" --allowedTools 'Read,Write,Edit,Glob,Grep,Bash(python3 *),Bash(cd *)' --max-turns 40 --thinking disabled
```

**Copy-paste commands for each terminal:**

| Terminal | Replace `{TICKERS}` with |
|----------|--------------------------|
| 1 | `AAPL, AMGN, AXP, BA, CAT, CRM` |
| 2 | `CSCO, CVX, DIS, DOW, GS, HD` |
| 3 | `HON, IBM, INTC, JNJ, JPM, KO` |
| 4 | `MCD, MMM, MRK, MSFT, NKE, PG` |
| 5 | `TRV, UNH, V, VZ, WBA, WMT` |

**Key flags explained:**

| Flag | Purpose |
|------|---------|
| `--allowedTools` | Pre-approves file reads and python commands so saves run without manual approval |
| `--max-turns 40` | Enough turns for 6 reports (read data + generate + save per ticker) |
| `--thinking disabled` | Reduces generation time from ~6 min to ~3-4 min per report with minimal quality impact |

**Option B: Interactive**

Open 5 terminal windows and paste the prompt text (without the `claude -p` wrapper and flags) into each Claude Code session. You'll need to manually approve each bash command.

### Step 4: Verify Completion

```bash
python -m investment_research.batch_generation.batch_cli verify
```

## CLI Reference

```bash
cd chat-api/backend

# Prepare FMP data
python -m investment_research.batch_generation.batch_cli prepare [options]
  --output FILE       Output JSON file (default: djia_30_batch_data.json)
  --tickers LIST      Comma-separated tickers (default: all 30 DJIA)

# Launch parallel sessions
python -m investment_research.batch_generation.batch_cli parallel [options]
  --dry-run           Print commands without executing

# Verify reports exist
python -m investment_research.batch_generation.batch_cli verify [options]
  --env ENV           Environment: dev or prod (default: dev)

# Check for stale reports
python -m investment_research.batch_generation.batch_cli stale [options]
  --tickers-only      Output only ticker symbols (for piping)
```

## FMP API Endpoints Used

| Endpoint | Data Returned |
|----------|---------------|
| `/stable/balance-sheet-statement` | 20 quarters of balance sheet |
| `/stable/income-statement` | 20 quarters of income statement |
| `/stable/cash-flow-statement` | 20 quarters of cash flow |
| `/stable/key-metrics` | 5 years of P/E, P/B, EV/EBITDA |
| `/stable/key-metrics-ttm` | TTM valuation metrics |
| `/stable/ratios-ttm` | TTM profitability ratios |
| `/stable/analyst-estimates` | Forward EPS/revenue estimates |
| `/stable/earnings` | 12 quarters of EPS beat/miss history |
| `/stable/earnings-calendar` | Next upcoming earnings date |
| `/stable/dividends` | 40 periods of dividend payment history |

**Total API calls**: ~11 per ticker × 30 tickers = ~330 calls

> **Note**: The 3 new endpoints (earnings, earnings-calendar, dividends) feed the `earnings_events` and `dividend` metric categories in the metrics history cache, enabling the follow-up agent to answer questions about EPS beat/miss streaks and dividend consistency.

## Verification

### Check All Reports Exist

```bash
python -m investment_research.batch_generation.batch_cli verify
```

Output:
```
Checking 30 DJIA tickers in investment-reports-v2-dev...
------------------------------------------------------------
  ✓ AAPL: 2,234 words, generated 2026-01-27
  ✓ AMGN: 2,156 words, generated 2026-01-27
  ...
  ✗ WBA: MISSING
------------------------------------------------------------
Complete: 29/30
Missing:  WBA
```

### Check for Stale Reports

```bash
python -m investment_research.batch_generation.batch_cli stale
```

## Time Estimates

| Phase | Duration |
|-------|----------|
| Data preparation (330 API calls) | ~5-7 minutes |
| Parallel generation (5 sessions × 6 reports) | ~15 minutes |
| Verification | ~1 minute |
| **Total** | **~21-23 minutes** |

## Cache Management

### Stale Data During Earnings Season

The `buffett-dev-financial-data-cache` table caches raw FMP API responses with a ~90-day TTL. During earnings season, this cache may serve outdated quarters. To refresh:

1. **Check which tickers are stale:**

```bash
cd chat-api/backend
python3 -c "
from src.utils.fmp_client import get_fmp_api_key
import httpx, json

api_key = get_fmp_api_key()
with open('investment_research/data/djia_30_batch_data.json') as f:
    cached = json.load(f)

for ticker in sorted(cached.keys()):
    cached_date = cached[ticker]['raw_financials']['income_statement'][0]['date']
    url = f'https://financialmodelingprep.com/stable/income-statement?symbol={ticker}&period=quarterly&limit=1&apikey={api_key}'
    fmp_date = httpx.get(url).json()[0]['date']
    status = 'CURRENT' if cached_date == fmp_date else 'STALE'
    if status == 'STALE':
        print(f'{ticker}: cached={cached_date} vs FMP={fmp_date} -> STALE')
"
```

2. **Delete stale cache entries** from `buffett-dev-financial-data-cache` for affected tickers (try keys like `v3:TICKER:2026`, `v2:TICKER:2025`)

3. **Re-run data preparation** to fetch fresh data from FMP:

```bash
python -m investment_research.batch_generation.batch_cli prepare --prompt-version 5.2
```

### Two DynamoDB Tables (Not Redundant)

| Table | Purpose | Consumer |
|-------|---------|----------|
| `buffett-dev-financial-data-cache` | Caches raw FMP API responses (~97KB per ticker) | `prepare_data()` — avoids re-calling FMP |
| `metrics-history-dev` | Pre-processed, category-partitioned metrics (per quarter) | Follow-up agent — queries specific metric categories |

Both are refreshed when `prepare_data()` runs with fresh (non-cached) FMP data.

## Troubleshooting

### Terminal Windows Not Opening (macOS)

1. **Check permissions**: Terminal.app may need Accessibility permissions
2. **Script not executable**: `chmod +x open_parallel_terminals.sh`
3. **Claude CLI not found**: `which claude`

### FMP API Errors

Check your API key:
```bash
python -c "from investment_research.report_generator import ReportGenerator; r = ReportGenerator(); print('API key OK')"
```

### Regenerate Specific Tickers

```bash
python -m investment_research.batch_generation.batch_cli prepare --tickers AAPL,MSFT
```
