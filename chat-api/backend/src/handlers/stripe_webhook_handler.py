"""
Stripe Webhook Handler Lambda

Processes Stripe webhook events for subscription lifecycle management:
- checkout.session.completed: Activate subscription after successful checkout
- invoice.payment_succeeded: Reset token usage on successful renewal
- invoice.payment_failed: Handle failed payment (set past_due status)
- customer.subscription.deleted: Downgrade user to free tier

Webhook signature verification ensures events are from Stripe.
Idempotency is handled via event ID tracking to prevent duplicate processing.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Import stripe service utilities
from utils.stripe_service import verify_webhook_signature, TOKEN_LIMIT_PLUS

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
USERS_TABLE = os.environ.get('USERS_TABLE', f'buffett-{ENVIRONMENT}-users')
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE', f'buffett-{ENVIRONMENT}-token-usage')
PROCESSED_EVENTS_TABLE = os.environ.get('PROCESSED_EVENTS_TABLE', f'buffett-{ENVIRONMENT}-stripe-events')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(USERS_TABLE)
token_usage_table = dynamodb.Table(TOKEN_USAGE_TABLE)

# Try to initialize processed events table (may not exist yet)
try:
    processed_events_table = dynamodb.Table(PROCESSED_EVENTS_TABLE)
except Exception:
    processed_events_table = None


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle Stripe webhook events.

    Args:
        event: API Gateway event with Stripe webhook payload
        context: Lambda context

    Returns:
        API Gateway response
    """
    logger.info("Received Stripe webhook request")

    # Get raw body and signature header
    body = event.get('body', '')
    headers = event.get('headers', {})

    # Handle case-insensitive headers (API Gateway may lowercase them)
    sig_header = headers.get('stripe-signature') or headers.get('Stripe-Signature', '')

    if not sig_header:
        logger.error("Missing Stripe-Signature header")
        return _response(400, {'error': 'Missing signature header'})

    # Verify webhook signature and construct event
    try:
        stripe_event = verify_webhook_signature(body, sig_header)
    except ValueError as e:
        logger.error(f"Webhook signature verification failed: {str(e)}")
        return _response(400, {'error': str(e)})

    # Check for duplicate event (idempotency)
    event_id = stripe_event.get('id')
    if event_id and _is_event_processed(event_id):
        logger.info(f"Event {event_id} already processed, skipping")
        return _response(200, {'status': 'already_processed'})

    # Route event to handler
    event_type = stripe_event.get('type')
    event_data = stripe_event.get('data', {}).get('object', {})

    logger.info(f"Processing Stripe event: {event_type} (ID: {event_id})")

    handlers = {
        'checkout.session.completed': handle_checkout_completed,
        'invoice.payment_succeeded': handle_invoice_paid,
        'invoice.payment_failed': handle_invoice_failed,
        'customer.subscription.deleted': handle_subscription_deleted,
        'customer.subscription.updated': handle_subscription_updated,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            handler(event_data)
            # Mark event as processed
            _mark_event_processed(event_id, event_type)
            logger.info(f"Successfully processed event: {event_type}")
        except Exception as e:
            logger.error(f"Error handling {event_type}: {str(e)}", exc_info=True)
            # Return 500 so Stripe retries
            return _response(500, {'error': 'Handler error'})
    else:
        logger.info(f"Unhandled event type: {event_type}")

    return _response(200, {'status': 'ok'})


def handle_checkout_completed(session: Dict[str, Any]) -> None:
    """
    Activate subscription after successful checkout.

    Updates user record with:
    - stripe_customer_id
    - stripe_subscription_id
    - subscription_tier = 'plus'
    - subscription_status = 'active'
    - billing_day (from checkout completion date)

    Args:
        session: Stripe Checkout Session object
    """
    user_id = session.get('client_reference_id')
    customer_id = session.get('customer')
    subscription_id = session.get('subscription')
    customer_email = session.get('customer_email') or session.get('customer_details', {}).get('email')

    if not user_id:
        # Try to get user_id from metadata
        metadata = session.get('metadata', {})
        user_id = metadata.get('user_id')

    if not user_id:
        logger.error("No user_id found in checkout session")
        return

    logger.info(f"Activating subscription for user {user_id}, customer {customer_id}")

    now = datetime.now(timezone.utc)
    billing_day = now.day

    # Update user record
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET stripe_customer_id = :customer_id,
                    stripe_subscription_id = :subscription_id,
                    subscription_tier = :tier,
                    subscription_status = :status,
                    billing_day = :billing_day,
                    subscription_activated_at = :activated_at,
                    updated_at = :updated_at
            ''',
            ExpressionAttributeValues={
                ':customer_id': customer_id,
                ':subscription_id': subscription_id,
                ':tier': 'plus',
                ':status': 'active',
                ':billing_day': billing_day,
                ':activated_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            }
        )
        logger.info(f"Updated user {user_id} to Plus tier")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise

    # Initialize token usage for the new billing period
    _initialize_plus_token_usage(user_id, billing_day)


def handle_invoice_paid(invoice: Dict[str, Any]) -> None:
    """
    Handle successful payment - reset token usage for new billing period.

    This is called on subscription renewals, not initial checkout.

    Args:
        invoice: Stripe Invoice object
    """
    subscription_id = invoice.get('subscription')
    customer_id = invoice.get('customer')
    billing_reason = invoice.get('billing_reason')

    # Only handle subscription renewals, not initial subscriptions
    if billing_reason == 'subscription_create':
        logger.info("Skipping invoice.payment_succeeded for initial subscription (handled by checkout)")
        return

    if not subscription_id:
        logger.info("Invoice not related to subscription, skipping")
        return

    logger.info(f"Processing renewal payment for subscription {subscription_id}")

    # Find user by stripe_customer_id
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return

    user_id = user['user_id']
    billing_day = user.get('billing_day', datetime.now(timezone.utc).day)

    # Reset token usage for new billing period
    _initialize_plus_token_usage(user_id, billing_day)

    # Update subscription status to active (in case it was past_due)
    now = datetime.now(timezone.utc)
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET subscription_status = :status,
                    last_payment_at = :payment_at,
                    updated_at = :updated_at
            ''',
            ExpressionAttributeValues={
                ':status': 'active',
                ':payment_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            }
        )
        logger.info(f"Reset token usage for user {user_id}")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise


def handle_invoice_failed(invoice: Dict[str, Any]) -> None:
    """
    Handle failed payment - set subscription to past_due status.

    Users retain access during grace period (configured in Stripe).

    Args:
        invoice: Stripe Invoice object
    """
    subscription_id = invoice.get('subscription')
    customer_id = invoice.get('customer')

    if not subscription_id:
        logger.info("Invoice not related to subscription, skipping")
        return

    logger.info(f"Processing failed payment for subscription {subscription_id}")

    # Find user by stripe_customer_id
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return

    user_id = user['user_id']
    now = datetime.now(timezone.utc)

    # Update subscription status to past_due
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET subscription_status = :status,
                    payment_failed_at = :failed_at,
                    updated_at = :updated_at
            ''',
            ExpressionAttributeValues={
                ':status': 'past_due',
                ':failed_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            }
        )
        logger.info(f"Set user {user_id} subscription to past_due")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise


def handle_subscription_deleted(subscription: Dict[str, Any]) -> None:
    """
    Downgrade user to free tier on subscription cancellation.

    Args:
        subscription: Stripe Subscription object
    """
    subscription_id = subscription.get('id')
    customer_id = subscription.get('customer')

    logger.info(f"Processing subscription deletion: {subscription_id}")

    # Find user by stripe_customer_id
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return

    user_id = user['user_id']
    now = datetime.now(timezone.utc)

    # Downgrade to free tier
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET subscription_tier = :tier,
                    subscription_status = :status,
                    subscription_canceled_at = :canceled_at,
                    updated_at = :updated_at
                REMOVE stripe_subscription_id
            ''',
            ExpressionAttributeValues={
                ':tier': 'free',
                ':status': 'canceled',
                ':canceled_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            }
        )
        logger.info(f"Downgraded user {user_id} to free tier")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise


def handle_subscription_updated(subscription: Dict[str, Any]) -> None:
    """
    Handle subscription updates (status changes, etc.)

    Args:
        subscription: Stripe Subscription object
    """
    subscription_id = subscription.get('id')
    customer_id = subscription.get('customer')
    status = subscription.get('status')
    cancel_at_period_end = subscription.get('cancel_at_period_end', False)

    logger.info(f"Processing subscription update: {subscription_id}, status: {status}")

    # Find user by stripe_customer_id
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return

    user_id = user['user_id']
    now = datetime.now(timezone.utc)

    # Update subscription status
    try:
        update_expr = '''
            SET subscription_status = :status,
                cancel_at_period_end = :cancel_at_end,
                updated_at = :updated_at
        '''
        expr_values = {
            ':status': status,
            ':cancel_at_end': cancel_at_period_end,
            ':updated_at': now.isoformat().replace('+00:00', 'Z'),
        }

        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values
        )
        logger.info(f"Updated subscription status for user {user_id} to {status}")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise


# Helper functions

def _find_user_by_customer_id(customer_id: str) -> Optional[Dict[str, Any]]:
    """Find user record by Stripe customer ID using GSI."""
    try:
        # First try GSI if available
        response = users_table.query(
            IndexName='stripe-customer-index',
            KeyConditionExpression='stripe_customer_id = :cid',
            ExpressionAttributeValues={':cid': customer_id},
            Limit=1
        )
        items = response.get('Items', [])
        if items:
            return items[0]
    except ClientError as e:
        # GSI may not exist, fall back to scan
        if 'ValidationException' not in str(e):
            logger.warning(f"GSI query failed, falling back to scan: {str(e)}")

    # Fallback: scan (less efficient but works without GSI)
    try:
        response = users_table.scan(
            FilterExpression='stripe_customer_id = :cid',
            ExpressionAttributeValues={':cid': customer_id},
            Limit=1
        )
        items = response.get('Items', [])
        return items[0] if items else None
    except ClientError as e:
        logger.error(f"Failed to find user by customer ID: {str(e)}")
        return None


def _initialize_plus_token_usage(user_id: str, billing_day: int) -> None:
    """Initialize token usage record for new Plus billing period."""
    from utils.token_usage_tracker import TokenUsageTracker

    tracker = TokenUsageTracker()
    billing_period, period_start, period_end = tracker.get_current_billing_period(billing_day)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    try:
        token_usage_table.put_item(
            Item={
                'user_id': user_id,
                'billing_period': billing_period,
                'billing_day': billing_day,
                'billing_period_start': period_start,
                'billing_period_end': period_end,
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': 0,
                'request_count': 0,
                'token_limit': TOKEN_LIMIT_PLUS,
                'reset_date': period_end,
                'subscription_tier': 'plus',
                'subscribed_at': now,
            },
            ConditionExpression='attribute_not_exists(user_id) OR attribute_not_exists(billing_period)'
        )
        logger.info(f"Initialized Plus token usage for user {user_id}, period {billing_period}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # Record already exists, update token_limit instead
            token_usage_table.update_item(
                Key={'user_id': user_id, 'billing_period': billing_period},
                UpdateExpression='SET token_limit = :limit, subscription_tier = :tier',
                ExpressionAttributeValues={
                    ':limit': TOKEN_LIMIT_PLUS,
                    ':tier': 'plus'
                }
            )
            logger.info(f"Updated existing token usage for user {user_id}")
        else:
            logger.error(f"Failed to initialize token usage: {str(e)}")
            raise


def _is_event_processed(event_id: str) -> bool:
    """Check if webhook event has already been processed."""
    if not processed_events_table:
        return False

    try:
        response = processed_events_table.get_item(
            Key={'event_id': event_id}
        )
        return 'Item' in response
    except ClientError:
        return False


def _mark_event_processed(event_id: str, event_type: str) -> None:
    """Mark webhook event as processed for idempotency."""
    if not processed_events_table or not event_id:
        return

    try:
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        # TTL: 7 days
        ttl = int(datetime.now(timezone.utc).timestamp()) + (7 * 24 * 60 * 60)

        processed_events_table.put_item(
            Item={
                'event_id': event_id,
                'event_type': event_type,
                'processed_at': now,
                'ttl': ttl
            }
        )
    except ClientError as e:
        logger.warning(f"Failed to mark event as processed: {str(e)}")


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
        },
        'body': json.dumps(body)
    }
