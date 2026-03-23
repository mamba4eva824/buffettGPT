"""
Unit tests for the S&P 500 Aggregator Lambda.

Tests sector aggregation, index computation, earnings/dividend summaries,
and percentile calculations.
"""

import os
import sys
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ['ENVIRONMENT'] = 'test'
os.environ['METRICS_HISTORY_CACHE_TABLE'] = 'metrics-history-test'
os.environ['SP500_AGGREGATES_TABLE'] = 'buffett-test-sp500-aggregates'


def _make_ticker_data(ticker, sector, revenue, margin, fcf_margin,
                      de_ratio, roe, eps_surprise=None, eps_beat=None,
                      div_yield=None, payout=None):
    """Helper to create mock ticker data matching DynamoDB schema."""
    data = {
        'ticker': ticker,
        'fiscal_date': '2025-12-31',
        'fiscal_quarter': 'Q4',
        'revenue_profit': {
            'revenue': Decimal(str(revenue)),
            'net_income': Decimal(str(revenue * margin / 100)),
            'gross_margin': Decimal(str(margin + 10)),
            'operating_margin': Decimal(str(margin + 5)),
            'net_margin': Decimal(str(margin)),
            'revenue_growth_yoy': Decimal('15.0'),
            'roe': Decimal(str(roe)),
        },
        'cashflow': {
            'fcf_margin': Decimal(str(fcf_margin)),
            'capex_intensity': Decimal('5.0'),
            'fcf_payout_ratio': Decimal(str(payout)) if payout else Decimal('0'),
        },
        'debt_leverage': {
            'debt_to_equity': Decimal(str(de_ratio)),
            'current_ratio': Decimal('1.5'),
            'interest_coverage': Decimal('10.0'),
        },
        'valuation': {
            'roic': Decimal('20.0'),
            'roa': Decimal('10.0'),
            'asset_turnover': Decimal('0.8'),
        },
        'earnings_quality': {
            'sbc_to_revenue_pct': Decimal('3.0'),
        },
        'balance_sheet': {},
        'dilution': {},
    }
    if eps_surprise is not None:
        data['earnings_events'] = {
            'eps_surprise_pct': Decimal(str(eps_surprise)),
            'eps_beat': eps_beat,
            'eps_actual': Decimal('2.50'),
            'eps_estimated': Decimal('2.40'),
        }
    if div_yield is not None:
        data['dividend'] = {
            'dividend_yield': Decimal(str(div_yield)),
            'dps': Decimal('0.50'),
        }
    return data


# Sample data: 3 tech companies, 2 healthcare
TECH_DATA = [
    _make_ticker_data('AAPL', 'Technology', 400e9, 30, 35, 1.0, 150,
                      eps_surprise=3.9, eps_beat=True, div_yield=0.5, payout=15),
    _make_ticker_data('MSFT', 'Technology', 250e9, 40, 30, 0.5, 40,
                      eps_surprise=5.0, eps_beat=True, div_yield=0.8, payout=25),
    _make_ticker_data('NVDA', 'Technology', 100e9, 55, 50, 0.3, 80,
                      eps_surprise=-2.0, eps_beat=False),
]

HEALTH_DATA = [
    _make_ticker_data('JNJ', 'Healthcare', 100e9, 20, 15, 0.8, 25,
                      eps_surprise=1.0, eps_beat=True, div_yield=2.5, payout=50),
    _make_ticker_data('LLY', 'Healthcare', 50e9, 25, 20, 1.2, 60,
                      eps_surprise=8.0, eps_beat=True, div_yield=1.0, payout=30),
]


class TestComputePercentiles:
    def test_basic_percentiles(self):
        from src.handlers.sp500_aggregator import _compute_percentiles
        result = _compute_percentiles([10, 20, 30, 40, 50])
        assert result['median'] == 30
        assert result['count'] == 5

    def test_empty_list(self):
        from src.handlers.sp500_aggregator import _compute_percentiles
        result = _compute_percentiles([])
        assert result['median'] is None
        assert result['count'] == 0

    def test_single_value(self):
        from src.handlers.sp500_aggregator import _compute_percentiles
        result = _compute_percentiles([42.5])
        assert result['median'] == 42.5
        assert result['count'] == 1


class TestExtractMetric:
    def test_extract_existing_metric(self):
        from src.handlers.sp500_aggregator import _extract_metric
        data = {'revenue_profit': {'revenue': Decimal('100000')}}
        assert _extract_metric(data, 'revenue_profit', 'revenue') == 100000.0

    def test_extract_missing_category(self):
        from src.handlers.sp500_aggregator import _extract_metric
        assert _extract_metric({}, 'revenue_profit', 'revenue') is None

    def test_extract_missing_metric(self):
        from src.handlers.sp500_aggregator import _extract_metric
        data = {'revenue_profit': {'revenue': Decimal('100')}}
        assert _extract_metric(data, 'revenue_profit', 'nonexistent') is None


