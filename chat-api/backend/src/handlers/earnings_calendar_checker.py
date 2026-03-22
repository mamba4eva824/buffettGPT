"""
Earnings Calendar Checker — Placeholder Lambda

Fetches the FMP earnings calendar and cross-references with S&P 500 tickers
to identify companies that have recently reported or are about to report
quarterly earnings.

This is a PLACEHOLDER for future scheduling:
- Currently: logs tickers that need data refresh
- Future: triggers sp500_pipeline Lambda for stale tickers via EventBridge

FMP endpoint: /stable/earnings-calendar (available on Starter tier)

Invocation: manual or EventBridge daily schedule (disabled by default).
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List

import httpx

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')

# Cache the API key in Lambda memory
_fmp_api_key = None


def _get_fmp_api_key() -> str:
    """Fetch FMP API key from Secrets Manager (cached per Lambda instance)."""
    global _fmp_api_key
    if _fmp_api_key:
        return _fmp_api_key

    import boto3
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=FMP_SECRET_NAME)
    _fmp_api_key = response['SecretString']
    return _fmp_api_key


def fetch_earnings_calendar(from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """
    Fetch earnings calendar from FMP API.

    Args:
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)

    Returns:
        List of earnings calendar entries with fields:
        date, symbol, eps, epsEstimated, revenue, revenueEstimated, etc.
    """
    api_key = _get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/earnings-calendar"
    params = {
        'from': from_date,
        'to': to_date,
        'apikey': api_key,
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Check earnings calendar and identify S&P 500 tickers needing refresh.

    Event payload options:
        {} — check last 7 days + next 7 days
        {"lookback_days": 14} — custom lookback window
        {"lookahead_days": 7} — custom lookahead window
    """
    from investment_research.index_tickers import SP500_TICKERS, to_fmp_format

    lookback_days = event.get('lookback_days', 7)
    lookahead_days = event.get('lookahead_days', 7)

    today = datetime.now()
    from_date = (today - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    to_date = (today + timedelta(days=lookahead_days)).strftime('%Y-%m-%d')

    logger.info(f"Checking earnings calendar: {from_date} to {to_date}")

    # Build set of SP500 tickers in FMP format for fast lookup
    sp500_set = set(to_fmp_format(t) for t in SP500_TICKERS)

    # Fetch calendar
    try:
        calendar = fetch_earnings_calendar(from_date, to_date)
    except Exception as e:
        logger.error(f"Failed to fetch earnings calendar: {e}")
        return {'error': str(e)}

    logger.info(f"Earnings calendar returned {len(calendar)} entries")

    # Filter to S&P 500 tickers
    sp500_earnings = []
    for entry in calendar:
        symbol = entry.get('symbol', '')
        if symbol in sp500_set:
            sp500_earnings.append({
                'ticker': symbol,
                'date': entry.get('date', ''),
                'eps': entry.get('eps'),
                'eps_estimated': entry.get('epsEstimated'),
                'revenue': entry.get('revenue'),
                'revenue_estimated': entry.get('revenueEstimated'),
            })

    # Split into past (reported) and future (upcoming)
    today_str = today.strftime('%Y-%m-%d')
    recently_reported = [e for e in sp500_earnings if e['date'] <= today_str]
    upcoming = [e for e in sp500_earnings if e['date'] > today_str]

    # Tickers that need data refresh (recently reported new earnings)
    tickers_to_refresh = sorted(set(e['ticker'] for e in recently_reported))

    logger.info(f"S&P 500 earnings: {len(recently_reported)} reported, "
                f"{len(upcoming)} upcoming")
    logger.info(f"Tickers needing refresh: {len(tickers_to_refresh)}")
    if tickers_to_refresh:
        logger.info(f"Refresh list: {tickers_to_refresh}")

    # PLACEHOLDER: In the future, this would trigger sp500_pipeline
    # for the tickers_to_refresh list via:
    # - Direct Lambda invoke
    # - SQS message
    # - EventBridge target
    #
    # For now, just log and return the list.

    return {
        'checked_range': {'from': from_date, 'to': to_date},
        'total_calendar_entries': len(calendar),
        'sp500_recently_reported': len(recently_reported),
        'sp500_upcoming': len(upcoming),
        'tickers_to_refresh': tickers_to_refresh,
        'upcoming_tickers': sorted(set(e['ticker'] for e in upcoming)),
        'checked_at': today.isoformat(),
    }
