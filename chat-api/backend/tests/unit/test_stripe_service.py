"""
Unit tests for Stripe Service utility functions.

Tests all service layer functions including:
- Secret management (get_secret, caching)
- create_checkout_session
- create_portal_session
- get_subscription
- get_customer_by_email
- verify_webhook_signature

Run with: pytest tests/unit/test_stripe_service.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['TOKEN_LIMIT_PLUS'] = '2000000'


# =============================================================================
# Test Class: Secret Management
# =============================================================================

class TestSecretManagement:
    """Tests for secret fetching and caching."""

    @patch('utils.stripe_service.secrets_client')
    def test_get_secret_success(self, mock_secrets):
        """
        Test successful secret retrieval.

        Given: A valid secret name
        When: get_secret is called
        Then: Returns the secret string value
        """
        mock_secrets.get_secret_value.return_value = {
            'SecretString': 'sk_test_secret123'
        }

        # Clear cache to ensure fresh call
        from utils.stripe_service import get_secret
        get_secret.cache_clear()

        result = get_secret('stripe-secret-key-test')

        assert result == 'sk_test_secret123'
        mock_secrets.get_secret_value.assert_called_once_with(SecretId='stripe-secret-key-test')

    @patch('utils.stripe_service.secrets_client')
    def test_get_secret_caches_result(self, mock_secrets):
        """
        Test that get_secret caches results (LRU cache).

        Given: A secret that has been fetched once
        When: get_secret is called again with same name
        Then: Uses cached value without calling Secrets Manager again
        """
        mock_secrets.get_secret_value.return_value = {
            'SecretString': 'cached_secret'
        }

        from utils.stripe_service import get_secret
        get_secret.cache_clear()

        # First call
        result1 = get_secret('cached-secret-test')
        # Second call (should use cache)
        result2 = get_secret('cached-secret-test')

        assert result1 == result2 == 'cached_secret'
        # Should only be called once due to caching
        assert mock_secrets.get_secret_value.call_count == 1

    @patch('utils.stripe_service.secrets_client')
    def test_get_secret_not_found_raises_valueerror(self, mock_secrets):
        """
        Test that missing secret raises ValueError.

        Given: A secret name that doesn't exist
        When: get_secret is called
        Then: Raises ValueError with descriptive message
        """
        mock_secrets.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'ResourceNotFoundException', 'Message': 'Secret not found'}},
            'GetSecretValue'
        )

        from utils.stripe_service import get_secret
        get_secret.cache_clear()

        with pytest.raises(ValueError) as exc_info:
            get_secret('nonexistent-secret')

        assert 'not found' in str(exc_info.value)

    @patch('utils.stripe_service.secrets_client')
    def test_get_secret_other_error_propagates(self, mock_secrets):
        """
        Test that non-NotFound errors propagate as ClientError.

        Given: Secrets Manager returns a non-NotFound error
        When: get_secret is called
        Then: ClientError is propagated
        """
        mock_secrets.get_secret_value.side_effect = ClientError(
            {'Error': {'Code': 'AccessDeniedException', 'Message': 'Access denied'}},
            'GetSecretValue'
        )

        from utils.stripe_service import get_secret
        get_secret.cache_clear()

        with pytest.raises(ClientError):
            get_secret('forbidden-secret')


# =============================================================================
# Test Class: create_checkout_session
# =============================================================================

class TestCreateCheckoutSession:
    """Tests for Stripe checkout session creation."""

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_plus_price_id')
    def test_create_checkout_session_success(self, mock_get_price, mock_get_stripe):
        """
        Test successful checkout session creation.

        Given: Valid user and URLs
        When: create_checkout_session is called
        Then: Returns dict with checkout_url and session_id
        """
        mock_get_price.return_value = 'price_test_123'

        mock_session = MagicMock()
        mock_session.url = 'https://checkout.stripe.com/session_abc'
        mock_session.id = 'cs_test_abc123'

        mock_stripe = MagicMock()
        mock_stripe.checkout.Session.create.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_checkout_session

        result = create_checkout_session(
            user_id='user-123',
            user_email='test@example.com',
            success_url='https://app.com/success',
            cancel_url='https://app.com/cancel'
        )

        assert result['checkout_url'] == 'https://checkout.stripe.com/session_abc'
        assert result['session_id'] == 'cs_test_abc123'

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_plus_price_id')
    def test_create_checkout_session_uses_customer_id(self, mock_get_price, mock_get_stripe):
        """
        Test that customer_id is passed when provided.

        Given: Existing customer_id
        When: create_checkout_session is called with customer_id
        Then: Session created with customer param (not customer_email)
        """
        mock_get_price.return_value = 'price_test_123'

        mock_session = MagicMock()
        mock_session.url = 'https://checkout.stripe.com/session'
        mock_session.id = 'cs_test'

        mock_stripe = MagicMock()
        mock_stripe.checkout.Session.create.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_checkout_session

        create_checkout_session(
            user_id='user-123',
            user_email='test@example.com',
            success_url='https://app.com/success',
            cancel_url='https://app.com/cancel',
            customer_id='cus_existing_456'
        )

        # Verify customer param was used instead of customer_email
        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs['customer'] == 'cus_existing_456'
        assert 'customer_email' not in call_kwargs

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_plus_price_id')
    def test_create_checkout_session_uses_email_when_no_customer(self, mock_get_price, mock_get_stripe):
        """
        Test that email is used when no customer_id provided.

        Given: No customer_id
        When: create_checkout_session is called with email only
        Then: Session created with customer_email param
        """
        mock_get_price.return_value = 'price_test_123'

        mock_session = MagicMock()
        mock_session.url = 'https://checkout.stripe.com/session'
        mock_session.id = 'cs_test'

        mock_stripe = MagicMock()
        mock_stripe.checkout.Session.create.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_checkout_session

        create_checkout_session(
            user_id='user-123',
            user_email='newuser@example.com',
            success_url='https://app.com/success',
            cancel_url='https://app.com/cancel'
            # No customer_id
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert call_kwargs['customer_email'] == 'newuser@example.com'
        assert 'customer' not in call_kwargs

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_plus_price_id')
    def test_create_checkout_session_stripe_error_propagates(self, mock_get_price, mock_get_stripe):
        """
        Test that Stripe errors propagate up.

        Given: Stripe API raises an error
        When: create_checkout_session is called
        Then: StripeError is propagated
        """
        mock_get_price.return_value = 'price_test_123'

        mock_stripe = MagicMock()
        mock_stripe.error = MagicMock()
        mock_stripe.error.StripeError = Exception
        mock_stripe.checkout.Session.create.side_effect = Exception("Stripe API Error")
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_checkout_session

        with pytest.raises(Exception) as exc_info:
            create_checkout_session(
                user_id='user-123',
                user_email='test@example.com',
                success_url='https://app.com/success',
                cancel_url='https://app.com/cancel'
            )

        assert 'Stripe API Error' in str(exc_info.value)

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_plus_price_id')
    def test_create_checkout_session_includes_user_id_in_subscription_metadata(self, mock_get_price, mock_get_stripe):
        """
        Test that user_id is passed in subscription_data.metadata.

        Given: Valid user creating a checkout session
        When: create_checkout_session is called
        Then: subscription_data.metadata contains user_id so the
              customer.subscription.created webhook can find it
        """
        mock_get_price.return_value = 'price_test_123'

        mock_session = MagicMock()
        mock_session.url = 'https://checkout.stripe.com/session'
        mock_session.id = 'cs_test'

        mock_stripe = MagicMock()
        mock_stripe.checkout.Session.create.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_checkout_session

        create_checkout_session(
            user_id='user-789',
            user_email='test@example.com',
            success_url='https://app.com/success',
            cancel_url='https://app.com/cancel'
        )

        call_kwargs = mock_stripe.checkout.Session.create.call_args[1]
        assert 'subscription_data' in call_kwargs
        assert call_kwargs['subscription_data']['metadata']['user_id'] == 'user-789'


# =============================================================================
# Test Class: create_portal_session
# =============================================================================

class TestCreatePortalSession:
    """Tests for Stripe customer portal session creation."""

    @patch('utils.stripe_service.get_stripe')
    def test_create_portal_session_success(self, mock_get_stripe):
        """
        Test successful portal session creation.

        Given: Valid customer_id and return_url
        When: create_portal_session is called
        Then: Returns dict with portal_url
        """
        mock_session = MagicMock()
        mock_session.url = 'https://billing.stripe.com/portal_abc'

        mock_stripe = MagicMock()
        mock_stripe.billing_portal.Session.create.return_value = mock_session
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_portal_session

        result = create_portal_session(
            customer_id='cus_portal_123',
            return_url='https://app.com/settings'
        )

        assert result['portal_url'] == 'https://billing.stripe.com/portal_abc'
        mock_stripe.billing_portal.Session.create.assert_called_once_with(
            customer='cus_portal_123',
            return_url='https://app.com/settings'
        )

    @patch('utils.stripe_service.get_stripe')
    def test_create_portal_session_stripe_error_propagates(self, mock_get_stripe):
        """
        Test that Stripe errors propagate up.

        Given: Stripe API raises an error
        When: create_portal_session is called
        Then: Error is propagated
        """
        # Create a proper exception class
        class MockStripeError(Exception):
            pass

        mock_stripe = MagicMock()
        mock_stripe.error.StripeError = MockStripeError
        mock_stripe.billing_portal.Session.create.side_effect = MockStripeError("Invalid customer")
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import create_portal_session

        with pytest.raises(MockStripeError) as exc_info:
            create_portal_session(
                customer_id='cus_invalid',
                return_url='https://app.com/settings'
            )

        assert 'Invalid customer' in str(exc_info.value)


# =============================================================================
# Test Class: get_subscription
# =============================================================================

class TestGetSubscription:
    """Tests for Stripe subscription retrieval."""

    @patch('utils.stripe_service.get_stripe')
    def test_get_subscription_success(self, mock_get_stripe):
        """
        Test successful subscription retrieval.

        Given: Valid subscription_id
        When: get_subscription is called
        Then: Returns normalized subscription dict
        """
        mock_subscription = MagicMock()
        mock_subscription.id = 'sub_test_123'
        mock_subscription.status = 'active'
        mock_subscription.current_period_start = 1704067200
        mock_subscription.current_period_end = 1706745600
        mock_subscription.cancel_at_period_end = False
        mock_subscription.customer = 'cus_test_123'

        mock_stripe = MagicMock()
        mock_stripe.Subscription.retrieve.return_value = mock_subscription
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_subscription

        result = get_subscription('sub_test_123')

        assert result['id'] == 'sub_test_123'
        assert result['status'] == 'active'
        assert result['current_period_start'] == 1704067200
        assert result['current_period_end'] == 1706745600
        assert result['cancel_at_period_end'] is False
        assert result['customer'] == 'cus_test_123'

    @patch('utils.stripe_service.get_stripe')
    def test_get_subscription_not_found_returns_none(self, mock_get_stripe):
        """
        Test that non-existent subscription returns None.

        Given: Subscription_id that doesn't exist in Stripe
        When: get_subscription is called
        Then: Returns None
        """
        mock_stripe = MagicMock()
        mock_stripe.error.InvalidRequestError = type('InvalidRequestError', (Exception,), {})
        mock_stripe.Subscription.retrieve.side_effect = mock_stripe.error.InvalidRequestError()
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_subscription

        result = get_subscription('sub_nonexistent')

        assert result is None

    @patch('utils.stripe_service.get_stripe')
    def test_get_subscription_handles_attribute_error(self, mock_get_stripe):
        """
        Test graceful handling when period attributes are missing.

        Given: Subscription object without period dates
        When: get_subscription is called
        Then: Returns dict with None for period dates
        """
        # Create a custom class to simulate AttributeError on specific attributes
        class MockSubscription:
            id = 'sub_no_period'
            status = 'active'
            cancel_at_period_end = False
            customer = 'cus_test'

            @property
            def current_period_start(self):
                raise AttributeError('no period')

            @property
            def current_period_end(self):
                raise AttributeError('no period')

            def __getitem__(self, key):
                raise KeyError('items')

        mock_stripe = MagicMock()
        mock_stripe.Subscription.retrieve.return_value = MockSubscription()
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_subscription

        result = get_subscription('sub_no_period')

        # Should still return a valid dict with None for missing fields
        assert result['id'] == 'sub_no_period'
        assert result['current_period_start'] is None
        assert result['current_period_end'] is None

    @patch('utils.stripe_service.get_stripe')
    def test_get_subscription_stripe_error_propagates(self, mock_get_stripe):
        """
        Test that non-InvalidRequest Stripe errors propagate.

        Given: Stripe API raises a non-not-found error
        When: get_subscription is called
        Then: Error is propagated
        """
        mock_stripe = MagicMock()
        mock_stripe.error.InvalidRequestError = type('InvalidRequestError', (Exception,), {})
        mock_stripe.error.StripeError = type('StripeError', (Exception,), {})
        mock_stripe.Subscription.retrieve.side_effect = mock_stripe.error.StripeError("API Error")
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_subscription

        with pytest.raises(Exception) as exc_info:
            get_subscription('sub_error')

        assert 'API Error' in str(exc_info.value)


# =============================================================================
# Test Class: get_customer_by_email
# =============================================================================

class TestGetCustomerByEmail:
    """Tests for finding Stripe customers by email."""

    @patch('utils.stripe_service.get_stripe')
    def test_get_customer_by_email_found(self, mock_get_stripe):
        """
        Test finding existing customer by email.

        Given: Email that matches a Stripe customer
        When: get_customer_by_email is called
        Then: Returns customer dict with id, email, name, metadata
        """
        mock_customer = MagicMock()
        mock_customer.id = 'cus_found_123'
        mock_customer.email = 'found@example.com'
        mock_customer.name = 'Found Customer'
        mock_customer.metadata = {'user_id': 'user-123'}

        mock_customers = MagicMock()
        mock_customers.data = [mock_customer]

        mock_stripe = MagicMock()
        mock_stripe.Customer.list.return_value = mock_customers
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_customer_by_email

        result = get_customer_by_email('found@example.com')

        assert result['id'] == 'cus_found_123'
        assert result['email'] == 'found@example.com'
        assert result['name'] == 'Found Customer'
        assert result['metadata'] == {'user_id': 'user-123'}

    @patch('utils.stripe_service.get_stripe')
    def test_get_customer_by_email_not_found(self, mock_get_stripe):
        """
        Test that non-existent customer returns None.

        Given: Email with no matching Stripe customer
        When: get_customer_by_email is called
        Then: Returns None
        """
        mock_customers = MagicMock()
        mock_customers.data = []  # No customers found

        mock_stripe = MagicMock()
        mock_stripe.Customer.list.return_value = mock_customers
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import get_customer_by_email

        result = get_customer_by_email('notfound@example.com')

        assert result is None


# =============================================================================
# Test Class: verify_webhook_signature
# =============================================================================

class TestVerifyWebhookSignature:
    """Tests for Stripe webhook signature verification."""

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_webhook_secret')
    def test_verify_webhook_signature_valid(self, mock_get_secret, mock_get_stripe):
        """
        Test successful signature verification.

        Given: Valid payload and signature
        When: verify_webhook_signature is called
        Then: Returns the verified event object
        """
        mock_get_secret.return_value = 'whsec_test123'

        expected_event = {'id': 'evt_test', 'type': 'checkout.session.completed'}

        mock_stripe = MagicMock()
        mock_stripe.Webhook.construct_event.return_value = expected_event
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import verify_webhook_signature

        result = verify_webhook_signature('{"test": "payload"}', 't=123,v1=abc')

        assert result == expected_event
        mock_stripe.Webhook.construct_event.assert_called_once_with(
            '{"test": "payload"}',
            't=123,v1=abc',
            'whsec_test123'
        )

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_webhook_secret')
    def test_verify_webhook_signature_invalid_raises(self, mock_get_secret, mock_get_stripe):
        """
        Test that invalid signature raises ValueError.

        Given: Invalid signature
        When: verify_webhook_signature is called
        Then: Raises ValueError with 'Invalid webhook signature'
        """
        mock_get_secret.return_value = 'whsec_test123'

        mock_stripe = MagicMock()
        mock_stripe.error.SignatureVerificationError = type('SignatureVerificationError', (Exception,), {})
        mock_stripe.Webhook.construct_event.side_effect = mock_stripe.error.SignatureVerificationError()
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import verify_webhook_signature

        with pytest.raises(ValueError) as exc_info:
            verify_webhook_signature('payload', 'invalid_sig')

        assert 'Invalid webhook signature' in str(exc_info.value)

    @patch('utils.stripe_service.get_stripe')
    @patch('utils.stripe_service.get_stripe_webhook_secret')
    def test_verify_webhook_signature_invalid_payload_raises(self, mock_get_secret, mock_get_stripe):
        """
        Test that malformed payload raises ValueError.

        Given: Malformed JSON payload
        When: verify_webhook_signature is called
        Then: Raises ValueError with 'Invalid webhook payload'
        """
        mock_get_secret.return_value = 'whsec_test123'

        mock_stripe = MagicMock()
        mock_stripe.error.SignatureVerificationError = type('SignatureVerificationError', (Exception,), {})
        mock_stripe.Webhook.construct_event.side_effect = ValueError("No JSON object could be decoded")
        mock_get_stripe.return_value = mock_stripe

        from utils.stripe_service import verify_webhook_signature

        with pytest.raises(ValueError) as exc_info:
            verify_webhook_signature('not json', 'sig')

        assert 'Invalid webhook payload' in str(exc_info.value)
