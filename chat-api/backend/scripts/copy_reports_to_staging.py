"""
Copy Investment Reports, Metrics History & Stock Data from Dev to Staging DynamoDB.

Scans dev tables, filters out test tickers, resets TTLs, and writes to staging.

Usage:
    # Dry run (default) - shows what would be copied
    python scripts/copy_reports_to_staging.py

    # Execute the copy
    python scripts/copy_reports_to_staging.py --execute

    # Verify staging counts match expectations
    python scripts/copy_reports_to_staging.py --verify

    # Copy only specific tickers
    python scripts/copy_reports_to_staging.py --execute --tickers AAPL,MSFT,NVDA

    # Custom source/target environments
    python scripts/copy_reports_to_staging.py --execute --source dev --target staging

    # Copy only stock data
    python scripts/copy_reports_to_staging.py --execute --stock-data-only
"""

import argparse
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# TTL durations matching production settings
REPORTS_TTL_DAYS = 120
METRICS_TTL_DAYS = 90
STOCK_DATA_TTL_DAYS = 365

# Test ticker patterns to exclude:
#   D + 4+ uppercase alpha (Docker E2E tests, e.g. DTEST, DGSJC)
#   E2E + hex chars (Zip Lambda E2E tests, e.g. E2E300D)
#   INT + 4 hex chars (Integration tests, e.g. INT23C8) — NOT INTC (Intel)
#   SNDK (known stale/test ticker)
TEST_TICKER_RE = re.compile(r'^(D[A-Z]{4,}|E2E.+|INT[0-9A-F]{4}|SNDK)$')

REGION = 'us-east-1'


def is_test_ticker(ticker: str) -> bool:
    return bool(TEST_TICKER_RE.match(ticker))


def scan_full_table(table) -> list:
    """Scan entire DynamoDB table with pagination."""
    items = []
    kwargs = {}
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get('Items', []))
        last_key = response.get('LastEvaluatedKey')
        if not last_key:
            break
        kwargs['ExclusiveStartKey'] = last_key
    return items


def reset_report_ttl(item: dict) -> dict:
    """Reset the 'ttl' field to 120 days from now."""
    new_ttl = int((datetime.now(timezone.utc) + timedelta(days=REPORTS_TTL_DAYS)).timestamp())
    item['ttl'] = new_ttl
    return item


def reset_metrics_ttl(item: dict) -> dict:
    """Reset the 'expires_at' field to 90 days from now."""
    new_expires = int((datetime.now(timezone.utc) + timedelta(days=METRICS_TTL_DAYS)).timestamp())
    item['expires_at'] = new_expires
    # Also update cached_at to current time
    item['cached_at'] = int(datetime.now(timezone.utc).timestamp())
    return item


def reset_stock_data_ttl(item: dict) -> dict:
    """Reset the 'expires_at' field to 365 days from now."""
    new_expires = int((datetime.now(timezone.utc) + timedelta(days=STOCK_DATA_TTL_DAYS)).timestamp())
    item['expires_at'] = new_expires
    return item


def batch_write(table, items: list) -> int:
    """Write items using batch_writer. Returns count written."""
    written = 0
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=item)
            written += 1
    return written


def _default_ticker_fn(item: dict) -> str:
    return item.get('ticker', 'UNKNOWN')


def _stock_data_ticker_fn(item: dict) -> str:
    return item.get('PK', '').replace('TICKER#', '') or 'UNKNOWN'


