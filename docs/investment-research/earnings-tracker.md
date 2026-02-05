# Earnings Tracker

The earnings tracker detects when investment reports become stale due to new earnings announcements.

## Overview

Reports should be regenerated after a company announces new earnings, as the financial data becomes outdated.

## How It Works

1. **Track Earnings Dates** - Monitor upcoming and past earnings announcements
2. **Compare to Report Date** - Check if earnings occurred after report generation
3. **Flag Stale Reports** - Mark reports that need regeneration

## Usage

### Check Report Staleness

```python
from investment_research.earnings_tracker import EarningsTracker

tracker = EarningsTracker()
is_stale = tracker.is_report_stale('AAPL')

if is_stale:
    print("Report needs regeneration")
```

### Batch Staleness Check

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

## Data Sources

- **Earnings Dates** - From FMP API earnings calendar
- **Report Generation Date** - Stored in DynamoDB report metadata

## Staleness Criteria

A report is considered stale when:

1. New earnings have been announced since report generation
2. Report is older than configurable threshold (default: 90 days)
3. Significant price movement indicates material changes

## Related

- [Report Generation](report-generation.md)
- [Batch Generation](batch-generation.md)
