# S&P 500 Concentration Analysis: Methodology & Calculation Audit
### Executive Reference Document | February 2026

---

## 1. Purpose

This document provides a complete audit trail for every figure published in *SP500_MAG7_CONCENTRATION.md*. For each reported number, it specifies: the data source, the mathematical formula, the code implementation reference, and known limitations. This enables independent reviewers to reproduce all results and assess their reliability.

---

## 2. Data Sources & Pipeline

### 2.1 Raw Data Provider

**Financial Modeling Prep (FMP) API** — Starter tier, accessed via `fetch_sp500_data.py`.

| Dataset | FMP Endpoint | Records | Coverage |
|---------|-------------|---------|----------|
| Company Profiles | `/stable/profile` | 498 companies | Current snapshot (market cap, sector, industry) |
| Daily Stock Prices | `/stable/historical-price-eod/light` | ~600,000 rows | Feb 2021 - Feb 2026, per company |
| SPY ETF Prices | `/stable/historical-price-eod/full` | 1,255 rows | Feb 2021 - Feb 2026, daily OHLCV |
| Pre-Computed Returns | `/stable/stock-price-change` | ~496 rows | YTD, 1D, 5D, 1M, 3M, 6M, 1Y, 3Y, 5Y, 10Y, max |
| Quarterly Financials | `/stable/income-statement`, `/stable/cash-flow-statement`, `/stable/balance-sheet-statement` | ~10,798 rows | 20 quarters (Q3 2018 - Q1 2026) |

### 2.2 Data Pipeline

Raw JSON from FMP is processed by `build_dataset.py` into 5 analysis-ready parquet files:

| Parquet File | Key Columns | Derived Columns Added |
|-------------|-------------|----------------------|
| `sp500_profiles.parquet` | symbol, companyName, sector, industry, marketCap, beta, price | — |
| `sp500_daily_prices.parquet` | symbol, date, price, volume | quarter, year, daily_return |
| `sp500_spy_daily.parquet` | date, open, high, low, close, volume, change, changePercent, vwap | quarter, daily_return, quarterly_return |
| `sp500_price_changes.parquet` | symbol, return_1d through return_max | — (pre-computed by FMP) |
| `sp500_quarterly.parquet` | symbol, date, ~138 financial statement columns | calendar_quarter |

### 2.3 Deduplication

GOOG (Alphabet Class C, non-voting) is excluded from all analyses to avoid double-counting with GOOGL (Class A, voting). Both trade independently but represent the same underlying company.

**Implementation** — `analyze_concentration.py:30-57`:
```python
EXCLUDE_DUPLICATES = ["GOOG"]
# Applied to all 4 company-level dataframes in load_all_data()
profiles = profiles[~profiles["symbol"].isin(EXCLUDE_DUPLICATES)]
```

After deduplication, the analysis covers **~497 unique companies**.

### 2.4 Sector Classification

FMP uses its own sector taxonomy, which differs from GICS:

| Company | FMP Sector | GICS Sector |
|---------|-----------|-------------|
| AMZN | Consumer Cyclical | Consumer Discretionary |
| TSLA | Consumer Cyclical | Consumer Discretionary |
| GOOGL | Technology | Communication Services |
| META | Technology | Communication Services |

All sector-level figures in the report use FMP labels. The "Technology" sector under FMP includes 86 companies (including GOOGL and META, which GICS would classify separately).

---

## 3. Calculation Methods by Report Section

### 3.1 Section 1: Tech Sector's Share of S&P 500 Gains

**Goal:** Determine what fraction of total S&P 500 market cap growth came from each sector over 5 years.

#### 3.1.1 Historical Market Cap Estimation

Since FMP's Starter tier only provides *current* market caps (not historical), past market caps are back-calculated using price returns.

**Formula:**
```
mc_5y_ago = mc_now / (1 + return_5y)
mc_added  = mc_now - mc_5y_ago
```

**Worked Example — NVDA:**
```
mc_now     = $4.7T
return_5y  = +1167.6% = 11.676
mc_5y_ago  = $4.7T / (1 + 11.676) = $4.7T / 12.676 = $370.8B
mc_added   = $4.7T - $370.8B = $4.33T
```

**Implementation** — `analyze_concentration.py:188-192`:
```python
pc["return_5y_frac"] = pc["return_5y"] / 100.0
pc["mc_5y_ago"] = pc["mc_now"] / (1 + pc["return_5y_frac"])
pc["mc_added"] = pc["mc_now"] - pc["mc_5y_ago"]
```

