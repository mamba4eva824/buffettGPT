# Investment Research Changelog

All notable changes to the investment research module are documented here.

---

## [2026-01-09] Report Caching — Single Version Per Ticker

### Problem
The `save_report()` method was saving reports with `ticker` + `fiscal_year` as the composite key, allowing multiple versions of reports to accumulate in DynamoDB for the same ticker.

### Solution
Updated `save_report()` to delete any existing reports for a ticker before saving the new one. This ensures only 1 version exists per ticker in the `investment-reports-{env}` table.

**New behavior:**
1. Query for all existing reports for the ticker
2. Delete each existing report
3. Save the new report

**New method added:** `_delete_existing_reports(ticker)` — Queries and deletes all reports for a given ticker.

### Files Modified
- `report_generator.py` — Updated `save_report()`, added `_delete_existing_reports()`

### Console Output
When saving a report that replaces an existing one:
```
  Saving report for OKTA (prompt v4.8) to DynamoDB...
  Deleted 1 existing report(s) for OKTA
  Report saved for OKTA (prompt v4.8)
```

### Impact
- **No stale reports** — Each ticker has exactly 1 report in the cache
- **Automatic cleanup** — Old reports are deleted before new ones are saved
- **No table schema changes** — Works with existing DynamoDB table structure

---

## [2026-01-09] Prompt v4.8 Release — Executive Summary First + Dynamic Headers [RECOMMENDED]

### Problem
Previous prompts (v4.5-v4.7) required readers to scroll through detailed analysis before reaching the verdict. Additionally:
- Table headers and section headers were often generic across reports
- Terminology was still too financial for non-finance audiences
- No hybrid between v4.5's quick-scan tools and v4.7's educational depth

### Solution
Created v4.8 hybrid prompt (~350 lines) with three major innovations:

**1. Executive Summary First (~600 words)**
Verdict visible immediately without scrolling:
- TL;DR (2-3 sentences)
- What {ticker} Actually Does
- Quick Health Check (consolidated dashboard)
- Investment Fit Assessment table
- Rating Table with all 6 categories
- Real Talk verdict

**2. Dynamic Headers (CRITICAL — Prevents Cookie-Cutter Reports)**
Every section AND table header must be unique to {ticker}'s story:

| Section | Generic (BAD) | Dynamic (GOOD) |
|---------|---------------|----------------|
| Growth | "Growth Analysis" | "From 19% to 12%: The Slowdown Story" |
| Debt | "Debt Analysis" | "The $2B War Chest" or "The $50B Mountain" |
| Profitability | "Profitability Section" | "From Red to Black: The $172M Turnaround" |

Table headers also customized:
- Net cash: `Year | What They Owe | Cash in Bank | Extra Cash After Debt ✅`
- High debt: `Year | The Debt Mountain | Cash Available | Still Owe After Savings`

**3. Simplified Terminology**
Changed jargon translation approach from "Say Instead" to "Wall Street Says | You Say":

| Wall Street Says | You Say |
|------------------|---------|
| Free Cash Flow | money left over |
| OCF/Net Income | is the cash real? |
| Debt-to-Equity | how much they borrowed |
| Stock-Based Compensation | paying employees in stock |

Quick Health Check uses questions instead of metrics:
- "How fast are they growing?" instead of "Growth Speed"
- "Is the money real?" instead of "Cash Quality"
- "Is your slice shrinking?" instead of "Dilution Check"

### Features Inherited

**From v4.5:**
- 6-Point Vibe Check table
- Warning Signs Checklist
- Emoji flag system (🟢🟡🟠🔴)
- SBC Risk Scale thresholds

**From v4.7:**
- Investment Fit Assessment table
- $100/Month projections
- Net Cash Position format (positive display)
- Business analogy framework

### Files Modified
- `prompts/investment_report_prompt_v4_8.txt` (NEW)
- `report_generator.py` — Added v4.7, v4.8 to PROMPT_VERSIONS; set v4.8 as default

### Version Comparison
| Version | Lines | Structure | Default |
|---------|-------|-----------|---------|
| v4.5 | ~320 | Analysis first, verdict at end | No |
| v4.6 | ~280 | Dashboard consolidation | No |
| v4.7 | ~450 | Extensive depth, educational | No |
| **v4.8** | ~350 | **Executive summary first** | **YES** |

