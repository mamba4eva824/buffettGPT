"""
WebSocket Disconnect Handler
Handles WebSocket disconnections by cleaning up connection metadata in DynamoDB.
"""

import json
import boto3
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CONNECTIONS_TABLE = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE', os.environ.get('CONNECTIONS_TABLE', 'buffett-dev-websocket-connections'))
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# DynamoDB tables
connections_table = dynamodb.Table(CONNECTIONS_TABLE)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle WebSocket disconnection requests.
    
    Args:
        event: API Gateway WebSocket event
        context: Lambda context
    
    Returns:
        Response with status code and optional body
    """
    
    start_time = time.time()
    connection_id = event['requestContext']['connectionId']
    
    logger.info(f"WebSocket disconnection request", extra={
        'connection_id': connection_id,
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'event_type': 'websocket_disconnect',
        'request_id': context.aws_request_id
    })
    
    try:
        # Get connection data before deletion for logging
        connection_data = get_connection_data(connection_id)
        
        # Delete connection from DynamoDB
        deletion_result = delete_connection(connection_id)
        
        processing_time = (time.time() - start_time) * 1000
        
        logger.info(f"WebSocket connection cleanup completed", extra={
            'connection_id': connection_id,
            'user_id': connection_data.get('user_id'),
            'session_id': connection_data.get('session_id'),
            'connected_duration_seconds': calculate_connection_duration(connection_data),
            'processing_time_ms': processing_time,
            'deletion_success': deletion_result['success']
        })
        
        return create_response(200, {
            "message": "Disconnected successfully",
            "connection_id": connection_id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(f"Error during WebSocket disconnection", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time_ms': processing_time
        }, exc_info=True)
        
        # Even if cleanup fails, return success to API Gateway
        # (connection is already closed)
        return create_response(200, {
            "message": "Connection closed",
            "connection_id": connection_id
        })

def get_connection_data(connection_id: str) -> Dict[str, Any]:
    """
    Retrieve connection data from DynamoDB.
    
    Args:
        connection_id: WebSocket connection ID
    
    Returns:
        Connection data dictionary or empty dict if not found
    """
    
    try:
        response = connections_table.get_item(
            Key={'connection_id': connection_id}
        )
        
        connection_data = response.get('Item', {})
        
        if connection_data:
            logger.debug(f"Retrieved connection data", extra={
                'connection_id': connection_id,
                'user_id': connection_data.get('user_id'),
                'session_id': connection_data.get('session_id'),
                'connected_at': connection_data.get('connected_at')
            })
        else:
            logger.warning(f"Connection data not found", extra={
                'connection_id': connection_id
            })
        
        return connection_data
        
    except Exception as e:
        logger.error(f"Error retrieving connection data", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        
        return {}

def delete_connection(connection_id: str) -> Dict[str, Any]:
    """
    Delete connection record from DynamoDB.
    
    Args:
        connection_id: WebSocket connection ID
    
    Returns:
        Dictionary with deletion results
    """
    
    try:
        response = connections_table.delete_item(
            Key={'connection_id': connection_id},
            ReturnValues='ALL_OLD'
        )
        
        deleted_item = response.get('Attributes')
        success = deleted_item is not None
        
        if success:
            logger.info(f"Connection record deleted successfully", extra={
                'connection_id': connection_id,
                'user_id': deleted_item.get('user_id'),
                'session_id': deleted_item.get('session_id')
            })
        else:
            logger.warning(f"Connection record not found for deletion", extra={
                'connection_id': connection_id
            })
        
        return {
            'success': success,
            'deleted_item': deleted_item
        }
        
    except Exception as e:
        logger.error(f"Error deleting connection record", extra={
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)
        
        return {
            'success': False,
            'error': str(e)
        }

def calculate_connection_duration(connection_data: Dict[str, Any]) -> float:
    """
    Calculate how long the connection was active.
    
    Args:
        connection_data: Connection metadata from DynamoDB
    
    Returns:
        Duration in seconds, or 0 if cannot calculate
    """
    
    try:
        connected_at_str = connection_data.get('connected_at')
        if not connected_at_str:
            return 0
        
        connected_at = datetime.fromisoformat(connected_at_str.replace('Z', '+00:00'))
        disconnected_at = datetime.utcnow()
        
        duration = (disconnected_at - connected_at).total_seconds()
        return max(0, duration)  # Ensure non-negative
        
    except Exception as e:
        logger.debug(f"Could not calculate connection duration", extra={
            'connected_at': connection_data.get('connected_at'),
            'error': str(e)
        })
        return 0

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
