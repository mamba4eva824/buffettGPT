#!/usr/bin/env python3
"""
Comprehensive unit tests for ReportGenerator in report_generator.py

Tests the following key functionality:
1. Fiscal Year Aggregation Fix (_aggregate_annual_data)
   - fiscalYear field usage from FMP data
   - Non-calendar fiscal years (e.g., OKTA ends Jan 31)
   - Calendar fiscal years (e.g., JPM ends Dec 31)
   - Fallback chain: fiscalYear -> calendarYear -> date extraction

2. Data Aggregation Logic
   - Flow metrics (revenue, netIncome) SUMMED across quarters
   - Point-in-time metrics (debt, cash) use most recent quarter value

3. ReportGenerator Core Functionality
   - Class initialization and prompt version selection
   - prepare_data() method behavior

Run:
    cd chat-api/backend
    pytest investment_research/tests/test_report_generator.py -v

Or directly:
    cd chat-api/backend
    python -m pytest investment_research/tests/test_report_generator.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
from datetime import datetime

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investment_research.report_generator import (
    ReportGenerator,
    DecimalEncoder,
    decimal_to_float,
)


# =============================================================================
# MOCK DATA GENERATORS
# =============================================================================

def generate_okta_like_fiscal_year_data(num_quarters: int = 8) -> dict:
    """
    Generate mock FMP data for a company with non-calendar fiscal year.

    OKTA's fiscal year ends January 31, so:
    - FY2024 Q4 ends Jan 31, 2024 (but fiscalYear = 2024)
    - FY2024 Q3 ends Oct 31, 2023 (but fiscalYear = 2024)
    - FY2024 Q2 ends Jul 31, 2023 (but fiscalYear = 2024)
    - FY2024 Q1 ends Apr 30, 2023 (but fiscalYear = 2024)

    This tests the fiscalYear field correctly grouping quarters that span
    calendar years.
    """
    income_statements = []
    balance_sheets = []
    cash_flows = []

    # FY2024 quarters (spans calendar 2023-2024)
    fy2024_quarters = [
        {'date': '2024-01-31', 'period': 'Q4', 'fiscalYear': 2024, 'calendarYear': 2024},
        {'date': '2023-10-31', 'period': 'Q3', 'fiscalYear': 2024, 'calendarYear': 2023},
        {'date': '2023-07-31', 'period': 'Q2', 'fiscalYear': 2024, 'calendarYear': 2023},
        {'date': '2023-04-30', 'period': 'Q1', 'fiscalYear': 2024, 'calendarYear': 2023},
    ]

    # FY2023 quarters (spans calendar 2022-2023)
    fy2023_quarters = [
        {'date': '2023-01-31', 'period': 'Q4', 'fiscalYear': 2023, 'calendarYear': 2023},
        {'date': '2022-10-31', 'period': 'Q3', 'fiscalYear': 2023, 'calendarYear': 2022},
        {'date': '2022-07-31', 'period': 'Q2', 'fiscalYear': 2023, 'calendarYear': 2022},
        {'date': '2022-04-30', 'period': 'Q1', 'fiscalYear': 2023, 'calendarYear': 2022},
    ]

    all_quarters = fy2024_quarters + fy2023_quarters

    for i, q in enumerate(all_quarters[:num_quarters]):
        # Flow metrics - distinct values per quarter for testing summation
        base_revenue = 500_000_000 + (i * 10_000_000)  # ~$500M per quarter

        income_statements.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'revenue': base_revenue,
            'netIncome': int(base_revenue * 0.05),  # 5% margin
            'grossProfit': int(base_revenue * 0.70),
            'operatingIncome': int(base_revenue * 0.08),
            'costOfRevenue': int(base_revenue * 0.30),
            'operatingExpenses': int(base_revenue * 0.62),
            'interestExpense': 5_000_000,
            'incomeBeforeTax': int(base_revenue * 0.07),
            'incomeTaxExpense': int(base_revenue * 0.02),
            'ebitda': int(base_revenue * 0.12),
            'eps': round(base_revenue * 0.05 / 150_000_000, 2),  # ~150M shares
        })

        # Point-in-time metrics - balance sheet shows position at quarter end
        # Most recent quarter should be used for annual balance sheet
        balance_sheets.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'totalDebt': 2_000_000_000 - (i * 50_000_000),  # Decreasing debt
            'cashAndCashEquivalents': 2_500_000_000 + (i * 100_000_000),
            'totalStockholdersEquity': 3_000_000_000,
            'totalAssets': 8_000_000_000,
            'totalCurrentAssets': 3_500_000_000,
            'totalCurrentLiabilities': 1_500_000_000,
        })

        # Cash flow - flow metrics that should be summed
        cash_flows.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'operatingCashFlow': int(base_revenue * 0.15),
            'freeCashFlow': int(base_revenue * 0.10),
            'capitalExpenditure': -int(base_revenue * 0.05),
            'dividendsPaid': 0,
            'commonStockRepurchased': -10_000_000,
            'netCashUsedForInvestingActivites': -int(base_revenue * 0.08),
            'netCashUsedProvidedByFinancingActivities': -20_000_000,
            'netChangeInCash': int(base_revenue * 0.05),
        })

    return {
        'income_statement': income_statements,
        'balance_sheet': balance_sheets,
        'cash_flow': cash_flows,
    }


def generate_jpm_like_calendar_fiscal_year_data(num_quarters: int = 8) -> dict:
    """
    Generate mock FMP data for a company with calendar fiscal year (Dec 31).

    JPM's fiscal year matches calendar year:
    - FY2024 Q4 ends Dec 31, 2024 (fiscalYear = 2024, calendarYear = 2024)
    - FY2024 Q3 ends Sep 30, 2024 (fiscalYear = 2024, calendarYear = 2024)
    - etc.

    For calendar year companies, fiscalYear == calendarYear.
    """
    income_statements = []
    balance_sheets = []
    cash_flows = []

    # FY2024 quarters
    fy2024_quarters = [
        {'date': '2024-12-31', 'period': 'Q4', 'fiscalYear': 2024, 'calendarYear': 2024},
        {'date': '2024-09-30', 'period': 'Q3', 'fiscalYear': 2024, 'calendarYear': 2024},
        {'date': '2024-06-30', 'period': 'Q2', 'fiscalYear': 2024, 'calendarYear': 2024},
        {'date': '2024-03-31', 'period': 'Q1', 'fiscalYear': 2024, 'calendarYear': 2024},
    ]

    # FY2023 quarters
    fy2023_quarters = [
        {'date': '2023-12-31', 'period': 'Q4', 'fiscalYear': 2023, 'calendarYear': 2023},
        {'date': '2023-09-30', 'period': 'Q3', 'fiscalYear': 2023, 'calendarYear': 2023},
        {'date': '2023-06-30', 'period': 'Q2', 'fiscalYear': 2023, 'calendarYear': 2023},
        {'date': '2023-03-31', 'period': 'Q1', 'fiscalYear': 2023, 'calendarYear': 2023},
    ]

    all_quarters = fy2024_quarters + fy2023_quarters

    for i, q in enumerate(all_quarters[:num_quarters]):
        # Bank-like financials - higher revenue, different margins
        base_revenue = 40_000_000_000 + (i * 500_000_000)  # ~$40B per quarter

        income_statements.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'revenue': base_revenue,
            'netIncome': int(base_revenue * 0.25),  # 25% margin (bank)
            'grossProfit': int(base_revenue * 0.60),
            'operatingIncome': int(base_revenue * 0.35),
            'costOfRevenue': int(base_revenue * 0.40),
            'operatingExpenses': int(base_revenue * 0.25),
            'interestExpense': int(base_revenue * 0.10),
            'incomeBeforeTax': int(base_revenue * 0.30),
            'incomeTaxExpense': int(base_revenue * 0.05),
            'ebitda': int(base_revenue * 0.40),
            'eps': round(base_revenue * 0.25 / 3_000_000_000, 2),  # ~3B shares
        })

        balance_sheets.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'totalDebt': 300_000_000_000,  # $300B debt (bank)
            'cashAndCashEquivalents': 500_000_000_000,  # $500B cash
            'totalStockholdersEquity': 280_000_000_000,
            'totalAssets': 3_500_000_000_000,  # $3.5T assets
            'totalCurrentAssets': 800_000_000_000,
            'totalCurrentLiabilities': 700_000_000_000,
        })

        cash_flows.append({
            'date': q['date'],
            'period': q['period'],
            'fiscalYear': q['fiscalYear'],
            'calendarYear': q['calendarYear'],
            'operatingCashFlow': int(base_revenue * 0.30),
            'freeCashFlow': int(base_revenue * 0.25),
            'capitalExpenditure': -int(base_revenue * 0.05),
            'dividendsPaid': -int(base_revenue * 0.08),
            'commonStockRepurchased': -int(base_revenue * 0.10),
            'netCashUsedForInvestingActivites': -int(base_revenue * 0.10),
            'netCashUsedProvidedByFinancingActivities': -int(base_revenue * 0.15),
            'netChangeInCash': int(base_revenue * 0.05),
        })

    return {
        'income_statement': income_statements,
        'balance_sheet': balance_sheets,
        'cash_flow': cash_flows,
    }


def generate_data_without_fiscal_year_field(num_quarters: int = 8) -> dict:
    """
    Generate mock FMP data where fiscalYear field is missing.

    Tests the fallback chain: fiscalYear -> calendarYear -> date extraction.
    Some older FMP data or certain endpoints may not include fiscalYear.
    """
    income_statements = []
    balance_sheets = []
    cash_flows = []

    quarters = [
        {'date': '2024-12-31', 'calendarYear': 2024},
        {'date': '2024-09-30', 'calendarYear': 2024},
        {'date': '2024-06-30', 'calendarYear': 2024},
        {'date': '2024-03-31', 'calendarYear': 2024},
        {'date': '2023-12-31', 'calendarYear': 2023},
        {'date': '2023-09-30', 'calendarYear': 2023},
        {'date': '2023-06-30', 'calendarYear': 2023},
        {'date': '2023-03-31', 'calendarYear': 2023},
    ]

    for i, q in enumerate(quarters[:num_quarters]):
        base_revenue = 10_000_000_000

        # Note: No fiscalYear field - should fall back to calendarYear
        income_statements.append({
            'date': q['date'],
            'calendarYear': q['calendarYear'],
            'revenue': base_revenue,
            'netIncome': int(base_revenue * 0.10),
            'grossProfit': int(base_revenue * 0.50),
            'operatingIncome': int(base_revenue * 0.15),
            'costOfRevenue': int(base_revenue * 0.50),
            'operatingExpenses': int(base_revenue * 0.35),
            'interestExpense': 100_000_000,
            'incomeBeforeTax': int(base_revenue * 0.12),
            'incomeTaxExpense': int(base_revenue * 0.02),
            'ebitda': int(base_revenue * 0.20),
            'eps': 2.50,
        })

        balance_sheets.append({
            'date': q['date'],
            'calendarYear': q['calendarYear'],
            'totalDebt': 20_000_000_000,
            'cashAndCashEquivalents': 15_000_000_000,
            'totalStockholdersEquity': 50_000_000_000,
            'totalAssets': 100_000_000_000,
            'totalCurrentAssets': 25_000_000_000,
            'totalCurrentLiabilities': 15_000_000_000,
        })

        cash_flows.append({
            'date': q['date'],
            'calendarYear': q['calendarYear'],
            'operatingCashFlow': int(base_revenue * 0.15),
            'freeCashFlow': int(base_revenue * 0.10),
            'capitalExpenditure': -int(base_revenue * 0.05),
            'dividendsPaid': -int(base_revenue * 0.03),
            'commonStockRepurchased': -int(base_revenue * 0.02),
            'netCashUsedForInvestingActivites': -int(base_revenue * 0.06),
            'netCashUsedProvidedByFinancingActivities': -int(base_revenue * 0.04),
            'netChangeInCash': int(base_revenue * 0.05),
        })

    return {
        'income_statement': income_statements,
        'balance_sheet': balance_sheets,
        'cash_flow': cash_flows,
    }


def generate_data_with_only_date_field(num_quarters: int = 4) -> dict:
    """
    Generate mock FMP data where only the date field exists.

    Tests final fallback: extract year from date string.
    """
    income_statements = []
    balance_sheets = []
    cash_flows = []

    dates = ['2024-12-31', '2024-09-30', '2024-06-30', '2024-03-31']

    for i, date in enumerate(dates[:num_quarters]):
        base_revenue = 5_000_000_000

        # No fiscalYear, no calendarYear - only date
        income_statements.append({
            'date': date,
            'revenue': base_revenue,
            'netIncome': int(base_revenue * 0.10),
            'grossProfit': int(base_revenue * 0.50),
            'operatingIncome': int(base_revenue * 0.15),
            'costOfRevenue': int(base_revenue * 0.50),
            'operatingExpenses': int(base_revenue * 0.35),
            'interestExpense': 50_000_000,
            'incomeBeforeTax': int(base_revenue * 0.12),
            'incomeTaxExpense': int(base_revenue * 0.02),
            'ebitda': int(base_revenue * 0.20),
            'eps': 1.25,
        })

        balance_sheets.append({
            'date': date,
            'totalDebt': 10_000_000_000,
            'cashAndCashEquivalents': 8_000_000_000,
            'totalStockholdersEquity': 30_000_000_000,
            'totalAssets': 60_000_000_000,
            'totalCurrentAssets': 15_000_000_000,
            'totalCurrentLiabilities': 10_000_000_000,
        })

        cash_flows.append({
            'date': date,
            'operatingCashFlow': int(base_revenue * 0.15),
            'freeCashFlow': int(base_revenue * 0.10),
            'capitalExpenditure': -int(base_revenue * 0.05),
            'dividendsPaid': -int(base_revenue * 0.03),
            'commonStockRepurchased': -int(base_revenue * 0.02),
            'netCashUsedForInvestingActivites': -int(base_revenue * 0.06),
            'netCashUsedProvidedByFinancingActivities': -int(base_revenue * 0.04),
            'netChangeInCash': int(base_revenue * 0.05),
        })

    return {
        'income_statement': income_statements,
        'balance_sheet': balance_sheets,
        'cash_flow': cash_flows,
    }


# =============================================================================
# UTILITY FUNCTION TESTS
# =============================================================================

class TestDecimalToFloat:
    """Tests for the decimal_to_float utility function."""

    def test_converts_decimal_to_float(self):
        """decimal_to_float should convert Decimal to float."""
        result = decimal_to_float(Decimal('123.45'))
        assert result == 123.45
        assert isinstance(result, float)

    def test_handles_nested_dict(self):
        """decimal_to_float should recursively convert dicts."""
        data = {
            'value1': Decimal('100.50'),
            'nested': {
                'value2': Decimal('200.75'),
                'deep': {
                    'value3': Decimal('300.25')
                }
            }
        }
        result = decimal_to_float(data)

        assert result['value1'] == 100.50
        assert result['nested']['value2'] == 200.75
        assert result['nested']['deep']['value3'] == 300.25

    def test_handles_list(self):
        """decimal_to_float should recursively convert lists."""
        data = [Decimal('1.1'), Decimal('2.2'), {'val': Decimal('3.3')}]
        result = decimal_to_float(data)

        assert result == [1.1, 2.2, {'val': 3.3}]

    def test_passes_through_non_decimals(self):
        """decimal_to_float should pass through non-Decimal types."""
        assert decimal_to_float(42) == 42
        assert decimal_to_float('hello') == 'hello'
        assert decimal_to_float(None) is None
        assert decimal_to_float(3.14) == 3.14


class TestDecimalEncoder:
    """Tests for the DecimalEncoder JSON encoder."""

    def test_encodes_decimal(self):
        """DecimalEncoder should encode Decimal as float."""
        import json
        data = {'amount': Decimal('99.99')}
        result = json.dumps(data, cls=DecimalEncoder)
        assert result == '{"amount": 99.99}'

    def test_encodes_mixed_types(self):
        """DecimalEncoder should handle mixed types."""
        import json
        data = {
            'decimal_val': Decimal('50.25'),
            'int_val': 100,
            'float_val': 3.14,
            'str_val': 'test'
        }
        result = json.loads(json.dumps(data, cls=DecimalEncoder))

        assert result['decimal_val'] == 50.25
        assert result['int_val'] == 100
        assert result['float_val'] == 3.14
        assert result['str_val'] == 'test'


# =============================================================================
# FISCAL YEAR AGGREGATION TESTS
# =============================================================================

class TestAggregateAnnualDataFiscalYear:
    """
    Tests for _aggregate_annual_data focusing on fiscal year handling.

    The critical fix being tested:
    - Line 339: year = stmt.get('fiscalYear') or stmt.get('calendarYear') or ...
    - Line 348: year = bs.get('fiscalYear') or bs.get('calendarYear') or ...
    - Line 354: year = cf.get('fiscalYear') or cf.get('calendarYear') or ...

    This ensures quarters are grouped by FISCAL year, not calendar year.
    """

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator with mocked AWS dependencies."""
        with patch('investment_research.report_generator.boto3'):
            generator = ReportGenerator(use_api=False, prompt_version=4.2)
            return generator

    def test_okta_like_non_calendar_fiscal_year(self, report_generator):
        """
        Test grouping for non-calendar fiscal year (OKTA ends Jan 31).

        FY2024 should include:
        - Q4 ending Jan 31, 2024 (calendar 2024)
        - Q3 ending Oct 31, 2023 (calendar 2023)
        - Q2 ending Jul 31, 2023 (calendar 2023)
        - Q1 ending Apr 30, 2023 (calendar 2023)

        Without fiscalYear field, these would incorrectly be split between
        calendar years 2023 and 2024.
        """
        data = generate_okta_like_fiscal_year_data(8)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should have exactly 2 fiscal years
        assert 2024 in annual_data or '2024' in annual_data
        assert 2023 in annual_data or '2023' in annual_data

        # Get FY2024 data (handle both int and string keys)
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        fy2024 = annual_data[fy2024_key]

        # Should have 4 quarters for FY2024
        assert fy2024['quarters_count'] == 4, \
            f"Expected 4 quarters for FY2024, got {fy2024['quarters_count']}"

        # Revenue should be sum of 4 quarters (~$2B total)
        # Q1: 530M, Q2: 520M, Q3: 510M, Q4: 500M = ~$2.06B
        expected_min_revenue = 2_000_000_000
        actual_revenue = fy2024['income']['revenue']
        assert actual_revenue > expected_min_revenue, \
            f"FY2024 revenue {actual_revenue} should be > {expected_min_revenue}"

    def test_jpm_like_calendar_fiscal_year(self, report_generator):
        """
        Test grouping for calendar fiscal year (JPM ends Dec 31).

        For calendar year companies, fiscalYear == calendarYear, so
        both grouping methods should produce the same result.
        """
        data = generate_jpm_like_calendar_fiscal_year_data(8)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should have 2 fiscal years
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        fy2023_key = 2023 if 2023 in annual_data else '2023'

        assert fy2024_key in annual_data
        assert fy2023_key in annual_data

        # Each year should have 4 quarters
        assert annual_data[fy2024_key]['quarters_count'] == 4
        assert annual_data[fy2023_key]['quarters_count'] == 4

    def test_fallback_to_calendar_year(self, report_generator):
        """
        Test fallback when fiscalYear field is missing.

        Should fall back to calendarYear field.
        """
        data = generate_data_without_fiscal_year_field(8)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should still group correctly using calendarYear
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        fy2023_key = 2023 if 2023 in annual_data else '2023'

        assert fy2024_key in annual_data
        assert fy2023_key in annual_data

        # Each calendar year should have 4 quarters
        assert annual_data[fy2024_key]['quarters_count'] == 4
        assert annual_data[fy2023_key]['quarters_count'] == 4

    def test_fallback_to_date_extraction(self, report_generator):
        """
        Test final fallback: extract year from date string.

        When both fiscalYear and calendarYear are missing, should extract
        year from date field (e.g., '2024-12-31' -> '2024').
        """
        data = generate_data_with_only_date_field(4)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should extract 2024 from date strings
        assert '2024' in annual_data or 2024 in annual_data

        year_key = '2024' if '2024' in annual_data else 2024
        assert annual_data[year_key]['quarters_count'] == 4


class TestFlowMetricsSummation:
    """
    Tests for flow metrics being correctly SUMMED across quarters.

    Flow metrics represent activity over a period and must be summed:
    - revenue, netIncome, grossProfit, operatingIncome
    - costOfRevenue, operatingExpenses, interestExpense
    - incomeBeforeTax, incomeTaxExpense, ebitda
    - operatingCashFlow, freeCashFlow, capitalExpenditure
    - dividendsPaid, commonStockRepurchased, etc.
    """

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator with mocked AWS dependencies."""
        with patch('investment_research.report_generator.boto3'):
            return ReportGenerator(use_api=False, prompt_version=4.2)

    def test_revenue_summed_across_quarters(self, report_generator):
        """Revenue should be sum of all quarters in fiscal year."""
        data = generate_okta_like_fiscal_year_data(8)

        # Calculate expected FY2024 revenue (sum of first 4 quarters)
        fy2024_quarters = [s for s in data['income_statement'][:4]]
        expected_revenue = sum(q['revenue'] for q in fy2024_quarters)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_revenue = annual_data[fy2024_key]['income']['revenue']

        assert actual_revenue == expected_revenue, \
            f"Revenue mismatch: expected {expected_revenue}, got {actual_revenue}"

    def test_net_income_summed_across_quarters(self, report_generator):
        """Net income should be sum of all quarters in fiscal year."""
        data = generate_jpm_like_calendar_fiscal_year_data(8)

        # Calculate expected FY2024 net income
        fy2024_quarters = [s for s in data['income_statement'][:4]]
        expected_ni = sum(q['netIncome'] for q in fy2024_quarters)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_ni = annual_data[fy2024_key]['income']['netIncome']

        assert actual_ni == expected_ni, \
            f"Net income mismatch: expected {expected_ni}, got {actual_ni}"

    def test_operating_cash_flow_summed(self, report_generator):
        """Operating cash flow should be summed across quarters."""
        data = generate_okta_like_fiscal_year_data(8)

        # Calculate expected FY2024 OCF
        fy2024_quarters = [cf for cf in data['cash_flow'][:4]]
        expected_ocf = sum(q['operatingCashFlow'] for q in fy2024_quarters)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_ocf = annual_data[fy2024_key]['cashflow']['operatingCashFlow']

        assert actual_ocf == expected_ocf, \
            f"OCF mismatch: expected {expected_ocf}, got {actual_ocf}"

    def test_free_cash_flow_summed(self, report_generator):
        """Free cash flow should be summed across quarters."""
        data = generate_jpm_like_calendar_fiscal_year_data(8)

        fy2024_quarters = [cf for cf in data['cash_flow'][:4]]
        expected_fcf = sum(q['freeCashFlow'] for q in fy2024_quarters)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_fcf = annual_data[fy2024_key]['cashflow']['freeCashFlow']

        assert actual_fcf == expected_fcf, \
            f"FCF mismatch: expected {expected_fcf}, got {actual_fcf}"

    def test_eps_summed_across_quarters(self, report_generator):
        """EPS should be summed across quarters for annual figure."""
        data = generate_okta_like_fiscal_year_data(8)

        fy2024_quarters = [s for s in data['income_statement'][:4]]
        expected_eps = sum(q['eps'] for q in fy2024_quarters)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_eps = annual_data[fy2024_key]['income']['eps']

        # Use approximate comparison for floating point
        assert abs(actual_eps - expected_eps) < 0.01, \
            f"EPS mismatch: expected {expected_eps}, got {actual_eps}"

    def test_handles_none_values_in_summation(self, report_generator):
        """Summation should treat None values as 0."""
        data = generate_okta_like_fiscal_year_data(4)

        # Set some values to None
        data['income_statement'][1]['netIncome'] = None
        data['cash_flow'][2]['freeCashFlow'] = None

        # Should not raise exception
        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'

        # Should have summed values (with None treated as 0)
        assert 'revenue' in annual_data[fy2024_key]['income']
        assert annual_data[fy2024_key]['income']['revenue'] > 0


class TestPointInTimeMetrics:
    """
    Tests for point-in-time metrics using most recent quarter value.

    Balance sheet items represent a snapshot at a point in time:
    - totalDebt, cashAndCashEquivalents
    - totalStockholdersEquity, totalAssets
    - totalCurrentAssets, totalCurrentLiabilities

    These should use the most recent quarter's value, not be summed.
    """

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator with mocked AWS dependencies."""
        with patch('investment_research.report_generator.boto3'):
            return ReportGenerator(use_api=False, prompt_version=4.2)

    def test_balance_sheet_uses_most_recent_quarter(self, report_generator):
        """Balance sheet should use Q4 (most recent) values, not sum."""
        data = generate_okta_like_fiscal_year_data(8)

        # Get the most recent Q4 balance sheet for FY2024
        # First item in list is most recent (Q4 FY2024)
        expected_debt = data['balance_sheet'][0]['totalDebt']
        expected_cash = data['balance_sheet'][0]['cashAndCashEquivalents']
        expected_equity = data['balance_sheet'][0]['totalStockholdersEquity']

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_balance = annual_data[fy2024_key]['balance']

        # Balance sheet values should NOT be summed
        assert actual_balance['totalDebt'] == expected_debt, \
            f"Debt should be most recent value {expected_debt}, not sum"
        assert actual_balance['cashAndCashEquivalents'] == expected_cash
        assert actual_balance['totalStockholdersEquity'] == expected_equity

    def test_balance_sheet_not_summed(self, report_generator):
        """Verify balance sheet values are NOT summed across quarters."""
        data = generate_jpm_like_calendar_fiscal_year_data(8)

        # If balance sheet were incorrectly summed, totalDebt would be
        # 300B * 4 = 1.2T instead of 300B
        single_quarter_debt = data['balance_sheet'][0]['totalDebt']
        summed_debt = sum(bs['totalDebt'] for bs in data['balance_sheet'][:4])

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'
        actual_debt = annual_data[fy2024_key]['balance']['totalDebt']

        # Should be single quarter value, not summed
        assert actual_debt == single_quarter_debt, \
            f"Debt should be {single_quarter_debt}, got {actual_debt}"
        assert actual_debt != summed_debt, \
            "Balance sheet values should NOT be summed"


