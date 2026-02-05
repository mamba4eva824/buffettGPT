# Batch DJIA Investment Report Generation

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
│   │     open_parallel_terminals.sh (AppleScript automation)      │   │
│   │              OR run_parallel_reports.sh (tmux)               │   │
│   │                                                              │   │
│   │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│   │
│   │  │Terminal1│ │Terminal2│ │Terminal3│ │Terminal4│ │Terminal5││   │
│   │  │ 6 tickers│ │ 6 tickers│ │ 6 tickers│ │ 6 tickers│ │ 6 tickers││   │
│   │  │ claude  │ │ claude  │ │ claude  │ │ claude  │ │ claude  ││   │
│   │  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘│   │
│   │       │          │          │          │          │         │   │
│   │       └──────────┴──────────┴──────────┴──────────┘         │   │
│   │                    (All 5 run in parallel)                   │   │
│   └──────────────────────────────┬──────────────────────────────┘   │
│                                  │                                   │
│                                  ▼                                   │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │                    DynamoDB v2 Table                         │   │
│   │                 investment-reports-v2                        │   │
│   │               (13 sections × 30 tickers)                     │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
chat-api/backend/investment_research/batch_generation/
├── __init__.py                    # Package init
├── batch_cli.py                   # Unified CLI for batch operations
├── batch_prompt_template.md       # Instructions template for each batch
├── check_stale_reports.py         # Check for reports needing refresh
├── open_parallel_terminals.sh     # macOS: Opens 5 Terminal.app windows (recommended)
├── prepare_batch_data.py          # Pre-fetch FMP data for all tickers
├── run_parallel_reports.sh        # tmux launcher for parallel sessions (alternative)
├── verify_reports.py              # Verify all reports saved to DynamoDB
└── tests/                         # Unit tests
    ├── __init__.py
    ├── test_batch_cli.py
    ├── test_check_stale_reports.py
    ├── test_prepare_batch_data.py
    └── test_verify_reports.py
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
- All 5 windows run in parallel simultaneously

**Option B: tmux Sessions (Alternative)**

```bash
python -m investment_research.batch_generation.batch_cli parallel
```

This creates 5 tmux windows in a single session.

**Batch Assignments (both options):**

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

All 5 windows generate reports **simultaneously in parallel**.

### Step 4: Monitor Progress

**For Terminal.app windows:**
- All 5 windows are visible on screen
- Monitor progress directly in each window
- Each window shows `✓ TICKER saved` as reports complete

**For tmux sessions:**
```bash
tmux attach -t djia-reports
```

Navigation:
- `Ctrl+B` then `0-4` to switch between windows
- `Ctrl+B` then `D` to detach

### Step 5: Verify Completion

```bash
python -m investment_research.batch_generation.batch_cli verify
```

## CLI Reference

### Automated Terminal Launcher (macOS)

```bash
cd chat-api/backend/investment_research/batch_generation

# Open 5 Terminal windows with Claude ready (recommended)
./open_parallel_terminals.sh

# Preview what would happen without opening windows
./open_parallel_terminals.sh --dry-run
```

**Features:**
- Uses AppleScript to open visible Terminal.app windows
- Each window is titled with batch assignment (e.g., "DJIA Batch 1: AAPL,AMGN,...")
- Claude CLI is automatically started in each window
- 1-second delay between windows to prevent race conditions
- All 5 windows run truly in parallel

**Prerequisites:**
- macOS with Terminal.app
- `claude` CLI installed and in PATH
- `djia_30_batch_data.json` exists (from prepare step)

### Unified CLI (batch_cli.py)

```bash
cd chat-api/backend

# Prepare FMP data
python -m investment_research.batch_generation.batch_cli prepare [options]
  --output FILE       Output JSON file (default: djia_30_batch_data.json)
  --tickers LIST      Comma-separated tickers (default: all 30 DJIA)
  --prompt-version N  Prompt version to use (default: 4.8)

# Launch parallel sessions (tmux alternative)
python -m investment_research.batch_generation.batch_cli parallel [options]
  --dry-run           Print commands without executing

# Verify reports exist
python -m investment_research.batch_generation.batch_cli verify [options]
  --env ENV           Environment: dev or prod (default: dev)
  --tickers LIST      Comma-separated tickers to check

# Check for stale reports
python -m investment_research.batch_generation.batch_cli stale [options]
  --tickers-only      Output only ticker symbols (for piping)
  --env ENV           Environment: dev or prod (default: dev)
  --tickers LIST      Comma-separated tickers to check

# Get status summary
python -m investment_research.batch_generation.batch_cli status [options]
  --env ENV           Environment: dev or prod (default: dev)
```

### Individual Scripts

```bash
# Prepare data only
python -m investment_research.batch_generation.prepare_batch_data \
  --output djia_30_batch_data.json \
  --tickers AAPL,MSFT,GOOGL

# Verify reports only
python -m investment_research.batch_generation.verify_reports

# Check staleness only
python -m investment_research.batch_generation.check_stale_reports --tickers-only
```

## FMP API Endpoints Used

The `prepare_batch_data.py` script fetches data from these FMP endpoints:

