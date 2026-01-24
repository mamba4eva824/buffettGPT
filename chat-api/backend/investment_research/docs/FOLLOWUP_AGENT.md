# Follow-up Research Agent - Executive Report

## Overview

The Follow-up Research Agent is a Bedrock-powered conversational AI system that enables users to ask follow-up questions about investment research reports. It provides intelligent access to pre-generated investment analysis through natural language queries, leveraging AWS Bedrock's agent framework with action groups.

**Deployment Date:** January 17, 2026
**Agent Model:** Claude Haiku 4.5 (us.anthropic.claude-haiku-4-5-20251001-v1:0)
**Agent ID:** LWY2A9T2DQ
**Agent Status:** PREPARED (Ready for Use)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                     │
│                    (Investment Research Frontend)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     INVESTMENT RESEARCH LAMBDA                               │
│            invoke_followup_agent() - Handles user follow-up questions        │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BEDROCK AGENT                                       │
│                      (buffett-dev-followup)                                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Agent Instructions (followup_agent_v1.txt)                          │    │
│  │  • Role: Follow-up Research Assistant                                │    │
│  │  • Context: Value investing principles (Warren Buffett inspired)     │    │
│  │  • Guidelines: Data-driven responses, cite sources, no predictions   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                     ┌──────────────┴──────────────┐                         │
│                     ▼                              ▼                         │
│         ┌──────────────────┐           ┌──────────────────┐                 │
│         │  Knowledge Base  │           │   Action Group   │                 │
│         │   (NOT USED)     │           │ (ReportResearch) │                 │
│         └──────────────────┘           └──────────────────┘                 │
│                                                │                             │
└────────────────────────────────────────────────│─────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      FOLLOWUP ACTION LAMBDA                                  │
│                  (buffett-dev-followup-action)                               │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  Docker Container (ECR: buffett/followup-action:latest)            │     │
│  │  • Runtime: Python 3.11                                            │     │
│  │  • Memory: 512 MB                                                  │     │
│  │  • Timeout: 30 seconds                                             │     │
│  │  • No Lambda Web Adapter (returns Bedrock JSON directly)           │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                    │                                         │
│         ┌──────────────────────────┼──────────────────────────┐             │
│         ▼                          ▼                          ▼             │
│  ┌─────────────┐          ┌─────────────┐          ┌─────────────┐         │
│  │ Report      │          │ Ratings     │          │ Metrics     │         │
│  │ Sections    │          │ Service     │          │ History     │         │
│  └─────────────┘          └─────────────┘          └─────────────┘         │
│                                    │                                         │
└────────────────────────────────────│─────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DYNAMODB                                           │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  investment-reports-v2                                               │    │
│  │  • PK: ticker, SK: section_id                                       │    │
│  │  • Contains: Report sections, ratings, executive summaries           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  financial-data-cache (future use)                                   │    │
│  │  • Historical metrics from FMP API                                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Business Value

| Benefit | Description |
|---------|-------------|
| **Enhanced User Engagement** | Users can ask natural language questions about reports instead of re-reading sections |
| **Improved Data Accessibility** | Complex financial data presented in conversational, digestible format |
| **Reduced Cognitive Load** | Agent handles data retrieval; users focus on understanding |
| **Contextual Responses** | Agent maintains conversation context for multi-turn interactions |
| **Cost-Effective** | Claude Haiku 4.5 provides quality responses at lower cost than larger models |

---

## Action Group Technical Analysis

### Overview

The **ReportResearch** action group provides four functions for retrieving investment report data. These functions are defined via OpenAPI 3.0 schema and implemented in the followup-action Lambda.

### Action Group Configuration

| Property | Value |
|----------|-------|
| Action Group ID | TKUXSMSIJL |
| Action Group Name | ReportResearch |
| State | ENABLED |
| Agent Version | DRAFT |
| Schema Format | OpenAPI 3.0 |

### API Operations

#### 1. getReportSection

**Purpose:** Retrieve a specific section from an investment report.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ticker | string | Yes | Stock ticker symbol (e.g., AAPL, MSFT) |
| section_id | enum | Yes | Section identifier (see table below) |

**Available Sections:**

| Section ID | Description | Report Part |
|------------|-------------|-------------|
| 01_executive_summary | Overview with key findings and verdict | Part 1 (Executive) |
| 06_growth | Revenue and earnings growth analysis | Part 2 (Detailed) |
| 07_profit | Profitability and margin analysis | Part 2 (Detailed) |
| 08_valuation | Valuation metrics and comparison | Part 2 (Detailed) |
| 09_earnings | Earnings quality assessment | Part 2 (Detailed) |
| 10_cashflow | Cash flow generation and conversion | Part 2 (Detailed) |
| 11_debt | Debt levels and leverage analysis | Part 2 (Detailed) |
| 12_dilution | Shareholder dilution trends | Part 2 (Detailed) |
| 13_bull | Bull case and positive catalysts | Part 3 (RealTalk) |
| 14_bear | Bear case and risks | Part 3 (RealTalk) |
| 15_warnings | Red flags and warning signs | Part 3 (RealTalk) |
| 16_vibe | Overall sentiment and vibe check | Part 3 (RealTalk) |
| 17_realtalk | Candid assessment and bottom line | Part 3 (RealTalk) |

**Response Schema:**
```json
{
  "success": true,
  "ticker": "AAPL",
  "section_id": "11_debt",
  "title": "Debt Assessment",
  "content": "## Debt Assessment\n\nApple maintains...",
  "part": 2,
  "word_count": 450
}
```

---

#### 2. getReportRatings

**Purpose:** Retrieve all investment ratings for a ticker.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ticker | string | Yes | Stock ticker symbol |

**Response Schema:**
```json
{
  "success": true,
  "ticker": "AAPL",
  "ratings": {
    "debt_rating": "STRONG",
    "debt_confidence": 85,
    "cashflow_rating": "STRONG",
    "cashflow_confidence": 90,
    "growth_rating": "NEUTRAL",
    "growth_confidence": 72,
    "overall_verdict": "BUY",
    "conviction": 78
  },
  "generated_at": "2026-01-15T10:30:00Z"
}
```