class TestSectorAggregate:
    def test_tech_sector_metrics(self):
        from src.handlers.sp500_aggregator import _compute_sector_aggregate

        # Add required fields
        for d in TECH_DATA:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Technology'

        result = _compute_sector_aggregate('Technology', TECH_DATA)

        assert result['aggregate_type'] == 'SECTOR'
        assert result['aggregate_key'] == 'Technology'
        assert result['company_count'] == 3
        assert 'metrics' in result
        assert 'net_margin' in result['metrics']
        assert result['metrics']['net_margin']['count'] == 3

    def test_top_companies_by_revenue(self):
        from src.handlers.sp500_aggregator import _compute_sector_aggregate

        for d in TECH_DATA:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Technology'

        result = _compute_sector_aggregate('Technology', TECH_DATA)
        top_rev = result['top_companies']['by_revenue']

        assert len(top_rev) <= 5
        assert top_rev[0]['ticker'] == 'AAPL'  # Highest revenue

    def test_earnings_summary(self):
        from src.handlers.sp500_aggregator import _compute_sector_aggregate

        for d in TECH_DATA:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Technology'

        result = _compute_sector_aggregate('Technology', TECH_DATA)
        es = result['earnings_summary']

        assert es['companies_with_earnings'] == 3
        assert es['pct_beat_eps'] == pytest.approx(66.7, abs=0.1)  # 2/3 beat
        assert es['median_eps_surprise_pct'] is not None

    def test_dividend_summary(self):
        from src.handlers.sp500_aggregator import _compute_sector_aggregate

        for d in TECH_DATA:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Technology'

        result = _compute_sector_aggregate('Technology', TECH_DATA)
        ds = result['dividend_summary']

        assert ds['dividend_payers'] == 2  # AAPL + MSFT have dividends, NVDA doesn't
        assert ds['pct_payers'] == pytest.approx(66.7, abs=0.1)
        assert ds['median_yield'] is not None


class TestIndexAggregate:
    def test_index_covers_all_tickers(self):
        from src.handlers.sp500_aggregator import (
            _compute_sector_aggregate, _compute_index_aggregate
        )

        all_data = TECH_DATA + HEALTH_DATA
        for d in all_data:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Test'

        tech_agg = _compute_sector_aggregate('Technology', TECH_DATA)
        health_agg = _compute_sector_aggregate('Healthcare', HEALTH_DATA)

        latest_dict = {d['ticker']: d for d in all_data}
        result = _compute_index_aggregate(latest_dict, [tech_agg, health_agg])

        assert result['aggregate_type'] == 'INDEX'
        assert result['aggregate_key'] == 'OVERALL'
        assert result['company_count'] == 5
        assert 'sector_weights' in result
        assert 'Technology' in result['sector_weights']
        assert 'Healthcare' in result['sector_weights']

    def test_sector_weights_sum_to_100(self):
        from src.handlers.sp500_aggregator import (
            _compute_sector_aggregate, _compute_index_aggregate
        )

        all_data = TECH_DATA + HEALTH_DATA
        for d in all_data:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Test'

        tech_agg = _compute_sector_aggregate('Technology', TECH_DATA)
        health_agg = _compute_sector_aggregate('Healthcare', HEALTH_DATA)

        latest_dict = {d['ticker']: d for d in all_data}
        result = _compute_index_aggregate(latest_dict, [tech_agg, health_agg])

        total_weight = sum(
            s['revenue_weight_pct'] for s in result['sector_weights'].values()
        )
        assert total_weight == pytest.approx(100.0, abs=0.5)

    def test_concentration_top_10(self):
        from src.handlers.sp500_aggregator import (
            _compute_sector_aggregate, _compute_index_aggregate
        )

        all_data = TECH_DATA + HEALTH_DATA
        for d in all_data:
            d['_ticker'] = d['ticker']
            d['_company_name'] = d['ticker']
            d['_industry'] = 'Test'

        tech_agg = _compute_sector_aggregate('Technology', TECH_DATA)
        health_agg = _compute_sector_aggregate('Healthcare', HEALTH_DATA)

        latest_dict = {d['ticker']: d for d in all_data}
        result = _compute_index_aggregate(latest_dict, [tech_agg, health_agg])

        assert 'concentration' in result
        assert len(result['concentration']['top_10_tickers']) <= 10
        # With only 5 companies, top 10 = 100%
        assert result['concentration']['top_10_revenue_pct'] == 100.0


class TestProcessScanPage:
    def test_keeps_latest_per_ticker(self):
        from src.handlers.sp500_aggregator import _process_scan_page

        latest = {}
        items = [
            {'ticker': 'AAPL', 'fiscal_date': '2025-06-28'},
            {'ticker': 'AAPL', 'fiscal_date': '2025-12-27'},
            {'ticker': 'AAPL', 'fiscal_date': '2025-09-27'},
        ]
        _process_scan_page(items, latest)

        assert latest['AAPL']['fiscal_date'] == '2025-12-27'

    def test_handles_multiple_tickers(self):
        from src.handlers.sp500_aggregator import _process_scan_page

        latest = {}
        items = [
            {'ticker': 'AAPL', 'fiscal_date': '2025-12-27'},
            {'ticker': 'MSFT', 'fiscal_date': '2025-12-31'},
        ]
        _process_scan_page(items, latest)

        assert len(latest) == 2
        assert 'AAPL' in latest
        assert 'MSFT' in latest
