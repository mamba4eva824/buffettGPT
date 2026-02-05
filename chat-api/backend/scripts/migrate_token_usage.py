#!/usr/bin/env python3
"""
Migration Script: Token Usage Table (month → billing_period)

Migrates token usage data from the legacy month-based schema (YYYY-MM)
to the anniversary-based billing_period schema (YYYY-MM-DD).

This migration is necessary because:
1. The old table uses 'month' as sort key (YYYY-MM format)
2. The TokenUsageTracker code expects 'billing_period' (YYYY-MM-DD format)
3. Anniversary-based billing requires tracking the exact billing day

Migration logic:
- Reads from: buffett-{env}-token-usage (old table with 'month' key)
- Writes to: token-usage-{env}-buffett (new table with 'billing_period' key)
- Transforms: "2026-02" → "2026-02-01" (defaults billing_day to 1)

Usage:
    # Dry run (default) - shows what would be migrated
    python scripts/migrate_token_usage.py --env dev

    # Execute migration
    python scripts/migrate_token_usage.py --env dev --execute

    # Migrate specific users
    python scripts/migrate_token_usage.py --env dev --execute --users user1,user2

    # With custom region
    python scripts/migrate_token_usage.py --env dev --execute --region us-west-2
"""

import os
import sys
import argparse
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TokenUsageMigrator:
    """Migrates token usage from month-based to billing_period-based schema."""

    # Table naming conventions
    OLD_TABLE_FORMAT = "buffett-{env}-token-usage"
    NEW_TABLE_FORMAT = "token-usage-{env}-buffett"

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
        self.client = boto3.client('dynamodb', region_name=region)

        self.old_table_name = self.OLD_TABLE_FORMAT.format(env=environment)
        self.new_table_name = self.NEW_TABLE_FORMAT.format(env=environment)

        self.old_table = self.dynamodb.Table(self.old_table_name)
        self.new_table = self.dynamodb.Table(self.new_table_name)

        logger.info(f"Migrator initialized for {environment}")
        logger.info(f"  Old table: {self.old_table_name}")
        logger.info(f"  New table: {self.new_table_name}")

    def check_tables_exist(self) -> Dict[str, bool]:
        """Check if both tables exist and are accessible."""
        results = {'old': False, 'new': False}

        try:
            self.client.describe_table(TableName=self.old_table_name)
            results['old'] = True
            logger.info(f"✓ Old table exists: {self.old_table_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"✗ Old table not found: {self.old_table_name}")
            else:
                raise

        try:
            self.client.describe_table(TableName=self.new_table_name)
            results['new'] = True
            logger.info(f"✓ New table exists: {self.new_table_name}")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceNotFoundException':
                logger.warning(f"✗ New table not found: {self.new_table_name}")
            else:
                raise

        return results

    def transform_key(self, month_str: str, billing_day: int = 1) -> str:
        """
        Transform YYYY-MM to YYYY-MM-DD format.

        For existing users, default billing_day to 1 (first of month)
        to preserve calendar month semantics for historical data.

        Args:
            month_str: Month in "YYYY-MM" format (e.g., "2026-02")
            billing_day: Day of month (1-31), defaults to 1

        Returns:
            Billing period in "YYYY-MM-DD" format (e.g., "2026-02-01")
        """
        return f"{month_str}-{billing_day:02d}"

    def calculate_period_end(self, billing_period: str) -> str:
        """
        Calculate the end of the billing period (next reset date).

        Args:
            billing_period: Period start in "YYYY-MM-DD" format

        Returns:
            Period end in ISO format
        """
        try:
            year, month, day = map(int, billing_period.split('-'))

            if month == 12:
                end_date = datetime(year + 1, 1, day, tzinfo=timezone.utc)
            else:
                # Handle months with fewer days
                next_month = month + 1
                try:
                    end_date = datetime(year, next_month, day, tzinfo=timezone.utc)
                except ValueError:
                    # Day doesn't exist in next month, use last day
                    if next_month == 2:
                        end_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
                    elif next_month in [4, 6, 9, 11]:
                        end_day = 30
                    else:
                        end_day = 31
                    end_date = datetime(year, next_month, min(day, end_day), tzinfo=timezone.utc)

            return end_date.isoformat().replace('+00:00', 'Z')

        except Exception as e:
            logger.warning(f"Error calculating period end for {billing_period}: {e}")
            return ""

    def scan_old_table(self, user_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Scan all items from the old table.

        Args:
            user_ids: Optional list of specific user IDs to migrate

        Returns:
            List of items from old table
        """
        items = []

        try:
            if user_ids:
                # Query specific users
                for user_id in user_ids:
                    response = self.old_table.query(
                        KeyConditionExpression='user_id = :uid',
                        ExpressionAttributeValues={':uid': user_id}
                    )
                    items.extend(response.get('Items', []))
            else:
                # Full table scan with pagination
                scan_kwargs = {}
                while True:
                    response = self.old_table.scan(**scan_kwargs)
                    items.extend(response.get('Items', []))

                    if 'LastEvaluatedKey' not in response:
                        break
                    scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

            logger.info(f"Found {len(items)} items in old table")

        except ClientError as e:
            logger.error(f"Error scanning old table: {e}")
            raise

        return items

    def transform_item(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Transform a single item from old schema to new schema.

        Args:
            item: Item from old table

        Returns:
            Transformed item for new table, or None if invalid
        """
        user_id = item.get('user_id')
        month = item.get('month')

        if not user_id or not month:
            logger.warning(f"Skipping invalid item (missing user_id or month): {item}")
            return None

        # Get or default billing_day
        billing_day = int(item.get('billing_day', 1))

        # Transform the key
        billing_period = self.transform_key(month, billing_day)

        # Create new item with transformed key
        new_item = {}

        # Copy all fields except 'month' (the old sort key)
        for key, value in item.items():
            if key == 'month':
                continue
            # Convert Decimal to int for numeric fields
            if isinstance(value, Decimal):
                new_item[key] = int(value) if value == int(value) else float(value)
            else:
                new_item[key] = value

        # Set new key and billing fields
        new_item['billing_period'] = billing_period
        new_item['billing_day'] = billing_day

        # Add billing period timestamps if not present
        if 'billing_period_start' not in new_item:
            new_item['billing_period_start'] = f"{billing_period}T00:00:00Z"

        if 'billing_period_end' not in new_item:
            new_item['billing_period_end'] = self.calculate_period_end(billing_period)

        # Add reset_date if not present (same as billing_period_end)
        if 'reset_date' not in new_item:
            new_item['reset_date'] = new_item['billing_period_end']

        # Default subscription tier if not present
        if 'subscription_tier' not in new_item:
            new_item['subscription_tier'] = 'free'

        return new_item

    def migrate_item(self, item: Dict[str, Any], dry_run: bool = True) -> bool:
        """
        Migrate a single item to new table.

        Args:
            item: Item from old table
            dry_run: If True, only log what would be migrated

        Returns:
            True if migration succeeded, False otherwise
        """
        user_id = item.get('user_id', 'unknown')
        month = item.get('month', 'unknown')

        # Transform the item
        new_item = self.transform_item(item)
        if new_item is None:
            return False

        billing_period = new_item['billing_period']
        total_tokens = new_item.get('total_tokens', 0)
        token_limit = new_item.get('token_limit', 0)

        logger.info(f"  {user_id}: {month} → {billing_period} "
                   f"({total_tokens}/{token_limit} tokens)")

        if dry_run:
            return True

        try:
            self.new_table.put_item(Item=new_item)
            return True
        except ClientError as e:
            logger.error(f"Failed to write item for {user_id}: {e}")
            return False

    def run_migration(
        self,
        dry_run: bool = True,
        user_ids: Optional[List[str]] = None
    ) -> Dict[str, int]:
        """
        Run the full migration.

        Args:
            dry_run: If True, only show what would be migrated
            user_ids: Optional list of specific users to migrate

        Returns:
            Dictionary with migration statistics
        """
        mode = "DRY RUN" if dry_run else "EXECUTE"
        logger.info(f"\n{'='*60}")
        logger.info(f"Migration Mode: {mode}")
        logger.info(f"{'='*60}\n")

        # Check tables
        table_status = self.check_tables_exist()

        if not table_status['old']:
            logger.error("Old table does not exist. Cannot proceed.")
            return {'total': 0, 'migrated': 0, 'failed': 0, 'skipped': 0}

        if not table_status['new'] and not dry_run:
            logger.error("New table does not exist. Run 'terraform apply' first.")
            return {'total': 0, 'migrated': 0, 'failed': 0, 'skipped': 0}

        # Scan old table
        items = self.scan_old_table(user_ids)

        results = {
            'total': len(items),
            'migrated': 0,
            'failed': 0,
            'skipped': 0
        }

        if not items:
            logger.info("No items to migrate.")
            return results

        logger.info(f"\nMigrating {len(items)} items...\n")

        for item in items:
            if self.migrate_item(item, dry_run=dry_run):
                results['migrated'] += 1
            else:
                results['failed'] += 1

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"Migration Summary ({mode})")
        logger.info(f"{'='*60}")
        logger.info(f"  Total items:    {results['total']}")
        logger.info(f"  Migrated:       {results['migrated']}")
        logger.info(f"  Failed:         {results['failed']}")
        logger.info(f"  Skipped:        {results['skipped']}")

        if dry_run:
            logger.info(f"\nTo execute migration, run with --execute flag")

        return results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate token usage table from month to billing_period schema'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute the migration (default is dry-run)'
    )
    parser.add_argument(
        '--env',
        default='dev',
        choices=['dev', 'staging', 'prod'],
        help='Environment to migrate (default: dev)'
    )
    parser.add_argument(
        '--region',
        default='us-east-1',
        help='AWS region (default: us-east-1)'
    )
    parser.add_argument(
        '--users',
        type=str,
        help='Comma-separated list of user IDs to migrate (default: all)'
    )

    args = parser.parse_args()

    # Parse user IDs if provided
    user_ids = None
    if args.users:
        user_ids = [u.strip() for u in args.users.split(',')]
        logger.info(f"Migrating specific users: {user_ids}")

    # Run migration
    migrator = TokenUsageMigrator(environment=args.env, region=args.region)
    results = migrator.run_migration(dry_run=not args.execute, user_ids=user_ids)

    # Exit with error code if any failures
    if results['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