**Rating Values:**
- **Ratings:** STRONG, NEUTRAL, WEAK
- **Verdict:** BUY, HOLD, AVOID
- **Confidence/Conviction:** 0-100 scale

---

#### 3. getMetricsHistory

**Purpose:** Retrieve historical financial metrics for trend analysis.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| ticker | string | Yes | - | Stock ticker symbol |
| metric_type | enum | No | "all" | Category of metrics (see below) |
| quarters | integer | No | 20 | Quarters of history (max 40) |

**Metric Categories:**

| Category | Description | Key Metrics |
|----------|-------------|-------------|
| revenue_profit | Revenue & Profitability | revenue, netIncome, gross_margin, operating_margin, eps |
| cashflow | Cash Flow | operatingCashFlow, freeCashFlow, fcf_margin, capitalExpenditure |
| balance_sheet | Balance Sheet | totalDebt, cashAndCashEquivalents, totalLiquidity, netDebt |
| debt_leverage | Debt & Leverage Ratios | debt_to_equity, debt_to_assets, interest_coverage, current_ratio |
| earnings_quality | Earnings Quality | gaap_net_income, stock_based_compensation, sbc_to_revenue_pct |
| dilution | Shareholder Dilution | basic_shares_outstanding, diluted_shares_outstanding, dilution_pct |
| valuation | Valuation Metrics | pe_ratio, pb_ratio, ev_to_ebitda, price_to_fcf, roe, roic |

**Note:** Historical metrics retrieval from financial-data-cache is planned for future implementation.

---

#### 4. getAvailableReports

**Purpose:** List all available investment reports in the database.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | No parameters required |

**Response Schema:**
```json
{
  "success": true,
  "count": 15,
  "reports": [
    {
      "ticker": "AAPL",
      "company_name": "Apple Inc.",
      "generated_at": "2026-01-15T10:30:00Z"
    },
    {
      "ticker": "MSFT",
      "company_name": "Microsoft Corporation",
      "generated_at": "2026-01-14T15:45:00Z"
    }
  ]
}
```

---

### Bedrock Response Format

All action group responses follow the Bedrock action group specification:

```json
{
  "messageVersion": "1.0",
  "response": {
    "actionGroup": "ReportResearch",
    "apiPath": "/getReportSection",
    "httpMethod": "POST",
    "httpStatusCode": 200,
    "responseBody": {
      "application/json": {
        "body": "{\"success\": true, \"ticker\": \"AAPL\", ...}"
      }
    }
  }
}
```

**Key Points:**
- `messageVersion` must be "1.0"
- `responseBody.application/json.body` must be a JSON **string**, not an object
- HTTP status codes indicate success (200) or error (400, 500)

---

## Infrastructure Components

### Lambda Function: followup-action

| Property | Value |
|----------|-------|
| Function Name | buffett-dev-followup-action |
| Package Type | Docker Image |
| ECR Repository | buffett/followup-action |
| Image Tag | latest |
| Memory | 512 MB |
| Timeout | 30 seconds |
| Runtime | Python 3.11 |
| X-Ray Tracing | Active |

**Environment Variables:**

| Variable | Description |
|----------|-------------|
| INVESTMENT_REPORTS_V2_TABLE | DynamoDB table for report sections (`investment-reports-v2-dev`) |
| FINANCIAL_DATA_CACHE_TABLE | DynamoDB table for metrics cache |
| LOG_LEVEL | Logging verbosity (INFO) |

### IAM Permissions

The Lambda execution role has the following permissions:

| Action | Resource | Purpose |
|--------|----------|---------|
| dynamodb:GetItem | investment-reports-v2 | Read report sections |
| dynamodb:Query | investment-reports-v2 | Query by ticker |
| dynamodb:Scan | investment-reports-v2 | List all reports |
| dynamodb:GetItem | financial-data-cache | Read cached metrics |
| dynamodb:Query | financial-data-cache | Query metrics history |
| logs:CreateLogGroup | CloudWatch Logs | Create log groups |
| logs:CreateLogStream | CloudWatch Logs | Create log streams |
| logs:PutLogEvents | CloudWatch Logs | Write log events |
| xray:PutTraceSegments | X-Ray | Tracing data |
| kms:Decrypt | KMS Key | DynamoDB encryption |

### Bedrock Agent Configuration

| Property | Value |
|----------|-------|
| Agent Name | buffett-dev-followup |
| Foundation Model | Claude Haiku 4.5 |
| Agent Alias | TSTALIASID (routes to DRAFT) |
| Idle Session TTL | 1800 seconds (30 minutes) |
| Knowledge Base | Not associated |
| Guardrails | Inherited from platform |

---

## CI/CD Pipeline

The followup-action Lambda is included in the automated deployment pipeline:

### Build Triggers

| Trigger | Condition |
|---------|-----------|
| Path Change | Files modified in `chat-api/backend/lambda/followup_action/` |
| Manual Input | `build_followup_action: true` |
| Build All | `build_all_docker: true` |

### Deployment Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Detect Changes │───▶│  Build Docker   │───▶│  Push to ECR    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                      │
                                                      ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Terraform      │◀───│  Update Lambda  │◀───│  Tag with SHA   │
│  Apply          │    │  Image URI      │    │  and 'latest'   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Note:** Health check is skipped for this Lambda since it's a Bedrock action group handler (no HTTP endpoint).

---

## Usage Examples

### Example 1: Debt Analysis Question

**User:** "What's driving Apple's debt increase?"

**Agent Action:**
1. Calls `getMetricsHistory(ticker="AAPL", metric_type="debt_leverage")`
2. Calls `getReportSection(ticker="AAPL", section_id="11_debt")`

**Response:** "According to the Debt Assessment section, Apple's total debt increased from $108B to $112B over the past year. However, the debt-to-equity ratio remains low at 1.73 because retained earnings grew proportionally. The report rates Apple's debt profile as STRONG with 85% confidence."

