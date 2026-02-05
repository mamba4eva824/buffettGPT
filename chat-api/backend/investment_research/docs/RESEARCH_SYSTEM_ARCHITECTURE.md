# Investment Research System - End-to-End Architecture

## Executive Summary

This document provides a comprehensive technical overview of the BuffettGPT Investment Research system, detailing the complete data flow from frontend user interaction through API Gateway authentication, Lambda processing, and DynamoDB persistence. The system implements a progressive streaming architecture that delivers AI-generated investment reports with real-time section rendering and persistent state management.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Frontend Architecture](#2-frontend-architecture)
3. [API Gateway Layer](#3-api-gateway-layer)
4. [Lambda Processing Layer](#4-lambda-processing-layer)
5. [DynamoDB Data Layer](#5-dynamodb-data-layer)
6. [POST Request Flows (Write Operations)](#6-post-request-flows-write-operations)
7. [GET Request Flows (Read Operations)](#7-get-request-flows-read-operations)
8. [State Persistence Architecture](#8-state-persistence-architecture)
9. [Data Reference Mapping](#9-data-reference-mapping)
10. [Security and Authentication](#10-security-and-authentication)

---

## 1. System Overview

### 1.1 High-Level Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│ API Gateway │────▶│   Lambda    │────▶│  DynamoDB   │
│   (React)   │◀────│ (HTTP API)  │◀────│  (Python)   │◀────│  (Tables)   │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
       │                   │                   │                   │
       │    SSE Stream     │   JWT Auth        │   Report Gen      │
       │    WebSocket      │   Rate Limit      │   Section Query   │
       │                   │                   │   State Persist   │
```

### 1.2 Key Components

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React 18 + Vite | User interface, SSE consumption, state management |
| API Gateway | AWS HTTP API | Request routing, JWT authorization, CORS |
| Lambda | Python 3.11 + FastAPI | Business logic, Bedrock integration, streaming |
| DynamoDB | NoSQL Tables | Report storage, conversation persistence, message history |
| Bedrock | Claude 3.5 Haiku | AI report generation, follow-up responses |

### 1.3 Request Types

| Type | Method | Use Case |
|------|--------|----------|
| Streaming | GET + SSE | Progressive report delivery |
| On-Demand | GET | Section fetch, status check |
| Persistence | PUT | Save ToC state to conversation metadata |
| Messages | POST | Save follow-up Q&A to messages table |
| History | GET | Load conversation list, retrieve saved state |

---

## 2. Frontend Architecture

### 2.1 Research State Management (ResearchContext)

The `ResearchContext` provides Redux-style state management for the research experience:

```javascript
// ResearchContext State Shape
{
  selectedTicker: "AAPL",           // Current ticker being analyzed
  activeSectionId: "01_executive_summary",  // ToC highlight state
  isStreaming: false,               // SSE stream active
  streamStatus: "complete",         // connecting | streaming | complete | error
  reportMeta: {
    toc: [...],                     // 13 section entries
    ratings: {...},                 // Investment ratings
    total_word_count: 15000,
    generated_at: "2025-01-23T..."
  },
  streamedContent: {
    "01_executive_summary": { title, content, isComplete, part, icon, word_count },
    "06_growth": {...},
    // ... 13 total sections
  },
  followUpMessages: []              // User Q&A pairs
}
```

### 2.2 SSE Event Processing

The frontend establishes an EventSource connection and processes events sequentially:

```
Event Sequence:
1. connected        → SET_STATUS('streaming')
2. executive_meta   → SET_REPORT_META (ToC + ratings)
3. section_start    → Begin section accumulation
4. section_chunk    → Append 256-char chunks (typewriter effect)
5. section_end      → Mark section complete
6. progress         → Informational updates
7. complete         → SET_STATUS('complete')
```

### 2.3 On-Demand Section Loading

When a user clicks a ToC item for an unloaded section:

```javascript
handleSectionClick(sectionId):
  if (!streamedContent[sectionId].content) {
    // Fetch from API (not streamed)
    GET /research/report/{ticker}/section/{sectionId}
    → Response: { section_id, title, content, part, icon, word_count }
    → Dispatch: SET_SECTION
  }
  setActiveSection(sectionId)
```

---

## 3. API Gateway Layer

### 3.1 Research Endpoints Configuration

**Terraform Configuration:** `chat-api/terraform/modules/api-gateway/analysis_streaming.tf`

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/research/report/{ticker}/stream` | GET | JWT | SSE stream complete report |
| `/research/report/{ticker}/status` | GET | JWT | Check report existence/expiration |
| `/research/report/{ticker}/section/{section_id}` | GET | JWT | Fetch single section |
| `/research/followup` | POST | JWT | Stream follow-up responses |

### 3.2 Authentication Flow

```
┌─────────────┐     ┌─────────────────┐     ┌────────────────┐
│   Request   │────▶│  API Gateway    │────▶│  JWT Authorizer│
│  + Bearer   │     │  (Route Match)  │     │  (Lambda)      │
│    Token    │     └─────────────────┘     └────────┬───────┘
└─────────────┘                                      │
                                                     ▼
                                            ┌────────────────┐
                                            │ Verify JWT     │
                                            │ • Signature    │
                                            │ • Expiration   │
                                            │ • Claims       │
                                            └────────┬───────┘
                                                     │
                                    ┌────────────────┴────────────────┐
                                    │                                 │
                                    ▼                                 ▼
                              Valid Token                      Invalid Token
                              (200 + Policy)                  (401 Unauthorized)
```

### 3.3 JWT Authorizer Lambda

**Handler:** `chat-api/backend/src/handlers/auth_verify.py`

- **Input:** `Authorization: Bearer {token}` header
- **Validation:** Signature, expiration, issuer, audience
- **Output:** IAM policy allowing/denying execution
- **Cache:** 300 seconds per token

### 3.4 CORS Configuration

```hcl
cors_configuration {
  allow_methods = ["GET", "POST", "OPTIONS"]
  allow_headers = ["Content-Type", "Authorization", "Accept"]
  allow_origins = [local.allowed_origin]  # CloudFront URL or *
  max_age       = 86400
}
```

---

## 4. Lambda Processing Layer

### 4.1 Investment Research Lambda

**Handler:** `chat-api/backend/lambda/investment_research/app.py`
**Runtime:** Python 3.11 with Lambda Web Adapter
**Framework:** FastAPI with Starlette SSE support

### 4.2 Endpoint Implementations

#### Stream Report (GET /report/{ticker}/stream)

```python
@app.get("/report/{ticker}/stream")
async def stream_report(ticker: str):
    async def generate_section_stream():
        yield sse_event("connected", {})

        # 1. Load metadata (ToC + ratings)
        executive = await report_service.get_executive(ticker)
        yield sse_event("executive_meta", {
            "toc": executive.toc,
            "ratings": executive.ratings,
            "total_word_count": executive.total_word_count,
            "generated_at": executive.generated_at
        })

        # 2. Stream Executive Summary (merged Part 1)
        yield sse_event("section_start", executive_summary.metadata)
        for chunk in chunk_content(executive_summary.content, 256):
            yield sse_event("section_chunk", {"text": chunk})
            await asyncio.sleep(0.01)  # Typewriter effect
        yield sse_event("section_end", {"sectionId": "01_executive_summary"})

        # 3. Stream detailed sections (Part 2 + 3)
        for section in detailed_sections:
            yield sse_event("section_start", section.metadata)
            for chunk in chunk_content(section.content, 256):
                yield sse_event("section_chunk", {"text": chunk})
                await asyncio.sleep(0.01)
            yield sse_event("section_end", {"sectionId": section.section_id})

        yield sse_event("complete", {})

    return EventSourceResponse(generate_section_stream())
```

#### Get Section (GET /report/{ticker}/section/{section_id})

```python
@app.get("/report/{ticker}/section/{section_id}")
async def get_section(ticker: str, section_id: str):
    section = await report_service.get_report_section(ticker, section_id)
    return {
        "section_id": section_id,
        "title": section.title,
        "content": section.content,
        "part": section.part,
        "icon": section.icon,
        "word_count": section.word_count
    }
```

#### Report Status (GET /report/{ticker}/status)

```python
@app.get("/report/{ticker}/status")
async def get_status(ticker: str):
    status = await report_service.get_report_status(ticker)
    return {
        "exists": status.exists,
        "expired": status.expired,
        "ttl_remaining_days": status.ttl_remaining_days,
        "generated_at": status.generated_at,
        "total_word_count": status.total_word_count
    }
```

#### Follow-up Stream (POST /followup)

```python
@app.post("/followup")
async def stream_followup(request: FollowupRequest):
    async def generate_response():
        message_id = str(uuid.uuid4())
        yield sse_event("followup_start", {"message_id": message_id})

        # Invoke Bedrock Claude 3.5 Haiku
        response_stream = await invoke_followup_agent(
            ticker=request.ticker,
            question=request.question,
            section_context=request.section_id
        )

        for chunk in response_stream:
            yield sse_event("followup_chunk", {
                "message_id": message_id,
                "text": chunk
            })

        yield sse_event("followup_end", {"message_id": message_id})

    return EventSourceResponse(generate_response())
```

### 4.3 Report Service (Data Access Layer)

**File:** `chat-api/backend/lambda/investment_research/services/report_service.py`

| Method | DynamoDB Operation | Return Value |
|--------|-------------------|--------------|
| `get_executive(ticker)` | GetItem: `(ticker, "00_executive")` | ToC, ratings, merged executive summary |
| `get_report_section(ticker, section_id)` | GetItem: `(ticker, section_id)` | Single section content |
| `get_all_sections(ticker)` | Query: `ticker = :ticker` | All 17 sections |
| `get_report_status(ticker)` | GetItem with projection | Existence + TTL status |

---

## 5. DynamoDB Data Layer

### 5.1 Table Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DynamoDB Tables                               │
├─────────────────────┬───────────────────────────────────────────────┤
│ investment-reports-v2│ Section-based report storage (18 items/report)│
├─────────────────────┼───────────────────────────────────────────────┤
│ conversations       │ Conversation metadata + research_state        │
├─────────────────────┼───────────────────────────────────────────────┤
│ chat-messages       │ Follow-up Q&A message history                 │
└─────────────────────┴───────────────────────────────────────────────┘
```

### 5.2 investment-reports-v2 Table Schema

**Terraform:** `chat-api/terraform/modules/dynamodb/reports_table.tf`

```
Primary Key:
  - ticker (S, hash key): "AAPL", "NVDA", etc.
  - section_id (S, range key): "00_executive", "01_executive_summary", "06_growth", etc.

Item Types:
  1. Metadata Item (00_executive):
     - toc: JSON array of 13 section entries
     - ratings: JSON object with debt/cashflow/growth/verdict/conviction
     - executive_summary: Merged Part 1 content (all 5 sections combined)
     - total_word_count: Report total
     - generated_at: ISO timestamp
     - ttl: Unix expiration timestamp

  2. Section Items (01_executive_summary, 06_growth, etc.):
     - title: Display title
     - content: Full markdown content
     - part: 1 (Executive), 2 (Detailed), 3 (Real Talk)
     - icon: Lucide icon name
     - word_count: Section word count
     - display_order: Sort order (1-17)
```

**Global Secondary Indexes:**

| GSI Name | Hash Key | Range Key | Projection | Use Case |
|----------|----------|-----------|------------|----------|
| `part-index` | ticker | part | ALL | Query sections by part number |
| `generated-at-index` | ticker | generated_at | KEYS_ONLY | Track report generation times |

### 5.3 Section ID Mapping

| Section ID | Title | Part | Display Order |
|-----------|-------|------|---------------|
| `01_executive_summary` | Executive Summary (merged) | 1 | 1 |
| `02_business` | What Do They Do? | 1 | 2 |
| `03_health` | Quick Health Check | 1 | 3 |
| `04_fit` | Investment Fit | 1 | 4 |
| `05_verdict` | The Verdict | 1 | 5 |
| `06_growth` | Growth | 2 | 6 |
| `07_profit` | Profitability | 2 | 7 |
| `08_valuation` | Valuation | 2 | 8 |
| `09_earnings` | Earnings Quality | 2 | 9 |
| `10_cashflow` | Cash Flow | 2 | 10 |
| `11_debt` | Debt | 2 | 11 |
| `12_dilution` | Dilution | 2 | 12 |
| `13_bull` | Bull Case | 2 | 13 |
| `14_bear` | Bear Case | 2 | 14 |
| `15_warnings` | Warning Signs | 2 | 15 |
| `16_vibe` | Vibe Check | 2 | 16 |
| `17_realtalk` | Real Talk | 3 | 17 |

### 5.4 conversations Table Schema

**Terraform:** `chat-api/terraform/modules/dynamodb/conversations.tf`

```
Primary Key:
  - conversation_id (S, hash key): UUID

Attributes:
  - user_id (S): Authenticated user ID
  - title (S): "Research: AAPL - Apple Inc."
  - metadata (M): Map containing research_state
  - created_at (N): Unix timestamp
  - updated_at (N): Unix timestamp
  - is_archived (BOOL): Soft delete flag

GSI: user-conversations-index
  - Hash key: user_id
  - Range key: updated_at (descending)
  - Use case: List user's conversations chronologically
```

### 5.5 chat-messages Table Schema

**Terraform:** `chat-api/terraform/modules/dynamodb/messages.tf`

```
Primary Key:
  - conversation_id (S, hash key)
  - timestamp (N, range key): Unix timestamp

Attributes:
  - message_id (S): UUID
  - message_type (S): "user" | "assistant"
  - content (S): JSON-encoded message payload
  - user_id (S): Message owner
  - created_at (S): ISO timestamp
  - status (S): "saved"
```

---

## 6. POST Request Flows (Write Operations)

### 6.1 Save Research State (PUT /conversations/{id})

**Trigger:** ToC section click, report completion, or conversation switch

```
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐     ┌─────────────┐
│   Frontend   │────▶│   API Gateway   │────▶│  conversations │────▶│  DynamoDB   │
│  App.jsx     │     │  PUT /conv/{id} │     │  _handler.py   │     │ conversations│
└──────────────┘     └─────────────────┘     └────────────────┘     └─────────────┘
       │                                              │
       │ conversationsApi.updateResearchState()       │
       │                                              │
       ▼                                              ▼
Request Body:                               UpdateItem:
{                                           SET metadata.#research_state = :rs
  "metadata": {                             WHERE conversation_id = :id
    "research_state": {
      "ticker": "AAPL",
      "generated_at": "2025-01-23T...",
      "toc": [...13 entries],
      "ratings": {...},
      "active_section_id": "06_growth",
      "visible_sections": ["01_executive_summary", "06_growth"]
    }
  }
}
```

**Backend Processing:** `conversations_handler.py`

```python
def update_conversation(event):
    # Extract request
    conversation_id = event['pathParameters']['conversation_id']
    body = json.loads(event['body'])

    # Verify ownership
    conversation = conversations_table.get_item(Key={'conversation_id': conversation_id})
    if conversation['user_id'] != authenticated_user_id:
        return 403  # Access denied

    # Handle partial metadata update
    if 'metadata' in body:
        metadata_updates = convert_floats_to_decimal(body['metadata'])
        existing_metadata = conversation.get('metadata')

        if not existing_metadata:
            # Create new metadata
            update_expr.append('#metadata = :metadata')
            expr_attr_values[':metadata'] = metadata_updates
        else:
            # Partial update (preserves other metadata fields)
            for key, value in metadata_updates.items():
                update_expr.append(f'#metadata.#meta_{key} = :meta_{key}')
                expr_attr_names[f'#meta_{key}'] = key
                expr_attr_values[f':meta_{key}'] = value

    conversations_table.update_item(
        Key={'conversation_id': conversation_id},
        UpdateExpression='SET ' + ', '.join(update_expr),
        ExpressionAttributeNames=expr_attr_names,
        ExpressionAttributeValues=expr_attr_values
    )
```

### 6.2 Save Follow-Up Message (POST /conversations/{id}/messages)

**Trigger:** After follow-up Q&A completes

```
Frontend:                                   Backend:
conversationsApi.saveMessage({              PutItem:
  "message_type": "user",                   {
  "content": JSON.stringify({                 "conversation_id": "uuid",
    "_type": "followup_question",             "timestamp": 1706012400000,
    "ticker": "AAPL",                         "message_id": "uuid",
    "question": "What's their debt?",         "message_type": "user",
    "timestamp": 1706012400                   "content": "{...}",
  })                                          "user_id": "user123"
})                                          }
```

### 6.3 Create New Conversation (POST /conversations)

**Trigger:** First research request in new session

```
Request:                                    DynamoDB Item:
{                                           {
  "title": "Research: AAPL - Apple Inc.",     "conversation_id": "uuid-generated",
  "conversation_type": "research",            "user_id": "auth-user-id",
  "metadata": {                               "title": "Research: AAPL...",
    "ticker": "AAPL"                          "conversation_type": "research",
  }                                           "metadata": {"ticker": "AAPL"},
}                                             "created_at": 1706012400,
                                              "updated_at": 1706012400
                                            }
```

---

## 7. GET Request Flows (Read Operations)

### 7.1 Load Conversation List (GET /conversations)

**Trigger:** User opens app, views sidebar

```
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐     ┌─────────────┐
│   Frontend   │────▶│   API Gateway   │────▶│  conversations │────▶│  DynamoDB   │
│  App.jsx     │     │ GET /conversations│   │  _handler.py   │     │ GSI Query   │
└──────────────┘     └─────────────────┘     └────────────────┘     └─────────────┘
       │                                              │
       │ conversationsApi.list(token)                 │
       │                                              ▼
       ▼                                      Query: user-conversations-index
Response:                                     KeyCondition: user_id = :uid
{                                             ScanIndexForward: false
  "conversations": [                          (Most recent first)
    {
      "conversation_id": "abc-123",
      "title": "Research: AAPL...",
      "updated_at": 1706012400,
      "metadata": {
        "research_state": {...}
      }
    },
    ...
  ]
}
```

### 7.2 Load Saved Research Conversation (GET /conversations/{id})

**Trigger:** User clicks "Research: AAPL" in sidebar

```
Step 1: Fetch Conversation Metadata
────────────────────────────────────
GET /conversations/{conversation_id}
Response: {
  "conversation_id": "abc-123",
  "title": "Research: AAPL...",
  "metadata": {
    "research_state": {
      "ticker": "AAPL",
      "generated_at": "2025-01-22T...",
      "toc": [...13 entries],
      "ratings": {...},
      "active_section_id": "06_growth",
      "visible_sections": ["01_executive_summary", "06_growth"]
    }
  }
}

Step 2: Verify Report Still Exists
────────────────────────────────────
GET /research/report/AAPL/status
Response: {
  "exists": true,
  "expired": false,
  "ttl_remaining_days": 25,
  "generated_at": "2025-01-22T..."
}

If expired → Show ExpiredReportBanner
If valid   → Continue to Step 3

Step 3: Restore UI State
────────────────────────────────────
Frontend loadSavedReport():
  - reportMeta: { toc, ratings } from research_state
  - activeSectionId: "06_growth" (restores ToC highlight)
  - streamedContent: {} (empty, loads on-demand)
  - followUpMessages: (loaded from messages)

Step 4: Load Messages (Follow-up History)
────────────────────────────────────
GET /conversations/{id}/messages
Response: {
  "messages": [
    { "content": "{\"_type\":\"followup_question\",...}", ... },
    { "content": "{\"_type\":\"followup_response\",...}", ... }
  ]
}
```

### 7.3 Fetch Section On-Demand (GET /report/{ticker}/section/{section_id})

**Trigger:** User clicks ToC item in saved conversation

```
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐     ┌───────────────────┐
│   Frontend   │────▶│   API Gateway   │────▶│  investment_   │────▶│ investment-       │
│  ResearchCtx │     │ /section/{id}   │     │  research      │     │ reports-v2        │
└──────────────┘     └─────────────────┘     └────────────────┘     └───────────────────┘
       │                                              │
       │ fetchSection(ticker, sectionId)              │
       │                                              ▼
       ▼                                      GetItem:
Response:                                     (ticker="AAPL", section_id="06_growth")
{
  "section_id": "06_growth",
  "title": "Growth",
  "content": "## Revenue Growth\n\nApple's revenue...",
  "part": 2,
  "icon": "chart-up",
  "word_count": 1200
}
```

---

## 8. State Persistence Architecture

### 8.1 Research State Schema

```typescript
interface ResearchState {
  ticker: string;                    // "AAPL"
  generated_at: string;              // ISO timestamp of report generation
  report_table: string;              // "investment-reports-v2" (reference)

  // Table of Contents (for rendering)
  toc: {
    section_id: string;              // "06_growth"
    title: string;                   // "Growth"
    part: 1 | 2 | 3;                // Executive/Detailed/RealTalk
    icon: string;                    // "chart-up"
    word_count: number;
    display_order: number;
  }[];

  // Investment Ratings
  ratings: {
    debt: { rating: string; confidence: number; key_factors: string[] };
    cashflow: { rating: string; confidence: number; key_factors: string[] };
    growth: { rating: string; confidence: number; key_factors: string[] };
    overall_verdict: "BUY" | "HOLD" | "SELL";
    conviction: "High" | "Medium" | "Low";
  };

  total_word_count: number;

  // UI State
  active_section_id: string;         // ToC highlight position
  visible_sections: string[];        // Sections user has viewed

  last_updated: string;              // ISO timestamp of last state save
}
```

### 8.2 State Persistence Triggers

| Event | Action | Storage Location |
|-------|--------|------------------|
| Report streaming complete | Save research_state | conversations.metadata |
| ToC section click | Update active_section_id, visible_sections | conversations.metadata |
| Follow-up question sent | Save user message | chat-messages table |
| Follow-up response complete | Save assistant message | chat-messages table |
| Conversation switch | Save current state before loading new | conversations.metadata |

### 8.3 Partial Update Implementation

The backend supports partial metadata updates to avoid clobbering unrelated fields:

```python
# conversations_handler.py

if 'metadata' in body:
    metadata_updates = convert_floats_to_decimal(body['metadata'])
    existing_metadata = conversation.get('metadata')

    if not existing_metadata:
        # No existing metadata - create fresh
        update_expr.append('#metadata = :metadata')
        expr_attr_values[':metadata'] = metadata_updates
    else:
        # Existing metadata - partial update each key
        for key, value in metadata_updates.items():
            update_expr.append(f'#metadata.#meta_{key} = :meta_{key}')
            expr_attr_names[f'#meta_{key}'] = key
            expr_attr_values[f':meta_{key}'] = value
```

This ensures updating `research_state` doesn't overwrite other metadata like `ticker`, `report_type`, etc.

---

## 9. Data Reference Mapping

### 9.1 Cross-Table References

```
conversations table                    investment-reports-v2 table
┌─────────────────────────┐           ┌─────────────────────────────┐
│ conversation_id (PK)    │           │ ticker (PK) + section_id (SK)│
│ metadata.research_state │───────────│                             │
│   .ticker: "AAPL"       │    ref    │ "AAPL" / "00_executive"     │
│   .toc[].section_id     │───────────│ "AAPL" / "06_growth"        │
│   .active_section_id    │           │ "AAPL" / "07_profit"        │
└─────────────────────────┘           │ ...                         │
                                      └─────────────────────────────┘

chat-messages table
┌─────────────────────────┐
│ conversation_id (PK)    │◀──── Same conversation_id links messages
│ timestamp (SK)          │
│ content._type           │      followup_question | followup_response
│ content.ticker          │───── Reference to report ticker
└─────────────────────────┘
```

### 9.2 Section ID Resolution Flow

When loading a saved conversation:

```
1. Load conversation → metadata.research_state.ticker = "AAPL"
2. Load ToC → research_state.toc = [{section_id: "01_executive_summary"}, ...]
3. Restore active section → active_section_id = "06_growth"
4. User clicks ToC item → section_id = "07_profit"
5. Fetch section:
   GET /research/report/AAPL/section/07_profit
   → DynamoDB GetItem(ticker="AAPL", section_id="07_profit")
   → Return section content
```

### 9.3 Report Expiration Handling

```
┌─────────────────────────────────────────────────────────────────┐
│                  Report Lifecycle                                │
├─────────────────────────────────────────────────────────────────┤
│ 1. Report Generated                                             │
│    - TTL set to 30 days from generation                         │
│    - generated_at stored in metadata item                       │
│                                                                 │
│ 2. User Saves Conversation                                      │
│    - research_state.generated_at captures report timestamp      │
│    - Conversation persists indefinitely                         │
│                                                                 │
│ 3. Report Expires (TTL passes)                                  │
│    - DynamoDB auto-deletes all items for ticker                 │
│    - Conversation still exists with stale research_state        │
│                                                                 │
│ 4. User Loads Expired Conversation                              │
│    - GET /report/{ticker}/status returns { expired: true }      │
│    - Frontend shows ExpiredReportBanner                         │
│    - User can regenerate report                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 10. Security and Authentication

### 10.1 Authentication Flow

```
┌──────────────┐     ┌─────────────────┐     ┌────────────────┐
│    Google    │     │    Frontend     │     │   Backend      │
│    OAuth     │────▶│    Callback     │────▶│  auth_callback │
└──────────────┘     └─────────────────┘     └────────────────┘
       │                                              │
       │ OAuth Code                                   │ Verify with Google
       │                                              │ Generate JWT
       │                                              ▼
       │                                      ┌────────────────┐
       │◀─────────────────────────────────────│   JWT Token    │
       │          Set in localStorage         │  • user_id     │
       │                                      │  • email       │
       │                                      │  • exp (24h)   │
       └──────────────────────────────────────└────────────────┘
```

### 10.2 Request Authorization

Every API request includes:
```
Headers:
  Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

API Gateway JWT Authorizer verifies:
- Signature validity (HMAC-SHA256 with secret)
- Token expiration (`exp` claim)
- Issuer (`iss` claim = "buffett-chat-api")

### 10.3 Data Access Control

```python
# conversations_handler.py

def get_conversation(event):
    user_id = event['requestContext']['authorizer']['user_id']
    conversation = table.get_item(Key={'conversation_id': conv_id})

    # Ownership check
    if conversation['user_id'] != user_id:
        return 403  # Access denied

    return conversation
```

### 10.4 Rate Limiting

| User Type | Monthly Limit | Implementation |
|-----------|---------------|----------------|
| Anonymous | 5 requests | Device fingerprint (IP + User-Agent) |
| Authenticated | 500 requests | User ID tracking |

Rate limits tracked in `enhanced-rate-limits` and `usage-tracking` tables.

---

## Appendix A: Key File References

| Component | File Path |
|-----------|-----------|
| Research Context | `frontend/src/contexts/ResearchContext.jsx` |
| Main App | `frontend/src/App.jsx` |
| Conversations API | `frontend/src/api/conversationsApi.js` |
| Investment Research Lambda | `chat-api/backend/lambda/investment_research/app.py` |
| Report Service | `chat-api/backend/lambda/investment_research/services/report_service.py` |
| Conversations Handler | `chat-api/backend/src/handlers/conversations_handler.py` |
| API Gateway Config | `chat-api/terraform/modules/api-gateway/analysis_streaming.tf` |
| Reports Table | `chat-api/terraform/modules/dynamodb/reports_table.tf` |
| Conversations Table | `chat-api/terraform/modules/dynamodb/conversations.tf` |

---

## Appendix B: SSE Event Reference

| Event | Payload | Purpose |
|-------|---------|---------|
| `connected` | `{}` | Stream established |
| `executive_meta` | `{toc, ratings, total_word_count, generated_at}` | Report metadata |
| `section_start` | `{section_id, title, part, icon, word_count}` | Begin section |
| `section_chunk` | `{sectionId, text}` | 256-char content chunk |
| `section_end` | `{sectionId}` | Section complete |
| `progress` | `{message}` | Status update |
| `complete` | `{}` | Stream finished |
| `followup_start` | `{message_id}` | Follow-up response begin |
| `followup_chunk` | `{message_id, text}` | Response chunk |
| `followup_end` | `{message_id}` | Response complete |
| `error` | `{error}` | Error occurred |

---

*Document Version: 1.0*
*Last Updated: January 2025*
*Author: System Documentation*
