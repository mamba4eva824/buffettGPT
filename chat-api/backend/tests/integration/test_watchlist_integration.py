"""
Integration tests for watchlist_handler and earnings_feed_handler.

Tests full handler flows including DynamoDB interactions using moto mocks.
Covers:
  - Full add-then-list cycle (PUT + GET)
  - Add-then-delete-then-list cycle (PUT + DELETE + GET)
  - Multiple ticker lifecycle management
  - Snapshot accuracy (price from stock-data-4h, EPS from metrics-history)
  - Delta computation accuracy (price_change_pct from snapshot vs current)
  - Earnings feed recent and season endpoints
  - Auth enforcement (watchlist requires auth, earnings is public)

Run with:
  cd chat-api/backend
  python -m pytest tests/integration/test_watchlist_integration.py -v
"""

import json
import os
import sys
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Environment setup — MUST happen before handler import
# ---------------------------------------------------------------------------

os.environ['ENVIRONMENT'] = 'test'
os.environ['WATCHLIST_TABLE'] = 'watchlist-integ-test'
os.environ['USERS_TABLE'] = 'users-integ-test'
os.environ['STOCK_DATA_4H_TABLE'] = 'stock-data-4h-integ-test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-integ-test'
os.environ['SP500_AGGREGATES_TABLE'] = 'sp500-aggregates-integ-test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'

# Ensure handlers directory is on sys.path
_handlers_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'handlers')
if _handlers_dir not in sys.path:
    sys.path.insert(0, _handlers_dir)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(method, path, user_id=None):
    """Create a mock API Gateway v2 event."""
    event = {
        'httpMethod': method,
        'path': path,
        'rawPath': path,
        'requestContext': {
            'http': {'method': method},
            'authorizer': {},
        },
        'queryStringParameters': {},
    }
    if user_id:
        event['requestContext']['authorizer'] = {
            'lambda': {'user_id': user_id}
        }
    return event


def _make_earnings_event(path, method='GET', params=None):
    """Create a mock API Gateway event for earnings feed handler."""
    return {
        'rawPath': path,
        'requestContext': {'http': {'method': method}},
        'queryStringParameters': params,
    }


def _parse_body(result):
    """Parse the JSON body from a Lambda response."""
    return json.loads(result['body'])


