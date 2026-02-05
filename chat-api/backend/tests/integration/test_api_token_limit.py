"""
API Integration tests for token limit enforcement.

These tests hit the REAL deployed API Gateway endpoint to verify
that token limits are enforced end-to-end.

Run with:
    cd chat-api/backend
    AWS_PROFILE=dev BUFFETT_JWT_SECRET='your-secret' \
        pytest tests/integration/test_api_token_limit.py -v -s -m integration

Requirements:
    - AWS credentials with access to DynamoDB
    - JWT secret from AWS Secrets Manager (buffett-dev-jwt-secret)
    - Network access to the deployed API

IMPORTANT: These tests use real AWS resources and hit the deployed API.
The 429 test creates a user already over the limit, so NO Bedrock costs
are incurred (limit check happens before agent invocation).
"""

import os
import sys
import pytest
import uuid
import time
import json
import logging
import requests
import jwt
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Configure logging for test visibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# TEST CONSTANTS
# =============================================================================

TEST_USER_PREFIX = "integration-test-api-"
# Use the REAL dev table since we're testing the deployed Lambda
# New naming convention: token-usage-{env}-{project}
DEV_TOKEN_TABLE = "token-usage-dev-buffett"
TEST_TOKEN_LIMIT = 10000  # Low limit to prevent accidental Bedrock costs

# API endpoints - use Lambda Function URL for streaming endpoint
# The analysis_followup Lambda uses Function URL with RESPONSE_STREAM mode
DEFAULT_API_URL = os.environ.get(
    'ANALYSIS_FOLLOWUP_URL',
    'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev'
)

# JWT secret - must be set for tests to run
JWT_SECRET = os.environ.get('BUFFETT_JWT_SECRET')


# =============================================================================
# CREDENTIAL CHECKS
# =============================================================================

def check_aws_credentials() -> bool:
    """Check if AWS credentials are available (respects AWS_PROFILE env var)."""
    try:
        import boto3
        session = boto3.Session()
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        logger.info(f"AWS credentials available: {identity.get('Arn', 'unknown')}")
        return True
    except Exception as e:
        logger.warning(f"AWS credentials not available: {e}")
        return False


# Lazy credential check
AWS_CREDENTIALS_AVAILABLE = None


def get_aws_credentials_status() -> bool:
    """Lazy check for AWS credentials - called at test collection time."""
    global AWS_CREDENTIALS_AVAILABLE
    if AWS_CREDENTIALS_AVAILABLE is None:
        AWS_CREDENTIALS_AVAILABLE = check_aws_credentials()
    return AWS_CREDENTIALS_AVAILABLE


def check_jwt_secret() -> bool:
    """Check if JWT secret is available."""
    if JWT_SECRET and len(JWT_SECRET) >= 32:
        logger.info("JWT secret available")
        return True
    logger.warning("JWT secret not available or too short (need 32+ chars)")
    return False


# Skip markers
pytestmark = pytest.mark.integration

requires_all_credentials = pytest.mark.skipif(
    not JWT_SECRET,
    reason="BUFFETT_JWT_SECRET environment variable not set"
)


# =============================================================================
# JWT HELPER
# =============================================================================

def create_test_jwt(
    user_id: str,
    email: str = "test@example.com",
    expires_in_minutes: int = 30
) -> str:
    """
    Create a valid JWT token for API testing.

    Args:
        user_id: The user ID to encode in the token
        email: Email address for the user
        expires_in_minutes: Token validity duration

    Returns:
        Encoded JWT token string
    """
    if not JWT_SECRET:
        raise ValueError("BUFFETT_JWT_SECRET not set")

    current_unix_time = int(time.time())

    payload = {
        'user_id': user_id,
        'email': email,
        'name': 'Test User',
        'subscription_tier': 'free',
        'iat': current_unix_time - 3600,  # Issued 1 hour ago (avoid clock skew)
        'exp': current_unix_time + (expires_in_minutes * 60),
        'iss': 'buffett-chat-api'
    }

    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


# =============================================================================
# DYNAMODB HELPERS
# =============================================================================

def get_dynamodb_table():
    """Get DynamoDB table resource for the dev token usage table."""
    import boto3
    dynamodb = boto3.resource('dynamodb')
    return dynamodb.Table(DEV_TOKEN_TABLE)


