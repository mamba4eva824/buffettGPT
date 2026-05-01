"""
Unit tests for earnings_feed_handler.py

Covers:
- GET /earnings/recent — returns recent earnings events from aggregates table
- GET /earnings/upcoming — returns upcoming earnings from aggregates table
- GET /earnings/season — returns sector summaries and rankings
- 404 for unknown paths

Uses moto to mock DynamoDB — no real AWS calls.
"""

import json
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = 'buffett-test-sp500-aggregates'

# Dynamic future date so the upcoming-earnings fixture doesn't time-bomb.
# The handler filters out earnings_date < today, so a hardcoded date will
# silently start failing once today catches up.
_UPCOMING_DATE = (date.today() + timedelta(days=30)).strftime('%Y-%m-%d')


@pytest.fixture(scope='module')
def dynamodb_mock():
    """Start moto mock and create the aggregates table at module scope."""
    with mock_aws():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['SP500_AGGREGATES_TABLE'] = TABLE_NAME
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {'AttributeName': 'aggregate_type', 'KeyType': 'HASH'},
                {'AttributeName': 'aggregate_key', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'aggregate_type', 'AttributeType': 'S'},
                {'AttributeName': 'aggregate_key', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )

        # Seed with test data
        _seed_test_data(table)

        yield table


def _seed_test_data(table):
    """Seed test data into the aggregates table."""
    # Recent earnings events
    recent_events = [
        {
            'aggregate_type': 'EARNINGS_RECENT',
            'aggregate_key': '2026-04-07#AAPL',
            'ticker': 'AAPL',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'earnings_date': '2026-04-07',
            'eps_actual': Decimal('2.40'),
            'eps_estimated': Decimal('2.36'),
            'eps_beat': True,
            'eps_surprise_pct': Decimal('1.69'),
            'updated_at': '2026-04-07T18:00:00',
        },
        {
            'aggregate_type': 'EARNINGS_RECENT',
            'aggregate_key': '2026-04-06#MSFT',
            'ticker': 'MSFT',
            'company_name': 'Microsoft Corporation',
            'sector': 'Technology',
            'earnings_date': '2026-04-06',
            'eps_actual': Decimal('3.10'),
            'eps_estimated': Decimal('3.25'),
            'eps_beat': False,
            'eps_surprise_pct': Decimal('-4.62'),
            'updated_at': '2026-04-06T18:00:00',
        },
    ]

    # Upcoming earnings events
    upcoming_events = [
        {
            'aggregate_type': 'EARNINGS_UPCOMING',
            'aggregate_key': f'{_UPCOMING_DATE}#NVDA',
            'ticker': 'NVDA',
            'company_name': 'NVIDIA Corporation',
            'sector': 'Technology',
            'earnings_date': _UPCOMING_DATE,
            'eps_estimated': Decimal('1.75'),
        },
    ]

    # Sector aggregates
    sector_items = [
        {
            'aggregate_type': 'SECTOR',
            'aggregate_key': 'Technology',
            'company_count': 87,
            'earnings_summary': {
                'median_eps_surprise_pct': Decimal('4.2'),
                'pct_beat_eps': Decimal('78.5'),
                'companies_with_earnings': 32,
            },
            'computed_at': '2026-04-07T12:00:00',
        },
        {
            'aggregate_type': 'SECTOR',
            'aggregate_key': 'Healthcare',
            'company_count': 65,
            'earnings_summary': {
                'median_eps_surprise_pct': Decimal('2.1'),
                'pct_beat_eps': Decimal('65.0'),
                'companies_with_earnings': 20,
            },
            'computed_at': '2026-04-07T12:00:00',
        },
    ]

    # Index overall
    index_item = {
        'aggregate_type': 'INDEX',
        'aggregate_key': 'OVERALL',
        'company_count': 498,
        'earnings_summary': {
            'median_eps_surprise_pct': Decimal('3.5'),
            'pct_beat_eps': Decimal('72.3'),
            'companies_with_earnings': 180,
        },
    }

    # Rankings
    beats_item = {
        'aggregate_type': 'RANKING',
        'aggregate_key': 'eps_surprise_pct',
        'companies': [
            {'ticker': 'AAPL', 'name': 'Apple Inc.', 'sector': 'Technology', 'value': Decimal('15.2')},
            {'ticker': 'GOOG', 'name': 'Alphabet Inc.', 'sector': 'Technology', 'value': Decimal('12.8')},
        ],
    }
    misses_item = {
        'aggregate_type': 'RANKING',
        'aggregate_key': 'eps_surprise_pct_asc',
        'companies': [
            {'ticker': 'MSFT', 'name': 'Microsoft Corporation', 'sector': 'Technology', 'value': Decimal('-4.62')},
        ],
    }

    with table.batch_writer() as batch:
        for item in recent_events + upcoming_events + sector_items + [index_item, beats_item, misses_item]:
            batch.put_item(Item=item)