# =============================================================================
# REPORT GENERATOR INITIALIZATION TESTS
# =============================================================================

class TestReportGeneratorInit:
    """Tests for ReportGenerator initialization and configuration."""

    def test_init_default_prompt_version(self):
        """Default prompt version should be 4.2."""
        with patch('investment_research.report_generator.boto3'):
            generator = ReportGenerator(use_api=False)
            assert generator.prompt_version == 4.2

    def test_init_accepts_valid_prompt_versions(self):
        """Should accept all valid prompt versions."""
        valid_versions = [1, 2, 3, 4, 4.2]

        with patch('investment_research.report_generator.boto3'):
            for version in valid_versions:
                generator = ReportGenerator(use_api=False, prompt_version=version)
                assert generator.prompt_version == version

    def test_init_rejects_invalid_prompt_version(self):
        """Should raise ValueError for invalid prompt version."""
        with patch('investment_research.report_generator.boto3'):
            with pytest.raises(ValueError) as exc_info:
                ReportGenerator(use_api=False, prompt_version=99)

            assert 'Invalid prompt_version' in str(exc_info.value)

    def test_init_api_mode_without_key_raises_error(self):
        """API mode without ANTHROPIC_API_KEY should raise ValueError."""
        with patch('investment_research.report_generator.boto3'):
            with patch.dict(os.environ, {}, clear=True):
                # Remove ANTHROPIC_API_KEY if present
                os.environ.pop('ANTHROPIC_API_KEY', None)

                with pytest.raises(ValueError) as exc_info:
                    ReportGenerator(use_api=True)

                assert 'ANTHROPIC_API_KEY' in str(exc_info.value)

    def test_init_non_api_mode_does_not_require_key(self):
        """Non-API mode should not require ANTHROPIC_API_KEY."""
        with patch('investment_research.report_generator.boto3'):
            with patch.dict(os.environ, {}, clear=True):
                os.environ.pop('ANTHROPIC_API_KEY', None)

                # Should not raise
                generator = ReportGenerator(use_api=False)
                assert generator.anthropic_client is None

    def test_prompt_version_stored_correctly(self):
        """PROMPT_VERSIONS dict should have correct mappings."""
        expected_versions = {
            1: 'investment_report_prompt.txt',
            2: 'investment_report_prompt_v2.txt',
            3: 'investment_report_prompt_v3.txt',
            4: 'investment_report_prompt_v4.txt',
            4.2: 'investment_report_prompt_v4_2.txt',
        }

        assert ReportGenerator.PROMPT_VERSIONS == expected_versions


