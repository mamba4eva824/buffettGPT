# Investment Research Feature - Implementation Guide

> **Status**: Phase 1 & 2 Complete | Phase 3-7 Pending

This document covers the implementation details for the Investment Research feature add-on. For the original architecture plan, see [INVESTMENT_RESEARCH_FEATURE_ADD_ON.md](./INVESTMENT_RESEARCH_FEATURE_ADD_ON.md).

---

## Table of Contents

1. [Overview](#overview)
2. [Phase 1: DynamoDB Reports Table](#phase-1-dynamodb-reports-table)
3. [Phase 2: Report Generation CLI Tool](#phase-2-report-generation-cli-tool)
4. [Usage Guide](#usage-guide)
5. [Report Format & Structure](#report-format--structure)
6. [Data Sources](#data-sources)
7. [Future Phases](#future-phases)

---

## Overview

The Investment Research feature generates AI-powered investment analysis reports using Claude (via Claude Code or Anthropic API). Reports are:

- **Pre-generated and cached** in DynamoDB for fast retrieval
- **Targeted at Millennials/Gen Z** with plain English explanations
- **5-point rating system**: Very Strong / Strong / Stable / Weak / Very Weak
- **Dynamic and engaging** with contextual headers unique to each company

### Architecture Summary

```
┌─────────────────────────────────────────────────────────────┐
│                    Report Generation Flow                    │
│                                                              │
│   CLI Tool (generate_report.py)                             │
│         │                                                    │
│         ▼                                                    │
│   ReportGenerator.prepare_data()                            │
│         │                                                    │
│         ▼                                                    │
│   FMP Client (src/utils/fmp_client.py)                      │
│   - Fetches 5 years quarterly financial data                │
│   - Caches in DynamoDB (financial-data-cache)               │
│         │                                                    │
│         ▼                                                    │
│   Feature Extractor (src/utils/feature_extractor.py)        │
│   - Extracts debt, cashflow, growth metrics                 │
│         │                                                    │
│         ▼                                                    │
│   Claude Code / Opus 4.5 (report generation)                │
│         │                                                    │
│         ▼                                                    │
│   ReportGenerator.save_report()                             │
│   - Stores in DynamoDB (investment-reports-{env})           │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 1: DynamoDB Reports Table

### Terraform Configuration

**File**: `chat-api/terraform/modules/dynamodb/reports_table.tf`

```hcl
resource "aws_dynamodb_table" "investment_reports" {
  name         = "investment-reports-${var.environment}"
  billing_mode = var.billing_mode

  hash_key  = "ticker"
  range_key = "fiscal_year"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "fiscal_year"
    type = "N"
  }

  attribute {
    name = "generated_at"
    type = "S"
  }

  # GSI for querying by generation date
  global_secondary_index {
    name            = "generated-at-index"
    hash_key        = "ticker"
    range_key       = "generated_at"
    projection_type = "ALL"
  }

  # TTL for automatic expiration (reports refresh quarterly)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
```

### Report Schema

```json
{
  "ticker": "AAPL",
  "fiscal_year": 2026,
  "report_content": "## TL;DR\n...",
  "ratings": {
    "debt": {
      "rating": "Strong",
      "confidence": "High",
      "key_factors": ["Strategic leverage", "Strong interest coverage", "Improving trend"]
    },
    "cashflow": {
      "rating": "Very Strong",
      "confidence": "High",
      "key_factors": ["25%+ FCF margins", "$20B+ annual buybacks", "Services growth"]
    },
    "growth": {
      "rating": "Stable",
      "confidence": "High",
      "key_factors": ["Flat revenue", "Margin expansion", "No new category"]
    },
    "overall_verdict": "HOLD",
    "conviction": "Medium"
  },
  "generated_at": "2026-01-05T15:30:00Z",
  "model": "claude-code",
  "features_snapshot": "{...}",
  "ttl": 1718841600
}
```

### Deployment

```bash
cd chat-api/terraform/environments/dev
terraform plan -target=module.dynamodb.aws_dynamodb_table.investment_reports
terraform apply -target=module.dynamodb.aws_dynamodb_table.investment_reports
```

---

## Phase 2: Report Generation CLI Tool

### Package Structure

```
chat-api/backend/investment_research/
├── __init__.py              # Package exports
├── generate_report.py       # CLI entry point
├── report_generator.py      # Core ReportGenerator class
└── index_tickers.py         # DJIA & S&P 500 ticker lists
```

### Files Created

#### 1. `__init__.py`

```python
from .report_generator import ReportGenerator
from .index_tickers import get_index_tickers, get_test_tickers, DJIA_TICKERS, SP500_TICKERS

__all__ = [
    'ReportGenerator',
    'get_index_tickers',
    'get_test_tickers',
    'DJIA_TICKERS',
    'SP500_TICKERS',
]
```

#### 2. `index_tickers.py`

Contains 10 representative tickers per index for initial testing:

```python
# DJIA - 10 companies for testing
DJIA_TICKERS = [
    'AAPL',   # Apple - Tech, strong cash
    'MSFT',   # Microsoft - Tech, cloud growth
    'JPM',    # JPMorgan - Financials
    'JNJ',    # Johnson & Johnson - Healthcare
    'V',      # Visa - Payments
    'UNH',    # UnitedHealth - Healthcare
    'HD',     # Home Depot - Retail
    'KO',     # Coca-Cola - Consumer staples
    'CVX',    # Chevron - Energy
    'BA',     # Boeing - Industrials, cyclical
]

# S&P 500 - 10 different companies for testing
SP500_TICKERS = [
    'NVDA',   # NVIDIA - High growth, AI
    'GOOGL',  # Alphabet - Tech, advertising
    'AMZN',   # Amazon - E-commerce, cloud
    'META',   # Meta - Social, advertising
    'TSLA',   # Tesla - EV, volatile
    'XOM',    # Exxon - Energy
    'LLY',    # Eli Lilly - Pharma, growth
    'WFC',    # Wells Fargo - Banking
    'F',      # Ford - Auto, high debt
    'T',      # AT&T - Telecom, dividend
]
```

#### 3. `report_generator.py`

Core class with two modes of operation:

**Claude Code Mode** (default):
- `prepare_data(ticker)` - Fetches FMP data, returns formatted metrics
- `save_report(ticker, fiscal_year, content, ratings)` - Saves to DynamoDB

**API Mode** (requires ANTHROPIC_API_KEY):
- `generate_report(ticker)` - Full automated generation via Anthropic API

#### 4. `generate_report.py`

CLI with the following options:

```bash
# Single ticker
python -m investment_research.generate_report AAPL

# Multiple tickers
python -m investment_research.generate_report AAPL MSFT NVDA

# Index generation
python -m investment_research.generate_report --djia
python -m investment_research.generate_report --sp500

# Test tickers (AAPL, MSFT, F, NVDA)
python -m investment_research.generate_report --test

# Force refresh cached report
python -m investment_research.generate_report --refresh AAPL

# Specific fiscal year
python -m investment_research.generate_report --fiscal-year 2025 AAPL

# Dry run (show what would be processed)
python -m investment_research.generate_report --dry-run --djia

# List tickers
python -m investment_research.generate_report --list-djia
python -m investment_research.generate_report --list-sp500
```

---

## Usage Guide

### Claude Code Mode (Recommended)

This mode uses your Claude Max subscription instead of per-token API costs.

**Step 1: Prepare Data**

```python
from investment_research.report_generator import ReportGenerator

generator = ReportGenerator(use_api=False)
data = generator.prepare_data('AAPL')

print(data['metrics_context'])  # Financial data formatted for analysis
```

**Step 2: Generate Report** (Claude Code analyzes the data)

Use Claude Code to analyze the metrics_context and generate a report following the prompt template.

**Step 3: Save Report**

```python
generator.save_report(
    ticker='AAPL',
    fiscal_year=2026,
    report_content=report_markdown,  # Your generated report
    ratings={
        "debt": {"rating": "Strong", "confidence": "High", "key_factors": [...]},
        "cashflow": {"rating": "Very Strong", "confidence": "High", "key_factors": [...]},
        "growth": {"rating": "Stable", "confidence": "High", "key_factors": [...]},
        "overall_verdict": "HOLD",
        "conviction": "Medium"
    },
    features=data['features']
)
```

### API Mode (Automated)

Requires `ANTHROPIC_API_KEY` environment variable.

```python
generator = ReportGenerator(use_api=True)
report = await generator.generate_report('AAPL', force_refresh=True)
```

---

## Report Format & Structure

### Writing Style Guidelines

Reports are designed for **Millennials and Gen Z investors** with these principles:

1. **Plain English First**: Financial terms are immediately explained in simple language
2. **Fresh, Relatable Analogies**: Each report uses unique analogies (gaming, streaming, sports, cooking, etc.)
3. **Dynamic Headers**: Section titles reflect the company's specific situation
4. **Visual Indicators**: +/~/- for quick scanning
5. **Conversational Tone**: Like explaining to a smart friend
6. **Standalone Reports**: Each report is 100% self-contained (no cross-references)
7. **Valuation Context**: Based on historical data trends, not specific P/E multiples

### Required Sections

| Section | Description |
|---------|-------------|
| **TL;DR** | 2-3 sentence elevator pitch |
| **What Does [TICKER] Do?** | Plain English business description |
| **Debt Health** | Dynamic header + metrics + 5-year trajectory |
| **Cash Flow** | Dynamic header + FCF analysis + capital allocation |
| **Growth** | Dynamic header + revenue/margin trends |
| **Bull Case** | 3-4 strengths with specific metrics |
| **Bear Case** | 3-4 risks with specific concerns |
| **The Verdict** | Ratings table + target investor + conviction |

### Rating Scale

| Rating | Meaning |
|--------|---------|
| **Very Strong** | Best-in-class, sleep-well-at-night quality |
| **Strong** | Better than most, solid with minor concerns |
| **Stable** | Average, nothing special or scary |
| **Weak** | Below average, yellow flags, needs watching |
| **Very Weak** | Red flags, significant concerns |

### JSON Output Format

```json
{
  "debt": {
    "rating": "Very Strong | Strong | Stable | Weak | Very Weak",
    "confidence": "High | Medium | Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  },
  "cashflow": {
    "rating": "...",
    "confidence": "...",
    "key_factors": ["..."]
  },
  "growth": {
    "rating": "...",
    "confidence": "...",
    "key_factors": ["..."]
  },
  "overall_verdict": "BUY | HOLD | SELL",
  "conviction": "High | Medium | Low"
}
```

---

## Data Sources

### FMP API Endpoints Used

| Endpoint | Data Retrieved |
|----------|----------------|
| `/stable/balance-sheet-statement` | Debt, cash, equity, assets, liabilities |
| `/stable/income-statement` | Revenue, gross profit, operating income, net income, EPS |
| `/stable/cash-flow-statement` | Operating CF, FCF, CapEx, dividends, buybacks |
| `/stable/search-name` | Company name to ticker resolution |

**Parameters:**
- `period=quarter`
- `limit=20` (5 years of quarterly data)

### Data Flow

1. **FMP Client** fetches 20 quarters of financial data
2. **Feature Extractor** computes debt, cashflow, growth metrics
3. **Report Generator** formats data into metrics context
4. **Claude** (Code or API) generates the analysis report
5. **DynamoDB** caches the report with 120-day TTL

### Caching Strategy

| Cache | Table | TTL |
|-------|-------|-----|
| Financial data | `buffett-dev-financial-data-cache` | 90 days |
| Investment reports | `investment-reports-dev` | 120 days |
| Ticker lookups | `buffett-dev-ticker-lookup` | 30 days |

---

## Future Phases

### Phase 3: Investment Research Lambda
- Docker + Lambda Web Adapter
- Streams cached reports to frontend
- Routes follow-up questions to Bedrock agent

### Phase 4: Bedrock Follow-up Agent
- Haiku 4.5 agent for follow-up Q&A
- Action group to retrieve cached reports
- Conversational context about the analysis

### Phase 5: Frontend Updates
- Mode dropdown: "Buffett" vs "Investment Research"
- 5-point rating display in bubbles
- Follow-up chat component

### Phase 6: Terraform for New Resources
- Lambda function URLs
- Bedrock agent configuration
- IAM roles and permissions

### Phase 7: End-to-End Testing
- Report generation validation
- Streaming verification
- Follow-up chat testing

---

## Test Tickers

| Ticker | Characteristics | Test Purpose |
|--------|-----------------|--------------|
| AAPL | Strong cash, low debt, mature | Baseline - all aligned |
| MSFT | Growth + margins, cloud | Growth expert accuracy |
| F | High debt, cyclical | Debt expert sensitivity |
| NVDA | High growth, volatile | Confidence calibration |

---

## Troubleshooting

### Common Issues

**"No financial data available for TICKER"**
- Check if ticker is valid
- FMP API may not have data for this company
- Try using company name instead of ticker

**Cache miss on every request**
- Check `FINANCIAL_DATA_CACHE_TABLE` environment variable
- Verify DynamoDB table exists
- Check IAM permissions

**Report not saving**
- Check `INVESTMENT_REPORTS_TABLE` environment variable
- Verify DynamoDB table exists
- Check item size (DynamoDB has 400KB limit)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INVESTMENT_REPORTS_TABLE` | `investment-reports-dev` | Reports cache table |
| `FINANCIAL_DATA_CACHE_TABLE` | `buffett-dev-financial-data-cache` | FMP data cache |
| `FMP_SECRET_NAME` | `buffett-dev-fmp` | AWS Secrets Manager key |
| `ANTHROPIC_API_KEY` | (none) | Only for API mode |

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-05 | Phase 1 & 2 complete |
| 2026-01-05 | Added standalone reports rule |
| 2026-01-05 | Added valuation context guideline |
| 2026-01-05 | Dynamic headers and fresh analogies |
