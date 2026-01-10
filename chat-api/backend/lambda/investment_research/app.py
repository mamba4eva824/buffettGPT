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
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, List
from contextlib import asynccontextmanager

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
)
from models.schemas import HealthResponse, FollowUpRequest

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    Handle follow-up questions about a report.

    STUB IMPLEMENTATION - Phase 4 will integrate with Bedrock agent.

    The eventual implementation will:
    1. Fetch the relevant report via action group
    2. Pass question + report context to Bedrock agent
    3. Stream the agent's response back

    Args:
        request: FollowUpRequest with ticker, question, conversation_id

    Returns:
        JSONResponse with stub message (for now)
    """
    logger.info(
        f"Follow-up stub called for {request.ticker}: "
        f"{request.question[:50]}..."
    )

    return JSONResponse(
        content={
            "status": "stub",
            "message": "Follow-up functionality coming in Phase 4. "
                       "This endpoint will integrate with Bedrock agent.",
            "ticker": request.ticker,
            "question_received": request.question,
            "fiscal_year": request.fiscal_year or DEFAULT_FISCAL_YEAR,
            "conversation_id": request.conversation_id,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    )


# =============================================================================
# V2 API Endpoints (Section-Based Progressive Loading)
# =============================================================================

async def generate_section_stream(ticker: str) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events for streaming sections progressively.

    V2 Event sequence (Single Executive Item schema):
    1. connected - Initial connection established
    2. executive - Combined item (ToC + ratings + 5 executive sections)
    3. section (x12) - Detailed sections (06_growth through 17_realtalk)
    4. progress - Progress updates between section batches
    5. complete - Stream finished

    Args:
        ticker: Stock ticker symbol (uppercase)

    Yields:
        Dict with event and data keys for EventSourceResponse
    """
    try:
        # 1. Connection event
        yield connected_event()

        # 2. Get combined executive item (single DynamoDB read)
        exec_item = get_executive(ticker)

        if not exec_item:
            yield error_event(
                f"No report found for {ticker} in v2 format. "
                "Report may not be generated yet.",
                code="REPORT_NOT_FOUND"
            )
            return

        # 3. Send executive event with ToC + ratings + Part 1 sections upfront
        yield executive_event(exec_item)

        # 4. Get detailed sections (Part 2 & 3) and stream them
        detailed_sections = get_all_sections(ticker)  # Already filters out 00_executive

        if not detailed_sections:
            yield error_event(
                f"No detailed sections found for {ticker}.",
                code="SECTIONS_NOT_FOUND"
            )
            return

        total_detailed = len(detailed_sections)

        # 5. Stream detailed sections
        yield progress_event(0, total_detailed, "Loading detailed analysis...")

        for i, section in enumerate(detailed_sections):
            # Send section event (like chunk event)
            yield section_event(
                section_id=section.get('section_id', ''),
                title=section.get('title', ''),
                content=section.get('content', ''),
                part=section.get('part', 0),
                icon=section.get('icon', ''),
                word_count=section.get('word_count', 0),
                display_order=section.get('display_order', 0)
            )

            # Send progress events at key points
            current = i + 1
            if current == 6:  # Halfway through detailed analysis
                yield progress_event(current, total_detailed, "Deep diving into metrics...")
            elif current == 11:  # Before Real Talk (Part 3)
                yield progress_event(current, total_detailed, "Almost done...")

        # 6. Completion event (5 exec + 12 detailed = 17 total sections)
        total_sections = len(exec_item.get('executive_sections', [])) + total_detailed
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
        description="Section identifier (e.g., 06_growth, 11_debt)",
        min_length=1,
        max_length=20
    )
):
    """
    Get a specific section content.

    Enables on-demand section loading for navigation.

    Args:
        ticker: Stock ticker symbol (1-5 letters)
        section_id: Section identifier (e.g., '06_growth')

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
    Get combined executive item (ToC + ratings + 5 executive sections).

    Returns everything needed for initial load in a single DynamoDB read:
    - toc: Full table of contents for all sections
    - ratings: Investment ratings with verdict and conviction
    - executive_sections: Part 1 sections with content
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
        "executive_sections": item.get('executive_sections', []),
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