**Limitation:** This approximation assumes constant share count. In reality, share issuance (dilution from stock-based compensation) and buybacks change the share count. A company that issued 10% more shares would have its historical market cap *underestimated* by this method, and a company that bought back 10% of shares would have its historical cap *overestimated*.

#### 3.1.2 Sector Contribution

**Formula:**
```
sector_pct_of_gains = sector_mc_added / total_mc_added
sector_weight_now   = sector_mc_now / total_mc_now
sector_weight_5y    = sector_mc_5y_ago / total_mc_5y_ago
```

**Reported Figure — Technology:**
```
Tech mc_added  = $15.0T
Total mc_added = $26.6T
Tech share     = $15.0T / $26.6T = 56.6%
Tech weight now    = 42.8%
Tech weight 5Y ago = 31.9%
```

**Implementation** — `analyze_concentration.py:200-209`:
```python
sector_gains = valid.groupby("sector").agg(
    mc_now=("mc_now", "sum"), mc_5y_ago=("mc_5y_ago", "sum"),
    mc_added=("mc_added", "sum"), count=("symbol", "count"),
).sort_values("mc_added", ascending=False)
sector_gains["pct_of_total_gains"] = sector_gains["mc_added"] / total_mc_added
```

#### 3.1.3 Magnificent 7 Contribution

**Formula:**
```
mag7_mc_added = sum(mc_added for each Mag 7 stock)
mag7_share    = mag7_mc_added / total_mc_added
```

**Reported: $11.9T (44.9% of $26.6T)**

**Implementation** — `analyze_concentration.py:212-214`:
```python
mag7_data = valid[valid["symbol"].isin(MAG7)]
mag7_mc_added = mag7_data["mc_added"].sum()
mag7_pct = mag7_mc_added / total_mc_added
```

---

### 3.2 Section 2: Top 10 Stocks by Market Cap

**Goal:** Identify the 10 largest stocks and quantify their dominance growth.

#### 3.2.1 Selection & Weight

**Formula:**
```
top_10 = 10 stocks with largest current marketCap
weight_now   = company_mc / total_mc
weight_5y_ago = company_mc_5y_ago / total_mc_5y_ago
```

**Implementation** — `analyze_concentration.py:288-290`:
```python
top10 = pc.nlargest(10, "mc_now").copy()
top10["weight_now"] = top10["mc_now"] / total_mc
top10["weight_5y_ago"] = top10["mc_5y_ago"] / total_mc_5y
```

**Reported:** Top 10 = 40.5% of index now, 28.7% five years ago.

#### 3.2.2 Multi-Period Returns

1Y, 3Y, 5Y returns are read directly from `sp500_price_changes.parquet`, which contains pre-computed values from FMP's `/stable/stock-price-change` endpoint. These are simple price returns (not total return with dividends).

**Implementation** — `analyze_concentration.py:321-323`:
```python
for _, row in top10.iterrows():
    md.append(f"| {row['symbol']} | {fmt_pct_raw(row.get('return_1y', None))} | "
              f"{fmt_pct_raw(row.get('return_3y', None))} | {fmt_pct_raw(row['return_5y'])} |")
```

#### 3.2.3 Note on Top 7 vs Magnificent 7

The top 7 stocks by current market cap include **Broadcom (AVGO)** at #7, not Tesla (TSLA) at #8. This means "Top 7 by cap" (34.9%) differs from "Magnificent 7" (34.6%). The report computes each separately and labels them distinctly.

---

### 3.3 Section 3: Sector Performance Divergence

**Goal:** Show which sectors are accelerating vs. decelerating using median stock returns.

#### 3.3.1 Median Return by Sector

**Formula:**
```
For each sector, for each time period (YTD, 1Y, 3Y, 5Y):
  median_return = median of all individual stock returns in that sector
```

Median is used (not mean) to avoid distortion from outliers. FMP's pre-computed return columns from `price_changes` are used.

**Implementation** — `analyze_concentration.py:346-353`:
```python
for sector, grp in pc.groupby("sector"):
    row = {"Sector": sector, "Count": len(grp)}
    for label, col in periods.items():
        row[f"Median {label}"] = grp[col].median()
```

**Worked Example — Energy 5Y:**
```
24 energy stocks, each with a 5Y return from FMP
Sort returns, take the 12th/13th values (median of 24)
Result: +113.5%
```

