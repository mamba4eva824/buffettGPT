"""
Earnings Update Lambda — Daily Automated Earnings Ingestion

Checks the FMP earnings calendar for S&P 500 companies that recently reported,
then fetches full financials + earnings + dividends + TTM valuations and updates
the metrics-history DynamoDB table via update_item (preserves existing attributes).

Runs twice daily via EventBridge:
  - 9 PM UTC (6 PM ET) — catches after-hours earnings reports
  - 4:30 PM UTC (11:30 AM ET) — catches pre-market earnings reports

Event payload options:
  {}                                — auto mode: check calendar, process recently reported
  {"tickers": ["AAPL", "MSFT"]}    — manual mode: skip calendar, process specific tickers
  {"lookback_days": 3}             — custom calendar lookback window (default: 2)
  {"include_upcoming": true}       — also return upcoming earnings in response

Response includes structured data for future notifications:
  {
    "tickers_checked": 12,
    "tickers_updated": ["AAPL", "MSFT"],
    "results": [{"ticker": "AAPL", "earnings_date": "...", "eps_beat": true, ...}],
    "upcoming": [{"ticker": "NVDA", "earnings_date": "2026-05-20", "eps_estimated": 1.75}]
  }

Environment Variables:
  FMP_SECRET_NAME              — Secrets Manager name for FMP API key
  METRICS_HISTORY_CACHE_TABLE  — DynamoDB table for quarterly metrics
  ENVIRONMENT                  — dev/staging/prod
  LOG_LEVEL                    — DEBUG/INFO/WARNING
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

import boto3
import httpx

from utils.fmp_client import (
    get_financial_data,
    fetch_earnings,
    fetch_dividends,
    fetch_ttm_valuations,
)
from utils.feature_extractor import extract_quarterly_trends, prepare_metrics_for_cache

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_RATE_LIMIT_DELAY = 0.5  # Seconds between FMP calls (300 calls/min limit)

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------
dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)
secrets_client = boto3.client('secretsmanager')

_fmp_api_key = None


def _get_fmp_api_key() -> str:
    global _fmp_api_key
    if _fmp_api_key is None:
        response = secrets_client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        _fmp_api_key = secret['FMP_API_KEY']
    return _fmp_api_key


# ---------------------------------------------------------------------------
# Earnings Calendar
# ---------------------------------------------------------------------------
def _check_earnings_calendar(lookback_days: int = 2) -> Dict[str, List]:
    """
    Check FMP earnings calendar for S&P 500 tickers that recently reported.

    Returns dict with 'reported' (tickers with new earnings) and 'upcoming'.
    """
    from investment_research.index_tickers import SP500_TICKERS, to_fmp_format

    api_key = _get_fmp_api_key()
    sp500_fmp = {to_fmp_format(t): t for t in SP500_TICKERS}

    today = datetime.now()
    from_date = (today - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    to_date = (today + timedelta(days=7)).strftime('%Y-%m-%d')

    url = "https://financialmodelingprep.com/stable/earnings-calendar"
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params={
            'from': from_date,
            'to': to_date,
            'apikey': api_key,
        })
        response.raise_for_status()
        calendar = response.json()

    today_str = today.strftime('%Y-%m-%d')
    reported = []
    upcoming = []

    for entry in calendar:
        fmp_symbol = entry.get('symbol', '')
        if fmp_symbol not in sp500_fmp:
            continue

        original_ticker = sp500_fmp[fmp_symbol]
        earnings_date = entry.get('date', '')

        record = {
            'ticker': original_ticker,
            'fmp_ticker': fmp_symbol,
            'earnings_date': earnings_date,
            'eps_estimated': entry.get('epsEstimated'),
            'revenue_estimated': entry.get('revenueEstimated'),
        }

        if earnings_date <= today_str:
            reported.append(record)
        else:
            upcoming.append(record)

    logger.info(f"Earnings calendar: {len(reported)} reported, {len(upcoming)} upcoming "
                f"(checked {from_date} to {to_date})")

    return {
        'reported': reported,
        'upcoming': sorted(upcoming, key=lambda x: x['earnings_date']),
    }


# ---------------------------------------------------------------------------
# Per-Ticker Processing
# ---------------------------------------------------------------------------
def _process_ticker(ticker: str) -> Dict[str, Any]:
    """
    Fetch full financials + earnings + dividends + TTM for a single ticker
    and update all categories in metrics-history via update_item.

    Returns a summary dict for the response.
    """
    from investment_research.index_tickers import to_fmp_format

    fmp_ticker = to_fmp_format(ticker)
    result = {'ticker': ticker, 'status': 'success'}

    # 1. Fetch financial data (income, balance sheet, cash flow)
    financial_data = get_financial_data(fmp_ticker)
    raw_financials = financial_data.get('raw_financials', {})
    if not raw_financials:
        result['status'] = 'no_financial_data'
        return result

    currency = financial_data.get('currency_info', {}).get('code', 'USD')
    cache_key = financial_data.get('cache_key', f'v3:{ticker}:{datetime.now().year}')

    # 2. Extract quarterly trends (78 metrics across 7 categories)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # 3. Fetch earnings + dividends (always — this is the whole point)
    earnings_history = None
    dividend_history = None
    try:
        earnings_history = fetch_earnings(fmp_ticker)
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch earnings for {ticker}: {e}")

    try:
        dividend_history = fetch_dividends(fmp_ticker)
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch dividends for {ticker}: {e}")

    # 4. Prepare items (7 base categories + earnings_events + dividend)
    items = prepare_metrics_for_cache(
        ticker=ticker,
        quarterly_trends=quarterly_trends,
        currency=currency,
        source_cache_key=cache_key,
        earnings_history=earnings_history,
        dividend_history=dividend_history,
    )

    if not items:
        result['status'] = 'no_items_generated'
        return result

    # 5. Fetch TTM valuations and attach to latest quarter
    try:
        ttm = fetch_ttm_valuations(fmp_ticker)
        if ttm:
            latest_item = max(items, key=lambda x: x.get('fiscal_date', ''))
            latest_item['market_valuation'] = ttm
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch TTM for {ticker}: {e}")

    # 6. Write all categories via update_item (preserves existing attributes)
    _update_items(items)

    # 7. Build result summary
    latest = max(items, key=lambda x: x.get('fiscal_date', ''))
    ee = latest.get('earnings_events', {})
    result.update({
        'quarters_written': len(items),
        'latest_fiscal_date': latest.get('fiscal_date'),
        'latest_fiscal_quarter': latest.get('fiscal_quarter'),
        'earnings_date': ee.get('earnings_date'),
        'eps_actual': float(ee['eps_actual']) if ee.get('eps_actual') is not None else None,
        'eps_estimated': float(ee['eps_estimated']) if ee.get('eps_estimated') is not None else None,
        'eps_beat': ee.get('eps_beat'),
        'eps_surprise_pct': float(ee['eps_surprise_pct']) if ee.get('eps_surprise_pct') is not None else None,
        'has_market_valuation': 'market_valuation' in latest,
    })

    return result


# ---------------------------------------------------------------------------
# DynamoDB update_item (safe writes — preserves existing attributes)
# ---------------------------------------------------------------------------
ALL_CATEGORIES = [
    'revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
    'earnings_quality', 'dilution', 'valuation',
    'earnings_events', 'dividend', 'market_valuation',
]
META_FIELDS = ['fiscal_year', 'fiscal_quarter', 'currency', 'source_cache_key', 'cached_at', 'expires_at']


def _update_items(items: List[Dict[str, Any]]) -> None:
    """
    Update items in metrics-history using update_item (not put_item).
    Preserves existing attributes not included in the current write.
    """
    for item in items:
        ticker = item.get('ticker')
        fiscal_date = item.get('fiscal_date')
        if not ticker or not fiscal_date:
            continue

        item_decimal = json.loads(
            json.dumps(item, default=str),
            parse_float=Decimal
        )

        set_parts = []
        attr_values = {}
        attr_names = {}

        for field in META_FIELDS:
            if field in item_decimal:
                safe_name = f'#{field}'
                safe_val = f':{field}'
                set_parts.append(f'{safe_name} = {safe_val}')
                attr_names[safe_name] = field
                attr_values[safe_val] = item_decimal[field]

        for category in ALL_CATEGORIES:
            if category in item_decimal:
                safe_name = f'#{category}'
                safe_val = f':{category}'
                set_parts.append(f'{safe_name} = {safe_val}')
                attr_names[safe_name] = category
                attr_values[safe_val] = item_decimal[category]

        if not set_parts:
            continue

        try:
            metrics_table.update_item(
                Key={'ticker': ticker, 'fiscal_date': fiscal_date},
                UpdateExpression='SET ' + ', '.join(set_parts),
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
        except Exception as e:
            logger.error(f"Failed to update {ticker}/{fiscal_date}: {e}")


# ---------------------------------------------------------------------------
# SNS Notifications
# ---------------------------------------------------------------------------
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
_sns_client = None


def _get_sns_client():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client('sns')
    return _sns_client


def _publish_sns_summary(response: Dict[str, Any]) -> None:
    """Publish a run summary to SNS. Failures are logged but never raise."""
    if not SNS_TOPIC_ARN:
        return
    try:
        updated = response.get('total_updated', 0)
        failures = response.get('total_failures', 0)
        mode = response.get('mode', 'unknown')
        checked = response.get('tickers_checked', 0)

        if checked == 0 and not response.get('tickers_updated'):
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: No tickers to process"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: NO WORK\n"
                f"No companies recently reported earnings."
            )
        elif failures > 0:
            failed_tickers = ', '.join(f.get('ticker', '?') for f in response.get('failures', []))
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: {updated} updated, {failures} failed"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: COMPLETED WITH ERRORS\n"
                f"Tickers checked: {checked}\n"
                f"Tickers updated: {', '.join(response.get('tickers_updated', []))}\n"
                f"Failures ({failures}): {failed_tickers}"
            )
        else:
            tickers_list = ', '.join(response.get('tickers_updated', []))
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: {updated} updated"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: SUCCESS\n"
                f"Tickers checked: {checked}\n"
                f"Tickers updated ({updated}): {tickers_list}"
            )

        _get_sns_client().publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
    except Exception as e:
        logger.warning(f"Failed to publish SNS notification: {e}")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entry point. Triggered by EventBridge twice daily or manually.

    Auto mode (default): checks earnings calendar, processes recently reported tickers.
    Manual mode: processes specific tickers from event payload.
    """
    manual_tickers = event.get('tickers')
    lookback_days = event.get('lookback_days', 2)
    include_upcoming = event.get('include_upcoming', True)

    response = {
        'mode': 'manual' if manual_tickers else 'auto',
        'started_at': datetime.now().isoformat(),
        'tickers_updated': [],
        'results': [],
        'failures': [],
    }

    # Determine which tickers to process
    if manual_tickers:
        tickers_to_process = sorted(manual_tickers)
        logger.info(f"Manual mode: processing {len(tickers_to_process)} tickers")
    else:
        calendar = _check_earnings_calendar(lookback_days)
        tickers_to_process = sorted(set(r['ticker'] for r in calendar['reported']))
        if include_upcoming:
            response['upcoming'] = calendar['upcoming']
        logger.info(f"Auto mode: {len(tickers_to_process)} tickers recently reported")

    response['tickers_checked'] = len(tickers_to_process)

    if not tickers_to_process:
        response['message'] = 'No tickers to process'
        logger.info("No tickers to process — no recent earnings reports")
        _publish_sns_summary(response)
        return response

    # Process each ticker
    for i, ticker in enumerate(tickers_to_process):
        # Check Lambda timeout (leave 30s buffer)
        if context and hasattr(context, 'get_remaining_time_in_millis'):
            remaining_ms = context.get_remaining_time_in_millis()
            if remaining_ms < 30_000:
                logger.warning(f"Timeout approaching at ticker {i}/{len(tickers_to_process)}")
                response['stopped_early'] = True
                break

        try:
            result = _process_ticker(ticker)
            response['results'].append(result)
            if result['status'] == 'success':
                response['tickers_updated'].append(ticker)

            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(tickers_to_process)} processed")

        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}")
            response['failures'].append({'ticker': ticker, 'error': str(e)})

        # Rate limit between tickers
        if i + 1 < len(tickers_to_process):
            time.sleep(FMP_RATE_LIMIT_DELAY)

    response['completed_at'] = datetime.now().isoformat()
    response['total_updated'] = len(response['tickers_updated'])
    response['total_failures'] = len(response['failures'])

    logger.info(f"Earnings update complete: {response['total_updated']} updated, "
                f"{response['total_failures']} failures")

    _publish_sns_summary(response)
    return response
