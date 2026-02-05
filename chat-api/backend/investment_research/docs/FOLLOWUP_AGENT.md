# Follow-Up Agent - Technical Documentation

**Document Version:** 2.0
**Last Updated:** January 31, 2026
**Status:** Production (dev environment)

---

## Executive Summary

The Follow-Up Agent enables users to ask natural language questions about investment reports. The system uses Amazon Bedrock's Converse API with tool use orchestration, retrieving real data from DynamoDB rather than relying on model training data.

### Key Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Frontend | React (localhost:3000) | User interface for Q&A |
| API Gateway | REST API (t5wvlwfo5b) | JWT authentication, routing |
| Lambda | `buffett-dev-analysis-followup` | Orchestration, tool execution |
| AI Model | Claude Haiku 4.5 | Natural language understanding |
| Data Stores | DynamoDB (4 tables) | Reports, metrics, messages, tokens |

### Model Configuration

| Property | Value |
|----------|-------|
| Model ID | `us.anthropic.claude-haiku-4-5-20251001-v1:0` |
| API | Bedrock Converse API with toolConfig |
| Max Turns | 10 (per orchestration loop) |
| Streaming | Supported via Function URL |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERACTION LAYER                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────────┐                                                               │
│   │   Browser    │                                                               │
│   │ localhost:3000│                                                              │
│   └──────┬───────┘                                                               │
│          │ POST /research/followup                                               │
│          │ Headers: Authorization: Bearer <JWT>                                  │
│          │ Body: { session_id, question, ticker, agent_type }                    │
│          ▼                                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                              API GATEWAY LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────┐              │
│   │          REST API: buffett-dev-analysis-api                   │              │
│   │                    (t5wvlwfo5b)                                │              │
│   │                                                                │              │
│   │   Route: POST /research/followup                              │              │
│   │   Integration: HTTP_PROXY → Lambda Function URL               │              │
│   │   Auth: JWT verified via x-amzn-apigateway-api-id header     │              │
│   └──────────────────────┬───────────────────────────────────────┘              │
│                          │                                                       │
│                          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────────┐              │
│   │        Lambda Function URL (HTTP_PROXY passthrough)           │              │
│   │   https://buef5xunrsdmsyrhdpb37nyuuu0uhglg.lambda-url...     │              │
│   └──────────────────────┬───────────────────────────────────────┘              │
│                          │                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                           COMPUTE LAYER (LAMBDA)                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                          │                                                       │
│                          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────────┐              │
│   │          buffett-dev-analysis-followup Lambda                 │              │
│   │                                                                │              │
│   │   Handler: analysis_followup.lambda_handler                   │              │
│   │   Runtime: Python 3.11                                         │              │
│   │   Memory: 256 MB                                               │              │
│   │   Timeout: 29 seconds                                          │              │
│   │                                                                │              │
│   │   Endpoints:                                                   │              │
│   │   ├── GET /health          → Health check (no auth)           │              │
│   │   └── POST /research/followup → Follow-up Q&A (JWT required) │              │
│   │                                                                │              │
│   │   ┌────────────────────────────────────────────────────────┐  │              │
│   │   │              ORCHESTRATION LOOP                         │  │              │
│   │   │                                                         │  │              │
│   │   │   1. Validate JWT token                                 │  │              │
│   │   │   2. Check token usage limit                            │  │              │
│   │   │   3. Save user message to DynamoDB                      │  │              │
│   │   │   4. Call Bedrock Converse API with tools               │  │              │
│   │   │   5. If tool_use → execute tool → loop back             │  │              │
│   │   │   6. If end_turn → save response & record tokens        │  │              │
│   │   │   7. Return response to user                            │  │              │
│   │   └────────────────────────────────────────────────────────┘  │              │
│   │                                                                │              │
│   │   Tool Executor Module:                                        │              │
│   │   ├── getReportSection(ticker, section_id)                    │              │
│   │   ├── getReportRatings(ticker)                                │              │
│   │   ├── getMetricsHistory(ticker, metric_type, quarters)        │              │
│   │   └── getAvailableReports()                                   │              │
│   └──────────────────────┬───────────────────────────────────────┘              │
│                          │                                                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                              AI MODEL LAYER                                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                          │                                                       │
│                          ▼                                                       │
│   ┌──────────────────────────────────────────────────────────────┐              │
│   │              Amazon Bedrock Runtime                           │              │
│   │                                                                │              │
│   │   Model: us.anthropic.claude-haiku-4-5-20251001-v1:0         │              │
│   │   API: Converse API with toolConfig                           │              │
│   │                                                                │              │
│   │   Available Tools:                                             │              │
│   │   ┌──────────────────┬─────────────────────────────────────┐  │              │
│   │   │ getReportSection │ Retrieve report sections from DB    │  │              │
│   │   │ getReportRatings │ Get investment ratings/verdict      │  │              │
│   │   │ getMetricsHistory│ Query historical financial metrics  │  │              │
│   │   │ getAvailableRpts │ List all available reports          │  │              │
│   │   └──────────────────┴─────────────────────────────────────┘  │              │
│   └──────────────────────────────────────────────────────────────┘              │
│                                                                                  │
├─────────────────────────────────────────────────────────────────────────────────┤
│                              DATA LAYER (DYNAMODB)                               │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────────────────┐  ┌─────────────────────────────────┐      │
│   │  investment-reports-v2-dev      │  │  metrics-history-dev            │      │
│   │                                  │  │                                  │      │
│   │  PK: ticker (String)            │  │  PK: ticker (String)            │      │
│   │  SK: section_id (String)        │  │  SK: fiscal_date (String)       │      │
│   │                                  │  │                                  │      │
│   │  Sections:                       │  │  Categories:                     │      │
│   │  - 00_executive (ratings)       │  │  - revenue_profit                │      │
│   │  - 01_executive_summary         │  │  - cashflow                      │      │
│   │  - 06_growth                    │  │  - balance_sheet                 │      │
│   │  - 07_profit (margins)          │  │  - debt_leverage                 │      │
│   │  - 08_valuation                 │  │  - earnings_quality              │      │
│   │  - 10_cashflow                  │  │  - dilution                      │      │
│   │  - 11_debt                      │  │  - valuation                     │      │
│   │  - 13_bull, 14_bear, 15_warnings│  │                                  │      │
│   └─────────────────────────────────┘  └─────────────────────────────────┘      │
│                                                                                  │
│   ┌─────────────────────────────────┐  ┌─────────────────────────────────┐      │
│   │  buffett-dev-chat-messages      │  │  buffett-dev-token-usage        │      │
│   │                                  │  │                                  │      │
│   │  PK: session_id (String)        │  │  PK: user_id (String)           │      │
│   │  SK: message_id (String)        │  │  SK: month (String)             │      │
│   │                                  │  │                                  │      │
│   │  Fields:                         │  │  Fields:                         │      │
│   │  - role (user/assistant)        │  │  - total_tokens (Number)        │      │
│   │  - content (String)             │  │  - token_limit (Number)         │      │
│   │  - timestamp (String)           │  │  - input_tokens (Number)        │      │
│   │  - ticker, agent_type           │  │  - output_tokens (Number)       │      │
│   └─────────────────────────────────┘  └─────────────────────────────────┘      │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow

### Non-Streaming Path (API Gateway)

```
┌──────┐          ┌───────────┐       ┌────────────┐      ┌─────────┐      ┌──────────┐
│ User │          │API Gateway│       │  Lambda    │      │ Bedrock │      │ DynamoDB │
└──┬───┘          └─────┬─────┘       └──────┬─────┘      └────┬────┘      └────┬─────┘
   │                    │                    │                 │                │
   │ POST /research/followup                 │                 │                │
   │ Authorization: Bearer <JWT>             │                 │                │
   │ {session_id, question, ticker}          │                 │                │
   │───────────────────>│                    │                 │                │
   │                    │                    │                 │                │
   │                    │ HTTP_PROXY         │                 │                │
   │                    │ (passthrough)      │                 │                │
   │                    │───────────────────>│                 │                │
   │                    │                    │                 │                │
   │                    │                    │ Validate JWT    │                │
   │                    │                    │ Check token limit│               │
   │                    │                    │─────────────────────────────────>│
   │                    │                    │<─────────────────────────────────│
   │                    │                    │                 │                │
   │                    │                    │ Save user msg   │                │
   │                    │                    │─────────────────────────────────>│
   │                    │                    │<─ chat-messages ────────────────│
   │                    │                    │                 │                │
   │                    │                    │ ═══════════════════════════════ │
   │                    │                    │ ║  ORCHESTRATION LOOP (Turn 1) ║ │
   │                    │                    │ ═══════════════════════════════ │
   │                    │                    │                 │                │
   │                    │                    │ Converse API    │                │
   │                    │                    │ + toolConfig    │                │
   │                    │                    │────────────────>│                │
   │                    │                    │                 │                │
   │                    │                    │<───────────────│                │
   │                    │                    │ stop_reason=tool_use             │
   │                    │                    │ tool: getReportSection           │
   │                    │                    │                 │                │
   │                    │                    │ Execute tool    │                │
   │                    │                    │─────────────────────────────────>│
   │                    │                    │<─ reports-v2 ───────────────────│
   │                    │                    │                 │                │
   │                    │                    │ ═══════════════════════════════ │
   │                    │                    │ ║  ORCHESTRATION LOOP (Turn 2) ║ │
   │                    │                    │ ═══════════════════════════════ │
   │                    │                    │                 │                │
   │                    │                    │ Converse API    │                │
   │                    │                    │ + tool results  │                │
   │                    │                    │────────────────>│                │
   │                    │                    │                 │                │
   │                    │                    │<───────────────│                │
   │                    │                    │ stop_reason=end_turn             │
   │                    │                    │ (final answer)  │                │
   │                    │                    │                 │                │
   │                    │                    │ Save assistant msg               │
   │                    │                    │─────────────────────────────────>│
   │                    │                    │<─ chat-messages ────────────────│
   │                    │                    │                 │                │
   │                    │                    │ Record token usage               │
   │                    │                    │─────────────────────────────────>│
   │                    │                    │<─ token-usage ──────────────────│
   │                    │                    │                 │                │
   │                    │<───────────────────│                 │                │
   │                    │   JSON Response    │                 │                │
   │<───────────────────│                    │                 │                │
   │   {answer, tokens} │                    │                 │                │
```

