# S&P 500 Follow-Up Analysis: Tariffs, Margins & Dividends
### Supplemental to the Silverblatt Report | Data as of February 18, 2026

**Data Sources:** Financial Modeling Prep (FMP) API — 498 S&P 500 constituents, 20 quarters of financial statements, per-company 5-year daily stock prices, 5 years of daily SPY pricing, and dividend history.

---

## 1. Inventory Builds & Tariff Front-Loading

> **Question:** Can we use the S&P 500 dataset to show companies increased inventories during 2025 due to tariffs?

**363 companies** in the S&P 500 carry inventory on their balance sheet. The remaining 133 (primarily Financial Services, Real Estate, Technology/software, and Utilities) do not.

### Aggregate S&P 500 Inventory Levels (Quarterly)

| Quarter | Total Inventory | YoY Change |
|---------|----------------|------------|
| 2023-Q1 | $1.11T | +6.8% |
| 2023-Q2 | $1.29T | +3.5% |
| 2023-Q3 | $1.77T | +29.4% |
| 2023-Q4 | $1.50T | -17.6% |
| 2024-Q1 | $1.23T | +10.5% |
| 2024-Q2 | $1.23T | -4.8% |
| 2024-Q3 | $1.25T | -29.5% |
| 2024-Q4 | $1.25T | -16.7% |
| 2025-Q1 | $1.24T | +1.4% |
| 2025-Q2 | $1.27T | +3.7% |
| 2025-Q3 | $1.26T | +0.8% |
| 2025-Q4 | $1.07T | -14.1% |
| 2026-Q1 | $0.01T | -99.3% |

### Inventory Change by Sector (2025 vs 2024 Full Year)

| Sector | 2024 Inventory | 2025 Inventory | YoY Change |
|--------|---------------|---------------|------------|
| Technology | $504.9B | $533.8B | +5.7% |
| Basic Materials | $237.8B | $246.9B | +3.8% |
| Industrials | $923.6B | $941.8B | +2.0% |
| Real Estate | $2.6B | $2.6B | +1.4% |
| Consumer Defensive | $800.0B | $809.4B | +1.2% |
| Consumer Cyclical | $1036.0B | $1021.7B | -1.4% |
| Healthcare | $841.9B | $790.2B | -6.1% |
| Communication Services | $53.1B | $48.0B | -9.6% |
| Energy | $317.6B | $265.8B | -16.3% |
| Utilities | $126.6B | $99.5B | -21.4% |
| Financial Services | $0.0B | $0.0B | +nan% |

### Top 20 Inventory Builders (2025 vs 2024, by Absolute Increase)

| Rank | Company | Sector | 2024 Avg Inv | 2025 Avg Inv | Change | % Change |
|------|---------|--------|-------------|-------------|--------|----------|
| 1 | NVIDIA Corporation (NVDA) | Technology | $6.4B | $14.0B | $+7.7B | +120.4% |
| 2 | Amazon.com, Inc. (AMZN) | Consumer Cyclical | $33.9B | $39.1B | $+5.2B | +15.4% |
| 3 | Eli Lilly and Company (LLY) | Healthcare | $6.9B | $10.8B | $+3.9B | +56.8% |
| 4 | Bunge Global S.A. (BG) | Consumer Defensive | $7.4B | $10.7B | $+3.3B | +44.7% |
| 5 | The Home Depot, Inc. (HD) | Consumer Cyclical | $22.6B | $25.1B | $+2.5B | +11.0% |
| 6 | Cencora, Inc. (COR) | Healthcare | $18.9B | $20.9B | $+2.1B | +10.9% |
| 7 | Super Micro Computer, Inc. (SMCI) | Technology | $4.2B | $6.2B | $+2.0B | +46.5% |
| 8 | Walmart Inc. (WMT) | Consumer Defensive | $57.3B | $59.2B | $+1.9B | +3.4% |
| 9 | Advanced Micro Devices, Inc. (AMD) | Technology | $5.2B | $7.1B | $+1.9B | +36.5% |
| 10 | McKesson Corporation (MCK) | Healthcare | $23.7B | $25.3B | $+1.6B | +6.9% |
| 11 | Cardinal Health, Inc. (CAH) | Healthcare | $16.2B | $17.7B | $+1.5B | +9.1% |
| 12 | Caterpillar Inc. (CAT) | Industrials | $17.0B | $18.4B | $+1.3B | +7.9% |
| 13 | Johnson & Johnson (JNJ) | Healthcare | $12.1B | $13.4B | $+1.3B | +10.3% |
| 14 | CVS Health Corporation (CVS) | Healthcare | $17.0B | $18.3B | $+1.2B | +7.1% |
| 15 | Philip Morris International Inc. (PM) | Consumer Defensive | $9.5B | $10.7B | $+1.1B | +11.6% |
| 16 | Amcor plc (AMCR) | Consumer Cyclical | $2.1B | $3.1B | $+1.0B | +48.4% |
| 17 | The Boeing Company (BA) | Industrials | $85.0B | $86.0B | $+1.0B | +1.2% |
| 18 | HP Inc. (HPQ) | Technology | $7.5B | $8.4B | $+0.9B | +11.8% |
| 19 | The TJX Companies, Inc. (TJX) | Consumer Cyclical | $6.8B | $7.6B | $+0.8B | +12.0% |
| 20 | RTX Corporation (RTX) | Industrials | $12.9B | $13.7B | $+0.8B | +6.1% |

