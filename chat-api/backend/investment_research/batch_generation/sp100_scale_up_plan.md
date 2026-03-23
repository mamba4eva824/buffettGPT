# GSD: Scale Batch Report Generation from 30 → 100 S&P 500 Stocks

## Configuration: 5 parallel windows, all 8 steps, top 100 S&P 500 by market cap

---

## AUDIT SNAPSHOT

### Knowns / Evidence
1. **Current system**: 5 tmux windows × 6 hardcoded tickers = 30 DJIA stocks, ~40 min
2. **FMP plan**: Starter ($29/mo) = **300 calls/min**, 20 GB/30-day bandwidth
3. **API calls per ticker**: 7 (3 financial statements via `fetch_from_fmp` + 4 valuation via `fetch_key_metrics`, `fetch_key_metrics_ttm`, `fetch_financial_ratios_ttm`, `fetch_analyst_estimates`). Financial statements are cached 90 days; valuation endpoints always hit FMP
4. **For 100 tickers (cold cache)**: 700 FMP calls. At 300/min = ~2.3 min. But NO retry logic — a single 429 crashes everything
5. **5 FMP fetch functions** need retry: `fetch_from_fmp` (L425), `fetch_key_metrics` (L706), `fetch_key_metrics_ttm` (L745), `fetch_financial_ratios_ttm` (L786), `fetch_analyst_estimates` (L827)
6. **Shell scripts**: Hardcoded BATCH1-5 with exact tickers, "djia" in session/log names, `djia_30_batch_data.json` as data file
7. **batch_prompt_template.md**: Has hardcoded "(6 companies per batch, 5 batches total = 30 DJIA companies)" and the DJIA batch assignment table
8. **All Python scripts** import `DJIA_TICKERS` directly and use it as default
9. **SP500_TICKERS**: Only 10 test tickers, not a real list

### Unknowns / Gaps
1. **Claude Max plan tier** — determines practical parallel session limit
2. **Actual turns per report** — estimated 3-4 but not measured
3. **DynamoDB throughput mode** — on-demand vs provisioned

### Constraints
- FMP: 300 calls/min (Starter)
- 5 parallel tmux windows (user-specified)
- Must keep `--index djia` working identically to today

### Risks (Top 3)
1. **FMP 429 with no retry** → prepare_batch_data crashes mid-run
2. **Claude quota exhaustion** → sessions terminate before finishing 20 tickers
3. **100 turns insufficient** → batch of 20 tickers needs more headroom

---

## PRD: Acceptance Criteria

### AC-1: Top 100 S&P 500 Ticker List
Given `get_index_tickers('sp100')`, then it returns exactly 100 tickers (top S&P 500 by market cap).
Note: GOOGL used (not GOOG duplicate), BRK-B used (FMP format for BRK.B).

### AC-2: FMP Retry Logic
Given any FMP `fetch_*` function receives HTTP 429,
then it retries with exponential backoff (1s, 2s, 4s — up to 3 retries) and logs each retry.
On non-429 errors: raise immediately (existing behavior preserved).

### AC-3: Dynamic Batch Splitting
Given `run_parallel_reports.sh --index sp100 --windows 5`,
then it dynamically splits 100 tickers into 5 batches of 20, creates 5 tmux windows.
No hardcoded BATCH1-5 variables.

### AC-4: Parameterized Everything
Shell scripts accept: `--index <name>` (default: djia), `--windows <N>` (default: 5),
`--max-turns <N>` (auto: tickers_per_window × 5 + 20), `--prompt-version <N>`.

### AC-5: Dynamic Data File Naming
prepare_batch_data uses `{index}_{count}_batch_data.json` (e.g., `sp100_100_batch_data.json`).
Shell scripts infer filename from `--index`.

### AC-6: Backward Compatibility
`--index djia` produces identical behavior to current scripts (5 windows × 6 tickers, same naming).

### AC-7: CLI --index Support
All batch_cli.py commands (prepare, parallel, verify, stale, status) accept `--index`.

### AC-8: Template Updated
batch_prompt_template.md has no hardcoded DJIA references or batch assignment table.

---

## IMPLEMENTATION PLAN

### Step 1: Add SP100_TICKERS to index_tickers.py

**File**: `chat-api/backend/investment_research/index_tickers.py`

