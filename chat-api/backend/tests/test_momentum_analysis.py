"""
Unit tests for momentum analysis helper functions in report_generator.py

Tests the trend detection logic for:
- Growth momentum and deceleration
- Margin compression
- Debt health trends
- Cash flow trends
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from investment_research.report_generator import ReportGenerator


class TestMomentumAnalysis:
    """Tests for _calculate_momentum_metrics() function."""

    @pytest.fixture
    def generator(self):
        """Create a ReportGenerator instance for testing."""
        # Don't use API mode for unit tests
        return ReportGenerator(use_api=False)

    def test_detects_growth_deceleration(self, generator):
        """Should flag when YoY growth drops significantly from peak."""
        # Mock income statements with declining growth
        # Q3 2025: 4% YoY growth (down from 25% peak)
        # Q4 2024: 25% YoY growth (peak) - need >15pp deceleration
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20800000000},  # Q3 2025: +4% YoY
            {'date': '2025-06-30', 'revenue': 21500000000},  # Q2 2025: +7.5% YoY
            {'date': '2025-03-31', 'revenue': 23000000000},  # Q1 2025: +15% YoY
            {'date': '2024-12-31', 'revenue': 25000000000},  # Q4 2024: +25% YoY (peak)
            {'date': '2024-09-30', 'revenue': 20000000000},  # Q3 2024: base
            {'date': '2024-06-30', 'revenue': 20000000000},  # Q2 2024: base
            {'date': '2024-03-31', 'revenue': 20000000000},  # Q1 2024: base
            {'date': '2023-12-31', 'revenue': 20000000000},  # Q4 2023: base
        ]

        result = generator._calculate_momentum_metrics(income_statements)

        assert result['current_growth_rate'] == 4.0
        assert result['peak_growth_rate'] == 25.0
        assert result['deceleration_magnitude'] == 21.0
        assert result['is_decelerating'] == True
        assert len(result['warnings']) > 0

    def test_no_false_positive_on_stable_growth(self, generator):
        """Should not flag normal growth fluctuations."""
        # Mock income statements with stable ~20% growth
        income_statements = [
            {'date': '2025-09-30', 'revenue': 24000000000},  # +20% YoY
            {'date': '2025-06-30', 'revenue': 23500000000},  # +18% YoY
            {'date': '2025-03-31', 'revenue': 24200000000},  # +21% YoY
            {'date': '2024-12-31', 'revenue': 23800000000},  # +19% YoY
            {'date': '2024-09-30', 'revenue': 20000000000},  # base
            {'date': '2024-06-30', 'revenue': 19915000000},  # base
            {'date': '2024-03-31', 'revenue': 20000000000},  # base
            {'date': '2023-12-31', 'revenue': 20000000000},  # base
        ]

        result = generator._calculate_momentum_metrics(income_statements)

        # Small fluctuations shouldn't trigger deceleration flag
        assert result['is_decelerating'] == False

    def test_counts_consecutive_qoq_declines(self, generator):
        """Should count sequential revenue declines."""
        # 3 quarters of declining revenue
        income_statements = [
            {'date': '2025-09-30', 'revenue': 18000000000},  # -10% QoQ
            {'date': '2025-06-30', 'revenue': 20000000000},  # -5% QoQ
            {'date': '2025-03-31', 'revenue': 21000000000},  # -5% QoQ
            {'date': '2024-12-31', 'revenue': 22000000000},  # base
            {'date': '2024-09-30', 'revenue': 20000000000},
            {'date': '2024-06-30', 'revenue': 20000000000},
            {'date': '2024-03-31', 'revenue': 20000000000},
            {'date': '2023-12-31', 'revenue': 20000000000},
        ]

        result = generator._calculate_momentum_metrics(income_statements)

        assert result['consecutive_qoq_declines'] == 3
        assert any('declined' in w.lower() for w in result['warnings'])

    def test_handles_missing_data_gracefully(self, generator):
        """Should not crash on incomplete data."""
        # Only 2 quarters of data (insufficient)
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000},
            {'date': '2025-06-30', 'revenue': 19000000000},
        ]

        result = generator._calculate_momentum_metrics(income_statements)

        # Should return safe defaults without crashing
        assert result['is_decelerating'] == False
        assert 'Insufficient data' in result['warnings'][0]


class TestMarginCompression:
    """Tests for _check_margin_compression() function."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(use_api=False)

    def test_detects_margin_compression(self, generator):
        """Should flag when gross margin drops >3pp YoY."""
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000, 'grossProfit': 15200000000, 'netIncome': 5000000000},  # 76% GM
            {'date': '2025-06-30', 'revenue': 20000000000, 'grossProfit': 15600000000, 'netIncome': 5200000000},
            {'date': '2025-03-31', 'revenue': 20000000000, 'grossProfit': 16000000000, 'netIncome': 5400000000},
            {'date': '2024-12-31', 'revenue': 20000000000, 'grossProfit': 16400000000, 'netIncome': 5600000000},
            {'date': '2024-09-30', 'revenue': 20000000000, 'grossProfit': 16800000000, 'netIncome': 6000000000},  # 84% GM (YoY)
            {'date': '2024-06-30', 'revenue': 20000000000, 'grossProfit': 16600000000, 'netIncome': 5800000000},
            {'date': '2024-03-31', 'revenue': 20000000000, 'grossProfit': 16400000000, 'netIncome': 5600000000},
            {'date': '2023-12-31', 'revenue': 20000000000, 'grossProfit': 16200000000, 'netIncome': 5400000000},
        ]

        result = generator._check_margin_compression(income_statements)

        assert result['gross_margin_current'] == 76.0
        assert result['gross_margin_yoy'] == 84.0
        assert result['gross_margin_change'] == -8.0
        assert result['is_compressing'] == True
        assert len(result['warnings']) > 0

    def test_no_flag_on_stable_margins(self, generator):
        """Should not flag when margins are stable."""
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000, 'grossProfit': 16000000000, 'netIncome': 5000000000},  # 80%
            {'date': '2025-06-30', 'revenue': 20000000000, 'grossProfit': 16200000000, 'netIncome': 5100000000},
            {'date': '2025-03-31', 'revenue': 20000000000, 'grossProfit': 15800000000, 'netIncome': 4900000000},
            {'date': '2024-12-31', 'revenue': 20000000000, 'grossProfit': 16000000000, 'netIncome': 5000000000},
            {'date': '2024-09-30', 'revenue': 20000000000, 'grossProfit': 16200000000, 'netIncome': 5100000000},  # 81% (YoY)
        ]

        result = generator._check_margin_compression(income_statements)

        # 1pp change should not trigger compression flag
        assert result['is_compressing'] == False