def create_user_over_limit(user_id: str, token_limit: int = TEST_TOKEN_LIMIT) -> Dict[str, Any]:
    """
    Create a user record in DynamoDB with tokens already over the limit.

    This ensures the API will return 429 without invoking Bedrock (no cost).

    Uses the new billing_period schema (YYYY-MM-DD format) for anniversary-based billing.

    Args:
        user_id: The user ID to create
        token_limit: The token limit to set (default 10,000)

    Returns:
        The created item data
    """
    table = get_dynamodb_table()

    # Calculate current billing period (anniversary-based)
    today = datetime.now(timezone.utc)
    billing_day = today.day
    billing_period = today.strftime('%Y-%m-%d')

    # Calculate reset date (next billing period)
    if today.month == 12:
        reset_date = today.replace(year=today.year + 1, month=1, day=billing_day)
    else:
        # Handle months with fewer days
        next_month = today.month + 1
        try:
            reset_date = today.replace(month=next_month, day=billing_day)
        except ValueError:
            # Day doesn't exist in next month, use last valid day
            reset_date = today.replace(month=next_month, day=28)

    item = {
        'user_id': user_id,
        'billing_period': billing_period,  # New schema uses billing_period
        'billing_day': billing_day,
        'total_tokens': token_limit + 1,  # Over limit
        'token_limit': token_limit,
        'request_count': 100,
        'created_at': today.isoformat(),
        'updated_at': today.isoformat(),
        'limit_reached_at': today.isoformat(),
        'reset_date': reset_date.isoformat(),
        'billing_period_start': f"{billing_period}T00:00:00Z",
        'billing_period_end': reset_date.isoformat(),
        'subscription_tier': 'free'
    }

    table.put_item(Item=item)
    logger.info(f"Created over-limit user: {user_id} with {token_limit + 1}/{token_limit} tokens")

    return item


def create_user_under_limit(user_id: str, token_limit: int = TEST_TOKEN_LIMIT) -> Dict[str, Any]:
    """
    Create a user record in DynamoDB with tokens under the limit.

    WARNING: If this test proceeds past the limit check, Bedrock WILL be invoked.

    Uses the new billing_period schema (YYYY-MM-DD format) for anniversary-based billing.

    Args:
        user_id: The user ID to create
        token_limit: The token limit to set

    Returns:
        The created item data
    """
    table = get_dynamodb_table()

    today = datetime.now(timezone.utc)
    billing_day = today.day
    billing_period = today.strftime('%Y-%m-%d')

    if today.month == 12:
        reset_date = today.replace(year=today.year + 1, month=1, day=billing_day)
    else:
        try:
            reset_date = today.replace(month=today.month + 1, day=billing_day)
        except ValueError:
            reset_date = today.replace(month=today.month + 1, day=28)

    item = {
        'user_id': user_id,
        'billing_period': billing_period,  # New schema uses billing_period
        'billing_day': billing_day,
        'total_tokens': 0,  # Under limit
        'token_limit': token_limit,
        'request_count': 0,
        'created_at': today.isoformat(),
        'updated_at': today.isoformat(),
        'reset_date': reset_date.isoformat(),
        'billing_period_start': f"{billing_period}T00:00:00Z",
        'billing_period_end': reset_date.isoformat(),
        'subscription_tier': 'free'
    }

    table.put_item(Item=item)
    logger.info(f"Created under-limit user: {user_id} with 0/{token_limit} tokens")

    return item


def cleanup_user_records(user_id: str) -> None:
    """
    Delete all records for a test user from DynamoDB.

    Uses the new billing_period schema.

    Args:
        user_id: The user ID to clean up
    """
    table = get_dynamodb_table()

    try:
        # Query all billing periods for this user
        response = table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )

        items = response.get('Items', [])
        logger.info(f"Found {len(items)} records to delete for user {user_id}")

        # Delete each record using billing_period as the sort key
        for item in items:
            table.delete_item(
                Key={
                    'user_id': item['user_id'],
                    'billing_period': item['billing_period']
                }
            )

        logger.info(f"Cleaned up user {user_id}")

    except Exception as e:
        logger.error(f"Error cleaning up user {user_id}: {e}")


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module", autouse=True)
def check_credentials():
    """Skip all tests in module if credentials not available."""
    if not get_aws_credentials_status():
        pytest.skip("AWS credentials not available - skipping API integration tests")
    if not check_jwt_secret():
        pytest.skip("JWT secret not available - skipping API integration tests")