Add `SP100_TICKERS` — top 100 S&P 500 by market cap (from SlickCharts, Feb 2026):
```python
SP100_TICKERS = [
    'AAPL', 'ABBV', 'ABT', 'ACN', 'ADI', 'AMAT', 'AMD', 'AMGN', 'AMZN', 'ANET',
    'APH', 'AVGO', 'AXP', 'BA', 'BAC', 'BLK', 'BMY', 'BKNG', 'BRK-B', 'BSX',
    'C', 'CAT', 'CEG', 'CMCSA', 'CME', 'COF', 'COP', 'COST', 'CRM', 'CSCO',
    'CVX', 'DE', 'DHR', 'DIS', 'ETN', 'GE', 'GILD', 'GLW', 'GOOGL', 'GS',
    'HCA', 'HD', 'HON', 'IBM', 'INTC', 'ISRG', 'JNJ', 'JPM', 'KLAC', 'KO',
    'LIN', 'LLY', 'LMT', 'LOW', 'LRCX', 'MA', 'MCD', 'MCK', 'MDT', 'MET',
    'META', 'MO', 'MRK', 'MS', 'MSFT', 'MU', 'NEE', 'NFLX', 'NOC', 'NOW',
    'NVDA', 'ORCL', 'PANW', 'PEP', 'PFE', 'PG', 'PGR', 'PH', 'PLD', 'PLTR',
    'PM', 'QCOM', 'RTX', 'SBUX', 'SCHW', 'SO', 'SPGI', 'SYK', 'T', 'TJX',
    'TMO', 'TMUS', 'TSLA', 'TXN', 'UBER', 'UNH', 'UNP', 'V', 'VRTX', 'WFC',
    'WMT', 'XOM',
]
# Note: 102 tickers. BRK-B is FMP's format for Berkshire Hathaway B shares.
# WELL, NEM, APP, CB removed — ranked below top 100 at time of update.
# Last updated: Feb 2026. Refresh quarterly from slickcharts.com/sp500/marketcap
```

Update `get_index_tickers()`:
```python
def get_index_tickers(index: str) -> list:
    idx = index.upper().replace('-', '')
    if idx == 'DJIA':
        return DJIA_TICKERS.copy()
    elif idx == 'SP500':
        return SP500_TICKERS.copy()
    elif idx == 'SP100':
        return SP100_TICKERS.copy()
    else:
        raise ValueError(f"Unknown index: {index}. Use 'DJIA', 'SP500', or 'SP100'")
```

**Verify**: `python -c "from investment_research.index_tickers import get_index_tickers; t = get_index_tickers('sp100'); print(len(t), t[:5])"`

---

### Step 2: Add FMP retry logic with exponential backoff

**File**: `chat-api/backend/src/utils/fmp_client.py`

Add helper near top (after imports):
```python
import time

def _request_with_retry(client, method, url, params, max_retries=3):
    """HTTP request with exponential backoff on 429 (rate limit)."""
    for attempt in range(max_retries + 1):
        response = client.get(url, params=params) if method == 'GET' else client.request(method, url, params=params)
        if response.status_code == 429:
            if attempt == max_retries:
                logger.error(f"FMP rate limit: max retries ({max_retries}) exhausted for {url}")
                response.raise_for_status()
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(f"FMP rate limit (429): retrying in {wait}s (attempt {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response
    return response  # unreachable but satisfies linters
```

Update 5 functions to use it:
- `fetch_from_fmp()` (L451): `response = client.get(url, params=params)` → `response = _request_with_retry(client, 'GET', url, params)`
- `fetch_key_metrics()` (L706)
- `fetch_key_metrics_ttm()` (L745)
- `fetch_financial_ratios_ttm()` (L786)
- `fetch_analyst_estimates()` (L827)

Each of these has the same pattern: `response = client.get(url, params=params)` followed by `response.raise_for_status()`. Replace both lines with just `response = _request_with_retry(client, 'GET', url, params)`.

**Verify**: `cd chat-api/backend && python -m pytest tests/ -k "fmp" -x` (existing tests still pass)

---

### Step 3: Add --index and --delay to prepare_batch_data.py

**File**: `chat-api/backend/investment_research/batch_generation/prepare_batch_data.py`

Changes:
1. Replace `from investment_research.index_tickers import DJIA_TICKERS` with `from investment_research.index_tickers import get_index_tickers`
2. Add `--index` arg (default: `djia`)
3. Add `--delay` arg (default: `0.0` — no delay for small batches, user can set `0.2` for large ones)
4. Change default output to auto-generate from index: `{index}_{count}_batch_data.json`
5. Update banner text from "DJIA" to dynamic index name
6. Add `time.sleep(delay)` between tickers in the loop
7. In `prepare_all_data()`, change `tickers` default from `DJIA_TICKERS` to `None`, resolve from index parameter

**Verify**: `python -m investment_research.batch_generation.prepare_batch_data --index sp100 --delay 0.2 --tickers AAPL,MSFT` (test with 2 tickers)

---

### Step 4: Make run_parallel_reports.sh dynamic

**File**: `chat-api/backend/investment_research/batch_generation/run_parallel_reports.sh`

