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
CACHE_VERSION = "v3"  # Bumped for currency support

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


def get_forex_cache_table():
    """Get the DynamoDB table for forex rate cache."""
    table_name = os.environ.get(
        'FOREX_CACHE_TABLE',
        'buffett-dev-forex-cache'
    )
    return dynamodb.Table(table_name)


def get_cached_forex_rate(from_currency: str, to_currency: str = 'USD') -> Optional[float]:
    """
    Check DynamoDB cache for forex rate.

    Args:
        from_currency: Source currency code (e.g., 'DKK')
        to_currency: Target currency code (default: 'USD')

    Returns:
        Cached exchange rate if found and not expired, None otherwise
    """
    if from_currency == to_currency:
        return 1.0

    table = get_forex_cache_table()
    pair_key = f"{from_currency.upper()}{to_currency.upper()}"

    try:
        response = table.get_item(Key={'currency_pair': pair_key})

        if 'Item' not in response:
            logger.info(f"[FOREX] Cache miss for {pair_key}")
            return None

        cached = response['Item']
        expires_at = cached.get('expires_at', 0)

        # Check if cache is expired
        if int(expires_at) < int(datetime.now().timestamp()):
            logger.info(f"[FOREX] Cache expired for {pair_key}")
            return None

        rate = float(cached.get('rate', 0))
        logger.info(f"[FOREX] Cache hit for {pair_key}: {rate}")
        return rate

    except Exception as e:
        logger.warning(f"[FOREX] Cache lookup failed for {pair_key}: {e}")
        return None


def store_forex_rate(from_currency: str, to_currency: str, rate: float) -> None:
    """
    Store forex rate in DynamoDB cache with 24-hour TTL.

    Args:
        from_currency: Source currency code
        to_currency: Target currency code
        rate: Exchange rate
    """
    table = get_forex_cache_table()
    pair_key = f"{from_currency.upper()}{to_currency.upper()}"

    now = datetime.now()
    expires_at = int((now + timedelta(hours=24)).timestamp())

    item = {
        'currency_pair': pair_key,
        'rate': Decimal(str(round(rate, 6))),
        'from_currency': from_currency.upper(),
        'to_currency': to_currency.upper(),
        'cached_at': int(now.timestamp()),
        'expires_at': expires_at
    }

    try:
        table.put_item(Item=item)
        logger.info(f"[FOREX] Cached rate for {pair_key}: {rate}")
    except Exception as e:
        logger.warning(f"[FOREX] Failed to cache rate for {pair_key}: {e}")
        # Don't raise - caching is not critical


def fetch_forex_rate(from_currency: str, to_currency: str = 'USD') -> Optional[float]:
    """
    Fetch exchange rate from FMP forex API.

    Args:
        from_currency: Source currency code (e.g., 'DKK', 'EUR')
        to_currency: Target currency code (default: 'USD')

    Returns:
        Exchange rate as float (1 from_currency = X to_currency), or None if unavailable

    Example:
        fetch_forex_rate('DKK', 'USD') -> 0.143 (meaning 1 DKK = 0.143 USD)
    """
    if from_currency == to_currency:
        return 1.0

    api_key = get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/quote"

    # FMP uses pairs like "DKKUSD" for DKK to USD
    pair_symbol = f"{from_currency.upper()}{to_currency.upper()}"

    with httpx.Client(timeout=10.0) as client:
        try:
            response = client.get(url, params={'symbol': pair_symbol, 'apikey': api_key})
            response.raise_for_status()
            data = response.json()

            if data and len(data) > 0:
                rate = data[0].get('price')
                if rate and rate > 0:
                    logger.info(f"[FOREX] Fetched {pair_symbol} rate: {rate}")
                    return float(rate)
                else:
                    logger.warning(f"[FOREX] Invalid rate for {pair_symbol}: {rate}")
                    return None
            else:
                logger.warning(f"[FOREX] No data returned for {pair_symbol}")
                return None

        except httpx.HTTPStatusError as e:
            logger.warning(f"[FOREX] HTTP error fetching {pair_symbol}: {e}")
            return None
        except Exception as e:
            logger.warning(f"[FOREX] Failed to fetch rate for {pair_symbol}: {e}")
            return None


