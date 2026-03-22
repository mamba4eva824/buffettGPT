"""
Unit tests for the S&P 500 Data Ingestion Pipeline.

Tests the pipeline handler, ticker processing, freshness checks,
and batch write logic with mocked AWS services.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, call
from datetime import datetime
from decimal import Decimal
import time

# Ensure src and project root are in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'


class TestIndexTickers:
    """Test the consolidated S&P 500 ticker list."""

    def test_sp500_ticker_count(self):
        from investment_research.index_tickers import SP500_TICKERS
        assert len(SP500_TICKERS) == 498

    def test_sp500_sectors_count(self):
        from investment_research.index_tickers import SP500_SECTORS
        assert len(SP500_SECTORS) == 498

    def test_sp500_sectors_have_required_fields(self):
        from investment_research.index_tickers import SP500_SECTORS
        for ticker, info in SP500_SECTORS.items():
            assert 'sector' in info, f"{ticker} missing sector"
            assert 'industry' in info, f"{ticker} missing industry"
            assert 'name' in info, f"{ticker} missing name"
            assert info['sector'], f"{ticker} has empty sector"

    def test_eleven_gics_sectors(self):
        from investment_research.index_tickers import get_sp500_sectors
        sectors = get_sp500_sectors()
        assert len(sectors) == 11

    def test_to_fmp_format(self):
        from investment_research.index_tickers import to_fmp_format
        assert to_fmp_format('BRK.B') == 'BRK-B'
        assert to_fmp_format('BF.B') == 'BF-B'
        assert to_fmp_format('AAPL') == 'AAPL'

    def test_get_sp500_by_sector(self):
        from investment_research.index_tickers import get_sp500_by_sector
        tech = get_sp500_by_sector('Technology')
        assert len(tech) >= 80
        assert 'AAPL' in tech
        assert 'MSFT' in tech

    def test_existing_functions_unchanged(self):
        from investment_research.index_tickers import (
            DJIA_TICKERS, SP100_TICKERS, get_index_tickers, get_test_tickers
        )
        assert len(DJIA_TICKERS) == 30
        assert len(SP100_TICKERS) == 102
        assert get_test_tickers() == ['AAPL', 'MSFT', 'F', 'NVDA']
        assert len(get_index_tickers('DJIA')) == 30


class TestPipelineHandler:
    """Test the sp500_pipeline Lambda handler."""

    @pytest.fixture
    def mock_aws(self):
        """Mock boto3 DynamoDB for pipeline tests."""
        mock_table = MagicMock()
        mock_table.query.return_value = {'Items': []}

        mock_batch_writer = MagicMock()
        mock_batch_writer.__enter__ = MagicMock(return_value=mock_batch_writer)
        mock_batch_writer.__exit__ = MagicMock(return_value=False)
        mock_table.batch_writer.return_value = mock_batch_writer

        mock_dynamodb = MagicMock()
        mock_dynamodb.Table.return_value = mock_table

        with patch('boto3.resource', return_value=mock_dynamodb):
            yield {
                'table': mock_table,
                'batch_writer': mock_batch_writer,
            }

    @patch('src.handlers.sp500_pipeline.get_financial_data')
    @patch('src.handlers.sp500_pipeline.extract_quarterly_trends')
    @patch('src.handlers.sp500_pipeline.prepare_metrics_for_cache')
    def test_process_ticker_success(self, mock_prepare, mock_extract, mock_get_data, mock_aws):
        """Test successful processing of a single ticker."""
        mock_get_data.return_value = {
            'raw_financials': {'income_statement': [{}], 'cash_flow': [{}], 'balance_sheet': [{}]},
            'currency_info': {'code': 'USD'},
            'cache_key': 'v3:AAPL:2026',
        }
        mock_extract.return_value = {'quarters': [1, 2, 3]}
        mock_prepare.return_value = [
            {'ticker': 'AAPL', 'fiscal_date': '2025-09-27', 'revenue_profit': {}},
        ]

        from src.handlers.sp500_pipeline import _process_ticker
        result = _process_ticker('AAPL', skip_fresh=False, include_events=False)

        assert result in ('cache_hit', 'api_call')
        mock_get_data.assert_called_once()
        mock_extract.assert_called_once()
        mock_prepare.assert_called_once()

    @patch('src.handlers.sp500_pipeline._process_ticker')
    def test_lambda_handler_processes_custom_tickers(self, mock_process, mock_aws):
        """Test handler with custom ticker list."""
        mock_process.return_value = 'cache_hit'

        from src.handlers.sp500_pipeline import lambda_handler
        event = {'tickers': ['AAPL', 'MSFT', 'GOOGL'], 'skip_fresh': False}
        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = 600_000

        result = lambda_handler(event, context)

        assert result['processed'] == 3
        assert result['total_tickers'] == 3
        assert mock_process.call_count == 3

    @patch('src.handlers.sp500_pipeline._process_ticker')
    def test_lambda_handler_handles_failures(self, mock_process, mock_aws):
        """Test handler records failures without stopping."""
        mock_process.side_effect = [
            'cache_hit',
            Exception('FMP API error'),
            'api_call',
        ]

        from src.handlers.sp500_pipeline import lambda_handler
        event = {'tickers': ['AAPL', 'FAIL', 'MSFT'], 'skip_fresh': False}
        context = MagicMock()
        context.get_remaining_time_in_millis.return_value = 600_000

        result = lambda_handler(event, context)

        assert result['processed'] == 2
        assert len(result['failures']) == 1
        assert result['failures'][0]['ticker'] == 'FAIL'

    @patch('src.handlers.sp500_pipeline._process_ticker')
    def test_lambda_handler_stops_on_timeout(self, mock_process, mock_aws):
        """Test handler stops gracefully when Lambda timeout approaches."""
        mock_process.return_value = 'cache_hit'

        from src.handlers.sp500_pipeline import lambda_handler
        event = {'tickers': ['AAPL', 'MSFT', 'GOOGL'], 'skip_fresh': False}
        context = MagicMock()
        # Return 30s remaining (< 60s buffer)
        context.get_remaining_time_in_millis.return_value = 30_000

        result = lambda_handler(event, context)

        assert result.get('stopped_early') is True
        # Should have stopped before processing all 3
        assert result['processed'] < 3

    def test_has_fresh_data_returns_false_when_empty(self, mock_aws):
        """Test freshness check returns False when no data exists."""
        mock_aws['table'].query.return_value = {'Items': []}

        import src.handlers.sp500_pipeline as pipeline_mod
        pipeline_mod.metrics_table = mock_aws['table']
        assert pipeline_mod._has_fresh_data('NEWCO') is False

    def test_has_fresh_data_returns_true_when_recent(self, mock_aws):
        """Test freshness check returns True for recent data."""
        mock_aws['table'].query.return_value = {
            'Items': [{'ticker': 'AAPL', 'cached_at': Decimal(str(time.time()))}]
        }

        import src.handlers.sp500_pipeline as pipeline_mod
        pipeline_mod.metrics_table = mock_aws['table']
        assert pipeline_mod._has_fresh_data('AAPL') is True

    def test_has_fresh_data_returns_false_when_old(self, mock_aws):
        """Test freshness check returns False for stale data."""
        old_time = time.time() - (30 * 86400)  # 30 days ago
        mock_aws['table'].query.return_value = {
            'Items': [{'ticker': 'AAPL', 'cached_at': Decimal(str(old_time))}]
        }

        import src.handlers.sp500_pipeline as pipeline_mod
        pipeline_mod.metrics_table = mock_aws['table']
        assert pipeline_mod._has_fresh_data('AAPL') is False


class TestBackfillScript:
    """Test the sp500_backfill local JSON loader."""

    def test_load_local_financials_remaps_keys(self, tmp_path):
        """Test that local JSON keys are remapped to fmp_client format."""
        # Create a mock JSON file
        mock_data = {
            'symbol': 'TEST',
            'income': [{'revenue': 1000, 'date': '2025-09-27'}],
            'cashflow': [{'operatingCashFlow': 500}],
            'balance': [{'totalDebt': 200}],
        }
        json_path = tmp_path / 'TEST.json'
        json_path.write_text(json.dumps(mock_data))

        # Patch the data dir
        with patch('src.handlers.sp500_backfill.SP500_DATA_DIR', tmp_path):
            from src.handlers.sp500_backfill import load_local_financials
            result = load_local_financials('TEST')

        assert result is not None
        assert 'income_statement' in result
        assert 'cash_flow' in result
        assert 'balance_sheet' in result
        assert len(result['income_statement']) == 1
        assert result['income_statement'][0]['revenue'] == 1000

    def test_load_local_financials_missing_file(self, tmp_path):
        """Test graceful handling of missing JSON file."""
        with patch('src.handlers.sp500_backfill.SP500_DATA_DIR', tmp_path):
            from src.handlers.sp500_backfill import load_local_financials
            result = load_local_financials('NONEXISTENT')

        assert result is None

    @patch('src.handlers.sp500_backfill.prepare_metrics_for_cache')
    @patch('src.handlers.sp500_backfill.extract_quarterly_trends')
    def test_backfill_ticker_dry_run(self, mock_extract, mock_prepare, tmp_path):
        """Test dry run doesn't write to DynamoDB."""
        mock_data = {
            'symbol': 'TEST',
            'income': [{'revenue': 1000, 'date': '2025-09-27', 'reportedCurrency': 'USD'}],
            'cashflow': [{'operatingCashFlow': 500}],
            'balance': [{'totalDebt': 200}],
        }
        json_path = tmp_path / 'TEST.json'
        json_path.write_text(json.dumps(mock_data))

        mock_extract.return_value = {'quarters': [1]}
        mock_prepare.return_value = [{'ticker': 'TEST', 'fiscal_date': '2025-09-27'}]

        mock_table = MagicMock()

        with patch('src.handlers.sp500_backfill.SP500_DATA_DIR', tmp_path):
            from src.handlers.sp500_backfill import backfill_ticker
            result = backfill_ticker('TEST', mock_table, dry_run=True)

        assert result['status'] == 'dry_run'
        assert result['items'] == 1
        mock_table.batch_writer.assert_not_called()


