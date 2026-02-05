# Investment Report Prompt Comparison: v1 vs v2 vs v3 Proposal

**Document Version:** 1.0
**Created:** January 7, 2026
**Author:** Claude Code Analysis

---

## Executive Summary

This document compares the v1 (Financial Grade) and v2 (Consumer Grade) investment report prompts using actual generated reports for Tesla (TSLA) and Novo Nordisk (NVO). Based on this analysis, we propose a v3 "Balanced Grade" prompt that combines consumer-friendly language with enhanced financial depth.

### Quick Comparison Matrix

| Dimension | v1 (Financial) | v2 (Consumer) | v3 (Proposed) |
|-----------|----------------|---------------|---------------|
| Target Audience | Finance-literate | Gen Z/Millennials | Gen Z/Millennials |
| Table Row Limit | 8 columns | 4 columns | **6 columns** |
| Financial Jargon | Heavy | Minimal | Minimal with context |
| Analogies | Some | Required per section | Required per section |
| Sections | Debt → Cash → Growth | Debt → Cash → Growth | **Growth → Profitability → Cash → Debt** |
| Profitability Section | Embedded in Growth | Embedded in Growth | **Dedicated section** |
| Operating Metrics | Limited | Limited | **Expanded (OCF, Net Margin, etc.)** |
| Report Length | ~11,500 chars | ~10,500 chars | ~12,500 chars (target) |
| Quick Dashboard | No | Yes | Yes |
| Plain-English Translations | Some | Mandatory | Mandatory |

---

## Part 1: Detailed v1 vs v2 Comparison

### 1.1 Report Structure Comparison

#### TSLA Reports

| Section | v1 Structure | v2 Structure |
|---------|--------------|--------------|
| Header | Standard title + date | Title + "v2 Consumer Grade" label |
| Dashboard | None | **Quick Health Dashboard (4 areas)** |
| TL;DR | 3 sentences, technical | 3 sentences, plain language |
| Company Description | Technical (vertical integration, AI) | Relatable (Apple meets Toyota) |
| Debt Section | "The Cash Fortress" (8-row table) | "Tesla's Money Situation" (3-row table) |
| Cash Flow Section | "Cash Flow Comeback" (5-row table) | "Cash Flow: The Comeback Kid" (3-row table) |
| Growth Section | "The Margin Reality Check" (5-row table) | "The Profit Problem" (3-row table) |
| Verdict | Detailed rating breakdown | Simplified with "What It Means" column |

#### NVO Reports

| Section | v1 Structure | v2 Structure |
|---------|--------------|--------------|
| Currency Note | Technical (1 DKK = $0.156) | Intuitive ($1 = about 6.4 DKK) |
| Debt Header | "The Debt Detour" | "The $16 Billion Bet" (more dramatic) |
| Cash Flow Header | "The Cash Flow Tsunami" | "The Cash Machine" (simpler) |
| Growth Header | "The Growth Reckoning" | "The Growth Hangover" (relatable) |

### 1.2 Language & Terminology Comparison

#### Financial Term Handling

| Term | v1 Usage | v2 Usage |
|------|----------|----------|
| FCF Margin | "FCF Margin: 14.2%" | "Cash Keep Rate: keeps 14 cents of every dollar" |
| Debt-to-Equity | "Debt/Equity: 0.17x" | "Borrowing level: 0.17x (borrowed 17 cents...)" |
| Interest Coverage | "Interest Coverage: 21.4x" | "Debt safety cushion: earns 21x what they need" |
| Operating CF | "Operating CF: $6.2B" | "Cash from running the business" |
| YoY Growth | "YoY Growth: +11.6%" | "vs last year: +12%" |
| Sequential | "Sequential decline" | "vs last quarter" |

#### Analogy Examples (v2 Additions)

**TSLA v2 Analogies:**
1. "Tesla is like a freelancer's income. Q1-Q2 was like having slow months where they barely covered rent. Q3 was like landing a massive sponsorship."
2. "Like the only gourmet burger place in town, keeping $27 profit from every $100 tab. Now there are 15 burger joints on the block."

