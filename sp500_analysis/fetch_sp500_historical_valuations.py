#!/usr/bin/env python3
"""
S&P 500 Historical Valuation Data Fetcher

Fetches annual key-metrics from FMP /stable/key-metrics for all S&P 500 tickers.
Returns 5-10 years of annual valuation data: P/E, EV/EBITDA, EV/Sales, market cap.

Each record has a 'date' matching the fiscal year-end quarter, which allows
mapping to the existing quarterly items in metrics-history DynamoDB.

Saves one JSON file per ticker to sp500_analysis/data/company_historical_valuations/.

API budget: 498 calls at 300/min = ~1.7 minutes
"""

import argparse
import json
import logging
import os
import time
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
log = logging.getLogger("sp500_hist_valuations")

DATA_DIR = Path(__file__).parent / "data"
HIST_VALUATIONS_DIR = DATA_DIR / "company_historical_valuations"

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


def fetch_historical_valuations(ticker: str, client: httpx.Client, limit: int = 10) -> list:
    """Fetch annual key metrics from FMP (quarterly not available on current plan)."""
    url = f"{FMP_BASE_URL}/stable/key-metrics"
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
            resp = client.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        log.error(f"  {ticker}: HTTP {e.response.status_code}")
        return []
    except Exception as e:
        log.error(f"  {ticker}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Fetch S&P 500 historical valuation data")
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

    HIST_VALUATIONS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(f"Fetching historical valuations for {len(tickers)} tickers")

    stats = {"fetched": 0, "skipped": 0, "empty": 0, "errors": 0}
    start = time.monotonic()

    with httpx.Client() as client:
        for i, ticker in enumerate(tickers):
            out_path = HIST_VALUATIONS_DIR / f"{ticker}.json"
            if args.resume and out_path.exists():
                stats["skipped"] += 1
                continue

            if stats["fetched"] > 0 and stats["fetched"] % BATCH_SIZE == 0:
                log.info(f"  Batch pause ({BATCH_PAUSE_SECONDS}s)...")
                time.sleep(BATCH_PAUSE_SECONDS)

            data = fetch_historical_valuations(ticker, client)

            if data:
                with open(out_path, "w") as f:
                    json.dump(data, f, indent=2)
                stats["fetched"] += 1
            else:
                with open(out_path, "w") as f:
                    json.dump([], f)
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
