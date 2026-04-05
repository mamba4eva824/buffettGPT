"""
Value Insights Handler
Serves financial metrics and ratings for the Value Insights frontend.
"""

import json
import boto3
import logging
import os
import urllib3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

dynamodb = boto3.resource('dynamodb')

METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', 'metrics-history-dev')
REPORTS_TABLE = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
STOCK_DATA_4H_TABLE = os.environ.get('STOCK_DATA_4H_TABLE', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')

FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

metrics_table = dynamodb.Table(METRICS_TABLE)
reports_table = dynamodb.Table(REPORTS_TABLE)

secrets_client = boto3.client('secretsmanager')
http = urllib3.PoolManager()
_fmp_api_key: str | None = None


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            f = float(obj)
            if f == int(f):
                return int(f)
            return f
        return super().default(obj)


def _cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'content-type,authorization',
        'Access-Control-Allow-Methods': 'GET,OPTIONS',
    }


def _response(status_code: int, body: Any) -> Dict:
    return {
        'statusCode': status_code,
        'headers': {**_cors_headers(), 'Content-Type': 'application/json'},
        'body': json.dumps(body, cls=DecimalEncoder),
    }


def _get_metrics(ticker: str) -> list:
    response = metrics_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('ticker').eq(ticker),
        ScanIndexForward=True,
        Limit=24,
    )
    return response.get('Items', [])


def _get_ratings(ticker: str) -> dict | None:
    response = reports_table.get_item(
        Key={'ticker': ticker, 'section_id': '00_executive'},
    )
    item = response.get('Item')
    if not item:
        return None

    ratings = item.get('ratings')
    if ratings is None:
        return None

    # Handle both JSON string and dict formats
    if isinstance(ratings, str):
        try:
            ratings = json.loads(ratings)
        except (json.JSONDecodeError, TypeError):
            return None

    return ratings


