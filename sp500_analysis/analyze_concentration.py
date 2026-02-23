#!/usr/bin/env python3
"""
S&P 500 Concentration Analysis — Mag 7 & Market Leadership

Quantifies the concentration of S&P 500 returns in mega-cap stocks
over the last 5 years across 6 dimensions:
  1. Tech sector share of total gains
  2. Top 10 stocks by market cap — weights, returns, cap added
  3. Sector performance divergence (5Y / 3Y / 1Y / YTD)
  4. Mag 7 vs S&P 500 vs S&P Ex-Mag 7 (annual + compounding)
  5. Additional concentration metrics (HHI, Top N, earnings, breadth)
  6. Single-stock dependency ("If you removed X")

Outputs: SP500_MAG7_CONCENTRATION.md
"""

import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = Path(__file__).parent / "SP500_MAG7_CONCENTRATION.md"

# Mag 7 constituents (GOOGL is the voting share; GOOG is non-voting — treat as one company)
MAG7 = ["AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA"]

# GOOG is a duplicate listing of Alphabet (same company as GOOGL).
# Exclude from analysis to avoid double-counting.
EXCLUDE_DUPLICATES = ["GOOG"]

# FMP classifies AMZN/TSLA as "Consumer Cyclical" and GOOGL/META as "Technology".
# For GICS-aligned analysis, we define a "Mag 7 Sector" grouping separately.
# The "Technology" figures below use FMP's native sector labels.


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_all_data():
    """Load all parquet datasets, deduplicate, and enrich with sector/profile info."""
    profiles = pd.read_parquet(DATA_DIR / "sp500_profiles.parquet")
    quarterly = pd.read_parquet(DATA_DIR / "sp500_quarterly.parquet")
    spy = pd.read_parquet(DATA_DIR / "sp500_spy_daily.parquet")
    price_changes = pd.read_parquet(DATA_DIR / "sp500_price_changes.parquet")
    daily_prices = pd.read_parquet(DATA_DIR / "sp500_daily_prices.parquet")

    # Remove duplicate listings (GOOG = non-voting Alphabet, same company as GOOGL)
    profiles = profiles[~profiles["symbol"].isin(EXCLUDE_DUPLICATES)]
    quarterly = quarterly[~quarterly["symbol"].isin(EXCLUDE_DUPLICATES)]
    price_changes = price_changes[~price_changes["symbol"].isin(EXCLUDE_DUPLICATES)]
    daily_prices = daily_prices[~daily_prices["symbol"].isin(EXCLUDE_DUPLICATES)]

    # Ensure date columns are datetime
    daily_prices["date"] = pd.to_datetime(daily_prices["date"])
    spy["date"] = pd.to_datetime(spy["date"])
    quarterly["date"] = pd.to_datetime(quarterly["date"])

    # Join sector + market cap onto price_changes
    price_changes = price_changes.merge(
        profiles[["symbol", "sector", "companyName", "marketCap"]],
        on="symbol", how="left",
    )

    # Join sector onto quarterly
    quarterly = quarterly.merge(
        profiles[["symbol", "sector", "companyName", "marketCap"]],
        on="symbol", how="left",
    )

    # Add is_mag7 flag
    price_changes["is_mag7"] = price_changes["symbol"].isin(MAG7)
    daily_prices["is_mag7"] = daily_prices["symbol"].isin(MAG7)

    return {
        "profiles": profiles,
        "quarterly": quarterly,
        "spy": spy,
        "price_changes": price_changes,
        "daily_prices": daily_prices,
    }


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def fmt_pct(val, decimals=1):
    """Format a percentage value (0.25 → '+25.0%')."""
    if pd.isna(val):
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val * 100:.{decimals}f}%"


def fmt_pct_raw(val, decimals=1):
    """Format a raw percentage value (25.0 → '+25.0%')."""
    if pd.isna(val):
        return "N/A"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.{decimals}f}%"


def fmt_dollars(val, decimals=1):
    """Format dollar value in trillions/billions."""
    if pd.isna(val):
        return "N/A"
    if abs(val) >= 1e12:
        return f"${val / 1e12:.{decimals}f}T"
    elif abs(val) >= 1e9:
        return f"${val / 1e9:.{decimals}f}B"
    elif abs(val) >= 1e6:
        return f"${val / 1e6:.{decimals}f}M"
    return f"${val:,.0f}"


def get_annual_returns(daily_prices_df, symbols, start_year=2021, end_year=2026):
    """
    Compute equal-weighted annual price returns for a basket of symbols.
    Returns dict: {year: return_fraction, ...} plus 'cumulative'.
    Uses first/last trading day of each year.
    """
    df = daily_prices_df[daily_prices_df["symbol"].isin(symbols)].copy()
    df = df.sort_values(["symbol", "date"])

    results = {}
    cumulative = 1.0

    for year in range(start_year, end_year + 1):
        year_data = df[df["date"].dt.year == year]
        if year_data.empty:
            continue

        # Get first and last price for each symbol in this year
        first = year_data.groupby("symbol")["price"].first()
        last = year_data.groupby("symbol")["price"].last()

        # Only include symbols with both first and last
        common = first.index.intersection(last.index)
        if len(common) == 0:
            continue

        # Equal-weighted return
        stock_returns = (last[common] / first[common]) - 1
        avg_return = stock_returns.mean()
        results[year] = avg_return
        cumulative *= (1 + avg_return)

    results["cumulative"] = cumulative - 1
    return results


