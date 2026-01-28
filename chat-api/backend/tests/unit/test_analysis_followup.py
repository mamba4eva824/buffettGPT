"""
Unit tests for the Analysis Follow-Up Handler.

Tests the message persistence functionality for follow-up questions
to investment research reports.
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
os.environ['ENVIRONMENT'] = 'test'
os.environ['PROJECT_NAME'] = 'buffett-test'
os.environ['JWT_SECRET'] = 'test-secret-key'
os.environ['DEBT_AGENT_ID'] = 'test-debt-agent-id'
os.environ['DEBT_AGENT_ALIAS'] = 'test-debt-alias'
os.environ['CASHFLOW_AGENT_ID'] = 'test-cashflow-agent-id'
os.environ['CASHFLOW_AGENT_ALIAS'] = 'test-cashflow-alias'
os.environ['GROWTH_AGENT_ID'] = 'test-growth-agent-id'
os.environ['GROWTH_AGENT_ALIAS'] = 'test-growth-alias'


@pytest.fixture(scope='module')
def mock_boto3():
    """Mock boto3 for all tests in this module."""
    mock_dynamodb = MagicMock()
    mock_table = MagicMock()
    mock_dynamodb.Table.return_value = mock_table

    mock_bedrock = MagicMock()
    mock_secrets = MagicMock()
    mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret'}

    with patch('boto3.client') as mock_client, \
         patch('boto3.resource') as mock_resource:

        def client_side_effect(service_name, **kwargs):
            if service_name == 'bedrock-agent-runtime':
                return mock_bedrock
            elif service_name == 'secretsmanager':
                return mock_secrets
            return MagicMock()

        mock_client.side_effect = client_side_effect
        mock_resource.return_value = mock_dynamodb

        yield {
            'bedrock': mock_bedrock,
            'dynamodb': mock_dynamodb,
            'table': mock_table,
            'secrets': mock_secrets
        }


@pytest.fixture
def handler_module(mock_boto3):
    """Import the handler module with mocked dependencies."""
    # Clear any cached imports
    if 'handlers.analysis_followup' in sys.modules:
        del sys.modules['handlers.analysis_followup']

    from handlers import analysis_followup
    # Inject the mock table
    analysis_followup.messages_table = mock_boto3['table']
    analysis_followup.bedrock_client = mock_boto3['bedrock']

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

    def test_api_gateway_saves_messages(self, handler_module, mock_boto3):
        """Test that API Gateway path saves both user and assistant messages."""
        mock_boto3['table'].put_item = MagicMock()

        # Mock Bedrock response
        mock_boto3['bedrock'].invoke_agent.return_value = {
            'completion': [
                {'chunk': {'bytes': b'The debt analysis shows '}},
                {'chunk': {'bytes': b'healthy fundamentals.'}}
            ]
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

        result = handler_module.lambda_handler(event, None)

        # Verify response
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['response'] == 'The debt analysis shows healthy fundamentals.'
        assert 'user_message_id' in body
        assert 'assistant_message_id' in body

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

        result = handler_module.lambda_handler(event, None)

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

        result = handler_module.lambda_handler(event, None)

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

        result = handler_module.lambda_handler(event, None)

        assert result['statusCode'] == 400
        body = json.loads(result['body'])
        assert 'session_id is required' in body['error']


class TestStreamFollowupResponse:
    """Tests for the streaming response function."""

    def test_streaming_saves_messages(self, handler_module, mock_boto3):
        """Test that streaming path saves both user and assistant messages."""
        mock_boto3['table'].put_item = MagicMock()

        # Mock Bedrock streaming response
        mock_boto3['bedrock'].invoke_agent.return_value = {
            'completion': [
                {'chunk': {'bytes': b'Streaming '}},
                {'chunk': {'bytes': b'response.'}}
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

        # Verify the complete event contains message IDs
        complete_event = None
        for result in results:
            if isinstance(result, str) and 'complete' in result:
                complete_event = result
                break

        assert complete_event is not None
        assert 'user_message_id' in complete_event
        assert 'assistant_message_id' in complete_event

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
        mock_boto3['bedrock'].invoke_agent.side_effect = Exception('Bedrock unavailable')

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
