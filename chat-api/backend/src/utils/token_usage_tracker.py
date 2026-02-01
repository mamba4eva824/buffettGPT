"""
Token Usage Tracker Module for Monthly Token Limiting

Tracks token consumption per user using the ConverseStream API and enforces
monthly limits with notifications at 80% and 90% thresholds.

Uses anniversary-based billing periods: users' usage resets on the same day
each month that they first subscribed (e.g., subscribed on Jan 15 → resets
on Feb 15, Mar 15, etc.). Handles edge cases for months with fewer days.

Schema (DynamoDB token-usage table):
- user_id (PK): User identifier from JWT
- billing_period (SK): Billing period start date in "YYYY-MM-DD" format
- billing_day: Day of month for billing cycle (1-31)
- billing_period_start: ISO timestamp of billing period start
- billing_period_end: ISO timestamp of billing period end (next reset date)
- input_tokens: Total input tokens consumed
- output_tokens: Total output tokens consumed
- total_tokens: Sum of input + output tokens
- request_count: Number of API requests made
- token_limit: Monthly limit for this user
- notified_80: True if 80% notification sent
- notified_90: True if 90% notification sent
- limit_reached_at: ISO timestamp when limit hit
- last_request_at: ISO timestamp of last request
- subscribed_at: ISO timestamp when user first started using the service
- reset_date: Pre-computed ISO timestamp for when usage resets (anniversary date)
- subscription_tier: User's subscription tier (free/plus)
"""

import boto3
import calendar
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)


