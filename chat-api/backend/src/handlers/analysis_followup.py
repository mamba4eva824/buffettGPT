"""
Analysis Follow-Up Handler

Handles follow-up questions after ensemble analysis.
Uses Bedrock session memory to maintain conversation context.

The same sessionId from the initial analysis is reused,
allowing the agent to remember the previous analysis.

Integrates with TokenUsageTracker for monthly token limiting:
- Pre-request validation to check if user is within limit
- Post-request recording of token consumption
- Support for threshold notifications (80%, 90%, 100%)
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

# Import token usage tracker
from utils.token_usage_tracker import TokenUsageTracker

# Import tool executor for orchestration loop
from utils.tool_executor import execute_tool, DecimalEncoder

# Configure logging - must set level on root logger for Lambda
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger()
logger.setLevel(getattr(logging, log_level))

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

# Initialize Bedrock clients
# bedrock-agent-runtime: For invoke_agent API (agent with action groups)
bedrock_agent_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)

# bedrock-runtime: For converse_stream API (direct model invocation with token tracking)
bedrock_runtime_client = boto3.client(
    'bedrock-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)

# Model ID for direct invocation (Claude 4.5 Haiku via US cross-region inference profile)
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)

# Keep backward compatibility alias
bedrock_client = bedrock_agent_client

# Initialize DynamoDB for message persistence
dynamodb = boto3.resource('dynamodb')
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')

# Initialize messages table (lazy initialization to handle missing env var gracefully)
messages_table = None
if CHAT_MESSAGES_TABLE:
    messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)

# Initialize token usage tracker
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')
token_tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE) if TOKEN_USAGE_TABLE else TokenUsageTracker()


# =============================================================================
# TOOL CONFIGURATION - Replaces Bedrock Agent Action Groups
# =============================================================================

FOLLOWUP_TOOLS = {
    "tools": [
        {
            "toolSpec": {
                "name": "getReportSection",
                "description": "Retrieves a specific section from a company's investment report. Use when the user asks about specific aspects of analysis like growth, debt, valuation, risks, etc.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol in uppercase (e.g., AAPL, MSFT, GOOGL)"
                            },
                            "section_id": {
                                "type": "string",
                                "enum": [
                                    "01_executive_summary",
                                    "06_growth",
                                    "07_profit",
                                    "08_valuation",
                                    "09_earnings",
                                    "10_cashflow",
                                    "11_debt",
                                    "12_dilution",
                                    "13_bull",
                                    "14_bear",
                                    "15_warnings",
                                    "16_vibe",
                                    "17_realtalk"
                                ],
                                "description": "Section identifier: 01_executive_summary (overview), 06_growth (revenue/earnings growth), 07_profit (margins), 08_valuation (P/E, etc.), 09_earnings (quality), 10_cashflow (FCF), 11_debt (leverage), 12_dilution (share count), 13_bull (positive case), 14_bear (risks), 15_warnings (red flags), 16_vibe (sentiment), 17_realtalk (bottom line)"
                            }
                        },
                        "required": ["ticker", "section_id"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getReportRatings",
                "description": "Gets the investment ratings, confidence scores, and overall verdict for a company. Use when the user asks about ratings, recommendations, or the overall investment thesis.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol in uppercase"
                            }
                        },
                        "required": ["ticker"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getMetricsHistory",
                "description": "Retrieves historical financial metrics for trend analysis. Use when the user asks about trends, historical performance, or comparisons over time.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol in uppercase"
                            },
                            "metric_type": {
                                "type": "string",
                                "enum": [
                                    "all",
                                    "revenue_profit",
                                    "cashflow",
                                    "balance_sheet",
                                    "debt_leverage",
                                    "earnings_quality",
                                    "dilution",
                                    "valuation"
                                ],
                                "description": "Category of metrics to retrieve. Use 'all' for comprehensive view or specific category for focused analysis.",
                                "default": "all"
                            },
                            "quarters": {
                                "type": "integer",
                                "description": "Number of quarters of history (1-40, default 8 for recent trends, 20 for long-term)",
                                "default": 8,
                                "minimum": 1,
                                "maximum": 40
                            }
                        },
                        "required": ["ticker"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getAvailableReports",
                "description": "Lists all companies with available investment reports. Use when the user asks what companies are covered or wants to explore available analyses.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        }
    ]
}


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
        # Use milliseconds for timestamp to prevent key collisions when saving
        # user question and assistant response in quick succession
        timestamp_unix = int(datetime.utcnow().timestamp() * 1000)
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




def format_sse_event(data: str, event_type: str = "message") -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {data}\n\n"


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text.

    Uses a rough approximation of ~4 characters per token for Claude models.
    This is conservative to ensure we don't undercount.

    Args:
        text: The text to estimate tokens for.

    Returns:
        Estimated token count.
    """
    if not text:
        return 0
    # Claude models average ~4 characters per token
    # Using 3.5 to be slightly conservative (won't undercount)
    return max(1, int(len(text) / 3.5))


