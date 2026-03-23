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

import calendar
import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import boto3
from botocore.exceptions import ClientError

# Import stripe service utilities
from utils.stripe_service import verify_webhook_signature, TOKEN_LIMIT_PLUS, TOKEN_LIMIT_FREE

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
USERS_TABLE = os.environ.get('USERS_TABLE', f'buffett-{ENVIRONMENT}-users')
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE', f'buffett-{ENVIRONMENT}-token-usage')
PROCESSED_EVENTS_TABLE = os.environ.get('PROCESSED_EVENTS_TABLE', f'buffett-{ENVIRONMENT}-stripe-events')
WAITLIST_TABLE = os.environ.get('WAITLIST_TABLE', f'waitlist-{ENVIRONMENT}-buffett')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(USERS_TABLE)
token_usage_table = dynamodb.Table(TOKEN_USAGE_TABLE)
waitlist_table = dynamodb.Table(WAITLIST_TABLE)

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
        return _response(400, {'error': 'Webhook verification failed'})

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
        'customer.subscription.created': handle_subscription_created,
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

    # Verify user exists before updating to prevent creating incomplete records
    existing_user = _get_user(user_id)
    if not existing_user:
        logger.error(f"User {user_id} not found in database - cannot activate subscription without existing user record")
        raise ValueError(f"User {user_id} does not exist")

    now = datetime.now(timezone.utc)
    billing_day = now.day

    # Determine subscription status: trialing if referral trial was applied
    checkout_metadata = session.get('metadata', {})
    referral_trial_days = checkout_metadata.get('referral_trial_days')
    subscription_status = 'trialing' if referral_trial_days else 'active'

    # Update user record - uses conditional expression to ensure user exists
    # This preserves existing attributes (email, name, picture, last_login)
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
                ':status': subscription_status,
                ':billing_day': billing_day,
                ':activated_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            },
            ConditionExpression='attribute_exists(user_id)'
        )
        logger.info(f"Updated user {user_id} to Plus tier (status: {subscription_status})")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.error(f"User {user_id} not found - cannot create incomplete user record via webhook")
            raise ValueError(f"User {user_id} does not exist")
        logger.error(f"Failed to update user record: {str(e)}")
        raise

    # Initialize token usage for the new billing period
    _initialize_plus_token_usage(user_id, billing_day)

    # Mark referral reward as claimed if this was a referral trial checkout
    referral_email = checkout_metadata.get('referral_email')
    if referral_trial_days and referral_email:
        _mark_referral_claimed(referral_email, int(referral_trial_days), user_id)


