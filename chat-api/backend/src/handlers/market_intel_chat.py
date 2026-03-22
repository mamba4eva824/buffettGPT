"""
Market Intelligence Chat Lambda Handler

Uses Bedrock Converse API (converse_stream) with inline tool definitions
to answer S&P 500 market analysis questions. Follows the same architecture
as analysis_followup.py.

Agent: market-intel-dev
Model: Claude 4.5 Haiku (us.anthropic.claude-haiku-4-5-20251001-v1:0)

Features:
- SSE streaming via Lambda Function URL (RESPONSE_STREAM)
- 9 inline tools for market analysis
- Token counting from Bedrock metadata
- JWT authentication
- Orchestration loop with max 10 turns

Invocation:
- Lambda Function URL (direct): SSE streaming response
- API Gateway HTTP_PROXY: Non-streaming JSON response
"""

import json
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
import jwt

from utils.market_intel_tools import execute_tool, DecimalEncoder
from utils.token_usage_tracker import TokenUsageTracker

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
JWT_SECRET = os.environ.get('JWT_SECRET', '')
USERS_TABLE = os.environ.get('USERS_TABLE') or f'buffett-{ENVIRONMENT}-users'

# DynamoDB for subscription check
dynamodb = boto3.resource('dynamodb')
users_table = dynamodb.Table(USERS_TABLE)

