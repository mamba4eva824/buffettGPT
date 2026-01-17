"""
Migration Script: Convert v1 Reports to v2 Section-Based Schema

Reads existing reports from investment-reports-{env} table and converts them
to the section-per-item format in investment-reports-v2-{env} table.

Usage:
    # Dry run (default) - shows what would be migrated
    python migrate_to_v2.py

    # Actually migrate
    python migrate_to_v2.py --execute

    # Migrate specific tickers
    python migrate_to_v2.py --execute --tickers AAPL,MSFT,F,NVDA

    # Migrate with specific environment
    python migrate_to_v2.py --execute --env prod
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from investment_research.section_parser import (
    parse_report_sections,
    extract_ratings_json,
    build_executive_item,
    get_detailed_section_items,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ReportMigrator:
    """Migrates v1 reports to v2 section-based schema."""

    def __init__(self, environment: str = 'dev', region: str = 'us-east-1'):
        """
        Initialize migrator with table references.

        Args:
            environment: Environment name (dev, staging, prod)
            region: AWS region
        """
        self.environment = environment
        self.region = region

        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.v1_table_name = f'investment-reports-{environment}'
        self.v2_table_name = f'investment-reports-v2-{environment}'

        self.v1_table = self.dynamodb.Table(self.v1_table_name)
        self.v2_table = self.dynamodb.Table(self.v2_table_name)

        logger.info(f"Migrator initialized for {environment}")
        logger.info(f"  v1 table: {self.v1_table_name}")
        logger.info(f"  v2 table: {self.v2_table_name}")

    def get_v1_reports(self, tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Get all v1 reports to migrate.

        Args:
            tickers: Optional list of specific tickers to migrate

        Returns:
            List of v1 report items
        """
        if tickers:
            # Get specific tickers
            reports = []
            for ticker in tickers:
                try:
                    # Get most recent report for ticker (current fiscal year)
                    response = self.v1_table.get_item(
                        Key={
                            'ticker': ticker.upper(),
                            'fiscal_year': datetime.now().year
                        }
                    )
                    if 'Item' in response:
                        reports.append(response['Item'])
                        logger.info(f"Found v1 report for {ticker}")
                    else:
                        logger.warning(f"No v1 report found for {ticker}")
                except ClientError as e:
                    logger.error(f"Error fetching {ticker}: {e}")
            return reports
        else:
            # Scan all reports
            reports = []
            try:
                paginator = self.v1_table.meta.client.get_paginator('scan')
                for page in paginator.paginate(TableName=self.v1_table_name):
                    reports.extend(page.get('Items', []))
                logger.info(f"Found {len(reports)} v1 reports to migrate")
            except ClientError as e:
                logger.error(f"Error scanning v1 table: {e}")
            return reports

    def check_v2_exists(self, ticker: str) -> bool:
        """Check if a v2 report already exists for the ticker."""
        try:
            response = self.v2_table.get_item(
                Key={
                    'ticker': ticker.upper(),
                    'section_id': '00_executive'
                },
                ProjectionExpression='ticker'
            )
            return 'Item' in response
        except ClientError:
            return False

    def migrate_report(self, v1_item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Migrate a single v1 report to v2 format.

        V2 Schema (Single Executive Item):
        - 1 executive item (00_executive): ToC + ratings + 5 executive sections
        - 12 detailed section items (06_growth through 17_realtalk)
        Total: 13 items per report

        Args:
            v1_item: V1 report item from DynamoDB
            dry_run: If True, only log what would be done

        Returns:
            True if migration successful (or would be successful in dry run)
        """
        ticker = v1_item.get('ticker', '').upper()
        fiscal_year = v1_item.get('fiscal_year', datetime.now().year)
        report_content = v1_item.get('report_content', '')

        if not ticker or not report_content:
            logger.warning(f"Skipping invalid report: ticker={ticker}, has_content={bool(report_content)}")
            return False

        # Check if already migrated
        if self.check_v2_exists(ticker):
            logger.info(f"[SKIP] {ticker} already exists in v2 table")
            return True

        logger.info(f"[MIGRATE] {ticker} FY{fiscal_year}")

        try:
            # Parse report into sections
            sections = parse_report_sections(report_content, ticker)
            if not sections:
                logger.warning(f"  No sections parsed for {ticker}")
                return False

            logger.info(f"  Parsed {len(sections)} sections")

            # Extract ratings from JSON block
            ratings = extract_ratings_json(report_content)
            if not ratings:
                # Fall back to v1 ratings if stored separately
                ratings = v1_item.get('ratings', {})
                if isinstance(ratings, str):
                    try:
                        ratings = json.loads(ratings)
                    except json.JSONDecodeError:
                        ratings = {}
            logger.info(f"  Ratings: {ratings.get('overall_verdict', 'N/A')} ({ratings.get('conviction', 'N/A')})")

            # Prepare TTL (90 days from now, matching v1)
            ttl_timestamp = int((datetime.utcnow() + timedelta(days=90)).timestamp())

            # Get metadata from v1
            generated_at = v1_item.get('generated_at', datetime.utcnow().isoformat() + 'Z')
            model = v1_item.get('model', 'migrated-from-v1')

            # Build executive item (ToC + ratings + Part 1 sections)
            executive_item = build_executive_item(
                sections=sections,
                ratings=ratings,
                ticker=ticker,
                generated_at=generated_at,
                model=model,
                prompt_version='v4.8-migrated',
                fiscal_year=fiscal_year
            )
            executive_item['migrated_at'] = datetime.utcnow().isoformat() + 'Z'
            executive_item['ttl'] = ttl_timestamp

            # Get detailed section items (Part 2 & 3)
            detailed_items = get_detailed_section_items(
                sections=sections,
                ticker=ticker,
                generated_at=generated_at
            )
            # Add TTL to detailed items
            for item in detailed_items:
                item['ttl'] = ttl_timestamp

            logger.info(f"  Executive sections: {len(executive_item.get('executive_sections', []))}")
            logger.info(f"  Detailed sections: {len(detailed_items)}")
            logger.info(f"  Total word count: {executive_item.get('total_word_count', 0)}")

            if dry_run:
                logger.info(f"  [DRY RUN] Would write 1 executive + {len(detailed_items)} detailed items")
                return True

            # Write to v2 table
            # 1. Write executive item (00_executive)
            self.v2_table.put_item(Item=executive_item)
            logger.info(f"  Wrote executive item (00_executive)")

            # 2. Batch write detailed section items
            with self.v2_table.batch_writer() as batch:
                for item in detailed_items:
                    batch.put_item(Item=item)

            logger.info(f"  Wrote {len(detailed_items)} detailed section items")
            logger.info(f"  [SUCCESS] {ticker} migrated to v2 (13 items total)")
            return True

        except Exception as e:
            logger.error(f"  [ERROR] Failed to migrate {ticker}: {e}")
            return False

    def run_migration(
        self,
        tickers: Optional[List[str]] = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Run the full migration.

        Args:
            tickers: Optional list of specific tickers to migrate
            dry_run: If True, only log what would be done

        Returns:
            Migration summary dict
        """
        mode = "DRY RUN" if dry_run else "EXECUTE"
        logger.info(f"")
        logger.info(f"{'='*60}")
        logger.info(f"Migration Mode: {mode}")
        logger.info(f"{'='*60}")
        logger.info(f"")

        # Get v1 reports
        v1_reports = self.get_v1_reports(tickers)

        if not v1_reports:
            logger.info("No v1 reports found to migrate")
            return {
                'mode': mode,
                'total': 0,
                'migrated': 0,
                'skipped': 0,
                'failed': 0
            }

        # Migrate each report
        results = {
            'mode': mode,
            'total': len(v1_reports),
            'migrated': 0,
            'skipped': 0,
            'failed': 0,
            'tickers': []
        }

        for v1_item in v1_reports:
            ticker = v1_item.get('ticker', 'UNKNOWN')

            if self.check_v2_exists(ticker):
                results['skipped'] += 1
                results['tickers'].append({'ticker': ticker, 'status': 'skipped'})
            elif self.migrate_report(v1_item, dry_run=dry_run):
                results['migrated'] += 1
                results['tickers'].append({'ticker': ticker, 'status': 'migrated'})
            else:
                results['failed'] += 1
                results['tickers'].append({'ticker': ticker, 'status': 'failed'})

        # Summary
        logger.info(f"")
        logger.info(f"{'='*60}")
        logger.info(f"Migration Summary ({mode})")
        logger.info(f"{'='*60}")
        logger.info(f"  Total v1 reports: {results['total']}")
        logger.info(f"  Migrated:         {results['migrated']}")
        logger.info(f"  Skipped (exists): {results['skipped']}")
        logger.info(f"  Failed:           {results['failed']}")
        logger.info(f"")

        return results


def main():
    """Main entry point for migration script."""
    parser = argparse.ArgumentParser(
        description='Migrate v1 investment reports to v2 section-based schema'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute the migration (default is dry run)'
    )
    parser.add_argument(
        '--tickers',
        type=str,
        help='Comma-separated list of tickers to migrate (e.g., AAPL,MSFT,F)'
    )
    parser.add_argument(
        '--env',
        type=str,
        default='dev',
        choices=['dev', 'staging', 'prod'],
        help='Environment to migrate (default: dev)'
    )
    parser.add_argument(
        '--region',
        type=str,
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )

    args = parser.parse_args()

    # Parse tickers if provided
    tickers = None
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]

    # Run migration
    migrator = ReportMigrator(environment=args.env, region=args.region)
    results = migrator.run_migration(tickers=tickers, dry_run=not args.execute)

    # Exit with error code if any failures
    if results['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