### Target Metrics
- ~2,550 words total
- ~10 minute read time
- Verdict visible within first screen scroll

### Quality Check Additions
```markdown
**Dynamic Headers (CRITICAL — prevents cookie-cutter reports):**
- [ ] EVERY section header includes {ticker}'s actual numbers or situation
- [ ] Section headers would NOT work for a different company (uniqueness test)
- [ ] Table headers are customized to {ticker}'s story (not generic templates)
```

### Impact
- **Immediate Verdict** — Readers see recommendation without scrolling through 2,000 words
- **No Cookie-Cutter Reports** — Dynamic headers force unique content per ticker
- **True Accessibility** — Questions and everyday words replace all Wall Street jargon
- **Best of Both Worlds** — Quick-scan tools (v4.5) + educational depth (v4.7)

---

## [2026-01-09] Prompt v4.7 Release — Extensive Educational Depth

### Problem
v4.6 consolidated dashboards but lacked:
- Educational context for budget-conscious investors
- $100/month investment projections
- Investment Fit Assessment (who should/shouldn't buy)
- Detailed explanations of why metrics matter

### Solution
Created v4.7 prompt (~450 lines) with extensive educational content:

**1. Investment Fit Assessment Table**
| Investor Type | Fit? | Why |
|---------------|------|-----|
| Growth seekers | 🟡 | Slowing from 19% to 12% |
| Income investors | ❌ | No dividends |
| Value hunters | 🟡 | Trading at premium |
| Long-term holders | ✅ | Strong fundamentals |

**2. $100/Month Projections**
"If you invest $100/month and {ticker} keeps growing at X%..."

**3. Net Cash Position Display**
For companies with more savings than debt, show positive numbers:
- Before: "Net Debt: -$2.0B"
- After: "Net Cash Position: $2.0B ✅"

**4. "Who You're Writing For" Brief**
Added context about target audience (budget-conscious millennials/Gen Z investing $100-500/month)

### Files Modified
- `prompts/investment_report_prompt_v4_7.txt` (NEW)
- `report_generator.py` — Added v4.7 to PROMPT_VERSIONS

### Version Comparison
| Version | Lines | Educational Depth | Investment Fit |
|---------|-------|-------------------|----------------|
| v4.6 | ~280 | Moderate | No |
| **v4.7** | ~450 | **Extensive** | **Yes** |

### Impact
- Reports provide more educational value for newer investors
- Clear guidance on who should/shouldn't consider the stock
- $100/month framing makes investing feel accessible

---

## [2026-01-09] Prompt v4.6 Update — Streamlined Analogy Guidance (Middle Ground)

### Problem
v4.2 had minimal analogy guidance (3 lines), while v4 had overly prescriptive requirements (~60 lines with mandatory counting). Neither approach was ideal:
- v4.2: Too brief, reports might lack analogies
- v4: Over-prescriptive, limits creative freedom

### Solution
Middle ground approach (~25 lines) that provides guidance without counting requirements:

**What's included:**
- 4 Gen Z/Millennial categories in a compact table (Streaming, Payment Apps, Side Hustles, Gaming)
- Use cases for each category
- Example analogies for each
- Dynamic application examples (good vs bad for specific tickers)
- Uniqueness test

**What's removed:**
- "Required Analogies Per Section" table with "1 minimum" counts
- "MANDATORY: Use at least 2 from EACH category"
- Quality Check counting requirements

### Files Modified
- `prompts/investment_report_prompt_v4_6.txt` (streamlined from ~50 to ~25 lines)
- `changelog/CHANGELOG.md`

### Comparison
| Approach | Lines | Prescriptiveness |
|----------|-------|------------------|
| v4.2 | ~3 | Too brief |
| v4 | ~60 | Over-prescriptive |
| **v4.6** | **~25** | **Balanced guidance** |

### Impact
Reports have clear analogy guidance with creative freedom — no mandatory minimums to hit.

---

## [2026-01-09] Prompt v4.6 Release — Dashboard Consolidation

### Problem
v4.5 had three overlapping dashboard/checklist components:
1. **Quick Health Dashboard** (Section 2) — 7 rows, simple emoji + one-liner
2. **6-Point Vibe Check** (guidance at end) — 6 rows, detailed trend analysis
3. **Warning Signs Checklist** (Section 12) — 8 rows, redundant with above

This created redundancy and inconsistent coverage (Vibe Check missing "Debt Situation").

### Solution
Consolidated all three into a streamlined structure:

**1. New Section 2: Quick Health Check**
- Merged Quick Health Dashboard + 6-Point Vibe Check
- 7 rows covering: Growth Speed, Streak Length, Margin Direction, Cash Reality, Debt Situation, Earnings Reality, Dilution Check
- **Dynamic header only in output** — no "Quick Health Check" label
- Examples: "OKTA's Profitability Turnaround Scorecard", "COST's Retail Powerhouse Scorecard"
- Flag system: 🟢 Looking good | 🟡 Watch this | 🟠 Getting worse | 🔴 Red flag

**2. Warning Signs → Merged into The Verdict**
- Removed separate Warning Signs Checklist (Section 12)
- Added "Dilution" row to Verdict's rating table
- Verdict now covers all 6 categories: Growth, Profitability, Earnings Quality, Cash Flow, Debt Health, Dilution

**3. Updated JSON Block**
- Added `dilution` object with rating, confidence, dilution_pct, key_factors

### Files Modified
- `prompts/investment_report_prompt_v4_6.txt` (new)
- `report_generator.py` (added v4.6 to PROMPT_VERSIONS)

### Section Count
- **v4.5:** 13 sections
- **v4.6:** 12 sections (Warning Signs merged into Verdict)

### Version Comparison
| Version | Sections | Dashboards | Warning Signs |
|---------|----------|------------|---------------|
| v4.5 | 13 | 2 (Dashboard + Vibe Check) | Separate section |
| **v4.6** | 12 | 1 (Quick Health Check) | Merged into Verdict |

### Impact
- **No redundancy** — Single consolidated health check at top
- **Better coverage** — Added "Debt Situation" (missing from Vibe Check)
- **Dynamic headers** — Report shows "{ticker}'s [Story] Scorecard", not generic label
- **Streamlined flow** — Readers see health check once, not three times in different formats

---

## [2026-01-09] Removed Repetitive Section Framing — All Hooks Now Dynamic

### Problem
Technical sections (Earnings Quality, Cash Flow, Debt, Dilution) had repetitive, static framing:
- "**This section answers:**" — same in every section
- "**Why this matters:**" — same in every section
- Static bullet point explanations — identical boilerplate

This made reports feel formulaic and didn't leverage {ticker}-specific context.

### Solution
Replaced static framing with dynamic, {ticker}-specific requirements:

**Before (static):**
```markdown
### 6. Earnings Quality Section
**This section answers:** "Is this profit real..."
**Why this matters (explain in your own words):**
- GAAP = official profit reported to the SEC
- "Adjusted" = company's own math...
```

**After (dynamic):**
```markdown
### 6. Earnings Quality Section
**Dynamic header** that reflects {ticker}'s GAAP vs Adjusted story
(e.g., "The 597% Gap" or "Clean Books: {ticker}'s Profit Is What It Says")

**Open with a {ticker}-specific hook:**
- High SBC: "When {ticker} pays employees in stock instead of cash..."
- Clean books: "{ticker} is refreshingly old-school..."
```

### Files Modified
- `prompts/investment_report_prompt_v4_5.txt` — Rewrote all 4 technical sections with dynamic framing

### Impact
- **No more formulaic openers** — Each section starts with {ticker}'s specific story
- **Varied headers** — "The Fortress Balance Sheet" vs "The $50B Mountain" vs "Living Paycheck to Paycheck"
- **Example-driven guidance** — Shows different approaches for different company types
- **Better reader engagement** — Reports feel custom-written, not template-filled

---

## [2026-01-09] 6-Point Vibe Check Converted to Table Format

### Problem
The 6-Point Vibe Check was formatted as nested bullet points with subsections, which was inconsistent with the table-focused approach in other sections and harder to scan quickly.

### Solution
Converted the 6-Point Vibe Check to a table format with dynamic headers.

**New Structure:**
| {ticker}'s Story | The Trend | Flag | The Verdict |
|------------------|-----------|------|-------------|
| Growth Speed | X% → Y% | 🟢/🟡/🟠/🔴 | Analysis |
| Streak Length | Revenue pattern | ... | ... |
| Margin Direction | Margin trend | ... | ... |
| Cash Reality | Cash quality score | ... | ... |
| Earnings Reality | GAAP vs Adjusted gap | ... | ... |
| Dilution Check | Share count change | ... | ... |

**Dynamic Header Guidance:**
- Headers should incorporate {ticker}'s actual metrics
- Example: "{ticker}'s 19% → 12% Slowdown" instead of generic "Growth"

**Added green flag (🟢)** for "Looking good" — original only had yellow/orange/red.

### Files Modified
- `prompts/investment_report_prompt_v4_5.txt` — Rewrote Vibe Check as table with dynamic headers

### Impact
- **Consistent format** — All analytical sections now use tables
- **Faster scanning** — Readers see all 6 checks at a glance
- **Dynamic across reports** — Headers customize to each company's story

---

## [2026-01-09] Latest Earnings Date Header

### Problem
Reports did not indicate the freshness of the underlying financial data, making it unclear when the latest earnings data was from. Users had to scan through quarterly tables to determine data currency.

### Solution
Added a "DATA FRESHNESS" header at the top of the metrics context showing the latest earnings period end date.

**Example Output:**
```
## DATA FRESHNESS
Data through Q3 FY2025 ending Oct 31, 2024
```

**Files Modified:**
- `report_generator.py` — Added `_get_latest_earnings_info()` helper method and header output in `_format_metrics_for_prompt()`

**Key Features:**
1. Compares dates across income_statement, balance_sheet, and cash_flow to find most recent
2. Formats date in plain English (e.g., "Oct 31, 2024")
3. Uses FMP's `fiscalYear` field to correctly handle non-calendar fiscal years (OKTA Jan 31, AAPL Sep 27, MSFT Jun 30)
4. Gracefully handles missing fields or empty data

### Verification
Test with:
- **AAPL** (Sep fiscal year end) — Shows correct FY designation
- **OKTA** (Jan 31 fiscal year end) — Shows correct FY designation
- **JPM** (Dec 31 calendar year) — Shows calendar-aligned FY

### Impact
1. **Immediate Data Currency** — Users see at a glance how fresh the data is
2. **All Prompt Versions** — Header appears in metrics_context for all v4.x prompts
3. **No Prompt Changes Required** — Uses existing {metrics_context} placeholder

---

## [2026-01-09] Prompt v4.5 Release — Restored Structure + Gen Z Accessibility

### Problem
v4.4's streamlined prompt (~253 lines) lost several high-value structural elements from v4 (~703 lines) that helped ensure consistent, detailed reports:
- No row count guidance → inconsistent table depths
- No "when to use" guidance for dynamic vs standard headers
- No explicit pre-rating trend analysis framework
- No defined rating scale → inconsistent grades

### Solution
Created v4.5 (~310 lines) that restores 4 key sections from v4, rewritten in Gen Z/Millennial-friendly language:

**1. HOW TO BUILD TABLES**
- Max 6 columns guidance
- Row counts: 5 years for trends, 4-6 quarters for momentum, 3-4 for snapshots
- Template examples with plain English headers

**2. WHEN TO GET CREATIVE WITH HEADERS**
- Plain headers = data tables (consistency)
- Creative headers = summary tables (storytelling)
- Dynamic header formula with {ticker}-specific examples

**3. THE 6-POINT VIBE CHECK**
Pre-rating framework covering:
1. Is Growth Speeding Up or Slowing Down?
2. How Many Quarters in a Row?
3. Are Profits Getting Fatter or Thinner?
4. Is the Cash Actually Showing Up?
5. How Real Are These "Profits"?
6. Is Your Ownership Shrinking?

Plus severity guide (Yellow/Orange/Red flags)

**4. "THIS SECTION ANSWERS" FRAMING**
Each technical section now starts with a plain-English question it answers:
- Earnings Quality: "Is this profit real, or is the company making themselves look better than they are?"
- Cash Flow: "Is the money actually hitting their bank account, or is it just paper profits?"
- Debt: "Can this company pay its bills, or could debt become a problem?"
- Dilution: "Is the company giving away so much stock that my ownership is shrinking?"

**5. SBC RISK SCALE**
Added explicit thresholds for stock compensation assessment:
- Normal (<5%) / Elevated (5-15%) / High (>15%) / Very High (>20%)

**6. CAPITAL ALLOCATION REQUIREMENT**
Cash Flow section now requires explaining what the company DOES with cash (dividends, buybacks, debt paydown, reinvestment)

### Files Modified
- `prompts/investment_report_prompt_v4_5.txt` (new)
- `report_generator.py` (added v4.5 to PROMPT_VERSIONS)

### Version Comparison
| Version | Lines | Key Features |
|---------|-------|--------------|
| v4.4 | ~253 | Plain English headers, LTM timeframe fix |
| **v4.5** | ~320 | + Table structure, + Vibe check, + "Why this matters" framing, + SBC scale |
| v4 | ~703 | Full verbose (too long, dilution risk) |

### Impact
- **Consistent table structure** — Row counts enforced
- **Pre-rating analysis** — 6-point framework ensures thorough trend review
- **"Why this matters" framing** — Each technical section explains its purpose in plain English
- **SBC Risk Scale** — Clear thresholds (Normal/Elevated/High/Very High)
- **Capital allocation context** — Reports now explain what companies DO with their cash
- **Gen Z accessible** — All content uses casual, jargon-free language with dynamic analogies

---

## [2026-01-08] Fiscal Year Aggregation Bug Fix

### Problem
The `_aggregate_annual_data()` method in `report_generator.py` was incorrectly calculating annual figures for companies with non-calendar fiscal years.

**Root Cause:** Lines 339, 348, and 354 used `calendarYear` field (which FMP returns as N/A for most companies), then fell back to extracting the year from the `date` string. This caused fiscal year quarters to be grouped by calendar year instead of fiscal year.

**Example - OKTA (Fiscal Year ends January 31):**
- Q1 FY2025 (Apr 30, 2024) was grouped under "2024"
- Q2 FY2025 (Jul 31, 2024) was grouped under "2024"
- Q3 FY2025 (Oct 31, 2024) was grouped under "2024"
- Q4 FY2025 (Jan 31, 2025) was grouped under "2025"

Result: FY2025 was split across two calendar years, producing incorrect annual totals.

**Impact on Reports:**
| Metric | Before Fix (Wrong) | After Fix (Correct) |
|--------|-------------------|---------------------|
| OKTA FY2025 Net Income | $195M (TTM) | $28M |
| OKTA FY2025 Revenue | $2.80B | $2.61B |

### Solution
Changed fiscal year extraction to prioritize FMP's `fiscalYear` field, which correctly identifies the fiscal year regardless of calendar date.

**Files Modified:** `report_generator.py`

**Lines Changed:** 339, 348, 354

**Before:**
```python
year = stmt.get('calendarYear', stmt.get('date', 'Unknown')[:4] if stmt.get('date') else 'Unknown')
```

**After:**
```python
year = stmt.get('fiscalYear') or stmt.get('calendarYear') or (stmt.get('date', 'Unknown')[:4] if stmt.get('date') else 'Unknown')
```

### Verification
Tested with:
- **OKTA** (Jan 31 fiscal year end) — FY2025 now correctly shows $28M net income
- **JPM** (Dec 31 calendar year end) — Still works correctly, no regression

### Why This Matters
1. **Data Accuracy** — Reports now reflect actual fiscal year performance, matching official SEC filings
2. **All Companies Affected** — Any company with non-calendar fiscal year was potentially showing incorrect annual totals (AAPL, MSFT, OKTA, etc.)
3. **Audit Grade Compliance** — Investment reports must use correct fiscal year boundaries to be credible

---

## [2026-01-08] Total Liquidity Bug Fix (Cash + Short-term Investments)

### Problem
Reports were significantly understating cash positions for companies that hold substantial short-term investments (T-bills, money market funds, marketable securities).

**Root Cause:** The code only used `cashAndCashEquivalents` field, ignoring `shortTermInvestments` which are nearly as liquid as cash.

**Example - OKTA (Q3 FY2026):**
- Report showed: $645M cash
- Actual total liquidity: $2.46B (Cash: $645M + ST Investments: $1.82B)

This caused the "fortress balance sheet" assessment to be significantly understated.

### Solution
Created `get_total_liquidity()` helper function that captures the full liquidity picture:
1. Prefers FMP's `cashAndShortTermInvestments` field if available
2. Falls back to `cashAndCashEquivalents` + `shortTermInvestments`
3. Final fallback to just `cashAndCashEquivalents`

**Files Modified:**
- `report_generator.py`
- `prompts/investment_report_prompt_v4_2.txt`

**Changes:**
1. Added `get_total_liquidity()` helper function (lines 45-72)
2. Updated Balance Sheet Trend table to show "Liquidity*" instead of "Cash"
3. Updated Current Quarter Snapshot to show total liquidity with breakdown
4. Updated Debt Health Trajectory table to use total liquidity
5. All net debt calculations now use total liquidity
6. Updated v4.2 prompt translation table with "Liquidity" term
7. Updated v4.2 prompt Debt Section to explain liquidity for fortress assessments

**Before:**
```python
cash = bs.get('cashAndCashEquivalents', 0)
```

**After:**
```python
liquidity = get_total_liquidity(bs)  # Cash + short-term investments
```

### Verification
Tested with OKTA:
- **Before fix:** Cash Position: $645M
- **After fix:** Total Liquidity: $2.5B (Cash: $645M + ST Investments: $1.8B)

### Impact
1. **Accurate "Fortress" Assessment** — Reports now reflect true liquidity strength
2. **Correct Net Debt** — Net debt calculations use full liquidity, not just cash
3. **All Tech Companies Affected** — Many tech companies (AAPL, MSFT, OKTA, etc.) hold significant short-term investments
4. **Audit Grade Compliance** — Professional investment analysis must include all near-cash assets

### Why This Matters for OKTA Specifically
With $2.46B in total liquidity vs $423M debt, OKTA has:
- **Net cash position:** $2.04B (not the previously reported $222M)
- This enabled their $1B share buyback authorization in January 2026

---

## [2026-01-08] Prompt v4.3 Release — Full Translation Table Restored

### Problem
v4.2's streamlining reduced the translation table from 31 terms to 12, causing accessibility regression:

| Issue | v4.2 (Regressed) | v4.3 (Fixed) |
|-------|------------------|--------------|
| Translation terms | 12 | 31 |
| "Liquidity" | "near-cash investments" | "cash and savings combined" |
| Missing terms | 19 (OCF, ROE, EBITDA, etc.) | All restored |

**Key Regressions Identified:**
- "savings" replaced with technical "liquidity"
- "near-cash investments" used instead of everyday language
- Lost translations for: OCF, ROE, ROIC, CapEx, Working Capital, EBITDA, Current Ratio, EPS, GAAP, Non-GAAP, Dilution, Short/Long-term Debt

### Solution
Created v4.3 prompt that combines:
1. **v4.2's streamlined structure** (~220 lines vs v4's 703 lines)
2. **v4's full 31-term translation table** for comprehensive jargon coverage
3. **Restored accessible language** for liquidity: "cash and savings combined"