# Bedrock Runtime client (converse_stream API)
bedrock_runtime = boto3.client(
    'bedrock-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)

# Model ID — Claude 4.5 Haiku via US cross-region inference profile
MODEL_ID = os.environ.get(
    'MARKET_INTEL_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)

# Token tracking
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')
token_tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE) if TOKEN_USAGE_TABLE else TokenUsageTracker()


# =============================================================================
# SYSTEM PROMPT
# =============================================================================

SYSTEM_PROMPT = """You are a Market Intelligence Analyst for the S&P 500. You have access to comprehensive financial data for all ~500 S&P 500 companies, including 20 quarters (5 years) of quarterly metrics, sector-level aggregates, and earnings surprise data.

Your role:
- Answer questions about the S&P 500 market, sectors, and individual companies
- Provide data-driven insights backed by real financial metrics
- Compare companies and sectors using actual numbers
- Explain financial concepts in plain English when needed

IMPORTANT RULES:
1. ALWAYS use your tools to retrieve data before answering. NEVER make up financial numbers.
2. Cite specific data points (e.g., "AAPL's operating margin is 35.4%").
3. When showing rankings or comparisons, include the actual metric values.
4. If data is unavailable for a query, say so clearly.
5. Keep responses concise and focused on the data.

Available tools and when to use them:
- getIndexSnapshot: Start here for broad market questions ("How is the S&P 500?")
- getSectorOverview: For sector-specific questions ("How is tech doing?")
- compareSectors: When comparing 2+ sectors ("Tech vs healthcare margins")
- getTopCompanies: For rankings ("Top 10 by FCF margin")
- getCompanyProfile: For individual company deep dives ("Tell me about NVDA")
- compareCompanies: For head-to-head comparisons ("AAPL vs MSFT")
- screenStocks: For filtering by criteria ("Companies with >20% FCF margin in tech")
- getMetricTrend: For time series analysis ("How has AAPL's margin changed?")
- getEarningsSurprises: For earnings analysis ("Biggest earnings beats")

Available metrics for screening and ranking:
revenue, net_income, gross_margin, operating_margin, net_margin, revenue_growth_yoy, eps, roe,
fcf_margin, free_cash_flow, operating_cash_flow, capex_intensity, fcf_payout_ratio,
debt_to_equity, current_ratio, interest_coverage, net_debt_to_ebitda,
roic, roa, asset_turnover, sbc_to_revenue_pct, eps_surprise_pct, dividend_yield, dps

Sector names (use these exactly):
Technology, Healthcare, Financial Services, Consumer Cyclical, Consumer Defensive,
Communication Services, Industrials, Energy, Utilities, Real Estate, Basic Materials

Data freshness: Metrics are from the most recent available quarter per company. Aggregates are refreshed periodically."""


# =============================================================================
# TOOL CONFIGURATION — Converse API toolSpec format
# =============================================================================

MARKET_INTEL_TOOLS = {
    "tools": [
        {
            "toolSpec": {
                "name": "screenStocks",
                "description": "Filter S&P 500 companies by a metric threshold. Use for queries like 'companies with >20% FCF margin' or 'tech stocks with debt-to-equity under 1'.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "description": "Metric name: revenue, gross_margin, operating_margin, net_margin, fcf_margin, revenue_growth_yoy, eps, roe, debt_to_equity, current_ratio, roic, roa, dividend_yield, eps_surprise_pct, etc."
                            },
                            "operator": {
                                "type": "string",
                                "enum": [">", ">=", "<", "<=", "="],
                                "description": "Comparison operator"
                            },
                            "value": {
                                "type": "number",
                                "description": "Threshold value. Margins are in percentage points (e.g., 20 for 20%), ratios are raw (e.g., 1.5 for 1.5x D/E)"
                            },
                            "sector": {
                                "type": "string",
                                "description": "Optional: filter to a specific sector (e.g., 'Technology', 'Healthcare')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results to return (default 20, max 50)"
                            }
                        },
                        "required": ["metric", "operator", "value"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getSectorOverview",
                "description": "Get sector-level aggregate data including median metrics, top companies, earnings summary, and dividend coverage. Omit 'sector' to get all 11 sectors.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "sector": {
                                "type": "string",
                                "description": "Sector name (e.g., 'Technology', 'Healthcare'). Omit for all sectors."
                            }
                        },
                        "required": []
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getTopCompanies",
                "description": "Rank S&P 500 companies by any metric. Returns top N companies sorted by the metric.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "metric": {
                                "type": "string",
                                "description": "Metric to rank by: revenue, gross_margin, operating_margin, net_margin, fcf_margin, revenue_growth_yoy, roe, roic, dividend_yield, eps_surprise_pct, etc."
                            },
                            "n": {
                                "type": "integer",
                                "description": "Number of companies to return (default 10, max 50)"
                            },
                            "sector": {
                                "type": "string",
                                "description": "Optional: filter to a specific sector"
                            }
                        },
                        "required": ["metric"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getIndexSnapshot",
                "description": "Get overall S&P 500 index health metrics: median margins, sector weights, top-10 concentration, earnings beat rate, dividend coverage.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getCompanyProfile",
                "description": "Get detailed metrics for a single company including all financial categories, sector context, and how it compares to sector medians.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol (e.g., AAPL, MSFT, NVDA)"
                            }
                        },
                        "required": ["ticker"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "compareCompanies",
                "description": "Compare 2-10 companies side by side with financial metrics. Use for 'AAPL vs MSFT' style questions.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of 2-10 ticker symbols to compare"
                            },
                            "metric_type": {
                                "type": "string",
                                "enum": ["all", "revenue_profit", "cashflow", "balance_sheet", "debt_leverage", "earnings_quality", "dilution", "valuation"],
                                "description": "Category of metrics to compare (default: all)"
                            }
                        },
                        "required": ["tickers"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getMetricTrend",
                "description": "Get the quarterly trajectory of a specific metric for one company over time. Returns up to 20 quarters (5 years) of data.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {
                                "type": "string",
                                "description": "Stock ticker symbol"
                            },
                            "metric": {
                                "type": "string",
                                "description": "Metric name: operating_margin, fcf_margin, revenue_growth_yoy, debt_to_equity, roe, roic, etc."
                            },
                            "category": {
                                "type": "string",
                                "description": "Optional: metric category if metric name is ambiguous (e.g., 'revenue_profit', 'cashflow')"
                            },
                            "quarters": {
                                "type": "integer",
                                "description": "Number of quarters to return (default 20, max 20)"
                            }
                        },
                        "required": ["ticker", "metric"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getEarningsSurprises",
                "description": "Get companies ranked by earnings surprise — biggest EPS beats or worst misses. Based on actual vs estimated EPS.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "sort": {
                                "type": "string",
                                "enum": ["best", "worst"],
                                "description": "'best' for biggest beats, 'worst' for biggest misses (default: best)"
                            },
                            "n": {
                                "type": "integer",
                                "description": "Number of results (default 10, max 50)"
                            },
                            "sector": {
                                "type": "string",
                                "description": "Optional: filter to a specific sector"
                            }
                        },
                        "required": []
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "compareSectors",
                "description": "Compare 2-5 sectors side by side with median metrics, earnings summaries, and dividend coverage.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "sectors": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of 2-5 sector names to compare"
                            },
                            "metrics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Optional: specific metrics to compare (e.g., ['operating_margin', 'fcf_margin']). Omit for all."
                            }
                        },
                        "required": ["sectors"]
                    }
                }
            }
        }
    ]
}


