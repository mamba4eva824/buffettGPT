"""
E2E tests hitting the deployed dev API.

IMPORTANT: These tests incur Bedrock API costs!

Run with:
    AWS_PROFILE=default BUFFETT_JWT_SECRET='...' \
        pytest tests/e2e/test_followup_agent_e2e.py -v -m e2e

Requires:
    - AWS credentials
    - BUFFETT_JWT_SECRET environment variable
    - ANALYSIS_FOLLOWUP_URL environment variable (optional, has default)
"""

import os
import sys

import pytest
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tests.fixtures.data_seeding import (
    seed_test_report,
    seed_test_metrics,
    seed_token_usage,
    cleanup_test_data,
)

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

API_URL = os.environ.get(
    'ANALYSIS_FOLLOWUP_URL',
    'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev'
)


class TestFollowupAgentE2E:
    """Full E2E tests against deployed API."""

    @pytest.fixture(autouse=True)
    def reset_token_usage(self, e2e_test_data):
        """Reset user to 0 tokens before each test."""
        seed_token_usage(e2e_test_data['user_id'], total_tokens=0, limit=50000)
        yield

    def test_health_check(self):
        """GET /health returns 200 with status=healthy."""
        response = requests.get(f"{API_URL}/health", timeout=30)

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'healthy'

    def test_happy_path_simple_question(self, e2e_test_data, e2e_jwt):
        """POST /research/followup with valid JWT returns successful response."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json',
            },
            json={
                'question': 'What is the overall investment verdict?',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
                'agent_type': 'debt',
            },
            timeout=60,
        )

        assert response.status_code == 200, (
            f"Expected 200, got {response.status_code}: {response.text[:200]}"
        )
        body = response.json()
        assert body['success'] is True
        assert len(body['response']) > 50  # Non-trivial response
        assert body['turns'] >= 1
        assert body['token_usage']['input_tokens'] > 0
        assert body['token_usage']['output_tokens'] > 0

    def test_tool_invocation_growth_question(self, e2e_test_data, e2e_jwt):
        """Growth question triggers tools; response contains growth-related content."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json',
            },
            json={
                'question': 'Tell me about the growth analysis section',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
            },
            timeout=60,
        )

        assert response.status_code == 200
        body = response.json()
        assert body['success'] is True
        # Response should mention growth (AI may phrase differently, so check broadly)
        assert 'growth' in body['response'].lower() or 'revenue' in body['response'].lower()

    def test_multi_turn_metrics_question(self, e2e_test_data, e2e_jwt):
        """Metrics question references historical data."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json',
            },
            json={
                'question': 'Show me the historical revenue and profit metrics for this company',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
            },
            timeout=60,
        )

        assert response.status_code == 200
        body = response.json()
        assert body['success'] is True
        assert len(body['response']) > 50

    def test_token_limit_exceeded(self, e2e_test_data, e2e_jwt):
        """Request rejected when token limit exceeded (429)."""
        # Seed user over the limit
        seed_token_usage(e2e_test_data['user_id'], total_tokens=60000, limit=50000)

        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json',
            },
            json={
                'question': 'Should be rejected due to token limit',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
            },
            timeout=30,
        )

        assert response.status_code == 429
        body = response.json()
        assert (
            'limit' in body.get('error', '').lower()
            or 'limit' in body.get('message', '').lower()
        )

    def test_invalid_jwt_rejected(self, e2e_test_data):
        """Invalid JWT returns 401."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': 'Bearer invalid.jwt.token',
                'Content-Type': 'application/json',
            },
            json={
                'question': 'Should be rejected',
                'session_id': e2e_test_data['session_id'],
            },
            timeout=30,
        )

        assert response.status_code == 401

    def test_missing_auth_rejected(self, e2e_test_data):
        """Missing Authorization header returns 401."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={'Content-Type': 'application/json'},
            json={
                'question': 'Should be rejected',
                'session_id': e2e_test_data['session_id'],
            },
            timeout=30,
        )

        assert response.status_code == 401

    def test_missing_required_fields(self, e2e_test_data, e2e_jwt):
        """Missing question field returns 400."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json',
            },
            json={
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
            },
            timeout=30,
        )

        assert response.status_code == 400