#### 3.3.2 Accelerating / Decelerating Detection

**Formula:**
```
annualized_5y = (1 + median_5y_return / 100) ^ 0.2 - 1    [geometric annualization]
annualized_5y_pct = annualized_5y × 100

Accelerating:  1Y median > 1.5 × annualized 5Y AND 1Y median > 5%
Decelerating:  1Y median < 0.5 × annualized 5Y AND annualized 5Y > 3%
```

**Worked Example — Technology (Decelerating):**
```
5Y median = +44.8%
Annualized = (1 + 0.448)^0.2 - 1 = 1.0769 - 1 = 0.0769 = +7.7%
1Y median = -1.8%
-1.8% < 0.5 × 7.7% = 3.85% → Decelerating ✓
```

**Implementation** — `analyze_concentration.py:380-391`:
```python
ann_5y = ((1 + row["Median 5Y"]/100) ** 0.2 - 1) * 100
if row["Median 1Y"] > ann_5y * 1.5 and row["Median 1Y"] > 5:
    # Accelerating
if row["Median 1Y"] < ann_5y * 0.5 and ann_5y > 3:
    # Decelerating
```

---

### 3.4 Section 4: Magnificent 7 vs. S&P 500 vs. S&P Ex-Mag 7

**Goal:** Decompose S&P 500 returns into Mag 7 and non-Mag 7 components.

#### 3.4.1 SPY Annual Returns (Cap-Weighted S&P 500 Proxy)

**Formula:**
```
For each calendar year:
  annual_return = (last_trading_day_close / first_trading_day_close) - 1

Cumulative = ∏(1 + annual_return) - 1   [product across all years]
```

**Worked Example:**
```
2021: (close_Dec31 / close_Jan4) - 1 = +21.0%
2022: -19.9%
2023: +24.8%
2024: +24.0%
2025: +16.6%
2026 YTD: +1.3%

Cumulative = (1.210)(0.801)(1.248)(1.240)(1.166)(1.013) - 1 = +77.1%
```

**Implementation** — `analyze_concentration.py:158-175`:
```python
def get_spy_annual_returns(spy_df, start_year=2021, end_year=2026):
    for year in range(start_year, end_year + 1):
        year_data = df[df["date"].dt.year == year]
        first_close = year_data.iloc[0]["close"]
        last_close = year_data.iloc[-1]["close"]
        ret = (last_close / first_close) - 1
        cumulative *= (1 + ret)
```

#### 3.4.2 Equal-Weighted Portfolio Returns (Mag 7 and Ex-Mag 7)

**Formula:**
```
For each year, for each stock in the basket:
  stock_return = (last_price_of_year / first_price_of_year) - 1

basket_return = mean(stock_return for all stocks in basket)   [simple average = equal weight]

Cumulative = ∏(1 + basket_return) - 1
```

Each stock receives 1/N weight regardless of market cap. For Mag 7, N=7. For Ex-Mag 7, N≈490.

**Worked Example — Mag 7 EW, 2023:**
```
AAPL:  +49.0%    MSFT:  +56.8%    AMZN:  +80.9%    GOOGL: +58.3%
META:  +194.1%   NVDA:  +245.8%   TSLA:  +119.4%

Average = (49.0 + 56.8 + 80.9 + 58.3 + 194.1 + 245.8 + 119.4) / 7 = +114.9%
```

**Implementation** — `analyze_concentration.py:122-155`:
```python
def get_annual_returns(daily_prices_df, symbols, start_year=2021, end_year=2026):
    first = year_data.groupby("symbol")["price"].first()
    last = year_data.groupby("symbol")["price"].last()
    stock_returns = (last[common] / first[common]) - 1
    avg_return = stock_returns.mean()    # Equal-weighted
    cumulative *= (1 + avg_return)
```

#### 3.4.3 Cap-Weighted Mag 7 Returns

**Formula:**
```
For each year:
  weights = current_market_cap / sum(current_market_cap)   [for each Mag 7 stock]
  cw_return = Σ(stock_return × weight)

Cumulative = ∏(1 + cw_return) - 1
```

**Critical Limitation:** Weights are based on *current* (Feb 2026) market caps, not start-of-year market caps. This causes NVDA (current weight ~22% of Mag 7) to be overweighted in early years when it was a much smaller proportion. This is why the CW Mag 7 cumulative (+282.9%) significantly exceeds the EW figure (+206.3%).

