"""
Unit tests for JWT Authentication Middleware (SEC-001 Fix).

Tests the JWT authentication middleware that protects endpoints from
unauthenticated access via Lambda Function URLs.

Tests:
- Unauthenticated requests return 401 Unauthorized
- Valid JWT tokens grant access
- Invalid/expired JWT tokens return 401
- /health endpoint remains publicly accessible
- Protected endpoints (/followup, /report/*, /reports) require auth

Run:
    cd chat-api/backend/lambda/investment_research
    pytest tests/test_jwt_auth.py -v

Or from backend root:
    pytest lambda/investment_research/tests/test_jwt_auth.py -v
"""

import json
import os
import sys
import pytest
import jwt
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables before importing app
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['JWT_SECRET'] = 'test-secret-key-for-jwt-validation-min-32-chars'

from fastapi.testclient import TestClient


# =============================================================================
# TEST FIXTURES
# =============================================================================

# Test JWT secret (must be at least 32 chars)
TEST_JWT_SECRET = 'test-secret-key-for-jwt-validation-min-32-chars'


def create_valid_jwt(user_id: str = 'test-user-123', exp_hours: int = 24) -> str:
    """Create a valid JWT token for testing."""
    payload = {
        'user_id': user_id,
        'email': 'test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=exp_hours),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm='HS256')


def create_expired_jwt(user_id: str = 'test-user-123') -> str:
    """Create an expired JWT token for testing."""
    payload = {
        'user_id': user_id,
        'email': 'test@example.com',
        'exp': datetime.utcnow() - timedelta(hours=1),  # Expired 1 hour ago
        'iat': datetime.utcnow() - timedelta(hours=2)
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm='HS256')


def create_invalid_jwt() -> str:
    """Create a JWT signed with wrong secret."""
    payload = {
        'user_id': 'test-user-123',
        'email': 'test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, 'wrong-secret-key-that-is-long-enough', algorithm='HS256')


def create_jwt_without_user_id() -> str:
    """Create a JWT without user_id claim."""
    payload = {
        'email': 'test@example.com',
        'exp': datetime.utcnow() + timedelta(hours=24),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm='HS256')


@pytest.fixture
def client():
    """FastAPI test client with mocked JWT secret."""
    # Mock get_jwt_secret to return our test secret
    with patch('app.get_jwt_secret', return_value=TEST_JWT_SECRET):
        from app import app
        return TestClient(app)


@pytest.fixture
def valid_token():
    """Valid JWT token."""
    return create_valid_jwt()


@pytest.fixture
def expired_token():
    """Expired JWT token."""
    return create_expired_jwt()


@pytest.fixture
def invalid_token():
    """JWT signed with wrong secret."""
    return create_invalid_jwt()


# =============================================================================
# HEALTH ENDPOINT TESTS (PUBLIC - NO AUTH REQUIRED)
# =============================================================================

class TestHealthEndpointNoAuth:
    """Tests that /health endpoint is publicly accessible without auth."""

    def test_health_without_auth_returns_200(self, client):
        """GET /health without Authorization header should return 200."""
        response = client.get('/health')

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'

    def test_health_with_auth_still_works(self, client, valid_token):
        """GET /health with valid Authorization header should still work."""
        response = client.get(
            '/health',
            headers={'Authorization': f'Bearer {valid_token}'}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'


# =============================================================================
# FOLLOWUP ENDPOINT TESTS (PROTECTED - AUTH REQUIRED)
# =============================================================================

class TestFollowupEndpointAuth:
    """Tests for POST /followup endpoint authentication."""

    def test_followup_without_auth_returns_401(self, client):
        """POST /followup without Authorization header should return 401."""
        response = client.post(
            '/followup',
            json={
                'ticker': 'AAPL',
                'question': 'What is the revenue?'
            }
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert data['error'] == 'Unauthorized'
        assert 'Missing Authorization header' in data['detail']

    def test_followup_with_valid_auth_returns_200(self, client, valid_token):
        """POST /followup with valid JWT should return 200."""
        # Mock the followup service since we're testing auth, not business logic
        with patch('app.invoke_followup_agent') as mock_followup:
            # Make it return a simple async generator
            async def mock_generator(*args, **kwargs):
                yield {'event': 'connected', 'data': '{}'}
                yield {'event': 'complete', 'data': '{}'}

            mock_followup.return_value = mock_generator()

            response = client.post(
                '/followup',
                json={
                    'ticker': 'AAPL',
                    'question': 'What is the revenue?'
                },
                headers={'Authorization': f'Bearer {valid_token}'}
            )

            # Should get 200 (SSE stream)
            assert response.status_code == 200

    def test_followup_with_expired_token_returns_401(self, client, expired_token):
        """POST /followup with expired JWT should return 401."""
        response = client.post(
            '/followup',
            json={
                'ticker': 'AAPL',
                'question': 'What is the revenue?'
            },
            headers={'Authorization': f'Bearer {expired_token}'}
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert data['error'] == 'Unauthorized'
        assert 'expired' in data['detail'].lower()

    def test_followup_with_invalid_token_returns_401(self, client, invalid_token):
        """POST /followup with invalid JWT should return 401."""
        response = client.post(
            '/followup',
            json={
                'ticker': 'AAPL',
                'question': 'What is the revenue?'
            },
            headers={'Authorization': f'Bearer {invalid_token}'}
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert data['error'] == 'Unauthorized'

    def test_followup_with_malformed_auth_header_returns_401(self, client):
        """POST /followup with malformed Authorization header should return 401."""
        # Missing "Bearer " prefix
        response = client.post(
            '/followup',
            json={
                'ticker': 'AAPL',
                'question': 'What is the revenue?'
            },
            headers={'Authorization': 'some-random-token'}
        )

        assert response.status_code == 401
        data = response.json()
        assert data['success'] is False
        assert 'Invalid Authorization header format' in data['detail']

    def test_followup_with_empty_bearer_token_returns_401(self, client):
        """POST /followup with empty Bearer token should return 401."""
        response = client.post(
            '/followup',
            json={
                'ticker': 'AAPL',
                'question': 'What is the revenue?'
            },
            headers={'Authorization': 'Bearer '}
        )

        assert response.status_code == 401

    def test_followup_with_token_missing_user_id_returns_401(self, client):
        """POST /followup with JWT missing user_id claim should return 401."""
        token = create_jwt_without_user_id()

        with patch('app.get_jwt_secret', return_value=TEST_JWT_SECRET):
            from app import app
            test_client = TestClient(app)

            response = test_client.post(
                '/followup',
                json={
                    'ticker': 'AAPL',
                    'question': 'What is the revenue?'
                },
                headers={'Authorization': f'Bearer {token}'}
            )

            assert response.status_code == 401
            data = response.json()
            assert 'user_id' in data['detail'].lower()


# =============================================================================
# REPORT ENDPOINT TESTS (PROTECTED - AUTH REQUIRED)
# =============================================================================

class TestReportEndpointsAuth:
    """Tests for /report/* endpoints authentication."""

    def test_report_stream_without_auth_returns_401(self, client):
        """GET /report/AAPL/stream without auth should return 401."""
        response = client.get('/report/AAPL/stream')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_report_toc_without_auth_returns_401(self, client):
        """GET /report/AAPL/toc without auth should return 401."""
        response = client.get('/report/AAPL/toc')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_report_status_without_auth_returns_401(self, client):
        """GET /report/AAPL/status without auth should return 401."""
        response = client.get('/report/AAPL/status')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_report_section_without_auth_returns_401(self, client):
        """GET /report/AAPL/section/06_growth without auth should return 401."""
        response = client.get('/report/AAPL/section/06_growth')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_report_executive_without_auth_returns_401(self, client):
        """GET /report/AAPL/executive without auth should return 401."""
        response = client.get('/report/AAPL/executive')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_report_v1_without_auth_returns_401(self, client):
        """GET /report/AAPL (v1 endpoint) without auth should return 401."""
        response = client.get('/report/AAPL')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'


# =============================================================================
# REPORTS LIST ENDPOINT TESTS (PROTECTED)
# =============================================================================

class TestReportsListAuth:
    """Tests for /reports endpoint authentication."""

    def test_reports_list_without_auth_returns_401(self, client):
        """GET /reports without auth should return 401."""
        response = client.get('/reports')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'

    def test_reports_search_without_auth_returns_401(self, client):
        """GET /reports/search without auth should return 401."""
        response = client.get('/reports/search?q=apple')

        assert response.status_code == 401
        data = response.json()
        assert data['error'] == 'Unauthorized'


# =============================================================================
# AUTHENTICATED ACCESS TESTS
# =============================================================================

class TestAuthenticatedAccess:
    """Tests that authenticated requests can access protected endpoints."""

    def test_report_toc_with_valid_auth(self, client, valid_token):
        """GET /report/AAPL/toc with valid JWT should work."""
        mock_toc = {
            'ticker': 'AAPL',
            'toc': [{'section_id': '01_tldr', 'title': 'TL;DR'}],
            'ratings': {'overall_verdict': 'HOLD'},
            'total_word_count': 100,
            'generated_at': '2024-01-01T00:00:00Z'
        }

        with patch('app.get_report_toc', return_value=mock_toc):
            response = client.get(
                '/report/AAPL/toc',
                headers={'Authorization': f'Bearer {valid_token}'}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['ticker'] == 'AAPL'

    def test_reports_list_with_valid_auth(self, client, valid_token):
        """GET /reports with valid JWT should work."""
        mock_reports = {
            'success': True,
            'count': 2,
            'reports': [
                {'ticker': 'AAPL', 'company_name': 'Apple Inc.'},
                {'ticker': 'MSFT', 'company_name': 'Microsoft Corp.'}
            ]
        }

        with patch('app.get_available_reports', return_value=mock_reports):
            response = client.get(
                '/reports',
                headers={'Authorization': f'Bearer {valid_token}'}
            )

            assert response.status_code == 200


# =============================================================================
# AUTHORIZATION HEADER CASE SENSITIVITY TESTS
# =============================================================================

class TestAuthHeaderCaseSensitivity:
    """Tests for Authorization header case handling."""

    def test_lowercase_authorization_header(self, client, valid_token):
        """lowercase 'authorization' header should work."""
        response = client.get(
            '/report/AAPL/status',
            headers={'authorization': f'Bearer {valid_token}'}
        )

        # Should not return 401 (may return 404 if report doesn't exist)
        # The key is that auth passes
        assert response.status_code != 401 or 'Missing Authorization' not in response.json().get('detail', '')


# =============================================================================
# JWT SECRET CONFIGURATION TESTS
# =============================================================================

class TestJWTSecretConfig:
    """Tests for JWT secret configuration edge cases."""

    def test_missing_jwt_secret_raises_error(self):
        """Missing JWT_SECRET should raise appropriate error."""
        # Clear the environment variable
        original = os.environ.pop('JWT_SECRET', None)
        original_arn = os.environ.pop('JWT_SECRET_ARN', None)

        try:
            # Clear the lru_cache
            from app import get_jwt_secret
            get_jwt_secret.cache_clear()

            with pytest.raises(ValueError) as exc_info:
                get_jwt_secret()

            assert 'JWT_SECRET must be set' in str(exc_info.value)
        finally:
            # Restore
            if original:
                os.environ['JWT_SECRET'] = original
            if original_arn:
                os.environ['JWT_SECRET_ARN'] = original_arn


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
