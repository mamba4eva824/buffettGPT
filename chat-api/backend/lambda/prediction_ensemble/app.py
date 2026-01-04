"""
FastAPI Application for Ensemble Analyzer
Provides SSE streaming responses via Lambda Web Adapter

Endpoints:
- POST /supervisor - Run multi-agent supervisor analysis with streaming response
- POST /analyze - Value investor analysis for Bedrock action groups (non-streaming)
- POST /action-group - Handle Bedrock Action Group invocations (legacy, non-streaming)
- GET /health - Health check for Lambda Web Adapter

Uses ConverseStream API for Bedrock streaming with token counting.
"""

import json
import os
import logging
from typing import AsyncGenerator, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Import from modular services (v1.7.0 refactor)
from utils.fmp_client import normalize_ticker, validate_ticker
from utils.conversation_updater import update_conversation_timestamp
from services.persistence import save_message
from handlers.action_group import is_action_group_event, handle_action_group_request
from models.schemas import DecimalEncoder
from config.settings import ENVIRONMENT, PROJECT_NAME, SUPERVISOR_ENABLED
from services.orchestrator import orchestrate_supervisor_analysis


# ============================================================================
# Pydantic Models
# ============================================================================

class SupervisorRequest(BaseModel):
    """Request model for supervisor analysis endpoint."""
    company: str = Field(..., description="Company name or ticker symbol")
    fiscal_year: Optional[int] = Field(None, description="Fiscal year for analysis")
    session_id: Optional[str] = Field(None, description="Session ID for conversation memory")
    conversation_id: Optional[str] = Field(None, description="Conversation ID for message persistence")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    environment: str


# ============================================================================
# FastAPI Application
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Ensemble Analyzer FastAPI application starting")
    yield
    logger.info("Ensemble Analyzer FastAPI application shutting down")


app = FastAPI(
    title="Ensemble Analyzer API",
    description="Financial analysis with ML inference and Bedrock streaming",
    version="2.0.0",
    lifespan=lifespan
)

# ============================================================================
# Bedrock Agent Middleware for Lambda Web Adapter
# Handles transformation between Bedrock action group events and HTTP requests
# ============================================================================
try:
    from bedrock_agent.middleware import BedrockAgentMiddleware
    # Use /events as the pass-through path (matches AWS_LWA_PASS_THROUGH_PATH)
    app.add_middleware(BedrockAgentMiddleware, pass_through_path="/events")
    logger.info("BedrockAgentMiddleware enabled for action group handling")
except ImportError:
    logger.warning("BedrockAgentMiddleware not available - action groups may not work correctly")


# ============================================================================
# SSE Event Formatting
# ============================================================================

def format_sse_data(data: dict) -> dict:
    """Format data for SSE event."""
    return {
        "event": data.get("type", "message"),
        "data": json.dumps(data, cls=DecimalEncoder)
    }


def parse_sse_string(sse_string: str) -> dict:
    """
    Parse SSE-formatted string into dict for EventSourceResponse.

    Input format: "event: type\ndata: json\n\n"
    Output format: {"event": "type", "data": "json"}
    """
    event_type = "message"
    data = ""

    for line in sse_string.strip().split('\n'):
        if line.startswith('event: '):
            event_type = line[7:]
        elif line.startswith('data: '):
            data = line[6:]

    return {"event": event_type, "data": data}


async def generate_supervisor_stream(
    ticker: str,
    fiscal_year: int,
    session_id: str,
    conversation_id: Optional[str] = None,
    user_id: str = "authenticated"
) -> AsyncGenerator[dict, None]:
    """
    Generate SSE events for supervisor multi-agent analysis.

    Wraps the orchestrator's async generator and converts SSE strings
    to dicts for EventSourceResponse compatibility.

    Also handles conversation persistence by accumulating supervisor text
    and inference predictions for structured storage.
    """
    accumulated_text = []
    inference_data = {}  # Capture predictions: {debt: {prediction, confidence}, ...}
    start_time = datetime.utcnow()

    try:
        # Iterate through orchestrator events
        async for sse_string in orchestrate_supervisor_analysis(
            ticker=ticker,
            fiscal_year=fiscal_year,
            session_id=session_id
        ):
            # Parse SSE string to dict for EventSourceResponse
            event_dict = parse_sse_string(sse_string)
            yield event_dict

            # Capture data for persistence
            try:
                data = json.loads(event_dict.get("data", "{}"))

                # Capture inference events (predictions for each agent)
                if data.get("type") == "inference":
                    agent_type = data.get("agent_type")
                    if agent_type in ['debt', 'cashflow', 'growth']:
                        inference_data[agent_type] = {
                            'prediction': data.get('prediction'),
                            'confidence': data.get('confidence')
                        }

                # Accumulate supervisor text
                if data.get("type") == "chunk" and data.get("agent_type") == "supervisor":
                    accumulated_text.append(data.get("text", ""))
            except json.JSONDecodeError:
                pass

        # Save messages to conversation if provided
        if conversation_id and (accumulated_text or inference_data):
            processing_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Save user query
            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                message_type='user',
                content=f"Analyze {ticker}"
            )

            # Save structured analysis result as JSON
            analysis_result = {
                "_type": "supervisor_analysis",
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "predictions": inference_data,
                "synthesis": ''.join(accumulated_text)
            }
            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                message_type='assistant',
                content=json.dumps(analysis_result),
                processing_time_ms=processing_time_ms
            )
            update_conversation_timestamp(conversation_id, user_id=user_id)
            logger.info(f"Saved supervisor analysis to conversation {conversation_id} with {len(inference_data)} predictions")

    except Exception as e:
        logger.error(f"Supervisor stream error: {e}", exc_info=True)
        yield format_sse_data({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        })


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Lambda Web Adapter."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + 'Z',
        environment=ENVIRONMENT
    )


