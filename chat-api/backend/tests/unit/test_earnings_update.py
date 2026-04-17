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

    @patch('handlers.earnings_update._already_updated_since_earnings', return_value=False)
    @patch('handlers.earnings_update._check_earnings_calendar')
    @patch('handlers.earnings_update._process_ticker')
    def test_auto_mode_checks_calendar(self, mock_process, mock_calendar, mock_fresh):
        """Auto mode (no tickers in event) checks earnings calendar."""
        mock_calendar.return_value = {
            'reported': [
                {'ticker': 'AAPL', 'earnings_date': '2026-04-02'},
                {'ticker': 'MSFT', 'earnings_date': '2026-04-02'},
            ],
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

    @patch('handlers.earnings_update._ensure_feed_record')
    @patch('handlers.earnings_update._already_updated_since_earnings')
    @patch('handlers.earnings_update._check_earnings_calendar')
    @patch('handlers.earnings_update._process_ticker')
    def test_auto_mode_skips_already_processed(self, mock_process, mock_calendar, mock_fresh, mock_ensure):
        """Auto mode skips tickers already processed for this earnings cycle."""
        mock_calendar.return_value = {
            'reported': [
                {'ticker': 'AAPL', 'earnings_date': '2026-04-02', 'eps_actual': 2.84},
                {'ticker': 'MSFT', 'earnings_date': '2026-04-02', 'eps_actual': 3.95},
            ],
            'upcoming': [],
        }
        # AAPL already processed, MSFT not
        mock_fresh.side_effect = lambda t, d, fmp_actual: t == 'AAPL'
        mock_process.return_value = {'ticker': 'MSFT', 'status': 'success'}

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({}, None)

        # Only MSFT should be processed
        assert mock_process.call_count == 1
        assert 'AAPL' in result['skipped_already_processed']
        assert 'MSFT' in result['tickers_updated']

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


class TestAlreadyUpdatedSinceEarnings:
    """Test _already_updated_since_earnings freshness check (post-fix behavior)."""

    @patch('handlers.earnings_update.metrics_table')
    def test_skips_when_fmp_actual_present_and_stored_matches(self, mock_table):
        """Returns True when FMP has actual AND stored row matches the announced cycle."""
        mock_table.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-04-16',
                    'eps_actual': Decimal('1.25'),
                    'eps_estimated': Decimal('1.20'),
                },
            }],
        }

        from handlers.earnings_update import _already_updated_since_earnings
        assert _already_updated_since_earnings('NFLX', '2026-04-16', 1.25) is True

    @patch('handlers.earnings_update.metrics_table')
    def test_processes_when_fmp_actual_none(self, mock_table):
        """Returns False when FMP has no eps_actual yet (after-hours reporter, morning run)."""
        # Even if metrics row looks "fresh" for some prior cycle, FMP-actual=None wins.
        mock_table.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-01-20',
                    'eps_actual': Decimal('0.56'),
                },
            }],
        }

        from handlers.earnings_update import _already_updated_since_earnings
        assert _already_updated_since_earnings('NFLX', '2026-04-16', None) is False

    @patch('handlers.earnings_update.metrics_table')
    def test_processes_when_stored_date_mismatch(self, mock_table):
        """Returns False when stored cycle != announced cycle (prior-cycle false positive guard)."""
        mock_table.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-01-20',
                    'eps_actual': Decimal('0.56'),
                },
            }],
        }

        from handlers.earnings_update import _already_updated_since_earnings
        assert _already_updated_since_earnings('NFLX', '2026-04-16', 1.25) is False

    @patch('handlers.earnings_update.metrics_table')
    def test_normalizes_date_with_time_suffix(self, mock_table):
        """Returns True even if stored date has a time suffix (e.g. '2026-04-16 16:00:00')."""
        mock_table.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-04-16 16:00:00',
                    'eps_actual': Decimal('1.25'),
                },
            }],
        }

        from handlers.earnings_update import _already_updated_since_earnings
        assert _already_updated_since_earnings('NFLX', '2026-04-16', 1.25) is True


