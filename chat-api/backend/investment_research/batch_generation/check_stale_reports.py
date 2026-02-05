#!/usr/bin/env python3
"""
Check which DJIA reports need refresh based on new earnings.

Adapted from earnings_tracker.py for batch generation workflow.
Uses the FMP /stable/earnings-calendar endpoint to check if new
earnings have been released since the reports were generated.

Usage:
    python -m investment_research.batch_generation.check_stale_reports
    python -m investment_research.batch_generation.check_stale_reports --tickers-only
    python -m investment_research.batch_generation.check_stale_reports --env prod
"""

import argparse
import sys
import os
from typing import List, Optional

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from investment_research.earnings_tracker import EarningsTracker
from investment_research.index_tickers import DJIA_TICKERS


def check_djia_staleness(
    tickers_only: bool = False,
    environment: str = "dev",
    tickers: Optional[List[str]] = None
) -> List[str]:
    """
    Check staleness for all DJIA tickers.

    Args:
        tickers_only: If True, output only ticker symbols (for piping)
        environment: Environment name (dev, staging, prod)
        tickers: List of tickers to check (defaults to DJIA_TICKERS)

    Returns:
        List of stale ticker symbols
    """
    if tickers is None:
        tickers = DJIA_TICKERS

    tracker = EarningsTracker(environment=environment)

    stale = []
    fresh = []
    no_report = []

    if not tickers_only:
        print("=" * 60)
        print("  DJIA Report Staleness Check")
        print("=" * 60)
        print()
        print(f"Checking {len(tickers)} tickers...")
        print(f"Environment: {environment}")
        print("-" * 60)

    for ticker in tickers:
        result = tracker.check_needs_refresh(ticker)

        if result['reason'] == 'no_report_exists':
            no_report.append(ticker)
            if not tickers_only:
                print(f"  ? {ticker}: No report exists")
        elif result['needs_refresh']:
            stale.append(result)
            if not tickers_only:
                reason = result['reason']
                stored = result.get('last_earnings_stored', 'none')
                current = result.get('current_latest_earnings', 'unknown')
                print(f"  ✗ {ticker}: STALE - {reason}")
                print(f"      Stored earnings: {stored} → Current: {current}")
        else:
            fresh.append(result)
            if not tickers_only:
                print(f"  ✓ {ticker}: Fresh")

    if tickers_only:
        # Output just ticker symbols for piping to other commands
        for r in stale:
            print(r['ticker'])
        for ticker in no_report:
            print(ticker)
    else:
        print("-" * 60)
        print(f"Fresh:      {len(fresh)}/{len(tickers)}")
        print(f"Stale:      {len(stale)}/{len(tickers)}")
        print(f"No report:  {len(no_report)}/{len(tickers)}")

        if stale or no_report:
            all_needing_generation = [r['ticker'] for r in stale] + no_report
            print()
            print("Tickers needing (re)generation:")
            print(f"  {', '.join(all_needing_generation)}")
            print()
            print("To regenerate, run:")
            print(f"  python -m investment_research.batch_generation.prepare_batch_data --tickers {','.join(all_needing_generation)}")
        else:
            print()
            print("All reports are up to date!")

        print("=" * 60)

    return [r['ticker'] for r in stale] + no_report


def main():
    parser = argparse.ArgumentParser(
        description="Check which DJIA reports need refresh based on new earnings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Check all DJIA reports
    python -m investment_research.batch_generation.check_stale_reports

    # Output only stale ticker symbols (for piping)
    python -m investment_research.batch_generation.check_stale_reports --tickers-only

    # Check specific environment
    python -m investment_research.batch_generation.check_stale_reports --env prod

    # Pipe stale tickers to prepare_batch_data
    python -m investment_research.batch_generation.check_stale_reports --tickers-only | \\
        xargs -I {} python -m investment_research.batch_generation.prepare_batch_data --tickers {}
        """
    )
    parser.add_argument(
        "--tickers-only",
        action="store_true",
        help="Output only ticker symbols (for piping to other commands)"
    )
    parser.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment (default: dev)"
    )
    parser.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all DJIA)"
    )

    args = parser.parse_args()

    # Parse tickers if provided
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    stale_tickers = check_djia_staleness(
        tickers_only=args.tickers_only,
        environment=args.env,
        tickers=tickers
    )

    # Exit with error code if any stale
    sys.exit(0 if len(stale_tickers) == 0 else 1)


if __name__ == "__main__":
    main()
