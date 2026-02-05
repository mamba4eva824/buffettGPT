# Follow-up Research Agent

The Follow-up Research Agent enables users to ask natural language questions about investment reports. It uses Amazon Bedrock's Converse API with tool use orchestration to retrieve real data from DynamoDB.

## Overview

| Property | Value |
|----------|-------|
| **Model** | Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) |
| **API** | Bedrock Converse API with toolConfig |
| **Lambda** | `buffett-dev-analysis-followup` |
| **Status** | Production Ready |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERFACE                                     │
│                    (Investment Research Frontend)                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ POST /research/followup
                                    │ Authorization: Bearer <JWT>
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     API GATEWAY (REST API)                                   │
│                    t5wvlwfo5b                                                │
│                    HTTP_PROXY → Lambda Function URL                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│               ANALYSIS FOLLOWUP LAMBDA                                       │
│               (Orchestration Loop)                                           │
│                                                                              │
│   1. Validate JWT token                                                      │
│   2. Check token usage limit                                                 │
│   3. Save user message to DynamoDB                                          │
│   4. Call Bedrock Converse API with tools                                   │
│   5. If tool_use → execute tool → loop back to step 4                       │
│   6. If end_turn → save response & record tokens                            │
│   7. Return response                                                         │
└─────────────────────────────────────────────────────────────────────────────┘
          │                               │
          │ converse() API                │ Tool Execution
          ▼                               ▼
┌─────────────────────┐     ┌─────────────────────────────────────────────────┐
│   BEDROCK RUNTIME   │     │                DYNAMODB TABLES                   │
│                     │     │                                                  │
│   Claude Haiku 4.5  │     │  • investment-reports-v2-dev (report sections) │
│                     │     │  • metrics-history-dev (financial metrics)      │
│   Tools:            │     │  • buffett-dev-chat-messages (persistence)      │
│   - getReportSection│     │  • buffett-dev-token-usage (token tracking)     │
│   - getReportRatings│     │                                                  │
│   - getMetricsHistory│    └─────────────────────────────────────────────────┘
│   - getAvailableRpts│
└─────────────────────┘
```

## Business Value

| Benefit | Description |
|---------|-------------|
| **Enhanced User Engagement** | Users ask natural language questions about reports |
| **Data-Backed Responses** | Agent retrieves real data from DynamoDB, not training data |
| **Reduced Cognitive Load** | Agent handles data retrieval and formatting |
| **Contextual Responses** | Maintains conversation context for multi-turn interactions |
| **Cost-Effective** | Claude Haiku 4.5 provides quality at ~$0.006 per query |

## Tool Definitions

### getReportSection

Retrieves a specific section from an investment report.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| ticker | string | Yes | Stock ticker symbol (e.g., AAPL) |
| section_id | enum | Yes | Section identifier |

**Available Sections:**

| Section ID | Description | Part |
|------------|-------------|------|
| 01_executive_summary | Overview with key findings | Part 1 |
| 06_growth | Revenue and earnings growth | Part 2 |
| 07_profit | Profitability and margins | Part 2 |
| 08_valuation | Valuation metrics | Part 2 |
| 09_earnings | Earnings quality | Part 2 |
| 10_cashflow | Cash flow analysis | Part 2 |
| 11_debt | Debt and leverage | Part 2 |
| 12_dilution | Shareholder dilution | Part 2 |
| 13_bull | Bull case | Part 3 |
| 14_bear | Bear case | Part 3 |
| 15_warnings | Red flags | Part 3 |
| 16_vibe | Overall sentiment | Part 3 |
| 17_realtalk | Bottom line | Part 3 |

**Response:**
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

### getReportRatings

Retrieves all investment ratings for a ticker.

**Response:**
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

### getMetricsHistory

Retrieves historical financial metrics for trend analysis.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| ticker | string | Yes | - | Stock ticker symbol |
| metric_type | enum | No | "all" | Category of metrics |
| quarters | integer | No | 20 | Quarters of history |

**Metric Categories:**

| Category | Key Metrics |
|----------|-------------|
| revenue_profit | revenue, netIncome, gross_margin, operating_margin, eps |
| cashflow | operatingCashFlow, freeCashFlow, fcf_margin |
| balance_sheet | totalDebt, cashAndCashEquivalents, netDebt |
| debt_leverage | debt_to_equity, debt_to_assets, interest_coverage |
| earnings_quality | gaap_net_income, stock_based_compensation |
| dilution | basic_shares_outstanding, diluted_shares_outstanding |
| valuation | pe_ratio, pb_ratio, ev_to_ebitda, roe, roic |

### getAvailableReports

Lists all available investment reports in the database (no parameters).

## API Usage

### Follow-up Question Request

```http
POST /research/followup
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "session_id": "710fd641-b79b-4f32-a87f-c76a1826ff69",
  "ticker": "AAPL",
  "question": "What is Apple's debt to equity ratio?",
  "agent_type": "debt"
}
```

### Non-Streaming Response (API Gateway)

```json
{
  "success": true,
  "response": "Based on the investment report, Apple's debt-to-equity ratio is 1.73...",
  "input_tokens": 3089,
  "output_tokens": 209,
  "turns": 2
}
```

### Streaming Response (Function URL - SSE)

```
event: followup_start
data: {"type": "followup_start", "message_id": "uuid", "ticker": "AAPL"}

