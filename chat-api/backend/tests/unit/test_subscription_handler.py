"""
Unit tests for Subscription Handler Lambda.

Tests all subscription API endpoints including:
- POST /subscription/checkout - Create checkout session
- POST /subscription/portal - Create portal session
- GET /subscription/status - Get subscription status

Also tests JWT authorization parsing from various authorizer formats.

Run with: pytest tests/unit/test_subscription_handler.py -v
"""

import json
import os
import sys
import pytest
import boto3
from botocore.exceptions import ClientError
from moto import mock_aws
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any handler imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['USERS_TABLE'] = 'buffett-test-users'
os.environ['TOKEN_USAGE_TABLE'] = 'buffett-test-token-usage'
os.environ['FRONTEND_URL'] = 'https://buffettgpt.test'
os.environ['TOKEN_LIMIT_PLUS'] = '2000000'


# =============================================================================
# DynamoDB Table Helpers
# =============================================================================

def create_users_table(dynamodb):
    """Create users table."""
    table = dynamodb.create_table(
        TableName='buffett-test-users',
        KeySchema=[{'AttributeName': 'user_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'user_id', 'AttributeType': 'S'},
        ],
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


def create_all_tables(dynamodb):
    """Create all required tables."""
    return {
        'users': create_users_table(dynamodb),
        'token_usage': create_token_usage_table(dynamodb),
    }


def build_api_event(
    method='GET',
    path='/subscription/status',
    body=None,
    authorizer_context=None
):
    """Build a mock API Gateway event."""
    event = {
        'httpMethod': method,
        'path': path,
        'requestContext': {
            'authorizer': authorizer_context or {}
        },
        'headers': {}
    }
    if body:
        event['body'] = json.dumps(body)
    return event


# =============================================================================
# Test Class: Authentication
# =============================================================================

class TestAuthentication:
    """Tests for JWT authorization parsing."""

    @mock_aws
    def test_missing_authorizer_returns_401(self):
        """
        Test that missing authorizer context returns 401.

        Given: API request without authorizer context
        When: Handler is invoked
        Then: Returns 401 Unauthorized
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        import handlers.subscription_handler as handler

        event = build_api_event(authorizer_context={})
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 401
        body = json.loads(response['body'])
        assert body['error'] == 'Unauthorized'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    def test_lambda_authorizer_context_parsed(self, mock_get_sub):
        """
        Test parsing of HTTP API v2 Lambda authorizer format.

        Given: Request with authorizer.lambda.user_id context
        When: Handler is invoked
        Then: User ID is correctly extracted
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'lambda-auth-user',
            'subscription_tier': 'free',
        })

        mock_get_sub.return_value = None

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={
                'lambda': {
                    'user_id': 'lambda-auth-user',
                    'email': 'test@example.com'
                }
            }
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'free'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    def test_claims_authorizer_context_parsed(self, mock_get_sub):
        """
        Test parsing of Lambda authorizer claims format.

        Given: Request with authorizer.claims context
        When: Handler is invoked
        Then: User ID is correctly extracted from claims.sub
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'claims-auth-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_get_sub.return_value = None

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={
                'claims': {
                    'sub': 'claims-auth-user',
                    'email': 'test@example.com'
                }
            }
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    def test_direct_authorizer_context_parsed(self, mock_get_sub):
        """
        Test parsing of direct claims format.

        Given: Request with authorizer.user_id directly
        When: Handler is invoked
        Then: User ID is correctly extracted
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'direct-auth-user',
            'subscription_tier': 'free',
        })

        mock_get_sub.return_value = None

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={
                'user_id': 'direct-auth-user',
                'email': 'test@example.com'
            }
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    def test_jwt_authorizer_context_parsed(self, mock_get_sub):
        """
        Test parsing of HTTP API JWT authorizer format.

        Given: Request with authorizer.jwt.claims context
        When: Handler is invoked
        Then: User ID is correctly extracted from jwt.claims
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'jwt-auth-user',
            'subscription_tier': 'free',
        })

        mock_get_sub.return_value = None

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={
                'jwt': {
                    'claims': {
                        'sub': 'jwt-auth-user',
                        'email': 'test@example.com'
                    }
                }
            }
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200


# =============================================================================
# Test Class: handle_create_checkout
# =============================================================================

class TestHandleCreateCheckout:
    """Tests for POST /subscription/checkout endpoint."""

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_new_user_success(self, mock_get_customer, mock_create_session):
        """
        Test successful checkout session creation for new user.

        Given: Authenticated free user
        When: POST /subscription/checkout
        Then: Returns 200 with checkout_url and session_id
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'new-checkout-user',
            'email': 'new@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/session123',
            'session_id': 'cs_test_123'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'new-checkout-user', 'email': 'new@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'checkout_url' in body
        assert 'session_id' in body
        mock_create_session.assert_called_once()

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_existing_customer_reused(self, mock_get_customer, mock_create_session):
        """
        Test that existing Stripe customer ID is reused.

        Given: User with stripe_customer_id already set
        When: POST /subscription/checkout
        Then: Checkout session created with existing customer_id
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'existing-customer',
            'email': 'existing@example.com',
            'stripe_customer_id': 'cus_existing_123',
            'subscription_tier': 'free',
        })

        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/session456',
            'session_id': 'cs_test_456'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'existing-customer', 'email': 'existing@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200

        # Verify customer_id was passed to create_checkout_session
        call_kwargs = mock_create_session.call_args[1]
        assert call_kwargs['customer_id'] == 'cus_existing_123'
        mock_get_customer.assert_not_called()  # Should not look up by email

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_finds_customer_by_email(self, mock_get_customer, mock_create_session):
        """
        Test that customer is found by email if no customer_id on user.

        Given: User without stripe_customer_id but customer exists in Stripe
        When: POST /subscription/checkout
        Then: Customer found by email and ID stored on user
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'email-lookup-user',
            'email': 'lookup@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = {'id': 'cus_found_by_email'}
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/session789',
            'session_id': 'cs_test_789'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'email-lookup-user', 'email': 'lookup@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        mock_get_customer.assert_called_once_with('lookup@example.com')

        # Verify customer_id was passed to checkout
        call_kwargs = mock_create_session.call_args[1]
        assert call_kwargs['customer_id'] == 'cus_found_by_email'

    @mock_aws
    def test_create_checkout_already_subscribed_returns_400(self):
        """
        Test that already subscribed Plus user gets 400 error.

        Given: User with active Plus subscription
        When: POST /subscription/checkout
        Then: Returns 400 with 'Already subscribed' error
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'already-subscribed',
            'email': 'plus@example.com',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'already-subscribed', 'email': 'plus@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Already subscribed' in body.get('error', '')

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_custom_urls(self, mock_get_customer, mock_create_session):
        """
        Test that custom success/cancel URLs from request body are used.

        Given: Request with custom URLs in body
        When: POST /subscription/checkout
        Then: Custom URLs passed to create_checkout_session
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'custom-url-user',
            'email': 'custom@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/custom',
            'session_id': 'cs_custom'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            body={
                'success_url': 'https://buffettgpt.test/checkout/success',
                'cancel_url': 'https://buffettgpt.test/checkout/cancel'
            },
            authorizer_context={'lambda': {'user_id': 'custom-url-user', 'email': 'custom@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_create_session.call_args[1]
        assert call_kwargs['success_url'] == 'https://buffettgpt.test/checkout/success'
        assert call_kwargs['cancel_url'] == 'https://buffettgpt.test/checkout/cancel'

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_stripe_error_returns_500(self, mock_get_customer, mock_create_session):
        """
        Test that Stripe errors return 500.

        Given: Stripe API raises an exception
        When: POST /subscription/checkout
        Then: Returns 500 with error message
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'stripe-error-user',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.side_effect = Exception("Stripe API error")

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'stripe-error-user', 'email': 'error@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert 'error' in body

    @mock_aws
    def test_create_checkout_trialing_user_returns_400(self):
        """
        P1-1.5: Given Plus user in trial, when handle_create_checkout called,
        then returns 400 'Already subscribed'.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'trialing-user',
            'email': 'trialing@example.com',
            'subscription_tier': 'plus',
            'subscription_status': 'trialing',
        })

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'trialing-user', 'email': 'trialing@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'Already subscribed' in body.get('error', '')

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_canceled_user_can_resubscribe(self, mock_get_customer, mock_create_session):
        """
        P1-1.6: Given Plus user with canceled status, when handle_create_checkout called,
        then allows checkout (not blocked).
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User was Plus but subscription was canceled
        tables['users'].put_item(Item={
            'user_id': 'canceled-user',
            'email': 'canceled@example.com',
            'subscription_tier': 'plus',
            'subscription_status': 'canceled',
            'stripe_customer_id': 'cus_canceled123'
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/resubscribe',
            'session_id': 'cs_test_resubscribe'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'canceled-user', 'email': 'canceled@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        # Should succeed - canceled users can resubscribe
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'checkout_url' in body

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_uses_default_urls(self, mock_get_customer, mock_create_session):
        """
        P1-1.8: Given no URLs in body, when handle_create_checkout called,
        then uses FRONTEND_URL defaults.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'default-url-user',
            'email': 'default@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/default',
            'session_id': 'cs_test_default'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            # No body with custom URLs
            authorizer_context={'lambda': {'user_id': 'default-url-user', 'email': 'default@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        # Verify default URLs were used (from FRONTEND_URL env var)
        call_kwargs = mock_create_session.call_args[1]
        assert 'subscription=success' in call_kwargs['success_url']
        assert 'subscription=canceled' in call_kwargs['cancel_url']

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_checkout_rejects_external_success_url(self, mock_get_customer, mock_create_session):
        """
        Security: External URLs in success_url must be rejected to prevent open redirects.

        Given: Request with success_url pointing to attacker domain
        When: POST /subscription/checkout
        Then: Falls back to default FRONTEND_URL-based success URL
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'redirect-test-user',
            'email': 'redirect@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/test',
            'session_id': 'cs_test'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            body={
                'success_url': 'https://evil.com/phish',
                'cancel_url': 'https://evil.com/steal'
            },
            authorizer_context={'lambda': {'user_id': 'redirect-test-user', 'email': 'redirect@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_create_session.call_args[1]
        assert call_kwargs['success_url'].startswith('https://buffettgpt.test')
        assert call_kwargs['cancel_url'].startswith('https://buffettgpt.test')

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_checkout_rejects_javascript_url(self, mock_get_customer, mock_create_session):
        """
        Security: javascript: URIs must be rejected.

        Given: Request with javascript: scheme in success_url
        When: POST /subscription/checkout
        Then: Falls back to default URL
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'js-url-user',
            'email': 'jsurl@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/test',
            'session_id': 'cs_test'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            body={
                'success_url': 'javascript:alert(document.cookie)',
                'cancel_url': 'data:text/html,<script>alert(1)</script>'
            },
            authorizer_context={'lambda': {'user_id': 'js-url-user', 'email': 'jsurl@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_create_session.call_args[1]
        assert call_kwargs['success_url'].startswith('https://buffettgpt.test')
        assert call_kwargs['cancel_url'].startswith('https://buffettgpt.test')

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_checkout_uses_default_url_on_invalid_input(self, mock_get_customer, mock_create_session):
        """
        Security: Non-string or empty URL values fall back to defaults.

        Given: Request with None/empty success_url
        When: POST /subscription/checkout
        Then: Uses default FRONTEND_URL-based URLs
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'empty-url-user',
            'email': 'empty@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/test',
            'session_id': 'cs_test'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            body={
                'success_url': '',
                'cancel_url': None
            },
            authorizer_context={'lambda': {'user_id': 'empty-url-user', 'email': 'empty@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        call_kwargs = mock_create_session.call_args[1]
        assert 'subscription=success' in call_kwargs['success_url']
        assert 'subscription=canceled' in call_kwargs['cancel_url']

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_create_checkout_malformed_json_body(self, mock_get_customer, mock_create_session):
        """
        P1-1.9: Given invalid JSON in body, when handle_create_checkout called,
        then handles gracefully and uses defaults.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'malformed-body-user',
            'email': 'malformed@example.com',
            'subscription_tier': 'free',
        })

        mock_get_customer.return_value = None
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/malformed',
            'session_id': 'cs_test_malformed'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'malformed-body-user', 'email': 'malformed@example.com'}}
        )
        # Override with invalid JSON
        event['body'] = 'not valid json {{{}'

        response = handler.lambda_handler(event, None)

        # Should still succeed with default URLs
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'checkout_url' in body


