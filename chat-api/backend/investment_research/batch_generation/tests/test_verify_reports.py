"""
Unit tests for verify_reports.py

Tests the DynamoDB report verification functionality:
- verify_reports() function
- Missing report detection
- Report metadata extraction
- Environment-specific table names

Run:
    cd chat-api/backend
    pytest investment_research/batch_generation/tests/test_verify_reports.py -v
"""

import os
import sys
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock

# Add parent directories to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, backend_dir)

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from investment_research.batch_generation.verify_reports import verify_reports


# =============================================================================
# TEST DATA - Mock DynamoDB items
# =============================================================================

def get_mock_executive_item(ticker: str, word_count: int = 15000) -> dict:
    """Generate a mock executive item from DynamoDB."""
    return {
        'ticker': ticker,
        'section_id': '00_executive',
        'generated_at': '2025-01-15T10:30:00Z',
        'total_word_count': Decimal(str(word_count)),
        'prompt_version': '4.8',
        'company_name': f'{ticker} Company'
    }


# =============================================================================
# VERIFY_REPORTS TESTS
# =============================================================================

class TestVerifyReports:
    """Tests for verify_reports() function."""

    def test_returns_true_when_all_reports_exist(self):
        """Verify True is returned when all reports are found."""
        test_tickers = ["AAPL", "MSFT", "GOOGL"]

        mock_table = MagicMock()
        mock_table.get_item.side_effect = [
            {'Item': get_mock_executive_item(t)} for t in test_tickers
        ]

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            result = verify_reports(
                tickers=test_tickers,
                environment="dev"
            )

        assert result is True
        assert mock_table.get_item.call_count == 3

    def test_returns_false_when_reports_missing(self):
        """Verify False is returned when some reports are missing."""
        test_tickers = ["AAPL", "MSFT", "MISSING"]

        mock_table = MagicMock()
        mock_table.get_item.side_effect = [
            {'Item': get_mock_executive_item("AAPL")},
            {'Item': get_mock_executive_item("MSFT")},
            {}  # Missing report
        ]

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            result = verify_reports(
                tickers=test_tickers,
                environment="dev"
            )

        assert result is False

    def test_uses_correct_table_name_for_dev(self):
        """Verify dev environment uses base table name."""
        test_tickers = ["AAPL"]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_executive_item("AAPL")}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_resource = MagicMock()
            mock_boto.resource.return_value = mock_resource
            mock_resource.Table.return_value = mock_table

            verify_reports(
                table_name="investment-reports-v2",
                tickers=test_tickers,
                environment="dev"
            )

            mock_resource.Table.assert_called_once_with("investment-reports-v2")

    def test_uses_correct_table_name_for_prod(self):
        """Verify prod environment appends -prod to table name."""
        test_tickers = ["AAPL"]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_executive_item("AAPL")}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_resource = MagicMock()
            mock_boto.resource.return_value = mock_resource
            mock_resource.Table.return_value = mock_table

            verify_reports(
                table_name="investment-reports-v2",
                tickers=test_tickers,
                environment="prod"
            )

            mock_resource.Table.assert_called_once_with("investment-reports-v2-prod")

    def test_queries_correct_key(self):
        """Verify get_item uses correct key structure."""
        test_tickers = ["AAPL"]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_executive_item("AAPL")}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            verify_reports(tickers=test_tickers, environment="dev")

            call_args = mock_table.get_item.call_args
            assert call_args.kwargs['Key'] == {
                'ticker': 'AAPL',
                'section_id': '00_executive'
            }

    def test_uses_djia_tickers_when_none_specified(self):
        """Verify DJIA_TICKERS is used when tickers=None."""
        mock_djia = ["AAPL", "MSFT"]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_executive_item("AAPL")}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table
            with patch('investment_research.batch_generation.verify_reports.DJIA_TICKERS', mock_djia):
                verify_reports(tickers=None, environment="dev")

        assert mock_table.get_item.call_count == 2


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Tests for error handling in verify_reports."""

    def test_handles_dynamodb_client_error(self):
        """Verify ClientError is handled gracefully."""
        from botocore.exceptions import ClientError

        test_tickers = ["AAPL"]

        mock_table = MagicMock()
        mock_table.get_item.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}},
            "GetItem"
        )

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            result = verify_reports(tickers=test_tickers, environment="dev")

        # Should return False since we couldn't verify
        assert result is False

    def test_empty_ticker_list(self):
        """Verify empty ticker list returns True (vacuous truth)."""
        mock_table = MagicMock()

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            result = verify_reports(tickers=[], environment="dev")

        # No tickers to check = all (0) reports found
        assert result is True
        mock_table.get_item.assert_not_called()


# =============================================================================
# METADATA EXTRACTION TESTS
# =============================================================================

class TestMetadataExtraction:
    """Tests for metadata extraction from DynamoDB items."""

    def test_extracts_word_count(self):
        """Verify word_count is extracted from item."""
        test_tickers = ["AAPL"]

        mock_item = get_mock_executive_item("AAPL", word_count=20000)
        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': mock_item}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            # The function prints info, but we just verify it doesn't crash
            result = verify_reports(tickers=test_tickers, environment="dev")

        assert result is True

    def test_handles_missing_optional_fields(self):
        """Verify missing optional fields don't cause errors."""
        test_tickers = ["AAPL"]

        # Minimal item - missing company_name and prompt_version
        minimal_item = {
            'ticker': 'AAPL',
            'section_id': '00_executive',
            'generated_at': '2025-01-15T10:30:00Z',
            'total_word_count': Decimal('15000')
        }

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': minimal_item}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            result = verify_reports(tickers=test_tickers, environment="dev")

        assert result is True


# =============================================================================
# REGION TESTS
# =============================================================================

class TestRegionConfiguration:
    """Tests for AWS region configuration."""

    def test_uses_specified_region(self):
        """Verify specified region is used for DynamoDB."""
        test_tickers = ["AAPL"]

        mock_table = MagicMock()
        mock_table.get_item.return_value = {'Item': get_mock_executive_item("AAPL")}

        with patch('investment_research.batch_generation.verify_reports.boto3') as mock_boto:
            mock_boto.resource.return_value.Table.return_value = mock_table

            verify_reports(
                tickers=test_tickers,
                environment="dev",
                region="eu-west-1"
            )

            mock_boto.resource.assert_called_once_with('dynamodb', region_name='eu-west-1')


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
