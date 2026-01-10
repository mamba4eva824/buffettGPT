#!/usr/bin/env python3
"""
Investment Report Generator CLI

Generates investment analysis reports using Claude Opus 4.5 with extended thinking,
then caches them in DynamoDB for fast retrieval by the Investment Research feature.

Usage:
  python -m investment_research.generate_report AAPL              # Generate report for single ticker
  python -m investment_research.generate_report AAPL MSFT NVDA    # Generate reports for multiple tickers
  python -m investment_research.generate_report --djia            # Generate all DJIA reports (10 test)
  python -m investment_research.generate_report --sp500           # Generate S&P 500 reports (10 test)
  python -m investment_research.generate_report --test            # Generate reports for test tickers only
  python -m investment_research.generate_report --refresh AAPL    # Force refresh existing report
  python -m investment_research.generate_report --fiscal-year 2023 AAPL  # Specific fiscal year

Environment Variables:
  INVESTMENT_REPORTS_TABLE   DynamoDB table name (default: investment-reports-dev)
  FMP_API_KEY                FMP API key for financial data (or from secrets manager)
  ANTHROPIC_API_KEY          Anthropic API key for Opus 4.5 (only for API mode)

Examples:
  # Generate single report (uses cache if exists)
  python -m investment_research.generate_report AAPL

  # Force regenerate even if cached
  python -m investment_research.generate_report --refresh AAPL

  # Generate test set (AAPL, MSFT, F, NVDA)
  python -m investment_research.generate_report --test

  # Generate all DJIA constituents
  python -m investment_research.generate_report --djia

  # Generate with specific fiscal year
  python -m investment_research.generate_report --fiscal-year 2023 MSFT
"""

import argparse
import asyncio
import sys
import os
import time

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from investment_research.index_tickers import get_index_tickers, get_test_tickers

# Delay ReportGenerator import until actually needed (requires anthropic)
ReportGenerator = None

def get_report_generator(prompt_version: float = 4.6):
    """Lazy import of ReportGenerator to avoid anthropic dependency for list commands."""
    global ReportGenerator
    if ReportGenerator is None:
        from investment_research.report_generator import ReportGenerator as RG
        ReportGenerator = RG
    return ReportGenerator(prompt_version=prompt_version)


