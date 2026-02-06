"""
Follow-up Question Service for Investment Research

Provides context retrieval and integration with Bedrock agents for
answering follow-up questions about investment reports.

Uses only the ~60 metrics that appear in investment research reports
(not the full 80+ features from the feature extractor).
"""

import os
import json
import uuid
import boto3
import logging
from decimal import Decimal
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

# DynamoDB table names
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
FINANCIAL_CACHE_TABLE = os.environ.get('FINANCIAL_DATA_CACHE_TABLE', 'financial-data-cache-dev')

# Bedrock configuration
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
FOLLOWUP_AGENT_ID = os.environ.get('FOLLOWUP_AGENT_ID', '')
FOLLOWUP_AGENT_ALIAS = os.environ.get('FOLLOWUP_AGENT_ALIAS', 'TSTALIASID')

# Claude Haiku 4.5 model for follow-up chat (inference profile for cross-region)
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)

# Initialize clients
dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=BEDROCK_REGION)

# Token usage tracking
from services.token_usage_tracker import TokenUsageTracker
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')
token_tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE) if TOKEN_USAGE_TABLE else TokenUsageTracker()

# Message persistence
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE) if CHAT_MESSAGES_TABLE else None


def save_followup_message(
    session_id: str,
    message_type: str,
    content: str,
    user_id: str,
    ticker: str = ''
) -> Optional[str]:
    """Save a follow-up message to DynamoDB for conversation history."""
    if not messages_table:
        logger.warning("Messages table not configured, skipping persistence")
        return None

    try:
        from datetime import timezone
        timestamp_unix = int(datetime.now(timezone.utc).timestamp() * 1000)
        timestamp_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
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
                'agent_type': 'followup',
                'ticker': ticker
            }
        }

        messages_table.put_item(Item=message_record)
        logger.info(f"Saved {message_type} message {message_id} for session {session_id}")
        return message_id

    except Exception as e:
        logger.error(f"Failed to save {message_type} message: {e}", exc_info=True)
        return None


# =============================================================================
# Investment Research Metrics Definition
# These are the specific metrics used in investment research reports
# =============================================================================

INVESTMENT_RESEARCH_METRICS = {
    'revenue_profit': {
        'description': 'Revenue & Profitability Metrics',
        'metrics': [
            'revenue',
            'netIncome',
            'grossProfit',
            'operatingIncome',
            'eps',
            'gross_margin',
            'operating_margin',
            'net_margin',
            'revenue_growth_yoy',
        ]
    },
    'cashflow': {
        'description': 'Cash Flow Metrics',
        'metrics': [
            'operatingCashFlow',
            'freeCashFlow',
            'capitalExpenditure',
            'dividendsPaid',
            'commonStockRepurchased',
            'fcf_margin',
            'ocf_to_ni_ratio',
        ]
    },
    'balance_sheet': {
        'description': 'Balance Sheet Metrics',
        'metrics': [
            'totalDebt',
            'cashAndCashEquivalents',
            'shortTermInvestments',
            'totalLiquidity',  # cash + short-term investments
            'netDebt',
            'totalStockholdersEquity',
            'totalAssets',
            'totalCurrentAssets',
            'totalCurrentLiabilities',
        ]
    },
    'debt_leverage': {
        'description': 'Debt & Leverage Ratios',
        'metrics': [
            'debt_to_equity',
            'debt_to_assets',
            'interest_coverage',
            'current_ratio',
            'quick_ratio',
            'short_term_debt',
            'long_term_debt',
            'st_debt_pct',  # Short-term debt as % of total
        ]
    },
    'earnings_quality': {
        'description': 'Earnings Quality Metrics',
        'metrics': [
            'gaap_net_income',
            'stock_based_compensation',
            'depreciation_amortization',
            'adjusted_earnings',
            'sbc_to_revenue_pct',
        ]
    },
    'dilution': {
        'description': 'Shareholder Dilution Metrics',
        'metrics': [
            'basic_shares_outstanding',
            'diluted_shares_outstanding',
            'dilution_pct',
            'share_repurchases',
        ]
    },
    'valuation': {
        'description': 'Valuation Metrics (from Key Metrics TTM)',
        'metrics': [
            'pe_ratio',
            'pb_ratio',
            'ev_to_ebitda',
            'price_to_fcf',
            'peg_ratio',
            'dividend_yield',
            'roe',
            'roic',
        ]
    }
}

