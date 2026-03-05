"""
Financial Data Quality Validator

Measures the accuracy and completeness of financial data fetched from FMP.
Two main capabilities:
1. Internal consistency checks (accounting identities, cross-metric reconciliation)
2. Completeness scoring (% of expected data present)

Usage:
    from src.utils.data_quality import DataQualityValidator

    validator = DataQualityValidator(raw_financials)
    report = validator.validate()
    print(report['overall_score'])        # 0.0 - 1.0
    print(report['consistency_issues'])   # list of detected problems
    print(report['completeness'])         # per-statement completeness metrics
"""

from typing import Dict, List, Any, Optional
from .logger import get_logger

logger = get_logger(__name__)


# Fields expected on each quarterly balance sheet from FMP
EXPECTED_BALANCE_SHEET_FIELDS = [
    'totalAssets', 'totalLiabilities', 'totalStockholdersEquity',
    'totalCurrentAssets', 'totalCurrentLiabilities',
    'totalDebt', 'cashAndCashEquivalents',
    'shortTermDebt', 'longTermDebt',
    'date', 'period',
]

# Fields expected on each quarterly income statement
EXPECTED_INCOME_STATEMENT_FIELDS = [
    'revenue', 'costOfRevenue', 'grossProfit',
    'operatingExpenses', 'operatingIncome',
    'netIncome', 'ebitda', 'eps',
    'interestExpense', 'incomeTaxExpense',
    'weightedAverageShsOut', 'weightedAverageShsOutDil',
    'date', 'period',
]

# Fields expected on each quarterly cash flow statement
EXPECTED_CASH_FLOW_FIELDS = [
    'operatingCashFlow', 'capitalExpenditure', 'freeCashFlow',
    'stockBasedCompensation',
    'commonDividendsPaid', 'commonStockRepurchased',
    'date', 'period',
]

# Number of quarters we expect (5 years)
EXPECTED_QUARTERS = 20

# Tolerance for accounting identity checks (allows for rounding)
TOLERANCE_PCT = 0.02  # 2%
TOLERANCE_ABS = 1000  # $1000 absolute tolerance for very small values


