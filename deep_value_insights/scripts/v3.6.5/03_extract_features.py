#!/usr/bin/env python3
"""
v3.6.5 Step 3: Extract Features for AXP and COST
=================================================

Extracts all v3.6.4 features (base + new Buffett-core) for the expanded
AXP and COST datasets, then merges with HOLD labels.

Features per agent:
- Debt: 56 features (36 base + 10 v3.6.4 new + 10 raw columns used)
- Cashflow: 40 features (18 base + 10 v3.6.4 new + 12 raw columns)
- Growth: 61 features (42 base + 12 v3.6.4 new + 7 raw columns)

Author: Claude Code
Date: 2025-11-24
Version: v3.6.5
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path

# Add project root and v3.5 directory to path
project_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(project_dir / 'scripts' / 'v3.5'))

from extract_v35_features import (
    safe_divide,
    extract_debt_features_v35,
    extract_cashflow_features_v35,
    extract_growth_features_v361
)

# Setup paths
script_dir = Path(__file__).parent
data_dir = project_dir / 'data' / 'v3.6.5_expanded_hold'
raw_dir = data_dir / 'raw'
labels_dir = data_dir / 'labels'
features_dir = data_dir / 'features'


def prepare_raw_data(raw_file: Path, ticker: str):
    """
    Prepare raw FMP data for feature extraction.

    Standardizes column names to match the feature extraction functions.
    """
    df = pd.read_csv(raw_file)
    df['date'] = pd.to_datetime(df['date'])

    # Add required metadata columns
    df['symbol'] = ticker
    df['calendarYear'] = df['date'].dt.year

    # Standardize column names (FMP uses camelCase, features use snake_case)
    column_map = {
        'totalDebt': 'totalDebt',
        'totalStockholdersEquity': 'totalStockholdersEquity',
        'totalAssets': 'totalAssets',
        'cashAndCashEquivalents': 'cashAndCashEquivalents',
        'interestExpense': 'interestExpense',
        'operatingIncome': 'operatingIncome',
        'ebitda': 'ebitda',
        'totalCurrentAssets': 'totalCurrentAssets',
        'totalCurrentLiabilities': 'totalCurrentLiabilities',
        'inventory': 'inventory',
        'operatingCashFlow': 'operatingCashFlow',
        'capitalExpenditure': 'capitalExpenditure',
        'freeCashFlow': 'freeCashFlow',
        'netIncome': 'netIncome',
        'revenue': 'revenue',
        'changeInWorkingCapital': 'changeInWorkingCapital',
        'dividendsPaid': 'dividendsPaid',
        'commonStockRepurchased': 'commonStockRepurchased',
        'grossProfit': 'grossProfit',
        'costOfRevenue': 'costOfRevenue',
        'eps': 'eps',
        'depreciationAndAmortization': 'depreciationAndAmortization',
        'netReceivables': 'netReceivables',
        'accountPayables': 'accountPayables'
    }

    # Ensure all required columns exist (fill with 0 if missing)
    for fmp_col, std_col in column_map.items():
        if fmp_col not in df.columns:
            df[fmp_col] = 0

    # Handle common column name variations
    if 'dividendsPaid' not in df.columns or df['dividendsPaid'].isna().all():
        if 'dividendPaid' in df.columns:
            df['dividendsPaid'] = df['dividendPaid']
        else:
            df['dividendsPaid'] = 0

    # Sort by date (oldest first for temporal features)
    df = df.sort_values('date').reset_index(drop=True)

    return df


def add_v364_debt_features(df):
    """Add v3.6.4 new Debt features (10 features)."""
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    # ROA and ROIC
    df['roa'] = safe_divide(df['net_income'], df['total_assets']) * 100
    nopat = df['operating_income'] * (1 - 0.25)
    invested_capital = df['total_equity'] + df['total_debt']
    df['roic'] = safe_divide(nopat, invested_capital) * 100

    # Temporal ROA/ROIC
    df['roa_yoy'] = df.groupby('symbol')['roa'].pct_change(periods=4) * 100
    df['roa_trend_2yr'] = df.groupby('symbol')['roa'].diff(periods=8)
    df['roic_yoy'] = df.groupby('symbol')['roic'].pct_change(periods=4) * 100

    # DuPont components
    df['asset_turnover'] = safe_divide(df['revenue'], df['total_assets'])
    df['asset_turnover_yoy'] = df.groupby('symbol')['asset_turnover'].pct_change(periods=4) * 100
    df['equity_multiplier'] = safe_divide(df['total_assets'], df['total_equity'])

    # Debt coverage
    df['fcf_to_debt'] = safe_divide(df['free_cash_flow'], df['total_debt'])
    df['ebitda_to_interest'] = safe_divide(df['ebitda'], df['interest_expense'])

    return df


def add_v364_cashflow_features(df):
    """Add v3.6.4 new Cashflow features (10 features)."""
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    # Cash efficiency
    df['ocf_to_revenue'] = safe_divide(df['operating_cash_flow'], df['revenue']) * 100
    df['ocf_to_revenue_yoy'] = df.groupby('symbol')['ocf_to_revenue'].pct_change(periods=4) * 100
    df['fcf_to_revenue'] = safe_divide(df['free_cash_flow'], df['revenue']) * 100

    # Capital intensity
    df['capex_intensity'] = safe_divide(df['capital_expenditures'].abs(), df['revenue']) * 100
    df['capex_intensity_trend'] = df.groupby('symbol')['capex_intensity'].diff(periods=4)

    # Working capital detail (some may be 0 if data not available)
    df['dio'] = safe_divide(df.get('inventory', 0), df.get('cost_of_revenue', df['revenue'])) * 365
    df['working_capital_to_revenue'] = safe_divide(
        df['current_assets'] - df['current_liabilities'],
        df['revenue']
    )

    return df


def add_v364_growth_features(df):
    """Add v3.6.4 new Growth features (12 features)."""
    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    # Long-term margin trends (need to calculate margins first)
    if 'gross_margin' not in df.columns:
        df['gross_margin'] = safe_divide(df['gross_profit'], df['revenue']) * 100
    if 'operating_margin' not in df.columns:
        df['operating_margin'] = safe_divide(df['operating_income'], df['revenue']) * 100
    if 'net_margin' not in df.columns:
        df['net_margin'] = safe_divide(df['net_income'], df['revenue']) * 100

    df['gross_margin_trend_2yr'] = df.groupby('symbol')['gross_margin'].diff(periods=8)
    df['operating_margin_trend_2yr'] = df.groupby('symbol')['operating_margin'].diff(periods=8)
    df['net_margin_trend_2yr'] = df.groupby('symbol')['net_margin'].diff(periods=8)

    # Earnings quality
    df['roe_decomposed'] = (
        safe_divide(df['net_income'], df['revenue']) *
        safe_divide(df['revenue'], df['total_assets']) *
        safe_divide(df['total_assets'], df['total_equity'])
    )

    rolling_std = df.groupby('symbol')['net_income'].rolling(8, min_periods=4).std()
    rolling_mean = df.groupby('symbol')['net_income'].rolling(8, min_periods=4).mean().abs()
    df['earnings_stability'] = (rolling_std / rolling_mean).reset_index(level=0, drop=True)

    # Operating leverage
    ebit_pct = df.groupby('symbol')['operating_income'].pct_change(periods=4)
    rev_pct = df.groupby('symbol')['revenue'].pct_change(periods=4)
    df['operating_leverage'] = safe_divide(ebit_pct, rev_pct)

    return df


def extract_features_for_company(ticker: str, raw_file: Path, labels_file: Path):
    """
    Extract all features for a single company and merge with labels.

    Returns:
        Tuple of (debt_features_df, cashflow_features_df, growth_features_df)
    """
    print(f"\n{'='*60}")
    print(f"Extracting features for {ticker}")
    print(f"{'='*60}")

    # Load and prepare raw data
    df_raw = prepare_raw_data(raw_file, ticker)
    print(f"  Loaded {len(df_raw)} quarters from {raw_file.name}")

    # Load labels
    df_labels = pd.read_csv(labels_file)
    df_labels['date'] = pd.to_datetime(df_labels['date'])
    print(f"  Loaded {len(df_labels)} labels from {labels_file.name}")

    # Extract base v3.5 features
    print(f"  Extracting base v3.5 features...")
    debt_features = extract_debt_features_v35(df_raw)
    cashflow_features = extract_cashflow_features_v35(df_raw)
    growth_features = extract_growth_features_v361(df_raw)

    # Add metadata columns to features
    for features_df in [debt_features, cashflow_features, growth_features]:
        features_df['symbol'] = df_raw['symbol'].values
        features_df['date'] = df_raw['date'].values

    # Add v3.6.4 new features
    print(f"  Adding v3.6.4 new features...")

    # For debt features, we need raw columns
    debt_features['net_income'] = df_raw['netIncome'].values
    debt_features['total_assets'] = df_raw['totalAssets'].values
    debt_features['total_equity'] = df_raw['totalStockholdersEquity'].values
    debt_features['total_debt'] = df_raw['totalDebt'].values
    debt_features['operating_income'] = df_raw['operatingIncome'].values
    debt_features['revenue'] = df_raw['revenue'].values
    debt_features['free_cash_flow'] = df_raw['freeCashFlow'].values
    debt_features['ebitda'] = df_raw['ebitda'].values if 'ebitda' in df_raw.columns else df_raw['operatingIncome'] + df_raw.get('depreciationAndAmortization', 0)
    debt_features['interest_expense'] = df_raw['interestExpense'].values

    debt_features = add_v364_debt_features(debt_features)

    # For cashflow features
    cashflow_features['cost_of_revenue'] = df_raw['costOfRevenue'].values
    cashflow_features['inventory'] = df_raw['inventory'].values
    cashflow_features['current_assets'] = df_raw['totalCurrentAssets'].values
    cashflow_features['current_liabilities'] = df_raw['totalCurrentLiabilities'].values

    cashflow_features = add_v364_cashflow_features(cashflow_features)

    # For growth features
    growth_features['gross_profit'] = df_raw['grossProfit'].values
    growth_features['operating_income'] = df_raw['operatingIncome'].values
    growth_features['net_income'] = df_raw['netIncome'].values
    growth_features['total_assets'] = df_raw['totalAssets'].values
    growth_features['total_equity'] = df_raw['totalStockholdersEquity'].values

    growth_features = add_v364_growth_features(growth_features)

    # Merge with labels
    print(f"  Merging with labels...")

    def merge_with_labels(features_df, labels_df):
        """Merge features with labels on date."""
        merged = features_df.merge(
            labels_df[['symbol', 'date', 'company', 'year', 'label', 'label_name']],
            on=['symbol', 'date'],
            how='inner'
        )
        return merged

    debt_merged = merge_with_labels(debt_features, df_labels)
    cashflow_merged = merge_with_labels(cashflow_features, df_labels)
    growth_merged = merge_with_labels(growth_features, df_labels)

    print(f"  Debt features: {len(debt_merged)} samples, {len([c for c in debt_merged.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} features")
    print(f"  Cashflow features: {len(cashflow_merged)} samples, {len([c for c in cashflow_merged.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} features")
    print(f"  Growth features: {len(growth_merged)} samples, {len([c for c in growth_merged.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} features")

    return debt_merged, cashflow_merged, growth_merged


def main():
    """Extract features for AXP and COST."""
    print("="*60)
    print("v3.6.5: EXTRACT FEATURES FOR AXP AND COST")
    print("="*60)
    print(f"\nInput raw data: {raw_dir}")
    print(f"Input labels: {labels_dir}")
    print(f"Output features: {features_dir}")

    # Ensure output directory exists
    features_dir.mkdir(parents=True, exist_ok=True)

    all_debt = []
    all_cashflow = []
    all_growth = []

    # Process AXP
    axp_raw = raw_dir / 'AXP_all_statements_quarterly.csv'
    axp_labels = labels_dir / 'axp_hold_labels.csv'

    if axp_raw.exists() and axp_labels.exists():
        debt, cashflow, growth = extract_features_for_company('AXP', axp_raw, axp_labels)
        all_debt.append(debt)
        all_cashflow.append(cashflow)
        all_growth.append(growth)

        # Save individual company features
        debt.to_csv(features_dir / 'axp_debt_features.csv', index=False)
        cashflow.to_csv(features_dir / 'axp_cashflow_features.csv', index=False)
        growth.to_csv(features_dir / 'axp_growth_features.csv', index=False)
        print(f"  Saved AXP features to {features_dir}")
    else:
        print(f"  WARNING: AXP raw or labels file not found")

    # Process COST
    cost_raw = raw_dir / 'COST_all_statements_quarterly.csv'
    cost_labels = labels_dir / 'cost_hold_labels.csv'

    if cost_raw.exists() and cost_labels.exists():
        debt, cashflow, growth = extract_features_for_company('COST', cost_raw, cost_labels)
        all_debt.append(debt)
        all_cashflow.append(cashflow)
        all_growth.append(growth)

        # Save individual company features
        debt.to_csv(features_dir / 'cost_debt_features.csv', index=False)
        cashflow.to_csv(features_dir / 'cost_cashflow_features.csv', index=False)
        growth.to_csv(features_dir / 'cost_growth_features.csv', index=False)
        print(f"  Saved COST features to {features_dir}")
    else:
        print(f"  WARNING: COST raw or labels file not found")

    # Summary
    print("\n" + "="*60)
    print("FEATURE EXTRACTION SUMMARY")
    print("="*60)

    if all_debt:
        total_debt = pd.concat(all_debt, ignore_index=True)
        total_cashflow = pd.concat(all_cashflow, ignore_index=True)
        total_growth = pd.concat(all_growth, ignore_index=True)

        print(f"\n| Agent | Total Samples | Features |")
        print(f"|-------|---------------|----------|")
        print(f"| Debt | {len(total_debt)} | {len([c for c in total_debt.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} |")
        print(f"| Cashflow | {len(total_cashflow)} | {len([c for c in total_cashflow.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} |")
        print(f"| Growth | {len(total_growth)} | {len([c for c in total_growth.columns if c not in ['symbol', 'date', 'company', 'year', 'label', 'label_name']])} |")

        print(f"\n  Features saved to: {features_dir}")

    print("\n" + "="*60)
    print("FEATURE EXTRACTION COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
