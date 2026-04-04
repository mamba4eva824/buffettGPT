#!/usr/bin/env python3
"""
Local backfill script for stock-data-4h table.

Fetches 4-hour candle data from FMP for all S&P 500 tickers
and writes to DynamoDB. Designed to run locally with AWS credentials.

Usage:
    python scripts/backfill_4h_prices.py                      # Latest trading day
    python scripts/backfill_4h_prices.py --date 2026-04-02    # Specific date
    python scripts/backfill_4h_prices.py --force               # Overwrite existing
    python scripts/backfill_4h_prices.py --tickers AAPL MSFT   # Specific tickers only
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
        api_key = get_fmp_api_key()
        url = f"https://financialmodelingprep.com/api/v3/sp500_constituent?apikey={api_key}"
        resp = http.request("GET", url)
        data = json.loads(resp.data.decode("utf-8"))
        return sorted({item["symbol"] for item in data})


def fetch_4h_candles(ticker, trade_date):
    api_key = get_fmp_api_key()
    fmp_ticker = ticker.replace('.', '-')
    url = f"{FMP_BASE_URL}/historical-chart/4hour?symbol={fmp_ticker}&apikey={api_key}"
    try:
        resp = http.request("GET", url, timeout=15.0)
        if resp.status == 429:
            print(f"  Rate limited on {ticker}, waiting 2s...")
            time.sleep(2)
            resp = http.request("GET", url, timeout=15.0)
        if resp.status != 200:
            return []
        data = json.loads(resp.data.decode("utf-8"))
        if not isinstance(data, list):
            return []
        return [c for c in data if c.get("date", "").startswith(trade_date)]
    except Exception as e:
        print(f"  Error fetching {ticker}: {e}")
        return []


def to_decimal(value):
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def build_items(ticker, candles, trade_date):
    items = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for c in candles:
        dt = c.get("date", "")
        if not dt:
            continue
        items.append({
            "PK": f"TICKER#{ticker}",
            "SK": f"DATETIME#{dt}",
            "GSI_PK": f"DATE#{trade_date}",
            "GSI_SK": f"TICKER#{ticker}",
            "symbol": ticker,
            "date": trade_date,
            "datetime": dt,
            "open": to_decimal(c.get("open")),
            "high": to_decimal(c.get("high")),
            "low": to_decimal(c.get("low")),
            "close": to_decimal(c.get("close")),
            "volume": int(c.get("volume") or 0),
            "ingested_at": now_iso,
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


def already_ingested(trade_date):
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq('TICKER#AAPL')
                & boto3.dynamodb.conditions.Key('SK').begins_with(f'DATETIME#{trade_date}'),
            Limit=1,
        )
        return len(response.get("Items", [])) > 0
    except Exception:
        return False


def compute_trade_date():
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    wd = yesterday.weekday()
    if wd == 6:
        yesterday -= timedelta(days=2)
    elif wd == 5:
        yesterday -= timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="Backfill stock-data-4h table")
    parser.add_argument("--date", help="Trade date YYYY-MM-DD (default: last trading day)")
    parser.add_argument("--force", action="store_true", help="Overwrite existing data")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers (default: all S&P 500)")
    args = parser.parse_args()

    trade_date = args.date or compute_trade_date()
    print(f"Table:      {TABLE_NAME}")
    print(f"Trade date: {trade_date}")
    print(f"Force:      {args.force}")
    print()

    if not args.force and already_ingested(trade_date):
        print(f"Data for {trade_date} already exists. Use --force to overwrite.")
        return

    tickers = sorted(args.tickers) if args.tickers else get_sp500_tickers()
    print(f"Processing {len(tickers)} tickers...")
    print()

    all_items = []
    with_data = 0
    empty = 0

    for i, ticker in enumerate(tickers):
        candles = fetch_4h_candles(ticker, trade_date)
        if candles:
            items = build_items(ticker, candles, trade_date)
            all_items.extend(items)
            with_data += 1
        else:
            empty += 1

        if (i + 1) % 50 == 0 or (i + 1) == len(tickers):
            print(f"  [{i+1}/{len(tickers)}] {with_data} with data, {empty} empty, {len(all_items)} candles")

        if i + 1 < len(tickers):
            time.sleep(0.5)

    print()
    if not all_items:
        print(f"No candles returned for {trade_date} — possible market holiday.")
        return

    print(f"Writing {len(all_items)} items to DynamoDB...")
    written = batch_write(all_items)
    print(f"Done! {written} records written for {trade_date}.")
    print(f"  Tickers with data: {with_data}")
    print(f"  Tickers empty:     {empty}")


if __name__ == "__main__":
    main()