---

## Invocation Mode Detection

The Lambda automatically detects its invocation source and responds appropriately:

```python
# Detection logic in lambda_handler
is_function_url = 'http' in request_context
is_api_gateway = (
    event.get('httpMethod') or
    request_context.get('httpMethod') or
    headers.get('x-amzn-apigateway-api-id') or
    headers.get('X-Amzn-Apigateway-Api-Id')
)
```

| Invocation Source | Response Format | Streaming Support |
|-------------------|-----------------|-------------------|
| Lambda Function URL (direct) | Generator/SSE | Yes |
| API Gateway REST API | JSON with statusCode | No |

---

## Tool Definitions

The Lambda provides 4 tools to Bedrock via the Converse API:

### 1. getReportSection

Retrieves a specific section from an investment report.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | Yes | Stock ticker symbol (e.g., AAPL, MSFT) |
| `section_id` | enum | Yes | Section identifier (see table below) |

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

### 2. getReportRatings

Returns investment ratings and verdict for a ticker.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | Yes | Stock ticker symbol |

**Response includes:**
- Rating categories: growth, profitability, cashflow, debt, valuation
- Overall verdict: BUY, HOLD, AVOID
- Confidence scores: 0-100 scale

### 3. getMetricsHistory

Retrieves historical financial metrics for trend analysis.

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `ticker` | string | Yes | - | Stock ticker symbol |
| `metric_type` | enum | No | "all" | Category of metrics |
| `quarters` | integer | No | 20 | Quarters of history (max 40) |

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