event: followup_chunk
data: {"type": "followup_chunk", "message_id": "uuid", "text": "Based on the investment report..."}

event: followup_chunk
data: {"type": "followup_chunk", "message_id": "uuid", "text": "Apple's debt-to-equity ratio is 1.73..."}

event: followup_end
data: {"type": "followup_end", "message_id": "uuid"}
```

## Message Persistence

Follow-up messages are persisted to DynamoDB for conversation history:

### Backend Persistence (Lambda)

1. **User message saved** immediately after JWT validation
2. **Assistant message saved** after orchestration completes
3. **Token usage recorded** with input/output counts

### Message Schema

**User Question:**
```json
{
  "_type": "followup_question",
  "ticker": "HD",
  "question": "What are the main risks?",
  "timestamp": "2026-01-27T19:32:11.869Z"
}
```

**Assistant Response:**
```json
{
  "_type": "followup_response",
  "ticker": "HD",
  "response": "Home Depot faces several risks...",
  "timestamp": "2026-01-27T19:32:20.226Z"
}
```

## Performance Metrics

| Metric | Typical Value |
|--------|---------------|
| Cold Start | ~800 ms |
| Total Execution | 4-8 seconds |
| Orchestration Turns | 1-3 |
| Tokens per Query | ~4,000-5,000 |

### Cost Estimate

| Metric | Rate | Per Query | Monthly (1000 queries) |
|--------|------|-----------|------------------------|
| Input Tokens | $0.0008/1K | $0.0034 | $3.40 |
| Output Tokens | $0.004/1K | $0.0025 | $2.50 |
| **Total** | | **$0.0059** | **$5.90** |

## Error Handling

| Error | HTTP Code | Cause |
|-------|-----------|-------|
| Invalid/expired JWT | 401 | Token verification failed |
| Token limit exceeded | 429 | Monthly limit reached |
| Tool execution failure | 200 | Error in tool result, model retries |
| Bedrock API error | 500 | Model unavailable |

## Health Check

The Lambda exposes a health endpoint for CI/CD smoke tests:

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "analysis-followup",
  "environment": "dev",
  "model_id": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
  "timestamp": "2026-01-31T10:30:00.000Z"
}
```

## Recent Changes

### January 31, 2026 - AGENT_CONFIG Removal

Removed legacy blocking code that checked for deleted prediction ensemble agent IDs. The Lambda now directly uses the Converse API orchestration loop.

### January 30, 2026 - Health Endpoint

Added `/health` endpoint for CI/CD smoke tests (no JWT required).

### January 29, 2026 - API Gateway Detection

Fixed Lambda to correctly detect Function URL vs API Gateway invocation and return appropriate response format.

## Related Documentation

- [Technical Details](../../chat-api/backend/investment_research/docs/FOLLOWUP_AGENT.md)
- [System Architecture](../architecture/system-overview.md)
- [API Routes](../api/routes.md)
- [Token Limiter](token-limiter.md)
