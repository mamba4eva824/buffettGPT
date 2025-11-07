"""
Google OAuth Callback Handler
Handles Google Sign-In tokens and creates JWT sessions
"""

import json
import os
import boto3
import jwt
import time
from datetime import datetime, timedelta
from google.auth.transport import requests
from google.oauth2 import id_token
import logging
from typing import Dict, Any, Optional
from functools import lru_cache

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables - Now using ARNs for secrets
GOOGLE_OAUTH_SECRET_ARN = os.environ.get('GOOGLE_OAUTH_SECRET_ARN')
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')
USERS_TABLE = os.environ.get('USERS_TABLE', 'buffett-dev-users')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# DynamoDB table
users_table = dynamodb.Table(USERS_TABLE)

@lru_cache(maxsize=2)
def get_secret(secret_arn: str) -> str:
    """
    Fetch secret from AWS Secrets Manager with caching

    Args:
        secret_arn: ARN of the secret to fetch

    Returns:
        Secret value as string
    """
    try:
        response = secrets_client.get_secret_value(SecretId=secret_arn)
        return response['SecretString']
    except Exception as e:
        logger.error(f"Failed to fetch secret from Secrets Manager", extra={
            'secret_arn': secret_arn,
            'error': str(e)
        })
        raise

def get_google_credentials() -> Dict[str, str]:
    """Get Google OAuth credentials from Secrets Manager"""
    if GOOGLE_OAUTH_SECRET_ARN:
        secret_data = get_secret(GOOGLE_OAUTH_SECRET_ARN)
        return json.loads(secret_data)
    else:
        # Fallback to environment variables for backward compatibility
        return {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID', ''),
            'client_secret': os.environ.get('GOOGLE_CLIENT_SECRET', '')
        }

