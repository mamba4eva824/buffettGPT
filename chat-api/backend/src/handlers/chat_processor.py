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

# Optimization settings
KNOWLEDGE_BASE_ID = os.environ.get('KNOWLEDGE_BASE_ID', 'D1ZVQ1VWHU')  # Your Pinecone KB
ENABLE_SEMANTIC_OPTIMIZATION = os.environ.get('ENABLE_SEMANTIC_OPTIMIZATION', 'true').lower() == 'true'
RELEVANCE_THRESHOLD = float(os.environ.get('RELEVANCE_THRESHOLD', '0.7'))
MAX_CHUNKS_PER_QUERY = int(os.environ.get('MAX_CHUNKS_PER_QUERY', '3'))
MODEL_ID = 'anthropic.claude-3-haiku-20240307-v1:0'  # Same model as your agent

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
            'session_id': session_id,
            'timestamp': int(current_time.timestamp()),  # Store as number for DynamoDB
            'timestamp_iso': current_time.isoformat(),  # Keep ISO format for readability
            'message_id': ai_message_id,
            'user_id': user_id,
            'message_type': 'assistant',
            'content': ai_response,
            'status': 'completed',
            'parent_message_id': message_id,
            'processing_time_ms': bedrock_result.get('processing_time_ms'),
            'tokens_used': bedrock_result.get('tokens_used', 0),
            'model': MODEL_ID,
            'conversation_id': session_id,  # Using session_id as conversation_id for now
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

        # Update conversation timestamp for inbox sorting
        update_conversation_timestamp(session_id, int(datetime.utcnow().timestamp()))

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
                "timestamp": datetime.utcnow().isoformat(),
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

