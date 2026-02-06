"""
Locust HTTP load tests for BuffettGPT Stripe integration (Phase 5).

Two user classes simulate realistic traffic:
- SubscriptionUser: Authenticated users hitting subscription endpoints
- WebhookUser: Stripe sending webhook events at high frequency

Run headless:
    locust -f tests/performance/locustfile.py --headless -u 100 -r 10 -t 60s \
        --host=http://localhost:8000

Run with web UI:
    locust -f tests/performance/locustfile.py --host=http://localhost:8000

Tag-based filtering:
    locust -f tests/performance/locustfile.py --tags subscription --host=...
    locust -f tests/performance/locustfile.py --tags webhook --host=...
"""

import hashlib
import hmac
import json
import logging
import os
import random
import string
import sys
import time
import uuid

from locust import HttpUser, between, events, tag, task

# Add backend root to path for aws_auth imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)

# --- Auth Configuration ---
# When AWS_JWT_SECRET is set, generate real JWT tokens
# When AWS_WEBHOOK_SECRET is set, generate real Stripe signatures
# Otherwise, use existing mock behavior (backward compatible)
AWS_JWT_SECRET = os.environ.get('AWS_JWT_SECRET')
AWS_WEBHOOK_SECRET = os.environ.get('AWS_WEBHOOK_SECRET')

if AWS_JWT_SECRET or AWS_WEBHOOK_SECRET:
    from tests.performance.utils.aws_auth import generate_jwt, generate_stripe_signature


# ---------------------------------------------------------------------------
# Payload helpers (self-contained — does not import Phase 1 files)
# ---------------------------------------------------------------------------

def _rand_id(prefix: str, length: int = 14) -> str:
    """Generate a random Stripe-style ID like ``cus_AbCdEfGh123456``."""
    chars = string.ascii_letters + string.digits
    return f"{prefix}_{''.join(random.choices(chars, k=length))}"


def _make_stripe_signature(payload_bytes: bytes, secret: str = "whsec_test_secret") -> str:
    """Build a ``Stripe-Signature`` header value (``t=…,v1=…``)."""
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.".encode() + payload_bytes
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _checkout_completed_payload(user_id: str | None = None) -> dict:
    user_id = user_id or f"user-{uuid.uuid4().hex[:8]}"
    customer_id = _rand_id("cus")
    subscription_id = _rand_id("sub")
    return {
        "id": _rand_id("evt"),
        "object": "event",
        "type": "checkout.session.completed",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": _rand_id("cs"),
                "object": "checkout.session",
                "client_reference_id": user_id,
                "customer": customer_id,
                "subscription": subscription_id,
                "customer_email": f"{user_id}@test.com",
                "metadata": {"user_id": user_id},
                "mode": "subscription",
                "payment_status": "paid",
                "status": "complete",
            }
        },
    }


def _invoice_paid_payload() -> dict:
    return {
        "id": _rand_id("evt"),
        "object": "event",
        "type": "invoice.payment_succeeded",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": _rand_id("in"),
                "object": "invoice",
                "customer": _rand_id("cus"),
                "subscription": _rand_id("sub"),
                "billing_reason": "subscription_cycle",
                "status": "paid",
                "amount_paid": 999,
                "currency": "usd",
            }
        },
    }


def _subscription_updated_payload() -> dict:
    return {
        "id": _rand_id("evt"),
        "object": "event",
        "type": "customer.subscription.updated",
        "created": int(time.time()),
        "livemode": False,
        "data": {
            "object": {
                "id": _rand_id("sub"),
                "object": "subscription",
                "customer": _rand_id("cus"),
                "status": "active",
                "metadata": {},
                "cancel_at_period_end": False,
            }
        },
    }


# A fixed event ID reused for idempotency/duplicate tests
_DUPLICATE_EVENT_ID = "evt_duplicate_test_fixed_id"


def _duplicate_checkout_payload() -> dict:
    payload = _checkout_completed_payload()
    payload["id"] = _DUPLICATE_EVENT_ID
    return payload


