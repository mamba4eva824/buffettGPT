"""
Integration tests for TokenUsageTracker against dev DynamoDB.

Run with: pytest tests/integration/test_token_tracker_integration.py -v -s

IMPORTANT: These tests use real AWS resources. Ensure AWS credentials
are configured for the dev environment.

Usage:
    cd chat-api/backend
    AWS_PROFILE=dev pytest tests/integration/test_token_tracker_integration.py -v -s -m integration

    # Run specific test class:
    AWS_PROFILE=dev pytest tests/integration/test_token_tracker_integration.py::TestIntegrationBasicOperations -v -s

    # Run specific test:
    AWS_PROFILE=dev pytest tests/integration/test_token_tracker_integration.py::TestIntegrationBasicOperations::test_new_user_gets_billing_day_set -v -s
"""

import os
import sys
import pytest
import uuid
import time
import logging
import concurrent.futures
from datetime import datetime, timezone
from typing import List, Dict, Any
from decimal import Decimal

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Configure logging for test visibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Test constants
TEST_USER_PREFIX = "integration-test-"
DEV_TABLE_NAME = "buffett-dev-token-usage"
TEST_TABLE_NAME = "buffett-test-token-usage-integration"
TEST_TOKEN_LIMIT = 10000  # Small limit for testing
USE_TEST_TABLE = True  # Create dedicated test table with correct schema


def check_aws_credentials():
    """Check if AWS credentials are available (respects AWS_PROFILE env var)."""
    try:
        import boto3
        # boto3 automatically uses AWS_PROFILE if set
        session = boto3.Session()
        sts = session.client('sts')
        identity = sts.get_caller_identity()
        logger.info(f"AWS credentials available: {identity.get('Arn', 'unknown')}")
        return True
    except Exception as e:
        logger.warning(f"AWS credentials not available: {e}")
        return False


# Check credentials at module load time (after AWS_PROFILE is set)
AWS_CREDENTIALS_AVAILABLE = None


def get_aws_credentials_status():
    """Lazy check for AWS credentials - called at test collection time."""
    global AWS_CREDENTIALS_AVAILABLE
    if AWS_CREDENTIALS_AVAILABLE is None:
        AWS_CREDENTIALS_AVAILABLE = check_aws_credentials()
    return AWS_CREDENTIALS_AVAILABLE


# Skip all tests if AWS credentials not available
pytestmark = pytest.mark.integration


# =============================================================================
# TABLE SETUP
# =============================================================================

def create_test_table_if_needed():
    """
    Create test table with correct schema for anniversary-based billing.

    Schema:
    - user_id (PK): User identifier
    - billing_period (SK): Billing period in YYYY-MM-DD format
    """
    import boto3
    from botocore.exceptions import ClientError

    dynamodb = boto3.resource('dynamodb')
    client = boto3.client('dynamodb')

    try:
        # Check if table exists
        client.describe_table(TableName=TEST_TABLE_NAME)
        logger.info(f"Test table {TEST_TABLE_NAME} already exists")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceNotFoundException':
            raise

    # Create table with correct schema
    logger.info(f"Creating test table {TEST_TABLE_NAME}...")

    table = dynamodb.create_table(
        TableName=TEST_TABLE_NAME,
        KeySchema=[
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            {'AttributeName': 'billing_period', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'billing_period', 'AttributeType': 'S'}
        ],
        BillingMode='PAY_PER_REQUEST'
    )

    # Wait for table to be active
    table.wait_until_exists()
    logger.info(f"Test table {TEST_TABLE_NAME} created and active")
    return True


def delete_test_table():
    """Delete the test table (optional cleanup)."""
    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client('dynamodb')

    try:
        client.delete_table(TableName=TEST_TABLE_NAME)
        logger.info(f"Test table {TEST_TABLE_NAME} deleted")
    except ClientError as e:
        if e.response['Error']['Code'] != 'ResourceNotFoundException':
            raise


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module", autouse=True)
def check_credentials():
    """Skip all tests in module if AWS credentials not available."""
    if not get_aws_credentials_status():
        pytest.skip("AWS credentials not available - skipping integration tests")


