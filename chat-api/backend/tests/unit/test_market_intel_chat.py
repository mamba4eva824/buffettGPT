"""
Unit tests for Market Intelligence Chat Lambda handler.

Tests subscription gating, JWT auth, and routing logic.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ['ENVIRONMENT'] = 'test'
os.environ['JWT_SECRET'] = 'test-secret-key-for-testing-only'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['SP500_AGGREGATES_TABLE'] = 'buffett-test-sp500-aggregates'


@pytest.fixture(autouse=True)
def mock_boto3():
    """Mock boto3 for all tests."""
    mock_dynamodb = MagicMock()
    mock_users_table = MagicMock()
    mock_metrics_table = MagicMock()
    mock_agg_table = MagicMock()

    def table_router(name):
        if 'users' in name:
            return mock_users_table
        elif 'aggregates' in name:
            return mock_agg_table
        else:
            return mock_metrics_table

    mock_dynamodb.Table.side_effect = table_router
    mock_bedrock = MagicMock()

    with patch('boto3.resource', return_value=mock_dynamodb), \
         patch('boto3.client', return_value=mock_bedrock):
        yield {
            'users_table': mock_users_table,
            'metrics_table': mock_metrics_table,
            'aggregates_table': mock_agg_table,
            'bedrock': mock_bedrock,
        }


class TestSubscriptionGating:
    """Test Plus subscription check."""

    def test_get_subscription_tier_plus(self, mock_boto3):
        mock_boto3['users_table'].get_item.return_value = {
            'Item': {'user_id': 'user-123', 'subscription_tier': 'plus'}
        }

        # Need to reimport after mocking
        import importlib
        import src.handlers.market_intel_chat as mod
        importlib.reload(mod)
        mod.users_table = mock_boto3['users_table']

        result = mod._get_subscription_tier('user-123')
        assert result == 'plus'

    def test_get_subscription_tier_free(self, mock_boto3):
        mock_boto3['users_table'].get_item.return_value = {
            'Item': {'user_id': 'user-123', 'subscription_tier': 'free'}
        }

        import src.handlers.market_intel_chat as mod
        mod.users_table = mock_boto3['users_table']

        result = mod._get_subscription_tier('user-123')
        assert result == 'free'

    def test_get_subscription_tier_missing_user(self, mock_boto3):
        mock_boto3['users_table'].get_item.return_value = {}

        import src.handlers.market_intel_chat as mod
        mod.users_table = mock_boto3['users_table']

        result = mod._get_subscription_tier('nonexistent')
        assert result == 'free'

    def test_get_subscription_tier_dynamo_error(self, mock_boto3):
        mock_boto3['users_table'].get_item.side_effect = Exception("DynamoDB error")

        import src.handlers.market_intel_chat as mod
        mod.users_table = mock_boto3['users_table']

        result = mod._get_subscription_tier('user-123')
        assert result == 'free'  # Fails open


class TestLambdaHandler:
    """Test the lambda_handler routing and auth."""

    def _make_event(self, message="test", token=None, is_function_url=True):
        """Build a mock Lambda event."""
        event = {
            'body': json.dumps({'message': message}),
            'headers': {},
            'requestContext': {},
        }
        if token:
            event['headers']['authorization'] = f'Bearer {token}'

        if is_function_url:
            event['requestContext']['http'] = {'method': 'POST', 'path': '/'}
        else:
            event['httpMethod'] = 'POST'

        return event

    def test_health_check(self, mock_boto3):
        import src.handlers.market_intel_chat as mod

        event = {
            'requestContext': {'http': {'method': 'GET', 'path': '/health'}},
            'headers': {},
        }
        result = mod.lambda_handler(event, None)
        assert result['status'] == 'healthy'
        assert result['service'] == 'market-intel'

    def test_no_auth_returns_401(self, mock_boto3):
        import src.handlers.market_intel_chat as mod

        event = self._make_event(token=None)
        result = mod.lambda_handler(event, None)
        assert result['statusCode'] == 401

    @patch('src.handlers.market_intel_chat.verify_jwt_token')
    @patch('src.handlers.market_intel_chat._get_subscription_tier')
    def test_free_user_returns_403(self, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-123', 'email': 'test@test.com'}
        mock_tier.return_value = 'free'

        event = self._make_event(token='valid-token')
        result = mod.lambda_handler(event, None)
        assert result['statusCode'] == 403
        assert 'Plus subscription required' in json.loads(result['body'])['error']

    @patch('src.handlers.market_intel_chat.verify_jwt_token')
    @patch('src.handlers.market_intel_chat._get_subscription_tier')
    @patch('src.handlers.market_intel_chat.stream_market_intel_response')
    def test_plus_user_gets_streaming(self, mock_stream, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-123'}
        mock_tier.return_value = 'plus'
        mock_stream.return_value = iter([{"statusCode": 200}])

        event = self._make_event(token='valid-token', is_function_url=True)
        result = mod.lambda_handler(event, None)

        mock_stream.assert_called_once()

    @patch('src.handlers.market_intel_chat.verify_jwt_token')
    @patch('src.handlers.market_intel_chat._get_subscription_tier')
    @patch('src.handlers.market_intel_chat.non_streaming_response')
    def test_plus_user_api_gateway_non_streaming(self, mock_non_stream, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-123'}
        mock_tier.return_value = 'plus'
        mock_non_stream.return_value = {'statusCode': 200, 'body': '{}'}

        event = self._make_event(token='valid-token', is_function_url=False)
        result = mod.lambda_handler(event, None)

        mock_non_stream.assert_called_once()

    @patch('src.handlers.market_intel_chat.verify_jwt_token')
    @patch('src.handlers.market_intel_chat._get_subscription_tier')
    @patch('src.handlers.market_intel_chat.stream_market_intel_response')
    def test_premium_user_allowed(self, mock_stream, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-456'}
        mock_tier.return_value = 'premium'
        mock_stream.return_value = iter([{"statusCode": 200}])

        event = self._make_event(token='valid-token')
        result = mod.lambda_handler(event, None)

        mock_stream.assert_called_once()