# ---------------------------------------------------------------------------
# Module-scoped fixture: mock AWS + all DynamoDB tables + seed data
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def aws_env():
    """
    Set up mock AWS resources, seed baseline data, and import both handlers.

    Tables created:
      - watchlist (PK=user_id, SK=ticker)
      - users (PK=user_id)
      - stock-data-4h (PK=PK, SK=SK)
      - metrics-history (PK=ticker, SK=fiscal_date)
      - sp500-aggregates (PK=aggregate_type, SK=aggregate_key)
    """
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

        # -- Watchlist table ------------------------------------------------
        watchlist_table = dynamodb.create_table(
            TableName='watchlist-integ-test',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
                {'AttributeName': 'ticker', 'KeyType': 'RANGE'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
                {'AttributeName': 'ticker', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )

        # -- Users table ----------------------------------------------------
        users_table = dynamodb.create_table(
            TableName='users-integ-test',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )

        # -- Stock data table -----------------------------------------------
        stock_table = dynamodb.create_table(
            TableName='stock-data-4h-integ-test',
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

        # -- Metrics history table ------------------------------------------
        metrics_table = dynamodb.create_table(
            TableName='metrics-history-integ-test',
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

        # -- Aggregates table -----------------------------------------------
        aggregates_table = dynamodb.create_table(
            TableName='sp500-aggregates-integ-test',
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

        # ----- Seed baseline data ------------------------------------------

        # Free-tier user
        users_table.put_item(Item={
            'user_id': 'integ-user-free',
            'email': 'free@integ.test',
            'subscription_tier': 'free',
        })

        # Plus-tier user
        users_table.put_item(Item={
            'user_id': 'integ-user-plus',
            'email': 'plus@integ.test',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        # Stock price data: AAPL
        stock_table.put_item(Item={
            'PK': 'TICKER#AAPL',
            'SK': 'DAILY#2026-04-08',
            'close': Decimal('227.45'),
            'open': Decimal('225.00'),
            'high': Decimal('228.00'),
            'low': Decimal('224.50'),
        })

        # Stock price data: MSFT
        stock_table.put_item(Item={
            'PK': 'TICKER#MSFT',
            'SK': 'DAILY#2026-04-08',
            'close': Decimal('415.30'),
            'open': Decimal('412.00'),
            'high': Decimal('416.00'),
            'low': Decimal('411.00'),
        })

        # Metrics data: AAPL quarterly earnings
        metrics_table.put_item(Item={
            'ticker': 'AAPL',
            'fiscal_date': '2025-12-31',
            'fiscal_quarter': 'Q1 2026',
            'earnings_events': {
                'eps_actual': Decimal('2.18'),
                'eps_estimated': Decimal('2.10'),
            },
        })

        # Metrics data: MSFT quarterly earnings
        metrics_table.put_item(Item={
            'ticker': 'MSFT',
            'fiscal_date': '2025-12-31',
            'fiscal_quarter': 'Q2 2026',
            'earnings_events': {
                'eps_actual': Decimal('3.10'),
                'eps_estimated': Decimal('3.05'),
            },
        })

        # Upcoming earnings for AAPL
        aggregates_table.put_item(Item={
            'aggregate_type': 'EARNINGS_UPCOMING',
            'aggregate_key': 'AAPL#2026-05-01',
            'ticker': 'AAPL',
            'earnings_date': '2026-05-01',
        })

        # Recent earnings events for earnings feed
        aggregates_table.put_item(Item={
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
        })
        aggregates_table.put_item(Item={
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
        })

        # Sector aggregates for season endpoint
        aggregates_table.put_item(Item={
            'aggregate_type': 'SECTOR',
            'aggregate_key': 'Technology',
            'company_count': 87,
            'earnings_summary': {
                'median_eps_surprise_pct': Decimal('4.2'),
                'pct_beat_eps': Decimal('78.5'),
                'companies_with_earnings': 32,
            },
            'computed_at': '2026-04-07T12:00:00',
        })
        aggregates_table.put_item(Item={
            'aggregate_type': 'SECTOR',
            'aggregate_key': 'Healthcare',
            'company_count': 65,
            'earnings_summary': {
                'median_eps_surprise_pct': Decimal('2.1'),
                'pct_beat_eps': Decimal('65.0'),
                'companies_with_earnings': 20,
            },
            'computed_at': '2026-04-07T12:00:00',
        })

        # Index overall
        aggregates_table.put_item(Item={
            'aggregate_type': 'INDEX',
            'aggregate_key': 'OVERALL',
            'company_count': 498,
            'earnings_summary': {
                'median_eps_surprise_pct': Decimal('3.5'),
                'pct_beat_eps': Decimal('72.3'),
                'companies_with_earnings': 180,
            },
        })

        # Rankings: top beats and misses
        aggregates_table.put_item(Item={
            'aggregate_type': 'RANKING',
            'aggregate_key': 'eps_surprise_pct',
            'companies': [
                {'ticker': 'AAPL', 'name': 'Apple Inc.',
                 'sector': 'Technology', 'value': Decimal('15.2')},
                {'ticker': 'GOOG', 'name': 'Alphabet Inc.',
                 'sector': 'Technology', 'value': Decimal('12.8')},
            ],
        })
        aggregates_table.put_item(Item={
            'aggregate_type': 'RANKING',
            'aggregate_key': 'eps_surprise_pct_asc',
            'companies': [
                {'ticker': 'MSFT', 'name': 'Microsoft Corporation',
                 'sector': 'Technology', 'value': Decimal('-4.62')},
            ],
        })

        # ----- Import handlers AFTER mock is active ------------------------
        import watchlist_handler
        import earnings_feed_handler

        # Monkey-patch module-level table references to use mock tables
        watchlist_handler.watchlist_table = watchlist_table
        watchlist_handler.users_table = users_table
        watchlist_handler.stock_data_table = stock_table
        watchlist_handler.metrics_table = metrics_table
        watchlist_handler.aggregates_table = aggregates_table

        earnings_feed_handler.aggregates_table = aggregates_table

        yield {
            'watchlist_handler': watchlist_handler,
            'earnings_handler': earnings_feed_handler,
            'watchlist_table': watchlist_table,
            'users_table': users_table,
            'stock_table': stock_table,
            'metrics_table': metrics_table,
            'aggregates_table': aggregates_table,
        }


# ===========================================================================
# Watchlist Handler Integration Tests
# ===========================================================================

class TestWatchlistAddThenList:
    """PUT /watchlist/{ticker} -> GET /watchlist: full add-then-list cycle."""

    def test_add_ticker_then_list_shows_item_with_snapshots(self, aws_env):
        """
        PUT AAPL for a user, then GET the watchlist.
        The listed item must include correct snapshot values and computed deltas.
        """
        handler = aws_env['watchlist_handler']
        user = 'integ-cycle-user-1'

        # Step 1: Add AAPL
        put_result = handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )
        assert put_result['statusCode'] == 201
        put_body = _parse_body(put_result)
        assert put_body['ticker'] == 'AAPL'
        assert put_body['snapshot_price'] == 227.45
        assert put_body['snapshot_eps'] == 2.18

        # Step 2: List watchlist
        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        assert get_result['statusCode'] == 200
        get_body = _parse_body(get_result)
        assert get_body['count'] == 1

        item = get_body['watchlist'][0]
        assert item['ticker'] == 'AAPL'
        assert item['company_name'] == 'Apple Inc.'
        assert item['sector'] == 'Technology'

        # Snapshot values persisted correctly
        assert item['snapshot_price'] == 227.45
        assert item['snapshot_eps'] == 2.18

        # Current price enrichment
        assert item['current_price'] == 227.45

        # Deltas: same snapshot as current => 0% change
        assert item['price_change_pct'] == 0.0
        assert item['current_eps'] == 2.18

        # Next earnings date from aggregates
        assert item.get('next_earnings_date') == '2026-05-01'


class TestWatchlistAddDeleteList:
    """PUT -> DELETE -> GET: verify item is removed from watchlist."""

    def test_add_then_delete_then_list_shows_empty(self, aws_env):
        handler = aws_env['watchlist_handler']
        user = 'integ-del-cycle-user-1'

        # Add
        put_result = handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )
        assert put_result['statusCode'] == 201

        # Confirm it exists
        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        assert _parse_body(get_result)['count'] == 1

        # Delete
        del_result = handler.lambda_handler(
            _make_event('DELETE', '/watchlist/AAPL', user_id=user), None
        )
        assert del_result['statusCode'] == 200
        del_body = _parse_body(del_result)
        assert 'AAPL' in del_body['message']

        # Confirm it is gone
        get_result2 = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result2)
        assert body['count'] == 0
        assert body['watchlist'] == []

    def test_delete_also_removes_from_dynamo(self, aws_env):
        """After DELETE, the DynamoDB item itself should be gone."""
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-del-dynamo-user'

        handler.lambda_handler(
            _make_event('PUT', '/watchlist/MSFT', user_id=user), None
        )

        # Verify item exists in DynamoDB
        resp = table.get_item(Key={'user_id': user, 'ticker': 'MSFT'})
        assert 'Item' in resp

        handler.lambda_handler(
            _make_event('DELETE', '/watchlist/MSFT', user_id=user), None
        )

        # Verify item no longer exists in DynamoDB
        resp = table.get_item(Key={'user_id': user, 'ticker': 'MSFT'})
        assert 'Item' not in resp


class TestWatchlistMultipleTickerLifecycle:
    """Add multiple tickers, verify both appear, delete one, verify remainder."""

    def test_multi_ticker_add_delete_partial(self, aws_env):
        handler = aws_env['watchlist_handler']
        user = 'integ-multi-user-1'

        # Add AAPL and MSFT
        r1 = handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )
        assert r1['statusCode'] == 201

        r2 = handler.lambda_handler(
            _make_event('PUT', '/watchlist/MSFT', user_id=user), None
        )
        assert r2['statusCode'] == 201

        # GET: both should appear
        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        assert body['count'] == 2
        tickers = {item['ticker'] for item in body['watchlist']}
        assert tickers == {'AAPL', 'MSFT'}

        # Delete AAPL only
        del_result = handler.lambda_handler(
            _make_event('DELETE', '/watchlist/AAPL', user_id=user), None
        )
        assert del_result['statusCode'] == 200

        # GET: only MSFT should remain
        get_result2 = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body2 = _parse_body(get_result2)
        assert body2['count'] == 1
        assert body2['watchlist'][0]['ticker'] == 'MSFT'

    def test_multi_ticker_each_has_correct_enrichment(self, aws_env):
        """Each ticker in the list should have its own correct current price."""
        handler = aws_env['watchlist_handler']
        user = 'integ-multi-enrich-user'

        handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )
        handler.lambda_handler(
            _make_event('PUT', '/watchlist/MSFT', user_id=user), None
        )

        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        items_by_ticker = {i['ticker']: i for i in body['watchlist']}

        assert items_by_ticker['AAPL']['current_price'] == 227.45
        assert items_by_ticker['MSFT']['current_price'] == 415.30


class TestSnapshotAccuracy:
    """Verify DynamoDB items have correct snapshot values from source tables."""

    def test_snapshot_price_matches_stock_data(self, aws_env):
        """snapshot_price should equal the close from stock-data-4h."""
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-snap-price-user'

        handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )

        # Read the raw DynamoDB item
        resp = table.get_item(Key={'user_id': user, 'ticker': 'AAPL'})
        item = resp['Item']
        assert item['snapshot_price'] == Decimal('227.45')
        assert item['snapshot_price_date'] == '2026-04-08'

    def test_snapshot_eps_matches_metrics_history(self, aws_env):
        """snapshot_eps should equal eps_actual from metrics-history."""
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-snap-eps-user'

        handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL', user_id=user), None
        )

        resp = table.get_item(Key={'user_id': user, 'ticker': 'AAPL'})
        item = resp['Item']
        assert item['snapshot_eps'] == Decimal('2.18')
        assert item['snapshot_eps_estimated'] == Decimal('2.10')
        assert item['snapshot_fiscal_quarter'] == 'Q1 2026'

    def test_snapshot_for_ticker_with_no_price(self, aws_env):
        """
        AMZN has no price data seeded. snapshot_price should not be present
        in the DynamoDB item (None values are stripped before put_item).
        """
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-snap-no-price-user'

        result = handler.lambda_handler(
            _make_event('PUT', '/watchlist/AMZN', user_id=user), None
        )
        assert result['statusCode'] == 201

        resp = table.get_item(Key={'user_id': user, 'ticker': 'AMZN'})
        item = resp['Item']
        assert 'snapshot_price' not in item
        assert 'snapshot_price_date' not in item


