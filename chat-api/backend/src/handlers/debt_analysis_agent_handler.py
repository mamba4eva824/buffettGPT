"""
Debt Analysis Agent HTTP Handler
Invokes Bedrock Debt Analyst Agent for conversational debt analysis
"""

import json
import boto3
import os
import logging
import time
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Initialize Bedrock client
bedrock_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)

# Environment variables
DEBT_ANALYST_AGENT_ID = os.environ.get('DEBT_ANALYST_AGENT_ID')
DEBT_ANALYST_AGENT_ALIAS = os.environ.get('DEBT_ANALYST_AGENT_ALIAS')
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
WEBSOCKET_API_ENDPOINT = os.environ.get('WEBSOCKET_API_ENDPOINT')

# Initialize WebSocket API Gateway Management API client (lazy initialization)
_apigateway_client = None

def get_apigateway_client():
    """Get API Gateway Management API client for WebSocket connections"""
    global _apigateway_client
    if _apigateway_client is None and WEBSOCKET_API_ENDPOINT:
        _apigateway_client = boto3.client(
            'apigatewaymanagementapi',
            endpoint_url=WEBSOCKET_API_ENDPOINT
        )
    return _apigateway_client


def is_function_url_request(event: Dict[str, Any]) -> bool:
    """
    Check if request is from Lambda Function URL

    Args:
        event: Lambda event

    Returns:
        True if Function URL request, False if API Gateway
    """
    request_context = event.get('requestContext', {})
    # Function URL has 'http' key in requestContext
    return 'http' in request_context and request_context.get('http', {}).get('method')


def get_cors_headers(event: Dict[str, Any] = None):
    """
    Get CORS headers for API Gateway responses

    Lambda Function URLs handle CORS automatically via their configuration,
    so we only add CORS headers for API Gateway requests.

    Args:
        event: Lambda event (optional)

    Returns:
        Dict of CORS headers (empty for Function URL requests)
    """
    # Function URLs handle CORS automatically - don't add headers
    if event and is_function_url_request(event):
        return {}

    # API Gateway requires explicit CORS headers
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Session-Id',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }


def send_chunk_via_websocket(connection_id: Optional[str], text: Optional[str]) -> bool:
    """
    Send text chunk via WebSocket if connection available

    Args:
        connection_id: WebSocket connection ID (optional)
        text: Text chunk to send (None signals end of stream)

    Returns:
        True if sent successfully, False otherwise
    """
    if not connection_id:
        return False

    apigateway_client = get_apigateway_client()
    if not apigateway_client:
        logger.debug("WebSocket client not available (no WEBSOCKET_API_ENDPOINT)")
        return False

    try:
        message = {
            "type": "chunk" if text is not None else "chunk_complete",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }

        if text is not None:
            message["text"] = text

        apigateway_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message)
        )

        return True

    except apigateway_client.exceptions.GoneException:
        logger.warning(f"WebSocket connection {connection_id} is gone")
        return False
    except Exception as e:
        logger.warning(f"Failed to send chunk via WebSocket: {e}")
        return False


def format_sse_event(data: str, event_type: str = "message") -> str:
    """
    Format data as Server-Sent Event

    Args:
        data: JSON string data to send
        event_type: Event type (message, chunk, complete, error)

    Returns:
        Formatted SSE string
    """
    return f"event: {event_type}\ndata: {data}\n\n"


