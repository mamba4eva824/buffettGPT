"""
E2E tests for the Docker Lambda (investment-research) deployed to dev.

Validates:
- SSE streaming through Lambda Function URL
- Token tracking (usage recorded in DynamoDB)
- Token limit enforcement (pre-request check)
- Message persistence (user + assistant saved to DynamoDB)
- Auth validation (JWT required)

IMPORTANT: These tests hit real Bedrock and incur API costs (~$0.01-0.05 per request).

Run with:
    cd chat-api/backend
    AWS_PROFILE=default BUFFETT_JWT_SECRET='...' \
        pytest tests/e2e/test_docker_lambda_e2e.py -v -s -m e2e

Requires:
    - AWS credentials with DynamoDB access
    - BUFFETT_JWT_SECRET environment variable
    - DOCKER_LAMBDA_URL environment variable (optional, has default)
"""

import os
import sys
import uuid

import boto3
import pytest
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tests.fixtures.data_seeding import (
    seed_test_report,
    seed_test_metrics,
    seed_token_usage,
    cleanup_test_data,
    cleanup_messages,
)
from tests.e2e.conftest import post_followup_sse

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


# =============================================================================
# SSE Streaming Tests (AC-1)
# =============================================================================

class TestSSEStreaming:
    """Verify SSE event sequence from the Docker Lambda /followup endpoint."""

    def test_sse_event_sequence(self, docker_url, docker_test_data, docker_jwt):
        """
        AC-1: POST /followup returns SSE events in order:
        connected -> followup_start -> followup_chunk(s) -> followup_end.
        """
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'What is the overall investment verdict?',
            'conversation_id': docker_test_data['session_id'],
        })

        assert status == 200, f'Expected 200, got {status}'
        assert len(events) >= 3, f'Expected >= 3 events, got {len(events)}: {events}'

        event_types = [e[0] for e in events]

        # connected must come first
        assert event_types[0] == 'connected', f'First event should be connected, got {event_types[0]}'

        # followup_start must come second
        assert event_types[1] == 'followup_start', f'Second event should be followup_start, got {event_types[1]}'

        # At least one followup_chunk
        assert 'followup_chunk' in event_types, 'Expected at least one followup_chunk event'

        # followup_end must be last
        assert event_types[-1] == 'followup_end', f'Last event should be followup_end, got {event_types[-1]}'

    def test_followup_start_has_message_id(self, docker_url, docker_test_data, docker_jwt):
        """followup_start event contains message_id and ticker."""
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'Give me a quick summary',
            'conversation_id': f'start-test-{uuid.uuid4().hex[:8]}',
        })

        assert status == 200
        start_events = [e for e in events if e[0] == 'followup_start']
        assert len(start_events) == 1

        start_data = start_events[0][1]
        assert 'message_id' in start_data
        assert start_data['ticker'] == docker_test_data['ticker']

    def test_followup_chunks_contain_text(self, docker_url, docker_test_data, docker_jwt):
        """followup_chunk events contain non-empty text."""
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'What are the key risks?',
            'conversation_id': f'chunk-test-{uuid.uuid4().hex[:8]}',
        })

        assert status == 200
        chunks = [e for e in events if e[0] == 'followup_chunk']
        assert len(chunks) >= 1, 'Expected at least one chunk'

        # Concatenate all text and verify it's non-trivial
        full_text = ''.join(c[1].get('text', '') for c in chunks)
        assert len(full_text) > 20, f'Response too short: {full_text[:100]}'

    def test_health_check(self, docker_url):
        """GET /health returns 200 with status=healthy."""
        response = requests.get(f'{docker_url}/health', timeout=30)
        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'healthy'


# =============================================================================
# Token Tracking Tests (AC-2, AC-3)
# =============================================================================