**NVO v2 Analogies:**
1. "Like a homeowner with a paid-off house who took out a massive home equity loan to build an addition—right before the housing market cooled."
2. "Like a premium streaming service where customers pay monthly and almost never cancel."
3. "Like Netflix in 2022—hit a wall where most people who wanted the product already had it."

### 1.3 Table Complexity Comparison

#### TSLA Debt Tables

**v1 Table (5 columns, 5 rows):**
```
| Year | Debt/Equity | Net Cash | Trend |
|------|-------------|----------|-------|
| 2021 | 0.29x | $8.7B | Started strong |
| 2022 | 0.13x | $10.5B | Deleveraged during boom |
| 2023 | 0.15x | $6.8B | Stable |
| 2024 | 0.19x | $2.5B | Slight dip (CapEx ramp) |
| 2025 | 0.17x | $5.1B | Recovered nicely |
```

**v2 Table (3 columns, 3 rows):**
```
| What | Amount | Verdict |
|------|--------|---------|
| Total borrowed | $13.8B | Manageable |
| Cash in bank | $18.9B | Stacked |
| What they actually owe | -$5.1B | Net positive! |
```

**Analysis:** v2 is more scannable but loses 5-year trajectory context. v3 should use 6 rows to show recent trend + history.

### 1.4 Readability Metrics

| Metric | TSLA v1 | TSLA v2 | NVO v1 | NVO v2 |
|--------|---------|---------|--------|--------|
| Character Count | 11,595 | 10,231 | 12,747 | 10,781 |
| Estimated Reading Time | 6-7 min | 5-6 min | 7-8 min | 5-6 min |
| Technical Terms (unexeplained) | ~15 | ~3 | ~18 | ~4 |
| Analogies Used | 3 | 6 | 4 | 6 |
| Tables | 7 | 6 | 8 | 6 |
| Avg Rows per Table | 5.1 | 3.5 | 5.3 | 3.7 |

### 1.5 What v1 Does Better

1. **More Financial Depth:** v1 includes more historical data points (5-year trajectories with annual granularity)
2. **Precise Metrics:** v1 shows exact ratios without rounding (0.17x vs "17 cents")
3. **Professional Tone:** Better suited for users who want analyst-grade reports
4. **Quarterly Detail:** v1 includes more quarters of sequential data

### 1.6 What v2 Does Better

1. **Quick Dashboard:** Instant snapshot of company health before diving in
2. **Plain Language:** Every financial term explained immediately
3. **Relatable Analogies:** 6+ analogies vs 3-4 in v1
4. **Time Period Clarity:** "RIGHT NOW" vs "Bigger Picture" framing
5. **Simpler Tables:** Easier to scan, max 4 columns
6. **Dynamic Callout Headers:** Varied headers prevent monotony

### 1.7 Gaps in Both Versions

1. **No Dedicated Profitability Section:** Margins embedded in Growth section
2. **Limited Operating Metrics:** Operating Cash Flow, Net Margin not prominently featured
3. **Missing Key Ratios:** ROE, ROIC, Gross Margin trends not consistently shown
4. **Section Order:** Debt first may not match reader priorities (growth often more interesting)

---

## Part 2: v3 Prompt Proposal - "Balanced Grade"

### 2.1 Design Philosophy

v3 aims to combine:
- **v2's accessibility** (plain language, analogies, quick dashboard)
- **v1's depth** (more data points, additional metrics)
- **New enhancements** (profitability section, operating metrics, reordered sections)

### 2.2 Key Changes from v2

| Change | v2 | v3 (Proposed) |
|--------|-----|---------------|
| Table Rows | Max 4 | **Max 6** |
| Sections | Debt → Cash → Growth | **Growth → Profitability → Cash → Debt** |
| Profitability | Embedded | **Dedicated section** |
| Operating Metrics | Limited | **Expanded with OCF, Net Margin, Operating Margin** |
| Historical Data | 2-3 years | **5 years** |

### 2.3 New Section Order Rationale

**Proposed Order: Growth → Profitability → Cashflow → Debt**