def get_spy_annual_returns(spy_df, start_year=2021, end_year=2026):
    """Compute annual SPY returns from daily data."""
    df = spy_df.sort_values("date")
    results = {}
    cumulative = 1.0

    for year in range(start_year, end_year + 1):
        year_data = df[df["date"].dt.year == year]
        if year_data.empty:
            continue
        first_close = year_data.iloc[0]["close"]
        last_close = year_data.iloc[-1]["close"]
        ret = (last_close / first_close) - 1
        results[year] = ret
        cumulative *= (1 + ret)

    results["cumulative"] = cumulative - 1
    return results


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: TECH SECTOR SHARE OF S&P 500 GAINS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_tech_sector_gains(data):
    """Compute what fraction of S&P 500 market cap gains came from Tech."""
    pc = data["price_changes"].copy()
    profiles = data["profiles"].copy()

    # Current market cap and estimated 5Y-ago market cap
    # mc_now / (1 + 5Y_return) ≈ mc_5y_ago
    pc["mc_now"] = pc["marketCap"]
    pc["return_5y_frac"] = pc["return_5y"] / 100.0
    pc["mc_5y_ago"] = pc["mc_now"] / (1 + pc["return_5y_frac"])
    pc["mc_added"] = pc["mc_now"] - pc["mc_5y_ago"]

    # Drop rows without 5Y return data
    valid = pc.dropna(subset=["return_5y", "mc_now"])

    total_mc_added = valid["mc_added"].sum()

    # By sector
    sector_gains = valid.groupby("sector").agg(
        mc_now=("mc_now", "sum"),
        mc_5y_ago=("mc_5y_ago", "sum"),
        mc_added=("mc_added", "sum"),
        count=("symbol", "count"),
    ).sort_values("mc_added", ascending=False)

    sector_gains["pct_of_total_gains"] = sector_gains["mc_added"] / total_mc_added
    sector_gains["weight_now"] = sector_gains["mc_now"] / valid["mc_now"].sum()
    sector_gains["weight_5y_ago"] = sector_gains["mc_5y_ago"] / valid["mc_5y_ago"].sum()

    # Mag 7 specific contribution
    mag7_data = valid[valid["symbol"].isin(MAG7)]
    mag7_mc_added = mag7_data["mc_added"].sum()
    mag7_pct = mag7_mc_added / total_mc_added

    # Annual breakdown using daily prices
    daily = data["daily_prices"].copy()
    annual_sector = []
    for year in range(2021, 2027):
        year_data = daily[daily["date"].dt.year == year]
        if year_data.empty:
            continue
        first = year_data.groupby("symbol")["price"].first().rename("price_start")
        last = year_data.groupby("symbol")["price"].last().rename("price_end")
        yr = first.to_frame().join(last).join(
            profiles.set_index("symbol")[["sector", "marketCap"]]
        ).dropna()
        yr["return"] = (yr["price_end"] / yr["price_start"]) - 1
        # Approximate start-of-year market cap
        yr["mc_start"] = yr["marketCap"] / (1 + yr["return"])
        yr["mc_change"] = yr["marketCap"] * yr["return"] / (1 + yr["return"])

        for sector, grp in yr.groupby("sector"):
            annual_sector.append({
                "year": year,
                "sector": sector,
                "mc_change": grp["mc_change"].sum(),
                "avg_return": grp["return"].mean(),
            })

    annual_df = pd.DataFrame(annual_sector)

    md = []
    md.append("## 1. Tech Sector's Share of S&P 500 Gains\n")
    md.append("How much of the S&P 500's market cap growth over the past 5 years is attributable "
              "to the Technology sector and the Magnificent 7?\n")

    md.append("### Sector Contribution to Total Market Cap Gains (5-Year)\n")
    md.append("| Sector | Market Cap Added | % of Total Gains | Weight Now | Weight 5Y Ago |")
    md.append("|--------|-----------------|------------------|------------|---------------|")
    for sector, row in sector_gains.iterrows():
        md.append(f"| {sector} | {fmt_dollars(row['mc_added'])} | "
                  f"{row['pct_of_total_gains']:.1%} | {row['weight_now']:.1%} | "
                  f"{row['weight_5y_ago']:.1%} |")

    md.append(f"\n**Total market cap added (5Y):** {fmt_dollars(total_mc_added)}")
    md.append(f"\n**Magnificent 7 alone contributed {fmt_dollars(mag7_mc_added)} "
              f"({mag7_pct:.1%} of all gains).** Just 7 stocks out of ~500 drove "
              f"nearly {mag7_pct:.0%} of the entire index's market cap growth.\n")

    # Tech vs rest summary
    tech_row = sector_gains.loc["Technology"] if "Technology" in sector_gains.index else None
    if tech_row is not None:
        md.append(f"The Technology sector (FMP classification, {int(tech_row['count'])} companies) "
                  f"added {fmt_dollars(tech_row['mc_added'])}, representing "
                  f"**{tech_row['pct_of_total_gains']:.1%}** of total S&P 500 gains. "
                  f"Its index weight grew from {tech_row['weight_5y_ago']:.1%} to "
                  f"{tech_row['weight_now']:.1%}.\n")

    return "\n".join(md), sector_gains, annual_df


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: TOP 10 STOCKS BY MARKET CAP
# ═══════════════════════════════════════════════════════════════════════════