### 4. getAvailableReports

Lists all available investment reports in the database.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| (none) | - | - | No parameters required |

---

## Message Persistence

### Overview

Follow-up conversations are persisted to DynamoDB so users can reload previous conversations and continue where they left off.

### Message Content Schema

#### User Question (`followup_question`)

```json
{
  "_type": "followup_question",
  "ticker": "HD",
  "question": "What are the main risks for Home Depot?",
  "timestamp": "2026-01-27T19:32:11.869Z"
}
```

#### Assistant Response (`followup_response`)

```json
{
  "_type": "followup_response",
  "ticker": "HD",
  "response": "Home Depot faces several meaningful risks...",
  "timestamp": "2026-01-27T19:32:20.226Z"
}
```

### DynamoDB Record Structure

```json
{
  "message_id": "c7c404be-b620-4f3c-99ea-3bb8aeaa715a",
  "conversation_id": "51dde7b7-3f62-4711-b031-780b9a149eff",
  "user_id": "116437894912495148094",
  "message_type": "user",
  "content": "{\"_type\":\"followup_question\",...}",
  "status": "saved",
  "created_at": "2026-01-27T19:32:21.441126Z",
  "timestamp": 1769542341,
  "environment": "dev",
  "project": "buffett"
}
```

### Backend Persistence (Lambda)

Messages are saved directly by the Lambda handler during the orchestration loop:

1. **User message saved** immediately after JWT validation
2. **Assistant message saved** after orchestration completes (`stop_reason=end_turn`)
3. **Token usage recorded** with input/output counts

```python
# Save user question to DynamoDB
user_message_id = save_followup_message(
    session_id=session_id,
    message_type='user',
    content=question,
    user_id=user_id,
    agent_type=agent_type,
    ticker=ticker
)

# ... orchestration loop ...

# Save assistant response
save_followup_message(
    session_id=session_id,
    message_type='assistant',
    content=final_response,
    user_id=user_id,
    agent_type=agent_type,
    ticker=ticker
)
```

### Frontend Persistence

The frontend also persists messages via the conversations API for the history sidebar:

**POST Flow:**
1. Effect triggers when `followUpMessages` changes
2. Waits for assistant response to complete streaming
3. Batches user + assistant messages via `Promise.all()`
4. Updates `lastSavedFollowUpCountRef` on success

**GET Flow:**
1. User clicks conversation in history
2. Frontend fetches messages from `/conversations/{id}/messages`
3. Filters by `_type` (followup_question, followup_response)
4. Sets `lastSavedRef` to prevent re-saving loaded messages

---

## API Reference

### Health Check

```http
GET /health
```

No authentication required. Used by CI/CD smoke tests.

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

### Follow-up Question

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

**Response (Non-streaming):**
```json
{
  "success": true,
  "response": "Based on the investment report...",
  "input_tokens": 3089,
  "output_tokens": 209,
  "turns": 2
}
```

### Save Message

```http
POST /conversations/{conversation_id}/messages
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "message_type": "user",
  "content": "{\"_type\":\"followup_question\",...}"
}
```

### Get Messages

```http
GET /conversations/{conversation_id}/messages
Authorization: Bearer <jwt_token>
```