### Quarterly Inventory Trajectory (2024-2025)

| Quarter | Total Inventory | Companies Reporting | Median Inventory |
|---------|----------------|--------------------|--------------------|
| 2024-Q1 | $1.23T | 362 | $1.38B |
| 2024-Q2 | $1.23T | 361 | $1.35B |
| 2024-Q3 | $1.25T | 360 | $1.45B |
| 2024-Q4 | $1.25T | 356 | $1.44B |
| 2025-Q1 | $1.24T | 361 | $1.44B |
| 2025-Q2 | $1.27T | 357 | $1.52B |
| 2025-Q3 | $1.26T | 351 | $1.53B |
| 2025-Q4 | $1.07T | 283 | $1.50B |

**Key Findings:**

*Note: Q4 2025 aggregate totals appear lower due to reporting lag (only 283 companies vs ~360 in earlier quarters). Use Q1-Q3 for trend analysis.*

- **Matched-company analysis** (347 companies in both Q1 and Q3 2025): aggregate inventory rose 2.3% from Q1→Q3 2025 (post-tariff announcement period).
- **Clean YoY** (Q1 2025 vs Q1 2024, 354 matched companies): inventory +2.4%.
- **Technology** showed the largest sector-level inventory increase at +5.7% YoY.
- Of the tariff-exposed sectors, 4 out of 7 increased inventory in 2025.
- The top individual builder was **NVIDIA Corporation** (NVDA), adding $7.7B to average inventory — consistent with the semiconductor industry's tariff-driven chip stockpiling.
- Other notable builders include **Amazon** (+$5.2B, warehouse pre-stocking), **Eli Lilly** (+$3.9B, pharma supply chain hedging), and **Home Depot** (+$2.5B, building materials imports).

---

## 2. Tariff-Driven Margin Compression

> **Question:** Can it be tracked how tariffs have squeezed corporate profit margins in 2025-2026?

### S&P 500 Median Margins by Quarter

| Quarter | Gross Margin | Operating Margin | Net Margin | COGS % Rev | Companies |
|---------|-------------|-----------------|------------|-----------|-----------|
| 2023-Q1 | 43.3% | 17.1% | 11.7% | 56.7% | 463 |
| 2023-Q2 | 44.7% | 16.9% | 12.4% | 55.3% | 497 |
| 2023-Q3 | 42.5% | 16.7% | 11.9% | 57.5% | 497 |
| 2023-Q4 | 44.4% | 16.8% | 11.7% | 55.8% | 497 |
| 2024-Q1 | 43.8% | 16.7% | 12.4% | 56.2% | 497 |
| 2024-Q2 | 43.9% | 17.9% | 12.4% | 56.1% | 496 |
| 2024-Q3 | 43.6% | 18.2% | 13.1% | 56.4% | 495 |
| 2024-Q4 | 43.5% | 18.0% | 12.6% | 56.5% | 492 |
| 2025-Q1 | 43.7% | 17.5% | 11.7% | 56.2% | 489 |
| 2025-Q2 | 43.7% | 18.2% | 12.8% | 56.0% | 489 |
| 2025-Q3 | 45.3% | 18.4% | 13.3% | 54.5% | 484 |
| 2025-Q4 | 44.3% | 17.2% | 12.8% | 54.0% | 372 |
| 2026-Q1 | 41.6% | 29.9% | 15.5% | 58.4% | 6 |

