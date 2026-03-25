"""
Admin Settings Handler
Manages runtime configuration via DynamoDB admin-config table.

Routes:
    GET  /admin/settings            — Read all settings
    PUT  /admin/settings/{category} — Update a settings category
"""

import json
import os
import boto3
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
ADMIN_CONFIG_TABLE = os.environ.get('ADMIN_CONFIG_TABLE')

# DynamoDB - lazy initialization to support mocking in tests
_dynamodb = None
admin_table = None


def _get_admin_table():
    """Get or initialize the admin config DynamoDB table."""
    global _dynamodb, admin_table
    if admin_table is not None:
        return admin_table
    if not ADMIN_CONFIG_TABLE:
        return None
    if _dynamodb is None:
        _dynamodb = boto3.resource('dynamodb')
    admin_table = _dynamodb.Table(ADMIN_CONFIG_TABLE)
    return admin_table

VALID_CATEGORIES = [
    'token_limits',
    'rate_limits',
    'model_config',
    'feature_flags',
    'notification_thresholds',
    'referral_tiers',
]


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            if obj == int(obj):
                return int(obj)
            return float(obj)
        return super().default(obj)


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────

def _validate_range(value, field, min_val, max_val, errors):
    """Validate a numeric value is within range."""
    if value is None:
        return
    try:
        num = float(value)
    except (TypeError, ValueError):
        errors.append({'field': field, 'message': f'{field} must be a number'})
        return
    if num < min_val or num > max_val:
        errors.append({'field': field, 'message': f'{field} must be between {min_val} and {max_val}'})


def validate_settings(category: str, values: Any) -> List[Dict[str, str]]:
    """Validate settings values for a category. Returns list of error dicts."""
    errors: List[Dict[str, str]] = []

    if category == 'token_limits':
        if not isinstance(values, dict):
            return [{'field': 'token_limits', 'message': 'must be an object'}]
        for field in ('plus', 'free', 'default_fallback'):
            _validate_range(values.get(field), field, 1000, 100000000, errors)
        followup = values.get('followup_access')
        if isinstance(followup, dict):
            for field in ('anonymous', 'free', 'plus'):
                _validate_range(followup.get(field), f'followup_access.{field}', 0, 100000000, errors)

    elif category == 'rate_limits':
        if not isinstance(values, dict):
            return [{'field': 'rate_limits', 'message': 'must be an object'}]
        _validate_range(values.get('anonymous_monthly'), 'anonymous_monthly', 0, 1000, errors)
        _validate_range(values.get('authenticated_monthly'), 'authenticated_monthly', 0, 100000, errors)

    elif category == 'model_config':
        if not isinstance(values, dict):
            return [{'field': 'model_config', 'message': 'must be an object'}]
        for key in ('followup_temperature', 'market_intel_temperature'):
            if key in values:
                _validate_range(values[key], key, 0.0, 1.0, errors)
        for key in ('followup_max_tokens', 'market_intel_max_tokens'):
            if key in values:
                _validate_range(values[key], key, 256, 8192, errors)
        if 'max_orchestration_turns' in values:
            _validate_range(values['max_orchestration_turns'], 'max_orchestration_turns', 1, 50, errors)

    elif category == 'feature_flags':
        if not isinstance(values, dict):
            return [{'field': 'feature_flags', 'message': 'must be an object'}]

    elif category == 'notification_thresholds':
        if not isinstance(values, dict):
            return [{'field': 'notification_thresholds', 'message': 'must be an object'}]
        for key in ('warning_percent', 'critical_percent'):
            if key in values:
                _validate_range(values[key], key, 1, 99, errors)

    elif category == 'referral_tiers':
        if not isinstance(values, list):
            return [{'field': 'referral_tiers', 'message': 'must be an array'}]
        for i, tier in enumerate(values):
            if not isinstance(tier, dict):
                errors.append({'field': f'referral_tiers[{i}]', 'message': 'must be an object'})
                continue
            _validate_range(tier.get('threshold'), f'referral_tiers[{i}].threshold', 1, 100, errors)
            _validate_range(tier.get('trial_days'), f'referral_tiers[{i}].trial_days', 1, 365, errors)

    return errors


# ──────────────────────────────────────────────
# Auth helpers
# ──────────────────────────────────────────────