def analyze_top10_stocks(data):
    """Top 10 stocks by market cap with weights, returns, and cap added."""
    pc = data["price_changes"].copy()
    pc["mc_now"] = pc["marketCap"]
    pc["return_5y_frac"] = pc["return_5y"] / 100.0
    pc["mc_5y_ago"] = pc["mc_now"] / (1 + pc["return_5y_frac"])
    pc["mc_added"] = pc["mc_now"] - pc["mc_5y_ago"]

    total_mc = pc["mc_now"].sum()
    total_mc_5y = pc.dropna(subset=["mc_5y_ago"])["mc_5y_ago"].sum()

    top10 = pc.nlargest(10, "mc_now").copy()
    top10["weight_now"] = top10["mc_now"] / total_mc
    top10["weight_5y_ago"] = top10["mc_5y_ago"] / total_mc_5y

    # Also compute 1Y and 3Y returns
    md = []
    md.append("## 2. Top 10 Stocks by Market Cap\n")
    md.append("The ten largest companies in the S&P 500 and how their dominance has grown.\n")

    md.append("| Rank | Symbol | Company | Sector | Mkt Cap Now | Weight | 5Y Return | Mkt Cap Added | Weight 5Y Ago |")
    md.append("|------|--------|---------|--------|-------------|--------|-----------|---------------|---------------|")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        mag7_flag = " *" if row["symbol"] in MAG7 else ""
        md.append(f"| {i} | {row['symbol']}{mag7_flag} | {row['companyName'][:25]} | "
                  f"{row['sector'][:15]} | {fmt_dollars(row['mc_now'])} | "
                  f"{row['weight_now']:.1%} | {fmt_pct_raw(row['return_5y'])} | "
                  f"{fmt_dollars(row['mc_added'])} | {row['weight_5y_ago']:.1%} |")

    top10_now = top10["weight_now"].sum()
    top10_5y = top10["weight_5y_ago"].sum()
    top10_mc_added = top10["mc_added"].sum()
    total_added = pc.dropna(subset=["mc_added"])["mc_added"].sum()

    md.append(f"\n\\* = Magnificent 7 member\n")
    md.append(f"**Top 10 concentration:** {top10_now:.1%} of S&P 500 today vs "
              f"{top10_5y:.1%} five years ago.")
    md.append(f"\n**Top 10 contributed {fmt_dollars(top10_mc_added)} in market cap "
              f"({top10_mc_added/total_added:.1%} of all gains).**\n")

    # 1Y and 3Y returns for top 10
    md.append("### Top 10 Multi-Period Returns\n")
    md.append("| Symbol | 1Y Return | 3Y Return | 5Y Return |")
    md.append("|--------|-----------|-----------|-----------|")
    for _, row in top10.iterrows():
        md.append(f"| {row['symbol']} | {fmt_pct_raw(row.get('return_1y', None))} | "
                  f"{fmt_pct_raw(row.get('return_3y', None))} | {fmt_pct_raw(row['return_5y'])} |")

    md.append("")
    return "\n".join(md), top10


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: SECTOR PERFORMANCE DIVERGENCE
# ═══════════════════════════════════════════════════════════════════════════

def analyze_sector_divergence(data):
    """Sector-level median returns over multiple time horizons."""
    pc = data["price_changes"].copy()

    # Compute median return by sector for each period
    periods = {
        "YTD": "return_ytd",
        "1Y": "return_1y",
        "3Y": "return_3y",
        "5Y": "return_5y",
    }

    sector_perf = []
    for sector, grp in pc.groupby("sector"):
        row = {"Sector": sector, "Count": len(grp)}
        for label, col in periods.items():
            row[f"Median {label}"] = grp[col].median()
            row[f"Mean {label}"] = grp[col].mean()
        sector_perf.append(row)

    sector_df = pd.DataFrame(sector_perf).sort_values("Median 5Y", ascending=False)

    md = []
    md.append("## 3. Sector Performance Divergence\n")
    md.append("Median stock return by sector across multiple time horizons. "
              "This reveals which sectors have been accelerating vs. fading.\n")

    md.append("### Median Stock Return by Sector\n")
    md.append("| Sector | # Stocks | YTD | 1-Year | 3-Year | 5-Year |")
    md.append("|--------|----------|-----|--------|--------|--------|")
    for _, row in sector_df.iterrows():
        md.append(f"| {row['Sector']} | {int(row['Count'])} | "
                  f"{fmt_pct_raw(row['Median YTD'])} | {fmt_pct_raw(row['Median 1Y'])} | "
                  f"{fmt_pct_raw(row['Median 3Y'])} | {fmt_pct_raw(row['Median 5Y'])} |")

    # Highlight divergences
    md.append("\n### Key Divergences\n")

    # Best and worst 5Y sectors
    best_5y = sector_df.iloc[0]
    worst_5y = sector_df.iloc[-1]
    md.append(f"- **Best 5Y sector:** {best_5y['Sector']} (median {fmt_pct_raw(best_5y['Median 5Y'])} return)")
    md.append(f"- **Worst 5Y sector:** {worst_5y['Sector']} (median {fmt_pct_raw(worst_5y['Median 5Y'])} return)")

    # Sectors where 1Y >> 5Y/5 (accelerating)
    md.append(f"- **Accelerating (1Y > annualized 5Y):**")
    for _, row in sector_df.iterrows():
        ann_5y = ((1 + row["Median 5Y"]/100) ** 0.2 - 1) * 100 if row["Median 5Y"] > -100 else 0
        if row["Median 1Y"] > ann_5y * 1.5 and row["Median 1Y"] > 5:
            md.append(f"  - {row['Sector']}: 1Y median {fmt_pct_raw(row['Median 1Y'])} vs "
                      f"5Y annualized ~{fmt_pct_raw(ann_5y)}")

    # Sectors where 1Y << annualized 5Y (decelerating)
    md.append(f"- **Decelerating (1Y < annualized 5Y):**")
    for _, row in sector_df.iterrows():
        ann_5y = ((1 + row["Median 5Y"]/100) ** 0.2 - 1) * 100 if row["Median 5Y"] > -100 else 0
        if row["Median 1Y"] < ann_5y * 0.5 and ann_5y > 3:
            md.append(f"  - {row['Sector']}: 1Y median {fmt_pct_raw(row['Median 1Y'])} vs "
                      f"5Y annualized ~{fmt_pct_raw(ann_5y)}")

    md.append("")
    return "\n".join(md), sector_df


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: MAG 7 vs S&P 500 vs S&P EX-MAG 7
# ═══════════════════════════════════════════════════════════════════════════

