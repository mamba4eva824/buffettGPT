"""
FastAPI Application for Investment Research

Serves cached investment reports from DynamoDB via SSE streaming.
Uses Lambda Web Adapter for HTTP streaming support.

V1 Endpoints (single-blob reports):
- GET /health                              - Health check for Lambda Web Adapter
- GET /report/{ticker}                     - Stream cached report as SSE events (v1)
- POST /followup                           - Follow-up questions (STUB for Phase 4)

V2 Endpoints (section-based progressive loading):
- GET /report/{ticker}/toc                 - Get ToC + ratings (JSON)
- GET /report/{ticker}/section/{section_id} - Get specific section (JSON)
- GET /report/{ticker}/executive           - Get Part 1 executive sections (JSON)
- GET /report/{ticker}/stream              - Stream all sections as SSE events (v2)
"""

import os
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, List, Dict, Any
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from config.settings import ENVIRONMENT, DEFAULT_FISCAL_YEAR
from services.report_service import (
    # V1 methods
    get_cached_report,
    validate_ticker,
    # V2 methods
    get_executive,
    get_report_toc,
    get_report_section,
    get_executive_sections,
    get_all_sections,
    check_report_exists_v2,
)
from services.streaming import (
    # V1 events
    connected_event,
    rating_event,
    report_event,
    complete_event,
    error_event,
    # V2 events
    executive_event,
    toc_event,
    section_event,
    progress_event,
    complete_v2_event,
    # V2 chunk streaming events
    executive_meta_event,
    section_start_event,
    section_chunk_event,
    section_end_event,
)
from models.schemas import HealthResponse, FollowUpRequest
from services.followup_service import (
    invoke_followup_agent,
    get_report_ratings,
    get_available_reports,
    get_section_id_from_name,
)

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thread pool for running blocking DynamoDB calls without blocking the event loop
_executor = ThreadPoolExecutor(max_workers=4)


# =============================================================================
# Chunk Streaming Configuration
# =============================================================================

CHUNK_SIZE = 256  # Characters per chunk
CHUNK_DELAY_SECONDS = 0.01  # 10ms delay between chunks for smooth UX


async def stream_section_chunks(section: Dict[str, Any]) -> AsyncGenerator[dict, None]:
    """
    Stream a section's content as character chunks for typewriter effect.

    Emits events:
    1. section_start - metadata without content
    2. section_chunk (xN) - 256-char chunks with delay
    3. section_end - completion signal

    Args:
        section: Section dict with content, section_id, title, etc.

    Yields:
        SSE event dicts for EventSourceResponse
    """
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
        await asyncio.sleep(CHUNK_DELAY_SECONDS)

    # 3. Send section_end event
    yield section_end_event(section_id, total_chunks)


# =============================================================================
# FastAPI Application
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info(f"Investment Research API starting (env={ENVIRONMENT})")
    yield
    logger.info("Investment Research API shutting down")


app = FastAPI(
    title="Investment Research API",
    description="Stream cached investment analysis reports",
    version="1.0.0",
    lifespan=lifespan,
)


# =============================================================================
# SSE Report Streaming Generator
# =============================================================================

