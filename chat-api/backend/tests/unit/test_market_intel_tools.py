"""
Unit tests for Market Intelligence tool executor.

Tests all 9 tools with mocked DynamoDB responses.
"""

import json
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


def _mock_metrics_item(ticker, operating_margin=20.0, fcf_margin=15.0,
                        revenue=100e9, de_ratio=1.0, eps_surprise=5.0,
                        div_yield=1.5):
    """Create a mock metrics-history item."""
    return {
        'ticker': ticker,
        'fiscal_date': '2025-12-31',
        'fiscal_quarter': 'Q4',
        'revenue_profit': {
            'revenue': Decimal(str(revenue)),
            'net_income': Decimal(str(revenue * 0.15)),
            'operating_margin': Decimal(str(operating_margin)),
            'gross_margin': Decimal(str(operating_margin + 15)),
            'net_margin': Decimal(str(operating_margin - 5)),
            'revenue_growth_yoy': Decimal('12.0'),
            'roe': Decimal('30.0'),
            'eps': Decimal('5.00'),
        },
        'cashflow': {
            'fcf_margin': Decimal(str(fcf_margin)),
            'free_cash_flow': Decimal(str(revenue * fcf_margin / 100)),
            'fcf_payout_ratio': Decimal('25.0'),
        },
        'debt_leverage': {
            'debt_to_equity': Decimal(str(de_ratio)),
            'current_ratio': Decimal('1.5'),
        },
        'valuation': {
            'roic': Decimal('20.0'),
            'roa': Decimal('10.0'),
        },
        'earnings_events': {
            'eps_surprise_pct': Decimal(str(eps_surprise)),
            'eps_beat': eps_surprise > 0,
            'eps_actual': Decimal('5.25'),
            'eps_estimated': Decimal('5.00'),
            'earnings_date': '2026-01-30',
        },
        'dividend': {
            'dividend_yield': Decimal(str(div_yield)),
            'dps': Decimal('0.50'),
        } if div_yield > 0 else {},
        'earnings_quality': {},
        'dilution': {},
        'balance_sheet': {},
    }


def _mock_sector_aggregate(sector, company_count=50):
    """Create a mock sp500-aggregates SECTOR item."""
    return {
        'aggregate_type': 'SECTOR',
        'aggregate_key': sector,
        'company_count': company_count,
        'data_coverage': company_count,
        'metrics': {
            'operating_margin': {'median': Decimal('22.0'), 'p25': Decimal('15.0'), 'p75': Decimal('30.0'), 'count': company_count},
            'fcf_margin': {'median': Decimal('18.0'), 'p25': Decimal('10.0'), 'p75': Decimal('25.0'), 'count': company_count},
            'debt_to_equity': {'median': Decimal('0.8'), 'count': company_count},
        },
        'earnings_summary': {
            'median_eps_surprise_pct': Decimal('3.5'),
            'pct_beat_eps': Decimal('70.0'),
            'companies_with_earnings': 45,
        },
        'dividend_summary': {
            'median_yield': Decimal('1.2'),
            'pct_payers': Decimal('65.0'),
            'dividend_payers': 32,
        },
        'top_companies': {
            'by_revenue': [{'ticker': 'AAPL', 'name': 'Apple', 'revenue': 400e9}],
        },
        'totals': {'revenue': Decimal('5000000000000'), 'net_income': Decimal('500000000000')},
        'computed_at': '2026-03-21T12:00:00',
    }


class TestExecuteTool:
    def test_unknown_tool(self):
        from utils.market_intel_tools import execute_tool
        result = execute_tool("nonexistentTool", {})
        assert result['success'] is False
        assert 'Unknown tool' in result['error']

    def test_routes_to_correct_handler(self):
        from utils.market_intel_tools import execute_tool
        with patch('utils.market_intel_tools._get_index_snapshot') as mock:
            mock.return_value = {"success": True}
            result = execute_tool("getIndexSnapshot", {})
            mock.assert_called_once()


class TestResolveMetric:
    def test_known_metric(self):
        from utils.market_intel_tools import _resolve_metric
        assert _resolve_metric('operating_margin') == ('revenue_profit', 'operating_margin')
        assert _resolve_metric('fcf_margin') == ('cashflow', 'fcf_margin')
        assert _resolve_metric('debt_to_equity') == ('debt_leverage', 'debt_to_equity')

    def test_dotted_format(self):
        from utils.market_intel_tools import _resolve_metric
        assert _resolve_metric('revenue_profit.revenue') == ('revenue_profit', 'revenue')

    def test_unknown_metric(self):
        from utils.market_intel_tools import _resolve_metric
        assert _resolve_metric('nonexistent') is None


