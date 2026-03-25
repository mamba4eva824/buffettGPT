"""
Unit tests for Admin Handler Lambda.

Tests all admin settings API endpoints including:
- GET /admin/settings — Read all settings
- PUT /admin/settings/{category} — Update a settings category
- Authorization checks (403 for non-admins)
- Input validation for each category

Run with: pytest tests/unit/test_admin_handler.py -v
"""

import json
import os
import sys
import pytest
import boto3
from moto import mock_aws
from unittest.mock import patch, MagicMock
from decimal import Decimal

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment BEFORE any handler imports
os.environ['ENVIRONMENT'] = 'test'
os.environ['ADMIN_CONFIG_TABLE'] = 'buffett-test-admin-config'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['AWS_ACCESS_KEY_ID'] = 'testing'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'testing'


# =============================================================================
# DynamoDB Table Helpers
# =============================================================================

def create_admin_config_table(dynamodb):
    """Create admin-config table."""
    table = dynamodb.create_table(
        TableName='buffett-test-admin-config',
        KeySchema=[{'AttributeName': 'config_key', 'KeyType': 'HASH'}],
        AttributeDefinitions=[
            {'AttributeName': 'config_key', 'AttributeType': 'S'},
        ],
        BillingMode='PAY_PER_REQUEST'
    )
    table.wait_until_exists()
    return table


def seed_settings(table):
    """Seed the table with default settings."""
    table.put_item(Item={
        'config_key': 'token_limits',
        'config_value': {
            'plus': 2000000,
            'free': 100000,
            'default_fallback': 100000,
            'followup_access': {'anonymous': 0, 'free': 0, 'plus': 1000000},
        },
        'updated_at': '2026-01-01T00:00:00',
        'updated_by': 'seed',
    })
    table.put_item(Item={
        'config_key': 'feature_flags',
        'config_value': {
            'enable_rate_limiting': True,
            'enable_device_fingerprinting': True,
        },
        'updated_at': '2026-01-01T00:00:00',
        'updated_by': 'seed',
    })


def setup_handler(dynamodb, table):
    """Import handler and inject mocked DynamoDB table."""
    import handlers.admin_handler as handler
    handler.admin_table = table
    handler._dynamodb = dynamodb
    return handler


def teardown_handler():
    """Reset handler module state between tests."""
    import handlers.admin_handler as handler
    handler.admin_table = None
    handler._dynamodb = None


def build_api_event(
    method='GET',
    path='/admin/settings',
    body=None,
    is_admin=True,
    email='admin@example.com',
):
    """Build a mock API Gateway v2 event."""
    event = {
        'rawPath': f'/test{path}',
        'requestContext': {
            'http': {'method': method},
            'authorizer': {
                'lambda': {
                    'user_id': 'user-123',
                    'is_admin': 'true' if is_admin else 'false',
                    'email': email,
                }
            },
        },
        'headers': {},
    }
    if body is not None:
        event['body'] = json.dumps(body)
    return event


# =============================================================================
# Test Class: Authorization
# =============================================================================

class TestAuthorization:
    """Tests for admin authorization checks."""

    @mock_aws
    def test_non_admin_returns_403(self):
        """
        Given: A request from a non-admin user
        When: Handler is invoked
        Then: Returns 403 Forbidden
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = dynamodb.Table('buffett-test-admin-config')
        handler._dynamodb = dynamodb

        event = build_api_event(is_admin=False)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        handler.admin_table = None  # Reset for next test

        assert response['statusCode'] == 403
        body = json.loads(response['body'])
        assert body['error'] == 'Forbidden'

    @mock_aws
    def test_missing_authorizer_returns_403(self):
        """
        Given: A request without authorizer context
        When: Handler is invoked
        Then: Returns 403 Forbidden
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = dynamodb.Table('buffett-test-admin-config')
        handler._dynamodb = dynamodb

        event = {
            'rawPath': '/test/admin/settings',
            'requestContext': {
                'http': {'method': 'GET'},
                'authorizer': {},
            },
            'headers': {},
        }
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        handler.admin_table = None  # Reset for next test

        assert response['statusCode'] == 403


# =============================================================================
# Test Class: GET /admin/settings
# =============================================================================

class TestGetSettings:
    """Tests for reading admin settings."""

    @mock_aws
    def test_get_all_settings(self):
        """
        Given: Admin user and seeded settings
        When: GET /admin/settings
        Then: Returns all setting categories
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)
        seed_settings(table)

        import handlers.admin_handler as handler
        handler.admin_table = table

        event = build_api_event(method='GET', path='/admin/settings')
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'settings' in body
        assert 'token_limits' in body['settings']
        assert 'feature_flags' in body['settings']

    @mock_aws
    def test_get_empty_settings(self):
        """
        Given: Admin user and empty table
        When: GET /admin/settings
        Then: Returns empty settings dict
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        event = build_api_event(method='GET', path='/admin/settings')
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['settings'] == {}


