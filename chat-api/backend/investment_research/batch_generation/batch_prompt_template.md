# Investment Report Generation - Batch Instructions

This template is used by each parallel Claude session to generate reports for its assigned batch of companies.

## AUTOMATION MODE

**You are running in FULLY AUTOMATED mode.**
- Execute every step without waiting for confirmation
- Do NOT ask for user approval at any point
- Do NOT pause between reports
- If a step fails, log the error and continue with the next ticker

## Your Assigned Companies

{BATCH_TICKERS}

(6 companies per batch, 5 batches total = 30 DJIA companies)

---

## Prerequisites

Before running this batch:

1. **Data file exists**: `djia_30_batch_data.json` (from `prepare_batch_data.py`)
2. **Prompt file exists**: `chat-api/backend/investment_research/prompts/{PROMPT_FILE_NAME}`
3. **AWS credentials configured** for DynamoDB access

---

## For Each Company

### Step 1: Load Financial Data

```python
import json

# Load pre-fetched FMP data
with open('djia_30_batch_data.json') as f:
    batch_data = json.load(f)

# Get data for specific ticker
ticker = '{TICKER}'
ticker_data = batch_data[ticker]['metrics_context']
```

### Step 2: Read System Prompt

```python
# Read the prompt template
prompt_path = 'chat-api/backend/investment_research/prompts/{PROMPT_FILE_NAME}'
with open(prompt_path) as f:
    system_prompt = f.read()
```

### Step 3: Generate Report

Using Claude Code, generate the investment report following the prompt structure:

**Part 1: Executive Summary (5 sections)**
1. TL;DR - One paragraph summary
2. What {COMPANY} Does - Business overview
3. Financial Health Score Card - Key metrics
4. Is It a Good Fit? - Investment suitability
5. The Verdict - Buy/Hold/Sell recommendation

**Part 2: Deep Dive (12 sections)**
6. Growth - Revenue and earnings trends
7. Profitability - Margins and efficiency
8. Valuation - P/E, P/B, EV/EBITDA analysis
9. Earnings Quality - Accruals and sustainability
10. Cash Flow - Operating and free cash flow
11. Debt - Leverage and coverage ratios
12. Dilution - Share count trends
13. Bull Case - Optimistic scenario
14. Bear Case - Pessimistic scenario
15. Warning Signs - Red flags to watch
16. Vibe Check - Qualitative assessment

**Part 3: Conclusion**
17. Real Talk - Final honest assessment

### Step 4: Include JSON Ratings Block

At the end of the report, include:

```json
{
  "growth": {
    "rating": "Strong|Moderate|Weak|Concerning",
    "confidence": "High|Medium|Low",
    "key_factors": ["factor1", "factor2"]
  },
  "profitability": {
    "rating": "Exceptional|Strong|Average|Weak",
    "confidence": "High|Medium|Low",
    "key_factors": ["factor1", "factor2"]
  },
  "debt": {
    "rating": "Fortress|Healthy|Manageable|Concerning|Critical",
    "confidence": "High|Medium|Low",
    "key_factors": ["factor1", "factor2"]
  },
  "overall_verdict": "Strong Buy|Buy|Hold|Sell|Strong Sell",
  "conviction": "High|Medium|Low"
}
```

### Step 5: Save to DynamoDB

Write the report to a temp file, then save via Python:

```bash
# Write report to temp file (done via Write tool)
# Then save to DynamoDB:
cd {PROJECT_ROOT}/chat-api/backend && python3 -c "
import sys; sys.path.insert(0, '.')
from investment_research.report_generator import ReportGenerator
generator = ReportGenerator(prompt_version={PROMPT_VERSION})
report_content = open('/tmp/{TICKER}_report.md').read()
generator.save_report_sections('{TICKER}', 2026, report_content)
"
```

### Step 6: Confirm

Print: `✓ {TICKER} saved`

**Immediately proceed to the next ticker. Do not wait for confirmation.**

---

## Completion Signal

When all 6 reports in your batch are saved:

```
BATCH COMPLETE: {BATCH_TICKERS}
```

---

## Batch Assignments

| Batch | Window | Companies |
|-------|--------|-----------|
| 1 | 0 | AAPL, AMGN, AXP, BA, CAT, CRM |
| 2 | 1 | CSCO, CVX, DIS, DOW, GS, HD |
| 3 | 2 | HON, IBM, INTC, JNJ, JPM, KO |
| 4 | 3 | MCD, MMM, MRK, MSFT, NKE, PG |
| 5 | 4 | TRV, UNH, V, VZ, WBA, WMT |

---

## Error Handling

If a report fails to generate or save:

1. Log the error: `✗ {TICKER}: {error message}`
2. **Continue immediately** with the next ticker
3. Report failures at batch completion:
   ```
   BATCH COMPLETE: AAPL,AMGN,AXP,BA,CAT,CRM
   Failed: BA (DynamoDB write error), CRM (parse error)
   ```

---

## Estimated Time

- ~5-7 minutes per report
- ~35-40 minutes per batch (6 reports)
- ~35-40 minutes total (5 parallel batches)