class TestScreenStocks:
    @patch('utils.market_intel_tools._get_latest_per_ticker')
    def test_screen_by_margin(self, mock_latest):
        mock_latest.return_value = {
            'AAPL': _mock_metrics_item('AAPL', operating_margin=35),
            'MSFT': _mock_metrics_item('MSFT', operating_margin=45),
            'F': _mock_metrics_item('F', operating_margin=5),
        }

        from utils.market_intel_tools import _screen_stocks
        result = _screen_stocks({
            'metric': 'operating_margin',
            'operator': '>',
            'value': 30,
        })

        assert result['success'] is True
        assert result['total_matches'] == 2
        tickers = [c['ticker'] for c in result['companies']]
        assert 'AAPL' in tickers
        assert 'MSFT' in tickers
        assert 'F' not in tickers

    def test_missing_params(self):
        from utils.market_intel_tools import _screen_stocks
        result = _screen_stocks({})
        assert result['success'] is False


class TestGetSectorOverview:
    def test_single_sector(self):
        from utils.market_intel_tools import _get_sector_overview

        mock_item = _mock_sector_aggregate('Technology')
        with patch.object(
            __import__('utils.market_intel_tools', fromlist=['aggregates_table']).aggregates_table,
            'get_item',
            return_value={'Item': mock_item}
        ):
            result = _get_sector_overview({'sector': 'Technology'})

        assert result['success'] is True
        assert 'sector' in result

    def test_sector_not_found(self):
        from utils.market_intel_tools import _get_sector_overview
        import utils.market_intel_tools as mod

        mod.aggregates_table = MagicMock()
        mod.aggregates_table.get_item.return_value = {}

        result = _get_sector_overview({'sector': 'Nonexistent'})
        assert result['success'] is False


class TestGetTopCompanies:
    @patch('utils.market_intel_tools._get_latest_per_ticker')
    def test_top_by_fcf_margin(self, mock_latest):
        mock_latest.return_value = {
            'AAPL': _mock_metrics_item('AAPL', fcf_margin=35),
            'MSFT': _mock_metrics_item('MSFT', fcf_margin=30),
            'NVDA': _mock_metrics_item('NVDA', fcf_margin=50),
        }

        from utils.market_intel_tools import _get_top_companies
        result = _get_top_companies({'metric': 'fcf_margin', 'n': 2})

        assert result['success'] is True
        assert result['showing'] == 2
        assert result['rankings'][0]['ticker'] == 'NVDA'  # Highest


class TestGetCompanyProfile:
    def test_company_found(self):
        import utils.market_intel_tools as mod

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': [_mock_metrics_item('AAPL')]}

        mock_agg = MagicMock()
        mock_agg.get_item.return_value = {'Item': _mock_sector_aggregate('Technology')}

        mod.metrics_table = mock_metrics
        mod.aggregates_table = mock_agg

        result = mod._get_company_profile({'ticker': 'AAPL'})
        assert result['success'] is True
        assert result['profile']['ticker'] == 'AAPL'
        assert 'sector_context' in result['profile']

    def test_company_not_found(self):
        import utils.market_intel_tools as mod
        mod.metrics_table = MagicMock()
        mod.metrics_table.query.return_value = {'Items': []}

        result = mod._get_company_profile({'ticker': 'ZZZZ'})
        assert result['success'] is False


class TestCompareCompanies:
    @patch('utils.market_intel_tools._get_latest_per_ticker')
    def test_compare_two(self, mock_latest):
        mock_latest.return_value = {
            'AAPL': _mock_metrics_item('AAPL'),
            'MSFT': _mock_metrics_item('MSFT'),
        }

        from utils.market_intel_tools import _compare_companies
        result = _compare_companies({'tickers': ['AAPL', 'MSFT']})

        assert result['success'] is True
        assert len(result['tickers_compared']) == 2

    def test_too_few_tickers(self):
        from utils.market_intel_tools import _compare_companies
        result = _compare_companies({'tickers': ['AAPL']})
        assert result['success'] is False


