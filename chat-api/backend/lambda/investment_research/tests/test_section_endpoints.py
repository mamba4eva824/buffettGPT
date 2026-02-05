"""
Unit tests for DynamoDB-backed section endpoints in Investment Research API.

Tests the following DynamoDB operations:
- GET /report/{ticker}/section/{section_id} - GetItem from investment_reports_v2 table
- GET /report/{ticker}/toc - GetItem for executive item (00_executive)
- GET /report/{ticker}/status - GetItem with TTL expiration check

Focuses on:
1. Correct key construction (ticker.upper(), section_id.lower())
2. TTL expiration checking
3. Response format validation
4. Error handling for missing data

Run:
    cd chat-api/backend/lambda/investment_research
    pytest tests/test_section_endpoints.py -v

Or from backend root:
    pytest lambda/investment_research/tests/test_section_endpoints.py -v
"""

import json
import os
import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['INVESTMENT_REPORTS_TABLE_V2'] = 'test-investment-reports-v2'


# =============================================================================
# TEST DATA - Mock DynamoDB responses
# =============================================================================

def get_mock_section_item(ticker: str = 'AAPL', section_id: str = '06_growth', expired: bool = False) -> Dict[str, Any]:
    """Generate a mock DynamoDB section item."""
    ttl = int((datetime.utcnow() - timedelta(days=1)).timestamp()) if expired else int((datetime.utcnow() + timedelta(days=75)).timestamp())
    return {
        'ticker': ticker,
        'section_id': section_id,
        'title': 'From 3% to 4%: The Growth Crawl',
        'content': "Apple's growth has slowed dramatically from 19% in 2021 to just 3-4% today.",
        'part': Decimal('2'),
        'icon': 'trending-up',
        'word_count': Decimal('200'),
        'display_order': Decimal('6'),
        'ttl': Decimal(str(ttl)),
        'generated_at': '2024-01-01T12:00:00Z'
    }