class TokenUsageTracker:
    """
    Token usage tracking and limiting system.

    Features:
    - Atomic token counting with DynamoDB ADD operation
    - Anniversary-based billing periods (resets on user's subscription day)
    - Configurable limits per user tier
    - Threshold notifications at 80% and 90%
    - Hard cutoff when limit reached
    - Edge case handling for months with fewer days (e.g., Feb 28/29)
    """

    # Default token limits by user tier
    # Note: Free users cannot use follow-up feature (plus only)
    DEFAULT_LIMITS = {
        'anonymous': 0,      # No access
        'free': 0,           # No follow-up access (plus feature only)
        'plus': 1000000,     # 1M tokens/month
    }

    def __init__(self, table_name: Optional[str] = None, dynamodb_resource=None):
        """
        Initialize TokenUsageTracker.

        Args:
            table_name: DynamoDB table name. Defaults to TOKEN_USAGE_TABLE env var.
            dynamodb_resource: Optional boto3 DynamoDB resource for testing.
        """
        # NOTE: Default table name should match Terraform naming convention
        env = os.environ.get('ENVIRONMENT', 'dev')
        default_table = f'buffett-{env}-token-usage'
        self.table_name = table_name or os.environ.get('TOKEN_USAGE_TABLE', default_table)

        # Default limit from environment (for testing, use 50000)
        self.default_token_limit = int(os.environ.get('DEFAULT_TOKEN_LIMIT', '50000'))

        # Initialize DynamoDB
        try:
            if dynamodb_resource:
                self.dynamodb = dynamodb_resource
            else:
                self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table(self.table_name)
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB table: {str(e)}")
            self.table = None

    @staticmethod
    def get_current_month() -> str:
        """Get current month in YYYY-MM format (legacy, for backwards compatibility)."""
        return datetime.now(timezone.utc).strftime('%Y-%m')

    @staticmethod
    def get_reset_date() -> str:
        """
        Get the reset date (1st of next month) in ISO format.
        Legacy method for backwards compatibility - uses calendar month reset.

        Returns:
            ISO timestamp string of when the usage resets.
        """
        now = datetime.now(timezone.utc)
        if now.month == 12:
            reset = now.replace(year=now.year + 1, month=1, day=1,
                               hour=0, minute=0, second=0, microsecond=0)
        else:
            reset = now.replace(month=now.month + 1, day=1,
                               hour=0, minute=0, second=0, microsecond=0)
        return reset.isoformat().replace('+00:00', 'Z')

    @staticmethod
    def get_anniversary_reset_date(billing_day: int) -> str:
        """
        Calculate next reset date based on user's billing day.

        Args:
            billing_day: Day of month for billing cycle (1-31)

        Returns:
            ISO timestamp of next reset date.
        """
        now = datetime.now(timezone.utc)

        # Clamp billing_day to valid range
        billing_day = max(1, min(31, billing_day))

        # Get last day of current month
        last_day_this_month = calendar.monthrange(now.year, now.month)[1]

        # Determine the billing day for this month (handle months with fewer days)
        effective_billing_day = min(billing_day, last_day_this_month)

        # Try to create this month's billing date
        try:
            this_month_billing = now.replace(
                day=effective_billing_day,
                hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            # Fallback: use last day of month
            this_month_billing = now.replace(
                day=last_day_this_month,
                hour=0, minute=0, second=0, microsecond=0
            )

        if now < this_month_billing:
            reset = this_month_billing
        else:
            # Move to next month
            if now.month == 12:
                next_month = now.replace(year=now.year + 1, month=1, day=1)
            else:
                next_month = now.replace(month=now.month + 1, day=1)

            # Get last day of next month
            last_day_next_month = calendar.monthrange(next_month.year, next_month.month)[1]
            effective_billing_day_next = min(billing_day, last_day_next_month)

            try:
                reset = next_month.replace(
                    day=effective_billing_day_next,
                    hour=0, minute=0, second=0, microsecond=0
                )
            except ValueError:
                reset = next_month.replace(
                    day=last_day_next_month,
                    hour=0, minute=0, second=0, microsecond=0
                )

        return reset.isoformat().replace('+00:00', 'Z')

    @staticmethod
    def get_current_billing_period(billing_day: int) -> Tuple[str, str, str]:
        """
        Compute current billing period based on billing day.

        Args:
            billing_day: Day of month for billing cycle (1-31)

        Returns:
            Tuple of (billing_period_key, period_start_iso, period_end_iso)
            - billing_period_key: YYYY-MM-DD format for the start of the period
            - period_start_iso: ISO timestamp of period start
            - period_end_iso: ISO timestamp of period end (next reset date)
        """
        now = datetime.now(timezone.utc)

        # Clamp billing_day to valid range
        billing_day = max(1, min(31, billing_day))

        # Get last day of current month
        last_day_this_month = calendar.monthrange(now.year, now.month)[1]

        # Determine effective billing day for this month
        effective_billing_day = min(billing_day, last_day_this_month)

        # Create this month's billing date
        try:
            this_month_billing = now.replace(
                day=effective_billing_day,
                hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            this_month_billing = now.replace(
                day=last_day_this_month,
                hour=0, minute=0, second=0, microsecond=0
            )

        if now >= this_month_billing:
            # We're in the period starting this month
            period_start = this_month_billing
        else:
            # We're in the period that started last month
            if now.month == 1:
                prev_month = now.replace(year=now.year - 1, month=12, day=1)
            else:
                prev_month = now.replace(month=now.month - 1, day=1)

            # Get last day of previous month
            last_day_prev_month = calendar.monthrange(prev_month.year, prev_month.month)[1]
            effective_billing_day_prev = min(billing_day, last_day_prev_month)

            try:
                period_start = prev_month.replace(
                    day=effective_billing_day_prev,
                    hour=0, minute=0, second=0, microsecond=0
                )
            except ValueError:
                period_start = prev_month.replace(
                    day=last_day_prev_month,
                    hour=0, minute=0, second=0, microsecond=0
                )

        # Calculate period end (next billing date)
        period_end_iso = TokenUsageTracker.get_anniversary_reset_date(billing_day)

        # Format period key as YYYY-MM-DD
        period_key = period_start.strftime('%Y-%m-%d')
        period_start_iso = period_start.isoformat().replace('+00:00', 'Z')

        return period_key, period_start_iso, period_end_iso

    def get_billing_day(self, user_id: str) -> int:
        """
        Fetch user's billing day from their first usage record or default to today.

        Queries DynamoDB to find the user's billing_day. If not found, returns
        the current day of month (for new users).

        Args:
            user_id: User identifier.

        Returns:
            Billing day (1-31) for the user.
        """
        if not self.table:
            return datetime.now(timezone.utc).day

        try:
            # Query for the user's most recent record to get billing_day
            response = self.table.query(
                KeyConditionExpression='user_id = :uid',
                ExpressionAttributeValues={':uid': user_id},
                Limit=1,
                ScanIndexForward=False  # Get most recent first
            )

            items = response.get('Items', [])
            if items:
                # Check for billing_day field
                billing_day = items[0].get('billing_day')
                if billing_day:
                    return int(billing_day)

                # Fallback: extract from subscribed_at if present
                subscribed_at = items[0].get('subscribed_at')
                if subscribed_at:
                    try:
                        subscribed_dt = datetime.fromisoformat(
                            subscribed_at.replace('Z', '+00:00')
                        )
                        return subscribed_dt.day
                    except (ValueError, AttributeError):
                        pass

            # Default to current day for new users
            return datetime.now(timezone.utc).day

        except ClientError as e:
            logger.error(f"DynamoDB error fetching billing day: {str(e)}")
            return datetime.now(timezone.utc).day
        except Exception as e:
            logger.error(f"Unexpected error fetching billing day: {str(e)}")
            return datetime.now(timezone.utc).day

    def check_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user can make a request based on their token usage.

        Uses anniversary-based billing periods to determine current usage.

        Args:
            user_id: User identifier from JWT or device fingerprint.

        Returns:
            Dictionary with:
            - allowed: bool - whether request should proceed
            - total_tokens: int - tokens used this billing period
            - token_limit: int - monthly limit
            - percent_used: float - percentage of limit used
            - remaining_tokens: int - tokens remaining
            - reset_date: str - ISO timestamp of reset (anniversary date)
            - billing_day: int - user's billing day (1-31)
        """
        if not self.table:
            logger.warning("Token usage table not available, allowing request")
            return self._create_allowed_response(0, self.default_token_limit)

        try:
            # Get user's billing day
            billing_day = self.get_billing_day(user_id)

            # Get current billing period
            billing_period, period_start, period_end = self.get_current_billing_period(billing_day)

            # Get current usage
            response = self.table.get_item(
                Key={
                    'user_id': user_id,
                    'billing_period': billing_period
                }
            )

            item = response.get('Item', {})
            total_tokens = int(item.get('total_tokens', 0))
            token_limit = int(item.get('token_limit', self.default_token_limit))

            # Check if over limit
            if total_tokens >= token_limit:
                return {
                    'allowed': False,
                    'total_tokens': total_tokens,
                    'token_limit': token_limit,
                    'percent_used': 100.0,
                    'remaining_tokens': 0,
                    'reset_date': period_end,
                    'billing_day': billing_day,
                    'limit_reached_at': item.get('limit_reached_at')
                }

            return self._create_allowed_response(total_tokens, token_limit, billing_day)

        except ClientError as e:
            logger.error(f"DynamoDB error checking limit: {str(e)}")
            # Fail open - allow request but log error
            return self._create_allowed_response(0, self.default_token_limit)
        except Exception as e:
            logger.error(f"Unexpected error checking limit: {str(e)}")
            return self._create_allowed_response(0, self.default_token_limit)

    def record_usage(
        self,
        user_id: str,
        input_tokens: int,
        output_tokens: int
    ) -> Dict[str, Any]:
        """
        Record token usage atomically.

        Uses DynamoDB ADD operation for atomic increment to handle
        concurrent requests safely. Uses anniversary-based billing periods.

        Args:
            user_id: User identifier.
            input_tokens: Number of input tokens consumed.
            output_tokens: Number of output tokens consumed.

        Returns:
            Dictionary with:
            - total_tokens: int - new total after update
            - token_limit: int - user's monthly limit
            - percent_used: float - percentage of limit used
            - threshold_reached: str | None - "80%", "90%", "100%", or None
            - remaining_tokens: int - tokens remaining
            - billing_day: int - user's billing day (1-31)
            - reset_date: str - ISO timestamp of next reset
        """
        if not self.table:
            logger.warning("Token usage table not available, skipping recording")
            return {
                'total_tokens': 0,
                'token_limit': self.default_token_limit,
                'percent_used': 0.0,
                'threshold_reached': None,
                'remaining_tokens': self.default_token_limit
            }

        try:
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat().replace('+00:00', 'Z')
            total_new_tokens = input_tokens + output_tokens

            # Get user's billing day (or use today for new users)
            billing_day = self.get_billing_day(user_id)

            # Get current billing period
            billing_period, period_start, period_end = self.get_current_billing_period(billing_day)

            # Atomic update using ADD
            response = self.table.update_item(
                Key={
                    'user_id': user_id,
                    'billing_period': billing_period
                },
                UpdateExpression='''
                    ADD input_tokens :input,
                        output_tokens :output,
                        total_tokens :total,
                        request_count :one
                    SET last_request_at = :now,
                        token_limit = if_not_exists(token_limit, :default_limit),
                        reset_date = if_not_exists(reset_date, :reset),
                        billing_period_start = if_not_exists(billing_period_start, :period_start),
                        billing_period_end = if_not_exists(billing_period_end, :period_end),
                        billing_day = if_not_exists(billing_day, :billing_day),
                        subscribed_at = if_not_exists(subscribed_at, :now),
                        subscription_tier = if_not_exists(subscription_tier, :default_tier)
                ''',
                ExpressionAttributeValues={
                    ':input': input_tokens,
                    ':output': output_tokens,
                    ':total': total_new_tokens,
                    ':one': 1,
                    ':now': now,
                    ':default_limit': self.default_token_limit,
                    ':reset': period_end,
                    ':period_start': period_start,
                    ':period_end': period_end,
                    ':billing_day': billing_day,
                    ':default_tier': 'free'
                },
                ReturnValues='ALL_NEW'
            )

            attrs = response.get('Attributes', {})
            total_tokens = int(attrs.get('total_tokens', total_new_tokens))
            token_limit = int(attrs.get('token_limit', self.default_token_limit))
            stored_billing_day = int(attrs.get('billing_day', billing_day))

            # Calculate percentage
            percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 100.0

            # Check thresholds
            threshold_reached = self._check_thresholds(
                user_id, billing_period, total_tokens, token_limit, attrs
            )

            return {
                'total_tokens': total_tokens,
                'token_limit': token_limit,
                'percent_used': round(percent_used, 1),
                'threshold_reached': threshold_reached,
                'remaining_tokens': max(0, token_limit - total_tokens),
                'billing_day': stored_billing_day,
                'reset_date': period_end
            }

        except ClientError as e:
            logger.error(f"DynamoDB error recording usage: {str(e)}")
            return {
                'total_tokens': 0,
                'token_limit': self.default_token_limit,
                'percent_used': 0.0,
                'threshold_reached': None,
                'remaining_tokens': self.default_token_limit,
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error recording usage: {str(e)}")
            return {
                'total_tokens': 0,
                'token_limit': self.default_token_limit,
                'percent_used': 0.0,
                'threshold_reached': None,
                'remaining_tokens': self.default_token_limit,
                'error': str(e)
            }

    def _check_thresholds(
        self,
        user_id: str,
        billing_period: str,
        total_tokens: int,
        token_limit: int,
        attrs: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check and update threshold notifications.

        Args:
            user_id: User identifier.
            billing_period: Current billing period string (YYYY-MM-DD).
            total_tokens: Current total tokens.
            token_limit: User's token limit.
            attrs: Current item attributes from DynamoDB.

        Returns:
            Threshold string ("80%", "90%", "100%") if just crossed, else None.
        """
        percent = (total_tokens / token_limit * 100) if token_limit > 0 else 100.0
        notified_80 = attrs.get('notified_80', False)
        notified_90 = attrs.get('notified_90', False)
        limit_reached_at = attrs.get('limit_reached_at')

        threshold_reached = None
        update_expr_parts = []
        expr_values = {}

        # Check 100% (limit reached)
        if percent >= 100 and not limit_reached_at:
            threshold_reached = '100%'
            update_expr_parts.append('limit_reached_at = :limit_time')
            expr_values[':limit_time'] = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        # Check 90%
        elif percent >= 90 and not notified_90:
            threshold_reached = '90%'
            update_expr_parts.append('notified_90 = :true')
            expr_values[':true'] = True

        # Check 80%
        elif percent >= 80 and not notified_80:
            threshold_reached = '80%'
            update_expr_parts.append('notified_80 = :true')
            expr_values[':true'] = True

        # Update flags if threshold was crossed
        if update_expr_parts and self.table:
            try:
                self.table.update_item(
                    Key={'user_id': user_id, 'billing_period': billing_period},
                    UpdateExpression='SET ' + ', '.join(update_expr_parts),
                    ExpressionAttributeValues=expr_values
                )
            except Exception as e:
                logger.error(f"Failed to update threshold flags: {str(e)}")

        return threshold_reached

    def get_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Get current usage statistics for a user.

        Uses anniversary-based billing periods.

        Args:
            user_id: User identifier.

        Returns:
            Dictionary with full usage statistics:
            - input_tokens: int
            - output_tokens: int
            - total_tokens: int
            - token_limit: int
            - percent_used: float
            - remaining_tokens: int
            - request_count: int
            - reset_date: str (ISO timestamp of anniversary reset)
            - billing_day: int (1-31)
            - last_request_at: str | None
        """
        if not self.table:
            return self._create_empty_usage_response()

        try:
            # Get user's billing day
            billing_day = self.get_billing_day(user_id)

            # Get current billing period
            billing_period, period_start, period_end = self.get_current_billing_period(billing_day)

            response = self.table.get_item(
                Key={
                    'user_id': user_id,
                    'billing_period': billing_period
                }
            )

            item = response.get('Item', {})

            if not item:
                return self._create_empty_usage_response(billing_day)

            input_tokens = int(item.get('input_tokens', 0))
            output_tokens = int(item.get('output_tokens', 0))
            total_tokens = int(item.get('total_tokens', 0))
            token_limit = int(item.get('token_limit', self.default_token_limit))
            request_count = int(item.get('request_count', 0))
            stored_billing_day = int(item.get('billing_day', billing_day))

            percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 0.0

            return {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'token_limit': token_limit,
                'percent_used': round(percent_used, 1),
                'remaining_tokens': max(0, token_limit - total_tokens),
                'request_count': request_count,
                'reset_date': item.get('reset_date', period_end),
                'billing_day': stored_billing_day,
                'billing_period_start': item.get('billing_period_start', period_start),
                'billing_period_end': item.get('billing_period_end', period_end),
                'last_request_at': item.get('last_request_at'),
                'subscribed_at': item.get('subscribed_at'),
                'subscription_tier': item.get('subscription_tier', 'free')
            }

        except ClientError as e:
            logger.error(f"DynamoDB error getting usage: {str(e)}")
            return self._create_empty_usage_response()
        except Exception as e:
            logger.error(f"Unexpected error getting usage: {str(e)}")
            return self._create_empty_usage_response()

    def set_user_limit(
        self,
        user_id: str,
        token_limit: int,
        billing_period: Optional[str] = None
    ) -> bool:
        """
        Set a custom token limit for a user.

        Args:
            user_id: User identifier.
            token_limit: New monthly token limit.
            billing_period: Optional billing period to set limit for
                           (defaults to current billing period).

        Returns:
            True if successful, False otherwise.
        """
        if not self.table:
            logger.warning("Token usage table not available")
            return False

        try:
            if billing_period is None:
                # Get user's billing day and current period
                billing_day = self.get_billing_day(user_id)
                billing_period, _, _ = self.get_current_billing_period(billing_day)

            self.table.update_item(
                Key={
                    'user_id': user_id,
                    'billing_period': billing_period
                },
                UpdateExpression='SET token_limit = :limit',
                ExpressionAttributeValues={
                    ':limit': token_limit
                }
            )

            logger.info(f"Set token limit for {user_id} to {token_limit}")
            return True

        except Exception as e:
            logger.error(f"Failed to set user limit: {str(e)}")
            return False

    def reset_notifications(
        self,
        user_id: str,
        billing_period: Optional[str] = None
    ) -> bool:
        """
        Reset notification flags for a user (admin function).

        Args:
            user_id: User identifier.
            billing_period: Optional billing period (defaults to current billing period).

        Returns:
            True if successful, False otherwise.
        """
        if not self.table:
            return False

        try:
            if billing_period is None:
                # Get user's billing day and current period
                billing_day = self.get_billing_day(user_id)
                billing_period, _, _ = self.get_current_billing_period(billing_day)

            self.table.update_item(
                Key={
                    'user_id': user_id,
                    'billing_period': billing_period
                },
                UpdateExpression='REMOVE notified_80, notified_90, limit_reached_at'
            )

            return True

        except Exception as e:
            logger.error(f"Failed to reset notifications: {str(e)}")
            return False

    def _create_allowed_response(
        self,
        total_tokens: int,
        token_limit: int,
        billing_day: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create response for allowed requests."""
        percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 0.0

        # Use anniversary reset if billing_day provided, otherwise legacy reset
        if billing_day is not None:
            reset_date = self.get_anniversary_reset_date(billing_day)
        else:
            billing_day = datetime.now(timezone.utc).day
            reset_date = self.get_anniversary_reset_date(billing_day)

        return {
            'allowed': True,
            'total_tokens': total_tokens,
            'token_limit': token_limit,
            'percent_used': round(percent_used, 1),
            'remaining_tokens': max(0, token_limit - total_tokens),
            'reset_date': reset_date,
            'billing_day': billing_day
        }

    def _create_empty_usage_response(self, billing_day: Optional[int] = None) -> Dict[str, Any]:
        """Create response when no usage data exists."""
        # Use provided billing_day or default to today
        if billing_day is None:
            billing_day = datetime.now(timezone.utc).day

        # Get anniversary-based reset date and billing period
        reset_date = self.get_anniversary_reset_date(billing_day)
        _, period_start, period_end = self.get_current_billing_period(billing_day)

        return {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'token_limit': self.default_token_limit,
            'percent_used': 0.0,
            'remaining_tokens': self.default_token_limit,
            'request_count': 0,
            'reset_date': reset_date,
            'billing_day': billing_day,
            'billing_period_start': period_start,
            'billing_period_end': period_end,
            'last_request_at': None,
            'subscribed_at': None,
            'subscription_tier': 'free'
        }


# Convenience function for direct usage
def check_token_limit(user_id: str) -> Dict[str, Any]:
    """
    Quick check if user is within token limit.

    Args:
        user_id: User identifier.

    Returns:
        Dictionary with allowed status and usage details.
    """
    tracker = TokenUsageTracker()
    return tracker.check_limit(user_id)


def record_token_usage(user_id: str, input_tokens: int, output_tokens: int) -> Dict[str, Any]:
    """
    Record token usage after a request.

    Args:
        user_id: User identifier.
        input_tokens: Input tokens consumed.
        output_tokens: Output tokens consumed.

    Returns:
        Dictionary with updated usage and threshold info.
    """
    tracker = TokenUsageTracker()
    return tracker.record_usage(user_id, input_tokens, output_tokens)
