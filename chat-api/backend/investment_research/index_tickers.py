"""
DJIA, S&P 100, and S&P 500 ticker lists for batch report generation.

Used by the report generation CLI to iterate over major index constituents.

NOTE: SP500 still contains 10 representative companies for testing.
SP100 contains the top 100 S&P 500 companies by market cap (102 tickers).
"""

# Dow Jones Industrial Average - All 30 components
# Full DJIA constituent list for batch report generation
DJIA_TICKERS = [
    'AAPL',   # Apple - Tech, strong cash
    'AMGN',   # Amgen - Biotech
    'AXP',    # American Express - Financial services
    'BA',     # Boeing - Industrials, cyclical
    'CAT',    # Caterpillar - Heavy equipment
    'CRM',    # Salesforce - Cloud software
    'CSCO',   # Cisco - Networking
    'CVX',    # Chevron - Energy
    'DIS',    # Disney - Media/Entertainment
    'DOW',    # Dow Inc - Chemicals
    'GS',     # Goldman Sachs - Investment banking
    'HD',     # Home Depot - Retail
    'HON',    # Honeywell - Industrials
    'IBM',    # IBM - Tech services
    'INTC',   # Intel - Semiconductors
    'JNJ',    # Johnson & Johnson - Healthcare
    'JPM',    # JPMorgan - Financials
    'KO',     # Coca-Cola - Consumer staples
    'MCD',    # McDonald's - Restaurants
    'MMM',    # 3M - Industrials
    'MRK',    # Merck - Pharma
    'MSFT',   # Microsoft - Tech, cloud growth
    'NKE',    # Nike - Consumer discretionary
    'PG',     # Procter & Gamble - Consumer staples
    'TRV',    # Travelers - Insurance
    'UNH',    # UnitedHealth - Healthcare
    'V',      # Visa - Payments
    'VZ',     # Verizon - Telecom
    'WBA',    # Walgreens - Retail pharmacy
    'WMT',    # Walmart - Retail
]

# S&P 500 - 10 representative companies for testing
# Different from DJIA to test broader coverage
SP500_TICKERS = [
    'NVDA',   # NVIDIA - High growth, AI
    'GOOGL',  # Alphabet - Tech, advertising
    'AMZN',   # Amazon - E-commerce, cloud
    'META',   # Meta - Social, advertising
    'TSLA',   # Tesla - EV, volatile
    'XOM',    # Exxon - Energy
    'LLY',    # Eli Lilly - Pharma, growth
    'WFC',    # Wells Fargo - Banking
    'F',      # Ford - Auto, high debt
    'T',      # AT&T - Telecom, dividend
]

# Top 100 S&P 500 by market cap — 102 tickers
# BRK-B is FMP's format for Berkshire Hathaway B shares
# GOOGL used (not GOOG duplicate)
# Last updated: Feb 2026. Refresh quarterly from slickcharts.com/sp500/marketcap
SP100_TICKERS = [
    'AAPL', 'ABBV', 'ABT', 'ACN', 'ADI', 'AMAT', 'AMD', 'AMGN', 'AMZN', 'ANET',
    'APH', 'AVGO', 'AXP', 'BA', 'BAC', 'BLK', 'BMY', 'BKNG', 'BRK-B', 'BSX',
    'C', 'CAT', 'CEG', 'CMCSA', 'CME', 'COF', 'COP', 'COST', 'CRM', 'CSCO',
    'CVX', 'DE', 'DHR', 'DIS', 'ETN', 'GE', 'GILD', 'GLW', 'GOOGL', 'GS',
    'HCA', 'HD', 'HON', 'IBM', 'INTC', 'ISRG', 'JNJ', 'JPM', 'KLAC', 'KO',
    'LIN', 'LLY', 'LMT', 'LOW', 'LRCX', 'MA', 'MCD', 'MCK', 'MDT', 'MET',
    'META', 'MO', 'MRK', 'MS', 'MSFT', 'MU', 'NEE', 'NFLX', 'NOC', 'NOW',
    'NVDA', 'ORCL', 'PANW', 'PEP', 'PFE', 'PG', 'PGR', 'PH', 'PLD', 'PLTR',
    'PM', 'QCOM', 'RTX', 'SBUX', 'SCHW', 'SO', 'SPGI', 'SYK', 'T', 'TJX',
    'TMO', 'TMUS', 'TSLA', 'TXN', 'UBER', 'UNH', 'UNP', 'V', 'VRTX', 'WFC',
    'WMT', 'XOM',
]


def get_index_tickers(index: str) -> list:
    """
    Get tickers for a given index.

    Args:
        index: 'DJIA', 'SP500', or 'SP100'

    Returns:
        List of ticker symbols
    """
    idx = index.upper().replace('-', '')
    if idx == 'DJIA':
        return DJIA_TICKERS.copy()
    elif idx == 'SP500':
        return SP500_TICKERS.copy()
    elif idx == 'SP100':
        return SP100_TICKERS.copy()
    else:
        raise ValueError(f"Unknown index: {index}. Use 'DJIA', 'SP500', or 'SP100'")


def get_test_tickers() -> list:
    """
    Get standard test tickers per CLAUDE.md guidelines.

    Returns tickers with diverse characteristics:
    - AAPL: Strong cash, low debt, mature (baseline)
    - MSFT: Growth + margins, cloud
    - F: High debt, cyclical
    - NVDA: High growth, volatile
    """
    return ['AAPL', 'MSFT', 'F', 'NVDA']