### Example 2: Valuation Comparison

**User:** "Is Microsoft's valuation reasonable compared to growth?"

**Agent Action:**
1. Calls `getMetricsHistory(ticker="MSFT", metric_type="valuation")`
2. Calls `getReportSection(ticker="MSFT", section_id="08_valuation")`

**Response:** "Based on the report, Microsoft trades at a P/E of 32x with revenue growth of 14%. The PEG ratio (P/E divided by growth rate) is 2.3, which suggests the stock is moderately priced for its growth. The Valuation section rates this as NEUTRAL."

### Example 3: Risk Assessment

**User:** "What are the main risks for NVDA?"

**Agent Action:**
1. Calls `getReportSection(ticker="NVDA", section_id="14_bear")`
2. Calls `getReportSection(ticker="NVDA", section_id="15_warnings")`

**Response:** "The Bear Case section highlights three key risks: (1) AI demand normalization as hyperscaler capex moderates, (2) Increased competition from AMD and custom chips, (3) Geopolitical exposure to China restrictions. The Red Flags section also notes elevated valuation multiples."

---

## Monitoring & Observability

### CloudWatch Logs

| Log Group | Description |
|-----------|-------------|
| /aws/lambda/buffett-dev-followup-action | Lambda execution logs |

### X-Ray Tracing

X-Ray tracing is enabled for the followup-action Lambda, providing:
- Cold start latency analysis
- DynamoDB operation timing
- End-to-end request traces

### Recommended Alarms

| Alarm | Threshold | Description |
|-------|-----------|-------------|
| Error Rate | > 5% over 5 minutes | Lambda invocation errors |
| Duration | > 10 seconds | Slow execution |
| Throttling | > 0 over 1 minute | Concurrency issues |

---

## Future Enhancements

| Enhancement | Priority | Description |
|-------------|----------|-------------|
| Metrics History Implementation | High | Connect to financial-data-cache for historical data |
| Streaming Responses | Medium | Stream agent responses for better UX |
| Multi-Report Comparison | Medium | Compare metrics across multiple tickers |
| Conversation Memory | Low | Persist conversation history for returning users |
| Custom Guardrails | Low | Add investment-specific content filters |

---

## File Reference

| File | Purpose |
|------|---------|
| `chat-api/backend/lambda/followup_action/handler.py` | Lambda entry point, routing, and DecimalEncoder |
| `chat-api/backend/lambda/followup_action/services/report_service.py` | DynamoDB data access functions |
| `chat-api/backend/lambda/followup_action/Dockerfile` | Docker container definition |
| `chat-api/backend/lambda/investment_research/app.py` | Main API with /followup endpoint |
| `chat-api/backend/lambda/investment_research/services/followup_service.py` | Bedrock agent invocation and SSE streaming |
| `chat-api/backend/lambda/investment_research/services/streaming.py` | SSE event helper functions |
| `chat-api/terraform/modules/bedrock/schemas/followup_action.yaml` | OpenAPI schema for action group |
| `chat-api/terraform/modules/bedrock/prompts/followup_agent_v1.txt` | Agent instructions |
| `chat-api/terraform/modules/lambda/followup_action_docker.tf` | Terraform infrastructure for followup-action |
| `chat-api/terraform/modules/lambda/variables.tf` | Lambda module variables (table ARNs/names) |
| `chat-api/terraform/modules/dynamodb/outputs.tf` | DynamoDB module outputs |
| `chat-api/terraform/modules/bedrock/main.tf` | Bedrock agent configuration |
| `chat-api/terraform/environments/dev/main.tf` | Dev environment module composition |
| `frontend/src/contexts/ResearchContext.jsx` | Frontend SSE event handling |

---

## Known Issues & Fixes

This section documents issues encountered during integration and their resolutions.

---

### Issue 1: HTTP 422 Unprocessable Entity from /followup Endpoint

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** Critical (Blocked all follow-up functionality)

#### Symptoms
- Frontend received HTTP 422 error when submitting follow-up questions
- Error message: `"Input should be a valid dictionary or object to extract fields from"`
- The error showed the request body as a JSON string with escaped quotes instead of a parsed object

#### Root Cause
The API Gateway REST API was configured with `HTTP_PROXY` integration to route requests to the Lambda Function URL. This integration passes the request body as a **JSON-encoded string** rather than parsing it into a dictionary.

When FastAPI's Pydantic model tried to validate the request body:
```python
@app.post("/followup")
async def followup_question(request: FollowUpRequest):
```

It received a string like `"{\"ticker\":\"AAPL\",\"question\":\"...\"}"` instead of a parsed dict `{"ticker": "AAPL", "question": "..."}`.

#### Fix Applied
Modified `/followup` endpoint in `investment_research/app.py` to manually parse the raw request body with double-encoding detection:

```python
@app.post("/followup")
async def followup_question(raw_request: Request):
    raw_body = await raw_request.body()
    body_str = raw_body.decode("utf-8")
    body_data = json.loads(body_str)

    # Check if body is double-encoded (parsed result is a string)
    if isinstance(body_data, str):
        body_data = json.loads(body_data)

    # Validate with Pydantic model
    request = FollowUpRequest(**body_data)
```

**Files Modified:**
- `chat-api/backend/lambda/investment_research/app.py` (lines 298-343)

**Commit:** `fix(followup): add manual JSON parsing to handle double-encoded body from API Gateway`

---

### Issue 2: DynamoDB ResourceNotFoundException in followup-action Lambda

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** Critical (Blocked all follow-up functionality)

#### Symptoms
- After fixing Issue 1, follow-up requests returned HTTP 200 but displayed "Unknown error" in UI
- Bedrock agent invoked successfully but action group Lambda failed
- CloudWatch logs showed: `ResourceNotFoundException: Requested resource not found`

#### Root Cause
The followup-action Lambda's `report_service.py` was using the wrong environment variable for the DynamoDB table name:

```python
# WRONG - used non-existent table name
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_TABLE_V2', 'investment-reports-v2-dev')
```

