"""
Integration tests for the Follow-Up Agent with real DynamoDB, mocked Bedrock.

Run with:
    AWS_PROFILE=default pytest tests/integration/test_followup_agent_integration.py -v -m integration

Requires:
    - AWS credentials with DynamoDB access to dev tables
    - BUFFETT_JWT_SECRET environment variable (optional, falls back to JWT_SECRET)
"""

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import boto3
import jwt as pyjwt
import pytest

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tests.fixtures.data_seeding import (
    seed_test_report,
    seed_test_metrics,
    seed_token_usage,
    cleanup_test_data,
)

pytestmark = pytest.mark.integration


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(scope='module')
def test_data():
    """Seed test data to real DynamoDB dev tables, cleanup after module."""
    ticker = f'INT{uuid.uuid4().hex[:4]}'.upper()
    user_id = f'integration-test-{uuid.uuid4().hex[:8]}'

    seed_test_report(ticker)
    seed_test_metrics(ticker, quarters=8)
    seed_token_usage(user_id, total_tokens=1000, limit=50000)

    yield {
        'ticker': ticker,
        'user_id': user_id,
        'session_id': f'int-session-{uuid.uuid4().hex[:8]}',
    }

    cleanup_test_data(ticker, user_id)


@pytest.fixture(scope='module')
def dynamodb_resource():
    """Real DynamoDB resource for verification queries."""
    return boto3.resource('dynamodb', region_name='us-east-1')


@pytest.fixture(autouse=True)
def integration_env():
    """Override conftest test env vars with real dev values for integration tests."""
    overrides = {
        'ENVIRONMENT': 'dev',
        'CHAT_MESSAGES_TABLE': 'buffett-dev-chat-messages',
        'TOKEN_USAGE_TABLE': 'token-usage-dev-buffett',
        'METRICS_HISTORY_CACHE_TABLE': 'metrics-history-dev',
        'INVESTMENT_REPORTS_V2_TABLE': 'investment-reports-v2-dev',
        'PROJECT_NAME': 'buffett-chat-api',
        'DEFAULT_TOKEN_LIMIT': '50000',
    }
    originals = {k: os.environ.get(k) for k in overrides}
    for k, v in overrides.items():
        os.environ[k] = v
    yield
    for k, v in originals.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture
def jwt_secret():
    """JWT secret used for signing and verifying tokens."""
    return os.environ.get('JWT_SECRET', 'test-secret-key-for-testing-only')


@pytest.fixture
def valid_jwt(test_data, jwt_secret):
    """Generate valid JWT for integration test user."""
    payload = {
        'user_id': test_data['user_id'],
        'email': 'integration-test@example.com',
        'exp': datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return pyjwt.encode(payload, jwt_secret, algorithm='HS256')


@pytest.fixture
def tool_executor_mod():
    """Import tool_executor fresh with dev env vars."""
    # Ensure ENVIRONMENT=dev for correct table names
    os.environ['ENVIRONMENT'] = 'dev'
    for mod_key in list(sys.modules.keys()):
        if 'tool_executor' in mod_key:
            del sys.modules[mod_key]
    from utils.tool_executor import execute_tool
    return execute_tool


@pytest.fixture
def mock_bedrock_end_turn():
    """Standard Bedrock converse response — simple text, stopReason=end_turn."""
    return {
        'output': {
            'message': {
                'content': [{'text': 'Based on the analysis, the company shows strong fundamentals.'}]
            }
        },
        'stopReason': 'end_turn',
        'usage': {'inputTokens': 150, 'outputTokens': 75},
    }


@pytest.fixture
def mock_bedrock_tool_use(test_data):
    """Bedrock response requesting getReportSection tool use."""
    return {
        'output': {
            'message': {
                'content': [{
                    'toolUse': {
                        'toolUseId': f'tool-{uuid.uuid4().hex[:8]}',
                        'name': 'getReportSection',
                        'input': {
                            'ticker': test_data['ticker'],
                            'section_id': '06_growth',
                        }
                    }
                }]
            }
        },
        'stopReason': 'tool_use',
        'usage': {'inputTokens': 100, 'outputTokens': 30},
    }


@pytest.fixture
def mock_bedrock_multi_turn(mock_bedrock_tool_use, mock_bedrock_end_turn):
    """Side effect list: [tool_use_response, end_turn_response]."""
    return [mock_bedrock_tool_use, mock_bedrock_end_turn]


@pytest.fixture
def handler_with_mock_bedrock():
    """Import handler with mocked Bedrock but real DynamoDB.

    Mocks only boto3.client (bedrock-runtime, bedrock-agent-runtime, secretsmanager).
    boto3.resource (DynamoDB) is NOT mocked — tables point to real dev environment.
    """
    # Clear cached modules so handler reimports with current env vars
    for mod_key in list(sys.modules.keys()):
        if any(name in mod_key for name in (
            'analysis_followup', 'token_usage_tracker', 'tool_executor',
        )):
            del sys.modules[mod_key]

    mock_bedrock_runtime = MagicMock()

    with patch('boto3.client') as mock_client:
        mock_secrets = MagicMock()
        mock_secrets.get_secret_value.return_value = {
            'SecretString': os.environ.get('JWT_SECRET', 'test-secret-key-for-testing-only')
        }

        def client_factory(service, **kwargs):
            if service == 'bedrock-runtime':
                return mock_bedrock_runtime
            if service == 'bedrock-agent-runtime':
                return MagicMock()
            if service == 'secretsmanager':
                return mock_secrets
            return MagicMock()

        mock_client.side_effect = client_factory
        from handlers import analysis_followup

    # Ensure real DynamoDB table for messages (boto3.resource was never patched)
    real_dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    analysis_followup.messages_table = real_dynamodb.Table('buffett-dev-chat-messages')

    # Explicitly assign mock to module-level client to avoid stale references
    # from Python's module caching (the import may reuse a cached module object)
    analysis_followup.bedrock_runtime_client = mock_bedrock_runtime

    return analysis_followup, mock_bedrock_runtime


@pytest.fixture
def message_cleanup(dynamodb_resource):
    """Collect session IDs during test; cleanup messages after."""
    session_ids = []
    yield session_ids
    messages_table = dynamodb_resource.Table('buffett-dev-chat-messages')
    for sid in session_ids:
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': sid},
        )
        for item in response.get('Items', []):
            messages_table.delete_item(Key={
                'conversation_id': item['conversation_id'],
                'timestamp': item['timestamp'],
            })