# Flatten all metrics for quick lookup
ALL_INVESTMENT_METRICS = []
for category in INVESTMENT_RESEARCH_METRICS.values():
    ALL_INVESTMENT_METRICS.extend(category['metrics'])


# =============================================================================
# Report Context Retrieval (Action Group Functions)
# =============================================================================

def get_report_section(ticker: str, section_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific section from an investment report.

    Action group function for the follow-up agent.

    Args:
        ticker: Stock ticker symbol
        section_id: Section ID (e.g., '01_executive_summary', '06_growth')

    Returns:
        Dict with section content and metadata
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)
    ticker = ticker.upper()

    # Handle merged Executive Summary specially
    if section_id == '01_executive_summary':
        response = table.get_item(Key={'ticker': ticker, 'section_id': '00_executive'})
        item = response.get('Item')
        if item:
            return {
                'success': True,
                'ticker': ticker,
                'section_id': section_id,
                'title': 'Executive Summary',
                'content': item.get('executive_summary', {}).get('content', ''),
                'part': 1,
                'word_count': item.get('executive_summary', {}).get('word_count', 0)
            }
    else:
        response = table.get_item(Key={'ticker': ticker, 'section_id': section_id})
        item = response.get('Item')
        if item:
            return {
                'success': True,
                'ticker': ticker,
                'section_id': section_id,
                'title': item.get('title', ''),
                'content': item.get('content', ''),
                'part': item.get('part', 0),
                'word_count': item.get('word_count', 0)
            }

    return {
        'success': False,
        'error': f'Section {section_id} not found for {ticker}'
    }


def get_report_ratings(ticker: str) -> Dict[str, Any]:
    """
    Retrieve investment ratings for a ticker.

    Action group function for the follow-up agent.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with all ratings (debt, cashflow, growth, overall verdict)
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)
    ticker = ticker.upper()

    response = table.get_item(Key={'ticker': ticker, 'section_id': '00_executive'})
    item = response.get('Item')

    if item and item.get('ratings'):
        ratings = item['ratings']
        # Handle both JSON string and dict formats
        if isinstance(ratings, str):
            ratings = json.loads(ratings)
        return {
            'success': True,
            'ticker': ticker,
            'ratings': ratings,
            'generated_at': item.get('generated_at')
        }

    return {
        'success': False,
        'error': f'No ratings found for {ticker}'
    }


def get_metrics_history(
    ticker: str,
    metric_type: str = 'all',
    quarters: int = 20
) -> Dict[str, Any]:
    """
    Retrieve historical metrics for follow-up questions.

    Returns only the ~60 metrics used in investment research reports,
    not the full 80+ features.

    Args:
        ticker: Stock ticker symbol
        metric_type: Category filter ('revenue_profit', 'cashflow', 'debt_leverage',
                    'earnings_quality', 'dilution', 'valuation', or 'all')
        quarters: Number of quarters of history (default 20 = 5 years)

    Returns:
        Dict with historical metric data
    """
    # This would typically fetch from DynamoDB cache or FMP API
    # For now, return structure showing what metrics are available

    if metric_type == 'all':
        metrics_to_return = INVESTMENT_RESEARCH_METRICS
    elif metric_type in INVESTMENT_RESEARCH_METRICS:
        metrics_to_return = {metric_type: INVESTMENT_RESEARCH_METRICS[metric_type]}
    else:
        return {
            'success': False,
            'error': f'Unknown metric type: {metric_type}',
            'available_types': list(INVESTMENT_RESEARCH_METRICS.keys())
        }

    # TODO: Implement actual data retrieval from DynamoDB/FMP cache
    # For now, return metric definitions
    return {
        'success': True,
        'ticker': ticker.upper(),
        'metric_type': metric_type,
        'quarters_requested': quarters,
        'available_metrics': metrics_to_return,
        'note': 'Historical data retrieval to be implemented'
    }


def get_available_reports() -> Dict[str, Any]:
    """
    List all available investment reports.

    Returns list of tickers with reports, useful for search dropdown.
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)

    # Query for all 00_executive items (one per ticker)
    response = table.scan(
        FilterExpression='section_id = :sid',
        ExpressionAttributeValues={':sid': '00_executive'},
        ProjectionExpression='ticker, company_name, generated_at'
    )

    reports = []
    for item in response.get('Items', []):
        reports.append({
            'ticker': item.get('ticker'),
            'company_name': item.get('company_name', item.get('ticker')),
            'generated_at': item.get('generated_at')
        })

    # Sort by ticker
    reports.sort(key=lambda x: x['ticker'])

    return {
        'success': True,
        'count': len(reports),
        'reports': reports
    }


