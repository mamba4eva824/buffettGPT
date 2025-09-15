"""
HTTP API Handler for ${project_name} Chat Endpoint
Environment: ${environment}

This Lambda function handles HTTP requests to the /chat endpoint:
- POST /chat: Process user messages and return AI responses
- GET /health: Health check endpoint
- OPTIONS /chat: CORS preflight handling

Rate Limiting:
- Anonymous users: 5 requests per month
- Device fingerprinting for better identification
- Automatic rate limit headers in responses
"""

import json
import boto3
import uuid
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from decimal import Decimal

# Import rate limiting functionality
from rate_limiter import rate_limit_decorator, check_rate_limit_manual

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')
bedrock_client = boto3.client('bedrock-agent-runtime', region_name=os.environ.get('BEDROCK_REGION', 'us-east-1'))

# Environment variables
CHAT_SESSIONS_TABLE = os.environ['CHAT_SESSIONS_TABLE']
CHAT_MESSAGES_TABLE = os.environ['CHAT_MESSAGES_TABLE'] 
CHAT_PROCESSING_QUEUE_URL = os.environ['CHAT_PROCESSING_QUEUE_URL']
BEDROCK_AGENT_ID = os.environ['BEDROCK_AGENT_ID']
BEDROCK_AGENT_ALIAS = os.environ['BEDROCK_AGENT_ALIAS']
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# Rate limiting environment variables
RATE_LIMITS_TABLE = os.environ.get('RATE_LIMITS_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-rate-limits')
USAGE_TRACKING_TABLE = os.environ.get('USAGE_TRACKING_TABLE', f'{PROJECT_NAME}-{ENVIRONMENT}-usage-tracking')
ANONYMOUS_MONTHLY_LIMIT = os.environ.get('ANONYMOUS_MONTHLY_LIMIT', '5')
AUTHENTICATED_MONTHLY_LIMIT = os.environ.get('AUTHENTICATED_MONTHLY_LIMIT', '500')
ENABLE_DEVICE_FINGERPRINTING = os.environ.get('ENABLE_DEVICE_FINGERPRINTING', 'true')
ENABLE_RATE_LIMITING = os.environ.get('ENABLE_RATE_LIMITING', 'true')
RATE_LIMIT_GRACE_PERIOD_HOURS = os.environ.get('RATE_LIMIT_GRACE_PERIOD_HOURS', '1')

# DynamoDB tables
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

@rate_limit_decorator
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for HTTP API requests
    
    Rate limiting is applied automatically via the @rate_limit_decorator:
    - Anonymous users: 5 requests per month
    - Device fingerprinting for better identification
    - Returns 429 status when limit exceeded
    """
    try:
        # Log the incoming event for debugging
        logger.info(f"Received event: {json.dumps(event, default=str)}")
        
        # Extract route and method
        route_key = event.get('routeKey', '')
        method = event.get('requestContext', {}).get('http', {}).get('method', '')
        path = event.get('requestContext', {}).get('http', {}).get('path', '')
        
        logger.info(f"Processing {method} {path} (route: {route_key})")
        
        # Route handling
        if route_key == "GET /health":
            return handle_health_check(event, context)
        elif route_key == "OPTIONS /chat":
            return handle_cors_preflight(event, context)
        elif route_key == "POST /chat":
            return handle_chat_request(event, context)
        elif route_key.startswith("GET /api/v1/chat/history/"):
            return handle_chat_history(event, context)
        else:
            return create_error_response(404, "Route not found", f"Unknown route: {route_key}")
            
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {str(e)}", exc_info=True)
        return create_error_response(500, "Internal server error", "An unexpected error occurred")

def handle_health_check(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle GET /health requests"""
    try:
        health_data = {
            "status": "healthy",
            "service": PROJECT_NAME,
            "environment": ENVIRONMENT,
            "timestamp": datetime.utcnow().isoformat(),
            "version": "2.0",
            "checks": {
                "dynamodb": check_dynamodb_health(),
                "sqs": check_sqs_health(),
                "bedrock": check_bedrock_health()
            }
        }
        
        # Overall health status
        all_healthy = all(health_data["checks"].values())
        health_data["status"] = "healthy" if all_healthy else "degraded"
        
        return create_success_response(health_data)
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return create_error_response(503, "Service unhealthy", str(e))

