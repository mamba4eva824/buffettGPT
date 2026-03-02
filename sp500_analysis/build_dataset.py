#!/usr/bin/env python3
"""
Build S&P 500 Silverblatt-style analysis dataset from raw FMP API JSON files.

Produces 6 Parquet files in sp500_analysis/data/:
  - sp500_quarterly.parquet      (~10,000 rows × ~80 cols)
  - sp500_profiles.parquet       (~498 rows)
  - sp500_dividends.parquet      (~30,000 rows)
  - sp500_spy_daily.parquet      (~1,255 rows)
  - sp500_price_changes.parquet  (~496 rows — period returns per company)
  - sp500_daily_prices.parquet   (~600,000 rows — daily prices per company)
"""

import json
import os
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
FINANCIALS_DIR = DATA_DIR / "company_financials"
PROFILES_DIR = DATA_DIR / "company_profiles"
DIVIDENDS_DIR = DATA_DIR / "company_dividends"
PRICES_DIR = DATA_DIR / "company_prices"
SPY_FILE = DATA_DIR / "spy_historical_prices.json"
PRICE_CHANGES_FILE = DATA_DIR / "stock_price_changes.json"

# Metadata columns duplicated across income/cashflow/balance that should be
# dropped from cashflow and balance before merging (income's version is kept).
METADATA_COLS = ["cik", "filingDate", "acceptedDate", "reportedCurrency"]

# Non-metadata columns that appear in both income and cashflow.
# Keep income's version as primary; suffix cashflow's with _cf.
INCOME_CASHFLOW_DUPES = ["netIncome", "depreciationAndAmortization"]

# Non-metadata columns that appear in both cashflow and balance.
CASHFLOW_BALANCE_DUPES = ["accountsReceivables", "inventory"]

PROFILE_KEEP_COLS = [
    "symbol", "companyName", "sector", "industry", "marketCap", "beta",
    "price", "lastDividend", "fullTimeEmployees", "country", "exchange",
    "ipoDate",
]


def _date_to_calendar_quarter(date_str: str) -> str:
    """Convert a date string like '2025-03-29' to 'YYYY-QN' based on calendar date."""
    ts = pd.Timestamp(date_str)
    return f"{ts.year}-Q{ts.quarter}"


# ── Step 1: Load & flatten company financials ────────────────────────────────

