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
            secret = response['SecretString']
            if not secret or len(secret) < 32:
                raise ValueError("JWT secret must be at least 32 characters long")
            return secret
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret from Secrets Manager", extra={
                'secret_arn': JWT_SECRET_ARN,
                'error': str(e)
            })
            raise Exception("JWT_SECRET not properly configured in Secrets Manager") from e
    else:
        # Require JWT_SECRET environment variable - no default fallback for security
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            logger.error("JWT_SECRET environment variable not set")
            raise ValueError("JWT_SECRET must be set via environment variable or JWT_SECRET_ARN must be configured")
        if len(jwt_secret) < 32:
            logger.error("JWT_SECRET is too short")
            raise ValueError("JWT_SECRET must be at least 32 characters long for security")
        return jwt_secret

def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract JWT token from authorization event

    Supports multiple API Gateway authorizer formats:
    - REST API TOKEN authorizer: event.authorizationToken
    - HTTP API v2 authorizer: event.headers.authorization
    - WebSocket authorizer: query params or headers
    """

    # Check REST API TOKEN authorizer format first
    # REST API TOKEN authorizers pass the full header value in authorizationToken
    # Format: "Bearer <token>" in authorizationToken field
    auth_token = event.get('authorizationToken')
    if auth_token:
        if auth_token.startswith('Bearer '):
            return auth_token[7:]  # Remove 'Bearer ' prefix
        return auth_token  # Return as-is if no Bearer prefix

    # Try Authorization header (HTTP API v2 / WebSocket)
    headers = event.get('headers', {})
    auth_header = headers.get('authorization') or headers.get('Authorization')

    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]  # Remove 'Bearer ' prefix

    # Try token query parameter (WebSocket)
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
    Detect authorization request type to return correct response format.

    Response format requirements:
    - REST API TOKEN authorizers: have 'authorizationToken', need IAM policy
    - HTTP API v2 authorizers: have 'version: 2.0', need simple {"isAuthorized": true}
    - WebSocket authorizers: have methodArn with '/ws/', need IAM policy

    Args:
        event: The authorization event

    Returns:
        "rest_api", "websocket", or "http"
    """
    # REST API TOKEN authorizers have authorizationToken field
    # They need IAM policy response (same as WebSocket)
    if 'authorizationToken' in event:
        return "rest_api"

    # HTTP API v2 specific fields - need simple response
    if 'version' in event and event['version'] == '2.0':
        return "http"

    if 'routeArn' in event:
        return "http"

    # WebSocket or other REST API variants with methodArn
    if 'methodArn' in event:
        method_arn = event['methodArn']
        if '/ws/' in method_arn or '$connect' in method_arn or '$disconnect' in method_arn:
            return "websocket"
        else:
            return "rest_api"  # REST API needs IAM policy too

    # Default to websocket for backward compatibility (IAM policy response)
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
        # Use wildcard resource to allow all endpoints with same token
        # This is important for REST API TOKEN authorizers with caching
        # Without wildcard, cached policy from first request won't match subsequent requests
        # to different paths (e.g., /analysis/debt vs /analysis/cashflow)
        #
        # Convert: arn:aws:execute-api:region:account:api-id/stage/method/resource
        # To:      arn:aws:execute-api:region:account:api-id/stage/*
        wildcard_resource = resource
        if effect == "Allow":
            parts = resource.split('/')
            if len(parts) >= 2:
                # Keep up to stage, then wildcard
                wildcard_resource = '/'.join(parts[:2]) + '/*'

        policy = {
            "principalId": user_id or "anonymous",
            "policyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Action": "execute-api:Invoke",
                        "Effect": effect,
                        "Resource": wildcard_resource
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
            if request_type in ("http", "rest_api"):
                logger.info(f"No token provided for {request_type} request - denying access")
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
                if request_type in ("http", "rest_api"):
                    return create_policy("Deny", method_arn, None, request_type)
                else:
                    return create_policy("Allow", method_arn, None, request_type)

            logger.info(f"Authorization successful for user {user_id}")
            return create_policy("Allow", method_arn, user_id, request_type)

        except Exception as token_error:
            logger.warning(f"Token verification failed: {str(token_error)}")
            if request_type in ("http", "rest_api"):
                # For HTTP API and REST API, deny access on token verification failure
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