### Files Modified
- `prompts/investment_report_prompt_v4_3.txt` (new)
- `report_generator.py` (added v4.3 to PROMPT_VERSIONS)

### Key Translation Table Additions (v4.2 → v4.3)
| Term | v4.2 | v4.3 |
|------|------|------|
| Total Liquidity | "near-cash investments" | "cash and savings they can tap quickly" |
| Operating Cash Flow | (missing) | "cash from running the business" |
| ROE | (missing) | "return on owner's money" |
| EBITDA | (missing) | "operating profits (before loans & accounting)" |
| Current Ratio | (missing) | "short-term bill-paying power" |
| GAAP | (missing) | "official accounting rules" |
| Non-GAAP/Adjusted | (missing) | "company's own math" |
| Dilution | (missing) | "your slice gets smaller" |

### Version Comparison
| Version | Lines | Translations | Use Case |
|---------|-------|--------------|----------|
| v4.1 | 703 | 31 | Verbose, higher dilution risk |
| v4.2 | 194 | 12 | Too streamlined, accessibility gaps |
| **v4.3** | 220 | 31 | **Best of both: streamlined + comprehensive** |

### Impact
- Reports generated with v4.3 will have more consistent plain-English translations
- Enables A/B testing between v4.2 and v4.3 to measure output quality
- v4.3 is now the recommended version for production