class DataQualityValidator:
    """
    Validates financial data quality through internal consistency checks
    and completeness scoring.

    Args:
        raw_financials: Dict with 'balance_sheet', 'income_statement', 'cash_flow'
                       lists of quarterly data from FMP.
    """

    def __init__(self, raw_financials: Dict[str, Any]):
        self.balance_sheets = raw_financials.get('balance_sheet', [])
        self.income_statements = raw_financials.get('income_statement', [])
        self.cash_flows = raw_financials.get('cash_flow', [])
        self.issues: List[Dict[str, Any]] = []

    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks and return a quality report.

        Returns:
            Dict with:
                overall_score: float 0.0-1.0 (1.0 = perfect)
                completeness: dict with per-statement completeness metrics
                consistency_issues: list of detected problems
                summary: human-readable summary string
        """
        self.issues = []

        completeness = self._check_completeness()
        self._check_balance_sheet_identity()
        self._check_debt_breakdown()
        self._check_income_statement_consistency()
        self._check_cash_flow_consistency()
        self._check_cross_statement_consistency()
        self._check_sanity_bounds()

        # Score: weighted average of completeness and consistency
        completeness_score = completeness['overall_completeness']
        # Consistency: each issue deducts points based on severity
        severity_weights = {'error': 0.05, 'warning': 0.02, 'info': 0.005}
        consistency_penalty = sum(
            severity_weights.get(issue['severity'], 0.01)
            for issue in self.issues
        )
        consistency_score = max(0.0, 1.0 - consistency_penalty)

        overall_score = round(0.4 * completeness_score + 0.6 * consistency_score, 3)

        summary = self._build_summary(overall_score, completeness, self.issues)

        return {
            'overall_score': overall_score,
            'completeness': completeness,
            'consistency_issues': self.issues,
            'summary': summary,
        }

    def _check_completeness(self) -> Dict[str, Any]:
        """
        Check how much of the expected data is present.

        Returns:
            Dict with per-statement and overall completeness scores.
        """
        bs_result = self._field_completeness(
            self.balance_sheets, EXPECTED_BALANCE_SHEET_FIELDS, 'balance_sheet'
        )
        is_result = self._field_completeness(
            self.income_statements, EXPECTED_INCOME_STATEMENT_FIELDS, 'income_statement'
        )
        cf_result = self._field_completeness(
            self.cash_flows, EXPECTED_CASH_FLOW_FIELDS, 'cash_flow'
        )

        # Quarter coverage
        bs_quarters = len(self.balance_sheets)
        is_quarters = len(self.income_statements)
        cf_quarters = len(self.cash_flows)
        quarter_coverage = min(bs_quarters, is_quarters, cf_quarters) / EXPECTED_QUARTERS

        if quarter_coverage < 0.5:
            self.issues.append({
                'check': 'quarter_coverage',
                'severity': 'error',
                'message': (
                    f'Only {min(bs_quarters, is_quarters, cf_quarters)} of '
                    f'{EXPECTED_QUARTERS} expected quarters available'
                ),
            })
        elif quarter_coverage < 0.8:
            self.issues.append({
                'check': 'quarter_coverage',
                'severity': 'warning',
                'message': (
                    f'{min(bs_quarters, is_quarters, cf_quarters)} of '
                    f'{EXPECTED_QUARTERS} expected quarters available'
                ),
            })

        overall = round(
            (bs_result['score'] + is_result['score'] + cf_result['score'] + quarter_coverage) / 4,
            3
        )

        return {
            'balance_sheet': bs_result,
            'income_statement': is_result,
            'cash_flow': cf_result,
            'quarter_coverage': round(quarter_coverage, 3),
            'quarters_available': {
                'balance_sheet': bs_quarters,
                'income_statement': is_quarters,
                'cash_flow': cf_quarters,
            },
            'overall_completeness': overall,
        }

    def _field_completeness(
        self,
        statements: List[Dict],
        expected_fields: List[str],
        statement_type: str
    ) -> Dict[str, Any]:
        """
        Check field-level completeness for a list of quarterly statements.

        Returns:
            Dict with score (0-1) and list of missing fields.
        """
        if not statements:
            return {'score': 0.0, 'missing_fields': expected_fields, 'null_fields': {}}

        total_checks = len(expected_fields) * len(statements)
        present_count = 0
        null_field_counts: Dict[str, int] = {}

        for quarter in statements:
            for field in expected_fields:
                value = quarter.get(field)
                if value is not None and value != '':
                    present_count += 1
                else:
                    null_field_counts[field] = null_field_counts.get(field, 0) + 1

        score = round(present_count / total_checks, 3) if total_checks > 0 else 0.0

        # Fields missing in >50% of quarters
        chronic_missing = {
            field: count
            for field, count in null_field_counts.items()
            if count > len(statements) * 0.5
        }
        if chronic_missing:
            self.issues.append({
                'check': f'{statement_type}_field_completeness',
                'severity': 'warning',
                'message': (
                    f'{statement_type}: fields missing in >50% of quarters: '
                    f'{list(chronic_missing.keys())}'
                ),
            })

        return {
            'score': score,
            'missing_fields': list(chronic_missing.keys()),
            'null_fields': null_field_counts,
        }

    def _check_balance_sheet_identity(self) -> None:
        """
        Verify accounting identity: totalAssets = totalLiabilities + totalStockholdersEquity
        """
        for i, bs in enumerate(self.balance_sheets):
            total_assets = self._get_numeric(bs, 'totalAssets')
            total_liabilities = self._get_numeric(bs, 'totalLiabilities')
            total_equity = self._get_numeric(bs, 'totalStockholdersEquity')

            if total_assets is None or total_liabilities is None or total_equity is None:
                continue

            expected = total_liabilities + total_equity
            if not self._approx_equal(total_assets, expected):
                date = bs.get('date', f'quarter_{i}')
                diff = total_assets - expected
                self.issues.append({
                    'check': 'balance_sheet_identity',
                    'severity': 'error',
                    'message': (
                        f'Q{i} ({date}): totalAssets ({total_assets:,.0f}) != '
                        f'totalLiabilities ({total_liabilities:,.0f}) + '
                        f'totalEquity ({total_equity:,.0f}). '
                        f'Diff: {diff:,.0f}'
                    ),
                    'quarter': i,
                })

    def _check_debt_breakdown(self) -> None:
        """
        Verify: totalDebt ~= shortTermDebt + longTermDebt
        """
        for i, bs in enumerate(self.balance_sheets):
            total_debt = self._get_numeric(bs, 'totalDebt')
            short_term = self._get_numeric(bs, 'shortTermDebt')
            long_term = self._get_numeric(bs, 'longTermDebt')

            if total_debt is None or (short_term is None and long_term is None):
                continue

            short_term = short_term or 0
            long_term = long_term or 0
            expected = short_term + long_term

            if total_debt == 0 and expected == 0:
                continue

            if not self._approx_equal(total_debt, expected):
                date = bs.get('date', f'quarter_{i}')
                diff = total_debt - expected
                self.issues.append({
                    'check': 'debt_breakdown',
                    'severity': 'warning',
                    'message': (
                        f'Q{i} ({date}): totalDebt ({total_debt:,.0f}) != '
                        f'shortTermDebt ({short_term:,.0f}) + '
                        f'longTermDebt ({long_term:,.0f}). '
                        f'Diff: {diff:,.0f}'
                    ),
                    'quarter': i,
                })

    def _check_income_statement_consistency(self) -> None:
        """
        Verify income statement relationships:
        - grossProfit = revenue - costOfRevenue
        - operatingIncome ~= grossProfit - operatingExpenses (approximate)
        """
        for i, stmt in enumerate(self.income_statements):
            revenue = self._get_numeric(stmt, 'revenue')
            cost_of_revenue = self._get_numeric(stmt, 'costOfRevenue')
            gross_profit = self._get_numeric(stmt, 'grossProfit')

            # grossProfit = revenue - costOfRevenue
            if all(v is not None for v in [revenue, cost_of_revenue, gross_profit]):
                expected_gp = revenue - cost_of_revenue
                if not self._approx_equal(gross_profit, expected_gp):
                    date = stmt.get('date', f'quarter_{i}')
                    self.issues.append({
                        'check': 'gross_profit_calc',
                        'severity': 'error',
                        'message': (
                            f'Q{i} ({date}): grossProfit ({gross_profit:,.0f}) != '
                            f'revenue ({revenue:,.0f}) - costOfRevenue ({cost_of_revenue:,.0f})'
                        ),
                        'quarter': i,
                    })

            # Shares: diluted >= basic
            basic = self._get_numeric(stmt, 'weightedAverageShsOut')
            diluted = self._get_numeric(stmt, 'weightedAverageShsOutDil')
            if basic is not None and diluted is not None and diluted > 0 and basic > 0:
                if diluted < basic * 0.99:  # 1% tolerance
                    date = stmt.get('date', f'quarter_{i}')
                    self.issues.append({
                        'check': 'share_count',
                        'severity': 'warning',
                        'message': (
                            f'Q{i} ({date}): diluted shares ({diluted:,.0f}) < '
                            f'basic shares ({basic:,.0f})'
                        ),
                        'quarter': i,
                    })

    def _check_cash_flow_consistency(self) -> None:
        """
        Verify: freeCashFlow ~= operatingCashFlow - abs(capitalExpenditure)
        """
        for i, cf in enumerate(self.cash_flows):
            ocf = self._get_numeric(cf, 'operatingCashFlow')
            capex = self._get_numeric(cf, 'capitalExpenditure')
            fcf = self._get_numeric(cf, 'freeCashFlow')

            if ocf is None or capex is None or fcf is None:
                continue

            # capex is typically negative in FMP data
            expected_fcf = ocf + capex  # capex is negative, so this is ocf - |capex|
            if not self._approx_equal(fcf, expected_fcf):
                # Try with absolute capex (some FMP records store it positive)
                expected_fcf_abs = ocf - abs(capex)
                if not self._approx_equal(fcf, expected_fcf_abs):
                    date = cf.get('date', f'quarter_{i}')
                    self.issues.append({
                        'check': 'fcf_calc',
                        'severity': 'warning',
                        'message': (
                            f'Q{i} ({date}): FCF ({fcf:,.0f}) != '
                            f'OCF ({ocf:,.0f}) - CapEx ({abs(capex):,.0f})'
                        ),
                        'quarter': i,
                    })

    def _check_cross_statement_consistency(self) -> None:
        """
        Cross-statement checks:
        - Net income should appear consistently in income statement and cash flow
        """
        n = min(len(self.income_statements), len(self.cash_flows))
        for i in range(n):
            is_ni = self._get_numeric(self.income_statements[i], 'netIncome')
            cf_ni = self._get_numeric(self.cash_flows[i], 'netIncome')

            if is_ni is not None and cf_ni is not None:
                if not self._approx_equal(is_ni, cf_ni):
                    date = self.income_statements[i].get('date', f'quarter_{i}')
                    self.issues.append({
                        'check': 'cross_statement_net_income',
                        'severity': 'warning',
                        'message': (
                            f'Q{i} ({date}): netIncome mismatch - '
                            f'income stmt ({is_ni:,.0f}) vs '
                            f'cash flow ({cf_ni:,.0f})'
                        ),
                        'quarter': i,
                    })

    def _check_sanity_bounds(self) -> None:
        """
        Flag metrics outside reasonable bounds.
        These aren't necessarily errors, but warrant investigation.
        """
        for i, bs in enumerate(self.balance_sheets):
            total_assets = self._get_numeric(bs, 'totalAssets')
            total_equity = self._get_numeric(bs, 'totalStockholdersEquity')
            total_debt = self._get_numeric(bs, 'totalDebt')

            date = bs.get('date', f'quarter_{i}')

            # Negative total assets is essentially impossible
            if total_assets is not None and total_assets < 0:
                self.issues.append({
                    'check': 'sanity_negative_assets',
                    'severity': 'error',
                    'message': f'Q{i} ({date}): negative totalAssets ({total_assets:,.0f})',
                    'quarter': i,
                })

            # Negative total debt shouldn't happen
            if total_debt is not None and total_debt < 0:
                self.issues.append({
                    'check': 'sanity_negative_debt',
                    'severity': 'warning',
                    'message': f'Q{i} ({date}): negative totalDebt ({total_debt:,.0f})',
                    'quarter': i,
                })

            # Extreme debt-to-equity (> 50x)
            if total_debt is not None and total_equity is not None and total_equity > 0:
                dte = total_debt / total_equity
                if dte > 50:
                    self.issues.append({
                        'check': 'sanity_extreme_leverage',
                        'severity': 'info',
                        'message': (
                            f'Q{i} ({date}): extreme debt-to-equity ratio ({dte:.1f}x). '
                            f'May be a financial company or data error.'
                        ),
                        'quarter': i,
                    })

        for i, stmt in enumerate(self.income_statements):
            revenue = self._get_numeric(stmt, 'revenue')
            date = stmt.get('date', f'quarter_{i}')

            # Negative revenue (extremely rare, usually a data error)
            if revenue is not None and revenue < 0:
                self.issues.append({
                    'check': 'sanity_negative_revenue',
                    'severity': 'error',
                    'message': f'Q{i} ({date}): negative revenue ({revenue:,.0f})',
                    'quarter': i,
                })

            # Zero revenue (could be legitimate for pre-revenue companies)
            if revenue is not None and revenue == 0:
                self.issues.append({
                    'check': 'sanity_zero_revenue',
                    'severity': 'info',
                    'message': f'Q{i} ({date}): zero revenue',
                    'quarter': i,
                })

            # Shares outstanding should be positive
            shares = self._get_numeric(stmt, 'weightedAverageShsOut')
            if shares is not None and shares <= 0:
                self.issues.append({
                    'check': 'sanity_invalid_shares',
                    'severity': 'error',
                    'message': f'Q{i} ({date}): invalid shares outstanding ({shares:,.0f})',
                    'quarter': i,
                })

    def _get_numeric(self, data: Dict, key: str) -> Optional[float]:
        """Safely extract a numeric value, returning None for missing/non-numeric."""
        value = data.get(key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _approx_equal(self, a: float, b: float) -> bool:
        """
        Check if two values are approximately equal within tolerance.
        Uses both relative (2%) and absolute ($1000) tolerance.
        """
        diff = abs(a - b)
        if diff <= TOLERANCE_ABS:
            return True
        max_val = max(abs(a), abs(b))
        if max_val == 0:
            return True
        return (diff / max_val) <= TOLERANCE_PCT

    def _build_summary(
        self,
        overall_score: float,
        completeness: Dict,
        issues: List[Dict]
    ) -> str:
        """Build a human-readable summary of the quality report."""
        error_count = sum(1 for i in issues if i['severity'] == 'error')
        warning_count = sum(1 for i in issues if i['severity'] == 'warning')
        info_count = sum(1 for i in issues if i['severity'] == 'info')

        grade = 'A' if overall_score >= 0.95 else \
                'B' if overall_score >= 0.85 else \
                'C' if overall_score >= 0.70 else \
                'D' if overall_score >= 0.50 else 'F'

        quarters = completeness['quarters_available']
        min_quarters = min(quarters.values())

        lines = [
            f'Data Quality Grade: {grade} (score: {overall_score:.1%})',
            f'Quarters available: {min_quarters}/{EXPECTED_QUARTERS}',
            f'Field completeness: {completeness["overall_completeness"]:.1%}',
            f'Issues: {error_count} errors, {warning_count} warnings, {info_count} info',
        ]

        if error_count > 0:
            lines.append('Errors:')
            for issue in issues:
                if issue['severity'] == 'error':
                    lines.append(f'  - {issue["message"]}')

        return '\n'.join(lines)