# =============================================================================
# SSE HELPERS
# =============================================================================

def format_sse_event(data: str, event_type: str = "message") -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {data}\n\n"


def error_response(status_code: int, message: str) -> Dict:
    """Standard error response for API Gateway."""
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'error': message})
    }


def _get_subscription_tier(user_id: str) -> str:
    """Check user's subscription tier from DynamoDB users table.

    This is the authoritative source for subscription status.
    The JWT may contain a stale tier from login time.

    Returns: 'free', 'plus', or 'premium'
    """
    try:
        resp = users_table.get_item(
            Key={'user_id': user_id},
            ProjectionExpression='subscription_tier'
        )
        item = resp.get('Item', {})
        return item.get('subscription_tier', 'free')
    except Exception as e:
        logger.error(f"Failed to check subscription for {user_id}: {e}")
        # Fail open for DynamoDB errors — don't block users due to infra issues
        # The token tracker will still enforce limits
        return 'free'


def verify_jwt_token(event: Dict) -> Optional[Dict]:
    """Extract and verify JWT token from Authorization header."""
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization', headers.get('Authorization', ''))

    if not auth_header.startswith('Bearer '):
        return None

    token = auth_header[7:]
    if not JWT_SECRET:
        logger.warning("JWT_SECRET not configured")
        return None

    try:
        claims = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return claims
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT: {e}")
        return None


# =============================================================================
# STREAMING RESPONSE — converse_stream orchestration loop
# =============================================================================

