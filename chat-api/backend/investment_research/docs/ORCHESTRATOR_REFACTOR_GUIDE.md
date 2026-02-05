# Custom Orchestrator Refactor Guide

## Converting Follow-Up Agent from Bedrock Agent to Converse API with Tool Use

This guide details the refactor of `analysis_followup.py` to use the Converse API with Tool Use pattern, replacing the Bedrock Agent action groups while maintaining streaming, token counting, and all existing functionality.

---

## Executive Report: Why Custom Orchestration?

### The Problem

BuffettGPT's follow-up agent faces a fundamental architectural constraint with AWS Bedrock:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    THE BEDROCK API DILEMMA                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   OPTION A: invoke_agent() / invoke_agent_with_response_stream()            │
│   ✅ Supports Action Groups (query DynamoDB, access reports)                │
│   ✅ Supports Streaming (partial - agent controls pacing)                   │
│   ❌ NO TOKEN COUNTS - Usage metrics are hidden/unavailable                 │
│   ❌ Opaque orchestration - can't see or control tool decisions            │
│                                                                              │
│   OPTION B: converse() / converse_stream()                                  │
│   ❌ NO ACTION GROUPS - Can't call external functions                       │
│   ✅ Full Streaming Control (true real-time SSE)                            │
│   ✅ EXACT TOKEN COUNTS - metadata.usage in every response                  │
│   ✅ Transparent - full visibility into model behavior                      │
│                                                                              │
│   REQUIREMENT: We need ALL THREE capabilities simultaneously                │
│   - Action Groups (data access)                                              │
│   - Text Streaming (real-time UX)                                            │
│   - Token Counting (billing, limits, cost control)                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Neither API alone satisfies all requirements.** This is not a configuration issue - it's a fundamental limitation of how Bedrock Agents are designed.

### The Solution: Custom Orchestrator with Tool Use

The Converse API supports **Tool Use** (function calling), which allows us to implement action group functionality without the Bedrock Agent layer:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CUSTOM ORCHESTRATOR ARCHITECTURE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   converse_stream() + toolConfig                                            │
│   ✅ Tool Use replaces Action Groups (same functionality)                   │
│   ✅ Full Streaming Control (we control the SSE pipeline)                   │
│   ✅ EXACT TOKEN COUNTS (metadata event after each turn)                    │
│   ✅ Multi-turn conversations (orchestration loop handles tool calls)       │
│                                                                              │
│   THE KEY INSIGHT:                                                           │
│   Instead of Bedrock Agent calling our Lambda for action groups,            │
│   our Lambda becomes the orchestrator that:                                  │
│   1. Calls converse_stream() with tool definitions                          │
│   2. Receives tool_use blocks when model needs data                         │
│   3. Executes tools directly (DynamoDB queries)                             │
│   4. Sends tool_result back to model                                        │
│   5. Repeats until model finishes (end_turn)                                │
│   6. Extracts exact token counts from metadata                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Business Justification

#### 1. Token-Based Billing Accuracy

BuffettGPT uses a subscription model with monthly token limits:

| Tier | Monthly Limit | Impact of Inaccurate Counting |
|------|---------------|------------------------------|
| Anonymous | 1,000 tokens | Minor - exploratory users |
| Authenticated | 50,000 tokens | **Significant** - paying users |
| Premium | 500,000 tokens | **Critical** - high-value customers |
| Enterprise | Unlimited | Cost allocation for internal tracking |

