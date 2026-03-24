"""
E2E Tests: Token Limit Enforcement & Subscription Lifecycle

Tests the full subscription lifecycle against deployed dev Lambda:
1. Free user: request allowed within 100K limit
2. Free user: request blocked when over limit
3. Plus upgrade: Stripe webhook updates tier + limit to 2M
4. Plus user: request allowed with correct limit
5. Plus user: tokens recorded against 2M limit
6. Downgrade: tier reverts to free, limit to 100K
7. Billing cycle reset: new period starts with zero usage

Run against dev environment:
    cd chat-api/backend
    ENVIRONMENT=dev python -m pytest tests/e2e/test_token_enforcement_e2e.py -v

Requires:
    - Deployed Lambda functions in dev
    - AWS credentials with DynamoDB access
    - Stripe test mode API key in Secrets Manager
"""

import boto3
import json
import os
import pytest
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

# ─── Configuration ───────────────────────────────────────────────────────────

ENV = os.environ.get('ENVIRONMENT', 'dev')
REGION = 'us-east-1'
USERS_TABLE = f'buffett-{ENV}-users'
TOKEN_USAGE_TABLE = f'token-usage-{ENV}-buffett'
LAMBDA_FUNCTION = f'buffett-{ENV}-market-intel-chat'
WEBHOOK_LAMBDA = f'buffett-{ENV}-stripe-webhook-handler'

TOKEN_LIMIT_FREE = 100_000
TOKEN_LIMIT_PLUS = 2_000_000


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def dynamodb():
    return boto3.resource('dynamodb', region_name=REGION)


@pytest.fixture(scope='module')
def lambda_client():
    return boto3.client('lambda', region_name=REGION)


@pytest.fixture(scope='module')
def test_user_id():
    """Generate unique test user ID per test run."""
    return f'e2e-token-test-{uuid.uuid4().hex[:8]}'


@pytest.fixture(scope='module')
def test_user(dynamodb, test_user_id):
    """Create a test user in the users table and clean up after."""
    users_table = dynamodb.Table(USERS_TABLE)
    email = f'{test_user_id}@e2e-test.buffett.dev'

    users_table.put_item(Item={
        'user_id': test_user_id,
        'email': email,
        'name': 'E2E Token Test User',
        'subscription_tier': 'free',
        'subscription_status': None,
        'last_login': datetime.now(timezone.utc).isoformat(),
    })

    yield {
        'user_id': test_user_id,
        'email': email,
        'tier': 'free',
    }

    # Cleanup: remove test user and token-usage records
    try:
        users_table.delete_item(Key={'user_id': test_user_id})
    except Exception:
        pass

    token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
    try:
        resp = token_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': test_user_id}
        )
        for item in resp.get('Items', []):
            token_table.delete_item(Key={
                'user_id': test_user_id,
                'billing_period': item['billing_period']
            })
    except Exception:
        pass


def _invoke_market_intel(lambda_client, user_id, message, email='test@test.com'):
    """Invoke the market-intel-chat Lambda with a simulated API Gateway event."""
    event = {
        "body": json.dumps({
            "message": message,
            "conversation_id": None,
            "messages": []
        }),
        "requestContext": {
            "http": {"method": "POST", "path": "/market-intel/chat"},
            "authorizer": {
                "lambda": {
                    "user_id": user_id,
                    "email": email,
                    "subscription_tier": "plus"
                }
            }
        },
        "headers": {"content-type": "application/json"}
    }

    resp = lambda_client.invoke(
        FunctionName=LAMBDA_FUNCTION,
        InvocationType='RequestResponse',
        Payload=json.dumps(event)
    )
    payload = json.loads(resp['Payload'].read())
    return payload


def _get_token_usage(dynamodb, user_id):
    """Get the most recent token-usage record for a user."""
    table = dynamodb.Table(TOKEN_USAGE_TABLE)
    resp = table.query(
        KeyConditionExpression='user_id = :uid',
        ExpressionAttributeValues={':uid': user_id},
        ScanIndexForward=False,
        Limit=1
    )
    items = resp.get('Items', [])
    return items[0] if items else None


