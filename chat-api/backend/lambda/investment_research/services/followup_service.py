"""
Follow-up Question Service for Investment Research

Provides context retrieval and integration with Bedrock agents for
answering follow-up questions about investment reports.

Uses only the ~60 metrics that appear in investment research reports
(not the full 80+ features from the feature extractor).
"""

import os
import json
import boto3
import logging
from typing import Dict, Any, Optional, List, AsyncGenerator
from datetime import datetime

logger = logging.getLogger(__name__)

# DynamoDB table names
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_TABLE_V2', 'investment-reports-v2-dev')
FINANCIAL_CACHE_TABLE = os.environ.get('FINANCIAL_DATA_CACHE_TABLE', 'financial-data-cache-dev')

# Bedrock configuration
BEDROCK_REGION = os.environ.get('BEDROCK_REGION', 'us-east-1')
FOLLOWUP_AGENT_ID = os.environ.get('FOLLOWUP_AGENT_ID', '')
FOLLOWUP_AGENT_ALIAS = os.environ.get('FOLLOWUP_AGENT_ALIAS', 'TSTALIASID')

# Claude Haiku 4.5 model for follow-up chat (inference profile for cross-region)
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-3-5-haiku-20241022-v1:0'
)

# Initialize clients
dynamodb = boto3.resource('dynamodb')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=BEDROCK_REGION)
bedrock_agent_runtime = boto3.client('bedrock-agent-runtime', region_name=BEDROCK_REGION)


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


# =============================================================================
# Bedrock Agent Integration
# =============================================================================

async def invoke_followup_agent(
    ticker: str,
    question: str,
    session_id: Optional[str] = None,
    section_id: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Invoke the follow-up agent with streaming response.

    Uses Bedrock's converse_stream API for SSE-compatible streaming.

    Args:
        ticker: Stock ticker being discussed
        question: User's follow-up question
        session_id: Optional session ID for conversation continuity
        section_id: Optional section ID for additional context

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
        if FOLLOWUP_AGENT_ID:
            # Use Bedrock Agent with streaming
            async for event in _stream_agent_response(context_prompt, session_id):
                yield event
        else:
            # Use direct converse_stream with Claude Haiku 4.5
            async for event in _stream_claude_response(ticker, question, section_context):
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
    session_id: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream response from Bedrock Agent.
    """
    try:
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
                yield {
                    'event': 'chunk',
                    'data': json.dumps({'text': chunk_text})
                }

        yield {
            'event': 'complete',
            'data': json.dumps({'session_id': session_id})
        }

    except Exception as e:
        raise


async def _stream_claude_response(
    ticker: str,
    question: str,
    section_context: Optional[str] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream response from Claude Haiku 4.5 using converse_stream.

    Used for follow-up questions about investment research reports.

    Args:
        ticker: Stock ticker being discussed
        question: User's follow-up question
        section_context: Optional content from the currently viewed section

    Yields:
        SSE events: followup_start, followup_chunk(s), followup_end
    """
    import uuid
    from services.streaming import (
        followup_start_event,
        followup_chunk_event,
        followup_end_event,
    )

    message_id = str(uuid.uuid4())

    # Get report context
    ratings = get_report_ratings(ticker)
    executive = get_report_section(ticker, '01_executive_summary')

    # Build context
    context_parts = []
    if ratings.get('success'):
        context_parts.append(f"Investment Ratings:\n{json.dumps(ratings['ratings'], indent=2)}")
    if executive.get('success'):
        # Truncate to ~2000 chars to stay within context limits
        exec_content = executive['content'][:2000]
        context_parts.append(f"Executive Summary:\n{exec_content}...")
    if section_context:
        context_parts.append(f"Currently Viewing Section:\n{section_context[:1500]}...")

    context = "\n\n".join(context_parts)

    # System prompt for follow-up assistant
    system_prompt = f"""You are a helpful financial analyst assistant for the {ticker} investment research report.
Answer questions concisely using the provided report context.
Be specific, cite numbers when relevant, and acknowledge limitations of the data.
Keep responses focused and under 300 words unless more detail is specifically requested."""

    messages = [
        {
            "role": "user",
            "content": [{"text": f"Report Context:\n{context}\n\nQuestion: {question}"}]
        }
    ]

    try:
        # Emit start event
        yield followup_start_event(message_id, ticker)

        response = bedrock_runtime.converse_stream(
            modelId=FOLLOWUP_MODEL_ID,
            messages=messages,
            system=[{"text": system_prompt}],
            inferenceConfig={
                "maxTokens": 2048,
                "temperature": 0.7
            }
        )

        for event in response.get('stream', []):
            if 'contentBlockDelta' in event:
                delta = event['contentBlockDelta'].get('delta', {})
                if 'text' in delta:
                    yield followup_chunk_event(message_id, delta['text'])

        # Emit end event
        yield followup_end_event(message_id)

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