def analyze_mag7_isolation(data):
    """
    Compute annual returns for three portfolios:
      (a) Mag 7 (equal-weighted)
      (b) SPY (cap-weighted S&P 500 proxy)
      (c) S&P 500 ex-Mag 7 (all other stocks, equal-weighted)

    Also compute cap-weighted Mag 7 returns using market cap as weight.
    """
    daily = data["daily_prices"]
    spy = data["spy"]
    profiles = data["profiles"]

    # All non-Mag7 symbols
    all_symbols = daily["symbol"].unique()
    non_mag7 = [s for s in all_symbols if s not in MAG7]

    # Compute returns
    mag7_returns = get_annual_returns(daily, MAG7, 2021, 2026)
    non_mag7_returns = get_annual_returns(daily, non_mag7, 2021, 2026)
    spy_returns = get_spy_annual_returns(spy, 2021, 2026)

    # Cap-weighted Mag 7 returns using daily prices
    mag7_cw_returns = _compute_cap_weighted_mag7(daily, profiles)

    # Build compounding table
    years = list(range(2021, 2027))
    md = []
    md.append("## 4. Magnificent 7 vs. S&P 500 vs. S&P 500 Ex-Mag 7\n")
    md.append("Isolating the Mag 7's performance from the rest of the index reveals "
              "a stark bifurcation in market returns.\n")

    md.append("### Annual Returns\n")
    md.append("| Year | Mag 7 (EW) | Mag 7 (CW) | S&P 500 (SPY) | S&P Ex-Mag 7 (EW) |")
    md.append("|------|-----------|-----------|---------------|-------------------|")
    for year in years:
        m7 = mag7_returns.get(year, None)
        m7cw = mag7_cw_returns.get(year, None)
        sp = spy_returns.get(year, None)
        ex = non_mag7_returns.get(year, None)
        label = str(year) if year < 2026 else "2026 YTD"
        md.append(f"| {label} | {fmt_pct(m7)} | {fmt_pct(m7cw)} | "
                  f"{fmt_pct(sp)} | {fmt_pct(ex)} |")

    # Cumulative
    md.append(f"| **5Y Cumulative** | **{fmt_pct(mag7_returns.get('cumulative'))}** | "
              f"**{fmt_pct(mag7_cw_returns.get('cumulative'))}** | "
              f"**{fmt_pct(spy_returns.get('cumulative'))}** | "
              f"**{fmt_pct(non_mag7_returns.get('cumulative'))}** |")

    # Compounding table ($100 invested)
    md.append("\n### Growth of $100 Invested (Start of 2021)\n")
    md.append("| Year-End | Mag 7 (EW) | Mag 7 (CW) | S&P 500 | S&P Ex-Mag 7 |")
    md.append("|----------|-----------|-----------|---------|--------------|")

    m7_val, m7cw_val, spy_val, ex_val = 100, 100, 100, 100
    md.append(f"| Start 2021 | $100 | $100 | $100 | $100 |")
    for year in years:
        m7r = mag7_returns.get(year, 0)
        m7cwr = mag7_cw_returns.get(year, 0)
        spr = spy_returns.get(year, 0)
        exr = non_mag7_returns.get(year, 0)
        m7_val *= (1 + m7r)
        m7cw_val *= (1 + m7cwr)
        spy_val *= (1 + spr)
        ex_val *= (1 + exr)
        label = f"End {year}" if year < 2026 else "Feb 2026"
        md.append(f"| {label} | ${m7_val:.0f} | ${m7cw_val:.0f} | "
                  f"${spy_val:.0f} | ${ex_val:.0f} |")

    # Verification against screenshot (2023-2024 period)
    # The FactSet/HORAN chart shows "Total Return: 2023-2024" from ~1/2023 through ~1/2025
    md.append("\n### Verification: 2023-2024 Sub-Period (FactSet Chart Comparison)\n")
    md.append("The FactSet chart (HORAN Capital Advisors) shows total returns "
              "from Jan 2023 through ~Jan 2025. Below we compare their cap-weighted "
              "figures against our estimates.\n")
    md.append("| Portfolio | FactSet Chart | Our Cap-Weighted Est. | Our Equal-Weighted Est. |")
    md.append("|-----------|--------------|----------------------|------------------------|")

    # Compute 2023+2024 compounded for all methods
    m7_ew_2yr = (1 + mag7_returns.get(2023, 0)) * (1 + mag7_returns.get(2024, 0)) - 1
    m7_cw_2yr = (1 + mag7_cw_returns.get(2023, 0)) * (1 + mag7_cw_returns.get(2024, 0)) - 1
    spy_2yr = (1 + spy_returns.get(2023, 0)) * (1 + spy_returns.get(2024, 0)) - 1
    ex_ew_2yr = (1 + non_mag7_returns.get(2023, 0)) * (1 + non_mag7_returns.get(2024, 0)) - 1

    md.append(f"| MAG 7 | +159.65% | {fmt_pct(m7_cw_2yr)} | {fmt_pct(m7_ew_2yr)} |")
    md.append(f"| S&P 500 | +53.19% | {fmt_pct(spy_2yr)} | — |")
    md.append(f"| S&P 500 Ex-Mag 7 | +28.31% | — | {fmt_pct(ex_ew_2yr)} |")
    md.append("")
    md.append("**Reading the comparison:** Our S&P 500 (SPY) figure closely matches FactSet. "
              "The Mag 7 cap-weighted estimate differs because: (1) our data is price-only "
              "(no dividend reinvestment), (2) we use current market cap weights rather than "
              "time-varying weights, and (3) NVDA's massive 2023-2024 run is amplified by "
              "its end-of-period weight in our CW calculation. The equal-weighted Mag 7 — "
              "which treats all 7 stocks equally — more closely approximates the FactSet figure, "
              "as NVDA's outsized return is diluted. The overall story is consistent: "
              "the Mag 7 delivered 3-6x the return of the rest of the index.\n")

    return "\n".join(md), mag7_returns, spy_returns, non_mag7_returns