def handle_cors_preflight(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle OPTIONS requests for CORS preflight"""
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-ID",
            "Access-Control-Max-Age": "86400"
        },
        "body": ""
    }

def handle_chat_request(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle POST /chat requests"""
    try:
        # Parse request body
        body = parse_request_body(event)
        if not body:
            return create_error_response(400, "Invalid request", "Request body is required")
        
        # Validate required fields
        user_message = body.get('message', '').strip()
        if not user_message:
            return create_error_response(400, "Invalid request", "Message field is required and cannot be empty")
        
        # Extract user_id from JWT token if available
        user_id = extract_user_id_from_token(event)
        if not user_id:
            # Fall back to body user_id or generate anonymous
            user_id = body.get('user_id', f'anonymous_{uuid.uuid4().hex[:8]}')
        
        # Get or create session
        session_id = body.get('session_id') or str(uuid.uuid4())
        
        # Validate message length
        if len(user_message) > 4000:  # Reasonable limit
            return create_error_response(400, "Message too long", "Message must be less than 4000 characters")
        
        # Process the chat message
        response_data = process_chat_message(session_id, user_id, user_message)
        
        return create_success_response(response_data)
        
    except ValueError as e:
        logger.warning(f"Validation error: {str(e)}")
        return create_error_response(400, "Validation error", str(e))
    except Exception as e:
        logger.error(f"Error processing chat request: {str(e)}", exc_info=True)
        return create_error_response(500, "Processing failed", "Failed to process your message. Please try again.")

def process_chat_message(session_id: str, user_id: str, user_message: str) -> Dict[str, Any]:
    """Process chat message and return response"""
    
    # Create or update session
    timestamp = datetime.utcnow().isoformat()
    message_id = str(uuid.uuid4())
    
    # Save user message to DynamoDB
    user_message_record = {
        'session_id': session_id,
        'timestamp': timestamp,
        'message_id': message_id,
        'message_type': 'user',  # Changed from 'type' to match WebSocket handler
        'content': user_message,
        'user_id': user_id,
        'created_at': timestamp,
        'status': 'received',
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME
    }
    
    try:
        messages_table.put_item(Item=convert_floats_to_decimals(user_message_record))
        logger.info(f"Successfully saved user message: {message_id} for session: {session_id}, user: {user_id}")
    except Exception as e:
        logger.error(f"Failed to save user message to DynamoDB: {str(e)}", exc_info=True)
        logger.error(f"Message record that failed: {json.dumps(user_message_record, default=str)}")
        raise
    
    # Update or create session
    expires_at = datetime.utcnow() + timedelta(hours=24)
    session_data = {
        'session_id': session_id,
        'user_id': user_id,
        'status': 'active',
        'last_activity': timestamp,
        'expires_at': int(expires_at.timestamp())
    }
    
    # Check if session exists
    try:
        existing_session = sessions_table.get_item(Key={'session_id': session_id}).get('Item')
        if existing_session:
            # Update existing session
            sessions_table.update_item(
                Key={'session_id': session_id},
                UpdateExpression='SET last_activity = :activity, #status = :status, expires_at = :expires',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={
                    ':activity': timestamp,
                    ':status': 'active',
                    ':expires': int(expires_at.timestamp())
                }
            )
            logger.info(f"Updated session: {session_id}")
        else:
            # Create new session
            session_data.update({
                'created_at': timestamp,
                'message_count': 0
            })
            sessions_table.put_item(Item=convert_floats_to_decimals(session_data))
            logger.info(f"Created new session: {session_id}")
    except Exception as e:
        logger.error(f"Error managing session: {str(e)}")
        # Continue processing even if session management fails
    
    # Call Bedrock agent directly for immediate response
    try:
        ai_response = call_bedrock_agent(user_message, session_id)
        
        # Save AI response to DynamoDB
        ai_message_id = str(uuid.uuid4())
        ai_timestamp = datetime.utcnow().isoformat()
        
        ai_message_record = {
            'session_id': session_id,
            'timestamp': ai_timestamp,
            'message_id': ai_message_id,
            'message_type': 'assistant',  # Changed from 'type' to match WebSocket handler
            'content': ai_response['message'],
            'created_at': ai_timestamp,
            'processing_time': ai_response.get('processing_time', 0),
            'bedrock_response_id': ai_response.get('response_id', ''),
            'user_id': user_id,  # Add user_id for consistency
            'status': 'completed',
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME
        }
        
        try:
            messages_table.put_item(Item=convert_floats_to_decimals(ai_message_record))
            logger.info(f"Successfully saved AI response: {ai_message_id} for session: {session_id}, user: {user_id}")
        except Exception as save_error:
            logger.error(f"Failed to save AI message to DynamoDB: {str(save_error)}", exc_info=True)
            logger.error(f"AI message record that failed: {json.dumps(ai_message_record, default=str)}")
            # Don't raise here, we already have the response to return
        
        # Return structured response
        return {
            'session_id': session_id,
            'user_message_id': message_id,
            'ai_message_id': ai_message_id,
            'response': ai_response['message'],
            'processing_time': ai_response.get('processing_time', 0),
            'timestamp': ai_timestamp,
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"Error calling Bedrock: {str(e)}")
        
        # Return error response but don't fail the entire request
        error_response = "I apologize, but I'm experiencing technical difficulties right now. Please try again in a moment."
        
        # Save error response
        ai_message_id = str(uuid.uuid4())
        ai_timestamp = datetime.utcnow().isoformat()
        
        error_message_record = {
            'session_id': session_id,
            'timestamp': ai_timestamp,
            'message_id': ai_message_id,
            'message_type': 'assistant',  # Changed from 'type' to match WebSocket handler
            'content': error_response,
            'created_at': ai_timestamp,
            'error': str(e),
            'status': 'error',
            'user_id': user_id,  # Add user_id for consistency
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME
        }
        
        try:
            messages_table.put_item(Item=convert_floats_to_decimals(error_message_record))
            logger.info(f"Saved error response message: {ai_message_id}")
        except Exception as save_error:
            logger.error(f"Failed to save error message to DynamoDB: {str(save_error)}")
        
        return {
            'session_id': session_id,
            'user_message_id': message_id,
            'ai_message_id': ai_message_id,
            'response': error_response,
            'timestamp': ai_timestamp,
            'status': 'error',
            'error': 'bedrock_unavailable'
        }

def call_bedrock_agent(user_message: str, session_id: str) -> Dict[str, Any]:
    """Call Bedrock agent and return response"""
    
    start_time = time.time()
    
    try:
        response = bedrock_client.invoke_agent(
            agentId=BEDROCK_AGENT_ID,
            agentAliasId=BEDROCK_AGENT_ALIAS,
            sessionId=session_id,
            inputText=user_message
        )
        
        processing_time = time.time() - start_time
        
        # Extract response text from Bedrock streaming response
        response_text = ""
        response_id = response.get('sessionId', '')
        
        # Handle streaming response from Bedrock Agent
        if 'completion' in response:
            event_stream = response['completion']
            try:
                for event in event_stream:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            # Decode the bytes to string
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
                    elif 'trace' in event:
                        # Handle trace events if needed
                        logger.debug(f"Trace event: {event}")
            except Exception as stream_error:
                logger.error(f"Error processing event stream: {stream_error}")
                # If streaming fails, check for direct response format
                if isinstance(response, dict) and 'output' in response:
                    response_text = response['output'].get('text', '')
                else:
                    response_text = "Unable to process response from AI assistant."
        
        # Format response with Warren Buffett branding
        formatted_response = f"🏛️ **Warren Buffett Investment Advisor**\n\n{response_text}\n\n---\n📚 *Source: Warren Buffett Shareholder Letters*\n⏱️ *Response generated in {processing_time:.2f} seconds*"
        
        return {
            'message': formatted_response,
            'processing_time': Decimal(str(round(processing_time, 2))),  # Convert to Decimal for DynamoDB
            'response_id': response_id
        }
        
    except Exception as e:
        logger.error(f"Bedrock agent call failed: {str(e)}")
        raise e

def parse_request_body(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse and validate request body"""
    try:
        body = event.get('body', '')
        if not body:
            return None
        
        # Handle base64 encoded body
        is_base64_encoded = event.get('isBase64Encoded', False)
        if is_base64_encoded:
            import base64
            body = base64.b64decode(body).decode('utf-8')
        
        return json.loads(body)
        
    except json.JSONDecodeError as e:
        logger.warning(f"Invalid JSON in request body: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Error parsing request body: {str(e)}")
        return None

def check_dynamodb_health() -> bool:
    """Check DynamoDB table health"""
    try:
        # Use DynamoDB client to describe table
        dynamodb_client = boto3.client('dynamodb', region_name=BEDROCK_REGION)
        dynamodb_client.describe_table(TableName=CHAT_SESSIONS_TABLE)
        return True
    except Exception as e:
        logger.warning(f"DynamoDB health check failed: {str(e)}")
        return False

def check_sqs_health() -> bool:
    """Check SQS queue health"""
    try:
        sqs.get_queue_attributes(
            QueueUrl=CHAT_PROCESSING_QUEUE_URL,
            AttributeNames=['QueueArn']
        )
        return True
    except Exception as e:
        logger.warning(f"SQS health check failed: {str(e)}")
        return False

def check_bedrock_health() -> bool:
    """Check Bedrock agent health"""
    try:
        # Simple environment variable check - skip actual Bedrock call for now
        if BEDROCK_AGENT_ID and BEDROCK_AGENT_ALIAS and BEDROCK_REGION:
            return True
        return False
    except Exception as e:
        logger.warning(f"Bedrock health check failed: {str(e)}")
        return False

def create_success_response(data: Any, status_code: int = 200) -> Dict[str, Any]:
    """Create successful HTTP response"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-ID",
            "X-Request-ID": str(uuid.uuid4())
        },
        "body": json.dumps(data, default=str)
    }