class TestTokenTracking:
    """Verify token usage is recorded after successful requests."""

    @pytest.fixture(autouse=True)
    def reset_tokens(self, docker_test_data):
        """Reset user to 0 tokens before each test."""
        seed_token_usage(docker_test_data['user_id'], total_tokens=0, limit=100000)

    def test_followup_end_includes_token_usage(self, docker_url, docker_test_data, docker_jwt):
        """
        AC-2: followup_end event contains token_usage with input_tokens > 0,
        output_tokens > 0, total_tokens, and percent_used.
        """
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'What is the debt situation?',
            'conversation_id': f'token-test-{uuid.uuid4().hex[:8]}',
        })

        assert status == 200
        end_events = [e for e in events if e[0] == 'followup_end']
        assert len(end_events) == 1, f'Expected 1 followup_end, got {len(end_events)}'

        end_data = end_events[0][1]
        assert 'token_usage' in end_data, f'followup_end missing token_usage: {end_data}'

        tu = end_data['token_usage']
        assert tu['input_tokens'] > 0, f'input_tokens should be > 0, got {tu["input_tokens"]}'
        assert tu['output_tokens'] > 0, f'output_tokens should be > 0, got {tu["output_tokens"]}'
        assert 'total_tokens' in tu
        assert 'percent_used' in tu

    def test_token_usage_recorded_in_dynamodb(self, docker_url, docker_test_data, docker_jwt):
        """
        AC-3: After a request, token-usage-dev-buffett has total_tokens > 0
        and request_count >= 1 for the test user.
        """
        session_id = f'ddb-token-{uuid.uuid4().hex[:8]}'
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'How are the profit margins?',
            'conversation_id': session_id,
        })

        assert status == 200
        # Verify there was a successful completion
        end_events = [e for e in events if e[0] == 'followup_end']
        assert len(end_events) == 1

        # Query DynamoDB
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('token-usage-dev-buffett')

        response = table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': docker_test_data['user_id']},
        )

        items = response.get('Items', [])
        assert len(items) >= 1, f'Expected token usage record, got {items}'

        # Find the current billing period record
        record = items[0]
        assert int(record.get('total_tokens', 0)) > 0, (
            f'total_tokens should be > 0, got {record.get("total_tokens")}'
        )
        assert int(record.get('request_count', 0)) >= 1, (
            f'request_count should be >= 1, got {record.get("request_count")}'
        )


# =============================================================================
# Token Limit Enforcement Test (AC-4)
# =============================================================================

class TestTokenLimitEnforcement:
    """Verify token limit check blocks over-limit users."""

    def test_token_limit_exceeded_returns_error_event(
        self, docker_url, docker_test_data, docker_jwt
    ):
        """
        AC-4: User with total_tokens > token_limit gets an error SSE event
        with type=token_limit_exceeded, without Bedrock being called.
        """
        # Seed user over the limit
        seed_token_usage(
            docker_test_data['user_id'],
            total_tokens=200000,
            limit=100000,
        )

        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'Should be rejected due to token limit',
            'conversation_id': f'limit-test-{uuid.uuid4().hex[:8]}',
        })

        assert status == 200, (
            f'Expected 200 (SSE stream), got {status}'
        )

        # Should have connected, followup_start, then error
        event_types = [e[0] for e in events]
        assert 'error' in event_types, (
            f'Expected error event in stream, got: {event_types}'
        )

        error_events = [e for e in events if e[0] == 'error']
        error_data = error_events[0][1]
        assert error_data.get('type') == 'token_limit_exceeded', (
            f'Expected token_limit_exceeded, got: {error_data}'
        )

        # No followup_chunk events should exist (Bedrock was never called)
        chunks = [e for e in events if e[0] == 'followup_chunk']
        assert len(chunks) == 0, (
            f'Expected no chunks when limit exceeded, got {len(chunks)}'
        )

        # Reset for other tests
        seed_token_usage(docker_test_data['user_id'], total_tokens=0, limit=100000)


# =============================================================================
# Message Persistence Tests (AC-5, AC-6)
# =============================================================================

