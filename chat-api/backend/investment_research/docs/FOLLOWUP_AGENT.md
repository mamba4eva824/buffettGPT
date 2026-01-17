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
| `chat-api/backend/lambda/followup_action/handler.py` | Lambda entry point and routing |
| `chat-api/backend/lambda/followup_action/services/report_service.py` | DynamoDB data access functions |
| `chat-api/backend/lambda/followup_action/Dockerfile` | Docker container definition |
| `chat-api/terraform/modules/bedrock/schemas/followup_action.yaml` | OpenAPI schema for action group |
| `chat-api/terraform/modules/bedrock/prompts/followup_agent_v1.txt` | Agent instructions |
| `chat-api/terraform/modules/lambda/followup_action_docker.tf` | Terraform infrastructure |
| `chat-api/terraform/modules/bedrock/main.tf` | Bedrock agent configuration |

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

### Issue Resolution Summary

| Issue | Root Cause | Fix Location | Impact |
|-------|------------|--------------|--------|
| HTTP 422 | API Gateway HTTP_PROXY double-encodes JSON body | `investment_research/app.py` | All follow-up requests |
| DynamoDB not found | Wrong env var for table name | `followup_action/services/report_service.py` | Action group data retrieval |

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

## Conclusion

The Follow-up Research Agent represents a significant enhancement to the Deep Value Insights platform, enabling natural language interaction with investment research data. By leveraging AWS Bedrock's agent framework with action groups, the system provides:

1. **Intelligent Data Retrieval** - Agent determines which data to fetch based on user questions
2. **Consistent Response Format** - Bedrock handles formatting and conversation flow
3. **Scalable Architecture** - Docker-based Lambda with DynamoDB provides low-latency, high-availability
4. **Cost Efficiency** - Claude Haiku 4.5 offers quality responses at reduced cost
5. **Maintainability** - Clear separation between agent logic, action handlers, and data access

The system is now deployed and ready for integration with the frontend investment research interface.
