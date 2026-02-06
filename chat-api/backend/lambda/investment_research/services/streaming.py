"""
SSE (Server-Sent Events) formatting utilities for Investment Research.

Provides helper functions to format events for EventSourceResponse.
Each function returns a dict with 'event' and 'data' keys for sse-starlette.

V1 Event Types (single-blob reports):
- connected: Initial connection established
- rating: Domain rating (debt/cashflow/growth) - sent 3 times
- report: Full report content
- complete: Stream finished
- error: Error occurred

V2 Event Types (section-based progressive loading with Merged Executive Summary):
- connected: Initial connection established
- executive_meta: ToC + ratings (13 entries: 1 Executive Summary + 12 Detailed/RealTalk)
- section_start: Section metadata without content (signals start of streaming)
- section_chunk: 256-char content chunk for typewriter effect
- section_end: Section complete signal
- progress: Loading progress indicator
- complete: Stream finished
- error: Error occurred

V2 event flow (Merged Executive Summary schema):
connected → executive_meta → section_start/chunk/end (x1 exec) → section_start/chunk/end (x12 detailed) → complete
"""
import json
from datetime import datetime
from typing import Any, Dict, Optional

from models.schemas import DecimalEncoder


def _timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.utcnow().isoformat() + 'Z'


def _json_dumps(data: Dict[str, Any]) -> str:
    """JSON dumps with DecimalEncoder."""
    return json.dumps(data, cls=DecimalEncoder)


def connected_event() -> dict:
    """
    Initial connection event.

    Signals that the SSE stream is established and ready.

    Returns:
        Dict with event='connected' and connection data
    """
    return {
        "event": "connected",
        "data": _json_dumps({
            "type": "connected",
            "timestamp": _timestamp()
        })
    }


def rating_event(domain: str, rating_data: Dict[str, Any]) -> dict:
    """
    Domain rating event (debt, cashflow, growth).

    Emitted once per domain with the rating details.

    Args:
        domain: 'debt', 'cashflow', or 'growth'
        rating_data: Dict with rating, confidence, key_factors

    Returns:
        Dict with event='rating' and rating data
    """
    return {
        "event": "rating",
        "data": _json_dumps({
            "type": "rating",
            "domain": domain,
            "rating": rating_data.get("rating"),
            "confidence": rating_data.get("confidence"),
            "key_factors": rating_data.get("key_factors", []),
            "timestamp": _timestamp()
        })
    }


def report_event(
    report_content: str,
    metadata: Optional[Dict[str, Any]] = None
) -> dict:
    """
    Full report content event.

    Contains the complete markdown report and optional metadata.

    Args:
        report_content: Full markdown report text
        metadata: Optional dict with generated_at, model, overall_verdict, conviction

    Returns:
        Dict with event='report' and report data
    """
    data = {
        "type": "report",
        "content": report_content,
        "timestamp": _timestamp()
    }
    if metadata:
        data["metadata"] = metadata
    return {
        "event": "report",
        "data": _json_dumps(data)
    }


def complete_event(ticker: str, fiscal_year: int) -> dict:
    """
    Stream completion event.

    Signals that all data has been sent and the stream will close.

    Args:
        ticker: Stock ticker symbol
        fiscal_year: Fiscal year of the report

    Returns:
        Dict with event='complete' and completion data
    """
    return {
        "event": "complete",
        "data": _json_dumps({
            "type": "complete",
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "timestamp": _timestamp()
        })
    }


def error_event(message: str, code: Optional[str] = None) -> dict:
    """
    Error event.

    Signals that an error occurred during streaming.

    Args:
        message: Human-readable error message
        code: Optional error code (e.g., 'REPORT_NOT_FOUND', 'STREAM_ERROR')

    Returns:
        Dict with event='error' and error data
    """
    data = {
        "type": "error",
        "message": message,
        "timestamp": _timestamp()
    }
    if code:
        data["code"] = code
    return {
        "event": "error",
        "data": _json_dumps(data)
    }


# =============================================================================
# V2 Section-Based SSE Events (Progressive Loading)
# =============================================================================

