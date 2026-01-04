"""
Handler for supervisor-orchestrated analysis requests.

Routes requests to the multi-agent orchestrator which:
1. Fetches financial data (once)
2. Runs ML inference (3 models in sequence)
3. Invokes expert agents (in parallel)
4. Streams supervisor synthesis (to user)
"""
import asyncio
import json
import logging
import time
import base64
from datetime import datetime
from typing import Dict, Any

from services.orchestrator import orchestrate_supervisor_analysis
from services.persistence import save_message
from utils.fmp_client import normalize_ticker, validate_ticker
from utils.conversation_updater import update_conversation_timestamp

logger = logging.getLogger(__name__)


def handle_supervisor_request(
    event: Dict[str, Any],
    context: Any,
    user_claims: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle supervisor-mode analysis request.

    Runs async orchestration and returns buffered SSE streaming response.
    Saves messages to DynamoDB for conversation tracking.

    Args:
        event: Lambda event from Function URL or API Gateway
        context: Lambda context
        user_claims: Verified JWT claims

    Returns:
        Lambda response dict with statusCode, headers, and SSE body
    """
    start_time = time.time()

    # Parse request body
    body_str = event.get('body', '{}')
    if event.get('isBase64Encoded'):
        body_str = base64.b64decode(body_str).decode('utf-8')

    body = json.loads(body_str)
    company_input = body.get('company', body.get('ticker', '')).strip()
    fiscal_year = body.get('fiscal_year', datetime.now().year)
    session_id = body.get('session_id', f"supervisor-{context.aws_request_id}")
    conversation_id = body.get('conversation_id')
    user_id = user_claims.get('user_id', 'unknown')

    # Normalize and validate ticker
    ticker = normalize_ticker(company_input)
    if not validate_ticker(ticker):
        return {
            'statusCode': 400,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'success': False,
                'error': f'Invalid ticker: {company_input}',
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }

    logger.info(f"Starting supervisor analysis for {ticker} (FY{fiscal_year})")

    # Save user message if conversation tracking enabled
    user_message_id = None
    if conversation_id:
        user_query = f"Analyze {company_input}"
        user_message_id = save_message(
            conversation_id=conversation_id,
            user_id=user_id,
            message_type='user',
            content=user_query
        )
        logger.info(f"Saved user message {user_message_id} for conversation {conversation_id}")

    # Run async orchestration and collect chunks
    chunks = []
    accumulated_text = []

    async def collect_chunks():
        async for chunk in orchestrate_supervisor_analysis(
            ticker=ticker,
            fiscal_year=fiscal_year,
            session_id=session_id
        ):
            chunks.append(chunk)
            # Extract supervisor text for persistence
            # Chunks are SSE-formatted: "event: chunk\ndata: {...}\n\n"
            if 'data: ' in chunk and '"agent_type": "supervisor"' in chunk:
                try:
                    data_line = chunk.split('data: ')[1].split('\n')[0]
                    data = json.loads(data_line)
                    if data.get('type') == 'chunk' and 'text' in data:
                        accumulated_text.append(data['text'])
                except (json.JSONDecodeError, IndexError):
                    pass

    # Run the async function
    asyncio.run(collect_chunks())

    # Save assistant message to conversation if provided
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
        logger.info(f"Saved supervisor response to conversation {conversation_id}")

    # Return SSE response
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        },
        'body': ''.join(chunks)
    }