def get_jwt_secret() -> str:
    """Get JWT secret from Secrets Manager"""
    if JWT_SECRET_ARN:
        try:
            secret = get_secret(JWT_SECRET_ARN)
            if not secret or len(secret) < 32:
                raise ValueError("JWT secret must be at least 32 characters long")
            return secret
        except Exception as e:
            logger.error("Failed to fetch JWT secret from Secrets Manager")
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

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle Google OAuth callback

    Args:
        event: API Gateway event containing the Google ID token
        context: Lambda context

    Returns:
        Response with JWT token and user info
    """

    logger.info(f"Auth callback request received", extra={
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'request_id': context.aws_request_id,
        'method': event.get('requestContext', {}).get('http', {}).get('method', 'UNKNOWN')
    })

    # Handle OPTIONS request for CORS preflight
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return create_response(200, {'message': 'OK'}, event)

    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        google_token = body.get('credential')

        if not google_token:
            return create_response(400, {
                'error': 'Missing credential',
                'message': 'Google ID token is required'
            }, event)

        # Get Google credentials
        google_creds = get_google_credentials()
        google_client_id = google_creds.get('client_id')

        # Verify Google ID token
        try:
            # Verify the token with Google
            idinfo = id_token.verify_oauth2_token(
                google_token,
                requests.Request(),
                google_client_id
            )

            # Extract user information
            user_id = idinfo['sub']  # Google user ID
            email = idinfo['email']
            name = idinfo.get('name', '')
            picture = idinfo.get('picture', '')
            email_verified = idinfo.get('email_verified', False)

            logger.info(f"Google token verified", extra={
                'user_id': user_id,
                'email': email,
                'email_verified': email_verified
            })

        except Exception as e:
            logger.error(f"Failed to verify Google token", extra={
                'error': str(e)
            })
            return create_response(401, {
                'error': 'Invalid token',
                'message': 'Failed to verify Google credentials'
            }, event)

        # Check if email is verified
        if not email_verified:
            return create_response(403, {
                'error': 'Email not verified',
                'message': 'Please verify your Google account email'
            }, event)

        # Store or update user in DynamoDB
        current_time = datetime.utcnow()
        user_data = {
            'user_id': user_id,
            'email': email,
            'name': name,
            'picture': picture,
            'provider': 'google',
            'created_at': current_time.isoformat(),
            'updated_at': current_time.isoformat(),
            'last_login': current_time.isoformat(),
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'subscription_tier': 'free',  # Default tier
            'status': 'active'
        }

        # Try to update existing user or create new one
        try:
            users_table.update_item(
                Key={'user_id': user_id},
                UpdateExpression='SET #email = :email, #name = :name, #picture = :picture, '
                                '#updated_at = :updated_at, #last_login = :last_login',
                ExpressionAttributeNames={
                    '#email': 'email',
                    '#name': 'name',
                    '#picture': 'picture',
                    '#updated_at': 'updated_at',
                    '#last_login': 'last_login'
                },
                ExpressionAttributeValues={
                    ':email': email,
                    ':name': name,
                    ':picture': picture,
                    ':updated_at': current_time.isoformat(),
                    ':last_login': current_time.isoformat()
                }
            )
            logger.info(f"User updated", extra={'user_id': user_id})
        except Exception as e:
            # If update fails, try to create new user
            try:
                users_table.put_item(Item=user_data)
                logger.info(f"New user created", extra={'user_id': user_id})
            except Exception as create_error:
                logger.error(f"Failed to store user", extra={
                    'user_id': user_id,
                    'error': str(create_error)
                })

        # Generate JWT token
        jwt_payload = {
            'user_id': user_id,
            'email': email,
            'name': name,
            'subscription_tier': user_data.get('subscription_tier', 'free'),
            'exp': int((current_time + timedelta(days=7)).timestamp()),  # 7-day expiry
            'iat': int(current_time.timestamp()),
            'iss': PROJECT_NAME
        }

        jwt_secret = get_jwt_secret()
        jwt_token = jwt.encode(jwt_payload, jwt_secret, algorithm='HS256')

        # Prepare response
        response_data = {
            'token': jwt_token,
            'user': {
                'id': user_id,
                'email': email,
                'name': name,
                'picture': picture,
                'subscription_tier': user_data.get('subscription_tier', 'free')
            },
            'expires_in': 604800  # 7 days in seconds
        }

        logger.info(f"Authentication successful", extra={
            'user_id': user_id,
            'email': email
        })

        return create_response(200, response_data, event)

    except Exception as e:
        logger.error(f"Authentication error", extra={
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)

        return create_response(500, {
            'error': 'Internal server error',
            'message': 'Failed to process authentication'
        }, event)

def create_response(status_code: int, body: Any, event: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create API Gateway response with CORS headers

    Args:
        status_code: HTTP status code
        body: Response body
        event: Optional event object to extract origin from

    Returns:
        API Gateway response
    """

    # Whitelist of allowed origins - configure based on environment
    allowed_origins = []

    if ENVIRONMENT == 'prod':
        allowed_origins = [
            'https://buffettgpt.com',
            'https://www.buffettgpt.com',
            'https://app.buffettgpt.com'
        ]
    elif ENVIRONMENT == 'staging':
        allowed_origins = [
            'https://staging.buffettgpt.com',
            'https://staging-app.buffettgpt.com'
        ]
    else:  # dev environment
        allowed_origins = [
            'http://localhost:3000',
            'http://localhost:5173',
            'http://127.0.0.1:3000',
            'http://127.0.0.1:5173'
        ]

    # Extract origin from request headers
    origin = None
    if event:
        headers = event.get('headers', {})
        origin = headers.get('origin') or headers.get('Origin', '')

    # Only set CORS header if origin is in allowlist
    cors_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'POST,OPTIONS',
        'Access-Control-Max-Age': '3600'
    }

    # Add origin header only if it's in the allowlist
    if origin and origin in allowed_origins:
        cors_headers['Access-Control-Allow-Origin'] = origin
        cors_headers['Vary'] = 'Origin'

    return {
        'statusCode': status_code,
        'headers': cors_headers,
        'body': json.dumps(body)
    }