class TestEnsureFeedRecord:
    """Test _ensure_feed_record date-mismatch guard."""

    @patch('handlers.earnings_update.aggregates_table')
    @patch('handlers.earnings_update.metrics_table')
    def test_refuses_on_earnings_date_mismatch(self, mock_metrics, mock_aggregates):
        """Refuses to write a feed record when stored metrics earnings_date doesn't match."""
        mock_aggregates.get_item.return_value = {}  # No existing feed record
        mock_metrics.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-01-20',
                    'eps_actual': Decimal('0.56'),
                    'eps_estimated': Decimal('0.50'),
                },
            }],
        }

        from handlers.earnings_update import _ensure_feed_record
        _ensure_feed_record('NFLX', '2026-04-16')

        mock_aggregates.put_item.assert_not_called()

    @patch('handlers.earnings_update.aggregates_table')
    @patch('handlers.earnings_update.metrics_table')
    def test_writes_when_earnings_date_matches(self, mock_metrics, mock_aggregates):
        """Writes a feed record when stored metrics earnings_date matches the request."""
        mock_aggregates.get_item.return_value = {}  # No existing feed record
        mock_metrics.query.return_value = {
            'Items': [{
                'ticker': 'NFLX',
                'earnings_events': {
                    'earnings_date': '2026-04-16',
                    'eps_actual': Decimal('1.25'),
                    'eps_estimated': Decimal('1.20'),
                },
            }],
        }

        from handlers.earnings_update import _ensure_feed_record
        _ensure_feed_record('NFLX', '2026-04-16')

        mock_aggregates.put_item.assert_called_once()
        written = mock_aggregates.put_item.call_args.kwargs['Item']
        assert written['ticker'] == 'NFLX'
        assert written['earnings_date'] == '2026-04-16'


class TestForceRefreshAndPropagationLag:
    """Test force_refresh kwarg and FMP propagation-lag guard in _process_ticker."""

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_process_ticker_passes_force_refresh_true(
        self, mock_table, mock_get_financial_data, mock_extract,
        mock_prepare, mock_earnings, mock_dividends, mock_ttm,
    ):
        """_process_ticker always calls get_financial_data with force_refresh=True."""
        mock_get_financial_data.return_value = {
            'raw_financials': {
                'income_statement': [{'date': '2026-04-16'}],
                'balance_sheet': [{'date': '2026-04-16'}],
                'cash_flow': [{'date': '2026-04-16'}],
            },
            'currency_info': {'code': 'USD'},
            'cache_key': 'v3:AAPL:2026',
        }
        mock_extract.return_value = {'quarters': [1]}
        mock_prepare.return_value = MOCK_ITEMS
        mock_earnings.return_value = []
        mock_dividends.return_value = []
        mock_ttm.return_value = {}
        mock_table.update_item.return_value = {}

        from handlers.earnings_update import _process_ticker
        _process_ticker('AAPL', earnings_date='2026-04-16')

        assert mock_get_financial_data.call_args.kwargs == {'force_refresh': True}

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_propagation_lag_returns_early_with_lag_status(
        self, mock_table, mock_get_financial_data, mock_extract,
        mock_prepare, mock_earnings, mock_dividends, mock_ttm,
    ):
        """When FMP hasn't propagated the reported quarter, return lag status and skip processing."""
        mock_get_financial_data.return_value = {
            'raw_financials': {
                'income_statement': [{'date': '2026-01-20'}],
                'balance_sheet': [{'date': '2026-01-20'}],
                'cash_flow': [{'date': '2026-01-20'}],
            },
            'currency_info': {'code': 'USD'},
            'cache_key': 'v3:NFLX:2026',
        }

        from handlers.earnings_update import _process_ticker
        # Gap = 2026-04-16 - 2026-01-20 = 86 days (> 10).
        result = _process_ticker('NFLX', earnings_date='2026-04-16')

        assert result['status'] == 'fmp_propagation_lag'
        assert result['latest_statement_date'] == '2026-01-20'
        assert result['earnings_date'] == '2026-04-16'
        # Early return: pipeline steps below the guard must not execute.
        mock_extract.assert_not_called()
        mock_prepare.assert_not_called()

    @patch('handlers.earnings_update.fetch_ttm_valuations')
    @patch('handlers.earnings_update.fetch_dividends')
    @patch('handlers.earnings_update.fetch_earnings')
    @patch('handlers.earnings_update.prepare_metrics_for_cache')
    @patch('handlers.earnings_update.extract_quarterly_trends')
    @patch('handlers.earnings_update.get_financial_data')
    @patch('handlers.earnings_update.metrics_table')
    def test_no_lag_guard_when_earnings_date_none(
        self, mock_table, mock_get_financial_data, mock_extract,
        mock_prepare, mock_earnings, mock_dividends, mock_ttm,
    ):
        """When earnings_date is None (manual mode), the lag guard is a no-op."""
        mock_get_financial_data.return_value = {
            'raw_financials': {
                'income_statement': [{'date': '2026-01-20'}],
                'balance_sheet': [{'date': '2026-01-20'}],
                'cash_flow': [{'date': '2026-01-20'}],
            },
            'currency_info': {'code': 'USD'},
            'cache_key': 'v3:AAPL:2026',
        }
        mock_extract.return_value = {'quarters': [1]}
        mock_prepare.return_value = MOCK_ITEMS
        mock_earnings.return_value = []
        mock_dividends.return_value = []
        mock_ttm.return_value = {}
        mock_table.update_item.return_value = {}

        from handlers.earnings_update import _process_ticker
        result = _process_ticker('AAPL')

        assert result['status'] == 'success'
        # Pipeline ran — guard was a no-op.
        mock_extract.assert_called_once()
        mock_prepare.assert_called_once()

    @patch('handlers.earnings_update._process_ticker')
    def test_handler_surfaces_propagation_lag_in_response(self, mock_process):
        """Handler response surfaces tickers hit by FMP propagation lag."""
        mock_process.return_value = {
            'ticker': 'NFLX',
            'status': 'fmp_propagation_lag',
            'latest_statement_date': '2026-01-20',
            'earnings_date': '2026-04-16',
        }

        from handlers.earnings_update import lambda_handler
        result = lambda_handler({'tickers': ['NFLX']}, None)

        assert result['propagation_lag'] == ['NFLX']