---

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `ENVIRONMENT` | `dev` | Environment identifier |
| `FOLLOWUP_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model |
| `INVESTMENT_REPORTS_V2_TABLE` | `investment-reports-v2-dev` | Report sections |
| `METRICS_HISTORY_CACHE_TABLE` | `metrics-history-dev` | Historical metrics |
| `TOKEN_USAGE_TABLE` | `buffett-dev-token-usage` | Token tracking |
| `CHAT_MESSAGES_TABLE` | `buffett-dev-chat-messages` | Conversation history |
| `JWT_SECRET_ARN` | `arn:aws:secretsmanager:...` | JWT signing secret |
| `DEFAULT_TOKEN_LIMIT` | `50000` | Monthly token limit per user |

---

## Performance Metrics

| Metric | Typical Value |
|--------|---------------|
| Cold Start Duration | ~800 ms |
| Total Execution Time | 4-8 seconds |
| Memory Used | ~106 MB / 256 MB |
| Orchestration Turns | 1-3 |
| Tokens per Query | ~4,000-5,000 |

### Cost Estimate (Claude Haiku 4.5)

| Metric | Rate | Per Query | Monthly (1000 queries) |
|--------|------|-----------|------------------------|
| Input Tokens | $0.0008/1K | $0.0034 | $3.40 |
| Output Tokens | $0.004/1K | $0.0025 | $2.50 |
| **Total** | | **$0.0059** | **$5.90** |

---

## Error Handling

| Error | HTTP Code | Cause | Recovery |
|-------|-----------|-------|----------|
| Invalid/expired JWT | 401 | Token verification failed | User redirected to login |
| Token limit exceeded | 429 | Monthly limit reached | Returns limit details |
| Tool execution failure | 200 | DynamoDB error | Error in tool result, model retries |
| Bedrock API error | 500 | Model unavailable | Logged, error returned |

---

## Recent Changes

### January 31, 2026 - AGENT_CONFIG Removal

**Change:** Removed legacy `AGENT_CONFIG` dictionary and blocking checks.

**Background:** The code previously checked for Bedrock Agent IDs (`DEBT_AGENT_ID`, `CASHFLOW_AGENT_ID`, `GROWTH_AGENT_ID`) from a now-deleted prediction ensemble system. This caused 503 errors because those environment variables no longer exist.

**Fix Applied:**
- Removed `AGENT_CONFIG` dictionary (lines 325-339)
- Removed blocking checks in streaming path (lines 452-488)
- Removed blocking checks in non-streaming path (lines 893-898)

The code now directly uses the `converse` / `converse_stream` API orchestration loop.

### January 30, 2026 - Health Endpoint

**Added:** `/health` endpoint for CI/CD smoke tests.

- Returns service status, model ID, environment
- No JWT authentication required
- Supports both Function URL and API Gateway invocation

### January 29, 2026 - API Gateway Detection

**Fixed:** Lambda now correctly detects whether it's invoked via Function URL or API Gateway.

- Uses `x-amzn-apigateway-api-id` header as primary indicator
- Returns appropriate response format (streaming vs JSON)

---

## File Reference

| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/analysis_followup.py` | Main Lambda handler |
| `chat-api/backend/src/handlers/conversations_handler.py` | Messages persistence API |
| `chat-api/terraform/modules/lambda/analysis_followup.tf` | Lambda infrastructure |
| `chat-api/terraform/modules/dynamodb/main.tf` | DynamoDB table definitions |
| `frontend/src/App.jsx` | Frontend message persistence |
| `frontend/src/api/conversationsApi.js` | API client |

---

## Monitoring

### CloudWatch Logs

```
Log Group: /aws/lambda/buffett-dev-analysis-followup
Filter patterns:
  - "[NON-STREAMING]" - API Gateway requests
  - "[STREAMING]" - Function URL requests
  - "tool_use" - Tool execution events
  - "Token usage recorded" - Token tracking
```

### Key Metrics to Monitor

| Metric | Alert Threshold |
|--------|-----------------|
| Error Rate | > 5% over 5 minutes |
| Duration | > 15 seconds |
| Tokens per Query | > 8,000 average |
| Tool Calls per Query | > 5 |

---

## Conclusion

The Follow-Up Agent provides natural language Q&A for investment reports using:

- **Bedrock Converse API** with tool use orchestration
- **Claude Haiku 4.5** for cost-effective, quality responses
- **DynamoDB** for data retrieval and message persistence
- **JWT authentication** and **token usage tracking**

The system successfully retrieves real data from DynamoDB tables rather than relying on model training data, ensuring accurate and up-to-date responses about investment reports.