@pytest.fixture(scope="module")
def ensure_test_table():
    """Create test table if using dedicated test table."""
    if USE_TEST_TABLE:
        create_test_table_if_needed()
    yield
    # Optionally delete table after tests (commented out to allow inspection)
    # if USE_TEST_TABLE:
    #     delete_test_table()


@pytest.fixture
def test_user_id():
    """Generate unique test user ID."""
    unique_id = f"{TEST_USER_PREFIX}{uuid.uuid4().hex[:8]}"
    logger.info(f"Generated test user ID: {unique_id}")
    return unique_id


@pytest.fixture
def tracker(ensure_test_table):
    """Create tracker pointing to test table."""
    # Import here to avoid issues if module not found
    from utils.token_usage_tracker import TokenUsageTracker

    # Override default limit for testing
    os.environ['DEFAULT_TOKEN_LIMIT'] = str(TEST_TOKEN_LIMIT)

    table_name = TEST_TABLE_NAME if USE_TEST_TABLE else DEV_TABLE_NAME
    tracker = TokenUsageTracker(table_name=table_name)
    logger.info(f"Created tracker for table: {table_name}")
    return tracker


@pytest.fixture
def cleanup_users(tracker):
    """
    Track and clean up test users after tests.

    This fixture collects user IDs during the test and cleans them up afterward.
    """
    users_to_cleanup: List[str] = []

    yield users_to_cleanup

    # Cleanup phase
    logger.info(f"Cleaning up {len(users_to_cleanup)} test users...")
    for user_id in users_to_cleanup:
        try:
            _cleanup_user_records(tracker, user_id)
        except Exception as e:
            logger.warning(f"Failed to cleanup user {user_id}: {e}")


def _cleanup_user_records(tracker, user_id: str):
    """Delete all records for a test user."""
    if not tracker.table:
        return

    try:
        # Query all records for this user
        response = tracker.table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )

        items = response.get('Items', [])
        logger.info(f"Found {len(items)} records to delete for user {user_id}")

        # Delete each record
        for item in items:
            tracker.table.delete_item(
                Key={
                    'user_id': item['user_id'],
                    'billing_period': item['billing_period']
                }
            )

        logger.info(f"Cleaned up user {user_id}")

    except Exception as e:
        logger.error(f"Error cleaning up user {user_id}: {e}")


@pytest.fixture(autouse=True)
def cleanup(tracker, test_user_id, cleanup_users):
    """
    Auto cleanup fixture that runs after each test.

    Registers the test user for cleanup automatically.
    """
    # Register the test user for cleanup
    cleanup_users.append(test_user_id)

    yield

    # Cleanup is handled by cleanup_users fixture


# =============================================================================
# BASIC OPERATIONS TESTS
# =============================================================================

