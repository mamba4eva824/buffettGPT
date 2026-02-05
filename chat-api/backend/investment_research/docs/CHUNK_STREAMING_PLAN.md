# Implementation Plan: Section-Level Chunk Streaming

## Overview

Implement character-level streaming within sections, similar to the prediction_ensemble lambda's chunk streaming pattern. Currently, each section arrives as a single complete payload. This update will break section content into smaller chunks for a typewriter-style streaming effect.

**Current Behavior:** Each `section` event contains the full content (200-500 bytes at once)
**Target Behavior:** Section content streams in small chunks (~256 chars each) with timestamps

**Reference Implementation:** `chat-api/backend/lambda/prediction_ensemble/services/streaming.py`

---

## Event Flow Comparison

### Current (Section-Level Only)
```
connected → executive (15KB payload) → section (x12, full content each) → complete
```

### Target (With Chunk Streaming for ALL Sections)
```
connected → executive_meta (ToC + ratings) → section_start → chunk (x2-5) → section_end (x5 exec) → section_start → chunk → section_end (x12 detailed) → complete
```

**Note:** Both executive sections (Part 1) AND detailed sections (Part 2 & 3) will be chunk-streamed for a consistent typewriter effect throughout the report.

---

## Files to Modify

| File | Changes |
|------|---------|
| `services/streaming.py` | Add `section_chunk_event()`, `section_start_event()`, `section_end_event()`, `executive_meta_event()` |
| `app.py` | Modify `generate_section_stream()` to yield chunks |

---

## Phase 1: Add Chunk Event Helpers

**File:** `services/streaming.py`

### 1.1 Add `section_start_event()`

Signals the start of a section (header/metadata without content):

```python
def section_start_event(
    section_id: str,
    title: str,
    part: int,
    icon: str,
    word_count: int,
    display_order: int,
    total_chunks: int
) -> dict:
    """Signal start of section streaming - sends metadata without content."""
    return {
        "event": "section_start",
        "data": _json_dumps({
            "type": "section_start",
            "section_id": section_id,
            "title": title,
            "part": part,
            "icon": icon,
            "word_count": word_count,
            "display_order": display_order,
            "total_chunks": total_chunks,
            "timestamp": _timestamp()
        })
    }
```

### 1.2 Add `section_chunk_event()`

