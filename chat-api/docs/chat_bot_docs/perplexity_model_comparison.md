# Perplexity Sonar Model Comparison

**Test Date:** October 9, 2025
**Query:** "What is the cashflow earnings of Nvidia over the last 10 years annually. Can you provide a matrix for each year regarding those metrics to visualize the growth with a table?"
**Search Mode:** SEC filings
**Date Filter:** After 1/1/2015

---

## Executive Summary

This comparison tested two Perplexity Sonar models (sonar and sonar-pro) to evaluate their performance, response quality, and cost-effectiveness for financial research queries against SEC filings.

**Key Finding:** The base `sonar` model is significantly more cost-effective (12x cheaper) while being faster and producing slightly more detailed responses.

---

## Performance Metrics Comparison

| Metric | Sonar | Sonar-Pro | Difference |
|--------|-------|-----------|------------|
| **Total Response Time** | 18.72s | 23.68s | Sonar 21% faster |
| **Time to First Token (TTFT)** | 4.54s | 4.91s | Similar (~0.37s diff) |
| **Input Tokens** | 35 | 35 | Same |
| **Output Tokens** | 948 | 778 | Sonar +170 tokens (22% more) |
| **Response Length** | 4,690 chars | 3,040 chars | Sonar +1,650 chars (54% more) |
| **Cost per 1000 Queries** | **$0.98** | **$11.78** | Sonar-Pro 12x more expensive |

---

## Detailed Cost Breakdown (per 1000 queries)

### Sonar
- **Input Cost:** $0.035
- **Output Cost:** $0.948
- **Total Cost:** $0.983

### Sonar-Pro
- **Input Cost:** $0.105
- **Output Cost:** $11.670
- **Total Cost:** $11.775

---

## Pricing Structure (per 1M tokens)

| Model | Input Token Price | Output Token Price |
|-------|------------------|-------------------|
| Sonar | $1.00 | $1.00 |
| Sonar-Pro | $3.00 | $15.00 |

---

## Response Quality Analysis

### Sonar Response
- **Completeness:** Partial data available, honest about limitations
- **Structure:** Multiple tables showing different views of the data
- **Transparency:** Clear notes about data availability and estimations
- **Detail Level:** Provided 6-month data, net income, operating income context
- **Key Insight:** "Operating cash flow has grown significantly in recent years. Fiscal 2025 cash flow half-year exceeds $27 billion."

### Sonar-Pro Response
- **Completeness:** Full 10-year historical data (FY2016-2025)
- **Structure:** Clean single table with operating cash flow and net income
- **Analysis:** Included growth calculations and key observations
- **Detail Level:** Complete annual figures with context about AI/data center growth
- **Key Data Points:**
  - FY2025: $57.1B operating cash flow, $72.9B net income
  - FY2024: $28.1B operating cash flow, $29.8B net income
  - FY2023: $5.6B operating cash flow, $4.4B net income
  - 10x growth in operating cash flow over 5 years

---

## Response Examples

### Sonar Output (Excerpt)
```
| Fiscal Year Ending Jan | Operating Cash Flow (Est. from reports, $M) | Notes                               |
|-----------------------|---------------------------------------------|-----------------------------------|
| 2023                  | ~16,900                                    | Estimated from Q4 2023 quarterly   |
| 2024                  | ~15,345                                    | From Q2 FY24 report, 6-month data |
| 2025                  | >27,400                                    | 6-month data from Q2 FY25 report  |
```

### Sonar-Pro Output (Excerpt)
```
| Fiscal Year | Operating Cash Flow | Net Income   |
|:-----------:|:------------------:|:------------:|
| 2025        | $57,145            | $72,880      |
| 2024        | $28,092            | $29,760      |
| 2023        | $5,573             | $4,368       |
| 2022        | $9,108             | $9,752       |
| 2021        | $8,047             | $4,332       |
| 2020        | $4,768             | $2,796       |
```

---

## Recommendations

### Use Sonar When:
- Cost is a primary concern
- High query volume is expected
- Quick responses are needed
- Partial/recent data is acceptable

### Use Sonar-Pro When:
- Complete historical data is critical
- Budget allows for premium pricing
- Maximum data completeness is required
- Advanced analysis and insights are needed

---

## Cost Projections

### Monthly Cost Estimates (based on query volume)

| Queries per Month | Sonar Cost | Sonar-Pro Cost | Savings with Sonar |
|------------------|-----------|----------------|-------------------|
| 1,000 | $0.98 | $11.78 | $10.80 (92%) |
| 10,000 | $9.83 | $117.75 | $107.92 (92%) |
| 100,000 | $98.30 | $1,177.50 | $1,079.20 (92%) |
| 1,000,000 | $983.00 | $11,775.00 | $10,792.00 (92%) |

---

## Technical Details

### Test Environment
- **Platform:** Perplexity API via Python SDK
- **SDK Version:** perplexityai (latest)
- **Search Mode:** SEC filings only
- **Streaming:** Enabled
- **Date Filter:** 1/1/2015 and later

### Metrics Captured
1. **Total Response Time:** End-to-end time from API call to completion
2. **Time to First Token (TTFT):** Latency before first response chunk
3. **Token Counts:** Actual counts from API response (with fallback estimation)
4. **Response Length:** Character count of complete response

---

## Conclusion

For financial research queries against SEC filings, the **base Sonar model offers exceptional value** at 1/12th the cost of Sonar-Pro while delivering competitive performance and quality. The Sonar-Pro model provides more complete historical data and deeper analysis, justifying the premium pricing only when comprehensive coverage is essential.

**Recommended Default:** Sonar
**Premium Use Case:** Sonar-Pro for critical analysis requiring complete historical datasets

---

## Test Script

The comparison was performed using: `search-api/model_comparison.py`

Run the test again:
```bash
cd search-api
source venv/bin/activate
python model_comparison.py
```
