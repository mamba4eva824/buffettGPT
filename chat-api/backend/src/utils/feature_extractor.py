"""
Feature Extractor for Ensemble Analysis

Extracts key financial metrics from FMP data for the 3-agent ensemble:
- Debt Expert: Leverage, coverage, liquidity metrics
- Cashflow Expert: FCF, cash efficiency, capital allocation
- Growth Expert: Revenue growth, margin trends, acceleration

This module now includes:
- Quarterly time-series extraction (20 quarters / 5 years)
- Trend phase identification (deleveraging cycles, growth phases)
- Inflection point detection
- Peak/trough analysis

The full v3.6.5 feature set (163 features) is used for model inference.
"""

import time
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
from decimal import Decimal
from .logger import get_logger

logger = get_logger(__name__)


def safe_divide(numerator, denominator, default=0.0):
    """Safely divide two numbers, returning default if denominator is 0 or None."""
    try:
        if denominator is None or denominator == 0:
            return default
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return default


def extract_value(data_list: list, key: str, index: int = 0, default=None):
    """
    Extract a value from FMP API response list.
    Converts Decimal to float for numeric operations (DynamoDB returns Decimals).

    Args:
        data_list: List of quarterly data dicts from FMP
        key: Key to extract
        index: Which quarter (0 = most recent)
        default: Default value if not found
    """
    try:
        if not data_list or index >= len(data_list):
            return default
        value = data_list[index].get(key, default)
        if value is None:
            return default
        # Convert Decimal to float for numeric operations (DynamoDB stores numbers as Decimal)
        if hasattr(value, '__float__'):
            return float(value)
        return value
    except (IndexError, TypeError, AttributeError):
        return default


