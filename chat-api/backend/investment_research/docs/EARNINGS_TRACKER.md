# Earnings Tracker

Tracks company earnings dates to determine when investment reports need refreshing.

## Overview

The earnings tracker monitors existing reports in DynamoDB and compares them against the FMP Earnings Calendar API to identify which reports are stale due to new earnings releases.

**Key Principle**: Only check staleness for reports we've already generated, not all possible tickers.

## Architecture

```
┌─────────────────────┐     ┌──────────────────────┐
│   DynamoDB v2       │     │  FMP Earnings API    │
│   (Existing Reports)│     │  (Calendar Data)     │
└─────────┬───────────┘     └──────────┬───────────┘
          │                            │
          │  get_existing_reports()    │  _fetch_earnings_calendar()
          │                            │
          ▼                            ▼
┌─────────────────────────────────────────────────────┐
│                  EarningsTracker                     │
│                                                      │
│  • Scans DynamoDB for 00_executive items            │
│  • Fetches 90-day earnings calendar from FMP        │
│  • Compares last_earnings_date vs current earnings  │
│  • Returns stale reports needing refresh            │
└─────────────────────────────────────────────────────┘
```

## Data Flow

### When Saving Reports

```python
# report_generator.py - save_report_sections()
1. Generate report content
2. Fetch latest earnings date from FMP
3. Save to DynamoDB with:
   - generated_at: timestamp
   - last_earnings_date: "YYYY-MM-DD" (from FMP)
```

### When Checking Staleness

```python
# earnings_tracker.py - check_needs_refresh()
1. Get report metadata from DynamoDB (generated_at, last_earnings_date)
2. Fetch current earnings calendar from FMP
3. Compare dates:
   - If current_earnings > stored_earnings → STALE
   - If current_earnings > report_date (no stored) → STALE
   - Otherwise → FRESH
```

## DynamoDB Schema Addition

The `00_executive` item now includes:

| Field | Type | Description |
|-------|------|-------------|
| `last_earnings_date` | String | YYYY-MM-DD of earnings at report generation time |
| `generated_at` | String | ISO timestamp when report was created |

## CLI Usage

```bash
cd chat-api/backend

# Check a specific ticker's report status
python investment_research/earnings_tracker.py check AAPL

# Get all stale reports
python investment_research/earnings_tracker.py stale

# Get full summary (fresh/stale/unknown counts)
python investment_research/earnings_tracker.py summary
```

### Example Output

```
$ python investment_research/earnings_tracker.py summary

Reports Summary:
  Total: 7
  Fresh: 7
  Stale: 0
  Unknown: 0

$ python investment_research/earnings_tracker.py check AAPL

AAPL Report Status:
  Needs Refresh: False
  Reason: up_to_date
  Report Date: 2026-01-15T10:30:00Z
  Stored Earnings: 2025-10-31
  Current Earnings: 2025-10-31
  Upcoming Earnings: 2026-01-29
```

## API Reference

### EarningsTracker Class

```python
from investment_research.earnings_tracker import EarningsTracker

tracker = EarningsTracker(environment='dev')

# Get all existing reports in DynamoDB
reports = tracker.get_existing_reports()
# Returns: [{'ticker': 'AAPL', 'generated_at': '...', 'last_earnings_date': '...'}, ...]

# Check if a specific report needs refresh
result = tracker.check_needs_refresh('AAPL')
# Returns: {
#   'ticker': 'AAPL',
#   'needs_refresh': False,
#   'reason': 'up_to_date',
#   'report_date': '2026-01-15T10:30:00Z',
#   'last_earnings_stored': '2025-10-31',
#   'current_latest_earnings': '2025-10-31',
#   'upcoming_earnings': '2026-01-29'
# }

# Get all stale reports
stale = tracker.get_stale_reports()
# Returns: [{'ticker': 'MSFT', 'needs_refresh': True, 'reason': 'new_earnings_released', ...}]

# Get full summary
summary = tracker.get_reports_summary()
# Returns: {
#   'total_reports': 7,
#   'fresh_count': 6,
#   'stale_count': 1,
#   'unknown_count': 0,
#   'fresh_reports': [...],
#   'stale_reports': [...],
#   'unknown_reports': [...]
# }
```

### Convenience Functions

```python
from investment_research.earnings_tracker import get_stale_tickers, check_ticker

# Get just the ticker symbols that need refresh
stale_tickers = get_stale_tickers()
# Returns: ['MSFT', 'NVDA']

# Quick check for a single ticker
result = check_ticker('AAPL')
```

## Staleness Reasons

| Reason | Description |
|--------|-------------|
| `up_to_date` | Report is current, no refresh needed |
| `new_earnings_released` | New earnings date > stored earnings date |
| `earnings_after_report_generation` | Earnings released after report was generated (legacy reports without stored date) |
| `missing_report_date` | Report missing generated_at field |
| `no_report_exists` | No report found in DynamoDB for this ticker |

## FMP API Details

### Endpoint Used

```
GET https://financialmodelingprep.com/stable/earnings-calendar
    ?from=YYYY-MM-DD
    &to=YYYY-MM-DD
    &apikey=<key>
```

### Response Format

```json
[
  {
    "symbol": "AAPL",
    "date": "2025-10-31",
    "epsActual": 1.64,
    "epsEstimated": 1.60,
    "revenueActual": 94900000000,
    "revenueEstimated": 94500000000
  }
]
```

### Limitations

- **4000 record limit** per request (FMP caps results)
- **90-day lookback** is the default window
- Results indexed by ticker for O(1) lookup

## Caching

The earnings calendar is cached for 6 hours to avoid repeated API calls:

```python
self._cache_ttl = timedelta(hours=6)
```

Cache is invalidated automatically after TTL expires.

## Future: Earnings-Aware Batch Scheduler (Option 3)

This module provides the foundation for automated report refresh. A future scheduler could:

1. Run daily/weekly via CloudWatch Events
2. Call `get_stale_reports()` to find outdated reports
3. Trigger report regeneration for stale tickers
4. Optionally pre-fetch upcoming earnings dates to schedule refreshes proactively

```python
# Pseudocode for future scheduler
def refresh_stale_reports():
    tracker = EarningsTracker()
    stale = tracker.get_stale_reports()

    for report in stale:
        # Trigger report regeneration
        generate_report(report['ticker'])
```

## Files

| File | Purpose |
|------|---------|
| `earnings_tracker.py` | Main module with EarningsTracker class |
| `report_generator.py` | Updated to store `last_earnings_date` on save |

## Testing

```bash
# Import test
python -c "from investment_research.earnings_tracker import EarningsTracker; print('OK')"

# Full test
python investment_research/earnings_tracker.py summary
```
