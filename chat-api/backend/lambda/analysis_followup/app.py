"""
Analysis Follow-Up — FastAPI + Lambda Web Adapter (Docker)

Wraps the analysis_followup streaming logic in a FastAPI app served by uvicorn.
Lambda Web Adapter (LWA) proxies Lambda Function URL requests to this HTTP server,
enabling RESPONSE_STREAM for SSE in Python.

SSE events emitted:
  - followup_start: initial message with message_id
  - followup_chunk: streamed text tokens
  - followup_end: completion with token usage
  - error: validation or runtime errors
"""

import json
import boto3
import os
import logging
import jwt
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from sse_starlette.sse import EventSourceResponse

from utils.token_usage_tracker import TokenUsageTracker
from utils.tool_executor import execute_tool, DecimalEncoder

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

# ---------------------------------------------------------------------------
# AWS Clients (module-level, reused across requests)
# ---------------------------------------------------------------------------
secrets_client = boto3.client('secretsmanager')
bedrock_runtime_client = boto3.client(
    'bedrock-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)
dynamodb = boto3.resource('dynamodb')

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')

messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE) if CHAT_MESSAGES_TABLE else None
token_tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE) if TOKEN_USAGE_TABLE else TokenUsageTracker()

# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            secret = response['SecretString']
            if len(secret) < 32:
                raise ValueError("JWT secret too short (min 32 chars)")
            return secret
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret: {e}")
            raise
    jwt_secret = os.environ.get('JWT_SECRET')
    if jwt_secret:
        return jwt_secret
    raise ValueError("JWT_SECRET not configured")


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        secret = get_jwt_secret()
        return jwt.decode(token, secret, algorithms=['HS256'], options={'verify_exp': True})
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None


# ---------------------------------------------------------------------------
# JWT Middleware
# ---------------------------------------------------------------------------
PUBLIC_PATHS = {'/health'}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return JSONResponse(status_code=401, content={'error': 'Missing or invalid Authorization header'})

        token = auth_header[7:]
        claims = verify_jwt_token(token)
        if not claims:
            return JSONResponse(status_code=401, content={'error': 'Invalid or expired JWT token'})

        request.state.user_id = claims.get('user_id', claims.get('sub', 'anonymous'))
        request.state.user_claims = claims
        return await call_next(request)


# ---------------------------------------------------------------------------
# Tool Configuration (6 tools)
# ---------------------------------------------------------------------------
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
                                    "06_growth", "07_profit", "08_valuation",
                                    "09_earnings", "10_cashflow", "11_debt",
                                    "12_dilution", "13_bull", "14_bear",
                                    "15_warnings", "16_vibe", "17_realtalk"
                                ],
                                "description": "Section identifier"
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
                "description": "Gets the investment ratings, confidence scores, and overall verdict for a company.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "description": "Stock ticker symbol in uppercase"}
                        },
                        "required": ["ticker"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getMetricsHistory",
                "description": "Retrieves historical financial metrics for trend analysis.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "description": "Stock ticker symbol in uppercase"},
                            "metric_type": {
                                "type": "string",
                                "enum": ["all", "revenue_profit", "cashflow", "balance_sheet",
                                         "debt_leverage", "earnings_quality", "dilution", "valuation"],
                                "default": "all"
                            },
                            "quarters": {
                                "type": "integer",
                                "description": "Number of quarters (1-40)",
                                "default": 8, "minimum": 1, "maximum": 40
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
                "description": "Lists all companies with available investment reports.",
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
                "name": "compareStocks",
                "description": "Compares 2-5 stocks side-by-side across ratings and financial metrics. Use for 'AAPL vs MSFT' style questions.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "tickers": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 2, "maxItems": 5,
                                "description": "List of 2-5 stock ticker symbols"
                            },
                            "metric_type": {
                                "type": "string",
                                "enum": ["all", "revenue_profit", "cashflow", "balance_sheet",
                                         "debt_leverage", "earnings_quality", "dilution", "valuation"],
                                "default": "all"
                            },
                            "quarters": {
                                "type": "integer", "default": 4,
                                "minimum": 1, "maximum": 20
                            }
                        },
                        "required": ["tickers"]
                    }
                }
            }
        },
        {
            "toolSpec": {
                "name": "getFinancialSnapshot",
                "description": "Gets a quick financial snapshot combining latest quarter metrics and investment ratings in one call. Use this as a first step when evaluating a stock.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {
                            "ticker": {"type": "string", "description": "Stock ticker symbol in uppercase"}
                        },
                        "required": ["ticker"]
                    }
                }
            }
        }
    ]
}


