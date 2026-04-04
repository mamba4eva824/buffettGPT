"""
Unit tests for the earnings_update Lambda handler.

Tests cover:
- Calendar check mode (auto) vs manual ticker mode
- Per-ticker processing with mocked FMP + DynamoDB
- update_item usage (not put_item)
- Graceful failure handling
- Response structure for future notifications
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ['ENVIRONMENT'] = 'test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['FMP_SECRET_NAME'] = 'buffett-test-fmp'


MOCK_CALENDAR_RESPONSE = [
    {"symbol": "AAPL", "date": "2026-04-02", "eps": None, "epsEstimated": 2.67, "revenue": None, "revenueEstimated": 138000000000},
    {"symbol": "MSFT", "date": "2026-04-02", "eps": None, "epsEstimated": 3.90, "revenue": None, "revenueEstimated": 70000000000},
    {"symbol": "NVDA", "date": "2026-04-10", "eps": None, "epsEstimated": 1.54, "revenue": None, "revenueEstimated": 40000000000},
    {"symbol": "RANDOMTICKER", "date": "2026-04-02", "eps": None, "epsEstimated": 1.0, "revenue": None, "revenueEstimated": 1000000},
]

MOCK_FINANCIAL_DATA = {
    'raw_financials': {'income_statement': [{}], 'cash_flow': [{}], 'balance_sheet': [{}]},
    'currency_info': {'code': 'USD'},
    'cache_key': 'v3:AAPL:2026',
}

MOCK_ITEMS = [
    {
        'ticker': 'AAPL',
        'fiscal_date': '2025-12-27',
        'fiscal_quarter': 'Q4',
        'fiscal_year': 2025,
        'revenue_profit': {'revenue': 143756000000},
        'earnings_events': {
            'earnings_date': '2026-01-29',
            'eps_actual': 2.84,
            'eps_estimated': 2.67,
            'eps_beat': True,
            'eps_surprise_pct': 6.37,
        },
    },
]


class TestEarningsUpdateHandler:
    """Test the lambda_handler function."""

    @patch('handlers.earnings_update._check_earnings_calendar')
    @patch('handlers.earnings_update._process_ticker')
    def test_auto_mode_checks_calendar(self, mock_process, mock_calendar):
        """Auto mode (no tickers in event) checks earnings calendar."""
        mock_calendar.return_value = {
            'reported': [{'ticker': 'AAPL'}, {'ticker': 'MSFT'}],
            'upcoming': [{'ticker': 'NVDA', 'earnings_date': '2026-04-10'}],
        }
        mock_process.return_value = {'ticker': 'AAPL', 'status': 'success'}

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({}, None)

        assert result['mode'] == 'auto'
        mock_calendar.assert_called_once()
        assert result['tickers_checked'] == 2

    @patch('handlers.earnings_update._process_ticker')
    def test_manual_mode_skips_calendar(self, mock_process):
        """Manual mode (tickers in event) skips calendar check."""
        mock_process.return_value = {'ticker': 'AAPL', 'status': 'success'}

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({'tickers': ['AAPL']}, None)

        assert result['mode'] == 'manual'
        assert result['tickers_checked'] == 1

    @patch('handlers.earnings_update._check_earnings_calendar')
    def test_no_tickers_returns_early(self, mock_calendar):
        """Returns early when no tickers need processing."""
        mock_calendar.return_value = {'reported': [], 'upcoming': []}

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({}, None)

        assert result['tickers_checked'] == 0
        assert 'No tickers' in result.get('message', '')

    @patch('handlers.earnings_update._process_ticker')
    def test_response_includes_notification_data(self, mock_process):
        """Response includes structured data for future notifications."""
        mock_process.return_value = {
            'ticker': 'AAPL',
            'status': 'success',
            'earnings_date': '2026-01-29',
            'eps_actual': 2.84,
            'eps_estimated': 2.67,
            'eps_beat': True,
            'eps_surprise_pct': 6.37,
        }

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({'tickers': ['AAPL']}, None)

        assert 'AAPL' in result['tickers_updated']
        assert result['results'][0]['eps_beat'] is True
        assert result['results'][0]['eps_actual'] == 2.84

    @patch('handlers.earnings_update._process_ticker')
    def test_failure_handling(self, mock_process):
        """Failed tickers are recorded but don't stop processing."""
        mock_process.side_effect = [
            Exception("FMP timeout"),
            {'ticker': 'MSFT', 'status': 'success'},
        ]

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({'tickers': ['AAPL', 'MSFT']}, None)

        assert len(result['failures']) == 1
        assert result['failures'][0]['ticker'] == 'AAPL'
        assert 'MSFT' in result['tickers_updated']