class TestIntegrationBasicOperations:
    """Test basic token tracking operations."""

    def test_new_user_gets_billing_day_set(self, tracker, test_user_id, cleanup_users):
        """New user should get billing_day = current day."""
        logger.info("Testing: New user billing day initialization")

        # Record first usage for new user
        result = tracker.record_usage(test_user_id, 100, 50)

        # Verify billing_day is set to today
        today = datetime.now(timezone.utc).day
        assert result['billing_day'] == today, \
            f"Expected billing_day={today}, got {result['billing_day']}"

        # Verify tokens were recorded
        assert result['total_tokens'] == 150, \
            f"Expected total_tokens=150, got {result['total_tokens']}"

        logger.info(f"✓ New user billing_day correctly set to {today}")

    def test_token_accumulation_multiple_calls(self, tracker, test_user_id, cleanup_users):
        """Multiple record_usage calls should accumulate tokens."""
        logger.info("Testing: Token accumulation across multiple calls")

        # First usage
        result1 = tracker.record_usage(test_user_id, 100, 50)
        assert result1['total_tokens'] == 150

        # Second usage
        result2 = tracker.record_usage(test_user_id, 200, 100)
        assert result2['total_tokens'] == 450, \
            f"Expected 450, got {result2['total_tokens']}"

        # Third usage
        result3 = tracker.record_usage(test_user_id, 50, 25)
        assert result3['total_tokens'] == 525, \
            f"Expected 525, got {result3['total_tokens']}"

        # Verify with get_usage
        usage = tracker.get_usage(test_user_id)
        assert usage['total_tokens'] == 525
        assert usage['input_tokens'] == 350  # 100 + 200 + 50
        assert usage['output_tokens'] == 175  # 50 + 100 + 25
        assert usage['request_count'] == 3

        logger.info(f"✓ Token accumulation correct: {usage['total_tokens']} tokens over {usage['request_count']} requests")

    def test_check_limit_returns_false_when_over_limit(self, tracker, test_user_id, cleanup_users):
        """check_limit should return allowed=False when limit exceeded."""
        logger.info("Testing: Limit enforcement")

        # First, set a low limit for the user
        tracker.record_usage(test_user_id, 100, 50)
        tracker.set_user_limit(test_user_id, 500)  # Set limit to 500 tokens

        # Use tokens up to limit
        tracker.record_usage(test_user_id, 200, 200)  # Now at 550 total

        # Check limit - should be exceeded
        result = tracker.check_limit(test_user_id)

        assert result['allowed'] == False, \
            f"Expected allowed=False, got {result['allowed']}"
        assert result['total_tokens'] >= 500, \
            f"Expected total_tokens >= 500, got {result['total_tokens']}"
        assert result['remaining_tokens'] == 0

        logger.info(f"✓ Limit enforcement working: allowed={result['allowed']}, total={result['total_tokens']}")

    def test_check_limit_returns_true_when_under_limit(self, tracker, test_user_id, cleanup_users):
        """check_limit should return allowed=True when under limit."""
        logger.info("Testing: Under limit allows request")

        # Record small usage
        tracker.record_usage(test_user_id, 100, 50)

        # Check limit - should be allowed
        result = tracker.check_limit(test_user_id)

        assert result['allowed'] == True
        assert result['remaining_tokens'] > 0

        logger.info(f"✓ Under limit: allowed={result['allowed']}, remaining={result['remaining_tokens']}")


# =============================================================================
# THRESHOLD NOTIFICATION TESTS
# =============================================================================