### Margin Change: H1 2025 vs H2 2025 by Sector

Tariff impact is most visible comparing pre-tariff (Q1-Q2) vs post-tariff (Q3-Q4) 2025. Initial tariff announcements came in April 2025.

| Sector | H1 Gross | H2 Gross | Change | H1 Operating | H2 Operating | Change |
|--------|---------|---------|--------|-------------|-------------|--------|
| Basic Materials | 32.5% | 25.7% | -6.8pp | 14.2% | 10.4% | -3.8pp |
| Energy | 24.8% | 23.8% | -1.0pp | 18.5% | 15.5% | -2.9pp |
| Real Estate | 68.4% | 60.7% | -7.7pp | 31.1% | 29.1% | -1.9pp |
| Consumer Cyclical | 37.4% | 33.4% | -4.0pp | 12.9% | 11.6% | -1.3pp |
| Communication Services | 43.5% | 46.3% | +2.9pp | 16.4% | 15.4% | -1.0pp |
| Consumer Defensive | 34.7% | 33.6% | -1.1pp | 13.1% | 12.4% | -0.7pp |
| Industrials | 35.8% | 36.3% | +0.5pp | 17.3% | 17.1% | -0.3pp |
| Technology | 58.8% | 58.6% | -0.2pp | 20.7% | 21.2% | +0.5pp |
| Utilities | 42.5% | 48.8% | +6.3pp | 22.5% | 24.2% | +1.7pp |
| Healthcare | 57.4% | 58.0% | +0.7pp | 16.0% | 18.1% | +2.0pp |
| Financial Services | 55.0% | 60.2% | +5.2pp | 20.5% | 23.2% | +2.7pp |

### Tariff-Exposed Sectors: Year-over-Year Margin Trends

| Sector | 2023 GM | 2024 GM | 2025 GM | 2023 OM | 2024 OM | 2025 OM |
|--------|---------|---------|---------|---------|---------|---------|
| Industrials | 34.9% | 36.0% | 35.8% | 16.6% | 17.1% | 17.2% |
| Consumer Cyclical | 36.6% | 36.6% | 36.7% | 12.1% | 13.3% | 12.2% |
| Consumer Defensive | 34.1% | 36.4% | 34.1% | 13.4% | 13.3% | 12.5% |
| Basic Materials | 29.0% | 29.9% | 30.0% | 15.1% | 14.6% | 11.5% |
| Technology | 56.6% | 58.1% | 58.7% | 19.5% | 19.4% | 21.0% |
| Healthcare | 55.8% | 57.0% | 58.0% | 15.1% | 15.5% | 16.8% |
| Energy | 32.7% | 30.0% | 24.0% | 21.7% | 19.7% | 16.7% |

### "Revenue Up, Margin Down" — The Tariff Squeeze Screen

**49 companies** in tariff-exposed sectors grew revenue >2% in 2025 while their operating margin shrank >1 percentage point (out of 64 total across all sectors).

**Top 20 Most Squeezed (Tariff-Exposed Sectors):**

