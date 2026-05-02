"""
Tool Executor for Follow-Up Agent

Implements the tool functions invoked via Bedrock Runtime converse_stream's
inline `tools` parameter. Queries DynamoDB directly for investment reports
and metrics. (The deprecated followup-action action-group Lambda was removed
in 2026-05; this module is the live replacement.)
"""

import json
import logging
import os
from decimal import Decimal
from typing import Dict, Any, Optional, List

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
# NOTE: Use correct env var names that match Terraform configuration:
# - INVESTMENT_REPORTS_V2_TABLE (not INVESTMENT_REPORTS_TABLE)
# - METRICS_HISTORY_CACHE_TABLE (not METRICS_HISTORY_TABLE)
REPORTS_TABLE = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', f'investment-reports-v2-{ENVIRONMENT}')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')

# Log table names at module load for debugging
logger.info(f"tool_executor initialized: REPORTS_TABLE={REPORTS_TABLE}, METRICS_TABLE={METRICS_TABLE}")

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
reports_table = dynamodb.Table(REPORTS_TABLE)
metrics_table = dynamodb.Table(METRICS_TABLE)


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types from DynamoDB."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj) if obj % 1 else int(obj)
        return super().default(obj)


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route tool calls to appropriate handler functions.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Parameters for the tool

    Returns:
        Tool result dict with success/error status
    """
    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

    try:
        if tool_name == "getReportSection":
            return get_report_section(
                ticker=tool_input.get('ticker', ''),
                section_id=tool_input.get('section_id', '')
            )

        elif tool_name == "getReportRatings":
            return get_report_ratings(
                ticker=tool_input.get('ticker', '')
            )

        elif tool_name == "getMetricsHistory":
            return get_metrics_history(
                ticker=tool_input.get('ticker', ''),
                metric_type=tool_input.get('metric_type', 'all'),
                quarters=tool_input.get('quarters', 8)
            )

        elif tool_name == "getAvailableReports":
            return get_available_reports()

        elif tool_name == "compareStocks":
            return compare_stocks(
                tickers=tool_input.get('tickers', []),
                metric_type=tool_input.get('metric_type', 'all'),
                quarters=tool_input.get('quarters', 4)
            )

        elif tool_name == "getFinancialSnapshot":
            return get_financial_snapshot(
                ticker=tool_input.get('ticker', '')
            )

        else:
            logger.warning(f"Unknown tool requested: {tool_name}")
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }

    except Exception as e:
        logger.error(f"Tool execution error for {tool_name}: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def get_report_section(ticker: str, section_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific section from an investment report.

    Args:
        ticker: Stock ticker symbol
        section_id: Section identifier (e.g., '11_debt', '06_growth')

    Returns:
        Section content with metadata
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}
    if not section_id:
        return {"success": False, "error": "section_id is required"}

    ticker = ticker.upper().strip()

    # Section ID aliasing: map v5.2 IDs to v5.1 IDs for backward compatibility.
    # Reports generated with v5.1 use different section IDs for some sections.
    # Try the requested ID first; if not found, try the alias.
    SECTION_ID_ALIASES = {
        # v5.2 ID -> v5.1 ID (for reports generated before v5.2)
        '15_bull': '13_bull',
        '16_bear': '14_bear',
        '18_realtalk': '17_realtalk',
        '19_triggers': None,  # No v5.1 equivalent
        # v5.1 ID -> v5.2 ID (for future-proofing)
        '13_bull': '15_bull',
        '14_bear': '16_bear',
        '15_warnings': None,  # Removed in v5.2
        '16_vibe': None,  # Removed in v5.2
        '17_realtalk': '18_realtalk',
    }

    try:
        # Handle Executive Summary specially - stored under '00_executive'
        if section_id == '01_executive_summary':
            response = reports_table.get_item(
                Key={
                    'ticker': ticker,
                    'section_id': '00_executive'
                }
            )
            item = response.get('Item')
            if item:
                # Executive summary is nested in the item
                exec_summary = item.get('executive_summary', {})
                return {
                    "success": True,
                    "ticker": ticker,
                    "section_id": section_id,
                    "title": "Executive Summary",
                    "content": exec_summary.get('content', ''),
                    "part": 1,
                    "word_count": int(exec_summary.get('word_count', 0))
                }
        else:
            # Standard section lookup
            response = reports_table.get_item(
                Key={
                    'ticker': ticker,
                    'section_id': section_id
                }
            )
            item = response.get('Item')

            # If not found, try alias for backward/forward compatibility
            if not item and section_id in SECTION_ID_ALIASES:
                alias = SECTION_ID_ALIASES[section_id]
                if alias:
                    response = reports_table.get_item(
                        Key={
                            'ticker': ticker,
                            'section_id': alias
                        }
                    )
                    item = response.get('Item')

            if item:
                return {
                    "success": True,
                    "ticker": ticker,
                    "section_id": section_id,
                    "title": item.get('title', ''),
                    "content": item.get('content', ''),
                    "part": int(item.get('part', 0)),
                    "word_count": int(item.get('word_count', 0))
                }

        return {
            "success": False,
            "error": f"Section '{section_id}' not found for {ticker}. The report may not exist or use a different section ID."
        }

    except Exception as e:
        logger.error(f"Error fetching report section {ticker}/{section_id}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_report_ratings(ticker: str) -> Dict[str, Any]:
    """
    Get investment ratings and verdict for a company.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Ratings object with confidence scores and verdict
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    ticker = ticker.upper().strip()

    try:
        # Ratings are stored in the '00_executive' section
        response = reports_table.get_item(
            Key={
                'ticker': ticker,
                'section_id': '00_executive'
            }
        )

        item = response.get('Item')

        if not item or not item.get('ratings'):
            return {
                "success": False,
                "error": f"No ratings found for {ticker}. Report may not exist."
            }

        # Extract ratings - handle both JSON string and dict formats
        ratings = item.get('ratings', {})
        if isinstance(ratings, str):
            ratings = json.loads(ratings)

        return {
            "success": True,
            "ticker": ticker,
            "company_name": item.get('company_name', ticker),
            "ratings": ratings,
            "generated_at": item.get('generated_at', '')
        }

    except Exception as e:
        logger.error(f"Error fetching ratings for {ticker}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_metrics_history(
    ticker: str,
    metric_type: str = 'all',
    quarters: int = 8
) -> Dict[str, Any]:
    """
    Retrieve historical financial metrics for trend analysis.

    Uses optimized quarter-based schema: items with all 7 categories
    embedded in each item. Filters to requested category(s) before returning.

    Args:
        ticker: Stock ticker symbol
        metric_type: Category of metrics ('all', 'revenue_profit', 'cashflow', etc.)
        quarters: Number of quarters to retrieve (1-40)

    Returns:
        Historical metrics organized by category
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    ticker = ticker.upper().strip()
    quarters = min(max(int(quarters), 1), 40)  # Clamp to 1-40

    # Valid metric categories (7 quarterly-trend categories + 2 event-based categories)
    valid_categories = [
        'revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
        'earnings_quality', 'dilution', 'valuation',
        'earnings_events', 'dividend'
    ]

    if metric_type != 'all' and metric_type not in valid_categories:
        return {
            "success": False,
            "error": f"Unknown metric type: {metric_type}",
            "available_types": valid_categories
        }

    categories_to_include = valid_categories if metric_type == 'all' else [metric_type]

    try:
        # Query metrics table sorted by fiscal_date descending
        response = metrics_table.query(
            KeyConditionExpression=Key('ticker').eq(ticker),
            ScanIndexForward=False,  # Most recent first
            Limit=quarters
        )

        items = response.get('Items', [])

        if not items:
            return {
                "success": False,
                "error": f"No metrics history found for {ticker}. Report may not have been generated.",
                "ticker": ticker
            }

        # Category descriptions for context
        category_descriptions = {
            'revenue_profit': 'Revenue & Profitability Metrics',
            'cashflow': 'Cash Flow Metrics',
            'balance_sheet': 'Balance Sheet Metrics',
            'debt_leverage': 'Debt & Leverage Ratios',
            'earnings_quality': 'Earnings Quality Metrics',
            'dilution': 'Share Dilution Metrics',
            'valuation': 'Valuation & Returns Metrics',
            'earnings_events': 'Earnings Results — EPS & Revenue Beat/Miss per Quarter',
            'dividend': 'Dividend Metrics — DPS, Yield, Frequency (empty for non-paying companies)'
        }

        # Build result with filtered categories
        result = {
            "success": True,
            "ticker": ticker,
            "metric_type": metric_type,
            "quarters_requested": quarters,
            "quarters_available": len(items),
            "categories_returned": categories_to_include,
            "data": {}
        }

        # Initialize categories
        for category in categories_to_include:
            result['data'][category] = {
                'description': category_descriptions.get(category, category),
                'quarters': []
            }

        # Process each quarter
        for item in items:
            fiscal_date = item.get('fiscal_date', '')
            fiscal_year = item.get('fiscal_year')
            fiscal_quarter = item.get('fiscal_quarter', '')

            for category in categories_to_include:
                category_metrics = item.get(category, {})

                if category_metrics:
                    # Convert Decimals to floats for JSON serialization
                    metrics_clean = {}
                    for k, v in category_metrics.items():
                        if isinstance(v, Decimal):
                            metrics_clean[k] = float(v)
                        elif hasattr(v, '__float__'):
                            metrics_clean[k] = float(v)
                        elif v is not None:
                            metrics_clean[k] = v

                    result['data'][category]['quarters'].append({
                        'fiscal_date': fiscal_date,
                        'fiscal_year': int(fiscal_year) if fiscal_year else None,
                        'fiscal_quarter': fiscal_quarter,
                        'metrics': metrics_clean
                    })

        # Log metrics count for debugging
        total_metrics = sum(
            len(q['metrics'])
            for cat_data in result['data'].values()
            for q in cat_data['quarters']
        )
        logger.info(
            f"Retrieved {len(items)} quarters for {ticker} "
            f"(categories={categories_to_include}, metrics={total_metrics})"
        )

        return result

    except Exception as e:
        logger.error(f"Error fetching metrics for {ticker}: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def get_available_reports() -> Dict[str, Any]:
    """
    List all companies with available investment reports.

    Returns:
        List of available reports with metadata
    """
    try:
        # Scan for '00_executive' items (one per ticker)
        response = reports_table.scan(
            FilterExpression='section_id = :sid',
            ExpressionAttributeValues={':sid': '00_executive'},
            ProjectionExpression='ticker, company_name, generated_at'
        )

        reports = []
        for item in response.get('Items', []):
            reports.append({
                'ticker': item.get('ticker', ''),
                'company_name': item.get('company_name', item.get('ticker', '')),
                'generated_at': item.get('generated_at', '')
            })

        # Handle pagination if needed
        while 'LastEvaluatedKey' in response:
            response = reports_table.scan(
                FilterExpression='section_id = :sid',
                ExpressionAttributeValues={':sid': '00_executive'},
                ProjectionExpression='ticker, company_name, generated_at',
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            for item in response.get('Items', []):
                reports.append({
                    'ticker': item.get('ticker', ''),
                    'company_name': item.get('company_name', item.get('ticker', '')),
                    'generated_at': item.get('generated_at', '')
                })

        # Sort alphabetically by ticker
        reports.sort(key=lambda x: x['ticker'])

        return {
            "success": True,
            "count": len(reports),
            "reports": reports
        }

    except Exception as e:
        logger.error(f"Error listing available reports: {e}")
        return {
            "success": False,
            "error": f"Database error: {str(e)}"
        }


def compare_stocks(
    tickers: List[str],
    metric_type: str = 'all',
    quarters: int = 4
) -> Dict[str, Any]:
    """
    Compare 2-5 stocks side-by-side across metrics and ratings.

    Runs parallel-style queries per ticker, then assembles a comparison.

    Args:
        tickers: List of 2-5 stock ticker symbols
        metric_type: Category of metrics to compare ('all', 'revenue_profit', etc.)
        quarters: Number of quarters to include (default 4 for recent comparison)

    Returns:
        Comparison object with per-ticker ratings and metrics
    """
    if not tickers or not isinstance(tickers, list):
        return {"success": False, "error": "tickers must be a list of 2-5 stock symbols"}

    if len(tickers) < 2:
        return {"success": False, "error": "At least 2 tickers required for comparison"}

    if len(tickers) > 5:
        return {"success": False, "error": "Maximum 5 tickers for comparison"}

    tickers = [t.upper().strip() for t in tickers if t and isinstance(t, str)]

    if len(tickers) < 2:
        return {"success": False, "error": "At least 2 valid ticker symbols required"}

    quarters = min(max(int(quarters), 1), 20)

    try:
        comparison = {}
        not_found = []

        for ticker in tickers:
            # Fetch ratings
            ratings_result = get_report_ratings(ticker)

            # Fetch latest metrics
            metrics_result = get_metrics_history(ticker, metric_type, quarters)

            if not ratings_result.get('success') and not metrics_result.get('success'):
                not_found.append(ticker)
                continue

            comparison[ticker] = {
                "company_name": ratings_result.get('company_name', ticker),
                "ratings": ratings_result.get('ratings', {}) if ratings_result.get('success') else None,
                "generated_at": ratings_result.get('generated_at', ''),
                "metrics": metrics_result.get('data', {}) if metrics_result.get('success') else None,
                "quarters_available": metrics_result.get('quarters_available', 0)
            }

        if not comparison:
            return {
                "success": False,
                "error": f"No reports found for any of the requested tickers: {', '.join(not_found)}"
            }

        result = {
            "success": True,
            "tickers_compared": list(comparison.keys()),
            "metric_type": metric_type,
            "quarters": quarters,
            "comparison": comparison
        }

        if not_found:
            result["tickers_not_found"] = not_found
            result["warning"] = f"No reports found for: {', '.join(not_found)}"

        logger.info(f"Compared {len(comparison)} stocks: {list(comparison.keys())}")
        return result

    except Exception as e:
        logger.error(f"Error comparing stocks {tickers}: {e}")
        return {
            "success": False,
            "error": f"Comparison error: {str(e)}"
        }


def get_financial_snapshot(ticker: str) -> Dict[str, Any]:
    """
    Get a quick financial snapshot: latest quarter metrics + ratings in one call.

    Combines getReportRatings and getMetricsHistory(quarters=1) into a single
    response, reducing orchestration turns for quick assessments.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Combined snapshot with ratings, verdict, and latest quarter metrics
    """
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    ticker = ticker.upper().strip()

    try:
        # Fetch ratings
        ratings_result = get_report_ratings(ticker)

        # Fetch latest quarter across all categories
        metrics_result = get_metrics_history(ticker, 'all', 1)

        if not ratings_result.get('success') and not metrics_result.get('success'):
            return {
                "success": False,
                "error": f"No data found for {ticker}. Report may not exist.",
                "ticker": ticker
            }

        # Flatten the latest quarter metrics for easy consumption.
        # Exclude event-based categories (earnings_events, dividend) to keep
        # the snapshot lightweight — users should query those explicitly.
        SNAPSHOT_EXCLUDED_CATEGORIES = {'earnings_events', 'dividend'}
        latest_metrics = {}
        if metrics_result.get('success') and metrics_result.get('data'):
            for category, category_data in metrics_result['data'].items():
                if category in SNAPSHOT_EXCLUDED_CATEGORIES:
                    continue
                quarters_data = category_data.get('quarters', [])
                if quarters_data:
                    latest_metrics[category] = quarters_data[0].get('metrics', {})

        # Extract fiscal period info from metrics
        fiscal_period = {}
        if metrics_result.get('success') and metrics_result.get('data'):
            for category_data in metrics_result['data'].values():
                quarters_data = category_data.get('quarters', [])
                if quarters_data:
                    fiscal_period = {
                        'fiscal_date': quarters_data[0].get('fiscal_date', ''),
                        'fiscal_year': quarters_data[0].get('fiscal_year'),
                        'fiscal_quarter': quarters_data[0].get('fiscal_quarter', '')
                    }
                    break

        return {
            "success": True,
            "ticker": ticker,
            "company_name": ratings_result.get('company_name', ticker),
            "ratings": ratings_result.get('ratings', {}) if ratings_result.get('success') else None,
            "generated_at": ratings_result.get('generated_at', ''),
            "fiscal_period": fiscal_period,
            "latest_metrics": latest_metrics
        }

    except Exception as e:
        logger.error(f"Error fetching snapshot for {ticker}: {e}")
        return {
            "success": False,
            "error": f"Snapshot error: {str(e)}"
        }
