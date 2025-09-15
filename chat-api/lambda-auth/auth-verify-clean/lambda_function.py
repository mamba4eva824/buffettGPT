import json
import os
import jwt
import uuid
import time
import boto3
from datetime import datetime, timedelta
from google.auth.transport import requests
from google.oauth2 import id_token
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables
GOOGLE_CLIENT_ID_SECRET = os.environ['GOOGLE_CLIENT_ID_SECRET']
JWT_SECRET_NAME = os.environ['JWT_SECRET_NAME']
USERS_TABLE = os.environ['USERS_TABLE']
SESSIONS_TABLE = os.environ['SESSIONS_TABLE']
SECURITY_EVENTS_TABLE = os.environ['SECURITY_EVENTS_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat')

# Cache for secrets
secrets_cache = {}
secrets_cache_time = {}
SECRETS_CACHE_TTL = 300  # 5 minutes

def get_secret(secret_name):
    """Get secret from Secrets Manager with caching"""
    current_time = time.time()
    
    if secret_name in secrets_cache and (current_time - secrets_cache_time.get(secret_name, 0)) < SECRETS_CACHE_TTL:
        return secrets_cache[secret_name]
    
    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_value = response['SecretString']
        
        # Try to parse as JSON, otherwise return as string
        try:
            secret_value = json.loads(secret_value)
        except json.JSONDecodeError:
            pass
        
        secrets_cache[secret_name] = secret_value
        secrets_cache_time[secret_name] = current_time
        return secret_value
    except Exception as e:
        logger.error(f"Error retrieving secret {secret_name}: {str(e)}")
        raise

def log_security_event(event_type, user_id=None, details=None, success=True):
    """Log security events to DynamoDB"""
    try:
        security_table = dynamodb.Table(SECURITY_EVENTS_TABLE)
        event_id = f"{event_type}_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
        
        item = {
            'event_id': event_id,
            'timestamp': int(time.time() * 1000),
            'event_type': event_type,
            'success': success,
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'details': details or {},
            'ttl': int(time.time()) + (90 * 24 * 60 * 60)  # 90 days retention
        }
        
        if user_id:
            item['user_id'] = user_id
        
        security_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")

def lambda_handler(event, context):
    """Handle Google OAuth authentication requests"""
    try:
        # Debug logging
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Get HTTP method from API Gateway v2.0 format
        http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method')
        logger.info(f"HTTP Method: {http_method}")
        
        # Handle CORS preflight requests
        if http_method == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
                },
                'body': ''
            }
        
        # Parse request
        body = json.loads(event.get('body', '{}'))
        google_token = body.get('token')
        
        if not google_token:
            log_security_event('auth_failed', details={'error': 'No token provided'}, success=False)
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,POST'
                },
                'body': json.dumps({'error': 'Google token is required'})
            }
        
        # Get Google client ID
        google_secrets = get_secret(GOOGLE_CLIENT_ID_SECRET)
        google_client_id = google_secrets['client_id'] if isinstance(google_secrets, dict) else google_secrets
        
        # Verify Google token
        try:
            idinfo = id_token.verify_oauth2_token(google_token, requests.Request(), google_client_id)
            
            # Verify the issuer
            if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Invalid issuer')
            
            user_info = {
                'user_id': idinfo['sub'],
                'email': idinfo['email'],
                'name': idinfo.get('name', ''),
                'picture': idinfo.get('picture', ''),
                'email_verified': idinfo.get('email_verified', False)
            }
            
        except ValueError as e:
            logger.warning(f"Google token verification failed: {str(e)}")
            log_security_event('google_auth_failed', details={'error': str(e)}, success=False)
            return {
                'statusCode': 401,
                'headers': {'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Invalid Google token'})
            }
        
        # Create or update user
        user_data = create_or_update_user(user_info)
        
        # Create session
        session_data = create_user_session(user_data['user_id'], user_data['email'])
        
        # Generate JWT token
        jwt_secret = get_secret(JWT_SECRET_NAME)
        jwt_token = generate_jwt_token(user_data['user_id'], session_data['session_id'], jwt_secret)
        
        # Log successful authentication
        log_security_event('auth_success', user_id=user_data['user_id'], success=True)
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'
            },
            'body': json.dumps({
                'token': jwt_token,
                'user': {
                    'id': user_data['user_id'],
                    'email': user_data['email'],
                    'name': user_data['name'],
                    'picture': user_data.get('picture', ''),
                    'subscription_tier': user_data.get('subscription_tier', 'free'),
                    'preferences': user_data.get('preferences', {})
                },
                'session': {
                    'id': session_data['session_id'],
                    'expires_at': session_data['expires_at']
                }
            })
        }
        
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        log_security_event('auth_error', details={'error': str(e)}, success=False)
        return {
            'statusCode': 500,
            'headers': {'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': 'Internal server error'})
        }

def create_or_update_user(user_info):
    """Create new user or update existing user in DynamoDB"""
    users_table = dynamodb.Table(USERS_TABLE)
    
    user_data = {
        'user_id': user_info['user_id'],
        'email': user_info['email'],
        'name': user_info['name'],
        'picture': user_info['picture'],
        'email_verified': user_info['email_verified'],
        'updated_at': datetime.utcnow().isoformat(),
        'subscription_tier': 'free',
        'preferences': {
            'risk_tolerance': 'moderate',
            'investment_goals': [],
            'notifications_enabled': True,
            'theme': 'light'
        }
    }
    
    # Check if user exists
    try:
        response = users_table.get_item(Key={'user_id': user_info['user_id']})
        if 'Item' in response:
            # User exists, preserve certain fields
            existing_user = response['Item']
            user_data['created_at'] = existing_user.get('created_at', user_data['updated_at'])
            user_data['subscription_tier'] = existing_user.get('subscription_tier', 'free')
            user_data['preferences'] = existing_user.get('preferences', user_data['preferences'])
        else:
            # New user
            user_data['created_at'] = user_data['updated_at']
            log_security_event('new_user_created', user_id=user_info['user_id'], success=True)
    except Exception as e:
        logger.error(f"Error checking existing user: {str(e)}")
        user_data['created_at'] = user_data['updated_at']
    
    # Save user
    users_table.put_item(Item=user_data)
    
    return user_data

def create_user_session(user_id, email):
    """Create a new user session"""
    sessions_table = dynamodb.Table(SESSIONS_TABLE)
    
    session_id = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(days=7)  # 7 day expiration
    
    session_data = {
        'session_id': session_id,
        'user_id': user_id,
        'email': email,
        'created_at': datetime.utcnow().isoformat(),
        'expires_at': int(expires_at.timestamp()),  # Unix timestamp for TTL
        'last_activity': datetime.utcnow().isoformat(),
        'ip_address': None,  # Can be populated from API Gateway context
        'user_agent': None   # Can be populated from headers
    }
    
    sessions_table.put_item(Item=session_data)
    
    return session_data

def generate_jwt_token(user_id, session_id, jwt_secret):
    """Generate JWT token for authenticated user"""
    payload = {
        'user_id': user_id,
        'session_id': session_id,
        'iat': datetime.utcnow(),
        'exp': datetime.utcnow() + timedelta(days=7)
    }
    
    return jwt.encode(payload, jwt_secret, algorithm='HS256')