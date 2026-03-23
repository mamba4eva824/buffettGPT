"""
E2E integration tests for the referral-to-Stripe flow.

Tests the full lifecycle: waitlist referral rewards → checkout session creation
→ webhook processing → claim marking. Uses moto for DynamoDB and mocks only
Stripe API calls.

Test Scenarios:
1. Eligible user (3 referrals) → checkout session has 30-day trial
2. Eligible user (5 referrals) → checkout session has 90-day trial
3. Ineligible user (<3 referrals) → no trial on checkout
4. Webhook marks referral as claimed after checkout.session.completed
5. Double-claim prevention: already-claimed referral gets no trial

Run with: pytest tests/integration/test_referral_stripe_e2e.py -v
"""

import json
import os
import sys
import pytest
import boto3
from moto import mock_aws
from freezegun import freeze_time
from unittest.mock import patch, MagicMock

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any handler imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['TOKEN_USAGE_TABLE'] = 'buffett-test-token-usage'
os.environ['PROCESSED_EVENTS_TABLE'] = 'buffett-test-stripe-events'
os.environ['WAITLIST_TABLE'] = 'waitlist-test-buffett'
os.environ['FRONTEND_URL'] = 'https://buffettgpt.test'
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
    """Create stripe-events table for idempotency tracking."""
    table = dynamodb.create_table(
        TableName='buffett-test-stripe-events',
        KeySchema=[{'AttributeName': 'event_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'event_id', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def create_waitlist_table(dynamodb):
    """Create waitlist table with referral-code GSI."""
    table = dynamodb.create_table(
        TableName='waitlist-test-buffett',
        KeySchema=[{'AttributeName': 'email', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'email', 'AttributeType': 'S'},
            {'AttributeName': 'referral_code', 'AttributeType': 'S'},
        ],
        GlobalSecondaryIndexes=[{
            'IndexName': 'referral-code-index',
            'KeySchema': [{'AttributeName': 'referral_code', 'KeyType': 'HASH'}],
            'Projection': {'ProjectionType': 'ALL'},
        }],
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
        'waitlist': create_waitlist_table(dynamodb),
    }


# =============================================================================
# Event Builders
# =============================================================================

def build_checkout_api_event(user_id, email):
    """Build a mock API Gateway event for POST /subscription/checkout."""
    return {
        'httpMethod': 'POST',
        'path': '/subscription/checkout',
        'requestContext': {
            'authorizer': {
                'lambda': {
                    'user_id': user_id,
                    'email': email,
                }
            }
        },
        'headers': {},
        'body': None,
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


def build_webhook_api_gateway_event(body='{}', signature='test_sig'):
    """Build a mock API Gateway event for the webhook handler."""
    return {
        'body': body,
        'headers': {'stripe-signature': signature}
    }


def wire_subscription_handler(handler, tables):
    """Wire moto tables into the subscription handler module."""
    handler.users_table = tables['users']
    handler.waitlist_table = tables['waitlist']


def wire_webhook_handler(handler, tables):
    """Wire moto tables into the webhook handler module."""
    handler.users_table = tables['users']
    handler.token_usage_table = tables['token_usage']
    handler.processed_events_table = tables['events']
    handler.waitlist_table = tables['waitlist']


# =============================================================================
# Test Class: Full Referral → Checkout → Webhook E2E Flow
# =============================================================================

class TestReferralCheckoutE2E:
    """
    E2E integration tests for the referral-to-Stripe lifecycle.

    Each test exercises the full path:
    1. Seed waitlist entry with referral count
    2. Call subscription handler (POST /subscription/checkout)
    3. Verify checkout session parameters (trial days, metadata)
    4. Feed the metadata into the webhook handler (checkout.session.completed)
    5. Verify DynamoDB state (user record, waitlist claim)
    """

    @mock_aws
    @freeze_time("2026-02-15 10:00:00", tz_offset=0)
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_3_referrals_full_flow_30_day_trial(
        self, mock_verify, mock_get_customer, mock_create_session
    ):
        """
        E2E Scenario 1: User with 3 referrals gets a 30-day trial.

        Given: A waitlist entry with 3 referrals (triggers 30-day trial)
        When: User creates checkout, then checkout.session.completed fires
        Then:
            - Checkout session has subscription_data.trial_period_days = 30
            - Metadata includes referral_trial_days, referral_source, referral_email
            - User record shows subscription_status = 'trialing', tier = 'plus'
            - Waitlist entry has referral_claimed_at set
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        user_id = 'e2e-referral-3'
        email = 'referral3@e2e-test.com'

        # Seed user and waitlist entry with 3 referrals
        tables['users'].put_item(Item={
            'user_id': user_id,
            'email': email,
            'subscription_tier': 'free',
        })
        tables['waitlist'].put_item(Item={
            'email': email,
            'referral_code': 'BUFF-E2E-3REF',
            'referral_count': 3,
            'status': 'early_access',
        })

        # --- Phase 1: Checkout Creation ---
        captured_kwargs = {}

        def capture_checkout(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                'checkout_url': 'https://checkout.stripe.com/e2e-trial30',
                'session_id': 'cs_e2e_trial_30'
            }

        mock_get_customer.return_value = None
        mock_create_session.side_effect = capture_checkout

        import handlers.subscription_handler as sub_handler
        wire_subscription_handler(sub_handler, tables)

        checkout_response = sub_handler.lambda_handler(
            build_checkout_api_event(user_id, email), None
        )

        assert checkout_response['statusCode'] == 200

        # Verify checkout session was created with correct trial params
        assert captured_kwargs['trial_period_days'] == 30
        assert captured_kwargs['extra_metadata']['referral_trial_days'] == '30'
        assert captured_kwargs['extra_metadata']['referral_source'] == 'waitlist'
        assert captured_kwargs['extra_metadata']['referral_email'] == email

        # --- Phase 2: Webhook Processing ---
        # Simulate Stripe sending checkout.session.completed with the metadata
        mock_verify.return_value = build_webhook_event(
            'evt_e2e_3ref', 'checkout.session.completed',
            {
                'client_reference_id': user_id,
                'customer': 'cus_e2e_3ref',
                'subscription': 'sub_e2e_3ref',
                'metadata': {
                    'user_id': user_id,
                    'environment': 'test',
                    **captured_kwargs['extra_metadata'],
                }
            }
        )

        import handlers.stripe_webhook_handler as wh_handler
        wire_webhook_handler(wh_handler, tables)

        webhook_response = wh_handler.lambda_handler(
            build_webhook_api_gateway_event(), None
        )

        assert webhook_response['statusCode'] == 200

        # --- Phase 3: Verify Final State ---
        # User record: trialing + plus
        user = tables['users'].get_item(Key={'user_id': user_id})['Item']
        assert user['subscription_status'] == 'trialing'
        assert user['subscription_tier'] == 'plus'
        assert user['stripe_customer_id'] == 'cus_e2e_3ref'
        assert user['stripe_subscription_id'] == 'sub_e2e_3ref'

        # Waitlist entry: referral claimed
        waitlist_entry = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert 'referral_claimed_at' in waitlist_entry
        assert waitlist_entry['referral_claimed_by'] == user_id
        assert int(waitlist_entry['referral_trial_days_granted']) == 30

        # Token usage initialized
        token_items = tables['token_usage'].scan()['Items']
        assert len(token_items) >= 1
        assert any(item['user_id'] == user_id for item in token_items)

    @mock_aws
    @freeze_time("2026-02-15 10:00:00", tz_offset=0)
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_5_referrals_full_flow_90_day_trial(
        self, mock_verify, mock_get_customer, mock_create_session
    ):
        """
        E2E Scenario 2: User with 5 referrals gets a 90-day trial.

        Given: A waitlist entry with 5 referrals (triggers 90-day trial)
        When: User creates checkout, then checkout.session.completed fires
        Then:
            - Checkout session has trial_period_days = 90
            - Metadata includes referral_trial_days = '90'
            - User record shows subscription_status = 'trialing', tier = 'plus'
            - Waitlist entry has referral_claimed_at set with 90 days granted
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        user_id = 'e2e-referral-5'
        email = 'referral5@e2e-test.com'

        tables['users'].put_item(Item={
            'user_id': user_id,
            'email': email,
            'subscription_tier': 'free',
        })
        tables['waitlist'].put_item(Item={
            'email': email,
            'referral_code': 'BUFF-E2E-5REF',
            'referral_count': 5,
            'status': 'early_access',
        })

        # --- Phase 1: Checkout Creation ---
        captured_kwargs = {}

        def capture_checkout(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                'checkout_url': 'https://checkout.stripe.com/e2e-trial90',
                'session_id': 'cs_e2e_trial_90'
            }

        mock_get_customer.return_value = None
        mock_create_session.side_effect = capture_checkout

        import handlers.subscription_handler as sub_handler
        wire_subscription_handler(sub_handler, tables)

        checkout_response = sub_handler.lambda_handler(
            build_checkout_api_event(user_id, email), None
        )

        assert checkout_response['statusCode'] == 200
        assert captured_kwargs['trial_period_days'] == 90
        assert captured_kwargs['extra_metadata']['referral_trial_days'] == '90'

        # --- Phase 2: Webhook Processing ---
        mock_verify.return_value = build_webhook_event(
            'evt_e2e_5ref', 'checkout.session.completed',
            {
                'client_reference_id': user_id,
                'customer': 'cus_e2e_5ref',
                'subscription': 'sub_e2e_5ref',
                'metadata': {
                    'user_id': user_id,
                    'environment': 'test',
                    **captured_kwargs['extra_metadata'],
                }
            }
        )

        import handlers.stripe_webhook_handler as wh_handler
        wire_webhook_handler(wh_handler, tables)

        webhook_response = wh_handler.lambda_handler(
            build_webhook_api_gateway_event(), None
        )

        assert webhook_response['statusCode'] == 200

        # --- Phase 3: Verify Final State ---
        user = tables['users'].get_item(Key={'user_id': user_id})['Item']
        assert user['subscription_status'] == 'trialing'
        assert user['subscription_tier'] == 'plus'

        waitlist_entry = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert 'referral_claimed_at' in waitlist_entry
        assert int(waitlist_entry['referral_trial_days_granted']) == 90

    @mock_aws
    @freeze_time("2026-02-15 10:00:00", tz_offset=0)
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_fewer_than_3_referrals_no_trial(
        self, mock_verify, mock_get_customer, mock_create_session
    ):
        """
        E2E Scenario 3: User with <3 referrals gets no trial.

        Given: A waitlist entry with 1 referral (below threshold)
        When: User creates checkout, then checkout.session.completed fires
        Then:
            - Checkout session has no trial_period_days
            - No referral metadata attached
            - User record shows subscription_status = 'active' (not 'trialing')
            - No referral_claimed_at on waitlist entry
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        user_id = 'e2e-referral-1'
        email = 'referral1@e2e-test.com'

        tables['users'].put_item(Item={
            'user_id': user_id,
            'email': email,
            'subscription_tier': 'free',
        })
        tables['waitlist'].put_item(Item={
            'email': email,
            'referral_code': 'BUFF-E2E-1REF',
            'referral_count': 1,
            'status': 'waitlisted',
        })

        # --- Phase 1: Checkout Creation ---
        captured_kwargs = {}

        def capture_checkout(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                'checkout_url': 'https://checkout.stripe.com/e2e-notrial',
                'session_id': 'cs_e2e_notrial'
            }

        mock_get_customer.return_value = None
        mock_create_session.side_effect = capture_checkout

        import handlers.subscription_handler as sub_handler
        wire_subscription_handler(sub_handler, tables)

        checkout_response = sub_handler.lambda_handler(
            build_checkout_api_event(user_id, email), None
        )

        assert checkout_response['statusCode'] == 200
        assert captured_kwargs.get('trial_period_days') is None
        assert captured_kwargs.get('extra_metadata') is None

        # --- Phase 2: Webhook Processing (no referral metadata) ---
        mock_verify.return_value = build_webhook_event(
            'evt_e2e_1ref', 'checkout.session.completed',
            {
                'client_reference_id': user_id,
                'customer': 'cus_e2e_1ref',
                'subscription': 'sub_e2e_1ref',
                'metadata': {
                    'user_id': user_id,
                    'environment': 'test',
                }
            }
        )

        import handlers.stripe_webhook_handler as wh_handler
        wire_webhook_handler(wh_handler, tables)

        webhook_response = wh_handler.lambda_handler(
            build_webhook_api_gateway_event(), None
        )

        assert webhook_response['statusCode'] == 200

        # --- Phase 3: Verify Final State ---
        user = tables['users'].get_item(Key={'user_id': user_id})['Item']
        assert user['subscription_status'] == 'active'
        assert user['subscription_tier'] == 'plus'

        # Waitlist entry NOT claimed
        waitlist_entry = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert 'referral_claimed_at' not in waitlist_entry

    @mock_aws
    @freeze_time("2026-02-15 10:00:00", tz_offset=0)
    @patch('handlers.stripe_webhook_handler.verify_webhook_signature')
    def test_webhook_marks_referral_claimed(self, mock_verify):
        """
        E2E Scenario 4: Webhook marks referral as claimed.

        Given: A waitlist entry with 3+ referrals (unclaimed)
        When: checkout.session.completed fires with referral metadata
        Then:
            - Waitlist entry gets referral_claimed_at timestamp
            - referral_claimed_by matches the user_id
            - referral_trial_days_granted matches the trial days
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        user_id = 'e2e-claim-user'
        email = 'claim@e2e-test.com'

        tables['users'].put_item(Item={
            'user_id': user_id,
            'email': email,
        })
        tables['waitlist'].put_item(Item={
            'email': email,
            'referral_code': 'BUFF-E2E-CLAIM',
            'referral_count': 4,
            'status': 'early_access',
        })

        # Verify no claim exists before webhook
        entry_before = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert 'referral_claimed_at' not in entry_before

        mock_verify.return_value = build_webhook_event(
            'evt_e2e_claim', 'checkout.session.completed',
            {
                'client_reference_id': user_id,
                'customer': 'cus_e2e_claim',
                'subscription': 'sub_e2e_claim',
                'metadata': {
                    'user_id': user_id,
                    'environment': 'test',
                    'referral_trial_days': '30',
                    'referral_source': 'waitlist',
                    'referral_email': email,
                }
            }
        )

        import handlers.stripe_webhook_handler as wh_handler
        wire_webhook_handler(wh_handler, tables)

        response = wh_handler.lambda_handler(
            build_webhook_api_gateway_event(), None
        )

        assert response['statusCode'] == 200

        # Verify claim was written
        entry_after = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert entry_after['referral_claimed_at'] == '2026-02-15T10:00:00Z'
        assert entry_after['referral_claimed_by'] == user_id
        assert int(entry_after['referral_trial_days_granted']) == 30

    @mock_aws
    @freeze_time("2026-02-15 10:00:00", tz_offset=0)
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_double_claim_prevention_no_trial_on_second_checkout(
        self, mock_get_customer, mock_create_session
    ):
        """
        E2E Scenario 5: Double-claim prevention.

        Given: A waitlist entry with 5 referrals but referral_claimed_at already set
        When: User calls POST /subscription/checkout again
        Then:
            - No trial period is attached (treated as ineligible)
            - No referral metadata in checkout session
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        user_id = 'e2e-double-claim'
        email = 'doubleclaim@e2e-test.com'

        tables['users'].put_item(Item={
            'user_id': user_id,
            'email': email,
            'subscription_tier': 'free',
        })
        tables['waitlist'].put_item(Item={
            'email': email,
            'referral_code': 'BUFF-E2E-DOUBLE',
            'referral_count': 5,
            'status': 'early_access',
            # Already claimed from a previous checkout
            'referral_claimed_at': '2026-01-01T00:00:00Z',
            'referral_claimed_by': 'previous-user',
            'referral_trial_days_granted': 90,
        })

        captured_kwargs = {}

        def capture_checkout(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                'checkout_url': 'https://checkout.stripe.com/e2e-double',
                'session_id': 'cs_e2e_double'
            }

        mock_get_customer.return_value = None
        mock_create_session.side_effect = capture_checkout

        import handlers.subscription_handler as sub_handler
        wire_subscription_handler(sub_handler, tables)

        checkout_response = sub_handler.lambda_handler(
            build_checkout_api_event(user_id, email), None
        )

        assert checkout_response['statusCode'] == 200

        # No trial attached — the referral was already claimed
        assert captured_kwargs.get('trial_period_days') is None
        assert captured_kwargs.get('extra_metadata') is None

        # Original claim data unchanged
        waitlist_entry = tables['waitlist'].get_item(Key={'email': email})['Item']
        assert waitlist_entry['referral_claimed_by'] == 'previous-user'
        assert waitlist_entry['referral_claimed_at'] == '2026-01-01T00:00:00Z'