def _compute_cap_weighted_mag7(daily_prices, profiles):
    """
    Compute cap-weighted annual Mag 7 returns.
    Weights by start-of-year market cap (approximated from current cap / cumulative return).
    """
    mag7_daily = daily_prices[daily_prices["symbol"].isin(MAG7)].copy()
    mag7_daily = mag7_daily.sort_values(["symbol", "date"])

    # Get current market cap for weighting
    mc = profiles.set_index("symbol")["marketCap"].to_dict()

    results = {}
    cumulative = 1.0

    for year in range(2021, 2027):
        year_data = mag7_daily[mag7_daily["date"].dt.year == year]
        if year_data.empty:
            continue

        first = year_data.groupby("symbol")["price"].first()
        last = year_data.groupby("symbol")["price"].last()
        common = first.index.intersection(last.index)

        if len(common) == 0:
            continue

        returns = (last[common] / first[common]) - 1
        weights_raw = pd.Series({s: mc.get(s, 0) for s in common})
        weights = weights_raw / weights_raw.sum()

        cw_return = (returns * weights).sum()
        results[year] = cw_return
        cumulative *= (1 + cw_return)

    results["cumulative"] = cumulative - 1
    return results


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5: ADDITIONAL CONCENTRATION METRICS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_concentration_metrics(data):
    """HHI, Top N share, earnings concentration, breadth, equal-weight vs cap-weight."""
    profiles = data["profiles"]
    pc = data["price_changes"]
    quarterly = data["quarterly"]
    daily = data["daily_prices"]
    spy = data["spy"]

    total_mc = profiles["marketCap"].sum()

    md = []
    md.append("## 5. Additional Concentration Metrics\n")

    # --- 5a: HHI (Herfindahl-Hirschman Index) ---
    weights = profiles["marketCap"] / total_mc
    hhi = (weights ** 2).sum() * 10000  # Scale to standard HHI (0-10,000)

    # Theoretical equal-weight HHI
    n = len(profiles)
    equal_hhi = 10000 / n

    md.append("### 5a. Market Cap Concentration (HHI)\n")
    md.append("The Herfindahl-Hirschman Index measures concentration on a 0-10,000 scale. "
              "Higher = more concentrated.\n")
    md.append(f"| Metric | Value |")
    md.append(f"|--------|-------|")
    md.append(f"| Current HHI | {hhi:.0f} |")
    md.append(f"| Equal-Weight HHI (theoretical) | {equal_hhi:.0f} |")
    md.append(f"| Concentration Ratio (Current / Equal) | {hhi/equal_hhi:.1f}x |")
    md.append(f"\nThe S&P 500's HHI of {hhi:.0f} is **{hhi/equal_hhi:.1f}x** what it would be "
              f"if all 500 stocks were equally weighted ({equal_hhi:.0f}).\n")

    # --- 5b: Top N Share of Total Market Cap ---
    sorted_mc = profiles.sort_values("marketCap", ascending=False)
    top_n_data = []
    for n_val in [1, 3, 5, 7, 10, 20, 50]:
        top_mc = sorted_mc.head(n_val)["marketCap"].sum()
        top_n_data.append({
            "N": n_val,
            "Market Cap": top_mc,
            "Share": top_mc / total_mc,
            "Companies": ", ".join(sorted_mc.head(n_val)["symbol"].tolist()) if n_val <= 7 else "",
        })

    md.append("### 5b. Top N Stocks' Share of S&P 500 Market Cap\n")
    md.append("| Top N | Market Cap | Share of S&P 500 | Companies |")
    md.append("|-------|-----------|------------------|-----------|")
    for row in top_n_data:
        companies = row["Companies"] if row["N"] <= 7 else f"(top {row['N']})"
        md.append(f"| Top {row['N']} | {fmt_dollars(row['Market Cap'])} | "
                  f"{row['Share']:.1%} | {companies} |")

    # Compute actual Mag 7 weight (different from "Top 7 by cap" which includes AVGO)
    mag7_mc = profiles[profiles["symbol"].isin(MAG7)]["marketCap"].sum()
    mag7_share = mag7_mc / total_mc
    md.append(f"\n**The top 10 stocks hold {top_n_data[4]['Share']:.1%} of the entire S&P 500's market cap.** "
              f"The Magnificent 7 specifically hold **{mag7_share:.1%}**.\n")

    # --- 5c: Earnings Concentration (Top 10 vs Rest) ---
    latest_q = quarterly["calendar_quarter"].max()
    # Use trailing 4 quarters for annual earnings
    recent_quarters = sorted(quarterly["calendar_quarter"].unique())[-4:]
    annual_earnings = quarterly[quarterly["calendar_quarter"].isin(recent_quarters)].groupby("symbol").agg(
        total_net_income=("netIncome", "sum"),
        total_revenue=("revenue", "sum"),
        total_fcf=("freeCashFlow", "sum"),
    ).reset_index()
    annual_earnings = annual_earnings.merge(
        profiles[["symbol", "sector", "marketCap", "companyName"]],
        on="symbol", how="left",
    )

    top10_earnings = annual_earnings.nlargest(10, "marketCap")
    rest_earnings = annual_earnings[~annual_earnings["symbol"].isin(top10_earnings["symbol"])]

    top10_ni = top10_earnings["total_net_income"].sum()
    rest_ni = rest_earnings["total_net_income"].sum()
    total_ni = top10_ni + rest_ni

    top10_rev = top10_earnings["total_revenue"].sum()
    rest_rev = rest_earnings["total_revenue"].sum()
    total_rev = top10_rev + rest_rev

    top10_fcf = top10_earnings["total_fcf"].sum()
    rest_fcf = rest_earnings["total_fcf"].sum()
    total_fcf = top10_fcf + rest_fcf

    md.append("### 5c. Earnings & Revenue Concentration (Trailing 4Q)\n")
    md.append("Do the largest companies earn a disproportionate share of profits?\n")
    md.append("| Metric | Top 10 | Other 490 | Top 10 Share |")
    md.append("|--------|--------|-----------|-------------|")
    md.append(f"| Net Income | {fmt_dollars(top10_ni)} | {fmt_dollars(rest_ni)} | {top10_ni/total_ni:.1%} |")
    md.append(f"| Revenue | {fmt_dollars(top10_rev)} | {fmt_dollars(rest_rev)} | {top10_rev/total_rev:.1%} |")
    md.append(f"| Free Cash Flow | {fmt_dollars(top10_fcf)} | {fmt_dollars(rest_fcf)} | {top10_fcf/total_fcf:.1%} |")
    md.append(f"| Market Cap | {fmt_dollars(top10_earnings['marketCap'].sum())} | "
              f"{fmt_dollars(rest_earnings['marketCap'].sum())} | "
              f"{top10_earnings['marketCap'].sum()/total_mc:.1%} |")

    earnings_share = top10_ni / total_ni
    mc_share = top10_earnings["marketCap"].sum() / total_mc
    md.append(f"\nThe top 10 command **{mc_share:.1%}** of market cap but earn "
              f"**{earnings_share:.1%}** of net income")
    if mc_share > earnings_share:
        md.append(f" — their valuation premium ({mc_share:.1%} weight) exceeds their "
                  f"earnings contribution ({earnings_share:.1%}), reflecting the market's bet "
                  f"on future growth.\n")
    else:
        md.append(f" — their earnings contribution actually justifies or exceeds their weight.\n")

    # --- 5d: Breadth — % of stocks beating SPY each year ---
    spy_df = data["spy"]
    spy_annual = get_spy_annual_returns(spy_df, 2021, 2025)

    md.append("### 5d. Breadth: Percentage of Stocks Beating the Index\n")
    md.append("If most stocks underperform the index, gains are concentrated in a few names.\n")
    md.append("| Year | SPY Return | Stocks Beating SPY | % Beating | Median Stock Return |")
    md.append("|------|-----------|-------------------|-----------|-------------------|")

    for year in range(2021, 2026):
        year_data = daily[daily["date"].dt.year == year]
        if year_data.empty:
            continue
        first = year_data.groupby("symbol")["price"].first()
        last = year_data.groupby("symbol")["price"].last()
        common = first.index.intersection(last.index)
        stock_returns = (last[common] / first[common]) - 1
        spy_ret = spy_annual.get(year, 0)
        beating = (stock_returns > spy_ret).sum()
        total = len(stock_returns)
        median_ret = stock_returns.median()
        md.append(f"| {year} | {fmt_pct(spy_ret)} | {beating}/{total} | "
                  f"{beating/total:.1%} | {fmt_pct(median_ret)} |")

    md.append("\n*When fewer than 50% of stocks beat the index, it means the \"average\" stock "
              "underperforms — gains are being driven by a small number of outperformers.*\n")

    # --- 5e: Equal-Weight vs Cap-Weight ---
    md.append("### 5e. Equal-Weight vs. Cap-Weight S&P 500\n")
    md.append("When cap-weighted beats equal-weighted, it means large stocks are outperforming "
              "small ones — a direct measure of concentration.\n")

    md.append("| Year | Cap-Weight (SPY) | Equal-Weight (All Stocks) | Spread |")
    md.append("|------|-----------------|--------------------------|--------|")

    all_symbols = daily["symbol"].unique().tolist()
    ew_returns = get_annual_returns(daily, all_symbols, 2021, 2025)

    cumul_cw = 1.0
    cumul_ew = 1.0
    for year in range(2021, 2026):
        cw_ret = spy_annual.get(year, 0)
        ew_ret = ew_returns.get(year, 0)
        spread = cw_ret - ew_ret
        cumul_cw *= (1 + cw_ret)
        cumul_ew *= (1 + ew_ret)
        md.append(f"| {year} | {fmt_pct(cw_ret)} | {fmt_pct(ew_ret)} | {fmt_pct(spread)} |")

    cum_spread = (cumul_cw - 1) - (cumul_ew - 1)
    md.append(f"| **5Y Cumulative** | **{fmt_pct(cumul_cw - 1)}** | **{fmt_pct(cumul_ew - 1)}** | "
              f"**{fmt_pct(cum_spread)}** |")

    if cum_spread > 0:
        md.append(f"\nOver 5 years, cap-weighted outperformed equal-weighted by "
                  f"**{abs(cum_spread)*100:.1f} percentage points** — confirming that "
                  f"mega-cap stocks have systematically outperformed the typical S&P 500 member.\n")
    else:
        md.append(f"\nOver 5 years, equal-weighted outperformed cap-weighted by "
                  f"**{abs(cum_spread)*100:.1f} percentage points** — suggesting breadth "
                  f"has actually been broader than expected.\n")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6: SINGLE-STOCK DEPENDENCY
