"""
Unit tests for the Tool Executor.

Tests the tool functions that replace Bedrock Agent action groups.
Uses moto to mock DynamoDB interactions.
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from botocore.exceptions import ClientError

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['INVESTMENT_REPORTS_TABLE'] = 'investment-reports-v2-test'
os.environ['METRICS_HISTORY_TABLE'] = 'metrics-history-test'


class TestExecuteToolRouting:
    """Tests for execute_tool routing function."""

    def test_routes_to_get_report_section(self):
        """Test routing to getReportSection."""
        with patch('utils.tool_executor.get_report_section') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('getReportSection', {'ticker': 'AAPL', 'section_id': '06_growth'})

            mock_func.assert_called_once_with(ticker='AAPL', section_id='06_growth')
            assert result['success'] is True

    def test_routes_to_get_report_ratings(self):
        """Test routing to getReportRatings."""
        with patch('utils.tool_executor.get_report_ratings') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('getReportRatings', {'ticker': 'MSFT'})

            mock_func.assert_called_once_with(ticker='MSFT')
            assert result['success'] is True

    def test_routes_to_get_metrics_history(self):
        """Test routing to getMetricsHistory."""
        with patch('utils.tool_executor.get_metrics_history') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('getMetricsHistory', {
                'ticker': 'GOOGL',
                'metric_type': 'revenue_profit',
                'quarters': 12
            })

            mock_func.assert_called_once_with(ticker='GOOGL', metric_type='revenue_profit', quarters=12)
            assert result['success'] is True

    def test_routes_to_get_available_reports(self):
        """Test routing to getAvailableReports."""
        with patch('utils.tool_executor.get_available_reports') as mock_func:
            mock_func.return_value = {'success': True, 'count': 5}

            from utils.tool_executor import execute_tool
            result = execute_tool('getAvailableReports', {})

            mock_func.assert_called_once()
            assert result['success'] is True

    def test_unknown_tool_error(self):
        """Test error handling for unknown tool names."""
        from utils.tool_executor import execute_tool
        result = execute_tool('unknownTool', {'param': 'value'})

        assert result['success'] is False
        assert 'Unknown tool' in result['error']
        assert 'unknownTool' in result['error']

    def test_handles_exception_in_tool(self):
        """Test error handling when tool raises exception."""
        with patch('utils.tool_executor.get_report_section') as mock_func:
            mock_func.side_effect = Exception('Database connection failed')

            from utils.tool_executor import execute_tool
            result = execute_tool('getReportSection', {'ticker': 'AAPL', 'section_id': '06_growth'})

            assert result['success'] is False
            assert 'Database connection failed' in result['error']


class TestGetReportSection:
    """Tests for get_report_section function."""

    @pytest.fixture
    def mock_reports_table(self):
        """Create a mock DynamoDB table for reports."""
        with patch('utils.tool_executor.reports_table') as mock_table:
            yield mock_table

    def test_get_report_section_success(self, mock_reports_table):
        """Test successful section retrieval."""
        mock_reports_table.get_item.return_value = {
            'Item': {
                'ticker': 'AAPL',
                'section_id': '06_growth',
                'title': 'Growth Analysis',
                'content': 'Apple has shown strong revenue growth...',
                'part': 2,
                'word_count': 450
            }
        }

        from utils.tool_executor import get_report_section
        result = get_report_section('AAPL', '06_growth')

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['section_id'] == '06_growth'
        assert result['title'] == 'Growth Analysis'
        assert result['content'] == 'Apple has shown strong revenue growth...'
        assert result['part'] == 2
        assert result['word_count'] == 450

    def test_get_report_section_executive_summary(self, mock_reports_table):
        """Test special handling for executive summary section."""
        mock_reports_table.get_item.return_value = {
            'Item': {
                'ticker': 'AAPL',
                'section_id': '00_executive',
                'executive_summary': {
                    'content': 'Apple is a strong buy...',
                    'word_count': 300
                }
            }
        }

        from utils.tool_executor import get_report_section
        result = get_report_section('AAPL', '01_executive_summary')

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['section_id'] == '01_executive_summary'
        assert result['title'] == 'Executive Summary'
        assert result['content'] == 'Apple is a strong buy...'
        assert result['word_count'] == 300

        # Verify it queried with '00_executive'
        call_args = mock_reports_table.get_item.call_args
        assert call_args[1]['Key']['section_id'] == '00_executive'

    def test_get_report_section_not_found(self, mock_reports_table):
        """Test section not found response."""
        mock_reports_table.get_item.return_value = {}

        from utils.tool_executor import get_report_section
        result = get_report_section('AAPL', '99_invalid')

        assert result['success'] is False
        assert 'not found' in result['error']
        assert 'AAPL' in result['error']

    def test_get_report_section_missing_ticker(self, mock_reports_table):
        """Test error when ticker is missing."""
        from utils.tool_executor import get_report_section
        result = get_report_section('', '06_growth')

        assert result['success'] is False
        assert 'ticker is required' in result['error']

    def test_get_report_section_missing_section_id(self, mock_reports_table):
        """Test error when section_id is missing."""
        from utils.tool_executor import get_report_section
        result = get_report_section('AAPL', '')

        assert result['success'] is False
        assert 'section_id is required' in result['error']

    def test_get_report_section_normalizes_ticker(self, mock_reports_table):
        """Test ticker is normalized to uppercase."""
        mock_reports_table.get_item.return_value = {
            'Item': {'ticker': 'AAPL', 'section_id': '06_growth', 'title': 'Test', 'content': 'Test'}
        }

        from utils.tool_executor import get_report_section
        result = get_report_section('  aapl  ', '06_growth')

        assert result['success'] is True
        call_args = mock_reports_table.get_item.call_args
        assert call_args[1]['Key']['ticker'] == 'AAPL'

    def test_get_report_section_database_error(self, mock_reports_table):
        """Test handling of DynamoDB errors."""
        mock_reports_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'Test error'}},
            'GetItem'
        )

        from utils.tool_executor import get_report_section
        result = get_report_section('AAPL', '06_growth')

        assert result['success'] is False
        assert 'Database error' in result['error']


class TestGetReportRatings:
    """Tests for get_report_ratings function."""

    @pytest.fixture
    def mock_reports_table(self):
        """Create a mock DynamoDB table for reports."""
        with patch('utils.tool_executor.reports_table') as mock_table:
            yield mock_table

    def test_get_report_ratings_success(self, mock_reports_table):
        """Test successful ratings retrieval."""
        mock_reports_table.get_item.return_value = {
            'Item': {
                'ticker': 'AAPL',
                'section_id': '00_executive',
                'company_name': 'Apple Inc.',
                'ratings': {
                    'growth': {'rating': 'Strong', 'confidence': 0.85},
                    'debt': {'rating': 'Healthy', 'confidence': 0.9},
                    'verdict': 'BUY'
                },
                'generated_at': '2026-01-15T10:30:00Z'
            }
        }

        from utils.tool_executor import get_report_ratings
        result = get_report_ratings('AAPL')

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['company_name'] == 'Apple Inc.'
        assert result['ratings']['verdict'] == 'BUY'
        assert result['generated_at'] == '2026-01-15T10:30:00Z'

    def test_get_report_ratings_json_string_format(self, mock_reports_table):
        """Test handling of ratings stored as JSON string."""
        mock_reports_table.get_item.return_value = {
            'Item': {
                'ticker': 'AAPL',
                'section_id': '00_executive',
                'company_name': 'Apple Inc.',
                'ratings': json.dumps({'growth': 'Strong', 'verdict': 'BUY'}),
                'generated_at': '2026-01-15T10:30:00Z'
            }
        }

        from utils.tool_executor import get_report_ratings
        result = get_report_ratings('AAPL')

        assert result['success'] is True
        assert result['ratings']['growth'] == 'Strong'
        assert result['ratings']['verdict'] == 'BUY'

    def test_get_report_ratings_not_found(self, mock_reports_table):
        """Test ratings not found response."""
        mock_reports_table.get_item.return_value = {}

        from utils.tool_executor import get_report_ratings
        result = get_report_ratings('UNKNOWN')

        assert result['success'] is False
        assert 'No ratings found' in result['error']

    def test_get_report_ratings_missing_ratings_field(self, mock_reports_table):
        """Test when item exists but ratings field is missing."""
        mock_reports_table.get_item.return_value = {
            'Item': {
                'ticker': 'AAPL',
                'section_id': '00_executive',
                'company_name': 'Apple Inc.'
                # No 'ratings' field
            }
        }

        from utils.tool_executor import get_report_ratings
        result = get_report_ratings('AAPL')

        assert result['success'] is False
        assert 'No ratings found' in result['error']

    def test_get_report_ratings_missing_ticker(self, mock_reports_table):
        """Test error when ticker is missing."""
        from utils.tool_executor import get_report_ratings
        result = get_report_ratings('')

        assert result['success'] is False
        assert 'ticker is required' in result['error']


class TestGetMetricsHistory:
    """Tests for get_metrics_history function."""

    @pytest.fixture
    def mock_metrics_table(self):
        """Create a mock DynamoDB table for metrics."""
        with patch('utils.tool_executor.metrics_table') as mock_table:
            yield mock_table

    def test_get_metrics_history_all_categories(self, mock_metrics_table):
        """Test retrieving all metric categories."""
        mock_metrics_table.query.return_value = {
            'Items': [
                {
                    'ticker': 'AAPL',
                    'fiscal_date': '2025-12-28',
                    'fiscal_year': 2026,
                    'fiscal_quarter': 'Q1',
                    'revenue_profit': {'revenue': Decimal('100000'), 'net_margin': Decimal('0.25')},
                    'cashflow': {'freeCashFlow': Decimal('25000')},
                    'debt_leverage': {'debt_to_equity': Decimal('1.5')}
                },
                {
                    'ticker': 'AAPL',
                    'fiscal_date': '2025-09-28',
                    'fiscal_year': 2025,
                    'fiscal_quarter': 'Q4',
                    'revenue_profit': {'revenue': Decimal('95000')},
                    'cashflow': {'freeCashFlow': Decimal('23000')}
                }
            ]
        }

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL', 'all', 8)

        assert result['success'] is True
        assert result['ticker'] == 'AAPL'
        assert result['metric_type'] == 'all'
        assert result['quarters_available'] == 2
        assert 'revenue_profit' in result['data']
        assert 'cashflow' in result['data']
        assert 'debt_leverage' in result['data']

    def test_get_metrics_history_single_category(self, mock_metrics_table):
        """Test retrieving a single metric category."""
        mock_metrics_table.query.return_value = {
            'Items': [
                {
                    'ticker': 'AAPL',
                    'fiscal_date': '2025-12-28',
                    'fiscal_year': 2026,
                    'fiscal_quarter': 'Q1',
                    'debt_leverage': {'debt_to_equity': Decimal('1.5'), 'current_ratio': Decimal('1.2')}
                }
            ]
        }

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL', 'debt_leverage', 8)

        assert result['success'] is True
        assert result['metric_type'] == 'debt_leverage'
        assert 'debt_leverage' in result['data']
        assert result['categories_returned'] == ['debt_leverage']
        # Should only include the requested category
        assert len(result['data']) == 1

    def test_get_metrics_history_quarter_clamping_min(self, mock_metrics_table):
        """Test quarters parameter is clamped to minimum of 1."""
        mock_metrics_table.query.return_value = {'Items': []}

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL', 'all', -5)

        # Should query with Limit=1 (clamped from -5)
        call_args = mock_metrics_table.query.call_args
        assert call_args[1]['Limit'] == 1

    def test_get_metrics_history_quarter_clamping_max(self, mock_metrics_table):
        """Test quarters parameter is clamped to maximum of 40."""
        mock_metrics_table.query.return_value = {'Items': []}

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL', 'all', 100)

        # Should query with Limit=40 (clamped from 100)
        call_args = mock_metrics_table.query.call_args
        assert call_args[1]['Limit'] == 40

    def test_get_metrics_history_invalid_metric_type(self, mock_metrics_table):
        """Test error for invalid metric type."""
        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL', 'invalid_category', 8)

        assert result['success'] is False
        assert 'Unknown metric type' in result['error']
        assert 'available_types' in result

    def test_get_metrics_history_not_found(self, mock_metrics_table):
        """Test when no metrics are found."""
        mock_metrics_table.query.return_value = {'Items': []}

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('UNKNOWN', 'all', 8)

        assert result['success'] is False
        assert 'No metrics history found' in result['error']

    def test_get_metrics_history_missing_ticker(self, mock_metrics_table):
        """Test error when ticker is missing."""
        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('', 'all', 8)

        assert result['success'] is False
        assert 'ticker is required' in result['error']

    def test_get_metrics_history_default_parameters(self, mock_metrics_table):
        """Test default parameters for metric_type and quarters."""
        mock_metrics_table.query.return_value = {'Items': []}

        from utils.tool_executor import get_metrics_history
        result = get_metrics_history('AAPL')

        # Should use defaults: metric_type='all', quarters=8
        call_args = mock_metrics_table.query.call_args
        assert call_args[1]['Limit'] == 8


class TestGetAvailableReports:
    """Tests for get_available_reports function."""

    @pytest.fixture
    def mock_reports_table(self):
        """Create a mock DynamoDB table for reports."""
        with patch('utils.tool_executor.reports_table') as mock_table:
            yield mock_table

    def test_get_available_reports_success(self, mock_reports_table):
        """Test successful reports listing."""
        mock_reports_table.scan.return_value = {
            'Items': [
                {'ticker': 'AAPL', 'company_name': 'Apple Inc.', 'generated_at': '2026-01-15'},
                {'ticker': 'MSFT', 'company_name': 'Microsoft Corp.', 'generated_at': '2026-01-14'},
                {'ticker': 'GOOGL', 'company_name': 'Alphabet Inc.', 'generated_at': '2026-01-13'}
            ]
        }

        from utils.tool_executor import get_available_reports
        result = get_available_reports()

        assert result['success'] is True
        assert result['count'] == 3
        assert len(result['reports']) == 3
        # Should be sorted alphabetically
        assert result['reports'][0]['ticker'] == 'AAPL'
        assert result['reports'][1]['ticker'] == 'GOOGL'
        assert result['reports'][2]['ticker'] == 'MSFT'

    def test_get_available_reports_pagination(self, mock_reports_table):
        """Test pagination handling for large result sets."""
        # First call returns partial results with LastEvaluatedKey
        mock_reports_table.scan.side_effect = [
            {
                'Items': [
                    {'ticker': 'AAPL', 'company_name': 'Apple Inc.', 'generated_at': '2026-01-15'},
                    {'ticker': 'MSFT', 'company_name': 'Microsoft Corp.', 'generated_at': '2026-01-14'}
                ],
                'LastEvaluatedKey': {'ticker': 'MSFT', 'section_id': '00_executive'}
            },
            {
                'Items': [
                    {'ticker': 'GOOGL', 'company_name': 'Alphabet Inc.', 'generated_at': '2026-01-13'},
                    {'ticker': 'AMZN', 'company_name': 'Amazon.com Inc.', 'generated_at': '2026-01-12'}
                ]
            }
        ]

        from utils.tool_executor import get_available_reports
        result = get_available_reports()

        assert result['success'] is True
        assert result['count'] == 4
        assert len(result['reports']) == 4
        # Verify scan was called twice
        assert mock_reports_table.scan.call_count == 2

    def test_get_available_reports_empty(self, mock_reports_table):
        """Test empty reports list."""
        mock_reports_table.scan.return_value = {'Items': []}

        from utils.tool_executor import get_available_reports
        result = get_available_reports()

        assert result['success'] is True
        assert result['count'] == 0
        assert result['reports'] == []

    def test_get_available_reports_database_error(self, mock_reports_table):
        """Test handling of DynamoDB errors."""
        mock_reports_table.scan.side_effect = ClientError(
            {'Error': {'Code': 'InternalServerError', 'Message': 'Test error'}},
            'Scan'
        )

        from utils.tool_executor import get_available_reports
        result = get_available_reports()

        assert result['success'] is False
        assert 'Database error' in result['error']


class TestDecimalEncoder:
    """Tests for DecimalEncoder JSON serialization."""

    def test_decimal_to_float_conversion(self):
        """Test Decimal with decimals converts to float."""
        from utils.tool_executor import DecimalEncoder

        data = {'value': Decimal('123.456')}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['value'] == 123.456
        assert isinstance(parsed['value'], float)

    def test_decimal_to_int_conversion(self):
        """Test whole number Decimal converts to int."""
        from utils.tool_executor import DecimalEncoder

        data = {'value': Decimal('123')}
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['value'] == 123
        assert isinstance(parsed['value'], int)

    def test_nested_decimal_conversion(self):
        """Test nested Decimals are converted."""
        from utils.tool_executor import DecimalEncoder

        data = {
            'metrics': {
                'revenue': Decimal('1000000'),
                'margin': Decimal('0.25'),
                'quarters': [
                    {'value': Decimal('100')},
                    {'value': Decimal('200.5')}
                ]
            }
        }
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed['metrics']['revenue'] == 1000000
        assert parsed['metrics']['margin'] == 0.25
        assert parsed['metrics']['quarters'][0]['value'] == 100
        assert parsed['metrics']['quarters'][1]['value'] == 200.5

    def test_non_decimal_passthrough(self):
        """Test non-Decimal types are passed through."""
        from utils.tool_executor import DecimalEncoder

        data = {
            'string': 'hello',
            'int': 42,
            'float': 3.14,
            'bool': True,
            'null': None,
            'list': [1, 2, 3]
        }
        result = json.dumps(data, cls=DecimalEncoder)
        parsed = json.loads(result)

        assert parsed == data


class TestCompareStocks:
    """Tests for compare_stocks function."""

    def test_routes_to_compare_stocks(self):
        """Test routing to compareStocks."""
        with patch('utils.tool_executor.compare_stocks') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('compareStocks', {
                'tickers': ['AAPL', 'MSFT'],
                'metric_type': 'valuation',
                'quarters': 4
            })

            mock_func.assert_called_once_with(
                tickers=['AAPL', 'MSFT'],
                metric_type='valuation',
                quarters=4
            )
            assert result['success'] is True

    def test_compare_two_stocks_success(self):
        """Test successful comparison of two stocks."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.side_effect = lambda ticker: {
                'success': True,
                'ticker': ticker,
                'company_name': f'{ticker} Inc.',
                'ratings': {'verdict': 'BUY', 'conviction': 85},
                'generated_at': '2026-01-15T10:00:00Z'
            }

            mock_metrics.side_effect = lambda ticker, metric_type, quarters: {
                'success': True,
                'ticker': ticker,
                'data': {'valuation': {'quarters': [{'metrics': {'roe': 25.0}}]}},
                'quarters_available': 1
            }

            from utils.tool_executor import compare_stocks
            result = compare_stocks(['AAPL', 'MSFT'], 'valuation', 4)

            assert result['success'] is True
            assert 'AAPL' in result['comparison']
            assert 'MSFT' in result['comparison']
            assert result['tickers_compared'] == ['AAPL', 'MSFT']
            assert result['comparison']['AAPL']['company_name'] == 'AAPL Inc.'
            assert result['comparison']['MSFT']['company_name'] == 'MSFT Inc.'

    def test_compare_stocks_partial_not_found(self):
        """Test comparison when some tickers have no data."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            def ratings_side_effect(ticker):
                if ticker == 'AAPL':
                    return {'success': True, 'ticker': 'AAPL', 'company_name': 'Apple',
                            'ratings': {'verdict': 'BUY'}, 'generated_at': '2026-01-15'}
                return {'success': False, 'error': 'Not found'}

            def metrics_side_effect(ticker, metric_type, quarters):
                if ticker == 'AAPL':
                    return {'success': True, 'data': {}, 'quarters_available': 4}
                return {'success': False, 'error': 'Not found'}

            mock_ratings.side_effect = ratings_side_effect
            mock_metrics.side_effect = metrics_side_effect

            from utils.tool_executor import compare_stocks
            result = compare_stocks(['AAPL', 'FAKE'], 'all', 4)

            assert result['success'] is True
            assert 'AAPL' in result['comparison']
            assert 'FAKE' not in result['comparison']
            assert 'FAKE' in result['tickers_not_found']
            assert 'warning' in result

    def test_compare_stocks_all_not_found(self):
        """Test comparison when no tickers have data."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {'success': False, 'error': 'Not found'}
            mock_metrics.return_value = {'success': False, 'error': 'Not found'}

            from utils.tool_executor import compare_stocks
            result = compare_stocks(['FAKE1', 'FAKE2'], 'all', 4)

            assert result['success'] is False
            assert 'No reports found' in result['error']

    def test_compare_stocks_too_few_tickers(self):
        """Test error when fewer than 2 tickers provided."""
        from utils.tool_executor import compare_stocks
        result = compare_stocks(['AAPL'], 'all', 4)

        assert result['success'] is False
        assert 'At least 2 tickers' in result['error']

    def test_compare_stocks_too_many_tickers(self):
        """Test error when more than 5 tickers provided."""
        from utils.tool_executor import compare_stocks
        result = compare_stocks(['A', 'B', 'C', 'D', 'E', 'F'], 'all', 4)

        assert result['success'] is False
        assert 'Maximum 5 tickers' in result['error']

    def test_compare_stocks_empty_list(self):
        """Test error when empty list provided."""
        from utils.tool_executor import compare_stocks
        result = compare_stocks([], 'all', 4)

        assert result['success'] is False
        assert 'tickers must be a list' in result['error']

    def test_compare_stocks_not_a_list(self):
        """Test error when tickers is not a list."""
        from utils.tool_executor import compare_stocks
        result = compare_stocks('AAPL', 'all', 4)

        assert result['success'] is False

    def test_compare_stocks_normalizes_tickers(self):
        """Test that tickers are normalized to uppercase."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {
                'success': True, 'company_name': 'Test', 'ratings': {},
                'generated_at': ''
            }
            mock_metrics.return_value = {
                'success': True, 'data': {}, 'quarters_available': 0
            }

            from utils.tool_executor import compare_stocks
            result = compare_stocks(['aapl', ' msft '], 'all', 4)

            assert result['success'] is True
            assert 'AAPL' in result['comparison']
            assert 'MSFT' in result['comparison']

    def test_compare_stocks_clamps_quarters(self):
        """Test that quarters are clamped to 1-20 range."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {
                'success': True, 'company_name': 'Test', 'ratings': {},
                'generated_at': ''
            }
            mock_metrics.return_value = {
                'success': True, 'data': {}, 'quarters_available': 0
            }

            from utils.tool_executor import compare_stocks
            result = compare_stocks(['AAPL', 'MSFT'], 'all', 50)

            assert result['success'] is True
            assert result['quarters'] == 20