class TestGetPromptDescription:
    """Tests for _get_prompt_description method."""

    def test_returns_correct_descriptions(self):
        """Should return correct human-readable descriptions."""
        with patch('investment_research.report_generator.boto3'):
            descriptions = {
                1: "Financial Grade",
                2: "Consumer Grade",
                3: "Balanced Grade",
                4: "Audit Grade v4.1",
                4.2: "Audit Grade v4.2",
            }

            for version, expected_substring in descriptions.items():
                generator = ReportGenerator(use_api=False, prompt_version=version)
                description = generator._get_prompt_description()
                assert expected_substring in description, \
                    f"Expected '{expected_substring}' in description for v{version}"


# =============================================================================
# EDGE CASES AND ERROR HANDLING
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator with mocked AWS dependencies."""
        with patch('investment_research.report_generator.boto3'):
            return ReportGenerator(use_api=False, prompt_version=4.2)

    def test_empty_data_returns_empty_dict(self, report_generator):
        """Empty input data should return empty annual_data."""
        annual_data = report_generator._aggregate_annual_data([], [], [])
        assert annual_data == {}

    def test_missing_income_statements(self, report_generator):
        """Should handle missing income statements gracefully."""
        data = generate_jpm_like_calendar_fiscal_year_data(4)

        annual_data = report_generator._aggregate_annual_data(
            [],  # Empty income statements
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should return empty since income_statements drive the grouping
        assert annual_data == {}

    def test_missing_balance_sheets(self, report_generator):
        """Should handle missing balance sheets gracefully."""
        data = generate_jpm_like_calendar_fiscal_year_data(4)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            [],  # Empty balance sheets
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'

        # Should still have income data
        assert annual_data[fy2024_key]['income']['revenue'] > 0
        # Balance should be empty dict
        assert annual_data[fy2024_key]['balance'] == {}

    def test_missing_cash_flows(self, report_generator):
        """Should handle missing cash flows gracefully."""
        data = generate_jpm_like_calendar_fiscal_year_data(4)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            []  # Empty cash flows
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'

        # Should still have income and balance data
        assert annual_data[fy2024_key]['income']['revenue'] > 0
        assert annual_data[fy2024_key]['balance']['totalDebt'] > 0
        # Cashflow should be empty or have minimal data
        assert annual_data[fy2024_key]['cashflow'] == {}

    def test_partial_quarters(self, report_generator):
        """Should handle fiscal years with fewer than 4 quarters."""
        data = generate_okta_like_fiscal_year_data(6)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # FY2024 should have 4 quarters
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        assert annual_data[fy2024_key]['quarters_count'] == 4

        # FY2023 should have only 2 quarters
        fy2023_key = 2023 if 2023 in annual_data else '2023'
        assert annual_data[fy2023_key]['quarters_count'] == 2

    def test_handles_decimal_values(self, report_generator):
        """Should handle Decimal values from DynamoDB."""
        data = generate_okta_like_fiscal_year_data(4)

        # Convert some values to Decimal (simulating DynamoDB data)
        data['income_statement'][0]['revenue'] = Decimal('500000000')
        data['income_statement'][0]['netIncome'] = Decimal('25000000')
        data['balance_sheet'][0]['totalDebt'] = Decimal('2000000000')

        # Should not raise exception
        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        fy2024_key = 2024 if 2024 in annual_data else '2024'

        # Values should be converted to float
        assert isinstance(annual_data[fy2024_key]['income']['revenue'], (int, float))

    def test_unknown_date_format_skipped(self, report_generator):
        """Records with Unknown year should be skipped."""
        data = generate_okta_like_fiscal_year_data(4)

        # Add a record with no year info
        data['income_statement'].append({
            # No date, fiscalYear, or calendarYear
            'revenue': 100_000_000,
            'netIncome': 5_000_000,
        })

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should not include 'Unknown' as a year key
        assert 'Unknown' not in annual_data

    def test_very_old_data_limited_to_20_quarters(self, report_generator):
        """Should only process first 20 quarters of data."""
        # Generate more than 20 quarters
        data = {
            'income_statement': [],
            'balance_sheet': [],
            'cash_flow': [],
        }

        for i in range(30):
            year = 2024 - (i // 4)
            data['income_statement'].append({
                'date': f'{year}-12-31',
                'fiscalYear': year,
                'revenue': 1_000_000_000,
                'netIncome': 100_000_000,
            })
            data['balance_sheet'].append({
                'date': f'{year}-12-31',
                'fiscalYear': year,
                'totalDebt': 500_000_000,
                'cashAndCashEquivalents': 300_000_000,
                'totalStockholdersEquity': 2_000_000_000,
            })
            data['cash_flow'].append({
                'date': f'{year}-12-31',
                'fiscalYear': year,
                'operatingCashFlow': 150_000_000,
                'freeCashFlow': 100_000_000,
            })

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # Should have at most 5 years (20 quarters / 4)
        assert len(annual_data) <= 5


# =============================================================================
# PREPARE_DATA METHOD TESTS
# =============================================================================

class TestPrepareData:
    """Tests for the prepare_data method."""

    @pytest.fixture
    def mock_financial_data(self):
        """Create mock financial data response."""
        return {
            'raw_financials': generate_jpm_like_calendar_fiscal_year_data(8),
            'currency_info': {'code': 'USD', 'usd_rate': 1.0},
        }

    def test_prepare_data_returns_expected_structure(self, mock_financial_data):
        """prepare_data should return dict with expected keys."""
        with patch('investment_research.report_generator.boto3'):
            with patch('investment_research.report_generator.get_financial_data') as mock_get:
                mock_get.return_value = mock_financial_data

                with patch('investment_research.report_generator.extract_all_features') as mock_extract:
                    mock_extract.return_value = {'debt': {}, 'cashflow': {}, 'growth': {}}

                    with patch('investment_research.report_generator.extract_quarterly_trends') as mock_trends:
                        mock_trends.return_value = {}

                        generator = ReportGenerator(use_api=False)
                        result = generator.prepare_data('JPM')

                        assert 'ticker' in result
                        assert 'fiscal_year' in result
                        assert 'metrics_context' in result
                        assert 'features' in result
                        assert 'raw_financials' in result
                        assert 'currency_info' in result

    def test_prepare_data_uppercases_ticker(self, mock_financial_data):
        """prepare_data should uppercase the ticker symbol."""
        with patch('investment_research.report_generator.boto3'):
            with patch('investment_research.report_generator.get_financial_data') as mock_get:
                mock_get.return_value = mock_financial_data

                with patch('investment_research.report_generator.extract_all_features') as mock_extract:
                    mock_extract.return_value = {}

                    with patch('investment_research.report_generator.extract_quarterly_trends') as mock_trends:
                        mock_trends.return_value = {}

                        generator = ReportGenerator(use_api=False)
                        result = generator.prepare_data('jpm')  # lowercase

                        assert result['ticker'] == 'JPM'  # uppercase

    def test_prepare_data_raises_on_no_data(self):
        """prepare_data should raise ValueError when no data available."""
        with patch('investment_research.report_generator.boto3'):
            with patch('investment_research.report_generator.get_financial_data') as mock_get:
                mock_get.return_value = None

                generator = ReportGenerator(use_api=False)

                with pytest.raises(ValueError) as exc_info:
                    generator.prepare_data('INVALID')

                assert 'No financial data' in str(exc_info.value)

    def test_prepare_data_defaults_to_current_year(self, mock_financial_data):
        """prepare_data should default fiscal_year to current year."""
        with patch('investment_research.report_generator.boto3'):
            with patch('investment_research.report_generator.get_financial_data') as mock_get:
                mock_get.return_value = mock_financial_data

                with patch('investment_research.report_generator.extract_all_features') as mock_extract:
                    mock_extract.return_value = {}

                    with patch('investment_research.report_generator.extract_quarterly_trends') as mock_trends:
                        mock_trends.return_value = {}

                        generator = ReportGenerator(use_api=False)
                        result = generator.prepare_data('JPM')  # No fiscal_year specified

                        assert result['fiscal_year'] == datetime.now().year


# =============================================================================
# INTEGRATION-STYLE TESTS (Still mocked, but testing more complete flows)
# =============================================================================

class TestAggregationIntegration:
    """Integration-style tests for the full aggregation flow."""

    @pytest.fixture
    def report_generator(self):
        """Create ReportGenerator with mocked AWS dependencies."""
        with patch('investment_research.report_generator.boto3'):
            return ReportGenerator(use_api=False, prompt_version=4.2)

    def test_full_aggregation_flow_okta(self, report_generator):
        """
        Full test of OKTA-like fiscal year aggregation.

        Verifies:
        1. Quarters grouped by fiscalYear (not calendar)
        2. Flow metrics summed correctly
        3. Balance sheet uses most recent quarter
        4. quarters_count tracks data completeness
        """
        data = generate_okta_like_fiscal_year_data(8)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # FY2024 validation
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        fy2024 = annual_data[fy2024_key]

        # 1. Should have exactly 4 quarters
        assert fy2024['quarters_count'] == 4

        # 2. Flow metrics should be summed
        expected_revenue = sum(s['revenue'] for s in data['income_statement'][:4])
        assert fy2024['income']['revenue'] == expected_revenue

        expected_ocf = sum(cf['operatingCashFlow'] for cf in data['cash_flow'][:4])
        assert fy2024['cashflow']['operatingCashFlow'] == expected_ocf

        # 3. Balance sheet should be Q4 (most recent) values
        assert fy2024['balance']['totalDebt'] == data['balance_sheet'][0]['totalDebt']

        # FY2023 validation
        fy2023_key = 2023 if 2023 in annual_data else '2023'
        fy2023 = annual_data[fy2023_key]

        assert fy2023['quarters_count'] == 4
        expected_fy2023_revenue = sum(s['revenue'] for s in data['income_statement'][4:8])
        assert fy2023['income']['revenue'] == expected_fy2023_revenue

    def test_full_aggregation_flow_jpm(self, report_generator):
        """
        Full test of JPM-like calendar fiscal year aggregation.

        For calendar year companies, behavior should be identical
        whether using fiscalYear or calendarYear.
        """
        data = generate_jpm_like_calendar_fiscal_year_data(8)

        annual_data = report_generator._aggregate_annual_data(
            data['income_statement'],
            data['balance_sheet'],
            data['cash_flow']
        )

        # FY2024 validation
        fy2024_key = 2024 if 2024 in annual_data else '2024'
        fy2024 = annual_data[fy2024_key]

        # Should have 4 quarters
        assert fy2024['quarters_count'] == 4

        # Flow metrics summed
        expected_revenue = sum(s['revenue'] for s in data['income_statement'][:4])
        assert fy2024['income']['revenue'] == expected_revenue

        # Balance sheet point-in-time
        assert fy2024['balance']['totalDebt'] == 300_000_000_000
        assert fy2024['balance']['cashAndCashEquivalents'] == 500_000_000_000


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