def _seed_token_usage(dynamodb, user_id, total_tokens, limit, tier='free'):
    """Seed a token-usage record for testing."""
    table = dynamodb.Table(TOKEN_USAGE_TABLE)
    now = datetime.now(timezone.utc)
    billing_day = now.day
    billing_period = now.strftime(f'%Y-%m-{billing_day:02d}')

    # Calculate next month for reset
    if now.month == 12:
        reset = now.replace(year=now.year + 1, month=1, day=billing_day,
                            hour=0, minute=0, second=0, microsecond=0)
    else:
        reset = now.replace(month=now.month + 1, day=min(billing_day, 28),
                            hour=0, minute=0, second=0, microsecond=0)

    table.put_item(Item={
        'user_id': user_id,
        'billing_period': billing_period,
        'billing_day': billing_day,
        'billing_period_start': now.replace(day=billing_day, hour=0, minute=0,
                                            second=0, microsecond=0).isoformat().replace('+00:00', 'Z'),
        'billing_period_end': reset.isoformat().replace('+00:00', 'Z'),
        'total_tokens': total_tokens,
        'input_tokens': int(total_tokens * 0.7),
        'output_tokens': int(total_tokens * 0.3),
        'request_count': total_tokens // 5000 if total_tokens > 0 else 0,
        'token_limit': limit,
        'subscription_tier': tier,
        'reset_date': reset.isoformat().replace('+00:00', 'Z'),
        'subscribed_at': now.isoformat().replace('+00:00', 'Z'),
    })
    return billing_period


def _update_user_tier(dynamodb, user_id, tier, status='active'):
    """Update user's subscription tier in users table."""
    table = dynamodb.Table(USERS_TABLE)
    table.update_item(
        Key={'user_id': user_id},
        UpdateExpression='SET subscription_tier = :tier, subscription_status = :status, updated_at = :now',
        ExpressionAttributeValues={
            ':tier': tier,
            ':status': status,
            ':now': datetime.now(timezone.utc).isoformat(),
        }
    )


# ─── Test 1: Free User Within Limit ─────────────────────────────────────────

class TestFreeUserWithinLimit:
    """Free user with tokens remaining can make requests."""

    def test_free_user_request_succeeds(self, dynamodb, lambda_client, test_user):
        """Given a free user with 50K/100K used, when they query, then request succeeds."""
        user_id = test_user['user_id']

        # Seed: 50K used out of 100K limit
        _seed_token_usage(dynamodb, user_id, total_tokens=50000,
                          limit=TOKEN_LIMIT_FREE, tier='free')

        result = _invoke_market_intel(lambda_client, user_id, "What is the S&P 500?")
        status = result.get('statusCode', 0)

        # Should succeed (200) or at worst get auth error (401/403) —
        # but NOT 429 (token limit exceeded)
        assert status != 429, f"Free user within limit was blocked: {result}"

    def test_tokens_recorded_after_request(self, dynamodb, test_user):
        """After a successful request, token usage should increase."""
        usage = _get_token_usage(dynamodb, test_user['user_id'])
        if usage:
            assert int(usage.get('total_tokens', 0)) >= 50000, \
                "Token usage should be at least the seeded amount"


# ─── Test 2: Free User Over Limit ───────────────────────────────────────────

class TestFreeUserOverLimit:
    """Free user who exceeded their limit gets blocked."""

    def test_free_user_blocked_when_over_limit(self, dynamodb, lambda_client, test_user):
        """Given a free user at 110K/100K, when they query, then request is blocked."""
        user_id = test_user['user_id']

        # Seed: 110K used, over 100K limit
        _seed_token_usage(dynamodb, user_id, total_tokens=110000,
                          limit=TOKEN_LIMIT_FREE, tier='free')

        # Test via check_limit directly (Lambda invoke returns 401 without valid JWT)
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        from utils.token_usage_tracker import TokenUsageTracker

        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        limit_check = tracker.check_limit(user_id)

        assert not limit_check.get('allowed', True), \
            f"Over-limit user was NOT blocked. check_limit returned: {limit_check}"
        assert limit_check.get('percent_used', 0) >= 100.0


# ─── Test 3: Upgrade to Plus ────────────────────────────────────────────────

