#!/usr/bin/env python3
"""
v3.6.5 Step 4: Merge Expanded AXP/COST with v3.6.4 Training Data
=================================================================

Creates v3.6.5 training datasets by:
1. Loading v3.6.4 training data as base
2. Removing existing AXP/COST rows (to avoid duplicates)
3. Appending new expanded AXP/COST data
4. Aligning columns and verifying consistency
5. Saving as v3.6.5 training sets

Author: Claude Code
Date: 2025-11-24
Version: v3.6.5
"""

import pandas as pd
import numpy as np
from pathlib import Path


# Setup paths
script_dir = Path(__file__).parent
project_dir = script_dir.parent.parent
v364_dir = project_dir / 'data' / 'v3.6.4_feature_engineering'
v365_dir = project_dir / 'data' / 'v3.6.5_expanded_hold'
features_dir = v365_dir / 'features'


def merge_agent_data(agent_name: str, v364_file: str, new_features_files: list):
    """
    Merge v3.6.4 data with new expanded company data.

    Args:
        agent_name: Name of agent (debt, cashflow, growth)
        v364_file: Filename of v3.6.4 training data
        new_features_files: List of new feature files to append

    Returns:
        Merged DataFrame
    """
    print(f"\n{'='*60}")
    print(f"Merging {agent_name.upper()} Agent Data")
    print(f"{'='*60}")

    # Load v3.6.4 base data
    v364_path = v364_dir / v364_file
    if not v364_path.exists():
        print(f"  ERROR: v3.6.4 file not found: {v364_path}")
        return pd.DataFrame()

    df_base = pd.read_csv(v364_path)
    df_base['date'] = pd.to_datetime(df_base['date'])

    print(f"  Loaded v3.6.4 base: {len(df_base)} samples, {df_base['symbol'].nunique()} companies")
    print(f"  Base columns: {len(df_base.columns)}")

    # Check existing AXP/COST in base
    axp_count = (df_base['symbol'] == 'AXP').sum()
    cost_count = (df_base['symbol'] == 'COST').sum()
    print(f"  Existing AXP samples: {axp_count}")
    print(f"  Existing COST samples: {cost_count}")

    # Remove existing AXP and COST rows
    df_filtered = df_base[~df_base['symbol'].isin(['AXP', 'COST'])].copy()
    print(f"  After removing AXP/COST: {len(df_filtered)} samples")

    # Load and append new features
    new_dfs = []
    for features_file in new_features_files:
        features_path = features_dir / features_file
        if features_path.exists():
            df_new = pd.read_csv(features_path)
            df_new['date'] = pd.to_datetime(df_new['date'])
            new_dfs.append(df_new)
            print(f"  Loaded {features_file}: {len(df_new)} samples")
        else:
            print(f"  WARNING: File not found: {features_path}")

    if not new_dfs:
        print(f"  ERROR: No new feature files loaded")
        return df_filtered

    # Concatenate new data
    df_new_combined = pd.concat(new_dfs, ignore_index=True)
    print(f"  Combined new data: {len(df_new_combined)} samples")

    # Align columns - use v3.6.4 columns as reference
    base_columns = set(df_filtered.columns)
    new_columns = set(df_new_combined.columns)

    # Columns in base but not in new (need to add with NaN)
    missing_in_new = base_columns - new_columns
    if missing_in_new:
        print(f"  Columns missing in new data: {len(missing_in_new)}")
        for col in missing_in_new:
            df_new_combined[col] = np.nan

    # Columns in new but not in base (need to add to base with NaN)
    missing_in_base = new_columns - base_columns
    if missing_in_base:
        print(f"  Columns missing in base data: {len(missing_in_base)}")
        for col in missing_in_base:
            df_filtered[col] = np.nan

    # Ensure same column order
    all_columns = list(df_filtered.columns)
    df_new_combined = df_new_combined[all_columns]

    # Concatenate
    df_merged = pd.concat([df_filtered, df_new_combined], ignore_index=True)

    # Sort by symbol and date
    df_merged = df_merged.sort_values(['symbol', 'date']).reset_index(drop=True)

    print(f"\n  MERGED RESULT:")
    print(f"    Total samples: {len(df_merged)}")
    print(f"    Total companies: {df_merged['symbol'].nunique()}")
    print(f"    Total columns: {len(df_merged.columns)}")

    # Label distribution
    print(f"\n  Label Distribution:")
    for label in [0, 1, 2]:
        label_name = {0: 'SELL', 1: 'HOLD', 2: 'BUY'}.get(label)
        count = (df_merged['label'] == label).sum()
        pct = count / len(df_merged) * 100
        print(f"    {label_name}: {count:4d} ({pct:5.1f}%)")

    # New AXP/COST counts
    new_axp = (df_merged['symbol'] == 'AXP').sum()
    new_cost = (df_merged['symbol'] == 'COST').sum()
    print(f"\n  New AXP samples: {new_axp} (was {axp_count})")
    print(f"  New COST samples: {new_cost} (was {cost_count})")

    return df_merged


def main():
    """Create v3.6.5 training datasets."""
    print("="*60)
    print("v3.6.5: MERGE EXPANDED DATA WITH v3.6.4")
    print("="*60)
    print(f"\nBase data (v3.6.4): {v364_dir}")
    print(f"New features: {features_dir}")
    print(f"Output: {v365_dir}")

    # Merge Debt Agent
    debt_merged = merge_agent_data(
        'debt',
        'agent1_debt_v364.csv',
        ['axp_debt_features.csv', 'cost_debt_features.csv']
    )

    if not debt_merged.empty:
        output_file = v365_dir / 'agent1_debt_v365.csv'
        debt_merged.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Merge Cashflow Agent
    cashflow_merged = merge_agent_data(
        'cashflow',
        'agent2_cashflow_v364.csv',
        ['axp_cashflow_features.csv', 'cost_cashflow_features.csv']
    )

    if not cashflow_merged.empty:
        output_file = v365_dir / 'agent2_cashflow_v365.csv'
        cashflow_merged.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Merge Growth Agent
    growth_merged = merge_agent_data(
        'growth',
        'agent5_growth_v364.csv',
        ['axp_growth_features.csv', 'cost_growth_features.csv']
    )

    if not growth_merged.empty:
        output_file = v365_dir / 'agent5_growth_v365.csv'
        growth_merged.to_csv(output_file, index=False)
        print(f"  Saved: {output_file}")

    # Summary comparison
    print("\n" + "="*60)
    print("MERGE SUMMARY: v3.6.4 vs v3.6.5")
    print("="*60)

    # Load v3.6.4 for comparison
    v364_debt = pd.read_csv(v364_dir / 'agent1_debt_v364.csv')

    print(f"\n| Metric | v3.6.4 | v3.6.5 | Change |")
    print(f"|--------|--------|--------|--------|")

    if not debt_merged.empty:
        print(f"| Samples | {len(v364_debt)} | {len(debt_merged)} | +{len(debt_merged) - len(v364_debt)} |")
        print(f"| Companies | {v364_debt['symbol'].nunique()} | {debt_merged['symbol'].nunique()} | {debt_merged['symbol'].nunique() - v364_debt['symbol'].nunique():+d} |")

        # Label distribution change
        v364_hold = (v364_debt['label'] == 1).sum()
        v365_hold = (debt_merged['label'] == 1).sum()
        print(f"| HOLD samples | {v364_hold} | {v365_hold} | +{v365_hold - v364_hold} |")

        v364_hold_pct = v364_hold / len(v364_debt) * 100
        v365_hold_pct = v365_hold / len(debt_merged) * 100
        print(f"| HOLD % | {v364_hold_pct:.1f}% | {v365_hold_pct:.1f}% | +{v365_hold_pct - v364_hold_pct:.1f}% |")

    print(f"\n  Training data saved to: {v365_dir}")

    print("\n" + "="*60)
    print("MERGE COMPLETE")
    print("="*60)


if __name__ == '__main__':
    main()
