#!/usr/bin/env python3
"""
Metrics Audit: Compare Prediction Ensemble vs Investment Research

Validates that both Lambda systems produce consistent financial metrics.

Usage:
    python test_metrics_audit.py [TICKER] [YEAR]

Example:
    python test_metrics_audit.py JPM 2026
"""

import sys
import os
from decimal import Decimal

os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('ENVIRONMENT', 'dev')

import boto3

# Add paths for imports
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ENSEMBLE_DIR = os.path.join(BACKEND_DIR, 'lambda', 'prediction_ensemble')
RESEARCH_DIR = os.path.join(BACKEND_DIR, 'investment_research')

sys.path.insert(0, ENSEMBLE_DIR)
sys.path.insert(0, RESEARCH_DIR)

from utils.feature_extractor import aggregate_annual_data as ensemble_aggregate


def decimal_to_float(obj):
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


def research_aggregate(income_statements, balance_sheets, cash_flows):
    """
    Replicate Investment Research aggregation logic.
    (Inline to avoid import issues with class-based structure)
    """
    INCOME_FLOW_METRICS = [
        'revenue', 'netIncome', 'grossProfit', 'operatingIncome',
        'costOfRevenue', 'operatingExpenses', 'interestExpense',
        'incomeBeforeTax', 'incomeTaxExpense', 'ebitda'
    ]
    CASHFLOW_FLOW_METRICS = [
        'operatingCashFlow', 'freeCashFlow', 'capitalExpenditure',
        'commonDividendsPaid', 'commonStockRepurchased'
    ]

    # Group by fiscal year (try fiscalYear first, then calendarYear, then parse from date)
    fiscal_years = {}

    def get_fy(stmt):
        fy = stmt.get('fiscalYear') or stmt.get('calendarYear')
        if fy:
            return int(fy)
        date = stmt.get('date', '')
        if date:
            return int(date[:4])
        return None

    for stmt in income_statements:
        fy = get_fy(stmt)
        if not fy:
            continue
        if fy not in fiscal_years:
            fiscal_years[fy] = {'income': [], 'balance': [], 'cashflow': []}
        fiscal_years[fy]['income'].append(stmt)

    for stmt in balance_sheets:
        fy = get_fy(stmt)
        if not fy:
            continue
        if fy not in fiscal_years:
            fiscal_years[fy] = {'income': [], 'balance': [], 'cashflow': []}
        fiscal_years[fy]['balance'].append(stmt)

    for stmt in cash_flows:
        fy = get_fy(stmt)
        if not fy:
            continue
        if fy not in fiscal_years:
            fiscal_years[fy] = {'income': [], 'balance': [], 'cashflow': []}
        fiscal_years[fy]['cashflow'].append(stmt)

    # Aggregate
    annual_data = {}
    for year, quarters in fiscal_years.items():
        aggregated_income = {}
        aggregated_cashflow = {}
        aggregated_balance = {}

        if quarters['income']:
            for metric in INCOME_FLOW_METRICS:
                total = sum(q.get(metric, 0) or 0 for q in quarters['income'])
                aggregated_income[metric] = total

        if quarters['cashflow']:
            for metric in CASHFLOW_FLOW_METRICS:
                total = sum(q.get(metric, 0) or 0 for q in quarters['cashflow'])
                aggregated_cashflow[metric] = total

        if quarters['balance']:
            # Point-in-time: use most recent quarter
            sorted_balance = sorted(quarters['balance'], key=lambda x: x.get('date', ''), reverse=True)
            aggregated_balance = {
                'totalDebt': sorted_balance[0].get('totalDebt', 0),
                'cashAndCashEquivalents': sorted_balance[0].get('cashAndCashEquivalents', 0),
                'totalStockholdersEquity': sorted_balance[0].get('totalStockholdersEquity', 0)
            }

        annual_data[year] = {
            'income': aggregated_income,
            'cashflow': aggregated_cashflow,
            'balance': aggregated_balance,
            'quarters_count': len(quarters['income'])
        }

    return annual_data


def fmt(value, suffix=''):
    """Format large numbers as billions."""
    if value is None:
        return "N/A"
    return f"${value/1e9:.1f}B{suffix}"


