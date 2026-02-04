"""
DJIA, S&P 100, and S&P 500 ticker lists for batch report generation.

Used by the report generation CLI to iterate over major index constituents.

NOTE: Starting with 10 companies per index for initial testing.
Can be expanded to full lists after validation.
"""

# Dow Jones Industrial Average - 10 representative companies for testing
# Selected for sector diversity and varied financial characteristics
DJIA_TICKERS = [
    'AAPL',   # Apple - Tech, strong cash
    'MSFT',   # Microsoft - Tech, cloud growth
    'JPM',    # JPMorgan - Financials
    'JNJ',    # Johnson & Johnson - Healthcare
    'V',      # Visa - Payments
    'UNH',    # UnitedHealth - Healthcare
    'HD',     # Home Depot - Retail
    'KO',     # Coca-Cola - Consumer staples
    'CVX',    # Chevron - Energy
    'BA',     # Boeing - Industrials, cyclical
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

# S&P 100 (OEX) - Full list of 100 largest S&P 500 companies by market cap
# These are the most liquid and widely-traded large-cap stocks
SP100_TICKERS = [
    'AAPL',   # Apple
    'ABBV',   # AbbVie
    'ABT',    # Abbott Laboratories
    'ACN',    # Accenture
    'ADBE',   # Adobe
    'AIG',    # American International Group
    'AMD',    # Advanced Micro Devices
    'AMGN',   # Amgen
    'AMZN',   # Amazon
    'AXP',    # American Express
    'BA',     # Boeing
    'BAC',    # Bank of America
    'BK',     # Bank of New York Mellon
    'BKNG',   # Booking Holdings
    'BLK',    # BlackRock
    'BMY',    # Bristol-Myers Squibb
    'BRK.B',  # Berkshire Hathaway
    'C',      # Citigroup
    'CAT',    # Caterpillar
    'CHTR',   # Charter Communications
    'CL',     # Colgate-Palmolive
    'CMCSA',  # Comcast
    'COF',    # Capital One
    'COP',    # ConocoPhillips
    'COST',   # Costco
    'CRM',    # Salesforce
    'CSCO',   # Cisco
    'CVS',    # CVS Health
    'CVX',    # Chevron
    'DE',     # Deere & Company
    'DHR',    # Danaher
    'DIS',    # Walt Disney
    'DOW',    # Dow Inc
    'DUK',    # Duke Energy
    'EMR',    # Emerson Electric
    'EXC',    # Exelon
    'F',      # Ford
    'FDX',    # FedEx
    'GD',     # General Dynamics
    'GE',     # General Electric
    'GILD',   # Gilead Sciences
    'GM',     # General Motors
    'GOOG',   # Alphabet Class C
    'GOOGL',  # Alphabet Class A
    'GS',     # Goldman Sachs
    'HD',     # Home Depot
    'HON',    # Honeywell
    'IBM',    # IBM
    'INTC',   # Intel
    'JNJ',    # Johnson & Johnson
    'JPM',    # JPMorgan Chase
    'KHC',    # Kraft Heinz
    'KO',     # Coca-Cola
    'LIN',    # Linde
    'LLY',    # Eli Lilly
    'LMT',    # Lockheed Martin
    'LOW',    # Lowe's
    'MA',     # Mastercard
    'MCD',    # McDonald's
    'MDLZ',   # Mondelez
    'MDT',    # Medtronic
    'MET',    # MetLife
    'META',   # Meta Platforms
    'MMM',    # 3M
    'MO',     # Altria
    'MRK',    # Merck
    'MS',     # Morgan Stanley
    'MSFT',   # Microsoft
    'NEE',    # NextEra Energy
    'NFLX',   # Netflix
    'NKE',    # Nike
    'NVDA',   # NVIDIA
    'ORCL',   # Oracle
    'OXY',    # Occidental Petroleum
    'PEP',    # PepsiCo
    'PFE',    # Pfizer
    'PG',     # Procter & Gamble
    'PM',     # Philip Morris
    'PYPL',   # PayPal
    'QCOM',   # Qualcomm
    'RTX',    # RTX Corporation
    'SBUX',   # Starbucks
    'SCHW',   # Charles Schwab
    'SO',     # Southern Company
    'SPG',    # Simon Property Group
    'T',      # AT&T
    'TGT',    # Target
    'TMO',    # Thermo Fisher Scientific
    'TMUS',   # T-Mobile
    'TXN',    # Texas Instruments
    'UNH',    # UnitedHealth
    'UNP',    # Union Pacific
    'UPS',    # United Parcel Service
    'USB',    # U.S. Bancorp
    'V',      # Visa
    'VZ',     # Verizon
    'WBA',    # Walgreens Boots Alliance
    'WFC',    # Wells Fargo
    'WMT',    # Walmart
    'XOM',    # Exxon Mobil
]


def get_index_tickers(index: str) -> list:
    """
    Get tickers for a given index.

    Args:
        index: 'DJIA', 'SP100', or 'SP500'

    Returns:
        List of ticker symbols
    """
    if index.upper() == 'DJIA':
        return DJIA_TICKERS.copy()
    elif index.upper() == 'SP100':
        return SP100_TICKERS.copy()
    elif index.upper() == 'SP500':
        return SP500_TICKERS.copy()
    else:
        raise ValueError(f"Unknown index: {index}. Use 'DJIA', 'SP100', or 'SP500'")


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
