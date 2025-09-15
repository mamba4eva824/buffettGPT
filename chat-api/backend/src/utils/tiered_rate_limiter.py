"""
Tiered Rate Limiting System
Implements rate limiting for anonymous, authenticated, and premium users.
"""

import boto3
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from decimal import Decimal
import os

logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
RATE_LIMITS_TABLE = os.environ.get('RATE_LIMITS_TABLE', 'buffett-dev-enhanced-rate-limits')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

class TieredRateLimiter:
    """
    Rate limiter supporting multiple user tiers with different limits.
    """
    
    # Rate limit configurations by tier
    TIER_LIMITS = {
        'anonymous': {
            'daily': 5,
            'hourly': 3,
            'per_minute': 2,
            'burst': 2,  # Max requests in quick succession
            'message_history': False,
            'session_ttl_hours': 2,
            'daily_reset_hour': 0  # UTC midnight
        },
        'authenticated': {
            'daily': 20,
            'hourly': 10,
            'per_minute': 5,
            'burst': 3,
            'message_history': True,
            'session_ttl_hours': 168,  # 7 days
            'daily_reset_hour': 0
        },
        'premium': {
            'daily': 1000,  # Effectively unlimited
            'hourly': 100,
            'per_minute': 20,
            'burst': 10,
            'message_history': True,
            'session_ttl_hours': 720,  # 30 days
            'daily_reset_hour': 0
        },
        'enterprise': {
            'daily': 10000,
            'hourly': 1000,
            'per_minute': 100,
            'burst': 50,
            'message_history': True,
            'session_ttl_hours': 2160,  # 90 days
            'daily_reset_hour': 0
        }
    }
    
    def __init__(self, table_name: str = None):
        """
        Initialize the rate limiter.
        
        Args:
            table_name: DynamoDB table name for rate limit tracking
        """
        self.table_name = table_name or RATE_LIMITS_TABLE
        self.table = dynamodb.Table(self.table_name)
    
    def get_user_tier(self, user_type: str, subscription_tier: str = None) -> str:
        """
        Determine the rate limit tier for a user.
        
        Args:
            user_type: 'anonymous' or 'authenticated'
            subscription_tier: Subscription level for authenticated users
            
        Returns:
            Rate limit tier name
        """
        if user_type == 'anonymous':
            return 'anonymous'
        
        # Map subscription tiers to rate limit tiers
        subscription_mapping = {
            'free': 'authenticated',
            'basic': 'authenticated',
            'premium': 'premium',
            'pro': 'premium',
            'enterprise': 'enterprise'
        }
        
        return subscription_mapping.get(subscription_tier, 'authenticated')
    
    async def check_rate_limit(
        self, 
        user_id: str, 
        user_type: str,
        subscription_tier: str = None,
        increment: bool = True
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if user has exceeded rate limits.
        
        Args:
            user_id: User identifier (authenticated or device fingerprint)
            user_type: 'anonymous' or 'authenticated'
            subscription_tier: Subscription level for authenticated users
            increment: Whether to increment the counter if within limits
            
        Returns:
            Tuple of (allowed, info)
            - allowed: True if request is within limits
            - info: Rate limit information and remaining quotas
        """
        tier = self.get_user_tier(user_type, subscription_tier)
        limits = self.TIER_LIMITS[tier]
        
        current_time = datetime.utcnow()
        current_timestamp = int(current_time.timestamp())
        
        try:
            # Get or create rate limit record
            # Use a window key that represents the current time period
            window_key = f"{current_time.strftime('%Y-%m-%d')}"
            response = self.table.get_item(Key={'identifier': user_id, 'window': window_key})
            
            if 'Item' in response:
                rate_data = response['Item']
            else:
                # Initialize new rate limit record
                rate_data = self._initialize_rate_record(user_id, tier, current_time, window_key)
                self.table.put_item(Item=rate_data)
                
                if increment:
                    rate_data['daily_count'] = 1
                    rate_data['hourly_count'] = 1
                    rate_data['minute_count'] = 1
                    self._update_counts(user_id, rate_data, window_key)
                
                return True, self._format_rate_info(rate_data, limits, tier)
            
            # Check and reset counters if needed
            rate_data = self._reset_expired_counters(rate_data, current_time)
            
            # Check burst limit (requests in last few seconds)
            burst_violations = self._check_burst_limit(rate_data, current_timestamp, limits['burst'])
            if burst_violations:
                return False, {
                    'exceeded': 'burst',
                    'limit': limits['burst'],
                    'retry_after': 2,  # seconds
                    'tier': tier,
                    'message': f"Too many requests. Please wait 2 seconds."
                }
            
            # Check minute limit
            if rate_data.get('minute_count', 0) >= limits['per_minute']:
                seconds_until_reset = 60 - (current_timestamp % 60)
                return False, {
                    'exceeded': 'per_minute',
                    'limit': limits['per_minute'],
                    'retry_after': seconds_until_reset,
                    'tier': tier,
                    'message': f"Minute limit reached. Try again in {seconds_until_reset} seconds."
                }
            
            # Check hourly limit
            if rate_data.get('hourly_count', 0) >= limits['hourly']:
                minutes_until_reset = 60 - current_time.minute
                return False, {
                    'exceeded': 'hourly',
                    'limit': limits['hourly'],
                    'retry_after': minutes_until_reset * 60,
                    'tier': tier,
                    'message': f"Hourly limit reached. Try again in {minutes_until_reset} minutes."
                }
            
            # Check daily limit
            if rate_data.get('daily_count', 0) >= limits['daily']:
                reset_time = self._get_next_daily_reset(current_time, limits['daily_reset_hour'])
                hours_until_reset = (reset_time - current_time).total_seconds() / 3600
                
                return False, {
                    'exceeded': 'daily',
                    'limit': limits['daily'],
                    'reset_at': reset_time.isoformat(),
                    'retry_after': int((reset_time - current_time).total_seconds()),
                    'tier': tier,
                    'message': f"Daily limit reached. Resets in {hours_until_reset:.1f} hours.",
                    'upgrade_suggestion': self._get_upgrade_suggestion(tier)
                }
            
            # Request is within limits
            if increment:
                # Update counters
                rate_data['daily_count'] = rate_data.get('daily_count', 0) + 1
                rate_data['hourly_count'] = rate_data.get('hourly_count', 0) + 1
                rate_data['minute_count'] = rate_data.get('minute_count', 0) + 1
                rate_data['last_request'] = current_timestamp
                
                # Add to request history for burst detection
                request_history = rate_data.get('request_history', [])
                request_history.append(current_timestamp)
                # Keep only last 10 requests
                rate_data['request_history'] = request_history[-10:]
                
                self._update_counts(user_id, rate_data, window_key)
            
            return True, self._format_rate_info(rate_data, limits, tier)
            
        except Exception as e:
            logger.error(f"Rate limit check failed", extra={
                'user_id': user_id,
                'tier': tier,
                'error': str(e)
            }, exc_info=True)
            
            # Fail open in case of errors (allow the request)
            return True, {
                'tier': tier,
                'error': 'Rate limit check failed, allowing request',
                'remaining_daily': 'unknown'
            }
    
    def _initialize_rate_record(self, user_id: str, tier: str, current_time: datetime, window_key: str) -> Dict[str, Any]:
        """Initialize a new rate limit record."""
        reset_time = self._get_next_daily_reset(
            current_time, 
            self.TIER_LIMITS[tier]['daily_reset_hour']
        )
        
        # Set TTL for anonymous users to auto-cleanup
        ttl = None
        if tier == 'anonymous':
            ttl = int((current_time + timedelta(days=1)).timestamp())
        
        record = {
            'identifier': user_id,
            'window': window_key,
            'tier': tier,
            'daily_count': 0,
            'hourly_count': 0,
            'minute_count': 0,
            'daily_reset': reset_time.isoformat(),
            'hourly_reset': (current_time + timedelta(hours=1)).isoformat(),
            'minute_reset': (current_time + timedelta(minutes=1)).isoformat(),
            'last_request': int(current_time.timestamp()),
            'request_history': [],
            'created_at': current_time.isoformat(),
            'updated_at': current_time.isoformat()
        }
        
        if ttl:
            record['ttl'] = ttl
        
        return record
    
    def _reset_expired_counters(self, rate_data: Dict[str, Any], current_time: datetime) -> Dict[str, Any]:
        """Reset counters that have passed their reset time."""
        
        # Reset daily counter
        daily_reset = datetime.fromisoformat(rate_data.get('daily_reset', current_time.isoformat()))
        if current_time >= daily_reset:
            rate_data['daily_count'] = 0
            tier = rate_data.get('tier', 'authenticated')
            rate_data['daily_reset'] = self._get_next_daily_reset(
                current_time,
                self.TIER_LIMITS[tier]['daily_reset_hour']
            ).isoformat()
        
        # Reset hourly counter
        hourly_reset = datetime.fromisoformat(rate_data.get('hourly_reset', current_time.isoformat()))
        if current_time >= hourly_reset:
            rate_data['hourly_count'] = 0
            rate_data['hourly_reset'] = (current_time + timedelta(hours=1)).isoformat()
        
        # Reset minute counter
        minute_reset = datetime.fromisoformat(rate_data.get('minute_reset', current_time.isoformat()))
        if current_time >= minute_reset:
            rate_data['minute_count'] = 0
            rate_data['minute_reset'] = (current_time + timedelta(minutes=1)).isoformat()
        
        return rate_data
    
    def _check_burst_limit(self, rate_data: Dict[str, Any], current_timestamp: int, burst_limit: int) -> bool:
        """Check if user has exceeded burst limit (rapid requests)."""
        request_history = rate_data.get('request_history', [])
        
        # Count requests in last 2 seconds
        recent_requests = [ts for ts in request_history if current_timestamp - ts < 2]
        
        return len(recent_requests) >= burst_limit
    
    def _update_counts(self, user_id: str, rate_data: Dict[str, Any], window_key: str) -> None:
        """Update rate limit counts in DynamoDB."""
        try:
            self.table.update_item(
                Key={'identifier': user_id, 'window': window_key},
                UpdateExpression="""
                    SET daily_count = :daily,
                        hourly_count = :hourly,
                        minute_count = :minute,
                        last_request = :last_req,
                        request_history = :history,
                        updated_at = :updated,
                        daily_reset = :daily_reset,
                        hourly_reset = :hourly_reset,
                        minute_reset = :minute_reset
                """,
                ExpressionAttributeValues={
                    ':daily': rate_data['daily_count'],
                    ':hourly': rate_data['hourly_count'],
                    ':minute': rate_data['minute_count'],
                    ':last_req': rate_data['last_request'],
                    ':history': rate_data.get('request_history', []),
                    ':updated': datetime.utcnow().isoformat(),
                    ':daily_reset': rate_data['daily_reset'],
                    ':hourly_reset': rate_data['hourly_reset'],
                    ':minute_reset': rate_data['minute_reset']
                }
            )
        except Exception as e:
            logger.error(f"Failed to update rate limit counts", extra={
                'user_id': user_id,
                'error': str(e)
            })
    
    def _get_next_daily_reset(self, current_time: datetime, reset_hour: int) -> datetime:
        """Calculate the next daily reset time."""
        reset_time = current_time.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
        
        if current_time >= reset_time:
            # Reset has already passed today, next reset is tomorrow
            reset_time += timedelta(days=1)
        
        return reset_time
    
    def _format_rate_info(self, rate_data: Dict[str, Any], limits: Dict[str, Any], tier: str) -> Dict[str, Any]:
        """Format rate limit information for response."""
        return {
            'tier': tier,
            'limits': {
                'daily': limits['daily'],
                'hourly': limits['hourly'],
                'per_minute': limits['per_minute']
            },
            'remaining': {
                'daily': max(0, limits['daily'] - rate_data.get('daily_count', 0)),
                'hourly': max(0, limits['hourly'] - rate_data.get('hourly_count', 0)),
                'per_minute': max(0, limits['per_minute'] - rate_data.get('minute_count', 0))
            },
            'resets': {
                'daily': rate_data.get('daily_reset'),
                'hourly': rate_data.get('hourly_reset'),
                'per_minute': rate_data.get('minute_reset')
            },
            'features': {
                'message_history': limits['message_history'],
                'session_ttl_hours': limits['session_ttl_hours']
            }
        }
    
    def _get_upgrade_suggestion(self, tier: str) -> Dict[str, str]:
        """Get upgrade suggestion based on current tier."""
        suggestions = {
            'anonymous': {
                'action': 'sign_in',
                'message': 'Sign in with Google for 20 free queries per day',
                'benefits': ['Save chat history', 'Personalized responses', '4x more queries']
            },
            'authenticated': {
                'action': 'upgrade',
                'message': 'Upgrade to Premium for unlimited queries',
                'benefits': ['Unlimited queries', 'Priority support', 'Advanced features']
            }
        }
        
        return suggestions.get(tier, {})
    
    async def get_usage_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get detailed usage statistics for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Dictionary with usage statistics
        """
        try:
            # Use today's date as the window for stats
            window_key = datetime.utcnow().strftime('%Y-%m-%d')
            response = self.table.get_item(Key={'identifier': user_id, 'window': window_key})
            
            if 'Item' not in response:
                return {'status': 'no_data', 'user_id': user_id}
            
            rate_data = response['Item']
            tier = rate_data.get('tier', 'authenticated')
            limits = self.TIER_LIMITS[tier]
            
            return {
                'user_id': user_id,
                'tier': tier,
                'usage': {
                    'daily': rate_data.get('daily_count', 0),
                    'hourly': rate_data.get('hourly_count', 0),
                    'minute': rate_data.get('minute_count', 0)
                },
                'limits': limits,
                'last_request': rate_data.get('last_request'),
                'created_at': rate_data.get('created_at'),
                'resets': {
                    'daily': rate_data.get('daily_reset'),
                    'hourly': rate_data.get('hourly_reset')
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get usage stats", extra={
                'user_id': user_id,
                'error': str(e)
            })
            return {'status': 'error', 'user_id': user_id, 'error': str(e)}


# Convenience function for direct import
rate_limiter = TieredRateLimiter()