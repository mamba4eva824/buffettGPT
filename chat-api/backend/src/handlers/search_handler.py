"""
Search Lambda Handler with DynamoDB Persistence
Provides AI-powered search capabilities with full conversation tracking
"""

import json
import os
import logging
import uuid
import boto3
import time
from datetime import datetime
from typing import Dict, Any, Optional
from decimal import Decimal
from functools import lru_cache
from perplexity import Perplexity
from utils.conversation_updater import update_conversation_timestamp

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
secrets_client = boto3.client('secretsmanager')

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
SEARCH_API_KEY_ARN = os.environ.get('SEARCH_API_KEY_ARN')
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'buffett-dev-conversations')
MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE', 'buffett-dev-chat-messages')

# DynamoDB tables
messages_table = dynamodb.Table(MESSAGES_TABLE)

@lru_cache(maxsize=1)
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

def get_search_api_key() -> str:
    """Get Perplexity API key from Secrets Manager"""
    if SEARCH_API_KEY_ARN:
        return get_secret(SEARCH_API_KEY_ARN)
    else:
        # Fallback to environment variable for backward compatibility
        return os.environ.get('SEARCH_API_KEY', '')

def get_user_id(event: Dict[str, Any]) -> Optional[str]:
    """
    Extract user ID from the event.
    Handles both authenticated and anonymous users.
    """
    # Try to get from authorizer (authenticated users)
    if 'requestContext' in event and 'authorizer' in event['requestContext']:
        authorizer = event['requestContext']['authorizer']

        if isinstance(authorizer, dict):
            # Check lambda.user_id (API Gateway HTTP v2 format)
            if 'lambda' in authorizer and isinstance(authorizer['lambda'], dict):
                user_id = authorizer['lambda'].get('user_id')
                if user_id:
                    return str(user_id)

            # Check for user_id directly
            user_id = authorizer.get('user_id')
            if user_id:
                return str(user_id)

            # Check principalId
            principal_id = authorizer.get('principalId')
            if principal_id and principal_id != 'anonymous':
                return str(principal_id)

    # SECURITY: Only trust user_id from the verified API Gateway authorizer context.
    # Never extract user_id from unsigned JWT payloads, query params, or custom headers
    # as these are trivially spoofable. See docs/api/SECURITY_REVIEW.md CRIT-1.
    return 'anonymous'

def save_message(conversation_id: str, user_id: str, message_type: str,
                content: str, model: str, **kwargs) -> str:
    """
    Save a message to DynamoDB.

    Args:
        conversation_id: The conversation ID
        user_id: The user ID
        message_type: 'user' or 'assistant'
        content: Message content
        model: Model used (e.g., 'sonar')
        **kwargs: Additional fields (message_id, parent_message_id, processing_time_ms, etc.)

    Returns:
        The message ID
    """
    current_time = datetime.utcnow()
    message_id = kwargs.get('message_id', str(uuid.uuid4()))

    message = {
        'conversation_id': conversation_id,
        'timestamp': int(current_time.timestamp()),
        'timestamp_iso': current_time.isoformat() + 'Z',
        'message_id': message_id,
        'user_id': user_id,
        'message_type': message_type,
        'content': content,
        'model': model,
        'source': 'search',
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME
    }

    # Add optional fields
    if 'parent_message_id' in kwargs:
        message['parent_message_id'] = kwargs['parent_message_id']
    if 'processing_time_ms' in kwargs:
        message['processing_time_ms'] = Decimal(str(kwargs['processing_time_ms']))
    if 'status' in kwargs:
        message['status'] = kwargs['status']

    messages_table.put_item(Item=message)
    logger.info(f"Saved {message_type} message to DynamoDB", extra={
        'message_id': message_id,
        'conversation_id': conversation_id,
        'message_type': message_type
    })

    return message_id

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for AI search with DynamoDB persistence

    Args:
        event: Lambda event containing the search query
        context: Lambda context

    Returns:
        Search response with AI-generated answer and conversation tracking
    """
    # Handle OPTIONS request for CORS preflight
    request_context = event.get('requestContext', {})
    http_method = request_context.get('http', {}).get('method') or event.get('httpMethod', '')

    if http_method == 'OPTIONS':
        logger.info("Handling OPTIONS preflight request")
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps({'message': 'CORS preflight successful'})
        }

    start_time = time.time()

    try:
        logger.info(f"Search invoked", extra={
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'request_id': context.aws_request_id
        })

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        query = body.get('query', '')
        model = body.get('model', 'sonar')
        conversation_id = body.get('conversation_id', str(uuid.uuid4()))

        # Extract user ID
        user_id = get_user_id(event)

        logger.info(f"Processing search for user {user_id}", extra={
            'user_id': user_id,
            'conversation_id': conversation_id
        })

        # Validate query
        if not query:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Query parameter is required'
                })
            }

        # Get and validate API key
        search_api_key = get_search_api_key()
        if not search_api_key:
            logger.error("SEARCH_API_KEY not configured")
            return {
                'statusCode': 500,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({
                    'error': 'Search API key not configured'
                })
            }

        logger.info(f"Processing search query: {query[:100]}...")

        # Generate message IDs
        user_message_id = str(uuid.uuid4())

        # Save user message to DynamoDB BEFORE calling Perplexity
        save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_type='user',
            content=query,
            model=model,
            message_id=user_message_id
        )

        # Initialize search client and make API call
        client = Perplexity(api_key=search_api_key)

        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": query}
            ],
            stream=True
        )

        # Collect streaming chunks into full response
        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                full_response += chunk.choices[0].delta.content

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        # Generate AI message ID
        ai_message_id = str(uuid.uuid4())

        # Save AI response to DynamoDB AFTER receiving complete response
        save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_type='assistant',
            content=full_response,
            model=model,
            message_id=ai_message_id,
            parent_message_id=user_message_id,
            processing_time_ms=processing_time_ms,
            status='completed'
        )

        # Update conversation timestamp (creates conversation if doesn't exist)
        update_conversation_timestamp(
            conversation_id=conversation_id,
            timestamp=int(datetime.utcnow().timestamp()),
            user_id=user_id
        )

        logger.info(f"Search completed successfully", extra={
            'conversation_id': conversation_id,
            'user_message_id': user_message_id,
            'ai_message_id': ai_message_id,
            'processing_time_ms': processing_time_ms,
            'response_length': len(full_response)
        })

        # Return complete response with conversation tracking
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization'
            },
            'body': json.dumps({
                'query': query,
                'response': full_response,
                'conversation_id': conversation_id,
                'user_message_id': user_message_id,
                'ai_message_id': ai_message_id,
                'model': model,
                'processing_time_ms': int(processing_time_ms)
            })
        }

    except Exception as e:
        logger.error(f"Error in search: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': f'Internal server error: {str(e)}'
            })
        }


def lambda_streaming_handler(event: Dict[str, Any], context: Any):
    """
    Lambda handler for true streaming responses via Lambda Function URLs
    This requires the Function URL to be configured with InvokeMode: RESPONSE_STREAM

    Note: This is a placeholder for future implementation when streaming is needed.
    Lambda response streaming requires special response format with StreamingBody.
    """
    # For now, we use the standard handler above
    # To implement true streaming, we would need to use:
    # - awslambdaric.stream_response decorator
    # - Yield chunks as they arrive from Perplexity
    # - Configure Lambda Function URL with RESPONSE_STREAM mode
    pass
