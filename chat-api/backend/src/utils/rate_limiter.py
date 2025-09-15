"""
Rate Limiter Module for Anonymous User Rate Limiting
Implements device fingerprinting and monthly usage tracking
"""

import boto3
import json
import hashlib
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# Configure logging
logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Rate limiting system for anonymous and authenticated users
    
    Features:
    - Device fingerprinting using IP + User-Agent + CloudFront headers
    - Monthly usage windows (resets on 1st of each month)
    - Configurable limits per user type
    - Grace period for new devices
    - Automatic cleanup via TTL
    """
    
    def __init__(self):
        """Initialize DynamoDB clients and configuration"""
        self.dynamodb = boto3.resource('dynamodb')
        
        # Environment variables with defaults
        self.rate_limits_table_name = os.environ.get('RATE_LIMITS_TABLE', 'buffett-chat-api-dev-rate-limits')
        self.usage_tracking_table_name = os.environ.get('USAGE_TRACKING_TABLE', 'buffett-chat-api-dev-usage-tracking')
        
        # Rate limiting configuration
        self.anonymous_limit = int(os.environ.get('ANONYMOUS_MONTHLY_LIMIT', '5'))
        self.authenticated_limit = int(os.environ.get('AUTHENTICATED_MONTHLY_LIMIT', '500'))
        self.enable_fingerprinting = os.environ.get('ENABLE_DEVICE_FINGERPRINTING', 'true').lower() == 'true'
        self.grace_period_hours = int(os.environ.get('RATE_LIMIT_GRACE_PERIOD_HOURS', '1'))
        self.enable_rate_limiting = os.environ.get('ENABLE_RATE_LIMITING', 'true').lower() == 'true'
        
        # Initialize tables
        try:
            self.rate_limits_table = self.dynamodb.Table(self.rate_limits_table_name)
            self.usage_table = self.dynamodb.Table(self.usage_tracking_table_name)
        except Exception as e:
            logger.error(f"Failed to initialize DynamoDB tables: {str(e)}")
            # Gracefully degrade - disable rate limiting if tables don't exist
            self.enable_rate_limiting = False

    def get_client_identifier(self, event: Dict[str, Any]) -> Tuple[str, str]:
        """
        Generate unique identifier for rate limiting
        
        Returns:
            Tuple of (identifier, user_type)
            - identifier: unique string for this device/user
            - user_type: "anonymous", "authenticated", or "premium"
        """
        headers = event.get('headers', {})
        request_context = event.get('requestContext', {})
        
        # Check if user is authenticated
        authorizer = request_context.get('authorizer', {})
        if authorizer and authorizer.get('jwt'):
            user_id = authorizer.get('jwt', {}).get('claims', {}).get('sub')
            if user_id:
                return f"user:{user_id}", "authenticated"
        
        # For anonymous users, create device fingerprint
        if self.enable_fingerprinting:
            # Primary fingerprint components
            ip = self._extract_client_ip(headers)
            user_agent = headers.get('user-agent', 'unknown')[:200]  # Limit length
            
            # Additional CloudFront headers for better fingerprinting
            cf_country = headers.get('cloudfront-viewer-country', '')
            cf_device = headers.get('cloudfront-is-mobile-viewer', '') + headers.get('cloudfront-is-tablet-viewer', '')
            accept_language = headers.get('accept-language', '')[:50]  # First part only
            
            # Create composite fingerprint
            fingerprint_data = f"{ip}:{user_agent}:{cf_country}:{cf_device}:{accept_language}"
            fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
            
            return f"anon:{fingerprint}", "anonymous"
        else:
            # Fallback to IP-only
            ip = self._extract_client_ip(headers)
            ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:12]
            return f"ip:{ip_hash}", "anonymous"

    def _extract_client_ip(self, headers: Dict[str, str]) -> str:
        """Extract client IP from headers, handling various proxy configurations"""
        # Try different headers in order of preference
        ip_headers = [
            'x-forwarded-for',
            'x-real-ip',
            'x-client-ip',
            'x-forwarded',
            'forwarded-for',
            'forwarded'
        ]
        
        for header in ip_headers:
            ip = headers.get(header)
            if ip:
                # x-forwarded-for can contain multiple IPs, take the first (original client)
                return ip.split(',')[0].strip()
        
        # Fallback to request context sourceIp
        return headers.get('sourceIp', 'unknown')

    def check_rate_limit(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Check if request is within rate limits
        
        Returns:
            Dictionary with rate limit status:
            - allowed: bool - whether request should be allowed
            - limit: int - monthly limit for this user type
            - current: int - current usage count
            - remaining: int - remaining requests
            - reset_date: str - when limit resets
            - identifier: str - anonymized identifier for debugging
        """
        if not self.enable_rate_limiting:
            return {
                "allowed": True,
                "limit": self.anonymous_limit,
                "current": 0,
                "remaining": self.anonymous_limit,
                "reset_date": self._get_next_reset_date(),
                "identifier": "rate_limiting_disabled"
            }
        
        try:
            identifier, user_type = self.get_client_identifier(event)
            current_month = datetime.now().strftime("%Y-%m")
            
            # Get limit for user type
            limit = self._get_limit_for_user_type(user_type)
            
            # Check if this is within grace period for new devices
            if self._is_within_grace_period(identifier):
                logger.info(f"Grace period active for {identifier[:20]}...")
                return self._create_allowed_response(limit, 0)
            
            # Get current usage for this month
            current_usage = self._get_monthly_usage(identifier, current_month)
            
            if current_usage >= limit:
                logger.warning(f"Rate limit exceeded for {identifier[:20]}...: {current_usage}/{limit}")
                return {
                    "allowed": False,
                    "limit": limit,
                    "current": current_usage,
                    "remaining": 0,
                    "reset_date": self._get_next_reset_date(),
                    "identifier": identifier[:20] + "..." if len(identifier) > 20 else identifier
                }
            
            # Record this usage
            self._record_usage(identifier, user_type, current_month)
            
            return self._create_allowed_response(limit, current_usage + 1)
            
        except Exception as e:
            logger.error(f"Rate limiting error: {str(e)}")
            # Fail open for availability - allow the request but log the error
            return self._create_allowed_response(self.anonymous_limit, 0)

    def _get_limit_for_user_type(self, user_type: str) -> int:
        """Get monthly limit based on user type"""
        limits = {
            "anonymous": self.anonymous_limit,
            "authenticated": self.authenticated_limit,
            "premium": self.authenticated_limit * 4  # Future premium tier
        }
        return limits.get(user_type, self.anonymous_limit)

    def _is_within_grace_period(self, identifier: str) -> bool:
        """Check if identifier is within grace period"""
        if self.grace_period_hours <= 0:
            return False
        
        try:
            # Check if we've seen this identifier before
            grace_cutoff = datetime.now() - timedelta(hours=self.grace_period_hours)
            
            response = self.usage_table.query(
                KeyConditionExpression=Key('user_identifier').eq(identifier),
                ScanIndexForward=False,  # Newest first
                Limit=1
            )
            
            if not response['Items']:
                # New identifier - within grace period
                return True
            
            # Check if first usage was within grace period
            first_usage = response['Items'][0]
            first_timestamp = datetime.fromisoformat(first_usage['timestamp'].replace('Z', '+00:00'))
            
            return first_timestamp >= grace_cutoff
            
        except Exception as e:
            logger.error(f"Grace period check error: {str(e)}")
            return False

    def _get_monthly_usage(self, identifier: str, month: str) -> int:
        """Get usage count for the current month"""
        try:
            response = self.usage_table.query(
                IndexName="monthly-usage-index",
                KeyConditionExpression=Key('user_identifier').eq(identifier) & Key('time_window').eq(month),
                Select='COUNT'
            )
            return response['Count']
        except Exception as e:
            logger.error(f"Error getting monthly usage: {str(e)}")
            return 0

    def _record_usage(self, identifier: str, user_type: str, month: str):
        """Record a new API usage"""
        try:
            now = datetime.now()
            expires_at = int((now + timedelta(days=93)).timestamp())  # 3 months TTL
            
            # Record individual usage
            self.usage_table.put_item(
                Item={
                    'user_identifier': identifier,
                    'timestamp': now.isoformat(),
                    'time_window': month,
                    'user_type': user_type,
                    'expires_at': expires_at
                }
            )
            
            # Update/create monthly aggregate
            self.rate_limits_table.update_item(
                Key={
                    'identifier': identifier,
                    'time_window': month
                },
                UpdateExpression='ADD usage_count :inc SET user_type = :user_type, expires_at = :expires_at, last_updated = :now',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':user_type': user_type,
                    ':expires_at': expires_at,
                    ':now': now.isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error recording usage: {str(e)}")

    def _get_next_reset_date(self) -> str:
        """Get the next monthly reset date"""
        now = datetime.now()
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        
        return next_month.strftime("%Y-%m-%d")

    def _create_allowed_response(self, limit: int, current: int) -> Dict[str, Any]:
        """Create a response for allowed requests"""
        return {
            "allowed": True,
            "limit": limit,
            "current": current,
            "remaining": max(0, limit - current),
            "reset_date": self._get_next_reset_date(),
            "identifier": "allowed"
        }


def rate_limit_decorator(func):
    """
    Decorator to add rate limiting to Lambda functions
    
    Usage:
        @rate_limit_decorator
        def lambda_handler(event, context):
            # Your Lambda function code
            return response
    """
    def wrapper(event, context):
        rate_limiter = RateLimiter()
        
        # Check rate limit
        rate_check = rate_limiter.check_rate_limit(event)
        
        if not rate_check["allowed"]:
            # Return 429 Too Many Requests
            return {
                'statusCode': 429,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-RateLimit-Limit': str(rate_check["limit"]),
                    'X-RateLimit-Remaining': str(rate_check["remaining"]),
                    'X-RateLimit-Reset': rate_check["reset_date"],
                    'Access-Control-Allow-Origin': '*',  # CORS
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                },
                'body': json.dumps({
                    'error': 'Rate limit exceeded',
                    'message': f'You have exceeded your limit of {rate_check["limit"]} requests per month. Limit resets on {rate_check["reset_date"]}.',
                    'limit': rate_check["limit"],
                    'current': rate_check["current"],
                    'reset_date': rate_check["reset_date"],
                    'type': 'RATE_LIMIT_EXCEEDED'
                })
            }
        
        # Execute the original function
        try:
            response = func(event, context)
            
            # Add rate limit headers to successful responses
            if isinstance(response, dict) and 'headers' in response:
                response['headers'].update({
                    'X-RateLimit-Limit': str(rate_check["limit"]),
                    'X-RateLimit-Remaining': str(rate_check["remaining"]),
                    'X-RateLimit-Reset': rate_check["reset_date"]
                })
            elif isinstance(response, dict):
                response['headers'] = {
                    'X-RateLimit-Limit': str(rate_check["limit"]),
                    'X-RateLimit-Remaining': str(rate_check["remaining"]),
                    'X-RateLimit-Reset': rate_check["reset_date"]
                }
            
            return response
            
        except Exception as e:
            logger.error(f"Error in decorated function: {str(e)}")
            # Return error response with rate limit headers
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-RateLimit-Limit': str(rate_check["limit"]),
                    'X-RateLimit-Remaining': str(rate_check["remaining"]),
                    'X-RateLimit-Reset': rate_check["reset_date"]
                },
                'body': json.dumps({
                    'error': 'Internal server error',
                    'message': 'An unexpected error occurred'
                })
            }
    
    return wrapper


# Utility function for manual rate limit checking
def check_rate_limit_manual(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Manual rate limit check without decorator
    Useful for custom handling logic
    """
    rate_limiter = RateLimiter()
    return rate_limiter.check_rate_limit(event)

