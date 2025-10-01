"""
Chat Processor Lambda
Consumes SQS messages, processes them with Bedrock agent, and sends responses via WebSocket.
"""

import json
import boto3
import uuid
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from decimal import Decimal
from botocore.exceptions import ClientError
from utils.conversation_updater import update_conversation_timestamp

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
bedrock_client = boto3.client('bedrock-agent-runtime', region_name=os.environ.get('BEDROCK_REGION', 'us-east-1'))
bedrock_runtime = boto3.client('bedrock-runtime', region_name=os.environ.get('BEDROCK_REGION', 'us-east-1'))
apigateway_client = None  # Initialized when needed

# Environment variables
CONNECTIONS_TABLE = os.environ.get('WEBSOCKET_CONNECTIONS_TABLE', os.environ.get('CONNECTIONS_TABLE', 'buffett-dev-websocket-connections'))
CHAT_SESSIONS_TABLE = os.environ['CHAT_SESSIONS_TABLE']
CHAT_MESSAGES_TABLE = os.environ['CHAT_MESSAGES_TABLE']
BEDROCK_AGENT_ID = os.environ['BEDROCK_AGENT_ID']
BEDROCK_AGENT_ALIAS = os.environ['BEDROCK_AGENT_ALIAS']
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
WEBSOCKET_API_ENDPOINT = os.environ.get('WEBSOCKET_API_ENDPOINT', '')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

MODEL_ID = 'anthropic.claude-3-haiku-20240307-v1:0'  # Model ID for agent

# DynamoDB tables
connections_table = dynamodb.Table(CONNECTIONS_TABLE)
sessions_table = dynamodb.Table(CHAT_SESSIONS_TABLE)
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

def convert_floats_to_decimals(item):
    """Convert all float values to Decimal for DynamoDB compatibility"""
    if isinstance(item, dict):
        return {key: convert_floats_to_decimals(value) for key, value in item.items()}
    elif isinstance(item, list):
        return [convert_floats_to_decimals(value) for value in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    else:
        return item

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process SQS messages containing chat requests.
    
    Args:
        event: SQS event containing message records
        context: Lambda context
    
    Returns:
        Batch processing results for SQS
    """
    
    start_time = time.time()
    
    logger.info(f"Chat processor invoked", extra={
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'event_type': 'chat_processor',
        'request_id': context.aws_request_id,
        'message_count': len(event.get('Records', []))
    })
    
    batch_item_failures = []
    
    for record in event.get('Records', []):
        try:
            # Parse SQS message
            message_data = parse_sqs_record(record)
            if not message_data:
                continue
            
            # Process the chat message
            processing_result = process_chat_message(message_data, context)
            
            # If processing failed, add to batch failures for retry
            if not processing_result.get('success', False):
                batch_item_failures.append({
                    'itemIdentifier': record['messageId']
                })
                
                logger.error(f"Failed to process message", extra={
                    'sqs_message_id': record['messageId'],
                    'message_id': message_data.get('message_id'),
                    'session_id': message_data.get('session_id'),
                    'error': processing_result.get('error')
                })
            
        except Exception as e:
            logger.error(f"Error processing SQS record", extra={
                'sqs_message_id': record.get('messageId'),
                'error': str(e),
                'error_type': type(e).__name__
            }, exc_info=True)
            
            batch_item_failures.append({
                'itemIdentifier': record['messageId']
            })
    
    processing_time = (time.time() - start_time) * 1000
    
    logger.info(f"Chat processor completed", extra={
        'processing_time_ms': processing_time,
        'total_messages': len(event.get('Records', [])),
        'failed_messages': len(batch_item_failures),
        'success_rate': (len(event.get('Records', [])) - len(batch_item_failures)) / max(1, len(event.get('Records', []))) * 100
    })
    
    # Return batch results for SQS partial batch failure handling
    return {
        'batchItemFailures': batch_item_failures
    }

def parse_sqs_record(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Parse SQS record to extract message data.
    
    Args:
        record: SQS record from event
    
    Returns:
        Parsed message data or None if invalid
    """
    
    try:
        body = record.get('body', '{}')
        message_data = json.loads(body)
        
        # Validate required fields
        required_fields = ['message_id', 'session_id', 'user_id', 'connection_id', 'user_message']
        for field in required_fields:
            if field not in message_data:
                logger.warning(f"Missing required field in SQS message", extra={
                    'sqs_message_id': record.get('messageId'),
                    'missing_field': field,
                    'available_fields': list(message_data.keys())
                })
                return None
        
        return message_data
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in SQS message body", extra={
            'sqs_message_id': record.get('messageId'),
            'body': record.get('body', '')[:200],  # First 200 chars
            'json_error': str(e)
        })
        return None