class TestIntegrationThresholds:
    """Test threshold notification triggers."""

    def test_80_percent_threshold_triggers(self, tracker, test_user_id, cleanup_users):
        """80% threshold should trigger notification."""
        logger.info("Testing: 80% threshold notification")

        # Set a limit and record usage just under 80%
        tracker.record_usage(test_user_id, 100, 0)
        tracker.set_user_limit(test_user_id, 1000)

        # Record usage to push past 80%
        result = tracker.record_usage(test_user_id, 700, 100)  # Now at 900/1000 = 90%

        # First crossing should trigger 80%
        # Note: may trigger 90% instead if we crossed both
        assert result['threshold_reached'] in ['80%', '90%'], \
            f"Expected threshold trigger, got {result['threshold_reached']}"

        logger.info(f"✓ Threshold triggered: {result['threshold_reached']}")

    def test_90_percent_threshold_triggers(self, tracker, test_user_id, cleanup_users):
        """90% threshold should trigger notification."""
        logger.info("Testing: 90% threshold notification")

        # Set a limit
        tracker.record_usage(test_user_id, 100, 0)
        tracker.set_user_limit(test_user_id, 1000)

        # Record usage to exactly 80% - should trigger 80%
        result1 = tracker.record_usage(test_user_id, 700, 0)  # 800/1000 = 80%

        # Record more to push past 90%
        result2 = tracker.record_usage(test_user_id, 150, 0)  # 950/1000 = 95%

        assert result2['threshold_reached'] == '90%', \
            f"Expected 90% threshold, got {result2['threshold_reached']}"

        logger.info(f"✓ 90% threshold triggered correctly")

    def test_100_percent_threshold_triggers(self, tracker, test_user_id, cleanup_users):
        """100% threshold should trigger and set limit_reached_at."""
        logger.info("Testing: 100% threshold (limit reached)")

        # Set a low limit
        tracker.record_usage(test_user_id, 100, 0)
        tracker.set_user_limit(test_user_id, 500)

        # Clear notifications to ensure clean state
        tracker.reset_notifications(test_user_id)

        # Record usage to exceed limit
        result = tracker.record_usage(test_user_id, 400, 100)  # 600/500 = 120%

        assert result['threshold_reached'] == '100%', \
            f"Expected 100% threshold, got {result['threshold_reached']}"

        logger.info(f"✓ 100% limit reached correctly")

    def test_threshold_only_triggers_once(self, tracker, test_user_id, cleanup_users):
        """Thresholds should only trigger once per billing period."""
        logger.info("Testing: Threshold triggers only once")

        # Set limit first
        tracker.record_usage(test_user_id, 100, 0)
        tracker.set_user_limit(test_user_id, 1000)

        # First push to 80% - should trigger 80%
        result1 = tracker.record_usage(test_user_id, 700, 0)  # 800/1000 = 80%
        first_threshold = result1['threshold_reached']
        logger.info(f"First threshold: {first_threshold}")

        # Push more usage - should trigger 90%
        result2 = tracker.record_usage(test_user_id, 100, 0)  # 900/1000 = 90%
        second_threshold = result2['threshold_reached']
        logger.info(f"Second threshold: {second_threshold}")

        # Now add more usage - should NOT re-trigger 80% or 90%
        result3 = tracker.record_usage(test_user_id, 50, 0)  # 950/1000 = 95%

        # Third call should not trigger any threshold (already notified)
        assert result3['threshold_reached'] is None or result3['threshold_reached'] == '100%', \
            f"Unexpected threshold re-trigger: {result3['threshold_reached']}"

        logger.info("✓ Thresholds do not re-trigger after first notification")


# =============================================================================
# ANNIVERSARY-BASED RESET TESTS
# =============================================================================

