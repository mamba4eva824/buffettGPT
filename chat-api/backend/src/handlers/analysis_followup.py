"""
Analysis Follow-Up Handler

Handles follow-up questions after ensemble analysis.
Uses Bedrock session memory to maintain conversation context.

The same sessionId from the initial analysis is reused,
allowing the agent to remember the previous analysis.
"""

import json
import boto3
import os
import logging
import jwt
import uuid
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal
from functools import lru_cache

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

# Initialize Bedrock client
bedrock_client = boto3.client(
    'bedrock-agent-runtime',
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


def save_followup_message(
    session_id: str,
    message_type: str,
    content: str,
    user_id: str,
    agent_type: str,
    ticker: str = ''
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
            'metadata': {
                'source': 'investment_research_followup',
                'agent_type': agent_type,
                'ticker': ticker
            }
        }

        messages_table.put_item(Item=convert_floats_to_decimals(message_record))
        logger.info(f"Saved {message_type} message {message_id} for session {session_id}")
        return message_id

    except Exception as e:
        logger.error(f"Failed to save {message_type} message to DynamoDB: {e}", exc_info=True)
        return None


# Agent configuration
AGENT_CONFIG = {
    'debt': {
        'agent_id': os.environ.get('DEBT_AGENT_ID'),
        'agent_alias': os.environ.get('DEBT_AGENT_ALIAS'),
    },
    'cashflow': {
        'agent_id': os.environ.get('CASHFLOW_AGENT_ID'),
        'agent_alias': os.environ.get('CASHFLOW_AGENT_ALIAS'),
    },
    'growth': {
        'agent_id': os.environ.get('GROWTH_AGENT_ID'),
        'agent_alias': os.environ.get('GROWTH_AGENT_ALIAS'),
    }
}


def format_sse_event(data: str, event_type: str = "message") -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {data}\n\n"


def stream_followup_response(event: Dict[str, Any], context: Any, user_id: str = 'anonymous'):
    """
    Stream follow-up question response.

    Uses the same sessionId from initial analysis to maintain context.
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

        # Get agent config
        config = AGENT_CONFIG.get(agent_type, {})
        agent_id = config.get('agent_id')
        agent_alias = config.get('agent_alias')

        if not agent_id or not agent_alias:
            # Fallback response if agent not configured
            fallback_response = f"I understand you're asking about {ticker}'s {agent_type} analysis: \"{question}\"\n\n*Full follow-up responses require Bedrock agent configuration.*\n"

            yield format_sse_event(json.dumps({
                "type": "chunk",
                "text": f"I understand you're asking about {ticker}'s {agent_type} analysis: \"{question}\"\n\n",
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }), "chunk")

            yield format_sse_event(json.dumps({
                "type": "chunk",
                "text": "*Full follow-up responses require Bedrock agent configuration.*\n",
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }), "chunk")

            # Save user question even for fallback
            save_followup_message(session_id, 'user', question, user_id, agent_type, ticker)
            # Save fallback response
            save_followup_message(session_id, 'assistant', fallback_response, user_id, agent_type, ticker)

            yield format_sse_event(json.dumps({
                "type": "complete",
                "session_id": session_id,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }), "complete")
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

        # Invoke agent with same session (maintains context)
        response = bedrock_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias,
            sessionId=session_id,  # Same session = remembers context
            inputText=question,
            streamingConfigurations={'streamFinalResponse': True}
        )

        # Stream response chunks and collect full response
        full_response = ""
        for event_item in response.get('completion', []):
            if 'chunk' in event_item:
                chunk = event_item['chunk']
                if 'bytes' in chunk:
                    chunk_text = chunk['bytes'].decode('utf-8')
                    full_response += chunk_text
                    yield format_sse_event(json.dumps({
                        "type": "chunk",
                        "text": chunk_text,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    }), "chunk")

        # Save assistant response to DynamoDB
        assistant_message_id = save_followup_message(
            session_id=session_id,
            message_type='assistant',
            content=full_response,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # Completion event
        yield format_sse_event(json.dumps({
            "type": "complete",
            "session_id": session_id,
            "agent_type": agent_type,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "complete")

    except Exception as e:
        logger.error(f"Follow-up error: {e}", exc_info=True)
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")


def lambda_handler(event: Dict[str, Any], context: Any):
    """
    Handle follow-up questions to analysis.

    Request Format:
    {
        "question": "Why is the debt analyst bearish?",
        "session_id": "ensemble-abc123",  // Required - from initial analysis
        "agent_type": "debt",             // Which agent to ask
        "ticker": "AAPL"                  // For context
    }

    Authentication:
    - Requires valid JWT token in Authorization header (Bearer token)

    The session_id must match the one from the initial analysis
    to maintain conversation context.
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
        logger.info("Streaming follow-up response")
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

        config = AGENT_CONFIG.get(agent_type, {})
        agent_id = config.get('agent_id')
        agent_alias = config.get('agent_alias')

        if not agent_id or not agent_alias:
            return error_response(503, f"Agent {agent_type} not configured")

        # Save user question to DynamoDB
        user_message_id = save_followup_message(
            session_id=session_id,
            message_type='user',
            content=question,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # Invoke agent
        response = bedrock_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias,
            sessionId=session_id,
            inputText=question,
            streamingConfigurations={'streamFinalResponse': True}
        )

        # Collect full response
        full_response = ""
        for event_item in response.get('completion', []):
            if 'chunk' in event_item:
                chunk = event_item['chunk']
                if 'bytes' in chunk:
                    full_response += chunk['bytes'].decode('utf-8')

        # Save assistant response to DynamoDB
        assistant_message_id = save_followup_message(
            session_id=session_id,
            message_type='assistant',
            content=full_response,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'response': full_response,
                'session_id': session_id,
                'agent_type': agent_type,
                'user_message_id': user_message_id,
                'assistant_message_id': assistant_message_id,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
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