# ---------------------------------------------------------------------------
# Event listeners for failure logging
# ---------------------------------------------------------------------------

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    if exception:
        logger.error(
            "Request FAILED | %s %s | %.1fms | %s",
            request_type,
            name,
            response_time or 0,
            exception,
        )


# ---------------------------------------------------------------------------
# SubscriptionUser — authenticated subscription endpoint traffic
# ---------------------------------------------------------------------------

class SubscriptionUser(HttpUser):
    """Simulates authenticated users calling subscription management endpoints.

    Weighted towards GET /subscription/status (most common real-world call).
    """

    wait_time = between(0.1, 0.5)

    def on_start(self):
        """Set up auth header — real JWT when AWS_JWT_SECRET is set, mock otherwise."""
        self.user_id = f"perf-test-{uuid.uuid4().hex[:12]}"
        if AWS_JWT_SECRET:
            token = generate_jwt(
                user_id=self.user_id,
                email=f"{self.user_id}@buffettgpt.test",
                secret=AWS_JWT_SECRET,
            )
        else:
            token = f"mock-jwt-token-{self.user_id}"
        self.auth_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    @tag("subscription")
    @task(2)
    def create_checkout(self):
        """POST /subscription/checkout — create a Stripe Checkout session."""
        payload = {
            "success_url": "https://buffettgpt.com?subscription=success",
            "cancel_url": "https://buffettgpt.com?subscription=canceled",
        }
        self.client.post(
            "/subscription/checkout",
            json=payload,
            headers=self.auth_headers,
            name="/subscription/checkout",
        )

    @tag("subscription")
    @task(1)
    def create_portal(self):
        """POST /subscription/portal — create a Stripe Customer Portal session."""
        self.client.post(
            "/subscription/portal",
            json={},
            headers=self.auth_headers,
            name="/subscription/portal",
        )

    @tag("subscription")
    @task(5)
    def get_status(self):
        """GET /subscription/status — most common operation."""
        self.client.get(
            "/subscription/status",
            headers=self.auth_headers,
            name="/subscription/status",
        )


# ---------------------------------------------------------------------------
# WebhookUser — high-frequency Stripe webhook delivery
# ---------------------------------------------------------------------------

class WebhookUser(HttpUser):
    """Simulates Stripe sending webhook events at high frequency."""

    wait_time = between(0.05, 0.2)

    def _post_webhook(self, payload: dict, name: str):
        """Helper: POST a webhook payload with a Stripe-Signature header.

        Uses real Stripe signature when AWS_WEBHOOK_SECRET is set,
        otherwise falls back to mock signature.
        """
        body = json.dumps(payload)
        body_bytes = body.encode()
        if AWS_WEBHOOK_SECRET:
            sig = generate_stripe_signature(body, AWS_WEBHOOK_SECRET)
        else:
            sig = _make_stripe_signature(body_bytes)
        self.client.post(
            "/stripe/webhook",
            data=body_bytes,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": sig,
            },
            name=name,
        )

    @tag("webhook")
    @task(3)
    def send_checkout_webhook(self):
        """POST /stripe/webhook — checkout.session.completed."""
        self._post_webhook(
            _checkout_completed_payload(),
            "/stripe/webhook [checkout.completed]",
        )

    @tag("webhook")
    @task(3)
    def send_invoice_paid_webhook(self):
        """POST /stripe/webhook — invoice.payment_succeeded."""
        self._post_webhook(
            _invoice_paid_payload(),
            "/stripe/webhook [invoice.paid]",
        )

    @tag("webhook")
    @task(2)
    def send_subscription_updated_webhook(self):
        """POST /stripe/webhook — customer.subscription.updated."""
        self._post_webhook(
            _subscription_updated_payload(),
            "/stripe/webhook [subscription.updated]",
        )

    @tag("webhook")
    @task(1)
    def send_duplicate_webhook(self):
        """POST /stripe/webhook — duplicate event ID to test idempotency."""
        self._post_webhook(
            _duplicate_checkout_payload(),
            "/stripe/webhook [duplicate]",
        )