def get_mock_executive_item(ticker: str = 'AAPL', expired: bool = False) -> Dict[str, Any]:
    """Generate a mock DynamoDB executive item (00_executive)."""
    ttl = int((datetime.utcnow() - timedelta(days=1)).timestamp()) if expired else int((datetime.utcnow() + timedelta(days=75)).timestamp())
    return {
        'ticker': ticker,
        'section_id': '00_executive',
        'toc': [
            {'section_id': '01_executive_summary', 'title': 'Executive Summary', 'part': 1, 'icon': 'book-open', 'word_count': 500, 'display_order': 1},
            {'section_id': '06_growth', 'title': 'Growth Analysis', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
            {'section_id': '11_debt', 'title': 'Debt Analysis', 'part': 2, 'icon': 'credit-card', 'word_count': 180, 'display_order': 11},
        ],
        'ratings': {
            'growth': {'rating': 'Stable', 'confidence': 'High', 'key_factors': ['3% revenue growth']},
            'debt': {'rating': 'Strong', 'confidence': 'High', 'key_factors': ['Low debt ratio']},
            'cashflow': {'rating': 'Very Strong', 'confidence': 'High', 'key_factors': ['High FCF']},
            'overall_verdict': 'HOLD',
            'conviction': 'High'
        },
        'executive_summary': {
            'section_id': '01_executive_summary',
            'title': 'Executive Summary',
            'content': 'Apple is a strong value investment with stable growth.',
            'part': 1,
            'icon': 'book-open',
            'word_count': 500,
            'display_order': 1
        },
        'total_word_count': Decimal('880'),
        'ttl': Decimal(str(ttl)),
        'generated_at': '2024-01-01T12:00:00Z'
    }


# =============================================================================
# REPORT SERVICE UNIT TESTS
# =============================================================================

class TestGetReportSection:
    """Tests for get_report_section() DynamoDB operations."""

    def test_get_section_correct_key_construction(self):
        """Verify correct key construction: ticker.upper(), section_id.lower()."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_section_item()}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('aapl', '06_GROWTH')

            # Verify key construction
            mock_table.get_item.assert_called_once_with(
                Key={
                    'ticker': 'AAPL',  # Should be uppercased
                    'section_id': '06_growth'  # Should be lowercased
                }
            )
            assert result is not None

    def test_get_section_returns_correct_format(self):
        """Verify response format: section_id, title, content, part, icon, word_count."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_item = get_mock_section_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            assert result is not None
            assert result['section_id'] == '06_growth'
            assert result['title'] == 'From 3% to 4%: The Growth Crawl'
            assert 'content' in result
            assert result['part'] == 2  # Decimal converted to int
            assert result['icon'] == 'trending-up'
            assert result['word_count'] == 200  # Decimal converted to int
            assert result['display_order'] == 6

    def test_get_section_expired_ttl_returns_none(self):
        """Verify TTL expiration check returns None for expired items."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_item = get_mock_section_item(expired=True)
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            assert result is None

    def test_get_section_not_found_returns_none(self):
        """Verify returns None when section doesn't exist."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', 'nonexistent_section')

            assert result is None

    def test_get_section_decimal_conversion(self):
        """Verify Decimal values are converted to int/float."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_item = get_mock_section_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            # Verify Decimals are converted
            assert isinstance(result['part'], int)
            assert isinstance(result['word_count'], int)
            assert isinstance(result['display_order'], int)


class TestGetReportToc:
    """Tests for get_report_toc() DynamoDB operations."""

    def test_get_toc_fetches_executive_item(self):
        """Verify ToC is fetched from 00_executive item."""
        from services.report_service import get_report_toc

        mock_table = MagicMock()
        mock_item = get_mock_executive_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('AAPL')

            # Verify called with correct key
            mock_table.get_item.assert_called_once_with(
                Key={
                    'ticker': 'AAPL',
                    'section_id': '00_executive'
                }
            )
            assert result is not None

    def test_get_toc_extracts_toc_list(self):
        """Verify ToC list is extracted from executive item."""
        from services.report_service import get_report_toc

        mock_table = MagicMock()
        mock_item = get_mock_executive_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('AAPL')

            assert 'toc' in result
            assert len(result['toc']) == 3
            assert result['toc'][0]['section_id'] == '01_executive_summary'

    def test_get_toc_extracts_ratings(self):
        """Verify ratings are extracted from executive item."""
        from services.report_service import get_report_toc

        mock_table = MagicMock()
        mock_item = get_mock_executive_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('AAPL')

            assert 'ratings' in result
            assert result['ratings']['overall_verdict'] == 'HOLD'
            assert result['ratings']['conviction'] == 'High'

    def test_get_toc_not_found_returns_none(self):
        """Verify returns None when executive item doesn't exist."""
        from services.report_service import get_report_toc

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('UNKNOWN')

            assert result is None


class TestGetReportStatus:
    """Tests for get_report_status() DynamoDB operations."""

    def test_get_status_report_exists_not_expired(self):
        """Verify status for existing, non-expired report."""
        from services.report_service import get_report_status

        mock_table = MagicMock()
        ttl_future = int((datetime.utcnow() + timedelta(days=75)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_future)),
            'generated_at': '2024-01-01T12:00:00Z',
            'total_word_count': Decimal('15000')
        }
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('AAPL')

            assert result is not None
            assert result['exists'] is True
            assert result['expired'] is False
            assert result['ttl_remaining_days'] > 0
            assert result['ticker'] == 'AAPL'

    def test_get_status_report_expired(self):
        """Verify status for expired report."""
        from services.report_service import get_report_status

        mock_table = MagicMock()
        ttl_past = int((datetime.utcnow() - timedelta(days=1)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_past)),
            'generated_at': '2024-01-01T12:00:00Z',
            'total_word_count': Decimal('15000')
        }
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('AAPL')

            assert result is not None
            assert result['exists'] is True
            assert result['expired'] is True
            assert result['ttl_remaining_days'] == 0

    def test_get_status_report_not_found(self):
        """Verify status for non-existent report."""
        from services.report_service import get_report_status

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('UNKNOWN')

            assert result is None

    def test_get_status_uses_projection_expression(self):
        """Verify minimal data fetch with ProjectionExpression."""
        from services.report_service import get_report_status

        mock_table = MagicMock()
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal('1700000000'),
            'generated_at': '2024-01-01T12:00:00Z',
            'total_word_count': Decimal('15000')
        }
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            get_report_status('AAPL')

            # Verify ProjectionExpression is used
            call_kwargs = mock_table.get_item.call_args.kwargs
            assert 'ProjectionExpression' in call_kwargs
            assert 'ExpressionAttributeNames' in call_kwargs


