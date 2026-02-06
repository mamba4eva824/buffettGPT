"""
Performance test fixtures for Stripe integration load testing.

Extends patterns from tests/conftest.py with:
- moto DynamoDB setup for users, token-usage, stripe-events tables
- Metrics collection hooks (timing decorators)
- @pytest.mark.performance marker registration
"""

import os
import sys
import time
import functools

import boto3
import pytest
from moto import mock_aws

# Add src to path (matches tests/conftest.py pattern)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Add backend root to path so `tests.performance.*` is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.performance.utils.metrics_collector import MetricsCollector


# ---------------------------------------------------------------------------
# Marker registration
# ---------------------------------------------------------------------------

def pytest_configure(config):
    """Register the performance marker."""
    config.addinivalue_line(
        "markers", "performance: marks tests as performance tests"
    )


# ---------------------------------------------------------------------------
# Environment fixture (mirrors tests/conftest.py)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def performance_test_env():
    """Set environment variables for performance tests."""
    env_vars = {
        'ENVIRONMENT': 'test',
        'BEDROCK_REGION': 'us-east-1',
        'CHAT_MESSAGES_TABLE': 'test-chat-messages',
        'PROJECT_NAME': 'buffett-test',
        'JWT_SECRET': 'test-secret-key-for-testing-only',
        'USERS_TABLE': 'buffett-test-users',
        'TOKEN_USAGE_TABLE': 'buffett-test-token-usage',
        'PROCESSED_EVENTS_TABLE': 'buffett-test-stripe-events',
        'TOKEN_LIMIT_PLUS': '2000000',
        'FRONTEND_URL': 'https://buffettgpt.test',
    }

    original = {}
    for key, value in env_vars.items():
        original[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    for key, orig_val in original.items():
        if orig_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = orig_val


# ---------------------------------------------------------------------------
# DynamoDB table helpers (from test_stripe_webhook_handler.py)
# ---------------------------------------------------------------------------

def create_users_table(dynamodb):
    """Create users table with stripe-customer-index GSI."""
    table = dynamodb.create_table(
        TableName='buffett-test-users',
        KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'stripe_customer_id', 'AttributeType': 'S'},
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'stripe-customer-index',
            'KeySchema': [{'AttributeName': 'stripe_customer_id', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def create_token_usage_table(dynamodb):
    """Create token-usage table with composite key (user_id, billing_period)."""
    table = dynamodb.create_table(
        TableName='buffett-test-token-usage',
        KeySchema=[
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            {'AttributeName': 'billing_period', 'KeyType': 'RANGE'},
        ],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'billing_period', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def create_stripe_events_table(dynamodb):
    """Create stripe-events table for idempotency tracking."""
    table = dynamodb.create_table(
        TableName='buffett-test-stripe-events',
        KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'event_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST',
    )
    table.wait_until_exists()
    return table


def create_all_tables(dynamodb):
    """Create all required DynamoDB tables."""
    return {
        'users': create_users_table(dynamodb),
        'token_usage': create_token_usage_table(dynamodb),
        'events': create_stripe_events_table(dynamodb),
    }


# ---------------------------------------------------------------------------
# DynamoDB fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def aws_mock():
    """Provide a moto mock_aws context."""
    with mock_aws():
        yield


@pytest.fixture
def dynamodb_resource(aws_mock):
    """Provide a moto-backed DynamoDB resource."""
    return boto3.resource('dynamodb', region_name='us-east-1')


@pytest.fixture
def dynamodb_tables(dynamodb_resource):
    """Create all DynamoDB tables and return them as a dict."""
    return create_all_tables(dynamodb_resource)


@pytest.fixture
def users_table(dynamodb_tables):
    """Shortcut to the users table."""
    return dynamodb_tables['users']


@pytest.fixture
def token_usage_table(dynamodb_tables):
    """Shortcut to the token-usage table."""
    return dynamodb_tables['token_usage']


@pytest.fixture
def stripe_events_table(dynamodb_tables):
    """Shortcut to the stripe-events idempotency table."""
    return dynamodb_tables['events']


# ---------------------------------------------------------------------------
# Metrics collection
# ---------------------------------------------------------------------------

@pytest.fixture
def metrics():
    """Provide a fresh MetricsCollector for a test."""
    return MetricsCollector()


def timed(metric_name, collector):
    """Decorator that records execution time of a function into *collector*.

    Usage::

        mc = MetricsCollector()

        @timed('webhook_processing', mc)
        def process():
            ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                collector.record(metric_name, elapsed_ms)
        return wrapper
    return decorator