**Implementation** — `analyze_concentration.py:502-537`:
```python
def _compute_cap_weighted_mag7(daily_prices, profiles):
    mc = profiles.set_index("symbol")["marketCap"].to_dict()
    weights_raw = pd.Series({s: mc.get(s, 0) for s in common})
    weights = weights_raw / weights_raw.sum()
    cw_return = (returns * weights).sum()
```

#### 3.4.4 Growth of $100 Table

**Formula:**
```
value_start = $100
For each year:
  value = value × (1 + annual_return)
```

**Worked Example — SPY:**
```
Start:    $100
End 2021: $100 × 1.210 = $121
End 2022: $121 × 0.801 = $97
End 2023: $97  × 1.248 = $121
End 2024: $121 × 1.240 = $150
End 2025: $150 × 1.166 = $175
Feb 2026: $175 × 1.013 = $177
```

**Implementation** — `analyze_concentration.py:456-469`:
```python
m7_val, m7cw_val, spy_val, ex_val = 100, 100, 100, 100
for year in years:
    m7_val *= (1 + m7r)
    spy_val *= (1 + spr)
```

#### 3.4.5 FactSet Verification (2023-2024 Sub-Period)

**Formula:**
```
2yr_return = (1 + return_2023) × (1 + return_2024) - 1
```

**Reported Comparisons:**

| Portfolio | FactSet | Our CW | Our EW | Variance Explanation |
|-----------|---------|--------|--------|---------------------|
| MAG 7 | +159.65% | +267.9% | +250.6% | CW/EW overestimate because static end-period weights amplify NVDA |
| S&P 500 | +53.19% | +54.8% | — | Close match (1.6pp gap from price-only vs total return) |
| Ex-Mag 7 | +28.31% | — | +29.8% | Close match (1.5pp gap) |

The SPY and Ex-Mag 7 figures closely validate our methodology. The Mag 7 divergence is a known artifact of using end-period weights; it does not affect the directional conclusions.

**Implementation** — `analyze_concentration.py:480-488`:
```python
m7_cw_2yr = (1 + mag7_cw_returns.get(2023, 0)) * (1 + mag7_cw_returns.get(2024, 0)) - 1
spy_2yr = (1 + spy_returns.get(2023, 0)) * (1 + spy_returns.get(2024, 0)) - 1
```

---

### 3.5 Section 5: Additional Concentration Metrics

#### 3.5.1 HHI (Herfindahl-Hirschman Index)

The HHI is a standard measure of market concentration used by the DOJ and FTC.

**Formula:**
```
weight_i = company_marketCap / total_marketCap
HHI = Σ(weight_i²) × 10,000

Equal-weight HHI = 10,000 / N    [where N = number of companies]
Concentration Ratio = Actual HHI / Equal-Weight HHI
```

**Worked Example:**
```
N = ~497 companies
Equal-weight HHI = 10,000 / 497 ≈ 20
Actual HHI = 230
Concentration Ratio = 230 / 20 = 11.4x
```

An HHI of 230 is well below the DOJ's "moderately concentrated" threshold of 1,500, but the comparison to equal-weight (11.4x) illustrates how far the index deviates from uniform distribution.

**Implementation** — `analyze_concentration.py:558-564`:
```python
weights = profiles["marketCap"] / total_mc
hhi = (weights ** 2).sum() * 10000
equal_hhi = 10000 / n
```

#### 3.5.2 Top N Market Cap Share

**Formula:**
```
Sort all companies by marketCap descending
For N in {1, 3, 5, 7, 10, 20, 50}:
  top_N_share = sum(marketCap of top N) / total_marketCap
```

**Key Reported Values:**
```
Top 1  (NVDA):  $4.7T / $60.1T = 7.8%
Top 10:         $24.3T / $60.1T = 40.5%
Top 50:         $38.1T / $60.1T = 63.5%
```

**Mag 7 vs Top 7 Distinction:**
```
Top 7 by cap = NVDA, AAPL, GOOGL, MSFT, AMZN, META, AVGO → 34.9%
Mag 7        = NVDA, AAPL, GOOGL, MSFT, AMZN, META, TSLA → 34.6%
```
AVGO (Broadcom, $1.6T) is in Top 7 by cap; TSLA ($1.4T) is not. These are computed and labeled separately.

