"""
Value investor metrics definitions per agent type.
Based on Buffett/Graham investment principles.

Each agent receives 20 metrics with 20 quarters (5 years) of historical data.
Metrics MUST match exactly what's extracted in utils/feature_extractor.py
"""
from typing import Dict, List

# ─────────────────────────────────────────────────────────────────────────────
# Top 20 Value Investor Metrics per Agent
# Each metric array contains 20 quarters (5 years) of data
# Organized by logical groupings for expert analysis
# ─────────────────────────────────────────────────────────────────────────────

VALUE_INVESTOR_METRICS: Dict[str, List[str]] = {
    'debt': [
        # Core Leverage (5)
        'debt_to_equity',           # Total debt / Total equity. Prefer < 0.5
        'debt_to_assets',           # Total debt / Total assets. Prefer < 0.3
        'net_debt',                 # Total debt - cash. Negative = net cash position
        'net_debt_to_ebitda',       # Years to pay off debt. Prefer < 3x
        'total_debt',               # Absolute total debt (long + short term)
        # Liquidity (5)
        'current_ratio',            # Current assets / Current liabilities. Prefer > 2.0
        'quick_ratio',              # (Cash + STI) / Current liabilities. Prefer > 1.0
        'cash_position',            # Cash + short-term investments (absolute)
        'interest_coverage',        # EBIT / Interest expense. Require > 8x
        'interest_expense',         # Absolute interest expense (cost of debt)
        # Returns & Efficiency (5)
        'roa',                      # Return on assets (annualized). Prefer > 10%
        'roic',                     # Return on invested capital (annualized). Prefer > 15%
        'asset_turnover',           # Revenue / Total assets (annualized). Higher = efficient
        'equity_multiplier',        # Total assets / Equity. Leverage indicator
        'fcf_to_debt',              # Free cash flow / Total debt. > 0.25 = healthy
        # Trends & Equity (5)
        'total_equity',             # Shareholders' equity (book value)
        'debt_to_equity_change_1yr',  # D/E change vs 4 quarters ago. Negative = deleveraging
        'debt_to_equity_change_2yr',  # D/E change vs 8 quarters ago
        'current_ratio_change_1yr',   # Liquidity trend. Positive = improving
        'is_deleveraging',          # Binary: 1 if D/E is decreasing over time
    ],
    'cashflow': [
        # Core Cash Flow (5)
        'operating_cash_flow',      # Cash from operations (absolute)
        'free_cash_flow',           # OCF minus CapEx (owner earnings proxy)
        'fcf_margin',               # FCF / Revenue. Prefer > 15%
        'ocf_to_revenue',           # OCF / Revenue. Prefer > 20%
        'fcf_to_net_income',        # Earnings quality. Prefer > 0.8 (cash > accruals)
        # Capital Allocation (5)
        'capex',                    # Capital expenditures (absolute)
        'capex_intensity',          # CapEx / Revenue. Prefer < 15%
        'dividends_paid',           # Cash dividends paid to shareholders
        'share_buybacks',           # Stock repurchases (treasury stock)
        'shareholder_payout',       # Dividends + buybacks (total return)
        # Efficiency (5)
        'fcf_payout_ratio',         # Dividends / FCF. < 60% = sustainable
        'working_capital',          # Current assets - Current liabilities
        'working_capital_to_revenue',  # Working capital efficiency
        'reinvestment_rate',        # CapEx / OCF. How much cash reinvested
        'total_capital_return',     # Total shareholder returns (same as payout)
        # YoY Changes (5)
        'fcf_change_yoy',           # FCF change vs 4 quarters ago
        'fcf_margin_change_1yr',    # FCF margin trend. Positive = improving
        'ocf_change_yoy',           # OCF change vs 4 quarters ago
        'capex_change_yoy',         # CapEx change vs 4 quarters ago
        'capital_return_yield',     # Capital return / Market cap (placeholder)
    ],
    'growth': [
        # Core Profitability (5)
        'revenue',                  # Total revenue (top line)
        'gross_margin',             # Gross profit / Revenue. > 40% = moat
        'operating_margin',         # Operating income / Revenue. Prefer > 20%
        'net_margin',               # Net income / Revenue. Prefer > 15%
        'ebitda',                   # Earnings before interest, taxes, depreciation
        # Absolute Values (5)
        'net_income',               # Bottom line profit
        'gross_profit',             # Revenue - COGS
        'operating_income',         # EBIT
        'eps',                      # Earnings per share (diluted)
        'roe',                      # Return on equity (annualized). Prefer > 15%
        # Growth Rates (5)
        'revenue_growth_yoy',       # Revenue change vs 4 quarters ago
        'revenue_growth_qoq',       # Revenue change vs previous quarter
        'eps_growth_yoy',           # EPS change vs 4 quarters ago
        'roic_growth',              # ROIC (annualized) - shared with debt expert
        'net_income_growth_yoy',    # Net income change vs 4 quarters ago
        # Margin Trends (5)
        'gross_margin_change_1yr',  # Gross margin trend
        'operating_margin_change_1yr',   # Op margin change vs 4 quarters ago
        'operating_margin_change_2yr',   # Op margin change vs 8 quarters ago
        'net_margin_change_1yr',    # Net margin trend
        'is_margin_expanding',      # Binary: 1 if operating margin improving
        # ROE Trend (1) - Extra
        'roe_change_2yr',           # ROE change vs 8 quarters ago
    ]
}