@pytest.fixture
def test_user_id():
    """Generate unique test user ID."""
    unique_id = f"{TEST_USER_PREFIX}{uuid.uuid4().hex[:8]}"
    logger.info(f"Generated test user ID: {unique_id}")
    return unique_id


@pytest.fixture
def test_jwt(test_user_id):
    """Generate valid JWT for test user."""
    token = create_test_jwt(test_user_id)
    logger.info(f"Generated JWT for user: {test_user_id}")
    return token


@pytest.fixture
def over_limit_user(test_user_id):
    """Create a user with tokens over the limit."""
    create_user_over_limit(test_user_id)
    yield test_user_id
    cleanup_user_records(test_user_id)


@pytest.fixture
def under_limit_user(test_user_id):
    """Create a user with tokens under the limit."""
    create_user_under_limit(test_user_id)
    yield test_user_id
    cleanup_user_records(test_user_id)


# =============================================================================
# TEST CLASS
# =============================================================================

@pytest.mark.integration
@requires_all_credentials
class TestApiTokenLimitEnforcement:
    """
    Integration tests that hit the real deployed API.

    These tests verify that the token limit enforcement works end-to-end,
    from API Gateway through Lambda to DynamoDB and back.
    """

    def test_api_returns_429_when_limit_exceeded(self, over_limit_user, test_jwt):
        """
        Real API should return 429 when user's token limit is exceeded.

        This test:
        1. Creates a user with tokens already over the limit in DynamoDB
        2. Makes a POST request to /research/followup with valid JWT
        3. Verifies the API returns HTTP 429 with correct headers and body

        No Bedrock costs are incurred because the limit check happens first.
        """
        logger.info("Testing: API returns 429 when token limit exceeded")

        # Make request to the deployed API
        response = requests.post(
            f"{DEFAULT_API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {test_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'report_id': 'AAPL_2024',
                'question': 'What is the debt situation?',
                'session_id': f'test-session-{uuid.uuid4().hex[:8]}'
            },
            timeout=30
        )

        # Log response for debugging
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")

        # Assert 429 status code
        assert response.status_code == 429, (
            f"Expected 429, got {response.status_code}. "
            f"Response: {response.text[:500]}"
        )

        # Assert rate limit headers are present
        assert 'X-RateLimit-Limit' in response.headers, (
            "Missing X-RateLimit-Limit header"
        )
        assert response.headers.get('X-RateLimit-Remaining') == '0', (
            f"Expected X-RateLimit-Remaining=0, got {response.headers.get('X-RateLimit-Remaining')}"
        )
        assert 'X-RateLimit-Reset' in response.headers, (
            "Missing X-RateLimit-Reset header"
        )

        # Parse and validate response body
        # Note: API Gateway wraps the Lambda response, so we may need to unwrap
        try:
            outer_body = response.json()
        except json.JSONDecodeError:
            pytest.fail(f"Response is not valid JSON: {response.text[:500]}")

        # Handle wrapped response format: {statusCode, headers, body}
        if 'body' in outer_body and isinstance(outer_body.get('body'), str):
            try:
                body = json.loads(outer_body['body'])
            except json.JSONDecodeError:
                pytest.fail(f"Inner body is not valid JSON: {outer_body['body'][:500]}")
        else:
            body = outer_body

        # Assert body structure
        assert body.get('success') is False, "Expected success=false"
        assert body.get('error') == 'token_limit_exceeded', (
            f"Expected error='token_limit_exceeded', got '{body.get('error')}'"
        )
        assert 'message' in body, "Missing 'message' field in response"
        assert 'usage' in body, "Missing 'usage' field in response"

        # Validate usage object
        usage = body.get('usage', {})
        assert 'total_tokens' in usage, "Missing 'total_tokens' in usage"
        assert 'token_limit' in usage, "Missing 'token_limit' in usage"
        assert 'percent_used' in usage, "Missing 'percent_used' in usage"
        assert 'reset_date' in usage, "Missing 'reset_date' in usage"

        # Verify the user was actually over limit
        assert usage['total_tokens'] >= usage['token_limit'], (
            f"User should be over limit: {usage['total_tokens']}/{usage['token_limit']}"
        )

        logger.info(f"429 response validated successfully")
        logger.info(f"  Token usage: {usage['total_tokens']}/{usage['token_limit']}")
        logger.info(f"  Reset date: {usage['reset_date']}")
        print(f"\n429 test passed: User at {usage['total_tokens']}/{usage['token_limit']} tokens")

    @pytest.mark.slow
    def test_api_allows_request_when_under_limit(self, under_limit_user, test_jwt):
        """
        Real API should NOT return 429 when user is under the limit.

        WARNING: This test may incur Bedrock costs if it proceeds past the
        limit check. It's marked as @pytest.mark.slow so it can be skipped.

        The test verifies that:
        1. A user under the limit does NOT get a 429 response
        2. The request proceeds to the next stage (may fail for other reasons)
        """
        logger.info("Testing: API allows request when under token limit")

        # Make request to the deployed API
        response = requests.post(
            f"{DEFAULT_API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {test_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'report_id': 'AAPL_2024',
                'question': 'What is the debt situation?',
                'session_id': f'test-session-{uuid.uuid4().hex[:8]}'
            },
            timeout=60  # Longer timeout if Bedrock is invoked
        )

        logger.info(f"Response status: {response.status_code}")

        # The key assertion: should NOT be 429
        # It may be 200 (success), 404 (report not found), 400 (bad request), etc.
        assert response.status_code != 429, (
            f"User under limit should not get 429. "
            f"Got: {response.status_code} - {response.text[:500]}"
        )

        logger.info(f"Under-limit test passed: Got {response.status_code} (not 429)")
        print(f"\nUnder-limit test passed: Response was {response.status_code} (not 429)")