async def generate_report_stream(
    ticker: str,
    fiscal_year: int
) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events for streaming a cached report.

    Event sequence:
    1. connected - Initial connection established
    2. rating (x3) - One per domain (debt, cashflow, growth)
    3. report - Full report content with metadata
    4. complete - Stream finished

    Args:
        ticker: Stock ticker symbol (uppercase)
        fiscal_year: Fiscal year for the report

    Yields:
        Dict with event and data keys for EventSourceResponse
    """
    try:
        # 1. Connection event
        yield connected_event()

        # 2. Fetch cached report from DynamoDB
        report = get_cached_report(ticker, fiscal_year)

        if not report:
            yield error_event(
                f"No report found for {ticker} (FY{fiscal_year}). "
                "Report may not be generated yet.",
                code="REPORT_NOT_FOUND"
            )
            return

        # 3. Stream rating events (one per domain)
        ratings = report.get('ratings', {})
        for domain in ['debt', 'cashflow', 'growth']:
            domain_rating = ratings.get(domain)
            if domain_rating:
                yield rating_event(domain, domain_rating)

        # 4. Stream full report content with metadata
        report_content = report.get('report_content', '')
        metadata = {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'generated_at': report.get('generated_at'),
            'model': report.get('model'),
            'overall_verdict': ratings.get('overall_verdict'),
            'conviction': ratings.get('conviction')
        }
        yield report_event(report_content, metadata)

        # 5. Completion event
        yield complete_event(ticker, fiscal_year)

    except Exception as e:
        logger.error(f"Report stream error for {ticker}: {e}", exc_info=True)
        yield error_event(str(e), code="STREAM_ERROR")


# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint for Lambda Web Adapter.

    Returns service status and environment info.
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + 'Z',
        environment=ENVIRONMENT,
        service="investment-research"
    )


@app.get("/report/{ticker}")
async def get_report(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    ),
    fiscal_year: Optional[int] = Query(
        None,
        description="Fiscal year for the report (default: current year)",
        ge=2020,
        le=2030
    )
):
    """
    Stream cached investment report as SSE events.

    SSE Event Types:
    - connected: Initial connection established
    - rating: Domain rating (debt/cashflow/growth) - emitted 3 times
    - report: Full markdown report content with metadata
    - complete: Stream finished successfully
    - error: Error occurred

    Args:
        ticker: Stock ticker symbol (1-5 letters)
        fiscal_year: Fiscal year (default: current year)

    Returns:
        EventSourceResponse with SSE stream
    """
    # Validate ticker format
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    # Default fiscal year
    fiscal_year = fiscal_year or DEFAULT_FISCAL_YEAR

    logger.info(f"Starting report stream for {ticker} (FY{fiscal_year})")

    return EventSourceResponse(
        generate_report_stream(ticker, fiscal_year),
        media_type="text/event-stream"
    )


@app.post("/followup")
async def followup_question(request: FollowUpRequest):
    """
    Handle follow-up questions about a report via SSE streaming.

    Uses Claude Haiku 4.5 to provide streaming responses to user
    questions about investment research reports.

    SSE Event Types:
    - connected: Initial connection established
    - followup_start: Response generation started (includes message_id)
    - followup_chunk: Text chunk from Claude response
    - followup_end: Response complete
    - error: Error occurred

    Args:
        request: FollowUpRequest with ticker, question, section_id, conversation_id

    Returns:
        EventSourceResponse with SSE stream
    """
    ticker = request.ticker.upper().strip()

    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Follow-up question for {ticker}: {request.question[:100]}...")

    return EventSourceResponse(
        generate_followup_stream(
            ticker,
            request.question,
            request.conversation_id,
            request.section_id
        ),
        media_type="text/event-stream"
    )


async def generate_followup_stream(
    ticker: str,
    question: str,
    session_id: str = None,
    section_id: str = None
) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events for streaming follow-up responses.

    Args:
        ticker: Stock ticker symbol
        question: User's follow-up question
        session_id: Optional session ID for conversation continuity
        section_id: Optional section ID for additional context

    Yields:
        SSE event dicts for EventSourceResponse
    """
    try:
        # 1. Connection event
        yield connected_event()

        # 2. Stream Claude Haiku 4.5 response
        async for event in invoke_followup_agent(ticker, question, session_id, section_id):
            yield event

    except Exception as e:
        logger.error(f"Follow-up stream error for {ticker}: {e}", exc_info=True)
        yield error_event(str(e), code="FOLLOWUP_ERROR")


