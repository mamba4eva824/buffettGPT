#!/usr/bin/env python3
"""
S&P 500 Earnings Data Fetcher

Fetches historical earnings (EPS actual vs estimated, revenue surprise)
from FMP /stable/earnings endpoint for all S&P 500 constituents.

Saves one JSON file per ticker to sp500_analysis/data/company_earnings/.

Usage:
    python fetch_sp500_earnings.py          # Full fetch (all ~500 companies)
    python fetch_sp500_earnings.py --test   # Test mode (5 companies)
    python fetch_sp500_earnings.py --resume # Skip tickers with existing files

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

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sp500_earnings")

# Output directory
DATA_DIR = Path(__file__).parent / "data"
EARNINGS_DIR = DATA_DIR / "company_earnings"

# FMP API key (cached)
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


def fetch_earnings(ticker: str, client: httpx.Client, limit: int = 20) -> list:
    """Fetch earnings history from FMP /stable/earnings endpoint."""
    url = f"{FMP_BASE_URL}/stable/earnings"
    params = {
        "symbol": ticker,
        "limit": limit,
        "apikey": get_api_key(),
    }

    try:
        resp = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            log.warning(f"  {ticker}: Rate limited (429), waiting 15s...")
            time.sleep(15)
            # Retry once
            resp = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        log.error(f"  {ticker}: HTTP {e.response.status_code}")
        return []
    except Exception as e:
        log.error(f"  {ticker}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Fetch S&P 500 earnings data from FMP")
    parser.add_argument("--test", action="store_true", help="Test mode: 5 companies only")
    parser.add_argument("--resume", action="store_true", help="Skip tickers with existing files")
    parser.add_argument("--tickers", nargs="+", help="Specific tickers to fetch")
    args = parser.parse_args()

    # Select tickers
    if args.tickers:
        tickers = args.tickers
    elif args.test:
        tickers = SP500_SYMBOLS[:5]
    else:
        tickers = SP500_SYMBOLS

    # Create output directory
    EARNINGS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Fetching earnings for {len(tickers)} tickers")
    log.info(f"Output: {EARNINGS_DIR}")
    if args.resume:
        log.info("Resume mode: skipping existing files")

    stats = {"fetched": 0, "skipped": 0, "empty": 0, "errors": 0}
    start = time.monotonic()

    with httpx.Client() as client:
        for i, ticker in enumerate(tickers):
            # Resume mode: skip existing
            out_path = EARNINGS_DIR / f"{ticker}.json"
            if args.resume and out_path.exists():
                stats["skipped"] += 1
                continue

            # Rate limiting: pause every BATCH_SIZE calls
            if stats["fetched"] > 0 and stats["fetched"] % BATCH_SIZE == 0:
                log.info(f"  Batch pause ({BATCH_PAUSE_SECONDS}s)...")
                time.sleep(BATCH_PAUSE_SECONDS)

            # Fetch
            data = fetch_earnings(ticker, client)

            if data:
                with open(out_path, "w") as f:
                    json.dump(data, f, indent=2)
                stats["fetched"] += 1
            else:
                # Save empty list so resume mode skips it
                with open(out_path, "w") as f:
                    json.dump([], f)
                stats["empty"] += 1

            # Progress
            if (i + 1) % 50 == 0:
                elapsed = time.monotonic() - start
                rate = (stats["fetched"] + stats["empty"]) / elapsed * 60
                log.info(f"  Progress: {i + 1}/{len(tickers)} | "
                         f"fetched={stats['fetched']} empty={stats['empty']} "
                         f"skipped={stats['skipped']} | {rate:.0f} calls/min")

    elapsed = time.monotonic() - start
    log.info(f"Done in {elapsed:.1f}s: {json.dumps(stats)}")


if __name__ == "__main__":
    main()