def load_financials() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all company_financials JSONs, return (income_df, cashflow_df, balance_df)."""
    income_rows, cashflow_rows, balance_rows = [], [], []

    for fp in sorted(FINANCIALS_DIR.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)

        symbol = data.get("symbol", fp.stem)

        for rec in data.get("income", []):
            rec["symbol"] = symbol
            income_rows.append(rec)

        for rec in data.get("cashflow", []):
            rec["symbol"] = symbol
            cashflow_rows.append(rec)

        for rec in data.get("balance", []):
            rec["symbol"] = symbol
            balance_rows.append(rec)

    income_df = pd.DataFrame(income_rows)
    cashflow_df = pd.DataFrame(cashflow_rows)
    balance_df = pd.DataFrame(balance_rows)

    print(f"  Loaded financials: income={len(income_df)}, cashflow={len(cashflow_df)}, balance={len(balance_df)}")
    return income_df, cashflow_df, balance_df


# ── Step 2: Standardize calendar quarters ────────────────────────────────────

def add_calendar_quarter(df: pd.DataFrame) -> pd.DataFrame:
    """Add calendar_quarter column derived from the date field."""
    df = df.copy()
    df["calendar_quarter"] = df["date"].apply(_date_to_calendar_quarter)
    return df


# ── Step 3: Merge the 3 statements ──────────────────────────────────────────

def merge_statements(
    income_df: pd.DataFrame,
    cashflow_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> pd.DataFrame:
    """Merge income, cashflow, balance on (symbol, calendar_quarter) via outer join."""

    merge_keys = ["symbol", "calendar_quarter"]

    # Drop duplicate metadata cols from cashflow and balance
    cf_drop = [c for c in METADATA_COLS if c in cashflow_df.columns]
    bal_drop = [c for c in METADATA_COLS if c in balance_df.columns]

    # Also drop 'date', 'period', 'fiscalYear' from cashflow/balance to avoid suffixes
    # on columns we don't need duplicated. Keep income's versions.
    extra_drop = ["date", "period", "fiscalYear"]
    cf_drop += [c for c in extra_drop if c in cashflow_df.columns]
    bal_drop += [c for c in extra_drop if c in balance_df.columns]

    cashflow_clean = cashflow_df.drop(columns=cf_drop, errors="ignore")
    balance_clean = balance_df.drop(columns=bal_drop, errors="ignore")

    # Rename income-cashflow duplicate data columns in cashflow with _cf suffix
    cf_renames = {col: f"{col}_cf" for col in INCOME_CASHFLOW_DUPES if col in cashflow_clean.columns}
    cashflow_clean = cashflow_clean.rename(columns=cf_renames)

    # Rename cashflow-balance duplicate data columns in balance with _bal suffix
    bal_renames = {col: f"{col}_bal" for col in CASHFLOW_BALANCE_DUPES if col in balance_clean.columns}
    balance_clean = balance_clean.rename(columns=bal_renames)

    # Merge income + cashflow
    merged = income_df.merge(cashflow_clean, on=merge_keys, how="outer", suffixes=("", "_cf_dup"))

    # Merge with balance
    merged = merged.merge(balance_clean, on=merge_keys, how="outer", suffixes=("", "_bal_dup"))

    print(f"  Merged quarterly: {len(merged)} rows × {len(merged.columns)} cols")
    return merged


# ── Step 4: Add Silverblatt derived columns ──────────────────────────────────

def add_derived_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add derived columns for Silverblatt analysis areas."""
    df = df.copy()

    # net_buyback: abs(commonStockRepurchased) - stockBasedCompensation
    # commonStockRepurchased is negative (outflow), so abs() makes it positive
    df["net_buyback"] = (
        df["commonStockRepurchased"].abs() - df["stockBasedCompensation"]
    )

    # share_count_change_pct: QoQ % change in weightedAverageShsOutDil per company
    df = df.sort_values(["symbol", "date"])
    df["share_count_change_pct"] = (
        df.groupby("symbol")["weightedAverageShsOutDil"]
        .pct_change() * 100
    )

    # operating_gap: operatingIncome - netIncome
    df["operating_gap"] = df["operatingIncome"] - df["netIncome"]

    # operating_gap_pct: operating_gap / abs(operatingIncome), guarding div-by-zero
    df["operating_gap_pct"] = df["operating_gap"] / df["operatingIncome"].abs().replace(0, pd.NA)

    # payout_ratio: abs(commonDividendsPaid) / netIncome, guarding div-by-zero
    df["payout_ratio"] = df["commonDividendsPaid"].abs() / df["netIncome"].replace(0, pd.NA)

    # fcf_margin: freeCashFlow / revenue, guarding div-by-zero
    df["fcf_margin"] = df["freeCashFlow"] / df["revenue"].replace(0, pd.NA)

    print(f"  Added 6 derived columns")
    return df


# ── Step 5: Load & flatten profiles ──────────────────────────────────────────

def load_profiles() -> pd.DataFrame:
    """Load all company_profiles JSONs into a single DataFrame."""
    rows = []
    for fp in sorted(PROFILES_DIR.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)
        if isinstance(data, list) and len(data) > 0:
            profile = data[0]
            profile["symbol"] = fp.stem  # ensure symbol matches filename
            rows.append(profile)

    df = pd.DataFrame(rows)
    keep = [c for c in PROFILE_KEEP_COLS if c in df.columns]
    df = df[keep]
    print(f"  Loaded profiles: {len(df)} companies")
    return df


# ── Step 6: Load & flatten dividends ─────────────────────────────────────────

def load_dividends() -> pd.DataFrame:
    """Load all company_dividends JSONs into a long-format DataFrame."""
    rows = []
    for fp in sorted(DIVIDENDS_DIR.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)
        if isinstance(data, list):
            for rec in data:
                rec["symbol"] = fp.stem
                rows.append(rec)

    df = pd.DataFrame(rows)
    keep_cols = [
        "symbol", "date", "dividend", "adjDividend", "declarationDate",
        "paymentDate", "recordDate", "frequency", "yield",
    ]
    keep = [c for c in keep_cols if c in df.columns]
    df = df[keep]
    print(f"  Loaded dividends: {len(df)} records")
    return df


# ── Step 7: Load & process SPY prices ────────────────────────────────────────

