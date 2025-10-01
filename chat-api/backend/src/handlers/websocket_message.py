"""
WebSocket Message Handler
Handles incoming WebSocket messages, validates them, and queues for processing.
"""

import json
import boto3
import uuid
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from utils.conversation_updater import update_conversation_timestamp

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')
apigateway_client = boto3.client('apigatewaymanagementapi', 
                                 endpoint_url=f"https://{os.environ.get('WEBSOCKET_API_ENDPOINT', '')}")

# Environment variables
CONNECTIONS_TABLE = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE', os.environ.get('CONNECTIONS_TABLE', 'buffett-dev-websocket-connections'))
CHAT_SESSIONS_TABLE = os.environ['CHAT_SESSIONS_TABLE']
CHAT_MESSAGES_TABLE = os.environ['CHAT_MESSAGES_TABLE']
CHAT_PROCESSING_QUEUE_URL = os.environ['CHAT_PROCESSING_QUEUE_URL']
WEBSOCKET_API_ENDPOINT = os.environ.get('WEBSOCKET_API_ENDPOINT', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# DynamoDB tables
connections_table = dynamodb.Table(CONNECTIONS_TABLE)
sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket message requests.
    
    Args:
        event: API Gateway WebSocket event
        context: Lambda context
    
    Returns:
        Response with status code and optional body
    """
    
    start_time = time.time()
    connection_id = event['requestContext']['connectionId']
    route_key = event['requestContext']['routeKey']
    
    logger.info(f"WebSocket message received", extra={
        'connection_id': connection_id,
        'route_key': route_key,
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'event_type': 'websocket_message',
        'request_id': context.aws_request_id
    })
    
    try:
        # Parse message body
        message_data = parse_message_body(event.get('body', '{}'))
        if not message_data:
            return await_send_error_and_return(connection_id, "Invalid message format", 400)
        
        # Handle different message types
        action = message_data.get('action', route_key)

        if action == 'ping':
            return handle_ping(connection_id, message_data)
        elif action == 'message':
            return handle_chat_message(connection_id, message_data, context)
        elif action == 'switch_conversation':
            return handle_switch_conversation(connection_id, message_data)
        else:
            logger.warning(f"Unknown message action", extra={
                'connection_id': connection_id,
                'action': action,
                'available_actions': ['ping', 'message', 'switch_conversation']
            })
            return await_send_error_and_return(connection_id, f"Unknown action: {action}", 400)
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(f"Error processing WebSocket message", extra={
            'connection_id': connection_id,
            'route_key': route_key,
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time_ms': processing_time
        }, exc_info=True)
        
        return await_send_error_and_return(connection_id, "Internal server error", 500)

def parse_message_body(body: str) -> Optional[Dict[str, Any]]:
    """
    Parse and validate the WebSocket message body.
    
    Args:
        body: Raw message body string
    
    Returns:
        Parsed message dictionary or None if invalid
    """
    
    try:
        if not body or body.strip() == '':
            logger.warning("Empty message body received")
            return None
        
        message_data = json.loads(body)
        
        if not isinstance(message_data, dict):
            logger.warning(f"Message body is not a JSON object: {type(message_data)}")
            return None
        
        return message_data
        
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in message body", extra={
            'body': body[:100],  # First 100 chars for debugging
            'json_error': str(e)
        })
        return None

def handle_ping(connection_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle ping/heartbeat messages.
    
    Args:
        connection_id: WebSocket connection ID
        message_data: Parsed message data
    
    Returns:
        API Gateway response
    """
    
    try:
        # Send pong response
        pong_message = {
            "action": "pong",
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "message_id": message_data.get('message_id', str(uuid.uuid4()))
        }
        
        send_message_to_connection(connection_id, pong_message)
        
        logger.debug(f"Ping handled successfully", extra={
            'connection_id': connection_id,
            'message_id': pong_message['message_id']
        })
        
        return create_response(200)
        
    except Exception as e:
        logger.error(f"Error handling ping", extra={
            'connection_id': connection_id,
            'error': str(e)
        })
        return create_response(500)

def handle_switch_conversation(connection_id: str, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle switching to a different conversation.
    Updates the connection's session_id to point to the new conversation.

    Args:
        connection_id: WebSocket connection ID
        message_data: Parsed message data with conversation_id

    Returns:
        API Gateway response
    """

    try:
        # Validate conversation_id is provided
        conversation_id = message_data.get('conversation_id')
        if not conversation_id:
            return await_send_error_and_return(
                connection_id,
                "Missing required field: conversation_id",
                400
            )

        # Get current connection data
        connection_data = get_connection_data(connection_id)
        if not connection_data:
            return await_send_error_and_return(
                connection_id,
                "Connection not found",
                404
            )

        user_id = connection_data['user_id']
        old_session_id = connection_data.get('session_id')

        # Update connection record with new session_id
        connections_table.update_item(
            Key={'connection_id': connection_id},
            UpdateExpression='SET session_id = :session_id, last_activity = :timestamp',
            ExpressionAttributeValues={
                ':session_id': conversation_id,
                ':timestamp': datetime.utcnow().isoformat() + 'Z'
            }
        )

        # Send confirmation to client
        confirmation_message = {
            "action": "conversation_switched",
            "conversation_id": conversation_id,
            "previous_conversation_id": old_session_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }

        send_message_to_connection(connection_id, confirmation_message)

        logger.info(f"Conversation switched successfully", extra={
            'connection_id': connection_id,
            'user_id': user_id,
            'old_conversation_id': old_session_id,
            'new_conversation_id': conversation_id
        })

        return create_response(200)

    except Exception as e:
        logger.error(f"Error switching conversation", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)

        return await_send_error_and_return(
            connection_id,
            "Failed to switch conversation",
            500
        )

def handle_chat_message(connection_id: str, message_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle chat message by validating, storing, and queuing for processing.
    
    Args:
        connection_id: WebSocket connection ID
        message_data: Parsed message data
        context: Lambda context
    
    Returns:
        API Gateway response
    """
    
    try:
        # Validate message data
        validation_result = validate_chat_message(message_data)
        if not validation_result['valid']:
            return await_send_error_and_return(
                connection_id, 
                validation_result['error'], 
                400
            )
        
        # Get connection metadata
        connection_data = get_connection_data(connection_id)
        if not connection_data:
            return await_send_error_and_return(
                connection_id, 
                "Connection not found", 
                404
            )
        
        user_id = connection_data['user_id']
        session_id = connection_data['session_id']
        user_message = message_data['message']
        message_id = str(uuid.uuid4())
        current_time = datetime.utcnow()

        # Store user message in DynamoDB
        message_record = {
            'conversation_id': session_id,
            'timestamp': int(current_time.timestamp()),  # Store as Unix timestamp for DynamoDB LSI
            'timestamp_iso': current_time.isoformat() + 'Z',  # ISO format for readability and frontend
            'message_id': message_id,
            'user_id': user_id,
            'connection_id': connection_id,
            'message_type': 'user',
            'content': user_message,
            'status': 'received',
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME
        }
        
        messages_table.put_item(Item=message_record)

        # Update conversation timestamp for inbox sorting (creates if doesn't exist)
        update_conversation_timestamp(session_id, datetime.utcnow().isoformat() + 'Z', user_id)

        # Queue message for processing
        queue_message = {
            'message_id': message_id,
            'session_id': session_id,
            'user_id': user_id,
            'connection_id': connection_id,
            'user_message': user_message,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'request_id': context.aws_request_id
        }
        
        sqs.send_message(
            QueueUrl=CHAT_PROCESSING_QUEUE_URL,
            MessageBody=json.dumps(queue_message),
            MessageAttributes={
                'message_type': {
                    'StringValue': 'chat_request',
                    'DataType': 'String'
                },
                'session_id': {
                    'StringValue': session_id,
                    'DataType': 'String'
                },
                'user_id': {
                    'StringValue': user_id,
                    'DataType': 'String'
                }
            }
            # Note: MessageDeduplicationId and MessageGroupId are only for FIFO queues
        )
        
        # Send immediate acknowledgment to client
        ack_message = {
            "action": "message_received",
            "message_id": message_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z',
            "status": "queued_for_processing"
        }
        
        send_message_to_connection(connection_id, ack_message)
        
        # Update session activity
        update_session_activity(session_id)
        
        logger.info(f"Chat message processed successfully", extra={
            'connection_id': connection_id,
            'session_id': session_id,
            'user_id': user_id,
            'message_id': message_id,
            'message_length': len(user_message),
            'queued_for_processing': True
        })
        
        return create_response(200)
        
    except Exception as e:
        logger.error(f"Error handling chat message", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        
        return await_send_error_and_return(
            connection_id, 
            "Failed to process message", 
            500
        )

def validate_chat_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate chat message data.
    
    Args:
        message_data: Parsed message data
    
    Returns:
        Validation result with 'valid' boolean and optional 'error' message
    """
    
    if 'message' not in message_data:
        return {'valid': False, 'error': 'Missing required field: message'}
    
    message = message_data['message']
    
    if not isinstance(message, str):
        return {'valid': False, 'error': 'Message must be a string'}
    
    if len(message.strip()) == 0:
        return {'valid': False, 'error': 'Message cannot be empty'}
    
    if len(message) > 4000:  # Reasonable limit for chat messages
        return {'valid': False, 'error': 'Message too long (max 4000 characters)'}
    
    return {'valid': True}

def get_connection_data(connection_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve connection data from DynamoDB.
    
    Args:
        connection_id: WebSocket connection ID
    
    Returns:
        Connection data or None if not found
    """
    
    try:
        response = connections_table.get_item(
            Key={'connection_id': connection_id}
        )
        
        connection_data = response.get('Item')
        
        if not connection_data:
            logger.warning(f"Connection data not found", extra={
                'connection_id': connection_id
            })
        
        return connection_data
        
    except Exception as e:
        logger.error(f"Error retrieving connection data", extra={
            'connection_id': connection_id,
            'error': str(e)
        }, exc_info=True)
        
        return None

def update_session_activity(session_id: str) -> None:
    """
    Update session last activity timestamp.
    
    Args:
        session_id: Chat session ID
    """
    
    try:
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET #last_activity = :timestamp',
            ExpressionAttributeNames={'#last_activity': 'last_activity'},
            ExpressionAttributeValues={':timestamp': datetime.utcnow().isoformat()}
        )
        
    except Exception as e:
        logger.warning(f"Failed to update session activity", extra={
            'session_id': session_id,
            'error': str(e)
        })

def send_message_to_connection(connection_id: str, message: Dict[str, Any]) -> bool:
    """
    Send a message to a WebSocket connection.
    
    Args:
        connection_id: WebSocket connection ID
        message: Message to send
    
    Returns:
        True if successful, False otherwise
    """
    
    try:
        apigateway_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message, default=str)
        )
        
        logger.debug(f"Message sent to connection", extra={
            'connection_id': connection_id,
            'message_action': message.get('action'),
            'message_size': len(json.dumps(message))
        })
        
        return True
        
    except apigateway_client.exceptions.GoneException:
        logger.warning(f"Connection is gone", extra={
            'connection_id': connection_id
        })
        # Clean up stale connection
        cleanup_stale_connection(connection_id)
        return False
        
    except Exception as e:
        logger.error(f"Error sending message to connection", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__
        })
        return False

def cleanup_stale_connection(connection_id: str) -> None:
    """
    Clean up a stale connection from DynamoDB.
    
    Args:
        connection_id: WebSocket connection ID
    """
    
    try:
        connections_table.delete_item(
            Key={'connection_id': connection_id}
        )
        
        logger.info(f"Cleaned up stale connection", extra={
            'connection_id': connection_id
        })
        
    except Exception as e:
        logger.warning(f"Failed to cleanup stale connection", extra={
            'connection_id': connection_id,
            'error': str(e)
        })

def await_send_error_and_return(connection_id: str, error_message: str, status_code: int) -> Dict[str, Any]:
    """
    Send an error message to the connection and return an error response.
    
    Args:
        connection_id: WebSocket connection ID
        error_message: Error message to send
        status_code: HTTP status code
    
    Returns:
        API Gateway error response
    """
    
    error_response = {
        "action": "error",
        "error": error_message,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }
    
    send_message_to_connection(connection_id, error_response)
    
    return create_response(status_code, {"error": error_message})

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
