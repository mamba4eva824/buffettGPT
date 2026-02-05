"""
Unit tests for check_stale_reports.py

Tests the staleness checking functionality:
- check_djia_staleness() function
- Integration with EarningsTracker
- Stale vs fresh report classification
- Output formatting options

Run:
    cd chat-api/backend
    pytest investment_research/batch_generation/tests/test_check_stale_reports.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add parent directories to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, backend_dir)

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from investment_research.batch_generation.check_stale_reports import check_djia_staleness


# =============================================================================
# TEST DATA - Mock EarningsTracker responses
# =============================================================================

def get_mock_fresh_result(ticker: str) -> dict:
    """Generate a mock fresh report result."""
    return {
        'ticker': ticker,
        'needs_refresh': False,
        'reason': 'up_to_date',
        'last_earnings_stored': '2025-01-15',
        'current_latest_earnings': '2025-01-15'
    }


def get_mock_stale_result(ticker: str, reason: str = 'new_earnings_available') -> dict:
    """Generate a mock stale report result."""
    return {
        'ticker': ticker,
        'needs_refresh': True,
        'reason': reason,
        'last_earnings_stored': '2024-10-15',
        'current_latest_earnings': '2025-01-20'
    }


def get_mock_no_report_result(ticker: str) -> dict:
    """Generate a mock result for missing report."""
    return {
        'ticker': ticker,
        'needs_refresh': True,
        'reason': 'no_report_exists'
    }


# =============================================================================
# CHECK_DJIA_STALENESS TESTS
# =============================================================================

class TestCheckDjiaStaleness:
    """Tests for check_djia_staleness() function."""

    def test_returns_stale_tickers(self):
        """Verify stale tickers are returned in result list."""
        test_tickers = ["AAPL", "MSFT", "GOOGL"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result("AAPL"),
            get_mock_stale_result("MSFT"),
            get_mock_fresh_result("GOOGL")
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert "MSFT" in result
        assert len(result) == 1

    def test_returns_empty_list_when_all_fresh(self):
        """Verify empty list is returned when all reports are fresh."""
        test_tickers = ["AAPL", "MSFT"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result(t) for t in test_tickers
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert result == []

    def test_includes_missing_reports(self):
        """Verify missing reports are included in stale list."""
        test_tickers = ["AAPL", "MSFT", "NEWCO"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result("AAPL"),
            get_mock_fresh_result("MSFT"),
            get_mock_no_report_result("NEWCO")
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert "NEWCO" in result

    def test_uses_djia_tickers_when_none_specified(self):
        """Verify DJIA_TICKERS is used when tickers=None."""
        mock_djia = ["AAPL", "MSFT"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result(t) for t in mock_djia
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            with patch('investment_research.batch_generation.check_stale_reports.DJIA_TICKERS', mock_djia):
                check_djia_staleness(
                    tickers_only=False,
                    environment="dev",
                    tickers=None
                )

        assert mock_tracker.check_needs_refresh.call_count == 2

    def test_initializes_tracker_with_environment(self):
        """Verify EarningsTracker is initialized with correct environment."""
        test_tickers = ["AAPL"]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker') as MockTracker:
            mock_instance = MagicMock()
            mock_instance.check_needs_refresh.return_value = get_mock_fresh_result("AAPL")
            MockTracker.return_value = mock_instance

            check_djia_staleness(
                tickers_only=False,
                environment="prod",
                tickers=test_tickers
            )

            MockTracker.assert_called_once_with(environment="prod")


# =============================================================================
# OUTPUT FORMAT TESTS
# =============================================================================

class TestOutputFormat:
    """Tests for output formatting options."""

    def test_tickers_only_mode_returns_correct_list(self, capsys):
        """Verify tickers_only mode outputs only ticker symbols."""
        test_tickers = ["AAPL", "MSFT", "STALE"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result("AAPL"),
            get_mock_fresh_result("MSFT"),
            get_mock_stale_result("STALE")
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=True,
                environment="dev",
                tickers=test_tickers
            )

        # Should print just the stale ticker
        captured = capsys.readouterr()
        assert "STALE" in captured.out

    def test_verbose_mode_shows_details(self, capsys):
        """Verify verbose mode (tickers_only=False) shows details."""
        test_tickers = ["AAPL", "STALE"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_fresh_result("AAPL"),
            get_mock_stale_result("STALE")
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        captured = capsys.readouterr()
        # Should contain both check mark for fresh and X for stale
        assert "AAPL" in captured.out
        assert "STALE" in captured.out


# =============================================================================
# CLASSIFICATION TESTS
# =============================================================================

class TestClassification:
    """Tests for stale/fresh classification logic."""

    def test_classifies_new_earnings_as_stale(self):
        """Verify reports with new earnings are classified as stale."""
        test_tickers = ["AAPL"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.return_value = get_mock_stale_result(
            "AAPL",
            reason="new_earnings_available"
        )

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert "AAPL" in result

    def test_classifies_no_report_as_stale(self):
        """Verify missing reports are classified as stale."""
        test_tickers = ["NEWCO"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.return_value = get_mock_no_report_result("NEWCO")

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert "NEWCO" in result

    def test_classifies_up_to_date_as_fresh(self):
        """Verify up-to-date reports are classified as fresh."""
        test_tickers = ["AAPL"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.return_value = get_mock_fresh_result("AAPL")

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert "AAPL" not in result


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_ticker_list(self):
        """Verify empty ticker list returns empty result."""
        mock_tracker = MagicMock()

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=[]
            )

        assert result == []
        mock_tracker.check_needs_refresh.assert_not_called()

    def test_all_tickers_stale(self):
        """Verify all-stale scenario returns all tickers."""
        test_tickers = ["AAPL", "MSFT", "GOOGL"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_stale_result(t) for t in test_tickers
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert len(result) == 3
        assert set(result) == set(test_tickers)

    def test_mixed_stale_and_no_report(self):
        """Verify mixed stale reasons are handled correctly."""
        test_tickers = ["STALE1", "MISSING", "FRESH"]

        mock_tracker = MagicMock()
        mock_tracker.check_needs_refresh.side_effect = [
            get_mock_stale_result("STALE1"),
            get_mock_no_report_result("MISSING"),
            get_mock_fresh_result("FRESH")
        ]

        with patch('investment_research.batch_generation.check_stale_reports.EarningsTracker', return_value=mock_tracker):
            result = check_djia_staleness(
                tickers_only=False,
                environment="dev",
                tickers=test_tickers
            )

        assert len(result) == 2
        assert "STALE1" in result
        assert "MISSING" in result
        assert "FRESH" not in result


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