def copy_table(source_table, target_table, ttl_reset_fn, table_label: str,
               execute: bool = False, ticker_filter: set = None,
               ticker_fn=None) -> dict:
    """
    Copy items from source to target, filtering test tickers and resetting TTLs.

    Returns dict with counts: {ticker: item_count} for copied items,
    plus 'skipped_tickers' and 'skipped_count'.
    """
    if ticker_fn is None:
        ticker_fn = _default_ticker_fn

    logger.info(f"Scanning {table_label}: {source_table.table_name}...")
    items = scan_full_table(source_table)
    logger.info(f"  Found {len(items)} total items")

    # Group by ticker
    by_ticker = defaultdict(list)
    for item in items:
        ticker = ticker_fn(item)
        by_ticker[ticker].append(item)

    # Filter
    copy_items = []
    skipped_tickers = set()
    skipped_count = 0
    copied_counts = defaultdict(int)

    for ticker in sorted(by_ticker.keys()):
        ticker_items = by_ticker[ticker]

        if is_test_ticker(ticker):
            skipped_tickers.add(ticker)
            skipped_count += len(ticker_items)
            logger.info(f"  SKIP {ticker} ({len(ticker_items)} items) - test ticker")
            continue

        if ticker_filter and ticker not in ticker_filter:
            skipped_tickers.add(ticker)
            skipped_count += len(ticker_items)
            logger.info(f"  SKIP {ticker} ({len(ticker_items)} items) - not in ticker filter")
            continue

        copied_counts[ticker] = len(ticker_items)
        for item in ticker_items:
            copy_items.append(ttl_reset_fn(item.copy()))

    logger.info(f"  To copy: {len(copy_items)} items ({len(copied_counts)} tickers)")
    logger.info(f"  Skipped: {skipped_count} items ({len(skipped_tickers)} tickers)")

    if execute and copy_items:
        logger.info(f"  Writing to {target_table.table_name}...")
        start = time.time()
        written = batch_write(target_table, copy_items)
        elapsed = time.time() - start
        logger.info(f"  Wrote {written} items in {elapsed:.1f}s")
    elif not execute:
        logger.info("  DRY RUN - no data written")

    return {
        'copied_counts': dict(copied_counts),
        'total_copied': len(copy_items),
        'skipped_tickers': sorted(skipped_tickers),
        'skipped_count': skipped_count,
    }


def verify_staging(source_table, target_table, table_label: str,
                   ticker_fn=None) -> bool:
    """Compare item counts between source (dev, filtered) and target (staging)."""
    if ticker_fn is None:
        ticker_fn = _default_ticker_fn

    logger.info(f"Verifying {table_label}...")

    source_items = scan_full_table(source_table)
    target_items = scan_full_table(target_table)

    # Filter source test tickers
    source_by_ticker = defaultdict(int)
    for item in source_items:
        ticker = ticker_fn(item)
        if not is_test_ticker(ticker):
            source_by_ticker[ticker] += 1

    target_by_ticker = defaultdict(int)
    for item in target_items:
        ticker = ticker_fn(item)
        target_by_ticker[ticker] += 1

    source_total = sum(source_by_ticker.values())
    target_total = sum(target_by_ticker.values())

    logger.info(f"  Source (filtered): {source_total} items, {len(source_by_ticker)} tickers")
    logger.info(f"  Target:            {target_total} items, {len(target_by_ticker)} tickers")

    # Check for mismatches
    all_tickers = sorted(set(source_by_ticker.keys()) | set(target_by_ticker.keys()))
    mismatches = []
    for ticker in all_tickers:
        s = source_by_ticker.get(ticker, 0)
        t = target_by_ticker.get(ticker, 0)
        if s != t:
            mismatches.append((ticker, s, t))

    if mismatches:
        logger.warning(f"  MISMATCHES found ({len(mismatches)}):")
        for ticker, s, t in mismatches:
            logger.warning(f"    {ticker}: source={s}, target={t}")
        return False
    else:
        logger.info(f"  ALL MATCH - {len(all_tickers)} tickers verified")
        return True


def main():
    parser = argparse.ArgumentParser(description='Copy investment data from dev to staging')
    parser.add_argument('--execute', action='store_true',
                        help='Actually write data (default is dry-run)')
    parser.add_argument('--verify', action='store_true',
                        help='Verify staging counts match dev (filtered)')
    parser.add_argument('--source', default='dev',
                        help='Source environment (default: dev)')
    parser.add_argument('--target', default='staging',
                        help='Target environment (default: staging)')
    parser.add_argument('--tickers', type=str, default=None,
                        help='Comma-separated list of tickers to copy (default: all)')
    parser.add_argument('--reports-only', action='store_true',
                        help='Only copy reports table')
    parser.add_argument('--metrics-only', action='store_true',
                        help='Only copy metrics table')
    parser.add_argument('--stock-data-only', action='store_true',
                        help='Only copy stock-data-4h table')
    args = parser.parse_args()

    dynamodb = boto3.resource('dynamodb', region_name=REGION)

    reports_source = dynamodb.Table(f'investment-reports-v2-{args.source}')
    reports_target = dynamodb.Table(f'investment-reports-v2-{args.target}')
    metrics_source = dynamodb.Table(f'metrics-history-{args.source}')
    metrics_target = dynamodb.Table(f'metrics-history-{args.target}')
    stock_data_source = dynamodb.Table(f'stock-data-4h-{args.source}')
    stock_data_target = dynamodb.Table(f'stock-data-4h-{args.target}')

    ticker_filter = None
    if args.tickers:
        ticker_filter = set(t.strip().upper() for t in args.tickers.split(','))
        logger.info(f"Ticker filter: {sorted(ticker_filter)}")

    # Determine which tables to copy
    any_only = args.reports_only or args.metrics_only or args.stock_data_only
    do_reports = args.reports_only or not any_only
    do_metrics = args.metrics_only or not any_only
    do_stock_data = args.stock_data_only or not any_only

    mode = "EXECUTE" if args.execute else "DRY RUN"
    logger.info(f"Mode: {mode}")
    logger.info(f"Source: {args.source} -> Target: {args.target}")
    print()

    if args.verify:
        ok_reports = True
        ok_metrics = True
        ok_stock_data = True
        if do_reports:
            ok_reports = verify_staging(reports_source, reports_target, "Investment Reports")
            print()
        if do_metrics:
            ok_metrics = verify_staging(metrics_source, metrics_target, "Metrics History")
            print()
        if do_stock_data:
            ok_stock_data = verify_staging(stock_data_source, stock_data_target,
                                           "Stock Data 4H", ticker_fn=_stock_data_ticker_fn)

        if ok_reports and ok_metrics and ok_stock_data:
            print("\nVERIFICATION PASSED")
        else:
            print("\nVERIFICATION FAILED - see mismatches above")
        return

    # Copy reports
    if do_reports:
        reports_result = copy_table(
            reports_source, reports_target,
            reset_report_ttl, "Investment Reports",
            execute=args.execute, ticker_filter=ticker_filter
        )
        print()

    # Copy metrics
    if do_metrics:
        metrics_result = copy_table(
            metrics_source, metrics_target,
            reset_metrics_ttl, "Metrics History",
            execute=args.execute, ticker_filter=ticker_filter
        )
        print()

    # Copy stock data
    if do_stock_data:
        stock_data_result = copy_table(
            stock_data_source, stock_data_target,
            reset_stock_data_ttl, "Stock Data 4H",
            execute=args.execute, ticker_filter=ticker_filter,
            ticker_fn=_stock_data_ticker_fn
        )
        print()

    # Summary
    print("=" * 60)
    print(f"SUMMARY ({'EXECUTED' if args.execute else 'DRY RUN'})")
    print("=" * 60)
    if do_reports:
        print(f"Reports:    {reports_result['total_copied']} items "
              f"({len(reports_result['copied_counts'])} tickers)")
        print(f"  Skipped: {reports_result['skipped_count']} items "
              f"({len(reports_result['skipped_tickers'])} test tickers)")
    if do_metrics:
        print(f"Metrics:    {metrics_result['total_copied']} items "
              f"({len(metrics_result['copied_counts'])} tickers)")
        print(f"  Skipped: {metrics_result['skipped_count']} items "
              f"({len(metrics_result['skipped_tickers'])} test tickers)")
    if do_stock_data:
        print(f"Stock Data: {stock_data_result['total_copied']} items "
              f"({len(stock_data_result['copied_counts'])} tickers)")
        print(f"  Skipped: {stock_data_result['skipped_count']} items "
              f"({len(stock_data_result['skipped_tickers'])} test tickers)")

    if not args.execute:
        print("\nThis was a DRY RUN. Use --execute to write data.")


if __name__ == '__main__':
    main()