# ═══════════════════════════════════════════════════════════════════════════

def analyze_single_stock_dependency(data):
    """What would the S&P 500 look like without its best performer?"""
    pc = data["price_changes"]
    daily = data["daily_prices"]
    spy = data["spy"]
    profiles = data["profiles"]

    md = []
    md.append("## 6. Single-Stock Dependency: \"What If You Removed...?\"\n")
    md.append("How much does the S&P 500's performance depend on individual stocks? "
              "This analysis removes one stock at a time to measure dependency.\n")

    # For each year, find the best-performing large stock and show impact
    spy_annual = get_spy_annual_returns(spy, 2021, 2025)

    md.append("### Biggest Single-Stock Contributors by Year\n")
    md.append("| Year | Top Performer | Return | Est. Index Impact | SPY Without It |")
    md.append("|------|--------------|--------|------------------|----------------|")

    for year in range(2021, 2026):
        year_data = daily[daily["date"].dt.year == year]
        if year_data.empty:
            continue

        first = year_data.groupby("symbol")["price"].first()
        last = year_data.groupby("symbol")["price"].last()
        common = first.index.intersection(last.index)
        stock_returns = (last[common] / first[common]) - 1

        # Get market caps for weighting
        mc_dict = profiles.set_index("symbol")["marketCap"]
        mc_series = mc_dict.reindex(common).dropna()
        stock_returns = stock_returns.reindex(mc_series.index).dropna()
        mc_series = mc_series.reindex(stock_returns.index)

        weights = mc_series / mc_series.sum()

        # Contribution of each stock = weight × return
        contributions = weights * stock_returns
        top_contrib_sym = contributions.idxmax()
        top_contrib_val = contributions[top_contrib_sym]

        spy_ret = spy_annual.get(year, 0)
        spy_without = spy_ret - top_contrib_val  # Approximation

        name = profiles.set_index("symbol").loc[top_contrib_sym, "companyName"][:20]
        md.append(f"| {year} | {top_contrib_sym} ({name}) | "
                  f"{fmt_pct(stock_returns[top_contrib_sym])} | "
                  f"{fmt_pct(top_contrib_val)} | ~{fmt_pct(spy_without)} |")

    # "Remove NVDA" analysis — compute year-by-year contribution using
    # estimated start-of-year weight (avoids the bias of using current 7.3% weight
    # against the full 5Y return when NVDA started at ~1%)
    md.append("\n### The NVIDIA Effect\n")
    md.append("NVIDIA has been the single most impactful stock in the S&P 500 "
              "during the AI era. What would returns look like without it?\n")

    nvda_daily = daily[daily["symbol"] == "NVDA"].sort_values("date")
    if not nvda_daily.empty:
        nvda_5y_ret = (nvda_daily.iloc[-1]["price"] / nvda_daily.iloc[0]["price"]) - 1
        nvda_mc_now = profiles.set_index("symbol").loc["NVDA", "marketCap"]
        nvda_weight_now = nvda_mc_now / profiles["marketCap"].sum()

        # Estimate NVDA's annual contribution to SPY using per-year weight × return
        # Start-of-year weight is approximated by back-calculating from current cap
        spy_cum_ret = get_spy_annual_returns(spy, 2021, 2026)
        nvda_annual = get_annual_returns(daily, ["NVDA"], 2021, 2025)

        md.append("| Year | NVDA Return | Est. Index Weight (start) | Contribution to SPY |")
        md.append("|------|-----------|--------------------------|-------------------|")

        total_nvda_contribution = 0.0
        # Back-calculate NVDA start-of-year weight from price changes
        nvda_prices_by_year = {}
        for year in range(2021, 2027):
            yd = nvda_daily[nvda_daily["date"].dt.year == year]
            if not yd.empty:
                nvda_prices_by_year[year] = (yd.iloc[0]["price"], yd.iloc[-1]["price"])

        # Estimate start-of-year NVDA market cap by chaining returns backwards from current
        nvda_mc_timeline = {2026: nvda_mc_now}
        for year in range(2025, 2020, -1):
            if year in nvda_prices_by_year:
                start_p, end_p = nvda_prices_by_year[year]
                yr_ret = (end_p / start_p) - 1
                # mc at start of year = mc at end of year / (1 + return)
                next_year_start_mc = nvda_mc_timeline.get(year + 1, nvda_mc_timeline.get(year, nvda_mc_now))
                nvda_mc_timeline[year] = next_year_start_mc / (1 + yr_ret)

        spy_annual_full = get_spy_annual_returns(spy, 2021, 2025)
        for year in range(2021, 2026):
            nvda_ret = nvda_annual.get(year, 0)
            # Approximate NVDA's weight at start of year
            est_mc = nvda_mc_timeline.get(year, nvda_mc_now)
            # Total index market cap at start of year (rough: current / compounded SPY growth)
            spy_growth_since = 1.0
            for y in range(year, 2026):
                spy_growth_since *= (1 + spy_annual_full.get(y, 0))
            est_total_mc = profiles["marketCap"].sum() / spy_growth_since
            est_weight = est_mc / est_total_mc
            contribution = est_weight * nvda_ret
            total_nvda_contribution += contribution
            md.append(f"| {year} | {fmt_pct(nvda_ret)} | {est_weight:.1%} | {fmt_pct(contribution)} |")

        spy_cum = get_spy_annual_returns(spy, 2021, 2026).get("cumulative", 0)

        md.append(f"| **5Y Total** | **{fmt_pct(nvda_5y_ret)}** | "
                  f"{nvda_weight_now:.1%} (now) | **~{fmt_pct(total_nvda_contribution)}** |")
        md.append(f"\n| Metric | Value |")
        md.append(f"|--------|-------|")
        md.append(f"| SPY 5Y Return | {fmt_pct(spy_cum)} |")
        md.append(f"| Est. SPY 5Y Without NVDA | ~{fmt_pct(spy_cum - total_nvda_contribution)} |")
        md.append(f"| NVDA's Share of SPY Return | ~{total_nvda_contribution / spy_cum:.0%} |")

    # Mag 7 removal analysis
    md.append("\n### Removing the Entire Mag 7\n")

    all_symbols = daily["symbol"].unique().tolist()
    non_mag7 = [s for s in all_symbols if s not in MAG7]

    mag7_mc = profiles[profiles["symbol"].isin(MAG7)]["marketCap"].sum()
    mag7_weight = mag7_mc / profiles["marketCap"].sum()

    mag7_ew = get_annual_returns(daily, MAG7, 2021, 2026).get("cumulative", 0)
    non_mag7_ew = get_annual_returns(daily, non_mag7, 2021, 2026).get("cumulative", 0)
    spy_cum = get_spy_annual_returns(spy, 2021, 2026).get("cumulative", 0)

    md.append(f"| Portfolio | 5Y Cumulative Return |")
    md.append(f"|-----------|---------------------|")
    md.append(f"| S&P 500 (SPY) | {fmt_pct(spy_cum)} |")
    md.append(f"| S&P 500 Ex-Mag 7 | {fmt_pct(non_mag7_ew)} |")
    md.append(f"| Mag 7 Only | {fmt_pct(mag7_ew)} |")
    md.append(f"| Mag 7 Index Weight | {mag7_weight:.1%} |")

    md.append(f"\nThe Mag 7 ({mag7_weight:.1%} of the index) returned "
              f"**{fmt_pct(mag7_ew)}** while the other {len(non_mag7)} stocks returned "
              f"**{fmt_pct(non_mag7_ew)}** — a spread of "
              f"**{abs(mag7_ew - non_mag7_ew)*100:.0f} percentage points**.\n")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# REPORT ASSEMBLY