def process_chat_message(message_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Process a single chat message with Bedrock and send response via WebSocket.
    
    Args:
        message_data: Parsed message data from SQS
        context: Lambda context
    
    Returns:
        Processing result dictionary
    """
    
    message_id = message_data['message_id']
    session_id = message_data['session_id']
    user_id = message_data['user_id']
    connection_id = message_data['connection_id']
    user_message = message_data['user_message']
    
    start_time = time.time()
    
    logger.info(f"Processing chat message", extra={
        'message_id': message_id,
        'session_id': session_id,
        'user_id': user_id,
        'connection_id': connection_id,
        'message_length': len(user_message)
    })
    
    try:
        # Check if connection is still active
        connection_active = check_connection_active(connection_id)
        if not connection_active:
            logger.warning(f"Connection no longer active", extra={
                'connection_id': connection_id,
                'message_id': message_id
            })
            # Still process the message but don't try to send response
        
        # Send "typing" indicator if connection is active
        if connection_active:
            send_typing_indicator(connection_id, session_id, True)
        
        # Call Bedrock agent for AI response
        bedrock_result = call_bedrock_agent(user_message, session_id)
        
        if not bedrock_result.get('success', False):
            raise Exception(f"Bedrock call failed: {bedrock_result.get('error')}")
        
        ai_response = bedrock_result['response']
        ai_message_id = str(uuid.uuid4())

        # Store AI response in DynamoDB with token tracking
        current_time = datetime.utcnow()
        ai_message_record = {
            'conversation_id': session_id,
            'timestamp': int(current_time.timestamp()),  # Store as number for DynamoDB
            'timestamp_iso': current_time.isoformat() + 'Z',  # ISO format for readability and frontend
            'message_id': ai_message_id,
            'user_id': user_id,
            'message_type': 'assistant',
            'content': ai_response,
            'status': 'completed',
            'parent_message_id': message_id,
            'processing_time_ms': bedrock_result.get('processing_time_ms'),
            'tokens_used': bedrock_result.get('tokens_used', 0),
            'model': MODEL_ID,
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME
        }

        # Add detailed token metadata if available
        if 'metadata' in bedrock_result:
            metadata = bedrock_result['metadata']
            if 'input_tokens' in metadata:
                ai_message_record['input_tokens'] = metadata['input_tokens']
            if 'output_tokens' in metadata:
                ai_message_record['output_tokens'] = metadata['output_tokens']
        
        messages_table.put_item(Item=convert_floats_to_decimals(ai_message_record))

        # Update conversation timestamp for inbox sorting (creates if doesn't exist)
        update_conversation_timestamp(session_id, int(datetime.utcnow().timestamp()), user_id)

        # Send response via WebSocket if connection is active
        if connection_active:
            # Stop typing indicator
            send_typing_indicator(connection_id, session_id, False)
            
            # Send AI response
            response_message = {
                "action": "message_response",
                "message_id": ai_message_id,
                "parent_message_id": message_id,
                "session_id": session_id,
                "content": ai_response,
                "timestamp": datetime.utcnow().isoformat() + 'Z',
                "processing_time_ms": bedrock_result.get('processing_time_ms')
            }
            
            send_success = send_message_to_connection(connection_id, response_message)
            
            if not send_success:
                logger.warning(f"Failed to send response to connection", extra={
                    'connection_id': connection_id,
                    'message_id': ai_message_id
                })
        
        # Update session statistics
        update_session_stats(session_id, user_message, ai_response)
        
        processing_time = (time.time() - start_time) * 1000
        
        logger.info(f"Chat message processed successfully", extra={
            'message_id': message_id,
            'ai_message_id': ai_message_id,
            'session_id': session_id,
            'user_id': user_id,
            'processing_time_ms': processing_time,
            'bedrock_time_ms': bedrock_result.get('processing_time_ms'),
            'response_length': len(ai_response),
            'connection_active': connection_active
        })
        
        return {
            'success': True,
            'message_id': ai_message_id,
            'processing_time_ms': processing_time
        }
        
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(f"Error processing chat message", extra={
            'message_id': message_id,
            'session_id': session_id,
            'user_id': user_id,
            'connection_id': connection_id,
            'error': str(e),
            'error_type': type(e).__name__,
            'processing_time_ms': processing_time
        }, exc_info=True)
        
        # Send error message to connection if active
        connection_active = check_connection_active(connection_id)
        if connection_active:
            send_typing_indicator(connection_id, session_id, False)
            
            error_message = {
                "action": "error",
                "message_id": message_id,
                "session_id": session_id,
                "error": "Failed to process your message. Please try again.",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            send_message_to_connection(connection_id, error_message)
        
        return {
            'success': False,
            'error': str(e),
            'processing_time_ms': processing_time
        }

def call_bedrock_agent(user_message: str, session_id: str) -> Dict[str, Any]:
    """
    Call Bedrock agent to get response to user message
    """

    start_time = time.time()
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        logger.debug(f"Calling Bedrock agent (original method)", extra={
            'agent_id': BEDROCK_AGENT_ID,
            'agent_alias': BEDROCK_AGENT_ALIAS,
            'session_id': session_id,
            'message_length': len(user_message)
        })

        response = bedrock_client.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS,
            sessionId=session_id,
            inputText=user_message
        )

        # Extract response from Bedrock event stream
        ai_response = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk_data = event['chunk']
                if 'bytes' in chunk_data:
                    chunk_text = chunk_data['bytes'].decode('utf-8')
                    ai_response += chunk_text
                # Check for attribution data which may contain token info
                if 'attribution' in chunk_data:
                    logger.debug(f"Attribution data: {chunk_data['attribution']}")

            # InvokeAgent doesn't directly provide token metrics
            # We'll estimate based on character count for now

        if not ai_response.strip():
            raise Exception("Empty response from Bedrock agent")

        # Estimate token usage (rough approximation: 1 token ≈ 4 characters)
        # This is a fallback when using invoke_agent which doesn't provide token metrics
        estimated_input_tokens = len(user_message) // 4
        estimated_output_tokens = len(ai_response) // 4

        # Add some Warren Buffett branding if this is the Buffett advisor
        if 'buffett' in PROJECT_NAME.lower():
            ai_response = format_buffett_response(ai_response)

        processing_time = (time.time() - start_time) * 1000

        logger.info(f"Original agent response completed", extra={
            'session_id': session_id,
            'processing_time_ms': processing_time,
            'response_length': len(ai_response),
            'estimated_input_tokens': estimated_input_tokens,
            'estimated_output_tokens': estimated_output_tokens
        })

        return {
            'success': True,
            'response': ai_response,
            'processing_time_ms': processing_time,
            'tokens_used': estimated_input_tokens + estimated_output_tokens,
            'metadata': {
                'method': 'original_agent',
                'input_tokens': estimated_input_tokens,
                'output_tokens': estimated_output_tokens,
                'token_calculation': 'estimated'
            }
        }

    except Exception as e:
        error_msg = str(e)
        processing_time = (time.time() - start_time) * 1000

        logger.error(f"Original Bedrock agent call failed", extra={
            'session_id': session_id,
            'error': error_msg,
            'processing_time_ms': processing_time
        }, exc_info=True)

        return {
            'success': False,
            'error': error_msg,
            'processing_time_ms': processing_time
        }


def format_buffett_response(response: str) -> str:
    """
    Format Warren Buffett response (signature removed).

    Args:
        response: Raw AI response

    Returns:
        Formatted response without signature
    """

    # Ensure response ends with proper punctuation
    if not response.strip().endswith(('.', '!', '?')):
        response = response.strip() + '.'

    # Return response without signature
    return response

def check_connection_active(connection_id: str) -> bool:
    """
    Check if a WebSocket connection is still active.
    
    Args:
        connection_id: WebSocket connection ID
    
    Returns:
        True if connection is active, False otherwise
    """
    
    try:
        response = connections_table.get_item(
            Key={'connection_id': connection_id}
        )
        
        connection_data = response.get('Item')
        
        if not connection_data:
            return False
        
        # Check if connection has expired
        expires_at = connection_data.get('expires_at', 0)
        current_timestamp = int(datetime.utcnow().timestamp())
        
        if current_timestamp > expires_at:
            logger.debug(f"Connection expired", extra={
                'connection_id': connection_id,
                'expires_at': expires_at,
                'current_time': current_timestamp
            })
            return False
        
        return True
        
    except Exception as e:
        logger.warning(f"Error checking connection status", extra={
            'connection_id': connection_id,
            'error': str(e)
        })
        return False

def send_typing_indicator(connection_id: str, session_id: str, is_typing: bool) -> bool:
    """
    Send typing indicator to WebSocket connection.
    
    Args:
        connection_id: WebSocket connection ID
        session_id: Chat session ID
        is_typing: True to start typing, False to stop
    
    Returns:
        True if successful, False otherwise
    """
    
    try:
        typing_message = {
            "action": "typing",
            "session_id": session_id,
            "is_typing": is_typing,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return send_message_to_connection(connection_id, typing_message)
        
    except Exception as e:
        logger.debug(f"Failed to send typing indicator", extra={
            'connection_id': connection_id,
            'is_typing': is_typing,
            'error': str(e)
        })
        return False

def send_message_to_connection(connection_id: str, message: Dict[str, Any]) -> bool:
    """
    Send a message to a WebSocket connection.
    
    Args:
        connection_id: WebSocket connection ID
        message: Message to send
    
    Returns:
        True if successful, False otherwise
    """
    
    global apigateway_client
    
    try:
        # Initialize API Gateway client if not done yet
        if apigateway_client is None:
            apigateway_client = boto3.client(
                'apigatewaymanagementapi',
                endpoint_url=f"https://{WEBSOCKET_API_ENDPOINT}"
            )
        
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

def update_session_stats(session_id: str, user_message: str, ai_response: str) -> None:
    """
    Update session statistics.
    
    Args:
        session_id: Chat session ID
        user_message: User's message
        ai_response: AI response
    """
    
    try:
        sessions_table.update_item(
            Key={'session_id': session_id},
            UpdateExpression=(
                'SET #last_activity = :timestamp, '
                '#message_count = #message_count + :increment '
                'ADD #total_user_chars :user_chars, #total_ai_chars :ai_chars'
            ),
            ExpressionAttributeNames={
                '#last_activity': 'last_activity',
                '#message_count': 'message_count',
                '#total_user_chars': 'total_user_chars',
                '#total_ai_chars': 'total_ai_chars'
            },
            ExpressionAttributeValues={
                ':timestamp': datetime.utcnow().isoformat(),
                ':increment': 2,  # User message + AI response
                ':user_chars': len(user_message),
                ':ai_chars': len(ai_response)
            }
        )
        
    except Exception as e:
        logger.warning(f"Failed to update session stats", extra={
            'session_id': session_id,
            'error': str(e)
        })