def get_report_by_company_name(company_name: str) -> Optional[Dict[str, Any]]:
    """
    Get report metadata for a company by exact name using GSI.

    Uses the company-name-index GSI for efficient lookup without table scan.

    Args:
        company_name: Exact company name (e.g., 'Apple Inc.')

    Returns:
        Dict with ticker and company_name if found, None otherwise
    """
    from boto3.dynamodb.conditions import Key

    table = dynamodb.Table(REPORTS_TABLE_V2)

    try:
        response = table.query(
            IndexName='company-name-index',
            KeyConditionExpression=Key('company_name').eq(company_name) & Key('section_id').eq('00_executive'),
            ProjectionExpression='ticker, company_name'
        )

        items = response.get('Items', [])
        if items:
            item = items[0]
            return {
                'ticker': item.get('ticker'),
                'company_name': item.get('company_name')
            }
        return None

    except Exception as e:
        logger.error(f"Error querying by company name '{company_name}': {e}")
        return None


def search_reports_in_dynamodb(query: str, limit: int = 10) -> Dict[str, Any]:
    """
    Search for reports by company name or ticker in DynamoDB.

    Performs a case-insensitive search on both ticker and company_name fields
    by scanning executive items (00_executive) and filtering client-side.

    For large datasets, consider implementing ElasticSearch or DynamoDB Streams
    to a search index. This scan-based approach works well for < 1000 reports.

    Args:
        query: Search query (matches company name or ticker, case insensitive)
        limit: Maximum number of results to return (default 10)

    Returns:
        Dict with success status and list of matching ticker/name pairs
    """
    from boto3.dynamodb.conditions import Attr

    table = dynamodb.Table(REPORTS_TABLE_V2)
    query_lower = query.lower()

    try:
        # Scan for all executive items (one per ticker)
        # Filter for section_id = '00_executive' to get one item per report
        response = table.scan(
            FilterExpression=Attr('section_id').eq('00_executive'),
            ProjectionExpression='ticker, company_name'
        )

        items = response.get('Items', [])

        # Handle pagination for large datasets
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=Attr('section_id').eq('00_executive'),
                ProjectionExpression='ticker, company_name',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        # Client-side case-insensitive filtering
        results = []
        for item in items:
            ticker = item.get('ticker', '')
            company_name = item.get('company_name', ticker)  # Fallback to ticker

            # Check if query matches ticker or company name (case insensitive)
            if query_lower in ticker.lower() or query_lower in company_name.lower():
                results.append({
                    'ticker': ticker,
                    'name': company_name
                })

                if len(results) >= limit:
                    break

        # Sort results: exact ticker matches first, then by ticker alphabetically
        results.sort(key=lambda x: (
            0 if x['ticker'].lower() == query_lower else 1,
            x['ticker'].lower()
        ))

        return {
            'success': True,
            'count': len(results),
            'results': results[:limit]
        }

    except Exception as e:
        logger.error(f"Error searching reports for '{query}': {e}")
        return {
            'success': False,
            'error': str(e),
            'count': 0,
            'results': []
        }


# =============================================================================
# Bedrock Agent Integration
# =============================================================================

