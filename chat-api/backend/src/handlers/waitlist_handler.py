"""
Waitlist Handler Lambda

Provides endpoints for viral waitlist management:
- POST /waitlist/signup - Sign up for the waitlist with optional referral code
- GET /waitlist/status - Get waitlist position and referral dashboard

No JWT authentication required (email-based).
"""

import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
WAITLIST_TABLE = os.environ.get('WAITLIST_TABLE', f'waitlist-{ENVIRONMENT}-buffett')
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
waitlist_table = dynamodb.Table(WAITLIST_TABLE)

# Referral tier definitions
REFERRAL_TIERS = [
    {"name": "Early Access", "threshold": 1, "reward": "Skip the waitlist"},
    {"name": "1 Month Free Plus", "threshold": 3, "reward": "1 month free Plus subscription"},
    {"name": "3 Months Free Plus", "threshold": 10, "reward": "3 months free Plus subscription"},
]

# Characters for referral code generation (ambiguous chars removed)
REFERRAL_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

# Rate limit: max signups per IP per hour
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds

# Disposable email domains to reject
DISPOSABLE_DOMAINS = {
    'mailinator.com', 'guerrillamail.com', 'tempmail.com', 'throwaway.email',
    'yopmail.com', 'sharklasers.com', 'guerrillamailblock.com', 'grr.la',
    'dispostable.com', 'mailnesia.com', 'maildrop.cc', 'temp-mail.org',
    'fakeinbox.com', 'trashmail.com', 'getnada.com',
}