class TestDeltaComputationAccuracy:
    """Verify price_change_pct is computed correctly from snapshot vs current."""

    def test_price_change_pct_computed_correctly(self, aws_env):
        """
        Seed watchlist item with snapshot_price=200, current close=227.45.
        Expected delta: (227.45 - 200) / 200 * 100 = 13.725 => rounded to 13.73
        """
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-delta-user-1'

        # Directly seed a watchlist item with a known snapshot_price
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-03-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'snapshot_price': Decimal('200.00'),
            'snapshot_price_date': '2026-03-01',
        })

        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        assert body['count'] == 1
        item = body['watchlist'][0]

        # Current AAPL close = 227.45, snapshot = 200.00
        # (227.45 - 200) / 200 * 100 = 13.725 => banker's rounding = 13.72
        assert item['current_price'] == 227.45
        assert item['snapshot_price'] == 200.0
        assert abs(item['price_change_pct'] - 13.73) < 0.02

    def test_eps_change_pct_computed_correctly(self, aws_env):
        """
        Seed watchlist with snapshot_eps=2.00, current eps=2.18 (from metrics).
        Expected: (2.18 - 2.00) / 2.00 * 100 = 9.0
        """
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-delta-eps-user-1'

        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-03-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'snapshot_price': Decimal('220.00'),
            'snapshot_eps': Decimal('2.00'),
        })

        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        item = body['watchlist'][0]

        assert item['current_eps'] == 2.18
        assert item['eps_change_pct'] == 9.0

    def test_no_delta_when_snapshot_missing(self, aws_env):
        """If no snapshot_price was recorded, price_change_pct should not appear."""
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-delta-nosnapshot-user'

        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-03-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            # No snapshot_price
        })

        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        item = body['watchlist'][0]

        # current_price should still be enriched
        assert item['current_price'] == 227.45
        # But no delta — stripped as None
        assert 'price_change_pct' not in item or item['price_change_pct'] is None

    def test_no_delta_when_current_price_missing(self, aws_env):
        """If no current price data for a ticker, delta cannot be computed."""
        handler = aws_env['watchlist_handler']
        table = aws_env['watchlist_table']
        user = 'integ-delta-nocurrent-user'

        table.put_item(Item={
            'user_id': user,
            'ticker': 'AMZN',  # No price data seeded for AMZN
            'added_at': '2026-03-01T00:00:00',
            'company_name': 'Amazon.com, Inc.',
            'sector': 'Consumer Cyclical',
            'snapshot_price': Decimal('180.00'),
        })

        get_result = handler.lambda_handler(
            _make_event('GET', '/watchlist', user_id=user), None
        )
        body = _parse_body(get_result)
        item = body['watchlist'][0]

        assert 'price_change_pct' not in item or item['price_change_pct'] is None


