"""
DJIA and S&P 500 ticker lists for batch report generation.

Used by the report generation CLI to iterate over major index constituents.

NOTE: Starting with 10 companies per index for initial testing.
Can be expanded to full lists after validation.
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


def get_index_tickers(index: str) -> list:
    """
    Get tickers for a given index.

    Args:
        index: 'DJIA' or 'SP500'

    Returns:
        List of ticker symbols
    """
    if index.upper() == 'DJIA':
        return DJIA_TICKERS.copy()
    elif index.upper() == 'SP500':
        return SP500_TICKERS.copy()
    else:
        raise ValueError(f"Unknown index: {index}. Use 'DJIA' or 'SP500'")


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