class TestIntegrationAnniversaryReset:
    """Test anniversary-based billing period functionality."""

    def test_billing_period_key_format(self, tracker, test_user_id, cleanup_users):
        """Billing period key should be YYYY-MM-DD format."""
        logger.info("Testing: Billing period key format")

        # Record usage
        tracker.record_usage(test_user_id, 100, 50)

        # Get the raw record to check billing_period format
        response = tracker.table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': test_user_id},
            Limit=1
        )

        items = response.get('Items', [])
        assert len(items) == 1, "Expected one record"

        billing_period = items[0]['billing_period']

        # Verify YYYY-MM-DD format
        try:
            datetime.strptime(billing_period, '%Y-%m-%d')
        except ValueError:
            pytest.fail(f"billing_period '{billing_period}' is not in YYYY-MM-DD format")

        logger.info(f"✓ Billing period key format correct: {billing_period}")

    def test_usage_isolated_by_billing_period(self, tracker, test_user_id, cleanup_users):
        """Usage in different billing periods should not mix."""
        logger.info("Testing: Usage isolation by billing period")

        # Record usage in current period
        result = tracker.record_usage(test_user_id, 100, 50)
        current_period = result['billing_day']

        # Manually insert a record for a different period (last month)
        now = datetime.now(timezone.utc)
        if now.month == 1:
            old_period_date = now.replace(year=now.year - 1, month=12, day=15)
        else:
            old_period_date = now.replace(month=now.month - 1, day=15)

        old_billing_period = old_period_date.strftime('%Y-%m-%d')

        # Insert old period record
        tracker.table.put_item(
            Item={
                'user_id': test_user_id,
                'billing_period': old_billing_period,
                'input_tokens': 5000,
                'output_tokens': 2500,
                'total_tokens': 7500,
                'token_limit': TEST_TOKEN_LIMIT,
                'billing_day': 15,
                'request_count': 10
            }
        )

        # Current usage should still be 150, not 7650
        current_usage = tracker.get_usage(test_user_id)

        # Current period should only show current tokens
        assert current_usage['total_tokens'] == 150, \
            f"Expected 150 tokens in current period, got {current_usage['total_tokens']}"

        logger.info(f"✓ Usage correctly isolated: current={current_usage['total_tokens']}, old period had 7500")

    def test_get_usage_returns_correct_period_data(self, tracker, test_user_id, cleanup_users):
        """get_usage should return data for current billing period only."""
        logger.info("Testing: get_usage returns correct period data")

        # Record usage
        tracker.record_usage(test_user_id, 100, 50)
        tracker.record_usage(test_user_id, 200, 100)

        usage = tracker.get_usage(test_user_id)

        # Verify structure
        assert 'billing_period_start' in usage
        assert 'billing_period_end' in usage
        assert 'billing_day' in usage
        assert 'reset_date' in usage

        # Verify values
        assert usage['total_tokens'] == 450
        assert usage['request_count'] == 2

        # Verify billing day is consistent
        today = datetime.now(timezone.utc).day
        assert usage['billing_day'] == today

        logger.info(f"✓ get_usage returns correct period data: billing_day={usage['billing_day']}")


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestIntegrationEdgeCases:
    """Test edge cases and error handling."""

    def test_concurrent_requests_atomic_add(self, tracker, test_user_id, cleanup_users):
        """Concurrent record_usage calls should not lose tokens (atomic ADD)."""
        logger.info("Testing: Concurrent requests atomic ADD")

        # Number of concurrent requests
        num_requests = 10
        tokens_per_request = 100

        def record_usage():
            return tracker.record_usage(test_user_id, tokens_per_request, 0)

        # Execute concurrent requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(record_usage) for _ in range(num_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # Verify final count
        final_usage = tracker.get_usage(test_user_id)
        expected_total = num_requests * tokens_per_request

        assert final_usage['total_tokens'] == expected_total, \
            f"Expected {expected_total} tokens, got {final_usage['total_tokens']}. Lost {expected_total - final_usage['total_tokens']} tokens!"
        assert final_usage['request_count'] == num_requests, \
            f"Expected {num_requests} requests, got {final_usage['request_count']}"

        logger.info(f"✓ All {num_requests} concurrent requests accounted for: {final_usage['total_tokens']} tokens")

    def test_missing_user_check_limit_graceful(self, tracker, test_user_id, cleanup_users):
        """check_limit for non-existent user should return allowed=True with defaults."""
        logger.info("Testing: Missing user check_limit graceful handling")

        # Don't record any usage - user doesn't exist
        result = tracker.check_limit(test_user_id)

        assert result['allowed'] == True
        assert result['total_tokens'] == 0
        assert result['remaining_tokens'] == TEST_TOKEN_LIMIT
        assert 'billing_day' in result

        logger.info(f"✓ Missing user handled gracefully: allowed={result['allowed']}")

    def test_missing_user_get_usage_graceful(self, tracker, test_user_id, cleanup_users):
        """get_usage for non-existent user should return empty response."""
        logger.info("Testing: Missing user get_usage graceful handling")

        # Don't record any usage - user doesn't exist
        usage = tracker.get_usage(test_user_id)

        assert usage['total_tokens'] == 0
        assert usage['input_tokens'] == 0
        assert usage['output_tokens'] == 0
        assert usage['request_count'] == 0
        assert 'billing_day' in usage

        logger.info(f"✓ Missing user get_usage handled gracefully")

    def test_invalid_billing_day_recovery(self, tracker, test_user_id, cleanup_users):
        """System should handle corrupted billing_day data gracefully."""
        logger.info("Testing: Invalid billing_day handling")

        # Insert a record with invalid billing_day
        today = datetime.now(timezone.utc)
        billing_period = today.strftime('%Y-%m-%d')

        tracker.table.put_item(
            Item={
                'user_id': test_user_id,
                'billing_period': billing_period,
                'input_tokens': 100,
                'output_tokens': 50,
                'total_tokens': 150,
                'token_limit': TEST_TOKEN_LIMIT,
                'billing_day': 99,  # Invalid day!
                'request_count': 1
            }
        )

        # System should still work - get_billing_day returns the raw value,
        # but get_current_billing_period clamps it internally
        result = tracker.check_limit(test_user_id)

        # Should not crash - system continues to function
        assert 'allowed' in result
        assert 'billing_day' in result

        # Note: billing_day is returned as stored (99), but internal calculations
        # clamp it to valid range. The reset_date should still be valid.
        reset_date = result.get('reset_date')
        assert reset_date is not None, "reset_date should be present"

        # Verify reset_date is valid ISO format (proves internal clamping worked)
        try:
            datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"reset_date '{reset_date}' is invalid - clamping failed")

        logger.info(f"✓ System handles invalid billing_day (99) gracefully, reset_date={reset_date}")

    def test_zero_token_usage(self, tracker, test_user_id, cleanup_users):
        """Recording zero tokens should work correctly."""
        logger.info("Testing: Zero token usage")

        # Record zero tokens
        result = tracker.record_usage(test_user_id, 0, 0)

        assert result['total_tokens'] == 0

        # Record more zeros
        result2 = tracker.record_usage(test_user_id, 0, 0)
        assert result2['total_tokens'] == 0

        # Request count should still increment
        usage = tracker.get_usage(test_user_id)
        assert usage['request_count'] == 2

        logger.info(f"✓ Zero token usage handled correctly")