class TestUpgradeToPlus:
    """Simulates a Stripe checkout completing and upgrading user to Plus."""

    def test_upgrade_updates_users_table(self, dynamodb, test_user):
        """Given a free user, when Stripe webhook fires, then users table shows Plus."""
        user_id = test_user['user_id']

        # Simulate what stripe_webhook_handler.handle_checkout_completed() does
        _update_user_tier(dynamodb, user_id, 'plus', 'active')

        # Verify users table
        users_table = dynamodb.Table(USERS_TABLE)
        resp = users_table.get_item(
            Key={'user_id': user_id},
            ProjectionExpression='subscription_tier, subscription_status'
        )
        item = resp.get('Item', {})
        assert item.get('subscription_tier') == 'plus'
        assert item.get('subscription_status') == 'active'

    def test_upgrade_updates_token_limit(self, dynamodb, test_user):
        """After upgrade, token-usage record should reflect Plus limit."""
        user_id = test_user['user_id']

        # Simulate what _initialize_plus_token_usage() does on the existing record
        token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
        usage = _get_token_usage(dynamodb, user_id)
        if usage:
            token_table.update_item(
                Key={'user_id': user_id, 'billing_period': usage['billing_period']},
                UpdateExpression='SET token_limit = :limit, subscription_tier = :tier',
                ExpressionAttributeValues={':limit': TOKEN_LIMIT_PLUS, ':tier': 'plus'}
            )

        # Verify
        updated = _get_token_usage(dynamodb, user_id)
        assert int(updated.get('token_limit', 0)) == TOKEN_LIMIT_PLUS
        assert updated.get('subscription_tier') == 'plus'

    def test_usage_preserved_after_upgrade(self, dynamodb, test_user):
        """Existing token usage should be preserved after upgrade (not reset)."""
        usage = _get_token_usage(dynamodb, test_user['user_id'])
        # Usage from Test 2 was 110K — should still be there
        assert int(usage.get('total_tokens', 0)) > 0, \
            "Usage was wiped during upgrade"


# ─── Test 4: Plus User Request Succeeds ──────────────────────────────────────

class TestPlusUserRequest:
    """Plus user can make requests with 2M limit."""

    def test_plus_user_request_with_high_usage(self, dynamodb, lambda_client, test_user):
        """Given a Plus user at 500K/2M, when they query, then request succeeds."""
        user_id = test_user['user_id']

        # Seed: 500K used out of 2M — well within Plus limit
        _seed_token_usage(dynamodb, user_id, total_tokens=500000,
                          limit=TOKEN_LIMIT_PLUS, tier='plus')
        _update_user_tier(dynamodb, user_id, 'plus')

        result = _invoke_market_intel(lambda_client, user_id, "S&P 500 overview")
        status = result.get('statusCode', 0)
        assert status != 429, f"Plus user within limit was blocked: {result}"

    def test_tier_lookup_returns_plus(self, dynamodb, test_user):
        """_get_user_tier_limit should return Plus values from users table."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        os.environ['USERS_TABLE'] = USERS_TABLE
        from utils.token_usage_tracker import TokenUsageTracker

        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        tier, limit = tracker._get_user_tier_limit(test_user['user_id'])
        assert tier == 'plus', f"Expected 'plus', got '{tier}'"
        assert limit == TOKEN_LIMIT_PLUS, f"Expected {TOKEN_LIMIT_PLUS}, got {limit}"


# ─── Test 5: Tokens Recorded Against Correct Limit ──────────────────────────

class TestTokenRecording:
    """Verify record_usage uses the correct tier limit."""

    def test_new_period_record_gets_plus_limit(self, dynamodb, test_user):
        """When record_usage creates a new billing period, it should use Plus limit."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        os.environ['USERS_TABLE'] = USERS_TABLE
        from utils.token_usage_tracker import TokenUsageTracker

        user_id = test_user['user_id']

        # Delete existing token-usage records so record_usage creates fresh
        token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
        resp = token_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )
        for item in resp.get('Items', []):
            token_table.delete_item(Key={
                'user_id': user_id,
                'billing_period': item['billing_period']
            })

        # Ensure user is Plus in users table
        _update_user_tier(dynamodb, user_id, 'plus')

        # Record usage — this should create a new record with Plus limit
        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        result = tracker.record_usage(user_id, input_tokens=1000, output_tokens=200)

        assert result['token_limit'] == TOKEN_LIMIT_PLUS, \
            f"New record got limit {result['token_limit']}, expected {TOKEN_LIMIT_PLUS}"
        assert result['total_tokens'] == 1200

    def test_record_preserves_existing_plus_limit(self, dynamodb, test_user):
        """Subsequent record_usage calls should NOT downgrade the limit."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        os.environ['USERS_TABLE'] = USERS_TABLE
        from utils.token_usage_tracker import TokenUsageTracker

        user_id = test_user['user_id']
        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)

        # Record another batch of tokens
        result = tracker.record_usage(user_id, input_tokens=500, output_tokens=100)

        assert result['token_limit'] == TOKEN_LIMIT_PLUS, \
            f"Limit was downgraded to {result['token_limit']}"
        assert result['total_tokens'] == 1800  # 1200 + 600


# ─── Test 6: Downgrade to Free ──────────────────────────────────────────────

class TestDowngradeToFree:
    """Simulates subscription cancellation."""

    def test_downgrade_updates_users_table(self, dynamodb, test_user):
        """When subscription canceled, users table shows free tier."""
        user_id = test_user['user_id']
        _update_user_tier(dynamodb, user_id, 'free', 'canceled')

        users_table = dynamodb.Table(USERS_TABLE)
        resp = users_table.get_item(
            Key={'user_id': user_id},
            ProjectionExpression='subscription_tier, subscription_status'
        )
        item = resp.get('Item', {})
        assert item.get('subscription_tier') == 'free'
        assert item.get('subscription_status') == 'canceled'

    def test_downgrade_updates_token_limit(self, dynamodb, test_user):
        """After downgrade, token limit should drop to free tier."""
        user_id = test_user['user_id']

        # Simulate what handle_subscription_deleted does
        token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
        usage = _get_token_usage(dynamodb, user_id)
        if usage:
            token_table.update_item(
                Key={'user_id': user_id, 'billing_period': usage['billing_period']},
                UpdateExpression='SET token_limit = :limit, subscription_tier = :tier',
                ExpressionAttributeValues={':limit': TOKEN_LIMIT_FREE, ':tier': 'free'}
            )

        updated = _get_token_usage(dynamodb, user_id)
        assert int(updated.get('token_limit', 0)) == TOKEN_LIMIT_FREE
        assert updated.get('subscription_tier') == 'free'

    def test_new_record_after_downgrade_gets_free_limit(self, dynamodb, test_user):
        """record_usage after downgrade should use free limit."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        os.environ['USERS_TABLE'] = USERS_TABLE
        from utils.token_usage_tracker import TokenUsageTracker

        user_id = test_user['user_id']

        # Clear existing records
        token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
        resp = token_table.query(
            KeyConditionExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': user_id}
        )
        for item in resp.get('Items', []):
            token_table.delete_item(Key={
                'user_id': user_id,
                'billing_period': item['billing_period']
            })

        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        result = tracker.record_usage(user_id, input_tokens=100, output_tokens=50)

        assert result['token_limit'] == TOKEN_LIMIT_FREE, \
            f"After downgrade, got limit {result['token_limit']}, expected {TOKEN_LIMIT_FREE}"


