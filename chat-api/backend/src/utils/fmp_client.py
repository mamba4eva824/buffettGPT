"""
FMP (Financial Modeling Prep) API Client

Fetches financial data from FMP API with caching support.
Used by the ensemble analyzer to get 5 years / 20 quarters of financial data.
"""

import os
import json
import boto3
import httpx
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from .logger import get_logger

logger = get_logger(__name__)

# Initialize AWS clients
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def get_fmp_api_key() -> str:
    """
    Retrieve FMP API key from AWS Secrets Manager.
    Secret structure: {"FMP_API_KEY": "<actual-key>"}
    """
    secret_name = os.environ.get('FMP_SECRET_NAME', 'buffett-dev-fmp')

    try:
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_dict = json.loads(response['SecretString'])
        return secret_dict['FMP_API_KEY']
    except Exception as e:
        logger.error(f"Failed to retrieve FMP API key: {e}")
        raise


def get_cache_table():
    """Get the DynamoDB table for financial data cache."""
    table_name = os.environ.get(
        'FINANCIAL_DATA_CACHE_TABLE',
        'buffett-dev-financial-data-cache'
    )
    return dynamodb.Table(table_name)


def get_cached_data(ticker: str, fiscal_year: int) -> Optional[dict]:
    """
    Check DynamoDB cache for existing financial data.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        fiscal_year: Fiscal year to retrieve

    Returns:
        Cached data dict if found and not expired, None otherwise
    """
    table = get_cache_table()
    cache_key = f"{ticker}:{fiscal_year}"

    try:
        response = table.get_item(Key={'cache_key': cache_key})

        if 'Item' not in response:
            logger.info(f"Cache miss for {cache_key}")
            return None

        cached = response['Item']
        expires_at = cached.get('expires_at', 0)

        # Check if cache is expired
        if int(expires_at) < int(datetime.now().timestamp()):
            logger.info(f"Cache expired for {cache_key}")
            return None

        # Validate cache structure (must have raw_financials from new format)
        if 'raw_financials' not in cached:
            logger.info(f"Cache data for {cache_key} has old format, treating as miss")
            return None

        logger.info(f"Cache hit for {cache_key}")
        return cached

    except Exception as e:
        logger.error(f"Cache lookup failed: {e}")
        return None


def store_cached_data(ticker: str, fiscal_year: int, data: dict) -> None:
    """
    Store financial data in DynamoDB cache with 90-day TTL.

    Args:
        ticker: Stock ticker symbol
        fiscal_year: Fiscal year
        data: Full data payload including raw_financials and features
    """
    table = get_cache_table()
    cache_key = f"{ticker}:{fiscal_year}"

    # Set 90-day TTL
    now = datetime.now()
    expires_at = int((now + timedelta(days=90)).timestamp())

    item = {
        'cache_key': cache_key,
        'ticker': ticker,
        'fiscal_year': fiscal_year,
        'cached_at': int(now.timestamp()),
        'expires_at': expires_at,
        **data
    }

    # Convert floats to Decimals for DynamoDB
    item = json.loads(json.dumps(item, cls=DecimalEncoder), parse_float=Decimal)

    try:
        table.put_item(Item=item)
        logger.info(f"Cached data for {cache_key}, expires {expires_at}")
    except Exception as e:
        logger.error(f"Failed to cache data: {e}")
        raise


def fetch_from_fmp(ticker: str) -> dict:
    """
    Fetch 5 years / 20 quarters of financial data from FMP API.

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        dict with keys: balance_sheet, income_statement, cash_flow
        Each contains list of quarterly data (up to 20 quarters)
    """
    api_key = get_fmp_api_key()
    base_url = "https://financialmodelingprep.com/stable"

    statements = {}
    # FMP stable API endpoint names (with hyphens)
    endpoint_map = {
        'balance_sheet': 'balance-sheet-statement',
        'income_statement': 'income-statement',
        'cash_flow': 'cash-flow-statement'
    }

    # Create HTTP client with reasonable timeouts
    with httpx.Client(timeout=30.0) as client:
        for statement_key, endpoint_name in endpoint_map.items():
            url = f"{base_url}/{endpoint_name}"
            params = {
                'symbol': ticker.upper(),
                'period': 'quarter',
                'limit': 20,  # 5 years of quarterly data
                'apikey': api_key
            }

            try:
                logger.info(f"Fetching {endpoint_name} for {ticker}")
                response = client.get(url, params=params)
                response.raise_for_status()

                data = response.json()
                statements[statement_key] = data  # Use internal key (balance_sheet, etc.)

                logger.info(f"Retrieved {len(data)} quarters of {statement_key}")

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching {endpoint_name}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching {endpoint_name}: {e}")
                raise

    return statements