# =============================================================================
# Test Class: handle_create_portal
# =============================================================================

class TestHandleCreatePortal:
    """Tests for POST /subscription/portal endpoint."""

    @mock_aws
    @patch('handlers.subscription_handler.create_portal_session')
    def test_create_portal_success(self, mock_create_portal):
        """
        Test successful portal session creation.

        Given: User with active subscription and stripe_customer_id
        When: POST /subscription/portal
        Then: Returns 200 with portal_url
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'portal-user',
            'stripe_customer_id': 'cus_portal_123',
            'subscription_tier': 'plus',
        })

        mock_create_portal.return_value = {
            'portal_url': 'https://billing.stripe.com/portal123'
        }

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/portal',
            authorizer_context={'lambda': {'user_id': 'portal-user', 'email': 'portal@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'portal_url' in body

    @mock_aws
    def test_create_portal_user_not_found_returns_404(self):
        """
        Test that non-existent user returns 404.

        Given: Request for user that doesn't exist
        When: POST /subscription/portal
        Then: Returns 404 User not found
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/portal',
            authorizer_context={'lambda': {'user_id': 'nonexistent-user', 'email': 'none@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'User not found' in body.get('error', '')

    @mock_aws
    def test_create_portal_no_customer_id_returns_400(self):
        """
        Test that user without stripe_customer_id returns 400.

        Given: User without Stripe customer ID (never subscribed)
        When: POST /subscription/portal
        Then: Returns 400 with 'No subscription found'
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'no-customer-user',
            'subscription_tier': 'free',
            # No stripe_customer_id
        })

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/portal',
            authorizer_context={'lambda': {'user_id': 'no-customer-user', 'email': 'no@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert 'No subscription found' in body.get('error', '')

    @mock_aws
    @patch('handlers.subscription_handler.create_portal_session')
    def test_create_portal_stripe_error_returns_500(self, mock_create_portal):
        """
        Test that Stripe errors return 500.

        Given: Stripe API raises an exception
        When: POST /subscription/portal
        Then: Returns 500 with error message
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'portal-error-user',
            'stripe_customer_id': 'cus_error',
        })

        mock_create_portal.side_effect = Exception("Stripe API error")

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='POST',
            path='/subscription/portal',
            authorizer_context={'lambda': {'user_id': 'portal-error-user', 'email': 'error@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 500


# =============================================================================
# Test Class: handle_get_status
# =============================================================================

class TestHandleGetStatus:
    """Tests for GET /subscription/status endpoint."""

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_plus_user(self, mock_tracker_class, mock_get_sub):
        """
        Test full subscription details for Plus user.

        Given: User with active Plus subscription
        When: GET /subscription/status
        Then: Returns full subscription details including token usage
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'plus-status-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'stripe_subscription_id': 'sub_plus_123',
            'billing_day': Decimal('15'),
        })

        mock_get_sub.return_value = {
            'id': 'sub_plus_123',
            'status': 'active',
            'current_period_end': 1738454400,  # Unix timestamp
            'cancel_at_period_end': False,
        }

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 500000,
            'token_limit': 2000000,
            'percent_used': 25.0,
            'remaining_tokens': 1500000,
            'request_count': 10,
            'reset_date': '2025-02-15',
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'plus-status-user', 'email': 'plus@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'plus'
        assert body['subscription_status'] == 'active'
        assert body['has_subscription'] is True
        assert body['token_limit'] == 2000000
        assert 'token_usage' in body
        assert body['token_usage']['total_tokens'] == 500000

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_free_user(self, mock_tracker_class, mock_get_sub):
        """
        Test status response for free tier user.

        Given: User with free tier (no subscription)
        When: GET /subscription/status
        Then: Returns free tier with has_subscription=false
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'free-status-user',
            'subscription_tier': 'free',
        })

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 0,
            'token_limit': 0,
            'percent_used': 0,
            'remaining_tokens': 0,
            'request_count': 0,
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'free-status-user', 'email': 'free@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'free'
        assert body['has_subscription'] is False
        assert body['token_limit'] == 0
        mock_get_sub.assert_not_called()  # No Stripe lookup for free users

    @mock_aws
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_missing_user_defaults(self, mock_tracker_class):
        """
        Test that non-existent user gets free tier defaults.

        Given: User ID that doesn't exist in database
        When: GET /subscription/status
        Then: Returns 200 with free tier defaults
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {}
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'nonexistent-user', 'email': 'none@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'free'
        assert body['has_subscription'] is False

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_includes_token_usage(self, mock_tracker_class, mock_get_sub):
        """
        Test that token usage data is included in response.

        Given: Plus user with some token usage
        When: GET /subscription/status
        Then: Response includes token_usage object with usage stats
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'usage-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
        })

        mock_get_sub.return_value = None

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 1200000,
            'token_limit': 2000000,
            'percent_used': 60.0,
            'remaining_tokens': 800000,
            'request_count': 25,
            'reset_date': '2025-02-20',
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'usage-user', 'email': 'usage@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'token_usage' in body
        assert body['token_usage']['total_tokens'] == 1200000
        assert body['token_usage']['percent_used'] == 60.0
        assert body['token_usage']['remaining_tokens'] == 800000

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_fetches_stripe_subscription(self, mock_tracker_class, mock_get_sub):
        """
        Test that Stripe subscription is fetched for Plus users.

        Given: Plus user with stripe_subscription_id
        When: GET /subscription/status
        Then: get_subscription is called with the subscription ID
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'stripe-fetch-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'stripe_subscription_id': 'sub_to_fetch',
        })

        mock_get_sub.return_value = {'id': 'sub_to_fetch', 'status': 'active'}

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {}
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'stripe-fetch-user', 'email': 'fetch@example.com'}}
        )
        handler.lambda_handler(event, None)

        mock_get_sub.assert_called_once_with('sub_to_fetch')

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_handles_missing_subscription(self, mock_tracker_class, mock_get_sub):
        """
        Test graceful handling when Stripe subscription is missing.

        Given: User with stripe_subscription_id but subscription deleted in Stripe
        When: GET /subscription/status
        Then: Returns status with cached info from DynamoDB
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'missing-sub-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'stripe_subscription_id': 'sub_deleted',
        })

        mock_get_sub.return_value = None  # Subscription not found

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {}
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'missing-sub-user', 'email': 'missing@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        # Should still work with cached data
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_cancel_at_period_end(self, mock_tracker_class, mock_get_sub):
        """
        Test that cancel_at_period_end from Stripe is reflected.

        Given: User with subscription set to cancel at period end
        When: GET /subscription/status
        Then: cancel_at_period_end=True in response
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'cancel-end-user',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'stripe_subscription_id': 'sub_canceling',
            'cancel_at_period_end': False,  # DynamoDB might have stale value
        })

        mock_get_sub.return_value = {
            'id': 'sub_canceling',
            'status': 'active',
            'cancel_at_period_end': True,  # Stripe has current value
            'current_period_end': 1738454400,
        }

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {}
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'cancel-end-user', 'email': 'cancel@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        # Stripe value should override DynamoDB cached value
        assert body['cancel_at_period_end'] is True

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_past_due_user(self, mock_tracker_class, mock_get_sub):
        """
        P1-3.4: Given payment failed (past_due status), when handle_get_status called,
        then returns status=past_due.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'past-due-user',
            'subscription_tier': 'plus',
            'subscription_status': 'past_due',
            'stripe_subscription_id': 'sub_past_due_123',
        })

        mock_get_sub.return_value = {
            'id': 'sub_past_due_123',
            'status': 'past_due',
            'current_period_end': 1738454400,
            'cancel_at_period_end': False,
        }

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 200000,
            'token_limit': 2000000,
            'percent_used': 10.0,
            'remaining_tokens': 1800000,
            'request_count': 20,
            'reset_date': '2026-02-15',
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'past-due-user', 'email': 'pastdue@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_status'] == 'past_due'
        assert body['subscription_tier'] == 'plus'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_new_plus_user_default_tokens(self, mock_tracker_class, mock_get_sub):
        """
        P1-3.6: Given new Plus user (no token usage record), when handle_get_status called,
        then returns default token values.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'new-plus-user',
            'email': 'newplus@example.com',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'stripe_subscription_id': 'sub_newplus123',
        })

        mock_get_sub.return_value = {
            'id': 'sub_newplus123',
            'status': 'active',
            'current_period_end': 1738454400,
            'cancel_at_period_end': False,
        }

        # No usage record - tracker returns empty/default values
        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 0,
            'token_limit': 2000000,
            'percent_used': 0.0,
            'remaining_tokens': 2000000,
            'request_count': 0,
            'reset_date': None,
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'new-plus-user', 'email': 'newplus@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['token_usage']['total_tokens'] == 0
        assert body['token_usage']['token_limit'] == 2000000
        assert body['token_limit'] == 2000000

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_status_stripe_api_failure_uses_cached_data(self, mock_tracker_class, mock_get_sub):
        """
        P1-3.7: Given Stripe API unavailable, when handle_get_status called,
        then returns cached data and logs warning.
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'stripe-fail-user',
            'email': 'stripefail@example.com',
            'subscription_tier': 'plus',
            'subscription_status': 'active',
            'cancel_at_period_end': False,
            'stripe_subscription_id': 'sub_stripefail123',
        })

        # Stripe API fails
        mock_get_sub.side_effect = Exception("Stripe API unavailable")

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 100000,
            'token_limit': 2000000,
            'percent_used': 5.0,
            'remaining_tokens': 1900000,
            'request_count': 10,
            'reset_date': '2026-02-15',
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'stripe-fail-user', 'email': 'stripefail@example.com'}}
        )
        response = handler.lambda_handler(event, None)

        # Should still succeed with cached DynamoDB data
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'plus'
        assert body['subscription_status'] == 'active'
        # cancel_at_period_end should come from DynamoDB cache
        assert body['cancel_at_period_end'] is False


