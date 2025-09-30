"""
JWT Token Verifier for WebSocket and HTTP API Authorization
Verifies JWT tokens and returns authorization context for WebSocket and HTTP API connections
"""

import json
import os
import boto3
import jwt
import logging
from typing import Dict, Any, Optional
from functools import lru_cache

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')

# Environment variables
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT secret from AWS Secrets Manager with caching"""
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            return response['SecretString']
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret from Secrets Manager", extra={
                'secret_arn': JWT_SECRET_ARN,
                'error': str(e)
            })
            raise
    else:
        # Fallback to environment variable for backward compatibility
        return os.environ.get('JWT_SECRET', 'your-jwt-secret-key')

def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract JWT token from WebSocket event
    Supports both Authorization header and token query parameter
    """

    # Try Authorization header first
    headers = event.get('headers', {})
    auth_header = headers.get('authorization') or headers.get('Authorization')

    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove 'Bearer ' prefix

    # Try token query parameter
    query_params = event.get('queryStringParameters') or {}
    token = query_params.get('token')

    if token:
        return token

    # Try multiValueQueryStringParameters (API Gateway v2 format)
    multi_params = event.get('multiValueQueryStringParameters') or {}
    token_list = multi_params.get('token')
    if token_list and len(token_list) > 0:
        return token_list[0]

    return None

def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verify JWT token and extract claims

    Args:
        token: JWT token string

    Returns:
        Dictionary with user claims

    Raises:
        Exception: If token is invalid
    """

    jwt_secret = get_jwt_secret()

    try:
        # Decode and verify the JWT token
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=['HS256'],
            options={'verify_exp': True}
        )

        logger.info(f"JWT token verified successfully", extra={
            'user_id': payload.get('user_id'),
            'email': payload.get('email'),
            'expires_at': payload.get('exp')
        })

        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        raise Exception("Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {str(e)}")
        raise Exception("Invalid token")
    except Exception as e:
        logger.error(f"JWT verification error: {str(e)}")
        raise Exception("Token verification failed")

def detect_request_type(event: Dict[str, Any]) -> str:
    """
    Detect if this is a WebSocket or HTTP API authorization request

    Args:
        event: The authorization event

    Returns:
        "websocket" or "http"
    """
    # Check for HTTP API v2 specific fields
    if 'version' in event and event['version'] == '2.0':
        return "http"

    # Check for routeArn (HTTP API v2) vs methodArn (WebSocket)
    if 'routeArn' in event:
        return "http"
    elif 'methodArn' in event:
        # Could be either, but check the ARN format
        method_arn = event['methodArn']
        if '/ws/' in method_arn or '$connect' in method_arn or '$disconnect' in method_arn:
            return "websocket"
        else:
            return "http"

    # Default to websocket for backward compatibility
    return "websocket"

def create_policy(effect: str, resource: str, user_id: str = None, request_type: str = "websocket") -> Dict[str, Any]:
    """
    Create IAM policy for API Gateway authorization

    Args:
        effect: "Allow" or "Deny"
        resource: API Gateway resource ARN
        user_id: User ID to include in context
        request_type: "websocket" or "http"

    Returns:
        IAM policy document (for WebSocket) or HTTP API authorizer response (for HTTP)
    """

    if request_type == "http":
        # HTTP API v2 authorizer response format
        response = {
            "isAuthorized": effect == "Allow"
        }

        # Add context if user is authenticated
        if user_id and effect == "Allow":
            response["context"] = {
                "user_id": user_id,
                "environment": ENVIRONMENT,
                "project": PROJECT_NAME
            }

        return response
    else:
        # WebSocket/API Gateway v1 policy format
        policy = {
            "principalId": user_id or "anonymous",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": effect,
                        "Resource": resource
                    }
                ]
            }
        }

        # Add context if user is authenticated
        if user_id and effect == "Allow":
            policy["context"] = {
                "user_id": user_id,
                "environment": ENVIRONMENT,
                "project": PROJECT_NAME
            }

        return policy

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket and HTTP API authorization requests

    Args:
        event: API Gateway authorizer event
        context: Lambda context

    Returns:
        IAM policy for authorization (WebSocket) or HTTP API response (HTTP)
    """

    # Detect request type
    request_type = detect_request_type(event)

    logger.info(f"{request_type.title()} authorization request", extra={
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'request_id': context.aws_request_id,
        'request_type': request_type,
        'method_arn': event.get('methodArn', 'unknown'),
        'route_arn': event.get('routeArn', 'unknown')
    })

    try:
        # Extract the method ARN for the policy (support both HTTP and WebSocket formats)
        method_arn = event.get('methodArn') or event.get('routeArn')
        if not method_arn:
            logger.error("No methodArn or routeArn in event", extra={'event_keys': list(event.keys())})
            raise Exception("Invalid authorization request")

        # Extract JWT token from the request
        token = extract_token(event)

        if not token:
            if request_type == "http":
                logger.info("No token provided for HTTP request - denying access")
                return create_policy("Deny", method_arn, None, request_type)
            else:
                logger.info("No token provided for WebSocket - allowing anonymous access")
                return create_policy("Allow", method_arn, None, request_type)

        # Verify the JWT token
        try:
            claims = verify_jwt_token(token)
            user_id = claims.get('user_id') or claims.get('sub')

            if not user_id:
                logger.warning("JWT token missing user_id")
                if request_type == "http":
                    return create_policy("Deny", method_arn, None, request_type)
                else:
                    return create_policy("Allow", method_arn, None, request_type)

            logger.info(f"Authorization successful for user {user_id}")
            return create_policy("Allow", method_arn, user_id, request_type)

        except Exception as token_error:
            logger.warning(f"Token verification failed: {str(token_error)}")
            if request_type == "http":
                # For HTTP API, deny access on token verification failure
                return create_policy("Deny", method_arn, None, request_type)
            else:
                # For WebSocket, we still allow connection but treat as anonymous
                return create_policy("Allow", method_arn, None, request_type)

    except Exception as e:
        logger.error(f"Authorization error", extra={
            'error': str(e),
            'error_type': type(e).__name__,
            'method_arn': event.get('methodArn', 'unknown')
        }, exc_info=True)

        # In case of errors, deny access to be safe
        method_arn = event.get('methodArn') or event.get('routeArn', '*')
        return create_policy("Deny", method_arn, None, request_type)