def extract_user_id_from_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract user_id from JWT token in Authorization header"""
    try:
        # Get Authorization header
        headers = event.get('headers', {})
        auth_header = headers.get('Authorization') or headers.get('authorization', '')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        
        # Extract token
        token = auth_header[7:]  # Remove 'Bearer ' prefix
        
        # Decode JWT token (without verification for now - you should verify in production)
        # For now, just decode to get the user_id
        import base64
        
        # Split the JWT token
        parts = token.split('.')
        if len(parts) != 3:
            return None
        
        # Decode the payload (second part)
        payload = parts[1]
        # Add padding if needed
        payload += '=' * (4 - len(payload) % 4)
        
        # Decode base64
        decoded = base64.urlsafe_b64decode(payload)
        payload_data = json.loads(decoded)
        
        # Extract user_id from payload
        user_id = payload_data.get('user_id')
        
        logger.info(f"Extracted user_id from JWT: {user_id}")
        return user_id
        
    except Exception as e:
        logger.warning(f"Failed to extract user_id from token: {str(e)}")
        return None

def create_error_response(status_code: int, error: str, message: str) -> Dict[str, Any]:
    """Create error HTTP response"""
    error_data = {
        "error": error,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "status_code": status_code
    }
    
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS", 
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-ID",
            "X-Request-ID": str(uuid.uuid4())
        },
        "body": json.dumps(error_data)
    }

def handle_chat_history(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle GET /api/v1/chat/history/{session_id} requests
    Returns chat history for a given session
    """
    try:
        # Extract session_id from path parameters
        path_parameters = event.get('pathParameters', {})
        session_id = path_parameters.get('session_id')
        
        if not session_id:
            return create_error_response(400, "Missing session_id", "session_id is required in path")
        
        # Extract query parameters
        query_params = event.get('queryStringParameters') or {}
        limit = int(query_params.get('limit', 50))
        
        # Validate limit
        if limit > 200:
            limit = 200
        elif limit < 1:
            limit = 1
        
        logger.info(f"Fetching chat history for session {session_id}, limit: {limit}")
        
        # Query messages for this session
        messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)
        
        response = messages_table.query(
            KeyConditionExpression='session_id = :session_id',
            ExpressionAttributeValues={
                ':session_id': session_id
            },
            ScanIndexForward=True,  # Oldest first
            Limit=limit
        )
        
        messages = []
        for item in response.get('Items', []):
            messages.append({
                'message_id': item.get('message_id'),
                'session_id': item.get('session_id'),
                'user_id': item.get('user_id'),
                'type': item.get('message_type', item.get('type')),  # Support both field names for backward compatibility
                'content': item.get('content'),
                'timestamp': item.get('timestamp'),
                'parent_message_id': item.get('parent_message_id'),
                'processing_time_ms': float(item.get('processing_time_ms', 0)) if item.get('processing_time_ms') else None
            })
        
        logger.info(f"Retrieved {len(messages)} messages for session {session_id}")
        
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-ID",
                "X-Request-ID": str(uuid.uuid4())
            },
            "body": json.dumps({
                "status": "success",
                "session_id": session_id,
                "message_count": len(messages),
                "messages": messages
            })
        }
        
    except Exception as e:
        logger.error(f"Error fetching chat history: {str(e)}", exc_info=True)
        return create_error_response(500, "Failed to fetch chat history", str(e))

