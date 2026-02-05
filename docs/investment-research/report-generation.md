# Report Generation

This guide covers the end-to-end workflow for generating investment reports in BuffettGPT.

## Overview

Investment reports are generated using:

1. **Claude Code Mode** (recommended): Interactive generation with review
2. ~~API Mode~~: Deprecated - do not use

!!! warning "Important"
    Always use Claude Code mode for report generation. API mode is not supported.

## Workflow

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Prepare    │────▶│  Generate   │────▶│    Save     │
│    Data     │     │   Report    │     │  to Dynamo  │
└─────────────┘     └─────────────┘     └─────────────┘
      │                   │                    │
      ▼                   ▼                    ▼
   FMP API           Claude Code          DynamoDB
```

## Step 1: Prepare Data

Fetch financial data from the FMP API:

```python
from investment_research.report_generator import ReportGenerator

# Initialize generator (Claude Code mode)
generator = ReportGenerator(use_api=False, prompt_version=4.8)

# Fetch data for a ticker
data = generator.prepare_data('AAPL')
```

### Data Contents

The `prepare_data()` method fetches:

- Company profile and overview
- Income statements (quarterly and annual)
- Balance sheets
- Cash flow statements
- Key metrics and ratios
- Stock price history
- Peer comparison data

## Step 2: Load Prompt Template

Read the appropriate prompt version:

```
chat-api/backend/investment_research/prompts/investment_report_prompt_v4_8.txt
```

The prompt includes:

- System instructions
- Data placeholders
- Section formatting guidelines
- Rating criteria

## Step 3: Generate Report

Using Claude Code, follow the prompt template to generate the report markdown. The template guides you through:

1. **Executive Summary**: Key findings and recommendation
2. **Business Overview**: Company description and market position
3. **Financial Health**: Balance sheet analysis
4. **Growth Analysis**: Revenue and earnings trends
5. **Profitability**: Margins and efficiency metrics
6. **Debt Analysis**: Leverage and coverage ratios
7. **Cash Flow**: Operating and free cash flow
8. **Valuation**: P/E, P/S, and other multiples
9. **Risk Factors**: Key risks to monitor
10. **Investment Thesis**: Bull/bear cases
11. **Key Metrics Table**: Summary data table
12. **Rating Summary**: Overall ratings
13. **Disclaimer**: Legal notice

## Step 4: Save Report

Save the generated report to DynamoDB:

```python
generator.save_report(
    ticker='AAPL',
    fiscal_year=2026,
    report_content=report_markdown,
    ratings={
        'growth': 'Strong',
        'profitability': 'Exceptional',
        'financial_health': 'Strong',
        'valuation': 'Fair',
        'overall': 'Buy'
    }
)
```

### DynamoDB Schema (v2)

Reports are stored with 13 individual section columns:

| Column | Description |
|--------|-------------|
| `ticker` | Stock symbol (partition key) |
| `fiscal_year` | Year of report (sort key) |
| `executive_summary` | Section 1 content |
| `business_overview` | Section 2 content |
| ... | (remaining sections) |
| `ratings` | JSON ratings object |
| `created_at` | Timestamp |
| `updated_at` | Timestamp |

## Report Freshness

Reports are considered stale after earnings announcements. The [Earnings Tracker](earnings-tracker.md) monitors this automatically.

### Check Staleness

```python
from investment_research.earnings_tracker import EarningsTracker

tracker = EarningsTracker()
is_stale = tracker.is_report_stale('AAPL')
```

## Prompt Versions

| Version | Status | Key Features |
|---------|--------|--------------|
| v4.8 | **Current** | Executive summary first, dynamic headers |
| v5.0 | Testing | Enhanced valuation analysis |

See [Prompt Templates](../prompts/index.md) for version history.

## Best Practices

1. **Always use Claude Code mode** - Never use API mode
2. **Review before saving** - Check for accuracy and completeness
3. **Use current prompt version** - v4.8 is recommended
4. **Track earnings dates** - Regenerate after announcements
5. **Batch generation** - Use [Batch Generation](batch-generation.md) for multiple reports

## Troubleshooting

### Data Fetch Errors

```python
# Check FMP API availability
data = generator.prepare_data('AAPL')
if not data:
    print("FMP API may be unavailable")
```

### Save Errors

```python
try:
    generator.save_report(...)
except Exception as e:
    print(f"Save failed: {e}")
    # Check DynamoDB table permissions
```

## Next Steps

- [Batch Generation](batch-generation.md) - Generate reports for multiple companies
- [Follow-up Agent](followup-agent.md) - Enable Q&A on generated reports
- [Earnings Tracker](earnings-tracker.md) - Monitor report freshness