@pytest.fixture(scope='module')
def handler(dynamodb_mock):
    """Import the handler module AFTER moto is active."""
    handlers_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'handlers')
    if handlers_dir not in sys.path:
        sys.path.insert(0, handlers_dir)

    import earnings_feed_handler
    # Point the module's table to the mock
    earnings_feed_handler.aggregates_table = dynamodb_mock
    return earnings_feed_handler


def _make_event(path, method='GET', params=None):
    return {
        'rawPath': path,
        'requestContext': {'http': {'method': method}},
        'queryStringParameters': params,
    }


class TestGetRecentEarnings:
    def test_returns_recent_events(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent'), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 2
        # Should be sorted newest first
        assert body['events'][0]['ticker'] == 'AAPL'
        assert body['events'][1]['ticker'] == 'MSFT'

    def test_beat_miss_fields(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent'), None)
        body = json.loads(response['body'])
        aapl = body['events'][0]
        assert aapl['eps_beat'] is True
        assert aapl['eps_actual'] == 2.40
        assert aapl['eps_estimated'] == 2.36
        assert aapl['eps_surprise_pct'] == 1.69
        assert aapl['company_name'] == 'Apple Inc.'
        assert aapl['sector'] == 'Technology'

    def test_miss_event(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent'), None)
        body = json.loads(response['body'])
        msft = body['events'][1]
        assert msft['eps_beat'] is False
        assert msft['eps_surprise_pct'] == -4.62

    def test_limit_parameter(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent', params={'limit': '1'}), None)
        body = json.loads(response['body'])
        assert body['count'] == 1

    def test_cors_headers(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent'), None)
        assert response['headers']['Access-Control-Allow-Origin'] == '*'
        assert response['headers']['Content-Type'] == 'application/json'


class TestGetUpcomingEarnings:
    def test_returns_upcoming_events(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/upcoming'), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['count'] == 1
        assert body['events'][0]['ticker'] == 'NVDA'
        assert body['events'][0]['eps_estimated'] == 1.75

    def test_upcoming_has_no_actual(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/upcoming'), None)
        body = json.loads(response['body'])
        nvda = body['events'][0]
        assert 'eps_actual' not in nvda
        assert 'eps_beat' not in nvda


class TestGetSeasonOverview:
    def test_returns_sector_summaries(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/season'), None)
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert len(body['sectors']) == 2
        # Sorted by beat rate descending
        assert body['sectors'][0]['sector'] == 'Technology'
        assert body['sectors'][0]['pct_beat_eps'] == 78.5
        assert body['sectors'][1]['sector'] == 'Healthcare'

    def test_returns_overall_summary(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/season'), None)
        body = json.loads(response['body'])
        assert body['overall']['pct_beat_eps'] == 72.3
        assert body['overall']['median_eps_surprise_pct'] == 3.5
        assert body['overall']['companies_with_earnings'] == 180

    def test_returns_top_beats_and_misses(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/season'), None)
        body = json.loads(response['body'])
        assert len(body['top_beats']) == 2
        assert body['top_beats'][0]['ticker'] == 'AAPL'
        assert len(body['top_misses']) == 1
        assert body['top_misses'][0]['ticker'] == 'MSFT'


class TestRouting:
    def test_unknown_path_returns_404(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/unknown'), None)
        assert response['statusCode'] == 404

    def test_options_returns_200(self, handler):
        response = handler.lambda_handler(_make_event('/earnings/recent', method='OPTIONS'), None)
        assert response['statusCode'] == 200
