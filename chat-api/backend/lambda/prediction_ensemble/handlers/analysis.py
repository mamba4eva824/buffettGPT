"""
Streaming Analysis Handler.

EXTRACTED FROM: handler.py
- generate_analysis_chunks(): lines 755-883
- stream_sse_response(): lines 885-924
- handle_function_url_request(): lines 1142-1218

Handles streaming SSE responses for single-agent financial analysis.
"""
import json
import logging
import time
import base64
from datetime import datetime
from typing import Dict, Any, Generator

from utils.fmp_client import get_financial_data, normalize_ticker, validate_ticker
from utils.feature_extractor import extract_all_features
from utils.conversation_updater import update_conversation_timestamp
from services.inference import run_inference
from services.streaming import format_sse_event
from services.bedrock import invoke_agent_streaming
from services.persistence import save_message
from models.schemas import DecimalEncoder

logger = logging.getLogger(__name__)


def generate_analysis_chunks(event: Dict[str, Any], context: Any) -> Generator[str, None, None]:
    """
    Generator for ensemble analysis SSE events.

    Yields SSE-formatted string events for:
    1. Connection established
    2. Data fetching status
    3. Feature extraction status
    4. Model inference results (for each model)
    5. Agent response chunks
    6. Completion

    Args:
        event: Lambda event
        context: Lambda context

    Yields:
        SSE-formatted string chunks
    """
    try:
        # Send connection event
        yield format_sse_event(json.dumps({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "connected")

        # Parse request body
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            body_str = base64.b64decode(body_str).decode('utf-8')

        body = json.loads(body_str)
        company_input = body.get('company', body.get('ticker', '')).strip()
        agent_type = body.get('agent_type', 'debt')
        fiscal_year = body.get('fiscal_year', datetime.now().year)
        session_id = body.get('session_id', f"ensemble-{context.aws_request_id}")

        # Normalize ticker
        ticker = normalize_ticker(company_input)

        if not validate_ticker(ticker):
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Invalid company/ticker: {company_input}"
            }), "error")
            return

        logger.info(f"Analyzing {ticker} with {agent_type} agent")

        # Send status: fetching data
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Fetching financial data for {ticker}...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Fetch financial data (with caching)
        financial_data = get_financial_data(ticker, fiscal_year)

        if not financial_data or 'raw_financials' not in financial_data:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Could not fetch financial data for {ticker}"
            }), "error")
            return

        # Send status: extracting features
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": "Extracting financial features...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Extract features
        features = extract_all_features(financial_data['raw_financials'])

        # Send status: running inference
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Running {agent_type} model inference...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Run inference for requested agent type
        inference_result = run_inference(agent_type, features)

        # Send inference results
        yield format_sse_event(json.dumps({
            "type": "inference",
            "agent_type": agent_type,
            "ticker": ticker,
            "prediction": inference_result['prediction'],
            "confidence": inference_result['confidence'],
            "ci_width": inference_result['ci_width'],
            "confidence_interpretation": inference_result['confidence_interpretation'],
            "probabilities": inference_result['probabilities'],
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "inference")

        # Send status: generating analysis
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Generating {agent_type} expert analysis...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Stream agent response
        for chunk in invoke_agent_streaming(
            agent_type, ticker, fiscal_year,
            inference_result, features, session_id
        ):
            yield chunk

        # Send completion
        yield format_sse_event(json.dumps({
            "type": "complete",
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "agent_type": agent_type,
            "session_id": session_id,
            "inference": inference_result,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "complete")

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")


def stream_sse_response(event: Dict[str, Any], context: Any) -> Generator:
    """
    Generator function for Lambda response streaming with SSE format.

    For RESPONSE_STREAM mode, the first yield must contain response metadata
    (statusCode and headers), and subsequent yields contain the body chunks.

    Args:
        event: Lambda event from Function URL
        context: Lambda context

    Yields:
        First yield: Dict with statusCode and headers (response metadata)
        Subsequent yields: SSE-formatted string chunks (response body)
    """
    # First yield: Response metadata (required for RESPONSE_STREAM mode)
    # NOTE: CORS headers are handled by Terraform's Function URL CORS config
    yield {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    }

    # Subsequent yields: SSE chunks from generate_analysis_chunks
    try:
        for chunk in generate_analysis_chunks(event, context):
            yield chunk
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_event = format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")
        yield error_event


def handle_function_url_request(event: Dict[str, Any], context: Any,
                                 user_claims: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Lambda Function URL request with buffered SSE response.

    Collects all SSE chunks and returns them as a complete response.
    Saves messages to DynamoDB for conversation tracking.

    Args:
        event: Lambda event from Function URL
        context: Lambda context
        user_claims: Verified JWT claims

    Returns:
        Lambda response dict with statusCode, headers, and body
    """
    logger.info("Using Lambda Function URL (buffered response)")
    start_time = time.time()

    # Parse request to get conversation_id and ticker for message saving
    body_str = event.get('body', '{}')
    if event.get('isBase64Encoded'):
        body_str = base64.b64decode(body_str).decode('utf-8')
    body = json.loads(body_str)

    conversation_id = body.get('conversation_id')
    company_input = body.get('company', body.get('ticker', '')).strip()
    agent_type = body.get('agent_type', 'debt')
    user_id = user_claims.get('user_id', 'unknown')

    # Only save user message for the first agent (debt) to avoid duplicates
    # The frontend calls this 3 times (debt, cashflow, growth) in parallel
    user_message_id = None
    if conversation_id and agent_type == 'debt':
        user_query = f"Analyze {company_input}"
        user_message_id = save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_type='user',
            content=user_query
        )
        logger.info(f"Saved user message {user_message_id} for conversation {conversation_id}")

    # Collect all SSE chunks
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }
    chunks = []
    accumulated_text = []  # Accumulate text for saving

    for item in stream_sse_response(event, context):
        if isinstance(item, dict) and 'statusCode' in item:
            # This is the first yield (metadata) - update headers if needed
            headers.update(item.get('headers', {}))
        elif isinstance(item, str):
            # This is an SSE chunk
            chunks.append(item)
            # Extract text from chunk for accumulation
            if 'data: ' in item:
                try:
                    data_line = item.split('data: ')[1].split('\n')[0]
                    data = json.loads(data_line)
                    if data.get('type') == 'chunk' and 'text' in data:
                        accumulated_text.append(data['text'])
                except (json.JSONDecodeError, IndexError):
                    pass

    # Save assistant message if conversation_id provided
    if conversation_id and accumulated_text:
        processing_time_ms = (time.time() - start_time) * 1000
        full_response = ''.join(accumulated_text)
        save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_type='assistant',
            content=full_response,
            parent_message_id=user_message_id,
            processing_time_ms=processing_time_ms
        )
        # Update conversation timestamp
        update_conversation_timestamp(conversation_id, user_id=user_id)
        logger.info(f"Saved assistant response to conversation {conversation_id}")

    # Return complete response
    return {
        'statusCode': 200,
        'headers': headers,
        'body': ''.join(chunks)
    }


def handle_api_gateway_request(event: Dict[str, Any], context: Any,
                               user_claims: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle standard API Gateway request with JSON response.

    Args:
        event: API Gateway event
        context: Lambda context
        user_claims: Verified JWT claims (not currently used, but available)

    Returns:
        Lambda response dict with JSON body
    """
    from services.streaming import format_sse_event  # Already imported at top

    start_time = time.time()

    body = json.loads(event.get('body', '{}'))
    company_input = body.get('company', body.get('ticker', '')).strip()
    agent_type = body.get('agent_type', 'debt')
    fiscal_year = body.get('fiscal_year', datetime.now().year)
    session_id = body.get('session_id', f"ensemble-{context.aws_request_id}")

    ticker = normalize_ticker(company_input)

    if not validate_ticker(ticker):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'success': False,
                'error': f"Invalid company/ticker: {company_input}",
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }

    # Fetch data
    financial_data = get_financial_data(ticker, fiscal_year)

    if not financial_data or 'raw_financials' not in financial_data:
        return {
            'statusCode': 404,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'success': False,
                'error': f"Could not fetch financial data for {ticker}",
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }

    # Extract features
    features = extract_all_features(financial_data['raw_financials'])

    # Run inference
    inference_result = run_inference(agent_type, features)

    processing_time_ms = int((time.time() - start_time) * 1000)

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'success': True,
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'agent_type': agent_type,
            'session_id': session_id,
            'inference': inference_result,
            'features': features,
            'processing_time_ms': processing_time_ms,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder)
    }