def executive_event(item: Dict[str, Any]) -> dict:
    """
    Combined executive event - single payload with ToC + ratings + executive sections.

    Sends everything needed for initial page load in one event:
    - toc: Full table of contents for all 17 sections
    - ratings: Investment ratings with verdict and conviction
    - executive_sections: Part 1 sections (5 sections with content)
    - total_word_count: Total words in report
    - generated_at: When report was generated

    This is the primary event for the initial load - provides ToC for navigation
    and all executive content for immediate display.

    Args:
        item: Combined executive item from DynamoDB (00_executive)

    Returns:
        Dict with event='executive' and combined data
    """
    return {
        "event": "executive",
        "data": _json_dumps({
            "type": "executive",
            "ticker": item.get('ticker'),
            "toc": item.get('toc', []),
            "ratings": item.get('ratings', {}),
            "executive_sections": item.get('executive_sections', []),
            "total_word_count": item.get('total_word_count', 0),
            "generated_at": item.get('generated_at'),
            "timestamp": _timestamp()
        })
    }


def toc_event(
    toc: list,
    ratings: Dict[str, Any],
    total_word_count: int,
    generated_at: Optional[str] = None
) -> dict:
    """
    Table of Contents event with ratings.

    Sends ToC for progressive loading - client can show structure
    and ratings while sections stream in.

    Similar to prediction_ensemble's 'inference' event - sends metadata
    upfront before the content chunks.

    Args:
        toc: List of section entries [{section_id, title, part, icon, word_count}, ...]
        ratings: Structured ratings dict with overall_verdict, conviction, per-domain ratings
        total_word_count: Total words across all sections
        generated_at: ISO timestamp when report was generated

    Returns:
        Dict with event='toc' and ToC data
    """
    return {
        "event": "toc",
        "data": _json_dumps({
            "type": "toc",
            "toc": toc,
            "ratings": ratings,
            "total_word_count": total_word_count,
            "generated_at": generated_at,
            "timestamp": _timestamp()
        })
    }


def section_event(
    section_id: str,
    title: str,
    content: str,
    part: int,
    icon: str,
    word_count: int,
    display_order: int
) -> dict:
    """
    Individual section content event.

    Streams a single section for progressive rendering.

    Similar to prediction_ensemble's 'chunk' event - sends content
    incrementally for typewriter-style rendering.

    Args:
        section_id: Section identifier (e.g., '06_growth')
        title: Section title (may be dynamic, e.g., 'From 19% to 12%: The Slowdown')
        content: Markdown content of the section
        part: Part number (1=executive, 2=detailed, 3=realtalk)
        icon: Icon name for UI display
        word_count: Word count for this section
        display_order: Order for display (1-17)

    Returns:
        Dict with event='section' and section data
    """
    return {
        "event": "section",
        "data": _json_dumps({
            "type": "section",
            "section_id": section_id,
            "title": title,
            "content": content,
            "part": part,
            "icon": icon,
            "word_count": word_count,
            "display_order": display_order,
            "timestamp": _timestamp()
        })
    }


def progress_event(current: int, total: int, message: Optional[str] = None) -> dict:
    """
    Progress indicator event.

    Updates client on streaming progress.

    Similar to prediction_ensemble's 'status' event - provides
    progress feedback during streaming.

    Args:
        current: Current section number (1-17)
        total: Total number of sections (17)
        message: Optional status message (e.g., 'Loading detailed analysis...')

    Returns:
        Dict with event='progress' and progress data
    """
    percentage = round((current / total) * 100) if total > 0 else 0
    data = {
        "type": "progress",
        "current": current,
        "total": total,
        "percentage": percentage,
        "timestamp": _timestamp()
    }
    if message:
        data["message"] = message
    return {
        "event": "progress",
        "data": _json_dumps(data)
    }


def complete_v2_event(ticker: str, section_count: int) -> dict:
    """
    V2 stream completion event.

    Signals that all sections have been sent.

    Args:
        ticker: Stock ticker symbol
        section_count: Number of sections streamed

    Returns:
        Dict with event='complete' and completion data
    """
    return {
        "event": "complete",
        "data": _json_dumps({
            "type": "complete",
            "ticker": ticker,
            "section_count": section_count,
            "version": "v2",
            "timestamp": _timestamp()
        })
    }


# =============================================================================
# V2 Chunk Streaming Events (Typewriter Effect)
# =============================================================================