def decimal_to_float(obj):
    """
    Recursively convert Decimal to float in nested structures.
    DynamoDB returns numbers as Decimal objects which need conversion.
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def aggregate_annual_data(
    income_statements: list,
    balance_sheets: list,
    cash_flows: list
) -> dict:
    """
    Aggregate quarterly data into true annual figures.

    Flow metrics (revenue, income, cash flows) are SUMMED across all quarters
    in each fiscal year. Point-in-time metrics (debt, cash, equity) use the
    most recent quarter's values (typically Q4/year-end).

    Args:
        income_statements: List of quarterly income statements (most recent first)
        balance_sheets: List of quarterly balance sheets (most recent first)
        cash_flows: List of quarterly cash flow statements (most recent first)

    Returns:
        Dict keyed by fiscal year with aggregated 'income', 'balance', 'cashflow' data
    """
    # Flow metrics that should be summed across quarters
    INCOME_FLOW_METRICS = [
        'revenue', 'netIncome', 'grossProfit', 'operatingIncome',
        'costOfRevenue', 'operatingExpenses', 'interestExpense',
        'incomeBeforeTax', 'incomeTaxExpense', 'ebitda', 'ebitdaratio'
    ]
    CASHFLOW_FLOW_METRICS = [
        'operatingCashFlow', 'freeCashFlow', 'capitalExpenditure',
        'commonDividendsPaid', 'commonStockRepurchased', 'netCashProvidedByInvestingActivities',
        'netCashProvidedByFinancingActivities', 'netChangeInCash'
    ]

    # Group quarters by fiscal year
    quarters_by_year = {}

    for stmt in income_statements[:20]:
        stmt = decimal_to_float(stmt)
        year = stmt.get('fiscalYear') or stmt.get('calendarYear') or (stmt.get('date', 'Unknown')[:4] if stmt.get('date') else 'Unknown')
        if year == 'Unknown':
            continue
        # Convert year to int for consistent sorting
        try:
            year = int(year)
        except (ValueError, TypeError):
            continue
        if year not in quarters_by_year:
            quarters_by_year[year] = {'income': [], 'balance': [], 'cashflow': []}
        quarters_by_year[year]['income'].append(stmt)

    for bs in balance_sheets[:20]:
        bs = decimal_to_float(bs)
        year = bs.get('fiscalYear') or bs.get('calendarYear') or (bs.get('date', 'Unknown')[:4] if bs.get('date') else 'Unknown')
        try:
            year = int(year)
        except (ValueError, TypeError):
            continue
        if year in quarters_by_year:
            quarters_by_year[year]['balance'].append(bs)

    for cf in cash_flows[:20]:
        cf = decimal_to_float(cf)
        year = cf.get('fiscalYear') or cf.get('calendarYear') or (cf.get('date', 'Unknown')[:4] if cf.get('date') else 'Unknown')
        try:
            year = int(year)
        except (ValueError, TypeError):
            continue
        if year in quarters_by_year:
            quarters_by_year[year]['cashflow'].append(cf)

    # Build aggregated annual data
    annual_data = {}

    for year, quarters in quarters_by_year.items():
        # Sum income statement flow metrics
        aggregated_income = {}
        if quarters['income']:
            # Start with first quarter as template for non-flow fields
            aggregated_income = dict(quarters['income'][0])
            # Sum flow metrics across all quarters
            for metric in INCOME_FLOW_METRICS:
                total = sum(
                    q.get(metric, 0) or 0
                    for q in quarters['income']
                )
                aggregated_income[metric] = total
            # EPS needs special handling - sum quarterly EPS for annual
            aggregated_income['eps'] = sum(
                q.get('eps', 0) or 0
                for q in quarters['income']
            )

        # Sum cash flow statement flow metrics
        aggregated_cashflow = {}
        if quarters['cashflow']:
            aggregated_cashflow = dict(quarters['cashflow'][0])
            for metric in CASHFLOW_FLOW_METRICS:
                total = sum(
                    q.get(metric, 0) or 0
                    for q in quarters['cashflow']
                )
                aggregated_cashflow[metric] = total

        # Balance sheet uses most recent quarter (point-in-time, not summed)
        # Quarters are sorted most recent first, so [0] is the latest
        aggregated_balance = quarters['balance'][0] if quarters['balance'] else {}

        annual_data[year] = {
            'income': aggregated_income,
            'balance': aggregated_balance,
            'cashflow': aggregated_cashflow,
            'quarters_count': len(quarters['income'])  # Track how many quarters we have
        }

    return annual_data


def extract_debt_metrics(balance_sheet: list, income_statement: list, cashflow: list) -> dict:
    """
    Extract debt-related metrics for the Debt Expert agent.

    Returns dict with current values and historical comparisons.
    """
    metrics = {
        'current': {},
        'historical': {},
        'trends': {}
    }

    # Current quarter (index 0 = most recent)
    total_debt = extract_value(balance_sheet, 'totalDebt', 0, 0)
    total_equity = extract_value(balance_sheet, 'totalStockholdersEquity', 0, 0)
    total_assets = extract_value(balance_sheet, 'totalAssets', 0, 0)
    cash = extract_value(balance_sheet, 'cashAndCashEquivalents', 0, 0)
    current_assets = extract_value(balance_sheet, 'totalCurrentAssets', 0, 0)
    current_liabilities = extract_value(balance_sheet, 'totalCurrentLiabilities', 0, 0)

    operating_income = extract_value(income_statement, 'operatingIncome', 0, 0)
    ebitda = extract_value(income_statement, 'ebitda', 0, 0)
    interest_expense = extract_value(income_statement, 'interestExpense', 0, 0)

    fcf = extract_value(cashflow, 'freeCashFlow', 0, 0)

    # Calculate ratios
    metrics['current'] = {
        'total_debt': total_debt,
        'total_equity': total_equity,
        'debt_to_equity': round(safe_divide(total_debt, total_equity), 2),
        'debt_to_assets': round(safe_divide(total_debt, total_assets), 2),
        'net_debt': total_debt - cash,
        'net_debt_to_ebitda': round(safe_divide(total_debt - cash, ebitda), 2),
        'interest_coverage': round(safe_divide(operating_income, max(interest_expense, 1)), 1),
        'current_ratio': round(safe_divide(current_assets, current_liabilities), 2),
        'operating_income': operating_income,
        'fcf_to_debt': round(safe_divide(fcf, total_debt), 2),
        'cash': cash,
    }

    # Historical (4 quarters ago = 1 year)
    if len(balance_sheet) >= 5:
        debt_1y = extract_value(balance_sheet, 'totalDebt', 4, 0)
        equity_1y = extract_value(balance_sheet, 'totalStockholdersEquity', 4, 0)
        metrics['historical']['debt_to_equity_1y_ago'] = round(safe_divide(debt_1y, equity_1y), 2)

    # 3 years ago (12 quarters)
    if len(balance_sheet) >= 13:
        debt_3y = extract_value(balance_sheet, 'totalDebt', 12, 0)
        equity_3y = extract_value(balance_sheet, 'totalStockholdersEquity', 12, 0)
        metrics['historical']['debt_to_equity_3y_ago'] = round(safe_divide(debt_3y, equity_3y), 2)

    # Trends
    if len(balance_sheet) >= 5:
        current_dte = metrics['current']['debt_to_equity']
        hist_dte = metrics['historical'].get('debt_to_equity_1y_ago', current_dte)
        if hist_dte and hist_dte != 0:
            change_pct = ((current_dte - hist_dte) / hist_dte) * 100
            metrics['trends']['debt_to_equity_yoy_change'] = f"{'+' if change_pct > 0 else ''}{round(change_pct)}%"

    # Is company deleveraging?
    if len(balance_sheet) >= 5:
        debt_current = extract_value(balance_sheet, 'totalDebt', 0, 0)
        debt_1q_ago = extract_value(balance_sheet, 'totalDebt', 1, 0)
        debt_4q_ago = extract_value(balance_sheet, 'totalDebt', 4, 0)
        metrics['trends']['is_deleveraging'] = debt_current < debt_4q_ago
        metrics['trends']['leverage_momentum'] = 'decreasing' if debt_current < debt_1q_ago else 'increasing'

    return metrics


def extract_cashflow_metrics(balance_sheet: list, income_statement: list, cashflow: list) -> dict:
    """
    Extract cashflow-related metrics for the Cashflow Expert agent.
    """
    metrics = {
        'current': {},
        'historical': {},
        'trends': {}
    }

    # Current quarter
    revenue = extract_value(income_statement, 'revenue', 0, 0)
    net_income = extract_value(income_statement, 'netIncome', 0, 0)

    operating_cf = extract_value(cashflow, 'operatingCashFlow', 0, 0)
    fcf = extract_value(cashflow, 'freeCashFlow', 0, 0)
    capex = abs(extract_value(cashflow, 'capitalExpenditure', 0, 0))
    dividends = abs(extract_value(cashflow, 'commonDividendsPaid', 0, 0))
    buybacks = abs(extract_value(cashflow, 'commonStockRepurchased', 0, 0))

    # Current metrics
    metrics['current'] = {
        'operating_cash_flow': operating_cf,
        'free_cash_flow': fcf,
        'revenue': revenue,
        'fcf_margin': round(safe_divide(fcf, revenue) * 100, 1),
        'ocf_to_revenue': round(safe_divide(operating_cf, revenue) * 100, 1),
        'capex': capex,
        'capex_intensity': round(safe_divide(capex, revenue) * 100, 1),
        'fcf_to_net_income': round(safe_divide(fcf, net_income), 2) if net_income else None,
        'total_shareholder_returns': dividends + buybacks,
        'shareholder_returns_pct_fcf': round(safe_divide(dividends + buybacks, fcf) * 100, 0) if fcf else None,
    }

    # Historical comparison (4 quarters ago)
    if len(cashflow) >= 5:
        ocf_1y = extract_value(cashflow, 'operatingCashFlow', 4, 0)
        fcf_1y = extract_value(cashflow, 'freeCashFlow', 4, 0)
        metrics['historical']['operating_cash_flow_1y_ago'] = ocf_1y
        metrics['historical']['free_cash_flow_1y_ago'] = fcf_1y

    # Historical peak (look at all quarters)
    if len(cashflow) >= 4:
        ocf_values = [extract_value(cashflow, 'operatingCashFlow', i, 0) for i in range(min(8, len(cashflow)))]
        fcf_values = [extract_value(cashflow, 'freeCashFlow', i, 0) for i in range(min(8, len(cashflow)))]
        metrics['historical']['operating_cash_flow_peak'] = max(ocf_values) if ocf_values else 0
        metrics['historical']['free_cash_flow_peak'] = max(fcf_values) if fcf_values else 0

    # Trends
    if len(cashflow) >= 5:
        current_fcf = metrics['current']['free_cash_flow']
        fcf_1y = metrics['historical'].get('free_cash_flow_1y_ago', current_fcf)
        if fcf_1y and fcf_1y != 0:
            fcf_change = ((current_fcf - fcf_1y) / abs(fcf_1y)) * 100
            metrics['trends']['fcf_margin_trend'] = 'growing' if fcf_change > 0 else 'declining'
            metrics['trends']['fcf_yoy_change_pct'] = round(fcf_change, 1)

    return metrics


def extract_growth_metrics(balance_sheet: list, income_statement: list, cashflow: list) -> dict:
    """
    Extract growth-related metrics for the Growth Expert agent.
    """
    metrics = {
        'current': {},
        'historical': {},
        'trends': {}
    }

    # Current quarter
    revenue = extract_value(income_statement, 'revenue', 0, 0)
    gross_profit = extract_value(income_statement, 'grossProfit', 0, 0)
    operating_income = extract_value(income_statement, 'operatingIncome', 0, 0)
    net_income = extract_value(income_statement, 'netIncome', 0, 0)
    eps = extract_value(income_statement, 'eps', 0, 0)

    # Current margins
    metrics['current'] = {
        'revenue': revenue,
        'gross_margin': round(safe_divide(gross_profit, revenue) * 100, 1),
        'operating_margin': round(safe_divide(operating_income, revenue) * 100, 1),
        'net_margin': round(safe_divide(net_income, revenue) * 100, 1),
        'operating_income': operating_income,
        'net_income': net_income,
        'eps': eps,
    }

    # YoY growth (compare to 4 quarters ago)
    if len(income_statement) >= 5:
        revenue_1y = extract_value(income_statement, 'revenue', 4, 0)
        net_income_1y = extract_value(income_statement, 'netIncome', 4, 0)
        eps_1y = extract_value(income_statement, 'eps', 4, 0)
        op_margin_1y = safe_divide(
            extract_value(income_statement, 'operatingIncome', 4, 0),
            revenue_1y
        ) * 100

        if revenue_1y and revenue_1y != 0:
            metrics['current']['revenue_growth_yoy'] = round(((revenue - revenue_1y) / revenue_1y) * 100, 1)
        if net_income_1y and net_income_1y != 0:
            metrics['current']['net_income_growth_yoy'] = round(((net_income - net_income_1y) / abs(net_income_1y)) * 100, 1)
        if eps_1y and eps_1y != 0:
            metrics['current']['eps_growth_yoy'] = round(((eps - eps_1y) / abs(eps_1y)) * 100, 1)

        # Margin change
        current_op_margin = metrics['current']['operating_margin']
        metrics['trends']['operating_margin_change_1yr'] = round(current_op_margin - op_margin_1y, 2)

        net_margin_1y = safe_divide(net_income_1y, revenue_1y) * 100
        metrics['trends']['net_margin_change_1yr'] = round(metrics['current']['net_margin'] - net_margin_1y, 2)

    # QoQ momentum (compare to last quarter)
    if len(income_statement) >= 2:
        revenue_1q = extract_value(income_statement, 'revenue', 1, 0)
        if revenue_1q and revenue_1q != 0:
            qoq_growth = ((revenue - revenue_1q) / revenue_1q) * 100
            metrics['trends']['revenue_growth_qoq'] = round(qoq_growth, 1)

    # Is growth accelerating?
    if len(income_statement) >= 9:
        # Compare this year's growth to last year's growth
        revenue_now = extract_value(income_statement, 'revenue', 0, 0)
        revenue_4q = extract_value(income_statement, 'revenue', 4, 0)
        revenue_8q = extract_value(income_statement, 'revenue', 8, 0)

        if revenue_4q and revenue_8q and revenue_4q != 0 and revenue_8q != 0:
            growth_this_year = (revenue_now - revenue_4q) / revenue_4q
            growth_last_year = (revenue_4q - revenue_8q) / revenue_8q
            metrics['trends']['is_growth_accelerating'] = growth_this_year > growth_last_year

    # Historical revenue peak
    if len(income_statement) >= 4:
        revenue_values = [extract_value(income_statement, 'revenue', i, 0) for i in range(min(12, len(income_statement)))]
        metrics['historical']['revenue_peak'] = max(revenue_values) if revenue_values else 0

    return metrics


def extract_quarterly_trends(raw_financials: dict, num_quarters: int = 20) -> dict:
    """
    Extract 20-quarter time series for key metrics.

    Args:
        raw_financials: Dict with 'balance_sheet', 'income_statement', 'cash_flow'
        num_quarters: Number of quarters to extract (default 20 = 5 years)

    Returns:
        dict with quarterly arrays for key metrics (index 0 = most recent)
    """
    balance_sheet = raw_financials.get('balance_sheet', [])
    income_statement = raw_financials.get('income_statement', [])
    cashflow = raw_financials.get('cash_flow', [])

    # Limit to available data
    n = min(num_quarters, len(balance_sheet), len(income_statement), len(cashflow))

    # Extract time series for each key metric organized by agent specialty
    # Total: 60 metrics (20 per agent) + 2 metadata
    trends = {
        # ===============================
        # DEBT EXPERT METRICS (20)
        # ===============================
        # Core leverage (5)
        'debt_to_equity': [],
        'debt_to_assets': [],
        'net_debt': [],
        'net_debt_to_ebitda': [],
        'total_debt': [],
        # Liquidity (5)
        'current_ratio': [],
        'quick_ratio': [],
        'cash_position': [],
        'interest_coverage': [],
        'interest_expense': [],
        # Returns (5)
        'roa': [],                  # Net income / Total assets (annualized)
        'roic': [],                 # NOPAT / Invested capital (annualized)
        'asset_turnover': [],       # Revenue / Total assets (annualized)
        'equity_multiplier': [],    # Total assets / Total equity
        'fcf_to_debt': [],          # FCF / Total debt
        # Trends (5)
        'total_equity': [],
        'debt_to_equity_change_1yr': [],
        'debt_to_equity_change_2yr': [],
        'current_ratio_change_1yr': [],
        'is_deleveraging': [],

        # ===============================
        # CASHFLOW EXPERT METRICS (20)
        # ===============================
        # Core cash flow (5)
        'operating_cash_flow': [],
        'free_cash_flow': [],
        'fcf_margin': [],
        'ocf_to_revenue': [],
        'fcf_to_net_income': [],
        # Capital allocation (5)
        'capex': [],
        'capex_intensity': [],
        'dividends_paid': [],
        'share_buybacks': [],
        'shareholder_payout': [],
        # Efficiency (5)
        'fcf_payout_ratio': [],
        'working_capital': [],
        'working_capital_to_revenue': [],
        'reinvestment_rate': [],
        'total_capital_return': [],
        # YoY changes (5)
        'fcf_change_yoy': [],
        'fcf_margin_change_1yr': [],
        'ocf_change_yoy': [],
        'capex_change_yoy': [],
        'capital_return_yield': [],  # Placeholder - needs market cap

        # ===============================
        # GROWTH EXPERT METRICS (20)
        # ===============================
        # Core profitability (5)
        'revenue': [],
        'gross_margin': [],
        'operating_margin': [],
        'net_margin': [],
        'ebitda': [],
        # Absolute values (5)
        'net_income': [],
        'gross_profit': [],
        'operating_income': [],
        'eps': [],
        'roe': [],                  # Net income / Shareholders equity (annualized)
        # Growth rates (5)
        'revenue_growth_yoy': [],
        'revenue_growth_qoq': [],
        'eps_growth_yoy': [],
        'roic_growth': [],          # Placeholder for ROIC (shared with debt)
        'net_income_growth_yoy': [],
        # Margin trends (5)
        'gross_margin_change_1yr': [],
        'operating_margin_change_1yr': [],
        'operating_margin_change_2yr': [],
        'net_margin_change_1yr': [],
        'is_margin_expanding': [],
        # ROE trend (extra)
        'roe_change_2yr': [],

        # ===============================
        # METADATA
        # ===============================
        'quarters': [],
        'period_dates': [],         # Actual quarter end dates

        # ===============================
        # EARNINGS QUALITY / AUDIT METRICS (NEW)
        # ===============================
        # Debt maturity breakdown
        'short_term_debt': [],
        'long_term_debt': [],
        'short_term_debt_pct': [],

        # Stock-based compensation (actual SBC from dedicated FMP field)
        'sbc_actual': [],               # Actual SBC from stockBasedCompensation field
        'sbc_to_revenue_pct': [],       # SBC as % of revenue
        'd_and_a': [],                  # Depreciation & Amortization

        # Other non-cash items (impairments, writedowns for earnings quality)
        'other_non_cash_items': [],     # otherNonCashItems from cash flow (impairments, writedowns)

        # Legacy fields for backwards compatibility
        'non_cash_adjustments': [],     # Now points to other_non_cash_items
        'sbc_estimate': [],             # Now points to actual SBC

        # Dilution analysis
        'basic_shares': [],
        'diluted_shares': [],
        'dilution_pct': [],             # (diluted - basic) / basic * 100

        # GAAP vs Adjusted earnings bridge
        'gaap_net_income': [],
        'adjusted_earnings': [],        # GAAP + SBC + D&A (simplified)
        'gaap_adjusted_gap_pct': [],    # How much adjusted exceeds GAAP
    }

    for i in range(n):
        # ===============================
        # RAW DATA EXTRACTION
        # ===============================
        # Balance sheet metrics
        total_debt = extract_value(balance_sheet, 'totalDebt', i, 0)
        total_equity = extract_value(balance_sheet, 'totalStockholdersEquity', i, 0)
        total_assets = extract_value(balance_sheet, 'totalAssets', i, 0)
        cash = extract_value(balance_sheet, 'cashAndCashEquivalents', i, 0)
        short_term_investments = extract_value(balance_sheet, 'shortTermInvestments', i, 0)
        current_assets = extract_value(balance_sheet, 'totalCurrentAssets', i, 0)
        current_liabilities = extract_value(balance_sheet, 'totalCurrentLiabilities', i, 0)

        # NEW: Short-term debt for maturity analysis
        short_term_debt_val = extract_value(balance_sheet, 'shortTermDebt', i, 0)

        # Income statement metrics
        revenue = extract_value(income_statement, 'revenue', i, 0)
        gross_profit = extract_value(income_statement, 'grossProfit', i, 0)
        operating_income = extract_value(income_statement, 'operatingIncome', i, 0)
        net_income = extract_value(income_statement, 'netIncome', i, 0)
        ebitda = extract_value(income_statement, 'ebitda', i, 0)
        interest_expense_val = extract_value(income_statement, 'interestExpense', i, 0)
        eps = extract_value(income_statement, 'eps', i, 0)
        income_tax = extract_value(income_statement, 'incomeTaxExpense', i, 0)

        # NEW: D&A and shares for earnings quality
        d_and_a_val = extract_value(income_statement, 'depreciationAndAmortization', i, 0)
        basic_shares_val = extract_value(income_statement, 'weightedAverageShsOut', i, 0)
        diluted_shares_val = extract_value(income_statement, 'weightedAverageShsOutDil', i, 0)

        # Cash flow metrics
        fcf = extract_value(cashflow, 'freeCashFlow', i, 0)
        ocf = extract_value(cashflow, 'operatingCashFlow', i, 0)
        capex = abs(extract_value(cashflow, 'capitalExpenditure', i, 0))
        dividends = abs(extract_value(cashflow, 'commonDividendsPaid', i, 0))
        buybacks = abs(extract_value(cashflow, 'commonStockRepurchased', i, 0))

        # Stock-based compensation (actual SBC for dilution analysis)
        sbc_actual = extract_value(cashflow, 'stockBasedCompensation', i, 0)
        # Other non-cash items (impairments, writedowns for earnings quality)
        other_non_cash_items = extract_value(cashflow, 'otherNonCashItems', i, 0)

        # Period date
        period_date = extract_value(balance_sheet, 'date', i, None)

        # ===============================
        # DERIVED CALCULATIONS
        # ===============================
        # Debt calculations
        debt_to_equity = round(safe_divide(total_debt, total_equity), 2)
        current_ratio = round(safe_divide(current_assets, current_liabilities), 2)
        quick_ratio = round(safe_divide(cash + short_term_investments, current_liabilities), 2)
        net_debt_val = total_debt - cash

        # Return calculations (annualized for quarterly data)
        # Minimum denominator threshold: 1% of revenue guards against near-zero
        # denominators that produce extreme ratios (e.g., airlines during COVID)
        min_denom = abs(revenue) * 0.01 if revenue else 1e6
        roa = round(safe_divide(net_income * 4, total_assets) * 100, 1)  # Annualized
        if abs(total_equity) < min_denom:
            roe = None
        else:
            roe = max(-200.0, min(200.0, round(safe_divide(net_income * 4, total_equity) * 100, 1)))
        # ROIC = NOPAT / Invested Capital, where NOPAT = Operating Income * (1 - tax rate)
        # Invested Capital = Total Equity + Total Debt - Cash
        tax_rate = safe_divide(income_tax, max(operating_income - interest_expense_val, 1))
        nopat = operating_income * (1 - min(tax_rate, 0.4))  # Cap tax rate at 40%
        invested_capital = total_equity + total_debt - cash
        if abs(invested_capital) < min_denom:
            roic = None
        else:
            roic = max(-200.0, min(200.0, round(safe_divide(nopat * 4, invested_capital) * 100, 1)))

        # Margin calculations
        gross_margin = round(safe_divide(gross_profit, revenue) * 100, 1)
        operating_margin = round(safe_divide(operating_income, revenue) * 100, 1)
        net_margin = round(safe_divide(net_income, revenue) * 100, 1)

        # Cash flow derived
        shareholder_payout = dividends + buybacks
        working_capital = current_assets - current_liabilities
        fcf_margin = round(safe_divide(fcf, revenue) * 100, 1)

        # ===============================
        # DEBT EXPERT METRICS (20)
        # ===============================
        # Core leverage (5)
        trends['debt_to_equity'].append(debt_to_equity)
        trends['debt_to_assets'].append(round(safe_divide(total_debt, total_assets), 2))
        trends['net_debt'].append(net_debt_val)
        trends['net_debt_to_ebitda'].append(round(safe_divide(net_debt_val, ebitda), 2))
        trends['total_debt'].append(total_debt)
        # Liquidity (5)
        trends['current_ratio'].append(current_ratio)
        trends['quick_ratio'].append(quick_ratio)
        trends['cash_position'].append(cash)
        trends['interest_coverage'].append(round(safe_divide(operating_income, max(interest_expense_val, 1)), 1))
        trends['interest_expense'].append(interest_expense_val)
        # Returns (5)
        trends['roa'].append(roa)
        trends['roic'].append(roic)
        trends['asset_turnover'].append(round(safe_divide(revenue * 4, total_assets), 2))  # Annualized
        trends['equity_multiplier'].append(round(safe_divide(total_assets, total_equity), 2))
        trends['fcf_to_debt'].append(round(safe_divide(fcf, total_debt), 2))
        # Trends - will be calculated after loop
        trends['total_equity'].append(total_equity)

        # ===============================
        # CASHFLOW EXPERT METRICS (20)
        # ===============================
        # Core cash flow (5)
        trends['operating_cash_flow'].append(ocf)
        trends['free_cash_flow'].append(fcf)
        trends['fcf_margin'].append(fcf_margin)
        trends['ocf_to_revenue'].append(round(safe_divide(ocf, revenue) * 100, 1))
        # Only meaningful when net_income > 0; clamp to +/-10x to prevent
        # extreme spikes from quarters with tiny positive net_income
        if net_income and net_income > 0:
            fcf_ni = max(-10.0, min(10.0, round(safe_divide(fcf, net_income), 2)))
        else:
            fcf_ni = None
        trends['fcf_to_net_income'].append(fcf_ni)
        # Capital allocation (5)
        trends['capex'].append(capex)
        trends['capex_intensity'].append(round(safe_divide(capex, revenue) * 100, 1))
        trends['dividends_paid'].append(dividends)
        trends['share_buybacks'].append(buybacks)
        trends['shareholder_payout'].append(shareholder_payout)
        # Efficiency (5)
        trends['fcf_payout_ratio'].append(round(safe_divide(shareholder_payout, fcf) * 100, 1))
        trends['working_capital'].append(working_capital)
        trends['working_capital_to_revenue'].append(round(safe_divide(working_capital, revenue) * 100, 1))
        trends['reinvestment_rate'].append(round(safe_divide(capex, ocf) * 100, 1))
        trends['total_capital_return'].append(shareholder_payout)  # Alias for shareholder_payout

        # ===============================
        # GROWTH EXPERT METRICS (20)
        # ===============================
        # Core profitability (5)
        trends['revenue'].append(revenue)
        trends['gross_margin'].append(gross_margin)
        trends['operating_margin'].append(operating_margin)
        trends['net_margin'].append(net_margin)
        trends['ebitda'].append(ebitda)
        # Absolute values (5)
        trends['net_income'].append(net_income)
        trends['gross_profit'].append(gross_profit)
        trends['operating_income'].append(operating_income)
        trends['eps'].append(round(eps, 2) if eps else 0.0)
        trends['roe'].append(roe)

        # ===============================
        # YOY / QOQ GROWTH CALCULATIONS
        # ===============================
        # Revenue growth YoY (compare to same quarter last year, i+4)
        if i + 4 < len(income_statement):
            revenue_1y_ago = extract_value(income_statement, 'revenue', i + 4, 0)
            trends['revenue_growth_yoy'].append(
                round(safe_divide(revenue - revenue_1y_ago, abs(revenue_1y_ago)) * 100, 1) if revenue_1y_ago else 0.0
            )
        else:
            trends['revenue_growth_yoy'].append(None)

        # Revenue growth QoQ (compare to previous quarter, i+1)
        if i + 1 < len(income_statement):
            revenue_prev = extract_value(income_statement, 'revenue', i + 1, 0)
            trends['revenue_growth_qoq'].append(
                round(safe_divide(revenue - revenue_prev, abs(revenue_prev)) * 100, 1) if revenue_prev else 0.0
            )
        else:
            trends['revenue_growth_qoq'].append(None)

        # EPS growth YoY
        if i + 4 < len(income_statement):
            eps_1y_ago = extract_value(income_statement, 'eps', i + 4, 0)
            trends['eps_growth_yoy'].append(
                round(safe_divide(eps - eps_1y_ago, abs(eps_1y_ago)) * 100, 1) if eps_1y_ago else 0.0
            )
        else:
            trends['eps_growth_yoy'].append(None)

        # Net income growth YoY
        if i + 4 < len(income_statement):
            ni_1y_ago = extract_value(income_statement, 'netIncome', i + 4, 0)
            trends['net_income_growth_yoy'].append(
                round(safe_divide(net_income - ni_1y_ago, abs(ni_1y_ago)) * 100, 1) if ni_1y_ago else 0.0
            )
        else:
            trends['net_income_growth_yoy'].append(None)

        # ROIC placeholder (already calculated above, this is for growth tracking)
        trends['roic_growth'].append(roic)  # Will compute delta in post-processing

        # ===============================
        # CASHFLOW YOY CHANGES
        # ===============================
        # FCF change YoY
        if i + 4 < len(cashflow):
            fcf_1y_ago = extract_value(cashflow, 'freeCashFlow', i + 4, 0)
            trends['fcf_change_yoy'].append(
                round(safe_divide(fcf - fcf_1y_ago, abs(fcf_1y_ago)) * 100, 1) if fcf_1y_ago else 0.0
            )
        else:
            trends['fcf_change_yoy'].append(None)

        # FCF margin change 1yr
        if i + 4 < len(cashflow):
            fcf_1y = extract_value(cashflow, 'freeCashFlow', i + 4, 0)
            rev_1y = extract_value(income_statement, 'revenue', i + 4, 0)
            fcf_margin_1y = safe_divide(fcf_1y, rev_1y) * 100 if rev_1y else 0
            trends['fcf_margin_change_1yr'].append(round(fcf_margin - fcf_margin_1y, 1))
        else:
            trends['fcf_margin_change_1yr'].append(None)

        # OCF change YoY
        if i + 4 < len(cashflow):
            ocf_1y_ago = extract_value(cashflow, 'operatingCashFlow', i + 4, 0)
            trends['ocf_change_yoy'].append(
                round(safe_divide(ocf - ocf_1y_ago, abs(ocf_1y_ago)) * 100, 1) if ocf_1y_ago else 0.0
            )
        else:
            trends['ocf_change_yoy'].append(None)

        # CapEx change YoY
        if i + 4 < len(cashflow):
            capex_1y_ago = abs(extract_value(cashflow, 'capitalExpenditure', i + 4, 0))
            trends['capex_change_yoy'].append(
                round(safe_divide(capex - capex_1y_ago, abs(capex_1y_ago)) * 100, 1) if capex_1y_ago else 0.0
            )
        else:
            trends['capex_change_yoy'].append(None)

        # Capital return yield (placeholder - needs market cap)
        trends['capital_return_yield'].append(0.0)  # Would need market cap data

        # ===============================
        # MARGIN TREND CALCULATIONS
        # ===============================
        # Gross margin change 1yr
        if i + 4 < len(income_statement):
            gp_1y = extract_value(income_statement, 'grossProfit', i + 4, 0)
            rev_1y = extract_value(income_statement, 'revenue', i + 4, 0)
            gm_1y = safe_divide(gp_1y, rev_1y) * 100 if rev_1y else 0
            trends['gross_margin_change_1yr'].append(round(gross_margin - gm_1y, 1))
        else:
            trends['gross_margin_change_1yr'].append(None)

        # Operating margin change 1yr
        if i + 4 < len(income_statement):
            oi_1y = extract_value(income_statement, 'operatingIncome', i + 4, 0)
            rev_1y = extract_value(income_statement, 'revenue', i + 4, 0)
            om_1y = safe_divide(oi_1y, rev_1y) * 100 if rev_1y else 0
            trends['operating_margin_change_1yr'].append(round(operating_margin - om_1y, 1))
        else:
            trends['operating_margin_change_1yr'].append(None)

        # Operating margin change 2yr
        if i + 8 < len(income_statement):
            oi_2y = extract_value(income_statement, 'operatingIncome', i + 8, 0)
            rev_2y = extract_value(income_statement, 'revenue', i + 8, 0)
            om_2y = safe_divide(oi_2y, rev_2y) * 100 if rev_2y else 0
            trends['operating_margin_change_2yr'].append(round(operating_margin - om_2y, 1))
        else:
            trends['operating_margin_change_2yr'].append(None)

        # Net margin change 1yr
        if i + 4 < len(income_statement):
            ni_1y = extract_value(income_statement, 'netIncome', i + 4, 0)
            rev_1y = extract_value(income_statement, 'revenue', i + 4, 0)
            nm_1y = safe_divide(ni_1y, rev_1y) * 100 if rev_1y else 0
            trends['net_margin_change_1yr'].append(round(net_margin - nm_1y, 1))
        else:
            trends['net_margin_change_1yr'].append(None)

        # Is margin expanding (1 if operating margin improving vs 1yr ago)
        if i + 4 < len(income_statement):
            oi_1y = extract_value(income_statement, 'operatingIncome', i + 4, 0)
            rev_1y = extract_value(income_statement, 'revenue', i + 4, 0)
            om_1y = safe_divide(oi_1y, rev_1y) * 100 if rev_1y else 0
            trends['is_margin_expanding'].append(1 if operating_margin > om_1y else 0)
        else:
            trends['is_margin_expanding'].append(None)

        # ROE change 2yr
        if i + 8 < len(income_statement) and i + 8 < len(balance_sheet):
            ni_2y = extract_value(income_statement, 'netIncome', i + 8, 0)
            eq_2y = extract_value(balance_sheet, 'totalStockholdersEquity', i + 8, 0)
            roe_2y = safe_divide(ni_2y * 4, eq_2y) * 100 if eq_2y else 0
            trends['roe_change_2yr'].append(round(roe - roe_2y, 1))
        else:
            trends['roe_change_2yr'].append(None)

        # ===============================
        # DEBT TREND CALCULATIONS
        # ===============================
        # D/E change 1yr
        if i + 4 < len(balance_sheet):
            td_1y = extract_value(balance_sheet, 'totalDebt', i + 4, 0)
            eq_1y = extract_value(balance_sheet, 'totalStockholdersEquity', i + 4, 0)
            de_1y = safe_divide(td_1y, eq_1y) if eq_1y else 0
            trends['debt_to_equity_change_1yr'].append(round(debt_to_equity - de_1y, 2))
        else:
            trends['debt_to_equity_change_1yr'].append(None)

        # D/E change 2yr
        if i + 8 < len(balance_sheet):
            td_2y = extract_value(balance_sheet, 'totalDebt', i + 8, 0)
            eq_2y = extract_value(balance_sheet, 'totalStockholdersEquity', i + 8, 0)
            de_2y = safe_divide(td_2y, eq_2y) if eq_2y else 0
            trends['debt_to_equity_change_2yr'].append(round(debt_to_equity - de_2y, 2))
        else:
            trends['debt_to_equity_change_2yr'].append(None)

        # Current ratio change 1yr
        if i + 4 < len(balance_sheet):
            ca_1y = extract_value(balance_sheet, 'totalCurrentAssets', i + 4, 0)
            cl_1y = extract_value(balance_sheet, 'totalCurrentLiabilities', i + 4, 0)
            cr_1y = safe_divide(ca_1y, cl_1y) if cl_1y else 0
            trends['current_ratio_change_1yr'].append(round(current_ratio - cr_1y, 2))
        else:
            trends['current_ratio_change_1yr'].append(None)

        # Is deleveraging (1 if D/E improving vs 1yr ago)
        if i + 4 < len(balance_sheet):
            td_1y = extract_value(balance_sheet, 'totalDebt', i + 4, 0)
            eq_1y = extract_value(balance_sheet, 'totalStockholdersEquity', i + 4, 0)
            de_1y = safe_divide(td_1y, eq_1y) if eq_1y else 0
            trends['is_deleveraging'].append(1 if debt_to_equity < de_1y else 0)
        else:
            trends['is_deleveraging'].append(None)

        # ===============================
        # EARNINGS QUALITY / AUDIT METRICS (NEW)
        # ===============================
        # Debt maturity breakdown
        trends['short_term_debt'].append(short_term_debt_val)
        long_term_debt_val = total_debt - short_term_debt_val if total_debt > 0 else 0
        trends['long_term_debt'].append(long_term_debt_val)
        trends['short_term_debt_pct'].append(
            round(safe_divide(short_term_debt_val, total_debt) * 100, 1) if total_debt > 0 else 0
        )

        # === DILUTION METRICS (use actual SBC) ===
        sbc_val = abs(sbc_actual) if sbc_actual else 0
        trends['sbc_actual'].append(sbc_val)  # Actual SBC from dedicated field
        trends['sbc_to_revenue_pct'].append(
            round(safe_divide(sbc_val, revenue) * 100, 1) if revenue > 0 else 0
        )

        # === EARNINGS QUALITY METRICS (use other non-cash items) ===
        other_non_cash_val = other_non_cash_items if other_non_cash_items else 0
        trends['other_non_cash_items'].append(other_non_cash_val)  # Impairments, writedowns
        trends['d_and_a'].append(d_and_a_val)

        # Keep legacy fields for backwards compatibility
        trends['sbc_estimate'].append(sbc_val)  # Now points to actual SBC
        trends['non_cash_adjustments'].append(other_non_cash_val)  # Now points to other items

        # Dilution analysis
        trends['basic_shares'].append(basic_shares_val)
        trends['diluted_shares'].append(diluted_shares_val)
        dilution_pct_val = round(
            safe_divide(diluted_shares_val - basic_shares_val, basic_shares_val) * 100, 2
        ) if basic_shares_val > 0 else 0
        trends['dilution_pct'].append(dilution_pct_val)

        # GAAP vs Adjusted earnings bridge
        # Include: SBC + D&A + other non-cash items (impairments, writedowns)
        trends['gaap_net_income'].append(net_income)
        all_non_cash = sbc_val + d_and_a_val + abs(other_non_cash_val)
        adjusted_earnings_val = net_income + all_non_cash
        trends['adjusted_earnings'].append(adjusted_earnings_val)
        gaap_adjusted_gap = round(
            safe_divide(all_non_cash, abs(net_income)) * 100, 1
        ) if net_income != 0 else 0
        trends['gaap_adjusted_gap_pct'].append(gaap_adjusted_gap)

        # ===============================
        # METADATA
        # ===============================
        trends['quarters'].append(f"Q{i}")
        trends['period_dates'].append(period_date)

    logger.info(f"Extracted {n} quarters of trend data with {len(trends)} metrics")
    return trends


def filter_trends_for_agent(quarterly_trends: dict, agent_type: str) -> dict:
    """
    Filter quarterly trends to only include metrics relevant to a specific agent.

    Args:
        quarterly_trends: Full trends dict from extract_quarterly_trends
        agent_type: 'debt', 'cashflow', or 'growth'

    Returns:
        Filtered trends dict with only relevant metrics
    """
    agent_metrics = {
        'debt': [
            'debt_to_equity', 'net_debt_to_ebitda', 'interest_coverage',
            'total_debt', 'debt_to_assets', 'current_ratio', 'net_debt',
            'cash_position', 'quarters', 'period_dates'
        ],
        'cashflow': [
            'fcf_margin', 'ocf_to_revenue', 'capex_intensity', 'free_cash_flow',
            'operating_cash_flow', 'capex', 'dividends_paid', 'share_buybacks',
            'shareholder_payout', 'fcf_payout_ratio', 'fcf_to_net_income',
            'quarters', 'period_dates'
        ],
        'growth': [
            'revenue', 'net_margin', 'operating_margin', 'gross_margin',
            'revenue_growth_yoy', 'eps', 'eps_growth_yoy', 'operating_income',
            'ebitda', 'quarters', 'period_dates'
        ]
    }

    if agent_type not in agent_metrics:
        return quarterly_trends

    relevant_metrics = agent_metrics[agent_type]
    return {k: v for k, v in quarterly_trends.items() if k in relevant_metrics}


def identify_phases(quarterly_trends: dict) -> List[Dict]:
    """
    Identify distinct phases in the company's financial trajectory.

    Detects patterns like:
    - Deleveraging/Re-leveraging cycles
    - Growth acceleration/deceleration phases
    - Margin expansion/compression periods

    Returns:
        List of phase dicts with name, quarters, metric, and change
    """
    phases = []

    # Analyze debt_to_equity for leverage cycles
    dte = quarterly_trends.get('debt_to_equity', [])
    if len(dte) >= 4:
        phases.extend(_detect_trend_phases(dte, 'debt_to_equity', 'Deleveraging', 'Re-leveraging'))

    # Analyze revenue_growth_yoy for growth phases
    growth = quarterly_trends.get('revenue_growth_yoy', [])
    if len(growth) >= 4:
        phases.extend(_detect_growth_phases(growth))

    # Analyze net_margin for profitability phases
    margin = quarterly_trends.get('net_margin', [])
    if len(margin) >= 4:
        phases.extend(_detect_trend_phases(margin, 'net_margin', 'Margin Compression', 'Margin Expansion'))

    return phases


def _detect_trend_phases(values: List[float], metric_name: str,
                         decreasing_name: str, increasing_name: str,
                         min_quarters: int = 3) -> List[Dict]:
    """
    Detect phases where a metric consistently increases or decreases.

    Args:
        values: List of metric values (index 0 = most recent)
        metric_name: Name of the metric for labeling
        decreasing_name: Label for decreasing trend (e.g., "Deleveraging")
        increasing_name: Label for increasing trend (e.g., "Re-leveraging")
        min_quarters: Minimum quarters for a phase to be significant

    Returns:
        List of phase dicts
    """
    phases = []
    if len(values) < min_quarters:
        return phases

    # Detect consecutive trends (note: values[0] is most recent)
    i = 0
    while i < len(values) - 1:
        start_idx = i
        start_val = values[i]

        # Determine initial direction
        if values[i] > values[i + 1]:
            direction = 'increasing'  # Value was higher before (recent is lower)
            phase_name = decreasing_name
        elif values[i] < values[i + 1]:
            direction = 'decreasing'  # Value was lower before (recent is higher)
            phase_name = increasing_name
        else:
            i += 1
            continue

        # Find end of this phase
        j = i + 1
        while j < len(values) - 1:
            if direction == 'increasing' and values[j] <= values[j + 1]:
                break
            elif direction == 'decreasing' and values[j] >= values[j + 1]:
                break
            j += 1

        end_idx = j
        end_val = values[j]

        # Only record significant phases
        if end_idx - start_idx >= min_quarters - 1:
            change = round(start_val - end_val, 2)
            change_str = f"{'+' if change > 0 else ''}{change}"
            if metric_name == 'debt_to_equity':
                change_str += 'x'
            elif 'margin' in metric_name:
                change_str += ' pts'

            phases.append({
                'name': phase_name,
                'quarters': f"Q{end_idx}-Q{start_idx}",
                'metric': metric_name,
                'change': change_str,
                'start_value': end_val,
                'end_value': start_val
            })

        i = j

    return phases


def _detect_growth_phases(growth_values: List[float]) -> List[Dict]:
    """
    Detect growth acceleration and deceleration phases.

    Args:
        growth_values: List of YoY growth rates (index 0 = most recent)

    Returns:
        List of phase dicts
    """
    phases = []
    if len(growth_values) < 4:
        return phases

    # Filter out None values
    valid_values = [(i, v) for i, v in enumerate(growth_values) if v is not None]
    if len(valid_values) < 4:
        return phases

    # Detect periods of acceleration vs deceleration
    i = 0
    while i < len(valid_values) - 1:
        start_idx, start_val = valid_values[i]

        # Determine direction (acceleration = growth rate increasing)
        if i + 1 < len(valid_values):
            _, next_val = valid_values[i + 1]
            if start_val > next_val:
                direction = 'accelerating'
                phase_name = 'Growth Acceleration'
            elif start_val < next_val:
                direction = 'decelerating'
                phase_name = 'Growth Deceleration'
            else:
                i += 1
                continue

            # Find end of phase
            j = i + 1
            while j < len(valid_values) - 1:
                _, curr = valid_values[j]
                _, next_v = valid_values[j + 1]
                if direction == 'accelerating' and curr <= next_v:
                    break
                elif direction == 'decelerating' and curr >= next_v:
                    break
                j += 1

            end_idx, end_val = valid_values[j]

            # Record significant phases (3+ quarters)
            if j - i >= 2:
                change = round(start_val - end_val, 1)
                phases.append({
                    'name': phase_name,
                    'quarters': f"Q{end_idx}-Q{start_idx}",
                    'metric': 'revenue_growth_yoy',
                    'change': f"{'+' if change > 0 else ''}{change} pts",
                    'start_value': end_val,
                    'end_value': start_val
                })

            i = j
        else:
            break

    return phases


def find_inflection_points(quarterly_trends: dict) -> List[Dict]:
    """
    Detect inflection points where key metrics reverse direction.

    An inflection point is where a sustained trend reverses:
    - Deleveraging → Re-leveraging
    - Margin expansion → Compression
    - Growth acceleration → Deceleration

    Returns:
        List of inflection point dicts with quarter, metric, event, from/to
    """
    inflection_points = []

    # Check key metrics for inflection points
    metrics_to_check = [
        ('debt_to_equity', 'decreasing', 'increasing'),
        ('net_margin', 'increasing', 'decreasing'),
        ('revenue_growth_yoy', 'accelerating', 'decelerating'),
        ('fcf_margin', 'increasing', 'decreasing'),
    ]

    for metric_name, positive_trend, negative_trend in metrics_to_check:
        values = quarterly_trends.get(metric_name, [])
        inflections = _find_metric_inflections(values, metric_name, positive_trend, negative_trend)
        inflection_points.extend(inflections)

    # Sort by quarter (most recent first)
    inflection_points.sort(key=lambda x: int(x['quarter'].replace('Q', '')))

    return inflection_points


def _find_metric_inflections(values: List[float], metric_name: str,
                             positive_trend: str, negative_trend: str,
                             lookback: int = 3) -> List[Dict]:
    """
    Find inflection points in a single metric's time series.

    Args:
        values: List of values (index 0 = most recent)
        metric_name: Name of the metric
        positive_trend: Label for positive direction
        negative_trend: Label for negative direction
        lookback: Number of quarters to check for sustained trend

    Returns:
        List of inflection point dicts
    """
    inflections = []
    if len(values) < lookback * 2:
        return inflections

    # Filter out None values for analysis
    valid_indices = [i for i, v in enumerate(values) if v is not None]
    if len(valid_indices) < lookback * 2:
        return inflections

    for i in range(lookback, len(valid_indices) - lookback):
        idx = valid_indices[i]
        before_indices = valid_indices[i - lookback:i]
        after_indices = valid_indices[i:i + lookback]

        before_values = [values[j] for j in before_indices]
        after_values = [values[j] for j in after_indices]

        # Check if there's a trend before and after
        before_trend = _get_trend_direction(before_values)
        after_trend = _get_trend_direction(after_values)

        if before_trend and after_trend and before_trend != after_trend:
            # Map trend direction to labels
            from_label = positive_trend if before_trend == 'up' else negative_trend
            to_label = positive_trend if after_trend == 'up' else negative_trend

            inflections.append({
                'quarter': f"Q{idx}",
                'metric': metric_name,
                'event': 'trend_reversal',
                'from': from_label,
                'to': to_label,
                'value_at_inflection': values[idx]
            })

    return inflections


def _get_trend_direction(values: List[float]) -> Optional[str]:
    """
    Determine if values show an upward or downward trend.

    Args:
        values: List of values (earlier values first in time, so index 0 is oldest)

    Returns:
        'up', 'down', or None if no clear trend
    """
    if not values or len(values) < 2:
        return None

    # Count ups and downs
    ups = sum(1 for i in range(len(values) - 1) if values[i] < values[i + 1])
    downs = sum(1 for i in range(len(values) - 1) if values[i] > values[i + 1])

    total = ups + downs
    if total == 0:
        return None

    # Require majority agreement
    if ups / total >= 0.6:
        return 'up'
    elif downs / total >= 0.6:
        return 'down'
    return None


def find_peaks_troughs(quarterly_trends: dict) -> Dict:
    """
    Find 5-year peaks and troughs for key metrics.

    Returns:
        Dict with peak/trough info for each metric
    """
    peaks_troughs = {}

    metrics = [
        'debt_to_equity',
        'net_margin',
        'fcf_margin',
        'operating_margin',
        'revenue_growth_yoy',
        'interest_coverage'
    ]

    for metric in metrics:
        values = quarterly_trends.get(metric, [])
        if not values:
            continue

        # Filter out None values
        valid_data = [(i, v) for i, v in enumerate(values) if v is not None]
        if not valid_data:
            continue

        # Find max and min
        max_entry = max(valid_data, key=lambda x: x[1])
        min_entry = min(valid_data, key=lambda x: x[1])

        peaks_troughs[metric] = {
            'peak': {
                'value': max_entry[1],
                'quarter': f"Q{max_entry[0]}"
            },
            'trough': {
                'value': min_entry[1],
                'quarter': f"Q{min_entry[0]}"
            },
            'current': values[0] if values else None,
            'range': round(max_entry[1] - min_entry[1], 2)
        }

    return peaks_troughs


def compute_trend_insights(quarterly_trends: dict) -> dict:
    """
    Compute comprehensive trend insights from quarterly data.

    This is the main function that combines phase identification,
    inflection point detection, and peak/trough analysis.

    Args:
        quarterly_trends: Output from extract_quarterly_trends()

    Returns:
        dict with phases, inflection_points, and peaks_troughs
    """
    return {
        'phases': identify_phases(quarterly_trends),
        'inflection_points': find_inflection_points(quarterly_trends),
        'peaks_troughs': find_peaks_troughs(quarterly_trends)
    }


def compute_ml_features(quarterly_trends: dict) -> dict:
    """
    Compute the full ML feature set from quarterly trends.

    This computes the temporal derivatives that the v3.6.5 ML models expect:
    - *_yoy: Year-over-year change (index 0 vs index 4)
    - *_trend_1yr / *_trend_2yr: Difference over 4/8 quarters
    - *_velocity_qoq: Quarter-over-quarter rate of change
    - is_* flags: Boolean indicators

    Args:
        quarterly_trends: Output from extract_quarterly_trends()

    Returns:
        dict with 'debt', 'cashflow', 'growth' keys containing ML-ready features
    """
    def get_val(arr, idx, default=0.0):
        """Safely get value from array by index, converting Decimal to float."""
        if arr and len(arr) > idx and arr[idx] is not None:
            val = arr[idx]
            # Convert Decimal to float for numeric operations
            if hasattr(val, '__float__'):
                return float(val)
            return val
        return default

    def compute_yoy(arr, idx=0):
        """Compute YoY change: (current - 4q_ago) / 4q_ago * 100."""
        current = get_val(arr, idx)
        past = get_val(arr, idx + 4)
        if past and past != 0:
            return round(((current - past) / abs(past)) * 100, 2)
        return 0.0

    def compute_trend(arr, periods, idx=0):
        """Compute trend: current - periods_ago."""
        current = get_val(arr, idx)
        past = get_val(arr, idx + periods)
        return round(current - past, 4) if past is not None else 0.0

    def compute_velocity(arr, idx=0):
        """Compute QoQ velocity: (current - 1q_ago) / 1q_ago * 100."""
        current = get_val(arr, idx)
        past = get_val(arr, idx + 1)
        if past and past != 0:
            return round(((current - past) / abs(past)) * 100, 2)
        return 0.0

    def compute_acceleration(arr, idx=0):
        """Compute acceleration: velocity change over time."""
        vel_current = compute_velocity(arr, idx)
        vel_past = compute_velocity(arr, idx + 1)
        return round(vel_current - vel_past, 2)

    # Extract arrays
    dte = quarterly_trends.get('debt_to_equity', [])
    nde = quarterly_trends.get('net_debt_to_ebitda', [])
    ic = quarterly_trends.get('interest_coverage', [])
    cr = quarterly_trends.get('current_ratio', [])
    td = quarterly_trends.get('total_debt', [])
    nd = quarterly_trends.get('net_debt', [])
    da = quarterly_trends.get('debt_to_assets', [])
    cash = quarterly_trends.get('cash_position', [])

    fcf_m = quarterly_trends.get('fcf_margin', [])
    ocf_r = quarterly_trends.get('ocf_to_revenue', [])
    ci = quarterly_trends.get('capex_intensity', [])
    fcf = quarterly_trends.get('free_cash_flow', [])
    ocf = quarterly_trends.get('operating_cash_flow', [])
    capex = quarterly_trends.get('capex', [])
    fcf_ni = quarterly_trends.get('fcf_to_net_income', [])

    rev = quarterly_trends.get('revenue', [])
    nm = quarterly_trends.get('net_margin', [])
    om = quarterly_trends.get('operating_margin', [])
    gm = quarterly_trends.get('gross_margin', [])
    rev_yoy = quarterly_trends.get('revenue_growth_yoy', [])
    eps = quarterly_trends.get('eps', [])
    eps_yoy = quarterly_trends.get('eps_growth_yoy', [])
    oi = quarterly_trends.get('operating_income', [])
    ebitda = quarterly_trends.get('ebitda', [])

    # ===============================
    # DEBT FEATURES (58 total in v3.6.5)
    # ===============================
    debt_features = {
        # Base metrics
        'total_debt': get_val(td, 0),
        'total_equity': 0,  # Not directly in trends, derived from D/E
        'total_assets': 0,  # Not directly in trends
        'cash': get_val(cash, 0),
        'interest_expense': 0,  # Derived from interest coverage
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),
        'current_assets': 0,
        'current_liabilities': 0,
        'inventory': 0,

        # Ratios
        'debt_to_equity': get_val(dte, 0),
        'debt_to_assets': get_val(da, 0),
        'interest_coverage': get_val(ic, 0),
        'net_debt': get_val(nd, 0),
        'net_debt_to_ebitda': get_val(nde, 0),
        'current_ratio': get_val(cr, 0),
        'quick_ratio': get_val(cr, 0) * 0.9,  # Approximation

        # Temporal features - 1yr trends
        'debt_to_equity_trend_1yr': compute_trend(dte, 4),
        'net_debt_to_ebitda_trend_1yr': compute_trend(nde, 4),
        'current_ratio_trend_1yr': compute_trend(cr, 4),

        # Temporal features - 2yr trends
        'debt_to_equity_trend_2yr': compute_trend(dte, 8),
        'net_debt_to_ebitda_trend_2yr': compute_trend(nde, 8),

        # YoY changes
        'debt_to_equity_yoy': compute_yoy(dte),
        'net_debt_to_ebitda_yoy': compute_yoy(nde),
        'interest_coverage_yoy': compute_yoy(ic),
        'current_ratio_yoy': compute_yoy(cr),

        # Velocity (QoQ rate of change)
        'debt_to_equity_velocity_qoq': compute_velocity(dte),
        'net_debt_velocity_qoq': compute_velocity(nd),
        'interest_expense_velocity_qoq': 0.0,

        # Acceleration
        'debt_to_equity_acceleration_qoq': compute_acceleration(dte),

        # Flags
        'is_deleveraging': 1 if get_val(dte, 0) < get_val(dte, 4) else 0,

        # ROA/ROIC (derived)
        'roa': 0.0,  # Would need net_income / total_assets
        'roic': 0.0,  # Would need NOPAT / invested capital
        'roa_yoy': 0.0,
        'roa_trend_2yr': 0.0,
        'roic_yoy': 0.0,

        # DuPont
        'asset_turnover': 0.0,
        'asset_turnover_yoy': 0.0,
        'equity_multiplier': 0.0,

        # Debt coverage
        'fcf_to_debt': safe_divide(get_val(fcf, 0), get_val(td, 0)),
        'ebitda_to_interest': get_val(ic, 0),  # Approximation
    }

    # ===============================
    # CASHFLOW FEATURES (42 total in v3.6.5)
    # ===============================
    cashflow_features = {
        # Base metrics
        'operating_cash_flow': get_val(ocf, 0),
        'capital_expenditures': get_val(capex, 0),
        'free_cash_flow': get_val(fcf, 0),
        'net_income': 0,  # Not directly available
        'revenue': get_val(rev, 0),
        'working_capital_change': 0,
        'dividend_payout': 0,
        'share_buybacks': 0,

        # Ratios
        'fcf_to_net_income': get_val(fcf_ni, 0),
        'fcf_margin': get_val(fcf_m, 0),
        'total_capital_return': 0,
        'cash_conversion_cycle': 0,

        # Temporal features
        'fcf_margin_trend_1yr': compute_trend(fcf_m, 4),
        'fcf_trend_4q': compute_trend(fcf, 4),
        'fcf_margin_velocity_qoq': compute_velocity(fcf_m),
        'fcf_velocity_qoq': compute_velocity(fcf),
        'ocf_velocity_qoq': compute_velocity(ocf),
        'fcf_margin_acceleration': compute_acceleration(fcf_m),

        # Efficiency
        'ocf_to_revenue': get_val(ocf_r, 0),
        'ocf_to_revenue_yoy': compute_yoy(ocf_r),
        'fcf_to_revenue': get_val(fcf_m, 0),  # Same as fcf_margin

        # Capex
        'capex_intensity': get_val(ci, 0),
        'capex_intensity_trend': compute_trend(ci, 4),

        # Working capital
        'dio': 0.0,
        'working_capital_to_revenue': 0.0,

        # Include some debt features for model compatibility
        'total_debt': get_val(td, 0),
        'total_equity': 0,
        'total_assets': 0,
        'cash': get_val(cash, 0),
        'interest_expense': 0,
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),
        'current_assets': 0,
        'current_liabilities': 0,
        'inventory': 0,
        'gross_profit': 0,
        'eps': get_val(eps, 0),
    }

    # ===============================
    # GROWTH FEATURES (63 total in v3.6.5)
    # ===============================
    growth_features = {
        # YoY growth
        'revenue_growth_yoy': get_val(rev_yoy, 0, 0.0),
        'revenue_growth_qoq': compute_velocity(rev),
        'revenue_cagr_2yr': 0.0,  # Would need 8-quarter calculation
        'revenue_growth_vs_industry': 0.0,
        'revenue_growth_trend': compute_trend(rev_yoy, 4) if rev_yoy else 0.0,

        # Margin changes
        'operating_margin_change_1yr': compute_trend(om, 4),
        'operating_margin_momentum': compute_velocity(om),

        # ROE
        'roe_change_1yr': 0.0,
        'roe_trend_2yr': 0.0,

        # Cash quality
        'ocf_to_ni_ratio': 0.0,
        'fcf_to_ni_ratio': get_val(fcf_ni, 0),
        'quality_of_earnings': 0.0,

        # Investment
        'reinvestment_rate': 0.0,
        'growth_capex_pct': 0.0,

        # Velocity
        'revenue_growth_velocity': compute_velocity(rev_yoy) if rev_yoy else 0.0,
        'revenue_velocity_qoq': compute_velocity(rev),
        'revenue_growth_acceleration': compute_acceleration(rev_yoy) if rev_yoy else 0.0,

        # Momentum flags
        'growth_momentum_positive': 1 if get_val(rev_yoy, 0, 0) > 0 else 0,
        'growth_deceleration_warning': 1 if get_val(rev_yoy, 0, 0) < get_val(rev_yoy, 1, 0) else 0,

        # Margin trends
        'operating_margin_trend_1yr': compute_trend(om, 4),
        'operating_margin_velocity_qoq': compute_velocity(om),
        'operating_margin_acceleration': compute_acceleration(om),
        'margin_momentum_positive': 1 if get_val(om, 0) > get_val(om, 4) else 0,
        'is_margin_expanding': 1 if get_val(om, 0) > get_val(om, 1) else 0,

        # Long-term trends
        'revenue_growth_trend_4q': compute_trend(rev_yoy, 4) if rev_yoy else 0.0,
        'is_growth_accelerating': 1 if compute_velocity(rev_yoy) > 0 else 0 if rev_yoy else 0,

        # Base metrics
        'gross_profit': 0,
        'net_income_growth_yoy': compute_yoy(nm) if nm else 0.0,
        'eps_growth_yoy': get_val(eps_yoy, 0, 0.0),
        'is_profitability_improving': 1 if get_val(nm, 0) > get_val(nm, 4) else 0,

        # Margins
        'gross_margin': get_val(gm, 0),
        'operating_margin': get_val(om, 0),
        'net_margin': get_val(nm, 0),

        # 2-year trends
        'gross_margin_trend_2yr': compute_trend(gm, 8),
        'operating_margin_trend_2yr': compute_trend(om, 8),
        'net_margin_trend_2yr': compute_trend(nm, 8),

        # Other
        'roe_decomposed': 0.0,
        'earnings_stability': 0.0,
        'operating_leverage': 0.0,
        'revenue': get_val(rev, 0),
        'eps': get_val(eps, 0),
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),
    }

    return {
        'debt': {'current': debt_features},
        'cashflow': {'current': cashflow_features},
        'growth': {'current': growth_features}
    }


def extract_all_features(raw_financials: dict) -> dict:
    """
    Extract all key metrics for the 3-agent ensemble.

    This now computes the full ML feature set including temporal derivatives
    that the v3.6.5 models expect.

    Args:
        raw_financials: Dict with keys 'balance_sheet', 'income_statement', 'cash_flow'
                       Each contains list of quarterly data from FMP API

    Returns:
        dict with 'debt', 'cashflow', 'growth' keys, each containing metrics
    """
    balance_sheet = raw_financials.get('balance_sheet', [])
    income_statement = raw_financials.get('income_statement', [])
    cashflow = raw_financials.get('cash_flow', [])

    logger.info(f"Extracting features from {len(balance_sheet)} quarters of data")

    # First extract quarterly trends (20 quarters of raw data)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Compute ML features from quarterly trends
    ml_features = compute_ml_features(quarterly_trends)

    # Get base metrics for backward compatibility
    base_metrics = {
        'debt': extract_debt_metrics(balance_sheet, income_statement, cashflow),
        'cashflow': extract_cashflow_metrics(balance_sheet, income_statement, cashflow),
        'growth': extract_growth_metrics(balance_sheet, income_statement, cashflow),
    }

    # Merge ML features into base metrics
    # ML features take precedence (more complete)
    for agent_type in ['debt', 'cashflow', 'growth']:
        if agent_type in ml_features and 'current' in ml_features[agent_type]:
            # Merge ML features into base current metrics
            base_current = base_metrics[agent_type].get('current', {})
            ml_current = ml_features[agent_type]['current']
            # ML features override base features
            merged = {**base_current, **ml_current}
            base_metrics[agent_type]['current'] = merged

    # [FEATURE_DEBUG] Log extracted features for each agent
    logger.info(f"[FEATURE_DEBUG] === FEATURES EXTRACTED ===")
    for agent_type in ['debt', 'cashflow', 'growth']:
        current = base_metrics[agent_type].get('current', {})
        logger.info(f"[FEATURE_DEBUG] {agent_type.upper()} metrics count: {len(current)}")
        logger.info(f"[FEATURE_DEBUG] {agent_type.upper()} metric names: {list(current.keys())[:10]}...")

    # [FEATURE_DEBUG] Log sample values for key metrics
    debt_current = base_metrics['debt'].get('current', {})
    logger.info(f"[FEATURE_DEBUG] Debt sample: debt_to_equity={debt_current.get('debt_to_equity')}, "
                f"interest_coverage={debt_current.get('interest_coverage')}, "
                f"current_ratio={debt_current.get('current_ratio')}")

    cashflow_current = base_metrics['cashflow'].get('current', {})
    logger.info(f"[FEATURE_DEBUG] Cashflow sample: free_cash_flow={cashflow_current.get('free_cash_flow')}, "
                f"fcf_margin={cashflow_current.get('fcf_margin')}, "
                f"operating_cash_flow={cashflow_current.get('operating_cash_flow')}")

    growth_current = base_metrics['growth'].get('current', {})
    logger.info(f"[FEATURE_DEBUG] Growth sample: roe={growth_current.get('roe')}, "
                f"revenue_growth_yoy={growth_current.get('revenue_growth_yoy')}, "
                f"net_margin={growth_current.get('net_margin')}")

    return base_metrics


def format_currency(value, billions=True, currency_code: str = 'USD', usd_rate: float = 1.0) -> str:
    """
    Format a number as currency string with optional USD equivalent.

    For non-USD currencies, shows both native and USD equivalent:
    - "DKK 75.0B (~$10.7B)"

    Args:
        value: The numeric value to format
        billions: If True, uses auto-scaling (B/M/K)
        currency_code: ISO currency code (e.g., 'USD', 'DKK', 'EUR')
        usd_rate: Exchange rate to USD (1 native = X USD)

    Returns:
        Formatted currency string
    """
    if value is None:
        return 'N/A'

    from .currency import CurrencyFormatter
    fmt = CurrencyFormatter(currency_code, usd_rate)

    if billions:
        return fmt.money(value)
    else:
        return fmt.full(value)


def prepare_agent_payload(ticker: str, fiscal_year: int, model_inference: dict,
                          features: dict, agent_type: str,
                          currency_info: dict = None) -> dict:
    """
    Prepare the payload to send to a Bedrock agent.

    Args:
        ticker: Stock ticker
        fiscal_year: Fiscal year
        model_inference: Model prediction results
        features: Extracted features dict
        agent_type: 'debt', 'cashflow', or 'growth'
        currency_info: Optional dict with 'code' and 'usd_rate' for multi-currency support

    Returns:
        dict formatted for agent consumption
    """
    agent_features = features.get(agent_type, {})
    currency_info = currency_info or {}

    return {
        'ticker': ticker,
        'fiscal_year': fiscal_year,
        'fiscal_quarter': 'Q4',  # Assume latest quarter

        'model_inference': {
            'prediction': model_inference.get('prediction', 'HOLD'),
            'confidence': model_inference.get('confidence', 0.5),
            'ci_width': model_inference.get('ci_width', 0.5),
            'confidence_interpretation': model_inference.get('confidence_interpretation', 'MODERATE'),
            'probabilities': model_inference.get('probabilities', {
                'SELL': 0.33,
                'HOLD': 0.34,
                'BUY': 0.33
            })
        },

        'key_metrics': agent_features,

        'currency_info': {
            'code': currency_info.get('code', 'USD'),
            'usd_rate': currency_info.get('usd_rate', 1.0),
            'rate_fetched_at': currency_info.get('rate_fetched_at')
        },

        'formatting_hints': {
            'use_billions': True,
            'currency': currency_info.get('code', 'USD'),
            'usd_rate': currency_info.get('usd_rate', 1.0),
            'include_emojis': True
        }
    }


# =============================================================================
# METRICS HISTORY CACHE - Quarter-based schema with embedded categories
# =============================================================================
#
# Optimized schema: 20 items per ticker (one per quarter) instead of 140.
# Each item contains all 7 metric categories, filtered at query time.
#
# Schema:
#   PK: ticker (e.g., "AAPL")
#   SK: fiscal_date (e.g., "2025-09-27") - human-readable, sorts chronologically
#
# Benefits:
#   - 7x fewer DynamoDB items (20 vs 140)
#   - Simpler writes (1 batch vs 6)
#   - No GSIs needed
#   - Easy to query "all categories for N quarters"
#   - Client-side filtering for specific categories (~85% token savings preserved)

# Mapping from category to metric names in quarterly_trends
CATEGORY_METRICS = {
    'revenue_profit': [
        'revenue', 'net_income', 'gross_profit', 'operating_income', 'eps',
        'gross_margin', 'operating_margin', 'net_margin', 'revenue_growth_yoy',
        'revenue_growth_qoq', 'roe', 'ebitda', 'eps_growth_yoy', 'net_income_growth_yoy',
        'gross_margin_change_1yr', 'operating_margin_change_1yr', 'net_margin_change_1yr',
        'is_margin_expanding'
    ],
    'cashflow': [
        'operating_cash_flow', 'free_cash_flow', 'fcf_margin', 'ocf_to_revenue',
        'capex', 'capex_intensity', 'dividends_paid', 'share_buybacks',
        'fcf_to_net_income', 'working_capital', 'reinvestment_rate',
        'shareholder_payout', 'fcf_payout_ratio', 'working_capital_to_revenue',
        'total_capital_return', 'fcf_change_yoy', 'ocf_change_yoy', 'capex_change_yoy'
    ],
    'balance_sheet': [
        'total_debt', 'cash_position', 'net_debt', 'total_equity',
        'total_assets', 'working_capital', 'current_assets', 'current_liabilities',
        'short_term_debt', 'long_term_debt'
    ],
    'debt_leverage': [
        'debt_to_equity', 'debt_to_assets', 'interest_coverage',
        'current_ratio', 'quick_ratio', 'short_term_debt', 'long_term_debt',
        'short_term_debt_pct', 'net_debt_to_ebitda', 'fcf_to_debt',
        'debt_to_equity_change_1yr', 'debt_to_equity_change_2yr',
        'current_ratio_change_1yr', 'is_deleveraging', 'interest_expense',
        'equity_multiplier'
    ],
    'earnings_quality': [
        'gaap_net_income', 'sbc_actual', 'd_and_a', 'adjusted_earnings',
        'sbc_to_revenue_pct', 'gaap_adjusted_gap_pct', 'other_non_cash_items',
        'non_cash_adjustments'
    ],
    'dilution': [
        'basic_shares', 'diluted_shares', 'dilution_pct', 'share_buybacks'
    ],
    'valuation': [
        'roa', 'roic', 'roe', 'asset_turnover', 'equity_multiplier',
        'roic_growth', 'roe_change_2yr', 'capital_return_yield'
    ]
}

# Categories populated from event-based data (earnings/dividends), not quarterly_trends arrays.
# These are embedded into the same per-quarter DynamoDB items alongside CATEGORY_METRICS.
EVENT_BASED_CATEGORIES = ['earnings_events', 'dividend']


def _align_earnings_to_quarters(
    earnings_history: List[Dict[str, Any]],
    period_dates: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Align earnings event records to fiscal quarter period_dates.

    Earnings are matched to the most recent period_date that falls BEFORE
    the earnings announcement date, since earnings always report a quarter
    that has already ended.

    Args:
        earnings_history: List of FMP earnings dicts with 'date', 'epsActual',
            'epsEstimated', 'revenueActual', 'revenueEstimated'
        period_dates: Sorted list of fiscal quarter end dates (e.g., ["2024-09-28", "2024-12-28"])

    Returns:
        Dict mapping fiscal_date -> earnings metrics dict
    """
    if not earnings_history or not period_dates:
        return {}

    sorted_dates = sorted(period_dates)
    aligned = {}

    for earning in earnings_history:
        earn_date = earning.get('date', '')
        if not earn_date:
            continue

        # Find the most recent period_date before the earnings announcement
        best_match = None
        for pd in sorted_dates:
            if pd <= earn_date:
                best_match = pd
            else:
                break

        if not best_match:
            continue

        # Prefer reported earnings (has epsActual) over upcoming estimates.
        # If this quarter already has reported data, don't overwrite with an estimate.
        # If this quarter only has an estimate, allow a reported record to replace it.
        if best_match in aligned:
            existing_has_actual = 'eps_actual' in aligned[best_match]
            this_has_actual = earning.get('epsActual') is not None
            if existing_has_actual or not this_has_actual:
                continue

        eps_actual = earning.get('epsActual')
        eps_estimated = earning.get('epsEstimated')
        rev_actual = earning.get('revenueActual')
        rev_estimated = earning.get('revenueEstimated')

        metrics = {
            'earnings_date': earn_date,
        }

        if eps_actual is not None:
            metrics['eps_actual'] = eps_actual
        if eps_estimated is not None:
            metrics['eps_estimated'] = eps_estimated
        if eps_actual is not None and eps_estimated is not None:
            metrics['eps_surprise_pct'] = safe_divide(
                (float(eps_actual) - float(eps_estimated)),
                abs(float(eps_estimated))
            ) * 100
            metrics['eps_beat'] = float(eps_actual) > float(eps_estimated)

        if rev_actual is not None:
            metrics['revenue_actual'] = rev_actual
        if rev_estimated is not None:
            metrics['revenue_estimated'] = rev_estimated
        if rev_actual is not None and rev_estimated is not None and rev_estimated != 0:
            metrics['revenue_surprise_pct'] = safe_divide(
                (float(rev_actual) - float(rev_estimated)),
                abs(float(rev_estimated))
            ) * 100

        aligned[best_match] = metrics

    return aligned


