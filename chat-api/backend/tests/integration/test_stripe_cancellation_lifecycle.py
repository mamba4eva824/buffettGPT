"""
Integration tests for Stripe subscription cancellation lifecycle.

Tests the complete subscription cancellation flow including:
- Cancel at period end → subscription.updated → subscription.deleted
- Token limit reset on downgrade
- Token usage preserved on cancel
- Immediate cancellation
- Resubscribe after cancellation

Phase 2 Tests: AC-P2-5 (Cancellation Lifecycle Integration)

Run with: pytest tests/integration/test_stripe_cancellation_lifecycle.py -v
"""

import json
import os
import sys
import pytest
import boto3
from moto import mock_aws
from freezegun import freeze_time
from unittest.mock import patch

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any handler imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['TOKEN_USAGE_TABLE'] = 'buffett-test-token-usage'
os.environ['PROCESSED_EVENTS_TABLE'] = 'buffett-test-stripe-events'
os.environ['TOKEN_LIMIT_PLUS'] = '2000000'
os.environ['TOKEN_LIMIT_FREE'] = '100000'

pytestmark = pytest.mark.integration


# =============================================================================
# DynamoDB Table Helpers
# =============================================================================

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
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def create_token_usage_table(dynamodb):
    """Create token-usage table with composite key (user_id, billing_period)."""
    table = dynamodb.create_table(
        TableName='buffett-test-token-usage',
        KeySchema=[
            {'AttributeName': 'user_id', 'KeyType': 'HASH'},
            {'AttributeName': 'billing_period', 'KeyType': 'RANGE'}
        ],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
            {'AttributeName': 'billing_period', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def create_stripe_events_table(dynamodb):
    """Create stripe-events table for idempotency tracking."""
    table = dynamodb.create_table(
        TableName='buffett-test-stripe-events',
        KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'event_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def create_all_tables(dynamodb):
    """Create all required tables and return them as a dict."""
    return {
        'users': create_users_table(dynamodb),
        'token_usage': create_token_usage_table(dynamodb),
        'events': create_stripe_events_table(dynamodb),
    }


def build_webhook_event(event_id, event_type, data_object):
    """Build a mock Stripe webhook event structure."""
    return {
        'id': event_id,
        'type': event_type,
        'data': {'object': data_object}
    }


def build_api_gateway_event(body='{}', signature='test_sig'):
    """Build a mock API Gateway event for Lambda handler."""
    return {
        'body': body,
        'headers': {'stripe-signature': signature}
    }


# =============================================================================
# Test Class: Full Cancellation Lifecycle (AC-P2-5)
# =============================================================================

class TestCancellationLifecycle:
    """
    Integration tests for complete subscription cancellation lifecycle.

    Tests the full flow from active subscription through cancellation to downgrade.
    """

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_full_cancellation_lifecycle_cancel_at_period_end(self, mock_verify):
        """
        P2-5.1: Full cancellation lifecycle with cancel_at_period_end.

        Given: Plus user with active subscription
        When:
            1. User cancels (subscription.updated with cancel_at_period_end=true)
            2. Period ends (subscription.deleted fires)
        Then:
            - After step 1: tier=plus, cancel_at_period_end=true
            - After step 2: tier=free, status=canceled, token_limit=100,000
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'lifecycle-user',
            'stripe_customer_id': 'cus_lifecycle',
            'stripe_subscription_id': 'sub_lifecycle',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
            'cancel_at_period_end': False,
        })

        # Seed token usage
        tables['token_usage'].put_item(Item={
            'user_id': 'lifecycle-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'input_tokens': 100000,
            'output_tokens': 25000,
            'total_tokens': 125000,
        })

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        # Step 1: User cancels (cancel_at_period_end=true)
        mock_verify.return_value = build_webhook_event(
            'evt_lifecycle_cancel_01',
            'customer.subscription.updated',
            {
                'id': 'sub_lifecycle',
                'customer': 'cus_lifecycle',
                'status': 'active',  # Still active
                'cancel_at_period_end': True,  # Scheduled to cancel
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        # Verify after step 1
        user = tables['users'].get_item(Key={'user_id': 'lifecycle-user'})['Item']
        assert user['subscription_tier'] == 'plus'  # Still Plus
        assert user['cancel_at_period_end'] is True  # Scheduled to cancel

        usage = tables['token_usage'].get_item(
            Key={'user_id': 'lifecycle-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 2000000  # Still Plus limit

        # Step 2: Period ends, subscription.deleted fires
        mock_verify.return_value = build_webhook_event(
            'evt_lifecycle_delete_02',
            'customer.subscription.deleted',
            {
                'id': 'sub_lifecycle',
                'customer': 'cus_lifecycle',
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        # Verify after step 2
        user = tables['users'].get_item(Key={'user_id': 'lifecycle-user'})['Item']
        assert user['subscription_tier'] == 'free'  # Downgraded
        assert user['subscription_status'] == 'canceled'
        assert 'stripe_subscription_id' not in user  # Removed

        usage = tables['token_usage'].get_item(
            Key={'user_id': 'lifecycle-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000  # Reset to free limit
        assert usage['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_token_limit_reset_on_downgrade(self, mock_verify):
        """
        P2-5.2: Token limit should reset from 2M to 100K on downgrade.

        Given: Plus user with token_limit=2,000,000
        When: subscription.deleted fires
        Then: token_limit updated to 100,000 (TOKEN_LIMIT_FREE)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'token-limit-user',
            'stripe_customer_id': 'cus_token_limit',
            'stripe_subscription_id': 'sub_token_limit',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'token-limit-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 500000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_token_limit_reset',
            'customer.subscription.deleted',
            {
                'id': 'sub_token_limit',
                'customer': 'cus_token_limit',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token_limit reset
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'token-limit-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_token_usage_preserved_on_cancel(self, mock_verify):
        """
        P2-5.3: Token usage (input_tokens, output_tokens, total_tokens) should be preserved.

        Given: User has used 150,000 tokens (over free limit)
        When: subscription.deleted fires
        Then: Used tokens preserved, only limit changes
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'usage-preserved-user',
            'stripe_customer_id': 'cus_usage_preserved',
            'stripe_subscription_id': 'sub_usage_preserved',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        # User has used 150K tokens (over free limit of 100K)
        tables['token_usage'].put_item(Item={
            'user_id': 'usage-preserved-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'input_tokens': 120000,
            'output_tokens': 30000,
            'total_tokens': 150000,
            'request_count': 75,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_usage_preserved',
            'customer.subscription.deleted',
            {
                'id': 'sub_usage_preserved',
                'customer': 'cus_usage_preserved',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify usage preserved
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'usage-preserved-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['input_tokens']) == 120000  # Unchanged
        assert int(usage['output_tokens']) == 30000  # Unchanged
        assert int(usage['total_tokens']) == 150000  # Unchanged
        assert int(usage['request_count']) == 75  # Unchanged
        assert int(usage['token_limit']) == 100000  # Changed
        assert usage['subscription_tier'] == 'free'  # Changed

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_immediate_cancellation(self, mock_verify):
        """
        P2-5.4: Immediate cancellation (no cancel_at_period_end).

        Given: Plus user requests immediate cancel
        When: subscription.deleted fires (no period wait)
        Then: tier=free immediately, token_limit=100,000
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'immediate-cancel-user',
            'stripe_customer_id': 'cus_immediate',
            'stripe_subscription_id': 'sub_immediate',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'immediate-cancel-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 50000,
        })

        # Immediate cancel - goes directly to subscription.deleted
        mock_verify.return_value = build_webhook_event(
            'evt_immediate_cancel',
            'customer.subscription.deleted',
            {
                'id': 'sub_immediate',
                'customer': 'cus_immediate',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify immediate downgrade
        user = tables['users'].get_item(Key={'user_id': 'immediate-cancel-user'})['Item']
        assert user['subscription_tier'] == 'free'
        assert user['subscription_status'] == 'canceled'

        usage = tables['token_usage'].get_item(
            Key={'user_id': 'immediate-cancel-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_resubscribe_after_cancellation(self, mock_verify):
        """
        P2-5.5: Resubscribe after cancellation.

        Given: User was plus → canceled → free
        When: checkout.session.completed fires
        Then: tier=plus, token_limit=2,000,000, usage reset
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed canceled user
        tables['users'].put_item(Item={
            'user_id': 'resub-user',
            'email': 'resub@test.com',
            'stripe_customer_id': 'cus_resub',
            'subscription_tier': 'free',
            'subscription_status': 'canceled',
            'billing_day': 20,
        })

        # Old token usage from when they were Plus
        tables['token_usage'].put_item(Item={
            'user_id': 'resub-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'free',
            'token_limit': 100000,
            'total_tokens': 95000,  # Almost at free limit
        })

        mock_verify.return_value = build_webhook_event(
            'evt_resub_001',
            'checkout.session.completed',
            {
                'client_reference_id': 'resub-user',
                'customer': 'cus_resub',
                'subscription': 'sub_new_resub',
                'customer_email': 'resub@test.com',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user upgraded
        user = tables['users'].get_item(Key={'user_id': 'resub-user'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_subscription_id'] == 'sub_new_resub'

        # Verify token limit updated to Plus
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'resub-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 2000000
        assert usage['subscription_tier'] == 'plus'


# =============================================================================
# Test Class: Multi-Step Lifecycle Scenarios
# =============================================================================

class TestMultiStepLifecycleScenarios:
    """Tests for complex multi-step subscription lifecycle scenarios."""

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_cancel_then_reactivate_same_period(self, mock_verify):
        """
        Test: User cancels then reactivates within same billing period.

        Given: Plus user schedules cancellation
        When:
            1. subscription.updated (cancel_at_period_end=true)
            2. subscription.updated (cancel_at_period_end=false) - user reactivates
        Then: User remains Plus, cancel_at_period_end=false
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'reactivate-user',
            'stripe_customer_id': 'cus_reactivate',
            'stripe_subscription_id': 'sub_reactivate',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
            'cancel_at_period_end': False,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'reactivate-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 100000,
        })

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        # Step 1: Schedule cancellation
        mock_verify.return_value = build_webhook_event(
            'evt_cancel_sched_01',
            'customer.subscription.updated',
            {
                'id': 'sub_reactivate',
                'customer': 'cus_reactivate',
                'status': 'active',
                'cancel_at_period_end': True,
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'reactivate-user'})['Item']
        assert user['cancel_at_period_end'] is True

        # Step 2: Reactivate (user changes mind)
        mock_verify.return_value = build_webhook_event(
            'evt_reactivate_02',
            'customer.subscription.updated',
            {
                'id': 'sub_reactivate',
                'customer': 'cus_reactivate',
                'status': 'active',
                'cancel_at_period_end': False,  # Reactivated
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        # Verify reactivated
        user = tables['users'].get_item(Key={'user_id': 'reactivate-user'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['cancel_at_period_end'] is False
        assert user['subscription_status'] == 'active'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_payment_failure_then_success_lifecycle(self, mock_verify):
        """
        Test: Payment fails, then succeeds on retry.

        Given: Plus user with active subscription
        When:
            1. invoice.payment_failed fires
            2. invoice.payment_succeeded fires (retry successful)
        Then: User returns to active status
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'payment-retry-user',
            'stripe_customer_id': 'cus_payment_retry',
            'stripe_subscription_id': 'sub_payment_retry',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'payment-retry-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 200000,
        })

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        # Step 1: Payment fails
        mock_verify.return_value = build_webhook_event(
            'evt_payment_fail_01',
            'invoice.payment_failed',
            {
                'subscription': 'sub_payment_retry',
                'customer': 'cus_payment_retry',
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'payment-retry-user'})['Item']
        assert user['subscription_status'] == 'past_due'
        assert user['subscription_tier'] == 'plus'  # Still Plus during grace period

        # Step 2: Payment succeeds (retry)
        mock_verify.return_value = build_webhook_event(
            'evt_payment_success_02',
            'invoice.payment_succeeded',
            {
                'subscription': 'sub_payment_retry',
                'customer': 'cus_payment_retry',
                'billing_reason': 'subscription_cycle',
            }
        )

        response = handler.lambda_handler(build_api_gateway_event(), None)
        assert response['statusCode'] == 200

        # Verify restored to active
        user = tables['users'].get_item(Key={'user_id': 'payment-retry-user'})['Item']
        assert user['subscription_status'] == 'active'
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_exhausted_payment_retries_then_canceled(self, mock_verify):
        """
        Test: Multiple payment failures leading to cancellation.

        Given: Plus user in past_due state
        When: subscription.deleted fires after exhausted retries
        Then: User downgraded to free, token limit reset
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User already in past_due from previous payment failure
        tables['users'].put_item(Item={
            'user_id': 'exhausted-user',
            'stripe_customer_id': 'cus_exhausted',
            'stripe_subscription_id': 'sub_exhausted',
            'subscription_tier': 'plus',
            'subscription_status': 'past_due',
            'billing_day': 20,
            'payment_failed_at': '2025-01-15T10:00:00Z',
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'exhausted-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 150000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_exhausted_delete',
            'customer.subscription.deleted',
            {
                'id': 'sub_exhausted',
                'customer': 'cus_exhausted',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify downgraded
        user = tables['users'].get_item(Key={'user_id': 'exhausted-user'})['Item']
        assert user['subscription_tier'] == 'free'
        assert user['subscription_status'] == 'canceled'

        usage = tables['token_usage'].get_item(
            Key={'user_id': 'exhausted-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000


# =============================================================================
# Test Class: Edge Cases
# =============================================================================

class TestCancellationEdgeCases:
    """Tests for edge cases in cancellation lifecycle."""

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_cancellation_without_token_usage_record(self, mock_verify):
        """
        Test: Cancellation for user without token-usage record.

        Given: Plus user without existing token-usage record
        When: subscription.deleted fires
        Then: User downgraded, no error (token-usage sync is best-effort)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'no-usage-user',
            'stripe_customer_id': 'cus_no_usage',
            'stripe_subscription_id': 'sub_no_usage',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        # No token-usage record

        mock_verify.return_value = build_webhook_event(
            'evt_no_usage_cancel',
            'customer.subscription.deleted',
            {
                'id': 'sub_no_usage',
                'customer': 'cus_no_usage',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should succeed even without token-usage record
        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'no-usage-user'})['Item']
        assert user['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_cancellation_without_billing_day(self, mock_verify):
        """
        Test: Cancellation for user without billing_day.

        Given: Plus user without billing_day attribute
        When: subscription.deleted fires
        Then: User downgraded (token-usage sync skipped gracefully)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'no-billing-day-user',
            'stripe_customer_id': 'cus_no_billing',
            'stripe_subscription_id': 'sub_no_billing',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            # No billing_day
        })

        mock_verify.return_value = build_webhook_event(
            'evt_no_billing_cancel',
            'customer.subscription.deleted',
            {
                'id': 'sub_no_billing',
                'customer': 'cus_no_billing',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should succeed even without billing_day
        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'no-billing-day-user'})['Item']
        assert user['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_double_cancellation_idempotent(self, mock_verify):
        """
        Test: Double cancellation should be idempotent.

        Given: Already canceled user
        When: subscription.deleted fires again
        Then: User remains free (no error, idempotent)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'double-cancel-user',
            'stripe_customer_id': 'cus_double',
            'subscription_tier': 'free',
            'subscription_status': 'canceled',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'double-cancel-user',
            'billing_period': '2025-01-20',
            'subscription_tier': 'free',
            'token_limit': 100000,
            'total_tokens': 50000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_double_cancel',
            'customer.subscription.deleted',
            {
                'id': 'sub_double',
                'customer': 'cus_double',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should succeed (idempotent)
        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'double-cancel-user'})['Item']
        assert user['subscription_tier'] == 'free'

        # Token limit should still be free limit
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'double-cancel-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000
