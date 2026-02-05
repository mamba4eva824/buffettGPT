"""
Stripe Service Utility for Lambda Handlers

Provides:
- Secret fetching from AWS Secrets Manager
- Stripe client initialization with lazy loading
- Checkout session creation
- Customer portal session creation
- Subscription management helpers

Secrets follow the naming convention: {service}-{key-type}-{env}
"""

import os
import logging
from functools import lru_cache
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Secret names following the convention: {service}-{key-type}-{env}
STRIPE_SECRET_KEY_NAME = f"stripe-secret-key-{ENVIRONMENT}"
STRIPE_WEBHOOK_SECRET_NAME = f"stripe-webhook-secret-{ENVIRONMENT}"
STRIPE_PLUS_PRICE_ID_NAME = f"stripe-plus-price-id-{ENVIRONMENT}"

# Token limits for subscription tiers (from environment or defaults)
TOKEN_LIMIT_PLUS = int(os.environ.get('TOKEN_LIMIT_PLUS', '2000000'))
TOKEN_LIMIT_FREE = int(os.environ.get('TOKEN_LIMIT_FREE', '100000'))

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')


@lru_cache(maxsize=4)
def get_secret(secret_name: str) -> str:
    """
    Fetch a secret from Secrets Manager with caching.

    Args:
        secret_name: Name of the secret (e.g., 'stripe-secret-key-dev')

    Returns:
        Secret string value

    Raises:
        ValueError: If secret not found
        ClientError: If AWS API call fails
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        return response['SecretString']
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ResourceNotFoundException':
            logger.error(f"Secret '{secret_name}' not found in Secrets Manager")
            raise ValueError(f"Secret '{secret_name}' not found")
        logger.error(f"Failed to fetch secret '{secret_name}': {str(e)}")
        raise


def get_stripe_secret_key() -> str:
    """Get Stripe API secret key (sk_test_xxx or sk_live_xxx)."""
    return get_secret(STRIPE_SECRET_KEY_NAME)


def get_stripe_webhook_secret() -> str:
    """Get Stripe webhook signing secret (whsec_xxx)."""
    return get_secret(STRIPE_WEBHOOK_SECRET_NAME)


def get_stripe_plus_price_id() -> str:
    """Get Stripe Plus plan price ID (price_xxx)."""
    return get_secret(STRIPE_PLUS_PRICE_ID_NAME)


# Stripe module with lazy initialization
_stripe_module = None


def get_stripe():
    """
    Get initialized Stripe module.

    Lazy loads the secret key on first call and caches the module.

    Returns:
        Initialized stripe module
    """
    global _stripe_module
    import stripe

    if _stripe_module is None:
        stripe.api_key = get_stripe_secret_key()
        _stripe_module = stripe
        logger.info("Stripe client initialized")

    return _stripe_module


def create_checkout_session(
    user_id: str,
    user_email: str,
    success_url: str,
    cancel_url: str,
    customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a Stripe Checkout Session for Plus subscription.

    Args:
        user_id: Internal user ID (stored in client_reference_id)
        user_email: User's email for Stripe customer
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels
        customer_id: Optional existing Stripe customer ID

    Returns:
        Dictionary with checkout_url and session_id
    """
    stripe = get_stripe()
    price_id = get_stripe_plus_price_id()

    session_params = {
        'mode': 'subscription',
        'payment_method_types': ['card'],
        'line_items': [{
            'price': price_id,
            'quantity': 1,
        }],
        'success_url': success_url,
        'cancel_url': cancel_url,
        'client_reference_id': user_id,
        'metadata': {
            'user_id': user_id,
            'environment': ENVIRONMENT,
        },
    }

    # Use existing customer or create new one
    if customer_id:
        session_params['customer'] = customer_id
    else:
        session_params['customer_email'] = user_email

    try:
        session = stripe.checkout.Session.create(**session_params)
        logger.info(f"Created checkout session for user {user_id}: {session.id}")
        return {
            'checkout_url': session.url,
            'session_id': session.id
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {str(e)}")
        raise


def create_portal_session(
    customer_id: str,
    return_url: str
) -> Dict[str, Any]:
    """
    Create a Stripe Customer Portal session.

    Allows customers to manage their subscription (update payment, cancel, etc.)

    Args:
        customer_id: Stripe customer ID
        return_url: URL to return to after portal session

    Returns:
        Dictionary with portal_url
    """
    stripe = get_stripe()

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        logger.info(f"Created portal session for customer {customer_id}")
        return {
            'portal_url': session.url
        }
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating portal session: {str(e)}")
        raise


def get_subscription(subscription_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a Stripe subscription.

    Args:
        subscription_id: Stripe subscription ID

    Returns:
        Subscription object or None if not found
    """
    stripe = get_stripe()

    try:
        subscription = stripe.Subscription.retrieve(subscription_id)

        # In newer Stripe API versions, period dates may be on subscription items
        # Use try/except since Stripe SDK raises AttributeError for missing fields
        current_period_start = None
        current_period_end = None

        # Try top-level first (older API versions)
        try:
            current_period_start = subscription.current_period_start
        except AttributeError:
            pass

        try:
            current_period_end = subscription.current_period_end
        except AttributeError:
            pass

        # Fall back to subscription items (newer API versions)
        if current_period_start is None or current_period_end is None:
            try:
                # Access items as a StripeObject property, not dict.items()
                sub_items = subscription['items']
                if sub_items and sub_items.data:
                    first_item = sub_items.data[0]
                    if current_period_start is None:
                        try:
                            current_period_start = first_item.current_period_start
                        except AttributeError:
                            pass
                    if current_period_end is None:
                        try:
                            current_period_end = first_item.current_period_end
                        except AttributeError:
                            pass
            except (KeyError, TypeError):
                pass

        return {
            'id': subscription.id,
            'status': subscription.status,
            'current_period_start': current_period_start,
            'current_period_end': current_period_end,
            'cancel_at_period_end': subscription.cancel_at_period_end,
            'customer': subscription.customer,
        }
    except stripe.error.InvalidRequestError:
        logger.warning(f"Subscription {subscription_id} not found")
        return None
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error retrieving subscription: {str(e)}")
        raise


def get_customer_by_email(email: str) -> Optional[Dict[str, Any]]:
    """
    Find a Stripe customer by email.

    Args:
        email: Customer email address

    Returns:
        Customer object or None if not found
    """
    stripe = get_stripe()

    try:
        customers = stripe.Customer.list(email=email, limit=1)
        if customers.data:
            customer = customers.data[0]
            return {
                'id': customer.id,
                'email': customer.email,
                'name': customer.name,
                'metadata': dict(customer.metadata) if customer.metadata else {},
            }
        return None
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error searching customer: {str(e)}")
        raise


def verify_webhook_signature(payload: str, sig_header: str) -> Dict[str, Any]:
    """
    Verify Stripe webhook signature and construct event.

    Args:
        payload: Raw request body
        sig_header: Stripe-Signature header value

    Returns:
        Verified webhook event object

    Raises:
        ValueError: If signature verification fails
    """
    stripe = get_stripe()
    webhook_secret = get_stripe_webhook_secret()

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            webhook_secret
        )
        return event
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        raise ValueError("Invalid webhook signature")
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {str(e)}")
        raise ValueError("Invalid webhook payload")