def handle_subscription_created(subscription: Dict[str, Any]) -> None:
    """
    Activate subscription created via API (not checkout flow).

    This handles subscriptions created directly via Stripe API with user_id in metadata.
    For checkout-created subscriptions, handle_checkout_completed is used instead.

    Args:
        subscription: Stripe Subscription object
    """
    subscription_id = subscription.get('id')
    customer_id = subscription.get('customer')
    status = subscription.get('status')
    metadata = subscription.get('metadata', {})
    user_id = metadata.get('user_id')

    if not user_id:
        # Try to find existing user by customer_id
        user = _find_user_by_customer_id(customer_id)
        if user:
            user_id = user.get('user_id')

    if not user_id:
        logger.warning(f"No user_id found for subscription {subscription_id}, skipping activation")
        return

    # Verify user exists before updating to prevent creating incomplete records
    existing_user = _get_user(user_id)
    if not existing_user:
        logger.error(f"User {user_id} not found in database - cannot activate subscription without existing user record")
        raise ValueError(f"User {user_id} does not exist")

    logger.info(f"Activating subscription for user {user_id}, subscription {subscription_id}")

    now = datetime.now(timezone.utc)
    billing_day = now.day

    # Update user record - uses conditional expression to ensure user exists
    # This preserves existing attributes (email, name, picture, last_login)
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
                ':status': status,
                ':billing_day': billing_day,
                ':activated_at': now.isoformat().replace('+00:00', 'Z'),
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            },
            ConditionExpression='attribute_exists(user_id)'
        )
        logger.info(f"Updated user {user_id} to Plus tier via subscription.created")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.error(f"User {user_id} not found - cannot create incomplete user record via webhook")
            raise ValueError(f"User {user_id} does not exist")
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
    # DynamoDB returns numbers as Decimal, convert to int for datetime operations
    billing_day = int(user.get('billing_day', datetime.now(timezone.utc).day))

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

    Syncs subscription_tier='free' to both users and token-usage tables.

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
    # DynamoDB returns numbers as Decimal, convert to int
    billing_day = int(user.get('billing_day')) if user.get('billing_day') else None
    now = datetime.now(timezone.utc)

    # Sync tier to both tables (users table is authoritative)
    sync_success = _sync_subscription_tier(user_id, 'free', billing_day)
    if not sync_success:
        logger.warning(f"Token-usage tier sync failed for {user_id}, continuing with deletion cleanup...")

    # Update other subscription fields and remove subscription ID
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET subscription_status = :status,
                    subscription_canceled_at = :canceled_at,
                    updated_at = :updated_at
                REMOVE stripe_subscription_id
            ''',
            ExpressionAttributeValues={
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
    Handle subscription updates (status changes, tier sync, etc.)

    Syncs subscription_tier to both users and token-usage tables based on status:
    - active/trialing: tier = 'plus'
    - canceled: tier = 'free'
    - past_due/incomplete: no tier change (grace period)

    Args:
        subscription: Stripe Subscription object
    """
    subscription_id = subscription.get('id')
    customer_id = subscription.get('customer')
    status = subscription.get('status')
    cancel_at_period_end = subscription.get('cancel_at_period_end', False)

    logger.info(f"Processing subscription update: {subscription_id}, status: {status}, cancel_at_period_end: {cancel_at_period_end}")

    # Find user by stripe_customer_id
    user = _find_user_by_customer_id(customer_id)
    if not user:
        logger.error(f"User not found for customer {customer_id}")
        return

    user_id = user['user_id']
    # DynamoDB returns numbers as Decimal, convert to int
    billing_day = int(user.get('billing_day')) if user.get('billing_day') else None
    now = datetime.now(timezone.utc)

    # Determine if tier should change based on status
    # Note: cancel_at_period_end=true with status=active means user is still active until period ends
    new_tier = None
    if status in ('active', 'trialing'):
        new_tier = 'plus'
    elif status == 'canceled':
        new_tier = 'free'
    # past_due, incomplete, incomplete_expired, unpaid → no tier change (grace period)

    # Sync tier if it should change
    if new_tier:
        sync_success = _sync_subscription_tier(user_id, new_tier, billing_day)
        if not sync_success:
            logger.warning(f"Token-usage tier sync failed for {user_id}, continuing with status update...")

    # Update other subscription fields in users table
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='''
                SET subscription_status = :status,
                    cancel_at_period_end = :cancel_at_end,
                    updated_at = :updated_at
            ''',
            ExpressionAttributeValues={
                ':status': status,
                ':cancel_at_end': cancel_at_period_end,
                ':updated_at': now.isoformat().replace('+00:00', 'Z'),
            }
        )
        logger.info(f"Updated subscription for user {user_id}: status={status}, tier={new_tier or 'unchanged'}")
    except ClientError as e:
        logger.error(f"Failed to update user record: {str(e)}")
        raise


# Helper functions

def _get_user(user_id: str) -> Optional[Dict[str, Any]]:
    """Fetch user record from DynamoDB by user_id."""
    try:
        response = users_table.get_item(Key={'user_id': user_id})
        return response.get('Item')
    except ClientError as e:
        logger.error(f"Failed to get user {user_id}: {str(e)}")
        return None


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
            logger.critical(f"SECURITY_ALERT: stripe-customer-index GSI unavailable, falling back to table scan for customer {customer_id}: {str(e)}")

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


def _get_current_billing_period(billing_day: int) -> str:
    """
    Calculate current billing period start date in YYYY-MM-DD format.

    Args:
        billing_day: Day of month when billing period starts (1-31)

    Returns:
        Billing period start date string (YYYY-MM-DD)
    """
    now = datetime.now(timezone.utc)
    billing_day = max(1, min(31, billing_day))

    # Get last day of current month
    last_day = calendar.monthrange(now.year, now.month)[1]
    effective_day = min(billing_day, last_day)

    # Determine if we're before or after this month's billing day
    if now.day >= effective_day:
        # Current period started this month
        period_start = now.replace(day=effective_day, hour=0, minute=0, second=0, microsecond=0)
    else:
        # Current period started last month
        if now.month == 1:
            prev_month = now.replace(year=now.year - 1, month=12, day=1)
        else:
            prev_month = now.replace(month=now.month - 1, day=1)
        prev_last_day = calendar.monthrange(prev_month.year, prev_month.month)[1]
        period_start = prev_month.replace(
            day=min(billing_day, prev_last_day),
            hour=0, minute=0, second=0, microsecond=0
        )

    return period_start.strftime('%Y-%m-%d')


def _sync_subscription_tier(
    user_id: str,
    subscription_tier: str,
    billing_day: Optional[int] = None
) -> bool:
    """
    Sync subscription_tier to both users and token-usage tables.

    Users table is authoritative - failure raises exception.
    Token-usage table sync is best-effort - failure is logged but doesn't fail webhook.

    Args:
        user_id: User identifier
        subscription_tier: 'plus' or 'free'
        billing_day: Day of month for billing (needed for token-usage lookup)

    Returns:
        True if both updates succeeded, False if token-usage sync failed
        (users table failure raises exception)
    """
    now = datetime.now(timezone.utc)

    # 1. Update users table (authoritative - must succeed)
    try:
        users_table.update_item(
            Key={'user_id': user_id},
            UpdateExpression='SET subscription_tier = :tier, updated_at = :ts',
            ExpressionAttributeValues={
                ':tier': subscription_tier,
                ':ts': now.isoformat().replace('+00:00', 'Z')
            }
        )
        logger.info(f"Updated users table: user={user_id}, tier={subscription_tier}")
    except ClientError as e:
        logger.error(f"Failed to update users table for {user_id}: {e}")
        raise

    # 2. Sync token-usage table (best-effort)
    try:
        if billing_day:
            billing_period = _get_current_billing_period(billing_day)

            # Determine token limit based on tier
            token_limit = TOKEN_LIMIT_PLUS if subscription_tier == 'plus' else TOKEN_LIMIT_FREE

            token_usage_table.update_item(
                Key={'user_id': user_id, 'billing_period': billing_period},
                UpdateExpression='SET subscription_tier = :tier, token_limit = :limit',
                ExpressionAttributeValues={
                    ':tier': subscription_tier,
                    ':limit': token_limit
                },
                ConditionExpression='attribute_exists(user_id)'  # Only if record exists
            )
            logger.info(f"Synced token-usage table: user={user_id}, period={billing_period}, tier={subscription_tier}, limit={token_limit}")
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            # No token usage record yet - that's OK
            logger.info(f"No token usage record to sync for user {user_id} (period may not exist yet)")
            return True
        logger.error(f"Failed to sync token-usage tier for {user_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error syncing token-usage tier for {user_id}: {e}")
        return False


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


def _mark_referral_claimed(email: str, trial_days: int, user_id: str) -> None:
    """
    Mark referral reward as claimed in the waitlist table.

    Uses a conditional update to prevent double-claiming (only writes if
    referral_claimed_at does not already exist).

    Args:
        email: Waitlist email to mark as claimed
        trial_days: Number of trial days that were granted
        user_id: User ID who claimed the reward (for audit trail)
    """
    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    try:
        waitlist_table.update_item(
            Key={'email': email},
            UpdateExpression='SET referral_claimed_at = :ts, referral_claimed_by = :uid, referral_trial_days_granted = :days',
            ExpressionAttributeValues={
                ':ts': now,
                ':uid': user_id,
                ':days': trial_days,
            },
            ConditionExpression='attribute_not_exists(referral_claimed_at)'
        )
        logger.info(f"Marked referral reward as claimed: {trial_days}-day trial for user {user_id}")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            logger.warning(f"Referral reward already claimed for email (race condition prevented)")
        else:
            # Non-fatal: don't fail the webhook over claim tracking
            logger.error(f"Failed to mark referral as claimed: {str(e)}")


def _response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create API Gateway response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
        },
        'body': json.dumps(body)
    }
