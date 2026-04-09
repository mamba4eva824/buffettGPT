"""
Earnings Feed Handler — API for the Earnings Tracker Dashboard

Serves three endpoints:
  GET /earnings/recent   — Recent earnings results (beat/miss feed)
  GET /earnings/upcoming — Upcoming S&P 500 earnings calendar
  GET /earnings/season   — Sector-level earnings season summary

Data sources:
  - sp500-aggregates table (EARNINGS_RECENT, EARNINGS_UPCOMING partitions)
  - sp500-aggregates table (SECTOR partitions for season summary)
  - sp500-aggregates table (RANKING partitions for top beats/misses)

Environment Variables:
  SP500_AGGREGATES_TABLE  — DynamoDB table for aggregates (default: buffett-{env}-sp500-aggregates)
  ENVIRONMENT             — dev/staging/prod
  LOG_LEVEL               — DEBUG/INFO/WARNING
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Key

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------
dynamodb = boto3.resource('dynamodb')
aggregates_table = dynamodb.Table(AGGREGATES_TABLE)


# ---------------------------------------------------------------------------
# JSON serialization helper
# ---------------------------------------------------------------------------
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _response(status_code: int, body: Any) -> Dict:
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Content-Type': 'application/json',
        },
        'body': json.dumps(body, cls=DecimalEncoder),
    }


# ---------------------------------------------------------------------------
# Endpoint: GET /earnings/recent
# ---------------------------------------------------------------------------
def _get_recent_earnings(params: Dict) -> Dict:
    """Return recent earnings results sorted by date descending."""
    limit = min(int(params.get('limit', '50')), 100)

    result = aggregates_table.query(
        KeyConditionExpression=Key('aggregate_type').eq('EARNINGS_RECENT'),
        ScanIndexForward=False,  # newest first
        Limit=limit,
    )

    items = result.get('Items', [])

    # Parse aggregate_key into components for cleaner response
    events = []
    for item in items:
        key_parts = item.get('aggregate_key', '').split('#', 1)
        events.append({
            'ticker': item.get('ticker', key_parts[1] if len(key_parts) > 1 else ''),
            'company_name': item.get('company_name', ''),
            'sector': item.get('sector', ''),
            'earnings_date': item.get('earnings_date', key_parts[0] if key_parts else ''),
            'eps_actual': item.get('eps_actual'),
            'eps_estimated': item.get('eps_estimated'),
            'eps_beat': item.get('eps_beat'),
            'eps_surprise_pct': item.get('eps_surprise_pct'),
            'updated_at': item.get('updated_at'),
        })

    latest_updated_at = max((item.get('updated_at', '') for item in items), default='') or None

    return _response(200, {
        'events': events,
        'count': len(events),
        'updated_at': latest_updated_at,
    })


# ---------------------------------------------------------------------------
# Endpoint: GET /earnings/upcoming
# ---------------------------------------------------------------------------
def _get_upcoming_earnings(params: Dict) -> Dict:
    """Return upcoming earnings sorted by date ascending."""
    limit = min(int(params.get('limit', '50')), 100)

    result = aggregates_table.query(
        KeyConditionExpression=Key('aggregate_type').eq('EARNINGS_UPCOMING'),
        ScanIndexForward=True,  # soonest first
        Limit=limit,
    )

    items = result.get('Items', [])

    events = []
    for item in items:
        events.append({
            'ticker': item.get('ticker', ''),
            'company_name': item.get('company_name', ''),
            'sector': item.get('sector', ''),
            'earnings_date': item.get('earnings_date', ''),
            'eps_estimated': item.get('eps_estimated'),
            'revenue_estimated': item.get('revenue_estimated'),
        })

    latest_updated_at = max((item.get('updated_at', '') for item in items), default='') or None

    return _response(200, {
        'events': events,
        'count': len(events),
        'updated_at': latest_updated_at,
    })


# ---------------------------------------------------------------------------
# Endpoint: GET /earnings/season
# ---------------------------------------------------------------------------
def _get_season_overview(params: Dict) -> Dict:
    """Return sector-level earnings summary for the season heatmap."""
    # Query all SECTOR aggregates
    result = aggregates_table.query(
        KeyConditionExpression=Key('aggregate_type').eq('SECTOR'),
    )
    sectors = result.get('Items', [])

    # Query INDEX-level overall summary
    index_result = aggregates_table.get_item(
        Key={'aggregate_type': 'INDEX', 'aggregate_key': 'OVERALL'}
    )
    index_overall = index_result.get('Item', {})

    # Query top beats and misses from RANKING partition
    beats_result = aggregates_table.get_item(
        Key={'aggregate_type': 'RANKING', 'aggregate_key': 'eps_surprise_pct'}
    )
    misses_result = aggregates_table.get_item(
        Key={'aggregate_type': 'RANKING', 'aggregate_key': 'eps_surprise_pct_asc'}
    )

    # Build sector summaries
    sector_summaries = []
    for sector in sectors:
        es = sector.get('earnings_summary', {})
        sector_summaries.append({
            'sector': sector.get('aggregate_key', ''),
            'company_count': sector.get('company_count', 0),
            'pct_beat_eps': es.get('pct_beat_eps'),
            'median_eps_surprise_pct': es.get('median_eps_surprise_pct'),
            'companies_with_earnings': es.get('companies_with_earnings', 0),
            'computed_at': sector.get('computed_at', ''),
        })

    # Sort by beat rate descending
    sector_summaries.sort(key=lambda s: s.get('pct_beat_eps') or 0, reverse=True)

    # Index-level summary
    index_es = index_overall.get('earnings_summary', {})
    overall = {
        'pct_beat_eps': index_es.get('pct_beat_eps'),
        'median_eps_surprise_pct': index_es.get('median_eps_surprise_pct'),
        'companies_with_earnings': index_es.get('companies_with_earnings', 0),
        'company_count': index_overall.get('company_count', 0),
    }

    latest_updated_at = max((s.get('computed_at', '') for s in sector_summaries), default='') or None

    return _response(200, {
        'sectors': sector_summaries,
        'overall': overall,
        'top_beats': (beats_result.get('Item', {}).get('companies', []))[:10],
        'top_misses': (misses_result.get('Item', {}).get('companies', []))[:10],
        'updated_at': latest_updated_at,
    })


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Route to the appropriate endpoint based on the API Gateway path.
    """
    path = event.get('rawPath', '') or event.get('path', '')
    method = event.get('requestContext', {}).get('http', {}).get('method', 'GET')
    params = event.get('queryStringParameters') or {}

    logger.info(f"Earnings feed request: {method} {path}")

    if method == 'OPTIONS':
        return _response(200, {})

    if path.endswith('/earnings/recent'):
        return _get_recent_earnings(params)
    elif path.endswith('/earnings/upcoming'):
        return _get_upcoming_earnings(params)
    elif path.endswith('/earnings/season'):
        return _get_season_overview(params)
    else:
        return _response(404, {'error': f'Unknown path: {path}'})