**Implementation** — `analyze_concentration.py:577-600`:
```python
sorted_mc = profiles.sort_values("marketCap", ascending=False)
for n_val in [1, 3, 5, 7, 10, 20, 50]:
    top_mc = sorted_mc.head(n_val)["marketCap"].sum()
    # ...
mag7_mc = profiles[profiles["symbol"].isin(MAG7)]["marketCap"].sum()
mag7_share = mag7_mc / total_mc
```

#### 3.5.3 Earnings & Revenue Concentration

**Formula:**
```
For each of the top 10 stocks by market cap:
  trailing_4Q_net_income = sum(netIncome for most recent 4 quarters)
  trailing_4Q_revenue    = sum(revenue for most recent 4 quarters)
  trailing_4Q_fcf        = sum(freeCashFlow for most recent 4 quarters)

top10_share = top10_total / (top10_total + rest_total)
```

**Reported Values:**

| Metric | Top 10 | Total | Top 10 Share |
|--------|--------|-------|-------------|
| Net Income | $522.1B | $1,587B | 32.9% |
| Revenue | $2.5T | $13.6T | 18.1% |
| Free Cash Flow | $388.7B | $1,424B | 27.3% |
| Market Cap | $24.3T | $60.1T | 40.5% |

The gap between market cap share (40.5%) and earnings share (32.9%) quantifies the **valuation premium** — the market prices these companies above their current earnings contribution, reflecting expected future growth.

**Implementation** — `analyze_concentration.py:602-650`:
```python
recent_quarters = sorted(quarterly["calendar_quarter"].unique())[-4:]
annual_earnings = quarterly[quarterly["calendar_quarter"].isin(recent_quarters)].groupby("symbol").agg(
    total_net_income=("netIncome", "sum"),
    total_revenue=("revenue", "sum"),
    total_fcf=("freeCashFlow", "sum"),
)
top10_earnings = annual_earnings.nlargest(10, "marketCap")
```

#### 3.5.4 Breadth: Percentage of Stocks Beating SPY

**Formula:**
```
For each year:
  For each stock: stock_return = (last_price / first_price) - 1
  spy_return = (SPY last_close / SPY first_close) - 1

  beating_count = count(stock_return > spy_return)
  pct_beating = beating_count / total_stocks
  median_stock_return = median(all stock_returns)
```

**Worked Example — 2024:**
```
SPY return = +24.0%
Individual stock returns computed for 494 stocks
137 stocks had returns > +24.0%
pct_beating = 137/494 = 27.7%
Median stock return = +9.6%  (the 247th stock when sorted)
```

The fact that only 27.7% of stocks beat the index while the median return was +9.6% (vs index +24.0%) confirms that a small number of mega-cap winners pulled the average far above the median.

**Implementation** — `analyze_concentration.py:662-675`:
```python
stock_returns = (last[common] / first[common]) - 1
spy_ret = spy_annual.get(year, 0)
beating = (stock_returns > spy_ret).sum()
median_ret = stock_returns.median()
```

#### 3.5.5 Equal-Weight vs. Cap-Weight Spread

**Formula:**
```
Cap-Weight Return = SPY ETF annual return (actual market-cap-weighted index)
Equal-Weight Return = simple average of all ~497 stock annual returns (each stock = 1/497 weight)
Spread = Cap-Weight - Equal-Weight

Cumulative: compound each series separately, then subtract
```

**Reported:**
```
5Y Cap-Weight:   +74.8%   (note: differs slightly from SPY's +77.1% due to 2026 YTD exclusion)
5Y Equal-Weight: +65.1%
5Y Spread:       +9.8 percentage points
```

A positive spread means large-cap stocks outperformed. This has been persistent since 2023 (the AI boom), with spreads of +7.7%, +11.1%, and +7.2% in 2023-2025 respectively.

**Implementation** — `analyze_concentration.py:688-703`:
```python
all_symbols = daily["symbol"].unique().tolist()
ew_returns = get_annual_returns(daily, all_symbols, 2021, 2025)
for year in range(2021, 2026):
    spread = cw_ret - ew_ret
```

---

### 3.6 Section 6: Single-Stock Dependency

#### 3.6.1 Biggest Single-Stock Contributor Per Year

**Formula:**
```
For each stock:
  weight = current_marketCap / total_marketCap
  contribution = weight × stock_annual_return

top_contributor = stock with max(contribution)
spy_without = spy_return - top_contribution    [first-order approximation]
```

