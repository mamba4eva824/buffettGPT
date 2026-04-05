#!/usr/bin/env python3
"""
Backfill daily EOD prices from FMP's historical-price-eod/full endpoint.

Fetches daily OHLCV data for all S&P 500 tickers and stores in the
stock-data-4h DynamoDB table with SK prefix DAILY# (vs DATETIME# for 4h candles).

Usage:
    python scripts/backfill_eod_prices.py                        # Last 30 trading days
    python scripts/backfill_eod_prices.py --days 60              # Last 60 days
    python scripts/backfill_eod_prices.py --tickers AAPL MSFT    # Specific tickers
    python scripts/backfill_eod_prices.py --force                # Overwrite existing
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
import urllib3

# Add src and project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Config
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
TABLE_NAME = os.environ.get('STOCK_DATA_4H_TABLE', f'stock-data-4h-{ENVIRONMENT}')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
BATCH_WRITE_SIZE = 25

# AWS
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)
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
        print("WARNING: index_tickers not available, using small test set")
        return ["AAPL", "MSFT", "GOOGL"]


def to_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def fetch_daily_prices(ticker, from_date, to_date):
    """Fetch daily EOD prices from FMP for a date range."""
    api_key = get_fmp_api_key()
    fmp_ticker = ticker.replace('.', '-')
    url = (
        f"{FMP_BASE_URL}/historical-price-eod/full"
        f"?symbol={fmp_ticker}&from={from_date}&to={to_date}&apikey={api_key}"
    )
    try:
        resp = http.request("GET", url, timeout=15.0)
        if resp.status == 429:
            print(f"  Rate limited on {ticker}, waiting 2s...")
            time.sleep(2)
            resp = http.request("GET", url, timeout=15.0)
        if resp.status != 200:
            return []
        data = json.loads(resp.data.decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return []


def build_daily_items(ticker, daily_prices):
    """Convert FMP daily price records to DynamoDB items."""
    items = []
    now_iso = datetime.now(timezone.utc).isoformat()
    expires_at = int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp())

    for dp in daily_prices:
        trade_date = dp.get("date", "")
        if not trade_date:
            continue

        items.append({
            "PK": f"TICKER#{ticker}",
            "SK": f"DAILY#{trade_date}",
            "GSI_PK": f"DATE#{trade_date}",
            "GSI_SK": f"TICKER#{ticker}",
            "symbol": ticker,
            "date": trade_date,
            "open": to_decimal(dp.get("open")),
            "high": to_decimal(dp.get("high")),
            "low": to_decimal(dp.get("low")),
            "close": to_decimal(dp.get("close")),
            "volume": int(dp.get("volume") or 0),
            "change": to_decimal(dp.get("change")),
            "change_percent": to_decimal(dp.get("changePercent")),
            "vwap": to_decimal(dp.get("vwap")),
            "ingested_at": now_iso,
            "expires_at": expires_at,
        })

    return items


def batch_write(items):
    written = 0
    for i in range(0, len(items), BATCH_WRITE_SIZE):
        chunk = items[i:i + BATCH_WRITE_SIZE]
        request_items = {TABLE_NAME: [{"PutRequest": {"Item": item}} for item in chunk]}
        for attempt in range(5):
            response = dynamodb.meta.client.batch_write_item(RequestItems=request_items)
            unprocessed = response.get("UnprocessedItems", {})
            if not unprocessed:
                written += len(chunk)
                break
            remaining = len(unprocessed.get(TABLE_NAME, []))
            written += len(chunk) - remaining
            request_items = unprocessed
            chunk = [r["PutRequest"]["Item"] for r in unprocessed[TABLE_NAME]]
            time.sleep(min(2 ** attempt * 0.5, 8))
        else:
            print(f"  WARNING: {len(chunk)} items failed after retries")
    return written


def main():
    parser = argparse.ArgumentParser(description="Backfill daily EOD prices")
    parser.add_argument("--days", type=int, default=30, help="Number of calendar days to backfill (default: 30)")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (default: all S&P 500)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing data")
    args = parser.parse_args()

    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y-%m-%d")

    print(f"Table:      {TABLE_NAME}")
    print(f"Date range: {from_date} to {to_date}")
    print(f"Days:       {args.days}")
    print()

    tickers = sorted(args.tickers) if args.tickers else get_sp500_tickers()
    print(f"Processing {len(tickers)} tickers...")
    print()

    total_items = 0
    total_written = 0
    tickers_with_data = 0

    for i, ticker in enumerate(tickers):
        daily_prices = fetch_daily_prices(ticker, from_date, to_date)

        if daily_prices:
            items = build_daily_items(ticker, daily_prices)
            written = batch_write(items)
            total_items += len(items)
            total_written += written
            tickers_with_data += 1

        if (i + 1) % 50 == 0 or (i + 1) == len(tickers):
            print(f"  [{i+1}/{len(tickers)}] {tickers_with_data} tickers, {total_items} daily records, {total_written} written")

        if i + 1 < len(tickers):
            time.sleep(0.35)

    print()
    print(f"Done! {total_written} daily EOD records written.")
    print(f"  Tickers with data: {tickers_with_data}")
    print(f"  Date range: {from_date} to {to_date}")


if __name__ == "__main__":
    main()
