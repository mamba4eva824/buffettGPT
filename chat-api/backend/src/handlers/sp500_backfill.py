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
SP500_VALUATIONS_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_valuations'
SP500_HIST_VALUATIONS_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_historical_valuations'
SP500_PRICES_DIR = BACKEND_DIR.parent.parent / 'sp500_analysis' / 'data' / 'company_prices'

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


def load_local_valuations(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Load TTM valuation data from local JSON file.

    Returns dict with valuation metrics, or None if not available.
    Extracts and normalizes the key valuation multiples from FMP TTM data.
    """
    json_path = SP500_VALUATIONS_DIR / f'{ticker}.json'
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    if not data or not data.get('marketCap'):
        return None

    # Extract and normalize valuation metrics
    earnings_yield = data.get('earningsYieldTTM', 0)
    fcf_yield = data.get('freeCashFlowYieldTTM', 0)

    valuation = {
        'market_cap': data.get('marketCap'),
        'enterprise_value': data.get('enterpriseValueTTM'),
        'pe_ratio': round(1 / earnings_yield, 2) if earnings_yield and earnings_yield > 0 else None,
        'earnings_yield': round(earnings_yield * 100, 2) if earnings_yield else None,
        'ev_to_ebitda': round(data.get('evToEBITDATTM', 0), 2) if data.get('evToEBITDATTM') else None,
        'ev_to_sales': round(data.get('evToSalesTTM', 0), 2) if data.get('evToSalesTTM') else None,
        'ev_to_fcf': round(data.get('evToFreeCashFlowTTM', 0), 2) if data.get('evToFreeCashFlowTTM') else None,
        'fcf_yield': round(fcf_yield * 100, 2) if fcf_yield else None,
        'price_to_fcf': round(1 / fcf_yield, 2) if fcf_yield and fcf_yield > 0 else None,
    }

    # Remove None values
    return {k: v for k, v in valuation.items() if v is not None}


def _days_between(date1: str, date2: str) -> int:
    """Calculate days between two YYYY-MM-DD date strings."""
    from datetime import datetime as dt
    d1 = dt.strptime(date1, '%Y-%m-%d')
    d2 = dt.strptime(date2, '%Y-%m-%d')
    return (d1 - d2).days


def load_local_historical_valuations(ticker: str) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Load historical valuation data from local JSON file (quarterly or annual).

    Returns dict mapping fiscal_date -> valuation metrics dict.
    """
    json_path = SP500_HIST_VALUATIONS_DIR / f'{ticker}.json'
    if not json_path.exists():
        return None

    with open(json_path) as f:
        data = json.load(f)

    if not isinstance(data, list) or not data:
        return None

    # Map each annual record to its fiscal_date
    by_date = {}
    for record in data:
        date = record.get('date')
        if not date:
            continue

        earnings_yield = record.get('earningsYield', 0)
        fcf_yield_raw = record.get('freeCashFlowYield', 0)

        valuation = {
            'market_cap': record.get('marketCap'),
            'enterprise_value': record.get('enterpriseValue'),
            'pe_ratio': round(1 / earnings_yield, 2) if earnings_yield and earnings_yield > 0 else None,
            'earnings_yield': round(earnings_yield * 100, 2) if earnings_yield else None,
            'ev_to_ebitda': round(record.get('evToEBITDA', 0), 2) if record.get('evToEBITDA') else None,
            'ev_to_sales': round(record.get('evToSales', 0), 2) if record.get('evToSales') else None,
            'ev_to_fcf': round(record.get('evToFreeCashFlow', 0), 2) if record.get('evToFreeCashFlow') else None,
            'fcf_yield': round(fcf_yield_raw * 100, 2) if fcf_yield_raw else None,
        }

        # Remove None values
        by_date[date] = {k: v for k, v in valuation.items() if v is not None}

    return by_date if by_date else None


def compute_quarterly_valuations(ticker: str, items: list) -> int:
    """
    Compute quarterly valuation multiples (P/E, P/B, EV/EBITDA, P/FCF) from
    local daily price data + fundamentals already on each item.

    FMP's quarterly key-metrics requires a premium plan, so we derive these
    ourselves from stock price at quarter-end + financial statement data.

    Mutates items in-place, adding market_valuation dict to each item.
    Returns count of items enriched.
    """
    from datetime import datetime as dt

    # Load daily prices
    prices_path = SP500_PRICES_DIR / f'{ticker}.json'
    if not prices_path.exists():
        return 0

    with open(prices_path) as f:
        price_data = json.load(f)

    if not price_data:
        return 0

    # Build date -> price lookup
    prices_by_date = {p['date']: p['price'] for p in price_data if p.get('price')}

    def closest_price(fiscal_date: str) -> Optional[float]:
        """Find price on fiscal_date or nearest trading day within 5 days."""
        if fiscal_date in prices_by_date:
            return prices_by_date[fiscal_date]
        target = dt.strptime(fiscal_date, '%Y-%m-%d')
        for offset in range(1, 6):
            for delta in [offset, -offset]:
                d = (target + __import__('datetime').timedelta(days=delta)).strftime('%Y-%m-%d')
                if d in prices_by_date:
                    return prices_by_date[d]
        return None

    # Sort items chronologically for TTM computation
    sorted_items = sorted(items, key=lambda x: x.get('fiscal_date', ''))
    enriched = 0

    for idx, item in enumerate(sorted_items):
        fiscal_date = item.get('fiscal_date')
        if not fiscal_date:
            continue

        # Skip if item already has market_valuation from FMP annual data
        if item.get('market_valuation') and item['market_valuation'].get('pe_ratio'):
            continue

        price = closest_price(fiscal_date)
        if not price:
            continue

        rp = item.get('revenue_profit', {})
        bs = item.get('balance_sheet', {})
        cf = item.get('cashflow', {})
        dil = item.get('dilution', {})

        diluted_shares = dil.get('diluted_shares')
        total_equity = bs.get('total_equity')
        total_debt = bs.get('total_debt', 0)
        cash = bs.get('cash_position', 0)

        if not diluted_shares or diluted_shares <= 0:
            continue

        market_cap = price * diluted_shares

        # TTM sums (need 4 quarters of history)
        if idx < 3:
            continue
        last4 = sorted_items[idx - 3:idx + 1]

        ttm_eps = sum(q.get('revenue_profit', {}).get('eps', 0) or 0 for q in last4)
        ttm_ebitda = sum(q.get('revenue_profit', {}).get('ebitda', 0) or 0 for q in last4)
        ttm_fcf = sum(q.get('cashflow', {}).get('free_cash_flow', 0) or 0 for q in last4)

        enterprise_value = market_cap + total_debt - cash

        valuation = {
            'market_cap': round(market_cap),
            'enterprise_value': round(enterprise_value),
            'pe_ratio': round(price / (ttm_eps if ttm_eps else 1), 2) if ttm_eps and ttm_eps > 0 else None,
            'earnings_yield': round((ttm_eps / price) * 100, 2) if ttm_eps and ttm_eps > 0 else None,
            'ev_to_ebitda': round(enterprise_value / ttm_ebitda, 2) if ttm_ebitda and ttm_ebitda > 0 else None,
            'fcf_yield': round((ttm_fcf / market_cap) * 100, 2) if ttm_fcf and market_cap > 0 else None,
        }

        # Remove None values
        valuation = {k: v for k, v in valuation.items() if v is not None}

        if valuation.get('pe_ratio'):
            item['market_valuation'] = valuation
            enriched += 1

    return enriched


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

    # Attach TTM valuation data to the latest quarter item
    valuation_data = load_local_valuations(ticker)
    if valuation_data:
        latest_item = max(items, key=lambda x: x.get('fiscal_date', ''))
        latest_item['market_valuation'] = valuation_data

    # Attach historical valuations to matching quarterly items
    hist_valuations = load_local_historical_valuations(ticker)
    if hist_valuations:
        items_by_date = {item.get('fiscal_date'): item for item in items}
        matched = 0
        for val_date, val_data in hist_valuations.items():
            if val_date in items_by_date:
                # Exact date match — annual valuation maps to this quarter
                items_by_date[val_date]['market_valuation'] = val_data
                matched += 1
            else:
                # Find closest quarterly item within 45 days of the annual date
                for item in items:
                    item_date = item.get('fiscal_date', '')
                    if item_date and abs(_days_between(val_date, item_date)) <= 45:
                        if 'market_valuation' not in item:
                            item['market_valuation'] = val_data
                            matched += 1
                            break
        if matched > 0:
            logger.debug(f"{ticker}: mapped {matched} historical valuations to quarterly items")

    # Fill remaining quarters with price-derived valuation multiples
    price_enriched = compute_quarterly_valuations(ticker, items)
    if price_enriched > 0:
        logger.debug(f"{ticker}: computed {price_enriched} quarterly valuations from price data")

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
