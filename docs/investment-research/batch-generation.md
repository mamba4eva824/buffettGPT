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
│   │  (8 endpoints│───▶│  _data.py        │───▶│ _data.json       │  │
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
│   │                    DynamoDB v2 Table                         │   │
│   │               (13 sections × 30 tickers)                     │   │
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

- Call 8 FMP API endpoints for each of 30 tickers (~240 API calls)
- Save data to `djia_30_batch_data.json`
- Takes approximately 5 minutes

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

In each Terminal window, paste the following prompt:

```
Generate investment reports for: [TICKERS FROM YOUR WINDOW]
Read data from djia_30_batch_data.json
Use v4.8 prompt from prompts/investment_report_prompt_v4_8.txt
Save each report to DynamoDB with save_report_sections()
```

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

**Total API calls**: ~8 per ticker × 30 tickers = ~240 calls

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
| Data preparation (240 API calls) | ~5 minutes |
| Parallel generation (5 sessions × 6 reports) | ~15 minutes |
| Verification | ~1 minute |
| **Total** | **~20 minutes** |

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