class TestGetFinancialSnapshot:
    """Tests for get_financial_snapshot function."""

    def test_routes_to_get_financial_snapshot(self):
        """Test routing to getFinancialSnapshot."""
        with patch('utils.tool_executor.get_financial_snapshot') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('getFinancialSnapshot', {'ticker': 'AAPL'})

            mock_func.assert_called_once_with(ticker='AAPL')
            assert result['success'] is True

    def test_snapshot_success(self):
        """Test successful snapshot retrieval."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {
                'success': True,
                'ticker': 'AAPL',
                'company_name': 'Apple Inc.',
                'ratings': {
                    'growth_rating': 'STRONG',
                    'growth_confidence': 85,
                    'overall_verdict': 'BUY',
                    'conviction': 90
                },
                'generated_at': '2026-01-15T10:00:00Z'
            }

            mock_metrics.return_value = {
                'success': True,
                'data': {
                    'revenue_profit': {
                        'quarters': [{
                            'fiscal_date': '2025-12-28',
                            'fiscal_year': 2026,
                            'fiscal_quarter': 'Q1',
                            'metrics': {'revenue': 100000, 'net_margin': 0.25}
                        }]
                    },
                    'valuation': {
                        'quarters': [{
                            'fiscal_date': '2025-12-28',
                            'fiscal_year': 2026,
                            'fiscal_quarter': 'Q1',
                            'metrics': {'roe': 25.0}
                        }]
                    }
                },
                'quarters_available': 1
            }

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('AAPL')

            assert result['success'] is True
            assert result['ticker'] == 'AAPL'
            assert result['company_name'] == 'Apple Inc.'
            assert result['ratings']['overall_verdict'] == 'BUY'
            assert result['fiscal_period']['fiscal_year'] == 2026
            assert result['fiscal_period']['fiscal_quarter'] == 'Q1'
            assert 'revenue_profit' in result['latest_metrics']
            assert 'valuation' in result['latest_metrics']
            assert result['latest_metrics']['revenue_profit']['revenue'] == 100000

    def test_snapshot_missing_ticker(self):
        """Test error when ticker is empty."""
        from utils.tool_executor import get_financial_snapshot
        result = get_financial_snapshot('')

        assert result['success'] is False
        assert 'ticker is required' in result['error']

    def test_snapshot_not_found(self):
        """Test when no data found for ticker."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {'success': False, 'error': 'Not found'}
            mock_metrics.return_value = {'success': False, 'error': 'Not found'}

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('FAKE')

            assert result['success'] is False
            assert 'No data found' in result['error']

    def test_snapshot_ratings_only(self):
        """Test snapshot when only ratings are available (no metrics)."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {
                'success': True,
                'ticker': 'AAPL',
                'company_name': 'Apple Inc.',
                'ratings': {'verdict': 'BUY'},
                'generated_at': '2026-01-15'
            }
            mock_metrics.return_value = {'success': False, 'error': 'No metrics'}

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('AAPL')

            assert result['success'] is True
            assert result['ratings']['verdict'] == 'BUY'
            assert result['latest_metrics'] == {}

    def test_snapshot_metrics_only(self):
        """Test snapshot when only metrics are available (no ratings)."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {'success': False, 'error': 'Not found'}
            mock_metrics.return_value = {
                'success': True,
                'data': {
                    'revenue_profit': {
                        'quarters': [{
                            'fiscal_date': '2025-12-28',
                            'fiscal_year': 2026,
                            'fiscal_quarter': 'Q1',
                            'metrics': {'revenue': 100000}
                        }]
                    }
                },
                'quarters_available': 1
            }

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('AAPL')

            assert result['success'] is True
            assert result['ratings'] is None
            assert result['latest_metrics']['revenue_profit']['revenue'] == 100000

    def test_snapshot_normalizes_ticker(self):
        """Test that ticker is normalized to uppercase."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings, \
             patch('utils.tool_executor.get_metrics_history') as mock_metrics:

            mock_ratings.return_value = {
                'success': True, 'company_name': 'Apple', 'ratings': {},
                'generated_at': ''
            }
            mock_metrics.return_value = {
                'success': True, 'data': {}, 'quarters_available': 0
            }

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('  aapl  ')

            assert result['success'] is True
            assert result['ticker'] == 'AAPL'

    def test_snapshot_database_error(self):
        """Test handling of exceptions."""
        with patch('utils.tool_executor.get_report_ratings') as mock_ratings:
            mock_ratings.side_effect = Exception('Connection timeout')

            from utils.tool_executor import get_financial_snapshot
            result = get_financial_snapshot('AAPL')

            assert result['success'] is False
            assert 'Snapshot error' in result['error']


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_execute_tool_with_default_parameters(self):
        """Test execute_tool provides defaults for optional parameters."""
        with patch('utils.tool_executor.get_metrics_history') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            # Only provide ticker, omit optional params
            result = execute_tool('getMetricsHistory', {'ticker': 'AAPL'})

            mock_func.assert_called_once_with(ticker='AAPL', metric_type='all', quarters=8)

    def test_execute_tool_empty_input_dict(self):
        """Test execute_tool handles empty input for tools with no required params."""
        with patch('utils.tool_executor.get_available_reports') as mock_func:
            mock_func.return_value = {'success': True, 'count': 0}

            from utils.tool_executor import execute_tool
            result = execute_tool('getAvailableReports', {})

            mock_func.assert_called_once()
            assert result['success'] is True

    def test_execute_tool_compare_stocks_defaults(self):
        """Test execute_tool provides defaults for compareStocks optional params."""
        with patch('utils.tool_executor.compare_stocks') as mock_func:
            mock_func.return_value = {'success': True}

            from utils.tool_executor import execute_tool
            result = execute_tool('compareStocks', {'tickers': ['AAPL', 'MSFT']})

            mock_func.assert_called_once_with(
                tickers=['AAPL', 'MSFT'],
                metric_type='all',
                quarters=4
            )