| Order | Section | Rationale |
|-------|---------|-----------|
| 1 | Growth | Most investors care about revenue trajectory first |
| 2 | Profitability | Natural follow-up: "Is growth translating to profits?" |
| 3 | Cashflow | "Are profits converting to actual cash?" |
| 4 | Debt | Foundation layer - can they sustain operations? |

This follows the natural investor thought process: "Is it growing? → Is it profitable? → Is it generating cash? → Is it financially stable?"

### 2.4 New Profitability Section Specification

```markdown
## 📊 Profitability Section (NEW)
**Dynamic Header Required** - Example: "Is {ticker} Actually Making Money?"

### Required Metrics (with plain-English translations):

| Metric | Plain English Name | How to Explain |
|--------|-------------------|----------------|
| Gross Margin | "Profit per sale (before overhead)" | "Keeps X cents from every dollar of sales before paying salaries, rent, etc." |
| Operating Margin | "Profit from core business" | "Keeps X cents after running the day-to-day business" |
| Net Margin | "Take-home profit" | "Actually pockets X cents from every dollar of revenue" |
| EBITDA Margin | "Operating profits (before loans and accounting)" | "Makes X cents before interest payments and depreciation" |
| ROE | "Return on owner's money" | "For every $100 shareholders invested, company earned $X" |
| ROIC | "Return on all invested capital" | "For every $100 total invested, generated $X in returns" |

### Required Table Format (6 rows):
| Metric | Peak | Now | Trend | Verdict |
|--------|------|-----|-------|---------|
| Gross Margin | X% | Y% | ↑/↓/→ | Good/Watch/Concern |
| Operating Margin | X% | Y% | ↑/↓/→ | Good/Watch/Concern |
| Net Margin | X% | Y% | ↑/↓/→ | Good/Watch/Concern |
| Return on Equity | X% | Y% | ↑/↓/→ | Good/Watch/Concern |
| EPS | $X | $Y | ↑/↓/→ | Good/Watch/Concern |
| Profit Quality | Note | | | |

### Plain-Language Callout Required:
> **💰 The Profitability Reality:** [Fresh analogy explaining if the company is actually making money efficiently]
```

### 2.5 Enhanced Cashflow Section Specification

```markdown
## 💵 Cashflow Section (ENHANCED)
**Dynamic Header Required**

### Required Metrics (with plain-English translations):

| Metric | Plain English Name | How to Explain |
|--------|-------------------|----------------|
| Operating Cash Flow | "Cash from running the business" | "Generated $X from actually selling products/services" |
| Free Cash Flow | "Money left after paying all bills" | "After everything - salaries, equipment, taxes - had $X left over" |
| FCF Margin | "Cash keep rate" | "Keeps X cents of every revenue dollar as actual cash" |
| OCF/Net Income | "Cash conversion quality" | "For every $1 of profit, actually collected $X in cash" |
| CapEx | "Money spent on equipment/growth" | "Invested $X in factories, equipment, technology" |
| FCF Yield | "Cash return on stock price" | "Generates X% of its market value in cash each year" |

### Required Table Format (6 rows - Recent Quarters):
| Quarter | Cash from Business | Cash After Bills | Cash Keep Rate | Quality |
|---------|-------------------|------------------|----------------|---------|
| Q4 2025 | $X | $X | X% | Verdict |
| Q3 2025 | $X | $X | X% | Verdict |
| Q2 2025 | $X | $X | X% | Verdict |
| Q1 2025 | $X | $X | X% | Verdict |
| Q4 2024 | $X | $X | X% | Verdict |
| Q3 2024 | $X | $X | X% | Verdict |

### Additional Context Required:
- Operating vs Free Cash Flow differential explanation
- Cash allocation breakdown (dividends, buybacks, debt paydown, reinvestment)
- Cash conversion cycle if relevant

### Plain-Language Callout Required:
> **💸 Cash Flow Decoded:** [Fresh analogy explaining the company's cash situation]
```

### 2.6 Table Guidelines (6-Row Standard)

