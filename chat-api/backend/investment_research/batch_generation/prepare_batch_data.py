#!/usr/bin/env python3
"""
Pre-fetch financial data for batch report generation.

This script calls the FMP API endpoints to gather all financial data needed
for report generation, then saves it to a JSON file for Claude sessions.

FMP Endpoints called per ticker (via report_generator.prepare_data):
- /stable/balance-sheet-statement (20 quarters)
- /stable/income-statement (20 quarters)
- /stable/cash-flow-statement (20 quarters)
- /stable/key-metrics (5 years historical)
- /stable/key-metrics-ttm (current TTM)
- /stable/ratios-ttm (current TTM ratios)
- /stable/analyst-estimates (forward estimates)

Usage:
    python -m investment_research.batch_generation.prepare_batch_data
    python -m investment_research.batch_generation.prepare_batch_data --index sp100
    python -m investment_research.batch_generation.prepare_batch_data --index sp100 --delay 0.2
    python -m investment_research.batch_generation.prepare_batch_data --output custom.json
    python -m investment_research.batch_generation.prepare_batch_data --tickers AAPL,MSFT,NVDA
"""

import argparse
import json
import sys
import os
import time
from datetime import datetime
from typing import List, Optional

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from investment_research.report_generator import ReportGenerator
from investment_research.index_tickers import get_index_tickers
from src.utils.feature_extractor import decimal_to_float


def prepare_all_data(
    output_file: str = None,
    tickers: Optional[List[str]] = None,
    prompt_version: float = 5.1,
    index: str = "djia",
    delay: float = 0.0
) -> dict:
    """
    Fetch FMP data for all specified tickers and save to JSON.

    Args:
        output_file: Path to output JSON file
        tickers: List of tickers to process (defaults to DJIA_TICKERS)
        prompt_version: Prompt version to use for ReportGenerator

    Returns:
        Dict mapping ticker -> prepared data
    """
    if tickers is None:
        tickers = get_index_tickers(index)

    # Auto-generate output filename from index if not specified
    if output_file is None:
        output_file = f"{index.lower()}_{len(tickers)}_batch_data.json"

    generator = ReportGenerator(prompt_version=prompt_version)
    all_data = {}

    print("=" * 60)
    print(f"  {index.upper()} Batch Data Preparation")
    print("=" * 60)
    print()
    print(f"Tickers to process: {len(tickers)}")
    print(f"FMP endpoints per ticker: 7-8 API calls")
    print(f"Total estimated API calls: ~{len(tickers) * 8}")
    print(f"Output file: {output_file}")
    print("-" * 60)

    start_time = datetime.now()

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:2}/{len(tickers)}] {ticker}...", end=" ", flush=True)
        try:
            data = generator.prepare_data(ticker)
            all_data[ticker] = {
                "metrics_context": data["metrics_context"],
                "features": data.get("features", {}),
                "raw_financials": decimal_to_float(data.get("raw_financials", {})),
                "currency_info": decimal_to_float(data.get("currency_info", {})),
                "prepared_at": datetime.now().isoformat(),
                "prompt_version": prompt_version
            }
            print("✓")
        except Exception as e:
            print(f"✗ {e}")
            all_data[ticker] = {"error": str(e), "prepared_at": datetime.now().isoformat()}

        # Rate limit delay between tickers
        if delay > 0 and i < len(tickers):
            time.sleep(delay)

    # Save to JSON
    with open(output_file, "w") as f:
        json.dump(all_data, f, indent=2, default=str)

    # Summary
    elapsed = (datetime.now() - start_time).total_seconds()
    successful = sum(1 for v in all_data.values() if "error" not in v)
    failed = len(tickers) - successful

    print("-" * 60)
    print(f"Complete: {successful}/{len(tickers)} tickers")
    if failed > 0:
        print(f"Failed:   {failed} tickers")
        for ticker, data in all_data.items():
            if "error" in data:
                print(f"  - {ticker}: {data['error']}")
    if len(tickers) > 0:
        print(f"Time:     {elapsed:.1f} seconds ({elapsed/len(tickers):.1f}s per ticker)")
    else:
        print(f"Time:     {elapsed:.1f} seconds")
    print(f"Output:   {output_file}")
    print("=" * 60)

    return all_data


def main():
    parser = argparse.ArgumentParser(
        description="Pre-fetch FMP data for batch report generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Fetch data for all 30 DJIA companies
    python -m investment_research.batch_generation.prepare_batch_data

    # Fetch data for S&P 100 companies
    python -m investment_research.batch_generation.prepare_batch_data --index sp100

    # S&P 100 with rate limiting delay
    python -m investment_research.batch_generation.prepare_batch_data --index sp100 --delay 0.2

    # Custom output file
    python -m investment_research.batch_generation.prepare_batch_data --output my_data.json

    # Specific tickers only
    python -m investment_research.batch_generation.prepare_batch_data --tickers AAPL,MSFT,NVDA
        """
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path (default: auto-generated from index)"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all tickers in selected index)"
    )
    parser.add_argument(
        "--prompt-version",
        type=float,
        default=5.1,
        help="Prompt version for ReportGenerator (default: 5.1)"
    )
    parser.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use for tickers (default: djia). Options: djia, sp100, sp500"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between tickers for rate limiting (default: 0.0)"
    )

    args = parser.parse_args()

    # Parse tickers if provided
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    prepare_all_data(
        output_file=args.output,
        tickers=tickers,
        prompt_version=args.prompt_version,
        index=args.index,
        delay=args.delay
    )


if __name__ == "__main__":
    main()
