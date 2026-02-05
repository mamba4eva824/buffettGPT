#!/usr/bin/env python3
"""
Local test script for feature extraction and model inference.
Replicates the Lambda's flow using DynamoDB cached data and S3 models.

Usage:
    python test_local_inference.py [TICKER] [YEAR]

Example:
    python test_local_inference.py JPM 2026
    python test_local_inference.py AAPL 2026
"""

import sys
import os
import json
import logging
from decimal import Decimal

# Set up environment for local testing
os.environ.setdefault('AWS_DEFAULT_REGION', 'us-east-1')
os.environ.setdefault('AWS_REGION', 'us-east-1')
os.environ.setdefault('ENVIRONMENT', 'dev')
os.environ.setdefault('ML_MODELS_BUCKET', 'buffett-dev-models')
os.environ.setdefault('MODEL_S3_PREFIX', 'ensemble/v1')

import boto3

# Add the prediction_ensemble lambda directory to path for imports
LAMBDA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'lambda', 'prediction_ensemble')
sys.path.insert(0, LAMBDA_DIR)

from utils.feature_extractor import extract_all_features, aggregate_annual_data
from services.inference import run_inference, clear_model_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def decimal_to_float(obj):
    """Recursively convert Decimal objects to float."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(i) for i in obj]
    return obj


def fetch_cached_data(ticker: str, fiscal_year: int) -> dict:
    """Fetch cached financial data from DynamoDB."""
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table('buffett-dev-financial-data-cache')

    cache_key = f"v3:{ticker}:{fiscal_year}"
    logger.info(f"Fetching data from DynamoDB with cache_key: {cache_key}")

    response = table.get_item(Key={'cache_key': cache_key})

    if 'Item' not in response:
        raise ValueError(f"No cached data found for {ticker} (key: {cache_key})")

    item = response['Item']
    raw_financials = item.get('raw_financials', {})

    return decimal_to_float(raw_financials)


def format_annual_summary(annual_data: dict) -> str:
    """Format annual data as a readable summary."""
    lines = []
    lines.append("\n" + "="*80)
    lines.append("ANNUAL AGGREGATED DATA (Fiscal Year Totals)")
    lines.append("="*80)

    # Get fiscal years in descending order
    fiscal_years = sorted([fy for fy in annual_data.keys() if isinstance(fy, int)], reverse=True)

    if not fiscal_years:
        lines.append("\nNo annual data available")
        return "\n".join(lines)

    # Income Statement
    lines.append("\n### Income Statement (Annual)")
    lines.append(f"{'Fiscal Year':<12} {'Revenue':>15} {'Net Income':>15} {'Gross Profit':>15}")
    lines.append("-" * 60)

    for fy in fiscal_years:
        income = annual_data[fy].get('income', {})
        revenue = income.get('revenue', 0) / 1e9
        net_income = income.get('netIncome', 0) / 1e9
        gross_profit = income.get('grossProfit', 0) / 1e9
        quarters = annual_data[fy].get('quarters_count', 0)
        lines.append(f"FY{fy:<10} ${revenue:>14.1f}B ${net_income:>14.1f}B ${gross_profit:>14.1f}B ({quarters}Q)")

    # Cash Flow
    lines.append("\n### Cash Flow Statement (Annual)")
    lines.append(f"{'Fiscal Year':<12} {'Op. Cash Flow':>15} {'Free Cash Flow':>15} {'Buybacks':>15}")
    lines.append("-" * 60)

    for fy in fiscal_years:
        cf = annual_data[fy].get('cashflow', {})
        ocf = cf.get('operatingCashFlow', 0) / 1e9
        fcf = cf.get('freeCashFlow', 0) / 1e9
        buybacks = abs(cf.get('commonStockRepurchased', 0)) / 1e9
        lines.append(f"FY{fy:<10} ${ocf:>14.1f}B ${fcf:>14.1f}B ${buybacks:>14.1f}B")

    # Balance Sheet (point-in-time)
    lines.append("\n### Balance Sheet (Year-End Snapshots)")
    lines.append(f"{'Fiscal Year':<12} {'Total Debt':>15} {'Cash':>15} {'Equity':>15}")
    lines.append("-" * 60)

    for fy in fiscal_years:
        balance = annual_data[fy].get('balance', {})
        debt = balance.get('totalDebt', 0) / 1e9
        cash = balance.get('cashAndCashEquivalents', 0) / 1e9
        equity = balance.get('totalStockholdersEquity', 0) / 1e9
        lines.append(f"FY{fy:<10} ${debt:>14.1f}B ${cash:>14.1f}B ${equity:>14.1f}B")

    return "\n".join(lines)


def run_local_test(ticker: str, fiscal_year: int):
    """Run the full feature extraction and inference pipeline locally."""
    print(f"\n{'='*80}")
    print(f"LOCAL INFERENCE TEST: {ticker} (FY{fiscal_year})")
    print(f"{'='*80}")

    # Step 1: Fetch cached data
    print("\n[1/4] Fetching cached data from DynamoDB...")
    raw_data = fetch_cached_data(ticker, fiscal_year)

    income_statements = raw_data.get('income_statement', [])
    balance_sheets = raw_data.get('balance_sheet', [])
    cash_flows = raw_data.get('cash_flow', [])

    print(f"  - Income statements: {len(income_statements)} quarters")
    print(f"  - Balance sheets: {len(balance_sheets)} quarters")
    print(f"  - Cash flows: {len(cash_flows)} quarters")

    # Step 2: Annual aggregation
    print("\n[2/4] Aggregating quarterly data to annual...")
    annual_data = aggregate_annual_data(income_statements, balance_sheets, cash_flows)

    # Debug: print available keys and sample data
    print(f"  - Annual data keys: {list(annual_data.keys())}")
    for key in annual_data:
        if annual_data[key]:
            print(f"  - {key} fiscal years: {list(annual_data[key].keys())}")

    annual_summary = format_annual_summary(annual_data)
    print(annual_summary)

    # Step 3: Feature extraction
    print("\n[3/4] Extracting features for ML models...")
    features = extract_all_features(raw_data)

    print(f"  - Debt features: {len(features.get('debt', {}).get('current', {}))} metrics")
    print(f"  - Cashflow features: {len(features.get('cashflow', {}).get('current', {}))} metrics")
    print(f"  - Growth features: {len(features.get('growth', {}).get('current', {}))} metrics")

    # Step 4: Model inference
    print("\n[4/4] Running ML model inference...")
    print("  Loading models from S3 (buffett-dev-models/ensemble/v1)...")

    results = {}
    for model_type in ['debt', 'cashflow', 'growth']:
        print(f"\n  Running {model_type} model...")
        result = run_inference(model_type, features)
        results[model_type] = result

        print(f"    Prediction: {result['prediction']}")
        print(f"    Confidence: {result['confidence']:.0%} ({result['confidence_interpretation']})")
        print(f"    Probabilities: SELL={result['probabilities']['SELL']:.0%}, "
              f"HOLD={result['probabilities']['HOLD']:.0%}, "
              f"BUY={result['probabilities']['BUY']:.0%}")
        print(f"    Data Quality: {result['data_quality']}% ({result['data_quality_interpretation']})")

    # Summary
    print(f"\n{'='*80}")
    print("INFERENCE SUMMARY")
    print(f"{'='*80}")
    print(f"\n{'Expert':<12} {'Prediction':<10} {'Confidence':<12} {'Interpretation':<15}")
    print("-" * 50)
    for model_type in ['debt', 'cashflow', 'growth']:
        r = results[model_type]
        print(f"{model_type:<12} {r['prediction']:<10} {r['confidence']:.0%}{'':>5} {r['confidence_interpretation']:<15}")

    # Calculate consensus
    predictions = [results[m]['prediction'] for m in ['debt', 'cashflow', 'growth']]
    if predictions.count('BUY') >= 2:
        consensus = 'BUY'
    elif predictions.count('SELL') >= 2:
        consensus = 'SELL'
    else:
        consensus = 'HOLD'

    avg_confidence = sum(results[m]['confidence'] for m in ['debt', 'cashflow', 'growth']) / 3

    print(f"\n{'='*50}")
    print(f"CONSENSUS: {consensus} (avg confidence: {avg_confidence:.0%})")
    print(f"{'='*50}")

    return results, annual_data


if __name__ == '__main__':
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'JPM'
    fiscal_year = int(sys.argv[2]) if len(sys.argv) > 2 else 2026

    try:
        results, annual_data = run_local_test(ticker, fiscal_year)
        print("\n✅ Local inference test completed successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