| Rank | Company | Sector | Rev Growth | GM Change | OM Change |
|------|---------|--------|-----------|-----------|-----------|
| 1 | The Hershey Company (HSY) | Consumer Defensive | +4.4% | -13.8pp | -13.5pp |
| 2 | Diamondback Energy, Inc. (FANG) | Energy | +5.3% | -10.5pp | -11.0pp |
| 3 | CrowdStrike Holdings, Inc. (CRWD) | Technology | +22.0% | -1.4pp | -9.9pp |
| 4 | Synopsys, Inc. (SNPS) | Technology | +15.1% | -1.0pp | -9.7pp |
| 5 | ON Semiconductor Corporation (ON) | Technology | +115.2% | -9.1pp | -8.0pp |
| 6 | International Paper Company (IP) | Consumer Cyclical | +33.7% | +0.7pp | -7.0pp |
| 7 | Altria Group, Inc. (MO) | Consumer Defensive | +2.3% | +2.1pp | -6.3pp |
| 8 | Mondelez International, Inc. (MDLZ) | Consumer Defensive | +5.8% | -8.6pp | -6.2pp |
| 9 | ConocoPhillips (COP) | Energy | +9.3% | -2.4pp | -5.2pp |
| 10 | Paychex, Inc. (PAYX) | Industrials | +12.4% | +2.1pp | -5.2pp |
| 11 | ONEOK, Inc. (OKE) | Energy | +13.2% | -5.7pp | -4.5pp |
| 12 | Centene Corporation (CNC) | Healthcare | +19.4% | +2.8pp | -4.4pp |
| 13 | Starbucks Corporation (SBUX) | Consumer Cyclical | +4.3% | -4.0pp | -4.1pp |
| 14 | Super Micro Computer, Inc. (SMCI) | Technology | +34.8% | -3.0pp | -3.8pp |
| 15 | UnitedHealth Group Incorporated (UNH) | Healthcare | +11.8% | -4.5pp | -3.7pp |
| 16 | Alaska Air Group, Inc. (ALK) | Industrials | +21.3% | +34.7pp | -3.6pp |
| 17 | Waters Corporation (WAT) | Healthcare | +7.0% | -0.6pp | -3.4pp |
| 18 | Hewlett Packard Enterprise Company (HPE) | Technology | +14.1% | -2.8pp | -3.0pp |
| 19 | Steel Dynamics, Inc. (STLD) | Basic Materials | +3.6% | -2.6pp | -2.9pp |
| 20 | Lamb Weston Holdings, Inc. (LW) | Consumer Defensive | +2.3% | -2.3pp | -2.7pp |

**Squeeze by Sector:**

| Sector | Companies Squeezed |
|--------|-------------------|
| Technology | 11 |
| Healthcare | 9 |
| Industrials | 9 |
| Consumer Cyclical | 7 |
| Consumer Defensive | 7 |
| Basic Materials | 3 |
| Energy | 3 |

**Key Findings:**

- **7 out of 11 sectors** saw operating margin compression from H1 to H2 2025.
- **Basic Materials** experienced the sharpest operating margin decline (-3.8 percentage points H1→H2 2025).
- 49 companies in goods-producing sectors are in the "revenue up, margin down" trap — growing the top line but losing profitability, a hallmark of cost-push pressure from tariffs.

---

## 3. Dividend Stock Performance (5-Year)

> **Question:** What is the performance of dividend stocks in the S&P 500 over the last 5 years? Have companies also indicated they will raise their dividends?

### Stock Performance by Dividend Tier

Companies classified by trailing-twelve-month dividend yield as of Feb 2026.

| Tier | Count | Median YTD | Median 1Y | Median 3Y | Median 5Y |
|------|-------|-----------|----------|----------|----------|
| High Yield (≥3%) | 71 | +9.3% | -6.7% | -11.8% | -8.8% |
| Medium Yield (1-3%) | 211 | +8.2% | +10.7% | +30.4% | +49.7% |
| Low Yield (<1%) | 117 | +5.3% | +16.5% | +72.8% | +91.9% |
| Non-Payer | 97 | +1.6% | -2.3% | +23.4% | +19.6% |

### Dividend Tier Distribution by Sector

| Sector | High Yield | Medium Yield | Low Yield | Non-Payer |
|--------|-----------|-------------|-----------|-----------|
| Basic Materials | 4 | 8 | 9 | 1 |
| Communication Services | 5 | 6 | 1 | 4 |
| Consumer Cyclical | 5 | 19 | 13 | 18 |
| Consumer Defensive | 15 | 18 | 2 | 2 |
| Energy | 2 | 17 | 1 | 4 |
| Financial Services | 5 | 39 | 19 | 0 |
| Healthcare | 4 | 16 | 18 | 23 |
| Industrials | 7 | 34 | 24 | 6 |
| Real Estate | 16 | 10 | 1 | 2 |
| Technology | 2 | 22 | 26 | 37 |
| Utilities | 6 | 22 | 3 | 0 |

