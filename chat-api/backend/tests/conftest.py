"""
Pytest configuration and fixtures for BuffettGPT backend tests.
"""

import os
import sys
import pytest

# Add the src directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests (require AWS credentials)"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may incur API costs, can be skipped with -m 'not slow')"
    )


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables before each test."""
    test_env_vars = {
        # AWS / Bedrock
        'BEDROCK_REGION': 'us-east-1',
        'CHAT_MESSAGES_TABLE': 'test-chat-messages',
        'ENVIRONMENT': 'test',
        'PROJECT_NAME': 'buffett-test',
        'JWT_SECRET': 'test-secret-key-for-testing-only',
        'DEBT_AGENT_ID': 'test-debt-agent-id',
        'DEBT_AGENT_ALIAS': 'test-debt-alias',
        'CASHFLOW_AGENT_ID': 'test-cashflow-agent-id',
        'CASHFLOW_AGENT_ALIAS': 'test-cashflow-alias',
        'GROWTH_AGENT_ID': 'test-growth-agent-id',
        'GROWTH_AGENT_ALIAS': 'test-growth-alias',
        # Stripe integration
        'USERS_TABLE': 'buffett-test-users',
        'TOKEN_USAGE_TABLE': 'buffett-test-token-usage',
        'PROCESSED_EVENTS_TABLE': 'buffett-test-stripe-events',
        'TOKEN_LIMIT_PLUS': '2000000',
        'FRONTEND_URL': 'https://buffettgpt.test',
    }

    # Store original values
    original_values = {}
    for key, value in test_env_vars.items():
        original_values[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original values
    for key, original_value in original_values.items():
        if original_value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = original_value