async def invoke_followup_agent(
    ticker: str,
    question: str,
    session_id: Optional[str] = None,
    section_id: Optional[str] = None,
    user_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Invoke the follow-up agent with streaming response.

    Uses Bedrock's converse_stream API for SSE-compatible streaming.

    Args:
        ticker: Stock ticker being discussed
        question: User's follow-up question
        session_id: Optional session ID for conversation continuity
        section_id: Optional section ID for additional context
        user_id: Optional user ID from JWT for token tracking and persistence

    Yields:
        SSE events with agent response chunks
    """
    # Generate session ID if not provided (for conversation memory)
    if not session_id:
        session_id = f"{ticker}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Get section context if provided
    section_context = None
    if section_id:
        section_data = get_report_section(ticker, section_id)
        if section_data.get('success'):
            section_context = section_data.get('content', '')

    # Build context-enhanced prompt for Bedrock Agent path
    context_prompt = f"""
The user is asking about investment report for {ticker}.

User question: {question}

Use your available tools to:
1. Retrieve relevant report sections if needed
2. Get ratings and metrics data
3. Provide a helpful, data-backed answer
"""

    try:
        # Always use converse_stream for true token-by-token streaming.
        # The invoke_agent path (Bedrock Agent API) buffers the full response
        # before returning, which defeats SSE streaming.
        async for event in _stream_claude_response(ticker, question, section_context, user_id, session_id):
            yield event

    except Exception as e:
        logger.error(f"Follow-up agent error: {e}", exc_info=True)
        yield {
            'event': 'error',
            'data': json.dumps({
                'error': str(e),
                'code': 'AGENT_ERROR'
            })
        }


async def _stream_agent_response(
    prompt: str,
    session_id: str,
    ticker: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream response from Bedrock Agent.

    Uses followup_* event types for frontend compatibility.
    """
    from services.streaming import (
        followup_start_event,
        followup_chunk_event,
        followup_end_event,
    )

    message_id = str(uuid.uuid4())

    try:
        # Emit start event
        yield followup_start_event(message_id, ticker)

        response = bedrock_agent_runtime.invoke_agent(
            agentId=FOLLOWUP_AGENT_ID,
            agentAliasId=FOLLOWUP_AGENT_ALIAS,
            sessionId=session_id,
            inputText=prompt,
            enableTrace=False
        )

        # Process streaming response
        for event in response.get('completion', []):
            if 'chunk' in event:
                chunk_text = event['chunk'].get('bytes', b'').decode('utf-8')
                yield followup_chunk_event(message_id, chunk_text)

        # Emit end event
        yield followup_end_event(message_id)

    except Exception as e:
        raise


def _execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route tool calls to local handler functions.

    Uses the same functions already defined in this module
    (get_report_section, get_report_ratings, get_metrics_history, get_available_reports).
    """
    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

    try:
        if tool_name == "getReportSection":
            return get_report_section(
                ticker=tool_input.get('ticker', ''),
                section_id=tool_input.get('section_id', '')
            )
        elif tool_name == "getReportRatings":
            return get_report_ratings(
                ticker=tool_input.get('ticker', '')
            )
        elif tool_name == "getMetricsHistory":
            return get_metrics_history(
                ticker=tool_input.get('ticker', ''),
                metric_type=tool_input.get('metric_type', 'all'),
                quarters=tool_input.get('quarters', 8)
            )
        elif tool_name == "getAvailableReports":
            return get_available_reports()
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as e:
        logger.error(f"Tool execution error for {tool_name}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# Tool configuration for converse_stream (matches zip-based Lambda's FOLLOWUP_TOOLS)
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
                                    "01_executive_summary", "06_growth", "07_profit",
                                    "08_valuation", "09_earnings", "10_cashflow",
                                    "11_debt", "12_dilution", "13_bull", "14_bear",
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
                "description": "Retrieves historical financial metrics for trend analysis.",
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
                                "enum": ["all", "revenue_profit", "cashflow", "balance_sheet",
                                         "debt_leverage", "earnings_quality", "dilution", "valuation"],
                                "default": "all"
                            },
                            "quarters": {
                                "type": "integer",
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
                "description": "Lists all companies with available investment reports.",
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


class _DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB for tool result serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


async def _stream_claude_response(
    ticker: str,
    question: str,
    section_context: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream response from Claude Haiku 4.5 using converse_stream with tool orchestration.

    Supports multi-turn tool use: the model can call tools (getReportSection, etc.)
    and the results are fed back for the model to synthesize a final answer.
    Text tokens are streamed to the client as they arrive.

    Args:
        ticker: Stock ticker being discussed
        question: User's follow-up question
        section_context: Optional content from the currently viewed section
        user_id: Optional user ID for token tracking and message persistence
        session_id: Optional session ID for message persistence

    Yields:
        SSE events: followup_start, followup_chunk(s), followup_end
    """
    from services.streaming import (
        followup_start_event,
        followup_chunk_event,
        followup_end_event,
    )

    message_id = str(uuid.uuid4())

    # Enhanced system prompt (matches zip-based Lambda at analysis_followup.py:452-494)
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

Current context: {ticker} | followup analysis{f' | viewing section: {section_context[:200]}' if section_context else ''}"""

    messages = [
        {
            "role": "user",
            "content": [{"text": question}]
        }
    ]

    # Track tokens across all orchestration turns
    total_input_tokens = 0
    total_output_tokens = 0
    full_response = ""

    max_turns = 10
    turn_count = 0

    try:
        # Emit start event
        yield followup_start_event(message_id, ticker)

        # TOKEN LIMIT CHECK - Pre-request validation
        if user_id:
            limit_check = token_tracker.check_limit(user_id)
            if not limit_check.get('allowed', True):
                logger.warning(f"Token limit exceeded for user {user_id}: {limit_check}")
                yield {
                    'event': 'error',
                    'data': json.dumps({
                        'type': 'token_limit_exceeded',
                        'error': 'token_limit_exceeded',
                        'message': 'Monthly token limit reached. Usage resets at the start of your next billing period.',
                        'usage': {
                            'total_tokens': limit_check.get('total_tokens', 0),
                            'token_limit': limit_check.get('token_limit', 0),
                            'percent_used': limit_check.get('percent_used', 100.0),
                            'reset_date': limit_check.get('reset_date', '')
                        },
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    })
                }
                return

        # Orchestration loop - handle tool calls across multiple turns
        while turn_count < max_turns:
            turn_count += 1
            logger.info(f"[STREAM] Orchestration turn {turn_count}/{max_turns} for {ticker}: {question[:50]}...")

            response = bedrock_runtime.converse_stream(
                modelId=FOLLOWUP_MODEL_ID,
                messages=messages,
                system=[{"text": system_prompt}],
                toolConfig=FOLLOWUP_TOOLS,
                inferenceConfig={
                    "maxTokens": 2048,
                    "temperature": 0.7
                }
            )

            # Track this turn's content blocks
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

                # Content block delta - stream text or accumulate tool input
                if 'contentBlockDelta' in stream_event:
                    delta = stream_event['contentBlockDelta'].get('delta', {})

                    if 'text' in delta:
                        chunk_text = delta['text']
                        current_text_block += chunk_text
                        full_response += chunk_text  # Accumulate for persistence
                        # Stream text tokens immediately to client
                        yield followup_chunk_event(message_id, chunk_text)

                    if 'toolUse' in delta:
                        if current_tool_use and 'input' in delta['toolUse']:
                            current_tool_use['input'] += delta['toolUse']['input']

                # Content block stop - finalize text or tool use
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

                # Message stop
                if 'messageStop' in stream_event:
                    stop_reason = stream_event['messageStop'].get('stopReason')

                # Metadata - extract token counts
                if 'metadata' in stream_event:
                    usage = stream_event['metadata'].get('usage', {})
                    total_input_tokens += usage.get('inputTokens', 0)
                    total_output_tokens += usage.get('outputTokens', 0)
                    logger.info(f"Turn {turn_count} tokens: input={usage.get('inputTokens', 0)}, output={usage.get('outputTokens', 0)}")

            logger.info(f"[STREAM] Turn {turn_count} stop_reason={stop_reason}, blocks={len(assistant_content)}")

            if stop_reason == 'tool_use':
                # Model wants tools - execute and continue
                tool_names = [b['toolUse']['name'] for b in assistant_content if 'toolUse' in b]
                logger.info(f"[STREAM] Tool use requested: {tool_names}")

                messages.append({"role": "assistant", "content": assistant_content})

                tool_results = []
                for block in assistant_content:
                    if 'toolUse' in block:
                        tool_use = block['toolUse']
                        result = _execute_tool(tool_use['name'], tool_use.get('input', {}))
                        logger.info(f"[STREAM] Tool {tool_use['name']}: success={result.get('success')}")

                        tool_results.append({
                            "toolResult": {
                                "toolUseId": tool_use['toolUseId'],
                                "content": [{"text": json.dumps(result, cls=_DecimalEncoder)}]
                            }
                        })

                messages.append({"role": "user", "content": tool_results})
                continue

            elif stop_reason == 'end_turn':
                logger.info(f"[STREAM] Complete after {turn_count} turns")
                break
            else:
                logger.warning(f"[STREAM] Unexpected stop reason: {stop_reason}")
                break

        # Record token usage (accumulated across all turns)
        usage_result = {}
        if user_id:
            if total_input_tokens == 0 and total_output_tokens == 0:
                # Fallback estimation if no metadata received
                total_input_tokens = max(1, int(len(question) / 3.5))
                total_output_tokens = max(1, int(len(full_response) / 3.5))
                logger.warning("No token metadata received, using estimation")

            usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
            logger.info(f"Token usage recorded for {user_id}: input={total_input_tokens}, output={total_output_tokens}, "
                        f"total={usage_result.get('total_tokens')}, percent={usage_result.get('percent_used')}%")

        # Save messages to DynamoDB for conversation history
        user_message_id = None
        assistant_message_id = None
        if user_id and session_id:
            user_message_id = save_followup_message(
                session_id=session_id,
                message_type='user',
                content=question,
                user_id=user_id,
                ticker=ticker
            )
            assistant_message_id = save_followup_message(
                session_id=session_id,
                message_type='assistant',
                content=full_response,
                user_id=user_id,
                ticker=ticker
            )

        # Build token usage payload for followup_end event
        token_usage_payload = None
        if user_id and usage_result:
            token_usage_payload = {
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'total_tokens': usage_result.get('total_tokens'),
                'token_limit': usage_result.get('token_limit'),
                'percent_used': usage_result.get('percent_used'),
                'remaining_tokens': usage_result.get('remaining_tokens'),
                'threshold_reached': usage_result.get('threshold_reached'),
            }

        yield followup_end_event(
            message_id,
            token_usage=token_usage_payload,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id
        )

    except Exception as e:
        logger.error(f"Follow-up stream error for {ticker}: {e}", exc_info=True)
        raise


# =============================================================================
# Section ID Mapping for User-Friendly Names
# =============================================================================

SECTION_FRIENDLY_NAMES = {
    '01_executive_summary': 'Executive Summary',
    '06_growth': 'Growth Analysis',
    '07_profit': 'Profitability Assessment',
    '08_valuation': 'Valuation Metrics',
    '09_earnings': 'Earnings Quality',
    '10_cashflow': 'Cash Flow Analysis',
    '11_debt': 'Debt Assessment',
    '12_dilution': 'Shareholder Dilution',
    '13_bull': 'Bull Case',
    '14_bear': 'Bear Case',
    '15_warnings': 'Warning Signs',
    '16_vibe': 'Vibe Check',
    '17_realtalk': 'Real Talk',
}


def get_section_id_from_name(name: str) -> Optional[str]:
    """
    Convert user-friendly section name to section_id.

    Allows users to ask "what does the debt section say" instead of "11_debt".
    """
    name_lower = name.lower()
    for section_id, friendly_name in SECTION_FRIENDLY_NAMES.items():
        if name_lower in friendly_name.lower() or friendly_name.lower() in name_lower:
            return section_id
    return None
