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

V2 Event Types (section-based progressive loading with Single Executive Item):
- connected: Initial connection established
- executive: Combined item (ToC + ratings + 5 executive sections) - sent first for fast initial load
- section: Individual detailed section content (sent 12 times for Part 2 & 3)
- progress: Loading progress indicator
- complete: Stream finished
- error: Error occurred

V2 event flow (Single Executive Item schema):
connected → executive (combined) → section (x12 detailed) → progress → complete
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