class TestGetExecutive:
    """Tests for get_executive() DynamoDB operations."""

    def test_get_executive_returns_merged_summary(self):
        """Verify executive item includes merged executive summary."""
        from services.report_service import get_executive

        mock_table = MagicMock()
        mock_item = get_mock_executive_item()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is not None
            assert 'executive_summary' in result
            assert result['executive_summary']['section_id'] == '01_executive_summary'
            assert 'content' in result['executive_summary']

    def test_get_executive_parses_json_strings(self):
        """Verify JSON strings in executive item are parsed."""
        from services.report_service import get_executive

        mock_table = MagicMock()
        # Simulate JSON strings stored in DynamoDB
        mock_item = get_mock_executive_item()
        mock_item['toc'] = json.dumps(mock_item['toc'])
        mock_item['ratings'] = json.dumps(mock_item['ratings'])
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is not None
            assert isinstance(result['toc'], list)
            assert isinstance(result['ratings'], dict)

    def test_get_executive_expired_returns_none(self):
        """Verify expired executive item returns None."""
        from services.report_service import get_executive

        mock_table = MagicMock()
        mock_item = get_mock_executive_item(expired=True)
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is None


class TestCheckReportExistsV2:
    """Tests for check_report_exists_v2() DynamoDB operations."""

    def test_check_exists_returns_true_for_valid_report(self):
        """Verify returns True for existing, non-expired report."""
        from services.report_service import check_report_exists_v2

        mock_table = MagicMock()
        ttl_future = int((datetime.utcnow() + timedelta(days=75)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_future))
        }
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('AAPL')

            assert result is True

    def test_check_exists_returns_false_for_expired(self):
        """Verify returns False for expired report."""
        from services.report_service import check_report_exists_v2

        mock_table = MagicMock()
        ttl_past = int((datetime.utcnow() - timedelta(days=1)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_past))
        }
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('AAPL')

            assert result is False

    def test_check_exists_returns_false_for_missing(self):
        """Verify returns False for non-existent report."""
        from services.report_service import check_report_exists_v2

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}  # No Item

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('UNKNOWN')

            assert result is False


# =============================================================================
# API ENDPOINT TESTS WITH DYNAMODB MOCKING
# =============================================================================

# Helper to create a test client that bypasses JWT auth
def create_test_client_with_auth_bypass():
    """Create a FastAPI test client that bypasses JWT auth middleware."""
    from fastapi.testclient import TestClient
    from app import app

    # Mock the verify_jwt_token function to always succeed
    with patch('app.verify_jwt_token') as mock_verify:
        mock_verify.return_value = {'user_id': 'test-user-123'}
        # Use raise_server_exceptions=False to catch and return 500 errors
        return TestClient(app, raise_server_exceptions=False)


