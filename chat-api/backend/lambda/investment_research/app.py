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
- GET /report/{ticker}/status              - Check report existence/expiration (JSON)
- GET /report/{ticker}/section/{section_id} - Get specific section (JSON)
- GET /report/{ticker}/executive           - Get Part 1 executive sections (JSON)
- GET /report/{ticker}/stream              - Stream all sections as SSE events (v2)
"""

import os
import json
import asyncio
import logging
from datetime import datetime
from typing import AsyncGenerator, Optional, List, Dict, Any
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

import boto3
import jwt
from fastapi import FastAPI, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
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
    get_report_status,
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
    search_reports_in_dynamodb,
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
# JWT Authentication Middleware (SEC-001 Fix)
# =============================================================================

# Environment variables for JWT validation
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')

# Initialize AWS clients lazily
_secrets_client = None


def get_secrets_client():
    """Lazy initialization of Secrets Manager client."""
    global _secrets_client
    if _secrets_client is None:
        _secrets_client = boto3.client('secretsmanager')
    return _secrets_client


@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT secret from AWS Secrets Manager with caching."""
    if JWT_SECRET_ARN:
        try:
            client = get_secrets_client()
            response = client.get_secret_value(SecretId=JWT_SECRET_ARN)
            secret = response['SecretString']
            if not secret or len(secret) < 32:
                raise ValueError("JWT secret must be at least 32 characters long")
            return secret
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret from Secrets Manager: {e}")
            raise Exception("JWT_SECRET not properly configured in Secrets Manager") from e
    else:
        # Require JWT_SECRET environment variable - no default fallback for security
        jwt_secret = os.environ.get('JWT_SECRET')
        if not jwt_secret:
            logger.error("JWT_SECRET environment variable not set")
            raise ValueError("JWT_SECRET must be set via environment variable or JWT_SECRET_ARN must be configured")
        if len(jwt_secret) < 32:
            logger.error("JWT_SECRET is too short")
            raise ValueError("JWT_SECRET must be at least 32 characters long for security")
        return jwt_secret


def verify_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verify JWT token and extract claims.

    Args:
        token: JWT token string

    Returns:
        Dictionary with user claims

    Raises:
        Exception: If token is invalid
    """
    jwt_secret = get_jwt_secret()

    try:
        # Decode and verify the JWT token
        payload = jwt.decode(
            token,
            jwt_secret,
            algorithms=['HS256'],
            options={'verify_exp': True}
        )

        logger.info(f"JWT token verified successfully for user_id={payload.get('user_id')}")
        return payload

    except jwt.ExpiredSignatureError:
        logger.warning("JWT token has expired")
        raise Exception("Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {str(e)}")
        raise Exception("Invalid token")
    except Exception as e:
        logger.error(f"JWT verification error: {str(e)}")
        raise Exception("Token verification failed")


# Endpoints that don't require authentication
PUBLIC_PATHS = {"/health"}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce JWT authentication on protected endpoints.

    SEC-001 Fix: Prevents unauthenticated access to Function URL endpoints
    that invoke paid AI services (Claude Haiku 4.5).

    Public endpoints (no auth required):
    - /health

    Protected endpoints (JWT required):
    - /followup
    - /report/*
    - /reports
    - All other endpoints
    """

    async def dispatch(self, request: Request, call_next):
        # Allow public paths without authentication
        if request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Extract Authorization header
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")

        if not auth_header:
            logger.warning(f"No Authorization header for {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "Unauthorized",
                    "detail": "Missing Authorization header",
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }
            )

        # Extract Bearer token
        if not auth_header.startswith("Bearer "):
            logger.warning(f"Invalid Authorization header format for {request.url.path}")
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "Unauthorized",
                    "detail": "Invalid Authorization header format. Expected: Bearer <token>",
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        try:
            # Verify the JWT token
            claims = verify_jwt_token(token)
            user_id = claims.get('user_id') or claims.get('sub')

            if not user_id:
                logger.warning("JWT token missing user_id claim")
                return JSONResponse(
                    status_code=401,
                    content={
                        "success": False,
                        "error": "Unauthorized",
                        "detail": "Token missing user_id claim",
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    }
                )

            # Add user info to request state for use by endpoints
            request.state.user_id = user_id
            request.state.user_claims = claims

            logger.info(f"Authenticated request from user_id={user_id} to {request.url.path}")
            return await call_next(request)

        except Exception as e:
            logger.warning(f"JWT validation failed for {request.url.path}: {str(e)}")
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": "Unauthorized",
                    "detail": str(e),
                    "timestamp": datetime.utcnow().isoformat() + 'Z'
                }
            )


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

