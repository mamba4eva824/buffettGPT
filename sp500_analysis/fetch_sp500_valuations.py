#!/usr/bin/env python3
"""
S&P 500 Valuation Data Fetcher

Fetches TTM (trailing twelve months) key metrics from FMP /stable/key-metrics-ttm
for all S&P 500 constituents. Returns current valuation multiples:
P/E, P/S, EV/EBITDA, EV/Sales, EV/FCF, market cap, etc.

Saves one JSON file per ticker to sp500_analysis/data/company_valuations/.

Usage:
    python fetch_sp500_valuations.py          # Full fetch
    python fetch_sp500_valuations.py --test   # 5 companies only
    python fetch_sp500_valuations.py --resume # Skip existing files

API budget: 498 calls at 300/min = ~1.7 minutes
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx

from config import (
    FMP_BASE_URL,
    FMP_SECRET_NAME,
    SP500_SYMBOLS,
    BATCH_SIZE,
    BATCH_PAUSE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sp500_valuations")

DATA_DIR = Path(__file__).parent / "data"
VALUATIONS_DIR = DATA_DIR / "company_valuations"

_api_key = None


def get_api_key() -> str:
    global _api_key
    if _api_key:
        return _api_key
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=FMP_SECRET_NAME)
    secret = json.loads(resp["SecretString"])
    _api_key = secret["FMP_API_KEY"]
    return _api_key


def fetch_valuation(ticker: str, client: httpx.Client) -> dict:
    """Fetch TTM key metrics from FMP."""
    url = f"{FMP_BASE_URL}/stable/key-metrics-ttm"
    params = {
        "symbol": ticker,
        "apikey": get_api_key(),
    }

    try:
        resp = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        # TTM returns a list with one item
        if isinstance(data, list) and data:
            return data[0]
        return data if isinstance(data, dict) else {}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            log.warning(f"  {ticker}: Rate limited (429), waiting 15s...")
            time.sleep(15)
            resp = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            return data[0] if isinstance(data, list) and data else {}
        log.error(f"  {ticker}: HTTP {e.response.status_code}")
        return {}
    except Exception as e:
        log.error(f"  {ticker}: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Fetch S&P 500 valuation data from FMP")
    parser.add_argument("--test", action="store_true", help="Test mode: 5 companies only")
    parser.add_argument("--resume", action="store_true", help="Skip tickers with existing files")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to fetch")
    args = parser.parse_args()

    if args.tickers:
        tickers = args.tickers
    elif args.test:
        tickers = SP500_SYMBOLS[:5]
    else:
        tickers = SP500_SYMBOLS

    VALUATIONS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Fetching TTM valuations for {len(tickers)} tickers")
    log.info(f"Output: {VALUATIONS_DIR}")

    stats = {"fetched": 0, "skipped": 0, "empty": 0, "errors": 0}
    start = time.monotonic()

    with httpx.Client() as client:
        for i, ticker in enumerate(tickers):
            out_path = VALUATIONS_DIR / f"{ticker}.json"
            if args.resume and out_path.exists():
                stats["skipped"] += 1
                continue

            if stats["fetched"] > 0 and stats["fetched"] % BATCH_SIZE == 0:
                log.info(f"  Batch pause ({BATCH_PAUSE_SECONDS}s)...")
                time.sleep(BATCH_PAUSE_SECONDS)

            data = fetch_valuation(ticker, client)

            if data and data.get("marketCap"):
                with open(out_path, "w") as f:
                    json.dump(data, f, indent=2)
                stats["fetched"] += 1
            else:
                with open(out_path, "w") as f:
                    json.dump({}, f)
                stats["empty"] += 1

            if (i + 1) % 50 == 0:
                elapsed = time.monotonic() - start
                rate = (stats["fetched"] + stats["empty"]) / elapsed * 60
                log.info(f"  Progress: {i + 1}/{len(tickers)} | "
                         f"fetched={stats['fetched']} empty={stats['empty']} | {rate:.0f} calls/min")

    elapsed = time.monotonic() - start
    log.info(f"Done in {elapsed:.1f}s: {json.dumps(stats)}")


if __name__ == "__main__":
    main()
