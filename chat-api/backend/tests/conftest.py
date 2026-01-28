"""
Pytest configuration and fixtures for BuffettGPT backend tests.
"""

import os
import sys
import pytest

# Add the src directory to the Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


@pytest.fixture(autouse=True)
def setup_test_environment():
    """Setup test environment variables before each test."""
    test_env_vars = {
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
