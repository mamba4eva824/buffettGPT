#!/usr/bin/env python3
"""
v3.6.5 Step 2: Create HOLD Labels for AXP and COST
===================================================

Creates HOLD labels (label=1) for the expanded AXP and COST data:
- AXP: 1995-2025 (Buffett's continuous holding since 1991)
- COST: 2000-2020 (Munger/Berkshire holding period)

These are quintessential long-term HOLD examples that will help balance the dataset.

Author: Claude Code
Date: 2025-11-24
Version: v3.6.5
"""

import pandas as pd
from pathlib import Path


# Setup paths
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
data_dir = project_dir / 'data' / 'v3.6.5_expanded_hold'
raw_dir = data_dir / 'raw'
labels_dir = data_dir / 'labels'


def create_hold_labels(ticker: str, raw_file: Path, company_name: str):
    """
    Create HOLD labels for all quarters in the raw data file.

    Args:
        ticker: Stock ticker symbol
        raw_file: Path to raw FMP data CSV
        company_name: Full company name

    Returns:
        DataFrame with labels
    """
    print(f"\n{'='*60}")
    print(f"Creating HOLD labels for {ticker} ({company_name})")
    print(f"{'='*60}")

    if not raw_file.exists():
        print(f"  ERROR: Raw data file not found: {raw_file}")
        return pd.DataFrame()

    # Load raw data
    df_raw = pd.read_csv(raw_file)
    df_raw['date'] = pd.to_datetime(df_raw['date'])

    print(f"  Loaded {len(df_raw)} quarters from {raw_file.name}")
    print(f"  Date range: {df_raw['date'].min().strftime('%Y-%m-%d')} to {df_raw['date'].max().strftime('%Y-%m-%d')}")

    # Create labels DataFrame
    df_labels = pd.DataFrame({
        'symbol': ticker,
        'company': company_name,
        'date': df_raw['date'],
        'year': df_raw['date'].dt.year,
        'label': 1,  # HOLD
        'label_name': 'HOLD',
        'label_source': 'v3.6.5_expanded_hold'
    })

    # Sort by date (oldest first for training)
    df_labels = df_labels.sort_values('date').reset_index(drop=True)

    print(f"  Created {len(df_labels)} HOLD labels")
    print(f"  Label distribution: HOLD={len(df_labels)} (100%)")

    return df_labels


def main():
    """Create HOLD labels for AXP and COST."""
    print("="*60)
    print("v3.6.5: CREATE HOLD LABELS")
    print("="*60)
    print(f"\nInput directory: {raw_dir}")
    print(f"Output directory: {labels_dir}")

    # Ensure output directory exists
    labels_dir.mkdir(parents=True, exist_ok=True)

    # Create AXP labels
    axp_labels = create_hold_labels(
        ticker='AXP',
        raw_file=raw_dir / 'AXP_all_statements_quarterly.csv',
        company_name='American Express Company'
    )

    if not axp_labels.empty:
        output_file = labels_dir / 'axp_hold_labels.csv'
        axp_labels.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Create COST labels
    cost_labels = create_hold_labels(
        ticker='COST',
        raw_file=raw_dir / 'COST_all_statements_quarterly.csv',
        company_name='Costco Wholesale Corporation'
    )

    if not cost_labels.empty:
        output_file = labels_dir / 'cost_hold_labels.csv'
        cost_labels.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Summary
    print("\n" + "="*60)
    print("LABEL CREATION SUMMARY")
    print("="*60)

    total_hold = 0
    print(f"\n| Ticker | Company | Quarters | Label | Date Range |")
    print(f"|--------|---------|----------|-------|------------|")

    if not axp_labels.empty:
        print(f"| AXP | American Express | {len(axp_labels)} | HOLD | {axp_labels['date'].min().strftime('%Y-%m')} to {axp_labels['date'].max().strftime('%Y-%m')} |")
        total_hold += len(axp_labels)

    if not cost_labels.empty:
        print(f"| COST | Costco | {len(cost_labels)} | HOLD | {cost_labels['date'].min().strftime('%Y-%m')} to {cost_labels['date'].max().strftime('%Y-%m')} |")
        total_hold += len(cost_labels)

    print(f"\n  Total new HOLD samples: {total_hold}")
    print(f"  Labels saved to: {labels_dir}")

    print("\n" + "="*60)
    print("LABEL CREATION COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
