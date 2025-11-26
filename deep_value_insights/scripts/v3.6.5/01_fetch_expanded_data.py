#!/usr/bin/env python3
"""
v3.6.5 Step 1: Fetch Expanded Historical Data for AXP and COST
===============================================================

Fetches extended quarterly financial data from FMP API:
- American Express (AXP): 1995-2025 (~120 quarters)
- Costco (COST): 2000-2020 (~80 quarters)

These are iconic Berkshire holdings that will add HOLD samples to balance the dataset.

Author: Claude Code
Date: 2025-11-24
Version: v3.6.5
"""

import sys
from pathlib import Path
import pandas as pd
from datetime import datetime

# Add project root to path
project_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_dir))

from scripts.fmp_api.fmp_client import FMPClient

# Setup paths
script_dir = Path(__file__).parent
data_dir = project_dir / 'data' / 'v3.6.5_expanded_hold' / 'raw'


def fetch_expanded_data(ticker: str, start_year: int, end_year: int):
    """
    Fetch quarterly financial data for a ticker within a date range.

    Args:
        ticker: Stock ticker symbol
        start_year: Start year (inclusive)
        end_year: End year (inclusive)

    Returns:
        DataFrame with merged financial statements
    """
    print(f"\n{'='*60}")
    print(f"Fetching {ticker} data ({start_year}-{end_year})")
    print(f"{'='*60}")

    client = FMPClient()

    # Fetch all statements (up to 200 quarters = 50 years)
    df = client.fetch_and_merge(ticker, period='quarter', limit=200)

    if df.empty:
        print(f"  ERROR: No data returned for {ticker}")
        return pd.DataFrame()

    # Filter to date range
    df['date'] = pd.to_datetime(df['date'])
    start_date = pd.Timestamp(f'{start_year}-01-01')
    end_date = pd.Timestamp(f'{end_year}-12-31')

    df_filtered = df[(df['date'] >= start_date) & (df['date'] <= end_date)].copy()

    print(f"  Total quarters from API: {len(df)}")
    print(f"  Date range in API: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')}")
    print(f"  Filtered to {start_year}-{end_year}: {len(df_filtered)} quarters")
    print(f"  Filtered date range: {df_filtered['date'].min().strftime('%Y-%m-%d')} to {df_filtered['date'].max().strftime('%Y-%m-%d')}")

    return df_filtered


def main():
    """Fetch expanded data for AXP and COST."""
    print("="*60)
    print("v3.6.5: FETCH EXPANDED HISTORICAL DATA")
    print("="*60)
    print(f"\nOutput directory: {data_dir}")

    # Ensure output directory exists
    data_dir.mkdir(parents=True, exist_ok=True)

    # Fetch AXP (American Express): 1995-2025
    # Buffett bought AXP in 1991, so 1995 gives us full context
    axp_df = fetch_expanded_data('AXP', 1995, 2025)

    if not axp_df.empty:
        output_file = data_dir / 'AXP_all_statements_quarterly.csv'
        axp_df.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Fetch COST (Costco): 2000-2020
    # Munger/Berkshire bought in 1999, HOLD through 2020
    cost_df = fetch_expanded_data('COST', 2000, 2020)

    if not cost_df.empty:
        output_file = data_dir / 'COST_all_statements_quarterly.csv'
        cost_df.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Summary
    print("\n" + "="*60)
    print("FETCH SUMMARY")
    print("="*60)
    print(f"\n| Ticker | Quarters | Date Range | Output |")
    print(f"|--------|----------|------------|--------|")

    if not axp_df.empty:
        print(f"| AXP | {len(axp_df)} | {axp_df['date'].min().strftime('%Y-%m')} to {axp_df['date'].max().strftime('%Y-%m')} | {data_dir / 'AXP_all_statements_quarterly.csv'} |")

    if not cost_df.empty:
        print(f"| COST | {len(cost_df)} | {cost_df['date'].min().strftime('%Y-%m')} to {cost_df['date'].max().strftime('%Y-%m')} | {data_dir / 'COST_all_statements_quarterly.csv'} |")

    print(f"\n  Data saved to: {data_dir}")
    print("="*60)
    print("FETCH COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
