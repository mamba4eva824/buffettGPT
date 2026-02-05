"""
Unit tests for prepare_batch_data.py

Tests the batch data preparation functionality:
- prepare_all_data() function
- CLI argument parsing
- Error handling for failed ticker fetches
- JSON output format

Run:
    cd chat-api/backend
    pytest investment_research/batch_generation/tests/test_prepare_batch_data.py -v
"""

import json
import os
import sys
import pytest
import tempfile
from datetime import datetime
from unittest.mock import patch, MagicMock

# Add parent directories to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, backend_dir)

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from investment_research.batch_generation.prepare_batch_data import prepare_all_data


# =============================================================================
# TEST DATA - Mock financial data
# =============================================================================

def get_mock_prepared_data(ticker: str) -> dict:
    """Generate mock data that ReportGenerator.prepare_data would return."""
    return {
        "metrics_context": f"Financial metrics for {ticker}...\nRevenue: $100B\nNet Income: $25B",
        "features": {
            "revenue_growth": 0.15,
            "net_margin": 0.25,
            "pe_ratio": 28.5,
            "debt_to_equity": 1.2
        },
        "raw_financials": {
            "income_statement": [{"quarter": f"Q{i}"} for i in range(1, 21)]
        },
        "valuation_data": {
            "pe": 28.5,
            "pb": 12.3
        }
    }


# =============================================================================
# PREPARE_ALL_DATA TESTS
# =============================================================================

class TestPrepareAllData:
    """Tests for prepare_all_data() function."""

    def test_prepares_data_for_all_tickers(self, tmp_path):
        """Verify data is prepared for all specified tickers."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL", "MSFT", "GOOGL"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.side_effect = [
            get_mock_prepared_data(t) for t in test_tickers
        ]

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers,
                prompt_version=4.8
            )

        assert len(result) == 3
        assert "AAPL" in result
        assert "MSFT" in result
        assert "GOOGL" in result
        assert mock_generator.prepare_data.call_count == 3

    def test_saves_output_to_json_file(self, tmp_path):
        """Verify output is saved to JSON file."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = get_mock_prepared_data("AAPL")

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        assert output_file.exists()

        with open(output_file) as f:
            saved_data = json.load(f)

        assert "AAPL" in saved_data
        assert "metrics_context" in saved_data["AAPL"]

    def test_includes_metadata_in_output(self, tmp_path):
        """Verify prepared_at and prompt_version are included."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = get_mock_prepared_data("AAPL")

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers,
                prompt_version=4.8
            )

        assert "prepared_at" in result["AAPL"]
        assert result["AAPL"]["prompt_version"] == 4.8

    def test_handles_failed_ticker_gracefully(self, tmp_path):
        """Verify failed tickers are recorded with error message."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL", "INVALID", "MSFT"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.side_effect = [
            get_mock_prepared_data("AAPL"),
            Exception("FMP API error: ticker not found"),
            get_mock_prepared_data("MSFT")
        ]

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        assert len(result) == 3
        assert "error" not in result["AAPL"]
        assert "error" in result["INVALID"]
        assert "FMP API error" in result["INVALID"]["error"]
        assert "error" not in result["MSFT"]

    def test_uses_djia_tickers_when_none_specified(self, tmp_path):
        """Verify DJIA_TICKERS is used when tickers=None."""
        output_file = tmp_path / "test_output.json"

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = get_mock_prepared_data("AAPL")

        mock_djia = ["AAPL", "MSFT"]

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            with patch('investment_research.batch_generation.prepare_batch_data.DJIA_TICKERS', mock_djia):
                result = prepare_all_data(
                    output_file=str(output_file),
                    tickers=None
                )

        assert len(result) == 2
        assert mock_generator.prepare_data.call_count == 2

    def test_extracts_financials_summary(self, tmp_path):
        """Verify raw_financials_summary is extracted correctly."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        mock_data = get_mock_prepared_data("AAPL")
        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = mock_data

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        summary = result["AAPL"]["raw_financials_summary"]
        assert summary["quarters"] == 20
        assert summary["has_valuation"] is True

    def test_initializes_generator_with_prompt_version(self, tmp_path):
        """Verify ReportGenerator is initialized with correct prompt version."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator') as MockGenerator:
            mock_instance = MagicMock()
            mock_instance.prepare_data.return_value = get_mock_prepared_data("AAPL")
            MockGenerator.return_value = mock_instance

            prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers,
                prompt_version=5.0
            )

            MockGenerator.assert_called_once_with(prompt_version=5.0)


# =============================================================================
# OUTPUT FORMAT TESTS
# =============================================================================

class TestOutputFormat:
    """Tests for JSON output format."""

    def test_output_is_valid_json(self, tmp_path):
        """Verify output file is valid JSON."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = get_mock_prepared_data("AAPL")

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        # This will raise if not valid JSON
        with open(output_file) as f:
            data = json.load(f)

        assert isinstance(data, dict)

    def test_output_contains_expected_keys(self, tmp_path):
        """Verify output has expected structure."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = get_mock_prepared_data("AAPL")

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        with open(output_file) as f:
            data = json.load(f)

        ticker_data = data["AAPL"]
        assert "metrics_context" in ticker_data
        assert "features" in ticker_data
        assert "raw_financials_summary" in ticker_data
        assert "prepared_at" in ticker_data
        assert "prompt_version" in ticker_data


# =============================================================================
# EDGE CASES
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_ticker_list(self, tmp_path):
        """Verify empty ticker list returns empty dict."""
        output_file = tmp_path / "test_output.json"

        mock_generator = MagicMock()

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=[]
            )

        assert result == {}
        mock_generator.prepare_data.assert_not_called()

    def test_all_tickers_fail(self, tmp_path):
        """Verify all-fail scenario is handled."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["BAD1", "BAD2"]

        mock_generator = MagicMock()
        mock_generator.prepare_data.side_effect = Exception("API error")

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        assert len(result) == 2
        assert "error" in result["BAD1"]
        assert "error" in result["BAD2"]

    def test_missing_optional_data_fields(self, tmp_path):
        """Verify missing optional fields are handled."""
        output_file = tmp_path / "test_output.json"
        test_tickers = ["AAPL"]

        # Minimal data - missing features and valuation_data
        minimal_data = {
            "metrics_context": "Some metrics",
            "raw_financials": {
                "income_statement": []
            }
        }

        mock_generator = MagicMock()
        mock_generator.prepare_data.return_value = minimal_data

        with patch('investment_research.batch_generation.prepare_batch_data.ReportGenerator', return_value=mock_generator):
            result = prepare_all_data(
                output_file=str(output_file),
                tickers=test_tickers
            )

        assert "AAPL" in result
        assert result["AAPL"]["features"] == {}
        assert result["AAPL"]["raw_financials_summary"]["has_valuation"] is False


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