**v3 Table Rules:**
1. **Maximum 6 columns** (increased from v2's 4)
2. **Maximum 6 data rows** (plus header)
3. **Always include:** Metric name | Value | Context/Comparison | Verdict
4. **Verdict column required:** Use intuitive indicators (Good/Watch/Concern or emojis)
5. **Historical tables:** Show 5-year trend with 6 data points (annual) OR 6 quarters

**Example v3 Table (6x6):**
```
| Year | Revenue | Growth | Net Margin | FCF | Verdict |
|------|---------|--------|------------|-----|---------|
| 2021 | $17.7B | +50% | 13.1% | $2.1B | Peak growth |
| 2022 | $24.3B | +37% | 15.3% | $3.5B | Strong |
| 2023 | $25.2B | +4% | 31.5%* | $2.8B | One-time boost |
| 2024 | $25.7B | +2% | 9.0% | $2.0B | Slowing |
| 2025 | $28.1B | +9% | 4.9% | $4.0B | Cash recovery |
| Trend | — | ↘️ | ↘️ | ↗️ | Mixed |
```

### 2.7 New Financial Translations Table (v3 Additions)

Add these to the existing v2 translation table:

| Financial Term | Plain English | How to Use |
|----------------|---------------|------------|
| Operating Cash Flow | "cash from running the business" | "Generated $6B from actually selling products" |
| OCF/Net Income Ratio | "cash conversion quality" | "Collects $2.30 in cash for every $1 of reported profit" |
| Operating Margin | "profit from core business" | "Keeps 18 cents after running day-to-day operations" |
| EBITDA | "operating profits before loans & accounting" | — |
| ROE | "return on owner's money" | "Shareholders earned 25% on their investment" |
| ROIC | "return on all invested money" | "Generated 18% return on total capital invested" |
| CapEx | "money spent on equipment/growth" | "Invested $3B in new factories and technology" |
| Working Capital | "cash tied up in daily operations" | "Has $2B locked up in inventory and unpaid bills" |
| FCF Yield | "cash return vs stock price" | "Generates 5% of its market value in cash yearly" |

### 2.8 Proposed v3 Section Order & Structure

```
1. TL;DR (2-3 sentences)
2. Quick Health Dashboard (5 areas now - added Profitability)
3. What Does {ticker} Actually Do?
---
4. Growth Section (Dynamic Header)
   - Revenue trajectory (6-row table)
   - Recent momentum vs bigger picture
   - Plain-Language Callout
   - Bottom Line: +/~/-

5. Profitability Section (NEW - Dynamic Header)
   - Margin analysis (6-row table: Gross, Operating, Net, ROE, EPS, Trend)
   - Are profits real or accounting tricks?
   - Plain-Language Callout
   - Bottom Line: +/~/-

6. Cashflow Section (ENHANCED - Dynamic Header)
   - OCF and FCF trends (6-row table)
   - Cash conversion quality
   - Capital allocation
   - Plain-Language Callout
   - Bottom Line: +/~/-

7. Debt Section (Dynamic Header)
   - Key debt metrics (6-row table)
   - 5-year trajectory
   - Debt safety cushion
   - Plain-Language Callout
   - Bottom Line: +/~/-
---
8. Bull Case (3-4 points)
9. Bear Case (3-4 points)
10. Warning Signs Checklist (6 checks now - added Profitability)
11. The Verdict
    - 4-category rating (Debt, Cash, Profitability, Growth)
    - Who should/shouldn't own
    - Final conviction
---
12. JSON Block (updated with profitability rating)
```

### 2.9 Updated JSON Structure

```json
{
  "growth": {
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  },
  "profitability": {
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  },
  "cashflow": {
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  },
  "debt": {
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  },
  "overall_verdict": "BUY" | "HOLD" | "SELL",
  "conviction": "High" | "Medium" | "Low"
}
```

### 2.10 Updated Quick Health Dashboard

```markdown
**{ticker} at a Glance**
| Area | Health | One-Liner |
|------|--------|-----------|
| 📈 Growth Trend | emoji | [One sentence] |
| 💰 Profitability | emoji | [One sentence] |
| 💵 Cash Generation | emoji | [One sentence] |
| 🏦 Debt Level | emoji | [One sentence] |
| ⚡ Recent Momentum | emoji | [One sentence] |

**Legend:** Green = Strong | Yellow = Mixed/Watch | Red = Concern
```

### 2.11 Updated Warning Signs Checklist

```markdown
| Check | Status | What's Happening |
|-------|--------|------------------|
| Revenue Growth | emoji | [accelerating/stable/slowing] |
| Profit Margins | emoji | [expanding/stable/compressing] |
| Cash Generation | emoji | [strong/adequate/weak] |
| Cash Conversion | emoji | [high quality/adequate/concerning] |
| Debt Level | emoji | [low/moderate/high] |
| Recent Momentum | emoji | [positive/mixed/negative] |

**Warning Flags:** X of 6 areas showing concern
```

---

## Part 3: Implementation Recommendations

### 3.1 File to Create

Create `investment_report_prompt_v3.txt` in:
```
chat-api/backend/investment_research/prompts/investment_report_prompt_v3.txt
```

### 3.2 ReportGenerator Updates

Add to `PROMPT_VERSIONS` dict:
```python
PROMPT_VERSIONS = {
    1: 'investment_report_prompt.txt',      # Financial grade
    2: 'investment_report_prompt_v2.txt',   # Consumer grade
    3: 'investment_report_prompt_v3.txt',   # Balanced grade
}
```

Update `_get_prompt_description`:
```python
descriptions = {
    1: "Financial Grade - technical analysis",
    2: "Consumer Grade - Gen Z/Millennial friendly",
    3: "Balanced Grade - consumer language + financial depth",
}
```

### 3.3 FMP Data Requirements

Ensure these metrics are fetched for v3 profitability section:

| Metric | FMP Endpoint | Notes |
|--------|--------------|-------|
| Gross Margin | income_statement | Calculate: grossProfit / revenue |
| Operating Margin | income_statement | Calculate: operatingIncome / revenue |
| Net Margin | income_statement | Calculate: netIncome / revenue |
| ROE | key_metrics | Direct field |
| ROIC | key_metrics | Direct field |
| Operating Cash Flow | cash_flow_statement | Direct field |
| CapEx | cash_flow_statement | capitalExpenditure field |

### 3.4 Testing Plan

1. Generate v3 reports for test tickers: TSLA, NVO, AAPL, MSFT
2. Compare character counts (target: 12,000-13,000 chars)
3. Verify all new metrics present
4. Confirm section order: Growth → Profitability → Cash → Debt
5. Validate 6-row tables throughout
6. Check plain-language callouts in all sections

---

## Appendix A: Sample v3 Report Outline (TSLA)

```markdown
# **TSLA (Tesla) - Investment Analysis Report**
*v3 Balanced Grade | January 2026*

## TL;DR
[2-3 sentences]

## TSLA at a Glance (5 areas)
[Updated dashboard with Profitability row]

## What Does Tesla Actually Do?
[2-3 sentences]

---

## 📈 From Rocket Ship to Cruise Control: Tesla's Growth Story
[6-row revenue table, YoY and QoQ trends, analogy, callout]

## 💰 The Margin Squeeze: Is Tesla Still Profitable?
[6-row profitability table with Gross/Operating/Net margins, ROE, EPS]
[Analogy about profit compression, callout]

## 💵 Cash is King: The Comeback Quarter
[6-row OCF/FCF table, cash conversion quality, allocation]
[Analogy, callout]

## 🏦 The Fortress Balance Sheet
[6-row debt table, 5-year trajectory]
[Analogy, callout]

---

## 🐂 Why Tesla Could Still Win
[4 bullet points]

## 🐻 Why You Might Want to Wait
[4 bullet points]

## ⚠️ Warning Signs Checklist
[6-check table]

## 🎯 The Verdict
[4-category ratings, who should own, conviction]

```json
{...updated JSON with profitability...}
```
```

---

## Appendix B: Prompt Character Estimates

| Version | Prompt Length | Report Length (avg) |
|---------|---------------|---------------------|
| v1 | ~10,500 chars | ~11,500 chars |
| v2 | ~14,600 chars | ~10,500 chars |
| v3 (est.) | ~18,000 chars | ~12,500 chars |

Note: Longer prompts don't necessarily create longer or more rigid reports - they provide better guardrails for consistent output.

---

## Document History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 7, 2026 | Initial comparison and v3 proposal |
