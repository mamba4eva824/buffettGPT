"""
E2E-specific pytest fixtures.

Provides fixtures for:
- Test data seeding/cleanup with unique tickers
- JWT generation for authenticated requests
- API URL configuration
- Docker Lambda SSE streaming helpers
"""

import json
import os
import random
import string
import sys
import uuid

import jwt
import pytest
import requests
from datetime import datetime, timedelta

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tests.fixtures.data_seeding import (
    seed_test_report,
    seed_test_metrics,
    seed_token_usage,
    cleanup_test_data,
    cleanup_messages,
)


# ---------------------------------------------------------------------------
# URL configuration
# ---------------------------------------------------------------------------

API_URL = os.environ.get(
    'ANALYSIS_FOLLOWUP_URL',
    'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev'
)

DOCKER_LAMBDA_URL = os.environ.get(
    'DOCKER_LAMBDA_URL',
    'https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws'
)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def parse_sse_stream(response):
    """
    Parse a raw text/event-stream response into a list of (event_type, data_dict) tuples.

    Handles the SSE wire format:
        event: <type>
        data: <json>

    Args:
        response: requests.Response with stream=True

    Returns:
        List of (event_type, parsed_data_dict) tuples
    """
    events = []
    current_event = None
    current_data = ''

    for line in response.iter_lines(decode_unicode=True):
        if line is None:
            continue

        if line.startswith('event:'):
            current_event = line[len('event:'):].strip()
        elif line.startswith('data:'):
            current_data = line[len('data:'):].strip()
        elif line == '':
            # Empty line = end of event block
            if current_event and current_data:
                try:
                    data = json.loads(current_data)
                except json.JSONDecodeError:
                    data = {'raw': current_data}
                events.append((current_event, data))
            current_event = None
            current_data = ''

    # Handle final event if stream ends without trailing newline
    if current_event and current_data:
        try:
            data = json.loads(current_data)
        except json.JSONDecodeError:
            data = {'raw': current_data}
        events.append((current_event, data))

    return events


def post_followup_sse(base_url, token, payload, timeout=90):
    """
    POST to /followup and return parsed SSE events.

    Args:
        base_url: Docker Lambda Function URL (no trailing slash)
        token: JWT bearer token
        payload: dict with ticker, question, conversation_id, etc.
        timeout: request timeout in seconds

    Returns:
        (status_code, events_list) where events_list is [(event_type, data_dict), ...]
    """
    response = requests.post(
        f'{base_url}/followup',
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        json=payload,
        stream=True,
        timeout=timeout,
    )

    if response.status_code != 200:
        return response.status_code, []

    events = parse_sse_stream(response)
    return response.status_code, events


# ---------------------------------------------------------------------------
# Shared fixtures - zip Lambda (existing)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def api_url():
    """Base URL for the deployed zip Lambda API."""
    return API_URL


@pytest.fixture(scope='module')
def e2e_test_data():
    """Seed E2E test data with unique ticker, cleanup after module."""
    ticker = f'E2E{uuid.uuid4().hex[:4]}'.upper()
    user_id = f'e2e-test-{uuid.uuid4().hex[:8]}'

    seed_test_report(ticker)
    seed_test_metrics(ticker, quarters=8)
    seed_token_usage(user_id, total_tokens=0, limit=50000)

    yield {
        'ticker': ticker,
        'user_id': user_id,
        'session_id': f'e2e-session-{uuid.uuid4().hex[:8]}'
    }

    cleanup_test_data(ticker, user_id)


@pytest.fixture
def e2e_jwt(e2e_test_data):
    """Generate valid JWT for E2E test user."""
    secret = os.environ.get('BUFFETT_JWT_SECRET')
    if not secret:
        pytest.skip('BUFFETT_JWT_SECRET not set')

    payload = {
        'user_id': e2e_test_data['user_id'],
        'email': 'e2e-test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


# ---------------------------------------------------------------------------
# Docker Lambda fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope='module')
def docker_url():
    """Base URL for the deployed Docker Lambda Function URL."""
    return DOCKER_LAMBDA_URL


def _random_alpha(n: int) -> str:
    """Generate a random uppercase alpha string of length n."""
    return ''.join(random.choices(string.ascii_uppercase, k=n))


@pytest.fixture(scope='module')
def docker_test_data():
    """Seed test data for Docker Lambda e2e tests, cleanup after module."""
    # Ticker must be 1-5 uppercase alpha (no digits) to pass validate_ticker
    ticker = f'D{_random_alpha(4)}'
    user_id = f'docker-e2e-{uuid.uuid4().hex[:8]}'

    seed_test_report(ticker)
    seed_test_metrics(ticker, quarters=8)
    seed_token_usage(user_id, total_tokens=0, limit=100000)

    yield {
        'ticker': ticker,
        'user_id': user_id,
        'session_id': f'dkr-session-{uuid.uuid4().hex[:8]}',
    }

    cleanup_test_data(ticker, user_id)


@pytest.fixture
def docker_jwt(docker_test_data):
    """Generate valid JWT for Docker Lambda e2e test user."""
    secret = os.environ.get('BUFFETT_JWT_SECRET')
    if not secret:
        pytest.skip('BUFFETT_JWT_SECRET not set')

    payload = {
        'user_id': docker_test_data['user_id'],
        'email': 'docker-e2e-test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm='HS256')


@pytest.fixture
def docker_session_id():
    """Generate a unique session ID for message isolation."""
    return f'dkr-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture
def message_cleanup():
    """Collect session IDs during tests; cleanup messages after."""
    session_ids = []
    yield session_ids
    cleanup_messages(session_ids)