# ---------------------------------------------------------------------------
# DynamoDB helpers
# ---------------------------------------------------------------------------
def convert_floats_to_decimals(item):
    if isinstance(item, dict):
        return {k: convert_floats_to_decimals(v) for k, v in item.items()}
    elif isinstance(item, list):
        return [convert_floats_to_decimals(v) for v in item]
    elif isinstance(item, float):
        return Decimal(str(item))
    return item


def save_followup_message(
    session_id: str, message_type: str, content: str,
    user_id: str, agent_type: str, ticker: str = ''
) -> Optional[str]:
    if not messages_table:
        logger.warning("Messages table not configured, skipping persistence")
        return None
    try:
        timestamp_unix = int(datetime.now(timezone.utc).timestamp() * 1000)
        timestamp_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        message_id = str(uuid.uuid4())

        messages_table.put_item(Item=convert_floats_to_decimals({
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
        }))
        logger.info(f"Saved {message_type} message {message_id} for session {session_id}")
        return message_id
    except Exception as e:
        logger.error(f"Failed to save {message_type} message: {e}", exc_info=True)
        return None


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 3.5))


def create_token_limit_error_response(limit_check: Dict[str, Any]) -> Dict[str, Any]:
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


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------
def build_system_prompt(ticker: str, agent_type: str) -> str:
    return f"""You're a financial advisor who explains investing like talking to a friend. Inspired by Warren Buffett's value investing principles, you help users make data-backed investment decisions. Your reader is 25-35, may have student loans, and wants to build wealth but doesn't speak Wall Street.

## YOUR ROLE
You don't just explain reports — you help users decide whether to buy, hold, or avoid stocks by analyzing real data from the tools. You give clear, opinionated recommendations backed by numbers.

## ZERO JARGON POLICY - Always translate finance-speak:
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
- ROIC → "how well they invest every dollar back into the business"
- Dilution → "your slice of the pie is shrinking"

## TONE
- Casual and conversational — like texting a smart friend who happens to know finance
- Use analogies: "It's like having a $50K mortgage while keeping $80K in savings"
- Make numbers tangible: "$99B is enough to buy every NFL team... twice"
- Be direct: "Here's the deal..." or "Bottom line:"
- Be opinionated — users want your take, not a Wikipedia article

## DECISION FRAMEWORK
When a user asks "should I buy X?" or wants a stock evaluation:

1. SNAPSHOT FIRST → Use getFinancialSnapshot to get ratings + latest metrics in one call
2. TREND CHECK → Use getMetricsHistory to see if the business is improving or deteriorating
3. RISK SCAN → Use getReportSection for 14_bear (risks) and 15_warnings (red flags)
4. FORM A VIEW → Synthesize into a clear BUY / HOLD / AVOID recommendation

When a user asks to compare stocks ("AAPL vs MSFT", "which is better"):
1. Use compareStocks to get side-by-side data in one call
2. Highlight the key differences that matter most
3. Give a clear winner with reasoning

## TOOL USAGE
- For SPECIFIC {ticker} numbers/metrics → MUST use tools (never guess or hallucinate data)
- For general finance concepts → just explain it
- For quick single-stock assessment → use getFinancialSnapshot first
- For comparing 2-5 stocks → use compareStocks
- For deep dives on trends → use getMetricsHistory
- For specific report sections → use getReportSection

## AVAILABLE TOOLS
1. getFinancialSnapshot(ticker) - Quick snapshot: latest quarter metrics + ratings in one call.
   Use this FIRST for any stock evaluation. More efficient than separate calls.

2. compareStocks(tickers, metric_type, quarters) - Side-by-side comparison of 2-5 stocks.
   Use for "X vs Y" questions. Returns ratings + metrics for all tickers at once.

3. getReportSection(ticker, section_id) - Deep dive into specific report sections:
   01_executive_summary, 06_growth, 07_profit, 08_valuation, 09_earnings,
   10_cashflow, 11_debt, 12_dilution, 13_bull, 14_bear, 15_warnings,
   16_vibe, 17_realtalk

4. getReportRatings(ticker) - Investment ratings and overall verdict

5. getMetricsHistory(ticker, metric_type, quarters) - Historical trends:
   metric_types: revenue_profit, cashflow, balance_sheet, debt_leverage,
   earnings_quality, dilution, valuation, all
   quarters: 4 (recent) to 20 (long-term)

6. getAvailableReports() - List all companies with reports

## RESPONSE GUIDELINES
- Lead with your take, then back it up with data
- Keep responses 100-300 words unless a deep dive is requested
- End with a clear "Bottom line:" statement when giving investment analysis
- Always note: "This is based on historical data and report analysis — not personalized financial advice. Do your own research before investing."

Current context: {ticker} | {agent_type} analysis"""


# ---------------------------------------------------------------------------
# SSE streaming generator
# ---------------------------------------------------------------------------
async def generate_followup_stream(
    question: str,
    session_id: str,
    ticker: str,
    agent_type: str,
    user_id: str
):
    """
    Async generator that yields SSE events for sse-starlette.

    Events: followup_start, followup_chunk, followup_end, error
    """
    try:
        # Token limit check
        limit_check = token_tracker.check_limit(user_id)
        if not limit_check.get('allowed', True):
            logger.warning(f"Token limit exceeded for user {user_id}")
            yield {
                "event": "error",
                "data": json.dumps({
                    "type": "token_limit_exceeded",
                    **create_token_limit_error_response(limit_check),
                    "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
                })
            }
            return

        # Generate message ID and emit followup_start
        assistant_message_id = str(uuid.uuid4())
        yield {
            "event": "followup_start",
            "data": json.dumps({
                "message_id": assistant_message_id,
                "session_id": session_id,
                "ticker": ticker,
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            })
        }

        logger.info(f"Follow-up for session {session_id}: {question[:100]}...")

        # Build messages and system prompt
        messages = [{"role": "user", "content": [{"text": question}]}]
        system_prompt = build_system_prompt(ticker, agent_type)

        # Track tokens across turns
        total_input_tokens = 0
        total_output_tokens = 0
        full_response = ""
        max_turns = 10
        turn_count = 0

        # Orchestration loop
        while turn_count < max_turns:
            turn_count += 1
            logger.info(f"[STREAM] Turn {turn_count}/{max_turns} for session {session_id}")

            response = bedrock_runtime_client.converse_stream(
                modelId=FOLLOWUP_MODEL_ID,
                messages=messages,
                system=[{"text": system_prompt}],
                toolConfig=FOLLOWUP_TOOLS,
                inferenceConfig={"maxTokens": 2048, "temperature": 0.7}
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
                        yield {
                            "event": "followup_chunk",
                            "data": json.dumps({
                                "message_id": assistant_message_id,
                                "text": chunk_text
                            })
                        }

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

                # Metadata
                if 'metadata' in stream_event:
                    usage = stream_event['metadata'].get('usage', {})
                    total_input_tokens += usage.get('inputTokens', 0)
                    total_output_tokens += usage.get('outputTokens', 0)

                # Message stop
                if 'messageStop' in stream_event:
                    stop_reason = stream_event['messageStop'].get('stopReason')

            # Handle stop reason
            logger.info(f"[STREAM] Turn {turn_count} stop_reason={stop_reason}")

            if stop_reason == 'tool_use':
                tool_names = [b['toolUse']['name'] for b in assistant_content if 'toolUse' in b]
                logger.info(f"[STREAM] Tool use: {tool_names}")

                messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if 'toolUse' in block:
                        tool_use = block['toolUse']
                        result = execute_tool(tool_use['name'], tool_use.get('input', {}))
                        logger.info(f"[STREAM] Tool {tool_use['name']}: success={result.get('success')}")
                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use['toolUseId'],
                                "content": [{"text": json.dumps(result, cls=DecimalEncoder)}]
                            }
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            elif stop_reason == 'end_turn':
                logger.info(f"[STREAM] Done after {turn_count} turns, len={len(full_response)}")
                break
            else:
                logger.warning(f"[STREAM] Unexpected stop: {stop_reason}")
                break

        # Post-loop: save messages and record tokens
        user_message_id = save_followup_message(
            session_id=session_id, message_type='user',
            content=question, user_id=user_id,
            agent_type=agent_type, ticker=ticker
        )
        saved_assistant_id = save_followup_message(
            session_id=session_id, message_type='assistant',
            content=full_response, user_id=user_id,
            agent_type=agent_type, ticker=ticker
        )

        if total_input_tokens == 0 and total_output_tokens == 0:
            logger.warning("No token metadata, using estimation")
            total_input_tokens = estimate_tokens(question)
            total_output_tokens = estimate_tokens(full_response)

        usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
        logger.info(f"Tokens: in={total_input_tokens}, out={total_output_tokens}, turns={turn_count}")

        threshold = usage_result.get('threshold_reached')
        if threshold:
            logger.info(f"User {user_id} reached {threshold} token threshold")

        # Emit followup_end
        yield {
            "event": "followup_end",
            "data": json.dumps({
                "message_id": assistant_message_id,
                "session_id": session_id,
                "agent_type": agent_type,
                "user_message_id": user_message_id,
                "assistant_message_id": saved_assistant_id,
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
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            })
        }

    except Exception as e:
        logger.error(f"Follow-up error: {e}", exc_info=True)
        yield {
            "event": "error",
            "data": json.dumps({
                "type": "error",
                "message": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
            })
        }


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Analysis Follow-Up starting: env={ENVIRONMENT}, model={FOLLOWUP_MODEL_ID}")
    yield
    logger.info("Analysis Follow-Up shutting down")