def _is_admin(event: Dict[str, Any]) -> bool:
    """Check if the request comes from an admin user."""
    try:
        authorizer = event.get('requestContext', {}).get('authorizer', {})
        # HTTP API v2 Lambda authorizer context is under 'lambda' key
        lambda_ctx = authorizer.get('lambda', {})
        return lambda_ctx.get('is_admin') == 'true'
    except Exception:
        return False


def _get_admin_email(event: Dict[str, Any]) -> str:
    """Extract admin email from authorizer context."""
    try:
        authorizer = event.get('requestContext', {}).get('authorizer', {})
        lambda_ctx = authorizer.get('lambda', {})
        return lambda_ctx.get('email', 'unknown')
    except Exception:
        return 'unknown'


# ──────────────────────────────────────────────
# CRUD operations
# ──────────────────────────────────────────────

def _get_settings() -> Dict[str, Any]:
    """Read all categories from DynamoDB."""
    table = _get_admin_table()
    if not table:
        return {}

    response = table.scan()
    settings: Dict[str, Any] = {}
    for item in response.get('Items', []):
        key = item.get('config_key')
        val = item.get('config_value')
        if key and val is not None:
            settings[key] = val
    return settings


def _update_settings(category: str, body: Any, admin_email: str) -> Dict[str, Any]:
    """Validate and write a category to DynamoDB."""
    errors = validate_settings(category, body)
    if errors:
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': 'Validation failed',
                'details': errors,
            }),
        }

    now = datetime.utcnow().isoformat()
    # Convert floats to Decimal for DynamoDB
    config_value = json.loads(json.dumps(body), parse_float=Decimal)

    _get_admin_table().put_item(
        Item={
            'config_key': category,
            'config_value': config_value,
            'updated_at': now,
            'updated_by': admin_email,
        }
    )

    logger.info(f"Admin settings updated", extra={
        'category': category,
        'updated_by': admin_email,
    })

    return {
        'statusCode': 200,
        'body': json.dumps({
            'success': True,
            'category': category,
            'updated_at': now,
        }),
    }


# ──────────────────────────────────────────────
# Lambda entry point
# ──────────────────────────────────────────────

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Route GET /admin/settings and PUT /admin/settings/{category}."""
    logger.info("Admin handler invoked", extra={
        'path': event.get('rawPath', ''),
        'method': event.get('requestContext', {}).get('http', {}).get('method', ''),
    })

    # Auth check
    if not _is_admin(event):
        return _response(403, {'error': 'Forbidden', 'message': 'Admin access required'})

    if not _get_admin_table():
        return _response(500, {'error': 'ADMIN_CONFIG_TABLE not configured'})

    method = event.get('requestContext', {}).get('http', {}).get('method', '')
    raw_path = event.get('rawPath', '')
    # Strip stage prefix (e.g. /dev/admin/settings → /admin/settings)
    path_parts = raw_path.strip('/').split('/')
    if path_parts and path_parts[0] == ENVIRONMENT:
        path_parts = path_parts[1:]
    path = '/' + '/'.join(path_parts)

    if method == 'GET' and path == '/admin/settings':
        settings = _get_settings()
        return _response(200, {'settings': settings})

    if method == 'PUT' and path.startswith('/admin/settings/'):
        category = path_parts[-1] if path_parts else ''
        if category not in VALID_CATEGORIES:
            return _response(404, {'error': f'Unknown category: {category}'})

        try:
            body = json.loads(event.get('body', '{}'))
        except (json.JSONDecodeError, TypeError):
            return _response(400, {'error': 'Invalid JSON body'})

        admin_email = _get_admin_email(event)
        result = _update_settings(category, body, admin_email)
        return _make_cors_response(result)

    return _response(404, {'error': 'Not found'})


def _response(status_code: int, body: Any) -> Dict[str, Any]:
    """Create API Gateway response with CORS headers."""
    return _make_cors_response({
        'statusCode': status_code,
        'body': json.dumps(body, cls=DecimalEncoder),
    })


def _make_cors_response(result: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure CORS headers are present."""
    headers = result.get('headers', {})
    headers.update({
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,PUT,OPTIONS',
    })
    result['headers'] = headers
    if 'statusCode' not in result:
        result['statusCode'] = 200
    return result