@app.get("/reports")
async def list_available_reports():
    """
    List all available investment reports.

    Returns list of tickers with reports for search dropdown.
    Includes company_name for display.
    """
    result = get_available_reports()

    return JSONResponse(content={
        "success": result.get('success', False),
        "count": result.get('count', 0),
        "reports": result.get('reports', []),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


@app.get("/reports/search")
async def search_reports_by_company(
    q: str = Query(
        ...,
        description="Search query for company name or ticker",
        min_length=1,
        max_length=100
    )
):
    """
    Search for reports by company name or ticker.

    Uses static company_names dictionary for prefix matching.
    Allows users to type "Apple" and find AAPL reports.

    Args:
        q: Search query (matches company name or ticker, case insensitive)

    Returns:
        JSONResponse with matching ticker/name pairs
    """
    from investment_research.company_names import search_companies

    # Get matching companies from static dictionary
    matches = search_companies(q, limit=10)

    return JSONResponse(content={
        "success": True,
        "query": q,
        "count": len(matches),
        "results": matches,
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


# =============================================================================
# V2 API Endpoints (Section-Based Progressive Loading)
# =============================================================================

async def generate_section_stream(ticker: str) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events for streaming sections with chunk-level typewriter effect.

    V2 Event sequence (Chunk Streaming - Merged Executive Summary):
    1. connected - Initial connection established
    2. executive_meta - ToC + ratings (no section content, 13 entries in ToC)
    3. progress - "Loading executive summary..."
    4. section_start/chunk/end (x1) - Single merged Executive Summary streamed in chunks
    5. progress - "Loading detailed analysis..."
    6. section_start/chunk/end (x12) - Detailed sections streamed in chunks
    7. complete - Stream finished

    Args:
        ticker: Stock ticker symbol (uppercase)

    Yields:
        Dict with event and data keys for EventSourceResponse
    """
    try:
        # 1. Connection event
        yield connected_event()

        # 2. Get combined executive item (single DynamoDB read, run in executor to avoid blocking)
        loop = asyncio.get_event_loop()
        exec_item = await loop.run_in_executor(_executor, get_executive, ticker)

        if not exec_item:
            yield error_event(
                f"No report found for {ticker} in v2 format. "
                "Report may not be generated yet.",
                code="REPORT_NOT_FOUND"
            )
            return

        # 3. Send executive metadata (ToC + ratings, no section content)
        # ToC now has 13 entries: 1 Executive Summary + 12 Detailed/RealTalk
        yield executive_meta_event(exec_item)

        # 4. Stream merged Executive Summary (Part 1) as single section
        executive_summary = exec_item.get('executive_summary', {})

        if executive_summary:
            yield progress_event(0, 1, "Loading executive summary...")
            async for chunk_event in stream_section_chunks(executive_summary):
                yield chunk_event

        # 5. Get detailed sections (Part 2 & 3, run in executor to avoid blocking)
        detailed_sections = await loop.run_in_executor(_executor, get_all_sections, ticker)

        if not detailed_sections:
            yield error_event(
                f"No detailed sections found for {ticker}.",
                code="SECTIONS_NOT_FOUND"
            )
            return

        total_detailed = len(detailed_sections)

        # 6. Stream detailed sections with chunks
        yield progress_event(0, total_detailed, "Loading detailed analysis...")

        for i, section in enumerate(detailed_sections):
            async for chunk_event in stream_section_chunks(section):
                yield chunk_event

            # Progress updates at key points
            current = i + 1
            if current == 6:  # Halfway through detailed analysis
                yield progress_event(current, total_detailed, "Deep diving into metrics...")
            elif current == 11:  # Before Real Talk (Part 3)
                yield progress_event(current, total_detailed, "Almost done...")

        # 7. Completion event (1 exec + 12 detailed = 13 total sections)
        total_sections = 1 + total_detailed
        yield complete_v2_event(ticker, total_sections)

    except Exception as e:
        logger.error(f"Section stream error for {ticker}: {e}", exc_info=True)
        yield error_event(str(e), code="STREAM_ERROR")


@app.get("/report/{ticker}/toc")
async def get_toc(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    )
):
    """
    Get report table of contents with ratings.

    Returns ToC for progressive loading - client can show structure
    and navigate while fetching sections on-demand.

    Args:
        ticker: Stock ticker symbol (1-5 letters)

    Returns:
        JSONResponse with toc, ratings, metadata
    """
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Fetching ToC for {ticker}")

    toc_data = get_report_toc(ticker)
    if not toc_data:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for {ticker}."
        )

    return JSONResponse(content={
        "success": True,
        "ticker": ticker,
        "toc": toc_data.get('toc', []),
        "ratings": toc_data.get('ratings', {}),
        "total_word_count": toc_data.get('total_word_count', 0),
        "generated_at": toc_data.get('generated_at'),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


@app.get("/report/{ticker}/section/{section_id}")
async def get_section(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    ),
    section_id: str = Path(
        ...,
        description="Section identifier (e.g., 01_executive_summary, 06_growth, 11_debt)",
        min_length=1,
        max_length=25
    )
):
    """
    Get a specific section content.

    Enables on-demand section loading for navigation.
    For 01_executive_summary, returns merged Part 1 content from executive item.
    For other sections, returns from individual section items.

    Args:
        ticker: Stock ticker symbol (1-5 letters)
        section_id: Section identifier (e.g., '01_executive_summary', '06_growth')

    Returns:
        JSONResponse with section content and metadata
    """
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Fetching section {section_id} for {ticker}")

    # Handle merged Executive Summary specially
    if section_id == '01_executive_summary':
        exec_item = get_executive(ticker)
        if not exec_item:
            raise HTTPException(
                status_code=404,
                detail=f"Report not found for {ticker}."
            )
        section = exec_item.get('executive_summary')
        if not section:
            raise HTTPException(
                status_code=404,
                detail=f"Executive summary not found for {ticker}."
            )
    else:
        # Fetch from individual section items (Part 2/3)
        section = get_report_section(ticker, section_id)
        if not section:
            raise HTTPException(
                status_code=404,
                detail=f"Section {section_id} not found for {ticker}."
            )

    return JSONResponse(content={
        "success": True,
        "ticker": ticker,
        "section_id": section.get('section_id'),
        "title": section.get('title'),
        "content": section.get('content'),
        "part": section.get('part'),
        "icon": section.get('icon'),
        "word_count": section.get('word_count'),
        "display_order": section.get('display_order'),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


@app.get("/report/{ticker}/executive")
async def get_executive_endpoint(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    )
):
    """
    Get combined executive item (ToC + ratings + merged Executive Summary).

    Returns everything needed for initial load in a single DynamoDB read:
    - toc: Table of contents (13 entries: 1 Executive Summary + 12 Detailed/RealTalk)
    - ratings: Investment ratings with verdict and conviction
    - executive_summary: Merged Part 1 section with all executive content
    - total_word_count: Total words in report

    This is the primary endpoint for initial page load.

    Args:
        ticker: Stock ticker symbol (1-5 letters)

    Returns:
        JSONResponse with combined executive item
    """
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Fetching executive item for {ticker}")

    item = get_executive(ticker)
    if not item:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for {ticker}."
        )

    return JSONResponse(content={
        "success": True,
        "ticker": ticker,
        "toc": item.get('toc', []),
        "ratings": item.get('ratings', {}),
        "executive_summary": item.get('executive_summary', {}),
        "total_word_count": item.get('total_word_count', 0),
        "generated_at": item.get('generated_at'),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


@app.get("/report/{ticker}/stream")
async def stream_sections(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    )
):
    """
    Stream all report sections as SSE events.

    V2 progressive loading - streams ToC first, then sections
    in order for typewriter-style rendering.

    SSE Event Types:
    - connected: Initial connection established
    - toc: Table of contents + ratings
    - section: Individual section content (emitted 17 times)
    - progress: Loading progress updates
    - complete: Stream finished successfully
    - error: Error occurred

    Args:
        ticker: Stock ticker symbol (1-5 letters)

    Returns:
        EventSourceResponse with SSE stream
    """
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Starting section stream for {ticker}")

    return EventSourceResponse(
        generate_section_stream(ticker),
        media_type="text/event-stream"
    )


# =============================================================================
# Error Handlers
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with consistent format."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": exc.detail,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc) if ENVIRONMENT == 'dev' else None,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    )


# =============================================================================
# Development Server (for local testing without Lambda)
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
