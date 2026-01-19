"""
Report Service for Investment Research Follow-up Action Group.

Provides functions to retrieve investment report data from DynamoDB.
These functions are called by the action group handler based on Bedrock agent requests.

Based on followup_service.py from investment_research Lambda.
"""

import json
import logging
import os
from typing import Any, Dict

import boto3

logger = logging.getLogger(__name__)

# DynamoDB table names from environment
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
FINANCIAL_CACHE_TABLE = os.environ.get('FINANCIAL_DATA_CACHE_TABLE', 'financial-data-cache-dev')
METRICS_HISTORY_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', 'metrics-history-dev')

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')


# =============================================================================
# Investment Research Metrics Definition
# These are the specific metrics used in investment research reports
# =============================================================================

INVESTMENT_RESEARCH_METRICS = {
    'revenue_profit': {
        'description': 'Revenue & Profitability Metrics',
        'metrics': [
            'revenue',
            'netIncome',
            'grossProfit',
            'operatingIncome',
            'eps',
            'gross_margin',
            'operating_margin',
            'net_margin',
            'revenue_growth_yoy',
        ]
    },
    'cashflow': {
        'description': 'Cash Flow Metrics',
        'metrics': [
            'operatingCashFlow',
            'freeCashFlow',
            'capitalExpenditure',
            'dividendsPaid',
            'commonStockRepurchased',
            'fcf_margin',
            'ocf_to_ni_ratio',
        ]
    },
    'balance_sheet': {
        'description': 'Balance Sheet Metrics',
        'metrics': [
            'totalDebt',
            'cashAndCashEquivalents',
            'shortTermInvestments',
            'totalLiquidity',
            'netDebt',
            'totalStockholdersEquity',
            'totalAssets',
            'totalCurrentAssets',
            'totalCurrentLiabilities',
        ]
    },
    'debt_leverage': {
        'description': 'Debt & Leverage Ratios',
        'metrics': [
            'debt_to_equity',
            'debt_to_assets',
            'interest_coverage',
            'current_ratio',
            'quick_ratio',
            'short_term_debt',
            'long_term_debt',
            'st_debt_pct',
        ]
    },
    'earnings_quality': {
        'description': 'Earnings Quality Metrics',
        'metrics': [
            'gaap_net_income',
            'stock_based_compensation',
            'depreciation_amortization',
            'adjusted_earnings',
            'sbc_to_revenue_pct',
        ]
    },
    'dilution': {
        'description': 'Shareholder Dilution Metrics',
        'metrics': [
            'basic_shares_outstanding',
            'diluted_shares_outstanding',
            'dilution_pct',
            'share_repurchases',
        ]
    },
    'valuation': {
        'description': 'Valuation Metrics (from Key Metrics TTM)',
        'metrics': [
            'pe_ratio',
            'pb_ratio',
            'ev_to_ebitda',
            'price_to_fcf',
            'peg_ratio',
            'dividend_yield',
            'roe',
            'roic',
        ]
    }
}


# =============================================================================
# Action Group Functions
# =============================================================================

def get_report_section(ticker: str, section_id: str) -> Dict[str, Any]:
    """
    Retrieve a specific section from an investment report.

    Args:
        ticker: Stock ticker symbol
        section_id: Section ID (e.g., '01_executive_summary', '06_growth')

    Returns:
        Dict with section content and metadata
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)
    ticker = ticker.upper()

    # Handle merged Executive Summary specially
    if section_id == '01_executive_summary':
        response = table.get_item(Key={'ticker': ticker, 'section_id': '00_executive'})
        item = response.get('Item')
        if item:
            return {
                'success': True,
                'ticker': ticker,
                'section_id': section_id,
                'title': 'Executive Summary',
                'content': item.get('executive_summary', {}).get('content', ''),
                'part': 1,
                'word_count': item.get('executive_summary', {}).get('word_count', 0)
            }
    else:
        response = table.get_item(Key={'ticker': ticker, 'section_id': section_id})
        item = response.get('Item')
        if item:
            return {
                'success': True,
                'ticker': ticker,
                'section_id': section_id,
                'title': item.get('title', ''),
                'content': item.get('content', ''),
                'part': item.get('part', 0),
                'word_count': item.get('word_count', 0)
            }

    return {
        'success': False,
        'error': f'Section {section_id} not found for {ticker}'
    }


def get_report_ratings(ticker: str) -> Dict[str, Any]:
    """
    Retrieve investment ratings for a ticker.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Dict with all ratings (debt, cashflow, growth, overall verdict)
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)
    ticker = ticker.upper()

    response = table.get_item(Key={'ticker': ticker, 'section_id': '00_executive'})
    item = response.get('Item')

    if item and item.get('ratings'):
        ratings = item['ratings']
        # Handle both JSON string and dict formats
        if isinstance(ratings, str):
            ratings = json.loads(ratings)
        return {
            'success': True,
            'ticker': ticker,
            'ratings': ratings,
            'generated_at': item.get('generated_at')
        }

    return {
        'success': False,
        'error': f'No ratings found for {ticker}'
    }


