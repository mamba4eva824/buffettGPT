#!/usr/bin/env python3
"""
Unified CLI for DJIA batch report generation.

Combines data preparation, parallel execution, and verification into one tool.
Adapted from generate_report.py for batch workflow.

Usage:
    # Check for stale reports
    python -m investment_research.batch_generation.batch_cli stale

    # Prepare FMP data for all 30 tickers
    python -m investment_research.batch_generation.batch_cli prepare

    # Launch parallel Claude sessions
    python -m investment_research.batch_generation.batch_cli parallel

    # Verify all reports exist
    python -m investment_research.batch_generation.batch_cli verify

    # Show help
    python -m investment_research.batch_generation.batch_cli --help
"""

import argparse
import subprocess
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


def print_banner():
    """Print CLI banner."""
    print("=" * 60)
    print("  DJIA Batch Report Generator")
    print("  30 Companies | v4.8 Prompt | Parallel Execution")
    print("=" * 60)
    print()


def cmd_prepare(args):
    """Prepare FMP data for all tickers."""
    from investment_research.batch_generation.prepare_batch_data import prepare_all_data

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    prepare_all_data(
        output_file=args.output,
        tickers=tickers,
        prompt_version=args.prompt_version
    )


def cmd_parallel(args):
    """Launch parallel Claude sessions via tmux."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "run_parallel_reports.sh")

    if not os.path.exists(script_path):
        print(f"ERROR: Script not found: {script_path}")
        sys.exit(1)

    cmd = ["bash", script_path]
    if args.dry_run:
        cmd.append("--dry-run")

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to launch parallel sessions: {e}")
        sys.exit(1)


def cmd_verify(args):
    """Verify all reports exist in DynamoDB."""
    from investment_research.batch_generation.verify_reports import verify_reports

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    success = verify_reports(
        environment=args.env,
        tickers=tickers
    )

    sys.exit(0 if success else 1)


def cmd_stale(args):
    """Check for stale reports."""
    from investment_research.batch_generation.check_stale_reports import check_djia_staleness

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    stale = check_djia_staleness(
        tickers_only=args.tickers_only,
        environment=args.env,
        tickers=tickers
    )

    sys.exit(0 if len(stale) == 0 else 1)


def cmd_status(args):
    """Show overall status of DJIA reports."""
    from investment_research.batch_generation.verify_reports import verify_reports
    from investment_research.batch_generation.check_stale_reports import check_djia_staleness

    print("=" * 60)
    print("  DJIA Batch Report Status")
    print("=" * 60)
    print()

    # Check what exists
    print("Checking existing reports...")
    verify_reports(environment=args.env)

    print()

    # Check staleness
    print("Checking for stale reports...")
    check_djia_staleness(environment=args.env)


def main():
    parser = argparse.ArgumentParser(
        description="DJIA Batch Report Generator - Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full workflow
    python -m investment_research.batch_generation.batch_cli stale
    python -m investment_research.batch_generation.batch_cli prepare
    python -m investment_research.batch_generation.batch_cli parallel
    python -m investment_research.batch_generation.batch_cli verify

    # Check overall status
    python -m investment_research.batch_generation.batch_cli status

    # Prepare specific tickers
    python -m investment_research.batch_generation.batch_cli prepare --tickers AAPL,MSFT

    # Dry run parallel (show what would happen)
    python -m investment_research.batch_generation.batch_cli parallel --dry-run
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # prepare command
    p_prepare = subparsers.add_parser(
        "prepare",
        help="Fetch FMP financial data for batch generation"
    )
    p_prepare.add_argument(
        "--output",
        default="djia_30_batch_data.json",
        help="Output JSON file (default: djia_30_batch_data.json)"
    )
    p_prepare.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all DJIA)"
    )
    p_prepare.add_argument(
        "--prompt-version",
        type=float,
        default=4.8,
        help="Prompt version (default: 4.8)"
    )
    p_prepare.set_defaults(func=cmd_prepare)

    # parallel command
    p_parallel = subparsers.add_parser(
        "parallel",
        help="Launch parallel Claude sessions via tmux"
    )
    p_parallel.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would happen without launching"
    )
    p_parallel.set_defaults(func=cmd_parallel)

    # verify command
    p_verify = subparsers.add_parser(
        "verify",
        help="Verify reports exist in DynamoDB"
    )
    p_verify.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment (default: dev)"
    )
    p_verify.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all DJIA)"
    )
    p_verify.set_defaults(func=cmd_verify)

    # stale command
    p_stale = subparsers.add_parser(
        "stale",
        help="Check for reports needing refresh"
    )
    p_stale.add_argument(
        "--tickers-only",
        action="store_true",
        help="Output only ticker symbols"
    )
    p_stale.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment (default: dev)"
    )
    p_stale.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all DJIA)"
    )
    p_stale.set_defaults(func=cmd_stale)

    # status command
    p_status = subparsers.add_parser(
        "status",
        help="Show overall status of DJIA reports"
    )
    p_status.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment (default: dev)"
    )
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    print_banner()
    args.func(args)


if __name__ == "__main__":
    main()