class TestNarrowScopeAndSanityGates:
    """Regression tests for narrow-scope writes + sanity/no-new-quarter gates."""

    def test_narrow_scope_writes_only_latest_quarter(self):
        """AC-1: default mode writes exactly 1 row (the reported quarter)."""
        import handlers.earnings_update as eu

        items = [
            {'ticker': 'NFLX', 'fiscal_date': '2025-06-30', 'revenue_profit': {'revenue': 100},
             'balance_sheet': {'total_equity': 10}, 'fiscal_year': 2025, 'fiscal_quarter': 'Q2'},
            {'ticker': 'NFLX', 'fiscal_date': '2025-09-30', 'revenue_profit': {'revenue': 120},
             'balance_sheet': {'total_equity': 12}, 'fiscal_year': 2025, 'fiscal_quarter': 'Q3'},
            {'ticker': 'NFLX', 'fiscal_date': '2025-12-31', 'revenue_profit': {'revenue': 140},
             'balance_sheet': {'total_equity': 14}, 'fiscal_year': 2025, 'fiscal_quarter': 'Q4'},
            {'ticker': 'NFLX', 'fiscal_date': '2026-04-10', 'revenue_profit': {'revenue': 160},
             'balance_sheet': {'total_equity': 16}, 'earnings_events': {'earnings_date': '2026-04-16'},
             'fiscal_year': 2026, 'fiscal_quarter': 'Q1'},
        ]
        with patch('handlers.earnings_update.get_financial_data', return_value={
                    'raw_financials': {'income_statement': [{'date': '2026-04-10'}]},
                    'currency_info': {'code': 'USD'}, 'cache_key': 'v3:NFLX:2026'}), \
             patch('handlers.earnings_update.extract_quarterly_trends', return_value={}), \
             patch('handlers.earnings_update.prepare_metrics_for_cache', return_value=items), \
             patch('handlers.earnings_update.fetch_earnings', return_value=[]), \
             patch('handlers.earnings_update.fetch_dividends', return_value=[]), \
             patch('handlers.earnings_update.fetch_ttm_valuations', return_value={}), \
             patch('handlers.earnings_update._get_stored_max_fiscal_date', return_value='2025-12-31'), \
             patch.object(eu.metrics_table, 'update_item') as mock_update:
            result = eu._process_ticker('NFLX', earnings_date='2026-04-16')

        assert result['status'] == 'success'
        assert result['quarters_written'] == 1
        assert mock_update.call_count == 1
        written_key = mock_update.call_args.kwargs['Key']
        assert written_key == {'ticker': 'NFLX', 'fiscal_date': '2026-04-10'}

    def test_suspect_data_skips_write(self):
        """AC-3: SCHW-style corrupted balance sheet triggers fmp_suspect_data, no write."""
        import handlers.earnings_update as eu

        items = [
            # Previous quarters are fine (won't be inspected since gate only checks latest)
            {'ticker': 'SCHW', 'fiscal_date': '2025-12-31', 'revenue_profit': {'revenue': 3100000000},
             'balance_sheet': {'total_equity': 49000000000}, 'fiscal_year': 2025, 'fiscal_quarter': 'Q4'},
            # Latest quarter: equity $2.7M vs revenue $3.1B — ratio ~0.00087, far below 0.01
            {'ticker': 'SCHW', 'fiscal_date': '2026-04-10', 'revenue_profit': {'revenue': 3100000000},
             'balance_sheet': {'total_equity': 2700000},
             'earnings_events': {'earnings_date': '2026-04-16'},
             'fiscal_year': 2026, 'fiscal_quarter': 'Q1'},
        ]
        with patch('handlers.earnings_update.get_financial_data', return_value={
                    'raw_financials': {'income_statement': [{'date': '2026-04-10'}]},
                    'currency_info': {'code': 'USD'}, 'cache_key': 'v3:SCHW:2026'}), \
             patch('handlers.earnings_update.extract_quarterly_trends', return_value={}), \
             patch('handlers.earnings_update.prepare_metrics_for_cache', return_value=items), \
             patch('handlers.earnings_update.fetch_earnings', return_value=[]), \
             patch('handlers.earnings_update.fetch_dividends', return_value=[]), \
             patch('handlers.earnings_update.fetch_ttm_valuations', return_value={}), \
             patch.object(eu.metrics_table, 'update_item') as mock_update:
            result = eu._process_ticker('SCHW', earnings_date='2026-04-16')

        assert result['status'] == 'fmp_suspect_data'
        assert result['latest_fiscal_date'] == '2026-04-10'
        assert mock_update.call_count == 0

    def test_no_new_quarter_skips_write(self):
        """AC-4a: FMP's latest fiscal_date matches stored max, but earnings_events.earnings_date mismatches."""
        import handlers.earnings_update as eu

        items = [
            {'ticker': 'PLD', 'fiscal_date': '2025-12-31',
             'revenue_profit': {'revenue': 2000000000},
             'balance_sheet': {'total_equity': 53000000000},
             'earnings_events': {'earnings_date': '2026-01-05'},  # old cycle
             'fiscal_year': 2025, 'fiscal_quarter': 'Q4'},
        ]
        with patch('handlers.earnings_update.get_financial_data', return_value={
                    'raw_financials': {'income_statement': [{'date': '2025-12-31'}]},
                    'currency_info': {'code': 'USD'}, 'cache_key': 'v3:PLD:2026'}), \
             patch('handlers.earnings_update.extract_quarterly_trends', return_value={}), \
             patch('handlers.earnings_update.prepare_metrics_for_cache', return_value=items), \
             patch('handlers.earnings_update.fetch_earnings', return_value=[]), \
             patch('handlers.earnings_update.fetch_dividends', return_value=[]), \
             patch('handlers.earnings_update.fetch_ttm_valuations', return_value={}), \
             patch('handlers.earnings_update._get_stored_max_fiscal_date', return_value='2025-12-31'), \
             patch.object(eu.metrics_table, 'update_item') as mock_update:
            result = eu._process_ticker('PLD', earnings_date='2026-01-07')

        assert result['status'] == 'fmp_no_new_quarter'
        assert mock_update.call_count == 0

    def test_earnings_date_missing_skips_write(self):
        """AC-4b: FMP has latest fiscal_date matching stored max, but earnings_events.earnings_date is missing."""
        import handlers.earnings_update as eu

        items = [
            {'ticker': 'FOO', 'fiscal_date': '2025-12-31',
             'revenue_profit': {'revenue': 1000000000},
             'balance_sheet': {'total_equity': 5000000000},
             'earnings_events': {},  # no earnings_date
             'fiscal_year': 2025, 'fiscal_quarter': 'Q4'},
        ]
        with patch('handlers.earnings_update.get_financial_data', return_value={
                    'raw_financials': {'income_statement': [{'date': '2025-12-31'}]},
                    'currency_info': {'code': 'USD'}, 'cache_key': 'v3:FOO:2026'}), \
             patch('handlers.earnings_update.extract_quarterly_trends', return_value={}), \
             patch('handlers.earnings_update.prepare_metrics_for_cache', return_value=items), \
             patch('handlers.earnings_update.fetch_earnings', return_value=[]), \
             patch('handlers.earnings_update.fetch_dividends', return_value=[]), \
             patch('handlers.earnings_update.fetch_ttm_valuations', return_value={}), \
             patch('handlers.earnings_update._get_stored_max_fiscal_date', return_value='2025-12-31'), \
             patch.object(eu.metrics_table, 'update_item') as mock_update:
            result = eu._process_ticker('FOO', earnings_date='2026-01-07')

        assert result['status'] == 'fmp_earnings_date_missing'
        assert mock_update.call_count == 0

    def test_full_reingest_writes_all_quarters(self):
        """AC-6: full_reingest=True preserves original 20-row write behavior."""
        import handlers.earnings_update as eu

        # Generate 20 quarters with the latest at 2026-04-10 (within 10 days of earnings_date).
        # Use sortable date strings: most recent first, walking backward ~90 days each quarter.
        items = [
            {'ticker': 'AAPL',
             'fiscal_date': f'20{21 + q//4:02d}-{["04-10", "01-10", "10-10", "07-10"][q % 4]}'
                            if q < 20 else '2026-04-10',
             'revenue_profit': {'revenue': 100000000000},
             'balance_sheet': {'total_equity': 60000000000},
             'fiscal_year': 2021 + q // 4, 'fiscal_quarter': f'Q{(q % 4) + 1}'}
            for q in range(20)
        ]
        # Override item[0] to ensure latest_item = 2026-04-10 deterministically
        items[0] = {'ticker': 'AAPL', 'fiscal_date': '2026-04-10',
                    'revenue_profit': {'revenue': 100000000000},
                    'balance_sheet': {'total_equity': 60000000000},
                    'fiscal_year': 2026, 'fiscal_quarter': 'Q1'}
        with patch('handlers.earnings_update.get_financial_data', return_value={
                    'raw_financials': {'income_statement': [{'date': '2026-04-10'}]},
                    'currency_info': {'code': 'USD'}, 'cache_key': 'v3:AAPL:2026'}), \
             patch('handlers.earnings_update.extract_quarterly_trends', return_value={}), \
             patch('handlers.earnings_update.prepare_metrics_for_cache', return_value=items), \
             patch('handlers.earnings_update.fetch_earnings', return_value=[]), \
             patch('handlers.earnings_update.fetch_dividends', return_value=[]), \
             patch('handlers.earnings_update.fetch_ttm_valuations', return_value={}), \
             patch.object(eu.metrics_table, 'update_item') as mock_update:
            result = eu._process_ticker('AAPL', earnings_date='2026-04-16', full_reingest=True)

        assert result['status'] == 'success'
        assert result['quarters_written'] == 20
        assert mock_update.call_count == 20


class TestFeatureExtractorNoneGuard:
    """Regression tests for feature_extractor None-safety (tonight's SCHW crash)."""

    def test_roe_change_2yr_handles_none_roe(self):
        """AC-5: when roe is None (corrupted balance sheet), roe_change_2yr returns None, not TypeError."""
        from utils.feature_extractor import extract_quarterly_trends

        # Build a minimal raw_financials with SCHW-style corrupted Q1 equity
        # but healthy Q1-2y earlier (normal equity) to force `roe=None` current + `roe_2y=float` prior.
        # Each list is newest-first per FMP convention; index 0 = latest, index 8 = 2y ago.
        now = [{'date': '2026-03-31', 'netIncome': 1500000000, 'revenue': 3100000000, 'grossProfit': 2500000000,
                'operatingIncome': 1500000000, 'ebitda': 2000000000,
                'researchAndDevelopmentExpenses': 0, 'depreciationAndAmortization': 200000000,
                'interestExpense': 100000000, 'incomeTaxExpense': 400000000, 'epsdiluted': 0.80,
                'weightedAverageShsOutDil': 1800000000, 'weightedAverageShsOut': 1800000000}]
        # 7 fill quarters between now and 2y ago (index 1-7) — minimal structure
        filler_inc = [{'date': f'2025-{12-q:02d}-31', 'netIncome': 1200000000, 'revenue': 2900000000,
                       'grossProfit': 2400000000, 'operatingIncome': 1200000000, 'ebitda': 1700000000,
                       'researchAndDevelopmentExpenses': 0, 'depreciationAndAmortization': 200000000,
                       'interestExpense': 100000000, 'incomeTaxExpense': 300000000, 'epsdiluted': 0.67,
                       'weightedAverageShsOutDil': 1800000000, 'weightedAverageShsOut': 1800000000}
                      for q in range(1, 8)]
        two_years_ago = [{'date': '2024-03-31', 'netIncome': 1100000000, 'revenue': 2500000000,
                          'grossProfit': 2000000000, 'operatingIncome': 1100000000, 'ebitda': 1500000000,
                          'researchAndDevelopmentExpenses': 0, 'depreciationAndAmortization': 200000000,
                          'interestExpense': 100000000, 'incomeTaxExpense': 300000000, 'epsdiluted': 0.61,
                          'weightedAverageShsOutDil': 1800000000, 'weightedAverageShsOut': 1800000000}]
        income = now + filler_inc + two_years_ago
        # CORRUPTED balance sheet for Q0 only (equity $2.7M, $1000x too small)
        bs_now = [{'date': '2026-03-31', 'totalStockholdersEquity': 2700000,
                   'totalAssets': 3400000, 'totalDebt': 7800000,
                   'cashAndCashEquivalents': 3560000, 'totalCurrentAssets': 3000000,
                   'totalCurrentLiabilities': 1000000, 'longTermDebt': 5000000,
                   'shortTermDebt': 2800000, 'totalLiabilities': 2700000}]
        filler_bs = [{'date': f'2025-{12-q:02d}-31', 'totalStockholdersEquity': 48000000000,
                      'totalAssets': 500000000000, 'totalDebt': 30000000000,
                      'cashAndCashEquivalents': 60000000000, 'totalCurrentAssets': 200000000000,
                      'totalCurrentLiabilities': 100000000000, 'longTermDebt': 25000000000,
                      'shortTermDebt': 5000000000, 'totalLiabilities': 450000000000}
                     for q in range(1, 8)]
        bs_2y = [{'date': '2024-03-31', 'totalStockholdersEquity': 42000000000,
                  'totalAssets': 480000000000, 'totalDebt': 28000000000,
                  'cashAndCashEquivalents': 55000000000, 'totalCurrentAssets': 190000000000,
                  'totalCurrentLiabilities': 95000000000, 'longTermDebt': 23000000000,
                  'shortTermDebt': 5000000000, 'totalLiabilities': 430000000000}]
        balance = bs_now + filler_bs + bs_2y
        cf_all = [{'date': x['date'], 'operatingCashFlow': 1400000000, 'capitalExpenditure': -150000000,
                   'freeCashFlow': 1250000000, 'dividendsPaid': -200000000, 'commonStockRepurchased': -500000000,
                   'depreciationAndAmortization': 200000000, 'stockBasedCompensation': 80000000}
                  for x in income]

        raw = {'balance_sheet': balance, 'income_statement': income, 'cash_flow': cf_all}

        # This should NOT raise TypeError
        trends = extract_quarterly_trends(raw)

        # roe_change_2yr for index 0 should be None (roe is None for Q0, roe_2y is a float)
        assert 'roe_change_2yr' in trends
        assert trends['roe_change_2yr'][0] is None
