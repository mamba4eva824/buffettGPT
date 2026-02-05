"""
Unit tests for Stripe webhook handler.

Tests all webhook event handlers including:
- Signature verification
- Event routing
- Idempotency
- checkout.session.completed
- customer.subscription.created
- customer.subscription.deleted
- customer.subscription.updated
- invoice.payment_failed

Run with: pytest tests/unit/test_stripe_webhook_handler.py -v
"""

import json
import os
import sys
import pytest
import boto3
from moto import mock_aws
from freezegun import freeze_time
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any handler imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['TOKEN_USAGE_TABLE'] = 'buffett-test-token-usage'
os.environ['PROCESSED_EVENTS_TABLE'] = 'buffett-test-stripe-events'
os.environ['TOKEN_LIMIT_PLUS'] = '2000000'


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


def build_api_gateway_event(body='{}', signature='test_sig', headers=None):
    """Build a mock API Gateway event for Lambda handler."""
    if headers is None:
        headers = {'stripe-signature': signature}
    return {
        'body': body,
        'headers': headers
    }


# =============================================================================
# Test Class: Signature Verification
# =============================================================================

class TestSignatureVerification:
    """Tests for webhook signature verification."""

    @mock_aws
    def test_missing_signature_header_returns_400(self):
        """
        Test that missing Stripe-Signature header returns 400.

        Given: A webhook request without Stripe-Signature header
        When: Handler is invoked
        Then: Returns 400 with error message
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        import handlers.stripe_webhook_handler as handler

        # No signature header
        event = build_api_gateway_event(headers={})
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Missing signature header' in body.get('error', '')

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invalid_signature_returns_400(self, mock_verify):
        """
        Test that invalid signature returns 400.

        Given: A webhook request with invalid signature
        When: verify_webhook_signature raises ValueError
        Then: Returns 400 with error message
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        mock_verify.side_effect = ValueError("Invalid webhook signature")

        import handlers.stripe_webhook_handler as handler

        event = build_api_gateway_event(signature='invalid_sig')
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Invalid webhook signature' in body.get('error', '')

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_signature_header_case_insensitive(self, mock_verify):
        """
        Test that signature header lookup is case-insensitive.

        Given: A webhook request with lowercase 'stripe-signature' header
        When: Handler is invoked
        Then: Signature is extracted and verified
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_test', 'unknown.event', {}
        )

        import handlers.stripe_webhook_handler as handler
        handler.processed_events_table = tables['events']

        # Lowercase header (as API Gateway may send)
        event = build_api_gateway_event(headers={'stripe-signature': 'test_sig'})
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        mock_verify.assert_called_once()

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_valid_signature_proceeds_to_handler(self, mock_verify):
        """
        Test that valid signature allows processing to continue.

        Given: A webhook request with valid signature
        When: Handler is invoked
        Then: Returns 200 and processes event
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_valid', 'checkout.session.completed',
            {'client_reference_id': 'user-123', 'customer': 'cus_123', 'subscription': 'sub_123'}
        )

        # Create user for the checkout
        tables['users'].put_item(Item={'user_id': 'user-123', 'email': 'test@test.com'})

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        event = build_api_gateway_event()
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        mock_verify.assert_called_once()


# =============================================================================
# Test Class: Event Routing
# =============================================================================