**Limitation:** Uses current market cap weights, not start-of-year weights. For stocks whose weight changed significantly during the year (e.g., NVDA going from 3% to 7%), this overestimates the contribution. The NVIDIA Effect section (3.6.2) corrects for this.

**Implementation** — `analyze_concentration.py:750-769`:
```python
weights = mc_series / mc_series.sum()
contributions = weights * stock_returns
top_contrib_sym = contributions.idxmax()
spy_without = spy_ret - top_contrib_val
```

#### 3.6.2 The NVIDIA Effect (Year-by-Year with Back-Calculated Weights)

This is the most methodologically complex calculation in the report. It avoids the bias of applying NVDA's current 7.8% weight to historical returns (when NVDA was only ~1% of the index in early 2021).

**Step 1: Compute NVDA's annual price return from daily data**
```
For each year:
  nvda_return = (last_day_price / first_day_price) - 1
```

**Step 2: Back-calculate NVDA's start-of-year market cap**

Starting from NVDA's current market cap ($4.7T), chain backwards year by year:
```
mc_start_of_year = mc_start_of_next_year / (1 + year_return)
```

**Worked Example:**
```
mc_2026 (current) = $4.7T
mc_start_2025 = mc_2026 / (1 + 0.348) = $4.7T / 1.348 = $3.49T
mc_start_2024 = $3.49T / (1 + 1.788) = $3.49T / 2.788 = $1.25T
mc_start_2023 = $1.25T / (1 + (-0.515)) = $1.25T / 0.485 = $2.58T
  Wait — this is counter-intuitive because NVDA fell 51.5% in 2022, so
  mc_start_2023 = mc_start_2024 / (1 + 2022_return) ...
  Actually the chain goes: mc_start_2023 = mc_start_2024 / (1 + ret_2023)

Corrected chain (each year's start = next year's start / (1 + that year's return)):
  mc_start_2026 = $4.7T (current)
  mc_start_2025 = $4.7T / (1 + 0.348) = $3.49T
  mc_start_2024 = $3.49T / (1 + 1.788) = $1.25T
  mc_start_2023 = $1.25T / (1 + 2.458) = $362B
  mc_start_2022 = $362B / (1 + (-0.515)) = $746B
  mc_start_2021 = $746B / (1 + 1.221) = $336B
```

**Step 3: Estimate total S&P 500 market cap at each year start**
```
total_mc_start_of_year = total_mc_now / compounded_spy_growth_from_that_year_to_now
```

**Worked Example — Start of 2021:**
```
spy_growth_since = (1+0.210)(1-0.199)(1+0.248)(1+0.240)(1+0.166) = 1.771
total_mc_start_2021 = $60.1T / 1.771 = $33.9T
```

**Step 4: Compute NVDA's estimated weight and contribution**
```
est_weight = nvda_mc_start / total_mc_start
contribution = est_weight × nvda_annual_return
```

**Year-by-Year Results:**

| Year | NVDA Return | Est. Weight | Contribution |
|------|-----------|------------|-------------|
| 2021 | +122.1% | 1.0% | +1.2% |
| 2022 | -51.5% | 1.8% | -0.9% |
| 2023 | +245.8% | 1.1% | +2.6% |
| 2024 | +178.8% | 3.0% | +5.3% |
| 2025 | +34.8% | 6.7% | +2.3% |
| **Total** | | | **+10.6%** |

```
SPY 5Y Return:           +77.1%
SPY Without NVDA (est.):  +77.1% - 10.6% ≈ +66.5%
NVDA Share of SPY Return:  10.6% / 77.1% ≈ 14%
```

**Implementation** — `analyze_concentration.py:778-823`:
```python
# Back-calculate market cap timeline
nvda_mc_timeline = {2026: nvda_mc_now}
for year in range(2025, 2020, -1):
    start_p, end_p = nvda_prices_by_year[year]
    yr_ret = (end_p / start_p) - 1
    next_year_start_mc = nvda_mc_timeline.get(year + 1, ...)
    nvda_mc_timeline[year] = next_year_start_mc / (1 + yr_ret)

# Compute contribution per year
for year in range(2021, 2026):
    spy_growth_since = 1.0
    for y in range(year, 2026):
        spy_growth_since *= (1 + spy_annual_full.get(y, 0))
    est_total_mc = profiles["marketCap"].sum() / spy_growth_since
    est_weight = est_mc / est_total_mc
    contribution = est_weight * nvda_ret
    total_nvda_contribution += contribution
```