---

## [2026-01-08] Prompt v4.4 Release — Plain English Table Headers

### Problem
v4.3 had comprehensive in-text translations, but table column **headers** still used financial jargon:

| Issue | v4.3 Headers | v4.4 Headers |
|-------|--------------|--------------|
| Liquidity column | "Liquidity*" or "Total Liquidity" | "Cash & Savings" |
| Net debt column | "Net Debt" | "Debt After Savings" |
| D/E ratio column | "D/E" or "Debt/Equity" | "Borrowing Ratio" |
| Interest coverage | "Interest Cov" | "Loan Safety" |
| FCF margin column | "FCF Margin" | "Cash Keep Rate" |
| OCF/NI column | "OCF/NI" | "Cash Quality" |

**User Feedback:** "Non-financial literate people won't understand what liquidity is" — table headers need to be as accessible as the explanatory text.

### Solution
Created v4.4 with explicit **TABLE HEADER TRANSLATIONS** section:

```markdown
### TABLE HEADER TRANSLATIONS (CRITICAL)
**Use plain English for ALL table column headers.**

| Financial Term | Use This Header Instead |
|----------------|------------------------|
| Total Liquidity | Cash & Savings |
| Net Debt | Debt After Savings |
| Debt/Equity | Borrowing Ratio |
| Interest Coverage | Loan Safety |
| FCF Margin | Cash Keep Rate |
| OCF/NI | Cash Quality |
| ... | ... |
```

