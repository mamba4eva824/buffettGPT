"""
Authentication utilities for AWS dev environment load testing.
Generates real JWT tokens and Stripe webhook signatures using secrets
fetched from AWS Secrets Manager.
"""

import jwt          # PyJWT (already in requirements.txt)
import time
import hmac
import hashlib
import json
import boto3
from functools import lru_cache


@lru_cache(maxsize=8)
def fetch_secret(secret_id: str, region: str = 'us-east-1') -> str:
    """Fetch a secret value from AWS Secrets Manager. Cached per session."""
    client = boto3.client('secretsmanager', region_name=region)
    response = client.get_secret_value(SecretId=secret_id)
    return response['SecretString']


def generate_jwt(
    user_id: str,
    email: str,
    secret: str,
    subscription_tier: str = 'free',
    name: str = 'Perf Test User',
    expiry_hours: int = 1
) -> str:
    """
    Generate a real HS256 JWT token matching the format used by auth_callback.py.

    The JWT payload matches what auth_verify.py expects:
    - user_id, email, name, subscription_tier
    - exp (expiry), iat (issued at), iss (issuer)
    """
    now = int(time.time())
    payload = {
        'user_id': user_id,
        'email': email,
        'name': name,
        'subscription_tier': subscription_tier,
        'exp': now + (expiry_hours * 3600),
        'iat': now,
        'iss': 'buffett-chat-api'
    }
    return jwt.encode(payload, secret, algorithm='HS256')


def generate_stripe_signature(payload: str, secret: str) -> str:
    """
    Generate a valid Stripe webhook signature (v1) for the given payload.

    Stripe signature format: t=<timestamp>,v1=<hmac_sha256>
    The HMAC is computed over: "<timestamp>.<payload>"
    """
    timestamp = str(int(time.time()))
    signed_payload = f"{timestamp}.{payload}"
    signature = hmac.new(
        secret.encode('utf-8'),
        signed_payload.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={signature}"