class TestDebtTrends:
    """Tests for _check_debt_trends() function."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(use_api=False)

    def test_detects_rising_leverage(self, generator):
        """Should flag when D/E ratio increases significantly."""
        # D/E must increase by >0.2x (comparing avg of first 2 vs avg of last 2)
        # Recent avg: (0.7 + 0.65) / 2 = 0.675
        # Older avg: (0.4 + 0.25) / 2 = 0.325
        # Change: 0.675 - 0.325 = 0.35 > 0.2 ✓
        balance_sheets = [
            {'date': '2025-09-30', 'totalDebt': 70000000000, 'cashAndCashEquivalents': 10000000000, 'totalStockholdersEquity': 100000000000},  # 0.7x
            {'date': '2025-06-30', 'totalDebt': 65000000000, 'cashAndCashEquivalents': 12000000000, 'totalStockholdersEquity': 100000000000},  # 0.65x
            {'date': '2025-03-31', 'totalDebt': 40000000000, 'cashAndCashEquivalents': 15000000000, 'totalStockholdersEquity': 100000000000},  # 0.4x
            {'date': '2024-12-31', 'totalDebt': 25000000000, 'cashAndCashEquivalents': 20000000000, 'totalStockholdersEquity': 100000000000},  # 0.25x
        ]
        income_statements = [
            {'date': '2025-09-30', 'operatingIncome': 5000000000, 'interestExpense': 1000000000},
            {'date': '2025-06-30', 'operatingIncome': 5200000000, 'interestExpense': 900000000},
            {'date': '2025-03-31', 'operatingIncome': 5400000000, 'interestExpense': 800000000},
            {'date': '2024-12-31', 'operatingIncome': 5600000000, 'interestExpense': 500000000},
        ]

        result = generator._check_debt_trends(balance_sheets, income_statements)

        assert result['debt_equity_trend'] == 'increasing'
        assert any('increased' in w.lower() or 'ratio' in w.lower() for w in result['warnings'])

    def test_detects_deleveraging(self, generator):
        """Should identify when company is paying down debt."""
        # D/E must decrease by >0.2x (comparing avg of first 2 vs avg of last 2)
        # Recent avg: (0.15 + 0.20) / 2 = 0.175
        # Older avg: (0.40 + 0.50) / 2 = 0.45
        # Change: 0.175 - 0.45 = -0.275 < -0.2 ✓
        balance_sheets = [
            {'date': '2025-09-30', 'totalDebt': 15000000000, 'cashAndCashEquivalents': 30000000000, 'totalStockholdersEquity': 100000000000},  # 0.15x
            {'date': '2025-06-30', 'totalDebt': 20000000000, 'cashAndCashEquivalents': 25000000000, 'totalStockholdersEquity': 100000000000},  # 0.20x
            {'date': '2025-03-31', 'totalDebt': 40000000000, 'cashAndCashEquivalents': 20000000000, 'totalStockholdersEquity': 100000000000},  # 0.40x
            {'date': '2024-12-31', 'totalDebt': 50000000000, 'cashAndCashEquivalents': 15000000000, 'totalStockholdersEquity': 100000000000},  # 0.50x
        ]
        income_statements = [
            {'date': '2025-09-30', 'operatingIncome': 10000000000, 'interestExpense': 500000000},
            {'date': '2025-06-30', 'operatingIncome': 10000000000, 'interestExpense': 600000000},
            {'date': '2025-03-31', 'operatingIncome': 10000000000, 'interestExpense': 700000000},
            {'date': '2024-12-31', 'operatingIncome': 10000000000, 'interestExpense': 900000000},
        ]

        result = generator._check_debt_trends(balance_sheets, income_statements)

        assert result['debt_equity_trend'] == 'improving'


class TestCashflowTrends:
    """Tests for _check_cashflow_trends() function."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(use_api=False)

    def test_detects_consecutive_negative_fcf(self, generator):
        """Should flag multiple quarters of negative free cash flow."""
        cash_flows = [
            {'date': '2025-09-30', 'operatingCashFlow': 2000000000, 'freeCashFlow': -1000000000, 'capitalExpenditure': -3000000000},
            {'date': '2025-06-30', 'operatingCashFlow': 1500000000, 'freeCashFlow': -2000000000, 'capitalExpenditure': -3500000000},
            {'date': '2025-03-31', 'operatingCashFlow': 3000000000, 'freeCashFlow': 500000000, 'capitalExpenditure': -2500000000},
            {'date': '2024-12-31', 'operatingCashFlow': 4000000000, 'freeCashFlow': 1500000000, 'capitalExpenditure': -2500000000},
        ]
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000, 'netIncome': 3000000000},
            {'date': '2025-06-30', 'revenue': 20000000000, 'netIncome': 2500000000},
            {'date': '2025-03-31', 'revenue': 20000000000, 'netIncome': 3500000000},
            {'date': '2024-12-31', 'revenue': 20000000000, 'netIncome': 4000000000},
        ]

        result = generator._check_cashflow_trends(cash_flows, income_statements)

        assert result['consecutive_negative_fcf'] == 2
        assert any('negative' in w.lower() for w in result['warnings'])

    def test_detects_weak_cash_conversion(self, generator):
        """Should flag when OCF/Net Income ratio is low."""
        # Need at least 4 quarters for the function to process (returns early otherwise)
        cash_flows = [
            {'date': '2025-09-30', 'operatingCashFlow': 2000000000, 'freeCashFlow': 1000000000, 'capitalExpenditure': -1000000000},
            {'date': '2025-06-30', 'operatingCashFlow': 2200000000, 'freeCashFlow': 1200000000, 'capitalExpenditure': -1000000000},
            {'date': '2025-03-31', 'operatingCashFlow': 2100000000, 'freeCashFlow': 1100000000, 'capitalExpenditure': -1000000000},
            {'date': '2024-12-31', 'operatingCashFlow': 2300000000, 'freeCashFlow': 1300000000, 'capitalExpenditure': -1000000000},
        ]
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000, 'netIncome': 5000000000},  # OCF is only 40% of NI
            {'date': '2025-06-30', 'revenue': 20000000000, 'netIncome': 4800000000},
            {'date': '2025-03-31', 'revenue': 20000000000, 'netIncome': 4600000000},
            {'date': '2024-12-31', 'revenue': 20000000000, 'netIncome': 4400000000},
        ]

        result = generator._check_cashflow_trends(cash_flows, income_statements)

        # OCF: 2000+2200+2100+2300 = 8600, NI: 5000+4800+4600+4400 = 18800
        # Ratio: 8600/18800 = 0.457 ≈ 0.46 (rounded)
        assert result['ocf_ni_ratio'] == 0.46
        assert any('weak' in w.lower() or 'conversion' in w.lower() for w in result['warnings'])

    def test_healthy_cash_flow_no_warnings(self, generator):
        """Should not flag healthy cash flow metrics."""
        cash_flows = [
            {'date': '2025-09-30', 'operatingCashFlow': 8000000000, 'freeCashFlow': 5000000000, 'capitalExpenditure': -3000000000},
            {'date': '2025-06-30', 'operatingCashFlow': 7500000000, 'freeCashFlow': 4500000000, 'capitalExpenditure': -3000000000},
            {'date': '2025-03-31', 'operatingCashFlow': 7000000000, 'freeCashFlow': 4000000000, 'capitalExpenditure': -3000000000},
            {'date': '2024-12-31', 'operatingCashFlow': 7200000000, 'freeCashFlow': 4200000000, 'capitalExpenditure': -3000000000},
        ]
        income_statements = [
            {'date': '2025-09-30', 'revenue': 20000000000, 'netIncome': 5000000000},
            {'date': '2025-06-30', 'revenue': 20000000000, 'netIncome': 4800000000},
            {'date': '2025-03-31', 'revenue': 20000000000, 'netIncome': 4500000000},
            {'date': '2024-12-31', 'revenue': 20000000000, 'netIncome': 4600000000},
        ]

        result = generator._check_cashflow_trends(cash_flows, income_statements)

        assert result['consecutive_negative_fcf'] == 0
        assert result['fcf_trend'] != 'deteriorating'