def stream_market_intel_response(event: Dict, context: Any, user_id: str = 'anonymous'):
    """
    Stream market intelligence response via SSE.

    Orchestration loop:
    1. Call converse_stream with 9 tools
    2. Stream text chunks to client immediately
    3. If tool_use: execute tool, append results, continue
    4. On end_turn: emit complete event with token usage
    """
    try:
        # Response headers (first yield)
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
        if isinstance(body_str, str):
            body = json.loads(body_str)
        else:
            body = body_str

        message = body.get('message', '')
        session_id = body.get('session_id', f'market-intel-{datetime.now().strftime("%Y%m%d%H%M%S")}')
        conversation_history = body.get('messages', [])

        if not message:
            yield format_sse_event(json.dumps({
                "type": "error", "message": "No message provided"
            }), "error")
            return

        logger.info(f"[MARKET_INTEL] Query: {message[:80]}... | user={user_id} | session={session_id}")

        # Build messages array
        messages = list(conversation_history) if conversation_history else []
        messages.append({"role": "user", "content": [{"text": message}]})

        # Token tracking
        total_input_tokens = 0
        total_output_tokens = 0
        full_response = ""
        max_turns = 10
        turn_count = 0

        # =====================================================
        # ORCHESTRATION LOOP
        # =====================================================
        while turn_count < max_turns:
            turn_count += 1
            logger.info(f"[MARKET_INTEL] Turn {turn_count}/{max_turns}")

            response = bedrock_runtime.converse_stream(
                modelId=MODEL_ID,
                messages=messages,
                system=[{"text": SYSTEM_PROMPT}],
                toolConfig=MARKET_INTEL_TOOLS,
                inferenceConfig={
                    "maxTokens": 4096,
                    "temperature": 0.3
                }
            )

            assistant_content = []
            current_text_block = ""
            current_tool_use = None
            stop_reason = None

            for stream_event in response.get('stream', []):

                # Content block start
                if 'contentBlockStart' in stream_event:
                    start = stream_event['contentBlockStart'].get('start', {})
                    if 'toolUse' in start:
                        current_tool_use = {
                            'toolUseId': start['toolUse']['toolUseId'],
                            'name': start['toolUse']['name'],
                            'input': ''
                        }

                # Content block delta
                if 'contentBlockDelta' in stream_event:
                    delta = stream_event['contentBlockDelta'].get('delta', {})

                    if 'text' in delta:
                        chunk_text = delta['text']
                        current_text_block += chunk_text
                        full_response += chunk_text
                        yield format_sse_event(json.dumps({
                            "type": "chunk",
                            "text": chunk_text,
                            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                        }), "chunk")

                    if 'toolUse' in delta:
                        if current_tool_use and 'input' in delta['toolUse']:
                            current_tool_use['input'] += delta['toolUse']['input']

                # Content block stop
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

                # Metadata — token counts
                if 'metadata' in stream_event:
                    usage = stream_event['metadata'].get('usage', {})
                    total_input_tokens += usage.get('inputTokens', 0)
                    total_output_tokens += usage.get('outputTokens', 0)
                    logger.info(f"Turn {turn_count} tokens: in={usage.get('inputTokens', 0)} out={usage.get('outputTokens', 0)}")

                # Message stop
                if 'messageStop' in stream_event:
                    stop_reason = stream_event['messageStop'].get('stopReason')

            # =====================================================
            # HANDLE STOP REASON
            # =====================================================
            logger.info(f"[MARKET_INTEL] Turn {turn_count} stop={stop_reason} blocks={len(assistant_content)}")

            if stop_reason == 'tool_use':
                tool_names = [b['toolUse']['name'] for b in assistant_content if 'toolUse' in b]
                logger.info(f"[MARKET_INTEL] Tool calls: {tool_names}")

                messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if 'toolUse' in block:
                        tool_use = block['toolUse']
                        logger.info(f"[MARKET_INTEL] Executing: {tool_use['name']}")

                        result = execute_tool(tool_use['name'], tool_use.get('input', {}))

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use['toolUseId'],
                                "content": [{"text": json.dumps(result, cls=DecimalEncoder)}]
                            }
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            elif stop_reason == 'end_turn':
                logger.info(f"[MARKET_INTEL] Complete after {turn_count} turns, {len(full_response)} chars")
                break
            else:
                logger.warning(f"[MARKET_INTEL] Unexpected stop: {stop_reason}")
                break

        # =====================================================
        # POST-LOOP: Record tokens + emit complete event
        # =====================================================
        if total_input_tokens == 0 and total_output_tokens == 0:
            total_input_tokens = max(1, int(len(message) / 3.5))
            total_output_tokens = max(1, int(len(full_response) / 3.5))

        usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
        logger.info(f"[MARKET_INTEL] Tokens: in={total_input_tokens} out={total_output_tokens} turns={turn_count}")

        yield format_sse_event(json.dumps({
            "type": "complete",
            "session_id": session_id,
            "agent_type": "market-intel",
            "turns": turn_count,
            "token_usage": {
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "total_tokens": usage_result.get('total_tokens'),
                "token_limit": usage_result.get('token_limit'),
                "percent_used": usage_result.get('percent_used'),
                "remaining_tokens": usage_result.get('remaining_tokens'),
                "threshold_reached": usage_result.get('threshold_reached'),
            },
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }), "complete")

    except Exception as e:
        logger.error(f"[MARKET_INTEL] Error: {e}", exc_info=True)
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }), "error")


# =============================================================================
# NON-STREAMING RESPONSE (for API Gateway / direct invocation)
# =============================================================================

