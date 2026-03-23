"""
S&P 500 Data Ingestion Pipeline Lambda

Processes all S&P 500 tickers sequentially:
1. For each ticker, fetch financial data via fmp_client (cache-aware)
2. Extract quarterly trends via feature_extractor
3. Write 9-category metrics to metrics-history DynamoDB table

Designed to run within the 15-minute Lambda timeout.
Cached tickers (~1.5s each) allow processing 500 companies in ~12 minutes.
On cache miss, FMP API calls add ~3-5s per ticker (3 statements).

Invocation: manual, EventBridge schedule, or triggered by earnings_calendar_checker.
"""

import json
import logging
import os
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

from utils.fmp_client import get_financial_data, fetch_earnings, fetch_dividends
from utils.feature_extractor import extract_quarterly_trends, prepare_metrics_for_cache

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')

# DynamoDB
dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process S&P 500 tickers and populate metrics-history table.

    Event payload options:
        {} — process all 498 S&P 500 tickers
        {"tickers": ["AAPL", "MSFT"]} — process specific tickers
        {"skip_fresh": true} — skip tickers with data less than 7 days old (default: true)
        {"include_events": true} — also fetch earnings + dividends (default: false)
        {"run_aggregator": true} — run sp500_aggregator after pipeline completes (default: false)
    """
    from investment_research.index_tickers import SP500_TICKERS, to_fmp_format

    # Parse event
    tickers = event.get('tickers', SP500_TICKERS)
    skip_fresh = event.get('skip_fresh', True)
    include_events = event.get('include_events', False)

    logger.info(f"Starting SP500 pipeline: {len(tickers)} tickers, skip_fresh={skip_fresh}")

    # Track progress
    results = {
        'processed': 0,
        'skipped_fresh': 0,
        'cache_hits': 0,
        'api_calls': 0,
        'failures': [],
        'started_at': datetime.now().isoformat(),
    }

    for i, ticker in enumerate(tickers):
        # Check remaining Lambda time (leave 60s buffer)
        if context and hasattr(context, 'get_remaining_time_in_millis'):
            remaining_ms = context.get_remaining_time_in_millis()
            if remaining_ms < 60_000:
                logger.warning(f"Timeout approaching at ticker {i}/{len(tickers)}. Stopping.")
                results['stopped_early'] = True
                results['last_processed_index'] = i
                break

        try:
            result = _process_ticker(ticker, skip_fresh, include_events)
            if result == 'skipped_fresh':
                results['skipped_fresh'] += 1
            elif result == 'cache_hit':
                results['cache_hits'] += 1
                results['processed'] += 1
            else:
                results['api_calls'] += 1
                results['processed'] += 1

            if (i + 1) % 50 == 0:
                logger.info(f"Progress: {i + 1}/{len(tickers)} | "
                            f"processed={results['processed']} skipped={results['skipped_fresh']} "
                            f"failures={len(results['failures'])}")

        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}")
            results['failures'].append({'ticker': ticker, 'error': str(e)})

    results['completed_at'] = datetime.now().isoformat()
    results['total_tickers'] = len(tickers)

    logger.info(f"Pipeline complete: {json.dumps(results, default=str)}")

    # Optionally run aggregator after pipeline completes
    run_aggregator = event.get('run_aggregator', False)
    if run_aggregator and not results.get('stopped_early'):
        try:
            logger.info("Running sp500_aggregator...")
            from src.handlers.sp500_aggregator import lambda_handler as aggregator_handler
            agg_result = aggregator_handler({}, context)
            results['aggregator'] = agg_result
            logger.info(f"Aggregator complete: {agg_result.get('sectors_computed')} sectors")
        except Exception as e:
            logger.error(f"Aggregator failed: {e}")
            results['aggregator_error'] = str(e)

    return results


def _process_ticker(
    ticker: str,
    skip_fresh: bool,
    include_events: bool
) -> str:
    """
    Process a single ticker: fetch data, extract metrics, write to DynamoDB.

    Returns:
        'skipped_fresh' — ticker has recent data, skipped
        'cache_hit' — financial data came from cache
        'api_call' — financial data fetched from FMP API
    """
    from investment_research.index_tickers import to_fmp_format

    fmp_ticker = to_fmp_format(ticker)

    # Check freshness — skip if metrics-history has data < 7 days old
    if skip_fresh and _has_fresh_data(ticker):
        return 'skipped_fresh'

    # Fetch financial data (fmp_client handles caching internally)
    start = time.time()
    financial_data = get_financial_data(fmp_ticker)
    fetch_time = time.time() - start

    raw_financials = financial_data.get('raw_financials', {})
    if not raw_financials:
        raise ValueError(f"No financial data returned for {ticker}")

    currency_info = financial_data.get('currency_info', {})
    currency = currency_info.get('code', 'USD')
    cache_key = financial_data.get('cache_key', f'v3:{ticker}:{datetime.now().year}')

    # Determine if this was a cache hit (fast) or API call (slow)
    was_cache_hit = fetch_time < 2.0  # Cache hits are typically < 0.5s

    # Extract quarterly trends
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Optionally fetch earnings + dividends for event data
    earnings_history = None
    dividend_history = None
    if include_events:
        try:
            earnings_history = fetch_earnings(fmp_ticker)
        except Exception as e:
            logger.warning(f"Failed to fetch earnings for {ticker}: {e}")
        try:
            dividend_history = fetch_dividends(fmp_ticker)
        except Exception as e:
            logger.warning(f"Failed to fetch dividends for {ticker}: {e}")

    # Prepare metrics items (9 categories × up to 20 quarters)
    items = prepare_metrics_for_cache(
        ticker=ticker,
        quarterly_trends=quarterly_trends,
        currency=currency,
        source_cache_key=cache_key,
        earnings_history=earnings_history,
        dividend_history=dividend_history,
    )

    if not items:
        raise ValueError(f"No metrics items generated for {ticker}")

    # Batch write to metrics-history table
    _batch_write_items(items)

    logger.debug(f"Processed {ticker}: {len(items)} items, "
                 f"{'cache_hit' if was_cache_hit else 'api_call'}, {fetch_time:.1f}s")

    return 'cache_hit' if was_cache_hit else 'api_call'


def _has_fresh_data(ticker: str, max_age_days: int = 7) -> bool:
    """Check if metrics-history already has recent data for this ticker."""
    try:
        response = metrics_table.query(
            KeyConditionExpression='ticker = :t',
            ExpressionAttributeValues={':t': ticker},
            ScanIndexForward=False,
            Limit=1,
            ProjectionExpression='ticker, cached_at',
        )
        items = response.get('Items', [])
        if not items:
            return False

        cached_at = items[0].get('cached_at', 0)
        age_seconds = time.time() - float(cached_at)
        age_days = age_seconds / 86400

        if age_days < max_age_days:
            logger.debug(f"{ticker}: fresh data ({age_days:.1f} days old), skipping")
            return True
        return False

    except Exception as e:
        logger.warning(f"Freshness check failed for {ticker}: {e}")
        return False  # On error, process the ticker


def _batch_write_items(items: List[Dict[str, Any]]) -> None:
    """Batch write items to metrics-history table with Decimal conversion."""
    with metrics_table.batch_writer() as batch:
        for item in items:
            item_decimal = json.loads(
                json.dumps(item, default=str),
                parse_float=Decimal
            )
            batch.put_item(Item=item_decimal)