# Email validation regex
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle waitlist requests.

    Routes:
        POST /waitlist/signup - Sign up for waitlist
        GET /waitlist/status - Get position and referral dashboard
    """
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('path') or event.get('rawPath', '')

    logger.info(f"Waitlist request: {http_method} {path}")

    if http_method == 'OPTIONS':
        return _response(200, {'message': 'CORS preflight OK'})

    if path.endswith('/signup') and http_method == 'POST':
        return handle_signup(event)
    elif path.endswith('/status') and http_method == 'GET':
        return handle_status(event)
    else:
        return _response(404, {'error': 'Not found'})


def handle_signup(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle waitlist signup.

    Creates a new waitlist entry with a unique referral code.
    Optionally credits the referrer if a referral_code is provided.
    """
    # Parse request body
    body = {}
    if event.get('body'):
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            return _response(400, {'error': 'Invalid JSON body'})

    email = body.get('email', '').strip().lower()
    referral_code = body.get('referral_code', '').strip().upper() if body.get('referral_code') else None

    # Validate email
    if not email:
        return _response(400, {'error': 'Email is required'})

    if not EMAIL_REGEX.match(email):
        return _response(400, {'error': 'Invalid email format'})

    domain = email.split('@')[1]
    if domain in DISPOSABLE_DOMAINS:
        return _response(400, {'error': 'Please use a non-disposable email address'})

    # Get client IP for rate limiting
    ip_address = _get_client_ip(event)

    # Check rate limit
    if not _check_rate_limit(ip_address):
        return _response(429, {'error': 'Too many signups. Please try again later.'})

    # Generate unique referral code for this user
    new_referral_code = _generate_referral_code()

    # Validate referral code if provided
    referrer = None
    if referral_code:
        referrer = _lookup_referrer(referral_code)
        if not referrer:
            logger.warning(f"Invalid referral code: {referral_code}")
            referral_code = None  # Ignore invalid code, don't block signup
        elif referrer['email'] == email:
            logger.warning(f"Self-referral attempt: {email}")
            referral_code = None  # Cannot refer yourself

    # Create waitlist entry
    now = datetime.now(timezone.utc).isoformat()
    item = {
        'email': email,
        'referral_code': new_referral_code,
        'referral_count': 0,
        'status': 'waitlisted',
        'created_at': now,
        'ip_address': ip_address,
    }
    if referral_code:
        item['referred_by_code'] = referral_code

    try:
        waitlist_table.put_item(
            Item=item,
            ConditionExpression='attribute_not_exists(email)',
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # Email already registered — return their existing info
            existing = _get_waitlist_entry(email)
            if existing:
                return _response(409, {
                    'error': 'Email already registered',
                    'referral_code': existing.get('referral_code'),
                    'referral_count': existing.get('referral_count', 0),
                    'status': existing.get('status'),
                })
            return _response(409, {'error': 'Email already registered'})
        logger.error(f"Failed to create waitlist entry: {e}")
        return _response(500, {'error': 'Failed to sign up. Please try again.'})

    # Credit the referrer if valid
    if referral_code and referrer:
        _credit_referrer(referrer['email'])

    # Record rate limit hit
    _record_rate_limit(ip_address)

    # Calculate position
    position = _get_queue_position(now)

    return _response(201, {
        'email': email,
        'referral_code': new_referral_code,
        'position': position,
        'referral_count': 0,
        'status': 'waitlisted',
        'referral_link': f"{FRONTEND_URL}?ref={new_referral_code}",
        'tiers': REFERRAL_TIERS,
        'message': "You're on the waitlist!",
    })


def handle_status(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get waitlist status and referral dashboard.

    Requires email + referral_code as lightweight auth.
    """
    params = event.get('queryStringParameters') or {}
    email = params.get('email', '').strip().lower()
    code = params.get('code', '').strip().upper()

    if not email or not code:
        return _response(400, {'error': 'Both email and code parameters are required'})

    # Fetch entry
    entry = _get_waitlist_entry(email)
    if not entry:
        return _response(404, {'error': 'Email not found on waitlist'})

    # Verify referral code matches (lightweight auth)
    if entry.get('referral_code') != code:
        return _response(403, {'error': 'Invalid code for this email'})

    referral_count = int(entry.get('referral_count', 0))
    tier_info = _get_tier_info(referral_count)
    position = _get_queue_position(entry['created_at'])

    return _response(200, {
        'email': email,
        'referral_code': entry['referral_code'],
        'position': position,
        'referral_count': referral_count,
        'status': entry.get('status', 'waitlisted'),
        'current_tier': tier_info['current_tier'],
        'next_tier': tier_info['next_tier'],
        'referral_link': f"{FRONTEND_URL}?ref={entry['referral_code']}",
        'tiers': REFERRAL_TIERS,
    })


# ================================================
# Helper Functions
# ================================================

def _generate_referral_code() -> str:
    """Generate a unique branded referral code like BUFF-A3X9."""
    for _ in range(10):  # Retry on collision
        suffix = ''.join(secrets.choice(REFERRAL_CODE_CHARS) for _ in range(4))
        code = f"BUFF-{suffix}"
        # Check uniqueness via GSI
        existing = _lookup_referrer(code)
        if not existing:
            return code
    # Fallback: use 6 chars if 4-char space is crowded
    suffix = ''.join(secrets.choice(REFERRAL_CODE_CHARS) for _ in range(6))
    return f"BUFF-{suffix}"


def _lookup_referrer(referral_code: str) -> Optional[Dict[str, Any]]:
    """Look up a waitlist entry by referral code via GSI."""
    try:
        response = waitlist_table.query(
            IndexName='referral-code-index',
            KeyConditionExpression='referral_code = :code',
            ExpressionAttributeValues={':code': referral_code},
            Limit=1,
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except ClientError as e:
        logger.error(f"Failed to lookup referral code: {e}")
        return None


def _credit_referrer(referrer_email: str) -> None:
    """Increment referrer's referral_count and update status if threshold met."""
    try:
        response = waitlist_table.update_item(
            Key={'email': referrer_email},
            UpdateExpression='SET referral_count = if_not_exists(referral_count, :zero) + :one',
            ExpressionAttributeValues={':zero': 0, ':one': 1},
            ReturnValues='UPDATED_NEW',
        )
        new_count = int(response['Attributes'].get('referral_count', 0))

        # Update status to early_access if they hit the first tier
        if new_count >= 1:
            waitlist_table.update_item(
                Key={'email': referrer_email},
                UpdateExpression='SET #s = :status',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={':status': 'early_access', ':waitlisted': 'waitlisted'},
                ConditionExpression='#s = :waitlisted',
            )
    except ClientError as e:
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
            logger.error(f"Failed to credit referrer: {e}")


def _get_waitlist_entry(email: str) -> Optional[Dict[str, Any]]:
    """Fetch a waitlist entry by email."""
    try:
        response = waitlist_table.get_item(Key={'email': email})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Failed to get waitlist entry: {e}")
        return None


def _get_queue_position(created_at: str) -> int:
    """
    Calculate queue position based on creation timestamp.

    Counts waitlisted users who signed up before this user.
    Acceptable performance for <50K records.
    """
    try:
        response = waitlist_table.scan(
            FilterExpression='created_at < :ts AND #s = :status',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':ts': created_at,
                ':status': 'waitlisted',
            },
            Select='COUNT',
        )
        return response['Count'] + 1
    except ClientError as e:
        logger.error(f"Failed to calculate queue position: {e}")
        return 0


def _get_tier_info(referral_count: int) -> Dict[str, Any]:
    """Determine current and next referral tier based on count."""
    current_tier = None
    next_tier = None

    for tier in REFERRAL_TIERS:
        if referral_count >= tier['threshold']:
            current_tier = tier
        elif next_tier is None:
            next_tier = {
                **tier,
                'referrals_needed': tier['threshold'] - referral_count,
            }

    return {'current_tier': current_tier, 'next_tier': next_tier}


def _get_client_ip(event: Dict[str, Any]) -> str:
    """Extract client IP from API Gateway event."""
    # HTTP API v2 format
    source_ip = event.get('requestContext', {}).get('http', {}).get('sourceIp', '')
    if not source_ip:
        # REST API format
        source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp', '')
    return source_ip or 'unknown'


def _check_rate_limit(ip_address: str) -> bool:
    """Check if IP is under the signup rate limit."""
    if ip_address == 'unknown':
        return True

    rate_key = f"rate:{ip_address}"
    try:
        response = waitlist_table.get_item(Key={'email': rate_key})
        item = response.get('Item')
        if item:
            count = int(item.get('referral_count', 0))  # Reusing referral_count field for count
            if count >= RATE_LIMIT_MAX:
                return False
        return True
    except ClientError:
        return True  # Allow on error


def _record_rate_limit(ip_address: str) -> None:
    """Record a signup for rate limiting purposes."""
    if ip_address == 'unknown':
        return

    rate_key = f"rate:{ip_address}"
    ttl_value = int(time.time()) + RATE_LIMIT_WINDOW

    try:
        waitlist_table.update_item(
            Key={'email': rate_key},
            UpdateExpression='SET referral_count = if_not_exists(referral_count, :zero) + :one, #t = :ttl, #s = :status',
            ExpressionAttributeNames={'#t': 'ttl', '#s': 'status'},
            ExpressionAttributeValues={
                ':zero': 0,
                ':one': 1,
                ':ttl': ttl_value,
                ':status': 'rate_limit',
            },
        )
    except ClientError as e:
        logger.warning(f"Failed to record rate limit: {e}")


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response with CORS headers."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        },
        'body': json.dumps(body, cls=DecimalEncoder),
    }
