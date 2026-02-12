#!/usr/bin/env python3
"""
S&P 500 Data Fetcher — Silverblatt-style Market Analysis

Fetches all raw data from FMP API for a Howard Silverblatt-style S&P 500 analysis.
Uses per-company endpoints (Starter tier compatible) since bulk/index endpoints
require Enterprise tier.

Usage:
    python fetch_sp500_data.py          # Full fetch (all ~500 companies)
    python fetch_sp500_data.py --test   # Test mode (verify endpoints + 5 companies)
    python fetch_sp500_data.py --resume # Resume interrupted run (skip existing files)

Data fetched per company:
    - Income statement (20 quarters)    → earnings, EPS, shares outstanding
    - Cash flow statement (20 quarters) → buybacks, dividends paid, SBC
    - Balance sheet (20 quarters)       → shares outstanding, book value
    - Company profile                   → sector, market cap, dividend yield
    - Dividend history                  → per-share dividend amounts, dates

Index-level:
    - SPY ETF historical prices (proxy for S&P 500 index)

API call budget:
    ~2,500 calls (5 endpoints × 500 companies + SPY)
    At 300 calls/min = ~9 minutes
"""

import os
import json
import time
import logging
import argparse
from datetime import datetime, timezone

import httpx
import boto3

from config import (
    FMP_BASE_URL,
    FMP_SECRET_NAME,
    BATCH_SIZE,
    BATCH_PAUSE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    QUARTERLY_LIMIT,
    ENDPOINTS,
    STATEMENT_TYPES,
    DATA_DIR,
    OUTPUT_PATHS,
    SP500_SYMBOLS,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sp500_fetch")

# ---------------------------------------------------------------------------
# Manifest + call counter
# ---------------------------------------------------------------------------
manifest: list[dict] = []
call_count = 0
call_window_start = time.monotonic()


def record(name: str, endpoint: str, status: int | str, file_path: str | None, note: str = ""):
    manifest.append({
        "name": name,
        "endpoint": endpoint,
        "status": status,
        "file": file_path,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------
def throttle():
    """Pause after every BATCH_SIZE calls to stay under 300/min."""
    global call_count, call_window_start

    call_count += 1

    if call_count % BATCH_SIZE == 0:
        elapsed = time.monotonic() - call_window_start
        if elapsed < BATCH_PAUSE_SECONDS:
            sleep_time = BATCH_PAUSE_SECONDS - elapsed
            log.info(f"  [throttle] {sleep_time:.1f}s pause ({call_count} calls so far)")
            time.sleep(sleep_time)
        call_window_start = time.monotonic()


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------
def get_api_key() -> str:
    key = os.environ.get("FMP_API_KEY")
    if key:
        log.info("Using FMP API key from environment variable")
        return key

    log.info(f"Fetching FMP API key from Secrets Manager ({FMP_SECRET_NAME})")
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response["SecretString"])
        return secret["FMP_API_KEY"]
    except Exception as e:
        log.error(f"Failed to get API key: {e}")
        raise SystemExit("No FMP API key. Set FMP_API_KEY env var or configure AWS credentials.")


# ---------------------------------------------------------------------------
# HTTP client + fetch helper
# ---------------------------------------------------------------------------
def make_client() -> httpx.Client:
    return httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=True)


def fetch_json(
    client: httpx.Client,
    api_key: str,
    name: str,
    endpoint: str,
    params: dict | None = None,
    output_path: str | None = None,
    quiet: bool = False,
) -> dict | list | None:
    """GET from FMP, save to disk, record in manifest. Returns parsed JSON or None."""
    throttle()

    url = f"{FMP_BASE_URL}{endpoint}"
    req_params = {"apikey": api_key}
    if params:
        req_params.update(params)

    if not quiet:
        log.info(f"  Fetching: {name}")

    try:
        resp = client.get(url, params=req_params)

        if resp.status_code != 200:
            if not quiet:
                log.warning(f"  {name}: HTTP {resp.status_code}")
            record(name, endpoint, resp.status_code, output_path, note=resp.text[:200])
            return None

        data = resp.json()

        if isinstance(data, dict) and "Error Message" in data:
            if not quiet:
                log.warning(f"  {name}: FMP error — {data['Error Message'][:100]}")
            record(name, endpoint, "fmp_error", output_path, note=data["Error Message"][:200])
            return None

        if output_path:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(data, f)
            if not quiet:
                size_kb = os.path.getsize(output_path) / 1024
                count = len(data) if isinstance(data, list) else "obj"
                log.info(f"    -> {count} records, {size_kb:.1f} KB")

        record(name, endpoint, 200, output_path)
        return data

    except httpx.TimeoutException:
        log.error(f"  {name}: TIMEOUT")
        record(name, endpoint, "timeout", output_path)
        return None
    except Exception as e:
        log.error(f"  {name}: ERROR — {e}")
        record(name, endpoint, "error", output_path, note=str(e)[:200])
        return None


# ---------------------------------------------------------------------------
# Phase 1: Index-level data
# ---------------------------------------------------------------------------
def fetch_spy_prices(client: httpx.Client, api_key: str, resume: bool = False):
    output_path = OUTPUT_PATHS["spy_historical_prices"]
    if resume and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
        log.info("  SPY prices: skipping (already exists)")
        record("SPY prices", "", "skipped", output_path, "resume")
        return
    fetch_json(
        client, api_key,
        name="SPY Historical Prices (S&P 500 proxy)",
        endpoint=ENDPOINTS["spy_historical_prices"],
        params={"symbol": "SPY"},
        output_path=output_path,
    )


def save_constituents_file():
    """Save the hardcoded S&P 500 list to data/ for downstream scripts."""
    output_path = OUTPUT_PATHS["constituents"]
    data = [{"symbol": s} for s in SP500_SYMBOLS]
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)
    log.info(f"  Saved {len(data)} constituents to {output_path}")
    record("constituents", "hardcoded", 200, output_path, f"{len(data)} symbols")


