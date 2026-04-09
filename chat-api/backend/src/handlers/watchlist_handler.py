"""
Watchlist Handler Lambda — Per-user Stock Watchlist with Earnings/Price Tracking

Endpoints (all require JWT authentication):
  PUT /watchlist/{ticker}     — Add ticker to watchlist with price/EPS snapshot
  GET /watchlist               — List watched tickers with computed deltas
  DELETE /watchlist/{ticker}   — Remove ticker from watchlist

Environment Variables:
  WATCHLIST_TABLE             — DynamoDB table for watchlist
  USERS_TABLE                 — DynamoDB table for user records
  STOCK_DATA_4H_TABLE         — DynamoDB table for daily price data
  METRICS_HISTORY_CACHE_TABLE — DynamoDB table for quarterly metrics
  SP500_AGGREGATES_TABLE      — DynamoDB table for earnings events
  ENVIRONMENT                 — dev/staging/prod
  LOG_LEVEL                   — DEBUG/INFO/WARNING
"""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from investment_research.index_tickers import SP500_SECTORS, SP500_TICKERS

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
WATCHLIST_TABLE = os.environ.get('WATCHLIST_TABLE', f'watchlist-buffett-{ENVIRONMENT}')
USERS_TABLE = os.environ.get('USERS_TABLE') or f'buffett-{ENVIRONMENT}-users'
STOCK_DATA_4H_TABLE = os.environ.get('STOCK_DATA_4H_TABLE', f'stock-data-4h-{ENVIRONMENT}')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')

# Watchlist size limits by subscription tier
WATCHLIST_LIMITS = {
    'free': 20,
    'plus': 50,
}

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
watchlist_table = dynamodb.Table(WATCHLIST_TABLE)
users_table = dynamodb.Table(USERS_TABLE)
stock_data_table = dynamodb.Table(STOCK_DATA_4H_TABLE)
metrics_table = dynamodb.Table(METRICS_TABLE)
aggregates_table = dynamodb.Table(AGGREGATES_TABLE)

# Valid ticker set for O(1) lookup
VALID_TICKERS = set(SP500_TICKERS)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda entry point — route by HTTP method and path."""
    http_method = (
        event.get('httpMethod')
        or event.get('requestContext', {}).get('http', {}).get('method')
    )
    path = event.get('path') or event.get('rawPath', '')

    logger.info(f"Watchlist request: {http_method} {path}")

    # Handle OPTIONS preflight (no auth required)
    if http_method == 'OPTIONS':
        return _response(200, {'message': 'CORS preflight OK'})

    # Authenticate
    user_id = _get_user_id(event)
    if not user_id:
        return _response(401, {'error': 'Unauthorized'})

    # Route
    if http_method == 'PUT' and '/watchlist/' in path:
        return _handle_put(user_id, path)
    elif http_method == 'GET' and '/watchlist' in path:
        return _handle_get(user_id)
    elif http_method == 'DELETE' and '/watchlist/' in path:
        return _handle_delete(user_id, path)
    else:
        return _response(404, {'error': 'Not found'})


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_put(user_id: str, path: str) -> Dict[str, Any]:
    """PUT /watchlist/{ticker} — add ticker with price/EPS snapshot."""
    ticker = path.split('/')[-1].upper()

    # Validate ticker
    if ticker not in VALID_TICKERS:
        return _response(400, {'error': f'Invalid ticker: {ticker}. Must be an S&P 500 constituent.'})

    # Check watchlist size limit
    try:
        count_resp = watchlist_table.query(
            KeyConditionExpression=Key('user_id').eq(user_id),
            Select='COUNT',
        )
        current_count = count_resp.get('Count', 0)
    except ClientError as e:
        logger.error(f"Failed to count watchlist items: {e}")
        return _response(500, {'error': 'Failed to check watchlist size'})

    tier = _get_subscription_tier(user_id)
    limit = WATCHLIST_LIMITS.get(tier, WATCHLIST_LIMITS['free'])

    if current_count >= limit:
        return _response(409, {
            'error': 'Watchlist limit reached',
            'message': f'Your {tier} plan allows up to {limit} tickers. Remove a ticker or upgrade.',
            'limit': limit,
            'current_count': current_count,
        })

    # Snapshot current price
    close_price, price_date = _get_latest_price(ticker)

    # Snapshot latest EPS
    eps_actual, eps_estimated, fiscal_date, fiscal_quarter = _get_latest_eps(ticker)

    # Company info
    company_info = SP500_SECTORS.get(ticker, {})

    now = datetime.now(timezone.utc).isoformat()
    item = {
        'user_id': user_id,
        'ticker': ticker,
        'added_at': now,
        'company_name': company_info.get('name', ticker),
        'sector': company_info.get('sector', 'Unknown'),
        'industry': company_info.get('industry', 'Unknown'),
        'snapshot_price': Decimal(str(close_price)) if close_price is not None else None,
        'snapshot_price_date': price_date,
        'snapshot_eps': Decimal(str(eps_actual)) if eps_actual is not None else None,
        'snapshot_eps_estimated': Decimal(str(eps_estimated)) if eps_estimated is not None else None,
        'snapshot_fiscal_date': fiscal_date,
        'snapshot_fiscal_quarter': fiscal_quarter,
        'updated_at': now,
        'expires_at': int(datetime.now(timezone.utc).timestamp()) + (365 * 24 * 3600),
    }
    # Remove None values — DynamoDB rejects None
    item = {k: v for k, v in item.items() if v is not None}

    try:
        watchlist_table.put_item(Item=item)
    except ClientError as e:
        logger.error(f"Failed to put watchlist item: {e}")
        return _response(500, {'error': 'Failed to add ticker to watchlist'})

    return _response(201, item)


def _handle_get(user_id: str) -> Dict[str, Any]:
    """GET /watchlist — list watched tickers with computed deltas."""
    try:
        resp = watchlist_table.query(
            KeyConditionExpression=Key('user_id').eq(user_id),
        )
        items = resp.get('Items', [])
    except ClientError as e:
        logger.error(f"Failed to query watchlist: {e}")
        return _response(500, {'error': 'Failed to retrieve watchlist'})

    if not items:
        return _response(200, {'watchlist': [], 'count': 0})

    # Enrich each item with current data in parallel
    def _enrich(item: Dict[str, Any]) -> Dict[str, Any]:
        ticker = item['ticker']
        enriched = dict(item)

        # Current price
        current_price, current_price_date = _get_latest_price(ticker)
        enriched['current_price'] = Decimal(str(current_price)) if current_price is not None else None
        enriched['current_price_date'] = current_price_date

        # Price change delta
        snapshot_price = item.get('snapshot_price')
        if current_price is not None and snapshot_price is not None and snapshot_price != 0:
            enriched['price_change_pct'] = round(
                float((Decimal(str(current_price)) - snapshot_price) / snapshot_price * 100), 2
            )
        else:
            enriched['price_change_pct'] = None

        # Current EPS
        latest_eps, latest_eps_est, latest_fiscal_date, latest_fiscal_quarter = _get_latest_eps(ticker)
        enriched['current_eps'] = Decimal(str(latest_eps)) if latest_eps is not None else None
        enriched['current_eps_estimated'] = Decimal(str(latest_eps_est)) if latest_eps_est is not None else None
        enriched['current_fiscal_date'] = latest_fiscal_date
        enriched['current_fiscal_quarter'] = latest_fiscal_quarter

        # EPS change delta
        snapshot_eps = item.get('snapshot_eps')
        if latest_eps is not None and snapshot_eps is not None and snapshot_eps != 0:
            enriched['eps_change_pct'] = round(
                float((Decimal(str(latest_eps)) - snapshot_eps) / snapshot_eps * 100), 2
            )
        else:
            enriched['eps_change_pct'] = None

        # Next earnings date (optional)
        enriched['next_earnings_date'] = _get_next_earnings_date(ticker)

        # Strip None values for clean response
        return {k: v for k, v in enriched.items() if v is not None}

    with ThreadPoolExecutor(max_workers=10) as executor:
        enriched_items = list(executor.map(_enrich, items))

    return _response(200, {'watchlist': enriched_items, 'count': len(enriched_items)})


def _handle_delete(user_id: str, path: str) -> Dict[str, Any]:
    """DELETE /watchlist/{ticker} — remove ticker from watchlist."""
    ticker = path.split('/')[-1].upper()

    try:
        watchlist_table.delete_item(Key={'user_id': user_id, 'ticker': ticker})
    except ClientError as e:
        logger.error(f"Failed to delete watchlist item: {e}")
        return _response(500, {'error': 'Failed to remove ticker from watchlist'})

    return _response(200, {'message': f'{ticker} removed from watchlist'})


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _get_latest_price(ticker: str):
    """Query stock-data-4h for the most recent close price.

    Returns:
        (close_price, date_str) or (None, None)
    """
    try:
        resp = stock_data_table.query(
            KeyConditionExpression=Key('PK').eq(f'TICKER#{ticker}'),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get('Items', [])
        if not items:
            return None, None
        item = items[0]
        close_price = item.get('close')
        # SK format: DAILY#2026-04-09
        sk = item.get('SK', '')
        date_str = sk.replace('DAILY#', '') if sk.startswith('DAILY#') else sk
        return float(close_price) if close_price is not None else None, date_str
    except ClientError as e:
        logger.warning(f"Failed to get price for {ticker}: {e}")
        return None, None


def _get_latest_eps(ticker: str):
    """Query metrics-history for the latest fiscal quarter's earnings.

    Returns:
        (eps_actual, eps_estimated, fiscal_date, fiscal_quarter) or (None, None, None, None)
    """
    try:
        resp = metrics_table.query(
            KeyConditionExpression=Key('ticker').eq(ticker),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get('Items', [])
        if not items:
            return None, None, None, None
        item = items[0]
        earnings = item.get('earnings_events', {})
        if isinstance(earnings, str):
            try:
                earnings = json.loads(earnings)
            except (json.JSONDecodeError, TypeError):
                earnings = {}
        eps_actual = earnings.get('eps_actual')
        eps_estimated = earnings.get('eps_estimated')
        fiscal_date = item.get('fiscal_date', '')
        fiscal_quarter = item.get('fiscal_quarter')
        return (
            float(eps_actual) if eps_actual is not None else None,
            float(eps_estimated) if eps_estimated is not None else None,
            fiscal_date,
            fiscal_quarter,
        )
    except ClientError as e:
        logger.warning(f"Failed to get EPS for {ticker}: {e}")
        return None, None, None, None


def _get_next_earnings_date(ticker: str) -> Optional[str]:
    """Query sp500-aggregates EARNINGS_UPCOMING for next earnings date."""
    try:
        resp = aggregates_table.query(
            KeyConditionExpression=Key('aggregate_type').eq('EARNINGS_UPCOMING') & Key('aggregate_key').begins_with(ticker),
            Limit=1,
        )
        items = resp.get('Items', [])
        if items:
            return items[0].get('earnings_date') or items[0].get('aggregate_key')
        return None
    except ClientError as e:
        logger.warning(f"Failed to get next earnings for {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# Auth / user helpers
# ---------------------------------------------------------------------------

def _get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """Extract user_id from JWT authorizer context."""
    authorizer = event.get('requestContext', {}).get('authorizer', {})

    # HTTP API v2 with Lambda authorizer
    if 'lambda' in authorizer and isinstance(authorizer['lambda'], dict):
        user_id = authorizer['lambda'].get('user_id')
        if user_id:
            return str(user_id)

    # Direct authorizer context
    if isinstance(authorizer, dict):
        user_id = authorizer.get('user_id')
        if user_id:
            return str(user_id)

    return None


def _get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user record from DynamoDB."""
    try:
        response = users_table.get_item(Key={'user_id': user_id})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Failed to get user: {e}")
        return None


def _get_subscription_tier(user_id: str) -> str:
    """Return the user's subscription tier ('free' or 'plus')."""
    user = _get_user(user_id)
    if user and user.get('subscription_tier') == 'plus':
        subscription_status = user.get('subscription_status')
        if subscription_status in ('active', 'trialing'):
            return 'plus'
    return 'free'


# ---------------------------------------------------------------------------
# Response helper
# ---------------------------------------------------------------------------

def _response(status_code: int, body: Any) -> Dict[str, Any]:
    """Create API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json',
        },
        'body': json.dumps(body, cls=DecimalEncoder),
    }