def compare_metrics(ticker: str, fiscal_year: int):
    """Compare metrics between Prediction Ensemble and Investment Research."""
    print(f"\n{'='*80}")
    print(f"METRICS AUDIT: {ticker} (FY{fiscal_year})")
    print(f"{'='*80}")

    # Fetch data
    print("\n[1/3] Fetching data from DynamoDB...")
    raw_data = fetch_data(ticker, fiscal_year)

    income = raw_data.get('income_statement', [])
    balance = raw_data.get('balance_sheet', [])
    cashflow = raw_data.get('cash_flow', [])

    print(f"  - {len(income)} income statements")
    print(f"  - {len(balance)} balance sheets")
    print(f"  - {len(cashflow)} cash flow statements")

    # Run both aggregations
    print("\n[2/3] Running aggregation functions...")
    ensemble_data = ensemble_aggregate(income, balance, cashflow)
    research_data = research_aggregate(income, balance, cashflow)

    # Compare
    print("\n[3/3] Comparing metrics...\n")

    fiscal_years = sorted(set(ensemble_data.keys()) | set(research_data.keys()), reverse=True)

    all_match = True

    for fy in fiscal_years[:5]:  # Last 5 years
        print(f"\n{'─'*60}")
        print(f"FY{fy}")
        print(f"{'─'*60}")

        e_data = ensemble_data.get(fy, {})
        r_data = research_data.get(fy, {})

        e_inc = e_data.get('income', {})
        r_inc = r_data.get('income', {})
        e_cf = e_data.get('cashflow', {})
        r_cf = r_data.get('cashflow', {})
        e_bal = e_data.get('balance', {})
        r_bal = r_data.get('balance', {})

        # Income metrics
        metrics = [
            ('Revenue', 'revenue', e_inc, r_inc),
            ('Net Income', 'netIncome', e_inc, r_inc),
            ('Gross Profit', 'grossProfit', e_inc, r_inc),
            ('Operating Income', 'operatingIncome', e_inc, r_inc),
        ]

        print(f"\n{'Metric':<20} {'Ensemble':>15} {'Research':>15} {'Match':>10}")
        print("-" * 60)

        for name, key, e_dict, r_dict in metrics:
            e_val = e_dict.get(key, 0)
            r_val = r_dict.get(key, 0)
            match = "✓" if abs(e_val - r_val) < 1 else "✗"
            if match == "✗":
                all_match = False
            print(f"{name:<20} {fmt(e_val):>15} {fmt(r_val):>15} {match:>10}")

        # Cash flow metrics
        cf_metrics = [
            ('Op. Cash Flow', 'operatingCashFlow', e_cf, r_cf),
            ('Free Cash Flow', 'freeCashFlow', e_cf, r_cf),
            ('Buybacks', 'commonStockRepurchased', e_cf, r_cf),
        ]

        print()
        for name, key, e_dict, r_dict in cf_metrics:
            e_val = abs(e_dict.get(key, 0) or 0)
            r_val = abs(r_dict.get(key, 0) or 0)
            match = "✓" if abs(e_val - r_val) < 1 else "✗"
            if match == "✗":
                all_match = False
            print(f"{name:<20} {fmt(e_val):>15} {fmt(r_val):>15} {match:>10}")

        # Balance sheet metrics
        bal_metrics = [
            ('Total Debt', 'totalDebt', e_bal, r_bal),
            ('Cash', 'cashAndCashEquivalents', e_bal, r_bal),
            ('Equity', 'totalStockholdersEquity', e_bal, r_bal),
        ]

        print()
        for name, key, e_dict, r_dict in bal_metrics:
            e_val = e_dict.get(key, 0) or 0
            r_val = r_dict.get(key, 0) or 0
            match = "✓" if abs(e_val - r_val) < 1 else "✗"
            if match == "✗":
                all_match = False
            print(f"{name:<20} {fmt(e_val):>15} {fmt(r_val):>15} {match:>10}")

    # Summary
    print(f"\n{'='*60}")
    if all_match:
        print("✅ ALL METRICS MATCH - Both systems are consistent")
    else:
        print("⚠️  METRICS MISMATCH - Review differences above")
    print(f"{'='*60}")

    return all_match


if __name__ == '__main__':
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'JPM'
    fiscal_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

    try:
        compare_metrics(ticker, fiscal_year)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
