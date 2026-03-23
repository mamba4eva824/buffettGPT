#!/usr/bin/env python3
"""
Verify all index reports exist in DynamoDB.

Checks the investment-reports-v2 table for index company reports
and provides a summary of what exists and what's missing.

Usage:
    python -m investment_research.batch_generation.verify_reports
    python -m investment_research.batch_generation.verify_reports --index sp100
    python -m investment_research.batch_generation.verify_reports --env prod
    python -m investment_research.batch_generation.verify_reports --tickers AAPL,MSFT
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List, Optional

import boto3
from botocore.exceptions import ClientError

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from investment_research.index_tickers import get_index_tickers


def verify_reports(
    table_name: str = "investment-reports-v2",
    environment: str = "dev",
    tickers: Optional[List[str]] = None,
    region: str = "us-east-1",
    index: str = "djia"
) -> bool:
    """
    Check DynamoDB for investment reports.

    Args:
        table_name: Base table name (will append -environment if not 'dev')
        environment: Environment name (dev, staging, prod)
        tickers: List of tickers to check (defaults to index tickers)
        region: AWS region
        index: Index to verify (djia, sp100, sp500)

    Returns:
        True if all reports exist, False otherwise
    """
    if tickers is None:
        tickers = get_index_tickers(index)

    # Build full table name
    full_table_name = f"{table_name}-{environment}" if environment != "dev" else table_name

    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(full_table_name)

    missing = []
    complete = []
    details = []

    print("=" * 70)
    print(f"  {index.upper()} Report Verification")
    print("=" * 70)
    print()
    print(f"Table:   {full_table_name}")
    print(f"Tickers: {len(tickers)}")
    print("-" * 70)

    for ticker in tickers:
        try:
            response = table.get_item(
                Key={'ticker': ticker.upper(), 'section_id': '00_executive'},
                ProjectionExpression='ticker, generated_at, total_word_count, prompt_version, company_name'
            )

            if 'Item' in response:
                item = response['Item']
                generated_at = item.get('generated_at', 'unknown')
                word_count = item.get('total_word_count', 0)
                prompt_version = item.get('prompt_version', 'unknown')
                company_name = item.get('company_name', ticker)

                # Parse date for display
                try:
                    gen_date = generated_at[:10] if generated_at != 'unknown' else 'unknown'
                except:
                    gen_date = 'unknown'

                complete.append(ticker)
                details.append({
                    'ticker': ticker,
                    'status': 'complete',
                    'company_name': company_name,
                    'word_count': word_count,
                    'generated_at': gen_date,
                    'prompt_version': prompt_version
                })
                print(f"  ✓ {ticker:5} | {word_count:>6,} words | {gen_date} | {prompt_version}")
            else:
                missing.append(ticker)
                details.append({
                    'ticker': ticker,
                    'status': 'missing'
                })
                print(f"  ✗ {ticker:5} | MISSING")

        except ClientError as e:
            missing.append(ticker)
            details.append({
                'ticker': ticker,
                'status': 'error',
                'error': str(e)
            })
            print(f"  ✗ {ticker:5} | ERROR: {e}")

    # Summary
    print("-" * 70)
    print(f"Complete: {len(complete)}/{len(tickers)}")

    if missing:
        print(f"Missing:  {', '.join(missing)}")
        print()
        print("To generate missing reports, run:")
        print(f"  python -m investment_research.batch_generation.prepare_batch_data --tickers {','.join(missing)}")
        return False
    else:
        print()
        print("All reports present!")

        # Calculate total words
        total_words = sum(d.get('word_count', 0) for d in details if d['status'] == 'complete')
        print(f"Total word count: {total_words:,}")

    print("=" * 70)
    return len(missing) == 0


def main():
    parser = argparse.ArgumentParser(
        description="Verify index investment reports exist in DynamoDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Verify all DJIA reports in dev (default)
    python -m investment_research.batch_generation.verify_reports

    # Verify S&P 100 reports
    python -m investment_research.batch_generation.verify_reports --index sp100

    # Verify in production
    python -m investment_research.batch_generation.verify_reports --env prod

    # Verify specific tickers
    python -m investment_research.batch_generation.verify_reports --tickers AAPL,MSFT,NVDA
        """
    )
    parser.add_argument(
        "--index",
        type=str,
        default="djia",
        help="Index to verify (default: djia). Options: djia, sp100, sp500"
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
    parser.add_argument(
        "--region",
        type=str,
        default="us-east-1",
        help="AWS region (default: us-east-1)"
    )

    args = parser.parse_args()

    # Parse tickers if provided
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    success = verify_reports(
        environment=args.env,
        tickers=tickers,
        region=args.region,
        index=args.index
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