def get_financial_data(ticker: str, fiscal_year: Optional[int] = None) -> dict:
    """
    Get financial data for a company, using cache if available.

    This is the main entry point for the FMP client. It:
    1. Checks DynamoDB cache for existing data
    2. If cache miss, fetches from FMP API
    3. Stores fetched data in cache

    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL')
        fiscal_year: Fiscal year (defaults to current year)

    Returns:
        dict containing:
        - raw_financials: {balance_sheet, income_statement, cash_flow}
        - ticker: str
        - fiscal_year: int
        - cached_at: timestamp
    """
    if fiscal_year is None:
        fiscal_year = datetime.now().year

    ticker = ticker.upper().strip()

    # Validate ticker format
    if not ticker.isalpha() or len(ticker) > 5:
        raise ValueError(f"Invalid ticker format: {ticker}")

    # Check cache first
    cached = get_cached_data(ticker, fiscal_year)
    if cached:
        return cached

    # Cache miss - fetch from FMP
    logger.info(f"Fetching fresh data for {ticker}")
    raw_financials = fetch_from_fmp(ticker)

    # Build data payload
    data = {
        'raw_financials': raw_financials,
        'feature_metadata': {
            'version': 'v3.6.5',
            'extraction_timestamp': datetime.now().isoformat(),
            'data_source': 'FMP'
        }
    }

    # Store in cache
    store_cached_data(ticker, fiscal_year, data)

    # Return with additional metadata
    return {
        'cache_key': f"{ticker}:{fiscal_year}",
        'ticker': ticker,
        'fiscal_year': fiscal_year,
        'cached_at': int(datetime.now().timestamp()),
        **data
    }


def normalize_ticker(company_input: str) -> str:
    """
    Attempt to normalize a company name to its ticker symbol.

    For now, this is a simple lookup table. In production, you might
    use an API or more comprehensive database.

    Args:
        company_input: Company name or ticker (e.g., 'Apple' or 'AAPL')

    Returns:
        Ticker symbol in uppercase
    """
    # Common company name to ticker mappings
    COMPANY_TO_TICKER = {
        'apple': 'AAPL',
        'apple inc': 'AAPL',
        'microsoft': 'MSFT',
        'google': 'GOOGL',
        'alphabet': 'GOOGL',
        'amazon': 'AMZN',
        'meta': 'META',
        'facebook': 'META',
        'tesla': 'TSLA',
        'nvidia': 'NVDA',
        'netflix': 'NFLX',
        'disney': 'DIS',
        'walmart': 'WMT',
        'jpmorgan': 'JPM',
        'berkshire': 'BRK.B',
        'berkshire hathaway': 'BRK.B',
        'coca-cola': 'KO',
        'coca cola': 'KO',
        'pepsi': 'PEP',
        'pepsico': 'PEP',
        'visa': 'V',
        'mastercard': 'MA',
        'johnson & johnson': 'JNJ',
        'j&j': 'JNJ',
        'procter & gamble': 'PG',
        'p&g': 'PG',
        'exxon': 'XOM',
        'exxon mobil': 'XOM',
        'chevron': 'CVX',
        'costco': 'COST',
        'american express': 'AXP',
        'amex': 'AXP',
        'sirius': 'SIRI',
        'sirius xm': 'SIRI',
        'rivian': 'RIVN',
    }

    cleaned = company_input.strip().lower()

    # Check if it's already a valid ticker (1-5 uppercase letters)
    upper_input = company_input.strip().upper()
    if upper_input.replace('.', '').isalpha() and len(upper_input) <= 6:
        return upper_input

    # Look up in mapping
    if cleaned in COMPANY_TO_TICKER:
        return COMPANY_TO_TICKER[cleaned]

    # Return as-is (uppercase) if not found
    return upper_input


def validate_ticker(ticker: str) -> bool:
    """
    Validate that a string is a valid ticker format.

    Args:
        ticker: Potential ticker symbol

    Returns:
        True if valid format, False otherwise
    """
    if not ticker:
        return False

    cleaned = ticker.strip().upper()

    # Handle special cases like BRK.B
    if '.' in cleaned:
        parts = cleaned.split('.')
        if len(parts) != 2:
            return False
        return parts[0].isalpha() and len(parts[0]) <= 4 and len(parts[1]) <= 2

    # Standard ticker: 1-5 uppercase letters
    return cleaned.isalpha() and 1 <= len(cleaned) <= 5