class TestProcessTicker:
    """Test the _process_ticker function."""

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_processes_full_pipeline(self, mock_table, mock_get_data, mock_extract,
                                     mock_prepare, mock_earnings, mock_dividends, mock_ttm):
        """Processes all steps: financials + earnings + dividends + TTM."""
        mock_get_data.return_value = MOCK_FINANCIAL_DATA
        mock_extract.return_value = {'quarters': [1]}
        mock_prepare.return_value = MOCK_ITEMS
        mock_earnings.return_value = [{'date': '2026-01-29', 'epsActual': 2.84}]
        mock_dividends.return_value = []
        mock_ttm.return_value = {'pe_ratio': 31.05}
        mock_table.update_item.return_value = {}

        from handlers.earnings_update import _process_ticker
        result = _process_ticker('AAPL')

        assert result['status'] == 'success'
        assert result['ticker'] == 'AAPL'
        mock_get_data.assert_called_once()
        mock_earnings.assert_called_once()
        mock_dividends.assert_called_once()
        mock_ttm.assert_called_once()

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_uses_update_item_not_put_item(self, mock_table, mock_get_data, mock_extract,
                                            mock_prepare, mock_earnings, mock_dividends, mock_ttm):
        """Uses update_item to preserve existing attributes like market_valuation."""
        mock_get_data.return_value = MOCK_FINANCIAL_DATA
        mock_extract.return_value = {'quarters': [1]}
        mock_prepare.return_value = MOCK_ITEMS
        mock_earnings.return_value = []
        mock_dividends.return_value = []
        mock_ttm.return_value = {}
        mock_table.update_item.return_value = {}

        from handlers.earnings_update import _process_ticker
        _process_ticker('AAPL')

        mock_table.update_item.assert_called()
        # batch_writer / put_item should NOT be called
        mock_table.batch_writer.assert_not_called()

    @patch('handlers.earnings_update.get_financial_data')
    def test_handles_no_financial_data(self, mock_get_data):
        """Returns gracefully when FMP has no financial data."""
        mock_get_data.return_value = {'raw_financials': {}, 'currency_info': {}}

        from handlers.earnings_update import _process_ticker
        result = _process_ticker('AAPL')

        assert result['status'] == 'no_financial_data'

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_attaches_ttm_to_latest_quarter(self, mock_table, mock_get_data, mock_extract,
                                             mock_prepare, mock_earnings, mock_dividends, mock_ttm):
        """TTM valuations are attached to the latest quarter item."""
        mock_get_data.return_value = MOCK_FINANCIAL_DATA
        mock_extract.return_value = {'quarters': [1]}
        items = [
            {'ticker': 'AAPL', 'fiscal_date': '2025-06-28', 'revenue_profit': {}},
            {'ticker': 'AAPL', 'fiscal_date': '2025-12-27', 'revenue_profit': {}},
        ]
        mock_prepare.return_value = items
        mock_earnings.return_value = []
        mock_dividends.return_value = []
        mock_ttm.return_value = {'pe_ratio': 31.05, 'market_cap': 3700000000000}
        mock_table.update_item.return_value = {}

        from handlers.earnings_update import _process_ticker
        result = _process_ticker('AAPL')

        assert result['has_market_valuation'] is True
        latest = max(items, key=lambda x: x['fiscal_date'])
        assert latest['market_valuation']['pe_ratio'] == 31.05


class TestCalendarCheck:
    """Test the _check_earnings_calendar function."""

    @patch('handlers.earnings_update._get_fmp_api_key', return_value='test-key')
    def test_filters_to_sp500(self, mock_key):
        """Only S&P 500 tickers are included in results."""
        mock_response = MagicMock()
        mock_response.json.return_value = MOCK_CALENDAR_RESPONSE
        mock_response.raise_for_status = MagicMock()

        with patch('httpx.Client') as mock_client:
            mock_client.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            mock_client.return_value.__exit__ = MagicMock(return_value=False)

            from handlers.earnings_update import _check_earnings_calendar
            result = _check_earnings_calendar(lookback_days=2)

        # RANDOMTICKER should be filtered out
        all_tickers = [r['ticker'] for r in result['reported']] + [r['ticker'] for r in result['upcoming']]
        assert 'RANDOMTICKER' not in all_tickers
