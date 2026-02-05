# System Overview

This document provides a comprehensive technical overview of the BuffettGPT Investment Research system, detailing the complete data flow from frontend user interaction through API Gateway authentication, Lambda processing, and DynamoDB persistence.

## High-Level Architecture

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

## Key Components

| Layer | Technology | Purpose |
|-------|------------|---------|
| Frontend | React 18 + Vite | User interface, SSE consumption, state management |
| API Gateway | AWS HTTP API | Request routing, JWT authorization, CORS |
| Lambda | Python 3.11 + FastAPI | Business logic, Bedrock integration, streaming |
| DynamoDB | NoSQL Tables | Report storage, conversation persistence, message history |
| Bedrock | Claude 3.5 Haiku | AI report generation, follow-up responses |

## Request Types

| Type | Method | Use Case |
|------|--------|----------|
| Streaming | GET + SSE | Progressive report delivery |
| On-Demand | GET | Section fetch, status check |
| Persistence | PUT | Save ToC state to conversation metadata |
| Messages | POST | Save follow-up Q&A to messages table |
| History | GET | Load conversation list, retrieve saved state |

## Frontend Architecture

### Research State Management (ResearchContext)

The `ResearchContext` provides Redux-style state management for the research experience:

```javascript
// ResearchContext State Shape
{
  selectedTicker: "AAPL",
  activeSectionId: "01_executive_summary",
  isStreaming: false,
  streamStatus: "complete",
  reportMeta: {
    toc: [...],
    ratings: {...},
    total_word_count: 15000,
    generated_at: "2025-01-23T..."
  },
  streamedContent: {
    "01_executive_summary": { title, content, isComplete, part, icon, word_count },
    "06_growth": {...}
  },
  followUpMessages: []
}
```

### SSE Event Processing

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

## API Gateway Layer

### Research Endpoints Configuration

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/research/report/{ticker}/stream` | GET | JWT | SSE stream complete report |
| `/research/report/{ticker}/status` | GET | JWT | Check report existence/expiration |
| `/research/report/{ticker}/section/{section_id}` | GET | JWT | Fetch single section |
| `/research/followup` | POST | JWT | Stream follow-up responses |

### Authentication Flow

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
                                            └────────────────┘
```

## Lambda Processing Layer

### Investment Research Lambda

- **Handler**: `chat-api/backend/lambda/investment_research/app.py`
- **Runtime**: Python 3.11 with Lambda Web Adapter
- **Framework**: FastAPI with Starlette SSE support

### Stream Report Endpoint

```python
@app.get("/report/{ticker}/stream")
async def stream_report(ticker: str):
    async def generate_section_stream():
        yield sse_event("connected", {})

        # 1. Load metadata (ToC + ratings)
        executive = await report_service.get_executive(ticker)
        yield sse_event("executive_meta", {
            "toc": executive.toc,
            "ratings": executive.ratings
        })

        # 2. Stream sections with typewriter effect
        for section in sections:
            yield sse_event("section_start", section.metadata)
            for chunk in chunk_content(section.content, 256):
                yield sse_event("section_chunk", {"text": chunk})
                await asyncio.sleep(0.01)
            yield sse_event("section_end", {"sectionId": section.section_id})

        yield sse_event("complete", {})

    return EventSourceResponse(generate_section_stream())
```

## DynamoDB Data Layer

### Table Overview

| Table | Purpose |
|-------|---------|
| `investment-reports-v2` | Section-based report storage (18 items/report) |
| `conversations` | Conversation metadata + research_state |
| `chat-messages` | Follow-up Q&A message history |

### Investment Reports V2 Schema

```
Primary Key:
  - ticker (S, hash key): "AAPL", "NVDA", etc.
  - section_id (S, range key): "00_executive", "01_executive_summary", etc.

Item Types:
  1. Metadata Item (00_executive):
     - toc: JSON array of 13 section entries
     - ratings: JSON object
     - executive_summary: Merged Part 1 content
     - total_word_count: Report total
     - generated_at: ISO timestamp

  2. Section Items:
     - title: Display title
     - content: Full markdown content
     - part: 1 (Executive), 2 (Detailed), 3 (Real Talk)
     - icon: Lucide icon name
     - word_count: Section word count
```

### Section ID Mapping

| Section ID | Title | Part |
|-----------|-------|------|
| `01_executive_summary` | Executive Summary | 1 |
| `06_growth` | Growth | 2 |
| `07_profit` | Profitability | 2 |
| `08_valuation` | Valuation | 2 |
| `09_earnings` | Earnings Quality | 2 |
| `10_cashflow` | Cash Flow | 2 |
| `11_debt` | Debt | 2 |
| `12_dilution` | Dilution | 2 |
| `17_realtalk` | Real Talk | 3 |

## State Persistence

### Research State Schema

```typescript
interface ResearchState {
  ticker: string;
  generated_at: string;
  toc: {
    section_id: string;
    title: string;
    part: 1 | 2 | 3;
    icon: string;
    word_count: number;
  }[];
  ratings: {
    debt: { rating: string; confidence: number; key_factors: string[] };
    cashflow: { rating: string; confidence: number; key_factors: string[] };
    growth: { rating: string; confidence: number; key_factors: string[] };
    overall_verdict: "BUY" | "HOLD" | "SELL";
    conviction: "High" | "Medium" | "Low";
  };
  active_section_id: string;
  visible_sections: string[];
}
```

### State Persistence Triggers

| Event | Action | Storage Location |
|-------|--------|------------------|
| Report streaming complete | Save research_state | conversations.metadata |
| ToC section click | Update active_section_id | conversations.metadata |
| Follow-up question sent | Save user message | chat-messages table |
| Follow-up response complete | Save assistant message | chat-messages table |

## SSE Event Reference

| Event | Payload | Purpose |
|-------|---------|---------|
| `connected` | `{}` | Stream established |
| `executive_meta` | `{toc, ratings, total_word_count}` | Report metadata |
| `section_start` | `{section_id, title, part, icon}` | Begin section |
| `section_chunk` | `{sectionId, text}` | 256-char content chunk |
| `section_end` | `{sectionId}` | Section complete |
| `complete` | `{}` | Stream finished |
| `error` | `{error}` | Error occurred |
