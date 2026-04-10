"""
Report Generator using Claude Opus 4.5 with Thinking mode.

Generates comprehensive investment analysis reports and caches them in DynamoDB.
Reuses existing FMP client and feature extractor from prediction_ensemble.
"""

import json
import boto3
import anthropic
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from decimal import Decimal
import os
import re
import sys

# Add parent directory to path for imports (to access src/utils)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.utils.fmp_client import (
    get_financial_data,
    fetch_key_metrics,
    fetch_key_metrics_ttm,
    fetch_financial_ratios_ttm,
    fetch_analyst_estimates,
    fetch_earnings,
    fetch_earnings_calendar_upcoming,
    fetch_dividends
)
from src.utils.feature_extractor import extract_all_features, extract_quarterly_trends, prepare_metrics_for_cache
from investment_research.index_tickers import get_index_tickers
from investment_research.section_parser import (
    parse_report_sections,
    extract_ratings_json,
    build_executive_item,
    get_detailed_section_items
)
from investment_research.company_names import get_company_name_or_ticker


class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles Decimal types for DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def decimal_to_float(obj):
    """Recursively convert Decimal to float in nested structures."""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: decimal_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [decimal_to_float(item) for item in obj]
    return obj


def get_total_liquidity(balance_sheet: dict) -> float:
    """
    Get total liquidity (cash + short-term investments) from a balance sheet.

    Many companies (especially tech) hold significant amounts in short-term
    investments that are nearly as liquid as cash. This function captures
    the full liquidity picture.

    Priority order:
    1. cashAndShortTermInvestments (FMP's pre-calculated total)
    2. cashAndCashEquivalents + shortTermInvestments (calculated)
    3. cashAndCashEquivalents alone (fallback)

    Args:
        balance_sheet: Dict containing balance sheet data from FMP

    Returns:
        Total liquidity as float
    """
    # Try FMP's pre-calculated total first
    if balance_sheet.get('cashAndShortTermInvestments'):
        return float(balance_sheet.get('cashAndShortTermInvestments', 0) or 0)

    # Calculate from components
    cash = float(balance_sheet.get('cashAndCashEquivalents', 0) or 0)
    short_term = float(balance_sheet.get('shortTermInvestments', 0) or 0)

    return cash + short_term