| Endpoint | Data Returned |
|----------|---------------|
| `/stable/balance-sheet-statement` | 20 quarters of balance sheet |
| `/stable/income-statement` | 20 quarters of income statement |
| `/stable/cash-flow-statement` | 20 quarters of cash flow |
| `/stable/key-metrics` | 5 years of P/E, P/B, EV/EBITDA |
| `/stable/key-metrics-ttm` | TTM valuation metrics |
| `/stable/ratios-ttm` | TTM profitability ratios |
| `/stable/analyst-estimates` | Forward EPS/revenue estimates |
| `/stable/quote` | Currency conversion (if non-USD) |

**Total API calls**: ~8 per ticker × 30 tickers = ~240 calls

## Output Data Format

### djia_30_batch_data.json

```json
{
  "AAPL": {
    "metrics_context": "Financial metrics for AAPL...\nRevenue: $385.6B\n...",
    "features": {
      "revenue_growth": 0.08,
      "net_margin": 0.25,
      "pe_ratio": 28.5,
      "debt_to_equity": 1.8
    },
    "raw_financials_summary": {
      "quarters": 20,
      "has_valuation": true
    },
    "prepared_at": "2026-01-26T10:30:00.000Z",
    "prompt_version": 4.8
  },
  "MSFT": { ... },
  ...
}
```

### Error Handling

Failed tickers are recorded with error details:

```json
{
  "INVALID": {
    "error": "FMP API error: ticker not found",
    "prepared_at": "2026-01-26T10:30:00.000Z"
  }
}
```

## DynamoDB Output

Reports are saved to `investment-reports-v2-dev` (dev) or `investment-reports-v2-prod` (prod):

| Attribute | Description |
|-----------|-------------|
| `ticker` | Stock symbol (partition key) |
| `section_id` | Section identifier (sort key) |
| `content` | Markdown content |
| `generated_at` | ISO timestamp |
| `total_word_count` | Aggregate word count |
| `prompt_version` | Prompt version used |
| `last_earnings_date` | Earnings date at generation time |

**Expected items**: 13 sections × 30 tickers = 390 items

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

Output:
```
DJIA Report Staleness Check
----------------------------------------
Fresh:  28/30
Stale:  2/30

Stale reports (need regeneration):
  AAPL: new_earnings_available
  MSFT: new_earnings_available
```

## Running Tests

```bash
cd chat-api/backend

# Run all batch generation tests
pytest investment_research/batch_generation/tests/ -v

# Run specific test file
pytest investment_research/batch_generation/tests/test_prepare_batch_data.py -v

# Run with coverage
pytest investment_research/batch_generation/tests/ -v --cov=investment_research.batch_generation
```

**Test count**: 56 tests across 4 test files

## Troubleshooting

### Terminal Windows Not Opening (macOS)

If `open_parallel_terminals.sh` fails:

1. **Check permissions**: Terminal.app may need Accessibility permissions
   - System Preferences → Security & Privacy → Privacy → Accessibility
   - Add Terminal.app to the list

2. **Script not executable**:
   ```bash
   chmod +x open_parallel_terminals.sh
   ```

3. **Claude CLI not found**:
   ```bash
   which claude  # Should return a path
   ```

### tmux Not Installed (Alternative Approach)

```bash
brew install tmux  # macOS
apt install tmux   # Ubuntu/Debian
```

### FMP API Errors

Check your API key:
```bash
python -c "from investment_research.report_generator import ReportGenerator; r = ReportGenerator(); print('API key OK')"
```

### Missing Reports After Batch

1. Check tmux session for errors: `tmux attach -t djia-reports`
2. Verify specific ticker: `python -m investment_research.batch_generation.batch_cli verify --tickers AAPL`
3. Check DynamoDB directly in AWS Console

### Regenerate Specific Tickers

```bash
python -m investment_research.batch_generation.batch_cli prepare --tickers AAPL,MSFT
```

## Time Estimates

| Phase | Duration |
|-------|----------|
| Data preparation (240 API calls) | ~5 minutes |
| Parallel generation (5 sessions × 6 reports) | ~15 minutes |
| Verification | ~1 minute |
| **Total** | **~20 minutes** |

> **Note**: With 5 Claude Code sessions running in parallel, all 30 reports complete in ~15 minutes total. Each session generates 6 reports sequentially (~2.5 min per report).

## Files Reference

| File | Purpose |
|------|---------|
| [open_parallel_terminals.sh](../batch_generation/open_parallel_terminals.sh) | Automated Terminal.app launcher (macOS) |
| [run_parallel_reports.sh](../batch_generation/run_parallel_reports.sh) | tmux-based parallel launcher (alternative) |
| [batch_cli.py](../batch_generation/batch_cli.py) | Unified CLI for all batch operations |
| [prepare_batch_data.py](../batch_generation/prepare_batch_data.py) | Pre-fetch FMP data for all tickers |
| [batch_prompt_template.md](../batch_generation/batch_prompt_template.md) | Instructions template for each batch |
| [index_tickers.py](../index_tickers.py) | DJIA ticker list (30 companies) |
| [report_generator.py](../report_generator.py) | Core report generation logic |
| [prompts/investment_report_prompt_v4_8.txt](../prompts/investment_report_prompt_v4_8.txt) | Report prompt template |
| [earnings_tracker.py](../earnings_tracker.py) | Staleness checking source |

## See Also

- [EARNINGS_TRACKER.md](EARNINGS_TRACKER.md) - Staleness detection details
- [RESEARCH_SYSTEM_ARCHITECTURE.md](RESEARCH_SYSTEM_ARCHITECTURE.md) - Overall system architecture