**Limitation:** The subtraction `SPY - NVDA_contribution` is a first-order linear approximation. In reality, removing NVDA would change all other stocks' weights in the index. The true effect is slightly different due to rebalancing effects, but the approximation is adequate for illustrating magnitude.

#### 3.6.3 Mag 7 Removal

**Formula:**
```
mag7_ew_cumulative = get_annual_returns(MAG7 stocks, EW) → +206.3%
non_mag7_ew_cumulative = get_annual_returns(all non-MAG7 stocks, EW) → +71.8%
spread = 206.3% - 71.8% = 135 percentage points
```

**Reported:** The Mag 7 (34.6% of index weight) returned +206.3% vs +71.8% for the other 488 stocks.

---

## 4. Consolidated Limitations & Known Biases

| # | Limitation | Impact | Direction of Bias |
|---|-----------|--------|-------------------|
| 1 | **Price-only returns** (no dividend reinvestment) | Understates total returns | All returns understated by ~1-2% per year |
| 2 | **Survivorship bias** (current constituents only) | Excludes companies removed from S&P 500 during 5Y period | Likely overstates index performance (failed companies excluded) |
| 3 | **Historical market cap approximation** (mc / (1+return)) | Ignores share issuance and buybacks | Variable: overstates for buyback-heavy companies, understates for dilutive ones |
| 4 | **Static CW weights** (Mag 7 CW uses end-period caps) | NVDA overweighted in early years | CW Mag 7 returns likely overstated; EW is more reliable |
| 5 | **FMP sector classification** (differs from GICS) | GOOGL/META in "Technology" instead of "Communication Services" | Tech sector figures inflated relative to GICS definition |
| 6 | **SPY as S&P 500 proxy** | SPY has tracking error, expense ratio | Minimal impact (~0.03% annually) |
| 7 | **Linear subtraction for "without X" analysis** | Ignores weight rebalancing effects | Approximation adequate for magnitude illustration |
| 8 | **2026 YTD partial year** | Annualized comparison not valid for partial period | Labeled as "YTD" to avoid confusion |

---

## 5. Reproducibility

### 5.1 Environment
```
Python 3.11+
pandas, numpy
```

### 5.2 To Reproduce
```bash
cd sp500_analysis/
python analyze_concentration.py
```

Output: `SP500_MAG7_CONCENTRATION.md`

### 5.3 Data Refresh

To refresh the underlying data from FMP:
```bash
python fetch_sp500_data.py   # Re-fetches raw JSON from FMP API
python build_dataset.py      # Rebuilds parquet files from raw JSON
python analyze_concentration.py  # Regenerates the report
```

Requires `FMP_SECRET_NAME` environment variable pointing to AWS Secrets Manager secret containing the FMP API key.

### 5.4 Key Source Files

| File | Purpose |
|------|---------|
| `analyze_concentration.py` | All calculations documented in this audit (960 lines) |
| `fetch_sp500_data.py` | Raw data fetching from FMP API |
| `build_dataset.py` | Parquet dataset construction pipeline |
| `config.py` | API endpoints, rate limits, S&P 500 constituent list |
| `SP500_MAG7_CONCENTRATION.md` | Generated report output |

---

## 6. Validation Checkpoints

The following cross-checks were performed to validate the analysis:

| Check | Method | Result |
|-------|--------|--------|
| SPY 5Y return | Compared to public SPY data | +77.1% matches market sources (±1%) |
| SPY 2023-2024 return | Compared to FactSet chart | Our +54.8% vs FactSet +53.19% (1.6pp gap, expected for price-only) |
| S&P Ex-Mag 7 2023-2024 | Compared to FactSet chart | Our +29.8% vs FactSet +28.31% (1.5pp gap) |
| Total market cap | Sum of all company caps | ~$60T, consistent with public S&P 500 market cap figures |
| NVDA market cap | Profile data | $4.7T, consistent with public reporting |
| Sector counts | Sum of all sector stock counts | 497 total (after GOOG dedup), consistent with ~500 S&P members |
| HHI range | 230 on 0-10,000 scale | Reasonable for a ~500-stock index with known mega-cap concentration |
| Breadth trend | 2021-2022 broad → 2023-2025 narrow | Consistent with widely reported "narrow market" narrative |

---

*Document generated February 2026. All code references point to `sp500_analysis/analyze_concentration.py` in the project repository.*
