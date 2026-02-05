"""
Integration tests for Stripe subscription token reset.

Tests the webhook handler's ability to reset token usage when a subscription
is renewed via invoice.payment_succeeded events.

Run with: pytest tests/integration/test_stripe_token_reset.py -v -s
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
        'data': {
            'object': data_object
        }
    }


def build_api_gateway_event(body='{}', signature='test_sig'):
    """Build a mock API Gateway event for Lambda handler."""
    return {
        'body': body,
        'headers': {'stripe-signature': signature}
    }


# =============================================================================
# Test Class
# =============================================================================

class TestSubscriptionTokenReset:
    """Integration tests for Stripe subscription token reset."""

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_renewal_resets_token_usage(self, mock_verify):
        """
        Test that subscription renewal creates new billing period with reset tokens.

        Given: Plus user with 1.5M tokens used in billing period 2025-01-15
        When: invoice.payment_succeeded webhook fires with billing_reason='subscription_cycle'
        Then: New record created for 2025-02-15 with total_tokens=0, token_limit=2000000
        """
        # Setup moto tables
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed user with active Plus subscription
        tables['users'].put_item(Item={
            'user_id': 'user-renewal-test',
            'stripe_customer_id': 'cus_renewal123',
            'stripe_subscription_id': 'sub_test123',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 15,
        })

        # Seed previous billing period with high usage
        tables['token_usage'].put_item(Item={
            'user_id': 'user-renewal-test',
            'billing_period': '2025-01-15',
            'billing_day': 15,
            'total_tokens': 1500000,
            'input_tokens': 1000000,
            'output_tokens': 500000,
            'token_limit': 2000000,
            'subscription_tier': 'plus',
        })

        # Mock webhook signature verification to return parsed event
        mock_verify.return_value = build_webhook_event(
            event_id='evt_renewal_001',
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_renewal123',
                'subscription': 'sub_test123',
                'billing_reason': 'subscription_cycle',
            }
        )

        # Import and patch handler module-level tables
        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        # Execute webhook handler
        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Assert HTTP response
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body.get('status') == 'ok'

        # Verify new billing period record was created
        new_record = tables['token_usage'].get_item(
            Key={'user_id': 'user-renewal-test', 'billing_period': '2025-02-15'}
        )
        assert 'Item' in new_record, "New billing period record not created"
        item = new_record['Item']

        assert int(item['total_tokens']) == 0, "Tokens should be reset to 0"
        assert int(item['token_limit']) == 2000000, "Token limit should be 2M for Plus"
        assert item['subscription_tier'] == 'plus'
        assert int(item['billing_day']) == 15

        # Verify old record still exists (not overwritten)
        old_record = tables['token_usage'].get_item(
            Key={'user_id': 'user-renewal-test', 'billing_period': '2025-01-15'}
        )
        assert 'Item' in old_record
        assert int(old_record['Item']['total_tokens']) == 1500000

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_initial_subscription_skipped(self, mock_verify):
        """
        Test that initial subscription (not renewal) is skipped by handle_invoice_paid.

        Given: New subscription checkout
        When: invoice.payment_succeeded with billing_reason='subscription_create'
        Then: Handler returns 200, no token usage record created (handled by checkout.session.completed)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Mock webhook for initial subscription
        mock_verify.return_value = build_webhook_event(
            event_id='evt_initial_001',
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_new123',
                'subscription': 'sub_new123',
                'billing_reason': 'subscription_create',  # Initial, not renewal
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (event handled, but skipped)
        assert response['statusCode'] == 200

        # Token usage table should be empty (no record created)
        scan_result = tables['token_usage'].scan()
        assert len(scan_result.get('Items', [])) == 0, \
            "No token usage should be created for initial subscription"

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_duplicate_webhook_event_ignored(self, mock_verify):
        """
        Test that duplicate webhook events are ignored (idempotency).

        Given: Event ID already exists in stripe-events table
        When: Same event received again
        Then: Returns {"status": "already_processed"}
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        event_id = 'evt_duplicate_001'

        # Pre-populate the event as already processed
        tables['events'].put_item(Item={
            'event_id': event_id,
            'event_type': 'invoice.payment_succeeded',
            'processed_at': '2025-02-15T09:00:00Z',
        })

        # Seed user for the event
        tables['users'].put_item(Item={
            'user_id': 'user-dup-test',
            'stripe_customer_id': 'cus_dup123',
            'billing_day': 15,
        })

        mock_verify.return_value = build_webhook_event(
            event_id=event_id,  # Same ID as already processed
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_dup123',
                'subscription': 'sub_test',
                'billing_reason': 'subscription_cycle',
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

        # No token usage record should be created
        scan_result = tables['token_usage'].scan()
        assert len(scan_result.get('Items', [])) == 0

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_user_not_found_logs_error(self, mock_verify, caplog):
        """
        Test that unknown customer ID is handled gracefully.

        Given: Event with customer_id not in users table
        When: invoice.payment_succeeded fires
        Then: Handler logs error but returns 200 (to prevent Stripe retries)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Note: No user seeded - customer_id won't be found

        mock_verify.return_value = build_webhook_event(
            event_id='evt_unknown_user_001',
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_nonexistent',
                'subscription': 'sub_test',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 to prevent Stripe retries
        assert response['statusCode'] == 200

        # No token usage record created
        scan_result = tables['token_usage'].scan()
        assert len(scan_result.get('Items', [])) == 0

    @mock_aws
    @freeze_time("2025-02-28 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_february_edge_case_billing_day_31(self, mock_verify):
        """
        Test billing day adjustment for February (month with fewer than 31 days).

        Given: User with billing_day=31 (subscribed on Jan 31)
        When: Renewal on Feb 28 (Feb has only 28 days in 2025)
        Then: New billing period 2025-02-28 created (adjusted from 31)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User subscribed on the 31st
        tables['users'].put_item(Item={
            'user_id': 'user-feb-edge',
            'stripe_customer_id': 'cus_feb_edge',
            'subscription_tier': 'plus',
            'billing_day': 31,
        })

        # Previous period was Jan 31
        tables['token_usage'].put_item(Item={
            'user_id': 'user-feb-edge',
            'billing_period': '2025-01-31',
            'billing_day': 31,
            'total_tokens': 500000,
            'token_limit': 2000000,
        })

        mock_verify.return_value = build_webhook_event(
            event_id='evt_feb_edge_001',
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_feb_edge',
                'subscription': 'sub_test',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # New period should be Feb 28 (adjusted from 31)
        new_record = tables['token_usage'].get_item(
            Key={'user_id': 'user-feb-edge', 'billing_period': '2025-02-28'}
        )
        assert 'Item' in new_record, "Feb 28 billing period should exist"
        assert int(new_record['Item']['total_tokens']) == 0
        assert int(new_record['Item']['token_limit']) == 2000000

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_existing_period_record_updates_limit(self, mock_verify):
        """
        Test that existing billing period record gets token_limit updated.

        Given: Token-usage record already exists for new billing period
        When: invoice.payment_succeeded fires
        Then: ConditionalCheckFailedException caught, token_limit updated instead
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User with active subscription
        tables['users'].put_item(Item={
            'user_id': 'user-existing-record',
            'stripe_customer_id': 'cus_existing',
            'subscription_tier': 'plus',
            'billing_day': 15,
        })

        # Pre-existing record for current billing period (e.g., from a previous partial process)
        tables['token_usage'].put_item(Item={
            'user_id': 'user-existing-record',
            'billing_period': '2025-02-15',
            'billing_day': 15,
            'total_tokens': 100000,  # Some existing usage
            'token_limit': 1000000,  # Old limit (should be updated to 2M)
            'subscription_tier': 'free',  # Wrong tier (should be updated)
        })

        mock_verify.return_value = build_webhook_event(
            event_id='evt_existing_001',
            event_type='invoice.payment_succeeded',
            data_object={
                'customer': 'cus_existing',
                'subscription': 'sub_test',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify record was updated (not created new)
        record = tables['token_usage'].get_item(
            Key={'user_id': 'user-existing-record', 'billing_period': '2025-02-15'}
        )
        assert 'Item' in record
        item = record['Item']

        # Token limit should be updated to Plus tier
        assert int(item['token_limit']) == 2000000
        assert item['subscription_tier'] == 'plus'

        # Usage should be preserved (not reset) since record already existed
        # Note: The handler uses ConditionExpression on put_item and falls back to update_item
        # which only updates token_limit and subscription_tier
        assert int(item['total_tokens']) == 100000

    @mock_aws
    @freeze_time("2025-01-20 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_initializes_tokens(self, mock_verify):
        """
        Test that checkout.session.completed initializes token usage.

        Given: Free user completes checkout
        When: checkout.session.completed webhook fires
        Then: Token usage record created with Plus limits
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed free user
        tables['users'].put_item(Item={
            'user_id': 'checkout-token-init-user',
            'email': 'init@test.com',
            'subscription_tier': 'free',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_checkout_init_001',
            'checkout.session.completed',
            {
                'client_reference_id': 'checkout-token-init-user',
                'customer': 'cus_init123',
                'subscription': 'sub_init123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token usage initialized
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'checkout-token-init-user', 'billing_period': '2025-01-20'}
        )
        assert 'Item' in usage
        assert int(usage['Item']['token_limit']) == 2000000
        assert int(usage['Item']['total_tokens']) == 0
        assert usage['Item']['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_preserves_usage_history(self, mock_verify):
        """
        Test that subscription.deleted preserves historical token usage.

        Given: Plus user with token usage history
        When: customer.subscription.deleted fires
        Then: Historical token usage records are NOT deleted
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user with history
        tables['users'].put_item(Item={
            'user_id': 'history-preserve-user',
            'stripe_customer_id': 'cus_history',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        # Create historical usage records
        tables['token_usage'].put_item(Item={
            'user_id': 'history-preserve-user',
            'billing_period': '2024-12-20',
            'total_tokens': 1800000,
            'token_limit': 2000000,
        })
        tables['token_usage'].put_item(Item={
            'user_id': 'history-preserve-user',
            'billing_period': '2025-01-20',
            'total_tokens': 500000,
            'token_limit': 2000000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_preserve_001',
            'customer.subscription.deleted',
            {
                'id': 'sub_preserve',
                'customer': 'cus_history',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user downgraded
        user = tables['users'].get_item(Key={'user_id': 'history-preserve-user'})['Item']
        assert user['subscription_tier'] == 'free'

        # Verify ALL historical usage records still exist
        dec_usage = tables['token_usage'].get_item(
            Key={'user_id': 'history-preserve-user', 'billing_period': '2024-12-20'}
        )
        assert 'Item' in dec_usage
        assert int(dec_usage['Item']['total_tokens']) == 1800000

        jan_usage = tables['token_usage'].get_item(
            Key={'user_id': 'history-preserve-user', 'billing_period': '2025-01-20'}
        )
        assert 'Item' in jan_usage
        assert int(jan_usage['Item']['total_tokens']) == 500000

    @mock_aws
    @freeze_time("2025-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_failed_payment_does_not_reset_tokens(self, mock_verify):
        """
        Test that invoice.payment_failed does NOT reset token usage.

        Given: Plus user with 1M tokens used
        When: invoice.payment_failed fires
        Then: Token usage is NOT reset (user retains access during grace period)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'failed-no-reset-user',
            'stripe_customer_id': 'cus_failed_no_reset',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 15,
        })

        # Current period with significant usage
        tables['token_usage'].put_item(Item={
            'user_id': 'failed-no-reset-user',
            'billing_period': '2025-02-15',
            'total_tokens': 1000000,
            'token_limit': 2000000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_no_reset_001',
            'invoice.payment_failed',
            {
                'subscription': 'sub_failed',
                'customer': 'cus_failed_no_reset',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify status updated to past_due
        user = tables['users'].get_item(Key={'user_id': 'failed-no-reset-user'})['Item']
        assert user['subscription_status'] == 'past_due'

        # Verify token usage NOT reset
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'failed-no-reset-user', 'billing_period': '2025-02-15'}
        )
        assert int(usage['Item']['total_tokens']) == 1000000  # Still 1M

    @mock_aws
    @freeze_time("2025-03-10 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_multiple_billing_periods_isolated(self, mock_verify):
        """
        Test that multiple billing periods are properly isolated.

        Given: Plus user with multiple billing period records
        When: Renewal creates new period
        Then: New period has 0 tokens, old periods unchanged
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Seed Plus user
        tables['users'].put_item(Item={
            'user_id': 'multi-period-user',
            'stripe_customer_id': 'cus_multi_period',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 10,
        })

        # Create multiple historical periods
        tables['token_usage'].put_item(Item={
            'user_id': 'multi-period-user',
            'billing_period': '2025-01-10',
            'total_tokens': 1500000,
            'token_limit': 2000000,
        })
        tables['token_usage'].put_item(Item={
            'user_id': 'multi-period-user',
            'billing_period': '2025-02-10',
            'total_tokens': 1800000,
            'token_limit': 2000000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_multi_period_001',
            'invoice.payment_succeeded',
            {
                'customer': 'cus_multi_period',
                'subscription': 'sub_multi',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify new period created with 0 tokens
        new_usage = tables['token_usage'].get_item(
            Key={'user_id': 'multi-period-user', 'billing_period': '2025-03-10'}
        )
        assert 'Item' in new_usage
        assert int(new_usage['Item']['total_tokens']) == 0
        assert int(new_usage['Item']['token_limit']) == 2000000

        # Verify old periods unchanged
        jan_usage = tables['token_usage'].get_item(
            Key={'user_id': 'multi-period-user', 'billing_period': '2025-01-10'}
        )
        assert int(jan_usage['Item']['total_tokens']) == 1500000

        feb_usage = tables['token_usage'].get_item(
            Key={'user_id': 'multi-period-user', 'billing_period': '2025-02-10'}
        )
        assert int(feb_usage['Item']['total_tokens']) == 1800000
