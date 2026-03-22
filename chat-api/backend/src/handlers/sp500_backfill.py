"""
S&P 500 Local JSON Backfill Script

One-time script that reads pre-fetched financial data from
sp500_analysis/data/company_financials/ and populates the
metrics-history DynamoDB table without making any FMP API calls.

The local JSON files use a different key format than fmp_client:
  Local:  {"income": [...], "cashflow": [...], "balance": [...]}
  FMP:    {"income_statement": [...], "cash_flow": [...], "balance_sheet": [...]}

This script handles the key mapping before passing to feature_extractor.

Usage (from chat-api/backend/):
    python -m src.handlers.sp500_backfill
    python -m src.handlers.sp500_backfill --tickers AAPL MSFT
    python -m src.handlers.sp500_backfill --dry-run
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

import boto3

# Add backend to path for imports
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from src.utils.feature_extractor import extract_quarterly_trends, prepare_metrics_for_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Paths
SP500_DATA_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_financials'
SP500_DIVIDENDS_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_dividends'
SP500_EARNINGS_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_earnings'

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')

# Key mapping: local JSON format -> fmp_client format
KEY_MAP = {
    'income': 'income_statement',
    'cashflow': 'cash_flow',
    'balance': 'balance_sheet',
}


def load_local_financials(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Load and remap financial data from local JSON file.

    Converts sp500_analysis format to fmp_client format:
        income -> income_statement
        cashflow -> cash_flow
        balance -> balance_sheet
    """
    json_path = SP500_DATA_DIR / f'{ticker}.json'
    if not json_path.exists():
        # Try with dot-to-hyphen conversion (BRK.B -> BRK-B not needed here,
        # files are named with dots)
        logger.warning(f"File not found: {json_path}")
        return None

    with open(json_path) as f:
        data = json.load(f)

    # Remap keys
    raw_financials = {}
    for local_key, fmp_key in KEY_MAP.items():
        raw_financials[fmp_key] = data.get(local_key, [])

    # Validate we have data
    total_records = sum(len(v) for v in raw_financials.values())
    if total_records == 0:
        logger.warning(f"No financial data in {json_path}")
        return None

    return raw_financials


def load_local_dividends(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """
    Load dividend history from local JSON file.

    Returns list of FMP dividend records, or None if not available.
    """
    json_path = SP500_DIVIDENDS_DIR / f'{ticker}.json'
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    # Dividend files are a flat list of records
    if isinstance(data, list) and len(data) > 0:
        return data
    return None


def load_local_earnings(ticker: str) -> Optional[List[Dict[str, Any]]]:
    """
    Load earnings history from local JSON file.

    Returns list of FMP earnings records, or None if not available.
    """
    json_path = SP500_EARNINGS_DIR / f'{ticker}.json'
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    if isinstance(data, list) and len(data) > 0:
        return data
    return None


def backfill_ticker(
    ticker: str,
    metrics_table,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Process a single ticker from local JSON into metrics-history table.

    Returns summary dict with item_count and status.
    """
    raw_financials = load_local_financials(ticker)
    if not raw_financials:
        return {'ticker': ticker, 'status': 'no_data', 'items': 0}

    # Extract quarterly trends (same function used by report_generator)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Detect currency from first record (local files don't store currency_info)
    currency = 'USD'
    first_income = (raw_financials.get('income_statement') or [{}])[0] if raw_financials.get('income_statement') else {}
    reported_currency = first_income.get('reportedCurrency', 'USD')
    if reported_currency:
        currency = reported_currency

    # Load dividend and earnings history from local files
    dividend_history = load_local_dividends(ticker)
    earnings_history = load_local_earnings(ticker)

    # Prepare metrics items (including dividend + earnings data when available)
    items = prepare_metrics_for_cache(
        ticker=ticker,
        quarterly_trends=quarterly_trends,
        currency=currency,
        source_cache_key=f'backfill:{ticker}:{datetime.now().year}',
        earnings_history=earnings_history,
        dividend_history=dividend_history,
    )

    if not items:
        return {'ticker': ticker, 'status': 'no_metrics', 'items': 0}

    if dry_run:
        logger.info(f"[DRY RUN] {ticker}: would write {len(items)} items")
        return {'ticker': ticker, 'status': 'dry_run', 'items': len(items)}

    # Batch write to DynamoDB
    with metrics_table.batch_writer() as batch:
        for item in items:
            item_decimal = json.loads(
                json.dumps(item, default=str),
                parse_float=Decimal
            )
            batch.put_item(Item=item_decimal)

    return {'ticker': ticker, 'status': 'success', 'items': len(items)}


def run_backfill(
    tickers: Optional[List[str]] = None,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Run the full backfill for all (or specified) S&P 500 tickers.

    Returns summary with counts and failures.
    """
    from investment_research.index_tickers import SP500_TICKERS

    if tickers is None:
        tickers = SP500_TICKERS

    # Verify data directory exists
    if not SP500_DATA_DIR.exists():
        raise FileNotFoundError(f"Data directory not found: {SP500_DATA_DIR}")

    available_files = set(f.stem for f in SP500_DATA_DIR.glob('*.json'))
    logger.info(f"Data directory: {SP500_DATA_DIR} ({len(available_files)} files)")
    logger.info(f"Processing {len(tickers)} tickers (dry_run={dry_run})")

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(METRICS_TABLE)

    results = {
        'total': len(tickers),
        'success': 0,
        'no_data': 0,
        'no_metrics': 0,
        'failures': [],
        'started_at': datetime.now().isoformat(),
    }

    start_time = time.time()

    for i, ticker in enumerate(tickers):
        try:
            result = backfill_ticker(ticker, table, dry_run=dry_run)

            if result['status'] == 'success' or result['status'] == 'dry_run':
                results['success'] += 1
            elif result['status'] == 'no_data':
                results['no_data'] += 1
            elif result['status'] == 'no_metrics':
                results['no_metrics'] += 1

            if (i + 1) % 50 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                logger.info(f"Progress: {i + 1}/{len(tickers)} "
                            f"({rate:.1f} tickers/sec) | "
                            f"success={results['success']} "
                            f"no_data={results['no_data']} "
                            f"failures={len(results['failures'])}")

        except Exception as e:
            logger.error(f"Failed {ticker}: {e}")
            results['failures'].append({'ticker': ticker, 'error': str(e)})

    elapsed = time.time() - start_time
    results['completed_at'] = datetime.now().isoformat()
    results['elapsed_seconds'] = round(elapsed, 1)

    logger.info(f"Backfill complete in {elapsed:.1f}s: {json.dumps(results, default=str)}")
    return results


# Also usable as a Lambda handler
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda entry point for backfill (optional — primarily a CLI script)."""
    tickers = event.get('tickers')
    dry_run = event.get('dry_run', False)
    return run_backfill(tickers=tickers, dry_run=dry_run)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Backfill S&P 500 metrics from local JSON')
    parser.add_argument('--tickers', nargs='+', help='Specific tickers to process')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    results = run_backfill(tickers=args.tickers, dry_run=args.dry_run)
    print(json.dumps(results, indent=2, default=str))