# ===========================================================================
# Earnings Feed Handler Integration Tests
# ===========================================================================

class TestEarningsRecentRead:
    """GET /earnings/recent: verify recent earnings events are returned."""

    def test_recent_earnings_returns_seeded_events(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/recent'), None
        )
        assert result['statusCode'] == 200
        body = _parse_body(result)

        assert body['count'] == 2
        assert body['updated_at'] is not None

        # Events should be sorted newest first (descending by aggregate_key)
        assert body['events'][0]['ticker'] == 'AAPL'
        assert body['events'][1]['ticker'] == 'MSFT'

    def test_recent_earnings_event_fields(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/recent'), None
        )
        body = _parse_body(result)
        aapl = body['events'][0]

        assert aapl['ticker'] == 'AAPL'
        assert aapl['company_name'] == 'Apple Inc.'
        assert aapl['sector'] == 'Technology'
        assert aapl['earnings_date'] == '2026-04-07'
        assert aapl['eps_actual'] == 2.40
        assert aapl['eps_estimated'] == 2.36
        assert aapl['eps_beat'] is True
        assert aapl['eps_surprise_pct'] == 1.69
        assert aapl['updated_at'] == '2026-04-07T18:00:00'

    def test_recent_earnings_miss_event(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/recent'), None
        )
        body = _parse_body(result)
        msft = body['events'][1]

        assert msft['eps_beat'] is False
        assert msft['eps_surprise_pct'] == -4.62


