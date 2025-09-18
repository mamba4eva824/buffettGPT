"""
Conversations Handler
Manages chat conversations including listing, updating titles, and archiving.
"""

import json
import boto3
import logging
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'buffett-dev-conversations')
MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE', 'buffett-dev-chat-messages')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# DynamoDB tables
conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)
messages_table = dynamodb.Table(MESSAGES_TABLE)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle conversation management requests.

    Args:
        event: API Gateway event
        context: Lambda context

    Returns:
        API Gateway response
    """
    # Use print to ensure output
    print(f"CONVERSATIONS HANDLER INVOKED")
    print(f"Event keys: {list(event.keys())}")

    try:
        # Log the entire event for debugging
        print(f"Full event structure: {json.dumps(event, default=str)[:2000]}")  # Limit to 2000 chars
        logger.info(f"Full event structure: {json.dumps(event, default=str)[:2000]}")

        # Extract HTTP method and path
        http_method = event['requestContext']['http']['method']
        full_path = event['requestContext']['http']['path']

        # Remove stage prefix from path (e.g., /dev/conversations -> /conversations)
        # API Gateway v2 includes the stage in the path
        path = full_path
        if '/' in full_path[1:]:  # Check if there's a second slash after the first
            path_parts = full_path.split('/', 2)  # Split into ['', 'dev', 'conversations']
            if len(path_parts) > 2:
                path = '/' + path_parts[2]  # Get everything after stage

        logger.info(f"Handling {http_method} request to {path} (full: {full_path})", extra={
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'request_id': context.aws_request_id
        })

        # Handle OPTIONS for CORS preflight
        if http_method == 'OPTIONS':
            return create_response(200, {'message': 'CORS preflight response'})

        # Route based on method and path
        if http_method == 'GET' and path == '/conversations':
            return list_conversations(event)
        elif http_method == 'GET' and '/conversations/' in path and '/messages' in path:
            return get_conversation_messages(event)
        elif http_method == 'GET' and '/conversations/' in path:
            return get_conversation(event)
        elif http_method == 'POST' and path == '/conversations':
            return create_conversation(event)
        elif http_method == 'PUT' and '/conversations/' in path:
            return update_conversation(event)
        elif http_method == 'PATCH' and '/conversations/' in path:
            return update_conversation(event)
        elif http_method == 'DELETE' and '/conversations/' in path:
            return archive_conversation(event)
        else:
            return create_response(404, {'error': 'Not found'})

    except Exception as e:
        logger.error(f"Error handling conversation request", extra={
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)

        return create_response(500, {
            'error': 'Internal server error',
            'message': str(e)
        })

def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract user ID from the event.
    Handles both authenticated and anonymous users.

    Args:
        event: API Gateway event

    Returns:
        User ID or None
    """

    # Debug logging to understand the event structure
    if 'requestContext' in event:
        logger.debug(f"RequestContext structure: {str(event.get('requestContext', {}))}")

    # Try to get from authorizer (authenticated users)
    if 'requestContext' in event and 'authorizer' in event['requestContext']:
        authorizer = event['requestContext']['authorizer']
        logger.debug(f"Authorizer data: {str(authorizer)}")

        # For Lambda authorizer with API Gateway HTTP v2 (payload format 1.0)
        # The context from auth_verify is passed under 'lambda' key
        if isinstance(authorizer, dict):
            # Try lambda.user_id (for Lambda authorizers with context)
            if 'lambda' in authorizer and isinstance(authorizer['lambda'], dict):
                user_id = authorizer['lambda'].get('user_id')
                if user_id:
                    logger.info(f"Found user_id in authorizer.lambda: {user_id}")
                    return user_id

            # Try direct user_id (fallback)
            user_id = authorizer.get('user_id')
            if user_id:
                logger.info(f"Found user_id directly in authorizer: {user_id}")
                return user_id

    # Try to decode JWT from Authorization header (temporary solution)
    headers = event.get('headers', {})
    auth_header = headers.get('authorization', headers.get('Authorization', ''))

    if auth_header.startswith('Bearer '):
        try:
            import base64

            token = auth_header[7:]  # Remove 'Bearer ' prefix
            # JWT has 3 parts separated by dots: header.payload.signature
            parts = token.split('.')
            if len(parts) == 3:
                # Decode the payload (middle part)
                # Add padding if necessary
                payload = parts[1]
                padding = 4 - len(payload) % 4
                if padding != 4:
                    payload += '=' * padding

                decoded = base64.urlsafe_b64decode(payload)
                claims = json.loads(decoded)

                # Get user_id from JWT claims
                user_id = claims.get('sub') or claims.get('user_id') or claims.get('id')
                if user_id:
                    logger.info(f"Extracted user_id from JWT: {user_id}")
                    return user_id
        except Exception as e:
            logger.warning(f"Failed to decode JWT: {e}")

    # Try to get from query parameters (anonymous users)
    query_params = event.get('queryStringParameters', {})
    if query_params and 'user_id' in query_params:
        return query_params['user_id']

    # Try to get from headers (for WebSocket or custom auth)
    if 'x-user-id' in headers:
        return headers['x-user-id']

    return None

