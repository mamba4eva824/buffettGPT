#!/usr/bin/env python3
"""
Unified CLI for batch report generation.

Combines data preparation, parallel execution, and verification into one tool.
Adapted from generate_report.py for batch workflow.

Usage:
    # Check for stale reports (DJIA default)
    python -m investment_research.batch_generation.batch_cli stale

    # Prepare FMP data for S&P 100
    python -m investment_research.batch_generation.batch_cli prepare --index sp100

    # Launch parallel Claude sessions for S&P 100
    python -m investment_research.batch_generation.batch_cli parallel --index sp100 --windows 8

    # Verify all reports exist
    python -m investment_research.batch_generation.batch_cli verify --index sp100

    # Show help
    python -m investment_research.batch_generation.batch_cli --help
"""

import argparse
import subprocess
import sys
import os

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


def print_banner(index: str = "djia", prompt_version: float = 5.1):
    """Print CLI banner."""
    from investment_research.index_tickers import get_index_tickers
    try:
        count = len(get_index_tickers(index))
    except ValueError:
        count = "?"
    print("=" * 60)
    print(f"  {index.upper()} Batch Report Generator")
    print(f"  {count} Companies | v{prompt_version} Prompt | Parallel Execution")
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
        prompt_version=args.prompt_version,
        index=args.index,
        delay=args.delay
    )


def cmd_parallel(args):
    """Launch parallel Claude sessions via tmux."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "run_parallel_reports.sh")

    if not os.path.exists(script_path):
        print(f"ERROR: Script not found: {script_path}")
        sys.exit(1)

    cmd = ["bash", script_path, "--index", args.index, "--windows", str(args.windows),
           "--batch-size", str(args.batch_size)]
    if args.dry_run:
        cmd.append("--dry-run")
    if hasattr(args, 'prompt_version') and args.prompt_version:
        cmd.extend(["--prompt-version", str(args.prompt_version)])
    if hasattr(args, 'max_turns') and args.max_turns:
        cmd.extend(["--max-turns", str(args.max_turns)])

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
        tickers=tickers,
        index=args.index
    )

    sys.exit(0 if success else 1)


def cmd_stale(args):
    """Check for stale reports."""
    from investment_research.batch_generation.check_stale_reports import check_staleness

    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    stale = check_staleness(
        tickers_only=args.tickers_only,
        environment=args.env,
        tickers=tickers,
        index=args.index
    )

    sys.exit(0 if len(stale) == 0 else 1)


def cmd_status(args):
    """Show overall status of reports."""
    from investment_research.batch_generation.verify_reports import verify_reports
    from investment_research.batch_generation.check_stale_reports import check_staleness

    print("=" * 60)
    print(f"  {args.index.upper()} Batch Report Status")
    print("=" * 60)
    print()

    # Check what exists
    print("Checking existing reports...")
    verify_reports(environment=args.env, index=args.index)

    print()

    # Check staleness
    print("Checking for stale reports...")
    check_staleness(environment=args.env, index=args.index)


def main():
    parser = argparse.ArgumentParser(
        description="Batch Report Generator - Unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full workflow (DJIA default)
    python -m investment_research.batch_generation.batch_cli stale
    python -m investment_research.batch_generation.batch_cli prepare
    python -m investment_research.batch_generation.batch_cli parallel
    python -m investment_research.batch_generation.batch_cli verify

    # S&P 100 workflow
    python -m investment_research.batch_generation.batch_cli prepare --index sp100
    python -m investment_research.batch_generation.batch_cli parallel --index sp100 --windows 8
    python -m investment_research.batch_generation.batch_cli verify --index sp100

    # Check overall status
    python -m investment_research.batch_generation.batch_cli status --index sp100

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
        default=None,
        help="Output JSON file (default: auto-generated from index)"
    )
    p_prepare.add_argument(
        "--tickers",
        type=str,
        help="Comma-separated list of tickers (default: all from selected index)"
    )
    p_prepare.add_argument(
        "--prompt-version",
        type=float,
        default=5.1,
        help="Prompt version (default: 5.1)"
    )
    p_prepare.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use (default: djia). Options: djia, sp100, sp500"
    )
    p_prepare.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between tickers for rate limiting (default: 0.0)"
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
    p_parallel.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use (default: djia). Options: djia, sp100, sp500"
    )
    p_parallel.add_argument(
        "--windows",
        type=int,
        default=5,
        help="Number of parallel windows (default: 5)"
    )
    p_parallel.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Tickers per terminal session (default: 5). Limits context window usage."
    )
    p_parallel.add_argument(
        "--prompt-version",
        type=float,
        default=5.1,
        help="Prompt version (default: 5.1)"
    )
    p_parallel.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Max turns per Claude session (default: auto-calculated from batch-size)"
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
        help="Comma-separated list of tickers (default: all from selected index)"
    )
    p_verify.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use (default: djia). Options: djia, sp100, sp500"
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
        help="Comma-separated list of tickers (default: all from selected index)"
    )
    p_stale.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use (default: djia). Options: djia, sp100, sp500"
    )
    p_stale.set_defaults(func=cmd_stale)

    # status command
    p_status = subparsers.add_parser(
        "status",
        help="Show overall status of reports"
    )
    p_status.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "staging", "prod"],
        help="Environment (default: dev)"
    )
    p_status.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to use (default: djia). Options: djia, sp100, sp500"
    )
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    prompt_ver = getattr(args, 'prompt_version', 5.1)
    print_banner(index=args.index, prompt_version=prompt_ver)
    args.func(args)


if __name__ == "__main__":
    main()