The Lambda had **two similar environment variables** configured:
| Environment Variable | Value | Status |
|---------------------|-------|--------|
| `INVESTMENT_REPORTS_V2_TABLE` | `investment-reports-v2-dev` | Correct table |
| `INVESTMENT_REPORTS_TABLE_V2` | `buffett-dev-investment-reports-v2` | Non-existent table |

The code referenced `INVESTMENT_REPORTS_TABLE_V2` which pointed to a non-existent table.

#### Fix Applied
Changed the environment variable reference in `followup_action/services/report_service.py`:

```python
# CORRECT - uses the existing table
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
```

**Files Modified:**
- `chat-api/backend/lambda/followup_action/services/report_service.py` (line 20)

**Commit:** `fix(followup-action): use correct env var INVESTMENT_REPORTS_V2_TABLE`

---

### Issue 3: IAM Policy Table ARN Mismatch

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** Critical (Blocked DynamoDB access)

#### Symptoms
- followup-action Lambda invocations failed with AccessDeniedException
- CloudWatch logs showed permission denied errors for DynamoDB operations

#### Root Cause
The followup-action Lambda's IAM policy was granting DynamoDB access to the wrong table ARN. The policy used a pattern that resolved to `buffett-dev-investment-reports-v2`, but the actual DynamoDB table is named `investment-reports-v2-dev`.

```hcl
# WRONG - IAM policy pattern
Resource = "arn:aws:dynamodb:*:*:table/${var.project_name}-${var.environment}-investment-reports-v2"
# Resolved to: arn:aws:dynamodb:*:*:table/buffett-dev-investment-reports-v2

# CORRECT - Actual table name
# arn:aws:dynamodb:*:*:table/investment-reports-v2-dev
```

#### Fix Applied
Updated the Terraform Lambda module to accept table ARNs from the DynamoDB module outputs:

1. Added new variables in `modules/lambda/variables.tf`:
```hcl
variable "investment_reports_v2_table_arn" {
  description = "ARN of the investment reports v2 DynamoDB table"
  type        = string
  default     = ""
}
```

2. Updated IAM policy in `modules/lambda/followup_action_docker.tf`:
```hcl
Resource = var.investment_reports_v2_table_arn != "" ? [
  var.investment_reports_v2_table_arn,
  "${var.investment_reports_v2_table_arn}/index/*"
] : [
  "arn:aws:dynamodb:*:*:table/investment-reports-v2-*",
  "arn:aws:dynamodb:*:*:table/investment-reports-v2-*/index/*"
]
```

3. Pass table ARN from DynamoDB module in `environments/dev/main.tf`:
```hcl
investment_reports_v2_table_arn = module.dynamodb.investment_reports_v2_table_arn
```

**Files Modified:**
- `chat-api/terraform/modules/lambda/variables.tf`
- `chat-api/terraform/modules/lambda/followup_action_docker.tf`
- `chat-api/terraform/environments/dev/main.tf`

**Commit:** `fix(followup-action): use correct DynamoDB table ARN from module outputs`

---

### Issue 4: Decimal JSON Serialization Error

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** High (Blocked numeric data responses)

#### Symptoms
- Action group Lambda returned 500 errors when retrieving reports with numeric fields
- CloudWatch logs showed: `TypeError: Object of type Decimal is not JSON serializable`

#### Root Cause
DynamoDB returns numeric values as Python `Decimal` objects for precision. The standard `json.dumps()` function cannot serialize `Decimal` types.

```python
# FAILING - DynamoDB returns Decimal for numbers
item = {'word_count': Decimal('450'), 'confidence': Decimal('85')}
json.dumps(item)  # TypeError: Object of type Decimal is not JSON serializable
```

#### Fix Applied
Added a custom `DecimalEncoder` class in `followup_action/handler.py`:

```python
class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types from DynamoDB."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int or float as appropriate
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)
```

Updated all JSON serialization to use the encoder:
```python
json.dumps(result, cls=DecimalEncoder)
```

**Files Modified:**
- `chat-api/backend/lambda/followup_action/handler.py`

**Commit:** `fix(followup-action): add DecimalEncoder for DynamoDB numeric serialization`

---

### Issue 5: SSE Event Type Mismatch

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** Critical (Responses not displayed in UI)

#### Symptoms
- Follow-up requests returned HTTP 200 with streaming response
- Browser console showed: `Unknown SSE event: chunk`
- UI displayed "Unknown error" instead of the response content
- The response data was being received but not processed

#### Root Cause
The agent streaming path (`_stream_agent_response` function in `followup_service.py`) was emitting generic SSE event types (`chunk`, `complete`) but the frontend expected specific event types (`followup_start`, `followup_chunk`, `followup_end`).

```python
# WRONG - Generic event types
yield {'event': 'chunk', 'data': chunk_text}
yield {'event': 'complete', 'data': '{}'}

# CORRECT - Frontend expects these specific types
yield followup_start_event(message_id, ticker)
yield followup_chunk_event(message_id, chunk_text)
yield followup_end_event(message_id)
```

The frontend's SSE handler in `ResearchContext.jsx`:
```javascript
case 'followup_start':
  dispatch({ type: ACTIONS.FOLLOWUP_START, messageId: data.message_id });
  break;
case 'followup_chunk':
  dispatch({ type: ACTIONS.FOLLOWUP_CHUNK, messageId: data.message_id, text: data.text });
  break;
case 'followup_end':
  dispatch({ type: ACTIONS.FOLLOWUP_END, messageId: data.message_id });
  break;
default:
  console.warn('Unknown SSE event:', eventType, data);
```

#### Fix Applied
Updated `_stream_agent_response` in `followup_service.py` to use the correct SSE event helpers:

```python
async def _stream_agent_response(
    prompt: str,
    session_id: str,
    ticker: str
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Stream response from Bedrock Agent.

    Uses followup_* event types for frontend compatibility.
    """
    import uuid
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
```