@app.post("/supervisor")
async def supervisor_analysis(
    raw_request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Run supervisor multi-agent analysis with SSE streaming response.

    Orchestrates 3 expert agents (debt, cashflow, growth) in parallel,
    then streams supervisor synthesis with Buffett's principles.

    Returns:
        EventSourceResponse with SSE stream including:
        - 3 inference events (one per model)
        - Status updates for each stage
        - Supervisor synthesis chunks
        - Complete event with processing metrics
    """
    if not SUPERVISOR_ENABLED:
        raise HTTPException(
            status_code=503,
            detail="Supervisor mode is not enabled"
        )

    # Parse request body
    try:
        body = await raw_request.body()
        body_str = body.decode('utf-8')

        try:
            body_data = json.loads(body_str)
        except json.JSONDecodeError:
            body_data = body_str

        if isinstance(body_data, str):
            try:
                body_data = json.loads(body_data)
            except (json.JSONDecodeError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid request body format: {body_data[:100]}"
                )

        request = SupervisorRequest(**body_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error parsing supervisor request body: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid request body: {str(e)}"
        )

    # Normalize and validate ticker
    ticker = normalize_ticker(request.company)

    if not validate_ticker(ticker):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid company/ticker: {request.company}"
        )

    # Set defaults
    fiscal_year = request.fiscal_year or datetime.now().year
    session_id = request.session_id or f"supervisor-{datetime.utcnow().timestamp()}"

    logger.info(f"Starting supervisor analysis for {ticker} (FY{fiscal_year})")

    # Return SSE streaming response
    return EventSourceResponse(
        generate_supervisor_stream(
            ticker=ticker,
            fiscal_year=fiscal_year,
            session_id=session_id,
            conversation_id=request.conversation_id,
            user_id="authenticated"
        ),
        media_type="text/event-stream"
    )


# ============================================================================
# Action Group Analysis Endpoint (for Bedrock Agent Middleware)
# ============================================================================

class ActionGroupRequest(BaseModel):
    """Request model for action group analysis."""
    ticker: str = Field(..., description="Stock ticker symbol")
    analysis_type: str = Field("all", description="Type of analysis: debt, cashflow, growth, or all")


@app.post("/analyze")
async def analyze_financial_data(request: ActionGroupRequest):
    """
    Value investor financial analysis endpoint for Bedrock action groups.

    This endpoint is called by the BedrockAgentMiddleware when action groups
    invoke the /analyze path. Returns ML predictions and value metrics.
    """
    try:
        from utils.fmp_client import get_financial_data as fetch_financial_data
        from utils.feature_extractor import extract_all_features, extract_quarterly_trends
        from services.inference import run_inference
        from handlers.action_group import extract_value_metrics
        from models.schemas import json_dumps
        from config.settings import USE_VALUE_INVESTOR_FORMAT

        ticker = normalize_ticker(request.ticker)
        if not validate_ticker(ticker):
            raise HTTPException(status_code=400, detail=f"Invalid ticker: {request.ticker}")

        analysis_type = request.analysis_type or "all"
        logger.info(f"[ANALYZE_ENDPOINT] Processing {ticker} for {analysis_type} analysis")

        # Fetch financial data
        financial_data = fetch_financial_data(ticker)
        if not financial_data or 'error' in financial_data:
            error_msg = financial_data.get('error', 'Failed to fetch financial data') if financial_data else 'Failed to fetch financial data'
            raise HTTPException(status_code=500, detail=error_msg)

        raw_financials = financial_data.get('raw_financials', {})

        # Extract features
        all_features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        # Run ML inference
        if analysis_type == 'all':
            model_types = ['debt', 'cashflow', 'growth']
        else:
            model_types = [analysis_type]

        model_inference = {}
        for model_type in model_types:
            try:
                result = run_inference(model_type, all_features)
                model_inference[model_type] = result
                logger.info(f"[ANALYZE_ENDPOINT] {model_type} inference: {result.get('prediction')} ({result.get('confidence', 0):.0%})")
            except Exception as e:
                logger.error(f"Inference failed for {model_type}: {e}")
                model_inference[model_type] = {'error': str(e)}

        # Build response
        value_metrics = extract_value_metrics(quarterly_trends, all_features, analysis_type)

        response_body = {
            'ticker': ticker,
            'analysis_type': analysis_type,
            'model_inference': model_inference,
            'value_metrics': value_metrics,
            'metadata': {
                'quarters_analyzed': len(value_metrics.get('quarters', [])),
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'data_source': 'FMP',
                'model_version': 'v1.0.0'
            }
        }

        logger.info(f"[ANALYZE_ENDPOINT] Successfully processed {ticker}")
        # Return raw response body with explicit Content-Type (no charset)
        # The BedrockAgentMiddleware will wrap this in Bedrock format
        # Using explicit Content-Type ensures the middleware uses "application/json" as key
        # (not "application/json; charset=utf-8" which Bedrock rejects)
        return JSONResponse(
            content=response_body,
            media_type="application/json"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ANALYZE_ENDPOINT] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/action-group")
async def handle_action_group(request: Request):
    """
    Handle Bedrock Action Group invocations (legacy endpoint).
    Non-streaming endpoint for agent tool calls.

    Note: With BedrockAgentMiddleware, action groups should route to /analyze instead.
    This endpoint is kept for backwards compatibility.
    """
    try:
        event = await request.json()

        if not is_action_group_event(event):
            raise HTTPException(
                status_code=400,
                detail="Invalid action group event format"
            )

        result = handle_action_group_request(event)
        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"Action group error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": str(exc),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }
    )
