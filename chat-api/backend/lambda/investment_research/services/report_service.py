"""
Report service for retrieving cached investment reports from DynamoDB.

This is a lightweight implementation that does NOT depend on the
investment_research.report_generator module to avoid layer complexity.

Based on report_generator._get_cached_report() logic but standalone.
"""
import boto3
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from decimal import Decimal

from config.settings import (
    INVESTMENT_REPORTS_TABLE,
    INVESTMENT_REPORTS_TABLE_V2,
    DEFAULT_FISCAL_YEAR
)

logger = logging.getLogger(__name__)

# Initialize DynamoDB resource (lazy initialization for Lambda cold starts)
_dynamodb = None
_reports_table = None
_reports_table_v2 = None


def _get_table():
    """Get DynamoDB table resource with lazy initialization."""
    global _dynamodb, _reports_table
    if _reports_table is None:
        _dynamodb = boto3.resource('dynamodb')
        _reports_table = _dynamodb.Table(INVESTMENT_REPORTS_TABLE)
        logger.info(f"Initialized DynamoDB table: {INVESTMENT_REPORTS_TABLE}")
    return _reports_table


def _get_table_v2():
    """Get DynamoDB v2 table resource with lazy initialization."""
    global _dynamodb, _reports_table_v2
    if _reports_table_v2 is None:
        if _dynamodb is None:
            _dynamodb = boto3.resource('dynamodb')
        _reports_table_v2 = _dynamodb.Table(INVESTMENT_REPORTS_TABLE_V2)
        logger.info(f"Initialized DynamoDB v2 table: {INVESTMENT_REPORTS_TABLE_V2}")
    return _reports_table_v2


