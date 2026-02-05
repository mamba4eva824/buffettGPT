# Investment Research Changelog

All notable changes to the investment research module are documented here.

---

## [2026-01-24] Frontend E2E Test Infrastructure

**Summary:** Implemented P0 test suite with **92 tests passing**:
- 43 reducer state management tests
- 21 SSE connection handling tests
- 28 event parsing tests

---

## [2026-01-10] V2 Section-Based DynamoDB Schema

### Problem
The v1 DynamoDB schema stored entire reports as a single blob (400KB+ per report), causing slow initial load times and no progressive loading capability.

### Solution
Implemented section-based schema for v2:

| section_id | Contents |
|------------|----------|
| `00_executive` | ToC + ratings + 5 executive sections |
| `06_growth` - `17_realtalk` | 12 individual detailed sections |

**Key Benefits:**
1. **Fast Initial Load** — Single GetItem returns ToC + ratings + executive summary
2. **Progressive Loading** — Detailed sections fetched on-demand
3. **SSE Streaming** — Stream sections as they're retrieved

### New API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/report/{ticker}/executive` | GET | Combined executive item |
| `/report/{ticker}/toc` | GET | ToC + ratings only |
| `/report/{ticker}/section/{section_id}` | GET | Individual section |
| `/report/{ticker}/stream` | GET | SSE stream all sections |

---

## [2026-01-09] Prompt v4.8 Release — Executive Summary First

### Problem
Previous prompts required readers to scroll through detailed analysis before reaching the verdict.

### Solution
Created v4.8 hybrid prompt with three major innovations:

**1. Executive Summary First (~600 words)**
Verdict visible immediately without scrolling.

**2. Dynamic Headers**
Every section header must be unique to the ticker's story:

| Generic (BAD) | Dynamic (GOOD) |
|---------------|----------------|
| "Growth Analysis" | "From 19% to 12%: The Slowdown Story" |
| "Debt Analysis" | "The $2B War Chest" |

**3. Simplified Terminology**
All Wall Street jargon translated to plain English.

### Version Comparison

| Version | Lines | Structure | Default |
|---------|-------|-----------|---------|
| v4.5 | ~320 | Analysis first | No |
| v4.7 | ~450 | Educational | No |
| **v4.8** | ~350 | **Executive summary first** | **YES** |

---

## [2026-01-09] Report Caching — Single Version Per Ticker

### Problem
Multiple report versions accumulating in DynamoDB for the same ticker.

### Solution
Updated `save_report()` to delete existing reports before saving new ones.

---

## [2026-01-08] Fiscal Year Aggregation Bug Fix

### Problem
The `_aggregate_annual_data()` method was incorrectly grouping fiscal year quarters by calendar year.

### Solution
Changed fiscal year extraction to prioritize FMP's `fiscalYear` field.

**Impact:**
| Metric | Before Fix | After Fix |
|--------|------------|-----------|
| OKTA FY2025 Net Income | $195M (wrong) | $28M (correct) |

---

## [2026-01-08] Total Liquidity Bug Fix

### Problem
Reports were understating cash positions for companies with substantial short-term investments.

### Solution
Created `get_total_liquidity()` helper that includes cash + short-term investments.

**Example - OKTA:**
- Before: $645M cash
- After: $2.46B total liquidity

---

## [2026-01-08] Prompt v4.4 — Plain English Table Headers

### Problem
Table column headers still used financial jargon.

### Solution
Added TABLE HEADER TRANSLATIONS section:

| Financial Term | Plain English |
|----------------|---------------|
| Total Liquidity | Cash & Savings |
| Net Debt | Debt After Savings |
| Debt/Equity | Borrowing Ratio |
| Interest Coverage | Loan Safety |
| FCF Margin | Cash Keep Rate |

---

## [2026-01-08] Prompt v4.3 — Full Translation Table Restored

### Problem
v4.2's streamlining reduced translation terms from 31 to 12.

### Solution
Created v4.3 combining v4.2's structure with v4's full 31-term translation table.

---

## Template for Future Entries

```markdown
## [YYYY-MM-DD] Change Title

### Problem
Brief description of the issue.

### Solution
What was changed and why.

### Files Modified
- `filename.py` — description of change

### Impact
Who/what is affected by this change.
```