Major rewrite. Key changes:
1. Add `--index` arg (default: `djia`), `--windows` arg (default: `5`)
2. Remove hardcoded BATCH1-5 variables
3. Add Python-based batch splitter inline:
   ```bash
   # Get tickers and split into N batches
   BATCHES=$(python3 -c "
   import sys; sys.path.insert(0, '$PROJECT_ROOT/chat-api/backend')
   from investment_research.index_tickers import get_index_tickers
   tickers = get_index_tickers('$INDEX')
   n = $WINDOWS
   batch_size = len(tickers) // n
   remainder = len(tickers) % n
   batches = []
   start = 0
   for i in range(n):
       end = start + batch_size + (1 if i < remainder else 0)
       batches.append(','.join(tickers[start:end]))
       start = end
   print('|||'.join(batches))
   ")
   ```
4. Use `IFS='|||' read -ra BATCH_ARRAY <<< "$BATCHES"` to split into array
5. Loop to create tmux windows dynamically:
   ```bash
   for i in "${!BATCH_ARRAY[@]}"; do
       batch_num=$((i + 1))
       tickers="${BATCH_ARRAY[$i]}"
       if [ $i -eq 0 ]; then
           tmux new-session -d -s $SESSION -n "batch${batch_num}" -c "$PROJECT_ROOT"
       else
           tmux new-window -t $SESSION -n "batch${batch_num}" -c "$PROJECT_ROOT"
       fi
       tmux send-keys -t $SESSION:batch${batch_num} \
           "claude -p '$(build_prompt "$tickers")' --allowedTools '$ALLOWED_TOOLS' --max-turns $MAX_TURNS --output-format text 2>&1 | tee /tmp/${INDEX}_batch${batch_num}.log" Enter
   done
   ```
6. Update `DATA_FILE` to `$PROJECT_ROOT/${INDEX}_*_batch_data.json` (glob) or derive from index
7. Update `build_prompt()` to reference correct data file
8. Auto-calculate max-turns: `MAX_TURNS=${MAX_TURNS:-$((TICKERS_PER_BATCH * 5 + 20))}`
9. Update session name: `SESSION="${INDEX}-reports"`
10. Update all echo statements to use dynamic values

**Verify**: `./run_parallel_reports.sh --index sp100 --windows 5 --dry-run`

---

### Step 5: Update open_parallel_terminals.sh to match

**File**: `chat-api/backend/investment_research/batch_generation/open_parallel_terminals.sh`

Same changes as Step 4, adapted for AppleScript/Terminal.app:
1. Same `--index`, `--windows` args
2. Same Python-based batch splitter
3. Loop over batches calling `open_terminal_with_claude` dynamically
4. Update window titles, log paths, data file references

**Verify**: `./open_parallel_terminals.sh --index sp100 --windows 5 --dry-run`

---

### Step 6: Update batch_cli.py for --index support

**File**: `chat-api/backend/investment_research/batch_generation/batch_cli.py`

Changes:
1. Replace `from investment_research.index_tickers import DJIA_TICKERS` with `from investment_research.index_tickers import get_index_tickers`
2. Add `--index` to ALL subparsers (prepare, parallel, verify, stale, status). Default: `djia`
3. `print_banner()`: Dynamic — show index name and ticker count instead of "30 Companies"
4. `cmd_prepare()`: Pass `--index` to `prepare_all_data()`, auto-generate output filename from index
5. `cmd_parallel()`: Pass `--index` and `--windows` to shell script
6. `cmd_verify()`: Use `get_index_tickers(args.index)` as default ticker list
7. `cmd_stale()`: Same — use `get_index_tickers(args.index)` as default
8. `cmd_status()`: Pass index through to verify and stale
9. Update all help text from "DJIA" to "selected index"
10. Update prompt-version default from `4.8` to `5.1`

**Verify**: `python -m investment_research.batch_generation.batch_cli status --index sp100`

---

### Step 7: Update batch_prompt_template.md

**File**: `chat-api/backend/investment_research/batch_generation/batch_prompt_template.md`

Changes:
1. L17: `(6 companies per batch, 5 batches total = 30 DJIA companies)` → `({TICKERS_PER_BATCH} companies per batch, {WINDOW_COUNT} batches total = {TOTAL_TICKERS} companies)`
2. L25: `djia_30_batch_data.json` → `{DATA_FILE}`
3. L39: `with open('djia_30_batch_data.json')` → `with open('{DATA_FILE}')`
4. L135: `When all 6 reports in your batch are saved:` → `When all reports in your batch are saved:`
5. L145-151: Remove hardcoded batch assignment table entirely
6. L172-173: Update time estimates for variable batch sizes

**Verify**: Manual review — no hardcoded "DJIA", "30", or "6" references remain

---

### Step 8: Update check_stale_reports.py and verify_reports.py

**File 1**: `chat-api/backend/investment_research/batch_generation/check_stale_reports.py`

