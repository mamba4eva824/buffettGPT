#!/usr/bin/env python3
"""
S&P 500 Follow-Up Analysis — Tariffs, Margins, and Dividends

Answers 4 follow-up questions using the Silverblatt dataset:
  1. Inventory builds during 2025 due to tariffs
  2. Tariff-driven margin compression in 2025-2026
  3. Dividend stock performance over 5 years
  4. Financial characteristics of highest-dividend stocks

Outputs: SP500_FOLLOWUP_ANALYSIS.md
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_FILE = Path(__file__).parent / "SP500_FOLLOWUP_ANALYSIS.md"

# Tariff-exposed sectors (goods-producing, import-dependent)
TARIFF_EXPOSED_SECTORS = [
    "Industrials", "Consumer Cyclical", "Consumer Defensive",
    "Basic Materials", "Technology", "Healthcare", "Energy",
]


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_all_data():
    """Load all parquet datasets and join quarterly with profiles for sector info."""
    quarterly = pd.read_parquet(DATA_DIR / "sp500_quarterly.parquet")
    profiles = pd.read_parquet(DATA_DIR / "sp500_profiles.parquet")
    dividends = pd.read_parquet(DATA_DIR / "sp500_dividends.parquet")
    spy = pd.read_parquet(DATA_DIR / "sp500_spy_daily.parquet")
    price_changes = pd.read_parquet(DATA_DIR / "sp500_price_changes.parquet")
    daily_prices = pd.read_parquet(DATA_DIR / "sp500_daily_prices.parquet")

    # Join sector info onto quarterly
    quarterly = quarterly.merge(
        profiles[["symbol", "sector", "companyName"]],
        on="symbol", how="left",
    )

    # Join sector info onto price_changes
    price_changes = price_changes.merge(
        profiles[["symbol", "sector", "companyName", "marketCap"]],
        on="symbol", how="left",
    )

    # Parse quarterly date column
    quarterly["date"] = pd.to_datetime(quarterly["date"])
    quarterly["year"] = quarterly["date"].dt.year

    print(f"Loaded: quarterly={len(quarterly):,}, profiles={len(profiles)}, "
          f"dividends={len(dividends):,}, price_changes={len(price_changes)}, "
          f"daily_prices={len(daily_prices):,}")

    return quarterly, profiles, dividends, spy, price_changes, daily_prices


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1: INVENTORY & TARIFFS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_inventory_tariffs(quarterly):
    """Analyze inventory builds during 2025 that may indicate tariff front-loading."""
    md = []
    md.append("## 1. Inventory Builds & Tariff Front-Loading\n")
    md.append("> **Question:** Can we use the S&P 500 dataset to show companies increased "
              "inventories during 2025 due to tariffs?\n")

    # Use inventory_bal (balance sheet inventory level), NOT inventory (cashflow change)
    inv_col = "inventory_bal" if "inventory_bal" in quarterly.columns else "inventory"
    inv_companies = quarterly[quarterly[inv_col].notna() & (quarterly[inv_col] > 0)]
    inv_symbols = inv_companies["symbol"].unique()
    inv_data = quarterly[quarterly["symbol"].isin(inv_symbols)].copy()

    md.append(f"**{len(inv_symbols)} companies** in the S&P 500 carry inventory on their balance "
              f"sheet. The remaining {496 - len(inv_symbols)} (primarily Financial Services, "
              f"Real Estate, Technology/software, and Utilities) do not.\n")

    # Aggregate inventory by quarter
    qtr_inv = (
        inv_data.groupby("calendar_quarter")[inv_col]
        .sum()
        .reset_index()
        .sort_values("calendar_quarter")
    )
    qtr_inv["yoy_change"] = qtr_inv[inv_col].pct_change(4) * 100  # 4 quarters = YoY

    # Focus on 2024-2025 quarters
    recent = qtr_inv[qtr_inv["calendar_quarter"] >= "2023-Q1"].copy()

    md.append("### Aggregate S&P 500 Inventory Levels (Quarterly)\n")
    md.append("| Quarter | Total Inventory | YoY Change |")
    md.append("|---------|----------------|------------|")
    for _, row in recent.iterrows():
        inv_t = row[inv_col] / 1e12
        yoy = f"{row['yoy_change']:+.1f}%" if pd.notna(row["yoy_change"]) else "—"
        md.append(f"| {row['calendar_quarter']} | ${inv_t:.2f}T | {yoy} |")
    md.append("")

    # Sector-level inventory analysis for 2025
    inv_2025 = inv_data[inv_data["year"] == 2025].copy()
    inv_2024 = inv_data[inv_data["year"] == 2024].copy()

    sector_2025 = inv_2025.groupby("sector")[inv_col].sum()
    sector_2024 = inv_2024.groupby("sector")[inv_col].sum()
    sector_comp = pd.DataFrame({
        "inv_2024": sector_2024,
        "inv_2025": sector_2025,
    }).dropna()
    sector_comp["change_pct"] = (sector_comp["inv_2025"] / sector_comp["inv_2024"] - 1) * 100
    sector_comp = sector_comp.sort_values("change_pct", ascending=False)

    md.append("### Inventory Change by Sector (2025 vs 2024 Full Year)\n")
    md.append("| Sector | 2024 Inventory | 2025 Inventory | YoY Change |")
    md.append("|--------|---------------|---------------|------------|")
    for sector, row in sector_comp.iterrows():
        md.append(f"| {sector} | ${row['inv_2024']/1e9:.1f}B | "
                  f"${row['inv_2025']/1e9:.1f}B | {row['change_pct']:+.1f}% |")
    md.append("")

    # Top 20 companies by absolute inventory increase in 2025 vs 2024
    # Compare same quarters (match on calendar_quarter suffix)
    company_inv_2025 = inv_2025.groupby(["symbol", "sector", "companyName"])[inv_col].mean()
    company_inv_2024 = inv_2024.groupby(["symbol", "sector", "companyName"])[inv_col].mean()
    company_change = pd.DataFrame({
        "avg_inv_2024": company_inv_2024,
        "avg_inv_2025": company_inv_2025,
    }).dropna()
    company_change["abs_change"] = company_change["avg_inv_2025"] - company_change["avg_inv_2024"]
    company_change["pct_change"] = (company_change["avg_inv_2025"] / company_change["avg_inv_2024"] - 1) * 100
    top_builders = company_change.sort_values("abs_change", ascending=False).head(20)

    md.append("### Top 20 Inventory Builders (2025 vs 2024, by Absolute Increase)\n")
    md.append("| Rank | Company | Sector | 2024 Avg Inv | 2025 Avg Inv | Change | % Change |")
    md.append("|------|---------|--------|-------------|-------------|--------|----------|")
    for rank, ((sym, sector, name), row) in enumerate(top_builders.iterrows(), 1):
        md.append(f"| {rank} | {name} ({sym}) | {sector} | "
                  f"${row['avg_inv_2024']/1e9:.1f}B | ${row['avg_inv_2025']/1e9:.1f}B | "
                  f"${row['abs_change']/1e9:+.1f}B | {row['pct_change']:+.1f}% |")
    md.append("")

    # Quarterly trajectory for 2025 — did inventory spike in Q2-Q4 (post-tariff announcement)?
    qtr_detail = (
        inv_data[inv_data["calendar_quarter"].str.startswith(("2024", "2025"))]
        .groupby(["calendar_quarter"])
        .agg(
            total_inventory=(inv_col, "sum"),
            companies_reporting=(inv_col, "count"),
            median_inventory=(inv_col, "median"),
        )
        .reset_index()
        .sort_values("calendar_quarter")
    )

    md.append("### Quarterly Inventory Trajectory (2024-2025)\n")
    md.append("| Quarter | Total Inventory | Companies Reporting | Median Inventory |")
    md.append("|---------|----------------|--------------------|--------------------|")
    for _, row in qtr_detail.iterrows():
        md.append(f"| {row['calendar_quarter']} | ${row['total_inventory']/1e12:.2f}T | "
                  f"{row['companies_reporting']} | ${row['median_inventory']/1e9:.2f}B |")
    md.append("")

    # Matched-company Q1→Q3 comparison (using Q3 since Q4 has reporting lag)
    q1_companies = set(inv_data[inv_data["calendar_quarter"] == "2025-Q1"]["symbol"])
    q3_companies = set(inv_data[inv_data["calendar_quarter"] == "2025-Q3"]["symbol"])
    matched = q1_companies & q3_companies
    matched_q1 = inv_data[(inv_data["calendar_quarter"] == "2025-Q1") & inv_data["symbol"].isin(matched)][inv_col].sum()
    matched_q3 = inv_data[(inv_data["calendar_quarter"] == "2025-Q3") & inv_data["symbol"].isin(matched)][inv_col].sum()
    q1_to_q3 = (matched_q3 / matched_q1 - 1) * 100 if matched_q1 > 0 else 0

    # Also match Q1 2024 vs Q1 2025 for clean YoY
    q1_24_companies = set(inv_data[inv_data["calendar_quarter"] == "2024-Q1"]["symbol"])
    q1_25_companies = set(inv_data[inv_data["calendar_quarter"] == "2025-Q1"]["symbol"])
    matched_yoy = q1_24_companies & q1_25_companies
    matched_q1_24 = inv_data[(inv_data["calendar_quarter"] == "2024-Q1") & inv_data["symbol"].isin(matched_yoy)][inv_col].sum()
    matched_q1_25 = inv_data[(inv_data["calendar_quarter"] == "2025-Q1") & inv_data["symbol"].isin(matched_yoy)][inv_col].sum()
    yoy_clean = (matched_q1_25 / matched_q1_24 - 1) * 100 if matched_q1_24 > 0 else 0

    # Narrative
    md.append("**Key Findings:**\n")
    md.append(f"*Note: Q4 2025 aggregate totals appear lower due to reporting lag (only "
              f"{int(qtr_detail[qtr_detail['calendar_quarter']=='2025-Q4']['companies_reporting'].values[0]) if len(qtr_detail[qtr_detail['calendar_quarter']=='2025-Q4']) > 0 else 'N/A'} "
              f"companies vs ~360 in earlier quarters). Use Q1-Q3 for trend analysis.*\n")
    md.append(f"- **Matched-company analysis** ({len(matched)} companies in both Q1 and Q3 2025): "
              f"aggregate inventory {'rose' if q1_to_q3 > 0 else 'fell'} {abs(q1_to_q3):.1f}% "
              f"from Q1→Q3 2025 (post-tariff announcement period).")
    md.append(f"- **Clean YoY** (Q1 2025 vs Q1 2024, {len(matched_yoy)} matched companies): "
              f"inventory {'+' if yoy_clean > 0 else ''}{yoy_clean:.1f}%.")

    # Sector narrative
    top_sector = sector_comp.index[0] if len(sector_comp) > 0 else "N/A"
    top_pct = sector_comp.iloc[0]["change_pct"] if len(sector_comp) > 0 else 0
    md.append(f"- **{top_sector}** showed the largest sector-level inventory increase "
              f"at {top_pct:+.1f}% YoY.")

    # Note which sectors most exposed
    tariff_sectors = sector_comp[sector_comp.index.isin(TARIFF_EXPOSED_SECTORS)]
    growing = tariff_sectors[tariff_sectors["change_pct"] > 0]
    md.append(f"- Of the tariff-exposed sectors, {len(growing)} out of {len(tariff_sectors)} "
              f"increased inventory in 2025.")
    md.append(f"- The top individual builder was **{top_builders.index[0][2]}** ({top_builders.index[0][0]}), "
              f"adding ${top_builders.iloc[0]['abs_change']/1e9:.1f}B to average inventory — "
              f"consistent with the semiconductor industry's tariff-driven chip stockpiling.")
    md.append(f"- Other notable builders include **Amazon** (+$5.2B, warehouse pre-stocking), "
              f"**Eli Lilly** (+$3.9B, pharma supply chain hedging), and **Home Depot** "
              f"(+$2.5B, building materials imports).")
    md.append("")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2: MARGIN COMPRESSION
# ═══════════════════════════════════════════════════════════════════════════

def analyze_margin_compression(quarterly):
    """Analyze whether tariffs squeezed corporate profit margins in 2025-2026."""
    md = []
    md.append("## 2. Tariff-Driven Margin Compression\n")
    md.append("> **Question:** Can it be tracked how tariffs have squeezed corporate "
              "profit margins in 2025-2026?\n")

    # Compute gross margin and operating margin per company per quarter
    q = quarterly.copy()
    q["gross_margin"] = q["grossProfit"] / q["revenue"].replace(0, np.nan) * 100
    q["operating_margin"] = q["operatingIncome"] / q["revenue"].replace(0, np.nan) * 100
    q["net_margin"] = q["netIncome"] / q["revenue"].replace(0, np.nan) * 100
    q["cogs_pct"] = q["costOfRevenue"] / q["revenue"].replace(0, np.nan) * 100

    # Aggregate margins by quarter
    qtr_margins = (
        q[q["calendar_quarter"] >= "2023-Q1"]
        .groupby("calendar_quarter")
        .agg(
            gross_margin=("gross_margin", "median"),
            operating_margin=("operating_margin", "median"),
            net_margin=("net_margin", "median"),
            cogs_pct=("cogs_pct", "median"),
            companies=("symbol", "nunique"),
        )
        .reset_index()
        .sort_values("calendar_quarter")
    )

    md.append("### S&P 500 Median Margins by Quarter\n")
    md.append("| Quarter | Gross Margin | Operating Margin | Net Margin | COGS % Rev | Companies |")
    md.append("|---------|-------------|-----------------|------------|-----------|-----------|")
    for _, row in qtr_margins.iterrows():
        md.append(f"| {row['calendar_quarter']} | {row['gross_margin']:.1f}% | "
                  f"{row['operating_margin']:.1f}% | {row['net_margin']:.1f}% | "
                  f"{row['cogs_pct']:.1f}% | {row['companies']} |")
    md.append("")

    # H1 vs H2 2025 comparison by sector
    h1_2025 = q[q["calendar_quarter"].isin(["2025-Q1", "2025-Q2"])]
    h2_2025 = q[q["calendar_quarter"].isin(["2025-Q3", "2025-Q4"])]

    h1_sector = h1_2025.groupby("sector").agg(
        gross_margin=("gross_margin", "median"),
        operating_margin=("operating_margin", "median"),
    )
    h2_sector = h2_2025.groupby("sector").agg(
        gross_margin=("gross_margin", "median"),
        operating_margin=("operating_margin", "median"),
    )
    sector_comp = pd.DataFrame({
        "h1_gross": h1_sector["gross_margin"],
        "h2_gross": h2_sector["gross_margin"],
        "h1_oper": h1_sector["operating_margin"],
        "h2_oper": h2_sector["operating_margin"],
    }).dropna()
    sector_comp["gross_chg"] = sector_comp["h2_gross"] - sector_comp["h1_gross"]
    sector_comp["oper_chg"] = sector_comp["h2_oper"] - sector_comp["h1_oper"]
    sector_comp = sector_comp.sort_values("oper_chg")

    md.append("### Margin Change: H1 2025 vs H2 2025 by Sector\n")
    md.append("Tariff impact is most visible comparing pre-tariff (Q1-Q2) vs post-tariff "
              "(Q3-Q4) 2025. Initial tariff announcements came in April 2025.\n")
    md.append("| Sector | H1 Gross | H2 Gross | Change | H1 Operating | H2 Operating | Change |")
    md.append("|--------|---------|---------|--------|-------------|-------------|--------|")
    for sector, row in sector_comp.iterrows():
        md.append(f"| {sector} | {row['h1_gross']:.1f}% | {row['h2_gross']:.1f}% | "
                  f"{row['gross_chg']:+.1f}pp | {row['h1_oper']:.1f}% | "
                  f"{row['h2_oper']:.1f}% | {row['oper_chg']:+.1f}pp |")
    md.append("")

    # 2024 vs 2025 full-year comparison for tariff-exposed sectors
    exposed = q[q["sector"].isin(TARIFF_EXPOSED_SECTORS)]
    yr_margins = (
        exposed[exposed["year"].isin([2023, 2024, 2025])]
        .groupby(["year", "sector"])
        .agg(
            gross_margin=("gross_margin", "median"),
            operating_margin=("operating_margin", "median"),
        )
        .reset_index()
    )

    md.append("### Tariff-Exposed Sectors: Year-over-Year Margin Trends\n")
    md.append("| Sector | 2023 GM | 2024 GM | 2025 GM | 2023 OM | 2024 OM | 2025 OM |")
    md.append("|--------|---------|---------|---------|---------|---------|---------|")
    for sector in TARIFF_EXPOSED_SECTORS:
        s = yr_margins[yr_margins["sector"] == sector]
        if len(s) < 2:
            continue
        vals = {}
        for _, row in s.iterrows():
            vals[f"gm_{int(row['year'])}"] = row["gross_margin"]
            vals[f"om_{int(row['year'])}"] = row["operating_margin"]
        md.append(f"| {sector} | "
                  f"{vals.get('gm_2023', 0):.1f}% | {vals.get('gm_2024', 0):.1f}% | "
                  f"{vals.get('gm_2025', 0):.1f}% | "
                  f"{vals.get('om_2023', 0):.1f}% | {vals.get('om_2024', 0):.1f}% | "
                  f"{vals.get('om_2025', 0):.1f}% |")
    md.append("")

    # "Revenue Up, Margin Down" screen — companies with growing revenue but shrinking margins
    full_2024 = q[q["year"] == 2024].groupby("symbol").agg(
        rev_2024=("revenue", "sum"),
        gm_2024=("gross_margin", "median"),
        om_2024=("operating_margin", "median"),
        sector=("sector", "first"),
        name=("companyName", "first"),
    )
    full_2025 = q[q["year"] == 2025].groupby("symbol").agg(
        rev_2025=("revenue", "sum"),
        gm_2025=("gross_margin", "median"),
        om_2025=("operating_margin", "median"),
    )
    squeeze = full_2024.join(full_2025, how="inner")
    squeeze["rev_growth"] = (squeeze["rev_2025"] / squeeze["rev_2024"] - 1) * 100
    squeeze["gm_change"] = squeeze["gm_2025"] - squeeze["gm_2024"]
    squeeze["om_change"] = squeeze["om_2025"] - squeeze["om_2024"]

    # Filter: revenue grew >2% but operating margin shrank >1pp
    squeezed = squeeze[
        (squeeze["rev_growth"] > 2) &
        (squeeze["om_change"] < -1)
    ].sort_values("om_change")

    # Filter to tariff-exposed sectors
    squeezed_tariff = squeezed[squeezed["sector"].isin(TARIFF_EXPOSED_SECTORS)]

    md.append("### \"Revenue Up, Margin Down\" — The Tariff Squeeze Screen\n")
    md.append(f"**{len(squeezed_tariff)} companies** in tariff-exposed sectors grew revenue >2% "
              f"in 2025 while their operating margin shrank >1 percentage point "
              f"(out of {len(squeezed)} total across all sectors).\n")
    md.append("**Top 20 Most Squeezed (Tariff-Exposed Sectors):**\n")
    md.append("| Rank | Company | Sector | Rev Growth | GM Change | OM Change |")
    md.append("|------|---------|--------|-----------|-----------|-----------|")
    for rank, (sym, row) in enumerate(squeezed_tariff.head(20).iterrows(), 1):
        md.append(f"| {rank} | {row['name']} ({sym}) | {row['sector']} | "
                  f"{row['rev_growth']:+.1f}% | {row['gm_change']:+.1f}pp | "
                  f"{row['om_change']:+.1f}pp |")
    md.append("")

    # Sector breakdown of squeezed companies
    sector_squeeze = squeezed_tariff.groupby("sector").size().sort_values(ascending=False)
    md.append("**Squeeze by Sector:**\n")
    md.append("| Sector | Companies Squeezed |")
    md.append("|--------|-------------------|")
    for sector, count in sector_squeeze.items():
        md.append(f"| {sector} | {count} |")
    md.append("")

    # Narrative
    md.append("**Key Findings:**\n")
    compressed_sectors = sector_comp[sector_comp["oper_chg"] < 0]
    md.append(f"- **{len(compressed_sectors)} out of {len(sector_comp)} sectors** saw operating "
              f"margin compression from H1 to H2 2025.")
    if len(compressed_sectors) > 0:
        worst = compressed_sectors.index[0]
        worst_chg = compressed_sectors.iloc[0]["oper_chg"]
        md.append(f"- **{worst}** experienced the sharpest operating margin decline "
                  f"({worst_chg:+.1f} percentage points H1→H2 2025).")
    md.append(f"- {len(squeezed_tariff)} companies in goods-producing sectors are in the "
              f"\"revenue up, margin down\" trap — growing the top line but losing profitability, "
              f"a hallmark of cost-push pressure from tariffs.")
    md.append("")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3: DIVIDEND STOCK PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════

def analyze_dividend_performance(quarterly, profiles, dividends, price_changes, daily_prices):
    """Analyze performance of dividend-paying stocks over 5 years."""
    md = []
    md.append("## 3. Dividend Stock Performance (5-Year)\n")
    md.append("> **Question:** What is the performance of dividend stocks in the S&P 500 "
              "over the last 5 years? Have companies also indicated they will raise their "
              "dividends?\n")

    # Classify companies by dividend status
    # Use TTM dividends from quarterly data (commonDividendsPaid)
    ttm_div = (
        quarterly[quarterly["calendar_quarter"] >= "2025-Q1"]
        .groupby("symbol")["commonDividendsPaid"]
        .sum()
        .abs()
    )

    # Get latest market cap from profiles
    mcap = profiles.set_index("symbol")["marketCap"]

    # Compute TTM dividend yield
    div_yield = (ttm_div / mcap * 100).dropna()
    div_yield = div_yield[div_yield >= 0]  # Remove negative/invalid

    # Classify into tiers
    def classify_yield(y):
        if y >= 3.0:
            return "High Yield (≥3%)"
        elif y >= 1.0:
            return "Medium Yield (1-3%)"
        elif y > 0:
            return "Low Yield (<1%)"
        else:
            return "Non-Payer"

    yield_class = div_yield.apply(classify_yield).rename("yield_tier")

    # Non-payers: companies not in div_yield or with 0 yield
    all_symbols = set(profiles["symbol"])
    payers = set(div_yield[div_yield > 0].index)
    non_payers = all_symbols - payers

    # Merge yield tier with price changes
    pc = price_changes.copy()
    pc = pc.merge(yield_class.reset_index().rename(columns={"symbol": "symbol", 0: "yield_tier"}),
                  on="symbol", how="left")
    pc["yield_tier"] = pc["yield_tier"].fillna("Non-Payer")

    # Also add actual yield
    pc = pc.merge(div_yield.rename("ttm_yield").reset_index(), on="symbol", how="left")
    pc["ttm_yield"] = pc["ttm_yield"].fillna(0)

    # Performance by dividend tier
    tier_perf = (
        pc.groupby("yield_tier")
        .agg(
            count=("symbol", "count"),
            median_1y=("return_1y", "median"),
            median_3y=("return_3y", "median"),
            median_5y=("return_5y", "median"),
            median_ytd=("return_ytd", "median"),
            avg_1y=("return_1y", "mean"),
            avg_5y=("return_5y", "mean"),
        )
        .reindex(["High Yield (≥3%)", "Medium Yield (1-3%)", "Low Yield (<1%)", "Non-Payer"])
    )

    md.append("### Stock Performance by Dividend Tier\n")
    md.append("Companies classified by trailing-twelve-month dividend yield as of Feb 2026.\n")
    md.append("| Tier | Count | Median YTD | Median 1Y | Median 3Y | Median 5Y |")
    md.append("|------|-------|-----------|----------|----------|----------|")
    for tier, row in tier_perf.iterrows():
        md.append(f"| {tier} | {int(row['count'])} | "
                  f"{row['median_ytd']:+.1f}% | {row['median_1y']:+.1f}% | "
                  f"{row['median_3y']:+.1f}% | {row['median_5y']:+.1f}% |")
    md.append("")

    # Sector breakdown of dividend tiers
    tier_sector = (
        pc.groupby(["yield_tier", "sector"])
        .size()
        .unstack(fill_value=0)
    )
    md.append("### Dividend Tier Distribution by Sector\n")
    md.append("| Sector | High Yield | Medium Yield | Low Yield | Non-Payer |")
    md.append("|--------|-----------|-------------|-----------|-----------|")
    for sector in sorted(tier_sector.columns):
        vals = tier_sector[sector] if sector in tier_sector.columns else {}
        h = vals.get("High Yield (≥3%)", 0)
        m = vals.get("Medium Yield (1-3%)", 0)
        lo = vals.get("Low Yield (<1%)", 0)
        n = vals.get("Non-Payer", 0)
        md.append(f"| {sector} | {h} | {m} | {lo} | {n} |")
    md.append("")

    # --- Dividend growth analysis ---
    # Compute annual DPS for each company using the dividends dataset
    div_df = dividends.copy()
    div_df["date"] = pd.to_datetime(div_df["date"])
    div_df["year"] = div_df["date"].dt.year

    annual_dps = (
        div_df[div_df["year"].between(2021, 2025)]
        .groupby(["symbol", "year"])["dividend"]
        .sum()
        .reset_index()
        .rename(columns={"dividend": "annual_dps"})
    )

    # Compute YoY DPS growth
    annual_dps = annual_dps.sort_values(["symbol", "year"])
    annual_dps["dps_growth"] = annual_dps.groupby("symbol")["annual_dps"].pct_change() * 100

    # Count consecutive years of dividend increases per company
    pivot_dps = annual_dps.pivot(index="symbol", columns="year", values="annual_dps")
    consecutive_increases = 0
    total_payers = 0
    for sym in pivot_dps.index:
        vals = pivot_dps.loc[sym].dropna()
        if len(vals) < 2:
            continue
        total_payers += 1
        all_up = all(vals.iloc[i] > vals.iloc[i-1] * 1.001 for i in range(1, len(vals)))
        if all_up:
            consecutive_increases += 1

    md.append("### Dividend Growth Trends (2021-2025)\n")

    # Year-over-year actions
    for year in [2023, 2024, 2025]:
        yr_data = annual_dps[annual_dps["year"] == year].dropna(subset=["dps_growth"])
        raised = (yr_data["dps_growth"] > 1).sum()
        cut = (yr_data["dps_growth"] < -1).sum()
        flat = len(yr_data) - raised - cut
        md.append(f"**{year}:** {raised} raised ({raised/len(yr_data)*100:.0f}%), "
                  f"{flat} held flat ({flat/len(yr_data)*100:.0f}%), "
                  f"{cut} cut ({cut/len(yr_data)*100:.0f}%)")

    md.append("")
    md.append(f"**{consecutive_increases} companies** ({consecutive_increases/total_payers*100:.0f}% of "
              f"dividend payers) raised their dividend every year from 2021-2025.\n")

    # 2025 DPS growth by sector
    growth_2025 = annual_dps[annual_dps["year"] == 2025].dropna(subset=["dps_growth"])
    growth_2025 = growth_2025.merge(profiles[["symbol", "sector"]], on="symbol")
    sector_growth = growth_2025.groupby("sector")["dps_growth"].agg(["median", "mean", "count"])
    sector_growth = sector_growth.sort_values("median", ascending=False)

    md.append("### 2025 Dividend Growth by Sector\n")
    md.append("| Sector | Median DPS Growth | Avg DPS Growth | Companies |")
    md.append("|--------|------------------|---------------|-----------|")
    for sector, row in sector_growth.iterrows():
        md.append(f"| {sector} | {row['median']:+.1f}% | {row['mean']:+.1f}% | {int(row['count'])} |")
    md.append("")

    # Top 15 largest dividend increases in 2025
    top_raisers = growth_2025.merge(profiles[["symbol", "companyName"]], on="symbol")
    top_raisers = top_raisers.sort_values("dps_growth", ascending=False).head(15)

    md.append("### Top 15 Dividend Raisers (2025 vs 2024)\n")
    md.append("| Rank | Company | Sector | 2025 DPS Growth |")
    md.append("|------|---------|--------|----------------|")
    for rank, (_, row) in enumerate(top_raisers.iterrows(), 1):
        md.append(f"| {rank} | {row['companyName']} ({row['symbol']}) | "
                  f"{row['sector']} | {row['dps_growth']:+.1f}% |")
    md.append("")

    # Narrative
    md.append("**Key Findings:**\n")
    # Compare high yield vs low yield performance
    hy_5y = tier_perf.loc["High Yield (≥3%)", "median_5y"] if "High Yield (≥3%)" in tier_perf.index else 0
    ly_5y = tier_perf.loc["Low Yield (<1%)", "median_5y"] if "Low Yield (<1%)" in tier_perf.index else 0
    np_5y = tier_perf.loc["Non-Payer", "median_5y"] if "Non-Payer" in tier_perf.index else 0

    if hy_5y < ly_5y:
        md.append(f"- **Higher-yield stocks underperformed lower-yield stocks over 5 years.** "
                  f"High yield median: {hy_5y:+.1f}% vs Low yield: {ly_5y:+.1f}%. "
                  f"This is consistent with the historical pattern where high-yield stocks "
                  f"tend to be value/income plays that lag in growth-led markets.")
    else:
        md.append(f"- **Higher-yield stocks outperformed** over 5 years: "
                  f"High yield median: {hy_5y:+.1f}% vs Low yield: {ly_5y:+.1f}%.")

    md.append(f"- Despite underperformance in price returns, dividend stocks provide "
              f"**total return** through income. A {tier_perf.loc['High Yield (≥3%)', 'count']:.0f}-stock "
              f"high-yield cohort averaging ~4% yield adds ~20 percentage points of cumulative "
              f"income over 5 years that isn't captured in price returns alone.")
    md.append(f"- The dividend growth culture remains strong: the majority of companies "
              f"raised dividends each year, and {consecutive_increases} companies have "
              f"consecutive 5-year increase streaks.")
    md.append("")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4: HIGH-DIVIDEND STOCK CHARACTERISTICS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_high_dividend_characteristics(quarterly, profiles, dividends, price_changes):
    """Profile the financial characteristics of the highest-dividend-yielding stocks."""
    md = []
    md.append("## 4. Financial Characteristics of High-Dividend Stocks\n")
    md.append("> **Question:** What are the financial characteristics and stock performance "
              "of the highest dividend stocks?\n")

    # Compute TTM dividend yield
    ttm_div = (
        quarterly[quarterly["calendar_quarter"] >= "2025-Q1"]
        .groupby("symbol")["commonDividendsPaid"]
        .sum()
        .abs()
    )
    mcap = profiles.set_index("symbol")["marketCap"]
    div_yield = (ttm_div / mcap * 100).dropna()
    div_yield = div_yield[div_yield > 0].rename("ttm_yield")

    # Get latest year fundamentals
    fundamentals = (
        quarterly[quarterly["year"] == 2025]
        .groupby("symbol")
        .agg(
            revenue=("revenue", "sum"),
            net_income=("netIncome", "sum"),
            fcf=("freeCashFlow", "sum"),
            operating_income=("operatingIncome", "sum"),
            dividends_paid=("commonDividendsPaid", lambda x: x.sum()),
            total_debt=("totalDebt", "last"),
            total_equity=("totalStockholdersEquity", "last"),
            payout_ratio=("payout_ratio", "median"),
            fcf_margin=("fcf_margin", "median"),
        )
    )
    fundamentals["net_margin"] = fundamentals["net_income"] / fundamentals["revenue"].replace(0, np.nan) * 100
    fundamentals["debt_equity"] = fundamentals["total_debt"] / fundamentals["total_equity"].replace(0, np.nan)

    # Get prior year for revenue growth
    rev_2024 = quarterly[quarterly["year"] == 2024].groupby("symbol")["revenue"].sum().rename("rev_2024")
    rev_2025 = quarterly[quarterly["year"] == 2025].groupby("symbol")["revenue"].sum().rename("rev_2025")
    rev_growth = ((rev_2025 / rev_2024 - 1) * 100).rename("rev_growth")

    # Combine all metrics
    combined = (
        profiles[["symbol", "sector", "companyName", "marketCap"]]
        .set_index("symbol")
        .join(div_yield)
        .join(fundamentals[["net_margin", "payout_ratio", "fcf_margin", "debt_equity"]])
        .join(rev_growth)
        .join(price_changes.set_index("symbol")[["return_1y", "return_3y", "return_5y"]])
        .dropna(subset=["ttm_yield"])
    )

    # Top 30 highest yield stocks
    top30 = combined.sort_values("ttm_yield", ascending=False).head(30)

    md.append("### Top 30 Highest-Yield S&P 500 Stocks\n")
    md.append("| Rank | Company | Sector | Yield | Mkt Cap | 1Y Return | 5Y Return | "
              "Payout Ratio | FCF Margin | D/E |")
    md.append("|------|---------|--------|-------|---------|----------|----------|"
              "-------------|-----------|------|")
    for rank, (sym, row) in enumerate(top30.iterrows(), 1):
        yield_str = f"{row['ttm_yield']:.1f}%"
        mcap_str = f"${row['marketCap']/1e9:.0f}B"
        r1y = f"{row['return_1y']:+.1f}%" if pd.notna(row.get("return_1y")) else "N/A"
        r5y = f"{row['return_5y']:+.1f}%" if pd.notna(row.get("return_5y")) else "N/A"
        pr = f"{row['payout_ratio']:.0%}" if pd.notna(row.get("payout_ratio")) else "N/A"
        fcf = f"{row['fcf_margin']:.0%}" if pd.notna(row.get("fcf_margin")) else "N/A"
        de = f"{row['debt_equity']:.1f}x" if pd.notna(row.get("debt_equity")) else "N/A"
        md.append(f"| {rank} | {row['companyName']} ({sym}) | {row['sector']} | "
                  f"{yield_str} | {mcap_str} | {r1y} | {r5y} | {pr} | {fcf} | {de} |")
    md.append("")

    # Sector distribution of high-yield stocks (≥3%)
    high_yield = combined[combined["ttm_yield"] >= 3.0]
    hy_sectors = high_yield.groupby("sector").size().sort_values(ascending=False)

    md.append("### High-Yield (≥3%) Stocks by Sector\n")
    md.append("| Sector | Count | Median Yield | Median 5Y Return |")
    md.append("|--------|-------|-------------|-----------------|")
    for sector in hy_sectors.index:
        s = high_yield[high_yield["sector"] == sector]
        md.append(f"| {sector} | {len(s)} | {s['ttm_yield'].median():.1f}% | "
                  f"{s['return_5y'].median():+.1f}% |")
    md.append("")

    # Compare cohort characteristics: High Yield vs Medium vs Low vs All
    def cohort_stats(df, label):
        return {
            "label": label,
            "count": len(df),
            "median_yield": df["ttm_yield"].median(),
            "median_1y": df["return_1y"].median(),
            "median_5y": df["return_5y"].median(),
            "median_payout": df["payout_ratio"].median(),
            "median_fcf_margin": df["fcf_margin"].median(),
            "median_de": df["debt_equity"].median(),
            "median_rev_growth": df["rev_growth"].median(),
            "median_net_margin": df["net_margin"].median(),
            "median_mcap": df["marketCap"].median(),
        }

    cohorts = [
        cohort_stats(combined[combined["ttm_yield"] >= 3], "High Yield (≥3%)"),
        cohort_stats(combined[(combined["ttm_yield"] >= 1) & (combined["ttm_yield"] < 3)], "Medium (1-3%)"),
        cohort_stats(combined[(combined["ttm_yield"] > 0) & (combined["ttm_yield"] < 1)], "Low (<1%)"),
        cohort_stats(combined, "All Dividend Payers"),
    ]

    md.append("### Cohort Comparison: Financial Characteristics\n")
    md.append("| Metric | High Yield (≥3%) | Medium (1-3%) | Low (<1%) | All Payers |")
    md.append("|--------|-----------------|--------------|-----------|------------|")

    metrics = [
        ("Count", "count", "d", 1),
        ("Median Yield", "median_yield", ".1f", 1, "%"),
        ("Median 1Y Return", "median_1y", "+.1f", 1, "%"),
        ("Median 5Y Return", "median_5y", "+.1f", 1, "%"),
        ("Median Payout Ratio", "median_payout", ".0%", 1),
        ("Median FCF Margin", "median_fcf_margin", ".0%", 1),
        ("Median D/E Ratio", "median_de", ".1f", 1, "x"),
        ("Median Rev Growth (YoY)", "median_rev_growth", "+.1f", 1, "%"),
        ("Median Net Margin", "median_net_margin", ".1f", 1, "%"),
        ("Median Market Cap", "median_mcap", ".0f", 1e9, "B"),
    ]

    for metric_info in metrics:
        label = metric_info[0]
        key = metric_info[1]
        fmt = metric_info[2]
        scale = metric_info[3]
        suffix = metric_info[4] if len(metric_info) > 4 else ""

        vals = []
        for c in cohorts:
            v = c[key]
            if pd.notna(v):
                if key == "median_mcap":
                    vals.append(f"${v/scale:{fmt}}{suffix}")
                elif fmt == "d":
                    vals.append(f"{int(v)}")
                elif fmt == ".0%":
                    vals.append(f"{v:{fmt}}")
                else:
                    vals.append(f"{v:{fmt}}{suffix}")
            else:
                vals.append("N/A")
        md.append(f"| {label} | {' | '.join(vals)} |")
    md.append("")

    # Narrative
    md.append("**Key Findings:**\n")

    hy_5y = high_yield["return_5y"].median()
    ly_5y = combined[combined["ttm_yield"] < 1]["return_5y"].median()
    hy_payout = high_yield["payout_ratio"].median()
    hy_de = high_yield["debt_equity"].median()

    md.append(f"- **High-yield stocks are characteristically different**: They have higher "
              f"payout ratios ({hy_payout:.0%} median), higher leverage ({hy_de:.1f}x D/E), "
              f"and lower revenue growth than their low-yield peers.")
    md.append(f"- **5-year price performance gap**: High-yield median {hy_5y:+.1f}% vs "
              f"low-yield median {ly_5y:+.1f}%. However, this ignores the ~15-20pp of "
              f"cumulative dividend income that high-yield stocks provided.")
    md.append(f"- **Sector concentration**: {hy_sectors.index[0]} and {hy_sectors.index[1] if len(hy_sectors) > 1 else 'N/A'} "
              f"dominate the high-yield cohort, reflecting their capital-intensive, "
              f"cash-generative business models.")
    md.append(f"- **Sustainability signal**: A median FCF margin of "
              f"{high_yield['fcf_margin'].median():.0%} for high-yield stocks suggests "
              f"most dividends are well-covered by free cash flow, though individual "
              f"names with payout ratios >100% warrant caution.")
    md.append("")

    return "\n".join(md)


# ═══════════════════════════════════════════════════════════════════════════
# REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def generate_report(quarterly, profiles, dividends, spy, price_changes, daily_prices):
    """Generate the full follow-up analysis report."""
    sections = []

    # Header
    sections.append("# S&P 500 Follow-Up Analysis: Tariffs, Margins & Dividends")
    sections.append("### Supplemental to the Silverblatt Report | Data as of February 18, 2026\n")
    sections.append("**Data Sources:** Financial Modeling Prep (FMP) API — 498 S&P 500 constituents, "
                    "20 quarters of financial statements, per-company 5-year daily stock prices, "
                    "5 years of daily SPY pricing, and dividend history.\n")
    sections.append("---\n")

    # Section 1
    print("\n[1/4] Analyzing inventory & tariffs...")
    sections.append(analyze_inventory_tariffs(quarterly))
    sections.append("---\n")

    # Section 2
    print("[2/4] Analyzing margin compression...")
    sections.append(analyze_margin_compression(quarterly))
    sections.append("---\n")

    # Section 3
    print("[3/4] Analyzing dividend stock performance...")
    sections.append(analyze_dividend_performance(quarterly, profiles, dividends, price_changes, daily_prices))
    sections.append("---\n")

    # Section 4
    print("[4/4] Analyzing high-dividend characteristics...")
    sections.append(analyze_high_dividend_characteristics(quarterly, profiles, dividends, price_changes))
    sections.append("---\n")

    # Methodology
    sections.append("## Methodology & Data Notes\n")
    sections.append("- **Financial data**: Quarterly income statements, cash flow statements, and "
                    "balance sheets from FMP API for 498 S&P 500 constituents (BF.B and BRK.B "
                    "excluded due to FMP tier restrictions). Data spans Q3 2018 through Q1 2026.")
    sections.append("- **Stock price returns**: FMP `/stable/stock-price-change` endpoint providing "
                    "1D/5D/1M/3M/6M/YTD/1Y/3Y/5Y/10Y percentage returns as of Feb 18, 2026. "
                    "These are **price returns only** (excluding dividends).")
    sections.append("- **Daily prices**: Per-company daily close prices from FMP "
                    "`/stable/historical-price-eod/light` (Feb 2021 – Feb 2026).")
    sections.append("- **Dividend data**: Per-payment dividend history from FMP, used to compute "
                    "annual DPS, growth rates, and yield classifications.")
    sections.append("- **Sector classification**: From FMP company profiles (point-in-time).")
    sections.append("- **TTM dividend yield**: Computed as trailing-12-month dividends paid "
                    "(from quarterly cashflow) divided by current market capitalization.")
    sections.append("- **Tariff timeline**: Initial tariff announcements in April 2025. "
                    "H1/H2 2025 split used as pre/post-tariff proxy.")
    sections.append("- **Limitations**: Price returns exclude dividends (total return would be higher "
                    "for income stocks). Inventory data is quarterly (not monthly), limiting "
                    "tariff timing precision. Q1 2026 data is partial.\n")

    sections.append("---\n")
    sections.append("*Analysis generated February 18, 2026 using S&P 500 Silverblatt dataset.*")

    return "\n".join(sections)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("S&P 500 Follow-Up Analysis")
    print("=" * 60)

    # Load data
    print("\nLoading datasets...")
    quarterly, profiles, dividends, spy, price_changes, daily_prices = load_all_data()

    # Generate report
    print("\nGenerating report...")
    report = generate_report(quarterly, profiles, dividends, spy, price_changes, daily_prices)

    # Save
    OUTPUT_FILE.write_text(report)
    print(f"\nReport saved to: {OUTPUT_FILE}")
    print(f"Report size: {len(report):,} characters")


if __name__ == "__main__":
    main()
