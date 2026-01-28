"""
Analysis Follow-Up Handler

Handles follow-up questions after ensemble analysis.
Uses Bedrock ConverseStream API for direct model access with token tracking.

Conversation history is retrieved from DynamoDB to maintain context
across multiple follow-up questions.
"""

import json
import boto3
import os
import logging
import jwt
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from boto3.dynamodb.conditions import Key

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Secrets Manager client for JWT
secrets_client = boto3.client('secretsmanager')

# JWT Configuration
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')


@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT secret from AWS Secrets Manager with caching."""
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            return response['SecretString']
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret: {e}")
            raise
    # Fallback to environment variable
    jwt_secret = os.environ.get('JWT_SECRET')
    if jwt_secret:
        return jwt_secret
    raise ValueError("JWT_SECRET not configured")


def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract JWT token from Authorization header."""
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def verify_jwt_token(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token from request.

    Returns:
        User claims dict if valid, None if invalid/missing
    """
    token = extract_token(event)
    if not token:
        return None

    try:
        jwt_secret = get_jwt_secret()
        payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={'verify_exp': True})
        logger.info(f"JWT verified for user: {payload.get('user_id', 'unknown')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None


# Initialize Bedrock Runtime client for ConverseStream API
bedrock_runtime = boto3.client(
    'bedrock-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)

# Initialize DynamoDB for message persistence
dynamodb = boto3.resource('dynamodb')
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# Initialize messages table (lazy initialization to handle missing env var gracefully)
messages_table = None
if CHAT_MESSAGES_TABLE:
    messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

# Model configuration
MODEL_ID = os.environ.get('BEDROCK_MODEL_ID', 'anthropic.claude-3-haiku-20240307-v1:0')
MAX_TOKENS = int(os.environ.get('CONVERSE_MAX_TOKENS', '2048'))
TEMPERATURE = float(os.environ.get('CONVERSE_TEMPERATURE', '0.7'))

# System prompts for each analyst type (replaces Bedrock Agent instructions)
SYSTEM_PROMPTS = {
    'debt': """You are an expert debt analyst specializing in corporate financial analysis.
You have previously analyzed a company's debt structure, leverage ratios, and credit profile.
When answering follow-up questions:
- Reference specific metrics like debt-to-equity, interest coverage, and debt maturity schedules
- Explain the implications of debt levels on the company's financial health
- Compare to industry benchmarks when relevant
- Be concise but thorough in your analysis
- Use markdown formatting for clarity""",

    'cashflow': """You are an expert cash flow analyst specializing in corporate financial analysis.
You have previously analyzed a company's cash flow statement, free cash flow generation, and working capital.
When answering follow-up questions:
- Reference specific metrics like operating cash flow, free cash flow, and cash conversion cycle
- Explain the sustainability and quality of cash flows
- Discuss capital allocation decisions and their implications
- Be concise but thorough in your analysis
- Use markdown formatting for clarity""",

    'growth': """You are an expert growth analyst specializing in corporate financial analysis.
You have previously analyzed a company's revenue growth, market position, and expansion potential.
When answering follow-up questions:
- Reference specific metrics like revenue CAGR, market share, and growth drivers
- Explain the sustainability of growth and competitive advantages
- Discuss risks to the growth thesis
- Be concise but thorough in your analysis
- Use markdown formatting for clarity"""
}

# Maximum conversation history to include (to manage token usage)
MAX_HISTORY_MESSAGES = int(os.environ.get('MAX_HISTORY_MESSAGES', '10'))


def convert_floats_to_decimals(item):
    """Convert all float values to Decimal for DynamoDB compatibility."""
    if isinstance(item, dict):
        return {key: convert_floats_to_decimals(value) for key, value in item.items()}
    elif isinstance(item, list):
        return [convert_floats_to_decimals(value) for value in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    else:
        return item


def get_conversation_history(session_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve conversation history from DynamoDB for context.

    Args:
        session_id: The session/conversation ID

    Returns:
        List of messages in ConverseStream format: [{'role': 'user'|'assistant', 'content': [{'text': '...'}]}]
    """
    if not messages_table:
        logger.warning("Messages table not configured, no conversation history available")
        return []

    try:
        # Query messages for this session, sorted by timestamp
        response = messages_table.query(
            KeyConditionExpression=Key('conversation_id').eq(session_id),
            ScanIndexForward=True,  # Chronological order (oldest first)
            Limit=MAX_HISTORY_MESSAGES
        )

        messages = []
        for item in response.get('Items', []):
            message_type = item.get('message_type')
            content = item.get('content', '')

            # Only include user and assistant messages
            if message_type in ('user', 'assistant'):
                messages.append({
                    'role': message_type,
                    'content': [{'text': content}]
                })

        logger.info(f"Retrieved {len(messages)} messages from history for session {session_id}")
        return messages

    except Exception as e:
        logger.error(f"Failed to retrieve conversation history: {e}", exc_info=True)
        return []


def save_followup_message(
    session_id: str,
    message_type: str,
    content: str,
    user_id: str,
    agent_type: str,
    ticker: str = '',
    token_usage: Optional[Dict[str, int]] = None
) -> Optional[str]:
    """
    Save a follow-up message to DynamoDB.

    Args:
        session_id: The session/conversation ID
        message_type: 'user' or 'assistant'
        content: The message content
        user_id: The user's ID
        agent_type: The agent type (debt, cashflow, growth)
        ticker: The stock ticker symbol
        token_usage: Optional token usage metrics from ConverseStream

    Returns:
        The message_id if saved successfully, None otherwise
    """
    if not messages_table:
        logger.warning("Messages table not configured, skipping message persistence")
        return None

    try:
        timestamp_unix = int(datetime.utcnow().timestamp())
        timestamp_iso = datetime.utcnow().isoformat() + 'Z'
        message_id = str(uuid.uuid4())

        metadata = {
            'source': 'investment_research_followup',
            'agent_type': agent_type,
            'ticker': ticker
        }

        # Add token usage to metadata if available
        if token_usage:
            metadata['token_usage'] = token_usage

        message_record = {
            'conversation_id': session_id,
            'timestamp': timestamp_unix,
            'message_id': message_id,
            'message_type': message_type,
            'content': content,
            'user_id': user_id,
            'created_at': timestamp_iso,
            'status': 'completed' if message_type == 'assistant' else 'received',
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'metadata': metadata
        }

        messages_table.put_item(Item=convert_floats_to_decimals(message_record))
        logger.info(f"Saved {message_type} message {message_id} for session {session_id}")
        return message_id

    except Exception as e:
        logger.error(f"Failed to save {message_type} message to DynamoDB: {e}", exc_info=True)
        return None


def format_sse_event(data: str, event_type: str = "message") -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {data}\n\n"


def call_converse_stream(
    messages: List[Dict[str, Any]],
    system_prompt: str,
    ticker: str = ''
) -> tuple:
    """
    Call Bedrock ConverseStream API.

    Args:
        messages: Conversation history in ConverseStream format
        system_prompt: System prompt for the analyst type
        ticker: Stock ticker for additional context

    Yields:
        Tuples of (event_type, data) where event_type is 'chunk', 'metadata', or 'error'
    """
    # Add ticker context to system prompt if available
    full_system_prompt = system_prompt
    if ticker:
        full_system_prompt += f"\n\nYou are analyzing {ticker}."

    try:
        response = bedrock_runtime.converse_stream(
            modelId=MODEL_ID,
            messages=messages,
            system=[{'text': full_system_prompt}],
            inferenceConfig={
                'maxTokens': MAX_TOKENS,
                'temperature': TEMPERATURE
            }
        )

        full_response = ""
        token_usage = None

        for event in response.get('stream', []):
            # Handle text chunks
            if 'contentBlockDelta' in event:
                delta = event['contentBlockDelta'].get('delta', {})
                if 'text' in delta:
                    chunk_text = delta['text']
                    full_response += chunk_text
                    yield ('chunk', chunk_text)

            # Handle metadata with token usage
            if 'metadata' in event:
                usage = event['metadata'].get('usage', {})
                token_usage = {
                    'inputTokens': usage.get('inputTokens', 0),
                    'outputTokens': usage.get('outputTokens', 0),
                    'totalTokens': usage.get('totalTokens', 0)
                }
                yield ('metadata', token_usage)

        # Yield the complete response
        yield ('complete', full_response)

    except Exception as e:
        logger.error(f"ConverseStream error: {e}", exc_info=True)
        yield ('error', str(e))


def stream_followup_response(event: Dict[str, Any], context: Any, user_id: str = 'anonymous'):
    """
    Stream follow-up question response using ConverseStream API.

    Retrieves conversation history from DynamoDB and uses it to maintain context.
    Saves both user questions and assistant responses to DynamoDB.

    Args:
        event: API Gateway event
        context: Lambda context
        user_id: The authenticated user's ID
    """
    try:
        # Response metadata
        yield {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        }

        # Parse request
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')

        body = json.loads(body_str)
        question = body.get('question', '').strip()
        session_id = body.get('session_id')
        agent_type = body.get('agent_type', 'debt')
        ticker = body.get('ticker', '')

        if not question:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": "Question is required"
            }), "error")
            return

        if not session_id:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": "session_id is required for follow-up questions"
            }), "error")
            return

        # Get system prompt for agent type
        system_prompt = SYSTEM_PROMPTS.get(agent_type)
        if not system_prompt:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Unknown agent type: {agent_type}"
            }), "error")
            return

        logger.info(f"Follow-up question for session {session_id}: {question[:100]}...")

        # Save user question to DynamoDB
        user_message_id = save_followup_message(
            session_id=session_id,
            message_type='user',
            content=question,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # Get conversation history from DynamoDB
        conversation_history = get_conversation_history(session_id)

        # Add the new user message to history
        conversation_history.append({
            'role': 'user',
            'content': [{'text': question}]
        })

        # Call ConverseStream API
        full_response = ""
        token_usage = None

        for event_type, data in call_converse_stream(conversation_history, system_prompt, ticker):
            if event_type == 'chunk':
                yield format_sse_event(json.dumps({
                    "type": "chunk",
                    "text": data,
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }), "chunk")

            elif event_type == 'metadata':
                token_usage = data
                # Send token usage info to client
                yield format_sse_event(json.dumps({
                    "type": "token_usage",
                    "input_tokens": data['inputTokens'],
                    "output_tokens": data['outputTokens'],
                    "total_tokens": data['totalTokens'],
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }), "token_usage")

            elif event_type == 'complete':
                full_response = data

            elif event_type == 'error':
                yield format_sse_event(json.dumps({
                    "type": "error",
                    "message": data,
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }), "error")
                return

        # Save assistant response to DynamoDB (with token usage)
        assistant_message_id = save_followup_message(
            session_id=session_id,
            message_type='assistant',
            content=full_response,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker,
            token_usage=token_usage
        )

        # Completion event
        yield format_sse_event(json.dumps({
            "type": "complete",
            "session_id": session_id,
            "agent_type": agent_type,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "token_usage": token_usage,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "complete")

    except Exception as e:
        logger.error(f"Follow-up error: {e}", exc_info=True)
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")


def process_non_streaming_request(
    question: str,
    session_id: str,
    agent_type: str,
    ticker: str,
    user_id: str
) -> Dict[str, Any]:
    """
    Process a non-streaming follow-up request.

    Args:
        question: The user's question
        session_id: Session ID for conversation context
        agent_type: Type of analyst (debt, cashflow, growth)
        ticker: Stock ticker symbol
        user_id: User identifier

    Returns:
        Response dict with success status, response text, and token usage
    """
    # Get system prompt
    system_prompt = SYSTEM_PROMPTS.get(agent_type)
    if not system_prompt:
        return {
            'success': False,
            'error': f"Unknown agent type: {agent_type}"
        }

    # Save user question
    user_message_id = save_followup_message(
        session_id=session_id,
        message_type='user',
        content=question,
        user_id=user_id,
        agent_type=agent_type,
        ticker=ticker
    )

    # Get conversation history
    conversation_history = get_conversation_history(session_id)
    conversation_history.append({
        'role': 'user',
        'content': [{'text': question}]
    })

    # Call ConverseStream and collect response
    full_response = ""
    token_usage = None

    for event_type, data in call_converse_stream(conversation_history, system_prompt, ticker):
        if event_type == 'complete':
            full_response = data
        elif event_type == 'metadata':
            token_usage = data
        elif event_type == 'error':
            return {
                'success': False,
                'error': data
            }

    # Save assistant response
    assistant_message_id = save_followup_message(
        session_id=session_id,
        message_type='assistant',
        content=full_response,
        user_id=user_id,
        agent_type=agent_type,
        ticker=ticker,
        token_usage=token_usage
    )

    return {
        'success': True,
        'response': full_response,
        'session_id': session_id,
        'agent_type': agent_type,
        'user_message_id': user_message_id,
        'assistant_message_id': assistant_message_id,
        'token_usage': token_usage,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }


def lambda_handler(event: Dict[str, Any], context: Any):
    """
    Handle follow-up questions to analysis.

    Request Format:
    {
        "question": "Why is the debt analyst bearish?",
        "session_id": "ensemble-abc123",  // Required - from initial analysis
        "agent_type": "debt",             // Which analyst to ask (debt, cashflow, growth)
        "ticker": "AAPL"                  // For context
    }

    Authentication:
    - Requires valid JWT token in Authorization header (Bearer token)

    Response includes token usage metrics from ConverseStream API.
    """
    request_context = event.get('requestContext', {})

    # JWT Authentication - verify token before processing
    user_claims = verify_jwt_token(event)
    if not user_claims:
        logger.warning("Unauthorized request - invalid or missing JWT token")
        # For streaming, yield auth error
        if 'http' in request_context:
            def auth_error_stream():
                yield {
                    "statusCode": 401,
                    "headers": {
                        "Content-Type": "application/json",
                        "Access-Control-Allow-Origin": "*"
                    }
                }
                yield json.dumps({
                    "success": False,
                    "error": "Unauthorized - valid JWT token required",
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                })
            yield from auth_error_stream()
            return
        else:
            return error_response(401, "Unauthorized - valid JWT token required")

    # Extract user_id from JWT claims
    user_id = user_claims.get('user_id', user_claims.get('sub', 'anonymous'))

    # Lambda Function URL - use streaming
    if 'http' in request_context:
        logger.info("Streaming follow-up response via ConverseStream")
        yield from stream_followup_response(event, context, user_id=user_id)
        return

    # API Gateway - standard response
    try:
        body = json.loads(event.get('body', '{}'))
        question = body.get('question', '').strip()
        session_id = body.get('session_id')
        agent_type = body.get('agent_type', 'debt')
        ticker = body.get('ticker', '')

        if not question:
            return error_response(400, "Question is required")

        if not session_id:
            return error_response(400, "session_id is required for follow-up questions")

        if agent_type not in SYSTEM_PROMPTS:
            return error_response(400, f"Invalid agent_type: {agent_type}. Must be one of: {list(SYSTEM_PROMPTS.keys())}")

        # Process the request
        result = process_non_streaming_request(
            question=question,
            session_id=session_id,
            agent_type=agent_type,
            ticker=ticker,
            user_id=user_id
        )

        if not result.get('success'):
            return error_response(500, result.get('error', 'Unknown error'))

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }

    except Exception as e:
        logger.error(f"Follow-up handler error: {e}", exc_info=True)
        return error_response(500, str(e))


def error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': False,
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }
