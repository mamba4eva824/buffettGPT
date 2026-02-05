# Streaming Implementation

This document covers the Server-Sent Events (SSE) streaming implementation for progressive report delivery.

## Overview

BuffettGPT uses SSE to stream investment reports section by section, creating a typewriter effect in the UI.

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │◀────│   Lambda    │◀────│  DynamoDB   │
│  EventSource│ SSE │   FastAPI   │     │   Sections  │
└─────────────┘     └─────────────┘     └─────────────┘
```

## SSE Event Types

| Event | Payload | Purpose |
|-------|---------|---------|
| `connected` | `{}` | Stream established |
| `executive_meta` | `{toc, ratings}` | Report metadata |
| `section_start` | `{section_id, title}` | Begin section |
| `section_chunk` | `{text}` | 256-char content chunk |
| `section_end` | `{sectionId}` | Section complete |
| `progress` | `{message}` | Status update |
| `complete` | `{}` | Stream finished |
| `error` | `{error}` | Error occurred |

## Backend Implementation

### FastAPI SSE Endpoint

```python
from sse_starlette.sse import EventSourceResponse

@app.get("/report/{ticker}/stream")
async def stream_report(ticker: str):
    async def generate():
        yield sse_event("connected", {})

        # Stream sections
        for section in sections:
            yield sse_event("section_start", section.metadata)

            # Chunk content for typewriter effect
            for chunk in chunk_content(section.content, 256):
                yield sse_event("section_chunk", {"text": chunk})
                await asyncio.sleep(0.01)

            yield sse_event("section_end", {"sectionId": section.section_id})

        yield sse_event("complete", {})

    return EventSourceResponse(generate())
```

### Chunk Size

Content is chunked into 256-character pieces:

```python
def chunk_content(content: str, size: int = 256) -> Generator[str, None, None]:
    for i in range(0, len(content), size):
        yield content[i:i + size]
```

## Frontend Implementation

### EventSource Connection

```javascript
const eventSource = new EventSource(
  `${API_URL}/research/report/${ticker}/stream`,
  { headers: { 'Authorization': `Bearer ${token}` } }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleSSEEvent(data);
};
```

### State Management

The ResearchContext handles SSE events:

```javascript
function handleSSEEvent(event) {
  switch (event.type) {
    case 'section_chunk':
      dispatch({ type: 'APPEND_CHUNK', payload: event });
      break;
    case 'section_end':
      dispatch({ type: 'MARK_SECTION_COMPLETE', payload: event });
      break;
    // ...
  }
}
```

## Performance Considerations

1. **Chunk Delay** - 10ms between chunks for smooth animation
2. **Connection Timeout** - 5 minute timeout for long reports
3. **Error Recovery** - Automatic reconnection on disconnect

## Related

- [System Architecture](../architecture/system-overview.md)
- [API WebSocket](../api/websocket.md)
