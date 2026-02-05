"""
Subscription Handler Lambda

Provides endpoints for Stripe subscription management:
- POST /subscription/checkout - Create Stripe Checkout session for Plus upgrade
- POST /subscription/portal - Create Stripe Customer Portal session
- GET /subscription/status - Get current subscription status

Requires JWT authentication for all endpoints.
"""

import json
import logging
import os
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError
from decimal import Decimal

# Import stripe service utilities
from utils.stripe_service import (
    create_checkout_session,
    create_portal_session,
    get_subscription,
    get_customer_by_email,
    TOKEN_LIMIT_PLUS,
)
from utils.token_usage_tracker import TokenUsageTracker

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
USERS_TABLE = os.environ.get('USERS_TABLE') or f'buffett-{ENVIRONMENT}-users'
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'https://buffettgpt.com')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(USERS_TABLE)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle subscription management requests.

    Routes:
        POST /subscription/checkout - Create checkout session
        POST /subscription/portal - Create portal session
        GET /subscription/status - Get subscription status

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('path') or event.get('rawPath', '')

    logger.info(f"Subscription request: {http_method} {path}")

    # Handle OPTIONS preflight requests (no auth required)
    if http_method == 'OPTIONS':
        return _response(200, {'message': 'CORS preflight OK'})

    # Extract user from JWT authorizer context
    user_info = _get_user_from_event(event)
    if not user_info:
        return _response(401, {'error': 'Unauthorized'})

    user_id = user_info.get('user_id')
    email = user_info.get('email')

    # Route request
    if path.endswith('/checkout') and http_method == 'POST':
        return handle_create_checkout(user_id, email, event)
    elif path.endswith('/portal') and http_method == 'POST':
        return handle_create_portal(user_id)
    elif path.endswith('/status') and http_method == 'GET':
        return handle_get_status(user_id)
    else:
        return _response(404, {'error': 'Not found'})


