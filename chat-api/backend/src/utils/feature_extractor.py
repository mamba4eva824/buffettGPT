"""
Feature Extractor for Ensemble Analysis

Extracts key financial metrics from FMP data for the 3-agent ensemble:
- Debt Expert: Leverage, coverage, liquidity metrics
- Cashflow Expert: FCF, cash efficiency, capital allocation
- Growth Expert: Revenue growth, margin trends, acceleration

This is a simplified version optimized for Lambda execution.
The full v3.6.5 feature set (163 features) is used for model inference.
"""

from typing import Optional
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

    Args:
        data_list: List of quarterly data dicts from FMP
        key: Key to extract
        index: Which quarter (0 = most recent)
        default: Default value if not found
    """
    try:
        if not data_list or index >= len(data_list):
            return default
        return data_list[index].get(key, default)
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


def extract_all_features(raw_financials: dict) -> dict:
    """
    Extract all key metrics for the 3-agent ensemble.

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

    return {
        'debt': extract_debt_metrics(balance_sheet, income_statement, cashflow),
        'cashflow': extract_cashflow_metrics(balance_sheet, income_statement, cashflow),
        'growth': extract_growth_metrics(balance_sheet, income_statement, cashflow),
    }


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