# ---------------------------------------------------------------------------
# Phase 2: Per-company data
# ---------------------------------------------------------------------------
def fetch_all_company_data(
    client: httpx.Client,
    api_key: str,
    symbols: list[str],
    resume: bool = True,
):
    """
    For each company, fetch:
      - 3 financial statements (income, cashflow, balance sheet) → company_financials/{SYM}.json
      - Company profile → company_profiles/{SYM}.json
      - Dividend history → company_dividends/{SYM}.json

    That's 5 API calls per company.
    """
    total = len(symbols)
    fin_dir = OUTPUT_PATHS["company_financials_dir"]
    prof_dir = OUTPUT_PATHS["company_profiles_dir"]
    div_dir = OUTPUT_PATHS["company_dividends_dir"]

    os.makedirs(fin_dir, exist_ok=True)
    os.makedirs(prof_dir, exist_ok=True)
    os.makedirs(div_dir, exist_ok=True)

    total_api_calls = total * 5
    log.info(f"\n{'='*60}")
    log.info(f"Fetching data for {total} S&P 500 companies")
    log.info(f"5 endpoints × {total} = ~{total_api_calls} API calls")
    log.info(f"Estimated time: ~{total_api_calls / 250:.0f} minutes")
    log.info(f"{'='*60}\n")

    stats = {"ok": 0, "skipped": 0, "partial": 0}
    start_time = time.monotonic()

    for i, symbol in enumerate(symbols):
        fin_path = os.path.join(fin_dir, f"{symbol}.json")
        prof_path = os.path.join(prof_dir, f"{symbol}.json")
        div_path = os.path.join(div_dir, f"{symbol}.json")

        # Skip if ALL 3 files already exist (resume mode)
        if resume and all(
            os.path.exists(p) and os.path.getsize(p) > 50
            for p in [fin_path, prof_path, div_path]
        ):
            stats["skipped"] += 1
            continue

        all_ok = True

        # --- Financial statements (combined into 1 file) ---
        if not (resume and os.path.exists(fin_path) and os.path.getsize(fin_path) > 100):
            company_fin = {"symbol": symbol, "fetched_at": datetime.now(timezone.utc).isoformat()}
            for stmt_key, stmt_label in STATEMENT_TYPES:
                result = fetch_json(
                    client, api_key,
                    name=f"{symbol} {stmt_label}",
                    endpoint=ENDPOINTS[stmt_key],
                    params={"symbol": symbol, "period": "quarterly", "limit": QUARTERLY_LIMIT},
                    quiet=True,
                )
                company_fin[stmt_label] = result if result is not None else []
                if result is None:
                    all_ok = False

            with open(fin_path, "w") as f:
                json.dump(company_fin, f)

        # --- Profile ---
        if not (resume and os.path.exists(prof_path) and os.path.getsize(prof_path) > 50):
            result = fetch_json(
                client, api_key,
                name=f"{symbol} profile",
                endpoint=ENDPOINTS["profile"],
                params={"symbol": symbol},
                output_path=prof_path,
                quiet=True,
            )
            if result is None:
                all_ok = False

        # --- Dividends ---
        if not (resume and os.path.exists(div_path) and os.path.getsize(div_path) > 10):
            result = fetch_json(
                client, api_key,
                name=f"{symbol} dividends",
                endpoint=ENDPOINTS["dividends"],
                params={"symbol": symbol},
                output_path=div_path,
                quiet=True,
            )
            if result is None:
                all_ok = False

        if all_ok:
            stats["ok"] += 1
        else:
            stats["partial"] += 1

        # Progress every 25 companies
        if (i + 1) % 25 == 0 or i == total - 1:
            elapsed = time.monotonic() - start_time
            rate = call_count / (elapsed / 60) if elapsed > 0 else 0
            remaining = total - (i + 1) - stats["skipped"]
            eta_min = (remaining * 5 / rate) if rate > 0 else 0
            log.info(
                f"  [{i+1}/{total}] "
                f"{stats['ok']} OK, {stats['skipped']} skip, {stats['partial']} partial | "
                f"{call_count} calls ({rate:.0f}/min) | "
                f"ETA: {eta_min:.1f}min"
            )

    log.info(f"\nDone: {stats['ok']} OK, {stats['skipped']} skipped, {stats['partial']} partial")


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def save_manifest():
    manifest_path = OUTPUT_PATHS["manifest"]
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    successes = sum(1 for m in manifest if m["status"] == 200)
    skipped = sum(1 for m in manifest if m["status"] == "skipped")
    failures = sum(1 for m in manifest if m["status"] not in (200, "skipped"))

    manifest_data = {
        "fetch_started": manifest[0]["timestamp"] if manifest else None,
        "fetch_completed": datetime.now(timezone.utc).isoformat(),
        "total_entries": len(manifest),
        "api_calls_made": call_count,
        "successes": successes,
        "skipped": skipped,
        "failures": failures,
        "entries": manifest,
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f, indent=2)
    log.info(f"Manifest written: {manifest_path}")


