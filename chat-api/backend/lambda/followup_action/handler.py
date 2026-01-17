"""
Bedrock Action Group Handler for Investment Research Follow-up Questions.

Handles action group invocations from the Bedrock Follow-up Agent.
Routes requests to the appropriate report service function and returns
Bedrock-compatible JSON responses.

No Lambda Web Adapter needed - returns Bedrock action group format directly.
"""

import json
import logging
import os
from decimal import Decimal
from typing import Any, Dict

from services.report_service import (
    get_available_reports,
    get_metrics_history,
    get_report_ratings,
    get_report_section,
)

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types from DynamoDB."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert Decimal to int or float as appropriate
            if obj % 1 == 0:
                return int(obj)
            return float(obj)
        return super().default(obj)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda entry point for Bedrock action group invocations.

    Args:
        event: Bedrock action group event
        context: Lambda context

    Returns:
        Bedrock action group response format
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # Extract action group metadata
        action_group = event.get('actionGroup', 'ReportResearch')
        api_path = event.get('apiPath', '')
        http_method = event.get('httpMethod', 'POST')

        # Parse request parameters
        parameters = parse_action_group_parameters(event)
        logger.info(f"Parsed parameters: {parameters}")

        # Route to appropriate function based on apiPath
        if api_path == '/getReportSection':
            result = handle_get_report_section(parameters)
        elif api_path == '/getReportRatings':
            result = handle_get_report_ratings(parameters)
        elif api_path == '/getMetricsHistory':
            result = handle_get_metrics_history(parameters)
        elif api_path == '/getAvailableReports':
            result = handle_get_available_reports(parameters)
        else:
            return format_error_response(
                action_group, api_path, http_method,
                f"Unknown apiPath: {api_path}", 400
            )

        return format_success_response(action_group, api_path, http_method, result)

    except Exception as e:
        logger.exception(f"Error processing request: {e}")
        return format_error_response(
            event.get('actionGroup', 'ReportResearch'),
            event.get('apiPath', ''),
            event.get('httpMethod', 'POST'),
            str(e), 500
        )


def parse_action_group_parameters(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse parameters from Bedrock action group event.

    Bedrock sends parameters in requestBody.content.application/json.properties
    as a list of {name, value} objects.
    """
    parameters = {}

    request_body = event.get('requestBody', {})
    content = request_body.get('content', {})
    json_content = content.get('application/json', {})
    properties = json_content.get('properties', [])

    for prop in properties:
        name = prop.get('name')
        value = prop.get('value')
        if name and value is not None:
            parameters[name] = value

    return parameters


def handle_get_report_section(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Handle getReportSection action."""
    ticker = parameters.get('ticker')
    section_id = parameters.get('section_id')

    if not ticker:
        return {'success': False, 'error': 'ticker is required'}
    if not section_id:
        return {'success': False, 'error': 'section_id is required'}

    return get_report_section(ticker, section_id)


def handle_get_report_ratings(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Handle getReportRatings action."""
    ticker = parameters.get('ticker')

    if not ticker:
        return {'success': False, 'error': 'ticker is required'}

    return get_report_ratings(ticker)


def handle_get_metrics_history(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Handle getMetricsHistory action."""
    ticker = parameters.get('ticker')
    metric_type = parameters.get('metric_type', 'all')
    quarters = parameters.get('quarters', 20)

    if not ticker:
        return {'success': False, 'error': 'ticker is required'}

    # Convert quarters to int if string
    if isinstance(quarters, str):
        quarters = int(quarters)

    return get_metrics_history(ticker, metric_type, quarters)


def handle_get_available_reports(parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Handle getAvailableReports action."""
    return get_available_reports()


def format_success_response(
    action_group: str,
    api_path: str,
    http_method: str,
    result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Format successful response in Bedrock action group format.

    The response body must be a JSON string, not a dict.
    """
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json.dumps(result, cls=DecimalEncoder)
                }
            }
        }
    }


def format_error_response(
    action_group: str,
    api_path: str,
    http_method: str,
    error_message: str,
    status_code: int = 500
) -> Dict[str, Any]:
    """Format error response in Bedrock action group format."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': status_code,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({
                        'success': False,
                        'error': error_message
                    })
                }
            }
        }
    }