def load_spy_prices() -> pd.DataFrame:
    """Load SPY daily prices, add quarter and return columns."""
    with open(SPY_FILE) as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # Add quarter column
    df["quarter"] = df["date"].dt.year.astype(str) + "-Q" + df["date"].dt.quarter.astype(str)

    # Daily return (pct change of close)
    df["daily_return"] = df["close"].pct_change()

    # Quarterly returns: last close / first close - 1
    qtr_first = df.groupby("quarter")["close"].first()
    qtr_last = df.groupby("quarter")["close"].last()
    qtr_returns = (qtr_last / qtr_first - 1).rename("quarterly_return")
    df = df.merge(qtr_returns, on="quarter", how="left")

    print(f"  Loaded SPY prices: {len(df)} trading days, {df['quarter'].nunique()} quarters")
    return df


# ── Step 8: Load stock price changes ──────────────────────────────────────

def load_price_changes() -> pd.DataFrame:
    """Load the batch stock-price-change JSON into a DataFrame.
    One row per company with 1D/5D/1M/3M/6M/YTD/1Y/3Y/5Y/10Y percentage returns.
    """
    if not PRICE_CHANGES_FILE.exists():
        print("  WARNING: stock_price_changes.json not found — skipping")
        return pd.DataFrame()

    with open(PRICE_CHANGES_FILE) as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    # Rename columns for clarity
    rename_map = {
        "1D": "return_1d", "5D": "return_5d", "1M": "return_1m",
        "3M": "return_3m", "6M": "return_6m", "ytd": "return_ytd",
        "1Y": "return_1y", "3Y": "return_3y", "5Y": "return_5y",
        "10Y": "return_10y", "max": "return_max",
    }
    df = df.rename(columns=rename_map)
    print(f"  Loaded price changes: {len(df)} companies")
    return df


# ── Step 9: Load per-company daily prices ────────────────────────────────

def load_daily_prices() -> pd.DataFrame:
    """Load all company_prices JSONs into a single long-format DataFrame.
    Columns: symbol, date, price, volume, plus derived quarter and returns.
    """
    if not PRICES_DIR.exists():
        print("  WARNING: company_prices/ not found — skipping")
        return pd.DataFrame()

    rows = []
    for fp in sorted(PRICES_DIR.glob("*.json")):
        with open(fp) as f:
            data = json.load(f)
        if isinstance(data, list):
            for rec in data:
                rec["symbol"] = fp.stem
                rows.append(rec)

    if not rows:
        print("  WARNING: No daily price data found")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["symbol", "date"]).reset_index(drop=True)

    # Add quarter column
    df["quarter"] = df["date"].dt.year.astype(str) + "-Q" + df["date"].dt.quarter.astype(str)

    # Add year column
    df["year"] = df["date"].dt.year

    # Daily return per company
    df["daily_return"] = df.groupby("symbol")["price"].pct_change()

    print(f"  Loaded daily prices: {len(df):,} records, {df['symbol'].nunique()} companies")
    return df


# ── Step 10: Save & verify ───────────────────────────────────────────────────