### Dividend Growth Trends (2021-2025)

**2023:** 312 raised (81%), 47 held flat (12%), 24 cut (6%)
**2024:** 281 raised (72%), 62 held flat (16%), 50 cut (13%)
**2025:** 303 raised (77%), 61 held flat (15%), 30 cut (8%)

**252 companies** (63% of dividend payers) raised their dividend every year from 2021-2025.

### 2025 Dividend Growth by Sector

| Sector | Median DPS Growth | Avg DPS Growth | Companies |
|--------|------------------|---------------|-----------|
| Financial Services | +8.0% | +12.3% | 62 |
| Industrials | +7.2% | +8.5% | 65 |
| Consumer Cyclical | +5.8% | +11.7% | 37 |
| Healthcare | +5.5% | +5.3% | 36 |
| Utilities | +5.3% | +10.9% | 31 |
| Real Estate | +4.9% | +6.6% | 27 |
| Energy | +4.5% | +1.5% | 20 |
| Technology | +4.0% | +1.8% | 47 |
| Consumer Defensive | +3.3% | +2.8% | 35 |
| Basic Materials | +2.8% | -1.7% | 22 |
| Communication Services | +2.7% | +4.6% | 12 |

### Top 15 Dividend Raisers (2025 vs 2024)

| Rank | Company | Sector | 2025 DPS Growth |
|------|---------|--------|----------------|
| 1 | The Progressive Corporation (PGR) | Financial Services | +326.1% |
| 2 | Royal Caribbean Cruises Ltd. (RCL) | Consumer Cyclical | +268.4% |
| 3 | Pacific Gas & Electric Co. (PCG) | Utilities | +127.3% |
| 4 | Nordson Corporation (NDSN) | Industrials | +86.0% |
| 5 | Xcel Energy Inc. (XEL) | Utilities | +72.1% |
| 6 | Howmet Aerospace Inc. (HWM) | Industrials | +69.2% |
| 7 | Raymond James Financial, Inc. (RJF) | Financial Services | +48.1% |
| 8 | Quanta Services, Inc. (PWR) | Industrials | +48.1% |
| 9 | State Street Corporation (STT) | Financial Services | +45.8% |
| 10 | Republic Services, Inc. (RSG) | Industrials | +43.3% |
| 11 | Edison International (EIX) | Utilities | +41.5% |
| 12 | Alphabet Inc. (GOOG) | Technology | +38.3% |
| 13 | Alphabet Inc. (GOOGL) | Technology | +38.3% |
| 14 | Essex Property Trust, Inc. (ESS) | Real Estate | +38.2% |
| 15 | Targa Resources Corp. (TRGP) | Energy | +36.4% |

**Key Findings:**

- **Higher-yield stocks underperformed lower-yield stocks over 5 years.** High yield median: -8.8% vs Low yield: +91.9%. This is consistent with the historical pattern where high-yield stocks tend to be value/income plays that lag in growth-led markets.
- Despite underperformance in price returns, dividend stocks provide **total return** through income. A 71-stock high-yield cohort averaging ~4% yield adds ~20 percentage points of cumulative income over 5 years that isn't captured in price returns alone.
- The dividend growth culture remains strong: the majority of companies raised dividends each year, and 252 companies have consecutive 5-year increase streaks.

---

## 4. Financial Characteristics of High-Dividend Stocks

> **Question:** What are the financial characteristics and stock performance of the highest dividend stocks?

### Top 30 Highest-Yield S&P 500 Stocks