def executive_meta_event(item: Dict[str, Any]) -> dict:
    """
    Executive metadata event - ToC + ratings without section content.

    Sends metadata upfront for initial load, then sections stream
    via chunk events for typewriter effect.

    Args:
        item: Combined executive item from DynamoDB (00_executive)

    Returns:
        Dict with event='executive_meta' and metadata (no section content)
    """
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


def section_start_event(
    section_id: str,
    title: str,
    part: int,
    icon: str,
    word_count: int,
    display_order: int,
    total_chunks: int
) -> dict:
    """
    Signal start of section streaming - sends metadata without content.

    Emitted before chunk events to provide section context.

    Args:
        section_id: Section identifier (e.g., '06_growth')
        title: Section title
        part: Part number (1=executive, 2=detailed, 3=realtalk)
        icon: Icon name for UI display
        word_count: Word count for this section
        display_order: Order for display (1-17)
        total_chunks: Expected number of chunks for this section

    Returns:
        Dict with event='section_start' and section metadata
    """
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


def section_chunk_event(
    section_id: str,
    chunk_index: int,
    text: str,
    is_final: bool = False
) -> dict:
    """
    Stream a chunk of section content.

    Emitted multiple times per section for typewriter-style rendering.
    Each chunk is approximately 256 characters.

    Args:
        section_id: Section identifier (e.g., '06_growth')
        chunk_index: Index of this chunk (0-based)
        text: Chunk text content (~256 characters)
        is_final: True if this is the last chunk for this section

    Returns:
        Dict with event='section_chunk' and chunk data
    """
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


def section_end_event(section_id: str, total_chunks: int) -> dict:
    """
    Signal end of section streaming.

    Emitted after all chunks for a section have been sent.

    Args:
        section_id: Section identifier (e.g., '06_growth')
        total_chunks: Total number of chunks that were sent

    Returns:
        Dict with event='section_end' and completion data
    """
    return {
        "event": "section_end",
        "data": _json_dumps({
            "type": "section_end",
            "section_id": section_id,
            "total_chunks": total_chunks,
            "timestamp": _timestamp()
        })
    }


# =============================================================================
# Follow-Up Chat SSE Events
# =============================================================================

def followup_start_event(message_id: str, ticker: str) -> dict:
    """
    Signal start of follow-up response streaming.

    Emitted when the assistant begins generating a response to a follow-up question.

    Args:
        message_id: Unique identifier for this response message
        ticker: Stock ticker being discussed

    Returns:
        Dict with event='followup_start' and message metadata
    """
    return {
        "event": "followup_start",
        "data": _json_dumps({
            "type": "followup_start",
            "message_id": message_id,
            "ticker": ticker,
            "timestamp": _timestamp()
        })
    }


def followup_chunk_event(message_id: str, text: str) -> dict:
    """
    Stream a chunk of follow-up response text.

    Emitted multiple times as the LLM generates tokens.

    Args:
        message_id: Unique identifier for this response message
        text: Text chunk from the LLM response

    Returns:
        Dict with event='followup_chunk' and text content
    """
    return {
        "event": "followup_chunk",
        "data": _json_dumps({
            "type": "followup_chunk",
            "message_id": message_id,
            "text": text,
            "timestamp": _timestamp()
        })
    }


def followup_end_event(
    message_id: str,
    token_usage: dict = None,
    user_message_id: str = None,
    assistant_message_id: str = None
) -> dict:
    """
    Signal end of follow-up response streaming.

    Emitted when the assistant has finished generating the response.

    Args:
        message_id: Unique identifier for this response message
        token_usage: Optional dict with token usage stats
        user_message_id: Optional ID of the saved user message
        assistant_message_id: Optional ID of the saved assistant message

    Returns:
        Dict with event='followup_end' and completion data
    """
    data = {
        "type": "followup_end",
        "message_id": message_id,
        "timestamp": _timestamp()
    }
    if token_usage:
        data["token_usage"] = token_usage
    if user_message_id:
        data["user_message_id"] = user_message_id
    if assistant_message_id:
        data["assistant_message_id"] = assistant_message_id
    return {
        "event": "followup_end",
        "data": _json_dumps(data)
    }