# Logical groupings for formatted table output
METRIC_GROUPS: Dict[str, List[tuple]] = {
    'debt': [
        ('Core Leverage', ['debt_to_equity', 'debt_to_assets', 'net_debt', 'net_debt_to_ebitda', 'total_debt']),
        ('Liquidity', ['current_ratio', 'quick_ratio', 'cash_position', 'interest_coverage', 'interest_expense']),
        ('Returns', ['roa', 'roic', 'asset_turnover', 'equity_multiplier', 'fcf_to_debt']),
        ('Trends', ['total_equity', 'debt_to_equity_change_1yr', 'debt_to_equity_change_2yr', 'current_ratio_change_1yr', 'is_deleveraging']),
    ],
    'cashflow': [
        ('Core Cash Flow', ['operating_cash_flow', 'free_cash_flow', 'fcf_margin', 'ocf_to_revenue', 'fcf_to_net_income']),
        ('Capital Allocation', ['capex', 'capex_intensity', 'dividends_paid', 'share_buybacks', 'shareholder_payout']),
        ('Efficiency', ['fcf_payout_ratio', 'working_capital', 'working_capital_to_revenue', 'reinvestment_rate', 'total_capital_return']),
        ('YoY Changes', ['fcf_change_yoy', 'fcf_margin_change_1yr', 'ocf_change_yoy', 'capex_change_yoy', 'capital_return_yield']),
    ],
    'growth': [
        ('Profitability', ['gross_margin', 'operating_margin', 'net_margin', 'roe', 'roic_growth']),
        ('Absolute Values', ['revenue', 'gross_profit', 'operating_income', 'net_income', 'ebitda', 'eps']),
        ('Growth Rates', ['revenue_growth_yoy', 'revenue_growth_qoq', 'eps_growth_yoy', 'net_income_growth_yoy']),
        ('Margin Trends', ['gross_margin_change_1yr', 'operating_margin_change_1yr', 'operating_margin_change_2yr', 'net_margin_change_1yr', 'is_margin_expanding', 'roe_change_2yr']),
    ]
}

# All metrics combined (for full analysis)
ALL_METRICS: List[str] = (
    VALUE_INVESTOR_METRICS['debt'] +
    VALUE_INVESTOR_METRICS['cashflow'] +
    VALUE_INVESTOR_METRICS['growth']
)


def get_metrics_for_agent(agent_type: str) -> List[str]:
    """Get the list of metrics for a specific agent type."""
    if agent_type == 'all':
        return ALL_METRICS
    return VALUE_INVESTOR_METRICS.get(agent_type, [])


def get_metric_groups(agent_type: str) -> List[tuple]:
    """Get logical metric groupings for an agent type."""
    return METRIC_GROUPS.get(agent_type, [])
