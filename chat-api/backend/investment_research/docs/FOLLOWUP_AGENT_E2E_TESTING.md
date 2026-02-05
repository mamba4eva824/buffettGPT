# Follow-Up Agent - E2E Integration Testing Guide

**Document Version:** 1.0
**Created:** February 4, 2026
**Status:** Reference Guide

---

## Table of Contents

1. [Overview](#overview)
2. [Test Categories](#test-categories)
3. [Prerequisites](#prerequisites)
4. [Test Scenarios Matrix](#test-scenarios-matrix)
5. [Running Tests](#running-tests)
6. [Test Data Seeding](#test-data-seeding)
7. [Unit Test Patterns](#unit-test-patterns)
8. [Integration Test Patterns](#integration-test-patterns)
9. [E2E Test Patterns](#e2e-test-patterns)
10. [Best Practices](#best-practices)
11. [CI/CD Integration](#cicd-integration)
12. [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers integration and E2E testing strategies for the Follow-Up Agent, which enables users to ask natural language questions about investment reports using Amazon Bedrock's Converse API.

### System Under Test

| Component | Location | Purpose |
|-----------|----------|---------|
| Handler | `src/handlers/analysis_followup.py` | Lambda handler (1,092 lines) |
| Tool Executor | `src/utils/tool_executor.py` | DynamoDB tool implementations (409 lines) |
| Token Tracker | `src/utils/token_usage_tracker.py` | Monthly usage limits |

### External Dependencies

| Service | Resource | Purpose |
|---------|----------|---------|
| Bedrock | Claude Haiku 4.5 | Natural language processing |
| DynamoDB | `investment-reports-v2-dev` | Report sections |
| DynamoDB | `metrics-history-cache-dev` | Historical metrics |
| DynamoDB | `buffett-dev-chat-messages` | Conversation history |
| DynamoDB | `buffett-dev-token-usage` | Token limit tracking |
| Secrets Manager | `buffett-dev-jwt-secret` | JWT signing key |

---

## Test Categories

### 1. Unit Tests (Fully Mocked)

**Location:** `tests/unit/test_analysis_followup.py`

**Characteristics:**
- All AWS services mocked via `unittest.mock` and module injection
- No network calls, no AWS credentials required
- Fast execution (~2-5 seconds for full suite)
- Runs in CI on every commit

**What to Test:**
- Utility functions (decimal conversion, SSE formatting)
- Message persistence logic
- Token limit enforcement
- Orchestration loop control flow
- Error handling branches

### 2. Integration Tests (Real DynamoDB, Mocked Bedrock)

**Location:** `tests/integration/test_followup_agent_integration.py`

**Characteristics:**
- Real DynamoDB tables in dev environment
- Bedrock API mocked to control responses
- Requires AWS credentials
- Tests actual data flow without AI costs

**What to Test:**
- DynamoDB read/write operations
- JWT authentication flow
- Tool execution with real data
- Message persistence across tables
- Token usage recording

### 3. E2E Tests (All Real Services)

**Location:** `tests/e2e/test_followup_agent_e2e.py`

**Characteristics:**
- Hits deployed API endpoint
- Real Bedrock API calls (incurs costs)
- Full system validation
- Run sparingly (manual trigger)

**What to Test:**
- Complete user journey
- Response quality validation
- Performance under real conditions
- Streaming response handling

---

## Prerequisites

### Environment Variables

```bash
# Required for all test types
export AWS_PROFILE=default
export AWS_REGION=us-east-1

# For integration and E2E tests
export BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-jwt-secret \
    --query SecretString --output text)

# For E2E tests
export ANALYSIS_FOLLOWUP_URL="https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev"
```

### Python Dependencies

```bash
cd chat-api/backend
make venv
make dev-install

# Key test dependencies (from requirements-dev.txt):
# - pytest >= 7.4.0
# - moto >= 4.2.0
# - freezegun >= 1.2.0
# - pytest-cov >= 4.1.0
# - pytest-mock >= 3.12.0
```

### AWS Permissions

For integration/E2E tests, your AWS credentials need:
- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:Query` on dev tables
- `secretsmanager:GetSecretValue` for JWT secret
- `bedrock:InvokeModel` (E2E only)

---

## Test Scenarios Matrix

| Scenario | Unit | Integration | E2E | Bedrock Cost |
|----------|:----:|:-----------:|:---:|:------------:|
| JWT validation (valid token) | ✅ | ✅ | ✅ | No |
| JWT validation (invalid/expired) | ✅ | ✅ | ✅ | No |
| JWT validation (missing token) | ✅ | ✅ | ✅ | No |
| Token limit check (under limit) | ✅ | ✅ | ✅ | Yes |
| Token limit check (at limit) | ✅ | ✅ | ✅ | No |
| Token limit check (exceeded) | ✅ | ✅ | ✅ | No |
| Single-turn Q&A (no tools) | ✅ | ✅ | ✅ | Yes |
| Multi-turn with tool use | ✅ | ✅ | ✅ | Yes |
| Tool: getReportSection | ✅ | ✅ | ✅ | Yes |
| Tool: getReportRatings | ✅ | ✅ | ✅ | Yes |
| Tool: getMetricsHistory | ✅ | ✅ | ✅ | Yes |
| Tool: getAvailableReports | ✅ | ✅ | ✅ | Yes |
| Max turns safety limit (10) | ✅ | ❌ | ❌ | N/A |
| Streaming response (SSE) | ✅ | ❌ | ✅ | Yes |
| Message persistence | ✅ | ✅ | ✅ | Yes |
| Tool execution errors | ✅ | ✅ | ❌ | N/A |
| Bedrock API failures | ✅ | ❌ | ❌ | N/A |
| Empty/missing report data | ✅ | ✅ | ❌ | N/A |

---

## Running Tests

### Unit Tests (Fast, No AWS)

```bash
cd chat-api/backend

# Run all unit tests
pytest tests/unit/test_analysis_followup.py -v

# Run specific test class
pytest tests/unit/test_analysis_followup.py::TestOrchestrationLoop -v

# Run with coverage
pytest tests/unit/ --cov=src/handlers/analysis_followup --cov-report=html
```

### Integration Tests (Requires AWS)

```bash
cd chat-api/backend

# Set credentials
export AWS_PROFILE=default
export BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-jwt-secret \
    --query SecretString --output text)

# Run integration tests
pytest tests/integration/ -v -m integration

# Run specific integration test
pytest tests/integration/test_followup_agent_integration.py::TestToolExecution -v -s
```

### E2E Tests (Costs Money)

```bash
cd chat-api/backend

# Set credentials and endpoint
export AWS_PROFILE=default
export BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-jwt-secret \
    --query SecretString --output text)
export ANALYSIS_FOLLOWUP_URL="https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev"

# Run E2E tests (use sparingly!)
pytest tests/e2e/ -v -m e2e -s

# Run only fast E2E tests (skip slow multi-turn tests)
pytest tests/e2e/ -v -m "e2e and not slow"
```

### Skip Expensive Tests

```bash
# Skip all integration and E2E tests
pytest tests/ -v -m "not integration and not e2e"

# Skip slow tests (including expensive E2E)
pytest tests/ -v -m "not slow"
```

---

## Test Data Seeding

### Seeding Investment Reports

```python
"""Seed test report data for integration/E2E tests."""
import boto3
import uuid
from datetime import datetime

def seed_test_report(ticker: str, environment: str = 'dev') -> dict:
    """
    Seed investment-reports-v2 table with test sections.

    Args:
        ticker: Stock ticker (use unique prefix like 'E2EXXXX')
        environment: Target environment ('dev', 'test')

    Returns:
        Dict with seeded section IDs
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'investment-reports-v2-{environment}')

    sections = {
        '00_executive': {
            'ticker': ticker,
            'section_id': '00_executive',
            'company_name': f'Test Company {ticker}',
            'ratings': {
                'growth': 'Strong',
                'profitability': 'Exceptional',
                'cashflow': 'Strong',
                'debt': 'Moderate',
                'valuation': 'Fair',
                'overall_verdict': 'BUY',
                'conviction': 'High'
            },
            'generated_at': datetime.utcnow().isoformat()
        },
        '06_growth': {
            'ticker': ticker,
            'section_id': '06_growth',
            'title': 'Growth Analysis',
            'content': f'{ticker} has demonstrated consistent revenue growth of 15% YoY...',
            'word_count': 450
        },
        '11_debt': {
            'ticker': ticker,
            'section_id': '11_debt',
            'title': 'Debt Analysis',
            'content': f'{ticker} maintains a debt-to-equity ratio of 0.45...',
            'word_count': 380
        }
    }

    for section_id, data in sections.items():
        table.put_item(Item=data)

    return {'ticker': ticker, 'sections': list(sections.keys())}


def seed_test_metrics(ticker: str, quarters: int = 8, environment: str = 'dev') -> dict:
    """
    Seed metrics-history-cache table with quarterly data.

    Args:
        ticker: Stock ticker
        quarters: Number of quarters to seed
        environment: Target environment

    Returns:
        Dict with seeded fiscal dates
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'metrics-history-cache-{environment}')

    fiscal_dates = []
    base_revenue = 50000000000  # $50B

    for q in range(quarters):
        year = 2025 - (q // 4)
        quarter = 4 - (q % 4)
        fiscal_date = f'{year}-Q{quarter}'
        fiscal_dates.append(fiscal_date)

        table.put_item(Item={
            'ticker': ticker,
            'fiscal_date': fiscal_date,
            'revenue': int(base_revenue * (1 + 0.03 * q)),
            'net_income': int(base_revenue * 0.2 * (1 + 0.02 * q)),
            'free_cash_flow': int(base_revenue * 0.15 * (1 + 0.025 * q)),
            'total_debt': int(base_revenue * 0.3),
            'shareholders_equity': int(base_revenue * 0.6)
        })

    return {'ticker': ticker, 'fiscal_dates': fiscal_dates}


def seed_token_usage(user_id: str, total_tokens: int, limit: int = 50000,
                     environment: str = 'dev') -> dict:
    """
    Seed token usage for testing limit scenarios.

    Args:
        user_id: User identifier
        total_tokens: Current usage to set
        limit: Token limit to set
        environment: Target environment

    Returns:
        Dict with seeded usage data
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    table = dynamodb.Table(f'buffett-{environment}-token-usage')

    month = datetime.utcnow().strftime('%Y-%m')

    table.put_item(Item={
        'user_id': user_id,
        'month': month,
        'total_tokens': total_tokens,
        'token_limit': limit,
        'input_tokens': int(total_tokens * 0.7),
        'output_tokens': int(total_tokens * 0.3),
        'request_count': total_tokens // 500
    })

    return {
        'user_id': user_id,
        'month': month,
        'total_tokens': total_tokens,
        'remaining': limit - total_tokens
    }


def cleanup_test_data(ticker: str, user_id: str = None, environment: str = 'dev') -> None:
    """
    Remove test data after E2E tests.

    Args:
        ticker: Stock ticker to clean up
        user_id: Optional user ID to clean up
        environment: Target environment
    """
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

    # Clean reports
    reports_table = dynamodb.Table(f'investment-reports-v2-{environment}')
    response = reports_table.query(
        KeyConditionExpression='ticker = :t',
        ExpressionAttributeValues={':t': ticker}
    )
    for item in response.get('Items', []):
        reports_table.delete_item(Key={
            'ticker': item['ticker'],
            'section_id': item['section_id']
        })

    # Clean metrics
    metrics_table = dynamodb.Table(f'metrics-history-cache-{environment}')
    response = metrics_table.query(
        KeyConditionExpression='ticker = :t',
        ExpressionAttributeValues={':t': ticker}
    )
    for item in response.get('Items', []):
        metrics_table.delete_item(Key={
            'ticker': item['ticker'],
            'fiscal_date': item['fiscal_date']
        })

    # Clean token usage if user_id provided
    if user_id:
        token_table = dynamodb.Table(f'buffett-{environment}-token-usage')
        month = datetime.utcnow().strftime('%Y-%m')
        token_table.delete_item(Key={'user_id': user_id, 'month': month})
```

---

## Unit Test Patterns

### Pattern 1: Module-Level boto3 Mocking

From `tests/unit/test_analysis_followup.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(scope='module')
def mock_boto3():
    """Mock boto3 for all tests in this module."""
    mock_dynamodb = MagicMock()
    mock_table = MagicMock()
    mock_token_table = MagicMock()
    mock_dynamodb.Table.side_effect = lambda name: (
        mock_token_table if 'token' in name else mock_table
    )

    mock_bedrock_runtime = MagicMock()
    mock_secrets = MagicMock()
    mock_secrets.get_secret_value.return_value = {'SecretString': 'test-secret'}

    with patch('boto3.client') as mock_client, \
         patch('boto3.resource') as mock_resource:

        def client_side_effect(service_name, **kwargs):
            if service_name == 'bedrock-runtime':
                return mock_bedrock_runtime
            elif service_name == 'secretsmanager':
                return mock_secrets
            return MagicMock()

        mock_client.side_effect = client_side_effect
        mock_resource.return_value = mock_dynamodb

        yield {
            'bedrock_runtime': mock_bedrock_runtime,
            'dynamodb': mock_dynamodb,
            'table': mock_table,
            'token_table': mock_token_table,
            'secrets': mock_secrets
        }
```

### Pattern 2: Handler Module Injection

```python
@pytest.fixture
def handler_module(mock_boto3):
    """Import handler with mocked dependencies."""
    import sys

    # Clear cached imports
    for mod in list(sys.modules.keys()):
        if 'analysis_followup' in mod or 'token_usage_tracker' in mod:
            del sys.modules[mod]

    from handlers import analysis_followup

    # Inject mocks
    analysis_followup.messages_table = mock_boto3['table']
    analysis_followup.bedrock_runtime_client = mock_boto3['bedrock_runtime']

    # Mock token tracker
    mock_token_tracker = MagicMock()
    mock_token_tracker.check_limit.return_value = {
        'allowed': True,
        'total_tokens': 10000,
        'token_limit': 50000,
        'percent_used': 20.0,
        'remaining_tokens': 40000
    }
    analysis_followup.token_tracker = mock_token_tracker

    return analysis_followup
```

### Pattern 3: Mock Bedrock Converse Response

```python
@pytest.fixture
def mock_bedrock_response():
    """Standard Bedrock converse response (no tool use)."""
    return {
        'output': {
            'message': {
                'role': 'assistant',
                'content': [{'text': 'Based on the investment report...'}]
            }
        },
        'stopReason': 'end_turn',
        'usage': {'inputTokens': 150, 'outputTokens': 75}
    }


@pytest.fixture
def mock_bedrock_tool_use_response():
    """Bedrock response requesting tool use."""
    return {
        'output': {
            'message': {
                'role': 'assistant',
                'content': [{
                    'toolUse': {
                        'toolUseId': 'tool-call-123',
                        'name': 'getReportSection',
                        'input': {'ticker': 'AAPL', 'section_id': '06_growth'}
                    }
                }]
            }
        },
        'stopReason': 'tool_use',
        'usage': {'inputTokens': 100, 'outputTokens': 30}
    }
```

### Pattern 4: Testing Orchestration Loop

```python
class TestOrchestrationLoop:
    """Tests for multi-turn tool use orchestration."""

    def test_single_turn_no_tools(self, handler_module, mock_boto3, mock_bedrock_response):
        """Test single-turn response without tool calls."""
        mock_boto3['bedrock_runtime'].converse.return_value = mock_bedrock_response

        event = self._create_api_event({'question': 'What is the verdict?'})
        result = handler_module.lambda_handler(event, None)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['turns'] == 1
        assert 'Based on the investment report' in body['response']

    def test_multi_turn_with_tool_call(self, handler_module, mock_boto3,
                                        mock_bedrock_tool_use_response,
                                        mock_bedrock_response):
        """Test multi-turn: tool request → tool result → final response."""
        # First call returns tool_use, second call returns end_turn
        mock_boto3['bedrock_runtime'].converse.side_effect = [
            mock_bedrock_tool_use_response,
            mock_bedrock_response
        ]

        # Mock tool execution
        with patch.object(handler_module, 'execute_tool') as mock_execute:
            mock_execute.return_value = {'success': True, 'content': 'Growth data...'}

            event = self._create_api_event({'question': 'Show growth metrics'})
            result = handler_module.lambda_handler(event, None)

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['turns'] == 2
        mock_execute.assert_called_once()

    def test_max_turns_safety_limit(self, handler_module, mock_boto3,
                                     mock_bedrock_tool_use_response):
        """Test that orchestration stops at max turns (10)."""
        # Always return tool_use to force max turns
        mock_boto3['bedrock_runtime'].converse.return_value = mock_bedrock_tool_use_response

        with patch.object(handler_module, 'execute_tool') as mock_execute:
            mock_execute.return_value = {'success': True, 'content': 'Data...'}

            event = self._create_api_event({'question': 'Complex query'})
            result = handler_module.lambda_handler(event, None)

        # Should stop at max turns with partial response
        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['turns'] == 10
```

### Pattern 5: Generator Testing (Streaming)

```python
def _consume_generator(self, gen):
    """Consume streaming generator, return final result."""
    if isinstance(gen, dict):
        return gen

    chunks = []
    try:
        while True:
            chunk = next(gen)
            chunks.append(chunk)
    except StopIteration as e:
        return e.value if e.value else chunks[-1] if chunks else None


def test_streaming_response(self, handler_module, mock_boto3):
    """Test SSE streaming response format."""
    # Configure for streaming
    mock_stream = MagicMock()
    mock_stream.get.return_value = iter([
        {'contentBlockDelta': {'delta': {'text': 'Hello '}}},
        {'contentBlockDelta': {'delta': {'text': 'world'}}},
        {'messageStop': {'stopReason': 'end_turn'}},
        {'metadata': {'usage': {'inputTokens': 50, 'outputTokens': 25}}}
    ])
    mock_boto3['bedrock_runtime'].converse_stream.return_value = {'stream': mock_stream}

    event = self._create_function_url_event({'question': 'Hello'})
    result = handler_module.lambda_handler(event, None)
    final = self._consume_generator(result)

    assert 'complete' in str(final)
```

---

## Integration Test Patterns

### Pattern 1: Real DynamoDB, Mocked Bedrock

```python
"""
Integration tests with real DynamoDB tables, mocked Bedrock.

Run with:
    AWS_PROFILE=default pytest tests/integration/test_followup_agent_integration.py -v -m integration
"""
import pytest
import os
import boto3
import jwt
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

pytestmark = pytest.mark.integration


@pytest.fixture(scope='module')
def dynamodb():
    """Real DynamoDB resource."""
    return boto3.resource('dynamodb', region_name='us-east-1')


@pytest.fixture(scope='module')
def test_data(dynamodb):
    """Seed test data, cleanup after module."""
    ticker = f'INT{uuid.uuid4().hex[:4]}'.upper()
    user_id = f'integration-test-{uuid.uuid4().hex[:8]}'

    # Seed data
    seed_test_report(ticker)
    seed_test_metrics(ticker)
    seed_token_usage(user_id, total_tokens=1000, limit=50000)

    yield {
        'ticker': ticker,
        'user_id': user_id
    }

    # Cleanup
    cleanup_test_data(ticker, user_id)


@pytest.fixture
def test_jwt(test_data):
    """Generate valid JWT for test user."""
    secret = os.environ.get('BUFFETT_JWT_SECRET', 'test-secret')
    payload = {
        'user_id': test_data['user_id'],
        'email': 'integration-test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


class TestToolExecutionIntegration:
    """Integration tests for tool execution with real DynamoDB."""

    def test_get_report_section_real_data(self, test_data, test_jwt):
        """Test getReportSection with real DynamoDB data."""
        with patch('boto3.client') as mock_client:
            # Only mock Bedrock, let DynamoDB be real
            mock_bedrock = MagicMock()
            mock_bedrock.converse.return_value = {
                'output': {
                    'message': {
                        'content': [{
                            'toolUse': {
                                'toolUseId': 'tool-1',
                                'name': 'getReportSection',
                                'input': {
                                    'ticker': test_data['ticker'],
                                    'section_id': '06_growth'
                                }
                            }
                        }]
                    }
                },
                'stopReason': 'tool_use',
                'usage': {'inputTokens': 100, 'outputTokens': 30}
            }

            def client_factory(service, **kwargs):
                if service == 'bedrock-runtime':
                    return mock_bedrock
                return boto3.client(service, **kwargs)

            mock_client.side_effect = client_factory

            # Import and execute
            from handlers import analysis_followup
            from utils.tool_executor import ToolExecutor

            executor = ToolExecutor()
            result = executor.execute('getReportSection', {
                'ticker': test_data['ticker'],
                'section_id': '06_growth'
            })

            assert result['success'] is True
            assert result['ticker'] == test_data['ticker']
            assert 'content' in result


    def test_message_persistence_integration(self, test_data, test_jwt, dynamodb):
        """Test that messages are persisted to real DynamoDB."""
        session_id = f'integration-session-{uuid.uuid4().hex[:8]}'

        # ... invoke handler with mocked Bedrock ...

        # Verify message in DynamoDB
        messages_table = dynamodb.Table('buffett-dev-chat-messages')
        response = messages_table.query(
            KeyConditionExpression='conversation_id = :sid',
            ExpressionAttributeValues={':sid': session_id}
        )

        assert len(response['Items']) >= 2  # User + assistant messages
        user_msg = next(m for m in response['Items'] if m['message_type'] == 'user')
        assert user_msg['user_id'] == test_data['user_id']
```

---

## E2E Test Patterns

### Pattern 1: Full API Request

```python
"""
E2E tests hitting the deployed dev API.

IMPORTANT: These tests incur Bedrock API costs!

Run with:
    AWS_PROFILE=default BUFFETT_JWT_SECRET='...' \
        pytest tests/e2e/test_followup_agent_e2e.py -v -m e2e
"""
import pytest
import requests
import os
import jwt
import uuid
from datetime import datetime, timedelta

pytestmark = [pytest.mark.e2e, pytest.mark.slow]

API_URL = os.environ.get(
    'ANALYSIS_FOLLOWUP_URL',
    'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev'
)


@pytest.fixture(scope='module')
def e2e_test_data():
    """Seed E2E test data with unique ticker."""
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
    """Generate JWT for E2E test user."""
    secret = os.environ['BUFFETT_JWT_SECRET']
    payload = {
        'user_id': e2e_test_data['user_id'],
        'email': 'e2e-test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=1)
    }
    return jwt.encode(payload, secret, algorithm='HS256')


class TestFollowupAgentE2E:
    """Full E2E tests against deployed API."""

    def test_health_check(self):
        """E2E: Health endpoint responds correctly."""
        response = requests.get(f"{API_URL}/health", timeout=10)

        assert response.status_code == 200
        body = response.json()
        assert body['status'] == 'healthy'
        assert 'haiku' in body['model_id'].lower()

    def test_happy_path_simple_question(self, e2e_test_data, e2e_jwt):
        """E2E: Simple question gets answered correctly."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'question': 'What is the overall investment verdict?',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker'],
                'agent_type': 'debt'
            },
            timeout=60
        )

        assert response.status_code == 200
        body = response.json()

        assert body['success'] is True
        assert len(body['response']) > 50  # Non-trivial response
        assert body['turns'] >= 1
        assert body['token_usage']['input_tokens'] > 0
        assert body['token_usage']['output_tokens'] > 0

    def test_tool_invocation_growth_question(self, e2e_test_data, e2e_jwt):
        """E2E: Growth question triggers getReportSection tool."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'question': 'Tell me about the growth analysis section',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker']
            },
            timeout=60
        )

        assert response.status_code == 200
        body = response.json()

        # Should have used tools (turns > 1) or mentioned growth
        assert body['success'] is True
        assert 'growth' in body['response'].lower()

    def test_token_limit_exceeded(self, e2e_test_data, e2e_jwt):
        """E2E: Request rejected when token limit exceeded."""
        # Seed user to be over limit
        seed_token_usage(e2e_test_data['user_id'], total_tokens=60000, limit=50000)

        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {e2e_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'question': 'Should be rejected',
                'session_id': e2e_test_data['session_id'],
                'ticker': e2e_test_data['ticker']
            },
            timeout=30
        )

        assert response.status_code == 429
        body = response.json()
        assert 'token_limit' in body.get('error', '').lower() or 'limit' in body.get('message', '').lower()

    def test_invalid_jwt_rejected(self, e2e_test_data):
        """E2E: Invalid JWT returns 401."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={
                'Authorization': 'Bearer invalid.jwt.token',
                'Content-Type': 'application/json'
            },
            json={
                'question': 'Should be rejected',
                'session_id': e2e_test_data['session_id']
            },
            timeout=30
        )

        assert response.status_code == 401

    def test_missing_auth_rejected(self, e2e_test_data):
        """E2E: Missing Authorization header returns 401."""
        response = requests.post(
            f"{API_URL}/research/followup",
            headers={'Content-Type': 'application/json'},
            json={
                'question': 'Should be rejected',
                'session_id': e2e_test_data['session_id']
            },
            timeout=30
        )

        assert response.status_code == 401
```

---

## Best Practices

### 1. Data Isolation

```python
# Always use unique prefixes for test data
TEST_TICKER_PREFIX = 'E2E'  # or 'INT' for integration
TEST_USER_PREFIX = 'e2e-test-'

# Generate unique identifiers
ticker = f'{TEST_TICKER_PREFIX}{uuid.uuid4().hex[:4]}'.upper()
user_id = f'{TEST_USER_PREFIX}{uuid.uuid4().hex[:8]}'
session_id = f'test-session-{uuid.uuid4().hex}'
```

### 2. Cleanup with Yield Fixtures

```python
@pytest.fixture(scope='module')
def test_data():
    """Seed data, yield to tests, then cleanup."""
    ticker = create_test_ticker()
    seed_test_report(ticker)

    yield {'ticker': ticker}

    # Always runs, even if tests fail
    cleanup_test_data(ticker)
```

### 3. Cost Control

```python
# Mark expensive tests
@pytest.mark.slow
@pytest.mark.e2e
def test_expensive_bedrock_call():
    ...

# Skip in CI by default
# pytest.ini or pyproject.toml:
# [pytest]
# markers =
#     slow: marks tests as slow (deselect with '-m "not slow"')
#     e2e: marks tests as end-to-end (deselect with '-m "not e2e"')
```

### 4. Test Independence

```python
# BAD: Shared state between tests
class TestBad:
    shared_data = {}  # Don't do this!

# GOOD: Each test creates its own data
class TestGood:
    def test_one(self, fresh_test_data):
        # fresh_test_data is unique to this test
        ...
```

### 5. Assertions

```python
# Be specific about what you're testing
assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

# Check structure, not exact content (AI responses vary)
assert 'response' in body
assert len(body['response']) > 50
assert body['turns'] >= 1

# Use approximate checks for variable values
assert body['token_usage']['input_tokens'] > 0
assert body['token_usage']['percent_used'] < 100
```

---

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Test Follow-Up Agent

on:
  push:
    branches: [dev, main]
  pull_request:
    branches: [dev, main]
  workflow_dispatch:
    inputs:
      run_e2e:
        description: 'Run E2E tests (costs money)'
        required: false
        default: 'false'

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd chat-api/backend
          pip install -r requirements-dev.txt

      - name: Run unit tests
        run: |
          cd chat-api/backend
          pytest tests/unit/test_analysis_followup.py -v --tb=short

  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd chat-api/backend
          pip install -r requirements-dev.txt

      - name: Run integration tests
        env:
          BUFFETT_JWT_SECRET: ${{ secrets.BUFFETT_JWT_SECRET }}
        run: |
          cd chat-api/backend
          pytest tests/integration/ -v --tb=short -m integration

  e2e-tests:
    runs-on: ubuntu-latest
    needs: integration-tests
    if: github.event.inputs.run_e2e == 'true'
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd chat-api/backend
          pip install -r requirements-dev.txt

      - name: Run E2E tests
        env:
          BUFFETT_JWT_SECRET: ${{ secrets.BUFFETT_JWT_SECRET }}
          ANALYSIS_FOLLOWUP_URL: ${{ secrets.ANALYSIS_FOLLOWUP_URL }}
        run: |
          cd chat-api/backend
          pytest tests/e2e/ -v --tb=short -m e2e
```

---

## Troubleshooting

### Common Issues

#### 1. JWT Validation Failures

```
Error: 401 Unauthorized - Invalid token
```

**Causes:**
- JWT secret mismatch between test and Lambda
- Token expired
- Wrong algorithm (must be HS256)

**Fix:**
```bash
# Verify secret matches
export BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-jwt-secret \
    --query SecretString --output text)

# Verify token
python -c "import jwt; print(jwt.decode('$TOKEN', '$BUFFETT_JWT_SECRET', algorithms=['HS256']))"
```

#### 2. DynamoDB Access Denied

```
Error: AccessDeniedException: User is not authorized
```

**Causes:**
- Wrong AWS profile
- Missing IAM permissions
- Wrong region

**Fix:**
```bash
# Verify credentials
aws sts get-caller-identity

# Test DynamoDB access
aws dynamodb describe-table --table-name investment-reports-v2-dev
```

#### 3. Bedrock Throttling

```
Error: ThrottlingException: Rate exceeded
```

**Causes:**
- Too many concurrent requests
- Account limits exceeded

**Fix:**
```python
# Add retry with backoff
import time

@pytest.fixture
def bedrock_with_retry():
    def make_request(func, *args, max_retries=3, **kwargs):
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except ClientError as e:
                if 'ThrottlingException' in str(e) and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
    return make_request
```

#### 4. Test Data Not Found

```
Error: Report section not found for ticker E2EXXXX
```

**Causes:**
- Seeding failed
- Cleanup ran prematurely
- Wrong table name

**Fix:**
```bash
# Verify data exists
aws dynamodb get-item \
    --table-name investment-reports-v2-dev \
    --key '{"ticker": {"S": "E2EXXXX"}, "section_id": {"S": "06_growth"}}'
```

#### 5. Token Limit Issues in Tests

```
Error: Monthly token limit reached
```

**Causes:**
- Previous test didn't reset token usage
- Wrong user_id in JWT

**Fix:**
```python
# Always reset token usage at start of test
@pytest.fixture(autouse=True)
def reset_token_usage(test_data):
    seed_token_usage(test_data['user_id'], total_tokens=0, limit=50000)
    yield
```

---

## RALF Workflow Phases

For implementing new tests, use the RALF workflow in separate Claude Code sessions:

### Phase 1: Create Test File Structure
- Create `tests/integration/test_followup_agent_integration.py`
- Create `tests/e2e/test_followup_agent_e2e.py`
- Create `tests/fixtures/data_seeding.py`
- Verify: Files exist with correct imports

### Phase 2: Implement Data Seeding Utilities
- Implement `seed_test_report()`, `seed_test_metrics()`, `seed_token_usage()`
- Implement `cleanup_test_data()`
- Verify: Can seed and query test data manually

### Phase 3: Implement Integration Tests
- Implement `TestToolExecutionIntegration`
- Implement `TestMessagePersistenceIntegration`
- Verify: `pytest tests/integration/ -v -m integration` passes

### Phase 4: Implement E2E Tests
- Implement `TestFollowupAgentE2E`
- Add health check, happy path, error cases
- Verify: `pytest tests/e2e/ -v -m e2e` passes

### Phase 5: CI/CD Integration
- Update `.github/workflows/` with test jobs
- Add secrets to GitHub repository
- Verify: CI pipeline runs tests correctly

---

## Related Documentation

- [FOLLOWUP_AGENT.md](./FOLLOWUP_AGENT.md) - Architecture reference
- [test_analysis_followup.py](../../tests/unit/test_analysis_followup.py) - Unit test examples
- [conftest.py](../../tests/conftest.py) - Shared fixtures