# ============================================================
# HELPERS
# ============================================================

def create_api_event(body, headers=None):
    """Create API Gateway-style Lambda event (non-streaming path)."""
    return {
        'body': json.dumps(body),
        'headers': headers or {},
        'requestContext': {},
    }


def consume_result(result):
    """Handle both dict and generator returns from lambda_handler."""
    if isinstance(result, dict):
        return result
    try:
        val = None
        while True:
            val = next(result)
    except StopIteration as e:
        return e.value if e.value is not None else val


# ============================================================
# TEST CLASSES
# ============================================================

class TestToolExecutionIntegration:
    """Verify each tool works against real DynamoDB dev tables."""

    def test_get_report_section(self, test_data, tool_executor_mod):
        """getReportSection retrieves growth section from real DynamoDB."""
        result = tool_executor_mod('getReportSection', {
            'ticker': test_data['ticker'],
            'section_id': '06_growth',
        })
        assert result['success'] is True
        assert result['ticker'] == test_data['ticker']
        assert 'content' in result
        assert 'growth' in result['content'].lower()

    def test_get_report_ratings(self, test_data, tool_executor_mod):
        """getReportRatings retrieves ratings from real DynamoDB."""
        result = tool_executor_mod('getReportRatings', {
            'ticker': test_data['ticker'],
        })
        assert result['success'] is True
        assert result['ticker'] == test_data['ticker']
        assert 'ratings' in result
        assert result['ratings']['overall_verdict'] == 'BUY'

    def test_get_metrics_history(self, test_data, tool_executor_mod):
        """getMetricsHistory retrieves quarterly data from real DynamoDB."""
        result = tool_executor_mod('getMetricsHistory', {
            'ticker': test_data['ticker'],
            'quarters': 4,
        })
        assert result['success'] is True
        assert result['ticker'] == test_data['ticker']
        assert result['quarters_available'] >= 1

    def test_get_available_reports(self, test_data, tool_executor_mod):
        """getAvailableReports includes test ticker in results."""
        result = tool_executor_mod('getAvailableReports', {})
        assert result['success'] is True
        assert result['count'] >= 1
        tickers = [r['ticker'] for r in result['reports']]
        assert test_data['ticker'] in tickers