class TestGetMetricTrend:
    def test_trend_returns_quarters(self):
        import utils.market_intel_tools as mod

        items = [
            {**_mock_metrics_item('AAPL'), 'fiscal_date': f'2025-{m:02d}-28', 'fiscal_quarter': f'Q{i+1}'}
            for i, m in enumerate([3, 6, 9, 12])
        ]
        mod.metrics_table = MagicMock()
        mod.metrics_table.query.return_value = {'Items': items}

        result = mod._get_metric_trend({'ticker': 'AAPL', 'metric': 'operating_margin'})

        assert result['success'] is True
        assert result['quarters'] == 4
        assert len(result['trend']) == 4

    def test_missing_ticker(self):
        from utils.market_intel_tools import _get_metric_trend
        result = _get_metric_trend({'metric': 'operating_margin'})
        assert result['success'] is False


class TestGetEarningsSurprises:
    @patch('utils.market_intel_tools._get_latest_per_ticker')
    def test_best_surprises(self, mock_latest):
        mock_latest.return_value = {
            'AAPL': _mock_metrics_item('AAPL', eps_surprise=10.0),
            'MSFT': _mock_metrics_item('MSFT', eps_surprise=5.0),
            'F': _mock_metrics_item('F', eps_surprise=-3.0),
        }

        from utils.market_intel_tools import _get_earnings_surprises
        result = _get_earnings_surprises({'sort': 'best', 'n': 2})

        assert result['success'] is True
        assert result['showing'] == 2
        assert result['surprises'][0]['ticker'] == 'AAPL'  # Best beat

    @patch('utils.market_intel_tools._get_latest_per_ticker')
    def test_worst_surprises(self, mock_latest):
        mock_latest.return_value = {
            'AAPL': _mock_metrics_item('AAPL', eps_surprise=10.0),
            'F': _mock_metrics_item('F', eps_surprise=-3.0),
        }

        from utils.market_intel_tools import _get_earnings_surprises
        result = _get_earnings_surprises({'sort': 'worst', 'n': 1})

        assert result['surprises'][0]['ticker'] == 'F'  # Worst miss


class TestCompareSectors:
    def test_compare_two_sectors(self):
        import utils.market_intel_tools as mod

        mock_agg = MagicMock()
        mock_agg.get_item.side_effect = [
            {'Item': _mock_sector_aggregate('Technology')},
            {'Item': _mock_sector_aggregate('Healthcare')},
        ]
        mod.aggregates_table = mock_agg

        result = mod._compare_sectors({'sectors': ['Technology', 'Healthcare']})

        assert result['success'] is True
        assert len(result['sectors_compared']) == 2

    def test_too_few_sectors(self):
        from utils.market_intel_tools import _compare_sectors
        result = _compare_sectors({'sectors': ['Technology']})
        assert result['success'] is False


def _mock_historical_valuation_item(
    ticker,
    fiscal_date,
    market_valuation=None,
    balance_sheet=None,
    valuation=None,
    revenue_profit=None,
):
    """Create a mock metrics-history item tailored for historical valuation tests.

    Only the sub-dicts needed by _get_historical_valuation are populated.
    Numeric values are wrapped in Decimal to mimic DynamoDB responses.
    """
    def _to_decimal_dict(d):
        if not d:
            return {}
        out = {}
        for k, v in d.items():
            if v is None:
                continue
            out[k] = Decimal(str(v))
        return out

    return {
        'ticker': ticker,
        'fiscal_date': fiscal_date,
        'fiscal_quarter': 'Q1',
        'fiscal_year': 2024,
        'market_valuation': _to_decimal_dict(market_valuation),
        'balance_sheet': _to_decimal_dict(balance_sheet),
        'valuation': _to_decimal_dict(valuation),
        'revenue_profit': _to_decimal_dict(revenue_profit),
    }