Without exact token counts:
- Users may be cut off prematurely (bad UX, support tickets)
- Users may exceed limits (revenue leakage, unexpected costs)
- No visibility into per-user cost (can't optimize pricing)

**With the Bedrock Agent API, we have zero visibility into actual token consumption.**

#### 2. Cost Control and Optimization

The orchestrator architecture provides:

```
Per-request visibility:
{
  "turn_1": {"input": 450, "output": 85},   // Initial prompt
  "turn_2": {"input": 1200, "output": 72},  // After tool result
  "turn_3": {"input": 1850, "output": 890}, // Final response
  "total": {"input": 3500, "output": 1047}  // Exact totals
}
```

This enables:
- **Cost attribution** per user, per conversation, per feature
- **Budget alerts** before limits are reached
- **Optimization opportunities** (e.g., reduce tool response size)
- **Pricing model validation** (are limits set correctly?)

#### 3. Real-Time Streaming UX

The follow-up agent streams responses character-by-character via Server-Sent Events (SSE):

```javascript
// Frontend receives chunks in real-time
event: chunk
data: {"type":"chunk","text":"Apple's debt-to-equity ratio"}

event: chunk
data: {"type":"chunk","text":" has improved from 1.8x to 1.2x"}

event: chunk
data: {"type":"chunk","text":" over the past 8 quarters..."}
```

With Bedrock Agents, streaming is controlled by the agent layer, which may buffer responses during tool execution. With our orchestrator, we have **full control** over when and how text is streamed to the client.

#### 4. Tool Response Optimization

Our orchestrator can dynamically adjust tool responses based on context:

```python
def execute_tool(tool_name, tool_input, user_remaining_budget=None):
    """Optionally reduce response verbosity for low-budget users."""

    if tool_name == "getMetricsHistory":
        # User running low on tokens - return fewer quarters
        quarters = 8 if user_remaining_budget > 10000 else 4
        return get_metrics_history(ticker, quarters=quarters)
```

This level of control is impossible with Bedrock Agent action groups.

#### 5. Debugging and Observability

With the orchestrator pattern, every step is logged:

```
INFO: Orchestration turn 1 for session abc123
INFO: Executing tool: getReportSection
INFO: Turn 1 tokens: input=450, output=85
INFO: Tool use requested, continuing...
INFO: Orchestration turn 2 for session abc123
INFO: Executing tool: getMetricsHistory
INFO: Turn 2 tokens: input=1200, output=72
INFO: End turn reached after 3 turns
INFO: Total tokens: input=3500, output=1047
```

Bedrock Agent logs are opaque - you can't see why the agent made certain decisions or how many internal turns occurred.

### Trade-off Analysis

| Factor | Bedrock Agent | Custom Orchestrator | Winner |
|--------|---------------|---------------------|--------|
| Development Effort | Low (managed service) | Medium (custom code) | Bedrock |
| Token Visibility | None | Complete | **Orchestrator** |
| Streaming Control | Partial | Full | **Orchestrator** |
| Tool Response Optimization | None | Full | **Orchestrator** |
| Debugging | Limited | Comprehensive | **Orchestrator** |
| AWS Managed Updates | Automatic | Manual | Bedrock |
| Vendor Lock-in | High | Lower | **Orchestrator** |
| Multi-model Support | Bedrock only | Any Converse-compatible | **Orchestrator** |

**Conclusion:** For a subscription-based product with token billing, the custom orchestrator is the correct architectural choice despite the additional development effort.

### Risk Mitigation

The primary risks and mitigations:

1. **Infinite Loop Risk**: Max turns limit (10) prevents runaway costs
2. **Token Explosion**: Per-turn tracking with budget checks
3. **Complexity**: Well-documented code, comprehensive tests
4. **Maintenance Burden**: Tool definitions are simple JSON schemas

### ROI Projection

| Investment | Return |
|------------|--------|
| ~670 lines of code | Exact token billing for all tiers |
| ~40 hours development | Eliminated billing disputes |
| Ongoing maintenance | Full cost visibility and optimization |
| | Improved debugging and support efficiency |
| | Foundation for premium tier differentiation |

---

## Technical Summary

### Current State
- `analysis_followup.py` uses `converse_stream()` for direct model invocation
- Token tracking via `TokenUsageTracker` is fully integrated (Phase 1 & 2 complete)
- Action groups exist in separate Docker Lambda (`followup_action/`) but are **not currently used**
- The handler provides basic Q&A without access to report data or metrics

### Target State
- Same handler uses `converse_stream()` with `toolConfig` parameter
- Tool Use loop handles model requests for data
- Action group logic moved inline (no separate Lambda needed)
- Full access to reports, ratings, and metrics during follow-up conversations
- Exact token counts preserved across all turns

### Why This Refactor?

| Requirement | Bedrock Agent | Converse + Tool Use |
|-------------|---------------|---------------------|
| Action Groups | ✅ Native | ✅ Via toolConfig |
| Text Streaming | ✅ Partial | ✅ Full control |
| Exact Token Counts | ❌ Hidden | ✅ From metadata |
| Multi-turn Tool Calls | ✅ Automatic | ✅ Orchestrator loop |
| Cost Visibility | ❌ Opaque | ✅ Per-turn tracking |

---

## Architecture Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BEFORE: Bedrock Agent (Not Used)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   analysis_followup.py → converse_stream() → Claude → Response              │
│                          (no tools, no data access)                          │
│                                                                              │
│   followup_action Lambda → (deployed but unused)                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                        AFTER: Custom Orchestrator                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   analysis_followup.py                                                       │
│        │                                                                     │
│        ├── converse_stream() with toolConfig                                │
│        │        │                                                            │
│        │        ├── Stream text → SSE to client                             │
│        │        │                                                            │
│        │        └── tool_use → execute_tool() → DynamoDB                    │
│        │                            │                                        │
│        │                            ├── getReportSection()                  │
│        │                            ├── getReportRatings()                  │
│        │                            ├── getMetricsHistory()                 │
│        │                            └── getAvailableReports()               │
│        │                                                                     │
│        └── metadata → token_tracker.record_usage()                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Development Phases

### Phase 1: Tool Configuration (Est. 1-2 hours)

**Task:** Define tool specifications matching the 4 action group functions.

**File:** `chat-api/backend/src/handlers/analysis_followup.py`

**Add after line 130 (after token_tracker initialization):**

```python
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
```

**Acceptance Criteria:**
- [ ] Tool definitions compile without errors
- [ ] All 4 action group functions represented
- [ ] Section IDs match DynamoDB `section_id` values exactly
- [ ] Metric types match `metrics-history` table categories

---

### Phase 2: Tool Executor Functions (Est. 2-3 hours)

**Task:** Implement DynamoDB query functions that replace the action group Lambda.

**Create new file:** `chat-api/backend/src/utils/tool_executor.py`

```python
"""
Tool Executor for Follow-Up Agent

Implements the 4 tool functions that replace Bedrock Agent action groups.
Queries DynamoDB directly for investment reports and metrics.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Dict, Any, Optional, List

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
REPORTS_TABLE = os.environ.get('INVESTMENT_REPORTS_TABLE', f'investment-reports-v2-{ENVIRONMENT}')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_TABLE', f'metrics-history-{ENVIRONMENT}')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
reports_table = dynamodb.Table(REPORTS_TABLE)
metrics_table = dynamodb.Table(METRICS_TABLE)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route tool calls to appropriate handler functions.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Parameters for the tool

    Returns:
        Tool result dict with success/error status
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
            logger.warning(f"Unknown tool requested: {tool_name}")
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

    except Exception as e:
        logger.error(f"Tool execution error for {tool_name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def get_report_section(ticker: str, section_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific section from an investment report.

    Args:
        ticker: Stock ticker symbol
        section_id: Section identifier (e.g., '11_debt', '06_growth')

    Returns:
        Section content with metadata
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}
    if not section_id:
        return {"success": False, "error": "section_id is required"}

    ticker = ticker.upper().strip()

    try:
        # Query DynamoDB for the section
        response = reports_table.get_item(
            Key={
                'ticker': ticker,
                'section_id': section_id
            }
        )

        item = response.get('Item')

        if not item:
            return {
                "success": False,
                "error": f"Section '{section_id}' not found for {ticker}. The report may not exist or use a different section ID."
            }

        return {
            "success": True,
            "ticker": ticker,
            "section_id": section_id,
            "title": item.get('title', ''),
            "content": item.get('content', ''),
            "part": int(item.get('part', 0)),
            "word_count": int(item.get('word_count', 0))
        }

    except Exception as e:
        logger.error(f"Error fetching report section {ticker}/{section_id}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_report_ratings(ticker: str) -> Dict[str, Any]:
    """
    Get investment ratings and verdict for a company.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Ratings object with confidence scores and verdict
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    ticker = ticker.upper().strip()

    try:
        # Ratings are stored in the executive summary section
        response = reports_table.get_item(
            Key={
                'ticker': ticker,
                'section_id': '01_executive_summary'
            }
        )

        item = response.get('Item')

        if not item:
            return {
                "success": False,
                "error": f"No ratings found for {ticker}. Report may not exist."
            }

        # Extract ratings - handle both JSON string and dict formats
        ratings = item.get('ratings_json') or item.get('ratings', {})
        if isinstance(ratings, str):
            ratings = json.loads(ratings)

        return {
            "success": True,
            "ticker": ticker,
            "company_name": item.get('company_name', ticker),
            "ratings": ratings,
            "generated_at": item.get('generated_at', '')
        }

    except Exception as e:
        logger.error(f"Error fetching ratings for {ticker}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_metrics_history(
    ticker: str,
    metric_type: str = 'all',
    quarters: int = 8
) -> Dict[str, Any]:
    """
    Retrieve historical financial metrics for trend analysis.

    Args:
        ticker: Stock ticker symbol
        metric_type: Category of metrics ('all', 'revenue_profit', 'cashflow', etc.)
        quarters: Number of quarters to retrieve (1-40)

    Returns:
        Historical metrics organized by category
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    ticker = ticker.upper().strip()
    quarters = min(max(int(quarters), 1), 40)  # Clamp to 1-40

    # Valid metric categories
    valid_categories = [
        'revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
        'earnings_quality', 'dilution', 'valuation'
    ]

    if metric_type != 'all' and metric_type not in valid_categories:
        return {
            "success": False,
            "error": f"Unknown metric type: {metric_type}",
            "available_types": valid_categories
        }

    categories_to_include = valid_categories if metric_type == 'all' else [metric_type]

    try:
        # Query metrics table sorted by fiscal_date descending
        response = metrics_table.query(
            KeyConditionExpression=Key('ticker').eq(ticker),
            ScanIndexForward=False,  # Most recent first
            Limit=quarters
        )

        items = response.get('Items', [])

        if not items:
            return {
                "success": False,
                "error": f"No metrics history found for {ticker}. Report may not have been generated.",
                "ticker": ticker
            }

        # Build result with filtered categories
        result = {
            "success": True,
            "ticker": ticker,
            "metric_type": metric_type,
            "quarters_requested": quarters,
            "quarters_available": len(items),
            "data": {}
        }

        # Category descriptions for context
        category_descriptions = {
            'revenue_profit': 'Revenue & Profitability',
            'cashflow': 'Cash Flow Metrics',
            'balance_sheet': 'Balance Sheet',
            'debt_leverage': 'Debt & Leverage Ratios',
            'earnings_quality': 'Earnings Quality',
            'dilution': 'Share Dilution',
            'valuation': 'Valuation Multiples'
        }

        # Initialize categories
        for category in categories_to_include:
            result['data'][category] = {
                'description': category_descriptions.get(category, category),
                'quarters': []
            }

        # Process each quarter
        for item in items:
            fiscal_date = item.get('fiscal_date', '')
            fiscal_year = item.get('fiscal_year')
            fiscal_quarter = item.get('fiscal_quarter', '')

            for category in categories_to_include:
                category_metrics = item.get(category, {})

                if category_metrics:
                    # Convert Decimals to floats
                    metrics_clean = {}
                    for k, v in category_metrics.items():
                        if isinstance(v, Decimal):
                            metrics_clean[k] = float(v)
                        elif v is not None:
                            metrics_clean[k] = v

                    result['data'][category]['quarters'].append({
                        'fiscal_date': fiscal_date,
                        'fiscal_year': int(fiscal_year) if fiscal_year else None,
                        'fiscal_quarter': fiscal_quarter,
                        'metrics': metrics_clean
                    })

        return result

    except Exception as e:
        logger.error(f"Error fetching metrics for {ticker}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_available_reports() -> Dict[str, Any]:
    """
    List all companies with available investment reports.

    Returns:
        List of available reports with metadata
    """
    try:
        # Scan for executive summary items (one per ticker)
        response = reports_table.scan(
            FilterExpression='section_id = :sid',
            ExpressionAttributeValues={':sid': '01_executive_summary'},
            ProjectionExpression='ticker, company_name, generated_at'
        )

        reports = []
        for item in response.get('Items', []):
            reports.append({
                'ticker': item.get('ticker', ''),
                'company_name': item.get('company_name', item.get('ticker', '')),
                'generated_at': item.get('generated_at', '')
            })

        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = reports_table.scan(
                FilterExpression='section_id = :sid',
                ExpressionAttributeValues={':sid': '01_executive_summary'},
                ProjectionExpression='ticker, company_name, generated_at',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                reports.append({
                    'ticker': item.get('ticker', ''),
                    'company_name': item.get('company_name', item.get('ticker', '')),
                    'generated_at': item.get('generated_at', '')
                })

        # Sort alphabetically by ticker
        reports.sort(key=lambda x: x['ticker'])

        return {
            "success": True,
            "count": len(reports),
            "reports": reports
        }

    except Exception as e:
        logger.error(f"Error listing available reports: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }
```

**Acceptance Criteria:**
- [ ] All 4 functions implemented
- [ ] DynamoDB queries match existing action group Lambda
- [ ] Decimal handling for DynamoDB numbers
- [ ] Error handling with descriptive messages
- [ ] Logging for debugging

---

### Phase 3: Orchestration Loop - Streaming Path (Est. 3-4 hours)

**Task:** Refactor `stream_followup_response()` to handle Tool Use in a loop.

**This is the most complex change.** The existing streaming code (lines 268-489) needs to be wrapped in an orchestration loop.

**Key Changes to `stream_followup_response()`:**

```python
def stream_followup_response(event: Dict[str, Any], context: Any, user_id: str = 'anonymous'):
    """
    Stream follow-up question response with Tool Use support.

    Uses orchestration loop to handle multiple tool calls while streaming.
    Accumulates token counts across all turns for accurate tracking.
    """
    try:
        # ... (keep existing header yield and request parsing, lines 281-329)

        # Import tool executor
        from utils.tool_executor import execute_tool

        # Build initial messages
        messages = [
            {
                "role": "user",
                "content": [{"text": question}]
            }
        ]

        # Enhanced system prompt with tool guidance
        system_prompt = f"""You are a financial analyst assistant with access to investment research tools.

You are helping with follow-up questions about {ticker}'s analysis.

AVAILABLE TOOLS:
- getReportSection: Get specific sections (growth, debt, valuation, etc.)
- getReportRatings: Get investment ratings and verdict
- getMetricsHistory: Get historical financial metrics for trends
- getAvailableReports: List all available company reports

GUIDELINES:
1. Use tools to retrieve data before answering questions about specific metrics or analysis
2. Cite specific numbers and data points from the tools
3. If asked about trends, use getMetricsHistory with appropriate quarters
4. Keep responses focused and under 300 words unless more detail is needed
5. Be direct and data-driven in your analysis

Current context: {agent_type} analysis for {ticker}"""

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
            logger.info(f"Orchestration turn {turn_count} for session {session_id}")

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

            if stop_reason == 'tool_use':
                # Model wants to use tools - execute them and continue
                logger.info(f"Tool use requested in turn {turn_count}")

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
                        logger.info(f"Executing tool: {tool_use['name']}")

                        # Execute the tool
                        result = execute_tool(tool_use['name'], tool_use['input'])

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

                # Continue the loop for model to process results
                continue

            elif stop_reason == 'end_turn':
                # Model finished responding - exit loop
                logger.info(f"End turn reached after {turn_count} turns")
                break

            else:
                # Unexpected stop reason
                logger.warning(f"Unexpected stop reason: {stop_reason}")
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
```

**Acceptance Criteria:**
- [ ] Tool use blocks detected and accumulated from stream
- [ ] Tools executed via `execute_tool()` function
- [ ] Tool results sent back to model correctly
- [ ] Loop continues until `end_turn` or max turns
- [ ] Token counts accumulated across all turns
- [ ] Text still streams in real-time during tool-free responses

---

### Phase 4: Orchestration Loop - Non-Streaming Path (Est. 2 hours)

**Task:** Apply same pattern to the non-streaming `lambda_handler()` path (lines 579-725).

The non-streaming path uses `converse()` instead of `converse_stream()`. The loop pattern is similar but simpler since we don't need to handle streaming events.

```python
# In lambda_handler(), replace the existing converse() call with a loop

# Track tokens across all turns
total_input_tokens = 0
total_output_tokens = 0
full_response = ""
max_turns = 10
turn_count = 0

messages = [{"role": "user", "content": [{"text": question}]}]

while turn_count < max_turns:
    turn_count += 1

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

    # Get output message
    output_message = response.get('output', {}).get('message', {})
    stop_reason = response.get('stopReason', '')

    # Process content blocks
    assistant_content = output_message.get('content', [])

    for block in assistant_content:
        if 'text' in block:
            full_response += block['text']

    if stop_reason == 'tool_use':
        # Add assistant message
        messages.append({"role": "assistant", "content": assistant_content})

        # Execute tools
        tool_results = []
        for block in assistant_content:
            if 'toolUse' in block:
                result = execute_tool(block['toolUse']['name'], block['toolUse']['input'])
                tool_results.append({
                    "toolResult": {
                        "toolUseId": block['toolUse']['toolUseId'],
                        "content": [{"text": json.dumps(result)}]
                    }
                })

        messages.append({"role": "user", "content": tool_results})
        continue

    elif stop_reason == 'end_turn':
        break

# Continue with existing token recording and response building...
```

**Acceptance Criteria:**
- [ ] Non-streaming path supports tool use
- [ ] Token counts accumulated correctly
- [ ] Response format unchanged for API consumers

---

### Phase 5: Testing (Est. 2-3 hours)

**Task:** Add unit tests for the new tool executor and integration tests for the orchestration loop.

**Create:** `chat-api/backend/tests/unit/test_tool_executor.py`

```python
"""Unit tests for tool executor functions."""

import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

# Test cases needed:
# - test_get_report_section_success
# - test_get_report_section_not_found
# - test_get_report_section_missing_ticker
# - test_get_report_ratings_success
# - test_get_report_ratings_json_string
# - test_get_metrics_history_all_categories
# - test_get_metrics_history_single_category
# - test_get_metrics_history_quarter_clamping
# - test_get_available_reports_pagination
# - test_execute_tool_routing
# - test_execute_tool_unknown_tool
# - test_decimal_handling
```

**Update:** `chat-api/backend/tests/unit/test_analysis_followup.py`

```python
# Add test cases for:
# - test_tool_use_single_turn
# - test_tool_use_multi_turn
# - test_tool_use_max_turns_safety
# - test_token_accumulation_across_turns
# - test_streaming_with_tool_interruption
```

**Acceptance Criteria:**
- [ ] Tool executor unit tests pass
- [ ] Orchestration loop tests pass
- [ ] Token accumulation tests pass
- [ ] All existing tests still pass

---

### Phase 6: Environment Configuration (Est. 1 hour)

**Task:** Add required environment variables to Terraform.

**Update:** `chat-api/terraform/modules/lambda/analysis_followup.tf`

```hcl
environment {
  variables = {
    # Existing variables...

    # NEW: Tables for tool executor
    INVESTMENT_REPORTS_TABLE = var.investment_reports_table_name
    METRICS_HISTORY_TABLE    = var.metrics_history_table_name
  }
}
```

**Update IAM policy** to allow DynamoDB access to reports and metrics tables:

```hcl
# Add to Lambda execution role policy
{
  Effect = "Allow"
  Action = [
    "dynamodb:GetItem",
    "dynamodb:Query",
    "dynamodb:Scan"
  ]
  Resource = [
    var.investment_reports_table_arn,
    "${var.investment_reports_table_arn}/index/*",
    var.metrics_history_table_arn,
    "${var.metrics_history_table_arn}/index/*"
  ]
}
```

**Acceptance Criteria:**
- [ ] Environment variables configured
- [ ] IAM permissions allow DynamoDB access
- [ ] Terraform plan shows expected changes

---

## Risk Assessment

### High Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Infinite loop in orchestration** | Lambda timeout, cost spike | Max turns limit (10), timeout monitoring |
| **Token count explosion** | User hits limit quickly, billing impact | Per-turn token tracking, budget alerts |
| **DynamoDB throttling** | Tool calls fail, degraded UX | Retry logic, exponential backoff |
| **Streaming interruption** | Partial response, lost context | Error recovery, client reconnect logic |

### Medium Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Tool input parsing errors** | Tool fails, fallback to no-tool response | Try/catch with default empty dict |
| **Model doesn't use tools** | Responses lack data, same as current | Improve system prompt, add examples |
| **Concurrent request race conditions** | Token counts inaccurate | Atomic DynamoDB updates (already implemented) |
| **Large tool responses** | Token budget consumed by tool data | Truncate large responses, filter fields |

### Low Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Section ID mismatch** | "Not found" errors | Enum validation in tool schema |
| **Decimal serialization** | JSON encoding errors | DecimalEncoder class |
| **Missing reports** | User sees "no data" message | Clear error messages, suggest alternatives |

---

## Rollback Plan

If issues arise during deployment:

1. **Feature flag approach** (recommended):
   ```python
   USE_TOOL_ORCHESTRATION = os.environ.get('USE_TOOL_ORCHESTRATION', 'false') == 'true'

   if USE_TOOL_ORCHESTRATION:
       # New orchestration loop
   else:
       # Existing converse_stream without tools
   ```

2. **Quick rollback**: Revert to previous Lambda version in AWS Console

3. **Terraform rollback**: `terraform apply` with previous state

---

## Deployment Checklist

### Pre-Deployment
- [ ] All unit tests passing locally
- [ ] Tool executor tested against dev DynamoDB tables
- [ ] Feature flag set to `false` initially
- [ ] CloudWatch alarms configured for Lambda errors

### Deployment
- [ ] Deploy Lambda with feature flag off
- [ ] Verify existing functionality unchanged
- [ ] Enable feature flag for single test user
- [ ] Monitor CloudWatch logs for tool execution
- [ ] Verify token counts in DynamoDB

### Post-Deployment
- [ ] Enable feature flag for all users
- [ ] Monitor error rates for 24 hours
- [ ] Verify token tracking accuracy
- [ ] Check user feedback for response quality

---

## Integration with Token Limiter System

This refactor **extends** the existing Token Limiter System (Phases 1 & 2 complete):

| Token Limiter Phase | Status | Orchestrator Impact |
|---------------------|--------|---------------------|
| Phase 1: TokenUsageTracker | ✅ Complete | No changes needed |
| Phase 2: ConverseStream integration | ✅ Complete | **Extended** with tool loop |
| Phase 3: Usage API endpoint | Pending | No overlap |
| Phase 4: Frontend display | Pending | No overlap |
| Phase 5: Notifications | Pending | No overlap |

The key integration point is **token accumulation across turns**:

```python
# OLD: Single turn token extraction
if 'metadata' in stream_event:
    input_tokens = usage.get('inputTokens', 0)
    output_tokens = usage.get('outputTokens', 0)

# NEW: Accumulated across all turns
total_input_tokens += usage.get('inputTokens', 0)
total_output_tokens += usage.get('outputTokens', 0)
```

This ensures accurate billing even when the model makes multiple tool calls.

---

## Files Changed Summary

| Action | File | Lines Changed |
|--------|------|---------------|
| MODIFY | `src/handlers/analysis_followup.py` | ~200 lines |
| CREATE | `src/utils/tool_executor.py` | ~250 lines |
| CREATE | `tests/unit/test_tool_executor.py` | ~150 lines |
| MODIFY | `tests/unit/test_analysis_followup.py` | ~50 lines |
| MODIFY | `terraform/modules/lambda/analysis_followup.tf` | ~20 lines |

**Total estimated changes:** ~670 lines

---

## Ralph Loop Instructions

When using Claude Code with the Ralph Loop for continuous development:

### Suggested Task Sequence

1. **Task 1:** Create `tool_executor.py` with all 4 functions
2. **Task 2:** Add `FOLLOWUP_TOOLS` configuration to `analysis_followup.py`
3. **Task 3:** Refactor `stream_followup_response()` with orchestration loop
4. **Task 4:** Refactor non-streaming path in `lambda_handler()`
5. **Task 5:** Write unit tests for `tool_executor.py`
6. **Task 6:** Update integration tests for orchestration loop
7. **Task 7:** Update Terraform configuration
8. **Task 8:** Test locally with mock DynamoDB

### Verification Points

After each task, verify:
- [ ] No syntax errors
- [ ] Existing tests still pass
- [ ] New code follows project conventions
- [ ] Logging added for debugging

---

## References

- [TOKEN_LIMITER_SYSTEM.md](TOKEN_LIMITER_SYSTEM.md) - Token tracking system documentation
- [FOLLOWUP_AGENT.md](FOLLOWUP_AGENT.md) - Current follow-up agent documentation
- [Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) - AWS documentation
- [Tool Use with Converse](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use.html) - AWS tool use guide

---

## Revision History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-28 | 1.0 | Initial implementation guide |