def run_test(client: httpx.Client, api_key: str):
    """Verify all endpoint types work, fetch 5 sample companies."""
    log.info("=" * 60)
    log.info("TEST MODE — verifying endpoints with 5 companies")
    log.info("=" * 60)

    # Index data
    save_constituents_file()
    fetch_spy_prices(client, api_key)

    # 5 sample companies
    test_symbols = SP500_SYMBOLS[:5]
    log.info(f"\nTest companies: {test_symbols}")
    fetch_all_company_data(client, api_key, test_symbols, resume=False)

    # Print sample field names
    sample_path = os.path.join(OUTPUT_PATHS["company_financials_dir"], f"{test_symbols[0]}.json")
    if os.path.exists(sample_path):
        with open(sample_path) as f:
            sample = json.load(f)
        for stmt_label in ["income", "cashflow", "balance"]:
            records = sample.get(stmt_label, [])
            if records:
                fields = list(records[0].keys())
                log.info(f"\n  {stmt_label} fields ({len(fields)}):")
                log.info(f"    {fields}")
                if stmt_label == "cashflow":
                    relevant = [f for f in fields if any(k in f.lower() for k in ["repurchas", "buyback", "stock", "dividend", "share"])]
                    log.info(f"    Buyback/dividend fields: {relevant}")
                if stmt_label == "income":
                    relevant = [f for f in fields if any(k in f.lower() for k in ["eps", "share", "weight"])]
                    log.info(f"    EPS/share fields: {relevant}")
                if stmt_label == "balance":
                    relevant = [f for f in fields if any(k in f.lower() for k in ["share", "stock", "equity", "outstanding"])]
                    log.info(f"    Share/equity fields: {relevant}")

    # Print sample profile
    prof_path = os.path.join(OUTPUT_PATHS["company_profiles_dir"], f"{test_symbols[0]}.json")
    if os.path.exists(prof_path):
        with open(prof_path) as f:
            prof = json.load(f)
        if isinstance(prof, list) and prof:
            log.info(f"\n  Profile fields: {list(prof[0].keys())}")

    save_manifest()
    _print_summary()