class TestMessagePersistenceIntegration:
    """Verify user and assistant messages are saved to buffett-dev-chat-messages."""

    def test_messages_saved_after_request(
        self, test_data, valid_jwt, handler_with_mock_bedrock,
        mock_bedrock_end_turn, dynamodb_resource, message_cleanup,
    ):
        """Both user and assistant messages are persisted to real DynamoDB."""
        handler, mock_bedrock = handler_with_mock_bedrock
        mock_bedrock.converse.return_value = mock_bedrock_end_turn

        session_id = f'int-msg-{uuid.uuid4().hex[:8]}'
        message_cleanup.append(session_id)

        event = create_api_event(
            body={
                'question': 'What is the investment verdict?',
                'session_id': session_id,
                'agent_type': 'debt',
                'ticker': test_data['ticker'],
            },
            headers={'Authorization': f'Bearer {valid_jwt}'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 200

        body = json.loads(result['body'])
        assert body['success'] is True
        assert body['user_message_id'] is not None
        assert body['assistant_message_id'] is not None

        # Verify messages exist in real DynamoDB
        messages_table = dynamodb_resource.Table('buffett-dev-chat-messages')
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
        )

        items = response.get('Items', [])
        assert len(items) >= 2  # user + assistant

        message_types = {item['message_type'] for item in items}
        assert 'user' in message_types
        assert 'assistant' in message_types

    def test_message_metadata_correct(
        self, test_data, valid_jwt, handler_with_mock_bedrock,
        mock_bedrock_end_turn, dynamodb_resource, message_cleanup,
    ):
        """Saved messages contain correct metadata (source, agent_type, ticker)."""
        handler, mock_bedrock = handler_with_mock_bedrock
        mock_bedrock.converse.return_value = mock_bedrock_end_turn

        session_id = f'int-meta-{uuid.uuid4().hex[:8]}'
        message_cleanup.append(session_id)

        event = create_api_event(
            body={
                'question': 'Tell me about growth',
                'session_id': session_id,
                'agent_type': 'growth',
                'ticker': test_data['ticker'],
            },
            headers={'Authorization': f'Bearer {valid_jwt}'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 200

        messages_table = dynamodb_resource.Table('buffett-dev-chat-messages')
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
        )

        items = response.get('Items', [])
        user_msg = next((m for m in items if m['message_type'] == 'user'), None)
        assert user_msg is not None
        assert user_msg['user_id'] == test_data['user_id']
        assert user_msg['metadata']['source'] == 'investment_research_followup'
        assert user_msg['metadata']['agent_type'] == 'growth'
        assert user_msg['metadata']['ticker'] == test_data['ticker']


class TestTokenTrackingIntegration:
    """Verify token usage is recorded after successful requests."""

    def test_token_usage_in_response(
        self, test_data, valid_jwt, handler_with_mock_bedrock, mock_bedrock_end_turn,
    ):
        """Response includes token_usage with values from mocked Bedrock."""
        handler, mock_bedrock = handler_with_mock_bedrock
        mock_bedrock.converse.return_value = mock_bedrock_end_turn

        event = create_api_event(
            body={
                'question': 'What are the ratings?',
                'session_id': f'int-token-{uuid.uuid4().hex[:8]}',
                'agent_type': 'debt',
                'ticker': test_data['ticker'],
            },
            headers={'Authorization': f'Bearer {valid_jwt}'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 200

        body = json.loads(result['body'])
        assert 'token_usage' in body
        assert body['token_usage']['input_tokens'] == 150  # From mock
        assert body['token_usage']['output_tokens'] == 75   # From mock

    def test_token_usage_accumulates_multi_turn(
        self, test_data, valid_jwt, handler_with_mock_bedrock,
        mock_bedrock_tool_use, mock_bedrock_end_turn,
    ):
        """Token usage accumulates correctly across tool-use turns."""
        handler, mock_bedrock = handler_with_mock_bedrock
        mock_bedrock.converse.side_effect = [mock_bedrock_tool_use, mock_bedrock_end_turn]

        event = create_api_event(
            body={
                'question': 'Show me the growth section',
                'session_id': f'int-multi-{uuid.uuid4().hex[:8]}',
                'agent_type': 'debt',
                'ticker': test_data['ticker'],
            },
            headers={'Authorization': f'Bearer {valid_jwt}'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 200

        body = json.loads(result['body'])
        assert body['turns'] == 2
        # Accumulated: tool_use(100+30) + end_turn(150+75) = 250 input, 105 output
        assert body['token_usage']['input_tokens'] == 250
        assert body['token_usage']['output_tokens'] == 105

        # Reset side_effect for other tests
        mock_bedrock.converse.side_effect = None


class TestAuthenticationIntegration:
    """Verify JWT authentication flow."""

    def test_valid_jwt_allows_request(
        self, test_data, valid_jwt, handler_with_mock_bedrock, mock_bedrock_end_turn,
    ):
        """Valid JWT passes authentication and request returns 200."""
        handler, mock_bedrock = handler_with_mock_bedrock
        mock_bedrock.converse.return_value = mock_bedrock_end_turn

        event = create_api_event(
            body={
                'question': 'What is the verdict?',
                'session_id': f'int-auth-{uuid.uuid4().hex[:8]}',
                'agent_type': 'debt',
                'ticker': test_data['ticker'],
            },
            headers={'Authorization': f'Bearer {valid_jwt}'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 200

    def test_invalid_jwt_returns_401(self, handler_with_mock_bedrock):
        """Invalid JWT returns 401 Unauthorized."""
        handler, _ = handler_with_mock_bedrock

        event = create_api_event(
            body={
                'question': 'Should be rejected',
                'session_id': 'test-session',
            },
            headers={'Authorization': 'Bearer invalid.jwt.token'},
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 401

    def test_missing_jwt_returns_401(self, handler_with_mock_bedrock):
        """Missing Authorization header returns 401."""
        handler, _ = handler_with_mock_bedrock

        event = create_api_event(
            body={
                'question': 'Should be rejected',
                'session_id': 'test-session',
            },
        )

        result = consume_result(handler.lambda_handler(event, None))
        assert result['statusCode'] == 401