Also updated the caller to pass the `ticker` parameter:
```python
async for event in _stream_agent_response(context_prompt, session_id, ticker):
    yield event
```

**Files Modified:**
- `chat-api/backend/lambda/investment_research/services/followup_service.py`

**Commit:** `fix(followup): use followup_* SSE events in agent streaming path`

---

### Issue 6: Environment Variable Table Name Construction

**Date Identified:** January 17, 2026
**Date Fixed:** January 17, 2026
**Severity:** High (Potential future deployment issues)

#### Symptoms
- Lambda environment variables used incorrectly constructed table names
- Pattern `${var.project_name}-${var.environment}-investment-reports-v2` resolved to `buffett-dev-investment-reports-v2`
- Actual table name is `investment-reports-v2-dev`

#### Root Cause
The Terraform configuration was constructing table names using a pattern that didn't match the actual DynamoDB table naming convention established in the `dynamodb` module.

```hcl
# WRONG - Constructed name pattern
environment {
  variables = {
    INVESTMENT_REPORTS_TABLE_V2 = "${var.project_name}-${var.environment}-investment-reports-v2"
    # Resolved to: buffett-dev-investment-reports-v2
  }
}

# CORRECT - Use actual table name from module output
environment {
  variables = {
    INVESTMENT_REPORTS_TABLE_V2 = var.investment_reports_v2_table_name
    # Resolved to: investment-reports-v2-dev
  }
}
```

#### Fix Applied
Updated Terraform to pass actual table names from DynamoDB module outputs:

1. Added new variables in `modules/lambda/variables.tf`:
```hcl
variable "investment_reports_v2_table_name" {
  description = "Name of the investment reports v2 DynamoDB table"
  type        = string
  default     = ""
}

variable "financial_data_cache_table_name" {
  description = "Name of the financial data cache DynamoDB table"
  type        = string
  default     = ""
}
```

2. Updated environment variables in `followup_action_docker.tf`:
```hcl
environment {
  variables = merge(
    var.common_env_vars,
    {
      INVESTMENT_REPORTS_TABLE_V2 = var.investment_reports_v2_table_name != "" ? var.investment_reports_v2_table_name : "investment-reports-v2-${var.environment}"
      FINANCIAL_DATA_CACHE_TABLE  = var.financial_data_cache_table_name != "" ? var.financial_data_cache_table_name : "financial-data-cache-${var.environment}"
      LOG_LEVEL                   = "INFO"
    }
  )
}
```

3. Pass table names from DynamoDB module in `environments/dev/main.tf`:
```hcl
investment_reports_v2_table_name = module.dynamodb.investment_reports_v2_table_name
financial_data_cache_table_name  = module.dynamodb.financial_data_cache_table_name
```

**Files Modified:**
- `chat-api/terraform/modules/lambda/variables.tf`
- `chat-api/terraform/modules/lambda/followup_action_docker.tf`
- `chat-api/terraform/environments/dev/main.tf`

**Commit:** `fix(followup-action): use correct DynamoDB table names from module outputs`

---

### Issue Resolution Summary

| Issue | Root Cause | Fix Location | Impact |
|-------|------------|--------------|--------|
| HTTP 422 | API Gateway HTTP_PROXY double-encodes JSON body | `investment_research/app.py` | All follow-up requests |
| DynamoDB not found | Wrong env var for table name | `followup_action/services/report_service.py` | Action group data retrieval |
| IAM Policy ARN | Table ARN pattern mismatch | `followup_action_docker.tf`, `main.tf` | DynamoDB access denied |
| Decimal serialization | json.dumps cannot serialize Decimal | `followup_action/handler.py` | Numeric data responses |
| SSE Event Types | Generic event types vs frontend expectations | `followup_service.py` | Response display in UI |
| Env Var Table Names | Constructed names didn't match actual tables | `followup_action_docker.tf`, `main.tf` | Table lookup failures |

#### Request Flow After Fixes

```
Frontend                API Gateway              Lambda (investment_research)
   │                        │                              │
   │  POST /followup        │                              │
   │  body: JSON object ────┼──> HTTP_PROXY integration ───┼──> raw body as string
   │                        │                              │
   │                        │                              │  Manual JSON parsing
   │                        │                              │  Double-encode check
   │                        │                              │  Pydantic validation ✓
   │                        │                              │
   │                        │                              ▼
   │                        │                         Bedrock Agent
   │                        │                              │
   │                        │                              │  InvokeAgent()
   │                        │                              │
   │                        │                              ▼
   │                        │                    followup-action Lambda
   │                        │                              │
   │                        │                              │  Correct table:
   │                        │                              │  investment-reports-v2-dev ✓
   │                        │                              │
   │                        │                              ▼
   │                        │                          DynamoDB
   │                        │                              │
   │  SSE stream ◄──────────┼◄─────────────────────────────┘
   │                        │
```

---

## Successful Integration Test

**Date:** January 17, 2026
**Test Environment:** Development (dev)
**Status:** ✅ PASSED

### Test Scenario

After resolving all six issues documented above, a comprehensive end-to-end test was conducted to verify the follow-up question functionality.

### Test Steps

1. **Load Investment Report**
   - Navigated to the Investment Research interface
   - Loaded the AAPL (Apple Inc.) investment report
   - Report rendered successfully with all sections and ratings

2. **Submit Follow-up Question**
   - Question: "What is Apple's debt to equity ratio?"
   - Submitted via the chat input at the bottom of the report

3. **Observe Response**
   - Network request returned HTTP 200
   - SSE stream initiated with `followup_start` event
   - Content streamed via `followup_chunk` events
   - Stream completed with `followup_end` event
   - Response displayed with Warren Buffett memoji avatar

### Test Results

**Response Content:**
The agent provided a comprehensive answer about Apple's debt position:

| Metric | Value |
|--------|-------|
| Total Debt | $112.4B |
| Cash & Short-term Investments | $54.7B |
| Net Debt | $57.7B |
| Debt-to-Equity Ratio | 1.73 |
| Debt Rating | STRONG |
| Confidence | 85% |