def print_banner():
    """Print CLI banner."""
    print("=" * 60)
    print("  Investment Report Generator")
    print("  Using Claude Opus 4.5 with Extended Thinking")
    print("=" * 60)
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Generate investment analysis reports using Claude Opus 4.5',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Positional argument for ticker(s)
    parser.add_argument(
        'tickers',
        nargs='*',
        help='One or more ticker symbols (e.g., AAPL MSFT)'
    )

    # Index generation options
    parser.add_argument(
        '--djia',
        action='store_true',
        help='Generate reports for all DJIA companies (10 test)'
    )
    parser.add_argument(
        '--sp500',
        action='store_true',
        help='Generate reports for S&P 500 companies (10 test)'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Generate reports for test tickers only (AAPL, MSFT, F, NVDA)'
    )

    # Generation options
    parser.add_argument(
        '--refresh',
        action='store_true',
        help='Force refresh/regenerate existing cached reports'
    )
    parser.add_argument(
        '--fiscal-year',
        type=int,
        help='Fiscal year to analyze (default: current year)'
    )
    parser.add_argument(
        '--prompt-version',
        type=float,
        default=4.6,
        help='Prompt template version (default: 4.6). Options: 1, 2, 3, 4, 4.2, 4.3, 4.4, 4.5, 4.6'
    )

    # Utility options
    parser.add_argument(
        '--list-djia',
        action='store_true',
        help='List all DJIA tickers and exit'
    )
    parser.add_argument(
        '--list-sp500',
        action='store_true',
        help='List all S&P 500 tickers and exit'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be generated without actually generating'
    )

    args = parser.parse_args()

    # Handle list commands
    if args.list_djia:
        tickers = get_index_tickers('DJIA')
        print(f"DJIA Tickers ({len(tickers)}):")
        for ticker in tickers:
            print(f"  {ticker}")
        return

    if args.list_sp500:
        tickers = get_index_tickers('SP500')
        print(f"S&P 500 Tickers ({len(tickers)}):")
        for ticker in tickers:
            print(f"  {ticker}")
        return

    # Determine which tickers to process
    tickers_to_process = []

    if args.djia:
        tickers_to_process = get_index_tickers('DJIA')
        print_banner()
        print(f"Mode: DJIA Index ({len(tickers_to_process)} companies)")
    elif args.sp500:
        tickers_to_process = get_index_tickers('SP500')
        print_banner()
        print(f"Mode: S&P 500 ({len(tickers_to_process)} companies)")
    elif args.test:
        tickers_to_process = get_test_tickers()
        print_banner()
        print(f"Mode: Test Tickers ({len(tickers_to_process)} companies)")
    elif args.tickers:
        tickers_to_process = [t.upper() for t in args.tickers]
        print_banner()
        print(f"Mode: Custom ({len(tickers_to_process)} ticker(s))")
    else:
        parser.print_help()
        return

    # Show configuration
    print(f"Refresh: {'Yes' if args.refresh else 'No (use cache if available)'}")
    print(f"Fiscal Year: {args.fiscal_year or 'Current'}")
    print(f"Prompt Version: v{args.prompt_version}")
    print(f"Table: {os.environ.get('INVESTMENT_REPORTS_TABLE', 'investment-reports-dev')}")
    print()

    # Dry run - just show what would be processed
    if args.dry_run:
        print("DRY RUN - Would process these tickers:")
        for i, ticker in enumerate(tickers_to_process, 1):
            print(f"  {i}. {ticker}")
        print(f"\nTotal: {len(tickers_to_process)} reports")
        return

    # Confirm for large batches
    if len(tickers_to_process) > 5:
        print(f"About to generate {len(tickers_to_process)} reports.")
        print("This may take significant time and API costs.")
        try:
            response = input("Continue? (y/N): ")
            if response.lower() != 'y':
                print("Aborted.")
                return
        except EOFError:
            # Non-interactive mode - proceed
            pass

    # Run generation
    generator = get_report_generator(prompt_version=args.prompt_version)
    start_time = time.time()

    if len(tickers_to_process) == 1:
        # Single ticker
        ticker = tickers_to_process[0]
        try:
            print(f"\nGenerating report for {ticker}...")
            asyncio.run(generator.generate_report(
                ticker,
                args.fiscal_year,
                force_refresh=args.refresh
            ))
            print(f"\n✓ Report for {ticker} complete!")
        except Exception as e:
            print(f"\n✗ Failed to generate report for {ticker}: {e}")
            sys.exit(1)
    else:
        # Multiple tickers
        print(f"\nGenerating {len(tickers_to_process)} reports...\n")

        success = 0
        failed = []

        for i, ticker in enumerate(tickers_to_process, 1):
            print(f"[{i}/{len(tickers_to_process)}] {ticker}", end=" ")
            try:
                asyncio.run(generator.generate_report(
                    ticker,
                    args.fiscal_year,
                    force_refresh=args.refresh
                ))
                success += 1
            except Exception as e:
                failed.append((ticker, str(e)))
                print(f"✗ {e}")

        # Summary
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"SUMMARY")
        print(f"  Successful: {success}/{len(tickers_to_process)}")
        print(f"  Failed: {len(failed)}/{len(tickers_to_process)}")
        print(f"  Time: {elapsed:.1f} seconds ({elapsed/len(tickers_to_process):.1f}s per report)")

        if failed:
            print("\n  Failed tickers:")
            for ticker, error in failed:
                print(f"    - {ticker}: {error}")

        print("=" * 60)


if __name__ == '__main__':
    main()