class TestMessagePersistence:
    """Verify user and assistant messages are saved to DynamoDB."""

    @pytest.fixture(autouse=True)
    def reset_tokens(self, docker_test_data):
        """Reset user to 0 tokens before each test."""
        seed_token_usage(docker_test_data['user_id'], total_tokens=0, limit=100000)

    def test_messages_saved_to_dynamodb(
        self, docker_url, docker_test_data, docker_jwt, message_cleanup
    ):
        """
        AC-5: After a request, buffett-dev-chat-messages contains exactly
        2 messages (user + assistant) with correct user_id, ticker, content.
        """
        session_id = f'msg-persist-{uuid.uuid4().hex[:8]}'
        message_cleanup.append(session_id)

        question = 'Tell me about the growth analysis'
        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': question,
            'conversation_id': session_id,
        })

        assert status == 200
        end_events = [e for e in events if e[0] == 'followup_end']
        assert len(end_events) == 1

        # Query DynamoDB for messages
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('buffett-dev-chat-messages')

        response = table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
        )

        items = response.get('Items', [])
        assert len(items) >= 2, (
            f'Expected 2 messages (user+assistant), got {len(items)}: {items}'
        )

        message_types = {item['message_type'] for item in items}
        assert 'user' in message_types, 'Missing user message'
        assert 'assistant' in message_types, 'Missing assistant message'

        # Verify user message content
        user_msg = next(m for m in items if m['message_type'] == 'user')
        assert user_msg['content'] == question
        assert user_msg['user_id'] == docker_test_data['user_id']
        assert user_msg['metadata']['ticker'] == docker_test_data['ticker']
        assert user_msg['metadata']['source'] == 'investment_research_followup'

        # Verify assistant message has non-empty content
        assistant_msg = next(m for m in items if m['message_type'] == 'assistant')
        assert len(assistant_msg['content']) > 20, (
            f'Assistant message too short: {assistant_msg["content"][:100]}'
        )

    def test_followup_end_includes_message_ids(
        self, docker_url, docker_test_data, docker_jwt, message_cleanup
    ):
        """
        AC-6: followup_end event contains user_message_id and
        assistant_message_id matching the persisted records.
        """
        session_id = f'msg-ids-{uuid.uuid4().hex[:8]}'
        message_cleanup.append(session_id)

        status, events = post_followup_sse(docker_url, docker_jwt, {
            'ticker': docker_test_data['ticker'],
            'question': 'What is the valuation?',
            'conversation_id': session_id,
        })

        assert status == 200
        end_events = [e for e in events if e[0] == 'followup_end']
        assert len(end_events) == 1

        end_data = end_events[0][1]
        assert 'user_message_id' in end_data, (
            f'followup_end missing user_message_id: {end_data}'
        )
        assert 'assistant_message_id' in end_data, (
            f'followup_end missing assistant_message_id: {end_data}'
        )

        # Verify these IDs match actual DynamoDB records
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('buffett-dev-chat-messages')

        response = table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': session_id},
        )

        items = response.get('Items', [])
        saved_ids = {item['message_id'] for item in items}

        assert end_data['user_message_id'] in saved_ids, (
            f'user_message_id {end_data["user_message_id"]} not found in DynamoDB'
        )
        assert end_data['assistant_message_id'] in saved_ids, (
            f'assistant_message_id {end_data["assistant_message_id"]} not found in DynamoDB'
        )


# =============================================================================
# Auth Validation Tests (AC-7, AC-8)
# =============================================================================

class TestAuthValidation:
    """Verify JWT authentication is enforced."""

    def test_invalid_jwt_rejected(self, docker_url, docker_test_data):
        """AC-7: Invalid JWT returns 401 or 403."""
        response = requests.post(
            f'{docker_url}/followup',
            headers={
                'Authorization': 'Bearer invalid.jwt.token',
                'Content-Type': 'application/json',
            },
            json={
                'ticker': docker_test_data['ticker'],
                'question': 'Should be rejected',
                'conversation_id': 'auth-test',
            },
            timeout=30,
        )

        assert response.status_code in (401, 403), (
            f'Expected 401 or 403, got {response.status_code}: {response.text[:200]}'
        )

    def test_missing_auth_rejected(self, docker_url, docker_test_data):
        """AC-8: Missing Authorization header returns 401 or 403."""
        response = requests.post(
            f'{docker_url}/followup',
            headers={'Content-Type': 'application/json'},
            json={
                'ticker': docker_test_data['ticker'],
                'question': 'Should be rejected',
                'conversation_id': 'auth-test',
            },
            timeout=30,
        )

        assert response.status_code in (401, 403), (
            f'Expected 401 or 403, got {response.status_code}: {response.text[:200]}'
        )