class TestFormattedOutput:
    """Integration tests for formatted output."""

    @pytest.fixture
    def generator(self):
        return ReportGenerator(use_api=False)

    def test_momentum_appears_in_formatted_output(self, generator):
        """Verify momentum section appears in prompt context."""
        # Create minimal mock data
        features = {'debt': {}, 'cashflow': {}, 'growth': {}}
        trends = {}
        raw_financials = {
            'income_statement': [
                {'date': '2025-09-30', 'calendarYear': '2025', 'revenue': 20000000000, 'grossProfit': 8000000000, 'netIncome': 3000000000, 'operatingIncome': 5000000000, 'interestExpense': 500000000, 'eps': 2.50},
                {'date': '2025-06-30', 'calendarYear': '2025', 'revenue': 21000000000, 'grossProfit': 8400000000, 'netIncome': 3200000000, 'operatingIncome': 5200000000, 'interestExpense': 500000000, 'eps': 2.60},
                {'date': '2025-03-31', 'calendarYear': '2025', 'revenue': 22000000000, 'grossProfit': 8800000000, 'netIncome': 3400000000, 'operatingIncome': 5400000000, 'interestExpense': 500000000, 'eps': 2.70},
                {'date': '2024-12-31', 'calendarYear': '2024', 'revenue': 23000000000, 'grossProfit': 9200000000, 'netIncome': 3600000000, 'operatingIncome': 5600000000, 'interestExpense': 500000000, 'eps': 2.80},
                {'date': '2024-09-30', 'calendarYear': '2024', 'revenue': 18000000000, 'grossProfit': 7200000000, 'netIncome': 2800000000, 'operatingIncome': 4400000000, 'interestExpense': 500000000, 'eps': 2.20},
                {'date': '2024-06-30', 'calendarYear': '2024', 'revenue': 17500000000, 'grossProfit': 7000000000, 'netIncome': 2700000000, 'operatingIncome': 4200000000, 'interestExpense': 500000000, 'eps': 2.10},
                {'date': '2024-03-31', 'calendarYear': '2024', 'revenue': 17000000000, 'grossProfit': 6800000000, 'netIncome': 2600000000, 'operatingIncome': 4000000000, 'interestExpense': 500000000, 'eps': 2.00},
                {'date': '2023-12-31', 'calendarYear': '2023', 'revenue': 16500000000, 'grossProfit': 6600000000, 'netIncome': 2500000000, 'operatingIncome': 3800000000, 'interestExpense': 500000000, 'eps': 1.90},
            ],
            'balance_sheet': [
                {'date': '2025-09-30', 'calendarYear': '2025', 'totalDebt': 10000000000, 'cashAndCashEquivalents': 5000000000, 'totalStockholdersEquity': 50000000000, 'totalAssets': 100000000000, 'totalLiabilities': 50000000000},
                {'date': '2024-12-31', 'calendarYear': '2024', 'totalDebt': 12000000000, 'cashAndCashEquivalents': 6000000000, 'totalStockholdersEquity': 48000000000, 'totalAssets': 98000000000, 'totalLiabilities': 50000000000},
                {'date': '2023-12-31', 'calendarYear': '2023', 'totalDebt': 14000000000, 'cashAndCashEquivalents': 7000000000, 'totalStockholdersEquity': 46000000000, 'totalAssets': 96000000000, 'totalLiabilities': 50000000000},
            ],
            'cash_flow': [
                {'date': '2025-09-30', 'calendarYear': '2025', 'operatingCashFlow': 5000000000, 'freeCashFlow': 3000000000, 'capitalExpenditure': -2000000000, 'commonDividendsPaid': -500000000, 'commonStockRepurchased': -1000000000},
                {'date': '2024-12-31', 'calendarYear': '2024', 'operatingCashFlow': 4500000000, 'freeCashFlow': 2500000000, 'capitalExpenditure': -2000000000, 'commonDividendsPaid': -500000000, 'commonStockRepurchased': -800000000},
                {'date': '2023-12-31', 'calendarYear': '2023', 'operatingCashFlow': 4000000000, 'freeCashFlow': 2000000000, 'capitalExpenditure': -2000000000, 'commonDividendsPaid': -500000000, 'commonStockRepurchased': -600000000},
            ],
        }

        output = generator._format_metrics_for_prompt(features, trends, raw_financials)

        # Check that new sections appear
        assert "QUARTERLY MOMENTUM ANALYSIS" in output
        assert "Growth Trend Alerts" in output
        assert "Debt Health Trajectory" in output
        assert "Cash Flow Trajectory" in output
        assert "Revenue & Growth Trajectory" in output


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
