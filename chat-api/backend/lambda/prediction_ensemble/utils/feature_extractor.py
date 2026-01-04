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

from typing import Optional, List, Dict, Tuple
from datetime import datetime
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
    dividends = abs(extract_value(cashflow, 'dividendsPaid', 0, 0))
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
        'period_dates': []          # Actual quarter end dates
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
        total_liabilities = extract_value(balance_sheet, 'totalLiabilities', i, 0)

        # Income statement metrics
        revenue = extract_value(income_statement, 'revenue', i, 0)
        gross_profit = extract_value(income_statement, 'grossProfit', i, 0)
        operating_income = extract_value(income_statement, 'operatingIncome', i, 0)
        net_income = extract_value(income_statement, 'netIncome', i, 0)
        ebitda = extract_value(income_statement, 'ebitda', i, 0)
        interest_expense_val = extract_value(income_statement, 'interestExpense', i, 0)
        eps = extract_value(income_statement, 'eps', i, 0)
        income_tax = extract_value(income_statement, 'incomeTaxExpense', i, 0)

        # Cash flow metrics
        fcf = extract_value(cashflow, 'freeCashFlow', i, 0)
        ocf = extract_value(cashflow, 'operatingCashFlow', i, 0)
        capex = abs(extract_value(cashflow, 'capitalExpenditure', i, 0))
        dividends = abs(extract_value(cashflow, 'dividendsPaid', i, 0))
        buybacks = abs(extract_value(cashflow, 'commonStockRepurchased', i, 0))

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
        roa = round(safe_divide(net_income * 4, total_assets) * 100, 1)  # Annualized
        roe = round(safe_divide(net_income * 4, total_equity) * 100, 1)  # Annualized
        # ROIC = NOPAT / Invested Capital, where NOPAT = Operating Income * (1 - tax rate)
        # Invested Capital = Total Equity + Total Debt - Cash
        tax_rate = safe_divide(income_tax, max(operating_income - interest_expense_val, 1))
        nopat = operating_income * (1 - min(tax_rate, 0.4))  # Cap tax rate at 40%
        invested_capital = total_equity + total_debt - cash
        roic = round(safe_divide(nopat * 4, invested_capital) * 100, 1)  # Annualized

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
        trends['fcf_to_net_income'].append(round(safe_divide(fcf, max(net_income, 1)), 2))
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

    # Convert Decimal to float for numeric operations
    values = [float(v) if v is not None else 0.0 for v in values]

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

    # Convert Decimal to float and filter out None values
    valid_values = [(i, float(v)) for i, v in enumerate(growth_values) if v is not None]
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

    # Convert Decimal to float for numeric operations
    values = [float(v) if v is not None else None for v in values]

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

        # Convert Decimal to float and filter out None values
        valid_data = [(i, float(v)) for i, v in enumerate(values) if v is not None]
        if not valid_data:
            continue

        # Find max and min
        max_entry = max(valid_data, key=lambda x: x[1])
        min_entry = min(valid_data, key=lambda x: x[1])

        # Convert current value to float
        current_val = float(values[0]) if values and values[0] is not None else None

        peaks_troughs[metric] = {
            'peak': {
                'value': max_entry[1],
                'quarter': f"Q{max_entry[0]}"
            },
            'trough': {
                'value': min_entry[1],
                'quarter': f"Q{min_entry[0]}"
            },
            'current': current_val,
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


def compute_ml_features(quarterly_trends: dict, raw_financials: dict = None) -> dict:
    """
    Compute the full ML feature set from quarterly trends and raw financial data.

    This computes the temporal derivatives that the v3.6.5 ML models expect:
    - *_yoy: Year-over-year change (index 0 vs index 4)
    - *_trend_1yr / *_trend_2yr: Difference over 4/8 quarters
    - *_velocity_qoq: Quarter-over-quarter rate of change
    - is_* flags: Boolean indicators

    Args:
        quarterly_trends: Output from extract_quarterly_trends()
        raw_financials: Optional dict with 'balance_sheet', 'income_statement', 'cash_flow'
                       Used to extract absolute values that aren't in trends

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

    def compute_cagr(arr, periods):
        """Compute CAGR over N periods (quarters)."""
        start = get_val(arr, periods)
        end = get_val(arr, 0)
        if start and start > 0 and end and end > 0:
            # CAGR = (end/start)^(4/periods) - 1 (annualized from quarters)
            return round(((end / start) ** (4.0 / periods) - 1) * 100, 2)
        return 0.0

    def compute_momentum(arr, periods):
        """Compute momentum: sum of directional changes over N periods."""
        if not arr or len(arr) < periods + 1:
            return 0.0
        momentum = sum(1 if get_val(arr, i) > get_val(arr, i + 1) else -1
                       for i in range(periods))
        return float(momentum)

    # ===============================
    # EXTRACT RAW FINANCIAL DATA
    # ===============================
    # Get absolute values from raw financials (not from trends)
    balance_sheet = raw_financials.get('balance_sheet', []) if raw_financials else []
    income_statement = raw_financials.get('income_statement', []) if raw_financials else []
    cashflow_stmt = raw_financials.get('cash_flow', []) if raw_financials else []

    # Balance sheet values (most recent quarter)
    total_equity = extract_value(balance_sheet, 'totalStockholdersEquity', 0, 0)
    total_assets = extract_value(balance_sheet, 'totalAssets', 0, 0)
    current_assets = extract_value(balance_sheet, 'totalCurrentAssets', 0, 0)
    current_liabilities = extract_value(balance_sheet, 'totalCurrentLiabilities', 0, 0)
    inventory = extract_value(balance_sheet, 'inventory', 0, 0)
    total_debt_raw = extract_value(balance_sheet, 'totalDebt', 0, 0)

    # Income statement values (most recent quarter)
    net_income = extract_value(income_statement, 'netIncome', 0, 0)
    interest_expense = extract_value(income_statement, 'interestExpense', 0, 0)
    revenue_raw = extract_value(income_statement, 'revenue', 0, 0)
    gross_profit = extract_value(income_statement, 'grossProfit', 0, 0)
    cost_of_revenue = extract_value(income_statement, 'costOfRevenue', 0, 0)

    # Historical gross profit for YoY
    gross_profit_1y = extract_value(income_statement, 'grossProfit', 4, 0)

    # Extract fiscal year/quarter from period date
    period_date = extract_value(balance_sheet, 'date', 0, None)
    if period_date:
        try:
            date_obj = datetime.strptime(str(period_date)[:10], "%Y-%m-%d")
            fiscal_year = date_obj.year
            fiscal_quarter = (date_obj.month - 1) // 3 + 1
        except (ValueError, TypeError):
            fiscal_year = 2025
            fiscal_quarter = 4
    else:
        fiscal_year = 2025
        fiscal_quarter = 4

    # Cash flow statement values
    dividends_paid = abs(extract_value(cashflow_stmt, 'dividendsPaid', 0, 0))
    share_buybacks = abs(extract_value(cashflow_stmt, 'commonStockRepurchased', 0, 0))

    # Historical values for YoY calculations (4 quarters ago)
    total_assets_1y = extract_value(balance_sheet, 'totalAssets', 4, 0)
    total_equity_1y = extract_value(balance_sheet, 'totalStockholdersEquity', 4, 0)
    net_income_1y = extract_value(income_statement, 'netIncome', 4, 0)
    revenue_1y = extract_value(income_statement, 'revenue', 4, 0)

    # 2-year ago values (8 quarters ago)
    total_assets_2y = extract_value(balance_sheet, 'totalAssets', 8, 0)
    net_income_2y = extract_value(income_statement, 'netIncome', 8, 0)

    # ===============================
    # COMPUTE DERIVED METRICS
    # ===============================
    # Annualize quarterly figures for ratios (*4 for annual rate)
    roa = safe_divide(net_income * 4, total_assets) * 100 if total_assets else 0.0
    roa_1y = safe_divide(net_income_1y * 4, total_assets_1y) * 100 if total_assets_1y else 0.0
    roa_2y = safe_divide(net_income_2y * 4, total_assets_2y) * 100 if total_assets_2y else 0.0

    # ROE (annualized)
    roe = safe_divide(net_income * 4, total_equity) * 100 if total_equity else 0.0
    roe_1y = safe_divide(net_income_1y * 4, total_equity_1y) * 100 if total_equity_1y else 0.0

    # ROIC = NOPAT / Invested Capital (approximation)
    invested_capital = total_equity + total_debt_raw
    roic = safe_divide((net_income + interest_expense) * 4, invested_capital) * 100 if invested_capital else 0.0

    # Asset turnover (annualized)
    asset_turnover = safe_divide(revenue_raw * 4, total_assets) if total_assets else 0.0
    asset_turnover_1y = safe_divide(revenue_1y * 4, total_assets_1y) if total_assets_1y else 0.0

    # Equity multiplier
    equity_multiplier = safe_divide(total_assets, total_equity) if total_equity else 0.0

    # Quick ratio (current assets - inventory) / current liabilities
    quick_ratio = safe_divide(current_assets - inventory, current_liabilities)

    # Working capital metrics
    working_capital = current_assets - current_liabilities
    working_capital_to_revenue = safe_divide(working_capital, revenue_raw * 4) * 100 if revenue_raw else 0.0

    # Shareholder returns
    total_capital_return = dividends_paid + share_buybacks

    # OCF to NI ratio (earnings quality)
    ocf_raw = extract_value(cashflow_stmt, 'operatingCashFlow', 0, 0)
    ocf_to_ni_ratio = safe_divide(ocf_raw, net_income) if net_income else 0.0

    # Extract arrays for trend calculations
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
        # Base metrics - NOW FROM RAW DATA
        'total_debt': get_val(td, 0) or total_debt_raw,
        'total_equity': total_equity,
        'total_assets': total_assets,
        'cash': get_val(cash, 0),
        'interest_expense': interest_expense,
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),
        'current_assets': current_assets,
        'current_liabilities': current_liabilities,
        'inventory': inventory,

        # Ratios
        'debt_to_equity': get_val(dte, 0),
        'debt_to_assets': get_val(da, 0),
        'interest_coverage': get_val(ic, 0),
        'net_debt': get_val(nd, 0),
        'net_debt_to_ebitda': get_val(nde, 0),
        'current_ratio': get_val(cr, 0),
        'quick_ratio': quick_ratio,  # FIXED: actual calculation

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
        'interest_expense_velocity_qoq': compute_yoy([interest_expense]) if interest_expense else 0.0,

        # Acceleration
        'debt_to_equity_acceleration_qoq': compute_acceleration(dte),

        # Flags
        'is_deleveraging': 1 if get_val(dte, 0) < get_val(dte, 4) else 0,

        # ROA/ROIC - NOW COMPUTED
        'roa': round(roa, 2),
        'roic': round(roic, 2),
        'roa_yoy': round(roa - roa_1y, 2) if roa_1y else 0.0,
        'roa_trend_2yr': round(roa - roa_2y, 2) if roa_2y else 0.0,
        'roic_yoy': 0.0,  # Would need historical ROIC

        # DuPont - NOW COMPUTED
        'asset_turnover': round(asset_turnover, 2),
        'asset_turnover_yoy': round(asset_turnover - asset_turnover_1y, 2) if asset_turnover_1y else 0.0,
        'equity_multiplier': round(equity_multiplier, 2),

        # Debt coverage
        'fcf_to_debt': safe_divide(get_val(fcf, 0), get_val(td, 0)),
        'ebitda_to_interest': get_val(ic, 0),

        # ADDED: Missing features required by debt model
        'debt_to_equity_cagr_3yr': compute_cagr(dte, 12),
        'leverage_momentum_3q': compute_momentum(dte, 3),
        'is_leverage_increasing': 1 if get_val(dte, 0) > get_val(dte, 4) else 0,
        'is_liquidity_deteriorating': 1 if get_val(cr, 0) < get_val(cr, 4) else 0,
        'debt_growth_faster_than_equity': 1 if compute_yoy(td) > compute_yoy([total_equity, total_equity_1y] if total_equity_1y else [total_equity]) else 0,
        'cost_of_revenue': cost_of_revenue,
        'year_x': fiscal_year,
        'year_y': fiscal_quarter,

        # ADDED: Shared features for model compatibility
        'revenue': get_val(rev, 0) or revenue_raw,
        'net_income': net_income,
        'gross_profit': gross_profit,
        'eps': get_val(eps, 0),
        'gross_margin': get_val(gm, 0),
        'net_margin': get_val(nm, 0),
        'operating_cash_flow': get_val(ocf, 0) or ocf_raw,
        'free_cash_flow': get_val(fcf, 0),
        'capital_expenditures': get_val(capex, 0),
    }

    # ===============================
    # CASHFLOW FEATURES (42 total in v3.6.5)
    # ===============================
    cashflow_features = {
        # Base metrics - NOW FROM RAW DATA
        'operating_cash_flow': get_val(ocf, 0) or ocf_raw,
        'capital_expenditures': get_val(capex, 0),
        'free_cash_flow': get_val(fcf, 0),
        'net_income': net_income,  # FIXED: from raw data
        'revenue': get_val(rev, 0) or revenue_raw,
        'working_capital_change': working_capital,  # FIXED: computed
        'dividend_payout': dividends_paid,  # FIXED: from raw data
        'share_buybacks': share_buybacks,  # FIXED: from raw data

        # Ratios
        'fcf_to_net_income': get_val(fcf_ni, 0),
        'fcf_margin': get_val(fcf_m, 0),
        'total_capital_return': total_capital_return,  # FIXED: computed
        'cash_conversion_cycle': 0,  # Would need receivables/payables data

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

        # Working capital - NOW COMPUTED
        'dio': 0.0,  # Would need COGS and inventory data
        'working_capital_to_revenue': round(working_capital_to_revenue, 2),

        # Include some debt features for model compatibility - NOW FROM RAW DATA
        'total_debt': get_val(td, 0) or total_debt_raw,
        'total_equity': total_equity,
        'total_assets': total_assets,
        'cash': get_val(cash, 0),
        'interest_expense': interest_expense,
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),
        'current_assets': current_assets,
        'current_liabilities': current_liabilities,
        'inventory': inventory,
        'gross_profit': gross_profit,  # FIXED: from raw data
        'eps': get_val(eps, 0),

        # ADDED: Missing features required by cashflow model
        'gross_margin': get_val(gm, 0),
        'net_margin': get_val(nm, 0),
        'cost_of_revenue': cost_of_revenue,
        'year_x': fiscal_year,
        'year_y': fiscal_quarter,
    }

    # ===============================
    # GROWTH FEATURES (63 total in v3.6.5)
    # ===============================
    # Calculate 2-year CAGR
    revenue_2y = extract_value(income_statement, 'revenue', 8, 0)
    revenue_cagr_2yr = 0.0
    if revenue_2y and revenue_2y > 0 and revenue_raw and revenue_raw > 0:
        # CAGR = (end/start)^(1/years) - 1
        revenue_cagr_2yr = round(((revenue_raw / revenue_2y) ** 0.5 - 1) * 100, 2)

    # Reinvestment rate = (CapEx - Depreciation) / Net Income
    capex_raw = abs(extract_value(cashflow_stmt, 'capitalExpenditure', 0, 0))
    reinvestment_rate = safe_divide(capex_raw, net_income) * 100 if net_income > 0 else 0.0

    # Earnings stability (simplified: std deviation of net margin over 4 quarters)
    # Using coefficient of variation as proxy
    nm_values = [get_val(nm, i) for i in range(min(4, len(nm)))] if nm else []
    nm_mean = sum(nm_values) / len(nm_values) if nm_values else 0
    earnings_stability = 1.0 if nm_mean and all(abs(v - nm_mean) < nm_mean * 0.3 for v in nm_values) else 0.0

    growth_features = {
        # YoY growth
        'revenue_growth_yoy': get_val(rev_yoy, 0, 0.0),
        'revenue_growth_qoq': compute_velocity(rev),
        'revenue_cagr_2yr': revenue_cagr_2yr,  # FIXED: computed
        'revenue_growth_vs_industry': 0.0,  # Would need industry data
        'revenue_growth_trend': compute_trend(rev_yoy, 4) if rev_yoy else 0.0,

        # Margin changes
        'operating_margin_change_1yr': compute_trend(om, 4),
        'operating_margin_momentum': compute_velocity(om),

        # ROE - NOW COMPUTED
        'roe_change_1yr': round(roe - roe_1y, 2) if roe_1y else 0.0,
        'roe_trend_2yr': 0.0,  # Would need 2y ago ROE

        # Cash quality - NOW COMPUTED
        'ocf_to_ni_ratio': round(ocf_to_ni_ratio, 2),
        'fcf_to_ni_ratio': get_val(fcf_ni, 0),
        'quality_of_earnings': round(ocf_to_ni_ratio, 2),  # Same as ocf_to_ni

        # Investment - NOW COMPUTED
        'reinvestment_rate': round(reinvestment_rate, 2),
        'growth_capex_pct': round(safe_divide(capex_raw, revenue_raw) * 100, 2) if revenue_raw else 0.0,

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

        # Base metrics - NOW FROM RAW DATA
        'gross_profit': gross_profit,
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

        # Other - NOW COMPUTED WHERE POSSIBLE
        'roe_decomposed': round(roe, 2),  # Just ROE for now
        'earnings_stability': earnings_stability,
        'operating_leverage': 0.0,  # Would need fixed/variable cost breakdown
        'revenue': get_val(rev, 0) or revenue_raw,
        'eps': get_val(eps, 0),
        'operating_income': get_val(oi, 0),
        'ebitda': get_val(ebitda, 0),

        # ADDED: Missing features required by growth model
        'eps_to_revenue': safe_divide(get_val(eps, 0), revenue_raw) * 1e6 if revenue_raw else 0.0,
        'cost_efficiency': safe_divide(revenue_raw - cost_of_revenue, revenue_raw) * 100 if revenue_raw else 0.0,
        'net_margin_trend_1yr': compute_trend(nm, 4),
        'gross_margin_change_1yr': compute_trend(gm, 4),
        'gross_profit_growth_yoy': round(safe_divide(gross_profit - gross_profit_1y, gross_profit_1y) * 100, 2) if gross_profit_1y else 0.0,
        'cost_of_revenue': cost_of_revenue,
        'year_x': fiscal_year,
        'year_y': fiscal_quarter,

        # ADDED: Additional shared features for model compatibility
        'total_debt': get_val(td, 0) or total_debt_raw,
        'total_equity': total_equity,
        'total_assets': total_assets,
        'cash': get_val(cash, 0),
        'interest_expense': interest_expense,
        'current_assets': current_assets,
        'current_liabilities': current_liabilities,
        'inventory': inventory,
        'operating_cash_flow': get_val(ocf, 0) or ocf_raw,
        'free_cash_flow': get_val(fcf, 0),
        'capital_expenditures': get_val(capex, 0),
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

    # Compute ML features from quarterly trends AND raw financials
    # Passing raw_financials allows extraction of absolute values (total_equity, total_assets, etc.)
    ml_features = compute_ml_features(quarterly_trends, raw_financials)

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

    return base_metrics


def format_currency(value, billions=True) -> str:
    """Format a number as currency string (e.g., '$32.4B')."""
    if value is None:
        return 'N/A'

    if billions and abs(value) >= 1e9:
        return f"${value / 1e9:.1f}B"
    elif abs(value) >= 1e6:
        return f"${value / 1e6:.1f}M"
    else:
        return f"${value:,.0f}"


def prepare_agent_payload(ticker: str, fiscal_year: int, model_inference: dict,
                          features: dict, agent_type: str) -> dict:
    """
    Prepare the payload to send to a Bedrock agent.

    Args:
        ticker: Stock ticker
        fiscal_year: Fiscal year
        model_inference: Model prediction results
        features: Extracted features dict
        agent_type: 'debt', 'cashflow', or 'growth'

    Returns:
        dict formatted for agent consumption
    """
    agent_features = features.get(agent_type, {})

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

        'formatting_hints': {
            'use_billions': True,
            'currency': 'USD',
            'include_emojis': True
        }
    }