class ReportGenerator:
    """
    Generates investment analysis reports using Claude Opus 4.5 with extended thinking.

    The generator:
    1. Fetches financial data from FMP API (via existing fmp_client)
    2. Extracts features and trends (via existing feature_extractor)
    3. Uses Claude Opus 4.5 with Thinking to generate comprehensive analysis
    4. Caches reports in DynamoDB V2 table (section-per-item schema)

    Storage:
    - Uses V2 table schema (investment-reports-v2) with section-per-item storage
    - V1 table was removed - all reports now use V2 schema
    - Each report stored as 15 items: 1 executive + 14 detailed sections

    Modes:
    - Claude Code mode (RECOMMENDED): Use prepare_data() to get metrics,
      then save_report_sections() to cache
    - API mode (DEPRECATED): Set ANTHROPIC_API_KEY for automated generation

    Prompt Versions:
    - v1: Financial-grade reports (original, more technical)
    - v2: Consumer-grade reports (Gen Z/Millennial friendly, more analogies)
    - v3: Balanced-grade reports (consumer language + financial depth, profitability section)
    - v4: Audit-grade v4.1 reports with enhanced Gen Z/Millennial accessibility:
          - Zero-tolerance jargon policy (all ratios require plain English in same sentence)
          - Dynamic section headers (unique to each company's metrics/story)
          - Contextual analogies (tailored to company's industry, not generic)
          - Mandatory analogy categories (streaming, payment apps, side hustles, gaming)
          - "Real Talk" verdict section (casual text-message style recommendation)
          - Dynamic table headers for narrative tables
          - Enhanced quality checklist with uniqueness tests
    - v4.2: Streamlined audit-grade (~40% shorter than v4.1):
          - Same core features as v4.1 but principle-based, not example-heavy
          - Three Core Principles: Zero-tolerance jargon, Uniqueness, Real Talk
          - Reduced prompt dilution risk for better output quality
          - Recommended for production use
    """

    # Available prompt versions
    PROMPT_VERSIONS = {
        1: 'investment_report_prompt.txt',      # Financial grade
        2: 'investment_report_prompt_v2.txt',   # Consumer grade
        3: 'investment_report_prompt_v3.txt',   # Balanced grade
        4: 'investment_report_prompt_v4.txt',   # Audit grade v4.1 (verbose, example-heavy)
        4.2: 'investment_report_prompt_v4_2.txt',  # Audit grade v4.2 (streamlined, principle-based)
        4.3: 'investment_report_prompt_v4_3.txt',  # Audit grade v4.3 (full translation table restored)
        4.4: 'investment_report_prompt_v4_4.txt',  # Audit grade v4.4 (plain English table headers)
        4.5: 'investment_report_prompt_v4_5.txt',  # Audit grade v4.5 (table structure, vibe check, rating scale)
        4.6: 'investment_report_prompt_v4_6.txt',  # Audit grade v4.6 (dashboard consolidation, 12 sections)
        4.7: 'investment_report_prompt_v4_7.txt',  # Audit grade v4.7 (extensive depth, investment fit, $100/mo projections)
        4.8: 'investment_report_prompt_v4_8.txt',  # Audit grade v4.8 (executive summary first, dynamic headers, simplified language)
        4.9: 'investment_report_prompt_v4_9.txt',  # Audit grade v4.9 (consolidated dashboard - removed redundant sections 15/16)
        5.0: 'investment_report_prompt_v5_0.txt',  # Audit grade v5.0 (visual momentum dashboards, progress bars, pattern alerts)
        5.1: 'investment_report_prompt_v5_1.txt',  # Audit grade v5.1 (revenue stickiness, margin waterfall, operating leverage, peer comparisons, decision triggers)
        5.2: 'investment_report_prompt_v5_2.txt',  # Audit grade v5.2 (cross-report uniqueness, anti-templating, variable DCA/momentum formats)
        6.0: 'investment_report_prompt_v6_slim.txt',  # Slim mode v6.0 (executive summary + decision triggers only, ~68% less content)
    }

    def __init__(self, use_api: bool = False, prompt_version: float = 5.2):
        """
        Initialize the report generator.

        Args:
            use_api: If True, requires ANTHROPIC_API_KEY. If False, operates in
                     data-prep mode for Claude Code to generate reports.
            prompt_version: Which prompt template to use (1=financial grade, 2=consumer grade)
        """
        self.use_api = use_api
        self.anthropic_client = None

        # Validate and set prompt version
        if prompt_version not in self.PROMPT_VERSIONS:
            raise ValueError(f"Invalid prompt_version: {prompt_version}. Must be one of {list(self.PROMPT_VERSIONS.keys())}")
        self.prompt_version = prompt_version
        print(f"  Using prompt version: v{prompt_version} ({self._get_prompt_description()})")

        if use_api:
            api_key = os.environ.get('ANTHROPIC_API_KEY')
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY environment variable is required for API mode.\n"
                    "Set it with: export ANTHROPIC_API_KEY='your-key-here'\n"
                    "Or use Claude Code mode (default) for interactive generation."
                )
            self.anthropic_client = anthropic.Anthropic(api_key=api_key)

        self.dynamodb = boto3.resource('dynamodb')

        # V2 table for section-based storage (section-per-item schema)
        # V1 table was removed - all reports now use V2 schema
        table_name_v2 = os.environ.get('INVESTMENT_REPORTS_TABLE_V2', 'investment-reports-v2-dev')
        self.reports_table_v2 = self.dynamodb.Table(table_name_v2)

        # Metrics history cache table (for follow-up agent queries)
        metrics_table_name = os.environ.get('METRICS_HISTORY_CACHE_TABLE', 'metrics-history-dev')
        self.metrics_history_table = self.dynamodb.Table(metrics_table_name)

    def _get_prompt_description(self) -> str:
        """Return human-readable description of current prompt version."""
        descriptions = {
            1: "Financial Grade - technical analysis",
            2: "Consumer Grade - Gen Z/Millennial friendly",
            3: "Balanced Grade - consumer language + financial depth",
            4: "Audit Grade v4.1 - verbose, example-heavy (660 lines)",
            4.2: "Audit Grade v4.2 - streamlined, principle-based (180 lines)",
            4.3: "Audit Grade v4.3 - full translation table + streamlined (220 lines)",
            4.4: "Audit Grade v4.4 - plain English table headers (240 lines)",
            4.5: "Audit Grade v4.5 - table structure + vibe check + rating scale (320 lines)",
            4.6: "Audit Grade v4.6 - dashboard consolidation (12 sections)",
            4.7: "Audit Grade v4.7 - extensive depth, investment fit, $100/mo projections",
            4.8: "Audit Grade v4.8 - executive summary first, dynamic headers, simplified language",
            4.9: "Audit Grade v4.9 - consolidated dashboard (removed redundant sections 15/16)",
            5.0: "Audit Grade v5.0 - visual momentum dashboards, progress bars, pattern alerts",
            5.1: "Audit Grade v5.1 - revenue stickiness, margin waterfall, operating leverage, decision triggers",
            5.2: "Audit Grade v5.2 - cross-report uniqueness, anti-templating, variable formats [RECOMMENDED]",
        }
        return descriptions.get(self.prompt_version, "Unknown")

    def prepare_data(self, ticker: str, fiscal_year: int = None) -> Dict[str, Any]:
        """
        Prepare financial data and metrics for Claude Code to analyze.

        This method fetches FMP data, extracts features, and returns formatted
        metrics context. Used in Claude Code mode where report generation
        happens interactively.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            fiscal_year: Fiscal year to analyze (default: current year)

        Returns:
            Dict with ticker, fiscal_year, metrics_context, and features
        """
        ticker = ticker.upper()
        fiscal_year = fiscal_year or datetime.now().year

        print(f"  Preparing data for {ticker}...")

        # 1. Fetch financial data
        financial_data = get_financial_data(ticker)
        if not financial_data:
            raise ValueError(f"No financial data available for {ticker}")

        # 2. Extract features and trends
        raw_financials = financial_data.get('raw_financials', {})
        currency_info = financial_data.get('currency_info', {})
        features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        # 3. Fetch valuation data for mean reversion analysis (parallel)
        print(f"  Fetching valuation data for {ticker}...")

        def _safe_fetch(fn, *args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                return None

        valuation_data = {}
        with ThreadPoolExecutor(max_workers=7) as executor:
            futures = {
                executor.submit(_safe_fetch, fetch_key_metrics, ticker, limit=5): 'key_metrics_historical',
                executor.submit(_safe_fetch, fetch_key_metrics_ttm, ticker): 'key_metrics_ttm',
                executor.submit(_safe_fetch, fetch_financial_ratios_ttm, ticker): 'financial_ratios_ttm',
                executor.submit(_safe_fetch, fetch_analyst_estimates, ticker, limit=10): 'analyst_estimates',
                executor.submit(_safe_fetch, fetch_earnings, ticker, limit=12): 'earnings_history',
                executor.submit(_safe_fetch, fetch_earnings_calendar_upcoming, ticker): 'earnings_calendar',
                executor.submit(_safe_fetch, fetch_dividends, ticker): 'dividend_history',
            }
            for future in as_completed(futures):
                key = futures[future]
                valuation_data[key] = future.result()

        # 4. Format data for analysis (with multi-currency support and valuation)
        metrics_context = self._format_metrics_for_prompt(
            features, quarterly_trends, raw_financials, currency_info, valuation_data
        )

        print(f"  Data prepared for {ticker}")
        # 5. Cache metrics by category for follow-up agent (async-safe, non-blocking)
        cache_key = financial_data.get('cache_key', f'v3:{ticker}:{fiscal_year}')
        self._batch_write_metrics_cache(
            ticker=ticker,
            quarterly_trends=quarterly_trends,
            currency=currency_info.get('code', 'USD'),
            source_cache_key=cache_key,
            earnings_history=valuation_data.get('earnings_history'),
            dividend_history=valuation_data.get('dividend_history')
        )
        # Track that metrics were cached for this ticker so save_report_sections()
        # doesn't redundantly cache them again
        self._metrics_cached_for = ticker

        return {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'metrics_context': metrics_context,
            'features': features,
            'raw_financials': raw_financials,
            'currency_info': currency_info,
            'valuation_data': valuation_data
        }

    def _batch_write_metrics_cache(
        self,
        ticker: str,
        quarterly_trends: Dict[str, Any],
        currency: str = "USD",
        source_cache_key: str = "",
        earnings_history: list = None,
        dividend_history: list = None
    ) -> None:
        """
        Batch write metrics items to metrics-history-cache table.

        This populates the category-partitioned metrics cache that enables
        the follow-up agent to query specific metric categories efficiently
        (~85% token savings vs querying all metrics).

        Args:
            ticker: Stock symbol
            quarterly_trends: Dict from extract_quarterly_trends()
            currency: Currency code
            source_cache_key: Cache key from financial data cache
            earnings_history: Optional list of FMP earnings records
            dividend_history: Optional list of FMP dividend records
        """
        try:
            # Prepare cache items (up to 9 categories × N quarters)
            items = prepare_metrics_for_cache(
                ticker=ticker,
                quarterly_trends=quarterly_trends,
                currency=currency,
                source_cache_key=source_cache_key,
                earnings_history=earnings_history,
                dividend_history=dividend_history
            )

            if not items:
                print(f"  No metrics to cache for {ticker}")
                return

            # Batch write to DynamoDB (handles 25-item limit internally)
            with self.metrics_history_table.batch_writer() as batch:
                for item in items:
                    # Convert floats to Decimal for DynamoDB
                    item_decimal = json.loads(
                        json.dumps(item),
                        parse_float=Decimal
                    )
                    batch.put_item(Item=item_decimal)

            print(f"  Cached {len(items)} metric items for {ticker} (up to 9 categories × {len(quarterly_trends.get('quarters', []))} quarters)")

        except Exception as e:
            # Non-blocking - log error but don't fail report generation
            print(f"  Warning: Failed to cache metrics for {ticker}: {e}")

    def save_report_sections(
        self,
        ticker: str,
        fiscal_year: int,
        report_content: str,
        ratings: Dict[str, Any],
        features: Dict[str, Any] = None,
        raw_financials: Dict[str, Any] = None,
        currency_info: Dict[str, Any] = None
    ) -> None:
        """
        Save a report as section items to DynamoDB v2 table.
        Also caches metrics to metrics-history table when raw_financials is provided.

        V2 Schema (Single Executive Item pattern):
        - 1 executive item (00_executive): ToC + ratings + 5 executive sections combined
        - 14 detailed section items (06_growth through 19_triggers)
        Total: 15 items per report

        This enables fast initial load (single DynamoDB read for executive)
        and progressive loading of detailed sections.

        Args:
            ticker: Stock symbol
            fiscal_year: Fiscal year
            report_content: Full markdown report content
            ratings: Structured ratings dict (or None to extract from report)
            features: Optional features snapshot to store in metadata
            raw_financials: Optional raw financial data for metrics caching.
                When provided, quarterly trends are extracted and cached to
                the metrics-history table for the follow-up agent.
            currency_info: Optional currency info dict (used with raw_financials)
        """
        ticker = ticker.upper()
        print(f"  Saving report sections for {ticker} (v2 schema) to DynamoDB...")

        # Cache metrics to metrics-history table if raw financials provided
        # and prepare_data() didn't already cache them for this ticker
        if raw_financials and getattr(self, '_metrics_cached_for', None) != ticker:
            try:
                quarterly_trends = extract_quarterly_trends(raw_financials)
                currency = (currency_info or {}).get('code', 'USD')
                cache_key = f'v3:{ticker}:{fiscal_year}'
                self._batch_write_metrics_cache(
                    ticker=ticker,
                    quarterly_trends=quarterly_trends,
                    currency=currency,
                    source_cache_key=cache_key
                )
            except Exception as e:
                print(f"  Warning: Failed to cache metrics for {ticker}: {e}")

        # Extract ratings from raw report content BEFORE parsing sections
        # (parsing strips the JSON block from the last section's content)
        if not ratings:
            ratings = extract_ratings_json(report_content) or {}

        # Parse report into sections (strips JSON block from last section)
        sections = parse_report_sections(report_content, ticker)
        if not sections:
            raise ValueError(f"Failed to parse any sections from report for {ticker}")

        print(f"    Parsed {len(sections)} sections")

        # Delete any existing sections for this ticker (ensures clean state)
        self._delete_existing_sections(ticker)

        # Common fields
        generated_at = datetime.utcnow().isoformat() + 'Z'
        ttl = int((datetime.utcnow() + timedelta(days=120)).timestamp())

        # Get company name for search functionality
        company_name = get_company_name_or_ticker(ticker)

        # Build executive item (00_executive): ToC + ratings + Part 1 sections combined
        executive_item = build_executive_item(
            sections=sections,
            ratings=ratings,
            ticker=ticker,
            generated_at=generated_at,
            model='claude-opus-4-5-20251101',
            prompt_version=f'v{self.prompt_version}',
            fiscal_year=fiscal_year,
            company_name=company_name
        )
        executive_item['ttl'] = ttl

        # Write executive item (convert floats to Decimal for DynamoDB)
        executive_item_decimal = json.loads(json.dumps(executive_item), parse_float=Decimal)
        self.reports_table_v2.put_item(Item=executive_item_decimal)
        exec_sections_count = len(executive_item.get('executive_sections', []))
        print(f"    Saved executive item (00_executive) with {exec_sections_count} sections")

        # Get detailed section items (Part 2 & 3)
        detailed_items = get_detailed_section_items(
            sections=sections,
            ticker=ticker,
            generated_at=generated_at
        )

        # Batch write detailed section items (convert floats to Decimal for DynamoDB)
        with self.reports_table_v2.batch_writer() as batch:
            for item in detailed_items:
                item['ttl'] = ttl
                item_decimal = json.loads(json.dumps(item), parse_float=Decimal)
                batch.put_item(Item=item_decimal)

        print(f"    Saved {len(detailed_items)} detailed section items")
        total_items = 1 + len(detailed_items)
        total_words = executive_item.get('total_word_count', 0)
        print(f"  Report saved for {ticker} (v2 schema): {total_items} items, {total_words} words")

    def _delete_existing_sections(self, ticker: str) -> int:
        """
        Delete all existing section items for a ticker from v2 table.

        Used to ensure clean state before writing new sections.

        Args:
            ticker: Stock symbol

        Returns:
            Number of items deleted
        """
        from boto3.dynamodb.conditions import Key

        # Query all items for this ticker (metadata + all sections)
        response = self.reports_table_v2.query(
            KeyConditionExpression=Key('ticker').eq(ticker.upper())
        )

        items = response.get('Items', [])
        deleted_count = 0

        # Delete each existing item
        with self.reports_table_v2.batch_writer() as batch:
            for item in items:
                batch.delete_item(
                    Key={
                        'ticker': item['ticker'],
                        'section_id': item['section_id']
                    }
                )
                deleted_count += 1

        if deleted_count > 0:
            print(f"    Deleted {deleted_count} existing section(s) for {ticker}")

        return deleted_count

    async def generate_report(
        self,
        ticker: str,
        fiscal_year: int = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Generate investment analysis report for a ticker.

        In API mode: Uses Anthropic API for automated generation.
        In Claude Code mode: Raises error - use prepare_data() and save_report() instead.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')
            fiscal_year: Fiscal year to analyze (default: current year)
            force_refresh: If True, regenerate even if cached

        Returns:
            Dict with report content and ratings
        """
        if not self.use_api:
            raise ValueError(
                "generate_report() requires API mode. "
                "Use prepare_data() and save_report_sections() for Claude Code mode."
            )

        ticker = ticker.upper()
        fiscal_year = fiscal_year or datetime.now().year

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = self._get_cached_report(ticker, fiscal_year)
            if cached:
                print(f"  Using cached report for {ticker}")
                return cached

        print(f"  Generating new report for {ticker}...")

        # 1. Fetch financial data (reuse existing FMP client)
        financial_data = get_financial_data(ticker)
        if not financial_data:
            raise ValueError(f"No financial data available for {ticker}")

        # 2. Extract features and trends (reuse existing extractor)
        raw_financials = financial_data.get('raw_financials', {})
        currency_info = financial_data.get('currency_info', {})
        features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        # 3. Format data for LLM prompt (with multi-currency support)
        metrics_context = self._format_metrics_for_prompt(
            features, quarterly_trends, raw_financials, currency_info
        )

        # 4. Generate report using Opus 4.5 + Thinking
        report = self._generate_with_opus(ticker, fiscal_year, metrics_context)

        # 5. Cache the report
        self._cache_report(ticker, fiscal_year, report, features)

        print(f"  Report generated and cached for {ticker}")
        return report

    async def generate_index_reports(self, index: str, force_refresh: bool = False):
        """
        Generate reports for all tickers in an index.

        Args:
            index: 'DJIA' or 'SP500'
            force_refresh: If True, regenerate all reports
        """
        tickers = get_index_tickers(index)
        print(f"Generating {len(tickers)} reports for {index}...")

        success_count = 0
        error_count = 0

        for i, ticker in enumerate(tickers, 1):
            try:
                print(f"[{i}/{len(tickers)}] {ticker}", end="")
                await self.generate_report(ticker, force_refresh=force_refresh)
                success_count += 1
                print(" ✓")
            except Exception as e:
                error_count += 1
                print(f" ✗ Failed: {e}")

        print(f"\nCompleted: {success_count} succeeded, {error_count} failed")

    def _get_latest_earnings_info(self, raw_financials: dict) -> dict:
        """
        Extract the latest earnings period information from raw financials.

        Compares dates across income_statement, balance_sheet, and cash_flow
        to find the most recent data point.

        Returns:
            dict with keys: date, period, fiscal_year, formatted_date
            Returns empty dict if no data available
        """
        from datetime import datetime

        # Get first entry from each statement (most recent)
        income = raw_financials.get('income_statement', [])
        balance = raw_financials.get('balance_sheet', [])
        cashflow = raw_financials.get('cash_flow', [])

        # Collect candidates with their dates
        candidates = []
        if income:
            candidates.append(('income', income[0]))
        if balance:
            candidates.append(('balance', balance[0]))
        if cashflow:
            candidates.append(('cashflow', cashflow[0]))

        if not candidates:
            return {}

        # Find the most recent entry by parsing date strings
        def parse_date(entry):
            date_str = entry.get('date', '')
            try:
                return datetime.strptime(date_str, '%Y-%m-%d')
            except (ValueError, TypeError):
                return datetime.min

        # Sort by date descending, prefer income_statement as tiebreaker
        priority = {'income': 0, 'balance': 1, 'cashflow': 2}
        candidates.sort(key=lambda x: (-parse_date(x[1]).timestamp(), priority[x[0]]))

        latest = candidates[0][1]

        # Extract fields - IMPORTANT: Use fiscalYear from FMP, not calendar year
        # FMP's fiscalYear field correctly handles non-calendar fiscal years
        # (e.g., AAPL ends Sep, OKTA ends Jan, MSFT ends Jun)
        date_str = latest.get('date', '')
        period = latest.get('period', '')
        fiscal_year = latest.get('fiscalYear') or latest.get('calendarYear') or ''

        # Format the date in plain English (e.g., "Oct 31, 2024")
        formatted_date = ''
        if date_str:
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                formatted_date = dt.strftime('%b %d, %Y')
            except ValueError:
                formatted_date = date_str

        # If no fiscal year, extract from date
        if not fiscal_year and date_str:
            fiscal_year = date_str[:4]

        return {
            'date': date_str,
            'period': period,
            'fiscal_year': fiscal_year,
            'formatted_date': formatted_date
        }

    def _aggregate_annual_data(
        self,
        income_statements: list,
        balance_sheets: list,
        cash_flows: list
    ) -> dict:
        """
        Aggregate quarterly data into true annual figures.

        Flow metrics (revenue, income, cash flows) are SUMMED across all quarters
        in each fiscal year. Point-in-time metrics (debt, cash, equity) use the
        most recent quarter's values (typically Q4/year-end).

        Args:
            income_statements: List of quarterly income statements (most recent first)
            balance_sheets: List of quarterly balance sheets (most recent first)
            cash_flows: List of quarterly cash flow statements (most recent first)

        Returns:
            Dict keyed by fiscal year with aggregated 'income', 'balance', 'cashflow' data
        """
        # Flow metrics that should be summed across quarters
        INCOME_FLOW_METRICS = [
            'revenue', 'netIncome', 'grossProfit', 'operatingIncome',
            'costOfRevenue', 'operatingExpenses', 'interestExpense',
            'incomeBeforeTax', 'incomeTaxExpense', 'ebitda', 'ebitdaratio'
        ]
        CASHFLOW_FLOW_METRICS = [
            'operatingCashFlow', 'freeCashFlow', 'capitalExpenditure',
            'commonDividendsPaid', 'commonStockRepurchased', 'netCashProvidedByInvestingActivities',
            'netCashProvidedByFinancingActivities', 'netChangeInCash'
        ]

        # Group quarters by fiscal year
        quarters_by_year = {}

        for stmt in income_statements[:20]:
            stmt = decimal_to_float(stmt)
            year = stmt.get('fiscalYear') or stmt.get('calendarYear') or (stmt.get('date', 'Unknown')[:4] if stmt.get('date') else 'Unknown')
            if year == 'Unknown':
                continue
            if year not in quarters_by_year:
                quarters_by_year[year] = {'income': [], 'balance': [], 'cashflow': []}
            quarters_by_year[year]['income'].append(stmt)

        for bs in balance_sheets[:20]:
            bs = decimal_to_float(bs)
            year = bs.get('fiscalYear') or bs.get('calendarYear') or (bs.get('date', 'Unknown')[:4] if bs.get('date') else 'Unknown')
            if year in quarters_by_year:
                quarters_by_year[year]['balance'].append(bs)

        for cf in cash_flows[:20]:
            cf = decimal_to_float(cf)
            year = cf.get('fiscalYear') or cf.get('calendarYear') or (cf.get('date', 'Unknown')[:4] if cf.get('date') else 'Unknown')
            if year in quarters_by_year:
                quarters_by_year[year]['cashflow'].append(cf)

        # Build aggregated annual data
        annual_data = {}

        for year, quarters in quarters_by_year.items():
            # Sum income statement flow metrics
            aggregated_income = {}
            if quarters['income']:
                # Start with first quarter as template for non-flow fields
                aggregated_income = dict(quarters['income'][0])
                # Sum flow metrics across all quarters
                for metric in INCOME_FLOW_METRICS:
                    total = sum(
                        q.get(metric, 0) or 0
                        for q in quarters['income']
                    )
                    aggregated_income[metric] = total
                # EPS needs special handling - sum quarterly EPS for annual
                aggregated_income['eps'] = sum(
                    q.get('eps', 0) or 0
                    for q in quarters['income']
                )

            # Sum cash flow statement flow metrics
            aggregated_cashflow = {}
            if quarters['cashflow']:
                aggregated_cashflow = dict(quarters['cashflow'][0])
                for metric in CASHFLOW_FLOW_METRICS:
                    total = sum(
                        q.get(metric, 0) or 0
                        for q in quarters['cashflow']
                    )
                    aggregated_cashflow[metric] = total

            # Balance sheet uses most recent quarter (point-in-time, not summed)
            # Quarters are sorted most recent first, so [0] is the latest
            aggregated_balance = quarters['balance'][0] if quarters['balance'] else {}

            annual_data[year] = {
                'income': aggregated_income,
                'balance': aggregated_balance,
                'cashflow': aggregated_cashflow,
                'quarters_count': len(quarters['income'])  # Track how many quarters we have
            }

        return annual_data

    def _calculate_ttm_metrics(
        self,
        income_statements: list,
        balance_sheets: list,
        cash_flows: list
    ) -> dict:
        """
        Calculate Trailing Twelve Months (TTM) metrics from most recent 4 quarters.

        TTM provides a rolling 12-month view that's more accurate than incomplete
        fiscal years for current performance assessment.

        Args:
            income_statements: List of quarterly income statements (most recent first)
            balance_sheets: List of quarterly balance sheets (most recent first)
            cash_flows: List of quarterly cash flow statements (most recent first)

        Returns:
            Dict with TTM aggregated metrics, or empty dict if insufficient data
        """
        ttm = {}

        # Need at least 4 quarters of data for TTM
        if len(income_statements) < 4 or len(cash_flows) < 4:
            return ttm

        # Convert Decimals to floats
        inc_stmts = [decimal_to_float(stmt) for stmt in income_statements[:4]]
        cf_stmts = [decimal_to_float(cf) for cf in cash_flows[:4]]

        # Income statement flow metrics (summed)
        ttm['revenue'] = sum(stmt.get('revenue', 0) or 0 for stmt in inc_stmts)
        ttm['netIncome'] = sum(stmt.get('netIncome', 0) or 0 for stmt in inc_stmts)
        ttm['grossProfit'] = sum(stmt.get('grossProfit', 0) or 0 for stmt in inc_stmts)
        ttm['operatingIncome'] = sum(stmt.get('operatingIncome', 0) or 0 for stmt in inc_stmts)
        ttm['eps'] = sum(stmt.get('eps', 0) or 0 for stmt in inc_stmts)

        # Cash flow metrics (summed)
        ttm['operatingCashFlow'] = sum(cf.get('operatingCashFlow', 0) or 0 for cf in cf_stmts)
        ttm['freeCashFlow'] = sum(cf.get('freeCashFlow', 0) or 0 for cf in cf_stmts)
        ttm['capitalExpenditure'] = sum(cf.get('capitalExpenditure', 0) or 0 for cf in cf_stmts)
        ttm['commonDividendsPaid'] = sum(cf.get('commonDividendsPaid', 0) or 0 for cf in cf_stmts)
        ttm['commonStockRepurchased'] = sum(cf.get('commonStockRepurchased', 0) or 0 for cf in cf_stmts)

        # Calculate derived ratios
        if ttm['revenue'] > 0:
            ttm['grossMargin'] = round(ttm['grossProfit'] / ttm['revenue'] * 100, 1)
            ttm['netMargin'] = round(ttm['netIncome'] / ttm['revenue'] * 100, 1)
            ttm['fcfMargin'] = round(ttm['freeCashFlow'] / ttm['revenue'] * 100, 1)

        if ttm['netIncome'] > 0:
            ttm['ocfToNi'] = round(ttm['operatingCashFlow'] / ttm['netIncome'], 2)

        return ttm

    def _format_metrics_for_prompt(
        self,
        features: dict,
        trends: dict,
        raw_financials: dict,
        currency_info: dict = None,
        valuation_data: dict = None
    ) -> str:
        """
        Format financial metrics as structured text for LLM analysis.

        Includes 5-year trend tables and all key metrics across
        debt, cashflow, growth, and valuation domains. Supports multi-currency
        display with USD equivalents for non-USD companies.
        """
        from src.utils.currency import CurrencyFormatter

        # Convert any Decimals to floats for clean formatting
        features = decimal_to_float(features)
        trends = decimal_to_float(trends)

        # Initialize currency formatter
        currency_info = currency_info or {}
        currency_code = currency_info.get('code', 'USD')
        usd_rate = currency_info.get('usd_rate', 1.0)
        fmt = CurrencyFormatter(currency_code, usd_rate)

        output = []

        # Add currency note if non-USD
        if currency_code != 'USD':
            output.append("## CURRENCY NOTE")
            output.append(fmt.currency_note)
            output.append("")

        # Add latest earnings date header
        earnings_info = self._get_latest_earnings_info(raw_financials)
        if earnings_info.get('formatted_date'):
            output.append("## DATA FRESHNESS")
            # Build header string based on available fields
            if earnings_info.get('period') and earnings_info['period'] != 'FY':
                header = f"Data through {earnings_info['period']} FY{earnings_info['fiscal_year']} ending {earnings_info['formatted_date']}"
            elif earnings_info.get('fiscal_year'):
                header = f"Data through FY{earnings_info['fiscal_year']} ending {earnings_info['formatted_date']}"
            else:
                header = f"Data through {earnings_info['formatted_date']}"
            output.append(header)
            output.append("")

        # === 5-YEAR TREND TABLES ===
        output.append("## 5-YEAR TREND DATA (Annual Summary)")
        output.append("Use this data to identify trajectories - improving, stable, or deteriorating.\n")

        # Build annual summary by aggregating quarterly data
        # Flow metrics (revenue, income, cash flows) are summed across quarters
        # Point-in-time metrics (debt, cash, equity) use year-end values
        income_statements = raw_financials.get('income_statement', [])
        balance_sheets = raw_financials.get('balance_sheet', [])
        cash_flows = raw_financials.get('cash_flow', [])

        annual_data = self._aggregate_annual_data(
            income_statements, balance_sheets, cash_flows
        )

        # Calculate TTM metrics for rolling 12-month view
        ttm_metrics = self._calculate_ttm_metrics(
            income_statements, balance_sheets, cash_flows
        )

        # Sort years descending (most recent first)
        sorted_years = sorted(annual_data.keys(), reverse=True)[:5]

        # Revenue & Profit Trend Table
        output.append("### Revenue & Profitability Trend")
        output.append("| Year | Revenue | Net Income | Gross Margin | Net Margin | EPS |")
        output.append("|------|---------|------------|--------------|------------|-----|")

        # Add TTM row first (most current rolling 12-month data)
        if ttm_metrics:
            ttm_rev = ttm_metrics.get('revenue', 0)
            ttm_ni = ttm_metrics.get('netIncome', 0)
            ttm_gm = ttm_metrics.get('grossMargin', 0)
            ttm_nm = ttm_metrics.get('netMargin', 0)
            ttm_eps = ttm_metrics.get('eps', 0)
            output.append(f"| **TTM** | {fmt.money(ttm_rev)} | {fmt.money(ttm_ni)} | {ttm_gm}% | {ttm_nm}% | {fmt.eps(ttm_eps)} |")

        for year in sorted_years:
            data = annual_data.get(year, {})
            inc = data.get('income', {})
            quarters_count = data.get('quarters_count', 4)
            rev = inc.get('revenue', 0)
            ni = inc.get('netIncome', 0)
            gp = inc.get('grossProfit', 0)
            eps = inc.get('eps', 0)
            gm = round(gp / rev * 100, 1) if rev else 0
            nm = round(ni / rev * 100, 1) if rev else 0
            # Mark incomplete years with YTD suffix
            year_label = f"{year}" if quarters_count >= 4 else f"{year} (YTD)"
            output.append(f"| {year_label} | {fmt.money(rev)} | {fmt.money(ni)} | {gm}% | {nm}% | {fmt.eps(eps)} |")

        # Cash Flow Trend Table (Enhanced)
        output.append("\n### Cash Flow Trend")
        output.append("| Year | Operating CF | Free Cash Flow | FCF Margin | CapEx | Dividends | Buybacks | OCF/NI |")
        output.append("|------|--------------|----------------|------------|-------|-----------|----------|--------|")

        # Add TTM row first (most current rolling 12-month data)
        if ttm_metrics:
            ttm_ocf = ttm_metrics.get('operatingCashFlow', 0)
            ttm_fcf = ttm_metrics.get('freeCashFlow', 0)
            ttm_capex = abs(ttm_metrics.get('capitalExpenditure', 0))
            ttm_dividends = abs(ttm_metrics.get('commonDividendsPaid', 0))
            ttm_buybacks = abs(ttm_metrics.get('commonStockRepurchased', 0))
            ttm_fcf_margin = ttm_metrics.get('fcfMargin', 0)
            ttm_ocf_ni = ttm_metrics.get('ocfToNi', 0)
            output.append(f"| **TTM** | {fmt.money(ttm_ocf)} | {fmt.money(ttm_fcf)} | {ttm_fcf_margin}% | {fmt.money(ttm_capex)} | {fmt.money(ttm_dividends)} | {fmt.money(ttm_buybacks)} | {ttm_ocf_ni}x |")

        for year in sorted_years:
            data = annual_data.get(year, {})
            cf = data.get('cashflow', {})
            inc = data.get('income', {})
            quarters_count = data.get('quarters_count', 4)
            ocf = cf.get('operatingCashFlow', 0)
            fcf = cf.get('freeCashFlow', 0)
            capex = abs(cf.get('capitalExpenditure', 0))
            dividends = abs(cf.get('commonDividendsPaid', 0))
            buybacks = abs(cf.get('commonStockRepurchased', 0))
            rev = inc.get('revenue', 1)
            ni = inc.get('netIncome', 1)
            fcf_margin = round(fcf / rev * 100, 1) if rev else 0
            ocf_ni = round(ocf / ni, 2) if ni and ni > 0 else 0
            # Mark incomplete years with YTD suffix
            year_label = f"{year}" if quarters_count >= 4 else f"{year} (YTD)"
            output.append(f"| {year_label} | {fmt.money(ocf)} | {fmt.money(fcf)} | {fcf_margin}% | {fmt.money(capex)} | {fmt.money(dividends)} | {fmt.money(buybacks)} | {ocf_ni}x |")

        # Balance Sheet Trend Table (Enhanced)
        # Note: "Liquidity" includes cash + short-term investments for accurate fortress assessment
        output.append("\n### Balance Sheet Trend")
        output.append("| Year | Total Debt | Liquidity* | Net Debt/Cash | Equity | Debt/Equity | Debt/Assets | Current Ratio |")
        output.append("|------|------------|------------|---------------|--------|-------------|-------------|---------------|")
        for year in sorted_years:
            data = annual_data.get(year, {})
            bs = data.get('balance', {})
            inc = data.get('income', {})
            debt = bs.get('totalDebt', 0)
            liquidity = get_total_liquidity(bs)  # Cash + short-term investments
            equity = bs.get('totalStockholdersEquity', 1)
            assets = bs.get('totalAssets', 1)
            current_assets = bs.get('totalCurrentAssets', 0)
            current_liab = bs.get('totalCurrentLiabilities', 1)
            net_debt = debt - liquidity
            # Format net debt: positive = debt, negative = net cash position
            if net_debt < 0:
                net_debt_display = f"(Cash: {fmt.money(abs(net_debt))})"
            else:
                net_debt_display = fmt.money(net_debt)
            de_ratio = round(debt / equity, 2) if equity else 0
            da_ratio = round(debt / assets, 2) if assets else 0
            current_ratio = round(current_assets / current_liab, 2) if current_liab else 0
            output.append(f"| {year} | {fmt.money(debt)} | {fmt.money(liquidity)} | {net_debt_display} | {fmt.money(equity)} | {de_ratio}x | {da_ratio}x | {current_ratio}x |")
        output.append("*Liquidity = Cash + Short-term Investments. Negative Net Debt shown as (Cash: $X) indicates net cash position.")

        # ============================================================
        # MOMENTUM INDICATORS (Temporal Derivatives)
        # ============================================================
        output.append("\n## MOMENTUM INDICATORS")
        output.append("Use these to determine if trends are ACCELERATING or DECELERATING\n")

        debt_current = features.get('debt', {}).get('current', {})
        cashflow_current = features.get('cashflow', {}).get('current', {})
        growth_current = features.get('growth', {}).get('current', {})

        # Profitability Momentum
        output.append("### Profitability Momentum Signals")
        output.append(f"- `operating_margin_velocity_qoq` = {growth_current.get('operating_margin_velocity_qoq', 0):.2f}")
        output.append(f"- `operating_margin_acceleration` = {growth_current.get('operating_margin_acceleration', 0):.2f}")
        output.append(f"- `is_margin_expanding` = {1 if growth_current.get('is_margin_expanding') else 0}")
        output.append(f"- `margin_momentum_positive` = {1 if growth_current.get('margin_momentum_positive') else 0}")

        # Cash Flow Momentum
        output.append("\n### Cash Flow Momentum Signals")
        output.append(f"- `fcf_margin_velocity_qoq` = {cashflow_current.get('fcf_margin_velocity_qoq', 0):.2f}")
        output.append(f"- `fcf_margin_acceleration` = {cashflow_current.get('fcf_margin_acceleration', 0):.2f}")
        output.append(f"- `fcf_velocity_qoq` = {cashflow_current.get('fcf_velocity_qoq', 0):.2f}")
        output.append(f"- `ocf_velocity_qoq` = {cashflow_current.get('ocf_velocity_qoq', 0):.2f}")
        # Add TTM FCF context (quarterly vs rolling 12-month for stability)
        if ttm_metrics:
            quarterly_fcf = cash_flows[0].get('freeCashFlow', 0) if cash_flows else 0
            ttm_fcf = ttm_metrics.get('freeCashFlow', 0)
            output.append(f"- `fcf_quarterly` = {fmt.money(quarterly_fcf)} | `fcf_ttm` = {fmt.money(ttm_fcf)}")

        # Debt Momentum
        output.append("\n### Debt Momentum Signals")
        output.append(f"- `debt_to_equity_velocity_qoq` = {debt_current.get('debt_to_equity_velocity_qoq', 0):.2f}")
        output.append(f"- `debt_to_equity_acceleration_qoq` = {debt_current.get('debt_to_equity_acceleration_qoq', 0):.2f}")
        output.append(f"- `is_deleveraging` = {1 if debt_current.get('is_deleveraging') else 0}")
        output.append(f"- `net_debt_velocity_qoq` = {debt_current.get('net_debt_velocity_qoq', 0):.2f}")

        # Growth Momentum
        output.append("\n### Growth Momentum Signals")
        output.append(f"- `revenue_growth_velocity` = {growth_current.get('revenue_growth_velocity', 0):.2f}")
        output.append(f"- `revenue_growth_acceleration` = {growth_current.get('revenue_growth_acceleration', 0):.2f}")
        output.append(f"- `is_growth_accelerating` = {1 if growth_current.get('is_growth_accelerating') else 0}")
        output.append(f"- `growth_deceleration_warning` = {1 if growth_current.get('growth_deceleration_warning') else 0}")

        # === QUARTERLY MOMENTUM ANALYSIS ===
        output.append("\n## QUARTERLY MOMENTUM ANALYSIS (Last 8 Quarters)")
        output.append("**CRITICAL: Review for recent trend changes**\n")

        # Get momentum metrics
        momentum = self._calculate_momentum_metrics(income_statements)
        margin_check = self._check_margin_compression(income_statements)
        debt_trends = self._check_debt_trends(balance_sheets, income_statements)
        cashflow_trends = self._check_cashflow_trends(cash_flows, income_statements)

        # Revenue & Growth Trajectory Table
        output.append("### Revenue & Growth Trajectory")
        output.append("| Quarter | Revenue | QoQ Change | YoY Growth | Trend |")
        output.append("|---------|---------|------------|------------|-------|")
        for q in momentum['quarterly_data'][:8]:
            rev = q['revenue']
            qoq = f"{q['qoq_change']:+.1f}%" if q['qoq_change'] is not None else "N/A"
            yoy = f"{q['yoy_growth']:+.1f}%" if q['yoy_growth'] is not None else "N/A"
            output.append(f"| {q['period']} | {fmt.money(rev)} | {qoq} | {yoy} | {q['trend']} |")

        # Growth Trend Alerts
        output.append("\n### Growth Trend Alerts")
        output.append("| Check | Status | Details |")
        output.append("|-------|--------|---------|")

        # Growth momentum check
        growth_status = "🚨" if momentum['is_decelerating'] else "✅"
        growth_detail = f"{momentum['peak_growth_rate']}% → {momentum['current_growth_rate']}%" if momentum['current_growth_rate'] else "N/A"
        if momentum['is_decelerating']:
            growth_detail += f" (-{momentum['deceleration_magnitude']}pp)"
        output.append(f"| Growth Momentum | {growth_status} | {growth_detail} |")

        # Sequential revenue check
        seq_status = "🚨" if momentum['consecutive_qoq_declines'] >= 2 else "✅"
        seq_detail = f"{'Declined' if momentum['consecutive_qoq_declines'] > 0 else 'Grew'} {momentum['consecutive_qoq_declines']} consecutive quarters"
        output.append(f"| Sequential Revenue | {seq_status} | {seq_detail} |")

        # Margin trend check
        margin_status = "🚨" if margin_check['is_compressing'] else "✅"
        if margin_check['gross_margin_change'] is not None:
            margin_detail = f"{margin_check['gross_margin_yoy']}% → {margin_check['gross_margin_current']}% ({margin_check['gross_margin_change']:+.1f}pp)"
        else:
            margin_detail = "N/A"
        output.append(f"| Margin Trend | {margin_status} | {margin_detail} |")

        # Add warning summary
        all_warnings = momentum['warnings'] + margin_check['warnings']
        if all_warnings:
            output.append("\n**⚠️ GROWTH ALERTS:**")
            for warning in all_warnings:
                output.append(f"- {warning}")

        # === DEBT HEALTH TRAJECTORY (8 Quarters) ===
        output.append("\n### Debt Health Trajectory (Last 8 Quarters)")
        output.append("| Quarter | Total Debt | Liquidity* | Net Debt | Debt/Equity | Debt/Assets | Interest Cov | Trend |")
        output.append("|---------|------------|------------|----------|-------------|-------------|--------------|-------|")
        for q in debt_trends['quarterly_data'][:8]:
            output.append(
                f"| {q['period']} | {fmt.money(q['total_debt'])} | {fmt.money(q.get('liquidity', 0))} | "
                f"{fmt.money(q['net_debt'])} | {q['debt_equity']:.2f}x | {q.get('debt_assets', 0):.2f}x | "
                f"{q['interest_coverage']:.1f}x | {q['trend']} |"
            )
        output.append("*Liquidity = Cash + Short-term Investments")

        output.append("\n### Debt Trend Alerts")
        output.append("| Check | Status | Details |")
        output.append("|-------|--------|---------|")

        de_status = "🚨" if debt_trends['debt_equity_trend'] == 'increasing' else "✅"
        output.append(f"| Debt/Equity Trend | {de_status} | {debt_trends['debt_equity_trend']} |")

        cov_status = "🚨" if debt_trends['interest_coverage_trend'] == 'weakening' else "✅"
        output.append(f"| Interest Coverage | {cov_status} | {debt_trends['interest_coverage_trend']} |")

        nd_status = "🚨" if debt_trends['net_debt_trend'] == 'accumulating' else "✅"
        output.append(f"| Net Debt Trajectory | {nd_status} | {debt_trends['net_debt_trend']} |")

        if debt_trends['warnings']:
            output.append("\n**⚠️ DEBT ALERTS:**")
            for warning in debt_trends['warnings']:
                output.append(f"- {warning}")

        # === CASH FLOW TRAJECTORY (8 Quarters) ===
        output.append("\n### Cash Flow Trajectory (Last 8 Quarters)")
        output.append("| Quarter | Operating CF | Free Cash Flow | FCF Margin | CapEx | Dividends | OCF/NI | Trend |")
        output.append("|---------|--------------|----------------|------------|-------|-----------|--------|-------|")
        for q in cashflow_trends['quarterly_data'][:8]:
            output.append(
                f"| {q['period']} | {fmt.money(q['operating_cf'])} | {fmt.money(q['free_cash_flow'])} | "
                f"{q['fcf_margin']:.1f}% | {fmt.money(q.get('capex', 0))} | {fmt.money(q.get('dividends', 0))} | "
                f"{q.get('ocf_ni_ratio', 0):.2f}x | {q['trend']} |"
            )

        output.append("\n### Cash Flow Trend Alerts")
        output.append("| Check | Status | Details |")
        output.append("|-------|--------|---------|")

        fcf_status = "🚨" if cashflow_trends['fcf_trend'] == 'deteriorating' else "✅"
        output.append(f"| FCF Trajectory | {fcf_status} | {cashflow_trends['fcf_trend']} |")

        neg_fcf_status = "🚨" if cashflow_trends['consecutive_negative_fcf'] >= 2 else "✅"
        output.append(f"| Consecutive Negative FCF | {neg_fcf_status} | {cashflow_trends['consecutive_negative_fcf']} quarters |")

        # Use TTM ratio for stability (quarterly can be volatile)
        ocf_ttm = cashflow_trends.get('ocf_ni_ratio_ttm') or cashflow_trends.get('ocf_ni_ratio')
        ocf_status = "🚨" if ocf_ttm and ocf_ttm < 0.8 else "✅"
        ocf_detail = f"{ocf_ttm}x (TTM)" if ocf_ttm else "N/A"
        output.append(f"| OCF to Net Income | {ocf_status} | {ocf_detail} |")

        if cashflow_trends['warnings']:
            output.append("\n**⚠️ CASH FLOW ALERTS:**")
            for warning in cashflow_trends['warnings']:
                output.append(f"- {warning}")

        # === CURRENT QUARTER SNAPSHOT ===
        output.append("\n## CURRENT QUARTER SNAPSHOT (Most Recent)")

        # Get most recent data
        latest_inc = decimal_to_float(income_statements[0]) if income_statements else {}
        latest_bs = decimal_to_float(balance_sheets[0]) if balance_sheets else {}
        latest_cf = decimal_to_float(cash_flows[0]) if cash_flows else {}

        output.append(f"Period: {latest_inc.get('date', 'N/A')}")
        output.append(f"Revenue: {fmt.money(latest_inc.get('revenue', 0))}")
        output.append(f"Net Income: {fmt.money(latest_inc.get('netIncome', 0))}")
        output.append(f"EPS: {fmt.eps(latest_inc.get('eps', 0))}")
        output.append(f"Free Cash Flow: {fmt.money(latest_cf.get('freeCashFlow', 0))}")
        output.append(f"Total Debt: {fmt.money(latest_bs.get('totalDebt', 0))}")
        # Total liquidity includes cash AND short-term investments (T-bills, money market, etc.)
        total_liquidity = get_total_liquidity(latest_bs)
        cash_only = latest_bs.get('cashAndCashEquivalents', 0) or 0
        short_term = latest_bs.get('shortTermInvestments', 0) or 0
        if short_term > 0:
            output.append(f"Total Liquidity: {fmt.money(total_liquidity)} (Cash: {fmt.money(cash_only)} + ST Investments: {fmt.money(short_term)})")
        else:
            output.append(f"Cash Position: {fmt.money(total_liquidity)}")

        # === KEY RATIOS ===
        output.append("\n## KEY FINANCIAL RATIOS")
        debt_features = features.get('debt', {})
        cashflow_features = features.get('cashflow', {})
        growth_features = features.get('growth', {})

        output.append("\n### Debt & Leverage")
        output.append(f"  Debt-to-Equity Ratio: {debt_features.get('debt_to_equity', 'N/A')}")
        output.append(f"  Debt-to-Assets: {debt_features.get('debt_to_assets', 'N/A')}")
        output.append(f"  Interest Coverage: {debt_features.get('interest_coverage', 'N/A')}x")
        output.append(f"  Current Ratio: {debt_features.get('current_ratio', 'N/A')}")

        output.append("\n### Cash Flow Quality")
        if isinstance(cashflow_features.get('free_cash_flow'), (int, float)):
            output.append(f"  Free Cash Flow: {fmt.money(cashflow_features.get('free_cash_flow', 0))}")
        output.append(f"  FCF Margin: {cashflow_features.get('fcf_margin', 'N/A')}%")
        if isinstance(cashflow_features.get('operating_cash_flow'), (int, float)):
            output.append(f"  Operating Cash Flow: {fmt.money(cashflow_features.get('operating_cash_flow', 0))}")

        output.append("\n### Growth & Profitability")
        output.append(f"  Revenue Growth (YoY): {growth_features.get('revenue_growth_yoy', 'N/A')}%")
        output.append(f"  Gross Margin: {growth_features.get('gross_margin', 'N/A')}%")
        output.append(f"  Operating Margin: {growth_features.get('operating_margin', 'N/A')}%")
        output.append(f"  Net Margin: {growth_features.get('net_margin', 'N/A')}%")

        # === EARNINGS QUALITY ANALYSIS (NEW FOR AUDIT) ===
        output.append("\n## EARNINGS QUALITY ANALYSIS")
        output.append("**Shows the difference between reported (GAAP) earnings and 'adjusted' earnings**\n")

        # Get latest quarterly data for earnings quality metrics
        if trends.get('gaap_net_income') and len(trends['gaap_net_income']) > 0:
            # Use most recent 4 quarters (annualized) for annual comparison
            recent_quarters = min(4, len(trends['gaap_net_income']))

            # Sum last 4 quarters for annual figures
            annual_gaap_ni = sum(trends['gaap_net_income'][:recent_quarters]) if trends.get('gaap_net_income') else 0
            annual_sbc = sum(trends['sbc_estimate'][:recent_quarters]) if trends.get('sbc_estimate') else 0
            annual_d_and_a = sum(trends['d_and_a'][:recent_quarters]) if trends.get('d_and_a') else 0
            annual_adjusted = annual_gaap_ni + annual_sbc + annual_d_and_a

            # Latest quarterly data for SBC metrics
            latest_revenue = trends.get('revenue', [0])[0] if trends.get('revenue') else 0
            latest_sbc = trends.get('sbc_estimate', [0])[0] if trends.get('sbc_estimate') else 0
            sbc_to_rev_pct = round(latest_sbc / latest_revenue * 100, 1) if latest_revenue > 0 else 0

            # GAAP vs Adjusted Bridge Table
            output.append("### GAAP to Adjusted Earnings Bridge (TTM)")
            output.append("| Step | Description | Amount |")
            output.append("|------|-------------|--------|")
            output.append(f"| 1 | GAAP Net Income | {fmt.money(annual_gaap_ni)} |")
            output.append(f"| 2 | + Stock-Based Compensation* | {fmt.money(annual_sbc)} |")
            output.append(f"| 3 | + Depreciation & Amortization | {fmt.money(annual_d_and_a)} |")
            output.append(f"| **Total** | **Adjusted Earnings** | **{fmt.money(annual_adjusted)}** |")
            output.append("")
            output.append("*SBC estimate from cash flow non-cash adjustments")

            # Calculate gap percentage
            if annual_gaap_ni != 0:
                gap_pct = round((annual_adjusted - annual_gaap_ni) / abs(annual_gaap_ni) * 100, 1)
                if gap_pct > 100:
                    output.append(f"\n⚠️ **WARNING**: Adjusted earnings are {gap_pct}% higher than GAAP - large gap indicates heavy use of stock compensation or non-cash charges")
                elif gap_pct > 50:
                    output.append(f"\n**Note**: Adjusted earnings exceed GAAP by {gap_pct}%")

        # ── EARNINGS HISTORY (v5.2) ──────────────────────────────────
        if valuation_data and valuation_data.get('earnings_history'):
            # Filter to only past quarters with actual results
            earnings = [e for e in valuation_data['earnings_history'] if e.get('epsActual') is not None]
            output.append("\n## EARNINGS HISTORY (Last 12 Quarters)")
            output.append("| Date | EPS Estimated | EPS Actual | EPS Surprise % | Revenue Estimated | Revenue Actual | Revenue Surprise % |")
            output.append("|------|---------------|------------|----------------|-------------------|----------------|--------------------|")
            beat_count = 0
            total_count = 0
            eps_surprises = []
            rev_beat_count = 0
            rev_total_count = 0
            for e in earnings[:12]:
                date = e.get('date', 'N/A')
                eps_est = e.get('epsEstimated')
                eps_act = e.get('epsActual')
                rev_est = e.get('revenueEstimated')
                rev_act = e.get('revenueActual')

                # Calculate surprise percentages
                eps_surprise = ''
                if eps_est and eps_act and eps_est != 0:
                    try:
                        eps_surprise_val = ((float(eps_act) - float(eps_est)) / abs(float(eps_est))) * 100
                        eps_surprise = f"{eps_surprise_val:+.1f}%"
                        eps_surprises.append({'date': date, 'val': eps_surprise_val})
                        if eps_surprise_val > 1:
                            beat_count += 1
                        total_count += 1
                    except (ValueError, ZeroDivisionError):
                        eps_surprise = 'N/A'
                        total_count += 1

                rev_surprise = ''
                if rev_est and rev_act and rev_est != 0:
                    try:
                        rev_surprise_val = ((float(rev_act) - float(rev_est)) / abs(float(rev_est))) * 100
                        rev_surprise = f"{rev_surprise_val:+.1f}%"
                        rev_total_count += 1
                        if rev_surprise_val > 0:
                            rev_beat_count += 1
                    except (ValueError, ZeroDivisionError):
                        rev_surprise = 'N/A'

                def fmt_val(v, is_revenue=False):
                    if v is None:
                        return 'N/A'
                    try:
                        v = float(v)
                        if is_revenue:
                            if abs(v) >= 1e9:
                                return f"${v/1e9:.1f}B"
                            elif abs(v) >= 1e6:
                                return f"${v/1e6:.0f}M"
                            else:
                                return f"${v:,.0f}"
                        else:
                            return f"${v:.2f}"
                    except (ValueError, TypeError):
                        return str(v)

                output.append(
                    f"| {date} | {fmt_val(eps_est)} | {fmt_val(eps_act)} | {eps_surprise} | {fmt_val(rev_est, True)} | {fmt_val(rev_act, True)} | {rev_surprise} |"
                )

            # Beat rate and summary stats
            if total_count > 0:
                beat_rate = (beat_count / total_count) * 100
                output.append(f"\n**EPS Beat Rate:** {beat_count}/{total_count} quarters ({beat_rate:.0f}%)")

                if eps_surprises:
                    avg_surprise = sum(s['val'] for s in eps_surprises) / len(eps_surprises)
                    largest_beat = max(eps_surprises, key=lambda s: s['val'])
                    largest_miss = min(eps_surprises, key=lambda s: s['val'])
                    output.append(f"**Avg EPS Surprise:** {avg_surprise:+.1f}%")
                    output.append(f"**Largest Beat:** {largest_beat['val']:+.1f}% ({largest_beat['date']})")
                    output.append(f"**Largest Miss:** {largest_miss['val']:+.1f}% ({largest_miss['date']})")

                    # Trend direction: compare avg of first half vs second half
                    if len(eps_surprises) >= 4:
                        mid = len(eps_surprises) // 2
                        recent_avg = sum(s['val'] for s in eps_surprises[:mid]) / mid
                        older_avg = sum(s['val'] for s in eps_surprises[mid:]) / (len(eps_surprises) - mid)
                        if recent_avg > older_avg + 2:
                            trend = "Accelerating (recent surprises larger)"
                        elif recent_avg < older_avg - 2:
                            trend = "Decelerating (recent surprises smaller)"
                        else:
                            trend = "Stable"
                        output.append(f"**Surprise Trend:** {trend}")

                if rev_total_count > 0:
                    rev_beat_rate = (rev_beat_count / rev_total_count) * 100
                    output.append(f"**Revenue Beat Rate:** {rev_beat_count}/{rev_total_count} quarters ({rev_beat_rate:.0f}%)")

        # ── NEXT EARNINGS DATE (v5.2) ────────────────────────────────
        if valuation_data and valuation_data.get('earnings_calendar'):
            cal = valuation_data['earnings_calendar']
            next_date = cal.get('date', 'Unknown')
            time_of_day = cal.get('time', '')
            time_label = ' (Before Market Open)' if time_of_day == 'bmo' else ' (After Market Close)' if time_of_day == 'amc' else ''
            output.append(f"\n## NEXT EARNINGS DATE\n{next_date}{time_label}")

        # === DEBT MATURITY ANALYSIS (NEW FOR AUDIT) ===
        output.append("\n## DEBT MATURITY STRUCTURE")
        output.append("**When are the debt payments due?**\n")

        # Get latest debt maturity data
        if trends.get('short_term_debt') and len(trends['short_term_debt']) > 0:
            latest_st_debt = trends['short_term_debt'][0]
            latest_lt_debt = trends['long_term_debt'][0] if trends.get('long_term_debt') else 0
            latest_total_debt = latest_st_debt + latest_lt_debt
            st_pct = round(latest_st_debt / latest_total_debt * 100, 1) if latest_total_debt > 0 else 0
            lt_pct = 100 - st_pct if latest_total_debt > 0 else 0

            output.append("### Current Debt Structure")
            output.append("| Component | Amount | % of Total | Risk Level |")
            output.append("|-----------|--------|------------|------------|")

            # Determine risk level based on percentages
            st_risk = "🚨 High" if st_pct > 50 else ("⚠️ Moderate" if st_pct > 30 else "✅ Low")
            lt_risk = "✅ Low" if lt_pct > 70 else ("⚠️ Moderate" if lt_pct > 50 else "🚨 High")

            output.append(f"| Short-term Debt (<12 months) | {fmt.money(latest_st_debt)} | {st_pct}% | {st_risk} |")
            output.append(f"| Long-term Debt (>12 months) | {fmt.money(latest_lt_debt)} | {round(lt_pct, 1)}% | {lt_risk} |")
            output.append(f"| **Total Debt** | **{fmt.money(latest_total_debt)}** | 100% | |")

            if st_pct > 50:
                output.append(f"\n⚠️ **REFINANCING RISK**: {st_pct}% of debt due within 12 months - watch for refinancing pressure")
            elif latest_total_debt == 0:
                output.append("\n✅ **DEBT-FREE**: Company has no debt on balance sheet")

        # === SHAREHOLDER DILUTION ANALYSIS (NEW FOR AUDIT) ===
        output.append("\n## SHAREHOLDER DILUTION ANALYSIS")
        output.append("**Is the company 'printing' more shares?**\n")

        if trends.get('basic_shares') and len(trends['basic_shares']) > 0:
            latest_basic = trends['basic_shares'][0]
            latest_diluted = trends['diluted_shares'][0] if trends.get('diluted_shares') else latest_basic
            latest_dilution_pct = trends['dilution_pct'][0] if trends.get('dilution_pct') else 0
            latest_sbc_to_rev = trends['sbc_to_revenue_pct'][0] if trends.get('sbc_to_revenue_pct') else 0

            output.append("### Share Dilution Metrics (Latest Quarter)")
            output.append("| Metric | Value | Assessment |")
            output.append("|--------|-------|------------|")

            # Format shares in millions
            basic_m = round(latest_basic / 1e6, 1) if latest_basic else 0
            diluted_m = round(latest_diluted / 1e6, 1) if latest_diluted else 0

            # Assess dilution risk
            dilution_status = "🚨 High" if latest_dilution_pct > 5 else ("⚠️ Moderate" if latest_dilution_pct > 2 else "✅ Low")
            sbc_status = "🚨 High" if latest_sbc_to_rev > 15 else ("⚠️ Moderate" if latest_sbc_to_rev > 8 else "✅ Normal")

            output.append(f"| Basic Shares Outstanding | {basic_m}M | |")
            output.append(f"| Diluted Shares Outstanding | {diluted_m}M | |")
            output.append(f"| Share Dilution (Basic → Diluted) | +{latest_dilution_pct}% | {dilution_status} |")
            output.append(f"| SBC as % of Revenue | {latest_sbc_to_rev}% | {sbc_status} |")

            if latest_sbc_to_rev > 15:
                output.append(f"\n⚠️ **DILUTION WARNING**: Stock-based compensation is {latest_sbc_to_rev}% of revenue - shareholders are being significantly diluted")
            elif latest_sbc_to_rev > 8:
                output.append(f"\n**Note**: SBC at {latest_sbc_to_rev}% of revenue is elevated compared to typical mature companies (3-5%)")

        # === RAW ANNUAL DATA ===
        output.append("\n## ANNUAL INCOME STATEMENT (Most Recent 5 Years)")
        income_statements = raw_financials.get('income_statement', [])[:5]
        for stmt in income_statements:
            stmt = decimal_to_float(stmt)
            year = stmt.get('calendarYear', stmt.get('date', 'Unknown')[:4])
            output.append(f"\n  {year}:")
            output.append(f"    Revenue: {fmt.full(stmt.get('revenue', 0))}" if stmt.get('revenue') else "    Revenue: N/A")
            output.append(f"    Gross Profit: {fmt.full(stmt.get('grossProfit', 0))}" if stmt.get('grossProfit') else "    Gross Profit: N/A")
            output.append(f"    Operating Income: {fmt.full(stmt.get('operatingIncome', 0))}" if stmt.get('operatingIncome') else "    Operating Income: N/A")
            output.append(f"    Net Income: {fmt.full(stmt.get('netIncome', 0))}" if stmt.get('netIncome') else "    Net Income: N/A")
            output.append(f"    EPS: {fmt.eps(stmt.get('eps', 0))}" if stmt.get('eps') else "    EPS: N/A")

        output.append("\n## ANNUAL BALANCE SHEET (Most Recent 5 Years)")
        balance_sheets = raw_financials.get('balance_sheet', [])[:5]
        for bs in balance_sheets:
            bs = decimal_to_float(bs)
            year = bs.get('calendarYear', bs.get('date', 'Unknown')[:4])
            output.append(f"\n  {year}:")
            output.append(f"    Total Assets: {fmt.full(bs.get('totalAssets', 0))}" if bs.get('totalAssets') else "    Total Assets: N/A")
            output.append(f"    Total Liabilities: {fmt.full(bs.get('totalLiabilities', 0))}" if bs.get('totalLiabilities') else "    Total Liabilities: N/A")
            output.append(f"    Total Debt: {fmt.full(bs.get('totalDebt', 0))}" if bs.get('totalDebt') else "    Total Debt: N/A")
            output.append(f"    Cash & Equivalents: {fmt.full(bs.get('cashAndCashEquivalents', 0))}" if bs.get('cashAndCashEquivalents') else "    Cash: N/A")
            output.append(f"    Stockholders Equity: {fmt.full(bs.get('totalStockholdersEquity', 0))}" if bs.get('totalStockholdersEquity') else "    Equity: N/A")

        output.append("\n## ANNUAL CASH FLOW (Most Recent 5 Years)")
        cash_flows = raw_financials.get('cash_flow', [])[:5]
        for cf in cash_flows:
            cf = decimal_to_float(cf)
            year = cf.get('calendarYear', cf.get('date', 'Unknown')[:4])
            output.append(f"\n  {year}:")
            output.append(f"    Operating Cash Flow: {fmt.full(cf.get('operatingCashFlow', 0))}" if cf.get('operatingCashFlow') else "    Operating CF: N/A")
            output.append(f"    Capital Expenditures: {fmt.full(cf.get('capitalExpenditure', 0))}" if cf.get('capitalExpenditure') else "    CapEx: N/A")
            output.append(f"    Free Cash Flow: {fmt.full(cf.get('freeCashFlow', 0))}" if cf.get('freeCashFlow') else "    FCF: N/A")
            output.append(f"    Dividends Paid: {fmt.full(cf.get('commonDividendsPaid', 0))}" if cf.get('commonDividendsPaid') else "    Dividends: N/A")
            output.append(f"    Share Repurchases: {fmt.full(cf.get('commonStockRepurchased', 0))}" if cf.get('commonStockRepurchased') else "    Buybacks: N/A")

        # === DIVIDEND ANALYSIS ===
        if valuation_data:
            dividend_output = self._format_dividend_analysis(valuation_data, fmt)
            output.append(dividend_output)

        # === VALUATION & MEAN REVERSION ANALYSIS ===
        if valuation_data:
            valuation_output = self._format_valuation_metrics(valuation_data, fmt)
            output.append(valuation_output)

        return "\n".join(output)

    def _format_dividend_analysis(self, valuation_data: dict, fmt) -> str:
        """
        Format dividend analysis from FMP /stable/dividends endpoint data.

        Computes annual DPS, raise history, CAGR, streak count, and combines
        with TTM ratios (yield, payout ratio, DPS) already fetched.
        For non-dividend stocks, returns a short "no dividend" note.

        Args:
            valuation_data: Dict containing 'dividend_history' list and
                           'financial_ratios_ttm' dict
            fmt: CurrencyFormatter instance for money formatting

        Returns:
            Formatted string with dividend analysis section
        """
        from collections import defaultdict
        from dateutil.relativedelta import relativedelta

        output = []
        output.append("\n## DIVIDEND ANALYSIS")

        dividend_history = valuation_data.get('dividend_history', [])
        ratios_ttm = valuation_data.get('financial_ratios_ttm', {})

        # Non-dividend stock path
        if not dividend_history:
            output.append("This company does not currently pay a dividend. No dividend history available.")
            return "\n".join(output)

        # --- Current Dividend Snapshot (from TTM ratios already fetched) ---
        ttm_yield = ratios_ttm.get('dividendYieldTTM')
        ttm_payout = ratios_ttm.get('dividendPayoutRatioTTM')
        ttm_dps = ratios_ttm.get('dividendPerShareTTM')
        frequency = dividend_history[0].get('frequency', 'N/A') if dividend_history else 'N/A'

        output.append("\n### Current Dividend Snapshot")
        output.append("| Metric | Value |")
        output.append("|--------|-------|")
        output.append(f"| Dividend Per Share (TTM) | {f'${ttm_dps:.2f}' if ttm_dps else 'N/A'} |")
        output.append(f"| Dividend Yield (TTM) | {f'{ttm_yield * 100:.2f}%' if ttm_yield else 'N/A'} |")
        output.append(f"| Payout Ratio (TTM) | {f'{ttm_payout * 100:.1f}%' if ttm_payout else 'N/A'} |")
        output.append(f"| Payment Frequency | {frequency} |")

        # Estimate next payment date from most recent payment
        try:
            last_payment_str = dividend_history[0].get('paymentDate', '')
            if last_payment_str:
                last_payment = datetime.strptime(last_payment_str, '%Y-%m-%d')
                freq_months = {'Quarterly': 3, 'Monthly': 1, 'Semi-Annual': 6, 'Annual': 12}
                months_ahead = freq_months.get(frequency, 3)
                next_payment = last_payment + relativedelta(months=months_ahead)
                output.append(f"| Next Expected Payment | ~{next_payment.strftime('%b %Y')} (estimated) |")
            else:
                output.append("| Next Expected Payment | N/A |")
        except (ValueError, TypeError):
            output.append("| Next Expected Payment | N/A |")

        # --- Filter to regular dividends only (exclude specials) ---
        regular_dividends = [
            d for d in dividend_history
            if d.get('frequency', '').lower() != 'special'
        ]

        if not regular_dividends:
            output.append("\nNo regular dividend payments found (only special dividends).")
            return "\n".join(output)

        # --- Aggregate annual DPS (sum adjDividend by calendar year) ---
        annual_dps = defaultdict(float)
        for d in regular_dividends:
            year = d.get('date', '')[:4]
            if year:
                annual_dps[year] += d.get('adjDividend', 0)

        # Sort years descending, skip current year if incomplete (< 2 payments)
        current_year = str(datetime.now().year)
        current_year_payments = sum(1 for d in regular_dividends if d.get('date', '').startswith(current_year))

        sorted_years = sorted(annual_dps.keys(), reverse=True)
        # Use current year only if it has enough payments, otherwise start from prior year
        if sorted_years and sorted_years[0] == current_year and current_year_payments < 2:
            sorted_years = sorted_years[1:]

        if len(sorted_years) < 2:
            output.append(f"\nInsufficient dividend history for raise analysis (only {len(sorted_years)} year(s) of data).")
            return "\n".join(output)

        # --- 5-Year Raise History Table ---
        output.append("\n### Raise History (Annual Dividend Per Share)")
        output.append("| Year | Annual DPS | YoY Change |")
        output.append("|------|-----------|------------|")

        display_years = sorted_years[:6]  # Show up to 6 years for 5 YoY changes
        raises_data = []
        for i, year in enumerate(display_years):
            dps = annual_dps[year]
            if i < len(display_years) - 1:
                prev_dps = annual_dps[display_years[i + 1]]
                if prev_dps > 0:
                    change_pct = ((dps - prev_dps) / prev_dps) * 100
                    raises_data.append({'year': year, 'dps': dps, 'change': change_pct})
                    output.append(f"| {year} | ${dps:.2f} | {'+' if change_pct >= 0 else ''}{change_pct:.1f}% |")
                else:
                    raises_data.append({'year': year, 'dps': dps, 'change': None})
                    output.append(f"| {year} | ${dps:.2f} | N/A |")
            else:
                output.append(f"| {year} | ${dps:.2f} | — (base year) |")

        # --- Consecutive Raise Streak ---
        streak = 0
        for i in range(len(sorted_years) - 1):
            current_dps = annual_dps[sorted_years[i]]
            prior_dps = annual_dps[sorted_years[i + 1]]
            if current_dps > prior_dps and prior_dps > 0:
                streak += 1
            else:
                break

        # Classify streak
        if streak >= 25:
            streak_label = "Dividend Aristocrat (25+ years)"
        elif streak >= 10:
            streak_label = "Reliable Raiser (10-24 years)"
        elif streak >= 5:
            streak_label = "Building Track Record (5-9 years)"
        elif streak >= 1:
            streak_label = "Early Stage (1-4 years)"
        else:
            streak_label = "No Consecutive Raises"

        output.append(f"\nConsecutive Raise Streak: {streak} years — {streak_label}")
        output.append("(Note: Streak is based on available data window; actual company streak may be longer)")

        # --- CAGR ---
        # Use max available window up to 5 years
        cagr_years = min(5, len(sorted_years) - 1)
        if cagr_years >= 2:
            latest_dps = annual_dps[sorted_years[0]]
            oldest_dps = annual_dps[sorted_years[cagr_years]]
            if oldest_dps > 0 and latest_dps > 0:
                cagr = (latest_dps / oldest_dps) ** (1 / cagr_years) - 1
                output.append(f"{cagr_years}-Year Dividend CAGR: {cagr * 100:.1f}%")
            else:
                output.append(f"{cagr_years}-Year Dividend CAGR: N/A (insufficient data)")
        else:
            output.append("Dividend CAGR: N/A (insufficient history)")

        # --- Special Dividends Note (if any) ---
        special_dividends = [
            d for d in dividend_history
            if d.get('frequency', '').lower() == 'special'
        ]
        if special_dividends:
            output.append(f"\nNote: {len(special_dividends)} special (one-time) dividend(s) detected and excluded from raise history/CAGR:")
            for sd in special_dividends[:3]:
                output.append(f"  - {sd.get('date', 'N/A')}: ${sd.get('adjDividend', 0):.2f}/share (Special)")

        return "\n".join(output)

    def _format_valuation_metrics(self, valuation_data: dict, fmt) -> str:
        """
        Format valuation metrics for mean reversion analysis.

        Compares current TTM values to 5-year historical averages to determine
        if the stock is trading above, below, or near historical norms.

        Args:
            valuation_data: Dict with key_metrics_historical, key_metrics_ttm,
                           financial_ratios_ttm, and analyst_estimates
            fmt: CurrencyFormatter instance for money formatting

        Returns:
            Formatted string with valuation section
        """
        output = []
        output.append("\n## VALUATION & MEAN REVERSION ANALYSIS")
        output.append("**Compare current valuations to 5-year historical averages**\n")

        # Extract data
        historical = valuation_data.get('key_metrics_historical', [])
        ttm = valuation_data.get('key_metrics_ttm', {})
        ratios_ttm = valuation_data.get('financial_ratios_ttm', {})
        estimates = valuation_data.get('analyst_estimates', [])

        # Merge ttm sources (key_metrics_ttm and ratios_ttm have different fields)
        merged_ttm = {**ttm, **ratios_ttm}

        # === 5-YEAR VALUATION MULTIPLES TREND ===
        output.append("### 5-Year Valuation Trend")
        output.append("| Year | P/E | EV/Sales | EV/EBITDA | ROE | ROA |")
        output.append("|------|-----|----------|-----------|-----|-----|")

        # Build year-by-year historical table
        for h in historical[:5]:
            year = h.get('fiscalYear', h.get('date', 'N/A')[:4])
            # Note: Historical key_metrics uses different field names
            pe = h.get('earningsYield')
            pe_str = f"{(1/pe):.1f}x" if pe and pe > 0 else "N/A"  # Invert earnings yield to get P/E
            ev_sales = h.get('evToSales')
            ev_sales_str = f"{ev_sales:.1f}x" if ev_sales else "N/A"
            ev_ebitda = h.get('evToEBITDA')
            ev_ebitda_str = f"{ev_ebitda:.1f}x" if ev_ebitda else "N/A"
            roe = h.get('returnOnEquity')
            roe_str = f"{roe*100:.1f}%" if roe else "N/A"
            roa = h.get('returnOnAssets')
            roa_str = f"{roa*100:.1f}%" if roa else "N/A"
            output.append(f"| {year} | {pe_str} | {ev_sales_str} | {ev_ebitda_str} | {roe_str} | {roa_str} |")

        # === CURRENT TTM VS 5-YEAR AVERAGE ===
        output.append("\n### Current Valuation vs 5-Year Average")
        output.append("| Metric | Current (TTM) | 5-Year Avg | vs History |")
        output.append("|--------|---------------|------------|------------|")

        # Valuation metrics: (ttm_key, hist_key, label, suffix)
        valuation_metrics = [
            ('priceToEarningsRatioTTM', 'earningsYield', 'P/E Ratio', 'x', True),  # Need to invert for avg
            ('priceToSalesRatioTTM', 'evToSales', 'P/S Ratio', 'x', False),
            ('priceToBookRatioTTM', None, 'P/B Ratio', 'x', False),
            ('evToEBITDATTM', 'evToEBITDA', 'EV/EBITDA', 'x', False),
        ]

        for ttm_key, hist_key, label, suffix, invert_hist in valuation_metrics:
            current_val = merged_ttm.get(ttm_key)

            # Calculate 5-year average from historical data if we have a hist_key
            hist_values = []
            if hist_key:
                for h in historical[:5]:
                    val = h.get(hist_key)
                    if val is not None and val != 0:
                        if invert_hist and val > 0:  # For P/E, invert earnings yield
                            hist_values.append(1.0 / float(val))
                        elif not invert_hist and val > 0:
                            hist_values.append(float(val))

            if current_val is not None and current_val > 0:
                current_val = float(current_val)

                if hist_values:
                    avg_val = sum(hist_values) / len(hist_values)
                    # Calculate % difference from historical average
                    pct_diff = ((current_val - avg_val) / avg_val) * 100
                    if pct_diff < -10:
                        vs_hist = f"🟢 {abs(pct_diff):.0f}% cheaper"
                    elif pct_diff > 10:
                        vs_hist = f"🔴 {pct_diff:.0f}% pricier"
                    else:
                        vs_hist = f"⚪ Near average"
                    output.append(f"| {label} | {current_val:.1f}{suffix} | {avg_val:.1f}{suffix} | {vs_hist} |")
                else:
                    output.append(f"| {label} | {current_val:.1f}{suffix} | N/A | No history |")
            elif current_val is not None and current_val < 0:
                output.append(f"| {label} | Negative | N/A | ⚠️ No profit |")
            else:
                output.append(f"| {label} | N/A | N/A | N/A |")

        # === PROFITABILITY & EFFICIENCY METRICS ===
        output.append("\n### Profitability & Efficiency (Current TTM)")
        output.append("| Metric | Value | Assessment |")
        output.append("|--------|-------|------------|")

        # ROE (from key_metrics_ttm)
        roe = ttm.get('returnOnEquityTTM')
        if roe is not None:
            roe_pct = float(roe) * 100
            if roe_pct > 15:
                assessment = "🟢 Strong"
            elif roe_pct > 10:
                assessment = "🟡 Average"
            elif roe_pct > 0:
                assessment = "🟠 Weak"
            else:
                assessment = "🔴 Negative"
            output.append(f"| Return on Equity (ROE) | {roe_pct:.1f}% | {assessment} |")
        else:
            output.append("| Return on Equity (ROE) | N/A | N/A |")

        # ROA (from key_metrics_ttm)
        roa = ttm.get('returnOnAssetsTTM')
        if roa is not None:
            roa_pct = float(roa) * 100
            if roa_pct > 10:
                assessment = "🟢 Strong"
            elif roa_pct > 5:
                assessment = "🟡 Average"
            elif roa_pct > 0:
                assessment = "🟠 Weak"
            else:
                assessment = "🔴 Negative"
            output.append(f"| Return on Assets (ROA) | {roa_pct:.1f}% | {assessment} |")
        else:
            output.append("| Return on Assets (ROA) | N/A | N/A |")

        # Net Profit Margin (from ratios_ttm)
        npm = ratios_ttm.get('netProfitMarginTTM')
        if npm is not None:
            npm_pct = float(npm) * 100
            if npm_pct > 20:
                assessment = "🟢 High margin"
            elif npm_pct > 10:
                assessment = "🟡 Healthy"
            elif npm_pct > 0:
                assessment = "🟠 Thin"
            else:
                assessment = "🔴 Loss"
            output.append(f"| Net Profit Margin | {npm_pct:.1f}% | {assessment} |")
        else:
            output.append("| Net Profit Margin | N/A | N/A |")

        # Asset Turnover (from ratios_ttm)
        at = ratios_ttm.get('assetTurnoverTTM')
        if at is not None:
            at_val = float(at)
            if at_val > 1.0:
                assessment = "🟢 Efficient"
            elif at_val > 0.5:
                assessment = "🟡 Average"
            else:
                assessment = "🟠 Capital intensive"
            output.append(f"| Asset Turnover | {at_val:.2f}x | {assessment} |")
        else:
            output.append("| Asset Turnover | N/A | N/A |")

        # === ANALYST ESTIMATES (Forward Looking) ===
        if estimates:
            output.append("\n### Analyst Estimates (Forward Projections)")
            output.append("| Fiscal Year | Est. Revenue | Est. EPS | # Analysts |")
            output.append("|-------------|--------------|----------|------------|")

            # Get current year for comparison
            current_year = datetime.now().year

            # Filter to future estimates and sort by date
            future_estimates = []
            for est in estimates:
                est_date = est.get('date', '')
                if est_date:
                    try:
                        est_year = int(est_date[:4])
                        if est_year >= current_year:
                            future_estimates.append((est_year, est))
                    except (ValueError, IndexError):
                        continue

            future_estimates.sort(key=lambda x: x[0])

            # Show next 2 fiscal years
            for est_year, est in future_estimates[:2]:
                rev_avg = est.get('revenueAvg', 0)
                eps_avg = est.get('epsAvg', 0)
                num_analysts = est.get('numAnalystsRevenue', est.get('numAnalystsEps', 0))

                rev_str = fmt.money(rev_avg) if rev_avg else "N/A"
                eps_str = f"${eps_avg:.2f}" if eps_avg else "N/A"

                output.append(f"| FY {est_year} | {rev_str} | {eps_str} | {num_analysts} |")

            # Add growth expectations if we have TTM data
            if len(future_estimates) >= 1 and ttm.get('revenuePerShareTTM'):
                # Note: We can calculate implied growth from estimates vs TTM
                output.append("\n**Note**: Compare estimates to current TTM figures to gauge expected growth.")

        # === VALUATION SUMMARY ===
        output.append("\n### Valuation Summary")

        # Calculate overall valuation signal using P/E from ratios_ttm
        pe_ttm = ratios_ttm.get('priceToEarningsRatioTTM')
        # Historical P/E is 1/earningsYield
        pe_hist_values = []
        for h in historical[:5]:
            ey = h.get('earningsYield')
            if ey and ey > 0:
                pe_hist_values.append(1.0 / float(ey))

        if pe_ttm and pe_ttm > 0 and pe_hist_values:
            pe_avg = sum(pe_hist_values) / len(pe_hist_values)
            pe_diff = ((float(pe_ttm) - pe_avg) / pe_avg) * 100

            if pe_diff < -20:
                output.append(f"**Mean Reversion Signal**: 🟢 Stock appears undervalued vs its own history ({abs(pe_diff):.0f}% below 5-year average P/E)")
            elif pe_diff > 20:
                output.append(f"**Mean Reversion Signal**: 🔴 Stock appears overvalued vs its own history ({pe_diff:.0f}% above 5-year average P/E)")
            else:
                output.append(f"**Mean Reversion Signal**: ⚪ Stock trading near historical norms ({pe_diff:+.0f}% vs 5-year average P/E)")
        elif pe_ttm and pe_ttm < 0:
            output.append("**Mean Reversion Signal**: ⚠️ P/E is negative (company has losses) - valuation multiples not applicable")
        else:
            output.append("**Mean Reversion Signal**: N/A - Insufficient data for comparison")

        return "\n".join(output)

    def _load_prompt_template(self) -> str:
        """
        Load the investment report prompt from external file.

        The prompt template contains {ticker}, {fiscal_year}, and {metrics_context}
        placeholders that will be filled in by _generate_with_opus().

        Uses self.prompt_version to select the appropriate template:
        - v1: investment_report_prompt.txt (financial grade)
        - v2: investment_report_prompt_v2.txt (consumer grade)
        """
        prompt_filename = self.PROMPT_VERSIONS.get(self.prompt_version, 'investment_report_prompt.txt')
        prompt_path = os.path.join(
            os.path.dirname(__file__),
            'prompts',
            prompt_filename
        )
        with open(prompt_path, 'r') as f:
            return f.read()

    def get_prompt_template(self) -> str:
        """
        Public method to get the current prompt template.
        Useful for Claude Code mode to see what prompt will be used.
        """
        return self._load_prompt_template()

    def _generate_with_opus(
        self,
        ticker: str,
        fiscal_year: int,
        metrics_context: str
    ) -> Dict[str, Any]:
        """
        Generate analysis using Claude Opus 4.5 with extended thinking.

        Uses Anthropic's thinking mode for deep analysis before generating
        the final report with structured ratings.
        """
        # Load and format the prompt template
        prompt_template = self._load_prompt_template()
        prompt = prompt_template.format(
            ticker=ticker,
            fiscal_year=fiscal_year,
            metrics_context=metrics_context
        )

        # Call Opus 4.5 with extended thinking
        print("    Calling Claude Opus 4.5 with extended thinking...")
        response = self.anthropic_client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000
            },
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract content (skip thinking blocks)
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        # Parse ratings JSON from response
        ratings = self._parse_ratings(content)

        # Log token usage
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        print(f"    Tokens - input: {input_tokens}, output: {output_tokens}")

        return {
            "content": content,
            "ratings": ratings,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens
            }
        }

    def _parse_ratings(self, content: str) -> Dict[str, Any]:
        """
        Extract JSON ratings block from response.

        Delegates to extract_ratings_json() from section_parser to avoid
        duplicate regex logic.
        """
        return extract_ratings_json(content) or {}

    def _cache_report(
        self,
        ticker: str,
        fiscal_year: int,
        report: dict,
        features: dict
    ):
        """
        Cache report in DynamoDB V2 table using section-based schema.

        DEPRECATED: Use save_report_sections() directly for Claude Code mode.
        This method is retained for API mode compatibility but converts to V2 format.
        """
        # Parse report content into sections and save using V2 schema
        report_content = report.get('content', '')
        ratings = report.get('ratings', {})

        # Parse ratings if they're a string
        if isinstance(ratings, str):
            try:
                ratings = json.loads(ratings)
            except json.JSONDecodeError:
                ratings = {}

        # Use save_report_sections which handles V2 schema
        self.save_report_sections(
            ticker=ticker,
            fiscal_year=fiscal_year,
            report_content=report_content,
            ratings=ratings,
            features=features
        )

    def _get_cached_report(self, ticker: str, fiscal_year: int) -> Optional[dict]:
        """
        Retrieve cached report from DynamoDB V2 table.

        Returns the executive section if exists, which contains report metadata.
        Returns None if no cached report exists.
        """
        try:
            # V2 uses ticker + section_id as keys
            # Check for executive section (00_executive) which contains metadata
            response = self.reports_table_v2.get_item(
                Key={'ticker': ticker.upper(), 'section_id': '00_executive'}
            )
            item = response.get('Item')
            if item:
                # Return metadata that callers expect
                return {
                    'ticker': item.get('ticker'),
                    'fiscal_year': item.get('fiscal_year'),
                    'generated_at': item.get('generated_at'),
                    'ratings': item.get('ratings', {}),
                    'prompt_version': item.get('prompt_version'),
                }
            return None
        except Exception as e:
            print(f"    Warning: Cache lookup failed: {e}")
            return None

    # ============================================================
    # TREND ANALYSIS HELPER FUNCTIONS
    # ============================================================

    def _calculate_momentum_metrics(self, income_statements: list) -> dict:
        """
        Calculate growth momentum and deceleration metrics from quarterly data.

        Analyzes YoY growth rates and QoQ sequential changes to detect
        acceleration or deceleration in revenue growth.

        Args:
            income_statements: List of quarterly income statements (most recent first)

        Returns:
            Dict with growth rates, deceleration flags, and warnings
        """
        income_statements = [decimal_to_float(s) for s in income_statements[:12]]

        metrics = {
            'quarterly_data': [],      # Last 8 quarters with calculations
            'growth_rates': [],        # YoY growth rates for recent quarters
            'is_decelerating': False,  # True if significant deceleration detected
            'deceleration_magnitude': 0,  # How much growth dropped (pp)
            'consecutive_qoq_declines': 0,  # Quarters of sequential decline
            'peak_growth_rate': 0,     # Recent peak for comparison
            'current_growth_rate': 0,  # Most recent YoY growth
            'warnings': []             # List of warning strings
        }

        if len(income_statements) < 5:
            metrics['warnings'].append("Insufficient data for momentum analysis")
            return metrics

        # Calculate YoY growth and QoQ change for each quarter
        for i, stmt in enumerate(income_statements[:8]):
            revenue = stmt.get('revenue', 0) or 0
            period = stmt.get('date', 'Unknown')

            # Find same quarter last year (4 quarters back)
            yoy_growth = None
            if i + 4 < len(income_statements):
                yoy_revenue = income_statements[i + 4].get('revenue', 0) or 0
                if yoy_revenue > 0:
                    yoy_growth = round((revenue - yoy_revenue) / yoy_revenue * 100, 1)

            # Calculate QoQ change (vs prior quarter)
            qoq_change = None
            if i + 1 < len(income_statements):
                prior_revenue = income_statements[i + 1].get('revenue', 0) or 0
                if prior_revenue > 0:
                    qoq_change = round((revenue - prior_revenue) / prior_revenue * 100, 1)

            # Determine trend indicator
            trend = ""
            if qoq_change is not None and qoq_change < -2:
                trend = "⚠️"
            if yoy_growth is not None and yoy_growth < 0:
                trend = "🚨"

            metrics['quarterly_data'].append({
                'period': period,
                'revenue': revenue,
                'yoy_growth': yoy_growth,
                'qoq_change': qoq_change,
                'trend': trend
            })

            if yoy_growth is not None:
                metrics['growth_rates'].append(yoy_growth)

        # Analyze growth trajectory
        if len(metrics['growth_rates']) >= 4:
            current = metrics['growth_rates'][0]
            metrics['current_growth_rate'] = current

            # Find peak growth in last 8 quarters
            peak = max(metrics['growth_rates'])
            metrics['peak_growth_rate'] = peak

            # Check for deceleration
            if peak > current:
                metrics['deceleration_magnitude'] = round(peak - current, 1)
                # Significant deceleration = more than 15pp drop from peak
                if metrics['deceleration_magnitude'] > 15:
                    metrics['is_decelerating'] = True
                    metrics['warnings'].append(
                        f"Growth decelerated from {peak}% to {current}% "
                        f"(-{metrics['deceleration_magnitude']}pp)"
                    )

        # Count consecutive QoQ declines
        consecutive_declines = 0
        for q in metrics['quarterly_data']:
            if q['qoq_change'] is not None and q['qoq_change'] < 0:
                consecutive_declines += 1
            else:
                break
        metrics['consecutive_qoq_declines'] = consecutive_declines

        if consecutive_declines >= 3:
            metrics['warnings'].append(
                f"Revenue declined {consecutive_declines} consecutive quarters"
            )

        return metrics

    def _check_margin_compression(self, income_statements: list) -> dict:
        """
        Check for margin compression vs prior year.

        Compares current quarter margins to same quarter last year
        to detect margin erosion.

        Args:
            income_statements: List of quarterly income statements

        Returns:
            Dict with margin metrics, compression flags, and warnings
        """
        income_statements = [decimal_to_float(s) for s in income_statements[:8]]

        metrics = {
            'gross_margin_current': None,
            'gross_margin_yoy': None,
            'gross_margin_change': None,
            'net_margin_current': None,
            'net_margin_yoy': None,
            'net_margin_change': None,
            'is_compressing': False,
            'warnings': []
        }

        if len(income_statements) < 5:
            return metrics

        current = income_statements[0]
        yoy = income_statements[4] if len(income_statements) > 4 else None

        # Calculate current margins
        current_rev = current.get('revenue', 0) or 1
        current_gp = current.get('grossProfit', 0) or 0
        current_ni = current.get('netIncome', 0) or 0

        metrics['gross_margin_current'] = round(current_gp / current_rev * 100, 1)
        metrics['net_margin_current'] = round(current_ni / current_rev * 100, 1)

        # Calculate YoY margins
        if yoy:
            yoy_rev = yoy.get('revenue', 0) or 1
            yoy_gp = yoy.get('grossProfit', 0) or 0
            yoy_ni = yoy.get('netIncome', 0) or 0

            metrics['gross_margin_yoy'] = round(yoy_gp / yoy_rev * 100, 1)
            metrics['net_margin_yoy'] = round(yoy_ni / yoy_rev * 100, 1)

            # Calculate changes
            metrics['gross_margin_change'] = round(
                metrics['gross_margin_current'] - metrics['gross_margin_yoy'], 1
            )
            metrics['net_margin_change'] = round(
                metrics['net_margin_current'] - metrics['net_margin_yoy'], 1
            )

            # Check for compression (more than 3pp decline is notable)
            if metrics['gross_margin_change'] < -3:
                metrics['is_compressing'] = True
                metrics['warnings'].append(
                    f"Gross margin compressed {abs(metrics['gross_margin_change'])}pp YoY "
                    f"({metrics['gross_margin_yoy']}% → {metrics['gross_margin_current']}%)"
                )

            if metrics['net_margin_change'] < -5:
                metrics['warnings'].append(
                    f"Net margin compressed {abs(metrics['net_margin_change'])}pp YoY "
                    f"({metrics['net_margin_yoy']}% → {metrics['net_margin_current']}%)"
                )

        return metrics

    def _check_debt_trends(self, balance_sheets: list, income_statements: list) -> dict:
        """
        Analyze debt health trajectory over recent quarters.

        Checks for rising leverage, weakening interest coverage,
        and net debt accumulation.

        Args:
            balance_sheets: List of quarterly balance sheets
            income_statements: List of quarterly income statements

        Returns:
            Dict with debt metrics, trend analysis, and warnings
        """
        balance_sheets = [decimal_to_float(bs) for bs in balance_sheets[:8]]
        income_statements = [decimal_to_float(inc) for inc in income_statements[:8]]

        metrics = {
            'quarterly_data': [],
            'debt_equity_trend': 'stable',
            'interest_coverage_trend': 'stable',
            'net_debt_trend': 'stable',
            'warnings': []
        }

        if len(balance_sheets) < 4:
            return metrics

        de_ratios = []
        coverage_ratios = []
        net_debts = []

        for i, bs in enumerate(balance_sheets[:8]):
            total_debt = bs.get('totalDebt', 0) or 0
            liquidity = get_total_liquidity(bs)  # Cash + short-term investments
            equity = bs.get('totalStockholdersEquity', 0) or 1
            assets = bs.get('totalAssets', 0) or 1
            net_debt = total_debt - liquidity

            # Get matching income statement for interest coverage
            inc = income_statements[i] if i < len(income_statements) else {}
            op_income = inc.get('operatingIncome', 0) or 0
            interest = inc.get('interestExpense', 0) or 0

            de_ratio = round(total_debt / equity, 2) if equity > 0 else 0
            da_ratio = round(total_debt / assets, 2) if assets > 0 else 0
            # Cap interest coverage at 999 for display (very high coverage = essentially no debt burden)
            if interest > 0:
                raw_coverage = op_income / interest
                interest_coverage = min(round(raw_coverage, 1), 999)
            else:
                interest_coverage = 999  # No interest expense = infinite coverage

            period = bs.get('date', 'Unknown')

            # Determine trend indicator
            trend = ""
            if de_ratio > 1.5:
                trend = "⚠️"
            if interest_coverage < 3:
                trend = "🚨"

            metrics['quarterly_data'].append({
                'period': period,
                'total_debt': total_debt,
                'liquidity': liquidity,  # Cash + short-term investments
                'debt_equity': de_ratio,
                'debt_assets': da_ratio,
                'interest_coverage': interest_coverage,
                'net_debt': net_debt,
                'trend': trend
            })

            de_ratios.append(de_ratio)
            coverage_ratios.append(interest_coverage)
            net_debts.append(net_debt)

        # Analyze trends (compare recent vs older)
        if len(de_ratios) >= 4:
            recent_de = sum(de_ratios[:2]) / 2
            older_de = sum(de_ratios[-2:]) / 2
            de_change = recent_de - older_de

            if de_change > 0.2:
                metrics['debt_equity_trend'] = 'increasing'
                metrics['warnings'].append(
                    f"Debt/Equity ratio increased from {older_de:.2f}x to {recent_de:.2f}x"
                )
            elif de_change < -0.2:
                metrics['debt_equity_trend'] = 'improving'

        if len(coverage_ratios) >= 4:
            recent_cov = coverage_ratios[0]
            # Filter out 999 (infinite coverage from no interest expense) for peak comparison
            meaningful_coverages = [c for c in coverage_ratios if c < 999]
            peak_cov = max(meaningful_coverages) if meaningful_coverages else recent_cov

            if recent_cov < 5:
                metrics['warnings'].append(
                    f"Interest coverage is tight at {recent_cov}x"
                )
            # Only flag weakening if comparing to meaningful coverage values
            if peak_cov < 999 and recent_cov < peak_cov * 0.5:
                metrics['interest_coverage_trend'] = 'weakening'
                metrics['warnings'].append(
                    f"Interest coverage weakened from {peak_cov}x to {recent_cov}x"
                )

        if len(net_debts) >= 4:
            recent_nd = net_debts[0]
            older_nd = net_debts[3]  # Exactly 4 quarters ago (not [-1] which could be 8 quarters)

            # Handle net debt vs net cash position transitions and trends
            if older_nd > 0 and recent_nd > older_nd * 1.2:
                # Was in debt, debt is growing
                metrics['net_debt_trend'] = 'accumulating'
                metrics['warnings'].append(
                    f"Net debt increased {round((recent_nd - older_nd) / older_nd * 100)}% over 4 quarters"
                )
            elif older_nd > 0 and recent_nd < older_nd * 0.8:
                # Was in debt, paying it down
                metrics['net_debt_trend'] = 'deleveraging'
            elif recent_nd < 0 and older_nd >= 0:
                # Transitioned from net debt to net cash position
                metrics['net_debt_trend'] = 'net_cash_achieved'
                metrics['has_net_cash'] = True
            elif recent_nd < 0 and older_nd < 0:
                # Was already net cash, check if growing
                metrics['has_net_cash'] = True
                if abs(recent_nd) > abs(older_nd) * 1.2:
                    metrics['net_debt_trend'] = 'cash_building'
                elif abs(recent_nd) < abs(older_nd) * 0.8:
                    metrics['net_debt_trend'] = 'cash_declining'
                    metrics['warnings'].append(
                        f"Net cash position declined {round((abs(older_nd) - abs(recent_nd)) / abs(older_nd) * 100)}% over 4 quarters"
                    )

        return metrics

    def _check_cashflow_trends(self, cash_flows: list, income_statements: list) -> dict:
        """
        Analyze cash flow health trajectory over recent quarters.

        Checks for FCF deterioration, consecutive negative quarters,
        and OCF to Net Income conversion quality.

        Args:
            cash_flows: List of quarterly cash flow statements
            income_statements: List of quarterly income statements

        Returns:
            Dict with cashflow metrics, trend analysis, and warnings
        """
        cash_flows = [decimal_to_float(cf) for cf in cash_flows[:8]]
        income_statements = [decimal_to_float(inc) for inc in income_statements[:8]]

        metrics = {
            'quarterly_data': [],
            'fcf_trend': 'stable',
            'consecutive_negative_fcf': 0,
            'ocf_ni_ratio': None,
            'warnings': []
        }

        if len(cash_flows) < 4:
            return metrics

        fcfs = []
        fcf_margins = []
        negative_fcf_streak = 0

        for i, cf in enumerate(cash_flows[:8]):
            ocf = cf.get('operatingCashFlow', 0) or 0
            fcf = cf.get('freeCashFlow', 0) or 0
            capex = abs(cf.get('capitalExpenditure', 0) or 0)
            dividends = abs(cf.get('commonDividendsPaid', 0) or 0)

            # Get revenue for FCF margin
            inc = income_statements[i] if i < len(income_statements) else {}
            revenue = inc.get('revenue', 0) or 1
            net_income = inc.get('netIncome', 0) or 1

            fcf_margin = round(fcf / revenue * 100, 1)
            ocf_ni = round(ocf / net_income, 2) if net_income > 0 else 0

            period = cf.get('date', 'Unknown')
            cash_position = cf.get('cashAtEndOfPeriod', 0) or 0

            # Determine trend indicator
            trend = ""
            if fcf < 0:
                trend = "🚨"
            elif fcf_margin < 5:
                trend = "⚠️"
            else:
                trend = "✅"

            metrics['quarterly_data'].append({
                'period': period,
                'operating_cf': ocf,
                'free_cash_flow': fcf,
                'fcf_margin': fcf_margin,
                'capex': capex,
                'dividends': dividends,
                'cash_position': cash_position,
                'ocf_ni_ratio': ocf_ni,
                'trend': trend
            })

            fcfs.append(fcf)
            fcf_margins.append(fcf_margin)

            # Count consecutive negative FCF quarters
            if i == 0 and fcf < 0:
                negative_fcf_streak = 1
            elif negative_fcf_streak > 0 and fcf < 0:
                negative_fcf_streak += 1
            elif fcf >= 0:
                if i == 0:
                    negative_fcf_streak = 0

        metrics['consecutive_negative_fcf'] = negative_fcf_streak

        if negative_fcf_streak >= 2:
            metrics['warnings'].append(
                f"{negative_fcf_streak} consecutive quarters of negative free cash flow"
            )

        # Calculate OCF to NI ratio (cash conversion quality)
        # Use TTM (trailing 12 months) for stability - quarterly ratios are too volatile
        if len(cash_flows) >= 4 and len(income_statements) >= 4:
            # TTM: Sum last 4 quarters (stable, preferred metric)
            ttm_ocf = sum(cf.get('operatingCashFlow', 0) or 0 for cf in cash_flows[:4])
            ttm_ni = sum(inc.get('netIncome', 0) or 0 for inc in income_statements[:4])
            metrics['ocf_ni_ratio_ttm'] = round(ttm_ocf / ttm_ni, 2) if ttm_ni > 0 else 0

            # TTM FCF calculation - provides stable view of cash generation
            ttm_fcf = sum(cf.get('freeCashFlow', 0) or 0 for cf in cash_flows[:4])
            ttm_revenue = sum(inc.get('revenue', 0) or 0 for inc in income_statements[:4])
            metrics['fcf_ttm'] = ttm_fcf
            metrics['fcf_quarterly'] = cash_flows[0].get('freeCashFlow', 0) or 0
            metrics['fcf_margin_ttm'] = round(ttm_fcf / ttm_revenue * 100, 1) if ttm_revenue > 0 else 0

            # Also keep quarterly for trend visibility
            recent_ocf = cash_flows[0].get('operatingCashFlow', 0) or 0
            recent_ni = income_statements[0].get('netIncome', 0) or 1
            metrics['ocf_ni_ratio_quarterly'] = round(recent_ocf / recent_ni, 2) if recent_ni > 0 else 0

            # Primary metric is TTM (used in alerts and Quick Health Check)
            metrics['ocf_ni_ratio'] = metrics['ocf_ni_ratio_ttm']

            # Warning if TTM ratio is weak
            if metrics['ocf_ni_ratio_ttm'] < 0.8:
                metrics['warnings'].append(
                    f"Weak cash conversion: OCF/Net Income ratio is {metrics['ocf_ni_ratio_ttm']}x (TTM)"
                )

            # Warning if quarterly differs significantly from TTM (volatility indicator)
            if abs(metrics['ocf_ni_ratio_quarterly'] - metrics['ocf_ni_ratio_ttm']) > 0.5:
                metrics['warnings'].append(
                    f"Cash conversion volatile: Q latest {metrics['ocf_ni_ratio_quarterly']}x vs TTM {metrics['ocf_ni_ratio_ttm']}x"
                )

            # Warning if quarterly FCF differs significantly from TTM average (seasonality/volatility)
            ttm_fcf_quarterly_avg = ttm_fcf / 4
            if ttm_fcf_quarterly_avg > 0 and metrics['fcf_quarterly'] < ttm_fcf_quarterly_avg * 0.5:
                metrics['warnings'].append(
                    f"Quarterly FCF below TTM trend: ${metrics['fcf_quarterly']:,.0f} vs TTM avg ${ttm_fcf_quarterly_avg:,.0f}"
                )
        elif len(cash_flows) > 0 and len(income_statements) > 0:
            # Fallback to single quarter if not enough data for TTM
            recent_ocf = cash_flows[0].get('operatingCashFlow', 0) or 0
            recent_ni = income_statements[0].get('netIncome', 0) or 1
            metrics['ocf_ni_ratio'] = round(recent_ocf / recent_ni, 2) if recent_ni > 0 else 0
            metrics['ocf_ni_ratio_ttm'] = metrics['ocf_ni_ratio']  # Use quarterly as fallback
            metrics['ocf_ni_ratio_quarterly'] = metrics['ocf_ni_ratio']

            if metrics['ocf_ni_ratio'] < 0.8:
                metrics['warnings'].append(
                    f"Weak cash conversion: OCF/Net Income ratio is {metrics['ocf_ni_ratio']}x (quarterly - insufficient data for TTM)"
                )

        # Check FCF margin trend
        if len(fcf_margins) >= 4:
            recent_margin = fcf_margins[0]
            yoy_margin = fcf_margins[4] if len(fcf_margins) > 4 else fcf_margins[-1]

            if recent_margin < yoy_margin - 15:
                metrics['fcf_trend'] = 'deteriorating'
                metrics['warnings'].append(
                    f"FCF margin declined {round(yoy_margin - recent_margin)}pp YoY "
                    f"({yoy_margin}% → {recent_margin}%)"
                )
            elif recent_margin > yoy_margin + 10:
                metrics['fcf_trend'] = 'improving'

        return metrics