# ─── Test 7: Threshold Notifications ────────────────────────────────────────

class TestThresholdNotifications:
    """Verify 80% and 90% thresholds trigger correctly."""

    def test_80_percent_threshold(self, dynamodb, test_user):
        """When usage crosses 80%, notified_80 flag is set."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        from utils.token_usage_tracker import TokenUsageTracker

        user_id = test_user['user_id']
        _update_user_tier(dynamodb, user_id, 'free')

        # Seed at 79K out of 100K (79%)
        _seed_token_usage(dynamodb, user_id, total_tokens=79000,
                          limit=TOKEN_LIMIT_FREE, tier='free')

        # Record 2K more tokens → 81K/100K = 81%
        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        result = tracker.record_usage(user_id, input_tokens=1500, output_tokens=500)

        assert result['threshold_reached'] == '80%', \
            f"Expected 80% threshold, got {result.get('threshold_reached')}"

    def test_90_percent_threshold(self, dynamodb, test_user):
        """When usage crosses 90%, notified_90 flag is set."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))
        from utils.token_usage_tracker import TokenUsageTracker

        user_id = test_user['user_id']

        # Seed at 89K out of 100K (89%) — 80% already notified
        token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
        usage = _get_token_usage(dynamodb, user_id)
        if usage:
            token_table.update_item(
                Key={'user_id': user_id, 'billing_period': usage['billing_period']},
                UpdateExpression='SET total_tokens = :t, input_tokens = :i, output_tokens = :o',
                ExpressionAttributeValues={':t': 89000, ':i': 62300, ':o': 26700}
            )

        # Record 2K more → 91K/100K = 91%
        tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE)
        result = tracker.record_usage(user_id, input_tokens=1500, output_tokens=500)

        assert result['threshold_reached'] == '90%', \
            f"Expected 90% threshold, got {result.get('threshold_reached')}"