class TestEventRouting:
    """Tests for webhook event routing."""

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_unknown_event_type_returns_200(self, mock_verify):
        """
        Test that unhandled event types return 200 (silent success).

        Given: A webhook with unknown event type
        When: Handler is invoked
        Then: Returns 200 with status 'ok'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_unknown', 'some.unknown.event', {}
        )

        import handlers.stripe_webhook_handler as handler
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'ok'

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_handler_exception_returns_500(self, mock_verify):
        """
        Test that handler exceptions return 500 (Stripe will retry).

        Given: A webhook that causes a handler to raise an exception
        When: Handler is invoked
        Then: Returns 500 with error
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # checkout.session.completed with missing user should raise
        mock_verify.return_value = build_webhook_event(
            'evt_error', 'checkout.session.completed',
            {'client_reference_id': 'nonexistent-user', 'customer': 'cus_123', 'subscription': 'sub_123'}
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'error' in body

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_event_routed_to_correct_handler(self, mock_verify):
        """
        Test that events are routed to their designated handlers.

        Given: Webhooks for known event types
        When: Handler is invoked
        Then: Each event type routes to correct handler
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Test routing of subscription.deleted (a simpler handler)
        tables['users'].put_item(Item={
            'user_id': 'user-route-test',
            'stripe_customer_id': 'cus_route123',
            'subscription_tier': 'plus',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_route', 'customer.subscription.deleted',
            {'id': 'sub_123', 'customer': 'cus_route123'}
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify user was downgraded (proves correct handler was called)
        user = tables['users'].get_item(Key={'user_id': 'user-route-test'})
        assert user['Item']['subscription_tier'] == 'free'


# =============================================================================
# Test Class: Idempotency
# =============================================================================

class TestIdempotency:
    """Tests for webhook idempotency tracking."""

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_duplicate_event_returns_already_processed(self, mock_verify):
        """
        Test that duplicate events return already_processed status.

        Given: Event ID already exists in processed events table
        When: Same event received again
        Then: Returns 200 with status 'already_processed'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        event_id = 'evt_dup_test'

        # Pre-populate the event as already processed
        tables['events'].put_item(Item={
            'event_id': event_id,
            'event_type': 'checkout.session.completed',
            'processed_at': '2025-01-15T10:00:00Z',
        })

        mock_verify.return_value = build_webhook_event(
            event_id, 'checkout.session.completed',
            {'client_reference_id': 'user-123'}
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['status'] == 'already_processed'

    @mock_aws
    @freeze_time("2025-01-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_event_marked_processed_after_success(self, mock_verify):
        """
        Test that event is marked as processed after successful handling.

        Given: A new webhook event
        When: Handler processes it successfully
        Then: Event ID is stored in processed events table
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        event_id = 'evt_new_001'
        tables['users'].put_item(Item={
            'user_id': 'user-mark-test',
            'stripe_customer_id': 'cus_mark123',
        })

        mock_verify.return_value = build_webhook_event(
            event_id, 'customer.subscription.deleted',
            {'id': 'sub_123', 'customer': 'cus_mark123'}
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify event was marked as processed
        event_record = tables['events'].get_item(Key={'event_id': event_id})
        assert 'Item' in event_record
        assert event_record['Item']['event_type'] == 'customer.subscription.deleted'

    @mock_aws
    @freeze_time("2025-01-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_processed_event_has_ttl(self, mock_verify):
        """
        Test that processed event record includes TTL for 7-day expiration.

        Given: A webhook event is processed
        When: Event is marked as processed
        Then: Record includes TTL attribute set to 7 days from now
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        event_id = 'evt_ttl_001'
        tables['users'].put_item(Item={
            'user_id': 'user-ttl-test',
            'stripe_customer_id': 'cus_ttl123',
        })

        mock_verify.return_value = build_webhook_event(
            event_id, 'customer.subscription.deleted',
            {'id': 'sub_123', 'customer': 'cus_ttl123'}
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        handler.lambda_handler(build_api_gateway_event(), None)

        # Verify TTL was set
        event_record = tables['events'].get_item(Key={'event_id': event_id})
        assert 'Item' in event_record
        assert 'ttl' in event_record['Item']

        # TTL should be approximately 7 days from frozen time
        expected_ttl = int(datetime(2025, 1, 15, 10, 0, 0, tzinfo=timezone.utc).timestamp()) + (7 * 24 * 60 * 60)
        assert int(event_record['Item']['ttl']) == expected_ttl


# =============================================================================
# Test Class: handle_checkout_completed
# =============================================================================

class TestHandleCheckoutCompleted:
    """Tests for checkout.session.completed webhook handler."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_creates_plus_subscription(self, mock_verify):
        """
        Test that checkout.session.completed upgrades user to Plus.

        Given: Existing user completes checkout
        When: checkout.session.completed webhook fires
        Then: User updated with subscription_tier='plus', subscription_status='active'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-checkout',
            'email': 'test@example.com',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_checkout_001', 'checkout.session.completed',
            {
                'client_reference_id': 'user-checkout',
                'customer': 'cus_checkout123',
                'subscription': 'sub_checkout123',
                'customer_email': 'test@example.com',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'user-checkout'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_customer_id'] == 'cus_checkout123'
        assert user['stripe_subscription_id'] == 'sub_checkout123'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_sets_billing_day(self, mock_verify):
        """
        Test that billing_day is set to current day of month.

        Given: User completes checkout on the 20th
        When: checkout.session.completed fires
        Then: billing_day is set to 20
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={'user_id': 'user-billing-day'})

        mock_verify.return_value = build_webhook_event(
            'evt_billing_day', 'checkout.session.completed',
            {
                'client_reference_id': 'user-billing-day',
                'customer': 'cus_123',
                'subscription': 'sub_123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        handler.lambda_handler(build_api_gateway_event(), None)

        user = tables['users'].get_item(Key={'user_id': 'user-billing-day'})['Item']
        assert int(user['billing_day']) == 20

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_initializes_token_usage(self, mock_verify):
        """
        Test that token usage record is created with Plus limits.

        Given: User completes checkout
        When: checkout.session.completed fires
        Then: Token usage record created with token_limit=2000000, total_tokens=0
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={'user_id': 'user-token-init'})

        mock_verify.return_value = build_webhook_event(
            'evt_token_init', 'checkout.session.completed',
            {
                'client_reference_id': 'user-token-init',
                'customer': 'cus_123',
                'subscription': 'sub_123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        handler.lambda_handler(build_api_gateway_event(), None)

        # Token usage should be initialized
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-token-init', 'billing_period': '2025-01-20'}
        )
        assert 'Item' in usage
        assert int(usage['Item']['token_limit']) == 2000000
        assert int(usage['Item']['total_tokens']) == 0
        assert usage['Item']['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_uses_client_reference_id(self, mock_verify):
        """
        Test that user_id is extracted from client_reference_id.

        Given: Checkout session with client_reference_id set
        When: checkout.session.completed fires
        Then: Correct user is updated
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={'user_id': 'client-ref-user'})

        mock_verify.return_value = build_webhook_event(
            'evt_client_ref', 'checkout.session.completed',
            {
                'client_reference_id': 'client-ref-user',
                'customer': 'cus_123',
                'subscription': 'sub_123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'client-ref-user'})['Item']
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_uses_metadata_user_id(self, mock_verify):
        """
        Test fallback to metadata.user_id when client_reference_id is missing.

        Given: Checkout session with user_id in metadata only
        When: checkout.session.completed fires
        Then: Correct user is updated from metadata
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={'user_id': 'metadata-user'})

        mock_verify.return_value = build_webhook_event(
            'evt_metadata', 'checkout.session.completed',
            {
                # No client_reference_id
                'customer': 'cus_123',
                'subscription': 'sub_123',
                'metadata': {'user_id': 'metadata-user'},
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'metadata-user'})['Item']
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_user_not_found_raises(self, mock_verify):
        """
        Test that missing user raises error (triggers Stripe retry).

        Given: Checkout session with user_id that doesn't exist
        When: checkout.session.completed fires
        Then: Handler raises ValueError (returns 500)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # No user created

        mock_verify.return_value = build_webhook_event(
            'evt_no_user', 'checkout.session.completed',
            {
                'client_reference_id': 'nonexistent-user',
                'customer': 'cus_123',
                'subscription': 'sub_123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 500 to trigger Stripe retry
        assert response['statusCode'] == 500

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_no_user_id_skips(self, mock_verify):
        """
        Test that checkout without user_id is skipped gracefully.

        Given: Checkout session with no user_id anywhere
        When: checkout.session.completed fires
        Then: Handler returns 200 (no error, but no action)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_no_id', 'checkout.session.completed',
            {
                # No client_reference_id, no metadata.user_id
                'customer': 'cus_123',
                'subscription': 'sub_123',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (handled but skipped)
        assert response['statusCode'] == 200


# =============================================================================
# Test Class: handle_subscription_created
# =============================================================================

class TestHandleSubscriptionCreated:
    """Tests for customer.subscription.created webhook handler."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_created_activates_user(self, mock_verify):
        """
        Test that subscription.created activates the user subscription.

        Given: Subscription created via API with user_id in metadata
        When: customer.subscription.created fires
        Then: User updated with subscription details
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={'user_id': 'user-sub-created'})

        mock_verify.return_value = build_webhook_event(
            'evt_sub_created', 'customer.subscription.created',
            {
                'id': 'sub_created_123',
                'customer': 'cus_created_123',
                'status': 'active',
                'metadata': {'user_id': 'user-sub-created'},
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'user-sub-created'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'
        assert user['stripe_subscription_id'] == 'sub_created_123'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_created_finds_user_by_customer_id(self, mock_verify):
        """
        Test fallback to GSI lookup when metadata.user_id is missing.

        Given: Subscription created without user_id metadata
        When: customer.subscription.created fires
        Then: User found by stripe_customer_id GSI
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User with existing customer_id
        tables['users'].put_item(Item={
            'user_id': 'user-gsi-lookup',
            'stripe_customer_id': 'cus_gsi_123',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_gsi_lookup', 'customer.subscription.created',
            {
                'id': 'sub_gsi_123',
                'customer': 'cus_gsi_123',
                'status': 'active',
                # No metadata.user_id
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'user-gsi-lookup'})['Item']
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_created_no_user_id_skips(self, mock_verify):
        """
        Test that subscription.created skips if no user found.

        Given: Subscription created with unknown customer
        When: customer.subscription.created fires
        Then: Handler returns 200 (skipped)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_no_user_sub', 'customer.subscription.created',
            {
                'id': 'sub_orphan',
                'customer': 'cus_unknown',
                'status': 'active',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (skipped, not error)
        assert response['statusCode'] == 200

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_created_user_not_found_raises(self, mock_verify):
        """
        Test that subscription.created raises if user_id found but user doesn't exist.

        Given: Subscription with user_id in metadata but user deleted
        When: customer.subscription.created fires
        Then: Handler raises ValueError (returns 500)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Create user then query will return it but get_item won't
        # Actually we need the user to NOT exist but metadata has user_id
        mock_verify.return_value = build_webhook_event(
            'evt_deleted_user', 'customer.subscription.created',
            {
                'id': 'sub_deleted',
                'customer': 'cus_deleted',
                'status': 'active',
                'metadata': {'user_id': 'deleted-user'},
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 500 (user not found raises)
        assert response['statusCode'] == 500


# =============================================================================
# Test Class: handle_subscription_deleted
# =============================================================================

class TestHandleSubscriptionDeleted:
    """Tests for customer.subscription.deleted webhook handler."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_downgrades_to_free(self, mock_verify):
        """
        Test that subscription.deleted downgrades user to free tier.

        Given: Plus user with active subscription
        When: customer.subscription.deleted fires
        Then: User updated with subscription_tier='free', subscription_status='canceled'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-downgrade',
            'stripe_customer_id': 'cus_downgrade',
            'stripe_subscription_id': 'sub_downgrade',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_downgrade', 'customer.subscription.deleted',
            {
                'id': 'sub_downgrade',
                'customer': 'cus_downgrade',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'user-downgrade'})['Item']
        assert user['subscription_tier'] == 'free'
        assert user['subscription_status'] == 'canceled'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_removes_subscription_id(self, mock_verify):
        """
        Test that subscription.deleted removes stripe_subscription_id.

        Given: User with stripe_subscription_id
        When: customer.subscription.deleted fires
        Then: stripe_subscription_id attribute is removed
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-remove-sub-id',
            'stripe_customer_id': 'cus_remove',
            'stripe_subscription_id': 'sub_to_remove',
            'subscription_tier': 'plus',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_remove_sub', 'customer.subscription.deleted',
            {
                'id': 'sub_to_remove',
                'customer': 'cus_remove',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        handler.lambda_handler(build_api_gateway_event(), None)

        user = tables['users'].get_item(Key={'user_id': 'user-remove-sub-id'})['Item']
        assert 'stripe_subscription_id' not in user

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_user_not_found_logs(self, mock_verify):
        """
        Test that subscription.deleted handles missing user gracefully.

        Given: Subscription deletion for unknown customer
        When: customer.subscription.deleted fires
        Then: Returns 200 (logs error but doesn't raise)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_no_user_delete', 'customer.subscription.deleted',
            {
                'id': 'sub_orphan',
                'customer': 'cus_unknown',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (handled gracefully)
        assert response['statusCode'] == 200


# =============================================================================
# Test Class: handle_subscription_updated
# =============================================================================

class TestHandleSubscriptionUpdated:
    """Tests for customer.subscription.updated webhook handler."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_status_change(self, mock_verify):
        """
        Test that subscription.updated syncs status changes.

        Given: User with active subscription
        When: subscription.updated fires with status='past_due'
        Then: User subscription_status updated to 'past_due'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-status-update',
            'stripe_customer_id': 'cus_status',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_status_change', 'customer.subscription.updated',
            {
                'id': 'sub_status',
                'customer': 'cus_status',
                'status': 'past_due',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'user-status-update'})['Item']
        assert user['subscription_status'] == 'past_due'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_cancel_at_period_end(self, mock_verify):
        """
        Test that cancel_at_period_end flag is synced.

        Given: User with active subscription
        When: subscription.updated fires with cancel_at_period_end=True
        Then: User cancel_at_period_end updated to True
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-cancel-end',
            'stripe_customer_id': 'cus_cancel_end',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'cancel_at_period_end': False,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_cancel_end', 'customer.subscription.updated',
            {
                'id': 'sub_cancel_end',
                'customer': 'cus_cancel_end',
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
        user = tables['users'].get_item(Key={'user_id': 'user-cancel-end'})['Item']
        assert user['cancel_at_period_end'] is True

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_user_not_found_logs(self, mock_verify):
        """
        Test that subscription.updated handles missing user gracefully.

        Given: Subscription update for unknown customer
        When: customer.subscription.updated fires
        Then: Returns 200 (logs error but doesn't raise)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_update_no_user', 'customer.subscription.updated',
            {
                'id': 'sub_orphan',
                'customer': 'cus_unknown',
                'status': 'active',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (handled gracefully)
        assert response['statusCode'] == 200


# =============================================================================
# Test Class: handle_invoice_failed
# =============================================================================

class TestHandleInvoiceFailed:
    """Tests for invoice.payment_failed webhook handler."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_failed_sets_past_due(self, mock_verify):
        """
        Test that invoice.payment_failed sets status to past_due.

        Given: User with active subscription
        When: invoice.payment_failed fires
        Then: User subscription_status updated to 'past_due', payment_failed_at set
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-failed-payment',
            'stripe_customer_id': 'cus_failed',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_failed', 'invoice.payment_failed',
            {
                'subscription': 'sub_failed',
                'customer': 'cus_failed',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        user = tables['users'].get_item(Key={'user_id': 'user-failed-payment'})['Item']
        assert user['subscription_status'] == 'past_due'
        assert 'payment_failed_at' in user

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_failed_non_subscription_skipped(self, mock_verify):
        """
        Test that invoice.payment_failed without subscription is skipped.

        Given: Failed invoice without subscription_id
        When: invoice.payment_failed fires
        Then: Handler returns 200 (skipped)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_no_sub_failed', 'invoice.payment_failed',
            {
                # No subscription_id
                'customer': 'cus_one_time',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (skipped)
        assert response['statusCode'] == 200


# =============================================================================
# Test Class: Tier Sync Tests (AC-1 through AC-7)
# =============================================================================

class TestSubscriptionTierSync:
    """Tests for subscription tier synchronization to both tables."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_active_syncs_tier_to_both_tables(self, mock_verify):
        """
        AC-1: subscription.updated with status=active syncs tier to both tables.

        Given: A subscription.updated webhook with status=active
        When: Handler processes the event
        Then: User's subscription_tier is set to 'plus' in BOTH users and token-usage tables
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # Create user with existing billing_day (simulating prior subscription)
        tables['users'].put_item(Item={
            'user_id': 'user-tier-sync-active',
            'stripe_customer_id': 'cus_tier_active',
            'subscription_tier': 'free',  # Currently free
            'subscription_status': 'incomplete',
            'billing_day': 20,
        })

        # Create existing token-usage record
        tables['token_usage'].put_item(Item={
            'user_id': 'user-tier-sync-active',
            'billing_period': '2025-01-20',
            'subscription_tier': 'free',
            'total_tokens': 1000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_tier_active', 'customer.subscription.updated',
            {
                'id': 'sub_tier_active',
                'customer': 'cus_tier_active',
                'status': 'active',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table
        user = tables['users'].get_item(Key={'user_id': 'user-tier-sync-active'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['subscription_status'] == 'active'

        # Verify token-usage table
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-tier-sync-active', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_canceled_syncs_tier_to_both_tables(self, mock_verify):
        """
        AC-3: subscription.updated with status=canceled syncs tier to both tables.

        Given: A subscription.updated webhook with status=canceled
        When: Handler processes the event
        Then: User's subscription_tier is set to 'free' in BOTH tables
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-tier-cancel',
            'stripe_customer_id': 'cus_tier_cancel',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-tier-cancel',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'total_tokens': 5000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_tier_cancel', 'customer.subscription.updated',
            {
                'id': 'sub_tier_cancel',
                'customer': 'cus_tier_cancel',
                'status': 'canceled',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table
        user = tables['users'].get_item(Key={'user_id': 'user-tier-cancel'})['Item']
        assert user['subscription_tier'] == 'free'

        # Verify token-usage table
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-tier-cancel', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_past_due_preserves_tier(self, mock_verify):
        """
        AC-4: past_due status preserves tier (grace period).

        Given: A subscription.updated webhook with status=past_due
        When: Handler processes the event
        Then: User's subscription_tier remains 'plus' (no tier change to either table)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-tier-pastdue',
            'stripe_customer_id': 'cus_tier_pastdue',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-tier-pastdue',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'total_tokens': 3000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_tier_pastdue', 'customer.subscription.updated',
            {
                'id': 'sub_tier_pastdue',
                'customer': 'cus_tier_pastdue',
                'status': 'past_due',  # Grace period status
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table - tier should be unchanged
        user = tables['users'].get_item(Key={'user_id': 'user-tier-pastdue'})['Item']
        assert user['subscription_tier'] == 'plus'  # Unchanged
        assert user['subscription_status'] == 'past_due'  # Status updated

        # Verify token-usage table - tier should be unchanged
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-tier-pastdue', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'plus'  # Unchanged

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_cancel_at_period_end_preserves_tier(self, mock_verify):
        """
        AC-5: cancel_at_period_end=true preserves tier.

        Given: A subscription.updated webhook with cancel_at_period_end=true and status=active
        When: Handler processes the event
        Then: User's subscription_tier remains 'plus' (until actual deletion)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-tier-cancelend',
            'stripe_customer_id': 'cus_tier_cancelend',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-tier-cancelend',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'total_tokens': 2000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_tier_cancelend', 'customer.subscription.updated',
            {
                'id': 'sub_tier_cancelend',
                'customer': 'cus_tier_cancelend',
                'status': 'active',  # Still active
                'cancel_at_period_end': True,  # Scheduled to cancel
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table - tier should be plus (active status)
        user = tables['users'].get_item(Key={'user_id': 'user-tier-cancelend'})['Item']
        assert user['subscription_tier'] == 'plus'
        assert user['cancel_at_period_end'] is True

        # Verify token-usage table - tier unchanged
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-tier-cancelend', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_trialing_sets_tier_plus(self, mock_verify):
        """
        Test that trialing status sets tier to plus.

        Given: A subscription.updated webhook with status=trialing
        When: Handler processes the event
        Then: User's subscription_tier is set to 'plus'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-tier-trial',
            'stripe_customer_id': 'cus_tier_trial',
            'subscription_tier': 'free',
            'subscription_status': 'incomplete',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-tier-trial',
            'billing_period': '2025-01-20',
            'subscription_tier': 'free',
            'total_tokens': 0,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_tier_trial', 'customer.subscription.updated',
            {
                'id': 'sub_tier_trial',
                'customer': 'cus_tier_trial',
                'status': 'trialing',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table
        user = tables['users'].get_item(Key={'user_id': 'user-tier-trial'})['Item']
        assert user['subscription_tier'] == 'plus'

        # Verify token-usage table
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-tier-trial', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_sync_tier_no_token_usage_record_succeeds(self, mock_verify):
        """
        AC-6/AC-7: Token-usage sync succeeds even when no record exists.

        Given: User without existing token-usage record
        When: subscription.updated fires with status=active
        Then: Users table updated, no error (token-usage sync is best-effort)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User exists but NO token-usage record
        tables['users'].put_item(Item={
            'user_id': 'user-no-usage',
            'stripe_customer_id': 'cus_no_usage',
            'subscription_tier': 'free',
            'subscription_status': 'incomplete',
            'billing_day': 20,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_no_usage', 'customer.subscription.updated',
            {
                'id': 'sub_no_usage',
                'customer': 'cus_no_usage',
                'status': 'active',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should succeed (200) even without token-usage record
        assert response['statusCode'] == 200

        # Verify users table updated correctly
        user = tables['users'].get_item(Key={'user_id': 'user-no-usage'})['Item']
        assert user['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_syncs_tier_to_token_usage(self, mock_verify):
        """
        Test that subscription.deleted syncs tier='free' to token-usage table.

        Given: Plus user with token-usage record
        When: customer.subscription.deleted fires
        Then: Both users and token-usage tables updated to tier='free'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-deleted-sync',
            'stripe_customer_id': 'cus_deleted_sync',
            'stripe_subscription_id': 'sub_deleted_sync',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-deleted-sync',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'total_tokens': 10000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_deleted_sync', 'customer.subscription.deleted',
            {
                'id': 'sub_deleted_sync',
                'customer': 'cus_deleted_sync',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify users table
        user = tables['users'].get_item(Key={'user_id': 'user-deleted-sync'})['Item']
        assert user['subscription_tier'] == 'free'

        # Verify token-usage table
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-deleted-sync', 'billing_period': '2025-01-20'}
        )['Item']
        assert usage['subscription_tier'] == 'free'


# =============================================================================
# Test Class: Helper Function Tests
# =============================================================================

class TestBillingPeriodHelper:
    """Tests for _get_current_billing_period helper function."""

    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    def test_billing_period_same_day(self):
        """
        Test billing period when current day equals billing day.

        Given: Today is the 20th, billing_day is 20
        When: _get_current_billing_period is called
        Then: Returns current month's billing date (2025-01-20)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(20)
        assert period == '2025-01-20'

    @freeze_time("2025-01-25 14:30:00", tz_offset=0)
    def test_billing_period_after_billing_day(self):
        """
        Test billing period when current day is after billing day.

        Given: Today is the 25th, billing_day is 15
        When: _get_current_billing_period is called
        Then: Returns current month's billing date (2025-01-15)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(15)
        assert period == '2025-01-15'

    @freeze_time("2025-01-10 14:30:00", tz_offset=0)
    def test_billing_period_before_billing_day(self):
        """
        Test billing period when current day is before billing day.

        Given: Today is the 10th, billing_day is 20
        When: _get_current_billing_period is called
        Then: Returns previous month's billing date (2024-12-20)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(20)
        assert period == '2024-12-20'

    @freeze_time("2025-02-15 14:30:00", tz_offset=0)
    def test_billing_period_february_edge_case(self):
        """
        Test billing period calculation in February with day > 28.

        Given: Today is Feb 15, billing_day is 31
        When: _get_current_billing_period is called
        Then: Returns previous month with clamped day (2025-01-31)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(31)
        # Feb 15 is before the effective billing day (Feb 28), so period started Jan 31
        assert period == '2025-01-31'

    @freeze_time("2025-03-01 14:30:00", tz_offset=0)
    def test_billing_period_month_boundary(self):
        """
        Test billing period at month boundary.

        Given: Today is March 1, billing_day is 15
        When: _get_current_billing_period is called
        Then: Returns previous month's billing date (2025-02-15)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(15)
        assert period == '2025-02-15'

    @freeze_time("2025-01-01 00:00:00", tz_offset=0)
    def test_billing_period_year_boundary(self):
        """
        Test billing period at year boundary.

        Given: Today is Jan 1, billing_day is 15
        When: _get_current_billing_period is called
        Then: Returns previous year's December billing date (2024-12-15)
        """
        import handlers.stripe_webhook_handler as handler
        period = handler._get_current_billing_period(15)
        assert period == '2024-12-15'


# =============================================================================
# Test Class: Token Limit Sync Tests (BUG-1 through BUG-5)
# =============================================================================

class TestTokenLimitSync:
    """Tests for token_limit synchronization during tier changes."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_deleted_resets_token_limit_to_free(self, mock_verify):
        """
        BUG-1: subscription.deleted should reset token_limit to 100,000.

        Given: Plus user with token_limit=2,000,000
        When: customer.subscription.deleted fires
        Then: token_limit is updated to 100,000 (TOKEN_LIMIT_FREE)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-token-reset',
            'stripe_customer_id': 'cus_token_reset',
            'stripe_subscription_id': 'sub_token_reset',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-token-reset',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'input_tokens': 50000,
            'output_tokens': 10000,
            'total_tokens': 60000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_token_reset', 'customer.subscription.deleted',
            {
                'id': 'sub_token_reset',
                'customer': 'cus_token_reset',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token_limit reset to FREE limit
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-token-reset', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000
        assert usage['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_checkout_completed_sets_token_limit_to_plus(self, mock_verify):
        """
        BUG-2: checkout.session.completed should set token_limit to 2,000,000.

        Given: Free user with token_limit=100,000
        When: checkout.session.completed fires
        Then: token_limit is updated to 2,000,000 (TOKEN_LIMIT_PLUS)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-upgrade-limit',
            'email': 'test@example.com',
            'subscription_tier': 'free',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_upgrade_limit', 'checkout.session.completed',
            {
                'client_reference_id': 'user-upgrade-limit',
                'customer': 'cus_upgrade_limit',
                'subscription': 'sub_upgrade_limit',
                'customer_email': 'test@example.com',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token_limit set to PLUS limit
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-upgrade-limit', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 2000000
        assert usage['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_to_free_resets_token_limit(self, mock_verify):
        """
        BUG-1 (via subscription.updated): status=canceled should reset token_limit.

        Given: Plus user with token_limit=2,000,000
        When: subscription.updated fires with status=canceled
        Then: token_limit is updated to 100,000
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-updated-cancel',
            'stripe_customer_id': 'cus_updated_cancel',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-updated-cancel',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 25000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_updated_cancel', 'customer.subscription.updated',
            {
                'id': 'sub_updated_cancel',
                'customer': 'cus_updated_cancel',
                'status': 'canceled',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token_limit reset to FREE limit
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-updated-cancel', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 100000
        assert usage['subscription_tier'] == 'free'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_subscription_updated_to_active_sets_plus_limit(self, mock_verify):
        """
        BUG-2 (via subscription.updated): status=active should set token_limit to 2,000,000.

        Given: Free user with token_limit=100,000
        When: subscription.updated fires with status=active
        Then: token_limit is updated to 2,000,000
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-updated-active',
            'stripe_customer_id': 'cus_updated_active',
            'subscription_tier': 'free',
            'subscription_status': 'incomplete',
            'billing_day': 20,
        })

        tables['token_usage'].put_item(Item={
            'user_id': 'user-updated-active',
            'billing_period': '2025-01-20',
            'subscription_tier': 'free',
            'token_limit': 100000,
            'total_tokens': 5000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_updated_active', 'customer.subscription.updated',
            {
                'id': 'sub_updated_active',
                'customer': 'cus_updated_active',
                'status': 'active',
                'cancel_at_period_end': False,
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify token_limit set to PLUS limit
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-updated-active', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['token_limit']) == 2000000
        assert usage['subscription_tier'] == 'plus'

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_downgrade_preserves_used_tokens(self, mock_verify):
        """
        BUG-5: Used tokens should be preserved on downgrade (only limit changes).

        Given: User has used 150,000 tokens (over free limit)
        When: subscription.deleted fires
        Then: input_tokens, output_tokens, total_tokens unchanged, only token_limit changes
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-preserve-tokens',
            'stripe_customer_id': 'cus_preserve',
            'stripe_subscription_id': 'sub_preserve',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        # User has used 150,000 tokens (over free limit of 100,000)
        tables['token_usage'].put_item(Item={
            'user_id': 'user-preserve-tokens',
            'billing_period': '2025-01-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'input_tokens': 120000,
            'output_tokens': 30000,
            'total_tokens': 150000,
            'request_count': 50,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_preserve', 'customer.subscription.deleted',
            {
                'id': 'sub_preserve',
                'customer': 'cus_preserve',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # Verify used tokens preserved, only limit and tier changed
        usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-preserve-tokens', 'billing_period': '2025-01-20'}
        )['Item']
        assert int(usage['input_tokens']) == 120000  # Unchanged
        assert int(usage['output_tokens']) == 30000  # Unchanged
        assert int(usage['total_tokens']) == 150000  # Unchanged
        assert int(usage['request_count']) == 50  # Unchanged
        assert int(usage['token_limit']) == 100000  # Changed to free limit
        assert usage['subscription_tier'] == 'free'  # Changed to free

# =============================================================================
# Test Class: Invoice Payment Succeeded Edge Cases (AC-P2-1)
# =============================================================================

class TestInvoicePaymentSucceededEdgeCases:
    """Tests for invoice.payment_succeeded edge cases."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_paid_subscription_create_skipped(self, mock_verify):
        """
        P2-1.x: Initial subscription invoice is skipped (handled by checkout).

        Given: Invoice with billing_reason='subscription_create'
        When: invoice.payment_succeeded fires
        Then: Handler returns 200 (skipped, no user update)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-initial-invoice',
            'stripe_customer_id': 'cus_initial',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_initial_invoice', 'invoice.payment_succeeded',
            {
                'subscription': 'sub_initial',
                'customer': 'cus_initial',
                'billing_reason': 'subscription_create',  # Initial subscription
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200
        # No token usage record should be created (skipped)
        usage_items = tables['token_usage'].scan()['Items']
        assert len(usage_items) == 0

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_paid_renewal_creates_new_period(self, mock_verify):
        """
        P2-1.1: Renewal invoice creates new billing period and resets tokens.

        Given: Plus user with existing token usage
        When: invoice.payment_succeeded fires with billing_reason='subscription_cycle'
        Then: Token usage reset for new billing period
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-renewal',
            'stripe_customer_id': 'cus_renewal',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        # Old billing period usage
        tables['token_usage'].put_item(Item={
            'user_id': 'user-renewal',
            'billing_period': '2024-12-20',
            'subscription_tier': 'plus',
            'token_limit': 2000000,
            'total_tokens': 500000,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_renewal', 'invoice.payment_succeeded',
            {
                'subscription': 'sub_renewal',
                'customer': 'cus_renewal',
                'billing_reason': 'subscription_cycle',  # Renewal
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        # New billing period should be created
        new_usage = tables['token_usage'].get_item(
            Key={'user_id': 'user-renewal', 'billing_period': '2025-01-20'}
        )
        assert 'Item' in new_usage
        assert int(new_usage['Item']['total_tokens']) == 0  # Reset

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_paid_non_subscription_skipped(self, mock_verify):
        """
        P2-2.3: Non-subscription invoice is skipped.

        Given: Invoice without subscription_id (one-time charge)
        When: invoice.payment_succeeded fires
        Then: Handler returns 200 (skipped)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_one_time', 'invoice.payment_succeeded',
            {
                # No subscription field
                'customer': 'cus_one_time',
                'billing_reason': 'manual',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_paid_restores_active_status(self, mock_verify):
        """
        Test that invoice.payment_succeeded restores active status from past_due.

        Given: User with subscription_status='past_due'
        When: invoice.payment_succeeded fires
        Then: subscription_status updated to 'active'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-restore',
            'stripe_customer_id': 'cus_restore',
            'subscription_tier': 'plus',
            'subscription_status': 'past_due',  # Was past_due
            'billing_day': 20,
            'payment_failed_at': '2025-01-15T10:00:00Z',
        })

        mock_verify.return_value = build_webhook_event(
            'evt_restore', 'invoice.payment_succeeded',
            {
                'subscription': 'sub_restore',
                'customer': 'cus_restore',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'user-restore'})['Item']
        assert user['subscription_status'] == 'active'
        assert 'last_payment_at' in user

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_paid_user_not_found_logs(self, mock_verify):
        """
        Test that invoice.payment_succeeded handles missing user gracefully.

        Given: Invoice for unknown customer
        When: invoice.payment_succeeded fires
        Then: Returns 200 (logs error but doesn't raise)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_no_user_paid', 'invoice.payment_succeeded',
            {
                'subscription': 'sub_orphan',
                'customer': 'cus_unknown',
                'billing_reason': 'subscription_cycle',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (handled gracefully)
        assert response['statusCode'] == 200


# =============================================================================
# Test Class: Invoice Payment Failed Additional Tests (AC-P2-2)
# =============================================================================

class TestInvoicePaymentFailedAdditional:
    """Additional tests for invoice.payment_failed edge cases."""

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_failed_first_failure_sets_past_due(self, mock_verify):
        """
        P2-2.1: First payment failure sets status to past_due but keeps tier.

        Given: Plus user with active subscription
        When: invoice.payment_failed fires (first failure)
        Then: subscription_status='past_due', subscription_tier='plus' (unchanged)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-first-fail',
            'stripe_customer_id': 'cus_first_fail',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'billing_day': 20,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_first_fail', 'invoice.payment_failed',
            {
                'subscription': 'sub_first_fail',
                'customer': 'cus_first_fail',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'user-first-fail'})['Item']
        assert user['subscription_status'] == 'past_due'
        assert user['subscription_tier'] == 'plus'  # Still plus (grace period)

    @mock_aws
    @freeze_time("2025-01-20 14:30:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_failed_multiple_failures_stays_past_due(self, mock_verify):
        """
        P2-2.2: Multiple failures keep status as past_due.

        Given: Plus user already in past_due status
        When: invoice.payment_failed fires again (retry failure)
        Then: subscription_status remains 'past_due'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'user-multi-fail',
            'stripe_customer_id': 'cus_multi_fail',
            'subscription_tier': 'plus',
            'subscription_status': 'past_due',  # Already past_due
            'payment_failed_at': '2025-01-15T10:00:00Z',
            'billing_day': 20,
        })

        mock_verify.return_value = build_webhook_event(
            'evt_multi_fail', 'invoice.payment_failed',
            {
                'subscription': 'sub_multi_fail',
                'customer': 'cus_multi_fail',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        assert response['statusCode'] == 200

        user = tables['users'].get_item(Key={'user_id': 'user-multi-fail'})['Item']
        assert user['subscription_status'] == 'past_due'  # Still past_due
        assert user['subscription_tier'] == 'plus'  # Still plus

    @mock_aws
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_invoice_failed_user_not_found_logs(self, mock_verify):
        """
        Test that invoice.payment_failed handles missing user gracefully.

        Given: Invoice failure for unknown customer
        When: invoice.payment_failed fires
        Then: Returns 200 (logs error but doesn't raise)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_verify.return_value = build_webhook_event(
            'evt_fail_no_user', 'invoice.payment_failed',
            {
                'subscription': 'sub_orphan',
                'customer': 'cus_unknown',
            }
        )

        import handlers.stripe_webhook_handler as handler
        handler.users_table = tables['users']
        handler.token_usage_table = tables['token_usage']
        handler.processed_events_table = tables['events']

        response = handler.lambda_handler(build_api_gateway_event(), None)

        # Should return 200 (handled gracefully)
        assert response['statusCode'] == 200