def get_forex_rate(from_currency: str, to_currency: str = 'USD') -> float:
    """
    Get forex rate, using cache if available, falling back to API.

    This is the main entry point for forex rates. It:
    1. Returns 1.0 if currencies are the same
    2. Checks cache for existing rate
    3. Fetches from FMP API if cache miss
    4. Stores fetched rate in cache
    5. Falls back to 1.0 if all else fails (with warning)

    Args:
        from_currency: Source currency code (e.g., 'DKK')
        to_currency: Target currency code (default: 'USD')

    Returns:
        Exchange rate (1 from_currency = X to_currency)
        Returns 1.0 as fallback if rate cannot be fetched
    """
    if not from_currency or from_currency.upper() == to_currency.upper():
        return 1.0

    from_currency = from_currency.upper()
    to_currency = to_currency.upper()

    # Check cache first
    cached_rate = get_cached_forex_rate(from_currency, to_currency)
    if cached_rate is not None:
        return cached_rate

    # Fetch fresh rate
    rate = fetch_forex_rate(from_currency, to_currency)
    if rate is not None:
        store_forex_rate(from_currency, to_currency, rate)
        return rate

    # Fallback: return 1.0 and log warning
    logger.warning(f"[FOREX] Using fallback rate 1.0 for {from_currency}/{to_currency}")
    return 1.0


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
        dict with keys: balance_sheet, income_statement, cash_flow, reported_currency
        Each statement contains list of quarterly data (up to 20 quarters)
        reported_currency is the ISO currency code from FMP (e.g., 'USD', 'DKK')
    """
    api_key = get_fmp_api_key()
    base_url = "https://financialmodelingprep.com/stable"

    statements = {}
    reported_currency = None  # Track currency from first response

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

                # Extract reportedCurrency from first response (all should be same currency)
                if reported_currency is None and data and len(data) > 0:
                    reported_currency = data[0].get('reportedCurrency') or data[0].get('currency') or 'USD'
                    logger.info(f"[FMP_DEBUG] Detected reportedCurrency: {reported_currency}")

                logger.info(f"Retrieved {len(data)} quarters of {statement_key}")

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching {endpoint_name}: {e}")
                raise
            except Exception as e:
                logger.error(f"Error fetching {endpoint_name}: {e}")
                raise

    # Include currency in return data
    statements['reported_currency'] = reported_currency or 'USD'
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
        - currency_info: {code: 'DKK', usd_rate: 0.143, rate_fetched_at: timestamp}
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
        # [FMP_DEBUG] Log cache hit with data summary
        raw = cached.get('raw_financials', {})
        logger.info(f"[FMP_DEBUG] CACHE HIT for {ticker}:{fiscal_year}")
        logger.info(f"[FMP_DEBUG] Cached data: balance_sheet={len(raw.get('balance_sheet', []))} quarters, "
                    f"income_statement={len(raw.get('income_statement', []))} quarters, "
                    f"cash_flow={len(raw.get('cash_flow', []))} quarters")
        # Log sample data point
        if raw.get('balance_sheet'):
            bs = raw['balance_sheet'][0]
            logger.info(f"[FMP_DEBUG] Sample Q0: totalDebt={bs.get('totalDebt')}, "
                        f"totalEquity={bs.get('totalStockholdersEquity')}, date={bs.get('date')}")
        return cached

    # Cache miss - fetch from FMP
    logger.info(f"[FMP_DEBUG] CACHE MISS for {ticker}:{fiscal_year} - fetching from FMP API")
    raw_financials = fetch_from_fmp(ticker)

    # [FMP_DEBUG] Log fresh data retrieved
    logger.info(f"[FMP_DEBUG] FMP response: balance_sheet={len(raw_financials.get('balance_sheet', []))} quarters, "
                f"income_statement={len(raw_financials.get('income_statement', []))} quarters, "
                f"cash_flow={len(raw_financials.get('cash_flow', []))} quarters")
    # Log sample data point (most recent quarter)
    if raw_financials.get('balance_sheet'):
        bs = raw_financials['balance_sheet'][0]
        logger.info(f"[FMP_DEBUG] Sample Q0: totalDebt={bs.get('totalDebt')}, "
                    f"totalEquity={bs.get('totalStockholdersEquity')}, date={bs.get('date')}")
    if raw_financials.get('income_statement'):
        inc = raw_financials['income_statement'][0]
        logger.info(f"[FMP_DEBUG] Sample Q0: revenue={inc.get('revenue')}, netIncome={inc.get('netIncome')}")
    if raw_financials.get('cash_flow'):
        cf = raw_financials['cash_flow'][0]
        logger.info(f"[FMP_DEBUG] Sample Q0: operatingCashFlow={cf.get('operatingCashFlow')}, freeCashFlow={cf.get('freeCashFlow')}")

    # Extract and process currency info
    reported_currency = raw_financials.pop('reported_currency', 'USD')
    usd_rate = get_forex_rate(reported_currency, 'USD') if reported_currency != 'USD' else 1.0

    currency_info = {
        'code': reported_currency,
        'usd_rate': usd_rate,
        'rate_fetched_at': datetime.now().isoformat()
    }
    logger.info(f"[FMP_DEBUG] Currency info: {currency_info}")

    # Build data payload
    data = {
        'raw_financials': raw_financials,
        'currency_info': currency_info,
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


# ============================================================
# VALUATION DATA ENDPOINTS
# ============================================================

def fetch_key_metrics(ticker: str, limit: int = 5) -> list:
    """
    Fetch historical key metrics for mean reversion analysis.

    Returns annual key metrics including P/E, P/S, P/B, EV/EBITDA,
    ROE, ROA for the specified number of years.

    Args:
        ticker: Stock ticker symbol (e.g., 'INTC')
        limit: Number of annual periods to fetch (default: 5 for 5-year average)

    Returns:
        List of annual key metrics dicts, most recent first
    """
    api_key = get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/key-metrics"

    with httpx.Client(timeout=15.0) as client:
        try:
            response = client.get(
                url,
                params={
                    'symbol': ticker.upper(),
                    'limit': limit,
                    'apikey': api_key
                }
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[FMP] Fetched {len(data)} periods of key metrics for {ticker}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"[FMP] HTTP error fetching key metrics for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"[FMP] Error fetching key metrics for {ticker}: {e}")
            return []


def fetch_key_metrics_ttm(ticker: str) -> dict:
    """
    Fetch trailing twelve months (TTM) key metrics.

    Returns current TTM values for P/E, P/S, P/B, EV/EBITDA, ROE, ROA.
    Use this for current snapshot comparison against historical averages.

    Args:
        ticker: Stock ticker symbol (e.g., 'INTC')

    Returns:
        Dict with TTM key metrics, or empty dict if unavailable
    """
    api_key = get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/key-metrics-ttm"

    with httpx.Client(timeout=15.0) as client:
        try:
            response = client.get(
                url,
                params={
                    'symbol': ticker.upper(),
                    'apikey': api_key
                }
            )
            response.raise_for_status()
            data = response.json()

            # TTM endpoint returns a list with one item
            if data and len(data) > 0:
                logger.info(f"[FMP] Fetched TTM key metrics for {ticker}")
                return data[0]
            return {}
        except httpx.HTTPStatusError as e:
            logger.error(f"[FMP] HTTP error fetching TTM key metrics for {ticker}: {e}")
            return {}
        except Exception as e:
            logger.error(f"[FMP] Error fetching TTM key metrics for {ticker}: {e}")
            return {}


def fetch_financial_ratios_ttm(ticker: str) -> dict:
    """
    Fetch trailing twelve months (TTM) financial ratios.

    Returns current TTM values for profitability and efficiency ratios
    including Net Profit Margin, Asset Turnover, etc.

    Args:
        ticker: Stock ticker symbol (e.g., 'INTC')

    Returns:
        Dict with TTM financial ratios, or empty dict if unavailable
    """
    api_key = get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/ratios-ttm"

    with httpx.Client(timeout=15.0) as client:
        try:
            response = client.get(
                url,
                params={
                    'symbol': ticker.upper(),
                    'apikey': api_key
                }
            )
            response.raise_for_status()
            data = response.json()

            # TTM endpoint returns a list with one item
            if data and len(data) > 0:
                logger.info(f"[FMP] Fetched TTM financial ratios for {ticker}")
                return data[0]
            return {}
        except httpx.HTTPStatusError as e:
            logger.error(f"[FMP] HTTP error fetching TTM ratios for {ticker}: {e}")
            return {}
        except Exception as e:
            logger.error(f"[FMP] Error fetching TTM ratios for {ticker}: {e}")
            return {}


def fetch_analyst_estimates(ticker: str, limit: int = 10) -> list:
    """
    Fetch analyst estimates for forward revenue and EPS.

    Returns consensus estimates for upcoming fiscal years including
    estimated revenue average and estimated EPS average.

    Args:
        ticker: Stock ticker symbol (e.g., 'INTC')
        limit: Number of estimate periods to fetch (default: 10)

    Returns:
        List of analyst estimate dicts, most recent first
    """
    api_key = get_fmp_api_key()
    url = "https://financialmodelingprep.com/stable/analyst-estimates"

    with httpx.Client(timeout=15.0) as client:
        try:
            response = client.get(
                url,
                params={
                    'symbol': ticker.upper(),
                    'period': 'annual',
                    'limit': limit,
                    'apikey': api_key
                }
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"[FMP] Fetched {len(data)} analyst estimates for {ticker}")
            return data
        except httpx.HTTPStatusError as e:
            logger.error(f"[FMP] HTTP error fetching analyst estimates for {ticker}: {e}")
            return []
        except Exception as e:
            logger.error(f"[FMP] Error fetching analyst estimates for {ticker}: {e}")
            return []
