"""
Unit tests for watchlist_handler.py

Covers:
- PUT /watchlist/{ticker}     — add ticker to watchlist with price/EPS snapshot
- GET /watchlist               — list watched tickers with computed deltas
- DELETE /watchlist/{ticker}   — remove ticker from watchlist
- Authentication enforcement (401 for unauthenticated)
- Validation (400 for invalid tickers)
- Limit enforcement (409 when watchlist full)
- Graceful handling of missing price/EPS data
- CORS headers and routing

Uses moto to mock DynamoDB — no real AWS calls.
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
os.environ['WATCHLIST_TABLE'] = 'watchlist-buffett-test'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['STOCK_DATA_4H_TABLE'] = 'stock-data-4h-test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['SP500_AGGREGATES_TABLE'] = 'buffett-test-sp500-aggregates'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'

# Ensure handlers directory is on sys.path
_handlers_dir = os.path.join(os.path.dirname(__file__), '..', 'src', 'handlers')
if _handlers_dir not in sys.path:
    sys.path.insert(0, _handlers_dir)


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


# ---------------------------------------------------------------------------
# Module-scoped fixture: mock AWS + DynamoDB tables + seed data + handler
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def aws_setup():
    """Set up mock AWS resources, seed data, and import handler."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

        # -- Watchlist table (PK=user_id, SK=ticker) ----------------------
        watchlist_table = dynamodb.create_table(
            TableName='watchlist-buffett-test',
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

        # -- Users table (PK=user_id) ------------------------------------
        users_table = dynamodb.create_table(
            TableName='buffett-test-users',
            KeySchema=[
                {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            ],
            AttributeDefinitions=[
                {'AttributeName': 'user_id', 'AttributeType': 'S'},
            ],
            BillingMode='PAY_PER_REQUEST',
        )

        # -- Stock data table (PK=PK, SK=SK) — matches handler queries ---
        stock_table = dynamodb.create_table(
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

        # -- Metrics history table (PK=ticker, SK=fiscal_date) --------
        metrics_table = dynamodb.create_table(
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

        # -- Aggregates table (PK=aggregate_type, SK=aggregate_key) --
        aggregates_table = dynamodb.create_table(
            TableName='buffett-test-sp500-aggregates',
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

        # ----- Seed data ------------------------------------------------

        # Free-tier user
        users_table.put_item(Item={
            'user_id': 'test-user-free',
            'email': 'free@test.com',
            'subscription_tier': 'free',
        })

        # Plus-tier user (active)
        users_table.put_item(Item={
            'user_id': 'test-user-plus',
            'email': 'plus@test.com',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        # Stock price data — AAPL
        stock_table.put_item(Item={
            'PK': 'TICKER#AAPL',
            'SK': 'DAILY#2026-04-08',
            'close': Decimal('227.45'),
            'open': Decimal('225.00'),
            'high': Decimal('228.00'),
            'low': Decimal('224.50'),
        })

        # Stock price data — MSFT
        stock_table.put_item(Item={
            'PK': 'TICKER#MSFT',
            'SK': 'DAILY#2026-04-08',
            'close': Decimal('415.30'),
            'open': Decimal('412.00'),
            'high': Decimal('416.00'),
            'low': Decimal('411.00'),
        })

        # Metrics data — AAPL quarterly earnings
        metrics_table.put_item(Item={
            'ticker': 'AAPL',
            'fiscal_date': '2025-12-31',
            'fiscal_quarter': 'Q1 2026',
            'earnings_events': {
                'eps_actual': Decimal('2.18'),
                'eps_estimated': Decimal('2.10'),
            },
        })

        # Upcoming earnings — AAPL
        aggregates_table.put_item(Item={
            'aggregate_type': 'EARNINGS_UPCOMING',
            'aggregate_key': 'AAPL#2026-05-01',
            'ticker': 'AAPL',
            'earnings_date': '2026-05-01',
        })

        # ----- Import handler AFTER mock is active -----------------------
        import watchlist_handler

        # Monkey-patch module-level table references to use mock tables
        watchlist_handler.watchlist_table = watchlist_table
        watchlist_handler.users_table = users_table
        watchlist_handler.stock_data_table = stock_table
        watchlist_handler.metrics_table = metrics_table
        watchlist_handler.aggregates_table = aggregates_table

        yield {
            'handler': watchlist_handler,
            'watchlist_table': watchlist_table,
            'users_table': users_table,
            'stock_table': stock_table,
            'metrics_table': metrics_table,
            'aggregates_table': aggregates_table,
        }


# ---------------------------------------------------------------------------
# Tests: Authentication
# ---------------------------------------------------------------------------

class TestAuthentication:
    """Verify 401 for unauthenticated requests and OPTIONS bypass."""

    def test_unauthenticated_get_returns_401(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('GET', '/watchlist')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 401
        body = json.loads(result['body'])
        assert body['error'] == 'Unauthorized'

    def test_unauthenticated_put_returns_401(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/AAPL')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 401

    def test_unauthenticated_delete_returns_401(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('DELETE', '/watchlist/AAPL')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 401

    def test_options_returns_200_without_auth(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('OPTIONS', '/watchlist')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200


# ---------------------------------------------------------------------------
# Tests: PUT /watchlist/{ticker}
# ---------------------------------------------------------------------------

class TestPutWatchlist:
    """Verify adding tickers to watchlist with snapshots and validation."""

    def test_add_valid_ticker(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/AAPL', user_id='put-test-user-1')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['ticker'] == 'AAPL'
        assert body['company_name'] == 'Apple Inc.'
        assert body['sector'] == 'Technology'
        assert body['industry'] == 'Consumer Electronics'
        assert 'added_at' in body
        assert 'user_id' in body

    def test_add_invalid_ticker_returns_400(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/FAKE', user_id='put-test-user-1')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Invalid ticker' in body['error']

    def test_add_invalid_ticker_special_chars_returns_400(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/A$$L', user_id='put-test-user-1')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 400

    def test_ticker_is_uppercased(self, aws_setup):
        handler = aws_setup['handler']
        # The handler does .upper() on the path segment
        event = _make_event('PUT', '/watchlist/msft', user_id='put-test-user-2')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['ticker'] == 'MSFT'

    def test_snapshot_price_captured(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/AAPL', user_id='put-test-user-3')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['snapshot_price'] == 227.45
        assert body['snapshot_price_date'] == '2026-04-08'

    def test_snapshot_eps_captured(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/AAPL', user_id='put-test-user-4')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['snapshot_eps'] == 2.18
        assert body['snapshot_eps_estimated'] == 2.10
        assert body['snapshot_fiscal_quarter'] == 'Q1 2026'

    def test_add_ticker_without_price_data(self, aws_setup):
        """Ticker valid but no price data seeded — graceful None handling."""
        handler = aws_setup['handler']
        # AMZN is a valid S&P 500 ticker, but we haven't seeded price data
        event = _make_event('PUT', '/watchlist/AMZN', user_id='put-test-user-5')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['ticker'] == 'AMZN'
        # snapshot_price should be absent (stripped as None)
        assert 'snapshot_price' not in body

    def test_add_ticker_without_eps_data(self, aws_setup):
        """Ticker valid but no EPS data seeded — graceful None handling."""
        handler = aws_setup['handler']
        # MSFT has price data but no metrics data seeded
        event = _make_event('PUT', '/watchlist/MSFT', user_id='put-test-user-6')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201
        body = json.loads(result['body'])
        assert body['ticker'] == 'MSFT'
        assert body['snapshot_price'] == 415.30
        # No EPS data seeded for MSFT
        assert 'snapshot_eps' not in body

    def test_watchlist_limit_free_tier_returns_409(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']
        users_table = aws_setup['users_table']

        limit_user = 'test-limit-free-user'

        # Create free-tier user
        users_table.put_item(Item={
            'user_id': limit_user,
            'email': 'limit@test.com',
            'subscription_tier': 'free',
        })

        # Fill to free-tier limit (20 items)
        from investment_research.index_tickers import SP500_TICKERS
        tickers = sorted(list(SP500_TICKERS))[:20]
        for t in tickers:
            table.put_item(Item={
                'user_id': limit_user,
                'ticker': t,
                'added_at': '2026-01-01T00:00:00',
            })

        # Attempt to add the 21st ticker
        extra_ticker = sorted(list(SP500_TICKERS))[20]
        event = _make_event('PUT', f'/watchlist/{extra_ticker}', user_id=limit_user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 409
        body = json.loads(result['body'])
        assert 'limit' in body['error'].lower()
        assert body['limit'] == 20
        assert body['current_count'] == 20

    def test_watchlist_limit_plus_tier_higher(self, aws_setup):
        """Plus users get 50 slots — 20 items should be fine."""
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        plus_user = 'test-user-plus'
        # Plus user already seeded with 'active' subscription_status

        # Add 20 items (under plus limit of 50)
        from investment_research.index_tickers import SP500_TICKERS
        tickers = sorted(list(SP500_TICKERS))[:20]
        for t in tickers:
            table.put_item(Item={
                'user_id': plus_user,
                'ticker': t,
                'added_at': '2026-01-01T00:00:00',
            })

        # 21st ticker should succeed for plus user
        extra_ticker = sorted(list(SP500_TICKERS))[20]
        event = _make_event('PUT', f'/watchlist/{extra_ticker}', user_id=plus_user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 201

    def test_idempotent_put_overwrites(self, aws_setup):
        """Adding the same ticker twice should overwrite (DynamoDB put_item)."""
        handler = aws_setup['handler']
        user = 'put-idempotent-user'
        event = _make_event('PUT', '/watchlist/AAPL', user_id=user)

        result1 = handler.lambda_handler(event, None)
        assert result1['statusCode'] == 201

        result2 = handler.lambda_handler(event, None)
        assert result2['statusCode'] == 201

        # Only one item should exist
        table = aws_setup['watchlist_table']
        resp = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('user_id').eq(user)
        )
        aapl_items = [i for i in resp['Items'] if i['ticker'] == 'AAPL']
        assert len(aapl_items) == 1


# ---------------------------------------------------------------------------
# Tests: GET /watchlist
# ---------------------------------------------------------------------------

class TestGetWatchlist:
    """Verify listing watchlist with enrichment and delta computation."""

    def test_get_empty_watchlist(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('GET', '/watchlist', user_id='empty-user')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['watchlist'] == []
        assert body['count'] == 0

    def test_get_watchlist_returns_items(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'get-test-user-1'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'snapshot_price': Decimal('220.00'),
            'snapshot_price_date': '2026-04-01',
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['count'] == 1
        item = body['watchlist'][0]
        assert item['ticker'] == 'AAPL'
        assert item['company_name'] == 'Apple Inc.'

    def test_get_watchlist_computes_price_delta(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'delta-price-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'snapshot_price': Decimal('200.00'),
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        body = json.loads(result['body'])
        item = body['watchlist'][0]

        # Current AAPL price = 227.45, snapshot = 200.00
        # (227.45 - 200) / 200 * 100 = 13.725 => rounded to 13.73
        assert item['price_change_pct'] is not None
        assert abs(item['price_change_pct'] - 13.73) < 0.1

    def test_get_watchlist_includes_current_price(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'current-price-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'MSFT',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Microsoft Corporation',
            'sector': 'Technology',
            'snapshot_price': Decimal('400.00'),
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        body = json.loads(result['body'])
        item = body['watchlist'][0]
        assert item['current_price'] == 415.30

    def test_get_watchlist_computes_eps_delta(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'delta-eps-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            'snapshot_price': Decimal('220.00'),
            'snapshot_eps': Decimal('2.00'),
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        body = json.loads(result['body'])
        item = body['watchlist'][0]

        # Current EPS = 2.18, snapshot = 2.00
        # (2.18 - 2.00) / 2.00 * 100 = 9.0
        assert item['eps_change_pct'] is not None
        assert abs(item['eps_change_pct'] - 9.0) < 0.5

    def test_get_watchlist_includes_next_earnings_date(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'earnings-date-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        body = json.loads(result['body'])
        item = body['watchlist'][0]
        assert item.get('next_earnings_date') == '2026-05-01'

    def test_get_watchlist_missing_price_data_graceful(self, aws_setup):
        """Ticker with no price data returns None deltas without error."""
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'no-price-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AMZN',  # No price data seeded
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Amazon.com, Inc.',
            'sector': 'Consumer Cyclical',
            'snapshot_price': Decimal('180.00'),
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        item = body['watchlist'][0]
        # No current price => price_change_pct should be absent (None stripped)
        assert 'price_change_pct' not in item or item['price_change_pct'] is None

    def test_get_watchlist_no_snapshot_price_no_delta(self, aws_setup):
        """Item without snapshot_price still returns without error."""
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'no-snapshot-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
            # No snapshot_price
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        item = body['watchlist'][0]
        # Has current price but no snapshot => no delta
        assert 'price_change_pct' not in item or item['price_change_pct'] is None

    def test_get_watchlist_multiple_items(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'multi-item-user'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
            'company_name': 'Apple Inc.',
            'sector': 'Technology',
        })
        table.put_item(Item={
            'user_id': user,
            'ticker': 'MSFT',
            'added_at': '2026-04-02T00:00:00',
            'company_name': 'Microsoft Corporation',
            'sector': 'Technology',
        })

        event = _make_event('GET', '/watchlist', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['count'] == 2
        tickers = {item['ticker'] for item in body['watchlist']}
        assert tickers == {'AAPL', 'MSFT'}


# ---------------------------------------------------------------------------
# Tests: DELETE /watchlist/{ticker}
# ---------------------------------------------------------------------------

class TestDeleteWatchlist:
    """Verify removing tickers from watchlist."""

    def test_delete_existing_ticker(self, aws_setup):
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'delete-test-user-1'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'AAPL',
            'added_at': '2026-04-01T00:00:00',
        })

        event = _make_event('DELETE', '/watchlist/AAPL', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert 'removed' in body['message'].lower() or 'AAPL' in body['message']

        # Verify item is gone
        resp = table.get_item(Key={'user_id': user, 'ticker': 'AAPL'})
        assert 'Item' not in resp

    def test_delete_nonexistent_ticker_still_200(self, aws_setup):
        """DynamoDB delete_item is idempotent — no error if key doesn't exist."""
        handler = aws_setup['handler']
        event = _make_event('DELETE', '/watchlist/NVDA', user_id='delete-test-user-2')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200

    def test_delete_lowercased_ticker(self, aws_setup):
        """Handler uppercases the ticker from path."""
        handler = aws_setup['handler']
        table = aws_setup['watchlist_table']

        user = 'delete-test-user-3'
        table.put_item(Item={
            'user_id': user,
            'ticker': 'MSFT',
            'added_at': '2026-04-01T00:00:00',
        })

        event = _make_event('DELETE', '/watchlist/msft', user_id=user)
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 200

        resp = table.get_item(Key={'user_id': user, 'ticker': 'MSFT'})
        assert 'Item' not in resp


# ---------------------------------------------------------------------------
# Tests: Routing and CORS
# ---------------------------------------------------------------------------

class TestRouting:
    """Verify HTTP routing, unknown paths, and CORS headers."""

    def test_unknown_path_returns_404(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('GET', '/unknown', user_id='test-user-free')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 404
        body = json.loads(result['body'])
        assert body['error'] == 'Not found'

    def test_post_method_returns_404(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('POST', '/watchlist', user_id='test-user-free')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 404

    def test_cors_headers_on_success(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('GET', '/watchlist', user_id='test-user-free')
        result = handler.lambda_handler(event, None)
        assert result['headers']['Access-Control-Allow-Origin'] == '*'
        assert result['headers']['Content-Type'] == 'application/json'

    def test_cors_headers_on_error(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('PUT', '/watchlist/FAKE', user_id='test-user-free')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 400
        assert result['headers']['Access-Control-Allow-Origin'] == '*'
        assert result['headers']['Content-Type'] == 'application/json'

    def test_cors_headers_on_401(self, aws_setup):
        handler = aws_setup['handler']
        event = _make_event('GET', '/watchlist')
        result = handler.lambda_handler(event, None)
        assert result['statusCode'] == 401
        assert result['headers']['Access-Control-Allow-Origin'] == '*'