**Key Points from Response:**
- Detailed breakdown of Apple's debt structure
- Analysis of debt sustainability
- Comparison to historical levels
- Citation of specific report sections
- Proper value investing perspective (Buffett-style)

### UI Verification

| Component | Status |
|-----------|--------|
| Chat input field | ✅ Working |
| Send button | ✅ Working |
| Loading indicator | ✅ Displayed during streaming |
| Response bubble | ✅ Rendered with proper styling |
| Buffett memoji avatar | ✅ Displayed correctly |
| Markdown formatting | ✅ Tables and lists rendered |
| Streaming effect | ✅ Typewriter-style text appearance |

### Network Verification

| Checkpoint | Status |
|------------|--------|
| POST /followup request | ✅ HTTP 200 |
| JSON body parsing | ✅ No 422 errors |
| SSE stream established | ✅ Connected |
| followup_start event | ✅ Received |
| followup_chunk events | ✅ Multiple chunks received |
| followup_end event | ✅ Stream completed |
| No console errors | ✅ Clean console |

### Performance Metrics

| Metric | Value |
|--------|-------|
| Time to First Byte (TTFB) | ~1.2s |
| Total Response Time | ~4.5s |
| Number of Chunks | 12 |
| Response Length | ~650 words |

### Screenshot Evidence

The test was conducted using Chrome DevTools MCP integration, which provided:
- Page snapshots for UI verification
- Network request inspection
- Console log monitoring
- Element interaction automation

### Conclusion

The follow-up question functionality is fully operational. All six issues identified during integration have been resolved, and the system correctly:

1. ✅ Parses JSON request bodies (including double-encoded payloads)
2. ✅ Connects to the correct DynamoDB table
3. ✅ Has proper IAM permissions for data access
4. ✅ Serializes Decimal values to JSON
5. ✅ Emits correct SSE event types for frontend consumption
6. ✅ Uses accurate table names from Terraform module outputs

The agent provides contextual, data-driven responses about investment reports, maintaining the Warren Buffett-inspired value investing perspective as intended.

---

## Token Usage Analysis & Optimization Report

**Analysis Date:** January 19, 2026
**Queries Analyzed:** 2 real-world follow-up questions via Chrome DevTools MCP

This section provides detailed analysis of the JSON payloads the Bedrock agent receives and the corresponding token consumption, with optimization recommendations.

---

### Test Queries Analyzed

| Query | Question | Session ID |
|-------|----------|------------|
| Q1 | "What is Apple's revenue growth trend?" | AAPL_20260119231613 |
| Q2 | "What is Apple's debt situation?" | AAPL_20260119231632 |

---

### Query 1: Revenue Growth Analysis

#### Bedrock Agent Input

```json
{
  "inputText": "\nThe user is asking about investment report for AAPL.\n\nUser question: What is Apple's revenue growth trend?\n\nUse your available tools to:\n1. Retrieve relevant report sections if needed\n2. Get ratings and metrics data\n3. Provide a helpful, data-backed answer\n",
  "enableTrace": false
}
```

**Input Text Size:** 306 bytes (~75 tokens)

#### Agent's Tool Selection Decision

The agent autonomously decided to make **2 parallel tool calls**:

| Tool Call | API Path | Parameters | Rationale |
|-----------|----------|------------|-----------|
| 1 | `/getMetricsHistory` | `metric_type: "revenue_profit"`, `quarters: 20`, `ticker: "AAPL"` | Historical data for trend analysis |
| 2 | `/getReportSection` | `section_id: "06_growth"`, `ticker: "AAPL"` | Pre-written narrative analysis |

#### Action Group Payload (Tool Call 1 - Metrics History)

```json
{
  "messageVersion": "1.0",
  "parameters": [],
  "sessionAttributes": {},
  "promptSessionAttributes": {},
  "sessionId": "AAPL_20260119231613",
  "agent": {
    "name": "buffett-dev-followup",
    "version": "DRAFT",
    "id": "LWY2A9T2DQ",
    "alias": "TSTALIASID"
  },
  "actionGroup": "ReportResearch",
  "inputText": "\nThe user is asking about investment report for AAPL.\n\nUser question: What is Apple's revenue growth trend?\n\nUse your available tools to:\n1. Retrieve relevant report sections if needed\n2. Get ratings and metrics data\n3. Provide a helpful, data-backed answer\n",
  "httpMethod": "POST",
  "apiPath": "/getMetricsHistory",
  "requestBody": {
    "content": {
      "application/json": {
        "properties": [
          {"name": "metric_type", "type": "string", "value": "revenue_profit"},
          {"name": "quarters", "type": "integer", "value": "20"},
          {"name": "ticker", "type": "string", "value": "AAPL"}
        ]
      }
    }
  }
}
```

#### Data Retrieved

**Metrics History Response (revenue_profit category):**

| Metric | Data Type | 20 Quarters | Example Values (Q3 2025) |
|--------|-----------|-------------|--------------------------|
| revenue | currency | ✓ | $102,466,000,000 |
| net_income | currency | ✓ | $27,466,000,000 |
| gross_profit | currency | ✓ | $48,341,000,000 |
| operating_income | currency | ✓ | $32,427,000,000 |
| ebitda | currency | ✓ | $35,931,000,000 |
| eps | decimal | ✓ | $1.85 |
| gross_margin | percentage | ✓ | 47.2% |
| operating_margin | percentage | ✓ | 31.6% |
| net_margin | percentage | ✓ | 26.8% |
| roe | percentage | ✓ | 149% |
| revenue_growth_yoy | percentage | ✓ | 7.9% |
| revenue_growth_qoq | percentage | ✓ | 9% |
| net_income_growth_yoy | percentage | ✓ | 86.4% |
| eps_growth_yoy | percentage | ✓ | 90.7% |
| gross_margin_change_1yr | percentage | ✓ | 1.0% |
| operating_margin_change_1yr | percentage | ✓ | 0.4% |
| net_margin_change_1yr | percentage | ✓ | 11.3% |
| is_margin_expanding | boolean | ✓ | 1 (true) |