def print_summary(quarterly: pd.DataFrame, profiles: pd.DataFrame,
                  dividends: pd.DataFrame, spy: pd.DataFrame,
                  price_changes: pd.DataFrame = None,
                  daily_prices: pd.DataFrame = None) -> None:
    """Print verification summary."""
    print("\n" + "=" * 70)
    print("DATASET SUMMARY")
    print("=" * 70)

    # Row counts
    print(f"\n{'File':<35} {'Rows':>8} {'Cols':>6}")
    print("-" * 51)
    print(f"{'sp500_quarterly.parquet':<35} {len(quarterly):>8,} {len(quarterly.columns):>6}")
    print(f"{'sp500_profiles.parquet':<35} {len(profiles):>8,} {len(profiles.columns):>6}")
    print(f"{'sp500_dividends.parquet':<35} {len(dividends):>8,} {len(dividends.columns):>6}")
    print(f"{'sp500_spy_daily.parquet':<35} {len(spy):>8,} {len(spy.columns):>6}")
    if price_changes is not None and len(price_changes) > 0:
        print(f"{'sp500_price_changes.parquet':<35} {len(price_changes):>8,} {len(price_changes.columns):>6}")
    if daily_prices is not None and len(daily_prices) > 0:
        print(f"{'sp500_daily_prices.parquet':<35} {len(daily_prices):>8,} {len(daily_prices.columns):>6}")

    # Date range
    if "date" in quarterly.columns:
        dates = pd.to_datetime(quarterly["date"])
        print(f"\nQuarterly date range: {dates.min().date()} to {dates.max().date()}")

    if "calendar_quarter" in quarterly.columns:
        quarters = sorted(quarterly["calendar_quarter"].dropna().unique())
        print(f"Calendar quarters: {quarters[0]} to {quarters[-1]} ({len(quarters)} quarters)")

    # Companies with >15 quarters
    if "symbol" in quarterly.columns and "calendar_quarter" in quarterly.columns:
        qtr_counts = quarterly.groupby("symbol")["calendar_quarter"].nunique()
        gt15 = (qtr_counts > 15).sum()
        print(f"\nCompanies with >15 quarters of data: {gt15} / {qtr_counts.shape[0]}")

    # Sector distribution
    if "sector" in profiles.columns:
        print(f"\nSector distribution:")
        sector_counts = profiles["sector"].value_counts()
        for sector, count in sector_counts.items():
            print(f"  {sector:<35} {count:>4}")

    # Spot-check: AAPL most recent quarter
    if "symbol" in quarterly.columns:
        aapl = quarterly[quarterly["symbol"] == "AAPL"].sort_values("date", ascending=False)
        if len(aapl) > 0:
            row = aapl.iloc[0]
            print(f"\n--- AAPL spot-check (most recent quarter: {row.get('calendar_quarter', 'N/A')}) ---")
            derived = [
                "net_buyback", "share_count_change_pct", "operating_gap",
                "operating_gap_pct", "payout_ratio", "fcf_margin",
            ]
            spot_cols = [
                "revenue", "netIncome", "operatingIncome", "freeCashFlow",
                "commonStockRepurchased", "stockBasedCompensation",
                "commonDividendsPaid", "weightedAverageShsOutDil",
            ] + derived
            for col in spot_cols:
                val = row.get(col)
                if pd.notna(val):
                    if isinstance(val, float) and abs(val) > 1_000_000:
                        print(f"  {col:<30} {val:>20,.0f}")
                    elif isinstance(val, float):
                        print(f"  {col:<30} {val:>20.4f}")
                    else:
                        print(f"  {col:<30} {val:>20}")

    print("\n" + "=" * 70)


def main():
    print("Building S&P 500 Silverblatt dataset...\n")

    # Step 1: Load financials
    print("[1/10] Loading company financials...")
    income_df, cashflow_df, balance_df = load_financials()

    # Step 2: Add calendar quarters
    print("[2/10] Standardizing calendar quarters...")
    income_df = add_calendar_quarter(income_df)
    cashflow_df = add_calendar_quarter(cashflow_df)
    balance_df = add_calendar_quarter(balance_df)

    # Step 3: Merge
    print("[3/10] Merging financial statements...")
    quarterly = merge_statements(income_df, cashflow_df, balance_df)

    # Step 4: Derived columns
    print("[4/10] Adding derived columns...")
    quarterly = add_derived_columns(quarterly)

    # Step 5: Profiles
    print("[5/10] Loading company profiles...")
    profiles = load_profiles()

    # Step 6: Dividends
    print("[6/10] Loading company dividends...")
    dividends = load_dividends()

    # Step 7: SPY prices
    print("[7/10] Loading SPY daily prices...")
    spy = load_spy_prices()

    # Step 8: Stock price changes
    print("[8/10] Loading stock price changes...")
    price_changes = load_price_changes()

    # Step 9: Daily prices
    print("[9/10] Loading per-company daily prices...")
    daily_prices = load_daily_prices()

    # Step 10: Save
    print("[10/10] Saving Parquet files...")
    quarterly.to_parquet(DATA_DIR / "sp500_quarterly.parquet", index=False)
    profiles.to_parquet(DATA_DIR / "sp500_profiles.parquet", index=False)
    dividends.to_parquet(DATA_DIR / "sp500_dividends.parquet", index=False)
    spy.to_parquet(DATA_DIR / "sp500_spy_daily.parquet", index=False)

    file_count = 4
    if len(price_changes) > 0:
        price_changes.to_parquet(DATA_DIR / "sp500_price_changes.parquet", index=False)
        file_count += 1
    if len(daily_prices) > 0:
        daily_prices.to_parquet(DATA_DIR / "sp500_daily_prices.parquet", index=False)
        file_count += 1
    print(f"  Saved {file_count} Parquet files to sp500_analysis/data/")

    # Summary
    print_summary(quarterly, profiles, dividends, spy, price_changes, daily_prices)


if __name__ == "__main__":
    main()
