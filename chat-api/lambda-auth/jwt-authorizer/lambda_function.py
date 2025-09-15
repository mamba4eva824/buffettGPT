import json
import os
import jwt
import time
import boto3
from datetime import datetime
import logging

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')

# Environment variables
JWT_SECRET_NAME = os.environ['JWT_SECRET_NAME']
SESSIONS_TABLE = os.environ['SESSIONS_TABLE']
SECURITY_EVENTS_TABLE = os.environ['SECURITY_EVENTS_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')

# Cache for JWT secret
jwt_secret_cache = None
jwt_secret_cache_time = 0
JWT_SECRET_CACHE_TTL = 300  # 5 minutes

def get_jwt_secret():
    """Get JWT secret from Secrets Manager with caching"""
    global jwt_secret_cache, jwt_secret_cache_time
    
    current_time = time.time()
    if jwt_secret_cache and (current_time - jwt_secret_cache_time) < JWT_SECRET_CACHE_TTL:
        return jwt_secret_cache
    
    try:
        response = secrets_client.get_secret_value(SecretId=JWT_SECRET_NAME)
        jwt_secret_cache = response['SecretString']
        jwt_secret_cache_time = current_time
        return jwt_secret_cache
    except Exception as e:
        logger.error(f"Error retrieving JWT secret: {str(e)}")
        raise Exception('Unable to retrieve JWT secret')

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
            'details': details or {},
            'ttl': int(time.time()) + (90 * 24 * 60 * 60)  # 90 days retention
        }
        
        if user_id:
            item['user_id'] = user_id
        
        security_table.put_item(Item=item)
    except Exception as e:
        logger.error(f"Error logging security event: {str(e)}")

def lambda_handler(event, context):
    """
    API Gateway Custom Authorizer for JWT validation
    Supports both HTTP API and WebSocket API
    """
    try:
        # Debug: Log the full event structure for WebSocket debugging
        logger.info(f"Authorizer event: {json.dumps(event, default=str)}")
        # Extract token based on event type
        token = None
        method_arn = None
        
        # Check if this is a WebSocket request
        if 'methodArn' in event:
            # REST API or WebSocket $connect
            method_arn = event['methodArn']
            
            # Try to get token from different sources
            if 'authorizationToken' in event:
                token = event['authorizationToken']
            elif 'headers' in event:
                # WebSocket connection might have token in headers
                auth_header = event['headers'].get('Authorization') or event['headers'].get('authorization')
                if auth_header:
                    token = auth_header
            elif 'queryStringParameters' in event:
                # WebSocket might pass token as query parameter
                token = event['queryStringParameters'].get('token')
        
        # HTTP API format
        elif 'headers' in event and 'authorization' in event['headers']:
            token = event['headers']['authorization']
            method_arn = event['routeArn'] if 'routeArn' in event else event['methodArn']
        
        if not token:
            logger.warning("No authorization token provided")
            log_security_event('jwt_validation_failed', details={'error': 'No token provided'}, success=False)
            raise Exception('Unauthorized')
        
        # Remove 'Bearer ' prefix if present
        if token.startswith('Bearer '):
            token = token[7:]
        
        # Get JWT secret
        jwt_secret = get_jwt_secret()
        
        # Verify JWT token
        try:
            payload = jwt.decode(token, jwt_secret, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            log_security_event('jwt_validation_failed', details={'error': 'Token expired'}, success=False)
            raise Exception('Unauthorized - Token expired')
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {str(e)}")
            log_security_event('jwt_validation_failed', details={'error': 'Invalid token'}, success=False)
            raise Exception('Unauthorized - Invalid token')
        
        # Extract user information
        user_id = payload.get('user_id')
        session_id = payload.get('session_id')
        
        if not user_id or not session_id:
            logger.warning("Token missing required claims")
            log_security_event('jwt_validation_failed', user_id=user_id, 
                             details={'error': 'Missing claims'}, success=False)
            raise Exception('Unauthorized - Invalid token claims')
        
        # Verify session is still valid
        sessions_table = dynamodb.Table(SESSIONS_TABLE)
        try:
            response = sessions_table.get_item(Key={'session_id': session_id})
            if 'Item' not in response:
                logger.warning(f"Session not found: {session_id}")
                log_security_event('session_validation_failed', user_id=user_id,
                                 details={'session_id': session_id}, success=False)
                raise Exception('Unauthorized - Invalid session')
            
            session = response['Item']
            
            # Verify session belongs to user
            if session['user_id'] != user_id:
                logger.warning("Session user mismatch")
                log_security_event('session_validation_failed', user_id=user_id,
                                 details={'error': 'User mismatch'}, success=False)
                raise Exception('Unauthorized - Invalid session')
            
            # Update last activity
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET last_activity = :activity',
                ExpressionAttributeValues={
                    ':activity': datetime.utcnow().isoformat()
                }
            )
            
        except Exception as e:
            logger.error(f"Error validating session: {str(e)}")
            raise Exception('Unauthorized')
        
        # Log successful validation
        log_security_event('jwt_validation_success', user_id=user_id, success=True)
        
        # Generate policy
        policy = generate_policy(user_id, 'Allow', method_arn)
        
        # Add context for downstream services
        policy['context'] = {
            'user_id': user_id,
            'session_id': session_id,
            'email': session.get('email', ''),
            'subscription_tier': session.get('subscription_tier', 'free')
        }
        
        return policy
        
    except Exception as e:
        logger.error(f"Authorization error: {str(e)}")
        raise Exception('Unauthorized')

def generate_policy(principal_id, effect, resource):
    """Generate API Gateway policy"""
    policy = {
        'principalId': principal_id
    }
    
    if effect and resource:
        policy['policyDocument'] = {
            'Version': '2012-10-17',
            'Statement': [
                {
                    'Action': 'execute-api:Invoke',
                    'Effect': effect,
                    'Resource': resource
                }
            ]
        }
    
    return policy