def non_streaming_response(event: Dict, context: Any, user_id: str = 'anonymous') -> Dict:
    """Handle non-streaming request (API Gateway or test invocation)."""
    body_str = event.get('body', '{}')
    if isinstance(body_str, str):
        body = json.loads(body_str)
    else:
        body = body_str

    message = body.get('message', '')
    conversation_history = body.get('messages', [])

    if not message:
        return error_response(400, "No message provided")

    messages = list(conversation_history) if conversation_history else []
    messages.append({"role": "user", "content": [{"text": message}]})

    total_input_tokens = 0
    total_output_tokens = 0
    full_response = ""
    max_turns = 10
    turn_count = 0

    while turn_count < max_turns:
        turn_count += 1

        response = bedrock_runtime.converse(
            modelId=MODEL_ID,
            messages=messages,
            system=[{"text": SYSTEM_PROMPT}],
            toolConfig=MARKET_INTEL_TOOLS,
            inferenceConfig={
                "maxTokens": 4096,
                "temperature": 0.3
            }
        )

        output = response.get('output', {})
        assistant_message = output.get('message', {})
        stop_reason = response.get('stopReason', 'end_turn')

        usage = response.get('usage', {})
        total_input_tokens += usage.get('inputTokens', 0)
        total_output_tokens += usage.get('outputTokens', 0)

        if stop_reason == 'tool_use':
            messages.append(assistant_message)

            tool_results = []
            for block in assistant_message.get('content', []):
                if 'toolUse' in block:
                    tool_use = block['toolUse']
                    result = execute_tool(tool_use['name'], tool_use.get('input', {}))
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": tool_use['toolUseId'],
                            "content": [{"text": json.dumps(result, cls=DecimalEncoder)}]
                        }
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        elif stop_reason == 'end_turn':
            for block in assistant_message.get('content', []):
                if 'text' in block:
                    full_response += block['text']
            break
        else:
            break

    usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)

    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'response': full_response,
            'agent_type': 'market-intel',
            'turns': turn_count,
            'token_usage': {
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'total_tokens': usage_result.get('total_tokens'),
            }
        })
    }


# =============================================================================
# LAMBDA HANDLER
# =============================================================================

def lambda_handler(event: Dict[str, Any], context: Any):
    """
    Handle market intelligence chat requests.

    Request format:
    {
        "message": "What sectors have the best margins?",
        "session_id": "optional-session-id",
        "messages": []  // Optional conversation history
    }

    Authentication: JWT token required in Authorization header.
    """
    request_context = event.get('requestContext', {})
    headers = event.get('headers', {}) or {}

    # Detect invocation source
    is_function_url = 'http' in request_context
    is_api_gateway = (
        event.get('httpMethod') or
        request_context.get('httpMethod') or
        headers.get('x-amzn-apigateway-api-id') or
        headers.get('X-Amzn-Apigateway-Api-Id')
    )

    # Health check
    http_context = request_context.get('http', {})
    path = http_context.get('path', event.get('path', ''))
    method = http_context.get('method', event.get('httpMethod', 'POST'))

    if path == '/health' and method == 'GET':
        health = {
            'status': 'healthy',
            'service': 'market-intel',
            'model_id': MODEL_ID,
            'environment': ENVIRONMENT,
            'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        }
        if is_function_url and not is_api_gateway:
            return health
        return {'statusCode': 200, 'headers': {'Content-Type': 'application/json'}, 'body': json.dumps(health)}

    # JWT Authentication
    user_claims = verify_jwt_token(event)
    if not user_claims:
        logger.warning("Unauthorized request")
        return error_response(401, "Unauthorized - valid JWT token required")

    user_id = user_claims.get('user_id', user_claims.get('sub', 'anonymous'))

    # Plus subscription check — query DynamoDB for authoritative tier
    # (JWT subscription_tier may be stale if user upgraded after login)
    subscription_tier = _get_subscription_tier(user_id)
    if subscription_tier not in ('plus', 'premium'):
        logger.warning(f"[MARKET_INTEL] User {user_id} denied — tier={subscription_tier}")
        return error_response(403, "Plus subscription required for Market Intelligence")

    # Route to streaming or non-streaming
    if is_function_url and not is_api_gateway:
        logger.info(f"[MARKET_INTEL] Streaming response for user {user_id}")
        return stream_market_intel_response(event, context, user_id=user_id)

    logger.info(f"[MARKET_INTEL] Non-streaming response for user {user_id}")
    return non_streaming_response(event, context, user_id=user_id)
