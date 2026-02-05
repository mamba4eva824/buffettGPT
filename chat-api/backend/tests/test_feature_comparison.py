#!/usr/bin/env python3
"""
Feature Comparison Audit: Prediction Ensemble vs Investment Research

Compares the full ML feature sets and temporal derivatives between:
1. Prediction Ensemble Lambda (lambda/prediction_ensemble/utils/feature_extractor.py)
2. Investment Research (src/utils/feature_extractor.py)

Key differences detected:
- Lambda version has aggregate_annual_data() as standalone function
- Lambda compute_ml_features() accepts raw_financials for actual values
- src/utils version sets many metrics to 0 or approximations

Usage:
    python test_feature_comparison.py [TICKER] [FISCAL_YEAR]

Example:
    python test_feature_comparison.py JPM 2026
"""

import sys
import os
from decimal import Decimal
from typing import Dict, Any, List, Tuple

os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('ENVIRONMENT', 'dev')

import boto3

# === PATH SETUP ===
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ENSEMBLE_DIR = os.path.join(BACKEND_DIR, 'lambda', 'prediction_ensemble')
SRC_UTILS_DIR = os.path.join(BACKEND_DIR, 'src', 'utils')

# === MOCK LOGGER SETUP (before any imports) ===
class MockLogger:
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass
    def debug(self, msg): pass

# Create mock logger module for src.utils
mock_logger_module = type(sys)('mock_logger')
mock_logger_module.get_logger = lambda name: MockLogger()
sys.modules['src.utils.logger'] = mock_logger_module

# Import from both locations
sys.path.insert(0, ENSEMBLE_DIR)
sys.path.insert(0, BACKEND_DIR)
sys.path.insert(0, SRC_UTILS_DIR)

# Import Lambda version (prediction_ensemble)
from utils.feature_extractor import (
    extract_quarterly_trends as ensemble_extract_trends,
    compute_ml_features as ensemble_compute_ml,
    aggregate_annual_data as ensemble_aggregate,
    extract_all_features as ensemble_extract_all
)

# Import src/utils version - need to read and exec to avoid import collision
# Read the source file and modify it to avoid relative imports
src_fe_path = os.path.join(SRC_UTILS_DIR, 'feature_extractor.py')
with open(src_fe_path, 'r') as f:
    src_code = f.read()

# Replace relative import with mock
src_code = src_code.replace(
    'from .logger import get_logger',
    'get_logger = lambda name: type("MockLogger", (), {"info": lambda s, m: None, "warning": lambda s, m: None, "error": lambda s, m: None, "debug": lambda s, m: None})()'
)

# Execute in a new namespace
src_namespace = {'__name__': 'src_feature_extractor', '__file__': src_fe_path}
exec(src_code, src_namespace)

src_extract_trends = src_namespace['extract_quarterly_trends']
src_compute_ml = src_namespace['compute_ml_features']
src_extract_all = src_namespace['extract_all_features']


def decimal_to_float(obj):
    """Recursively convert Decimal to float."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    return obj


def fetch_data(ticker: str, fiscal_year: int) -> dict:
    """Fetch cached financial data from DynamoDB."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('buffett-dev-financial-data-cache')

    cache_key = f"v3:{ticker}:{fiscal_year}"
    response = table.get_item(Key={'cache_key': cache_key})

    if 'Item' not in response:
        raise ValueError(f"No cached data found for {ticker}")

    return decimal_to_float(response['Item'].get('raw_financials', {}))


def format_value(value, is_percentage: bool = False, is_currency: bool = False) -> str:
    """Format value for display."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        return value
    if is_currency and abs(value) >= 1e9:
        return f"${value/1e9:.2f}B"
    if is_currency and abs(value) >= 1e6:
        return f"${value/1e6:.1f}M"
    if is_percentage:
        return f"{value:.2f}%"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def compare_features(
    ensemble_features: Dict[str, Any],
    src_features: Dict[str, Any],
    category: str,
    currency_metrics: List[str] = None,
    percentage_metrics: List[str] = None
) -> Tuple[int, int, List[Dict]]:
    """
    Compare features between two dicts and report differences.

    Returns:
        Tuple of (matches, mismatches, differences_list)
    """
    currency_metrics = currency_metrics or []
    percentage_metrics = percentage_metrics or []

    matches = 0
    mismatches = 0
    differences = []

    # Get all keys from both
    all_keys = sorted(set(ensemble_features.keys()) | set(src_features.keys()))

    for key in all_keys:
        e_val = ensemble_features.get(key)
        s_val = src_features.get(key)

        is_currency = key in currency_metrics
        is_pct = key in percentage_metrics or '_margin' in key or '_yoy' in key or 'growth' in key

        # Determine if values match
        if e_val is None and s_val is None:
            matches += 1
            continue

        if e_val is None or s_val is None:
            mismatches += 1
            differences.append({
                'metric': key,
                'ensemble': format_value(e_val, is_pct, is_currency),
                'src_utils': format_value(s_val, is_pct, is_currency),
                'diff': 'MISSING',
                'category': category
            })
            continue

        # Compare numeric values
        if isinstance(e_val, (int, float)) and isinstance(s_val, (int, float)):
            # For currency, use relative tolerance
            if is_currency and abs(e_val) > 1000:
                tolerance = abs(e_val) * 0.001  # 0.1% tolerance
            else:
                tolerance = 0.01  # Absolute tolerance for small values

            if abs(e_val - s_val) <= tolerance:
                matches += 1
            else:
                mismatches += 1
                diff_val = e_val - s_val
                diff_pct = (diff_val / abs(s_val) * 100) if s_val != 0 else float('inf')
                differences.append({
                    'metric': key,
                    'ensemble': format_value(e_val, is_pct, is_currency),
                    'src_utils': format_value(s_val, is_pct, is_currency),
                    'diff': f"{diff_pct:+.1f}%" if abs(diff_pct) < 1000 else "LARGE",
                    'category': category
                })
        else:
            # String/bool comparison
            if e_val == s_val:
                matches += 1
            else:
                mismatches += 1
                differences.append({
                    'metric': key,
                    'ensemble': str(e_val),
                    'src_utils': str(s_val),
                    'diff': 'MISMATCH',
                    'category': category
                })

    return matches, mismatches, differences


def run_comparison(ticker: str, fiscal_year: int):
    """Run full feature comparison between both systems."""
    print(f"\n{'='*90}")
    print(f"FEATURE COMPARISON AUDIT: {ticker} (FY{fiscal_year})")
    print(f"{'='*90}")

    # Fetch data
    print("\n[1/5] Fetching data from DynamoDB...")
    raw_data = fetch_data(ticker, fiscal_year)

    income = raw_data.get('income_statement', [])
    balance = raw_data.get('balance_sheet', [])
    cashflow = raw_data.get('cash_flow', [])

    print(f"  - {len(income)} income statements")
    print(f"  - {len(balance)} balance sheets")
    print(f"  - {len(cashflow)} cash flow statements")

    # Extract quarterly trends (both should be identical)
    print("\n[2/5] Extracting quarterly trends...")
    ensemble_trends = ensemble_extract_trends(raw_data)
    src_trends = src_extract_trends(raw_data)

    # Compare quarterly trends
    print("\n" + "─"*90)
    print("QUARTERLY TRENDS COMPARISON")
    print("─"*90)

    trend_matches = 0
    trend_mismatches = 0

    for key in sorted(ensemble_trends.keys()):
        e_arr = ensemble_trends.get(key, [])
        s_arr = src_trends.get(key, [])

        if len(e_arr) != len(s_arr):
            print(f"  ✗ {key}: length mismatch ({len(e_arr)} vs {len(s_arr)})")
            trend_mismatches += 1
        else:
            # Compare first few values
            matches = all(
                abs(e - s) < 0.01 if isinstance(e, (int, float)) and isinstance(s, (int, float)) else e == s
                for e, s in zip(e_arr[:4], s_arr[:4])
            )
            if matches:
                trend_matches += 1
            else:
                print(f"  ✗ {key}: value mismatch")
                print(f"      Ensemble: {e_arr[:3]}")
                print(f"      src/utils: {s_arr[:3]}")
                trend_mismatches += 1

    print(f"\n  Quarterly Trends: {trend_matches} match, {trend_mismatches} mismatch")

    # Compute ML features
    print("\n[3/5] Computing ML features...")

    # Lambda version: pass raw_financials for actual values
    ensemble_ml = ensemble_compute_ml(ensemble_trends, raw_data)

    # src/utils version: only takes quarterly_trends, sets many to 0
    src_ml = src_compute_ml(src_trends)

    # Define metrics that are currency vs percentage
    currency_metrics = [
        'total_debt', 'total_equity', 'total_assets', 'cash', 'net_debt',
        'operating_income', 'ebitda', 'operating_cash_flow', 'free_cash_flow',
        'revenue', 'net_income', 'gross_profit', 'working_capital',
        'interest_expense', 'current_assets', 'current_liabilities',
        'inventory', 'capital_expenditures', 'dividend_payout', 'share_buybacks'
    ]

    # Compare ML features by category
    print("\n" + "─"*90)
    print("ML FEATURES COMPARISON")
    print("─"*90)

    total_matches = 0
    total_mismatches = 0
    all_differences = []

    for agent_type in ['debt', 'cashflow', 'growth']:
        e_features = ensemble_ml.get(agent_type, {}).get('current', {})
        s_features = src_ml.get(agent_type, {}).get('current', {})

        matches, mismatches, diffs = compare_features(
            e_features, s_features, agent_type, currency_metrics
        )

        total_matches += matches
        total_mismatches += mismatches
        all_differences.extend(diffs)

        print(f"\n  {agent_type.upper()} FEATURES: {matches} match, {mismatches} mismatch")

    # Show significant differences
    if all_differences:
        print("\n" + "─"*90)
        print("SIGNIFICANT DIFFERENCES FOUND")
        print("─"*90)

        # Group by difference type
        zero_diffs = [d for d in all_differences if d['src_utils'] == '0' or d['src_utils'] == '0.0000']
        approx_diffs = [d for d in all_differences if d['src_utils'] != '0' and d['src_utils'] != '0.0000']

        if zero_diffs:
            print(f"\n  Metrics set to 0 in src/utils (computed in Lambda): {len(zero_diffs)}")
            print(f"  {'Metric':<35} {'Lambda':<20} {'src/utils':<15}")
            print(f"  {'-'*70}")
            for d in zero_diffs[:15]:  # Show first 15
                print(f"  {d['metric']:<35} {d['ensemble']:<20} {d['src_utils']:<15}")
            if len(zero_diffs) > 15:
                print(f"  ... and {len(zero_diffs) - 15} more")

        if approx_diffs:
            print(f"\n  Metrics with calculation differences: {len(approx_diffs)}")
            print(f"  {'Metric':<35} {'Lambda':<20} {'src/utils':<15} {'Diff':<10}")
            print(f"  {'-'*80}")
            for d in approx_diffs[:15]:
                print(f"  {d['metric']:<35} {d['ensemble']:<20} {d['src_utils']:<15} {d['diff']:<10}")
            if len(approx_diffs) > 15:
                print(f"  ... and {len(approx_diffs) - 15} more")

    # Compare annual aggregation
    print("\n[4/5] Comparing annual aggregation...")
    print("\n" + "─"*90)
    print("ANNUAL AGGREGATION COMPARISON")
    print("─"*90)

    ensemble_annual = ensemble_aggregate(income, balance, cashflow)

    # For src/utils, there's no standalone function, so we replicate what Investment Research does
    # (it uses _aggregate_annual_data as a class method)
    print(f"\n  NOTE: src/utils doesn't have standalone aggregate_annual_data()")
    print(f"  Lambda aggregate_annual_data() returns {len(ensemble_annual)} fiscal years")

    for year in sorted(ensemble_annual.keys(), reverse=True)[:3]:
        data = ensemble_annual[year]
        inc = data.get('income', {})
        print(f"\n  FY{year}:")
        print(f"    Revenue:    ${inc.get('revenue', 0)/1e9:.1f}B (sum of {data.get('quarters_count', 0)} quarters)")
        print(f"    Net Income: ${inc.get('netIncome', 0)/1e9:.1f}B")
        print(f"    FCF:        ${data.get('cashflow', {}).get('freeCashFlow', 0)/1e9:.1f}B")

    # Summary
    print("\n[5/5] Summary")
    print("\n" + "="*90)
    print("AUDIT SUMMARY")
    print("="*90)

    print(f"\n  Quarterly Trends:")
    print(f"    ✓ Matches:    {trend_matches}")
    print(f"    ✗ Mismatches: {trend_mismatches}")

    print(f"\n  ML Features:")
    print(f"    ✓ Matches:    {total_matches}")
    print(f"    ✗ Mismatches: {total_mismatches}")

    # Key findings
    print(f"\n  KEY FINDINGS:")
    print(f"  ─────────────")
    if zero_diffs:
        print(f"  ⚠️  {len(zero_diffs)} metrics are 0 in src/utils but computed in Lambda")
        print(f"     These include: total_equity, total_assets, roa, roic, quick_ratio, etc.")

    print(f"\n  RECOMMENDATION:")
    print(f"  ───────────────")
    print(f"  The Lambda version has more complete feature computation because")
    print(f"  compute_ml_features() accepts raw_financials to extract absolute values.")
    print(f"  Consider updating src/utils/feature_extractor.py to match Lambda version.")

    print(f"\n{'='*90}\n")

    return total_mismatches == 0


if __name__ == '__main__':
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'JPM'
    fiscal_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

    try:
        run_comparison(ticker, fiscal_year)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
