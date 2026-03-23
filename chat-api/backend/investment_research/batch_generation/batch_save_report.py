#!/usr/bin/env python3
"""
Save a generated report to DynamoDB with proper metrics caching.

Standalone CLI helper for the batch workflow. Reads the batch JSON file
to extract raw_financials and currency_info for the given ticker, then
calls save_report_sections() to persist the report and cache metrics.

Usage:
    python3 -m investment_research.batch_generation.batch_save_report \
        --ticker AAPL --data-file batch.json --report /tmp/AAPL_report.md

    python3 -m investment_research.batch_generation.batch_save_report \
        --ticker MSFT --data-file sp100_batch.json --report /tmp/MSFT_report.md \
        --prompt-version 5.2 --fiscal-year 2027
"""

import argparse
import json
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from investment_research.report_generator import ReportGenerator


def main():
    parser = argparse.ArgumentParser(
        description="Save a generated report to DynamoDB with metrics caching"
    )
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g. AAPL)")
    parser.add_argument("--data-file", required=True, help="Path to batch JSON data file")
    parser.add_argument("--report", required=True, help="Path to generated report markdown file")
    parser.add_argument("--prompt-version", type=float, default=5.1, help="Prompt version (default: 5.1)")
    parser.add_argument("--fiscal-year", type=int, default=2026, help="Fiscal year (default: 2026)")

    args = parser.parse_args()
    ticker = args.ticker.upper()

    # Load batch data
    with open(args.data_file, "r") as f:
        batch_data = json.load(f)

    # Load report content
    with open(args.report, "r") as f:
        report_content = f.read()

    # Extract financials for this ticker
    ticker_data = batch_data.get(ticker, {})
    raw_financials = None
    currency_info = None

    if "error" not in ticker_data:
        raw_financials = ticker_data.get("raw_financials")
        currency_info = ticker_data.get("currency_info")

    # Save report sections
    generator = ReportGenerator(prompt_version=args.prompt_version)
    try:
        generator.save_report_sections(
            ticker=ticker,
            fiscal_year=args.fiscal_year,
            report_content=report_content,
            ratings=None,
            raw_financials=raw_financials,
            currency_info=currency_info
        )
        print(f"Successfully saved report for {ticker} (FY{args.fiscal_year})")
    except Exception as e:
        print(f"Failed to save report for {ticker}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