class TestGetHistoricalValuation:
    def test_happy_path_returns_all_nine_metrics(self):
        import utils.market_intel_tools as mod

        pe_values = [20, 22, 24, 26, 28, 30, 32, 34, 36, 38, 40, 42]
        ev_values = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]
        ey_values = [5.0] * 12
        fcfy_values = [4.0] * 12  # price_to_fcf = 25.0 all quarters
        roic_values = [12, 12.5, 13, 13.5, 14, 14.5, 15, 15.5, 16, 16.5, 17, 17.5]
        roe_values = [25, 25, 26, 26, 27, 27, 28, 28, 29, 29, 30, 30]
        roa_values = [8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13]
        market_caps = [1000 + 50 * i for i in range(12)]
        equities = [500] * 12

        items = []
        for i in range(12):
            items.append(_mock_historical_valuation_item(
                'AAPL',
                fiscal_date=f'2023-{(i % 12) + 1:02d}-28',
                market_valuation={
                    'pe_ratio': pe_values[i],
                    'ev_to_ebitda': ev_values[i],
                    'earnings_yield': ey_values[i],
                    'fcf_yield': fcfy_values[i],
                    'market_cap': market_caps[i],
                },
                balance_sheet={'total_equity': equities[i]},
                valuation={'roic': roic_values[i], 'roa': roa_values[i]},
                revenue_profit={'roe': roe_values[i]},
            ))

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': items}

        mock_agg = MagicMock()
        mock_agg.get_item.return_value = {
            'Item': {
                'aggregate_type': 'SECTOR',
                'aggregate_key': 'Technology',
                'company_count': Decimal('75'),
                'metrics': {
                    'pe_ratio': {'median': Decimal('25.0')},
                    'pb_ratio': {'median': Decimal('4.5')},
                    'ev_to_ebitda': {'median': Decimal('15.0')},
                },
            }
        }

        mod.metrics_table = mock_metrics
        mod.aggregates_table = mock_agg

        result = mod._get_historical_valuation({'ticker': 'AAPL'})

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['name'] == 'Apple Inc.'
        assert result['sector'] == 'Technology'
        assert result['quarters_analyzed'] == 12

        expected_keys = {
            'pe_ratio', 'pb_ratio', 'ev_to_ebitda', 'price_to_fcf',
            'earnings_yield', 'fcf_yield', 'roic', 'roe', 'roa',
        }
        assert set(result['metrics'].keys()) == expected_keys

        for key in expected_keys:
            metric = result['metrics'][key]
            assert 'label' in metric
            assert 'plain_english' in metric
            assert 'direction' in metric
            assert 'current' in metric
            assert 'assessment' in metric
            assert 'verdict' in metric

        pe = result['metrics']['pe_ratio']
        assert pe['current'] == 42
        assert pe['assessment'] == 'expensive'
        assert pe['percentile'] >= 75
        assert 'more expensive than' in pe['verdict'].lower()

        assert result['sector_context']['company_count'] == 75

    def test_polarity_inversion_for_earnings_yield(self):
        import utils.market_intel_tools as mod

        ey_values = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 10.0]
        pe_values = [25.0] * 8  # constant → fair

        items = []
        for i in range(8):
            items.append(_mock_historical_valuation_item(
                'AAPL',
                fiscal_date=f'2023-{i + 1:02d}-28',
                market_valuation={
                    'pe_ratio': pe_values[i],
                    'earnings_yield': ey_values[i],
                    'fcf_yield': 5.0,
                    'ev_to_ebitda': 15.0,
                    'market_cap': 1000,
                },
                balance_sheet={'total_equity': 500},
                valuation={'roic': 15.0, 'roa': 10.0},
                revenue_profit={'roe': 25.0},
            ))

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': items}
        mod.metrics_table = mock_metrics
        mod.aggregates_table = MagicMock()
        mod.aggregates_table.get_item.return_value = {}

        result = mod._get_historical_valuation({'ticker': 'AAPL'})

        assert result['success'] is True
        ey = result['metrics']['earnings_yield']
        assert ey['direction'] == 'higher_is_cheaper'
        assert ey['assessment'] == 'cheap'
        # higher_is_cheaper verdicts use "higher than X%" language, not "cheaper than",
        # so retail investors aren't confused by "a high ROIC is cheap".
        assert 'higher than' in ey['verdict'].lower()

    def test_insufficient_history_for_sparse_market_valuation(self):
        import utils.market_intel_tools as mod

        items = []
        for i in range(10):
            has_mv = i >= 8  # only last 2 quarters have market_valuation
            mv = {
                'pe_ratio': 30.0,
                'earnings_yield': 3.3,
                'fcf_yield': 5.0,
                'ev_to_ebitda': 15.0,
                'market_cap': 1000,
            } if has_mv else {}

            items.append(_mock_historical_valuation_item(
                'AAPL',
                fiscal_date=f'2023-{i + 1:02d}-28',
                market_valuation=mv,
                balance_sheet={'total_equity': 500} if has_mv else {},
                valuation={'roic': 15.0 + i * 0.1, 'roa': 10.0 + i * 0.1},
                revenue_profit={'roe': 25.0 + i * 0.1},
            ))

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': items}
        mod.metrics_table = mock_metrics
        mod.aggregates_table = MagicMock()
        mod.aggregates_table.get_item.return_value = {}

        result = mod._get_historical_valuation({'ticker': 'AAPL'})

        assert result['success'] is True
        pe = result['metrics']['pe_ratio']
        assert pe['assessment'] == 'insufficient_history'
        assert 'not enough history' in pe['verdict'].lower()
        assert pe['current'] is not None

        roic = result['metrics']['roic']
        assert roic['assessment'] != 'insufficient_history'

    def test_missing_ticker_returns_error(self):
        from utils.market_intel_tools import _get_historical_valuation
        result = _get_historical_valuation({})
        assert result['success'] is False
        assert 'ticker' in result['error']

    def test_ticker_with_no_data_returns_error(self):
        import utils.market_intel_tools as mod

        mod.metrics_table = MagicMock()
        mod.metrics_table.query.return_value = {'Items': []}

        result = mod._get_historical_valuation({'ticker': 'ZZZZ'})
        assert result['success'] is False
        assert ('No data' in result['error']) or ('ZZZZ' in result['error'])

    def test_pb_ratio_derived_from_market_cap_and_total_equity(self):
        import utils.market_intel_tools as mod

        market_caps = [100, 110, 120, 130, 140, 150]
        equities = [50, 50, 50, 50, 0, 50]  # one zero to test graceful handling

        items = []
        for i in range(6):
            items.append(_mock_historical_valuation_item(
                'AAPL',
                fiscal_date=f'2023-{i + 1:02d}-28',
                market_valuation={
                    'pe_ratio': 25.0,
                    'earnings_yield': 4.0,
                    'fcf_yield': 5.0,
                    'ev_to_ebitda': 15.0,
                    'market_cap': market_caps[i],
                },
                balance_sheet={'total_equity': equities[i]},
                valuation={'roic': 15.0, 'roa': 10.0},
                revenue_profit={'roe': 25.0},
            ))

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': items}
        mod.metrics_table = mock_metrics
        mod.aggregates_table = MagicMock()
        mod.aggregates_table.get_item.return_value = {}

        result = mod._get_historical_valuation({'ticker': 'AAPL'})

        assert result['success'] is True
        pb = result['metrics']['pb_ratio']
        # The last quarter: market_cap=150, total_equity=50 → pb=3.0
        assert pb['current'] == 3.0
        assert 'percentile' in pb
        assert 'assessment' in pb
        # One quarter had total_equity=0 → None → skipped.
        # Remaining 5 valid pb values: [2.0, 2.2, 2.4, 2.6, 3.0]
        assert pb['quarters_available'] == 5

    def test_price_to_fcf_derived_from_fcf_yield(self):
        import utils.market_intel_tools as mod

        fcf_yields = [5.0, 4.0, 2.5, 2.0, 1.25, 1.0]

        items = []
        for i in range(6):
            items.append(_mock_historical_valuation_item(
                'AAPL',
                fiscal_date=f'2023-{i + 1:02d}-28',
                market_valuation={
                    'pe_ratio': 25.0,
                    'earnings_yield': 4.0,
                    'fcf_yield': fcf_yields[i],
                    'ev_to_ebitda': 15.0,
                    'market_cap': 1000,
                },
                balance_sheet={'total_equity': 500},
                valuation={'roic': 15.0, 'roa': 10.0},
                revenue_profit={'roe': 25.0},
            ))

        mock_metrics = MagicMock()
        mock_metrics.query.return_value = {'Items': items}
        mod.metrics_table = mock_metrics
        mod.aggregates_table = MagicMock()
        mod.aggregates_table.get_item.return_value = {}

        result = mod._get_historical_valuation({'ticker': 'AAPL'})

        assert result['success'] is True
        p_fcf = result['metrics']['price_to_fcf']
        assert p_fcf['direction'] == 'lower_is_cheaper'
        # Latest fcf_yield = 1.0 → price_to_fcf = 100.0
        assert p_fcf['current'] == 100.0
        # 100.0 is the max → expensive assessment
        assert p_fcf['assessment'] == 'expensive'
