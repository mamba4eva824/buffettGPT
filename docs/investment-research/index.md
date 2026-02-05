# Investment Research

This section covers BuffettGPT's AI-powered investment research and report generation system.

## Overview

The Investment Research module generates comprehensive company analysis reports using:

- **Financial Market Provider (FMP) API** for real-time financial data
- **Claude AI** for analysis and report generation
- **DynamoDB** for report persistence with section-based schema
- **Server-Sent Events (SSE)** for streaming report delivery

## Capabilities

- **Company Analysis**: Deep-dive reports covering financials, growth, debt, and valuation
- **DJIA 30 Coverage**: Pre-built support for all Dow Jones Industrial Average companies
- **Follow-up Q&A**: Context-aware questions about generated reports
- **Batch Generation**: Parallel report generation for multiple companies
- **Report Freshness**: Automatic staleness detection based on earnings announcements

## Documentation

| Document | Description |
|----------|-------------|
| [Report Generation](report-generation.md) | End-to-end workflow for generating reports |
| [Batch Generation](batch-generation.md) | Parallel report generation for DJIA 30 |
| [Follow-up Agent](followup-agent.md) | Q&A system architecture and usage |
| [Earnings Tracker](earnings-tracker.md) | Report staleness detection |
| [Token Limiter](token-limiter.md) | Context window management |
| [Metrics Cache](metrics-cache.md) | Financial data caching system |

## Report Structure

Each report contains 13 sections stored in DynamoDB v2 schema:

1. Executive Summary
2. Business Overview
3. Financial Health
4. Growth Analysis
5. Profitability Metrics
6. Debt Analysis
7. Cash Flow Analysis
8. Valuation Metrics
9. Risk Factors
10. Investment Thesis
11. Key Metrics Table
12. Rating Summary
13. Disclaimer

## Quick Start

### Generate a Report (Claude Code Mode)

```python
from investment_research.report_generator import ReportGenerator

# Prepare data from FMP API
generator = ReportGenerator(use_api=False, prompt_version=4.8)
data = generator.prepare_data('AAPL')

# Generate report using Claude Code (interactive)
# Follow the prompt template in prompts/investment_report_prompt_v4_8.txt

# Save to DynamoDB
generator.save_report(
    ticker='AAPL',
    fiscal_year=2026,
    report_content=report_markdown,
    ratings={'growth': 'Strong', 'profitability': 'Exceptional'}
)
```

## Supported Companies

The module includes built-in support for DJIA 30 companies. See [Company Tickers](../reference/company-tickers.md) for the complete list.
