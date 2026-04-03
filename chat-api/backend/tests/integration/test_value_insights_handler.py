"""
Integration tests for Value Insights handler.

Tests the Lambda handler with mocked DynamoDB tables using moto.
Covers: metrics retrieval, ratings retrieval, error handling, empty data.

Run with: pytest tests/integration/test_value_insights_handler.py -v
"""

import json
import os
import sys
import pytest
import boto3
from moto import mock_aws
from decimal import Decimal
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

os.environ['ENVIRONMENT'] = 'test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['INVESTMENT_REPORTS_V2_TABLE'] = 'investment-reports-v2-test'
os.environ['STOCK_DATA_4H_TABLE'] = 'stock-data-4h-test'


def create_metrics_table(dynamodb):
    table = dynamodb.create_table(
        TableName='metrics-history-test',
        KeySchema=[
            {'AttributeName': 'ticker', 'KeyType': 'HASH'},
            {'AttributeName': 'fiscal_date', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'ticker', 'AttributeType': 'S'},
            {'AttributeName': 'fiscal_date', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def create_reports_table(dynamodb):
    table = dynamodb.create_table(
        TableName='investment-reports-v2-test',
        KeySchema=[
            {'AttributeName': 'ticker', 'KeyType': 'HASH'},
            {'AttributeName': 'section_id', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'ticker', 'AttributeType': 'S'},
            {'AttributeName': 'section_id', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


SAMPLE_QUARTER = {
    'ticker': 'AAPL',
    'fiscal_date': '2025-09-27',
    'fiscal_year': Decimal('2025'),
    'fiscal_quarter': 'Q3',
    'currency': 'USD',
    'revenue_profit': {
        'revenue': Decimal('94930000000'),
        'net_income': Decimal('23636000000'),
        'gross_profit': Decimal('43879000000'),
        'operating_income': Decimal('29561000000'),
        'ebitda': Decimal('32502000000'),
        'gross_margin': Decimal('46.22'),
        'operating_margin': Decimal('31.14'),
        'net_margin': Decimal('24.90'),
        'eps': Decimal('1.56'),
        'roe': Decimal('157.41'),
    },
    'cashflow': {
        'operating_cash_flow': Decimal('26810000000'),
        'free_cash_flow': Decimal('23350000000'),
        'fcf_margin': Decimal('24.60'),
        'capex': Decimal('-3460000000'),
        'capex_intensity': Decimal('3.65'),
        'ocf_to_revenue': Decimal('28.24'),
        'fcf_to_net_income': Decimal('0.988'),
        'fcf_payout_ratio': Decimal('64.30'),
        'reinvestment_rate': Decimal('14.83'),
        'share_buybacks': Decimal('-23567000000'),
        'dividends_paid': Decimal('-3847000000'),
    },
    'balance_sheet': {
        'total_debt': Decimal('96802000000'),
        'cash_position': Decimal('29943000000'),
        'net_debt': Decimal('66859000000'),
        'total_equity': Decimal('56950000000'),
        'long_term_debt': Decimal('85750000000'),
        'short_term_debt': Decimal('11052000000'),
        'working_capital': Decimal('-32213000000'),
    },
    'debt_leverage': {
        'debt_to_equity': Decimal('1.70'),
        'interest_coverage': Decimal('28.67'),
        'current_ratio': Decimal('0.87'),
        'quick_ratio': Decimal('0.85'),
        'debt_to_assets': Decimal('0.29'),
        'net_debt_to_ebitda': Decimal('0.51'),
        'fcf_to_debt': Decimal('0.96'),
        'interest_expense': Decimal('-1134000000'),
    },
    'earnings_quality': {
        'gaap_net_income': Decimal('23636000000'),
        'sbc_actual': Decimal('2941000000'),
        'sbc_to_revenue_pct': Decimal('3.10'),
        'adjusted_earnings': Decimal('20695000000'),
        'd_and_a': Decimal('2941000000'),
        'gaap_adjusted_gap_pct': Decimal('12.45'),
    },
    'dilution': {
        'basic_shares': Decimal('15115785000'),
        'diluted_shares': Decimal('15204137000'),
        'dilution_pct': Decimal('0.58'),
        'share_buybacks': Decimal('-23567000000'),
    },
    'valuation': {
        'roe': Decimal('157.41'),
        'roic': Decimal('55.20'),
        'roa': Decimal('30.10'),
        'asset_turnover': Decimal('1.21'),
        'equity_multiplier': Decimal('5.23'),
    },
}

SAMPLE_RATINGS_DICT = {
    'growth': {'rating': 'Moderate', 'confidence': 'Medium', 'key_factors': ['Revenue growth slowed']},
    'profitability': {'rating': 'Strong', 'confidence': 'High', 'key_factors': ['Margins expanding']},
    'overall_verdict': 'BUY',
    'conviction': 'High',
}


def create_stock_data_4h_table(dynamodb):
    table = dynamodb.create_table(
        TableName='stock-data-4h-test',
        KeySchema=[
            {'AttributeName': 'PK', 'KeyType': 'HASH'},
            {'AttributeName': 'SK', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'PK', 'AttributeType': 'S'},
            {'AttributeName': 'SK', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


SAMPLE_4H_CANDLE = {
    'PK': 'TICKER#AAPL',
    'SK': 'DATETIME#2026-04-02 13:30:00',
    'GSI_PK': 'DATE#2026-04-02',
    'GSI_SK': 'TICKER#AAPL',
    'symbol': 'AAPL',
    'date': '2026-04-02',
    'datetime': '2026-04-02 13:30:00',
    'open': Decimal('255.35'),
    'high': Decimal('256.13'),
    'low': Decimal('254.31'),
    'close': Decimal('255.92'),
    'volume': 7012489,
    'ingested_at': '2026-04-02T22:00:00+00:00',
}


def _make_event(ticker, method='GET'):
    return {
        'routeKey': f'GET /insights/{ticker}',
        'pathParameters': {'ticker': ticker},
        'requestContext': {'http': {'method': method}},
    }


@pytest.fixture
def aws_resources():
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        metrics_table = create_metrics_table(dynamodb)
        reports_table = create_reports_table(dynamodb)
        stock_data_4h_table = create_stock_data_4h_table(dynamodb)

        # Import/reload handler inside moto context
        if 'handlers.value_insights_handler' in sys.modules:
            mod = importlib.reload(sys.modules['handlers.value_insights_handler'])
        else:
            mod = importlib.import_module('handlers.value_insights_handler')

        # Re-bind tables to mocked AWS
        mod.dynamodb = dynamodb
        mod.metrics_table = dynamodb.Table('metrics-history-test')
        mod.reports_table = dynamodb.Table('investment-reports-v2-test')
        mod.STOCK_DATA_4H_TABLE = 'stock-data-4h-test'

        yield {
            'handler': mod.lambda_handler,
            'mod': mod,
            'metrics_table': metrics_table,
            'reports_table': reports_table,
            'stock_data_4h_table': stock_data_4h_table,
        }


def test_returns_metrics_for_valid_ticker(aws_resources):
    """AC-2/AC-7: Given a ticker with data, returns all quarterly metrics."""
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ticker'] == 'AAPL'
    assert body['quarters_available'] == 1
    assert len(body['metrics']) == 1
    assert body['metrics'][0]['fiscal_date'] == '2025-09-27'
    assert body['metrics'][0]['revenue_profit']['gross_margin'] == 46.22


def test_returns_ratings_as_dict(aws_resources):
    """AC-6: Ratings stored as dict are returned correctly."""
    aws_resources['reports_table'].put_item(Item={
        'ticker': 'AAPL',
        'section_id': '00_executive',
        'ratings': SAMPLE_RATINGS_DICT,
    })

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ratings']['overall_verdict'] == 'BUY'
    assert body['ratings']['growth']['rating'] == 'Moderate'


def test_returns_ratings_as_json_string(aws_resources):
    """H1: Ratings stored as JSON string are deserialized correctly."""
    aws_resources['reports_table'].put_item(Item={
        'ticker': 'AAPL',
        'section_id': '00_executive',
        'ratings': json.dumps(SAMPLE_RATINGS_DICT),
    })

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ratings']['overall_verdict'] == 'BUY'


def test_returns_null_ratings_when_no_report(aws_resources):
    """AC-6: Graceful degradation when no ratings exist."""
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ratings'] is None
    assert body['quarters_available'] == 1


def test_returns_empty_metrics_for_unknown_ticker(aws_resources):
    """AC-5: Returns empty metrics for ticker with no data."""
    response = aws_resources['handler'](_make_event('ZZZZZ'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ticker'] == 'ZZZZZ'
    assert body['quarters_available'] == 0
    assert body['metrics'] == []


def test_missing_ticker_returns_400(aws_resources):
    """Returns 400 when ticker parameter is missing."""
    event = {
        'routeKey': 'GET /insights/',
        'pathParameters': {},
        'requestContext': {'http': {'method': 'GET'}},
    }
    response = aws_resources['handler'](event, None)
    assert response['statusCode'] == 400


def test_options_returns_200(aws_resources):
    """CORS preflight returns 200."""
    event = {
        'routeKey': 'OPTIONS /insights/AAPL',
        'pathParameters': {'ticker': 'AAPL'},
        'requestContext': {'http': {'method': 'OPTIONS'}},
    }
    response = aws_resources['handler'](event, None)

    assert response['statusCode'] == 200
    assert 'Access-Control-Allow-Origin' in response['headers']


def test_multiple_quarters_sorted_ascending(aws_resources):
    """AC-7: Multiple quarters returned sorted by fiscal_date ascending."""
    for date in ['2025-09-27', '2024-09-28', '2025-03-29']:
        item = {**SAMPLE_QUARTER, 'fiscal_date': date}
        aws_resources['metrics_table'].put_item(Item=item)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    dates = [q['fiscal_date'] for q in body['metrics']]
    assert dates == sorted(dates)
    assert body['quarters_available'] == 3


def test_ticker_case_insensitive(aws_resources):
    """Ticker parameter is uppercased for lookup."""
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)

    response = aws_resources['handler'](_make_event('aapl'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['ticker'] == 'AAPL'
    assert body['quarters_available'] == 1


def test_combined_metrics_and_ratings(aws_resources):
    """Full integration: metrics + ratings returned in single response."""
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)
    aws_resources['reports_table'].put_item(Item={
        'ticker': 'AAPL',
        'section_id': '00_executive',
        'ratings': SAMPLE_RATINGS_DICT,
    })

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['quarters_available'] == 1
    assert body['ratings']['conviction'] == 'High'
    assert body['metrics'][0]['revenue_profit']['eps'] == 1.56


def test_cors_headers_present(aws_resources):
    """CORS headers are present on all responses."""
    response = aws_resources['handler'](_make_event('AAPL'), None)

    assert response['headers']['Access-Control-Allow-Origin'] == '*'
    assert 'GET' in response['headers']['Access-Control-Allow-Methods']


# ============================================================================
# Latest Price Tests (_get_latest_price + integration)
# ============================================================================

def test_latest_price_returned_when_4h_data_exists(aws_resources):
    """latest_price is populated when stock-data-4h has candle data."""
    aws_resources['stock_data_4h_table'].put_item(Item=SAMPLE_4H_CANDLE)
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['latest_price'] is not None
    assert body['latest_price']['price'] == 255.92
    assert body['latest_price']['date'] == '2026-04-02'
    assert body['latest_price']['volume'] == 7012489


def test_latest_price_null_when_no_4h_data(aws_resources):
    """latest_price is None when no candle data exists for ticker."""
    aws_resources['metrics_table'].put_item(Item=SAMPLE_QUARTER)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert response['statusCode'] == 200
    assert body['latest_price'] is None


def test_latest_price_returns_most_recent_candle(aws_resources):
    """When multiple candles exist, the most recent is returned."""
    # Earlier candle
    aws_resources['stock_data_4h_table'].put_item(Item={
        **SAMPLE_4H_CANDLE,
        'SK': 'DATETIME#2026-04-02 09:30:00',
        'datetime': '2026-04-02 09:30:00',
        'close': Decimal('254.00'),
    })
    # Later candle (should be returned)
    aws_resources['stock_data_4h_table'].put_item(Item=SAMPLE_4H_CANDLE)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert body['latest_price']['price'] == 255.92
    assert body['latest_price']['datetime'] == '2026-04-02 13:30:00'


def test_latest_price_null_when_table_not_configured(aws_resources):
    """latest_price is None when STOCK_DATA_4H_TABLE env var is empty."""
    aws_resources['mod'].STOCK_DATA_4H_TABLE = ''

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    assert body['latest_price'] is None

    # Restore for other tests
    aws_resources['mod'].STOCK_DATA_4H_TABLE = 'stock-data-4h-test'


def test_latest_price_includes_ohlv_fields(aws_resources):
    """latest_price includes open, high, low, volume for the banner."""
    aws_resources['stock_data_4h_table'].put_item(Item=SAMPLE_4H_CANDLE)

    response = aws_resources['handler'](_make_event('AAPL'), None)
    body = json.loads(response['body'])

    lp = body['latest_price']
    assert lp['open'] == 255.35
    assert lp['high'] == 256.13
    assert lp['low'] == 254.31
    assert lp['volume'] == 7012489
