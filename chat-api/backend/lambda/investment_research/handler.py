"""
Investment Research Lambda Handler

This handler is for direct Lambda invocations (not via Lambda Web Adapter).
The primary invocation path is via LWA + FastAPI (app.py).

Direct invocation is not recommended for this Lambda because:
1. SSE streaming requires HTTP response streaming (LWA provides this)
2. Direct invocation returns a single JSON response, losing streaming benefits

This handler exists for:
1. Potential future direct invocation needs
2. Consistency with prediction_ensemble pattern
3. Lambda health check via direct invoke
"""

import json
import logging
import os
from datetime import datetime

from config.settings import ENVIRONMENT

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """
    Direct Lambda invocation handler.

    Note: Primary path is via Lambda Web Adapter (app.py).
    This handler is for direct invocations which don't support SSE streaming.

    Supported direct invocation patterns:
    - Health check: {"action": "health"}
    - Get report (non-streaming): {"action": "get_report", "ticker": "AAPL"}

    Args:
        event: Lambda event dict
        context: Lambda context

    Returns:
        Dict with statusCode, headers, and body
    """
    logger.info(f"Direct Lambda invocation: {json.dumps(event)[:200]}")

    action = event.get('action')

    # Health check action
    if action == 'health':
        return _success_response({
            'status': 'healthy',
            'environment': ENVIRONMENT,
            'service': 'investment-research',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'note': 'Use HTTP endpoint for SSE streaming'
        })

    # Get report action (non-streaming fallback)
    if action == 'get_report':
        ticker = event.get('ticker')
        fiscal_year = event.get('fiscal_year')

        if not ticker:
            return _error_response(400, "Missing 'ticker' parameter")

        # Import here to avoid circular imports
        from services.report_service import get_cached_report, validate_ticker

        if not validate_ticker(ticker):
            return _error_response(400, f"Invalid ticker format: {ticker}")

        report = get_cached_report(ticker.upper(), fiscal_year)
        if not report:
            return _error_response(404, f"No report found for {ticker}")

        return _success_response({
            'ticker': report.get('ticker'),
            'fiscal_year': report.get('fiscal_year'),
            'ratings': report.get('ratings'),
            'report_content': report.get('report_content'),
            'generated_at': report.get('generated_at'),
            'note': 'For streaming response, use HTTP endpoint'
        })

    # Default: Return guidance for proper usage
    return _error_response(
        400,
        "Direct invocation not supported for SSE streaming. "
        "Use HTTP endpoint for streaming reports. "
        "Supported direct actions: 'health', 'get_report'"
    )


def handler(event, *args):
    """
    Main entry point for Lambda.

    Routes based on invocation signature for compatibility with
    Lambda Web Adapter streaming patterns.

    Args:
        event: Lambda event
        *args: Additional arguments (context, response_stream for streaming)

    Returns:
        Response from lambda_handler
    """
    if len(args) >= 1:
        context = args[0]
        return lambda_handler(event, context)
    return lambda_handler(event, None)


def _success_response(body: dict) -> dict:
    """Format success response."""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }


def _error_response(status_code: int, message: str) -> dict:
    """Format error response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }
