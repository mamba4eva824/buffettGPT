#!/usr/bin/env python3
"""
Backfill Q4 2025 earnings data using FMP /stable/earnings API directly.

Fetches reported earnings from FMP and updates the earnings_events field
on existing metrics-history quarterly items. Only touches earnings_events —
does NOT replace financial statement data.

Usage:
    python scripts/backfill_q4_earnings.py                    # All S&P 500
    python scripts/backfill_q4_earnings.py --tickers AAPL MSFT # Specific tickers
    python scripts/backfill_q4_earnings.py --dry-run            # Preview what would be updated
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from decimal import Decimal

import boto3
import urllib3

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)
secrets_client = boto3.client('secretsmanager')
http = urllib3.PoolManager()

_fmp_api_key = None


def get_fmp_api_key():
    global _fmp_api_key
    if _fmp_api_key is None:
        response = secrets_client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        _fmp_api_key = secret['FMP_API_KEY']
    return _fmp_api_key


def get_sp500_tickers():
    try:
        from investment_research.index_tickers import SP500_TICKERS
        return sorted(SP500_TICKERS)
    except ImportError:
        return ["AAPL", "MSFT", "GOOGL"]


def fetch_earnings_from_fmp(ticker, limit=6):
    """Fetch recent earnings from FMP /stable/earnings endpoint."""
    api_key = get_fmp_api_key()
    fmp_ticker = ticker.replace('.', '-')
    url = f"{FMP_BASE_URL}/earnings?symbol={fmp_ticker}&limit={limit}&apikey={api_key}"

    try:
        resp = http.request("GET", url, timeout=15.0)
        if resp.status == 429:
            time.sleep(2)
            resp = http.request("GET", url, timeout=15.0)
        if resp.status != 200:
            return []
        data = json.loads(resp.data.decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  Error fetching earnings for {ticker}: {e}")
        return []


def get_existing_quarters(ticker):
    """Get all fiscal_dates for this ticker from metrics-history."""
    resp = metrics_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('ticker').eq(ticker),
        ProjectionExpression="fiscal_date, earnings_events",
        ScanIndexForward=True,
    )
    return resp.get('Items', [])


def align_and_update(ticker, earnings, quarters, dry_run=False):
    """
    Match FMP earnings to fiscal quarters and update earnings_events.

    Returns count of quarters updated.
    """
    if not earnings or not quarters:
        return 0

    sorted_dates = sorted([q['fiscal_date'] for q in quarters])
    existing_ee = {q['fiscal_date']: q.get('earnings_events', {}) for q in quarters}
    updated = 0

    # Process reported earnings only (has epsActual)
    for earning in earnings:
        eps_actual = earning.get('epsActual')
        if eps_actual is None:
            continue  # Skip upcoming/unannounced

        earn_date = earning.get('date', '')
        if not earn_date:
            continue

        # Find the most recent fiscal_date before the earnings announcement
        best_match = None
        for fd in sorted_dates:
            if fd <= earn_date:
                best_match = fd
            else:
                break

        if not best_match:
            continue

        # Check if this quarter already has this earnings data
        existing = existing_ee.get(best_match, {})
        if existing.get('eps_actual') and str(existing.get('eps_actual')) == str(eps_actual):
            continue  # Already up to date

        eps_estimated = earning.get('epsEstimated')
        rev_actual = earning.get('revenueActual')
        rev_estimated = earning.get('revenueEstimated')

        ee = {'earnings_date': earn_date, 'eps_actual': Decimal(str(eps_actual))}

        if eps_estimated is not None:
            ee['eps_estimated'] = Decimal(str(eps_estimated))
            if float(eps_estimated) != 0:
                surprise = ((float(eps_actual) - float(eps_estimated)) / abs(float(eps_estimated))) * 100
                ee['eps_surprise_pct'] = Decimal(str(surprise))
                ee['eps_beat'] = float(eps_actual) > float(eps_estimated)

        if rev_actual is not None:
            ee['revenue_actual'] = Decimal(str(rev_actual))
        if rev_estimated is not None:
            ee['revenue_estimated'] = Decimal(str(rev_estimated))
            if rev_actual is not None and float(rev_estimated) != 0:
                rev_surprise = ((float(rev_actual) - float(rev_estimated)) / abs(float(rev_estimated))) * 100
                ee['revenue_surprise_pct'] = Decimal(str(rev_surprise))

        if dry_run:
            beat = "BEAT" if ee.get('eps_beat') else "MISS"
            print(f"  {ticker} {best_match}: {earn_date} EPS ${eps_actual} vs ${eps_estimated} ({beat})")
        else:
            # Update just the earnings_events attribute
            metrics_table.update_item(
                Key={'ticker': ticker, 'fiscal_date': best_match},
                UpdateExpression="SET earnings_events = :ee",
                ExpressionAttributeValues={':ee': ee},
            )

        updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill Q4 2025 earnings from FMP API")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers")
    parser.add_argument("--dry-run", action="store_true", help="Preview updates without writing")
    parser.add_argument("--limit", type=int, default=0, help="Max tickers to process (0=all)")
    args = parser.parse_args()

    tickers = sorted(args.tickers) if args.tickers else get_sp500_tickers()

    print(f"Table: {METRICS_TABLE}")
    print(f"Mode:  {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Tickers: {len(tickers)}")
    print()

    total_updated = 0
    total_skipped = 0
    errors = 0

    to_process = tickers[:args.limit] if args.limit else tickers

    for i, ticker in enumerate(to_process):
        try:
            earnings = fetch_earnings_from_fmp(ticker)
            quarters = get_existing_quarters(ticker)
            count = align_and_update(ticker, earnings, quarters, dry_run=args.dry_run)
            total_updated += count
            if count == 0:
                total_skipped += 1
        except Exception as e:
            errors += 1
            print(f"  ERROR {ticker}: {e}")

        if (i + 1) % 50 == 0 or (i + 1) == len(to_process):
            print(f"  [{i+1}/{len(to_process)}] {total_updated} quarters updated, {total_skipped} already current")

        # Rate limit: 1 FMP call per ticker, 300/min limit → 0.5s delay
        if i + 1 < len(to_process):
            time.sleep(0.5)

    print()
    print(f"Done! {total_updated} quarters updated with reported earnings.")
    print(f"  Already current: {total_skipped}")
    print(f"  Errors: {errors}")


if __name__ == "__main__":
    main()