Streams content in small pieces (similar to prediction_ensemble's `chunk_event()`):

```python
def section_chunk_event(
    section_id: str,
    chunk_index: int,
    text: str,
    is_final: bool = False
) -> dict:
    """Stream a chunk of section content."""
    return {
        "event": "section_chunk",
        "data": _json_dumps({
            "type": "section_chunk",
            "section_id": section_id,
            "chunk_index": chunk_index,
            "text": text,
            "is_final": is_final,
            "timestamp": _timestamp()
        })
    }
```

### 1.3 Add `section_end_event()`

Signals completion of a section:

```python
def section_end_event(section_id: str, total_chunks: int) -> dict:
    """Signal end of section streaming."""
    return {
        "event": "section_end",
        "data": _json_dumps({
            "type": "section_end",
            "section_id": section_id,
            "total_chunks": total_chunks,
            "timestamp": _timestamp()
        })
    }
```

### 1.4 Add `executive_meta_event()`

Send ToC and ratings without section content:

```python
def executive_meta_event(item: Dict) -> dict:
    """Executive metadata event - ToC + ratings without section content."""
    return {
        "event": "executive_meta",
        "data": _json_dumps({
            "type": "executive_meta",
            "ticker": item.get('ticker'),
            "toc": item.get('toc', []),
            "ratings": item.get('ratings', {}),
            "total_word_count": item.get('total_word_count', 0),
            "generated_at": item.get('generated_at'),
            "timestamp": _timestamp()
        })
    }
```

---

## Phase 2: Modify Stream Generator

**File:** `app.py`

### 2.1 Add Helper Function for Chunking

```python
import asyncio

CHUNK_SIZE = 256  # Characters per chunk

async def stream_section_chunks(section: dict) -> AsyncGenerator[dict, None]:
    """Stream a section's content as character chunks."""
    content = section.get('content', '')
    section_id = section.get('section_id', '')
    total_chunks = max(1, (len(content) + CHUNK_SIZE - 1) // CHUNK_SIZE)

    # 1. Send section_start event (metadata without content)
    yield section_start_event(
        section_id=section_id,
        title=section.get('title', ''),
        part=section.get('part', 0),
        icon=section.get('icon', ''),
        word_count=section.get('word_count', 0),
        display_order=section.get('display_order', 0),
        total_chunks=total_chunks
    )

    # 2. Stream content chunks
    for chunk_idx in range(total_chunks):
        start = chunk_idx * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(content))
        chunk_text = content[start:end]
        is_final = (chunk_idx == total_chunks - 1)

        yield section_chunk_event(
            section_id=section_id,
            chunk_index=chunk_idx,
            text=chunk_text,
            is_final=is_final
        )

        # Small delay for smoother streaming (10ms)
        await asyncio.sleep(0.01)

    # 3. Send section_end event
    yield section_end_event(section_id, total_chunks)
```

### 2.2 Modify `generate_section_stream()`

Replace the entire executive + section emission logic:

```python
async def generate_section_stream(ticker: str) -> AsyncGenerator[dict, None]:
    try:
        yield connected_event()

        # 1. Get executive item
        exec_item = get_executive(ticker)
        if not exec_item:
            yield error_event(f"No report found for {ticker}", code="REPORT_NOT_FOUND")
            return

        # 2. Send metadata first (ToC + ratings without content)
        yield executive_meta_event(exec_item)

        # 3. Stream executive sections (Part 1) with chunks
        executive_sections = exec_item.get('executive_sections', [])
        yield progress_event(0, len(executive_sections), "Loading executive summary...")

        for section in executive_sections:
            async for chunk in stream_section_chunks(section):
                yield chunk

        # 4. Get detailed sections (Part 2 & 3)
        detailed_sections = get_all_sections(ticker)
        if not detailed_sections:
            yield error_event(f"No detailed sections found for {ticker}", code="SECTIONS_NOT_FOUND")
            return

        # 5. Stream detailed sections with chunks
        total_detailed = len(detailed_sections)
        yield progress_event(0, total_detailed, "Loading detailed analysis...")

        for i, section in enumerate(detailed_sections):
            async for chunk in stream_section_chunks(section):
                yield chunk

            # Progress updates at key points
            current = i + 1
            if current == 6:
                yield progress_event(current, total_detailed, "Deep diving into metrics...")
            elif current == 11:
                yield progress_event(current, total_detailed, "Almost done...")

        # 6. Complete
        total_sections = len(executive_sections) + total_detailed
        yield complete_v2_event(ticker, total_sections)

    except Exception as e:
        logger.error(f"Section stream error for {ticker}: {e}", exc_info=True)
        yield error_event(str(e), code="STREAM_ERROR")
```

---

## Phase 3: Update Imports

**File:** `app.py`

Add new imports at the top:

```python
from services.streaming import (
    # Existing imports...
    section_start_event,
    section_chunk_event,
    section_end_event,
    executive_meta_event,
)
```

---

## SSE Event Examples

### Before (Current - Full Payloads)
```
event: executive
data: {"type":"executive","toc":[...],"ratings":{...},"executive_sections":[{content:"[FULL]"},...]}

event: section
data: {"type":"section","section_id":"06_growth","content":"[FULL 500 BYTES]",...}
```

### After (Chunked - All Sections)
```
# 1. Metadata first (no section content)
event: executive_meta
data: {"type":"executive_meta","ticker":"NVDA","toc":[...],"ratings":{...},"total_word_count":2562}

# 2. Executive sections streamed with chunks
event: section_start
data: {"type":"section_start","section_id":"01_tldr","title":"TL;DR","total_chunks":1,...}

event: section_chunk
data: {"type":"section_chunk","section_id":"01_tldr","chunk_index":0,"text":"NVIDIA is the toll booth...","is_final":true}

event: section_end
data: {"type":"section_end","section_id":"01_tldr","total_chunks":1}

# ... repeat for 02_business, 03_health, 04_fit, 05_verdict ...

# 3. Detailed sections streamed with chunks
event: section_start
data: {"type":"section_start","section_id":"06_growth","title":"Growth...","total_chunks":3,...}

event: section_chunk
data: {"type":"section_chunk","section_id":"06_growth","chunk_index":0,"text":"[256 chars]","is_final":false}

event: section_chunk
data: {"type":"section_chunk","section_id":"06_growth","chunk_index":1,"text":"[256 chars]","is_final":false}

event: section_chunk
data: {"type":"section_chunk","section_id":"06_growth","chunk_index":2,"text":"[remaining]","is_final":true}

event: section_end
data: {"type":"section_end","section_id":"06_growth","total_chunks":3}

# ... repeat for remaining sections ...

# 4. Complete
event: complete
data: {"type":"complete","ticker":"NVDA","section_count":17}
```

---

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CHUNK_SIZE` | 256 | Characters per chunk |
| `CHUNK_DELAY_MS` | 10 | Milliseconds between chunks |

These can be made configurable via environment variables if needed.

---

## Verification Plan

### 1. Local Testing
```bash
cd chat-api/backend/lambda/investment_research
docker build --platform linux/amd64 -t investment-research:v1.2.0 .
docker run --rm -p 8080:8080 \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e ENVIRONMENT=dev \
  -e INVESTMENT_REPORTS_V2_TABLE=investment-reports-v2-dev \
  investment-research:v1.2.0

# Test streaming endpoint
curl -N "http://localhost:8080/report/NVDA/stream" | head -50
```

### 2. Verify Event Sequence
Expected output should show:
- `connected`
- `executive_meta` (ToC + ratings only)
- `progress`
- `section_start` → `section_chunk` (x2-5) → `section_end` (repeat for each section)
- `complete`

### 3. Check CloudWatch Logs
```bash
aws logs filter-log-events \
  --log-group-name "/aws/lambda/buffett-dev-investment-research" \
  --filter-pattern "section_chunk" \
  --region us-east-1
```

---

## Deployment

1. Update `streaming.py` with new event functions
2. Update `app.py` with chunking logic
3. Build and test Docker image locally
4. Push to ECR and update Lambda
5. Verify streaming via Lambda URL

---

## Success Criteria

- [ ] `executive_meta` event sent first with ToC + ratings (no content)
- [ ] Executive sections (01-05) chunk-streamed with typewriter effect
- [ ] Detailed sections (06-17) chunk-streamed with typewriter effect
- [ ] `section_start` → `section_chunk` (xN) → `section_end` sequence for each section
- [ ] Content streams in ~256 character chunks
- [ ] 10ms delay between chunks for smooth UX
- [ ] CloudWatch logs show `section_chunk` events
- [ ] Total of 17 sections streamed (5 executive + 12 detailed)
- [ ] Frontend can reassemble chunks by `section_id`