app = FastAPI(title="Analysis Follow-Up API", version="1.0.0", lifespan=lifespan)
app.add_middleware(JWTAuthMiddleware)


@app.get("/health")
async def health():
    return {
        'status': 'healthy',
        'service': 'analysis-followup',
        'environment': ENVIRONMENT,
        'model_id': FOLLOWUP_MODEL_ID,
        'timestamp': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    }


@app.post("/")
async def followup(raw_request: Request):
    """Handle follow-up questions with SSE streaming."""
    raw_body = await raw_request.body()
    try:
        body = json.loads(raw_body.decode('utf-8'))
        if isinstance(body, str):
            body = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return JSONResponse(status_code=400, content={'error': f'Invalid request body: {e}'})

    question = (body.get('question') or '').strip()
    # Accept both session_id and conversation_id for compatibility
    session_id = body.get('session_id') or body.get('conversation_id')
    agent_type = body.get('agent_type', 'debt')
    ticker = (body.get('ticker') or '').strip().upper()

    if not question:
        return JSONResponse(status_code=400, content={'error': 'question is required'})
    if not session_id:
        return JSONResponse(status_code=400, content={'error': 'session_id or conversation_id is required'})

    user_id = getattr(raw_request.state, 'user_id', 'anonymous')

    return EventSourceResponse(
        generate_followup_stream(question, session_id, ticker, agent_type, user_id),
        media_type="text/event-stream"
    )