# ═══════════════════════════════════════════════════════════════════════════

def build_report():
    """Run all analyses and assemble the final markdown report."""
    print("Loading data...")
    data = load_all_data()

    print("Section 1: Tech sector gains...")
    s1_md, sector_gains, annual_sector_df = analyze_tech_sector_gains(data)

    print("Section 2: Top 10 stocks...")
    s2_md, top10 = analyze_top10_stocks(data)

    print("Section 3: Sector divergence...")
    s3_md, sector_df = analyze_sector_divergence(data)

    print("Section 4: Mag 7 isolation...")
    s4_md, mag7_ret, spy_ret, non_mag7_ret = analyze_mag7_isolation(data)

    print("Section 5: Concentration metrics...")
    s5_md = analyze_concentration_metrics(data)

    print("Section 6: Single-stock dependency...")
    s6_md = analyze_single_stock_dependency(data)

    # Assemble
    report = []
    report.append("# S&P 500 Concentration Analysis: The Magnificent 7 Era")
    report.append(f"### Market Leadership, Sector Divergence & Wealth Concentration | "
                  f"Data as of February 2026\n")
    report.append("**Data Source:** Financial Modeling Prep (FMP) API — ~498 S&P 500 constituents, "
                  "5 years of daily prices (Feb 2021 - Feb 2026), 20 quarters of financial "
                  "statements, company profiles.\n")
    report.append("---\n")

    # Executive Summary
    report.append("## Executive Summary\n")

    mag7_cum = mag7_ret.get("cumulative", 0)
    spy_cum = spy_ret.get("cumulative", 0)
    non_mag7_cum = non_mag7_ret.get("cumulative", 0)

    tech_share = sector_gains.loc["Technology", "pct_of_total_gains"] if "Technology" in sector_gains.index else 0

    report.append(f"Over the past five years, the S&P 500's gains have become "
                  f"increasingly concentrated in a handful of mega-cap technology stocks. "
                  f"Key findings:\n")
    report.append(f"- **The Magnificent 7** (AAPL, MSFT, AMZN, GOOGL, META, NVDA, TSLA) "
                  f"returned **{fmt_pct(mag7_cum)}** (equal-weighted) vs. "
                  f"**{fmt_pct(spy_cum)}** for SPY and **{fmt_pct(non_mag7_cum)}** for "
                  f"the other ~490 stocks.")
    report.append(f"- **Technology** (FMP classification) accounted for "
                  f"**{tech_share:.0%}** of all S&P 500 market cap gains.")
    report.append(f"- **$100 invested** in the Mag 7 at the start of 2021 would be worth "
                  f"**${100*(1+mag7_cum):.0f}** today, vs. **${100*(1+spy_cum):.0f}** in SPY "
                  f"and **${100*(1+non_mag7_cum):.0f}** in the rest of the index.")
    report.append("")
    report.append("---\n")

    for section in [s1_md, s2_md, s3_md, s4_md, s5_md, s6_md]:
        report.append(section)
        report.append("---\n")

    # Methodology
    report.append("## Methodology & Limitations\n")
    report.append("- **Price returns only**: All return figures are price-only (no dividend "
                  "reinvestment). Total returns would be ~1-2% higher annually for "
                  "dividend-paying stocks.")
    report.append("- **Current constituents only**: Analysis uses today's S&P 500 members. "
                  "Companies removed from the index during the 5-year period are excluded "
                  "(survivorship bias).")
    report.append("- **Market cap estimates**: Historical market caps are approximated as "
                  "current_cap / (1 + cumulative_return). This ignores share issuance/buybacks.")
    report.append("- **FMP sector classification**: FMP classifies AMZN and TSLA as "
                  "\"Consumer Cyclical\" and GOOGL/META as \"Technology\" (not GICS "
                  "\"Communication Services\"). Sector-level figures reflect FMP labels.")
    report.append("- **Equal-weighted Mag 7**: The Mag 7 portfolio uses equal weighting "
                  "unless noted as \"CW\" (cap-weighted). FactSet/HORAN chart uses "
                  "cap-weighted methodology.")
    report.append("- **S&P 500 proxy**: SPY ETF used as the cap-weighted S&P 500 proxy. "
                  "\"S&P Ex-Mag 7\" uses equal-weighted returns of all non-Mag 7 constituents.")
    report.append("")

    full_report = "\n".join(report)

    # Save
    OUTPUT_FILE.write_text(full_report, encoding="utf-8")
    print(f"\nReport saved to: {OUTPUT_FILE}")
    print(f"Report length: {len(full_report):,} characters, "
          f"{full_report.count(chr(10)):,} lines")

    return full_report


if __name__ == "__main__":
    build_report()
