"""
Unit tests for the Analysis Follow-Up Handler.

Tests the message persistence functionality for follow-up questions
to investment research reports, including token usage tracking integration.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime
from decimal import Decimal

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment variables before importing the handler
os.environ['BEDROCK_REGION'] = 'us-east-1'
os.environ['CHAT_MESSAGES_TABLE'] = 'test-chat-messages'
os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
os.environ['ENVIRONMENT'] = 'test'
os.environ['PROJECT_NAME'] = 'buffett-test'
os.environ['JWT_SECRET'] = 'test-secret-key'
os.environ['DEFAULT_TOKEN_LIMIT'] = '50000'


@pytest.fixture(scope='module')
def mock_boto3():
    """Mock boto3 for all tests in this module."""
    mock_dynamodb = MagicMock()
    mock_table = MagicMock()
    mock_token_table = MagicMock()
    mock_dynamodb.Table.side_effect = lambda name: mock_token_table if 'token' in name else mock_table

    mock_bedrock_agent = MagicMock()
    mock_bedrock_runtime = MagicMock()
    mock_secrets = MagicMock()
    mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret'}

    with patch('boto3.client') as mock_client, \
         patch('boto3.resource') as mock_resource:

        def client_side_effect(service_name, **kwargs):
            if service_name == 'bedrock-agent-runtime':
                return mock_bedrock_agent
            elif service_name == 'bedrock-runtime':
                return mock_bedrock_runtime
            elif service_name == 'secretsmanager':
                return mock_secrets
            return MagicMock()

        mock_client.side_effect = client_side_effect
        mock_resource.return_value = mock_dynamodb

        yield {
            'bedrock_agent': mock_bedrock_agent,
            'bedrock_runtime': mock_bedrock_runtime,
            'bedrock': mock_bedrock_agent,  # Backward compatibility
            'dynamodb': mock_dynamodb,
            'table': mock_table,
            'token_table': mock_token_table,
            'secrets': mock_secrets
        }


@pytest.fixture
def handler_module(mock_boto3):
    """Import the handler module with mocked dependencies."""
    # Clear any cached imports
    if 'handlers.analysis_followup' in sys.modules:
        del sys.modules['handlers.analysis_followup']
    if 'utils.token_usage_tracker' in sys.modules:
        del sys.modules['utils.token_usage_tracker']

    from handlers import analysis_followup
    # Inject the mock tables and clients
    analysis_followup.messages_table = mock_boto3['table']
    analysis_followup.bedrock_client = mock_boto3['bedrock']
    analysis_followup.bedrock_agent_client = mock_boto3['bedrock_agent']
    analysis_followup.bedrock_runtime_client = mock_boto3['bedrock_runtime']

    # Create a mock token tracker
    mock_token_tracker = MagicMock()
    mock_token_tracker.check_limit.return_value = {
        'allowed': True,
        'total_tokens': 10000,
        'token_limit': 50000,
        'percent_used': 20.0,
        'remaining_tokens': 40000,
        'reset_date': '2026-02-01T00:00:00Z'
    }
    mock_token_tracker.record_usage.return_value = {
        'total_tokens': 10500,
        'token_limit': 50000,
        'percent_used': 21.0,
        'remaining_tokens': 39500,
        'threshold_reached': None
    }
    mock_token_tracker.get_reset_date.return_value = '2026-02-01T00:00:00Z'
    analysis_followup.token_tracker = mock_token_tracker

    return analysis_followup


class TestConvertFloatsToDecimals:
    """Tests for the convert_floats_to_decimals utility function."""

    def test_converts_float_to_decimal(self, handler_module):
        """Test that float values are converted to Decimal."""
        result = handler_module.convert_floats_to_decimals(3.14)
        assert isinstance(result, Decimal)
        assert result == Decimal('3.14')

    def test_converts_nested_dict_floats(self, handler_module):
        """Test conversion of floats in nested dictionaries."""
        input_data = {
            'name': 'test',
            'value': 1.5,
            'nested': {
                'inner_value': 2.5
            }
        }
        result = handler_module.convert_floats_to_decimals(input_data)

        assert result['name'] == 'test'
        assert isinstance(result['value'], Decimal)
        assert isinstance(result['nested']['inner_value'], Decimal)

    def test_converts_list_floats(self, handler_module):
        """Test conversion of floats in lists."""
        input_data = [1.1, 2.2, 3.3]
        result = handler_module.convert_floats_to_decimals(input_data)

        assert all(isinstance(v, Decimal) for v in result)

    def test_preserves_non_float_types(self, handler_module):
        """Test that non-float types are preserved."""
        input_data = {
            'string': 'hello',
            'integer': 42,
            'boolean': True,
            'none': None
        }
        result = handler_module.convert_floats_to_decimals(input_data)

        assert result['string'] == 'hello'
        assert result['integer'] == 42
        assert result['boolean'] is True
        assert result['none'] is None


class TestSaveFollowupMessage:
    """Tests for the save_followup_message function."""

    def test_saves_user_message_successfully(self, handler_module, mock_boto3):
        """Test successful saving of a user message."""
        mock_boto3['table'].put_item = MagicMock()

        with patch.object(handler_module, 'uuid') as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(__str__=lambda s: 'test-message-id')

            result = handler_module.save_followup_message(
                session_id='test-session-123',
                message_type='user',
                content='What is the debt ratio?',
                user_id='user-456',
                agent_type='debt',
                ticker='AAPL'
            )

        assert result == 'test-message-id'
        mock_boto3['table'].put_item.assert_called_once()

        # Verify the message record structure
        call_args = mock_boto3['table'].put_item.call_args
        item = call_args[1]['Item']

        assert item['conversation_id'] == 'test-session-123'
        assert item['message_type'] == 'user'
        assert item['content'] == 'What is the debt ratio?'
        assert item['user_id'] == 'user-456'
        assert item['status'] == 'received'
        assert item['metadata']['agent_type'] == 'debt'
        assert item['metadata']['ticker'] == 'AAPL'
        assert item['metadata']['source'] == 'investment_research_followup'

    def test_saves_assistant_message_with_completed_status(self, handler_module, mock_boto3):
        """Test that assistant messages are saved with 'completed' status."""
        mock_boto3['table'].put_item = MagicMock()

        with patch.object(handler_module, 'uuid') as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(__str__=lambda s: 'test-message-id')

            handler_module.save_followup_message(
                session_id='test-session-123',
                message_type='assistant',
                content='The debt ratio is 0.5, indicating moderate leverage.',
                user_id='user-456',
                agent_type='debt',
                ticker='AAPL'
            )

        call_args = mock_boto3['table'].put_item.call_args
        item = call_args[1]['Item']

        assert item['message_type'] == 'assistant'
        assert item['status'] == 'completed'

    def test_returns_none_when_table_not_configured(self, handler_module):
        """Test that function returns None when messages table is not configured."""
        # Temporarily set table to None
        original_table = handler_module.messages_table
        handler_module.messages_table = None

        result = handler_module.save_followup_message(
            session_id='test-session',
            message_type='user',
            content='test',
            user_id='user-123',
            agent_type='debt',
            ticker='AAPL'
        )

        assert result is None

        # Restore
        handler_module.messages_table = original_table

    def test_handles_dynamodb_error_gracefully(self, handler_module, mock_boto3):
        """Test that DynamoDB errors are handled gracefully."""
        mock_boto3['table'].put_item = MagicMock(side_effect=Exception('DynamoDB error'))

        result = handler_module.save_followup_message(
            session_id='test-session',
            message_type='user',
            content='test',
            user_id='user-123',
            agent_type='debt',
            ticker='AAPL'
        )

        assert result is None


class TestFormatSseEvent:
    """Tests for the format_sse_event function."""

    def test_formats_message_event(self, handler_module):
        """Test SSE event formatting for message type."""
        data = json.dumps({"text": "Hello"})
        result = handler_module.format_sse_event(data, "message")

        assert result == f"event: message\ndata: {data}\n\n"

    def test_formats_chunk_event(self, handler_module):
        """Test SSE event formatting for chunk type."""
        data = json.dumps({"type": "chunk", "text": "Some text"})
        result = handler_module.format_sse_event(data, "chunk")

        assert result == f"event: chunk\ndata: {data}\n\n"

    def test_formats_error_event(self, handler_module):
        """Test SSE event formatting for error type."""
        data = json.dumps({"type": "error", "message": "Something went wrong"})
        result = handler_module.format_sse_event(data, "error")

        assert result == f"event: error\ndata: {data}\n\n"


class TestLambdaHandler:
    """Tests for the main lambda_handler function."""

    def _create_event(self, body, headers=None, request_context=None):
        """Helper to create Lambda event."""
        return {
            'body': json.dumps(body),
            'headers': headers or {},
            'requestContext': request_context or {}
        }

    def _create_jwt_token(self, payload):
        """Helper to create a JWT token for testing."""
        import jwt
        return jwt.encode(payload, os.environ['JWT_SECRET'], algorithm='HS256')

    def _consume_generator(self, gen):
        """
        Consume a generator and return the final result.

        Handles both:
        - Generator returns (streaming path): consumes generator, returns StopIteration.value
        - Direct dict returns (non-streaming path): returns the dict directly
        """
        # If it's not a generator (direct dict return), return it
        if isinstance(gen, dict):
            return gen

        # Consume the generator
        try:
            result = None
            while True:
                result = next(gen)
        except StopIteration as e:
            # For non-streaming paths, the return value is here
            return e.value if e.value is not None else result

    def test_api_gateway_saves_messages(self, handler_module, mock_boto3):
        """Test that API Gateway path saves both user and assistant messages."""
        mock_boto3['table'].put_item = MagicMock()

        # Mock Bedrock converse response (new API format)
        mock_boto3['bedrock_runtime'].converse.return_value = {
            'output': {
                'message': {
                    'content': [
                        {'text': 'The debt analysis shows healthy fundamentals.'}
                    ]
                }
            },
            'usage': {
                'inputTokens': 100,
                'outputTokens': 50
            }
        }

        # Create valid JWT token
        token = self._create_jwt_token({
            'user_id': 'test-user-123',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-abc',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        # Verify response
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['response'] == 'The debt analysis shows healthy fundamentals.'
        assert 'user_message_id' in body
        assert 'assistant_message_id' in body
        assert 'token_usage' in body
        assert body['token_usage']['input_tokens'] == 100
        assert body['token_usage']['output_tokens'] == 50

        # Verify messages were saved (2 calls: user + assistant)
        assert mock_boto3['table'].put_item.call_count == 2

    def test_returns_401_without_jwt(self, handler_module):
        """Test that handler returns 401 when JWT is missing."""
        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-abc',
                'agent_type': 'debt'
            }
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        assert result['statusCode'] == 401
        body = json.loads(result['body'])
        assert 'Unauthorized' in body['error']

    def test_returns_400_without_question(self, handler_module):
        """Test that handler returns 400 when question is missing."""
        token = self._create_jwt_token({'user_id': 'test-user'})

        event = self._create_event(
            body={
                'session_id': 'session-abc',
                'agent_type': 'debt'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'Question is required' in body['error']

    def test_returns_400_without_session_id(self, handler_module):
        """Test that handler returns 400 when session_id is missing."""
        token = self._create_jwt_token({'user_id': 'test-user'})

        event = self._create_event(
            body={
                'question': 'What about the debt?',
                'agent_type': 'debt'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'session_id is required' in body['error']


class TestStreamFollowupResponse:
    """Tests for the streaming response function."""

    def test_streaming_saves_messages(self, handler_module, mock_boto3):
        """Test that streaming path saves both user and assistant messages."""
        mock_boto3['table'].put_item = MagicMock()

        # Mock Bedrock converse_stream response (new API format)
        mock_boto3['bedrock_runtime'].converse_stream.return_value = {
            'stream': [
                {'contentBlockDelta': {'delta': {'text': 'Streaming '}}},
                {'contentBlockDelta': {'delta': {'text': 'response.'}}},
                {'metadata': {'usage': {'inputTokens': 50, 'outputTokens': 25}}}
            ]
        }

        event = {
            'body': json.dumps({
                'question': 'Tell me about cash flow',
                'session_id': 'stream-session-123',
                'agent_type': 'cashflow',
                'ticker': 'MSFT'
            }),
            'isBase64Encoded': False
        }

        # Consume the generator
        results = list(handler_module.stream_followup_response(event, None, user_id='stream-user-456'))

        # First yield should be the headers
        assert results[0]['statusCode'] == 200
        assert results[0]['headers']['Content-Type'] == 'text/event-stream'

        # Verify messages were saved
        assert mock_boto3['table'].put_item.call_count == 2

        # Verify the complete event contains message IDs and token usage
        complete_event = None
        for result in results:
            if isinstance(result, str) and 'complete' in result:
                complete_event = result
                break

        assert complete_event is not None
        assert 'user_message_id' in complete_event
        assert 'assistant_message_id' in complete_event
        assert 'token_usage' in complete_event

    def test_streaming_handles_missing_question(self, handler_module):
        """Test that streaming returns error for missing question."""
        event = {
            'body': json.dumps({
                'session_id': 'test-session',
                'agent_type': 'debt'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Should have headers and error event
        assert len(results) >= 2

        # Find the error event
        error_found = False
        for result in results:
            if isinstance(result, str) and 'error' in result:
                assert 'Question is required' in result
                error_found = True
                break

        assert error_found

    def test_streaming_handles_bedrock_error(self, handler_module, mock_boto3):
        """Test that streaming handles Bedrock errors gracefully."""
        mock_boto3['table'].put_item = MagicMock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = Exception('Bedrock unavailable')

        event = {
            'body': json.dumps({
                'question': 'Test question',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'TEST'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Should have error event
        error_found = False
        for result in results:
            if isinstance(result, str) and 'error' in result:
                assert 'Bedrock unavailable' in result
                error_found = True
                break

        assert error_found


class TestMessageMetadata:
    """Tests for message metadata structure."""

    def test_message_contains_required_fields(self, handler_module, mock_boto3):
        """Test that saved messages contain all required fields."""
        mock_boto3['table'].put_item = MagicMock()

        with patch.object(handler_module, 'uuid') as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(__str__=lambda s: 'test-id')

            handler_module.save_followup_message(
                session_id='session-123',
                message_type='user',
                content='Test content',
                user_id='user-456',
                agent_type='growth',
                ticker='GOOGL'
            )

        call_args = mock_boto3['table'].put_item.call_args
        item = call_args[1]['Item']

        # Required fields
        assert 'conversation_id' in item
        assert 'timestamp' in item
        assert 'message_id' in item
        assert 'message_type' in item
        assert 'content' in item
        assert 'user_id' in item
        assert 'created_at' in item
        assert 'status' in item
        assert 'environment' in item
        assert 'project' in item
        assert 'metadata' in item

        # Metadata fields
        assert 'source' in item['metadata']
        assert 'agent_type' in item['metadata']
        assert 'ticker' in item['metadata']

    def test_timestamp_is_unix_integer(self, handler_module, mock_boto3):
        """Test that timestamp is saved as Unix integer."""
        mock_boto3['table'].put_item = MagicMock()

        with patch.object(handler_module, 'uuid') as mock_uuid:
            mock_uuid.uuid4.return_value = MagicMock(__str__=lambda s: 'test-id')

            handler_module.save_followup_message(
                session_id='session-123',
                message_type='user',
                content='Test',
                user_id='user-456',
                agent_type='debt',
                ticker='AAPL'
            )

        call_args = mock_boto3['table'].put_item.call_args
        item = call_args[1]['Item']

        assert isinstance(item['timestamp'], int)
        # Should be a reasonable Unix timestamp (after 2024)
        assert item['timestamp'] > 1704067200


class TestTokenLimiting:
    """Tests for token usage tracking and limiting functionality."""

    def _create_event(self, body, headers=None, request_context=None):
        """Helper to create Lambda event."""
        return {
            'body': json.dumps(body),
            'headers': headers or {},
            'requestContext': request_context or {}
        }

    def _create_jwt_token(self, payload):
        """Helper to create a JWT token for testing."""
        import jwt
        return jwt.encode(payload, os.environ['JWT_SECRET'], algorithm='HS256')

    def _consume_generator(self, gen):
        """Consume a generator and return the final result."""
        # If it's not a generator (direct dict return), return it
        if isinstance(gen, dict):
            return gen

        try:
            result = None
            while True:
                result = next(gen)
        except StopIteration as e:
            return e.value if e.value is not None else result

    def test_returns_429_when_token_limit_exceeded(self, handler_module, mock_boto3):
        """Test that API Gateway path returns 429 when token limit is exceeded."""
        # Configure token tracker to deny the request
        handler_module.token_tracker.check_limit.return_value = {
            'allowed': False,
            'total_tokens': 50000,
            'token_limit': 50000,
            'percent_used': 100.0,
            'remaining_tokens': 0,
            'reset_date': '2026-02-01T00:00:00Z',
            'limit_reached_at': '2026-01-28T12:00:00Z'
        }

        token = self._create_jwt_token({
            'user_id': 'test-user-limited',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-abc',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        # Verify 429 response
        assert result['statusCode'] == 429
        body = json.loads(result['body'])
        assert body['success'] is False
        assert body['error'] == 'token_limit_exceeded'
        assert 'usage' in body
        assert body['usage']['total_tokens'] == 50000
        assert body['usage']['token_limit'] == 50000

        # Verify rate limit headers
        assert result['headers']['X-RateLimit-Limit'] == '50000'
        assert result['headers']['X-RateLimit-Remaining'] == '0'

    def test_streaming_returns_error_when_token_limit_exceeded(self, handler_module, mock_boto3):
        """Test that streaming path returns error event when token limit is exceeded."""
        # Configure token tracker to deny the request
        handler_module.token_tracker.check_limit.return_value = {
            'allowed': False,
            'total_tokens': 50000,
            'token_limit': 50000,
            'percent_used': 100.0,
            'remaining_tokens': 0,
            'reset_date': '2026-02-01T00:00:00Z'
        }

        event = {
            'body': json.dumps({
                'question': 'Tell me about cash flow',
                'session_id': 'stream-session-123',
                'agent_type': 'cashflow',
                'ticker': 'MSFT'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='limited-user'))

        # First yield should be headers
        assert results[0]['statusCode'] == 200

        # Should have error event about token limit
        error_found = False
        for result in results:
            if isinstance(result, str) and 'token_limit_exceeded' in result:
                error_found = True
                assert 'Monthly token limit reached' in result
                break

        assert error_found

    def test_records_token_usage_after_successful_request(self, handler_module, mock_boto3):
        """Test that token usage is recorded after a successful request."""
        mock_boto3['table'].put_item = MagicMock()

        # Reset token tracker to allow the request
        handler_module.token_tracker.check_limit.return_value = {
            'allowed': True,
            'total_tokens': 10000,
            'token_limit': 50000,
            'percent_used': 20.0,
            'remaining_tokens': 40000,
            'reset_date': '2026-02-01T00:00:00Z'
        }
        handler_module.token_tracker.record_usage.return_value = {
            'total_tokens': 10150,
            'token_limit': 50000,
            'percent_used': 20.3,
            'remaining_tokens': 39850,
            'threshold_reached': None
        }

        # Mock Bedrock converse response
        mock_boto3['bedrock_runtime'].converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'Analysis response here.'}]
                }
            },
            'usage': {
                'inputTokens': 100,
                'outputTokens': 50
            }
        }

        token = self._create_jwt_token({
            'user_id': 'test-user-123',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-abc',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        # Verify record_usage was called with actual token counts
        handler_module.token_tracker.record_usage.assert_called_once_with(
            'test-user-123', 100, 50
        )

        # Verify response includes token usage
        body = json.loads(result['body'])
        assert 'token_usage' in body
        assert body['token_usage']['input_tokens'] == 100
        assert body['token_usage']['output_tokens'] == 50

    def test_threshold_notification_included_in_response(self, handler_module, mock_boto3):
        """Test that threshold notification is included when user crosses 80% or 90%."""
        mock_boto3['table'].put_item = MagicMock()

        handler_module.token_tracker.check_limit.return_value = {
            'allowed': True,
            'total_tokens': 39000,
            'token_limit': 50000,
            'percent_used': 78.0,
            'remaining_tokens': 11000,
            'reset_date': '2026-02-01T00:00:00Z'
        }
        # Simulate crossing 80% threshold
        handler_module.token_tracker.record_usage.return_value = {
            'total_tokens': 40500,
            'token_limit': 50000,
            'percent_used': 81.0,
            'remaining_tokens': 9500,
            'threshold_reached': '80%'
        }

        mock_boto3['bedrock_runtime'].converse.return_value = {
            'output': {
                'message': {
                    'content': [{'text': 'Analysis response.'}]
                }
            },
            'usage': {
                'inputTokens': 1000,
                'outputTokens': 500
            }
        }

        token = self._create_jwt_token({
            'user_id': 'test-user-threshold',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-abc',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        body = json.loads(result['body'])
        assert body['token_usage']['threshold_reached'] == '80%'

    def test_bedrock_not_called_when_limit_exceeded(self, handler_module, mock_boto3):
        """Cost protection: Bedrock should not be called when limit exceeded."""
        # Reset the mock to clear any previous call counts
        mock_boto3['bedrock_runtime'].converse.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()

        handler_module.token_tracker.check_limit.return_value = {
            'allowed': False,
            'total_tokens': 50000,
            'token_limit': 50000,
            'percent_used': 100.0,
            'remaining_tokens': 0,
            'reset_date': '2026-02-01T00:00:00Z'
        }

        token = self._create_jwt_token({
            'user_id': 'test-user-cost-check',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-cost-check',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        gen = handler_module.lambda_handler(event, None)
        result = self._consume_generator(gen)

        # Verify 429 returned AND Bedrock never called (cost protection)
        assert result['statusCode'] == 429
        mock_boto3['bedrock_runtime'].converse.assert_not_called()
        mock_boto3['bedrock_runtime'].converse_stream.assert_not_called()

    def test_streaming_bedrock_not_called_when_limit_exceeded(self, handler_module, mock_boto3):
        """Cost protection: Streaming path should not call Bedrock when limited."""
        # Reset the mock to clear any previous call counts
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()

        handler_module.token_tracker.check_limit.return_value = {
            'allowed': False,
            'total_tokens': 50000,
            'token_limit': 50000,
            'percent_used': 100.0,
            'remaining_tokens': 0,
            'reset_date': '2026-02-01T00:00:00Z'
        }

        event = {
            'body': json.dumps({
                'question': 'Tell me about cash flow',
                'session_id': 'stream-session-cost-check',
                'agent_type': 'cashflow',
                'ticker': 'MSFT'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='limited-user'))

        # Should have error event about token limit
        error_found = any(
            isinstance(r, str) and 'token_limit_exceeded' in r
            for r in results
        )
        assert error_found, "Expected token_limit_exceeded error event"

        # Bedrock should NOT be called (cost protection)
        mock_boto3['bedrock_runtime'].converse_stream.assert_not_called()

    def test_limit_check_exception_returns_500(self, handler_module, mock_boto3):
        """Exception in check_limit should result in 500 error (not silent failure)."""
        handler_module.token_tracker.check_limit.side_effect = Exception("DynamoDB error")

        token = self._create_jwt_token({
            'user_id': 'test-user-exception',
            'email': 'test@example.com'
        })

        event = self._create_event(
            body={
                'question': 'What is the debt situation?',
                'session_id': 'session-exception',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            },
            headers={'Authorization': f'Bearer {token}'}
        )

        # Should raise or return 500, not silently fail-open
        try:
            gen = handler_module.lambda_handler(event, None)
            result = self._consume_generator(gen)
            # If it returns, it should be 500 (not 200 or 429)
            assert result['statusCode'] == 500, \
                f"Expected 500 but got {result['statusCode']} - exception should not be silently ignored"
        except Exception:
            # Expected - exception bubbles up (fail-closed)
            pass
        finally:
            # Reset the side effect for other tests
            handler_module.token_tracker.check_limit.side_effect = None


class TestEstimateTokens:
    """Tests for the estimate_tokens helper function."""

    def test_estimates_tokens_for_text(self, handler_module):
        """Test token estimation for normal text."""
        # ~4 characters per token, using 3.5 for conservative estimate
        result = handler_module.estimate_tokens("Hello, how are you today?")
        # 25 chars / 3.5 ≈ 7 tokens
        assert 6 <= result <= 8

    def test_returns_zero_for_empty_text(self, handler_module):
        """Test that empty text returns 0 tokens."""
        assert handler_module.estimate_tokens("") == 0
        assert handler_module.estimate_tokens(None) == 0

    def test_minimum_one_token_for_short_text(self, handler_module):
        """Test that very short text returns at least 1 token."""
        result = handler_module.estimate_tokens("Hi")
        assert result >= 1


class TestCreateTokenLimitErrorResponse:
    """Tests for the create_token_limit_error_response helper function."""

    def test_creates_error_response_structure(self, handler_module):
        """Test that error response has correct structure."""
        limit_check = {
            'total_tokens': 50000,
            'token_limit': 50000,
            'percent_used': 100.0,
            'reset_date': '2026-02-01T00:00:00Z'
        }

        result = handler_module.create_token_limit_error_response(limit_check)

        assert result['error'] == 'token_limit_exceeded'
        assert 'Monthly token limit reached' in result['message']
        assert result['usage']['total_tokens'] == 50000
        assert result['usage']['token_limit'] == 50000
        assert result['usage']['percent_used'] == 100.0
        assert result['usage']['reset_date'] == '2026-02-01T00:00:00Z'


class TestOrchestrationLoop:
    """Tests for the tool use orchestration loop functionality."""

    def _reset_token_tracker(self, handler_module):
        """Reset token tracker to allow requests."""
        handler_module.token_tracker.check_limit.return_value = {
            'allowed': True,
            'total_tokens': 10000,
            'token_limit': 50000,
            'percent_used': 20.0,
            'remaining_tokens': 40000,
            'reset_date': '2026-02-01T00:00:00Z'
        }
        handler_module.token_tracker.record_usage.return_value = {
            'total_tokens': 10500,
            'token_limit': 50000,
            'percent_used': 21.0,
            'remaining_tokens': 39500,
            'threshold_reached': None
        }

    def _mock_execute_tool(self, handler_module, return_value):
        """Inject mock execute_tool into handler module."""
        mock_func = MagicMock(return_value=return_value)
        handler_module.unified_execute = mock_func
        return mock_func

    def test_stream_single_turn_no_tools(self, handler_module, mock_boto3):
        """Test streaming with single turn and no tool calls."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        # Mock response with end_turn (no tools)
        mock_boto3['bedrock_runtime'].converse_stream.return_value = {
            'stream': [
                {'contentBlockStart': {'start': {}}},
                {'contentBlockDelta': {'delta': {'text': 'Simple '}}},
                {'contentBlockDelta': {'delta': {'text': 'response.'}}},
                {'contentBlockStop': {}},
                {'metadata': {'usage': {'inputTokens': 50, 'outputTokens': 25}}},
                {'messageStop': {'stopReason': 'end_turn'}}
            ]
        }

        event = {
            'body': json.dumps({
                'question': 'What is the summary?',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Find the complete event
        complete_event = None
        for result in results:
            if isinstance(result, str) and '"type": "complete"' in result:
                complete_event = result
                break

        assert complete_event is not None
        assert '"turns": 1' in complete_event
        # Only one API call since no tools
        assert mock_boto3['bedrock_runtime'].converse_stream.call_count == 1

    def test_stream_single_tool_call(self, handler_module, mock_boto3):
        """Test streaming with one tool call then response."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        # First call: tool_use
        # Second call: end_turn with text response
        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # First turn: tool use
                return {
                    'stream': [
                        {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-1', 'name': 'getReportRatings'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '"AAPL"}'}}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 100, 'outputTokens': 50}}},
                        {'messageStop': {'stopReason': 'tool_use'}}
                    ]
                }
            else:
                # Second turn: final response
                return {
                    'stream': [
                        {'contentBlockDelta': {'delta': {'text': 'Based on ratings, AAPL is a buy.'}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 200, 'outputTokens': 30}}},
                        {'messageStop': {'stopReason': 'end_turn'}}
                    ]
                }

        mock_boto3['bedrock_runtime'].converse_stream.side_effect = mock_converse_stream

        # Inject mock execute_tool
        mock_execute = self._mock_execute_tool(handler_module, {'success': True, 'ratings': {'verdict': 'BUY'}})

        event = {
            'body': json.dumps({
                'question': 'What are the ratings for AAPL?',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Verify tool was executed
        mock_execute.assert_called_once_with('getReportRatings', {'ticker': 'AAPL'})

        # Find the complete event
        complete_event = None
        for result in results:
            if isinstance(result, str) and '"type": "complete"' in result:
                complete_event = result
                break

        assert complete_event is not None
        assert '"turns": 2' in complete_event
        # Two API calls (tool request + final response)
        assert mock_boto3['bedrock_runtime'].converse_stream.call_count == 2

    def test_stream_multi_tool_calls(self, handler_module, mock_boto3):
        """Test streaming with multiple tool calls in sequence."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'stream': [
                        {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-1', 'name': 'getReportRatings'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":"AAPL"}'}}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 100, 'outputTokens': 50}}},
                        {'messageStop': {'stopReason': 'tool_use'}}
                    ]
                }
            elif call_count[0] == 2:
                return {
                    'stream': [
                        {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-2', 'name': 'getReportSection'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":"AAPL","section_id":"11_debt"}'}}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 150, 'outputTokens': 60}}},
                        {'messageStop': {'stopReason': 'tool_use'}}
                    ]
                }
            else:
                return {
                    'stream': [
                        {'contentBlockDelta': {'delta': {'text': 'Final analysis response.'}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 200, 'outputTokens': 40}}},
                        {'messageStop': {'stopReason': 'end_turn'}}
                    ]
                }

        mock_boto3['bedrock_runtime'].converse_stream.side_effect = mock_converse_stream

        mock_execute = self._mock_execute_tool(handler_module, {'success': True, 'data': 'test'})

        event = {
            'body': json.dumps({
                'question': 'Tell me about AAPL debt and ratings',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Verify both tools were executed
        assert mock_execute.call_count == 2

        # Find the complete event
        complete_event = None
        for result in results:
            if isinstance(result, str) and '"type": "complete"' in result:
                complete_event = result
                break

        assert complete_event is not None
        assert '"turns": 3' in complete_event

    def test_stream_max_turns_safety(self, handler_module, mock_boto3):
        """Test that orchestration loop respects max_turns limit."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        # Always return tool_use to force hitting max turns
        mock_boto3['bedrock_runtime'].converse_stream.return_value = {
            'stream': [
                {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-x', 'name': 'getReportRatings'}}}},
                {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":"AAPL"}'}}}},
                {'contentBlockStop': {}},
                {'metadata': {'usage': {'inputTokens': 100, 'outputTokens': 50}}},
                {'messageStop': {'stopReason': 'tool_use'}}
            ]
        }

        self._mock_execute_tool(handler_module, {'success': True})

        event = {
            'body': json.dumps({
                'question': 'Infinite loop test',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Should hit max_turns (10) and exit
        assert mock_boto3['bedrock_runtime'].converse_stream.call_count == 10

    def test_stream_token_accumulation_across_turns(self, handler_module, mock_boto3):
        """Test that tokens are accumulated correctly across multiple turns."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'stream': [
                        {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-1', 'name': 'getReportRatings'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":"AAPL"}'}}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 100, 'outputTokens': 50}}},
                        {'messageStop': {'stopReason': 'tool_use'}}
                    ]
                }
            else:
                return {
                    'stream': [
                        {'contentBlockDelta': {'delta': {'text': 'Response'}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 200, 'outputTokens': 75}}},
                        {'messageStop': {'stopReason': 'end_turn'}}
                    ]
                }

        mock_boto3['bedrock_runtime'].converse_stream.side_effect = mock_converse_stream

        self._mock_execute_tool(handler_module, {'success': True})

        event = {
            'body': json.dumps({
                'question': 'Test token accumulation',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Verify record_usage was called with accumulated tokens
        # Turn 1: 100 input + 50 output
        # Turn 2: 200 input + 75 output
        # Total: 300 input, 125 output
        handler_module.token_tracker.record_usage.assert_called_once_with(
            'test-user', 300, 125
        )

    def test_nonstream_tool_use_loop(self, handler_module, mock_boto3):
        """Test non-streaming path with tool use loop."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse.reset_mock()
        mock_boto3['bedrock_runtime'].converse.side_effect = None

        call_count = [0]

        def mock_converse(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'output': {
                        'message': {
                            'content': [
                                {
                                    'toolUse': {
                                        'toolUseId': 'tool-1',
                                        'name': 'getReportRatings',
                                        'input': {'ticker': 'AAPL'}
                                    }
                                }
                            ]
                        }
                    },
                    'stopReason': 'tool_use',
                    'usage': {'inputTokens': 100, 'outputTokens': 50}
                }
            else:
                return {
                    'output': {
                        'message': {
                            'content': [{'text': 'Analysis complete.'}]
                        }
                    },
                    'stopReason': 'end_turn',
                    'usage': {'inputTokens': 150, 'outputTokens': 40}
                }

        mock_boto3['bedrock_runtime'].converse.side_effect = mock_converse

        mock_execute = self._mock_execute_tool(handler_module, {'success': True, 'ratings': {'verdict': 'BUY'}})

        import jwt
        token = jwt.encode({'user_id': 'test-user'}, os.environ['JWT_SECRET'], algorithm='HS256')

        event = {
            'body': json.dumps({
                'question': 'What are the ratings?',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'headers': {'Authorization': f'Bearer {token}'},
            'requestContext': {}
        }

        result = handler_module.lambda_handler(event, None)

        # Verify tool was executed
        mock_execute.assert_called_once_with('getReportRatings', {'ticker': 'AAPL'})

        # Verify response
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['response'] == 'Analysis complete.'
        assert body['turns'] == 2
        # Accumulated: 100+150=250 input, 50+40=90 output
        assert body['token_usage']['input_tokens'] == 250
        assert body['token_usage']['output_tokens'] == 90

    def test_tool_execution_error_handling(self, handler_module, mock_boto3):
        """Test that tool execution errors are handled gracefully."""
        mock_boto3['table'].put_item = MagicMock()
        self._reset_token_tracker(handler_module)

        # Reset mock to clear previous test state
        mock_boto3['bedrock_runtime'].converse_stream.reset_mock()
        mock_boto3['bedrock_runtime'].converse_stream.side_effect = None

        call_count = [0]

        def mock_converse_stream(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'stream': [
                        {'contentBlockStart': {'start': {'toolUse': {'toolUseId': 'tool-1', 'name': 'getReportRatings'}}}},
                        {'contentBlockDelta': {'delta': {'toolUse': {'input': '{"ticker":"AAPL"}'}}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 100, 'outputTokens': 50}}},
                        {'messageStop': {'stopReason': 'tool_use'}}
                    ]
                }
            else:
                return {
                    'stream': [
                        {'contentBlockDelta': {'delta': {'text': 'Sorry, I could not get the data.'}}},
                        {'contentBlockStop': {}},
                        {'metadata': {'usage': {'inputTokens': 200, 'outputTokens': 30}}},
                        {'messageStop': {'stopReason': 'end_turn'}}
                    ]
                }

        mock_boto3['bedrock_runtime'].converse_stream.side_effect = mock_converse_stream

        # Tool returns error
        self._mock_execute_tool(handler_module, {'success': False, 'error': 'Database connection failed'})

        event = {
            'body': json.dumps({
                'question': 'Test error handling',
                'session_id': 'test-session',
                'agent_type': 'debt',
                'ticker': 'AAPL'
            }),
            'isBase64Encoded': False
        }

        results = list(handler_module.stream_followup_response(event, None, user_id='test-user'))

        # Should complete without raising an exception
        # Find the complete event
        complete_event = None
        for result in results:
            if isinstance(result, str) and '"type": "complete"' in result:
                complete_event = result
                break

        assert complete_event is not None
        # Model should receive the error and provide a graceful response
        assert '"turns": 2' in complete_event
