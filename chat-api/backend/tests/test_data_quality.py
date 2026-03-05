"""
Tests for the DataQualityValidator.

Tests internal consistency checks and completeness scoring
without requiring AWS credentials or API calls.
"""

import pytest
from src.utils.data_quality import DataQualityValidator


def _make_quarter(date, period='Q1', **overrides):
    """Helper to create a quarter of financial data with reasonable defaults."""
    base = {
        'date': date,
        'period': period,
        'fiscalYear': int(date[:4]),
    }
    base.update(overrides)
    return base


def _make_balance_sheet(date, period='Q1', **overrides):
    """Create a consistent balance sheet quarter."""
    defaults = {
        'totalAssets': 100_000_000,
        'totalLiabilities': 60_000_000,
        'totalStockholdersEquity': 40_000_000,
        'totalCurrentAssets': 30_000_000,
        'totalCurrentLiabilities': 20_000_000,
        'totalDebt': 25_000_000,
        'cashAndCashEquivalents': 10_000_000,
        'shortTermDebt': 5_000_000,
        'longTermDebt': 20_000_000,
    }
    defaults.update(overrides)
    return _make_quarter(date, period, **defaults)


def _make_income_statement(date, period='Q1', **overrides):
    """Create a consistent income statement quarter."""
    defaults = {
        'revenue': 50_000_000,
        'costOfRevenue': 30_000_000,
        'grossProfit': 20_000_000,
        'operatingExpenses': 10_000_000,
        'operatingIncome': 10_000_000,
        'netIncome': 7_000_000,
        'ebitda': 15_000_000,
        'eps': 1.50,
        'interestExpense': 1_000_000,
        'incomeTaxExpense': 2_000_000,
        'weightedAverageShsOut': 100_000_000,
        'weightedAverageShsOutDil': 105_000_000,
    }
    defaults.update(overrides)
    return _make_quarter(date, period, **defaults)


def _make_cash_flow(date, period='Q1', **overrides):
    """Create a consistent cash flow statement quarter."""
    defaults = {
        'operatingCashFlow': 12_000_000,
        'capitalExpenditure': -3_000_000,
        'freeCashFlow': 9_000_000,
        'stockBasedCompensation': 1_000_000,
        'commonDividendsPaid': -2_000_000,
        'commonStockRepurchased': -1_000_000,
        'netIncome': 7_000_000,
    }
    defaults.update(overrides)
    return _make_quarter(date, period, **defaults)


def _make_raw_financials(num_quarters=20):
    """Create a full set of consistent raw financials."""
    quarters = [f'202{5 - i // 4}-{["03", "06", "09", "12"][i % 4]}-30' for i in range(num_quarters)]
    periods = [f'Q{(i % 4) + 1}' for i in range(num_quarters)]
    return {
        'balance_sheet': [_make_balance_sheet(q, p) for q, p in zip(quarters, periods)],
        'income_statement': [_make_income_statement(q, p) for q, p in zip(quarters, periods)],
        'cash_flow': [_make_cash_flow(q, p) for q, p in zip(quarters, periods)],
    }


class TestDataQualityValidatorPerfectData:
    """Tests with perfect, internally consistent data."""

    def test_perfect_data_gets_high_score(self):
        raw = _make_raw_financials(20)
        report = DataQualityValidator(raw).validate()
        assert report['overall_score'] >= 0.90
        errors = [i for i in report['consistency_issues'] if i['severity'] == 'error']
        assert len(errors) == 0

    def test_completeness_all_quarters(self):
        raw = _make_raw_financials(20)
        report = DataQualityValidator(raw).validate()
        assert report['completeness']['quarter_coverage'] == 1.0

    def test_summary_contains_grade(self):
        raw = _make_raw_financials(20)
        report = DataQualityValidator(raw).validate()
        assert 'Data Quality Grade:' in report['summary']