# Add JWT authentication middleware (SEC-001 fix)
app.add_middleware(JWTAuthMiddleware)


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
async def followup_question(raw_request: Request):
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
    # Debug: Log raw request body to diagnose double-encoding issues
    raw_body = await raw_request.body()
    logger.info(f"[DEBUG] Raw body type: {type(raw_body)}, content: {raw_body[:500] if raw_body else 'empty'}")

    # Parse the JSON body manually to handle potential double-encoding
    try:
        body_str = raw_body.decode("utf-8")
        body_data = json.loads(body_str)

        # Check if body is double-encoded (parsed result is a string)
        if isinstance(body_data, str):
            logger.info(f"[DEBUG] Detected double-encoded JSON, re-parsing")
            body_data = json.loads(body_data)

        logger.info(f"[DEBUG] Parsed body: {body_data}")

        # Validate with Pydantic model
        request = FollowUpRequest(**body_data)

    except json.JSONDecodeError as e:
        logger.error(f"[DEBUG] JSON decode error: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except Exception as e:
        logger.error(f"[DEBUG] Request parsing error: {e}")
        raise HTTPException(status_code=422, detail=f"Validation error: {str(e)}")

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

    Queries DynamoDB investment-reports-v2 table for reports matching
    the search query. Allows users to type "Apple" and find AAPL reports.

    Falls back to static company_names dictionary if DynamoDB search
    returns no results (for companies without generated reports).

    Args:
        q: Search query (matches company name or ticker, case insensitive)

    Returns:
        JSONResponse with matching ticker/name pairs
    """
    # Primary: Search in DynamoDB for reports that actually exist
    db_result = search_reports_in_dynamodb(q, limit=10)

    if db_result.get('success') and db_result.get('count', 0) > 0:
        return JSONResponse(content={
            "success": True,
            "query": q,
            "count": db_result['count'],
            "results": db_result['results'],
            "source": "dynamodb",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        })

    # Fallback: Search static dictionary (useful for suggesting companies
    # that don't have reports yet, or if DynamoDB is temporarily unavailable)
    from investment_research.company_names import search_companies
    static_matches = search_companies(q, limit=10)

    return JSONResponse(content={
        "success": True,
        "query": q,
        "count": len(static_matches),
        "results": static_matches,
        "source": "static",
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


@app.get("/report/{ticker}/status")
async def get_status(
    ticker: str = Path(
        ...,
        description="Stock ticker symbol (e.g., AAPL, MSFT)",
        min_length=1,
        max_length=5
    )
):
    """
    Check if a report exists and its expiration status.

    Used for fast conversation loading without fetching full content.
    Returns status info to determine if sections can be fetched on-demand
    or if the report has expired.

    Args:
        ticker: Stock ticker symbol (1-5 letters)

    Returns:
        JSONResponse with exists, expired, ttl_remaining_days, generated_at
    """
    ticker = ticker.upper().strip()
    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ticker format: {ticker}. Must be 1-5 letters."
        )

    logger.info(f"Checking report status for {ticker}")

    status = get_report_status(ticker)
    if not status:
        return JSONResponse(
            status_code=404,
            content={
                "exists": False,
                "ticker": ticker,
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            }
        )

    return JSONResponse(content={
        **status,
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