def run_all(client: httpx.Client, api_key: str, resume: bool = False):
    """Full fetch — all S&P 500 data."""
    log.info("=" * 60)
    log.info(f"FULL FETCH — {len(SP500_SYMBOLS)} S&P 500 companies")
    log.info("=" * 60)

    # Phase 1: Index-level
    log.info("\n--- Phase 1: Index-level data ---")
    save_constituents_file()
    fetch_spy_prices(client, api_key, resume=resume)

    # Phase 2: Per-company
    log.info("\n--- Phase 2: Company data ---")
    fetch_all_company_data(client, api_key, SP500_SYMBOLS, resume=resume)

    save_manifest()
    _print_summary()


def _print_summary():
    successes = sum(1 for m in manifest if m["status"] == 200)
    skipped = sum(1 for m in manifest if m["status"] == "skipped")
    failures = sum(1 for m in manifest if m["status"] not in (200, "skipped"))

    log.info("\n" + "=" * 60)
    log.info("FETCH COMPLETE")
    log.info(f"  Manifest entries: {len(manifest)}")
    log.info(f"  API calls made:  {call_count}")
    log.info(f"  Successes:       {successes}")
    log.info(f"  Skipped:         {skipped}")
    log.info(f"  Failures:        {failures}")
    log.info("=" * 60)

    if failures > 0:
        log.warning("\nFailed fetches (first 20):")
        fail_entries = [m for m in manifest if m["status"] not in (200, "skipped")]
        for m in fail_entries[:20]:
            log.warning(f"  {m['name']}: {m['status']} — {m.get('note', '')[:80]}")
        if len(fail_entries) > 20:
            log.warning(f"  ... and {len(fail_entries) - 20} more")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Fetch S&P 500 data from FMP API")
    parser.add_argument("--test", action="store_true", help="Test mode: verify endpoints + 5 sample companies")
    parser.add_argument("--resume", action="store_true", help="Resume: skip already-fetched files")
    args = parser.parse_args()

    # Ensure output directories
    for key, path in OUTPUT_PATHS.items():
        if key.endswith("_dir"):
            os.makedirs(path, exist_ok=True)

    api_key = get_api_key()
    client = make_client()

    try:
        if args.test:
            run_test(client, api_key)
        else:
            run_all(client, api_key, resume=args.resume)
    finally:
        client.close()


if __name__ == "__main__":
    main()
