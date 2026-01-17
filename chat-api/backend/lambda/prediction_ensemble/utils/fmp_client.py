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

# Cache version - increment when feature extraction logic changes
# This ensures old cached data (with hardcoded zeros) is ignored
CACHE_VERSION = "v2"

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


def get_ticker_lookup_table():
    """Get the DynamoDB table for ticker lookup cache."""
    table_name = os.environ.get(
        'TICKER_LOOKUP_TABLE',
        'buffett-dev-ticker-lookup'
    )
    return dynamodb.Table(table_name)


def get_cached_ticker(company_name: str) -> Optional[str]:
    """
    Check DynamoDB cache for company name → ticker mapping.

    Args:
        company_name: Lowercase company name

    Returns:
        Ticker symbol if found and not expired, None otherwise
    """
    table = get_ticker_lookup_table()
    normalized_name = company_name.strip().lower()

    try:
        response = table.get_item(Key={'company_name': normalized_name})

        if 'Item' not in response:
            logger.info(f"Ticker cache miss for '{normalized_name}'")
            return None

        cached = response['Item']
        expires_at = cached.get('expires_at', 0)

        # Check if cache is expired
        if int(expires_at) < int(datetime.now().timestamp()):
            logger.info(f"Ticker cache expired for '{normalized_name}'")
            return None

        ticker = cached.get('ticker')
        logger.info(f"Ticker cache hit: '{normalized_name}' → {ticker}")
        return ticker

    except Exception as e:
        logger.error(f"Ticker cache lookup failed: {e}")
        return None


def store_cached_ticker(company_name: str, ticker: str, full_name: str = "") -> None:
    """
    Store company name → ticker mapping in DynamoDB cache with 30-day TTL.

    Args:
        company_name: Original company name query
        ticker: Resolved ticker symbol
        full_name: Full company name from FMP (for reference)
    """
    table = get_ticker_lookup_table()
    normalized_name = company_name.strip().lower()

    # Set 30-day TTL
    now = datetime.now()
    expires_at = int((now + timedelta(days=30)).timestamp())

    item = {
        'company_name': normalized_name,
        'ticker': ticker.upper(),
        'full_name': full_name,
        'cached_at': int(now.timestamp()),
        'expires_at': expires_at
    }

    try:
        table.put_item(Item=item)
        logger.info(f"Cached ticker: '{normalized_name}' → {ticker}")
    except Exception as e:
        logger.error(f"Failed to cache ticker: {e}")
        # Don't raise - caching is not critical


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
    # Include CACHE_VERSION in key to invalidate old cached data when feature extraction changes
    cache_key = f"{CACHE_VERSION}:{ticker}:{fiscal_year}"

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
    # Include CACHE_VERSION in key to invalidate old cached data when feature extraction changes
    cache_key = f"{CACHE_VERSION}:{ticker}:{fiscal_year}"

    # Set 90-day TTL
    now = datetime.now()
    expires_at = int((now + timedelta(days=90)).timestamp())

    item = {
        'cache_key': cache_key,
        'ticker': ticker,
        'fiscal_year': fiscal_year,
        'cache_version': CACHE_VERSION,  # Store version for debugging
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


def verify_cache_readable(ticker: str, fiscal_year: int, max_attempts: int = 3) -> bool:
    """
    Verify that cached data is readable after a write.
    Handles DynamoDB eventual consistency latency.

    This prevents race conditions when multiple Lambda instances try to read
    cache data that was just written by another instance.

    Args:
        ticker: Stock ticker symbol
        fiscal_year: Fiscal year
        max_attempts: Max retry attempts (default 3, ~300ms total)

    Returns:
        True if cache is readable, False if verification failed
    """
    import time

    for attempt in range(max_attempts):
        cached = get_cached_data(ticker, fiscal_year)
        if cached:
            logger.info(f"[CACHE_VERIFY] {ticker}:{fiscal_year} readable after {attempt + 1} attempt(s)")
            return True

        # Exponential backoff: 50ms, 100ms, 150ms
        wait_ms = 50 * (attempt + 1)
        logger.info(f"[CACHE_VERIFY] {ticker}:{fiscal_year} not readable, waiting {wait_ms}ms...")
        time.sleep(wait_ms / 1000)

    logger.warning(f"[CACHE_VERIFY] {ticker}:{fiscal_year} verification failed after {max_attempts} attempts")
    return False


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

    # Verify cache is readable before returning (handles DynamoDB eventual consistency)
    # This ensures parallel Lambda invocations will see the cached data
    verify_cache_readable(ticker, fiscal_year)

    # Return with additional metadata
    return {
        'cache_key': f"{CACHE_VERSION}:{ticker}:{fiscal_year}",
        'ticker': ticker,
        'fiscal_year': fiscal_year,
        'cache_version': CACHE_VERSION,
        'cached_at': int(datetime.now().timestamp()),
        **data
    }


def normalize_ticker(company_input: str) -> str:
    """
    Normalize a company name to its ticker symbol.

    Flow:
    1. If input looks like a ticker (e.g., 'AAPL') → return as-is
    2. Check DynamoDB ticker cache → if found, return cached ticker
    3. If cache miss → call FMP search API → cache result → return ticker

    Args:
        company_input: Company name or ticker (e.g., 'Novo Nordisk' or 'NVO')

    Returns:
        Ticker symbol in uppercase

    Raises:
        ValueError: If no matching company found
    """
    cleaned = company_input.strip()
    upper_input = cleaned.upper()

    # Step 1: Check if it's already a valid ticker format
    # Standard tickers are 1-4 letters. Special cases like BRK.B or 5-letter tickers (GOOGL) exist
    # but we should verify 5+ letter inputs since they could be company names (e.g., "APPLE")
    base_input = upper_input.replace('.', '').replace('-', '')
    if base_input.isalpha() and len(base_input) <= 4:
        # Short ticker - assume valid
        return upper_input
    elif '.' in upper_input or '-' in upper_input:
        # Special format like BRK.B - assume valid
        return upper_input

    # Step 2: Check DynamoDB ticker cache
    cached_ticker = get_cached_ticker(cleaned)
    if cached_ticker:
        return cached_ticker

    # Step 3: Cache miss - call FMP search API
    US_EXCHANGES = {'NASDAQ', 'NYSE', 'AMEX', 'NYSEARCA', 'BATS', 'CBOE'}

    try:
        api_key = get_fmp_api_key()
        base_url = "https://financialmodelingprep.com/stable/search-name"

        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                base_url,
                params={
                    'query': cleaned,
                    'limit': 10,
                    'apikey': api_key
                }
            )
            response.raise_for_status()
            results = response.json()

            if results and len(results) > 0:
                # Prioritize US exchanges
                us_results = [r for r in results if r.get('exchange') in US_EXCHANGES]
                best_match = us_results[0] if us_results else results[0]

                ticker = best_match.get('symbol', '').upper()
                full_name = best_match.get('name', '')
                logger.info(f"Resolved '{cleaned}' to {ticker} ({full_name})")

                # Cache the result for future lookups
                store_cached_ticker(cleaned, ticker, full_name)

                return ticker

            # No results found
            logger.warning(f"No ticker found for company: {cleaned}")
            raise ValueError(f"Could not find ticker for: {cleaned}")

    except httpx.HTTPError as e:
        logger.error(f"FMP search API error: {e}")
        raise ValueError(f"Failed to search for company: {cleaned}")
    except Exception as e:
        logger.error(f"Error normalizing ticker: {e}")
        raise


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