class TestSectionEndpointDynamoDB:
    """Tests for section endpoint with DynamoDB mocking."""

    def test_section_endpoint_calls_dynamodb(self):
        """Verify section endpoint triggers DynamoDB GetItem."""
        mock_section = {
            'ticker': 'AAPL',
            'section_id': '06_growth',
            'title': 'Growth Analysis',
            'content': 'Test content',
            'part': 2,
            'icon': 'trending-up',
            'word_count': 200,
            'display_order': 6
        }

        with patch('app.verify_jwt_token', return_value={'user_id': 'test-user-123'}):
            with patch('app.get_report_section', return_value=mock_section) as mock_get:
                with patch('app.get_executive', return_value=None):  # Not executive section
                    from fastapi.testclient import TestClient
                    from app import app
                    client = TestClient(app, raise_server_exceptions=False)

                    response = client.get(
                        '/report/AAPL/section/06_growth',
                        headers={'Authorization': 'Bearer test-token'}
                    )

                    mock_get.assert_called_once_with('AAPL', '06_growth')
                    assert response.status_code == 200

    def test_section_endpoint_handles_dynamodb_error(self):
        """Verify service layer handles DynamoDB errors gracefully."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception('DynamoDB connection error')

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            # Service should return None (not raise) when DynamoDB errors
            result = get_report_section('AAPL', '06_growth')
            assert result is None


class TestStatusEndpointDynamoDB:
    """Tests for status endpoint with DynamoDB mocking."""

    def test_status_endpoint_returns_expiration_info(self):
        """Verify status endpoint returns TTL expiration information."""
        mock_status = {
            'exists': True,
            'ticker': 'AAPL',
            'generated_at': '2024-01-01T12:00:00Z',
            'expired': False,
            'ttl_remaining_days': 75,
            'total_word_count': 15000
        }

        with patch('app.verify_jwt_token', return_value={'user_id': 'test-user-123'}):
            with patch('app.get_report_status', return_value=mock_status):
                from fastapi.testclient import TestClient
                from app import app
                client = TestClient(app, raise_server_exceptions=False)

                response = client.get(
                    '/report/AAPL/status',
                    headers={'Authorization': 'Bearer test-token'}
                )

                assert response.status_code == 200
                data = response.json()
                assert data['exists'] is True
                assert data['expired'] is False
                assert data['ttl_remaining_days'] == 75

    def test_status_endpoint_returns_404_for_missing(self):
        """Verify status endpoint returns 404 for non-existent report."""
        with patch('app.verify_jwt_token', return_value={'user_id': 'test-user-123'}):
            with patch('app.get_report_status', return_value=None):
                from fastapi.testclient import TestClient
                from app import app
                client = TestClient(app, raise_server_exceptions=False)

                # Use a valid ticker format (1-5 letters)
                response = client.get(
                    '/report/XYZ/status',
                    headers={'Authorization': 'Bearer test-token'}
                )

                assert response.status_code == 404
                data = response.json()
                assert data['exists'] is False


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Edge case tests for section endpoints."""

    def test_decimal_to_float_conversion_nested(self):
        """Verify nested Decimal conversion works correctly."""
        from services.report_service import decimal_to_float

        test_data = {
            'ratings': {
                'score': Decimal('8.5'),
                'factors': [Decimal('1'), Decimal('2'), Decimal('3')]
            },
            'count': Decimal('100')
        }

        result = decimal_to_float(test_data)

        assert result['ratings']['score'] == 8.5
        assert result['ratings']['factors'] == [1, 2, 3]
        assert result['count'] == 100

    def test_section_id_normalization(self):
        """Verify section_id is normalized to lowercase."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            get_report_section('AAPL', '06_GROWTH')

            call_kwargs = mock_table.get_item.call_args.kwargs
            assert call_kwargs['Key']['section_id'] == '06_growth'

    def test_ticker_normalization(self):
        """Verify ticker is normalized to uppercase."""
        from services.report_service import get_report_section

        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            get_report_section('aapl', '06_growth')

            call_kwargs = mock_table.get_item.call_args.kwargs
            assert call_kwargs['Key']['ticker'] == 'AAPL'


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