def handle_create_checkout(user_id: str, email: str, event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create Stripe Checkout session for Plus subscription.

    Args:
        user_id: Internal user ID
        email: User email address
        event: API Gateway event (for extracting return URLs)

    Returns:
        API Gateway response with checkout_url
    """
    logger.info(f"Creating checkout session for user {user_id}")

    # Get user record to check existing subscription
    user = _get_user(user_id)
    if user and user.get('subscription_tier') == 'plus':
        subscription_status = user.get('subscription_status')
        if subscription_status in ('active', 'trialing'):
            return _response(400, {
                'error': 'Already subscribed',
                'message': 'You already have an active Plus subscription'
            })

    # Parse request body for optional return URLs
    body = {}
    if event.get('body'):
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            pass

    # Construct success/cancel URLs
    success_url = body.get('success_url') or f"{FRONTEND_URL}?subscription=success"
    cancel_url = body.get('cancel_url') or f"{FRONTEND_URL}?subscription=canceled"

    # Check if user already has a Stripe customer ID
    customer_id = user.get('stripe_customer_id') if user else None

    # If no customer ID, check if one exists for this email
    if not customer_id and email:
        existing_customer = get_customer_by_email(email)
        if existing_customer:
            customer_id = existing_customer['id']
            # Store customer ID on user record
            _update_user_customer_id(user_id, customer_id)

    try:
        result = create_checkout_session(
            user_id=user_id,
            user_email=email,
            success_url=success_url,
            cancel_url=cancel_url,
            customer_id=customer_id
        )
        return _response(200, result)
    except Exception as e:
        logger.error(f"Failed to create checkout session: {str(e)}")
        return _response(500, {'error': 'Failed to create checkout session'})


def handle_create_portal(user_id: str) -> Dict[str, Any]:
    """
    Create Stripe Customer Portal session.

    Allows customers to manage payment methods and cancel subscription.

    Args:
        user_id: Internal user ID

    Returns:
        API Gateway response with portal_url
    """
    logger.info(f"Creating portal session for user {user_id}")

    # Get user's Stripe customer ID
    user = _get_user(user_id)
    if not user:
        return _response(404, {'error': 'User not found'})

    customer_id = user.get('stripe_customer_id')
    if not customer_id:
        return _response(400, {
            'error': 'No subscription found',
            'message': 'You need an active subscription to access the customer portal'
        })

    return_url = f"{FRONTEND_URL}/settings"

    try:
        result = create_portal_session(
            customer_id=customer_id,
            return_url=return_url
        )
        return _response(200, result)
    except Exception as e:
        logger.error(f"Failed to create portal session: {str(e)}")
        return _response(500, {'error': 'Failed to create portal session'})


def handle_get_status(user_id: str) -> Dict[str, Any]:
    """
    Get current subscription status.

    Args:
        user_id: Internal user ID

    Returns:
        API Gateway response with subscription details
    """
    logger.info(f"Getting subscription status for user {user_id}")

    user = _get_user(user_id)
    if not user:
        return _response(200, {
            'subscription_tier': 'free',
            'subscription_status': None,
            'token_limit': 0,
            'has_subscription': False
        })

    subscription_tier = user.get('subscription_tier', 'free')
    subscription_status = user.get('subscription_status')
    stripe_subscription_id = user.get('stripe_subscription_id')

    # Get live subscription details from Stripe if available
    stripe_subscription = None
    if stripe_subscription_id:
        try:
            stripe_subscription = get_subscription(stripe_subscription_id)
        except Exception as e:
            # Log error but continue gracefully - user still sees cached info from DynamoDB
            logger.warning(f"Failed to fetch Stripe subscription {stripe_subscription_id}: {str(e)}")
            stripe_subscription = None

    # Determine token limit based on tier
    token_limit = TOKEN_LIMIT_PLUS if subscription_tier == 'plus' else 0

    # Get token usage data
    token_tracker = TokenUsageTracker()
    usage_data = token_tracker.get_usage(user_id)

    response_data = {
        'subscription_tier': subscription_tier,
        'subscription_status': subscription_status,
        'token_limit': token_limit,
        'has_subscription': subscription_tier == 'plus',
        'cancel_at_period_end': user.get('cancel_at_period_end', False),
        'billing_day': user.get('billing_day'),
        # Token usage data for settings display
        'token_usage': {
            'total_tokens': usage_data.get('total_tokens', 0),
            'token_limit': usage_data.get('token_limit', token_limit),
            'percent_used': usage_data.get('percent_used', 0.0),
            'remaining_tokens': usage_data.get('remaining_tokens', token_limit),
            'request_count': usage_data.get('request_count', 0),
            'reset_date': usage_data.get('reset_date'),
            'subscription_tier': subscription_tier,
        }
    }

    # Add Stripe subscription details if available
    if stripe_subscription:
        response_data['current_period_end'] = stripe_subscription.get('current_period_end')
        response_data['cancel_at_period_end'] = stripe_subscription.get('cancel_at_period_end', False)

    return _response(200, response_data)


# Helper functions

def _get_user_from_event(event: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """Extract user info from JWT authorizer context."""
    # Try different locations for authorizer context
    authorizer = event.get('requestContext', {}).get('authorizer', {})

    # Check lambda context FIRST (HTTP API v2 with Lambda authorizer)
    # This is where the authorizer actually puts the user context
    if 'lambda' in authorizer and isinstance(authorizer['lambda'], dict):
        lambda_ctx = authorizer['lambda']
        user_id = lambda_ctx.get('user_id')
        if user_id:
            return {
                'user_id': str(user_id),
                'email': lambda_ctx.get('email'),
            }

    # Lambda authorizer format with claims
    if 'claims' in authorizer:
        claims = authorizer['claims']
        return {
            'user_id': claims.get('sub') or claims.get('user_id'),
            'email': claims.get('email'),
        }

    # Direct claims format
    if 'sub' in authorizer or 'user_id' in authorizer:
        return {
            'user_id': authorizer.get('sub') or authorizer.get('user_id'),
            'email': authorizer.get('email'),
        }

    # HTTP API JWT authorizer format
    jwt_claims = authorizer.get('jwt', {}).get('claims', {})
    if jwt_claims:
        return {
            'user_id': jwt_claims.get('sub') or jwt_claims.get('user_id'),
            'email': jwt_claims.get('email'),
        }

    return None


def _get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user record from DynamoDB."""
    try:
        response = users_table.get_item(Key={'user_id': user_id})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Failed to get user: {str(e)}")
        return None


def _update_user_customer_id(user_id: str, customer_id: str) -> None:
    """Store Stripe customer ID on user record."""
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET stripe_customer_id = :cid',
            ExpressionAttributeValues={':cid': customer_id}
        )
    except ClientError as e:
        logger.warning(f"Failed to update user customer ID: {str(e)}")


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
        },
        'body': json.dumps(body, cls=DecimalEncoder)
    }
