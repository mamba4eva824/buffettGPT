"""
DJIA, S&P 100, and S&P 500 ticker lists for batch report generation.

Used by the report generation CLI to iterate over major index constituents.

NOTE: S&P 500 list starts with 10 representative companies for initial testing.
DJIA and S&P 100 have full constituent lists.
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

# S&P 100 (OEX) - All 101 components (100 companies, Alphabet has 2 share classes)
# Full S&P 100 constituent list for batch report generation
# NOTE: Constituents change periodically; list reflects early 2025 composition
SP100_TICKERS = [
    'AAPL',   # Apple - Consumer electronics, services
    'ABBV',   # AbbVie - Biopharmaceuticals
    'ABT',    # Abbott Laboratories - Medical devices, diagnostics
    'ACN',    # Accenture - IT consulting
    'ADBE',   # Adobe - Software
    'AMAT',   # Applied Materials - Semiconductor equipment
    'AMD',    # Advanced Micro Devices - Semiconductors
    'AMGN',   # Amgen - Biotechnology
    'AMZN',   # Amazon - E-commerce, cloud
    'AVGO',   # Broadcom - Semiconductors, infrastructure software
    'AXP',    # American Express - Financial services
    'BA',     # Boeing - Aerospace, defense
    'BAC',    # Bank of America - Banking
    'BK',     # Bank of New York Mellon - Financial services
    'BKNG',   # Booking Holdings - Online travel
    'BLK',    # BlackRock - Asset management
    'BMY',    # Bristol-Myers Squibb - Pharmaceuticals
    'BRK-B',  # Berkshire Hathaway - Conglomerate
    'C',      # Citigroup - Banking
    'CAT',    # Caterpillar - Heavy equipment
    'CI',     # The Cigna Group - Health insurance
    'CL',     # Colgate-Palmolive - Consumer staples
    'CMCSA',  # Comcast - Media, telecom
    'COF',    # Capital One - Financial services
    'COP',    # ConocoPhillips - Energy
    'COST',   # Costco - Retail
    'CRM',    # Salesforce - Cloud software
    'CSCO',   # Cisco - Networking
    'CVS',    # CVS Health - Pharmacy, healthcare
    'CVX',    # Chevron - Energy
    'DE',     # Deere & Co - Agricultural equipment
    'DHR',    # Danaher - Life sciences, diagnostics
    'DIS',    # Walt Disney - Media, entertainment
    'DUK',    # Duke Energy - Utilities
    'EMR',    # Emerson Electric - Industrials
    'EXC',    # Exelon - Utilities
    'F',      # Ford Motor - Automotive
    'FDX',    # FedEx - Logistics
    'GD',     # General Dynamics - Defense
    'GE',     # GE Aerospace - Aerospace
    'GILD',   # Gilead Sciences - Biopharmaceuticals
    'GM',     # General Motors - Automotive
    'GOOG',   # Alphabet (Class C) - Tech, advertising
    'GOOGL',  # Alphabet (Class A) - Tech, advertising
    'GS',     # Goldman Sachs - Investment banking
    'HD',     # Home Depot - Retail
    'HON',    # Honeywell - Industrials
    'IBM',    # IBM - Tech services
    'INTC',   # Intel - Semiconductors
    'INTU',   # Intuit - Financial software
    'JNJ',    # Johnson & Johnson - Healthcare
    'JPM',    # JPMorgan Chase - Financials
    'KO',     # Coca-Cola - Consumer staples
    'LIN',    # Linde - Industrial gases
    'LLY',    # Eli Lilly - Pharmaceuticals
    'LMT',    # Lockheed Martin - Defense
    'LOW',    # Lowe's - Retail
    'MA',     # Mastercard - Payments
    'MCD',    # McDonald's - Restaurants
    'MDLZ',   # Mondelez - Consumer staples
    'MDT',    # Medtronic - Medical devices
    'MET',    # MetLife - Insurance
    'META',   # Meta Platforms - Social media, tech
    'MMM',    # 3M - Industrials
    'MO',     # Altria - Consumer staples
    'MRK',    # Merck - Pharmaceuticals
    'MS',     # Morgan Stanley - Financial services
    'MSFT',   # Microsoft - Tech, cloud
    'NEE',    # NextEra Energy - Utilities
    'NFLX',   # Netflix - Streaming
    'NKE',    # Nike - Consumer discretionary
    'NOW',    # ServiceNow - Cloud software
    'NVDA',   # NVIDIA - Semiconductors, AI
    'ORCL',   # Oracle - Enterprise software
    'PEP',    # PepsiCo - Consumer staples
    'PFE',    # Pfizer - Pharmaceuticals
    'PG',     # Procter & Gamble - Consumer staples
    'PM',     # Philip Morris - Consumer staples
    'PYPL',   # PayPal - Fintech
    'QCOM',   # Qualcomm - Semiconductors
    'RTX',    # RTX Corporation - Defense, aerospace
    'SBUX',   # Starbucks - Restaurants
    'SCHW',   # Charles Schwab - Financial services
    'SO',     # Southern Company - Utilities
    'SPG',    # Simon Property Group - Real estate
    'T',      # AT&T - Telecom
    'TGT',    # Target - Retail
    'TMO',    # Thermo Fisher Scientific - Life sciences
    'TMUS',   # T-Mobile - Telecom
    'TSLA',   # Tesla - EV, energy
    'TXN',    # Texas Instruments - Semiconductors
    'UNH',    # UnitedHealth - Healthcare
    'UNP',    # Union Pacific - Railroad
    'UPS',    # United Parcel Service - Logistics
    'USB',    # U.S. Bancorp - Banking
    'V',      # Visa - Payments
    'VZ',     # Verizon - Telecom
    'WBA',    # Walgreens Boots Alliance - Retail pharmacy
    'WFC',    # Wells Fargo - Banking
    'WMT',    # Walmart - Retail
    'XOM',    # ExxonMobil - Energy
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