# =============================================================================
# ADDITIONAL EDGE CASE TESTS
# =============================================================================

@pytest.mark.integration
@requires_all_credentials
class TestApiTokenLimitEdgeCases:
    """Edge case tests for token limit enforcement."""

    def test_api_returns_401_without_auth(self):
        """API should return 401 when no Authorization header is provided."""
        logger.info("Testing: API returns 401 without auth")

        response = requests.post(
            f"{DEFAULT_API_URL}/research/followup",
            headers={
                'Content-Type': 'application/json'
            },
            json={
                'report_id': 'AAPL_2024',
                'question': 'Test question'
            },
            timeout=30
        )

        # Should be 401 Unauthorized
        assert response.status_code == 401, (
            f"Expected 401, got {response.status_code}"
        )
        logger.info("401 test passed: Unauthenticated request rejected")
        print("\n401 test passed: Unauthenticated request correctly rejected")

    def test_rate_limit_headers_format(self, over_limit_user, test_jwt):
        """Verify rate limit headers have correct format."""
        logger.info("Testing: Rate limit header format")

        response = requests.post(
            f"{DEFAULT_API_URL}/research/followup",
            headers={
                'Authorization': f'Bearer {test_jwt}',
                'Content-Type': 'application/json'
            },
            json={
                'report_id': 'AAPL_2024',
                'question': 'Test',
                'session_id': f'test-{uuid.uuid4().hex[:8]}'
            },
            timeout=30
        )

        assert response.status_code == 429

        # X-RateLimit-Limit should be a number
        limit_header = response.headers.get('X-RateLimit-Limit')
        assert limit_header is not None
        assert limit_header.isdigit(), f"X-RateLimit-Limit should be numeric: {limit_header}"

        # X-RateLimit-Reset should be ISO format date
        reset_header = response.headers.get('X-RateLimit-Reset')
        assert reset_header is not None
        # Basic ISO format check (contains date-like pattern)
        assert '-' in reset_header and 'T' in reset_header, (
            f"X-RateLimit-Reset should be ISO format: {reset_header}"
        )

        logger.info(f"Header format validated: Limit={limit_header}, Reset={reset_header}")
        print(f"\nHeader format test passed")


# =============================================================================
# FIXTURE FOR EDGE CASE TESTS
# =============================================================================

# Note: Edge case tests reuse the fixtures defined above (over_limit_user, test_jwt)
# No duplicate fixture definitions needed