# =============================================================================
# Test Class: Routing
# =============================================================================

class TestRouting:
    """Tests for request routing."""

    @mock_aws
    def test_options_returns_200_without_auth(self):
        """
        Test that OPTIONS preflight requests return 200 without auth.

        Given: OPTIONS request (CORS preflight)
        When: Handler is invoked
        Then: Returns 200 without requiring authorization
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        import handlers.subscription_handler as handler

        event = build_api_event(
            method='OPTIONS',
            path='/subscription/checkout',
            authorizer_context={}  # No auth
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200

    @mock_aws
    def test_unknown_path_returns_404(self):
        """
        Test that unknown paths return 404.

        Given: Request to unknown endpoint
        When: Handler is invoked
        Then: Returns 404 Not found
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        import handlers.subscription_handler as handler

        event = build_api_event(
            method='GET',
            path='/subscription/unknown',
            authorizer_context={'lambda': {'user_id': 'test', 'email': 'test@test.com'}}
        )
        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error'] == 'Not found'

    @mock_aws
    @patch('handlers.subscription_handler.get_subscription')
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_http_api_v2_format_request(self, mock_tracker_class, mock_get_sub):
        """
        Test that HTTP API v2 event format is handled correctly.

        Given: Request in HTTP API v2 format (rawPath, requestContext.http.method)
        When: Handler is invoked
        Then: Method and path are correctly extracted
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        tables['users'].put_item(Item={
            'user_id': 'http-v2-user',
            'email': 'v2@example.com',
            'subscription_tier': 'free',
        })

        mock_get_sub.return_value = None

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {
            'total_tokens': 0,
            'token_limit': 0,
            'percent_used': 0.0,
            'remaining_tokens': 0,
            'request_count': 0,
            'reset_date': None,
        }
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler
        handler.users_table = tables['users']

        # HTTP API v2 format (no httpMethod, uses requestContext.http.method)
        event = {
            'rawPath': '/subscription/status',
            'requestContext': {
                'http': {
                    'method': 'GET'
                },
                'authorizer': {
                    'lambda': {
                        'user_id': 'http-v2-user',
                        'email': 'v2@example.com'
                    }
                }
            }
        }

        response = handler.lambda_handler(event, None)

        assert response['statusCode'] == 200


# =============================================================================
# Test Class: DecimalEncoder
# =============================================================================

class TestDecimalEncoder:
    """Tests for DecimalEncoder JSON serialization."""

    def test_decimal_encoder_integer_decimal(self):
        """Test that integer Decimal values are serialized as int."""
        from handlers.subscription_handler import DecimalEncoder

        data = {'value': Decimal('100')}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['value'] == 100
        assert isinstance(parsed['value'], int)

    def test_decimal_encoder_float_decimal(self):
        """Test that float Decimal values are serialized as float."""
        from handlers.subscription_handler import DecimalEncoder

        data = {'value': Decimal('99.99')}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['value'] == 99.99

    def test_decimal_encoder_mixed_types(self):
        """Test encoding with mixed types including Decimals."""
        from handlers.subscription_handler import DecimalEncoder

        data = {
            'integer_decimal': Decimal('100'),
            'float_decimal': Decimal('99.99'),
            'normal_int': 42,
            'normal_float': 3.14,
            'string': 'test'
        }

        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['integer_decimal'] == 100
        assert parsed['float_decimal'] == 99.99
        assert parsed['normal_int'] == 42
        assert parsed['normal_float'] == 3.14
        assert parsed['string'] == 'test'

    def test_decimal_encoder_non_serializable_raises(self):
        """
        Test that non-serializable types raise TypeError (covers line 50).

        Given: Data containing a non-JSON-serializable type (e.g., set)
        When: json.dumps is called with DecimalEncoder
        Then: TypeError is raised by super().default()
        """
        from handlers.subscription_handler import DecimalEncoder

        data = {'value': {1, 2, 3}}  # Sets are not JSON serializable

        with pytest.raises(TypeError):
            json.dumps(data, cls=DecimalEncoder)


# =============================================================================
# Test Class: DynamoDB Error Handling
# =============================================================================

class TestDynamoDBErrorHandling:
    """Tests for DynamoDB error handling in helper functions."""

    @mock_aws
    @patch('handlers.subscription_handler.TokenUsageTracker')
    def test_get_user_dynamodb_error_returns_default(self, mock_tracker_class):
        """
        Test that DynamoDB ClientError in _get_user returns None gracefully (covers lines 315-317).

        Given: DynamoDB get_item raises ClientError
        When: handle_get_status is called
        Then: Returns default free user response
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_all_tables(dynamodb)

        mock_tracker = MagicMock()
        mock_tracker.get_usage.return_value = {}
        mock_tracker_class.return_value = mock_tracker

        import handlers.subscription_handler as handler

        # Create a mock table that raises ClientError
        mock_table = MagicMock()
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'DynamoDB unavailable'}},
            'GetItem'
        )
        handler.users_table = mock_table

        event = build_api_event(
            method='GET',
            path='/subscription/status',
            authorizer_context={'lambda': {'user_id': 'error-user', 'email': 'error@example.com'}}
        )

        response = handler.lambda_handler(event, None)

        # Should return default free response when user lookup fails
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['subscription_tier'] == 'free'
        assert body['has_subscription'] is False

    @mock_aws
    @patch('handlers.subscription_handler.create_checkout_session')
    @patch('handlers.subscription_handler.get_customer_by_email')
    def test_update_user_customer_id_error_continues(self, mock_get_customer, mock_create_session):
        """
        Test that ClientError in _update_user_customer_id logs warning but continues (covers lines 328-329).

        Given: User found by email, but update_item fails
        When: handle_create_checkout is called
        Then: Checkout still succeeds (error is logged but not fatal)
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        tables = create_all_tables(dynamodb)

        # User exists without customer_id
        tables['users'].put_item(Item={
            'user_id': 'update-error-user',
            'email': 'update@example.com',
            'subscription_tier': 'free',
        })

        # Customer found by email
        mock_get_customer.return_value = {'id': 'cus_found_by_email'}
        mock_create_session.return_value = {
            'checkout_url': 'https://checkout.stripe.com/test',
            'session_id': 'cs_test_123'
        }

        import handlers.subscription_handler as handler

        # Create a mock table that works for get_item but fails on update_item
        real_table = tables['users']
        mock_table = MagicMock()
        mock_table.get_item.side_effect = real_table.get_item
        mock_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ConditionalCheckFailedException', 'Message': 'Update failed'}},
            'UpdateItem'
        )
        handler.users_table = mock_table

        event = build_api_event(
            method='POST',
            path='/subscription/checkout',
            authorizer_context={'lambda': {'user_id': 'update-error-user', 'email': 'update@example.com'}}
        )

        response = handler.lambda_handler(event, None)

        # Checkout should still succeed even if storing customer_id fails
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'checkout_url' in body