Also includes explicit correct/incorrect table examples to guide the LLM.

### Files Modified
- `prompts/investment_report_prompt_v4_4.txt` (new)
- `report_generator.py` (added v4.4 to PROMPT_VERSIONS)

### Key Changes from v4.3
1. Added TABLE HEADER TRANSLATIONS section (~20 new lines)
2. Updated required section templates with plain English column names
3. Added table header check to Quality Check section
4. Updated Earnings Quality bridge: `D&A` → `Wear & Tear Costs`, `SBC` → `Stock to Employees`
5. Updated Dilution section headers: `Basic Shares` → `Shares Today`

### Version Comparison
| Version | Lines | Focus | Status |
|---------|-------|-------|--------|
| v4.3 | 220 | In-text translations | Good |
| **v4.4** | 240 | In-text + table header translations | **RECOMMENDED** |

### Impact
- Tables in generated reports will use "Cash & Savings" instead of "Liquidity"
- All column headers will be understandable without financial background
- Better Gen Z/Millennial accessibility across all report elements

---

## [2026-01-08] Prompt v4.2 Release

### Summary
Created streamlined v4.2 prompt template (191 lines) to reduce prompt dilution risk from v4.1 (702 lines).

### Changes
- Consolidated verbose example-heavy guidance into Three Core Principles
- Maintained all accessibility requirements (zero-tolerance jargon, dynamic headers, Real Talk verdict)
- Set v4.2 as default in `report_generator.py`

### Files Modified
- `prompts/investment_report_prompt_v4_2.txt` (new)
- `report_generator.py` (updated default, added v4.2 to PROMPT_VERSIONS)

---

## [2026-01-08] Prompt v4.1 Accessibility Enhancements

### Summary
Enhanced v4 prompt template with stricter Gen Z/Millennial accessibility standards.

### Key Additions
- Zero-tolerance jargon policy with BAD/GOOD examples
- Dynamic table headers requirement
- Mandatory unique analogies per ticker
- "Real Talk" verdict requirement
- Expanded financial term translation table

### Files Modified
- `prompts/investment_report_prompt_v4.txt` (updated in-place)

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

### Verification
How the fix was tested.

### Impact
Who/what is affected by this change.
```