def stream_sse_response(event: Dict[str, Any], context: Any):
    """
    Generator function for Lambda response streaming with SSE format
    Streams Bedrock Agent responses in real-time to the client

    For RESPONSE_STREAM mode, the first yield must contain response metadata
    (statusCode and headers), and subsequent yields contain the body chunks.

    Args:
        event: Lambda event from Function URL
        context: Lambda context

    Yields:
        First yield: Dict with statusCode and headers (response metadata)
        Subsequent yields: SSE-formatted string chunks (response body)
    """
    try:
        # First yield: Response metadata (required for RESPONSE_STREAM mode)
        yield {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        }

        # Send connection event
        yield format_sse_event(json.dumps({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "connected")

        # Parse request body
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')

        body = json.loads(body_str)
        ticker = body.get('ticker', '').strip().upper()
        fiscal_year = body.get('fiscal_year')
        session_id = body.get('session_id', f"debt-analysis-{context.aws_request_id}")

        logger.info("SSE streaming request", extra={
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'session_id': session_id,
            'request_id': context.aws_request_id
        })

        # Validate ticker
        if not ticker:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": "ticker is required"
            }), "error")
            return

        if not is_valid_ticker(ticker):
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": "Invalid ticker format. Please provide 1-5 uppercase letters (e.g., AAPL, DIS, MSFT)"
            }), "error")
            return

        # Validate required environment variables
        if not DEBT_ANALYST_AGENT_ID or not DEBT_ANALYST_AGENT_ALIAS:
            logger.error("Missing required environment variables")
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": "Service configuration error"
            }), "error")
            return

        # Format user message for agent
        user_message = format_user_message(ticker, fiscal_year)

        logger.info("Invoking Bedrock Agent for streaming", extra={
            'agent_id': DEBT_ANALYST_AGENT_ID,
            'agent_alias': DEBT_ANALYST_AGENT_ALIAS
        })

        # Invoke Bedrock Agent with streaming configuration
        response = bedrock_client.invoke_agent(
            agentId=DEBT_ANALYST_AGENT_ID,
            agentAliasId=DEBT_ANALYST_AGENT_ALIAS,
            sessionId=session_id,
            inputText=user_message,
            streamingConfigurations={
                'streamFinalResponse': True
            }
        )

        # Stream chunks as SSE events
        agent_response = ""
        metrics_data = None
        chunk_count = 0

        for event_item in response.get('completion', []):
            # Extract and stream conversational text chunks
            if 'chunk' in event_item:
                chunk = event_item['chunk']
                if 'bytes' in chunk:
                    chunk_text = chunk['bytes'].decode('utf-8')
                    agent_response += chunk_text
                    chunk_count += 1

                    # Send chunk as SSE
                    yield format_sse_event(json.dumps({
                        "type": "chunk",
                        "text": chunk_text,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    }), "chunk")

            # Extract metrics from trace events
            elif 'trace' in event_item:
                trace = event_item['trace']

                # Look for action group invocation output
                if 'orchestrationTrace' in trace:
                    orch_trace = trace['orchestrationTrace']

                    if 'observation' in orch_trace:
                        observation = orch_trace['observation']

                        if 'actionGroupInvocationOutput' in observation:
                            action_output = observation['actionGroupInvocationOutput']

                            if 'text' in action_output:
                                try:
                                    metrics_data = json.loads(action_output['text'])
                                    logger.info("Extracted metrics from action group", extra={
                                        'ticker': metrics_data.get('ticker'),
                                        'signal': metrics_data.get('signal')
                                    })
                                except json.JSONDecodeError as e:
                                    logger.warning("Failed to parse action group JSON", extra={'error': str(e)})

        logger.info("Streaming complete", extra={
            'chunk_count': chunk_count,
            'response_length': len(agent_response),
            'has_metrics': bool(metrics_data)
        })

        # Send completion event with final data
        completion_data = {
            "type": "complete",
            "analysis": agent_response.strip(),
            "session_id": session_id,
            "ticker": ticker,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }

        # Add metrics if available
        if metrics_data:
            completion_data.update({
                'metrics': metrics_data.get('metrics', {}),
                'signal': metrics_data.get('signal'),
                'confidence': metrics_data.get('confidence'),
                'prediction': metrics_data.get('prediction'),
                'fiscal_year': metrics_data.get('fiscal_year')
            })

        yield format_sse_event(json.dumps(completion_data), "complete")

    except Exception as e:
        logger.error("SSE streaming error", extra={
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)

        yield format_sse_event(json.dumps({
            "type": "error",
            "message": f"Streaming error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")


def lambda_handler(event: Dict[str, Any], context: Any):
    """
    HTTP handler for conversational debt analysis via Bedrock Agent

    Supports both:
    1. Standard HTTP response (via API Gateway)
    2. SSE streaming response (via Lambda Function URL with RESPONSE_STREAM)

    For Python Lambda with RESPONSE_STREAM mode, the handler must be a generator
    that yields response chunks as bytes or strings. The Lambda runtime automatically
    handles streaming when the function yields instead of returns.

    Request Format:
    {
        "ticker": "DIS",
        "fiscal_year": 2023,  // optional
        "session_id": "session-123",  // optional, for follow-up questions
        "connection_id": "abc123xyz"  // optional, for WebSocket streaming (API Gateway only)
    }

    Response Format:
    {
        "success": true,
        "ticker": "DIS",
        "fiscal_year": 2023,
        "session_id": "session-123",
        "analysis": "Conversational analysis from agent...",
        "type": "conversational",
        "timestamp": "2024-01-15T12:00:00Z",
        "processing_time_ms": 8500,
        "metrics": {...},  // Financial metrics from ML model
        "signal": 1,  // Debt health signal (-2 to +2)
        "confidence": 0.73,  // Model confidence (0-1)
        "prediction": 1  // Same as signal
    }
    """
    # Detect if this is a Lambda Function URL request (for SSE streaming)
    request_context = event.get('requestContext', {})

    # Lambda Function URL has a different requestContext structure
    if 'http' in request_context and request_context.get('http', {}).get('method'):
        # This is a Function URL request - use TRUE Lambda Response Streaming
        logger.info("Detected Lambda Function URL request - using TRUE streaming (RESPONSE_STREAM mode)", extra={
            'request_id': context.aws_request_id,
            'method': request_context['http']['method']
        })

        # Use yield from to delegate to the generator
        # This makes lambda_handler itself a generator, which the Lambda runtime
        # will recognize and handle as a streaming response
        # First yield contains statusCode + headers, subsequent yields are body chunks
        yield from stream_sse_response(event, context)
        return  # End the generator

    # Otherwise, use standard API Gateway HTTP handler
    start_time = time.time()

    logger.info("Debt analysis agent handler invoked (API Gateway)", extra={
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME,
        'event_type': 'debt_analysis_agent',
        'request_id': context.aws_request_id
    })

    try:
        # Validate environment variables
        if not DEBT_ANALYST_AGENT_ID or not DEBT_ANALYST_AGENT_ALIAS:
            logger.error("Missing required environment variables", extra={
                'has_agent_id': bool(DEBT_ANALYST_AGENT_ID),
                'has_agent_alias': bool(DEBT_ANALYST_AGENT_ALIAS)
            })
            return error_response(
                500,
                "Service configuration error: Bedrock agent not configured",
                event
            )

        # Parse request body
        body = json.loads(event.get('body', '{}'))
        ticker = body.get('ticker', '').strip().upper()
        fiscal_year = body.get('fiscal_year')
        session_id = body.get('session_id', f"debt-analysis-{context.aws_request_id}")
        connection_id = body.get('connection_id')  # Optional WebSocket connection ID

        # Validate ticker
        if not ticker:
            return error_response(400, "ticker is required", event)

        if not is_valid_ticker(ticker):
            return error_response(
                400,
                "Invalid ticker format. Please provide 1-5 uppercase letters (e.g., AAPL, DIS, MSFT)",
                event
            )

        # Format user message for agent
        user_message = format_user_message(ticker, fiscal_year)

        logger.info("Invoking debt analyst agent", extra={
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'session_id': session_id,
            'agent_id': DEBT_ANALYST_AGENT_ID,
            'agent_alias': DEBT_ANALYST_AGENT_ALIAS,
            'has_websocket': bool(connection_id)
        })

        # Invoke Bedrock Agent with streaming configuration
        response = bedrock_client.invoke_agent(
            agentId=DEBT_ANALYST_AGENT_ID,
            agentAliasId=DEBT_ANALYST_AGENT_ALIAS,
            sessionId=session_id,
            inputText=user_message,
            streamingConfigurations={
                'streamFinalResponse': True  # Stream response as it's generated for real-time output
            }
        )

        # Extract streaming response and metrics
        agent_response, metrics_data = extract_agent_response(response, connection_id)

        # Send completion signal via WebSocket
        if connection_id:
            send_chunk_via_websocket(connection_id, None)

        if not agent_response:
            logger.error("Empty response from Bedrock agent")
            return error_response(500, "Agent returned empty response", event)

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info("Agent invocation successful", extra={
            'ticker': ticker,
            'session_id': session_id,
            'response_length': len(agent_response),
            'has_metrics': metrics_data is not None,
            'processing_time_ms': processing_time_ms
        })

        # Build response body
        response_body = {
            'success': True,
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'session_id': session_id,
            'analysis': agent_response,
            'type': 'conversational',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'processing_time_ms': processing_time_ms,
            'model': 'bedrock-debt-analyst-agent',
            'environment': ENVIRONMENT
        }

        # Add metrics if extracted from action group
        if metrics_data:
            response_body.update({
                'metrics': metrics_data.get('metrics', {}),
                'signal': metrics_data.get('signal'),
                'confidence': metrics_data.get('confidence'),
                'prediction': metrics_data.get('prediction')
            })
            # Update fiscal_year if provided by action group
            if 'fiscal_year' in metrics_data:
                response_body['fiscal_year'] = metrics_data['fiscal_year']

        # Return conversational response with embedded metrics
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                **get_cors_headers(event)
            },
            'body': json.dumps(response_body)
        }

    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in request body", extra={'error': str(e)})
        return error_response(400, "Invalid JSON in request body", event)

    except Exception as e:
        logger.error("Error invoking debt analyst agent", extra={
            'error': str(e),
            'error_type': type(e).__name__
        }, exc_info=True)

        # Check for specific AWS errors
        error_message = str(e)
        if 'ResourceNotFoundException' in error_message:
            return error_response(
                500,
                "Bedrock agent not found. Please check configuration.",
                event
            )
        elif 'AccessDeniedException' in error_message:
            return error_response(
                500,
                "Access denied to Bedrock agent. Please check IAM permissions.",
                event
            )
        elif 'ThrottlingException' in error_message:
            return error_response(
                429,
                "Service is temporarily overloaded. Please try again in a moment.",
                event
            )
        else:
            return error_response(500, f"Internal server error: {error_message}", event)


def format_user_message(ticker: str, fiscal_year: int = None) -> str:
    """
    Format user message for agent invocation

    Args:
        ticker: Stock ticker symbol
        fiscal_year: Optional fiscal year

    Returns:
        Formatted message string
    """
    message = f"Analyze {ticker}'s debt health"

    if fiscal_year:
        message += f" for fiscal year {fiscal_year}"

    message += ". Please use the ML model to assess their debt position and explain the key metrics."

    return message


def extract_agent_response(response: Dict[str, Any], connection_id: Optional[str] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Extract text and metrics from streaming agent response, optionally streaming chunks via WebSocket

    Args:
        response: Bedrock agent response with streaming completion
        connection_id: Optional WebSocket connection ID for streaming chunks

    Returns:
        Tuple of (agent_response_text, metrics_data)
        - agent_response_text: Complete conversational response text
        - metrics_data: Extracted metrics from action group invocation (if available)
    """
    agent_response = ""
    metrics_data = None

    try:
        for event in response.get('completion', []):
            # Extract and stream conversational text chunks
            if 'chunk' in event:
                chunk = event['chunk']
                if 'bytes' in chunk:
                    chunk_text = chunk['bytes'].decode('utf-8')

                    # Send chunk via WebSocket immediately
                    send_chunk_via_websocket(connection_id, chunk_text)

                    # Accumulate full response
                    agent_response += chunk_text

            # Extract metrics from trace events
            elif 'trace' in event:
                trace = event['trace']
                logger.debug("Agent trace event", extra={'trace': trace})

                # Look for action group invocation output
                if 'orchestrationTrace' in trace:
                    orch_trace = trace['orchestrationTrace']

                    # Check for observation with action group output
                    if 'observation' in orch_trace:
                        observation = orch_trace['observation']

                        if 'actionGroupInvocationOutput' in observation:
                            action_output = observation['actionGroupInvocationOutput']

                            # Extract text response (JSON string from Lambda)
                            if 'text' in action_output:
                                try:
                                    metrics_data = json.loads(action_output['text'])
                                    logger.info("Extracted metrics from action group", extra={
                                        'ticker': metrics_data.get('ticker'),
                                        'signal': metrics_data.get('signal'),
                                        'has_metrics': 'metrics' in metrics_data
                                    })
                                except json.JSONDecodeError as e:
                                    logger.warning("Failed to parse action group JSON response", extra={
                                        'error': str(e),
                                        'text': action_output.get('text', '')[:200]
                                    })

    except Exception as e:
        logger.error("Error extracting agent response", extra={'error': str(e)})
        raise

    return agent_response.strip(), metrics_data


def is_valid_ticker(ticker: str) -> bool:
    """
    Validate ticker symbol format

    Args:
        ticker: Stock ticker to validate

    Returns:
        True if valid ticker format
    """
    if not ticker or not isinstance(ticker, str):
        return False

    # Ticker should be 1-5 uppercase letters
    return len(ticker) >= 1 and len(ticker) <= 5 and ticker.isalpha() and ticker.isupper()


def error_response(status_code: int, message: str, event: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create standardized error response

    Args:
        status_code: HTTP status code
        message: Error message
        event: Lambda event (for CORS header detection)

    Returns:
        API Gateway response dict
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            **get_cors_headers(event)
        },
        'body': json.dumps({
            'success': False,
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }
