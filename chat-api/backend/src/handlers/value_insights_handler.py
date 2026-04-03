"""
Value Insights Handler
Serves financial metrics and ratings for the Value Insights frontend.
"""

import json
import boto3
import logging
import os
from decimal import Decimal
from typing import Dict, Any

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

dynamodb = boto3.resource('dynamodb')

METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', 'metrics-history-dev')
REPORTS_TABLE = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
STOCK_DATA_4H_TABLE = os.environ.get('STOCK_DATA_4H_TABLE', '')

metrics_table = dynamodb.Table(METRICS_TABLE)
reports_table = dynamodb.Table(REPORTS_TABLE)


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
    Fetch the most recent closing price from the stock-data-4h table.
    Returns {price, date, datetime} or None if unavailable.
    """
    if not STOCK_DATA_4H_TABLE:
        return None

    try:
        table = dynamodb.Table(STOCK_DATA_4H_TABLE)
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('PK').eq(f'TICKER#{ticker}'),
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
            'datetime': item.get('datetime', ''),
            'open': float(item.get('open', 0)),
            'high': float(item.get('high', 0)),
            'low': float(item.get('low', 0)),
            'volume': item.get('volume', 0),
        }
    except Exception as e:
        logger.warning(f"Failed to fetch latest price for {ticker}: {e}")
        return None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    route_key = event.get('routeKey', '')
    path_params = event.get('pathParameters') or {}
    http_method = event.get('requestContext', {}).get('http', {}).get('method', '')

    if http_method == 'OPTIONS':
        return _response(200, {})

    ticker = path_params.get('ticker', '').upper().strip()
    if not ticker:
        return _response(400, {'error': 'Missing ticker parameter'})

    try:
        metrics = _get_metrics(ticker)
        ratings = _get_ratings(ticker)
        latest_price = _get_latest_price(ticker)

        return _response(200, {
            'ticker': ticker,
            'metrics': metrics,
            'ratings': ratings,
            'quarters_available': len(metrics),
            'latest_price': latest_price,
        })
    except Exception as e:
        logger.exception(f"Error fetching insights for {ticker}")
        return _response(500, {'error': 'Internal server error'})
