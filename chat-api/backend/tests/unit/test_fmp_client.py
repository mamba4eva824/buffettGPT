"""
Unit tests for utils.fmp_client.

Focused on the force_refresh kwarg — confirms we can bypass the DynamoDB cache
read while still writing fresh data to cache for subsequent readers.
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ['ENVIRONMENT'] = 'test'
os.environ['FMP_SECRET_NAME'] = 'buffett-test-fmp'


class TestGetFinancialDataForceRefresh:
    """Test the force_refresh kwarg on get_financial_data."""

    @patch('utils.fmp_client.store_cached_data')
    @patch('utils.fmp_client.verify_cache_readable')
    @patch('utils.fmp_client.fetch_from_fmp')
    @patch('utils.fmp_client.get_cached_data')
    def test_force_refresh_skips_cache(self, mock_get_cache, mock_fetch, mock_verify, mock_store):
        """force_refresh=True skips cache read but still writes fresh data to cache."""
        # Arrange: cache would return something, but force_refresh=True should skip it
        mock_get_cache.return_value = {'raw_financials': {'balance_sheet': [{'date': '2025-12-31'}]}}
        mock_fetch.return_value = {
            'balance_sheet': [{'date': '2026-03-31'}],
            'income_statement': [{'date': '2026-03-31'}],
            'cash_flow': [{'date': '2026-03-31'}],
            'reported_currency': 'USD',
        }

        # Act
        from utils.fmp_client import get_financial_data
        result = get_financial_data('AAPL', fiscal_year=2026, force_refresh=True)

        # Assert
        mock_get_cache.assert_not_called()          # cache read skipped
        mock_fetch.assert_called_once_with('AAPL')  # fresh FMP call made
        mock_store.assert_called_once()             # fresh response still cached for subsequent readers
        assert result['raw_financials']['balance_sheet'][0]['date'] == '2026-03-31'
