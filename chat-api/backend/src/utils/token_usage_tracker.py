"""
Token Usage Tracker Module for Monthly Token Limiting

Tracks token consumption per user using the ConverseStream API and enforces
monthly limits with notifications at 80% and 90% thresholds.

Schema (DynamoDB token-usage table):
- user_id (PK): User identifier from JWT
- month (SK): Year-month format "YYYY-MM"
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
- reset_date: Pre-computed ISO timestamp for when usage resets (1st of next month)
- subscription_tier: User's subscription tier (free/plus)
"""

import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger(__name__)


class TokenUsageTracker:
    """
    Token usage tracking and limiting system.

    Features:
    - Atomic token counting with DynamoDB ADD operation
    - Monthly usage windows (resets on 1st of each month)
    - Configurable limits per user tier
    - Threshold notifications at 80% and 90%
    - Hard cutoff when limit reached
    """

    # Default token limits by user tier
    DEFAULT_LIMITS = {
        'anonymous': 1000,
        'free': 50000,   # Free tier (authenticated)
        'plus': 500000,  # Plus subscription tier
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
        """Get current month in YYYY-MM format."""
        return datetime.utcnow().strftime('%Y-%m')

    @staticmethod
    def get_reset_date() -> str:
        """
        Get the reset date (1st of next month) in ISO format.

        Returns:
            ISO timestamp string of when the usage resets.
        """
        now = datetime.utcnow()
        if now.month == 12:
            reset = now.replace(year=now.year + 1, month=1, day=1,
                               hour=0, minute=0, second=0, microsecond=0)
        else:
            reset = now.replace(month=now.month + 1, day=1,
                               hour=0, minute=0, second=0, microsecond=0)
        return reset.isoformat() + 'Z'

    def check_limit(self, user_id: str) -> Dict[str, Any]:
        """
        Check if user can make a request based on their token usage.

        Args:
            user_id: User identifier from JWT or device fingerprint.

        Returns:
            Dictionary with:
            - allowed: bool - whether request should proceed
            - total_tokens: int - tokens used this month
            - token_limit: int - monthly limit
            - percent_used: float - percentage of limit used
            - remaining_tokens: int - tokens remaining
            - reset_date: str - ISO timestamp of reset
        """
        if not self.table:
            logger.warning("Token usage table not available, allowing request")
            return self._create_allowed_response(0, self.default_token_limit)

        try:
            current_month = self.get_current_month()

            # Get current usage
            response = self.table.get_item(
                Key={
                    'user_id': user_id,
                    'month': current_month
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
                    'reset_date': self.get_reset_date(),
                    'limit_reached_at': item.get('limit_reached_at')
                }

            return self._create_allowed_response(total_tokens, token_limit)

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
        concurrent requests safely.

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
            current_month = self.get_current_month()
            now = datetime.utcnow().isoformat() + 'Z'
            total_new_tokens = input_tokens + output_tokens

            # Compute reset date for this billing period
            reset_date = self.get_reset_date()

            # Atomic update using ADD
            response = self.table.update_item(
                Key={
                    'user_id': user_id,
                    'month': current_month
                },
                UpdateExpression='''
                    ADD input_tokens :input,
                        output_tokens :output,
                        total_tokens :total,
                        request_count :one
                    SET last_request_at = :now,
                        token_limit = if_not_exists(token_limit, :default_limit),
                        reset_date = if_not_exists(reset_date, :reset),
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
                    ':reset': reset_date,
                    ':default_tier': 'free'
                },
                ReturnValues='ALL_NEW'
            )

            attrs = response.get('Attributes', {})
            total_tokens = int(attrs.get('total_tokens', total_new_tokens))
            token_limit = int(attrs.get('token_limit', self.default_token_limit))

            # Calculate percentage
            percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 100.0

            # Check thresholds
            threshold_reached = self._check_thresholds(
                user_id, current_month, total_tokens, token_limit, attrs
            )

            return {
                'total_tokens': total_tokens,
                'token_limit': token_limit,
                'percent_used': round(percent_used, 1),
                'threshold_reached': threshold_reached,
                'remaining_tokens': max(0, token_limit - total_tokens)
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
        month: str,
        total_tokens: int,
        token_limit: int,
        attrs: Dict[str, Any]
    ) -> Optional[str]:
        """
        Check and update threshold notifications.

        Args:
            user_id: User identifier.
            month: Current month string.
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
            expr_values[':limit_time'] = datetime.utcnow().isoformat() + 'Z'

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
                    Key={'user_id': user_id, 'month': month},
                    UpdateExpression='SET ' + ', '.join(update_expr_parts),
                    ExpressionAttributeValues=expr_values
                )
            except Exception as e:
                logger.error(f"Failed to update threshold flags: {str(e)}")

        return threshold_reached

    def get_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Get current usage statistics for a user.

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
            - reset_date: str (ISO timestamp)
            - last_request_at: str | None
        """
        if not self.table:
            return self._create_empty_usage_response()

        try:
            current_month = self.get_current_month()

            response = self.table.get_item(
                Key={
                    'user_id': user_id,
                    'month': current_month
                }
            )

            item = response.get('Item', {})

            if not item:
                return self._create_empty_usage_response()

            input_tokens = int(item.get('input_tokens', 0))
            output_tokens = int(item.get('output_tokens', 0))
            total_tokens = int(item.get('total_tokens', 0))
            token_limit = int(item.get('token_limit', self.default_token_limit))
            request_count = int(item.get('request_count', 0))

            percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 0.0

            return {
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'token_limit': token_limit,
                'percent_used': round(percent_used, 1),
                'remaining_tokens': max(0, token_limit - total_tokens),
                'request_count': request_count,
                'reset_date': item.get('reset_date', self.get_reset_date()),
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

    def set_user_limit(self, user_id: str, token_limit: int, month: Optional[str] = None) -> bool:
        """
        Set a custom token limit for a user.

        Args:
            user_id: User identifier.
            token_limit: New monthly token limit.
            month: Optional month to set limit for (defaults to current month).

        Returns:
            True if successful, False otherwise.
        """
        if not self.table:
            logger.warning("Token usage table not available")
            return False

        try:
            target_month = month or self.get_current_month()

            self.table.update_item(
                Key={
                    'user_id': user_id,
                    'month': target_month
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

    def reset_notifications(self, user_id: str, month: Optional[str] = None) -> bool:
        """
        Reset notification flags for a user (admin function).

        Args:
            user_id: User identifier.
            month: Optional month (defaults to current month).

        Returns:
            True if successful, False otherwise.
        """
        if not self.table:
            return False

        try:
            target_month = month or self.get_current_month()

            self.table.update_item(
                Key={
                    'user_id': user_id,
                    'month': target_month
                },
                UpdateExpression='REMOVE notified_80, notified_90, limit_reached_at'
            )

            return True

        except Exception as e:
            logger.error(f"Failed to reset notifications: {str(e)}")
            return False

    def _create_allowed_response(self, total_tokens: int, token_limit: int) -> Dict[str, Any]:
        """Create response for allowed requests."""
        percent_used = (total_tokens / token_limit * 100) if token_limit > 0 else 0.0
        return {
            'allowed': True,
            'total_tokens': total_tokens,
            'token_limit': token_limit,
            'percent_used': round(percent_used, 1),
            'remaining_tokens': max(0, token_limit - total_tokens),
            'reset_date': self.get_reset_date()
        }

    def _create_empty_usage_response(self) -> Dict[str, Any]:
        """Create response when no usage data exists."""
        return {
            'input_tokens': 0,
            'output_tokens': 0,
            'total_tokens': 0,
            'token_limit': self.default_token_limit,
            'percent_used': 0.0,
            'remaining_tokens': self.default_token_limit,
            'request_count': 0,
            'reset_date': self.get_reset_date(),
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