# =============================================================================
# Test Class: PUT /admin/settings/{category}
# =============================================================================

class TestUpdateSettings:
    """Tests for updating admin settings."""

    @mock_aws
    def test_update_token_limits(self):
        """
        Given: Valid token_limits payload
        When: PUT /admin/settings/token_limits
        Then: Returns success and persists data
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {
            'plus': 3000000,
            'free': 200000,
            'default_fallback': 150000,
            'followup_access': {'anonymous': 0, 'free': 0, 'plus': 2000000},
        }
        event = build_api_event(method='PUT', path='/admin/settings/token_limits', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['success'] is True
        assert body['category'] == 'token_limits'

        # Verify persisted
        item = table.get_item(Key={'config_key': 'token_limits'})['Item']
        assert item['config_value']['plus'] == 3000000
        assert item['updated_by'] == 'admin@example.com'

    @mock_aws
    def test_update_feature_flags(self):
        """
        Given: Valid feature_flags payload
        When: PUT /admin/settings/feature_flags
        Then: Returns success
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {'enable_rate_limiting': False, 'enable_device_fingerprinting': True}
        event = build_api_event(method='PUT', path='/admin/settings/feature_flags', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200

    @mock_aws
    def test_update_referral_tiers(self):
        """
        Given: Valid referral_tiers array
        When: PUT /admin/settings/referral_tiers
        Then: Returns success
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = [
            {'threshold': 5, 'trial_days': 90},
            {'threshold': 3, 'trial_days': 30},
        ]
        event = build_api_event(method='PUT', path='/admin/settings/referral_tiers', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200

    @mock_aws
    def test_unknown_category_returns_404(self):
        """
        Given: Unknown category name
        When: PUT /admin/settings/unknown_cat
        Then: Returns 404
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        event = build_api_event(method='PUT', path='/admin/settings/unknown_cat', body={})
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'Unknown category' in body['error']

    @mock_aws
    def test_invalid_json_body_returns_400(self):
        """
        Given: Invalid JSON in request body
        When: PUT /admin/settings/token_limits
        Then: Returns 400
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        event = build_api_event(method='PUT', path='/admin/settings/token_limits')
        event['body'] = 'not valid json {'
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 400


# =============================================================================
# Test Class: Validation
# =============================================================================

class TestValidation:
    """Tests for settings validation rules."""

    @mock_aws
    def test_token_limits_below_minimum(self):
        """
        Given: token_limits with value below minimum (1000)
        When: PUT /admin/settings/token_limits
        Then: Returns 400 with field-level errors
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {'plus': 500, 'free': 100000, 'default_fallback': 100000}
        event = build_api_event(method='PUT', path='/admin/settings/token_limits', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error'] == 'Validation failed'
        assert len(body['details']) > 0
        assert body['details'][0]['field'] == 'plus'

    @mock_aws
    def test_model_config_temperature_out_of_range(self):
        """
        Given: model_config with temperature > 1.0
        When: PUT /admin/settings/model_config
        Then: Returns 400
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {'followup_temperature': 1.5, 'followup_max_tokens': 2048}
        event = build_api_event(method='PUT', path='/admin/settings/model_config', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert any(d['field'] == 'followup_temperature' for d in body['details'])

    @mock_aws
    def test_notification_thresholds_out_of_range(self):
        """
        Given: notification_thresholds with percent > 99
        When: PUT /admin/settings/notification_thresholds
        Then: Returns 400
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {'warning_percent': 0, 'critical_percent': 100}
        event = build_api_event(method='PUT', path='/admin/settings/notification_thresholds', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert len(body['details']) == 2

    @mock_aws
    def test_referral_tiers_invalid_values(self):
        """
        Given: referral_tiers with threshold > 100
        When: PUT /admin/settings/referral_tiers
        Then: Returns 400
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = [{'threshold': 200, 'trial_days': 30}]
        event = build_api_event(method='PUT', path='/admin/settings/referral_tiers', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 400

    @mock_aws
    def test_rate_limits_valid_update(self):
        """
        Given: Valid rate_limits values
        When: PUT /admin/settings/rate_limits
        Then: Returns 200
        """
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = create_admin_config_table(dynamodb)

        import handlers.admin_handler as handler
        handler.admin_table = table

        payload = {'anonymous_monthly': 10, 'authenticated_monthly': 1000}
        event = build_api_event(method='PUT', path='/admin/settings/rate_limits', body=payload)
        response = handler.lambda_handler(event, MagicMock(aws_request_id='test'))

        assert response['statusCode'] == 200
