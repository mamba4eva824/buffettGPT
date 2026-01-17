"""
Prediction Ensemble Lambda Handler - v2.1.0 (Supervisor Integration)

Slim router that delegates to modular services and handlers.

Supports multiple invocation modes:
- Bedrock Action Group invocations (synchronous) -> handlers.action_group
- Lambda Function URL (SSE streaming) -> handlers.analysis or handlers.supervisor
- API Gateway REST API (streaming or buffered) -> handlers.analysis

Orchestration Modes:
- mode='single': Single agent analysis (legacy)
- mode='supervisor': Multi-agent orchestration with supervisor synthesis

Architecture:
- config/        : Environment settings and prompts
- models/        : Data schemas and metric definitions
- services/      : Business logic (inference, bedrock, persistence, streaming, orchestrator)
- handlers/      : Request handlers (action_group, analysis, supervisor)
- utils/         : Shared utilities (fmp_client, feature_extractor, etc.)

Version History:
- v1.0.x-1.4.x: Monolithic implementation
- v1.5.x: Initial modular config/models extraction
- v1.6.x: Services modules extraction
- v1.7.0: Handlers extraction, slim router
- v2.1.0: Supervisor integration (multi-agent orchestration)
"""

import json
import boto3
import os
import logging
import jwt
from typing import Dict, Any, Optional
from datetime import datetime
from functools import lru_cache

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# ============================================================================
# JWT Authentication (for Function URL - API Gateway uses auth_verify Lambda)
# ============================================================================

secrets_client = boto3.client('secretsmanager')
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')