def create_token_limit_error_response(limit_check: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a standardized error response for token limit exceeded.

    Args:
        limit_check: Response from TokenUsageTracker.check_limit()

    Returns:
        Error response dict for API Gateway or SSE.
    """
    return {
        'error': 'token_limit_exceeded',
        'message': 'Monthly token limit reached. Your usage will reset at the start of next month.',
        'usage': {
            'total_tokens': limit_check.get('total_tokens', 0),
            'token_limit': limit_check.get('token_limit', 0),
            'percent_used': limit_check.get('percent_used', 100.0),
            'reset_date': limit_check.get('reset_date', '')
        }
    }


def stream_followup_response(event: Dict[str, Any], context: Any, user_id: str = 'anonymous'):
    """
    Stream follow-up question response.

    Uses the same sessionId from initial analysis to maintain context.
    Saves both user questions and assistant responses to DynamoDB.
    Integrates with TokenUsageTracker for monthly token limiting.

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

        # =====================================================
        # TOKEN LIMIT CHECK - Pre-request validation
        # =====================================================
        limit_check = token_tracker.check_limit(user_id)
        if not limit_check.get('allowed', True):
            logger.warning(f"Token limit exceeded for user {user_id}: {limit_check}")
            yield format_sse_event(json.dumps({
                "type": "token_limit_exceeded",
                **create_token_limit_error_response(limit_check),
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }), "error")
            return

        logger.info(f"Follow-up question for session {session_id}: {question[:100]}...")

        # =====================================================
        # USE CONVERSE_STREAM API with TOOL USE ORCHESTRATION
        # =====================================================

        # Build initial messages
        messages = [
            {
                "role": "user",
                "content": [{"text": question}]
            }
        ]

        # Enhanced system prompt - layman-friendly financial analyst for millennials/gen-z
        system_prompt = f"""You're a financial analyst who explains investing like talking to a friend. Your reader is 25-35, may have student loans, and wants to build wealth but doesn't speak Wall Street.

ZERO JARGON POLICY - Always translate finance-speak:
- Free Cash Flow → "money left over after paying all the bills"
- FCF Margin → "what they keep from each dollar as real cash"
- Operating Cash Flow → "cash that actually came in"
- Debt-to-Equity → "how much they borrowed vs what they own"
- Interest Coverage → "can they pay their loans? They make Xx their loan payments"
- Net Debt → "what they still owe after using their savings"
- Net Cash → "extra savings after paying all debt"
- Gross Margin → "keeps X cents from every dollar of sales"
- Net Margin → "takes home X cents per dollar"
- P/E Ratio → "years of profits to pay back your investment"
- ROE → "how much profit they make from shareholder money"
- Dilution → "your slice of the pie is shrinking"

TONE:
- Casual and conversational — like texting a smart friend
- Use analogies: "It's like having a $50K mortgage while keeping $80K in savings"
- Make numbers tangible: "$99B is enough to buy every NFL team... twice"
- Be direct: "Here's the deal..." or "Bottom line:"

TOOL USAGE:
- For SPECIFIC {ticker} numbers/metrics → MUST use tools (never guess)
- For general finance concepts → just explain it
- For trends/comparisons → use getMetricsHistory

AVAILABLE TOOLS:
1. getReportSection(ticker, section_id) - Get report sections:
   07_profit (margins), 06_growth, 08_valuation, 10_cashflow, 11_debt,
   13_bull (bull case), 14_bear (risks), 15_warnings, 01_executive_summary

2. getReportRatings(ticker) - Investment ratings and verdict

3. getMetricsHistory(ticker, metric_type, quarters) - Historical metrics:
   metric_types: revenue_profit, cashflow, balance_sheet, debt_leverage, all
   quarters: 8 (recent) to 20 (long-term)

4. getAvailableReports() - List available company reports

Keep it real, keep it short, make them feel smarter when they're done reading.

Current context: {ticker} | {agent_type} analysis"""

        # Track tokens across all turns
        total_input_tokens = 0
        total_output_tokens = 0
        full_response = ""
        max_turns = 10  # Safety limit to prevent infinite loops
        turn_count = 0

        # =====================================================
        # ORCHESTRATION LOOP - Handle tool calls
        # =====================================================
        while turn_count < max_turns:
            turn_count += 1
            logger.info(f"[STREAMING] Orchestration turn {turn_count}/{max_turns} for session {session_id}, question: {question[:50]}...")

            # Call converse_stream with tools
            response = bedrock_runtime_client.converse_stream(
                modelId=FOLLOWUP_MODEL_ID,
                messages=messages,
                system=[{"text": system_prompt}],
                toolConfig=FOLLOWUP_TOOLS,
                inferenceConfig={
                    "maxTokens": 2048,
                    "temperature": 0.7
                }
            )

            # Track this turn's content
            assistant_content = []
            current_text_block = ""
            current_tool_use = None
            stop_reason = None

            for stream_event in response.get('stream', []):

                # Content block start - initialize text or tool use
                if 'contentBlockStart' in stream_event:
                    start = stream_event['contentBlockStart'].get('start', {})
                    if 'toolUse' in start:
                        current_tool_use = {
                            'toolUseId': start['toolUse']['toolUseId'],
                            'name': start['toolUse']['name'],
                            'input': ''
                        }

                # Content block delta - accumulate text or tool input
                if 'contentBlockDelta' in stream_event:
                    delta = stream_event['contentBlockDelta'].get('delta', {})

                    if 'text' in delta:
                        chunk_text = delta['text']
                        current_text_block += chunk_text
                        full_response += chunk_text
                        # Stream text immediately to client
                        yield format_sse_event(json.dumps({
                            "type": "chunk",
                            "text": chunk_text,
                            "timestamp": datetime.utcnow().isoformat() + 'Z'
                        }), "chunk")

                    if 'toolUse' in delta:
                        # Accumulate tool input JSON
                        if current_tool_use and 'input' in delta['toolUse']:
                            current_tool_use['input'] += delta['toolUse']['input']

                # Content block stop - finalize text or tool use block
                if 'contentBlockStop' in stream_event:
                    if current_text_block:
                        assistant_content.append({"text": current_text_block})
                        current_text_block = ""

                    if current_tool_use and current_tool_use.get('name'):
                        try:
                            tool_input = json.loads(current_tool_use['input']) if current_tool_use['input'] else {}
                        except json.JSONDecodeError:
                            tool_input = {}

                        assistant_content.append({
                            "toolUse": {
                                "toolUseId": current_tool_use['toolUseId'],
                                "name": current_tool_use['name'],
                                "input": tool_input
                            }
                        })
                        current_tool_use = None

                # Metadata - extract token counts
                if 'metadata' in stream_event:
                    usage = stream_event['metadata'].get('usage', {})
                    total_input_tokens += usage.get('inputTokens', 0)
                    total_output_tokens += usage.get('outputTokens', 0)
                    logger.info(f"Turn {turn_count} tokens: input={usage.get('inputTokens', 0)}, output={usage.get('outputTokens', 0)}")

                # Message stop - check stop reason
                if 'messageStop' in stream_event:
                    stop_reason = stream_event['messageStop'].get('stopReason')

            # =====================================================
            # HANDLE STOP REASON
            # =====================================================
            logger.info(f"[STREAMING] Turn {turn_count} stop_reason={stop_reason}, assistant_content_blocks={len(assistant_content)}")

            if stop_reason == 'tool_use':
                # Model wants to use tools - execute them and continue
                tool_names = [b['toolUse']['name'] for b in assistant_content if 'toolUse' in b]
                logger.info(f"[STREAMING] Tool use requested: {tool_names}")

                # Add assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": assistant_content
                })

                # Execute each tool and collect results
                tool_results = []
                for block in assistant_content:
                    if 'toolUse' in block:
                        tool_use = block['toolUse']
                        tool_input = tool_use.get('input', {})
                        logger.info(f"[STREAMING] Executing tool: {tool_use['name']} with input: {json.dumps(tool_input)}")

                        # Execute the tool
                        result = execute_tool(tool_use['name'], tool_input)

                        # Log result summary
                        result_success = result.get('success', False)
                        result_error = result.get('error', None)
                        logger.info(f"[STREAMING] Tool result: success={result_success}, error={result_error}, keys={list(result.keys())}")

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use['toolUseId'],
                                "content": [{"text": json.dumps(result, cls=DecimalEncoder)}]
                            }
                        })

                # Add tool results as user message
                messages.append({
                    "role": "user",
                    "content": tool_results
                })
                logger.info(f"[STREAMING] Added {len(tool_results)} tool results, continuing to next turn...")

                # Continue the loop for model to process results
                continue

            elif stop_reason == 'end_turn':
                # Model finished responding - exit loop
                logger.info(f"[STREAMING] End turn reached after {turn_count} turns, response length={len(full_response)}")
                break

            else:
                # Unexpected stop reason (could be max_tokens, content_filtered, etc.)
                logger.warning(f"[STREAMING] Unexpected stop reason: {stop_reason}, ending loop")
                break

        # =====================================================
        # POST-LOOP: Save messages and record tokens
        # =====================================================

        # Save user question
        user_message_id = save_followup_message(
            session_id=session_id,
            message_type='user',
            content=question,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # Save assistant response
        assistant_message_id = save_followup_message(
            session_id=session_id,
            message_type='assistant',
            content=full_response,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # Record token usage (accumulated across all turns)
        if total_input_tokens == 0 and total_output_tokens == 0:
            logger.warning("No token metadata received, using estimation")
            total_input_tokens = estimate_tokens(question)
            total_output_tokens = estimate_tokens(full_response)

        usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
        logger.info(f"Total tokens for session: input={total_input_tokens}, output={total_output_tokens}, turns={turn_count}")

        # Check for threshold notifications
        threshold = usage_result.get('threshold_reached')
        if threshold:
            logger.info(f"User {user_id} reached {threshold} token threshold")

        # Send completion event
        yield format_sse_event(json.dumps({
            "type": "complete",
            "session_id": session_id,
            "agent_type": agent_type,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "turns": turn_count,
            "token_usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": usage_result.get('total_tokens'),
                "token_limit": usage_result.get('token_limit'),
                "percent_used": usage_result.get('percent_used'),
                "remaining_tokens": usage_result.get('remaining_tokens'),
                "threshold_reached": threshold
            },
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

    Invocation modes:
    - Lambda Function URL (direct): Uses RESPONSE_STREAM for SSE streaming
    - API Gateway HTTP_PROXY: Returns non-streaming JSON response
    """
    request_context = event.get('requestContext', {})
    headers = event.get('headers', {}) or {}

    # DEBUG: Log key event fields to understand invocation source
    logger.info(f"Event keys: {list(event.keys())}")
    logger.info(f"RequestContext keys: {list(request_context.keys())}")
    logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k.lower().startswith(('x-', 'via', 'forwarded'))})}")

    # Detect invocation source:
    # - Lambda Function URL (direct): has 'http' in requestContext (e.g., requestContext.http.method)
    # - API Gateway REST API via HTTP_PROXY:
    #   * Has 'httpMethod' at top level or requestContext.httpMethod (standard API Gateway)
    #   * OR has x-amzn-apigateway-api-id header (forwarded from API Gateway)
    #   * OR has x-forwarded-for header set by API Gateway
    is_function_url = 'http' in request_context
    is_api_gateway = (
        event.get('httpMethod') or
        request_context.get('httpMethod') or
        headers.get('x-amzn-apigateway-api-id') or
        headers.get('X-Amzn-Apigateway-Api-Id') or
        # Check if forwarded through API Gateway - presence of these headers indicates proxy
        (headers.get('x-forwarded-for') and headers.get('x-forwarded-port'))
    )

    logger.info(f"Invocation detection: is_function_url={is_function_url}, is_api_gateway={is_api_gateway}")

    # Extract path for routing
    http_context = request_context.get('http', {})
    path = http_context.get('path', event.get('path', ''))
    method = http_context.get('method', event.get('httpMethod', 'POST'))

    # Health check endpoint - no auth required
    if path == '/health' and method == 'GET':
        logger.info("Health check request")
        health_body = {
            'status': 'healthy',
            'service': 'analysis-followup',
            'environment': os.environ.get('ENVIRONMENT', 'unknown'),
            'model_id': FOLLOWUP_MODEL_ID,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
        # For Lambda Function URL with RESPONSE_STREAM, use generator
        if is_function_url and not is_api_gateway:
            def health_stream():
                yield {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"}
                }
                yield json.dumps(health_body)
            return health_stream()
        # For API Gateway, use standard response format
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(health_body)
        }

    # JWT Authentication - verify token before processing
    user_claims = verify_jwt_token(event)
    if not user_claims:
        logger.warning("Unauthorized request - invalid or missing JWT token")
        # For streaming (direct Function URL), return a generator for auth error
        if is_function_url and not is_api_gateway:
            def auth_error_stream():
                yield {
                    "statusCode": 401,
                    "headers": {
                        "Content-Type": "application/json"
                        # Note: CORS headers handled by Lambda Function URL CORS config
                    }
                }
                yield json.dumps({
                    "success": False,
                    "error": "Unauthorized - valid JWT token required",
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                })
            # IMPORTANT: return the generator, don't yield from it
            # Using yield from would make lambda_handler itself a generator,
            # which breaks non-streaming invocations
            return auth_error_stream()
        else:
            return error_response(401, "Unauthorized - valid JWT token required")

    # Extract user_id from JWT claims
    user_id = user_claims.get('user_id', user_claims.get('sub', 'anonymous'))

    # Lambda Function URL (direct call) - use streaming
    # BUT if called via API Gateway HTTP_PROXY, use non-streaming even if 'http' is present
    if is_function_url and not is_api_gateway:
        logger.info("Streaming follow-up response (direct Function URL)")
        # IMPORTANT: return the generator, don't yield from it
        # Lambda's RESPONSE_STREAM mode handles returned generators correctly
        return stream_followup_response(event, context, user_id=user_id)

    # API Gateway REST API (via HTTP_PROXY) or standard Lambda invocation - non-streaming response
    logger.info("Non-streaming follow-up response (API Gateway or standard invocation)")
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

        # =====================================================
        # TOKEN LIMIT CHECK - Pre-request validation
        # =====================================================
        limit_check = token_tracker.check_limit(user_id)
        if not limit_check.get('allowed', True):
            logger.warning(f"Token limit exceeded for user {user_id}: {limit_check}")
            return {
                'statusCode': 429,
                'headers': {
                    'Content-Type': 'application/json',
                    # Note: CORS headers handled by Lambda Function URL CORS config
                    'X-RateLimit-Limit': str(limit_check.get('token_limit', 0)),
                    'X-RateLimit-Remaining': '0',
                    'X-RateLimit-Reset': limit_check.get('reset_date', '')
                },
                'body': json.dumps({
                    'success': False,
                    **create_token_limit_error_response(limit_check),
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                })
            }

        # Save user question to DynamoDB
        user_message_id = save_followup_message(
            session_id=session_id,
            message_type='user',
            content=question,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # =====================================================
        # USE CONVERSE API with TOOL USE ORCHESTRATION (non-streaming)
        # =====================================================

        # Enhanced system prompt - layman-friendly financial analyst for millennials/gen-z
        system_prompt = f"""You're a financial analyst who explains investing like talking to a friend. Your reader is 25-35, may have student loans, and wants to build wealth but doesn't speak Wall Street.

ZERO JARGON POLICY - Always translate finance-speak:
- Free Cash Flow → "money left over after paying all the bills"
- FCF Margin → "what they keep from each dollar as real cash"
- Operating Cash Flow → "cash that actually came in"
- Debt-to-Equity → "how much they borrowed vs what they own"
- Interest Coverage → "can they pay their loans? They make Xx their loan payments"
- Net Debt → "what they still owe after using their savings"
- Net Cash → "extra savings after paying all debt"
- Gross Margin → "keeps X cents from every dollar of sales"
- Net Margin → "takes home X cents per dollar"
- P/E Ratio → "years of profits to pay back your investment"
- ROE → "how much profit they make from shareholder money"
- Dilution → "your slice of the pie is shrinking"

TONE:
- Casual and conversational — like texting a smart friend
- Use analogies: "It's like having a $50K mortgage while keeping $80K in savings"
- Make numbers tangible: "$99B is enough to buy every NFL team... twice"
- Be direct: "Here's the deal..." or "Bottom line:"

TOOL USAGE:
- For SPECIFIC {ticker} numbers/metrics → MUST use tools (never guess)
- For general finance concepts → just explain it
- For trends/comparisons → use getMetricsHistory

AVAILABLE TOOLS:
1. getReportSection(ticker, section_id) - Get report sections:
   07_profit (margins), 06_growth, 08_valuation, 10_cashflow, 11_debt,
   13_bull (bull case), 14_bear (risks), 15_warnings, 01_executive_summary

2. getReportRatings(ticker) - Investment ratings and verdict

3. getMetricsHistory(ticker, metric_type, quarters) - Historical metrics:
   metric_types: revenue_profit, cashflow, balance_sheet, debt_leverage, all
   quarters: 8 (recent) to 20 (long-term)

4. getAvailableReports() - List available company reports

Keep it real, keep it short, make them feel smarter when they're done reading.

Current context: {ticker} | {agent_type} analysis"""

        # Track tokens across all turns
        total_input_tokens = 0
        total_output_tokens = 0
        full_response = ""
        max_turns = 10
        turn_count = 0

        messages = [{"role": "user", "content": [{"text": question}]}]

        logger.info(f"[NON-STREAMING] Starting orchestration: session={session_id}, ticker={ticker}, question={question[:80]}...")

        # =====================================================
        # ORCHESTRATION LOOP - Handle tool calls
        # =====================================================
        while turn_count < max_turns:
            turn_count += 1
            logger.info(f"[NON-STREAMING] Turn {turn_count}/{max_turns}, messages count={len(messages)}")

            response = bedrock_runtime_client.converse(
                modelId=FOLLOWUP_MODEL_ID,
                messages=messages,
                system=[{"text": system_prompt}],
                toolConfig=FOLLOWUP_TOOLS,
                inferenceConfig={"maxTokens": 2048, "temperature": 0.7}
            )

            # Extract token usage
            usage = response.get('usage', {})
            total_input_tokens += usage.get('inputTokens', 0)
            total_output_tokens += usage.get('outputTokens', 0)
            logger.info(f"Turn {turn_count} tokens: input={usage.get('inputTokens', 0)}, output={usage.get('outputTokens', 0)}")

            # Get output message
            output_message = response.get('output', {}).get('message', {})
            stop_reason = response.get('stopReason', '')

            # Process content blocks
            assistant_content = output_message.get('content', [])
            logger.info(f"[NON-STREAMING] Turn {turn_count} stop_reason={stop_reason}, content_blocks={len(assistant_content)}")

            for block in assistant_content:
                if 'text' in block:
                    full_response += block['text']

            if stop_reason == 'tool_use':
                # Model wants to use tools - execute them and continue
                tool_names = [b['toolUse']['name'] for b in assistant_content if 'toolUse' in b]
                logger.info(f"[NON-STREAMING] Tool use requested: {tool_names}")

                # Add assistant message
                messages.append({"role": "assistant", "content": assistant_content})

                # Execute tools
                tool_results = []
                for block in assistant_content:
                    if 'toolUse' in block:
                        tool_use = block['toolUse']
                        tool_input = tool_use.get('input', {})
                        logger.info(f"[NON-STREAMING] Executing tool: {tool_use['name']} with input: {json.dumps(tool_input)}")

                        result = execute_tool(tool_use['name'], tool_input)

                        # Log result summary
                        result_success = result.get('success', False)
                        result_error = result.get('error', None)
                        logger.info(f"[NON-STREAMING] Tool result: success={result_success}, error={result_error}")

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use['toolUseId'],
                                "content": [{"text": json.dumps(result, cls=DecimalEncoder)}]
                            }
                        })

                messages.append({"role": "user", "content": tool_results})
                logger.info(f"[NON-STREAMING] Added {len(tool_results)} tool results, continuing...")
                continue

            elif stop_reason == 'end_turn':
                # Model finished responding - exit loop
                logger.info(f"[NON-STREAMING] End turn after {turn_count} turns, response_length={len(full_response)}")
                break

            else:
                # Unexpected stop reason (could be max_tokens, content_filtered, etc.)
                logger.warning(f"[NON-STREAMING] Unexpected stop reason: {stop_reason}, ending loop")
                break

        logger.info(f"[NON-STREAMING] Complete: input_tokens={total_input_tokens}, output_tokens={total_output_tokens}, turns={turn_count}")

        # Fall back to estimation if no token counts
        if total_input_tokens == 0 and total_output_tokens == 0:
            logger.warning("No token counts in converse response, using estimation")
            total_input_tokens = estimate_tokens(question)
            total_output_tokens = estimate_tokens(full_response)

        # Save assistant response to DynamoDB
        assistant_message_id = save_followup_message(
            session_id=session_id,
            message_type='assistant',
            content=full_response,
            user_id=user_id,
            agent_type=agent_type,
            ticker=ticker
        )

        # =====================================================
        # TOKEN USAGE RECORDING - Post-request (accumulated across turns)
        # =====================================================
        usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
        logger.info(f"Token usage recorded for {user_id}: input={total_input_tokens}, output={total_output_tokens}, "
                    f"total={usage_result.get('total_tokens')}, percent={usage_result.get('percent_used')}%")

        threshold = usage_result.get('threshold_reached')
        if threshold:
            logger.info(f"User {user_id} reached {threshold} token threshold")

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                # Note: CORS headers handled by Lambda Function URL CORS config
                'X-RateLimit-Limit': str(usage_result.get('token_limit', 0)),
                'X-RateLimit-Remaining': str(usage_result.get('remaining_tokens', 0)),
                'X-RateLimit-Reset': token_tracker.get_reset_date()
            },
            'body': json.dumps({
                'success': True,
                'response': full_response,
                'session_id': session_id,
                'agent_type': agent_type,
                'user_message_id': user_message_id,
                'assistant_message_id': assistant_message_id,
                'turns': turn_count,
                'token_usage': {
                    'input_tokens': total_input_tokens,
                    'output_tokens': total_output_tokens,
                    'total_tokens': usage_result.get('total_tokens'),
                    'token_limit': usage_result.get('token_limit'),
                    'percent_used': usage_result.get('percent_used'),
                    'remaining_tokens': usage_result.get('remaining_tokens'),
                    'threshold_reached': threshold
                },
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
            'Content-Type': 'application/json'
            # Note: CORS headers handled by Lambda Function URL CORS config
        },
        'body': json.dumps({
            'success': False,
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }
