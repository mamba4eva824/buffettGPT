"""
Unit tests for Investment Research section endpoints and DynamoDB operations.

Tests DynamoDB operations for the investment_reports_v2 table:
- GET /report/{ticker}/toc - Get ToC + ratings
- GET /report/{ticker}/status - Check report existence/expiration
- GET /report/{ticker}/section/{section_id} - Get specific section
- GET /report/{ticker}/executive - Get combined executive item
- Decimal to float conversion for JSON serialization
- TTL expiration checks

Run:
    cd chat-api/backend
    pytest tests/test_investment_research_sections.py -v
"""

import json
import os
import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# Add parent directory and lambda directory to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)
# Add the investment_research Lambda directory to path
lambda_investment_research_dir = os.path.join(backend_dir, 'lambda', 'investment_research')
sys.path.insert(0, lambda_investment_research_dir)

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
os.environ['INVESTMENT_REPORTS_TABLE'] = 'test-investment-reports'
os.environ['INVESTMENT_REPORTS_TABLE_V2'] = 'test-investment-reports-v2'
os.environ['JWT_SECRET'] = 'test-jwt-secret-at-least-32-characters-long'

# Import after setting env vars - import from the services module directly
from services.report_service import (
    decimal_to_float,
    validate_ticker,
    get_executive,
    get_report_toc,
    get_report_section,
    get_all_sections,
    check_report_exists_v2,
    get_report_status,
)


# =============================================================================
# TEST DATA - Mock section structures
# =============================================================================

def get_mock_toc() -> list:
    """Generate a mock table of contents matching v5.1 merged format.

    This mirrors what build_merged_toc() produces:
    1 Executive Summary (merged Part 1) + individual Part 2/3 sections.
    """
    return [
        {'section_id': '01_executive_summary', 'title': 'Executive Summary', 'part': 1, 'icon': 'lightning', 'word_count': 1900, 'display_order': 1},
        {'section_id': '06_growth', 'title': 'Growth: 3% to 4% — The Slow Climb', 'part': 2, 'icon': 'chart-up', 'word_count': 800, 'display_order': 2},
        {'section_id': '07_profit', 'title': 'Profitability: 77% Margins', 'part': 2, 'icon': 'piggy-bank', 'word_count': 750, 'display_order': 3},
        {'section_id': '08_valuation', 'title': 'Valuation: 30% Off', 'part': 2, 'icon': 'calculator', 'word_count': 700, 'display_order': 4},
        {'section_id': '09_earnings', 'title': 'Earnings Quality: Clean Books', 'part': 2, 'icon': 'eye', 'word_count': 650, 'display_order': 5},
        {'section_id': '10_cashflow', 'title': 'Cash Flow: The $94B Cash Machine', 'part': 2, 'icon': 'cash', 'word_count': 600, 'display_order': 6},
        {'section_id': '11_debt', 'title': 'Debt: The $50B War Chest', 'part': 2, 'icon': 'bank', 'word_count': 550, 'display_order': 7},
        {'section_id': '12_dilution', 'title': 'Dilution: Buying Back 3%', 'part': 2, 'icon': 'pie-chart', 'word_count': 400, 'display_order': 8},
        {'section_id': '13_bull', 'title': 'Bull Case', 'part': 2, 'icon': 'trending-up', 'word_count': 350, 'display_order': 9},
        {'section_id': '14_bear', 'title': 'Bear Case', 'part': 2, 'icon': 'trending-down', 'word_count': 350, 'display_order': 10},
        {'section_id': '15_realtalk', 'title': 'Real Talk', 'part': 3, 'icon': 'message-circle', 'word_count': 500, 'display_order': 11},
        {'section_id': '16_triggers', 'title': 'Decision Triggers', 'part': 3, 'icon': 'crosshair', 'word_count': 400, 'display_order': 12},
    ]


def get_mock_ratings() -> Dict[str, Any]:
    """Generate mock ratings structure."""
    return {
        'debt': {'rating': 'Strong', 'confidence': Decimal('0.85'), 'key_factors': ['Low debt-to-equity', 'Strong interest coverage']},
        'cashflow': {'rating': 'Excellent', 'confidence': Decimal('0.92'), 'key_factors': ['High FCF yield', 'Consistent growth']},
        'growth': {'rating': 'Stable', 'confidence': Decimal('0.78'), 'key_factors': ['Mature market', 'Services expansion']},
        'overall_verdict': 'BUY',
        'conviction': 'High'
    }