def _align_dividends_to_quarters(
    dividend_history: List[Dict[str, Any]],
    period_dates: List[str]
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate dividend payment records into fiscal quarters.

    Each dividend payment is assigned to the most recent period_date before
    its ex-dividend date. Multiple payments in the same quarter are aggregated.

    Args:
        dividend_history: List of FMP dividend dicts with 'date', 'adjDividend',
            'yield', 'frequency'
        period_dates: Sorted list of fiscal quarter end dates

    Returns:
        Dict mapping fiscal_date -> dividend metrics dict.
        For non-dividend-paying companies (empty input), returns empty dict.
    """
    if not dividend_history or not period_dates:
        return {}

    sorted_dates = sorted(period_dates)
    # Aggregate dividends per quarter
    quarter_divs: Dict[str, list] = {}

    for div in dividend_history:
        div_date = div.get('date', '')
        if not div_date:
            continue

        # Find the most recent period_date before the ex-dividend date
        best_match = None
        for pd in sorted_dates:
            if pd <= div_date:
                best_match = pd
            else:
                break

        if not best_match:
            continue

        if best_match not in quarter_divs:
            quarter_divs[best_match] = []
        quarter_divs[best_match].append(div)

    # Build aggregated metrics per quarter
    aligned = {}
    for fiscal_date, divs in quarter_divs.items():
        total_dps = sum(d.get('adjDividend', 0) or 0 for d in divs)
        # Use the most recent dividend's yield and frequency
        latest = divs[0] if divs else {}
        frequency = latest.get('frequency', 'Unknown')

        metrics = {
            'dps': round(total_dps, 4) if total_dps else 0,
            'payments_in_quarter': len(divs),
            'frequency': frequency,
        }
        div_yield = latest.get('yield')
        if div_yield is not None:
            metrics['dividend_yield'] = div_yield

        # Annualize DPS based on frequency
        freq_multiplier = {
            'Quarterly': 4, 'Monthly': 12, 'Semi-Annual': 2,
            'Annual': 1, 'Special': 1
        }
        multiplier = freq_multiplier.get(frequency, 4)
        if total_dps > 0:
            metrics['annualized_dps'] = round(total_dps * multiplier, 4)

        aligned[fiscal_date] = metrics

    return aligned


def prepare_metrics_for_cache(
    ticker: str,
    quarterly_trends: Dict[str, Any],
    currency: str = "USD",
    source_cache_key: str = "",
    earnings_history: List[Dict[str, Any]] = None,
    dividend_history: List[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Transform quarterly_trends into quarter-based items for metrics-history-cache.

    Creates one DynamoDB item per quarter with all 9 metric categories embedded
    (7 from quarterly_trends + earnings_events + dividend from event data).
    This optimized schema reduces items from 140 to 20 per ticker while preserving
    the ability to filter by category at query time (~85% token savings).

    Args:
        ticker: Stock symbol (e.g., "AAPL")
        quarterly_trends: Dict from extract_quarterly_trends() with metric arrays
        currency: Currency code (e.g., "USD", "EUR")
        source_cache_key: Cache key from financial data cache (for traceability)
        earnings_history: Optional list of FMP earnings records (from fetch_earnings)
        dividend_history: Optional list of FMP dividend records (from fetch_dividends)

    Returns:
        List of items ready for DynamoDB batch_write_item.
        Each item represents one quarter with all categories.
        Expected: 20 items per ticker (one per quarter).

    Item structure:
        {
            "ticker": "AAPL",
            "fiscal_date": "2025-09-27",  # Sort key - human-readable
            "fiscal_year": 2025,
            "fiscal_quarter": "Q1",       # e.g., Q1, Q2, Q3, Q4
            "revenue_profit": { ... },    # ~18 metrics
            "cashflow": { ... },          # ~18 metrics
            "balance_sheet": { ... },     # ~10 metrics
            "debt_leverage": { ... },     # ~16 metrics
            "earnings_quality": { ... },  # ~8 metrics
            "dilution": { ... },          # ~4 metrics
            "valuation": { ... },         # ~8 metrics
            "earnings_events": { ... },   # EPS beat/miss, surprise % (optional)
            "dividend": { ... },          # DPS, yield, frequency (optional)
        }
    """
    items = []
    quarters = quarterly_trends.get('quarters', [])
    period_dates = quarterly_trends.get('period_dates', [])

    if not quarters:
        logger.warning(f"No quarters found in quarterly_trends for {ticker}")
        return items

    if not period_dates:
        logger.warning(f"No period_dates found in quarterly_trends for {ticker}")
        return items

    # Align event-based data to fiscal quarters
    earnings_by_quarter = _align_earnings_to_quarters(
        earnings_history or [], period_dates
    )
    dividend_by_quarter = _align_dividends_to_quarters(
        dividend_history or [], period_dates
    )

    now = int(time.time())
    expires_at = now + (90 * 24 * 60 * 60)  # 90 days TTL

    for q_idx, quarter in enumerate(quarters):
        fiscal_date = period_dates[q_idx] if q_idx < len(period_dates) else None

        if not fiscal_date:
            logger.warning(f"Skipping quarter {quarter} for {ticker}: no fiscal_date")
            continue

        # Extract fiscal year and quarter from the date
        # fiscal_date format: "2025-09-27"
        try:
            year = int(fiscal_date[:4])
            month = int(fiscal_date[5:7])
            # Determine fiscal quarter based on month
            # Most companies: Q1=Jan-Mar, Q2=Apr-Jun, Q3=Jul-Sep, Q4=Oct-Dec
            # Apple (Sep fiscal year end): Q1=Oct-Dec, Q2=Jan-Mar, Q3=Apr-Jun, Q4=Jul-Sep
            # For simplicity, use calendar quarters
            if month <= 3:
                fiscal_quarter = "Q1"
            elif month <= 6:
                fiscal_quarter = "Q2"
            elif month <= 9:
                fiscal_quarter = "Q3"
            else:
                fiscal_quarter = "Q4"
        except (ValueError, IndexError):
            year = None
            fiscal_quarter = None

        # Build item with all categories embedded
        item = {
            'ticker': ticker,
            'fiscal_date': fiscal_date,  # Sort key - human-readable date
            'fiscal_year': year,
            'fiscal_quarter': fiscal_quarter,
            'cached_at': now,
            'expires_at': expires_at,
            'currency': currency,
            'source_cache_key': source_cache_key
        }

        # Embed each quarterly_trends category's metrics
        has_any_metrics = False
        for category, metric_names in CATEGORY_METRICS.items():
            category_metrics = {}
            for metric_name in metric_names:
                if metric_name in quarterly_trends:
                    values = quarterly_trends[metric_name]
                    if q_idx < len(values) and values[q_idx] is not None:
                        category_metrics[metric_name] = values[q_idx]

            if category_metrics:
                item[category] = category_metrics
                has_any_metrics = True

        # Embed event-based categories (earnings + dividends)
        if fiscal_date in earnings_by_quarter:
            item['earnings_events'] = earnings_by_quarter[fiscal_date]
            has_any_metrics = True

        if fiscal_date in dividend_by_quarter:
            item['dividend'] = dividend_by_quarter[fiscal_date]
            has_any_metrics = True
        elif dividend_history is not None and len(dividend_history) == 0:
            # Explicitly signal non-dividend-paying company
            item['dividend'] = {'dividend_status': 'none', 'dps': 0}
            has_any_metrics = True

        # Only add item if we have at least one category with metrics
        if has_any_metrics:
            items.append(item)

    total_categories = 7 + (1 if earnings_by_quarter else 0) + (1 if dividend_by_quarter or (dividend_history is not None and len(dividend_history) == 0) else 0)
    logger.info(f"Prepared {len(items)} cache items for {ticker} (1 item per quarter, {total_categories} categories embedded)")
    return items
