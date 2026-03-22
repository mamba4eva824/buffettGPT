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
os.environ['CONVERSATIONS_TABLE'] = 'buffett-test-conversations'
os.environ['CHAT_MESSAGES_TABLE'] = 'buffett-test-chat-messages'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['SP500_AGGREGATES_TABLE'] = 'buffett-test-sp500-aggregates'


@pytest.fixture(autouse=True)
def mock_boto3():
    """Mock boto3 for all tests."""
    mock_dynamodb = MagicMock()
    mock_users_table = MagicMock()
    mock_conversations_table = MagicMock()
    mock_messages_table = MagicMock()
    mock_metrics_table = MagicMock()
    mock_agg_table = MagicMock()

    def table_router(name):
        if 'users' in name:
            return mock_users_table
        elif 'conversations' in name:
            return mock_conversations_table
        elif 'chat-messages' in name:
            return mock_messages_table
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
            'conversations_table': mock_conversations_table,
            'messages_table': mock_messages_table,
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
    @patch('src.handlers.market_intel_chat.non_streaming_response')
    def test_plus_user_gets_response(self, mock_non_stream, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-123'}
        mock_tier.return_value = 'plus'
        mock_non_stream.return_value = {'statusCode': 200, 'body': '{}'}

        event = self._make_event(token='valid-token', is_function_url=True)
        result = mod.lambda_handler(event, None)

        mock_non_stream.assert_called_once()

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
    @patch('src.handlers.market_intel_chat.non_streaming_response')
    def test_premium_user_allowed(self, mock_non_stream, mock_tier, mock_jwt, mock_boto3):
        import src.handlers.market_intel_chat as mod

        mock_jwt.return_value = {'user_id': 'user-456'}
        mock_tier.return_value = 'premium'
        mock_non_stream.return_value = {'statusCode': 200, 'body': '{}'}

        event = self._make_event(token='valid-token')
        result = mod.lambda_handler(event, None)

        mock_non_stream.assert_called_once()


class TestMessagePersistence:
    """Test save_message and update_conversation_record."""

    def test_save_message_success(self, mock_boto3):
        import importlib
        import src.handlers.market_intel_chat as mod
        importlib.reload(mod)
        mod.messages_table = mock_boto3['messages_table']

        result = mod.save_message('conv-123', 'user', 'Hello', 'user-1')
        assert result is not None
        mock_boto3['messages_table'].put_item.assert_called_once()
        item = mock_boto3['messages_table'].put_item.call_args[1]['Item']
        assert item['conversation_id'] == 'conv-123'
        assert item['message_type'] == 'user'
        assert item['content'] == 'Hello'
        assert item['user_id'] == 'user-1'
        assert item['metadata']['source'] == 'market_intelligence'
        assert item['status'] == 'received'

    def test_save_message_assistant_status(self, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.messages_table = mock_boto3['messages_table']

        mod.save_message('conv-123', 'assistant', 'Response text', 'user-1')
        item = mock_boto3['messages_table'].put_item.call_args[1]['Item']
        assert item['status'] == 'completed'

    def test_save_message_timestamp_offset(self, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.messages_table = mock_boto3['messages_table']

        mod.save_message('conv-1', 'user', 'Q', 'u1', timestamp_offset_ms=0)
        ts1 = mock_boto3['messages_table'].put_item.call_args[1]['Item']['timestamp']

        mod.save_message('conv-1', 'assistant', 'A', 'u1', timestamp_offset_ms=1)
        ts2 = mock_boto3['messages_table'].put_item.call_args[1]['Item']['timestamp']

        # Assistant timestamp should be >= user timestamp (with offset)
        assert ts2 >= ts1

    def test_save_message_dynamo_error_returns_none(self, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.messages_table = mock_boto3['messages_table']
        mock_boto3['messages_table'].put_item.side_effect = Exception("DynamoDB error")

        result = mod.save_message('conv-123', 'user', 'Hello', 'user-1')
        assert result is None

    def test_update_conversation_record(self, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.conversations_table = mock_boto3['conversations_table']

        mod.update_conversation_record('conv-123', 'user-1', message_count_increment=2)
        mock_boto3['conversations_table'].update_item.assert_called_once()
        call_kwargs = mock_boto3['conversations_table'].update_item.call_args[1]
        assert call_kwargs['Key'] == {'conversation_id': 'conv-123'}
        assert ':inc' in call_kwargs['ExpressionAttributeValues']
        assert call_kwargs['ExpressionAttributeValues'][':inc'] == 2

    def test_update_conversation_record_error_raises(self, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.conversations_table = mock_boto3['conversations_table']
        mock_boto3['conversations_table'].update_item.side_effect = Exception("DynamoDB error")

        with pytest.raises(Exception, match="DynamoDB error"):
            mod.update_conversation_record('conv-123', 'user-1')


class TestNonStreamingWithPersistence:
    """Test that non_streaming_response saves messages when conversation_id provided."""

    @patch('src.handlers.market_intel_chat.token_tracker')
    @patch('src.handlers.market_intel_chat.bedrock_runtime')
    def test_saves_messages_when_conversation_id_provided(self, mock_bedrock, mock_tracker, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.messages_table = mock_boto3['messages_table']
        mod.conversations_table = mock_boto3['conversations_table']

        mock_bedrock.converse.return_value = {
            'output': {'message': {'content': [{'text': 'AI response'}]}},
            'stopReason': 'end_turn',
            'usage': {'inputTokens': 10, 'outputTokens': 20}
        }
        mock_tracker.record_usage.return_value = {'total_tokens': 30}

        event = {
            'body': json.dumps({
                'message': 'Test question',
                'conversation_id': 'conv-abc'
            })
        }

        result = mod.non_streaming_response(event, None, user_id='user-1')
        body = json.loads(result['body'])

        assert body['conversation_id'] == 'conv-abc'
        assert body['response'] == 'AI response'
        assert mock_boto3['messages_table'].put_item.call_count == 2  # user + assistant
        mock_boto3['conversations_table'].update_item.assert_called_once()

    @patch('src.handlers.market_intel_chat.token_tracker')
    @patch('src.handlers.market_intel_chat.bedrock_runtime')
    def test_skips_persistence_without_conversation_id(self, mock_bedrock, mock_tracker, mock_boto3):
        import src.handlers.market_intel_chat as mod
        mod.messages_table = mock_boto3['messages_table']
        mod.conversations_table = mock_boto3['conversations_table']

        mock_bedrock.converse.return_value = {
            'output': {'message': {'content': [{'text': 'AI response'}]}},
            'stopReason': 'end_turn',
            'usage': {'inputTokens': 10, 'outputTokens': 20}
        }
        mock_tracker.record_usage.return_value = {'total_tokens': 30}

        event = {
            'body': json.dumps({'message': 'Test question'})
        }

        result = mod.non_streaming_response(event, None, user_id='user-1')
        body = json.loads(result['body'])

        assert body['conversation_id'] is None
        mock_boto3['messages_table'].put_item.assert_not_called()
        mock_boto3['conversations_table'].update_item.assert_not_called()