class TestCompletenessScoring:
    """Tests for completeness detection."""

    def test_few_quarters_lowers_score(self):
        raw = _make_raw_financials(8)
        report = DataQualityValidator(raw).validate()
        assert report['completeness']['quarter_coverage'] < 1.0
        assert report['completeness']['quarters_available']['balance_sheet'] == 8

    def test_very_few_quarters_raises_error(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        issues = [i for i in report['consistency_issues'] if i['check'] == 'quarter_coverage']
        assert any(i['severity'] == 'error' for i in issues)

    def test_missing_fields_detected(self):
        raw = _make_raw_financials(20)
        # Remove a field from all quarters
        for bs in raw['balance_sheet']:
            del bs['shortTermDebt']
        report = DataQualityValidator(raw).validate()
        bs_missing = report['completeness']['balance_sheet']['missing_fields']
        assert 'shortTermDebt' in bs_missing

    def test_empty_statements_score_zero(self):
        raw = {'balance_sheet': [], 'income_statement': [], 'cash_flow': []}
        report = DataQualityValidator(raw).validate()
        assert report['completeness']['overall_completeness'] == 0.0


class TestBalanceSheetIdentity:
    """Tests for Assets = Liabilities + Equity check."""

    def test_consistent_balance_sheet_passes(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        bs_issues = [i for i in report['consistency_issues'] if i['check'] == 'balance_sheet_identity']
        assert len(bs_issues) == 0

    def test_mismatched_balance_sheet_flagged(self):
        raw = _make_raw_financials(4)
        # Break the identity: assets doesn't equal liabilities + equity
        raw['balance_sheet'][0]['totalAssets'] = 200_000_000  # was 100M
        report = DataQualityValidator(raw).validate()
        bs_issues = [i for i in report['consistency_issues'] if i['check'] == 'balance_sheet_identity']
        assert len(bs_issues) == 1
        assert bs_issues[0]['severity'] == 'error'

    def test_small_rounding_difference_passes(self):
        raw = _make_raw_financials(4)
        # Small rounding: within $1000 tolerance
        raw['balance_sheet'][0]['totalAssets'] = 100_000_500
        report = DataQualityValidator(raw).validate()
        bs_issues = [i for i in report['consistency_issues'] if i['check'] == 'balance_sheet_identity']
        assert len(bs_issues) == 0


class TestDebtBreakdown:
    """Tests for totalDebt ~= shortTermDebt + longTermDebt."""

    def test_consistent_debt_passes(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        debt_issues = [i for i in report['consistency_issues'] if i['check'] == 'debt_breakdown']
        assert len(debt_issues) == 0

    def test_mismatched_debt_flagged(self):
        raw = _make_raw_financials(4)
        # totalDebt doesn't match short + long
        raw['balance_sheet'][0]['totalDebt'] = 50_000_000  # was 25M (5M + 20M)
        report = DataQualityValidator(raw).validate()
        debt_issues = [i for i in report['consistency_issues'] if i['check'] == 'debt_breakdown']
        assert len(debt_issues) == 1


class TestIncomeStatementConsistency:
    """Tests for income statement relationships."""

    def test_gross_profit_consistency(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        gp_issues = [i for i in report['consistency_issues'] if i['check'] == 'gross_profit_calc']
        assert len(gp_issues) == 0

    def test_gross_profit_mismatch_flagged(self):
        raw = _make_raw_financials(4)
        # Break: grossProfit != revenue - costOfRevenue
        raw['income_statement'][0]['grossProfit'] = 30_000_000  # should be 20M
        report = DataQualityValidator(raw).validate()
        gp_issues = [i for i in report['consistency_issues'] if i['check'] == 'gross_profit_calc']
        assert len(gp_issues) == 1

    def test_diluted_less_than_basic_flagged(self):
        raw = _make_raw_financials(4)
        # Diluted should never be less than basic
        raw['income_statement'][0]['weightedAverageShsOutDil'] = 90_000_000  # less than 100M basic
        report = DataQualityValidator(raw).validate()
        share_issues = [i for i in report['consistency_issues'] if i['check'] == 'share_count']
        assert len(share_issues) == 1


class TestCashFlowConsistency:
    """Tests for FCF = OCF - CapEx."""

    def test_consistent_fcf_passes(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        fcf_issues = [i for i in report['consistency_issues'] if i['check'] == 'fcf_calc']
        assert len(fcf_issues) == 0

    def test_inconsistent_fcf_flagged(self):
        raw = _make_raw_financials(4)
        # FCF doesn't match OCF - CapEx
        raw['cash_flow'][0]['freeCashFlow'] = 20_000_000  # should be 9M (12M - 3M)
        report = DataQualityValidator(raw).validate()
        fcf_issues = [i for i in report['consistency_issues'] if i['check'] == 'fcf_calc']
        assert len(fcf_issues) == 1


class TestCrossStatementConsistency:
    """Tests for cross-statement checks."""

    def test_matching_net_income_passes(self):
        raw = _make_raw_financials(4)
        report = DataQualityValidator(raw).validate()
        cross_issues = [i for i in report['consistency_issues'] if i['check'] == 'cross_statement_net_income']
        assert len(cross_issues) == 0

    def test_mismatched_net_income_flagged(self):
        raw = _make_raw_financials(4)
        # Net income in cash flow doesn't match income statement
        raw['cash_flow'][0]['netIncome'] = 15_000_000  # income stmt has 7M
        report = DataQualityValidator(raw).validate()
        cross_issues = [i for i in report['consistency_issues'] if i['check'] == 'cross_statement_net_income']
        assert len(cross_issues) == 1


class TestSanityBounds:
    """Tests for sanity bound checks."""

    def test_negative_assets_flagged(self):
        raw = _make_raw_financials(4)
        raw['balance_sheet'][0]['totalAssets'] = -1_000_000
        report = DataQualityValidator(raw).validate()
        sanity_issues = [i for i in report['consistency_issues'] if i['check'] == 'sanity_negative_assets']
        assert len(sanity_issues) == 1

    def test_negative_revenue_flagged(self):
        raw = _make_raw_financials(4)
        raw['income_statement'][0]['revenue'] = -500_000
        report = DataQualityValidator(raw).validate()
        sanity_issues = [i for i in report['consistency_issues'] if i['check'] == 'sanity_negative_revenue']
        assert len(sanity_issues) == 1

    def test_zero_revenue_flagged_as_info(self):
        raw = _make_raw_financials(4)
        raw['income_statement'][0]['revenue'] = 0
        report = DataQualityValidator(raw).validate()
        sanity_issues = [i for i in report['consistency_issues'] if i['check'] == 'sanity_zero_revenue']
        assert len(sanity_issues) == 1
        assert sanity_issues[0]['severity'] == 'info'

    def test_extreme_leverage_flagged_as_info(self):
        raw = _make_raw_financials(4)
        raw['balance_sheet'][0]['totalDebt'] = 5_000_000_000
        raw['balance_sheet'][0]['totalStockholdersEquity'] = 10_000_000
        report = DataQualityValidator(raw).validate()
        sanity_issues = [i for i in report['consistency_issues'] if i['check'] == 'sanity_extreme_leverage']
        assert len(sanity_issues) == 1
        assert sanity_issues[0]['severity'] == 'info'

    def test_invalid_shares_flagged(self):
        raw = _make_raw_financials(4)
        raw['income_statement'][0]['weightedAverageShsOut'] = 0
        report = DataQualityValidator(raw).validate()
        sanity_issues = [i for i in report['consistency_issues'] if i['check'] == 'sanity_invalid_shares']
        assert len(sanity_issues) == 1


class TestOverallScoring:
    """Tests for the overall scoring mechanism."""

    def test_errors_lower_score_more_than_warnings(self):
        # Data with an error
        raw_error = _make_raw_financials(20)
        raw_error['balance_sheet'][0]['totalAssets'] = 200_000_000
        report_error = DataQualityValidator(raw_error).validate()

        # Data with a warning (debt breakdown mismatch)
        raw_warning = _make_raw_financials(20)
        raw_warning['balance_sheet'][0]['totalDebt'] = 30_000_000  # slight mismatch
        report_warning = DataQualityValidator(raw_warning).validate()

        assert report_warning['overall_score'] >= report_error['overall_score']

    def test_multiple_issues_compound(self):
        raw_clean = _make_raw_financials(20)
        score_clean = DataQualityValidator(raw_clean).validate()['overall_score']

        raw_dirty = _make_raw_financials(20)
        for i in range(5):
            raw_dirty['balance_sheet'][i]['totalAssets'] = 200_000_000
        score_dirty = DataQualityValidator(raw_dirty).validate()['overall_score']

        assert score_dirty < score_clean
