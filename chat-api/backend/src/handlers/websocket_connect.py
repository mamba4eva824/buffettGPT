"""
WebSocket Connect Handler
Handles new WebSocket connections by storing connection metadata in DynamoDB.
"""

import json
import boto3
import uuid
import logging
import os
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CONNECTIONS_TABLE = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE', os.environ.get('CONNECTIONS_TABLE', 'buffett-dev-websocket-connections'))
CHAT_SESSIONS_TABLE = os.environ['CHAT_SESSIONS_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# DynamoDB tables
connections_table = dynamodb.Table(CONNECTIONS_TABLE)
sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket connection requests.
    
    Args:
        event: API Gateway WebSocket event
        context: Lambda context
    
    Returns:
        Response with status code and optional body
    """
    
    start_time = time.time()
    connection_id = event['requestContext']['connectionId']
    
    logger.info(f"WebSocket connection request", extra={
        'connection_id': connection_id,
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'event_type': 'websocket_connect',
        'request_id': context.aws_request_id
    })
    
    try:
        # Extract query parameters for session info
        query_params = event.get('queryStringParameters') or {}
        session_id = query_params.get('session_id')

        # Get authenticated user ID from authorizer context (if available)
        user_id = None
        user_type = 'anonymous'

        if 'requestContext' in event and 'authorizer' in event['requestContext']:
            # WebSocket connections with JWT authorization will have user_id in context
            user_id = event['requestContext']['authorizer'].get('user_id')
            if user_id:
                user_type = 'authenticated'

        # Fallback to query parameter for demo/testing mode (when no authorization)
        if not user_id:
            user_id = query_params.get('user_id')
            if user_id and not user_id.startswith('anonymous_'):
                user_type = 'authenticated'

        # If still no user_id, generate device fingerprint-based ID
        if not user_id:
            # Create a simple device fingerprint from headers
            headers = event.get('headers', {})
            user_agent = headers.get('User-Agent', 'unknown')
            accept_language = headers.get('Accept-Language', 'unknown')
            source_ip = headers.get('X-Forwarded-For', '').split(',')[0].strip() or 'unknown'

            # Create fingerprint hash
            fingerprint_data = f"{user_agent}|{accept_language}|{source_ip}"
            fingerprint_hash = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:12]

            # Generate anonymous user ID with fingerprint
            user_id = f"anonymous_{fingerprint_hash}"
            logger.info(f"Generated anonymous user_id with fingerprint: {user_id}", extra={
                'connection_id': connection_id,
                'query_params': query_params,
                'has_authorizer': 'authorizer' in event.get('requestContext', {}),
                'fingerprint_components': {
                    'user_agent': user_agent[:50],  # Truncate for logging
                    'accept_language': accept_language,
                    'source_ip': source_ip
                }
            })
        
        # If no session_id provided, create a new one
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"Generated new session_id: {session_id}", extra={
                'connection_id': connection_id,
                'user_id': user_id
            })
        
        # Determine session TTL based on user type
        session_ttl_hours = 24 if user_type == 'authenticated' else 2
        expires_at = int((datetime.utcnow() + timedelta(hours=session_ttl_hours)).timestamp())

        # Extract device info for analytics
        headers = event.get('headers', {})
        device_info = {
            'user_agent': headers.get('User-Agent', 'unknown'),
            'accept_language': headers.get('Accept-Language', 'unknown'),
            'source_ip': headers.get('X-Forwarded-For', '').split(',')[0].strip() or 'unknown'
        }

        # Store connection metadata
        connection_data = {
            'connection_id': connection_id,
            'user_id': user_id,
            'user_type': user_type,
            'session_id': session_id,
            'connected_at': datetime.utcnow().isoformat(),
            'expires_at': expires_at,
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'status': 'connected',
            'device_info': device_info,
            'allow_message_history': user_type == 'authenticated'
        }
        
        # Store connection in DynamoDB (overwrite if exists to handle reconnects)
        connections_table.put_item(Item=connection_data)
        
        # Update or create session record
        session_update_result = update_session_connection(
            session_id, user_id, user_type, connection_id, expires_at
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        logger.info(f"WebSocket connection established successfully", extra={
            'connection_id': connection_id,
            'user_id': user_id,
            'user_type': user_type,
            'session_id': session_id,
            'processing_time_ms': processing_time,
            'session_updated': session_update_result.get('updated', False)
        })

        # Prepare response with user type information
        response_body = {
            "message": "Connected successfully",
            "connection_id": connection_id,
            "session_id": session_id,
            "user_id": user_id,
            "user_type": user_type,
            "features": {
                "message_history": user_type == 'authenticated',
                "session_expires_in_hours": session_ttl_hours
            },
            "timestamp": datetime.utcnow().isoformat()
        }

        # Add upgrade suggestion for anonymous users
        if user_type == 'anonymous':
            response_body["upgrade_suggestion"] = {
                "message": "Sign in to save your chat history and get more features",
                "benefits": [
                    "Save chat history",
                    "Longer session duration",
                    "Personalized responses"
                ]
            }

        return create_response(200, response_body)
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(f"Error establishing WebSocket connection", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time_ms': processing_time,
            'traceback': str(e)
        }, exc_info=True)
        
        return create_response(500, {
            "error": "Internal server error",
            "message": "Failed to establish connection"
        })

def update_session_connection(
    session_id: str,
    user_id: str,
    user_type: str,
    connection_id: str,
    expires_at: int
) -> Dict[str, Any]:
    """
    Update session record with current connection ID.
    
    Args:
        session_id: Chat session ID
        user_id: User identifier
        connection_id: WebSocket connection ID
    
    Returns:
        Dictionary with update results
    """
    
    try:
        current_datetime = datetime.utcnow()
        current_time_iso = current_datetime.isoformat()
        current_timestamp = int(current_datetime.timestamp())

        # Since the sessions table has a composite key (session_id + timestamp),
        # we need to create a new entry for each connection
        session_data = {
            'session_id': session_id,
            'timestamp': current_timestamp,  # Range key
            'user_id': user_id,
            'user_type': user_type,
            'connection_id': connection_id,
            'created_at': current_time_iso,
            'updated_at': current_time_iso,
            'last_activity': current_time_iso,
            'status': 'active',
            'expires_at': expires_at,
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'message_count': 0,
            'allow_history': user_type == 'authenticated'
        }

        sessions_table.put_item(Item=session_data)

        logger.info(f"Created session entry", extra={
            'session_id': session_id,
            'connection_id': connection_id,
            'user_id': user_id,
            'timestamp': current_timestamp
        })

        return {'updated': True, 'session_data': session_data}
            
    except Exception as e:
        logger.error(f"Error updating session connection", extra={
            'session_id': session_id,
            'connection_id': connection_id,
            'user_id': user_id,
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        
        return {'updated': False, 'error': str(e)}

def create_response(status_code: int, body: Any = None) -> Dict[str, Any]:
    """
    Create a standardized API Gateway response.
    
    Args:
        status_code: HTTP status code
        body: Response body (will be JSON encoded)
    
    Returns:
        API Gateway response dictionary
    """
    
    response = {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'X-Environment': ENVIRONMENT,
            'X-Project': PROJECT_NAME
        }
    }
    
    if body is not None:
        response['body'] = json.dumps(body, default=str)
    
    return response