# =============================================================================
# ADMIN OPERATIONS TESTS
# =============================================================================

class TestIntegrationAdminOperations:
    """Test admin operations."""

    def test_set_user_limit_persists(self, tracker, test_user_id, cleanup_users):
        """set_user_limit should persist custom limit."""
        logger.info("Testing: set_user_limit persistence")

        # First create a record
        tracker.record_usage(test_user_id, 100, 50)

        # Set custom limit
        custom_limit = 999999
        success = tracker.set_user_limit(test_user_id, custom_limit)
        assert success == True

        # Verify limit persists
        usage = tracker.get_usage(test_user_id)
        assert usage['token_limit'] == custom_limit, \
            f"Expected limit {custom_limit}, got {usage['token_limit']}"

        # Verify it survives additional usage
        tracker.record_usage(test_user_id, 100, 50)
        usage2 = tracker.get_usage(test_user_id)
        assert usage2['token_limit'] == custom_limit

        logger.info(f"✓ Custom limit {custom_limit} persisted correctly")

    def test_reset_notifications_clears_flags(self, tracker, test_user_id, cleanup_users):
        """reset_notifications should clear threshold flags."""
        logger.info("Testing: reset_notifications clears flags")

        # Set up user with triggered notifications
        tracker.record_usage(test_user_id, 100, 0)
        tracker.set_user_limit(test_user_id, 100)

        # Trigger thresholds by exceeding limit
        tracker.record_usage(test_user_id, 50, 0)  # 150/100 = 150%

        # Get raw record to check flags
        response = tracker.table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': test_user_id},
            Limit=1,
            ScanIndexForward=False
        )
        item = response['Items'][0]

        # Verify flags were set
        assert item.get('notified_80') or item.get('notified_90') or item.get('limit_reached_at')

        # Reset notifications
        success = tracker.reset_notifications(test_user_id)
        assert success == True

        # Verify flags are cleared
        response = tracker.table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': test_user_id},
            Limit=1,
            ScanIndexForward=False
        )
        item = response['Items'][0]

        assert 'notified_80' not in item or item.get('notified_80') is None
        assert 'notified_90' not in item or item.get('notified_90') is None
        assert 'limit_reached_at' not in item or item.get('limit_reached_at') is None

        logger.info("✓ Notification flags cleared successfully")

    def test_set_user_limit_for_nonexistent_creates_record(self, tracker, test_user_id, cleanup_users):
        """set_user_limit for non-existent user should create record."""
        logger.info("Testing: set_user_limit creates record for new user")

        # Set limit before any usage
        custom_limit = 5000
        success = tracker.set_user_limit(test_user_id, custom_limit)
        assert success == True

        # Record should exist now
        response = tracker.table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': test_user_id},
            Limit=1
        )

        assert len(response.get('Items', [])) == 1
        assert int(response['Items'][0]['token_limit']) == custom_limit

        logger.info(f"✓ set_user_limit created record with limit {custom_limit}")