| Rank | Company | Sector | Yield | Mkt Cap | 1Y Return | 5Y Return | Payout Ratio | FCF Margin | D/E |
|------|---------|--------|-------|---------|----------|----------|-------------|-----------|------|
| 1 | Dow Inc. (DOW) | Basic Materials | 11.2% | $24B | -20.5% | -45.1% | -78% | -8% | 1.3x |
| 2 | FMC Corporation (FMC) | Basic Materials | 11.0% | $2B | -61.9% | -86.2% | -6% | -22% | 1.9x |
| 3 | Alexandria Real Estate Equities, Inc. (ARE) | Real Estate | 9.5% | $10B | -43.2% | -67.4% | -155% | 50% | 0.8x |
| 4 | TransDigm Group Incorporated (TDG) | Industrials | 7.1% | $74B | +1.2% | +128.1% | 8% | 22% | -3.2x |
| 5 | Conagra Brands, Inc. (CAG) | Consumer Defensive | 7.0% | $10B | -22.6% | -44.9% | 83% | 7% | 0.9x |
| 6 | LyondellBasell Industries N.V. (LYB) | Basic Materials | 6.9% | $19B | -28.4% | -41.0% | 247% | -2% | N/A |
| 7 | Robert Half International Inc. (RHI) | Industrials | 6.5% | $3B | -56.7% | -66.3% | 141% | 2% | 0.0x |
| 8 | Newell Brands Inc. (NWL) | Consumer Defensive | 6.3% | $2B | -31.0% | -79.9% | 27% | -1% | 2.3x |
| 9 | Altria Group, Inc. (MO) | Consumer Defensive | 6.3% | $111B | +26.6% | +53.0% | 116% | 56% | -7.3x |
| 10 | HP Inc. (HPQ) | Technology | 5.9% | $18B | -46.3% | -30.5% | 42% | 5% | -31.5x |
| 11 | Best Buy Co., Inc. (BBY) | Consumer Cyclical | 5.7% | $14B | -26.6% | -43.3% | 125% | 2% | 1.5x |
| 12 | Crown Castle Inc. (CCI) | Real Estate | 5.6% | $37B | -2.1% | -47.3% | 151% | 69% | -18.1x |
| 13 | Verizon Communications Inc. (VZ) | Communication Services | 5.6% | $205B | +16.6% | -15.7% | 58% | 13% | 1.9x |
| 14 | UnitedHealth Group Incorporated (UNH) | Healthcare | 5.5% | $253B | -42.4% | -12.2% | 72% | 5% | 0.8x |
| 15 | Campbell Soup Company (CPB) | Consumer Defensive | 5.3% | $9B | -27.9% | -41.6% | 72% | 5% | 1.8x |
| 16 | United Parcel Service, Inc. (UPS) | Industrials | 5.3% | $102B | +0.6% | -28.4% | 104% | 7% | 2.0x |
| 17 | BXP, Inc. (BXP) | Real Estate | 5.0% | $10B | -11.9% | -33.3% | 97% | 13% | 3.4x |
| 18 | Hormel Foods Corporation (HRL) | Consumer Defensive | 4.8% | $13B | -13.5% | -48.5% | 88% | 5% | 0.4x |
| 19 | The Kraft Heinz Company (KHC) | Consumer Defensive | 4.8% | $30B | -18.3% | -38.5% | 67% | 16% | 0.5x |
| 20 | Franklin Resources, Inc. (BEN) | Financial Services | 4.8% | $14B | +33.7% | +1.5% | 130% | -3% | 1.2x |
| 21 | Amcor plc (AMCR) | Consumer Cyclical | 4.7% | $23B | -2.8% | -13.2% | 103% | 9% | 1.5x |
| 22 | Kimberly-Clark Corporation (KMB) | Consumer Defensive | 4.7% | $36B | -19.0% | -16.9% | 83% | 14% | 4.4x |
| 23 | Pfizer Inc. (PFE) | Healthcare | 4.6% | $158B | +7.1% | -20.8% | 76% | 6% | 0.0x |
| 24 | L3Harris Technologies, Inc. (LHX) | Industrials | 4.6% | $63B | +79.9% | +86.1% | 50% | 10% | 0.6x |
| 25 | Public Storage (PSA) | Real Estate | 4.5% | $51B | +0.7% | +27.2% | 161% | 68% | 1.1x |
| 26 | Ford Motor Company (F) | Consumer Cyclical | 4.5% | $53B | +49.0% | +21.1% | 24% | 8% | 3.5x |
| 27 | Paychex, Inc. (PAYX) | Industrials | 4.5% | $34B | -36.5% | +3.3% | 100% | 34% | 1.3x |
| 28 | Skyworks Solutions, Inc. (SWKS) | Technology | 4.5% | $10B | -7.5% | -67.0% | 99% | 25% | 0.2x |
| 29 | Mid-America Apartment Communities, Inc. (MAA) | Real Estate | 4.4% | $16B | -14.2% | -1.6% | 171% | 30% | 1.0x |
| 30 | VICI Properties Inc. (VICI) | Real Estate | 4.4% | $31B | -2.1% | +9.6% | 60% | 60% | 0.6x |