def _get_latest_price(ticker: str) -> dict | None:
    """
    Fetch the most recent daily closing price from the stock-data-4h table.
    Queries DAILY# prefixed records (daily EOD data).
    Returns {price, date, change_percent, ...} or None if unavailable.
    """
    if not STOCK_DATA_4H_TABLE:
        return None

    try:
        table = dynamodb.Table(STOCK_DATA_4H_TABLE)
        response = table.query(
            KeyConditionExpression=(
                boto3.dynamodb.conditions.Key('PK').eq(f'TICKER#{ticker}')
                & boto3.dynamodb.conditions.Key('SK').begins_with('DAILY#')
            ),
            ScanIndexForward=False,  # Most recent first
            Limit=1,
        )
        items = response.get('Items', [])
        if not items:
            return None

        item = items[0]
        return {
            'price': float(item.get('close', 0)),
            'date': item.get('date', ''),
            'open': float(item.get('open', 0)),
            'high': float(item.get('high', 0)),
            'low': float(item.get('low', 0)),
            'volume': item.get('volume', 0),
            'change': float(item.get('change', 0)),
            'change_percent': float(item.get('change_percent', 0)),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch latest price for {ticker}: {e}")
        return None


def _get_sector_aggregate(sector: str) -> dict | None:
    """Fetch sector-level aggregate metrics from sp500-aggregates table."""
    try:
        table = dynamodb.Table(AGGREGATES_TABLE)
        response = table.get_item(
            Key={'aggregate_type': 'SECTOR', 'aggregate_key': sector}
        )
        return response.get('Item')
    except Exception as e:
        logger.warning(f"Failed to fetch sector aggregate for {sector}: {e}")
        return None


def _get_fmp_api_key() -> str:
    global _fmp_api_key
    if _fmp_api_key is None:
        response = secrets_client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        _fmp_api_key = secret['FMP_API_KEY']
    return _fmp_api_key


def _fetch_daily_prices_from_fmp(ticker: str) -> List[Dict]:
    """Fetch 5 years of daily prices from FMP. Returns list sorted oldest-first."""
    try:
        api_key = _get_fmp_api_key()
        fmp_ticker = ticker.replace('.', '-')
        url = f"{FMP_BASE_URL}/historical-price-eod/full?symbol={fmp_ticker}&apikey={api_key}"
        resp = http.request("GET", url, timeout=15.0)
        if resp.status != 200:
            return []
        data = json.loads(resp.data.decode("utf-8"))
        if not isinstance(data, list):
            return []
        # FMP returns newest first — reverse to oldest first
        return list(reversed(data))
    except Exception as e:
        logger.warning(f"Failed to fetch daily prices for {ticker}: {e}")
        return []


def _compute_post_earnings(metrics: List[Dict], daily_prices: List[Dict]) -> List[Dict]:
    """
    Compute post-earnings price performance for each quarter with reported earnings.

    For each quarter with earnings_events.earnings_date + eps_actual:
    - Find the closing price on (or nearest to) earnings date
    - Compute 1-day, 5-day, and 30-day % change after earnings

    Returns list of dicts sorted most recent first.
    """
    # Build date→price lookup (empty if no prices available)
    price_by_date = {p.get('date'): p for p in daily_prices}
    sorted_dates = sorted(price_by_date.keys())

    def find_price_on_or_after(target_date: str, max_offset: int = 5) -> Optional[Dict]:
        """Find closing price on target date or nearest trading day after."""
        for i, d in enumerate(sorted_dates):
            if d >= target_date:
                return price_by_date[d]
        return None

    def find_price_n_days_after(target_date: str, trading_days: int) -> Optional[Dict]:
        """Find price N trading days after target date."""
        start_idx = None
        for i, d in enumerate(sorted_dates):
            if d >= target_date:
                start_idx = i
                break
        if start_idx is None:
            return None
        target_idx = start_idx + trading_days
        if target_idx < len(sorted_dates):
            return price_by_date[sorted_dates[target_idx]]
        return None

    def pct_change(before: float, after: float) -> Optional[float]:
        if before and after and before > 0:
            return round(((after - before) / before) * 100, 2)
        return None

    results = []
    for item in metrics:
        ee = item.get('earnings_events', {})
        earnings_date = ee.get('earnings_date')
        eps_actual = ee.get('eps_actual')

        if not earnings_date or eps_actual is None:
            continue

        # Price on earnings day (close)
        price_on_day = find_price_on_or_after(earnings_date)
        if not price_on_day:
            # No price data for this earnings date range
            results.append({
                'fiscal_date': item.get('fiscal_date'),
                'fiscal_quarter': item.get('fiscal_quarter'),
                'fiscal_year': item.get('fiscal_year'),
                'earnings_date': earnings_date,
                'eps_actual': float(eps_actual),
                'eps_estimated': float(ee['eps_estimated']) if ee.get('eps_estimated') else None,
                'eps_surprise_pct': float(ee['eps_surprise_pct']) if ee.get('eps_surprise_pct') else None,
                'eps_beat': ee.get('eps_beat'),
                'revenue_actual': float(ee['revenue_actual']) if ee.get('revenue_actual') else None,
                'revenue_estimated': float(ee['revenue_estimated']) if ee.get('revenue_estimated') else None,
                'revenue_surprise_pct': float(ee['revenue_surprise_pct']) if ee.get('revenue_surprise_pct') else None,
                'price_on_earnings_date': None,
                'price_change_1d': None,
                'price_change_5d': None,
                'price_change_30d': None,
            })
            continue

        close_price = float(price_on_day.get('close', 0))

        # 1-day, 5-day, 30-day (trading days) after earnings
        price_1d = find_price_n_days_after(earnings_date, 1)
        price_5d = find_price_n_days_after(earnings_date, 5)
        price_30d = find_price_n_days_after(earnings_date, 21)  # ~30 calendar days = ~21 trading days

        results.append({
            'fiscal_date': item.get('fiscal_date'),
            'fiscal_quarter': item.get('fiscal_quarter'),
            'fiscal_year': item.get('fiscal_year'),
            'earnings_date': earnings_date,
            'eps_actual': float(eps_actual),
            'eps_estimated': float(ee['eps_estimated']) if ee.get('eps_estimated') else None,
            'eps_surprise_pct': float(ee['eps_surprise_pct']) if ee.get('eps_surprise_pct') else None,
            'eps_beat': ee.get('eps_beat'),
            'revenue_actual': float(ee['revenue_actual']) if ee.get('revenue_actual') else None,
            'revenue_estimated': float(ee['revenue_estimated']) if ee.get('revenue_estimated') else None,
            'revenue_surprise_pct': float(ee['revenue_surprise_pct']) if ee.get('revenue_surprise_pct') else None,
            'price_on_earnings_date': close_price,
            'price_change_1d': pct_change(close_price, float(price_1d['close'])) if price_1d else None,
            'price_change_5d': pct_change(close_price, float(price_5d['close'])) if price_5d else None,
            'price_change_30d': pct_change(close_price, float(price_30d['close'])) if price_30d else None,
        })

    # Most recent first
    results.sort(key=lambda x: x.get('earnings_date', ''), reverse=True)
    return results


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    route_key = event.get('routeKey', '')
    path_params = event.get('pathParameters') or {}
    http_method = event.get('requestContext', {}).get('http', {}).get('method', '')

    if http_method == 'OPTIONS':
        return _response(200, {})

    ticker = path_params.get('ticker', '').upper().strip()
    if not ticker:
        return _response(400, {'error': 'Missing ticker parameter'})

    # Optional sector query param for fetching sector aggregates
    qs = event.get('queryStringParameters') or {}
    sector = qs.get('sector', '')

    try:
        metrics = _get_metrics(ticker)
        ratings = _get_ratings(ticker)
        latest_price = _get_latest_price(ticker)
        sector_aggregate = _get_sector_aggregate(sector) if sector else None

        # Compute post-earnings performance using FMP daily prices
        daily_prices = _fetch_daily_prices_from_fmp(ticker)
        post_earnings = _compute_post_earnings(metrics, daily_prices)

        return _response(200, {
            'ticker': ticker,
            'metrics': metrics,
            'ratings': ratings,
            'quarters_available': len(metrics),
            'latest_price': latest_price,
            'sector_aggregate': sector_aggregate,
            'post_earnings': post_earnings,
        })
    except Exception as e:
        logger.exception(f"Error fetching insights for {ticker}")
        return _response(500, {'error': 'Internal server error'})
