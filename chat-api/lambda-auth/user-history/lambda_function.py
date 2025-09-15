"""
User History Lambda Function
Retrieves a user's complete chat conversation history
"""

import json
import os
import boto3
import logging
from datetime import datetime, timezone
from boto3.dynamodb.conditions import Key
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# Environment variables
CHAT_SESSIONS_TABLE = os.environ['CHAT_SESSIONS_TABLE']
CHAT_MESSAGES_TABLE = os.environ['CHAT_MESSAGES_TABLE']
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat')

# DynamoDB tables
sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

class DecimalEncoder(json.JSONEncoder):
    """Helper to convert DynamoDB Decimal to JSON"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def lambda_handler(event, context):
    """
    Retrieve user's chat history
    GET /user/history?limit=20&offset=0&session_id=specific_session_id
    """
    try:
        # Extract user_id from JWT context (set by authorizer)
        user_id = event['requestContext']['authorizer']['user_id']
        logger.info(f"Retrieving history for user: {user_id}")
        
        # Parse query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        limit = int(query_params.get('limit', 20))
        offset = int(query_params.get('offset', 0))
        specific_session_id = query_params.get('session_id')
        
        # Validate parameters
        if limit > 100:
            limit = 100  # Max limit to prevent excessive data retrieval
        if offset < 0:
            offset = 0
        
        # Handle CORS preflight
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                    'Access-Control-Allow-Methods': 'OPTIONS,GET'
                },
                'body': ''
            }
        
        # If specific session requested, return just that session
        if specific_session_id:
            return get_specific_session(user_id, specific_session_id)
        
        # Get user's chat sessions (recent first)
        logger.info(f"Querying sessions for user: {user_id}")
        sessions_response = sessions_table.query(
            IndexName='user-sessions-index',
            KeyConditionExpression=Key('user_id').eq(user_id),
            ScanIndexForward=False,  # Most recent first
            Limit=50  # Get up to 50 sessions to start
        )
        
        user_sessions = sessions_response.get('Items', [])
        logger.info(f"Found {len(user_sessions)} sessions for user")
        
        # Build conversation history
        conversation_history = []
        
        for session in user_sessions:
            session_id = session['session_id']
            
            # Get summary of messages for this session
            messages_response = messages_table.query(
                KeyConditionExpression=Key('session_id').eq(session_id),
                ScanIndexForward=True,  # Chronological order
                ProjectionExpression='message_id, message_type, content, #ts, #st',
                ExpressionAttributeNames={
                    '#ts': 'timestamp',
                    '#st': 'status'
                }
            )
            
            messages = messages_response.get('Items', [])
            
            if messages:
                # Generate conversation summary
                conversation = {
                    'session_id': session_id,
                    'created_at': session.get('created_at', ''),
                    'last_activity': session.get('last_activity', ''),
                    'message_count': len(messages),
                    'title': generate_conversation_title(messages),
                    'preview': generate_conversation_preview(messages),
                    'is_authenticated': session.get('is_authenticated', False),
                    'subscription_tier': session.get('subscription_tier', 'free'),
                    # Include last few messages for context
                    'recent_messages': format_messages(messages[-6:] if len(messages) > 6 else messages)
                }
                conversation_history.append(conversation)
        
        # Apply pagination
        total_conversations = len(conversation_history)
        paginated_conversations = conversation_history[offset:offset+limit]
        
        # Build response
        response_data = {
            'conversations': paginated_conversations,
            'pagination': {
                'total': total_conversations,
                'offset': offset,
                'limit': limit,
                'has_more': offset + limit < total_conversations
            },
            'user_id': user_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'OPTIONS,GET',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(response_data, cls=DecimalEncoder)
        }
        
    except KeyError as e:
        logger.error(f"Missing required field: {str(e)}")
        return error_response(400, f"Missing required field: {str(e)}")
        
    except Exception as e:
        logger.error(f"Error retrieving user history: {str(e)}", exc_info=True)
        return error_response(500, "Failed to retrieve conversation history")

def get_specific_session(user_id, session_id):
    """Get details for a specific conversation session"""
    try:
        # Verify session belongs to user
        session_response = sessions_table.get_item(
            Key={'session_id': session_id}
        )
        
        if 'Item' not in session_response:
            return error_response(404, "Session not found")
        
        session = session_response['Item']
        
        # Security check: ensure session belongs to requesting user
        if session.get('user_id') != user_id:
            logger.warning(f"User {user_id} attempted to access session {session_id} belonging to {session.get('user_id')}")
            return error_response(403, "Access denied")
        
        # Get all messages for this session
        messages_response = messages_table.query(
            KeyConditionExpression=Key('session_id').eq(session_id),
            ScanIndexForward=True  # Chronological order
        )
        
        messages = messages_response.get('Items', [])
        
        # Build detailed session response
        session_data = {
            'session': {
                'session_id': session_id,
                'created_at': session.get('created_at', ''),
                'last_activity': session.get('last_activity', ''),
                'message_count': len(messages),
                'title': generate_conversation_title(messages),
                'is_authenticated': session.get('is_authenticated', False),
                'subscription_tier': session.get('subscription_tier', 'free')
            },
            'messages': format_messages(messages),
            'user_id': user_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,Authorization',
                'Access-Control-Allow-Methods': 'OPTIONS,GET',
                'Content-Type': 'application/json'
            },
            'body': json.dumps(session_data, cls=DecimalEncoder)
        }
        
    except Exception as e:
        logger.error(f"Error retrieving specific session: {str(e)}", exc_info=True)
        return error_response(500, "Failed to retrieve session details")

def generate_conversation_title(messages):
    """Generate a title from the first user message"""
    for message in messages:
        if message.get('message_type') == 'user':
            content = message.get('content', '')
            # Clean up the content
            content = content.strip()
            # Take first 50 characters and add ellipsis if needed
            if len(content) > 50:
                # Try to break at word boundary
                truncated = content[:50]
                last_space = truncated.rfind(' ')
                if last_space > 30:  # If we have a reasonable break point
                    truncated = truncated[:last_space]
                return truncated + "..."
            return content
    
    return "New Conversation"

def generate_conversation_preview(messages):
    """Generate a preview from the last assistant message"""
    for message in reversed(messages):
        if message.get('message_type') == 'assistant' and message.get('status') == 'completed':
            content = message.get('content', '')
            content = content.strip()
            # Take first 100 characters for preview
            if len(content) > 100:
                truncated = content[:100]
                last_space = truncated.rfind(' ')
                if last_space > 70:
                    truncated = truncated[:last_space]
                return truncated + "..."
            return content
    
    return "No response yet"

def format_messages(messages):
    """Format messages for response, removing unnecessary fields"""
    formatted = []
    for msg in messages:
        formatted_msg = {
            'message_id': msg.get('message_id'),
            'timestamp': msg.get('timestamp'),
            'message_type': msg.get('message_type'),
            'content': msg.get('content', ''),
            'status': msg.get('status', 'completed')
        }
        
        # Add metadata for assistant messages if available
        if msg.get('message_type') == 'assistant':
            if 'model' in msg:
                formatted_msg['model'] = msg['model']
            if 'processing_time' in msg:
                formatted_msg['processing_time'] = msg['processing_time']
        
        formatted.append(formatted_msg)
    
    return formatted

def error_response(status_code, message):
    """Generate error response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type,Authorization',
            'Access-Control-Allow-Methods': 'OPTIONS,GET',
            'Content-Type': 'application/json'
        },
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })
    }