Changes:
1. Replace `from investment_research.index_tickers import DJIA_TICKERS` → `from investment_research.index_tickers import get_index_tickers`
2. Add `--index` arg to argparse (default: `djia`)
3. In `check_djia_staleness()`: add `index` param, change default from `DJIA_TICKERS` to `get_index_tickers(index)`
4. Rename function to `check_staleness()` (keep `check_djia_staleness` as alias for backward compat)
5. Update banner from "DJIA Report Staleness Check" to "{INDEX} Report Staleness Check"

**File 2**: `chat-api/backend/investment_research/batch_generation/verify_reports.py`

Changes:
1. Replace `from investment_research.index_tickers import DJIA_TICKERS` → `from investment_research.index_tickers import get_index_tickers`
2. Add `--index` arg to argparse (default: `djia`)
3. In `verify_reports()`: add `index` param, change default from `DJIA_TICKERS` to `get_index_tickers(index)`
4. Update banner from "DJIA Report Verification" to "{INDEX} Report Verification"

**Verify**: `python -m investment_research.batch_generation.verify_reports --index sp100`

---

## FILES TO MODIFY (9 files)

| # | File | Lines Today | Key Changes |
|---|------|-------------|-------------|
| 1 | `index_tickers.py` | 90 | +SP100_TICKERS (102 tickers), update get_index_tickers() |
| 2 | `fmp_client.py` | ~870 | +_request_with_retry(), update 5 fetch functions |
| 3 | `prepare_batch_data.py` | 165 | +--index, +--delay, dynamic filename |
| 4 | `run_parallel_reports.sh` | 200 | Rewrite: dynamic batch splitting, parameterized |
| 5 | `open_parallel_terminals.sh` | 193 | Same rewrite as #4 |
| 6 | `batch_cli.py` | 256 | +--index to all commands, dynamic banner |
| 7 | `batch_prompt_template.md` | 174 | Remove all hardcoded DJIA/30/6 references |
| 8 | `check_stale_reports.py` | 167 | +--index, dynamic ticker source |
| 9 | `verify_reports.py` | 190 | +--index, dynamic ticker source |

---

## TASK GRAPH (Execution Order)

```
[1] index_tickers.py (SP100_TICKERS)     ← independent, no deps
[2] fmp_client.py (retry logic)          ← independent, no deps
     ↓
[3] prepare_batch_data.py (--index)      ← depends on [1] (imports get_index_tickers)
[4] run_parallel_reports.sh (dynamic)    ← depends on [1] (calls get_index_tickers via python)
[5] open_parallel_terminals.sh           ← depends on [1] (same)
[6] batch_cli.py (--index)              ← depends on [1], [3], [4]
[7] batch_prompt_template.md             ← independent
[8] check_stale + verify (--index)       ← depends on [1]
```

Steps [1], [2], and [7] can run in parallel.
Then [3], [4], [5], [8] can run in parallel.
Then [6] last (it wires everything together).

---

## SELF-CRITIQUE

### What could go wrong
1. **BRK-B ticker format**: FMP uses `BRK-B` not `BRK.B`. Need to verify this works through the entire pipeline (FMP calls, DynamoDB keys, report parsing). If FMP rejects it, may need `BRK-A` instead.
2. **102 vs 100 tickers**: The SlickCharts list gives 102 because it includes GOOGL and some at the boundary. I've trimmed to ~102 sorted alphabetically. Need to verify exact count after dedup.
3. **20 tickers per window × ~5 min = 100 min**: That's a long Claude session. If quota runs out at ticker 15, the last 5 are lost. The verify script catches this, but it means a re-run for stragglers.
4. **--max-turns auto-calculation**: `20 * 5 + 20 = 120` should be enough, but if Claude needs 8+ turns per report (e.g., retrying a failed save), it could hit the limit.

### Simplest test to validate
After implementing, run:
```bash
# Test prepare with 3 tickers
python -m investment_research.batch_generation.batch_cli prepare --index sp100 --tickers NVDA,AMZN,META

# Test dry-run with full sp100
./run_parallel_reports.sh --index sp100 --windows 5 --dry-run

# Verify those 3 reports
python -m investment_research.batch_generation.batch_cli verify --index sp100 --tickers NVDA,AMZN,META
```

---

## TIMING ESTIMATES (100 tickers, 5 windows)

| Phase | Time | Notes |
|-------|------|-------|
| Prepare data (cold) | ~4-5 min | 100 × 7 calls, 300/min limit, 0.2s delay |
| Prepare data (cached) | ~30s | Only 4 valuation calls per ticker |
| Report generation | ~100 min | 5 windows × 20 tickers × ~5 min each |
| Verification | ~15 sec | 100 DynamoDB reads |
| **Total wall-clock** | **~105 min** | Dominated by generation phase |