@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT secret from AWS Secrets Manager with caching."""
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            return response['SecretString']
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret: {e}")
            raise
    jwt_secret = os.environ.get('JWT_SECRET')
    if jwt_secret:
        return jwt_secret
    raise ValueError("JWT_SECRET not configured")


def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract JWT token from Authorization header."""
    headers = event.get('headers', {}) or {}
    auth_header = headers.get('authorization') or headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def verify_jwt_token(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Verify JWT token from request. Returns user claims if valid."""
    token = extract_token(event)
    if not token:
        return None
    try:
        jwt_secret = get_jwt_secret()
        payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={'verify_exp': True})
        logger.info(f"JWT verified for user: {payload.get('user_id', 'unknown')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None


# ============================================================================
# Import Handlers and Services
# ============================================================================

from handlers.action_group import is_action_group_event, handle_action_group_request
from handlers.analysis import handle_function_url_request, handle_api_gateway_request
from handlers.supervisor import handle_supervisor_request
from config.settings import SUPERVISOR_ENABLED, ORCHESTRATION_MODE
from services.streaming import format_sse_event
from services.inference import run_inference
from services.persistence import save_message
from services.bedrock import invoke_agent_streaming
from utils.fmp_client import get_financial_data, normalize_ticker, validate_ticker
from utils.feature_extractor import extract_all_features
from utils.conversation_updater import update_conversation_timestamp
from models.schemas import DecimalEncoder


# ============================================================================
# Error Response Helper
# ============================================================================

def error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({
            'success': False,
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }


# ============================================================================
# Lambda Handler (Standard Invocation)
# ============================================================================

def lambda_handler(event: Dict[str, Any], context: Any):
    """
    Main Lambda handler for ensemble analysis.

    Routes to appropriate handler based on event type:
    - Bedrock Action Group -> handlers.action_group
    - Function URL -> handlers.analysis (buffered SSE)
    - API Gateway -> handlers.analysis (JSON response)
    """
    # Route: Bedrock Action Group (no JWT required)
    if is_action_group_event(event):
        logger.info("Routing to action group handler")
        return handle_action_group_request(event)

    # Route: HTTP requests (Function URL or API Gateway)
    request_context = event.get('requestContext', {})
    is_function_url = 'http' in request_context

    # JWT Authentication required for HTTP requests
    user_claims = verify_jwt_token(event)
    if not user_claims:
        logger.warning("Unauthorized request - invalid or missing JWT token")
        return error_response(401, "Unauthorized - valid JWT token required")

    # Parse request body to check mode
    try:
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')
        body = json.loads(body_str)
        mode = body.get('mode', ORCHESTRATION_MODE)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to parse body for mode detection: {e}")
        mode = ORCHESTRATION_MODE

    # Route: Supervisor mode (multi-agent orchestration)
    if mode == 'supervisor' and SUPERVISOR_ENABLED:
        logger.info(f"Routing to supervisor handler (mode={mode}, enabled={SUPERVISOR_ENABLED})")
        return handle_supervisor_request(event, context, user_claims)

    # Route: Function URL (buffered SSE response) - single agent mode
    if is_function_url:
        return handle_function_url_request(event, context, user_claims)

    # Route: API Gateway (JSON response) - single agent mode
    try:
        return handle_api_gateway_request(event, context, user_claims)
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return error_response(500, str(e))


# ============================================================================
# Streaming Handler (API Gateway with InvokeWithResponseStream)
# ============================================================================

def streaming_handler(event: Dict[str, Any], response_stream, context: Any):
    """
    Lambda handler for true response streaming via InvokeWithResponseStream.

    Used when API Gateway invokes with response_transfer_mode=STREAM.
    Writes SSE events directly to response stream for real-time delivery.

    Note: JWT authentication handled by API Gateway authorizer.
    """
    try:
        from awslambdaric.lambda_response_stream import ResponseStream

        logger.info("Using streaming handler (InvokeWithResponseStream)")

        # Set HTTP response metadata
        response_stream.response.status_code = 200
        response_stream.response.content_type = "text/event-stream"
        response_stream.response.headers["Cache-Control"] = "no-cache"
        response_stream.response.headers["Connection"] = "keep-alive"
        response_stream.response.headers["Access-Control-Allow-Origin"] = "*"
        response_stream.response.headers["Access-Control-Allow-Headers"] = "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        response_stream.response.headers["Access-Control-Allow-Methods"] = "POST,OPTIONS"

        # Action group in streaming handler (shouldn't happen, but handle it)
        if is_action_group_event(event):
            logger.info("Action group event in streaming handler - delegating")
            result = handle_action_group_request(event)
            response_stream.write(json.dumps(result))
            return

        # Parse request
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')

        body = json.loads(body_str)
        path_params = event.get('pathParameters') or {}
        agent_type = path_params.get('agent_type') or body.get('agent_type', 'debt')
        company_input = body.get('company', body.get('ticker', '')).strip()
        fiscal_year = body.get('fiscal_year', datetime.now().year)
        session_id = body.get('session_id', f"stream-{context.aws_request_id}")
        conversation_id = body.get('conversation_id')

        # Get user info from authorizer context
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        user_id = authorizer.get('user_id') or authorizer.get('sub') or 'authenticated'

        # Validate agent_type
        valid_agents = ['debt', 'cashflow', 'growth']
        if agent_type not in valid_agents:
            response_stream.write(format_sse_event(json.dumps({
                "type": "error",
                "message": f"Invalid agent_type: {agent_type}. Must be one of: {valid_agents}"
            }), "error"))
            return

        # Normalize and validate ticker
        ticker = normalize_ticker(company_input)
        if not validate_ticker(ticker):
            response_stream.write(format_sse_event(json.dumps({
                "type": "error",
                "message": f"Invalid company/ticker: {company_input}"
            }), "error"))
            return

        logger.info(f"Streaming analysis for {ticker} with {agent_type} agent")

        # Stream: Connection
        response_stream.write(format_sse_event(json.dumps({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "connected"))

        # Stream: Fetching data
        response_stream.write(format_sse_event(json.dumps({
            "type": "status",
            "message": f"Fetching financial data for {ticker}...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status"))

        financial_data = get_financial_data(ticker, fiscal_year)
        if not financial_data or 'raw_financials' not in financial_data:
            response_stream.write(format_sse_event(json.dumps({
                "type": "error",
                "message": f"Could not fetch financial data for {ticker}"
            }), "error"))
            return

        # Stream: Extracting features
        response_stream.write(format_sse_event(json.dumps({
            "type": "status",
            "message": "Extracting financial features...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status"))

        features = extract_all_features(financial_data['raw_financials'])

        # Stream: Running inference
        response_stream.write(format_sse_event(json.dumps({
            "type": "status",
            "message": f"Running {agent_type} model inference...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status"))

        inference_result = run_inference(agent_type, features)

        # Stream: Inference results
        response_stream.write(format_sse_event(json.dumps({
            "type": "inference",
            "agent_type": agent_type,
            "ticker": ticker,
            "prediction": inference_result['prediction'],
            "confidence": inference_result['confidence'],
            "ci_width": inference_result['ci_width'],
            "confidence_interpretation": inference_result['confidence_interpretation'],
            "probabilities": inference_result['probabilities'],
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "inference"))

        # Stream: Generating analysis
        response_stream.write(format_sse_event(json.dumps({
            "type": "status",
            "message": f"Generating {agent_type} expert analysis...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status"))

        # Stream: Agent response chunks
        accumulated_text = []
        for chunk in invoke_agent_streaming(
            agent_type, ticker, fiscal_year,
            inference_result, features, session_id
        ):
            response_stream.write(chunk)
            if 'data: ' in chunk:
                try:
                    data_line = chunk.split('data: ')[1].split('\n')[0]
                    data = json.loads(data_line)
                    if data.get('type') == 'chunk' and 'text' in data:
                        accumulated_text.append(data['text'])
                except (json.JSONDecodeError, IndexError):
                    pass

        # Stream: Completion
        response_stream.write(format_sse_event(json.dumps({
            "type": "complete",
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "agent_type": agent_type,
            "session_id": session_id,
            "inference": inference_result,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "complete"))

        # Save to conversation (only for debt agent to avoid duplicates)
        if conversation_id and accumulated_text and agent_type == 'debt':
            full_response = ''.join(accumulated_text)
            save_message(conversation_id, user_id, 'user', f"Analyze {company_input}")
            save_message(conversation_id, user_id, 'assistant', full_response)
            update_conversation_timestamp(conversation_id, user_id=user_id)

        logger.info(f"Streaming complete for {ticker} with {agent_type} agent")

    except Exception as e:
        logger.error(f"Streaming handler error: {e}", exc_info=True)
        try:
            response_stream.response.status_code = 500
            response_stream.response.content_type = "application/json"
            response_stream.response.headers["Access-Control-Allow-Origin"] = "*"
        except Exception:
            pass
        response_stream.write(format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error"))


# ============================================================================
# Main Entry Point
# ============================================================================

def handler(event, *args):
    """
    Main entry point that routes to the appropriate handler.

    For InvokeWithResponseStream (response_transfer_mode=STREAM):
        - 3 args: (event, response_stream, context) -> streaming_handler

    For standard Invoke:
        - 2 args: (event, context) -> lambda_handler
    """
    if len(args) == 2:
        response_stream, context = args
        logger.info("Detected streaming invocation (InvokeWithResponseStream)")
        return streaming_handler(event, response_stream, context)
    elif len(args) == 1:
        context = args[0]
        logger.info("Detected standard invocation (Invoke)")
        return lambda_handler(event, context)
    else:
        raise ValueError(f"Unexpected number of arguments: {len(args) + 1}")
