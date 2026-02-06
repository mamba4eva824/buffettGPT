"""
Mock Stripe event generators for performance testing.

Each generator returns a realistic Stripe webhook event dict matching the
payload structure consumed by stripe_webhook_handler.py.
"""

import random
import string
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _rand_id(prefix: str, length: int = 14) -> str:
    """Generate a random Stripe-style ID like 'cus_AbCdEfGh123456'."""
    chars = string.ascii_letters + string.digits
    return f"{prefix}_{''.join(random.choices(chars, k=length))}"


def _event_wrapper(event_type: str, data_object: Dict[str, Any], event_id: Optional[str] = None) -> Dict[str, Any]:
    """Wrap a data object in a full Stripe event envelope."""
    return {
        'id': event_id or _rand_id('evt'),
        'object': 'event',
        'api_version': '2023-10-16',
        'created': int(time.time()),
        'type': event_type,
        'livemode': False,
        'pending_webhooks': 1,
        'request': {'id': _rand_id('req'), 'idempotency_key': None},
        'data': {
            'object': data_object,
        },
    }


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def generate_checkout_completed(
    user_id: str,
    customer_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a ``checkout.session.completed`` event.

    Args:
        user_id: The ``client_reference_id`` linking back to our user.
        customer_id: Stripe customer ID (auto-generated if omitted).
        subscription_id: Stripe subscription ID (auto-generated if omitted).
        event_id: Override event ID for idempotency testing.
    """
    customer_id = customer_id or _rand_id('cus')
    subscription_id = subscription_id or _rand_id('sub')

    session = {
        'id': _rand_id('cs'),
        'object': 'checkout.session',
        'client_reference_id': user_id,
        'customer': customer_id,
        'subscription': subscription_id,
        'customer_email': f'{user_id}@test.com',
        'customer_details': {'email': f'{user_id}@test.com'},
        'metadata': {'user_id': user_id},
        'mode': 'subscription',
        'payment_status': 'paid',
        'status': 'complete',
        'success_url': 'https://buffettgpt.test/success',
        'cancel_url': 'https://buffettgpt.test/cancel',
    }

    return _event_wrapper('checkout.session.completed', session, event_id=event_id)


# ---------------------------------------------------------------------------
# Subscription lifecycle
# ---------------------------------------------------------------------------

def generate_subscription_created(
    customer_id: str,
    subscription_id: Optional[str] = None,
    metadata: Optional[Dict[str, str]] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a ``customer.subscription.created`` event."""
    subscription_id = subscription_id or _rand_id('sub')
    now = int(time.time())

    subscription = {
        'id': subscription_id,
        'object': 'subscription',
        'customer': customer_id,
        'status': 'active',
        'metadata': metadata or {},
        'current_period_start': now,
        'current_period_end': now + 30 * 86400,
        'items': {
            'data': [{
                'id': _rand_id('si'),
                'price': {'id': _rand_id('price'), 'product': _rand_id('prod')},
                'quantity': 1,
            }],
        },
        'cancel_at_period_end': False,
        'created': now,
        'start_date': now,
    }

    return _event_wrapper('customer.subscription.created', subscription, event_id=event_id)


def generate_subscription_updated(
    customer_id: str,
    subscription_id: Optional[str] = None,
    status: str = 'active',
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a ``customer.subscription.updated`` event."""
    subscription_id = subscription_id or _rand_id('sub')
    now = int(time.time())

    subscription = {
        'id': subscription_id,
        'object': 'subscription',
        'customer': customer_id,
        'status': status,
        'metadata': {},
        'current_period_start': now,
        'current_period_end': now + 30 * 86400,
        'cancel_at_period_end': False,
        'created': now - 86400,
    }

    return _event_wrapper('customer.subscription.updated', subscription, event_id=event_id)


def generate_subscription_deleted(
    customer_id: str,
    subscription_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a ``customer.subscription.deleted`` event."""
    subscription_id = subscription_id or _rand_id('sub')
    now = int(time.time())

    subscription = {
        'id': subscription_id,
        'object': 'subscription',
        'customer': customer_id,
        'status': 'canceled',
        'metadata': {},
        'current_period_start': now - 30 * 86400,
        'current_period_end': now,
        'cancel_at_period_end': False,
        'canceled_at': now,
        'created': now - 60 * 86400,
    }

    return _event_wrapper('customer.subscription.deleted', subscription, event_id=event_id)


# ---------------------------------------------------------------------------
# Invoice events
# ---------------------------------------------------------------------------

def generate_invoice_paid(
    customer_id: str,
    subscription_id: Optional[str] = None,
    billing_reason: str = 'subscription_cycle',
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an ``invoice.payment_succeeded`` event."""
    subscription_id = subscription_id or _rand_id('sub')
    now = int(time.time())

    invoice = {
        'id': _rand_id('in'),
        'object': 'invoice',
        'customer': customer_id,
        'subscription': subscription_id,
        'billing_reason': billing_reason,
        'status': 'paid',
        'amount_paid': 999,
        'currency': 'usd',
        'period_start': now - 30 * 86400,
        'period_end': now,
        'created': now,
    }

    return _event_wrapper('invoice.payment_succeeded', invoice, event_id=event_id)


def generate_invoice_failed(
    customer_id: str,
    subscription_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate an ``invoice.payment_failed`` event."""
    subscription_id = subscription_id or _rand_id('sub')
    now = int(time.time())

    invoice = {
        'id': _rand_id('in'),
        'object': 'invoice',
        'customer': customer_id,
        'subscription': subscription_id,
        'billing_reason': 'subscription_cycle',
        'status': 'open',
        'amount_due': 999,
        'amount_paid': 0,
        'currency': 'usd',
        'attempt_count': 1,
        'next_payment_attempt': now + 3 * 86400,
        'created': now,
    }

    return _event_wrapper('invoice.payment_failed', invoice, event_id=event_id)


# ---------------------------------------------------------------------------
# Random event generator
# ---------------------------------------------------------------------------

_GENERATORS = [
    lambda: generate_checkout_completed(user_id=f'user-{uuid.uuid4().hex[:8]}'),
    lambda: generate_subscription_created(customer_id=_rand_id('cus'), metadata={'user_id': f'user-{uuid.uuid4().hex[:8]}'}),
    lambda: generate_subscription_updated(customer_id=_rand_id('cus')),
    lambda: generate_subscription_deleted(customer_id=_rand_id('cus')),
    lambda: generate_invoice_paid(customer_id=_rand_id('cus')),
    lambda: generate_invoice_failed(customer_id=_rand_id('cus')),
]


def generate_random_event() -> Dict[str, Any]:
    """Return a random event type with a valid payload."""
    return random.choice(_GENERATORS)()