# =============================================================================
# TIMESTAMP AND METADATA TESTS
# =============================================================================

class TestIntegrationTimestamps:
    """Test timestamp and metadata handling."""

    def test_last_request_at_updates(self, tracker, test_user_id, cleanup_users):
        """last_request_at should update on each request."""
        logger.info("Testing: last_request_at updates")

        # First request
        tracker.record_usage(test_user_id, 100, 50)
        usage1 = tracker.get_usage(test_user_id)
        first_timestamp = usage1['last_request_at']

        # Wait a moment
        time.sleep(0.1)

        # Second request
        tracker.record_usage(test_user_id, 100, 50)
        usage2 = tracker.get_usage(test_user_id)
        second_timestamp = usage2['last_request_at']

        # Timestamps should be different
        assert first_timestamp != second_timestamp, \
            f"last_request_at should update: {first_timestamp} vs {second_timestamp}"
        assert second_timestamp > first_timestamp

        logger.info(f"✓ last_request_at updates correctly")

    def test_subscribed_at_set_only_once(self, tracker, test_user_id, cleanup_users):
        """subscribed_at should only be set on first request."""
        logger.info("Testing: subscribed_at set only once")

        # First request
        tracker.record_usage(test_user_id, 100, 50)
        usage1 = tracker.get_usage(test_user_id)
        first_subscribed = usage1['subscribed_at']

        # Wait and make more requests
        time.sleep(0.1)
        tracker.record_usage(test_user_id, 100, 50)
        tracker.record_usage(test_user_id, 100, 50)

        usage2 = tracker.get_usage(test_user_id)

        # subscribed_at should not change
        assert usage2['subscribed_at'] == first_subscribed, \
            "subscribed_at should not change after initial set"

        logger.info(f"✓ subscribed_at remains constant: {first_subscribed}")

    def test_reset_date_format(self, tracker, test_user_id, cleanup_users):
        """reset_date should be in ISO format with Z suffix."""
        logger.info("Testing: reset_date format")

        tracker.record_usage(test_user_id, 100, 50)
        usage = tracker.get_usage(test_user_id)

        reset_date = usage['reset_date']

        # Should end with Z
        assert reset_date.endswith('Z'), f"reset_date should end with Z: {reset_date}"

        # Should be parseable
        try:
            datetime.fromisoformat(reset_date.replace('Z', '+00:00'))
        except ValueError:
            pytest.fail(f"reset_date '{reset_date}' is not valid ISO format")

        logger.info(f"✓ reset_date format correct: {reset_date}")


# =============================================================================
# HELPER FUNCTION FOR MANUAL TESTING
# =============================================================================

def manual_cleanup(user_id_pattern: str = TEST_USER_PREFIX, use_test_table: bool = True):
    """
    Manual cleanup function to remove test data.

    Usage:
        from tests.integration.test_token_tracker_integration import manual_cleanup
        manual_cleanup()  # Cleans all integration-test-* users
    """
    import boto3

    dynamodb = boto3.resource('dynamodb')
    table_name = TEST_TABLE_NAME if use_test_table else DEV_TABLE_NAME
    table = dynamodb.Table(table_name)

    # Scan for test users
    response = table.scan(
        FilterExpression='begins_with(user_id, :prefix)',
        ExpressionAttributeValues={':prefix': user_id_pattern}
    )

    items = response.get('Items', [])
    print(f"Found {len(items)} test records to delete")

    for item in items:
        table.delete_item(
            Key={
                'user_id': item['user_id'],
                'billing_period': item['billing_period']
            }
        )
        print(f"Deleted: {item['user_id']} / {item['billing_period']}")

    print("Cleanup complete")


if __name__ == '__main__':
    # Allow running specific tests or cleanup from command line
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--cleanup':
        manual_cleanup()
    else:
        # Run tests
        pytest.main([__file__, '-v', '-s', '-m', 'integration'])
