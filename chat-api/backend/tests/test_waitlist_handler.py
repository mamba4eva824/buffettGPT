"""
Unit tests for waitlist_handler.py

Covers all code paths for the viral waitlist/referral system:
- POST /waitlist/signup (validation, rate limiting, referral credit, duplicate handling)
- GET /waitlist/status (auth, tier calculation, queue position)
- Helper functions (IP extraction, code generation, tier logic)

Uses moto to mock DynamoDB — no real AWS calls.
"""

import json
import os
import sys
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

import boto3
import pytest
from moto import mock_aws

# ================================================
# Module-scoped fixtures: moto must be active before handler import
# ================================================

TABLE_NAME = 'waitlist-test-buffett'


@pytest.fixture(scope='module')
def dynamodb_mock():
    """Start moto mock and create the waitlist table at module scope."""
    with mock_aws():
        os.environ['ENVIRONMENT'] = 'test'
        os.environ['WAITLIST_TABLE'] = TABLE_NAME
        os.environ['FRONTEND_URL'] = 'https://buffettgpt.test'

        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{'AttributeName': 'email', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'email', 'AttributeType': 'S'},
                {'AttributeName': 'referral_code', 'AttributeType': 'S'},
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'referral-code-index',
                'KeySchema': [{'AttributeName': 'referral_code', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'},
            }],
            BillingMode='PAY_PER_REQUEST',
        )

        yield table


@pytest.fixture(scope='module')
def handler(dynamodb_mock):
    """
    Import the handler module AFTER moto is active.

    Reassigns the module-level waitlist_table to the mocked table
    to avoid stale boto3 references. Mocks email_service to avoid
    Secrets Manager calls during tests.
    """
    # Clear cached module to force re-import under moto
    mod_key = 'handlers.waitlist_handler'
    if mod_key in sys.modules:
        del sys.modules[mod_key]

    # Pre-mock email_service so handler import doesn't hit Secrets Manager
    # We need real crypto functions but mock the email-sending functions
    email_mock = MagicMock()
    email_mock.send_welcome_email = MagicMock(return_value=None)
    email_mock.send_referral_success_email = MagicMock(return_value=None)
    email_mock.send_tier_unlocked_email = MagicMock(return_value=None)

    # Provide real implementations for non-email functions
    import hashlib
    import hmac as hmac_mod
    import html as html_mod
    from urllib.parse import quote as url_quote

    unsub_secret = os.environ.get('UNSUBSCRIBE_SECRET', os.environ.get('JWT_SECRET', 'dev-fallback-secret'))

    def _generate_unsubscribe_token(email_addr):
        return hmac_mod.new(unsub_secret.encode(), email_addr.lower().encode(), hashlib.sha256).hexdigest()

    def _verify_unsubscribe_token(email_addr, token):
        expected = _generate_unsubscribe_token(email_addr)
        return hmac_mod.compare_digest(expected, token)

    def _escape(value):
        return html_mod.escape(str(value))

    email_mock.generate_unsubscribe_token = _generate_unsubscribe_token
    email_mock.verify_unsubscribe_token = _verify_unsubscribe_token
    email_mock._escape = _escape

    sys.modules['utils.email_service'] = email_mock

    from handlers import waitlist_handler

    # CRITICAL: reassign module-level table to the mocked one
    waitlist_handler.waitlist_table = dynamodb_mock
    waitlist_handler.FRONTEND_URL = 'https://buffettgpt.test'

    return waitlist_handler


# ================================================
# Function-scoped fixtures
# ================================================

@pytest.fixture(autouse=True)
def clean_table(dynamodb_mock):
    """Clear all items from the table before each test."""
    scan = dynamodb_mock.scan()
    with dynamodb_mock.batch_writer() as batch:
        for item in scan.get('Items', []):
            batch.delete_item(Key={'email': item['email']})
    yield


@pytest.fixture
def signup_event():
    """Valid HTTP API v2 POST /waitlist/signup event."""
    return {
        'requestContext': {
            'http': {'method': 'POST', 'sourceIp': '192.168.1.1'}
        },
        'rawPath': '/dev/waitlist/signup',
        'body': json.dumps({'email': 'user@example.com'}),
    }


@pytest.fixture
def status_event():
    """Valid HTTP API v2 GET /waitlist/status event."""
    return {
        'requestContext': {
            'http': {'method': 'GET', 'sourceIp': '192.168.1.1'}
        },
        'rawPath': '/dev/waitlist/status',
        'queryStringParameters': {
            'email': 'user@example.com',
            'code': 'BUFF-AAAA',
        },
    }


@pytest.fixture
def seeded_user(handler, dynamodb_mock):
    """Insert one user and return their data."""
    dynamodb_mock.put_item(Item={
        'email': 'referrer@example.com',
        'referral_code': 'BUFF-AAAA',
        'referral_count': 0,
        'status': 'waitlisted',
        'created_at': '2026-02-12T10:00:00+00:00',
        'ip_address': '10.0.0.1',
    })
    return {'email': 'referrer@example.com', 'referral_code': 'BUFF-AAAA'}


def _parse(response):
    """Helper: parse response body JSON."""
    return json.loads(response['body'])


# ================================================
# Test Classes
# ================================================


class TestLambdaRouting:
    """Test main lambda_handler routing logic."""

    def test_options_returns_200_with_cors(self, handler):
        event = {
            'requestContext': {'http': {'method': 'OPTIONS'}},
            'rawPath': '/dev/waitlist/signup',
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert resp['headers']['Access-Control-Allow-Origin'] == '*'
        assert 'POST' in resp['headers']['Access-Control-Allow-Methods']

    def test_post_signup_routes_correctly(self, handler, signup_event):
        resp = handler.lambda_handler(signup_event, None)
        assert resp['statusCode'] == 201

    def test_get_status_routes_correctly(self, handler, seeded_user):
        event = {
            'requestContext': {'http': {'method': 'GET', 'sourceIp': '192.168.1.1'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'code': seeded_user['referral_code'],
            },
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 200

    def test_unknown_route_returns_404(self, handler):
        event = {
            'requestContext': {'http': {'method': 'DELETE'}},
            'rawPath': '/dev/waitlist/invalid',
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 404
        assert _parse(resp)['error'] == 'Not found'


class TestSignupHappyPath:
    """Test successful signup scenarios."""

    def test_signup_valid_email_returns_201(self, handler, signup_event):
        resp = handler.lambda_handler(signup_event, None)
        body = _parse(resp)

        assert resp['statusCode'] == 201
        assert body['email'] == 'user@example.com'
        assert body['referral_code'].startswith('BUFF-')
        assert body['position'] == 1
        assert body['referral_count'] == 0
        assert body['status'] == 'waitlisted'
        assert body['message'] == "You're on the waitlist!"
        assert 'tiers' in body
        assert len(body['tiers']) == 2

    def test_signup_with_valid_referral_credits_referrer(self, handler, dynamodb_mock, seeded_user, signup_event):
        signup_event['body'] = json.dumps({
            'email': 'newuser@example.com',
            'referral_code': seeded_user['referral_code'],
        })
        resp = handler.lambda_handler(signup_event, None)
        assert resp['statusCode'] == 201

        # Verify referrer was credited
        referrer = dynamodb_mock.get_item(Key={'email': seeded_user['email']})['Item']
        assert int(referrer['referral_count']) == 1

    def test_queue_position_increments_with_signups(self, handler, dynamodb_mock):
        emails = ['first@example.com', 'second@example.com', 'third@example.com']
        positions = []
        for i, email in enumerate(emails):
            event = {
                'requestContext': {'http': {'method': 'POST', 'sourceIp': f'10.0.0.{i}'}},
                'rawPath': '/dev/waitlist/signup',
                'body': json.dumps({'email': email}),
            }
            resp = handler.lambda_handler(event, None)
            positions.append(_parse(resp)['position'])

        # Each user should get an incrementing position
        assert positions[0] == 1
        assert positions[1] == 2
        assert positions[2] == 3

    def test_referral_link_uses_frontend_url(self, handler, signup_event):
        resp = handler.lambda_handler(signup_event, None)
        body = _parse(resp)
        assert body['referral_link'].startswith('https://buffettgpt.test?ref=BUFF-')


class TestSignupValidation:
    """Test input validation errors."""

    def test_invalid_json_returns_400(self, handler):
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': 'not-json{{{',
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        assert 'Invalid JSON' in _parse(resp)['error']

    def test_empty_email_returns_400(self, handler):
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': ''}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        assert 'required' in _parse(resp)['error'].lower()

    def test_invalid_email_format_returns_400(self, handler):
        for bad_email in ['not-an-email', 'missing@', '@no-local.com', 'spaces in@email.com']:
            event = {
                'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
                'rawPath': '/dev/waitlist/signup',
                'body': json.dumps({'email': bad_email}),
            }
            resp = handler.lambda_handler(event, None)
            assert resp['statusCode'] == 400, f"Expected 400 for '{bad_email}'"

    def test_email_too_long_returns_400(self, handler):
        long_email = 'a' * 245 + '@example.com'  # 257 chars
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': long_email}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        assert 'too long' in _parse(resp)['error'].lower()

    def test_disposable_email_returns_400(self, handler):
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': 'test@mailinator.com'}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400
        assert 'non-disposable' in _parse(resp)['error'].lower()


class TestRateLimiting:
    """Test rate limiting logic."""

    def test_rate_limit_exceeded_returns_429(self, handler, dynamodb_mock):
        # Pre-seed rate limit entry at max
        dynamodb_mock.put_item(Item={
            'email': 'rate:192.168.1.1',
            'referral_count': 5,  # at RATE_LIMIT_MAX
            'status': 'rate_limit',
            'ttl': int(time.time()) + 3600,
        })
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '192.168.1.1'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': 'blocked@example.com'}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 429
        assert 'Too many' in _parse(resp)['error']

    def test_multiple_signups_under_limit_succeed(self, handler):
        for i in range(5):
            event = {
                'requestContext': {'http': {'method': 'POST', 'sourceIp': '10.10.10.10'}},
                'rawPath': '/dev/waitlist/signup',
                'body': json.dumps({'email': f'user{i}@example.com'}),
            }
            resp = handler.lambda_handler(event, None)
            assert resp['statusCode'] == 201, f"Signup {i+1} should succeed"

    def test_unknown_ip_bypasses_rate_limit(self, handler):
        # Event with no sourceIp at all → 'unknown'
        event = {
            'requestContext': {'http': {'method': 'POST'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': 'noip@example.com'}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 201

    def test_rate_limit_record_has_ttl(self, handler, dynamodb_mock, signup_event):
        handler.lambda_handler(signup_event, None)

        # Check the rate limit entry was created with a TTL
        rate_item = dynamodb_mock.get_item(Key={'email': 'rate:192.168.1.1'}).get('Item')
        assert rate_item is not None
        assert 'ttl' in rate_item
        assert int(rate_item['ttl']) > int(time.time())


class TestDuplicateHandling:
    """Test duplicate email handling."""

    def test_duplicate_email_returns_409_with_existing_data(self, handler, seeded_user, signup_event):
        signup_event['body'] = json.dumps({'email': seeded_user['email']})
        resp = handler.lambda_handler(signup_event, None)
        body = _parse(resp)

        assert resp['statusCode'] == 409
        assert body['error'] == 'Email already registered'
        assert body['referral_code'] == seeded_user['referral_code']
        assert 'referral_count' in body
        assert 'status' in body


class TestReferralSystem:
    """Test referral code generation, validation, and credit logic."""

    def test_referral_code_format_is_buff_plus_6_chars(self, handler, signup_event):
        resp = handler.lambda_handler(signup_event, None)
        code = _parse(resp)['referral_code']
        assert code.startswith('BUFF-')
        assert len(code) == 11  # BUFF- + 6 chars

    def test_invalid_referral_code_ignored_signup_succeeds(self, handler, signup_event):
        signup_event['body'] = json.dumps({
            'email': 'newuser@example.com',
            'referral_code': 'BUFF-ZZZZ',  # doesn't exist
        })
        resp = handler.lambda_handler(signup_event, None)
        assert resp['statusCode'] == 201

    def test_self_referral_ignored_signup_succeeds(self, handler, dynamodb_mock, seeded_user, signup_event):
        # User tries to refer themselves
        signup_event['body'] = json.dumps({
            'email': seeded_user['email'],
            'referral_code': seeded_user['referral_code'],
        })
        resp = handler.lambda_handler(signup_event, None)
        # Duplicate email → 409, but the referral should not have credited
        assert resp['statusCode'] == 409

        referrer = dynamodb_mock.get_item(Key={'email': seeded_user['email']})['Item']
        assert int(referrer['referral_count']) == 0

    def test_referral_code_collision_retries(self, handler):
        """Mock _lookup_referrer to simulate collisions then succeed."""
        call_count = [0]
        original_lookup = handler._lookup_referrer

        def mock_lookup(code):
            call_count[0] += 1
            if call_count[0] <= 3:
                return {'email': 'someone@example.com', 'referral_code': code}
            return None

        with patch.object(handler, '_lookup_referrer', side_effect=mock_lookup):
            code = handler._generate_referral_code()

        assert code.startswith('BUFF-')
        assert len(code) == 11  # 6-char code succeeded after retries
        assert call_count[0] == 4  # 3 collisions + 1 success

    def test_referral_code_fallback_to_8_chars(self, handler):
        """When all 10 retries collide, fall back to 8-char code."""
        def always_collide(code):
            return {'email': 'x@y.com', 'referral_code': code}

        with patch.object(handler, '_lookup_referrer', side_effect=always_collide):
            code = handler._generate_referral_code()

        assert code.startswith('BUFF-')
        assert len(code) == 13  # BUFF- + 8 chars


class TestStatusEndpoint:
    """Test GET /waitlist/status endpoint."""

    def test_status_returns_dashboard_data(self, handler, seeded_user):
        event = {
            'requestContext': {'http': {'method': 'GET', 'sourceIp': '192.168.1.1'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'code': seeded_user['referral_code'],
            },
        }
        resp = handler.lambda_handler(event, None)
        body = _parse(resp)

        assert resp['statusCode'] == 200
        assert body['email'] == seeded_user['email']
        assert body['referral_code'] == seeded_user['referral_code']
        assert 'position' in body
        assert 'referral_count' in body
        assert 'current_tier' in body
        assert 'next_tier' in body
        assert body['referral_link'].startswith('https://buffettgpt.test')
        assert 'tiers' in body

    def test_status_missing_email_returns_400(self, handler):
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {'code': 'BUFF-AAAA'},
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_status_missing_code_returns_400(self, handler):
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {'email': 'user@example.com'},
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_status_email_not_found_returns_403(self, handler):
        """Unknown email returns 403 (same as wrong code) to prevent email enumeration."""
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {'email': 'nobody@example.com', 'code': 'BUFF-XXXX'},
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 403
        body = _parse(resp)
        assert body['error'] == 'Invalid email or code'

    def test_status_code_mismatch_returns_403(self, handler, seeded_user):
        """Wrong code returns same 403 as unknown email to prevent email enumeration."""
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/status',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'code': 'BUFF-WRONG',
            },
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 403
        body = _parse(resp)
        assert body['error'] == 'Invalid email or code'


class TestTierCalculation:
    """Test _get_tier_info logic."""

    def test_zero_referrals_shows_first_tier_as_next(self, handler):
        info = handler._get_tier_info(0)
        assert info['current_tier'] is None
        assert info['next_tier']['name'] == '1 Month Free Plus'
        assert info['next_tier']['referrals_needed'] == 3

    def test_count_at_threshold_shows_tier_as_current(self, handler):
        info = handler._get_tier_info(3)
        assert info['current_tier']['name'] == '1 Month Free Plus'
        assert info['next_tier']['name'] == '3 Months Free Plus'
        assert info['next_tier']['referrals_needed'] == 2

    def test_count_at_max_tier_shows_no_next(self, handler):
        info = handler._get_tier_info(5)
        assert info['current_tier']['name'] == '3 Months Free Plus'
        assert info['next_tier'] is None

    def test_count_between_tiers_shows_referrals_needed(self, handler):
        info = handler._get_tier_info(4)
        assert info['current_tier']['name'] == '1 Month Free Plus'
        assert info['next_tier']['name'] == '3 Months Free Plus'
        assert info['next_tier']['referrals_needed'] == 1


class TestEdgeCases:
    """Test edge cases and utility functions."""

    def test_email_normalized_to_lowercase(self, handler, dynamodb_mock, signup_event):
        signup_event['body'] = json.dumps({'email': 'Test@Example.COM'})
        resp = handler.lambda_handler(signup_event, None)
        body = _parse(resp)
        assert body['email'] == 'test@example.com'

        # Verify stored as lowercase
        item = dynamodb_mock.get_item(Key={'email': 'test@example.com'}).get('Item')
        assert item is not None

    def test_decimal_encoder_handles_dynamodb_decimals(self, handler):
        data = {'count': Decimal('5'), 'ratio': Decimal('3.14')}
        result = json.loads(json.dumps(data, cls=handler.DecimalEncoder))
        assert result['count'] == 5
        assert isinstance(result['count'], int)
        assert result['ratio'] == 3.14
        assert isinstance(result['ratio'], float)

    def test_ip_extracted_from_http_api_v2_format(self, handler):
        event = {'requestContext': {'http': {'sourceIp': '1.2.3.4'}}}
        assert handler._get_client_ip(event) == '1.2.3.4'

    def test_ip_extracted_from_rest_api_format(self, handler):
        event = {'requestContext': {'identity': {'sourceIp': '5.6.7.8'}}}
        assert handler._get_client_ip(event) == '5.6.7.8'

    def test_dynamodb_get_item_error_returns_none(self, handler, dynamodb_mock):
        """_get_waitlist_entry returns None on ClientError."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.get_item

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'GetItem',
            )

        dynamodb_mock.get_item = raise_error
        result = handler._get_waitlist_entry('any@email.com')
        assert result is None
        dynamodb_mock.get_item = original

    def test_dynamodb_query_error_in_lookup_referrer_returns_none(self, handler, dynamodb_mock):
        """_lookup_referrer returns None on ClientError."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.query

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'Query',
            )

        dynamodb_mock.query = raise_error
        result = handler._lookup_referrer('BUFF-XXXX')
        assert result is None
        dynamodb_mock.query = original

    def test_dynamodb_scan_error_returns_position_zero(self, handler, dynamodb_mock):
        """_get_queue_position returns 0 on ClientError."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.scan

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'test'}},
                'Scan',
            )

        dynamodb_mock.scan = raise_error
        result = handler._get_queue_position('2026-01-01T00:00:00+00:00')
        assert result == 0
        dynamodb_mock.scan = original

    def test_signup_dynamodb_error_returns_500(self, handler, dynamodb_mock):
        """Non-conditional DynamoDB error on put_item returns 500."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.put_item

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'boom'}},
                'PutItem',
            )

        dynamodb_mock.put_item = raise_error
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': 'fail@example.com'}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 500
        dynamodb_mock.put_item = original

    def test_credit_referrer_error_does_not_crash(self, handler, dynamodb_mock):
        """_credit_referrer swallows non-conditional errors."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.update_item

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'boom'}},
                'UpdateItem',
            )

        dynamodb_mock.update_item = raise_error
        # Should not raise
        handler._credit_referrer('anyone@example.com')
        dynamodb_mock.update_item = original

    def test_record_rate_limit_error_does_not_crash(self, handler, dynamodb_mock):
        """_record_rate_limit swallows errors."""
        from botocore.exceptions import ClientError

        original = dynamodb_mock.update_item

        def raise_error(**kwargs):
            raise ClientError(
                {'Error': {'Code': 'InternalServerError', 'Message': 'boom'}},
                'UpdateItem',
            )

        dynamodb_mock.update_item = raise_error
        # Should not raise
        handler._record_rate_limit('1.2.3.4')
        dynamodb_mock.update_item = original


class TestEmailIntegration:
    """Test email sending is triggered correctly during signup and referral flows."""

    def test_welcome_email_sent_on_signup(self, handler, signup_event):
        with patch.object(handler, 'send_welcome_email') as mock_welcome:
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201
            body = _parse(resp)

            mock_welcome.assert_called_once_with(
                'user@example.com',
                body['referral_code'],
                body['referral_link'],
            )

    def test_welcome_email_not_sent_on_duplicate(self, handler, seeded_user, signup_event):
        signup_event['body'] = json.dumps({'email': seeded_user['email']})
        with patch.object(handler, 'send_welcome_email') as mock_welcome:
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 409
            mock_welcome.assert_not_called()

    def test_welcome_email_not_sent_on_validation_error(self, handler):
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': ''}),
        }
        with patch.object(handler, 'send_welcome_email') as mock_welcome:
            resp = handler.lambda_handler(event, None)
            assert resp['statusCode'] == 400
            mock_welcome.assert_not_called()

    def test_referral_email_sent_to_referrer(self, handler, seeded_user, signup_event):
        signup_event['body'] = json.dumps({
            'email': 'referred@example.com',
            'referral_code': seeded_user['referral_code'],
        })
        with patch.object(handler, 'send_referral_success_email') as mock_ref, \
             patch.object(handler, 'send_tier_unlocked_email') as mock_tier:
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201

            # First referral (count=1) — no tier at 1, so referral success email only
            mock_ref.assert_called_once()
            assert mock_ref.call_args[1]['to'] == seeded_user['email']
            assert mock_ref.call_args[1]['referral_count'] == 1
            mock_tier.assert_not_called()

    def test_referral_success_email_when_no_tier_unlocked(self, handler, dynamodb_mock, signup_event):
        """When referral_count goes from 1 to 2, no tier unlocked — sends referral success email."""
        # Seed referrer with 1 referral (no tier unlocked yet, first tier at 3)
        dynamodb_mock.put_item(Item={
            'email': 'referrer2@example.com',
            'referral_code': 'BUFF-BBBB',
            'referral_count': 1,
            'status': 'waitlisted',
            'created_at': '2026-02-12T10:00:00+00:00',
            'ip_address': '10.0.0.2',
        })
        signup_event['body'] = json.dumps({
            'email': 'friend2@example.com',
            'referral_code': 'BUFF-BBBB',
        })
        with patch.object(handler, 'send_referral_success_email') as mock_ref, \
             patch.object(handler, 'send_tier_unlocked_email') as mock_tier:
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201

            # Count goes to 2 — no tier at 2, so referral success email
            mock_ref.assert_called_once()
            assert mock_ref.call_args[1]['to'] == 'referrer2@example.com'
            assert mock_ref.call_args[1]['referral_count'] == 2
            mock_tier.assert_not_called()

    def test_email_failure_does_not_block_signup(self, handler, signup_event):
        """Even if email sending raises, signup still returns 201."""
        with patch.object(handler, 'send_welcome_email', side_effect=Exception("SMTP down")):
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201

    def test_referral_email_failure_does_not_block_credit(self, handler, seeded_user, signup_event, dynamodb_mock):
        """Even if referral email fails, referral credit is still applied."""
        signup_event['body'] = json.dumps({
            'email': 'friend3@example.com',
            'referral_code': seeded_user['referral_code'],
        })
        with patch.object(handler, 'send_referral_success_email', side_effect=Exception("Email down")):
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201

        # Verify referrer was still credited despite email failure
        referrer = dynamodb_mock.get_item(Key={'email': seeded_user['email']})['Item']
        assert int(referrer['referral_count']) == 1


class TestHoneypot:
    """Test honeypot bot protection."""

    def test_honeypot_filled_returns_fake_201(self, handler):
        """Bot filling the honeypot field gets a fake success response."""
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({
                'email': 'bot@example.com',
                'website': 'http://spam.com',
            }),
        }
        resp = handler.lambda_handler(event, None)
        body = _parse(resp)

        assert resp['statusCode'] == 201
        assert body['referral_code'] == 'BUFF-000000'
        assert body['message'] == "You're on the waitlist!"

    def test_honeypot_filled_does_not_write_to_db(self, handler, dynamodb_mock):
        """Bot signup must NOT create a real DynamoDB entry."""
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '1.2.3.4'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({
                'email': 'sneakybot@example.com',
                'website': 'x',
            }),
        }
        handler.lambda_handler(event, None)

        # Verify no item was written
        item = dynamodb_mock.get_item(Key={'email': 'sneakybot@example.com'}).get('Item')
        assert item is None

    def test_honeypot_empty_proceeds_normally(self, handler):
        """Empty honeypot field (normal user) proceeds with real signup."""
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '10.0.0.99'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({
                'email': 'realuser@example.com',
                'website': '',
            }),
        }
        resp = handler.lambda_handler(event, None)
        body = _parse(resp)

        assert resp['statusCode'] == 201
        assert body['referral_code'] != 'BUFF-000000'

    def test_honeypot_absent_proceeds_normally(self, handler):
        """No honeypot field at all (normal user) proceeds with real signup."""
        event = {
            'requestContext': {'http': {'method': 'POST', 'sourceIp': '10.0.0.98'}},
            'rawPath': '/dev/waitlist/signup',
            'body': json.dumps({'email': 'normaluser@example.com'}),
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 201
        assert _parse(resp)['referral_code'] != 'BUFF-000000'


class TestUnsubscribe:
    """Test GET /waitlist/unsubscribe endpoint."""

    def test_unsubscribe_valid_token_sets_opt_out(self, handler, dynamodb_mock, seeded_user):
        """Valid unsubscribe link sets email_opted_out on the record."""
        from utils.email_service import generate_unsubscribe_token
        token = generate_unsubscribe_token(seeded_user['email'])

        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/unsubscribe',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'token': token,
            },
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 200
        assert 'text/html' in resp['headers']['Content-Type']
        assert 'unsubscribed' in resp['body'].lower()

        # Verify DynamoDB flag was set
        item = dynamodb_mock.get_item(Key={'email': seeded_user['email']})['Item']
        assert item.get('email_opted_out') is True

    def test_unsubscribe_invalid_token_returns_403(self, handler, seeded_user):
        """Invalid HMAC token is rejected."""
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/unsubscribe',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'token': 'definitely-not-valid',
            },
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 403

    def test_unsubscribe_missing_params_returns_400(self, handler):
        """Missing email or token returns 400."""
        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/unsubscribe',
            'queryStringParameters': {'email': 'x@y.com'},
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 400

    def test_unsubscribe_route_in_lambda_handler(self, handler, seeded_user):
        """Unsubscribe route is correctly wired in the router."""
        from utils.email_service import generate_unsubscribe_token
        token = generate_unsubscribe_token(seeded_user['email'])

        event = {
            'requestContext': {'http': {'method': 'GET'}},
            'rawPath': '/dev/waitlist/unsubscribe',
            'queryStringParameters': {
                'email': seeded_user['email'],
                'token': token,
            },
        }
        resp = handler.lambda_handler(event, None)
        assert resp['statusCode'] == 200


class TestEmailOptOut:
    """Test that opted-out users don't receive emails."""

    def test_opted_out_referrer_gets_no_email(self, handler, dynamodb_mock, signup_event):
        """When referrer has email_opted_out=True, no referral email is sent."""
        dynamodb_mock.put_item(Item={
            'email': 'optout-referrer@example.com',
            'referral_code': 'BUFF-OPTOUT',
            'referral_count': 0,
            'status': 'waitlisted',
            'created_at': '2026-02-12T10:00:00+00:00',
            'ip_address': '10.0.0.1',
            'email_opted_out': True,
        })

        signup_event['body'] = json.dumps({
            'email': 'newperson@example.com',
            'referral_code': 'BUFF-OPTOUT',
        })

        with patch.object(handler, 'send_tier_unlocked_email') as mock_tier, \
             patch.object(handler, 'send_referral_success_email') as mock_ref:
            resp = handler.lambda_handler(signup_event, None)
            assert resp['statusCode'] == 201

            # Neither email type should be sent
            mock_tier.assert_not_called()
            mock_ref.assert_not_called()

        # But referral credit should still be applied
        referrer = dynamodb_mock.get_item(Key={'email': 'optout-referrer@example.com'})['Item']
        assert int(referrer['referral_count']) == 1

    def test_is_opted_out_returns_false_for_normal_user(self, handler):
        assert handler._is_opted_out({'email': 'x@y.com'}) is False
        assert handler._is_opted_out(None) is False

    def test_is_opted_out_returns_true_when_flagged(self, handler):
        assert handler._is_opted_out({'email': 'x@y.com', 'email_opted_out': True}) is True


class TestHtmlEscaping:
    """Test that email templates escape HTML special characters."""

    def test_escape_function_escapes_html(self):
        """_escape properly escapes HTML special characters."""
        from utils.email_service import _escape
        assert _escape('<script>alert("xss")</script>') == '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;'
        assert _escape('normal text') == 'normal text'
        assert _escape(42) == '42'
        assert _escape("Tom & Jerry") == 'Tom &amp; Jerry'

    def test_unsubscribe_token_round_trip(self):
        """generate_unsubscribe_token and verify_unsubscribe_token work together."""
        from utils.email_service import generate_unsubscribe_token, verify_unsubscribe_token
        email = 'test@example.com'
        token = generate_unsubscribe_token(email)

        assert verify_unsubscribe_token(email, token) is True
        assert verify_unsubscribe_token(email, 'wrong-token') is False
        assert verify_unsubscribe_token('other@example.com', token) is False

    def test_unsubscribe_token_case_insensitive_email(self):
        """Token verification is case-insensitive for email."""
        from utils.email_service import generate_unsubscribe_token, verify_unsubscribe_token
        token = generate_unsubscribe_token('User@Example.COM')
        assert verify_unsubscribe_token('user@example.com', token) is True