def list_conversations(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all conversations for a user.

    Args:
        event: API Gateway event

    Returns:
        Response with list of conversations
    """

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    logger.info(f"Listing conversations for user {user_id}")

    try:
        # Query conversations using GSI
        response = conversations_table.query(
            IndexName='user-conversations-index',
            KeyConditionExpression='user_id = :user_id',
            ExpressionAttributeValues={':user_id': user_id},
            ScanIndexForward=False  # Most recent first
        )

        conversations = response.get('Items', [])

        # Filter out archived unless requested
        query_params = event.get('queryStringParameters', {}) or {}
        include_archived = query_params.get('include_archived', 'false').lower() == 'true'

        if not include_archived:
            conversations = [c for c in conversations if not c.get('is_archived', False)]

        # Add summary statistics for each conversation
        for conv in conversations:
            # Convert numeric timestamp to ISO format for response
            if 'updated_at' in conv and isinstance(conv['updated_at'], (int, float)):
                conv['updated_at_iso'] = datetime.fromtimestamp(conv['updated_at']).isoformat()

        logger.info(f"Found {len(conversations)} conversations for user {user_id}")

        return create_response(200, {
            'conversations': conversations,
            'count': len(conversations)
        })

    except Exception as e:
        logger.error(f"Error listing conversations", extra={
            'user_id': user_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to list conversations'})

def get_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a specific conversation by ID.

    Args:
        event: API Gateway event

    Returns:
        Response with conversation details
    """

    conversation_id = event['pathParameters'].get('conversation_id')
    if not conversation_id:
        return create_response(400, {'error': 'Conversation ID required'})

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    try:
        response = conversations_table.get_item(
            Key={'conversation_id': conversation_id}
        )

        conversation = response.get('Item')

        if not conversation:
            return create_response(404, {'error': 'Conversation not found'})

        # Verify ownership
        if conversation['user_id'] != user_id:
            return create_response(403, {'error': 'Access denied'})

        # Add ISO timestamp for numeric timestamps
        if 'updated_at' in conversation and isinstance(conversation['updated_at'], (int, float)):
            conversation['updated_at_iso'] = datetime.fromtimestamp(conversation['updated_at']).isoformat()

        return create_response(200, conversation)

    except Exception as e:
        logger.error(f"Error getting conversation", extra={
            'conversation_id': conversation_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to get conversation'})

def get_conversation_messages(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get messages for a specific conversation.

    Args:
        event: API Gateway event

    Returns:
        Response with conversation messages
    """

    conversation_id = event['pathParameters'].get('conversation_id')
    if not conversation_id:
        return create_response(400, {'error': 'Conversation ID required'})

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    try:
        # First verify the user owns this conversation
        conv_response = conversations_table.get_item(
            Key={'conversation_id': conversation_id}
        )

        conversation = conv_response.get('Item')
        if not conversation or conversation['user_id'] != user_id:
            return create_response(403, {'error': 'Access denied'})

        # Get messages for this conversation
        # Note: Currently using session_id as conversation_id
        response = messages_table.query(
            KeyConditionExpression='session_id = :session_id',
            ExpressionAttributeValues={':session_id': conversation_id},
            ScanIndexForward=True  # Oldest first (chronological order)
        )

        messages = response.get('Items', [])

        # Format timestamps
        for msg in messages:
            if 'timestamp' in msg and isinstance(msg['timestamp'], (int, float)):
                msg['timestamp_iso'] = datetime.fromtimestamp(msg['timestamp']).isoformat()

        return create_response(200, {
            'conversation_id': conversation_id,
            'messages': messages,
            'count': len(messages)
        })

    except Exception as e:
        logger.error(f"Error getting conversation messages", extra={
            'conversation_id': conversation_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to get messages'})

def create_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        event: API Gateway event

    Returns:
        Response with created conversation
    """

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    body = json.loads(event.get('body', '{}'))

    # Generate conversation ID
    conversation_id = str(uuid.uuid4())

    # Create conversation record
    conversation = {
        'conversation_id': conversation_id,
        'user_id': user_id,
        'title': body.get('title', 'New conversation'),
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': int(datetime.utcnow().timestamp()),
        'message_count': 0,
        'is_archived': False,
        'user_type': body.get('user_type', 'authenticated'),
        'metadata': body.get('metadata', {})
    }

    try:
        conversations_table.put_item(Item=conversation)

        logger.info(f"Created conversation {conversation_id} for user {user_id}")

        return create_response(201, conversation)

    except Exception as e:
        logger.error(f"Error creating conversation", extra={
            'user_id': user_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to create conversation'})

def update_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update conversation title or other metadata.

    Args:
        event: API Gateway event

    Returns:
        Response with update status
    """

    conversation_id = event['pathParameters'].get('conversation_id')
    if not conversation_id:
        return create_response(400, {'error': 'Conversation ID required'})

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    body = json.loads(event.get('body', '{}'))

    try:
        # Verify ownership
        response = conversations_table.get_item(
            Key={'conversation_id': conversation_id}
        )

        conversation = response.get('Item')

        if not conversation:
            return create_response(404, {'error': 'Conversation not found'})

        if conversation['user_id'] != user_id:
            return create_response(403, {'error': 'Access denied'})

        # Build update expression
        update_expr = []
        expr_attr_values = {}

        if 'title' in body:
            update_expr.append('title = :title')
            expr_attr_values[':title'] = body['title']

        if 'is_archived' in body:
            update_expr.append('is_archived = :archived')
            expr_attr_values[':archived'] = body['is_archived']

        if 'metadata' in body:
            update_expr.append('metadata = :metadata')
            expr_attr_values[':metadata'] = body['metadata']

        if update_expr:
            update_expr.append('updated_at = :updated')
            expr_attr_values[':updated'] = int(datetime.utcnow().timestamp())

            conversations_table.update_item(
                Key={'conversation_id': conversation_id},
                UpdateExpression='SET ' + ', '.join(update_expr),
                ExpressionAttributeValues=expr_attr_values
            )

            logger.info(f"Updated conversation {conversation_id}")

        return create_response(200, {
            'message': 'Conversation updated',
            'conversation_id': conversation_id
        })

    except Exception as e:
        logger.error(f"Error updating conversation", extra={
            'conversation_id': conversation_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to update conversation'})

def archive_conversation(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Archive (soft delete) a conversation.

    Args:
        event: API Gateway event

    Returns:
        Response with archive status
    """

    conversation_id = event['pathParameters'].get('conversation_id')
    if not conversation_id:
        return create_response(400, {'error': 'Conversation ID required'})

    user_id = get_user_id(event)
    if not user_id:
        return create_response(401, {'error': 'User ID not found'})

    try:
        # Archive with ownership check
        conversations_table.update_item(
            Key={'conversation_id': conversation_id},
            UpdateExpression='SET is_archived = :archived, updated_at = :updated',
            ExpressionAttributeValues={
                ':archived': True,
                ':updated': int(datetime.utcnow().timestamp()),
                ':user': user_id
            },
            ConditionExpression='user_id = :user'
        )

        logger.info(f"Archived conversation {conversation_id}")

        return create_response(200, {
            'message': 'Conversation archived',
            'conversation_id': conversation_id
        })

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return create_response(403, {'error': 'Access denied or conversation not found'})

    except Exception as e:
        logger.error(f"Error archiving conversation", extra={
            'conversation_id': conversation_id,
            'error': str(e)
        })

        return create_response(500, {'error': 'Failed to archive conversation'})

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
            'Access-Control-Allow-Origin': '*',  # Allow all origins for development
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
            'X-Environment': ENVIRONMENT,
            'X-Project': PROJECT_NAME
        }
    }

    if body is not None:
        response['body'] = json.dumps(body, default=str)

    return response