**Total Metrics Retrieved:** 331 individual data points (18 metrics × ~18-20 quarters with data)

**Report Section Response (06_growth):**

```
For a company this massive, any growth at all is impressive. Apple just pushed
past $416 billion in annual revenue, up from $391B last year — that's adding
roughly the entire revenue of a mid-sized Fortune 500 company in a single year.

| Year | Sales | Growth Rate | The Trend |
|------|-------|-------------|-----------|
| 2025 | $416.2B | +6.4% | Accelerating |
| 2024 | $391.0B | +2.0% | Slow year |
| 2023 | $383.3B | -2.8% | Dip |
| 2022 | $394.3B | +7.8% | Strong |
| 2021 | $365.8B | +33.3% | COVID boom |

... (205 words total)
```

#### Query 1 Token Breakdown

| Component | Estimated Tokens | Notes |
|-----------|------------------|-------|
| Agent instruction prompt | ~800 | Base system prompt |
| Input text (question) | ~75 | User question + context |
| Metrics JSON response | ~3,200 | 20 quarters × 18 metrics |
| Section content | ~300 | 205 words of markdown |
| **Total Input Tokens** | **~4,375** | |
| Output response | ~600 | Agent's formatted answer |
| **Total Tokens** | **~4,975** | |

---

### Query 2: Debt Situation Analysis

#### Agent's Tool Selection Decision

The agent decided to make **3 parallel tool calls**:

| Tool Call | API Path | Parameters | Rationale |
|-----------|----------|------------|-----------|
| 1 | `/getMetricsHistory` | `metric_type: "debt_leverage"`, `quarters: 20`, `ticker: "AAPL"` | Historical debt ratios |
| 2 | `/getReportRatings` | `ticker: "AAPL"` | Overall debt rating |
| 3 | `/getReportSection` | `section_id: "11_debt"`, `ticker: "AAPL"` | Pre-written debt analysis |

#### Action Group Payload (Tool Call 1 - Debt Metrics)

```json
{
  "messageVersion": "1.0",
  "sessionId": "AAPL_20260119231632",
  "agent": {"name": "buffett-dev-followup", "version": "DRAFT", "id": "LWY2A9T2DQ"},
  "actionGroup": "ReportResearch",
  "inputText": "...What is Apple's debt situation?...",
  "httpMethod": "POST",
  "apiPath": "/getMetricsHistory",
  "requestBody": {
    "content": {
      "application/json": {
        "properties": [
          {"name": "metric_type", "type": "string", "value": "debt_leverage"},
          {"name": "quarters", "type": "integer", "value": "20"},
          {"name": "ticker", "type": "string", "value": "AAPL"}
        ]
      }
    }
  }
}
```

#### Data Retrieved

**Metrics History Response (debt_leverage category):**

| Metric | Data Type | 20 Quarters | Example Values (Q3 2025) |
|--------|-----------|-------------|--------------------------|
| short_term_debt | currency | ✓ | $20,329,000,000 |
| long_term_debt | currency | ✓ | $92,048,000,000 |
| debt_to_equity | ratio | ✓ | 1.52 |
| debt_to_assets | ratio | ✓ | 0.31 |
| debt_to_equity_change_1yr | percentage | ✓ | -0.57 |
| debt_to_equity_change_2yr | percentage | ✓ | -0.47 |
| current_ratio | ratio | ✓ | 0.89 |
| quick_ratio | ratio | ✓ | 0.33 |
| current_ratio_change_1yr | percentage | ✓ | 0.02 |
| net_debt_to_ebitda | ratio | ✓ | 2.19 |
| interest_coverage | currency | ✓ | $32,427,000,000 |
| interest_expense | currency | ✓ | $0 |
| fcf_to_debt | ratio | ✓ | 0.24 |
| short_term_debt_pct | percentage | ✓ | 18.1% |
| equity_multiplier | ratio | ✓ | 4.87 |
| is_deleveraging | boolean | ✓ | 1 (true) |

**Total Metrics Retrieved:** 300 individual data points (15 metrics × 20 quarters)

**Ratings JSON Response:**

```json
{
  "debt": {
    "rating": "4/5",
    "confidence": "High",
    "short_term_debt_pct": 18,
    "key_factors": [
      "$57.7B net debt is manageable",
      "Only 18% due within 12 months",
      "Could pay all debt in 1 year of cash flow"
    ]
  }
}
```

**Report Section Response (11_debt):** 231 words

#### Query 2 Token Breakdown

| Component | Estimated Tokens | Notes |
|-----------|------------------|-------|
| Agent instruction prompt | ~800 | Base system prompt |
| Input text (question) | ~70 | User question + context |
| Metrics JSON response | ~2,800 | 20 quarters × 15 metrics |
| Ratings JSON | ~150 | Debt rating + key factors |
| Section content | ~350 | 231 words of markdown |
| **Total Input Tokens** | **~4,170** | |
| Output response | ~650 | Agent's formatted answer |
| **Total Tokens** | **~4,820** | |

---

### Token Usage Summary

| Query | Tool Calls | Metrics Retrieved | Input Tokens | Output Tokens | Total |
|-------|------------|-------------------|--------------|---------------|-------|
| Revenue Growth | 2 | 331 | ~4,375 | ~600 | ~4,975 |
| Debt Situation | 3 | 300 | ~4,170 | ~650 | ~4,820 |
| **Average** | **2.5** | **315** | **~4,270** | **~625** | **~4,900** |

#### Cost Estimate (Claude Haiku 4.5)

| Metric | Rate | Per Query | Monthly (1000 queries) |
|--------|------|-----------|------------------------|
| Input Tokens | $0.0008/1K | $0.0034 | $3.40 |
| Output Tokens | $0.004/1K | $0.0025 | $2.50 |
| **Total** | | **$0.0059** | **$5.90** |

---

### Optimization Opportunities

#### 🔴 High Impact Opportunities

##### 1. Reduce Quarters Returned by Default

