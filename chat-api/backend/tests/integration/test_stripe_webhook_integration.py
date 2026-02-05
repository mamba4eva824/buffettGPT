"""
Integration tests for Stripe webhook flows.

Tests end-to-end webhook processing with mocked AWS (moto):
- Full checkout flow (checkout.session.completed → user activated)
- Full renewal flow (invoice.payment_succeeded → tokens reset)
- Cancellation flow (subscription.deleted → downgrade to free)
- Failed payment flow (invoice.payment_failed → past_due status)
- GSI fallback behavior
- Concurrent webhook handling
- Idempotency

Run with: pytest tests/integration/test_stripe_webhook_integration.py -v
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

pytestmark = pytest.mark.integration


# =============================================================================
# DynamoDB Table Helpers
# =============================================================================

def create_users_table(dynamodb, with_gsi=True):
    """Create users table with optional GSI."""
    key_schema = [{'AttributeName': 'user_id', 'KeyType': 'HASH'}]
    attr_defs = [{'AttributeName': 'user_id', 'AttributeType': 'S'}]

    kwargs = {
        'TableName': 'buffett-test-users',
        'KeySchema': key_schema,
        'BillingMode': 'PAY_PER_REQUEST'
    }

    if with_gsi:
        attr_defs.append({'AttributeName': 'stripe_customer_id', 'AttributeType': 'S'})
        kwargs['GlobalSecondaryIndexes'] = [{
            'IndexName': 'stripe-customer-index',
            'KeySchema': [{'AttributeName': 'stripe_customer_id', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }]

    kwargs['AttributeDefinitions'] = attr_defs

    table = dynamodb.create_table(**kwargs)
    table.wait_until_exists()
    return table


def create_token_usage_table(dynamodb):
    """Create token-usage table."""
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
    """Create stripe-events table for idempotency."""
    table = dynamodb.create_table(
        TableName='buffett-test-stripe-events',
        KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'event_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def create_all_tables(dynamodb, with_gsi=True):
    """Create all required tables."""
    return {
        'users': create_users_table(dynamodb, with_gsi=with_gsi),
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
# Integration Tests
# =============================================================================

class TestStripeWebhookIntegration:
    """End-to-end integration tests for Stripe webhooks."""

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_full_checkout_flow_creates_plus_user(self, mock_verify):
        """
        Test complete checkout.session.completed flow.

        Given: Free user completes Stripe checkout
        When: checkout.session.completed webhook fires
        Then: User upgraded to Plus with token usage initialized
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed free user
        tables['users'].put_item(Item={
            'user_id': 'checkout-flow-user',
            'email': 'checkout@test.com',
            'subscription_tier': 'free',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_checkout_flow_001',
            'checkout.session.completed',
            {
                'client_reference_id': 'checkout-flow-user',
                'customer': 'cus_checkout_flow',
                'subscription': 'sub_checkout_flow',
                'customer_email': 'checkout@test.com',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Verify response
        assert response['statusCode'] == 200

        # Verify user upgraded
        user = tables['users'].get_item(Key={'user_id': 'checkout-flow-user'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_customer_id'] == 'cus_checkout_flow'
        assert user['stripe_subscription_id'] == 'sub_checkout_flow'
        assert int(user['billing_day']) == 20

        # Verify token usage initialized
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'checkout-flow-user', 'billing_period': '2025-01-20'}
        )
        assert 'Item' in usage
        assert int(usage['Item']['token_limit']) == 2000000
        assert int(usage['Item']['total_tokens']) == 0

        # Verify event marked as processed
        event = tables['events'].get_item(Key={'event_id': 'evt_checkout_flow_001'})
        assert 'Item' in event

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_full_renewal_flow_resets_tokens(self, mock_verify):
        """
        Test complete invoice.payment_succeeded renewal flow.

        Given: Plus user with 1.5M tokens used
        When: invoice.payment_succeeded fires for renewal
        Then: New billing period created with tokens reset to 0
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'renewal-flow-user',
            'stripe_customer_id': 'cus_renewal_flow',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 15,
        })

        # Seed previous period with high usage
        tables['token_usage'].put_item(Item={
            'user_id': 'renewal-flow-user',
            'billing_period': '2025-01-15',
            'total_tokens': 1500000,
            'token_limit': 2000000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_renewal_flow_001',
            'invoice.payment_succeeded',
            {
                'customer': 'cus_renewal_flow',
                'subscription': 'sub_renewal',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify new billing period created
        new_usage = tables['token_usage'].get_item(
            Key={'user_id': 'renewal-flow-user', 'billing_period': '2025-02-15'}
        )
        assert 'Item' in new_usage
        assert int(new_usage['Item']['total_tokens']) == 0
        assert int(new_usage['Item']['token_limit']) == 2000000

        # Verify old period preserved
        old_usage = tables['token_usage'].get_item(
            Key={'user_id': 'renewal-flow-user', 'billing_period': '2025-01-15'}
        )
        assert int(old_usage['Item']['total_tokens']) == 1500000

    @mock_aws
    @freeze_time("2025-01-25 16:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_cancellation_flow_downgrades_user(self, mock_verify):
        """
        Test complete subscription.deleted cancellation flow.

        Given: Plus user with active subscription
        When: customer.subscription.deleted fires
        Then: User downgraded to free tier
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'cancel-flow-user',
            'stripe_customer_id': 'cus_cancel_flow',
            'stripe_subscription_id': 'sub_to_cancel',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_cancel_flow_001',
            'customer.subscription.deleted',
            {
                'id': 'sub_to_cancel',
                'customer': 'cus_cancel_flow',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user downgraded
        user = tables['users'].get_item(Key={'user_id': 'cancel-flow-user'})['Item']
        assert user['subscription_tier'] == 'free'
        assert user['subscription_status'] == 'canceled'
        assert 'stripe_subscription_id' not in user
        assert 'subscription_canceled_at' in user

    @mock_aws
    @freeze_time("2025-01-28 09:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_failed_payment_sets_past_due(self, mock_verify):
        """
        Test complete invoice.payment_failed flow.

        Given: Plus user with active subscription
        When: invoice.payment_failed fires
        Then: User status set to past_due
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'failed-flow-user',
            'stripe_customer_id': 'cus_failed_flow',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_failed_flow_001',
            'invoice.payment_failed',
            {
                'subscription': 'sub_failed',
                'customer': 'cus_failed_flow',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify status updated
        user = tables['users'].get_item(Key={'user_id': 'failed-flow-user'})['Item']
        assert user['subscription_status'] == 'past_due'
        assert 'payment_failed_at' in user
        # Tier should remain Plus during grace period
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 12:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_gsi_fallback_to_scan(self, mock_verify):
        """
        Test that user lookup falls back to scan when GSI unavailable.

        Given: Users table without stripe-customer-index GSI
        When: Webhook fires requiring customer lookup
        Then: Falls back to table scan and finds user
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        # Create tables WITHOUT the GSI
        tables = create_all_tables(dynamodb, with_gsi=False)

        # Seed user
        tables['users'].put_item(Item={
            'user_id': 'gsi-fallback-user',
            'stripe_customer_id': 'cus_gsi_fallback',
            'subscription_tier': 'plus',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_gsi_fallback_001',
            'customer.subscription.deleted',
            {
                'id': 'sub_gsi',
                'customer': 'cus_gsi_fallback',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should succeed via scan fallback
        assert response['statusCode'] == 200

        # Verify user was found and updated
        user = tables['users'].get_item(Key={'user_id': 'gsi-fallback-user'})['Item']
        assert user['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_token_initialization_conditional_check(self, mock_verify):
        """
        Test that existing token record is updated, not overwritten.

        Given: Token-usage record already exists for billing period
        When: checkout.session.completed fires
        Then: Existing record updated with new limit, usage preserved
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed user
        tables['users'].put_item(Item={
            'user_id': 'conditional-user',
            'email': 'conditional@test.com',
        })

        # Pre-existing token usage for same period
        tables['token_usage'].put_item(Item={
            'user_id': 'conditional-user',
            'billing_period': '2025-01-20',
            'total_tokens': 50000,  # Some existing usage
            'token_limit': 100000,  # Old limit
            'subscription_tier': 'free',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_conditional_001',
            'checkout.session.completed',
            {
                'client_reference_id': 'conditional-user',
                'customer': 'cus_conditional',
                'subscription': 'sub_conditional',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token limit updated but usage preserved
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'conditional-user', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 2000000  # Updated to Plus limit
        assert usage['subscription_tier'] == 'plus'
        assert int(usage['total_tokens']) == 50000  # Preserved

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_webhook_idempotency_full_flow(self, mock_verify):
        """
        Test that duplicate events are processed only once.

        Given: Webhook event already processed
        When: Same event received again
        Then: Returns already_processed, no duplicate updates
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        event_id = 'evt_idempotent_001'

        # Pre-mark event as processed
        tables['events'].put_item(Item={
            'event_id': event_id,
            'event_type': 'customer.subscription.deleted',
            'processed_at': '2025-01-20T13:00:00Z',
        })

        # Seed user that would be affected
        tables['users'].put_item(Item={
            'user_id': 'idempotent-user',
            'stripe_customer_id': 'cus_idempotent',
            'subscription_tier': 'plus',
        })

        mock_verify.return_value = build_webhook_event(
            event_id,  # Same event ID
            'customer.subscription.deleted',
            {
                'id': 'sub_idempotent',
                'customer': 'cus_idempotent',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'already_processed'

        # Verify user NOT downgraded (event skipped)
        user = tables['users'].get_item(Key={'user_id': 'idempotent-user'})['Item']
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_update_status_sync(self, mock_verify):
        """
        Test that subscription.updated syncs status changes.

        Given: Plus user with subscription about to cancel
        When: customer.subscription.updated fires with cancel_at_period_end=True
        Then: User record updated with cancel_at_period_end flag
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'update-sync-user',
            'stripe_customer_id': 'cus_update_sync',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'cancel_at_period_end': False,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_update_sync_001',
            'customer.subscription.updated',
            {
                'id': 'sub_update',
                'customer': 'cus_update_sync',
                'status': 'active',
                'cancel_at_period_end': True,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify cancel_at_period_end synced
        user = tables['users'].get_item(Key={'user_id': 'update-sync-user'})['Item']
        assert user['cancel_at_period_end'] is True
        assert user['subscription_status'] == 'active'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_for_existing_customer(self, mock_verify):
        """
        Test checkout works for user who already has stripe_customer_id.

        Given: User who previously subscribed (has customer_id but lapsed)
        When: checkout.session.completed fires
        Then: Subscription reactivated with existing customer_id
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed lapsed user (has customer_id but free tier)
        tables['users'].put_item(Item={
            'user_id': 'resubscribe-user',
            'email': 'resub@test.com',
            'stripe_customer_id': 'cus_existing_customer',
            'subscription_tier': 'free',
            'subscription_status': 'canceled',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_resub_001',
            'checkout.session.completed',
            {
                'client_reference_id': 'resubscribe-user',
                'customer': 'cus_existing_customer',  # Same customer
                'subscription': 'sub_new_subscription',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user reactivated
        user = tables['users'].get_item(Key={'user_id': 'resubscribe-user'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_subscription_id'] == 'sub_new_subscription'
        assert user['stripe_customer_id'] == 'cus_existing_customer'

    @mock_aws
    @freeze_time("2025-01-20 14:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_created_via_api(self, mock_verify):
        """
        Test subscription.created for API-created subscriptions.

        Given: User with existing customer_id, subscription created via Stripe API
        When: customer.subscription.created fires
        Then: User activated based on customer_id lookup
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed user with customer_id but no subscription
        tables['users'].put_item(Item={
            'user_id': 'api-sub-user',
            'email': 'api@test.com',
            'stripe_customer_id': 'cus_api_sub',
            'subscription_tier': 'free',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_api_sub_001',
            'customer.subscription.created',
            {
                'id': 'sub_api_created',
                'customer': 'cus_api_sub',
                'status': 'active',
                # No metadata.user_id - must look up by customer_id
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user activated via GSI lookup
        user = tables['users'].get_item(Key={'user_id': 'api-sub-user'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_subscription_id'] == 'sub_api_created'