class TestEarningsSeasonOverviewRead:
    """GET /earnings/season: verify sector summaries and rankings."""

    def test_season_returns_sector_summaries(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/season'), None
        )
        assert result['statusCode'] == 200
        body = _parse_body(result)

        # Two sectors seeded
        assert len(body['sectors']) == 2
        # Sorted by pct_beat_eps descending
        assert body['sectors'][0]['sector'] == 'Technology'
        assert body['sectors'][0]['pct_beat_eps'] == 78.5
        assert body['sectors'][0]['company_count'] == 87
        assert body['sectors'][1]['sector'] == 'Healthcare'
        assert body['sectors'][1]['pct_beat_eps'] == 65.0

    def test_season_returns_overall_summary(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/season'), None
        )
        body = _parse_body(result)

        assert body['overall']['pct_beat_eps'] == 72.3
        assert body['overall']['median_eps_surprise_pct'] == 3.5
        assert body['overall']['companies_with_earnings'] == 180
        assert body['overall']['company_count'] == 498

    def test_season_returns_top_beats_and_misses(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/season'), None
        )
        body = _parse_body(result)

        assert len(body['top_beats']) == 2
        assert body['top_beats'][0]['ticker'] == 'AAPL'
        assert body['top_beats'][1]['ticker'] == 'GOOG'

        assert len(body['top_misses']) == 1
        assert body['top_misses'][0]['ticker'] == 'MSFT'

    def test_season_has_updated_at(self, aws_env):
        handler = aws_env['earnings_handler']

        result = handler.lambda_handler(
            _make_earnings_event('/earnings/season'), None
        )
        body = _parse_body(result)
        assert body['updated_at'] is not None


# ===========================================================================
# Auth Enforcement Tests
# ===========================================================================

class TestAuthEnforcement:
    """Verify auth requirements differ between watchlist and earnings."""

    def test_watchlist_get_rejects_unauthenticated(self, aws_env):
        """GET /watchlist without user_id must return 401."""
        handler = aws_env['watchlist_handler']
        result = handler.lambda_handler(
            _make_event('GET', '/watchlist'), None
        )
        assert result['statusCode'] == 401
        body = _parse_body(result)
        assert body['error'] == 'Unauthorized'

    def test_watchlist_put_rejects_unauthenticated(self, aws_env):
        """PUT /watchlist/AAPL without user_id must return 401."""
        handler = aws_env['watchlist_handler']
        result = handler.lambda_handler(
            _make_event('PUT', '/watchlist/AAPL'), None
        )
        assert result['statusCode'] == 401

    def test_watchlist_delete_rejects_unauthenticated(self, aws_env):
        """DELETE /watchlist/AAPL without user_id must return 401."""
        handler = aws_env['watchlist_handler']
        result = handler.lambda_handler(
            _make_event('DELETE', '/watchlist/AAPL'), None
        )
        assert result['statusCode'] == 401

    def test_earnings_recent_allows_unauthenticated(self, aws_env):
        """GET /earnings/recent is a public endpoint — no auth required."""
        handler = aws_env['earnings_handler']
        result = handler.lambda_handler(
            _make_earnings_event('/earnings/recent'), None
        )
        assert result['statusCode'] == 200

    def test_earnings_season_allows_unauthenticated(self, aws_env):
        """GET /earnings/season is a public endpoint — no auth required."""
        handler = aws_env['earnings_handler']
        result = handler.lambda_handler(
            _make_earnings_event('/earnings/season'), None
        )
        assert result['statusCode'] == 200