**Current:** 20 quarters always returned
**Issue:** Most questions don't need 5 years of history

**Recommendation:**
```python
# In report_service.py - getMetricsHistory
def get_metrics_history(ticker: str, metric_type: str = 'all', quarters: int = 8) -> Dict:
    """
    Default to 8 quarters (2 years) instead of 20 quarters (5 years).
    The agent can request more via the 'quarters' parameter if needed.
    """
```

**Savings:** ~60% reduction in metrics payload (~1,800 tokens saved per query)

##### 2. Add Metric Summarization Option

**Current:** Returns raw values for all quarters
**Issue:** Agent receives raw data and must process it

**Recommendation:** Add a `summarize` parameter that returns computed aggregates:

```python
# New response format with summarize=true
{
  "ticker": "AAPL",
  "summary": {
    "revenue_profit": {
      "latest_quarter": {"revenue": 102466000000, "net_margin": 26.8},
      "yoy_change": {"revenue": 7.9, "net_margin": 11.3},
      "5yr_cagr": {"revenue": 8.2, "net_income": 12.1},
      "trend": "accelerating"
    }
  }
}
```

**Savings:** ~80% reduction when summary is sufficient (~3,200 tokens saved)

##### 3. Semantic Metric Selection

**Current:** Returns all metrics in a category
**Issue:** Agent receives metrics it doesn't use

**Recommendation:** Add question-aware metric filtering in the action group:

```python
# In handler.py - analyze question to select relevant metrics
QUESTION_METRIC_MAP = {
    "revenue": ["revenue", "revenue_growth_yoy", "revenue_growth_qoq"],
    "profit": ["net_income", "net_margin", "gross_margin", "operating_margin"],
    "debt": ["debt_to_equity", "net_debt_to_ebitda", "interest_coverage"],
    "growth": ["revenue_growth_yoy", "eps_growth_yoy", "is_margin_expanding"],
}
```

**Savings:** ~50% reduction by returning only relevant metrics

---

#### 🟡 Medium Impact Opportunities

##### 4. Compress Large Numbers

**Current:** Numbers stored as full precision (`102466000000`)
**Issue:** 12-digit numbers waste tokens

**Recommendation:** Format as human-readable strings:

```python
# Before
{"revenue": 102466000000}

# After
{"revenue": "102.5B", "revenue_raw": 102466000000}
```

**Savings:** ~15% reduction in numeric token overhead

##### 5. Cache Section Content in Agent Memory

**Current:** Section content fetched on every related question
**Issue:** Same content retrieved repeatedly in a session

**Recommendation:** Use Bedrock agent session attributes:

```python
# In followup_service.py
response = bedrock_agent_runtime.invoke_agent(
    agentId=FOLLOWUP_AGENT_ID,
    sessionId=session_id,
    inputText=prompt,
    sessionAttributes={
        "cached_sections": json.dumps(["06_growth", "11_debt"]),
        "section_06_growth_hash": "abc123"
    }
)
```

**Savings:** Eliminates redundant section fetches (~300 tokens per repeated access)

##### 6. Differential Metrics Response

**Current:** Full dataset on every query
**Issue:** Follow-up questions often need incremental data

**Recommendation:** Track what was sent in session, only send new data:

```python
# First query: Full debt metrics
# Second query about debt: "No new data needed - using cached response"
```

**Savings:** ~90% reduction on follow-up questions about same topic

---

#### 🟢 Low Impact / Future Opportunities

##### 7. Binary Protocol for Metrics

Replace JSON with more compact binary format (MessagePack, Protocol Buffers) for internal Lambda-to-Lambda communication.

##### 8. Tiered Response Detail

Add a `detail_level` parameter: `summary`, `standard`, `detailed`

##### 9. Precomputed Trend Narratives

Store trend descriptions alongside raw data to reduce agent processing.

---

### Recommended Implementation Roadmap

| Priority | Optimization | Effort | Token Savings | Cost Savings/Month |
|----------|--------------|--------|---------------|-------------------|
| P0 | Reduce default quarters to 8 | Low | ~1,800/query | ~$2.10 |
| P1 | Add `summarize` parameter | Medium | ~3,200/query | ~$3.70 |
| P2 | Semantic metric selection | Medium | ~1,600/query | ~$1.85 |
| P3 | Number compression | Low | ~600/query | ~$0.70 |
| P4 | Session-based caching | High | Variable | Variable |

**Total Potential Savings:** ~60-70% reduction in input tokens

---

### Monitoring Recommendations

1. **Add Token Tracking to Logs:**
```python
logger.info(f"Metrics response size: {len(json.dumps(result))} bytes, ~{len(json.dumps(result))//4} tokens")
```

2. **Create CloudWatch Metrics:**
   - `FollowupAgent/InputTokens`
   - `FollowupAgent/OutputTokens`
   - `FollowupAgent/ToolCallCount`
   - `FollowupAgent/MetricsRetrieved`

3. **Set Up Alerts:**
   - Alert when average tokens per query > 6,000
   - Alert when tool calls per query > 4

---

## Conclusion

The Follow-up Research Agent represents a significant enhancement to the Deep Value Insights platform, enabling natural language interaction with investment research data. By leveraging AWS Bedrock's agent framework with action groups, the system provides:

1. **Intelligent Data Retrieval** - Agent determines which data to fetch based on user questions
2. **Consistent Response Format** - Bedrock handles formatting and conversation flow
3. **Scalable Architecture** - Docker-based Lambda with DynamoDB provides low-latency, high-availability
4. **Cost Efficiency** - Claude Haiku 4.5 offers quality responses at reduced cost
5. **Maintainability** - Clear separation between agent logic, action handlers, and data access

The token analysis reveals that the current implementation uses approximately **4,900 tokens per query** at an estimated cost of **$0.006 per query** ($5.90 per 1,000 queries). Implementing the recommended optimizations could reduce this by **60-70%**, bringing costs to approximately **$2.00 per 1,000 queries**.

The system is now deployed and ready for integration with the frontend investment research interface.