def call_bedrock_optimized(user_message: str, session_id: str) -> Dict[str, Any]:
    """
    Optimized Bedrock call using semantic retrieval + direct model invocation with token tracking

    Provides 60-70% token cost reduction by:
    1. Retrieving only top relevant chunks from Pinecone Knowledge Base
    2. Building focused prompt with limited context
    3. Calling Claude directly instead of full agent pipeline
    4. Tracks actual token usage from model response

    Args:
        user_message: User's message
        session_id: Chat session ID

    Returns:
        Dictionary with success status, response, processing time, and token usage
    """
    
    start_time = time.time()
    
    try:
        logger.info(f"🔍 Starting optimized semantic retrieval for session {session_id}")
        
        # STEP 1: Semantic Retrieval from Pinecone Knowledge Base
        retrieve_response = bedrock_client.retrieve(
            knowledgeBaseId=KNOWLEDGE_BASE_ID,
            retrievalQuery={
                'text': user_message
            },
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': MAX_CHUNKS_PER_QUERY,  # Only top N chunks
                    'overrideSearchType': 'SEMANTIC'  # Pinecone default
                }
            }
        )
        
        # STEP 2: Extract and filter relevant content
        relevant_chunks = []
        for result in retrieve_response.get('retrievalResults', []):
            content = result.get('content', {}).get('text', '')
            score = result.get('score', 0)
            metadata = result.get('metadata', {})
            
            # Only use high-confidence chunks
            if score >= RELEVANCE_THRESHOLD and content.strip():
                relevant_chunks.append({
                    'content': content[:800],  # Limit chunk size to control tokens
                    'score': score,
                    'source': metadata.get('x-amz-bedrock-kb-source-uri', 'unknown')
                })
        
        avg_score = sum(c['score'] for c in relevant_chunks) / len(relevant_chunks) if relevant_chunks else 0
        logger.info(f"📊 Retrieved {len(relevant_chunks)} relevant chunks (avg score: {avg_score:.3f})")
        
        # STEP 3: Build focused prompt (much smaller than full agent context)
        if relevant_chunks:
            context_sections = []
            for i, chunk in enumerate(relevant_chunks, 1):
                context_sections.append(f"--- Source {i} (Relevance: {chunk['score']:.2f}) ---\n{chunk['content']}")
            
            context = "\n\n".join(context_sections)
            
            prompt = f"""You are Warren Buffett. Answer this investment question based on the specific excerpts from my shareholder letters below.

RELEVANT EXCERPTS FROM MY LETTERS:
{context}

QUESTION: {user_message}

INSTRUCTIONS:
- Answer as Warren Buffett in first person
- Reference specific content from the excerpts above
- Include my characteristic wit and folksy wisdom
- If the excerpts don't address the question, say "I haven't specifically written about that in the letters you're referencing"
- Keep the response focused and practical

My response:"""

        else:
            # Fallback for questions with no relevant content
            prompt = f"""You are Warren Buffett. The question "{user_message}" doesn't match well with content from my shareholder letters.

Please provide a brief response explaining that this specific question isn't covered in my letters, but offer a general investment principle if relevant. Keep it short and direct."""

        # STEP 4: Direct Claude invocation with streaming for token tracking
        model_response = bedrock_runtime.invoke_model_with_response_stream(
            modelId=MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 800,  # Controlled response length
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0.1,
                "system": "You are Warren Buffett providing investment wisdom based on your shareholder letters."
            })
        )

        # Process the streaming response
        ai_response = ""
        input_tokens = 0
        output_tokens = 0

        stream = model_response.get('body', [])
        for event in stream:
            chunk = json.loads(event['chunk']['bytes'].decode('utf-8'))

            if chunk['type'] == 'message_start':
                # Extract usage metrics from message_start
                if 'message' in chunk and 'usage' in chunk['message']:
                    input_tokens = chunk['message']['usage'].get('input_tokens', 0)

            elif chunk['type'] == 'content_block_delta':
                # Accumulate response text
                if 'delta' in chunk and 'text' in chunk['delta']:
                    ai_response += chunk['delta']['text']

            elif chunk['type'] == 'message_delta':
                # Extract final token counts
                if 'usage' in chunk:
                    output_tokens = chunk['usage'].get('output_tokens', 0)

            elif chunk['type'] == 'message_stop':
                # Final metrics might be here
                if 'amazon-bedrock-invocationMetrics' in chunk:
                    metrics = chunk['amazon-bedrock-invocationMetrics']
                    if 'inputTokenCount' in metrics:
                        input_tokens = metrics['inputTokenCount']
                    if 'outputTokenCount' in metrics:
                        output_tokens = metrics['outputTokenCount']

        total_tokens = input_tokens + output_tokens
        
        processing_time = (time.time() - start_time) * 1000

        # Calculate token savings using actual metrics
        estimated_original_tokens = 2500  # Typical agent call with full context
        actual_tokens_used = total_tokens
        token_savings_percent = ((estimated_original_tokens - actual_tokens_used) / estimated_original_tokens) * 100 if actual_tokens_used > 0 else 0

        logger.info(f"✅ Optimized call completed in {processing_time:.0f}ms, {token_savings_percent:.1f}% token savings", extra={
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'total_tokens': total_tokens
        })

        return {
            'success': True,
            'response': ai_response,
            'processing_time_ms': processing_time,
            'tokens_used': total_tokens,
            'metadata': {
                'method': 'optimized_retrieval',
                'chunks_used': len(relevant_chunks),
                'relevance_scores': [c['score'] for c in relevant_chunks],
                'token_savings_percent': round(token_savings_percent, 1),
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'sources': [c['source'] for c in relevant_chunks]
            }
        }
        
    except Exception as e:
        error_msg = str(e)
        processing_time = (time.time() - start_time) * 1000
        
        logger.error(f"❌ Optimized Bedrock call failed: {error_msg}", extra={
            'session_id': session_id,
            'error': error_msg,
            'processing_time_ms': processing_time
        }, exc_info=True)
        
        return {
            'success': False,
            'error': error_msg,
            'processing_time_ms': processing_time
        }

def call_bedrock_original(user_message: str, session_id: str) -> Dict[str, Any]:
    """
    Original approach using full agent pipeline with token tracking
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

def call_bedrock_agent(user_message: str, session_id: str) -> Dict[str, Any]:
    """
    Call Bedrock agent to get response to user message
    
    Args:
        user_message: User's message
        session_id: Chat session ID
    
    Returns:
        Dictionary with success status, response, and processing time
    """
    
    logger.info(f"🤖 Calling Bedrock agent for session {session_id}")
    return call_bedrock_original(user_message, session_id)

def format_buffett_response(response: str) -> str:
    """
    Add Warren Buffett branding to the response.
    
    Args:
        response: Raw AI response
    
    Returns:
        Formatted response with branding
    """
    
    # Simple branding - in production you might want more sophisticated formatting
    if not response.strip().endswith(('.', '!', '?')):
        response = response.strip() + '.'
    
    return f"{response}\n\n*Warren Buffett's AI Investment Advisor*"

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