def get_mock_executive_item(ticker: str = 'AAPL', expired: bool = False) -> Dict[str, Any]:
    """Generate a mock executive item from v2 table."""
    # TTL: 90 days in future if not expired, 1 day in past if expired
    if expired:
        ttl = int((datetime.utcnow() - timedelta(days=1)).timestamp())
    else:
        ttl = int((datetime.utcnow() + timedelta(days=90)).timestamp())

    return {
        'ticker': ticker,
        'section_id': '00_executive',
        'toc': get_mock_toc(),
        'ratings': get_mock_ratings(),
        'executive_summary': {
            'section_id': '01_executive_summary',
            'title': 'Executive Summary',
            'content': f'# {ticker} Executive Summary\n\nThis is the merged executive summary content...',
            'part': 1,
            'icon': 'lightning',
            'word_count': 1900,
            'display_order': 1
        },
        'total_word_count': Decimal('15000'),
        'generated_at': '2025-01-15T10:30:00Z',
        'ttl': Decimal(str(ttl))
    }


def get_mock_section(section_id: str, ticker: str = 'AAPL', expired: bool = False) -> Dict[str, Any]:
    """Generate a mock section item matching v5.1 section IDs."""
    # TTL: 90 days in future if not expired, 1 day in past if expired
    if expired:
        ttl = int((datetime.utcnow() - timedelta(days=1)).timestamp())
    else:
        ttl = int((datetime.utcnow() + timedelta(days=90)).timestamp())

    section_data = {
        '06_growth': {'title': 'Growth: 3% to 4% — The Slow Climb', 'part': 2, 'icon': 'chart-up', 'display_order': 6},
        '11_debt': {'title': 'Debt: The $50B War Chest', 'part': 2, 'icon': 'bank', 'display_order': 11},
        '15_realtalk': {'title': 'Real Talk', 'part': 3, 'icon': 'message-circle', 'display_order': 15},
        '16_triggers': {'title': 'Decision Triggers', 'part': 3, 'icon': 'crosshair', 'display_order': 16},
    }

    data = section_data.get(section_id, {'title': 'Unknown Section', 'part': 2, 'icon': 'file-text', 'display_order': 99})

    return {
        'ticker': ticker,
        'section_id': section_id,
        'title': data['title'],
        'content': f'# {data["title"]}\n\nDetailed analysis content for {ticker}...',
        'part': data['part'],
        'icon': data['icon'],
        'word_count': Decimal('650'),
        'display_order': data['display_order'],
        'ttl': Decimal(str(ttl))
    }


# =============================================================================
# DECIMAL TO FLOAT CONVERSION TESTS
# =============================================================================

class TestDecimalToFloat:
    """Tests for decimal_to_float utility function."""

    def test_converts_decimal_to_int_for_whole_numbers(self):
        """Verify whole number Decimals become ints."""
        result = decimal_to_float(Decimal('100'))

        assert result == 100
        assert isinstance(result, int)

    def test_converts_decimal_to_float_for_fractions(self):
        """Verify fractional Decimals become floats."""
        result = decimal_to_float(Decimal('0.85'))

        assert result == 0.85
        assert isinstance(result, float)

    def test_converts_nested_decimals_in_dict(self):
        """Verify nested Decimals in dicts are converted."""
        data = {
            'ratings': {
                'confidence': Decimal('0.9'),
                'count': Decimal('42')
            }
        }

        result = decimal_to_float(data)

        assert isinstance(result['ratings']['confidence'], float)
        assert isinstance(result['ratings']['count'], int)

    def test_converts_decimals_in_lists(self):
        """Verify Decimals in lists are converted."""
        data = [Decimal('1.5'), Decimal('2'), Decimal('3.14')]

        result = decimal_to_float(data)

        assert result == [1.5, 2, 3.14]
        assert isinstance(result[1], int)
        assert isinstance(result[2], float)

    def test_preserves_non_decimal_types(self):
        """Verify non-Decimal types are preserved."""
        data = {
            'ticker': 'AAPL',
            'active': True,
            'items': ['a', 'b', 'c']
        }

        result = decimal_to_float(data)

        assert result == data


# =============================================================================
# VALIDATE TICKER TESTS
# =============================================================================

class TestValidateTicker:
    """Tests for ticker validation."""

    def test_accepts_valid_tickers(self):
        """Verify valid ticker formats are accepted."""
        assert validate_ticker('AAPL') is True
        assert validate_ticker('MSFT') is True
        assert validate_ticker('A') is True
        assert validate_ticker('GOOGL') is True

    def test_rejects_empty_ticker(self):
        """Verify empty tickers are rejected."""
        assert validate_ticker('') is False
        assert validate_ticker(None) is False

    def test_rejects_ticker_with_numbers(self):
        """Verify tickers with numbers are rejected."""
        assert validate_ticker('AAP1') is False
        assert validate_ticker('123') is False

    def test_rejects_too_long_ticker(self):
        """Verify tickers longer than 5 chars are rejected."""
        assert validate_ticker('TOOLONG') is False

    def test_handles_lowercase(self):
        """Verify lowercase tickers are handled (isalpha works for both)."""
        assert validate_ticker('aapl') is True


# =============================================================================
# GET EXECUTIVE TESTS
# =============================================================================

class TestGetExecutive:
    """Tests for get_executive() function."""

    def test_returns_executive_item_when_exists(self):
        """Verify executive item is returned when it exists."""
        mock_item = get_mock_executive_item('AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is not None
            assert result['ticker'] == 'AAPL'
            assert 'toc' in result
            assert 'ratings' in result
            assert 'executive_summary' in result
            assert len(result['toc']) == 12

    def test_returns_none_when_not_found(self):
        """Verify None is returned when executive item doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('NOTFOUND')

            assert result is None

    def test_returns_none_when_expired(self):
        """Verify None is returned when TTL has passed."""
        mock_item = get_mock_executive_item('AAPL', expired=True)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is None

    def test_converts_decimals_to_floats(self):
        """Verify Decimals in response are converted."""
        mock_item = get_mock_executive_item('AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            # total_word_count should be int now
            assert isinstance(result['total_word_count'], int)
            # rating confidence should be float
            assert isinstance(result['ratings']['debt']['confidence'], float)

    def test_normalizes_ticker_to_uppercase(self):
        """Verify ticker is normalized to uppercase."""
        mock_item = get_mock_executive_item('AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            get_executive('aapl')

            # Verify the key used uppercase
            call_args = mock_table.get_item.call_args
            assert call_args.kwargs['Key']['ticker'] == 'AAPL'


# =============================================================================
# GET REPORT TOC TESTS
# =============================================================================

class TestGetReportToc:
    """Tests for get_report_toc() function."""

    def test_returns_toc_from_executive_item(self):
        """Verify ToC is extracted from executive item."""
        mock_item = get_mock_executive_item('AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('AAPL')

            assert result is not None
            assert 'toc' in result
            assert 'ratings' in result
            assert len(result['toc']) == 12
            # Should NOT include executive_summary content
            assert 'executive_summary' not in result

    def test_returns_none_when_not_found(self):
        """Verify None is returned when report doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_toc('NOTFOUND')

            assert result is None


# =============================================================================
# GET REPORT SECTION TESTS
# =============================================================================

class TestGetReportSection:
    """Tests for get_report_section() function."""

    def test_returns_section_when_exists(self):
        """Verify section is returned when it exists."""
        mock_section = get_mock_section('06_growth', 'AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_section}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            assert result is not None
            assert result['section_id'] == '06_growth'
            assert result['title'] == 'Growth: 3% to 4% — The Slow Climb'
            assert 'content' in result

    def test_returns_none_when_not_found(self):
        """Verify None is returned when section doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', 'nonexistent')

            assert result is None

    def test_returns_none_when_expired(self):
        """Verify None is returned when section TTL has passed."""
        mock_section = get_mock_section('06_growth', 'AAPL', expired=True)

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_section}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            assert result is None

    def test_normalizes_section_id_to_lowercase(self):
        """Verify section_id is normalized to lowercase."""
        mock_section = get_mock_section('06_growth', 'AAPL')

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_section}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            get_report_section('AAPL', '06_GROWTH')

            call_args = mock_table.get_item.call_args
            assert call_args.kwargs['Key']['section_id'] == '06_growth'


# =============================================================================
# GET ALL SECTIONS TESTS
# =============================================================================

class TestGetAllSections:
    """Tests for get_all_sections() function."""

    def test_returns_sections_sorted_by_display_order(self):
        """Verify sections are returned sorted by display_order."""
        mock_items = [
            get_mock_section('11_debt', 'AAPL'),
            get_mock_section('06_growth', 'AAPL'),
            get_mock_section('15_realtalk', 'AAPL'),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': mock_items}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_all_sections('AAPL')

            assert len(result) == 3
            # Should be sorted: 06_growth (6), 11_debt (11), 15_realtalk (15)
            assert result[0]['section_id'] == '06_growth'
            assert result[1]['section_id'] == '11_debt'
            assert result[2]['section_id'] == '15_realtalk'

    def test_excludes_executive_item(self):
        """Verify 00_executive item is filtered out."""
        mock_items = [
            {'ticker': 'AAPL', 'section_id': '00_executive', 'display_order': 0},
            get_mock_section('06_growth', 'AAPL'),
        ]

        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': mock_items}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_all_sections('AAPL')

            assert len(result) == 1
            assert result[0]['section_id'] == '06_growth'

    def test_returns_empty_list_when_no_sections(self):
        """Verify empty list is returned when no sections found."""
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_all_sections('NOTFOUND')

            assert result == []


# =============================================================================
# CHECK REPORT EXISTS V2 TESTS
# =============================================================================

class TestCheckReportExistsV2:
    """Tests for check_report_exists_v2() function."""

    def test_returns_true_when_exists_and_not_expired(self):
        """Verify True is returned for valid report."""
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(int((datetime.utcnow() + timedelta(days=90)).timestamp())))
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('AAPL')

            assert result is True

    def test_returns_false_when_not_found(self):
        """Verify False is returned when report doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('NOTFOUND')

            assert result is False

    def test_returns_false_when_expired(self):
        """Verify False is returned when TTL has passed."""
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(int((datetime.utcnow() - timedelta(days=1)).timestamp())))
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('AAPL')

            assert result is False


# =============================================================================
# GET REPORT STATUS TESTS
# =============================================================================

class TestGetReportStatus:
    """Tests for get_report_status() function."""

    def test_returns_status_with_remaining_days(self):
        """Verify status includes ttl_remaining_days."""
        ttl_timestamp = int((datetime.utcnow() + timedelta(days=75)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_timestamp)),
            'generated_at': '2025-01-15T10:30:00Z',
            'total_word_count': Decimal('15000')
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('AAPL')

            assert result is not None
            assert result['exists'] is True
            assert result['ticker'] == 'AAPL'
            assert result['expired'] is False
            assert result['ttl_remaining_days'] >= 74  # Allow for test timing
            assert result['total_word_count'] == 15000

    def test_returns_expired_true_when_ttl_passed(self):
        """Verify expired=True when TTL has passed."""
        ttl_timestamp = int((datetime.utcnow() - timedelta(days=1)).timestamp())
        mock_item = {
            'ticker': 'AAPL',
            'ttl': Decimal(str(ttl_timestamp)),
            'generated_at': '2025-01-15T10:30:00Z',
            'total_word_count': Decimal('15000')
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('AAPL')

            assert result['expired'] is True
            assert result['ttl_remaining_days'] == 0

    def test_returns_none_when_not_found(self):
        """Verify None is returned when report doesn't exist."""
        mock_table = MagicMock()
        mock_table.get_item.return_value = {}

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_status('NOTFOUND')

            assert result is None


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in report service."""

    def test_get_executive_handles_dynamodb_error(self):
        """Verify get_executive returns None on DynamoDB error."""
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_executive('AAPL')

            assert result is None

    def test_get_report_section_handles_dynamodb_error(self):
        """Verify get_report_section returns None on DynamoDB error."""
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_report_section('AAPL', '06_growth')

            assert result is None

    def test_get_all_sections_handles_dynamodb_error(self):
        """Verify get_all_sections returns empty list on DynamoDB error."""
        mock_table = MagicMock()
        mock_table.query.side_effect = Exception("DynamoDB error")

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = get_all_sections('AAPL')

            assert result == []

    def test_check_report_exists_handles_dynamodb_error(self):
        """Verify check_report_exists_v2 returns False on DynamoDB error."""
        mock_table = MagicMock()
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        with patch('services.report_service._get_table_v2', return_value=mock_table):
            result = check_report_exists_v2('AAPL')

            assert result is False


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