class TestEarningsCalendarChecker:
    """Test the earnings calendar checker placeholder."""

    @patch('src.handlers.earnings_calendar_checker._get_fmp_api_key')
    @patch('httpx.Client')
    def test_fetch_earnings_calendar(self, mock_client_cls, mock_api_key):
        """Test FMP earnings calendar API call."""
        mock_api_key.return_value = 'test-key'
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {'symbol': 'AAPL', 'date': '2026-01-30', 'eps': 2.10},
            {'symbol': 'MSFT', 'date': '2026-01-28', 'eps': 3.23},
            {'symbol': 'PRIVATE_CO', 'date': '2026-01-29', 'eps': 1.00},
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.get.return_value = mock_response
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client_cls.return_value = mock_client

        from src.handlers.earnings_calendar_checker import fetch_earnings_calendar
        result = fetch_earnings_calendar('2026-01-25', '2026-02-01')

        assert len(result) == 3

    @patch('src.handlers.earnings_calendar_checker.fetch_earnings_calendar')
    def test_handler_filters_sp500(self, mock_fetch):
        """Test handler filters calendar to S&P 500 tickers only."""
        mock_fetch.return_value = [
            {'symbol': 'AAPL', 'date': '2026-01-30', 'eps': 2.10},
            {'symbol': 'PRIVATE_CO', 'date': '2026-01-29', 'eps': 1.00},
            {'symbol': 'MSFT', 'date': '2026-04-01', 'eps': 3.23},
        ]

        from src.handlers.earnings_calendar_checker import lambda_handler
        result = lambda_handler({'lookback_days': 365, 'lookahead_days': 365}, None)

        # AAPL and MSFT are in SP500, PRIVATE_CO is not
        all_sp500_tickers = result['tickers_to_refresh'] + result['upcoming_tickers']
        assert 'PRIVATE_CO' not in all_sp500_tickers
        assert result['total_calendar_entries'] == 3