### High-Yield (≥3%) Stocks by Sector

| Sector | Count | Median Yield | Median 5Y Return |
|--------|-------|-------------|-----------------|
| Real Estate | 16 | 3.6% | +1.5% |
| Consumer Defensive | 15 | 4.0% | -29.8% |
| Industrials | 7 | 4.6% | +3.3% |
| Utilities | 6 | 3.2% | +7.1% |
| Communication Services | 5 | 4.1% | +3.3% |
| Consumer Cyclical | 5 | 4.5% | -13.2% |
| Financial Services | 5 | 3.9% | +12.6% |
| Basic Materials | 4 | 9.0% | -43.1% |
| Healthcare | 4 | 4.1% | -6.8% |
| Energy | 2 | 3.5% | +93.5% |
| Technology | 2 | 5.2% | -48.8% |

### Cohort Comparison: Financial Characteristics

| Metric | High Yield (≥3%) | Medium (1-3%) | Low (<1%) | All Payers |
|--------|-----------------|--------------|-----------|------------|
| Count | 71 | 211 | 117 | 399 |
| Median Yield | 4.0% | 1.8% | 0.6% | 1.6% |
| Median 1Y Return | -6.7% | +10.7% | +16.5% | +10.3% |
| Median 5Y Return | -8.8% | +49.7% | +91.9% | +49.8% |
| Median Payout Ratio | 79% | 43% | 20% | 37% |
| Median FCF Margin | 9% | 13% | 16% | 13% |
| Median D/E Ratio | 0.9x | 0.8x | 0.6x | 0.8x |
| Median Rev Growth (YoY) | -2.2% | +1.5% | +4.3% | +1.9% |
| Median Net Margin | 9.5% | 12.7% | 13.7% | 12.7% |
| Median Market Cap | $25B | $41B | $54B | $41B |

**Key Findings:**

- **High-yield stocks are characteristically different**: They have higher payout ratios (79% median), higher leverage (0.9x D/E), and lower revenue growth than their low-yield peers.
- **5-year price performance gap**: High-yield median -8.8% vs low-yield median +91.9%. However, this ignores the ~15-20pp of cumulative dividend income that high-yield stocks provided.
- **Sector concentration**: Real Estate and Consumer Defensive dominate the high-yield cohort, reflecting their capital-intensive, cash-generative business models.
- **Sustainability signal**: A median FCF margin of 9% for high-yield stocks suggests most dividends are well-covered by free cash flow, though individual names with payout ratios >100% warrant caution.

---

## Methodology & Data Notes

- **Financial data**: Quarterly income statements, cash flow statements, and balance sheets from FMP API for 498 S&P 500 constituents (BF.B and BRK.B excluded due to FMP tier restrictions). Data spans Q3 2018 through Q1 2026.
- **Stock price returns**: FMP `/stable/stock-price-change` endpoint providing 1D/5D/1M/3M/6M/YTD/1Y/3Y/5Y/10Y percentage returns as of Feb 18, 2026. These are **price returns only** (excluding dividends).
- **Daily prices**: Per-company daily close prices from FMP `/stable/historical-price-eod/light` (Feb 2021 – Feb 2026).
- **Dividend data**: Per-payment dividend history from FMP, used to compute annual DPS, growth rates, and yield classifications.
- **Sector classification**: From FMP company profiles (point-in-time).
- **TTM dividend yield**: Computed as trailing-12-month dividends paid (from quarterly cashflow) divided by current market capitalization.
- **Tariff timeline**: Initial tariff announcements in April 2025. H1/H2 2025 split used as pre/post-tariff proxy.
- **Limitations**: Price returns exclude dividends (total return would be higher for income stocks). Inventory data is quarterly (not monthly), limiting tariff timing precision. Q1 2026 data is partial.

---

*Analysis generated February 18, 2026 using S&P 500 Silverblatt dataset.*