def get_metrics_history(
    ticker: str,
    metric_type: str = 'all',
    quarters: int = 20
) -> Dict[str, Any]:
    """
    Retrieve pre-computed metrics from metrics-history-cache table.

    Uses optimized quarter-based schema: 20 items per ticker with all 7 categories
    embedded in each item. Filters to requested category(s) before returning.
    ~85% token savings vs querying all raw financial data.

    Args:
        ticker: Stock ticker symbol
        metric_type: Category filter ('revenue_profit', 'cashflow', 'balance_sheet',
                    'debt_leverage', 'earnings_quality', 'dilution', 'valuation', or 'all')
        quarters: Number of quarters to retrieve (max 20)

    Returns:
        Dict with metrics organized by category and quarter, sorted most recent first
    """
    from boto3.dynamodb.conditions import Key

    ticker = ticker.upper()
    table = dynamodb.Table(METRICS_HISTORY_TABLE)

    # Valid categories (from CATEGORY_METRICS in feature_extractor.py)
    valid_categories = [
        'revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
        'earnings_quality', 'dilution', 'valuation'
    ]

    # Category descriptions for agent context
    category_descriptions = {
        'revenue_profit': 'Revenue & Profitability Metrics',
        'cashflow': 'Cash Flow Metrics',
        'balance_sheet': 'Balance Sheet Metrics',
        'debt_leverage': 'Debt & Leverage Ratios',
        'earnings_quality': 'Earnings Quality Metrics',
        'dilution': 'Share Dilution Metrics',
        'valuation': 'Valuation & Returns Metrics'
    }

    if metric_type != 'all' and metric_type not in valid_categories:
        return {
            'success': False,
            'error': f'Unknown metric type: {metric_type}',
            'available_types': valid_categories
        }

    # Determine which categories to include in response
    categories_to_include = valid_categories if metric_type == 'all' else [metric_type]

    try:
        # Query by ticker, sorted by fiscal_date (most recent first)
        # New schema: fiscal_date is the sort key, categories are embedded
        response = table.query(
            KeyConditionExpression=Key('ticker').eq(ticker),
            Limit=quarters,
            ScanIndexForward=False  # Descending order (most recent first)
        )

        items = response.get('Items', [])

        if not items:
            return {
                'success': False,
                'error': f'No metrics found for {ticker}. Report may not have been generated yet.',
                'ticker': ticker,
                'metric_type': metric_type
            }

        # Build result with requested categories only
        result = {
            'success': True,
            'ticker': ticker,
            'metric_type': metric_type,
            'quarters_requested': quarters,
            'quarters_available': len(items),
            'categories_returned': categories_to_include,
            'data': {}
        }

        # Initialize category containers
        for category in categories_to_include:
            result['data'][category] = {
                'description': category_descriptions.get(category, category),
                'quarters': []
            }

        # Process each quarter item
        for item in items:
            fiscal_date = item.get('fiscal_date')
            fiscal_year = item.get('fiscal_year')
            fiscal_quarter = item.get('fiscal_quarter')

            # Extract only the requested categories from this quarter
            for category in categories_to_include:
                category_metrics = item.get(category, {})

                if category_metrics:
                    # Convert Decimal to float for JSON serialization
                    metrics_float = {
                        k: float(v) if hasattr(v, '__float__') else v
                        for k, v in category_metrics.items()
                    }

                    result['data'][category]['quarters'].append({
                        'fiscal_date': fiscal_date,
                        'fiscal_year': fiscal_year,
                        'fiscal_quarter': fiscal_quarter,
                        'metrics': metrics_float
                    })

        # Count total metrics returned for logging
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
        logger.error(f"Error retrieving metrics for {ticker}: {e}")
        return {
            'success': False,
            'error': f'Failed to retrieve metrics: {str(e)}',
            'ticker': ticker,
            'metric_type': metric_type
        }


def get_available_reports() -> Dict[str, Any]:
    """
    List all available investment reports.

    Returns list of tickers with reports, useful for search dropdown.
    """
    table = dynamodb.Table(REPORTS_TABLE_V2)

    # Query for all 00_executive items (one per ticker)
    response = table.scan(
        FilterExpression='section_id = :sid',
        ExpressionAttributeValues={':sid': '00_executive'},
        ProjectionExpression='ticker, company_name, generated_at'
    )

    reports = []
    for item in response.get('Items', []):
        reports.append({
            'ticker': item.get('ticker'),
            'company_name': item.get('company_name', item.get('ticker')),
            'generated_at': item.get('generated_at')
        })

    # Sort by ticker
    reports.sort(key=lambda x: x['ticker'])

    return {
        'success': True,
        'count': len(reports),
        'reports': reports
    }
