"""
Company name mappings for investment research reports.

Maps ticker symbols to full company names for display in search dropdowns
and report headers.
"""

from typing import Optional

# Comprehensive mapping of ticker to company name
# Covers Dow 30, S&P 100, and common tickers
COMPANY_NAMES = {
    # Mega-cap Tech
    'AAPL': 'Apple Inc.',
    'MSFT': 'Microsoft Corporation',
    'NVDA': 'NVIDIA Corporation',
    'GOOGL': 'Alphabet Inc. (Google)',
    'GOOG': 'Alphabet Inc. (Google)',
    'AMZN': 'Amazon.com Inc.',
    'META': 'Meta Platforms Inc.',
    'TSLA': 'Tesla Inc.',
    'AVGO': 'Broadcom Inc.',
    'ORCL': 'Oracle Corporation',
    'ADBE': 'Adobe Inc.',

    # Large-cap Tech
    'CRM': 'Salesforce Inc.',
    'AMD': 'Advanced Micro Devices Inc.',
    'NFLX': 'Netflix Inc.',
    'SPOT': 'Spotify Technology S.A.',
    'CSCO': 'Cisco Systems Inc.',
    'INTC': 'Intel Corporation',
    'IBM': 'International Business Machines',
    'QCOM': 'Qualcomm Inc.',
    'TXN': 'Texas Instruments Inc.',
    'INTU': 'Intuit Inc.',
    'NOW': 'ServiceNow Inc.',

    # Financials
    'BRK.B': 'Berkshire Hathaway Inc.',
    'BRK-B': 'Berkshire Hathaway Inc.',
    'JPM': 'JPMorgan Chase & Co.',
    'V': 'Visa Inc.',
    'MA': 'Mastercard Inc.',
    'BAC': 'Bank of America Corp.',
    'WFC': 'Wells Fargo & Co.',
    'GS': 'Goldman Sachs Group Inc.',
    'MS': 'Morgan Stanley',
    'SPGI': 'S&P Global Inc.',
    'BLK': 'BlackRock Inc.',
    'C': 'Citigroup Inc.',
    'AXP': 'American Express Co.',
    'SCHW': 'Charles Schwab Corp.',
    'CB': 'Chubb Limited',
    'MMC': 'Marsh McLennan Companies',
    'TRV': 'The Travelers Companies Inc.',

    # Healthcare
    'UNH': 'UnitedHealth Group Inc.',
    'LLY': 'Eli Lilly and Company',
    'JNJ': 'Johnson & Johnson',
    'MRK': 'Merck & Co. Inc.',
    'ABBV': 'AbbVie Inc.',
    'PFE': 'Pfizer Inc.',
    'TMO': 'Thermo Fisher Scientific Inc.',
    'ABT': 'Abbott Laboratories',
    'DHR': 'Danaher Corporation',
    'BMY': 'Bristol-Myers Squibb Co.',
    'AMGN': 'Amgen Inc.',
    'GILD': 'Gilead Sciences Inc.',
    'CVS': 'CVS Health Corporation',
    'ISRG': 'Intuitive Surgical Inc.',
    'VRTX': 'Vertex Pharmaceuticals Inc.',

    # Consumer/Retail
    'WMT': 'Walmart Inc.',
    'PG': 'Procter & Gamble Co.',
    'COST': 'Costco Wholesale Corp.',
    'HD': 'The Home Depot Inc.',
    'KO': 'The Coca-Cola Company',
    'PEP': 'PepsiCo Inc.',
    'MCD': "McDonald's Corporation",
    'NKE': 'Nike Inc.',
    'SBUX': 'Starbucks Corporation',
    'TGT': 'Target Corporation',
    'LOW': "Lowe's Companies Inc.",
    'EL': 'The Estée Lauder Companies',

    # Industrials
    'GE': 'GE Aerospace',
    'CAT': 'Caterpillar Inc.',
    'RTX': 'RTX Corporation',
    'HON': 'Honeywell International Inc.',
    'UNP': 'Union Pacific Corporation',
    'UPS': 'United Parcel Service Inc.',
    'BA': 'The Boeing Company',
    'LMT': 'Lockheed Martin Corporation',
    'DE': 'Deere & Company',
    'MMM': '3M Company',
    'GD': 'General Dynamics Corporation',
    'EMR': 'Emerson Electric Co.',
    'DOW': 'Dow Inc.',
    'SHW': 'The Sherwin-Williams Company',

    # Energy
    'XOM': 'Exxon Mobil Corporation',
    'CVX': 'Chevron Corporation',
    'COP': 'ConocoPhillips',
    'SLB': 'Schlumberger Limited',
    'EOG': 'EOG Resources Inc.',
    'PXD': 'Pioneer Natural Resources Co.',
    'MPC': 'Marathon Petroleum Corp.',
    'OXY': 'Occidental Petroleum Corp.',

    # Telecom/Media
    'DIS': 'The Walt Disney Company',
    'CMCSA': 'Comcast Corporation',
    'VZ': 'Verizon Communications Inc.',
    'T': 'AT&T Inc.',
    'TMUS': 'T-Mobile US Inc.',
    'CHTR': 'Charter Communications Inc.',

    # Utilities & REITs
    'NEE': 'NextEra Energy Inc.',
    'SO': 'The Southern Company',
    'DUK': 'Duke Energy Corporation',
    'D': 'Dominion Energy Inc.',
    'SRE': 'Sempra',
    'AEP': 'American Electric Power Co.',
    'AMT': 'American Tower Corporation',
    'CCI': 'Crown Castle Inc.',
    'PSA': 'Public Storage',
    'SPG': 'Simon Property Group Inc.',

    # Automotive
    'F': 'Ford Motor Company',
    'GM': 'General Motors Company',
}


def get_company_name(ticker: str) -> Optional[str]:
    """
    Get the full company name for a ticker symbol.

    Args:
        ticker: Stock ticker symbol (case insensitive)

    Returns:
        Company name if found, None otherwise
    """
    return COMPANY_NAMES.get(ticker.upper())


def get_company_name_or_ticker(ticker: str) -> str:
    """
    Get the company name, falling back to ticker if not found.

    Args:
        ticker: Stock ticker symbol (case insensitive)

    Returns:
        Company name if found, otherwise the uppercase ticker
    """
    return COMPANY_NAMES.get(ticker.upper(), ticker.upper())


def search_companies(query: str, limit: int = 10) -> list:
    """
    Search for companies by name or ticker.

    Args:
        query: Search query (matches ticker or name, case insensitive)
        limit: Maximum number of results to return

    Returns:
        List of dicts with ticker and name matching the query
    """
    query_lower = query.lower()
    results = []

    for ticker, name in COMPANY_NAMES.items():
        if query_lower in ticker.lower() or query_lower in name.lower():
            results.append({
                'ticker': ticker,
                'name': name
            })
            if len(results) >= limit:
                break

    return results


def get_all_companies() -> list:
    """
    Get all companies as a list of ticker/name pairs.

    Returns:
        List of dicts with ticker and name
    """
    return [
        {'ticker': ticker, 'name': name}
        for ticker, name in sorted(COMPANY_NAMES.items())
    ]
