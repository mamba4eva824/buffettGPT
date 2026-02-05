# Claude Code Workflow

This guide covers how to generate investment reports using Claude Code mode.

## Quick Start - Generate a Report

### Step 1: Prepare Financial Data

```python
# In Python REPL or script
import sys
sys.path.insert(0, '/path/to/buffett_chat_api/chat-api/backend')

from investment_research.report_generator import ReportGenerator

generator = ReportGenerator(prompt_version=4.8)
data = generator.prepare_data('NVDA')  # or any ticker

print(data['metrics_context'])  # This is what Claude needs to analyze
```

### Step 2: Generate the Report (Claude Code)

Use the `metrics_context` from Step 1 along with the prompt template in `prompts/investment_report_prompt_v4_8.txt` to generate a comprehensive investment report.

The report MUST follow the v4.8 structure:

- **Part 1: Executive Summary** - TL;DR, Business Overview, Health Check, Investment Fit, Verdict
- **Part 2: Detailed Analysis** - Growth, Profitability, Valuation, Earnings Quality, Cash Flow, Debt, Dilution, Bull/Bear Cases, Warnings, Vibe Check
- **Part 3: Real Talk**

The report MUST end with a JSON ratings block:

```json
{
  "growth": {"rating": "...", "confidence": "...", "key_factors": [...]},
  "profitability": {"rating": "...", "confidence": "...", "key_factors": [...]},
  "overall_verdict": "BUY" | "HOLD" | "SELL",
  "conviction": "High" | "Medium" | "Low"
}
```

### Step 3: Save the Report

```python
from datetime import datetime

generator.save_report_sections(
    ticker='NVDA',
    fiscal_year=datetime.now().year,
    report_content=report_content,  # The full markdown report
    ratings=None  # Will be extracted from JSON block in report
)
```

## Batch Generation Workflow

For generating multiple reports:

```python
import sys
sys.path.insert(0, '/path/to/buffett_chat_api/chat-api/backend')

from investment_research.report_generator import ReportGenerator
from datetime import datetime

generator = ReportGenerator(prompt_version=4.8)

# List of tickers to generate
tickers = ['NVDA', 'NVO', 'AAPL', 'MSFT']

for ticker in tickers:
    # Step 1: Get data
    data = generator.prepare_data(ticker)

    # Step 2: Claude Code generates report (manual step)
    # Use data['metrics_context'] with the v4.8 prompt template

    # Step 3: Save (after report is generated)
    generator.save_report_sections(
        ticker=ticker,
        fiscal_year=datetime.now().year,
        report_content=report_content,
        ratings=None
    )
```

## Important Notes

### JSON Ratings Block

The report MUST end with a JSON ratings block wrapped in triple backticks. The `save_report_sections()` function will:

- Automatically extract ratings from the JSON block if not provided
- Serialize the ratings to a JSON string for DynamoDB (floats are not natively supported)
- Store ratings as a JSON string, which the Lambda deserializes when streaming

### DynamoDB V2 Schema

Reports are saved as:

- `00_executive` item: Contains ToC + ratings + merged Executive Summary (Part 1 sections combined)
- Individual section items: `06_growth`, `07_profit`, etc. for Part 2/3 sections

### Merged Executive Summary

Part 1 sections (TL;DR, Business, Health Check, Fit, Verdict) are automatically merged into a single `01_executive_summary` section for streamlined ToC display.

### Section Parsing

The `section_parser.py` module handles parsing the markdown report into individual sections based on the `## Static Keyword: Dynamic Subtitle` header format.

### Prompt Version

Always use v4.8 (the latest) which has:

- Executive Summary first (verdict at top)
- Dynamic section headers with ticker-specific numbers
- Plain English translations for all financial terms
- ~2,500 word target length

## Files Reference

| File | Purpose |
|------|---------|
| `report_generator.py` | Main generator class with `prepare_data()` and `save_report_sections()` |
| `section_parser.py` | Parses markdown into sections, builds ToC, handles merged executive |
| `prompts/investment_report_prompt_v4_8.txt` | Latest prompt template |
| `generate_report.py` | CLI for API mode (not used in Claude Code mode) |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INVESTMENT_REPORTS_TABLE` | `investment-reports-dev` | Legacy v1 table |
| `INVESTMENT_REPORTS_V2_TABLE` | `investment-reports-v2-dev` | V2 section-based table |