def decimal_to_float(obj: Any) -> Any:
    """
    Recursively convert Decimal to float in nested structures.

    DynamoDB returns numbers as Decimal objects which need to be
    converted for JSON serialization.

    Args:
        obj: Any Python object (dict, list, Decimal, etc.)

    Returns:
        Same structure with Decimals converted to float/int
    """
    if isinstance(obj, Decimal):
        # Convert to int if whole number, else float
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def get_cached_report(ticker: str, fiscal_year: int = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve cached report from DynamoDB.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        fiscal_year: Fiscal year (default: current year)

    Returns:
        Dict with report_content, ratings, generated_at, etc.
        None if no report exists or TTL expired.

    DynamoDB Table Schema:
        - ticker (S): Partition key
        - fiscal_year (N): Sort key
        - report_content (S): Full markdown report
        - ratings (M): Structured ratings map
            - debt: {rating, confidence, key_factors}
            - cashflow: {rating, confidence, key_factors}
            - growth: {rating, confidence, key_factors}
            - overall_verdict: BUY/HOLD/SELL
            - conviction: High/Medium/Low
        - generated_at (S): ISO timestamp
        - model (S): Model used to generate
        - features_snapshot (S): JSON string of features
        - ttl (N): TTL timestamp for auto-expiration
    """
    ticker = ticker.upper()
    fiscal_year = fiscal_year or DEFAULT_FISCAL_YEAR

    try:
        table = _get_table()
        response = table.get_item(
            Key={
                'ticker': ticker,
                'fiscal_year': fiscal_year
            }
        )

        item = response.get('Item')
        if not item:
            logger.info(f"No cached report found for {ticker} FY{fiscal_year}")
            return None

        # Check if TTL has passed (DynamoDB TTL deletion is async)
        ttl = item.get('ttl', 0)
        if ttl and isinstance(ttl, (int, float, Decimal)):
            ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
            if ttl_value < datetime.utcnow().timestamp():
                logger.info(f"Report for {ticker} FY{fiscal_year} has expired (TTL passed)")
                return None

        # Convert Decimals to floats for JSON serialization
        item = decimal_to_float(item)

        # Parse ratings from JSON string if stored as string
        # (ratings is serialized as JSON for DynamoDB float compatibility)
        if 'ratings' in item and isinstance(item['ratings'], str):
            try:
                import json
                item['ratings'] = json.loads(item['ratings'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse ratings JSON for {ticker}")

        logger.info(f"Retrieved cached report for {ticker} FY{fiscal_year}")
        return item

    except Exception as e:
        logger.error(f"Error retrieving report for {ticker}: {e}")
        return None


def validate_ticker(ticker: str) -> bool:
    """
    Basic ticker validation.

    Args:
        ticker: Stock ticker symbol

    Returns:
        True if valid format, False otherwise
    """
    if not ticker:
        return False

    ticker = ticker.strip().upper()

    # Basic format: 1-5 uppercase letters (covers most US tickers)
    if not (1 <= len(ticker) <= 5):
        return False

    if not ticker.isalpha():
        return False

    return True


def get_available_reports(limit: int = 100) -> list:
    """
    Get list of available reports (for debugging/admin).

    Note: This scans the table and should be used sparingly.

    Args:
        limit: Maximum number of reports to return

    Returns:
        List of {ticker, fiscal_year, generated_at} dicts
    """
    try:
        table = _get_table()
        response = table.scan(
            ProjectionExpression='ticker, fiscal_year, generated_at',
            Limit=limit
        )

        items = response.get('Items', [])
        return [decimal_to_float(item) for item in items]

    except Exception as e:
        logger.error(f"Error scanning reports: {e}")
        return []


# ============================================================
# V2 TABLE METHODS (Section-per-item schema)
# ============================================================

def get_executive(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get combined executive item from v2 table (single DynamoDB read).

    Returns the 00_executive item which contains:
    - toc: List of section entries with section_id, title, part, icon, word_count
    - ratings: Structured ratings dict
    - executive_sections: List of Part 1 sections with content
    - total_word_count: Total words in report
    - generated_at: ISO timestamp

    This is the primary method for initial load - returns everything needed
    to render the executive summary in a single DynamoDB GetItem call.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        Dict with toc, ratings, executive_sections, metadata. None if not found.
    """
    ticker = ticker.upper()

    try:
        table = _get_table_v2()
        response = table.get_item(
            Key={
                'ticker': ticker,
                'section_id': '00_executive'
            }
        )

        item = response.get('Item')
        if not item:
            logger.info(f"No executive item (v2) found for {ticker}")
            return None

        # Check TTL
        ttl = item.get('ttl', 0)
        if ttl and isinstance(ttl, (int, float, Decimal)):
            ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
            if ttl_value < datetime.utcnow().timestamp():
                logger.info(f"Executive item for {ticker} has expired (TTL passed)")
                return None

        # Convert Decimals
        item = decimal_to_float(item)

        # Parse JSON strings if stored as strings
        import json
        if 'toc' in item and isinstance(item['toc'], str):
            try:
                item['toc'] = json.loads(item['toc'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse toc JSON for {ticker}")

        if 'ratings' in item and isinstance(item['ratings'], str):
            try:
                item['ratings'] = json.loads(item['ratings'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse ratings JSON for {ticker}")

        if 'executive_sections' in item and isinstance(item['executive_sections'], str):
            try:
                item['executive_sections'] = json.loads(item['executive_sections'])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Could not parse executive_sections JSON for {ticker}")

        exec_count = len(item.get('executive_sections', []))
        toc_count = len(item.get('toc', []))
        logger.info(f"Retrieved executive for {ticker} ({exec_count} sections, {toc_count} ToC entries)")
        return item

    except Exception as e:
        logger.error(f"Error retrieving executive for {ticker}: {e}")
        return None


def get_report_toc(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get report table of contents and ratings from v2 table.

    Note: This now fetches from 00_executive item for compatibility.
    For full executive content, use get_executive() instead.

    Returns:
    - toc: List of section entries with section_id, title, part, icon, word_count
    - ratings: Structured ratings dict
    - total_word_count: Total words in report
    - generated_at: ISO timestamp

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        Dict with toc, ratings, metadata. None if not found.
    """
    # ToC is now part of the executive item
    item = get_executive(ticker)
    if not item:
        return None

    # Return subset without executive_sections for backward compatibility
    return {
        'ticker': item.get('ticker'),
        'section_id': item.get('section_id'),
        'toc': item.get('toc', []),
        'ratings': item.get('ratings', {}),
        'total_word_count': item.get('total_word_count', 0),
        'generated_at': item.get('generated_at')
    }


def get_report_section(ticker: str, section_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific section from the v2 table.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')
        section_id: Section identifier (e.g., '06_growth')

    Returns:
        Dict with content, title, part, icon, word_count. None if not found.
    """
    ticker = ticker.upper()
    section_id = section_id.lower()

    try:
        table = _get_table_v2()
        response = table.get_item(
            Key={
                'ticker': ticker,
                'section_id': section_id
            }
        )

        item = response.get('Item')
        if not item:
            logger.info(f"Section {section_id} not found for {ticker}")
            return None

        # Check TTL
        ttl = item.get('ttl', 0)
        if ttl and isinstance(ttl, (int, float, Decimal)):
            ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
            if ttl_value < datetime.utcnow().timestamp():
                logger.info(f"Section {section_id} for {ticker} has expired (TTL passed)")
                return None

        # Convert Decimals
        item = decimal_to_float(item)

        logger.info(f"Retrieved section {section_id} for {ticker}")
        return item

    except Exception as e:
        logger.error(f"Error retrieving section {section_id} for {ticker}: {e}")
        return None


def get_executive_sections(ticker: str) -> list:
    """
    Get Part 1 (executive summary) sections from the v2 table.

    Uses the part-index GSI to efficiently query all sections with part=1.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        List of section items sorted by display_order.
        Empty list if not found or error.
    """
    ticker = ticker.upper()

    try:
        table = _get_table_v2()

        # Query using part-index GSI
        from boto3.dynamodb.conditions import Key
        response = table.query(
            IndexName='part-index',
            KeyConditionExpression=Key('ticker').eq(ticker) & Key('part').eq(1)
        )

        items = response.get('Items', [])
        if not items:
            logger.info(f"No executive sections found for {ticker}")
            return []

        # Check TTL on first item (all have same TTL)
        if items:
            ttl = items[0].get('ttl', 0)
            if ttl and isinstance(ttl, (int, float, Decimal)):
                ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
                if ttl_value < datetime.utcnow().timestamp():
                    logger.info(f"Executive sections for {ticker} have expired (TTL passed)")
                    return []

        # Convert Decimals and sort by display_order
        items = [decimal_to_float(item) for item in items]
        items.sort(key=lambda x: x.get('display_order', 0))

        logger.info(f"Retrieved {len(items)} executive sections for {ticker}")
        return items

    except Exception as e:
        logger.error(f"Error retrieving executive sections for {ticker}: {e}")
        return []


def get_all_sections(ticker: str) -> list:
    """
    Get all sections for a ticker from the v2 table.

    Queries all items for the ticker and sorts by display_order.
    Excludes the metadata item (section_id = '00_metadata').

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        List of section items sorted by display_order.
        Empty list if not found or error.
    """
    ticker = ticker.upper()

    try:
        table = _get_table_v2()

        # Query all items for this ticker
        from boto3.dynamodb.conditions import Key
        response = table.query(
            KeyConditionExpression=Key('ticker').eq(ticker)
        )

        items = response.get('Items', [])
        if not items:
            logger.info(f"No sections found for {ticker}")
            return []

        # Check TTL on first item
        if items:
            ttl = items[0].get('ttl', 0)
            if ttl and isinstance(ttl, (int, float, Decimal)):
                ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
                if ttl_value < datetime.utcnow().timestamp():
                    logger.info(f"Sections for {ticker} have expired (TTL passed)")
                    return []

        # Convert Decimals
        items = [decimal_to_float(item) for item in items]

        # Filter out executive item and sort by display_order
        sections = [
            item for item in items
            if item.get('section_id') != '00_executive'
        ]
        sections.sort(key=lambda x: x.get('display_order', 0))

        logger.info(f"Retrieved {len(sections)} sections for {ticker}")
        return sections

    except Exception as e:
        logger.error(f"Error retrieving all sections for {ticker}: {e}")
        return []


def check_report_exists_v2(ticker: str) -> bool:
    """
    Check if a report exists in the v2 table for the given ticker.

    Quick existence check without retrieving full content.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        True if report exists and is not expired, False otherwise.
    """
    ticker = ticker.upper()

    try:
        table = _get_table_v2()
        response = table.get_item(
            Key={
                'ticker': ticker,
                'section_id': '00_executive'
            },
            ProjectionExpression='ticker, ttl'  # Minimal data
        )

        item = response.get('Item')
        if not item:
            return False

        # Check TTL
        ttl = item.get('ttl', 0)
        if ttl and isinstance(ttl, (int, float, Decimal)):
            ttl_value = float(ttl) if isinstance(ttl, Decimal) else ttl
            if ttl_value < datetime.utcnow().timestamp():
                return False

        return True

    except Exception as e:
        logger.error(f"Error checking report existence for {ticker}: {e}")
        return False


def get_report_status(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Get report status for conversation loading optimization.

    Returns detailed status information without fetching full content.
    Used by frontend to determine if sections can be fetched on-demand
    or if the report has expired.

    Args:
        ticker: Stock symbol (e.g., 'AAPL')

    Returns:
        Dict with status info:
        {
            'exists': True,
            'ticker': 'AAPL',
            'generated_at': '2025-01-15T10:30:00Z',
            'expired': False,
            'ttl_remaining_days': 75,
            'total_word_count': 15000
        }
        Returns None if report doesn't exist.
    """
    ticker = ticker.upper()

    try:
        table = _get_table_v2()
        # Use ExpressionAttributeNames for 'ttl' since it's a DynamoDB reserved word
        response = table.get_item(
            Key={
                'ticker': ticker,
                'section_id': '00_executive'
            },
            ProjectionExpression='ticker, #t, generated_at, total_word_count',
            ExpressionAttributeNames={'#t': 'ttl'}
        )

        item = response.get('Item')
        if not item:
            logger.info(f"No report found for {ticker}")
            return None

        # Convert Decimals
        item = decimal_to_float(item)

        # Check TTL and calculate remaining days
        ttl = item.get('ttl', 0)
        now = datetime.utcnow().timestamp()
        expired = False
        ttl_remaining_days = None

        if ttl:
            if ttl < now:
                expired = True
                ttl_remaining_days = 0
            else:
                ttl_remaining_days = int((ttl - now) / 86400)  # Convert seconds to days

        status = {
            'exists': True,
            'ticker': ticker,
            'generated_at': item.get('generated_at'),
            'expired': expired,
            'ttl_remaining_days': ttl_remaining_days,
            'total_word_count': item.get('total_word_count', 0)
        }

        logger.info(f"Report status for {ticker}: expired={expired}, ttl_remaining={ttl_remaining_days} days")
        return status

    except Exception as e:
        logger.error(f"Error getting report status for {ticker}: {e}")
        return None
