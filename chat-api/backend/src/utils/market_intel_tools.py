"""
Tool Executor for Market Intelligence Agent

Implements 9 tools that query metrics-history and sp500-aggregates DynamoDB tables
to answer S&P 500 market analysis questions.

Tools:
  1. screenStocks       — Filter companies by metric thresholds
  2. getSectorOverview  — Sector medians, top companies, earnings/dividend summary
  3. getTopCompanies    — Rank companies by any metric
  4. getIndexSnapshot   — Overall S&P 500 health metrics
  5. getCompanyProfile  — Single company metrics + sector context
  6. compareCompanies   — Side-by-side multi-ticker comparison
  7. getMetricTrend     — Quarterly trajectory of a metric over time
  8. getEarningsSurprises — Biggest EPS beats or misses
  9. compareSectors     — Side-by-side sector comparison
"""

import json
import logging
import os
import statistics
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

# Import ticker data from investment_research package
from investment_research.index_tickers import SP500_TICKERS, SP500_SECTORS

logger = logging.getLogger(__name__)

# Environment configuration
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)
aggregates_table = dynamodb.Table(AGGREGATES_TABLE)


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
        handlers = {
            "screenStocks": _screen_stocks,
            "getSectorOverview": _get_sector_overview,
            "getTopCompanies": _get_top_companies,
            "getIndexSnapshot": _get_index_snapshot,
            "getCompanyProfile": _get_company_profile,
            "compareCompanies": _compare_companies,
            "getMetricTrend": _get_metric_trend,
            "getEarningsSurprises": _get_earnings_surprises,
            "compareSectors": _compare_sectors,
            "getHistoricalValuation": _get_historical_valuation,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        return handler(tool_input)

    except Exception as e:
        logger.error(f"Tool execution error for {tool_name}: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


def _safe_float(value) -> Optional[float]:
    """Convert DynamoDB Decimal/string/None to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _compute_metric_stats(values: List[float], current: Optional[float], direction: str) -> Dict:
    """Compute summary statistics + percentile/verdict for a metric time series."""
    clean = [v for v in values if v is not None]

    if current is None:
        return {
            "current": None,
            "assessment": "unavailable",
            "verdict": "No current value available for this metric.",
        }

    if len(clean) < 4:
        return {
            "current": round(current, 4),
            "assessment": "insufficient_history",
            "verdict": f"Not enough history to judge yet — only {len(clean)} quarter(s) available.",
            "quarters_available": len(clean),
        }

    mean_v = statistics.mean(clean)
    median_v = statistics.median(clean)
    min_v = min(clean)
    max_v = max(clean)
    stdev_v = statistics.stdev(clean) if len(clean) > 1 else 0
    z_score = round((current - mean_v) / stdev_v, 2) if stdev_v > 0 else None

    count_below_or_equal = sum(1 for v in clean if v <= current)
    percentile = round(100 * count_below_or_equal / len(clean))

    effective_pct = percentile if direction == "lower_is_cheaper" else 100 - percentile

    if effective_pct < 25:
        assessment = "cheap"
    elif effective_pct > 75:
        assessment = "expensive"
    else:
        assessment = "fair"

    # cheapness_pct: 0 = most expensive observed, 100 = cheapest observed
    cheapness_pct = 100 - percentile if direction == "lower_is_cheaper" else percentile

    # Use natural directional language per metric type. Valuation multiples read naturally as
    # "cheaper/more expensive". Returns/yields read naturally as "higher/lower" — saying "ROIC is
    # cheaper than 80% of history" is technically right but jarring to retail investors.
    if direction == "lower_is_cheaper":
        if assessment == "cheap":
            verdict = f"Cheaper than {cheapness_pct}% of its last 5 years of history."
        elif assessment == "expensive":
            verdict = f"More expensive than {100 - cheapness_pct}% of its last 5 years of history."
        else:
            verdict = "Around the middle of its last 5 years of history."
    else:  # higher_is_cheaper — returns and yields
        if assessment == "cheap":
            verdict = f"Higher than {cheapness_pct}% of its last 5 years of history (good for the investor)."
        elif assessment == "expensive":
            verdict = f"Lower than {100 - cheapness_pct}% of its last 5 years of history (worse than usual)."
        else:
            verdict = "Around the middle of its last 5 years of history."

    return {
        "current": round(current, 4),
        "min": round(min_v, 4),
        "max": round(max_v, 4),
        "mean": round(mean_v, 4),
        "median": round(median_v, 4),
        "percentile": percentile,
        "z_score": z_score,
        "assessment": assessment,
        "verdict": verdict,
        "quarters_available": len(clean),
    }


def _derive_pb_ratio(item: Dict) -> Optional[float]:
    """Compute Price-to-Book from market_cap and balance_sheet.total_equity."""
    market_cap = _safe_float(item.get('market_valuation', {}).get('market_cap'))
    total_equity = _safe_float(item.get('balance_sheet', {}).get('total_equity'))
    if not market_cap or not total_equity or total_equity <= 0:
        return None
    return round(market_cap / total_equity, 4)


def _extract_metric(item: Dict, category: str, metric: str) -> Optional[float]:
    """Extract a numeric metric from a DynamoDB item."""
    cat_data = item.get(category, {})
    if not cat_data or not isinstance(cat_data, dict):
        return None
    return _safe_float(cat_data.get(metric))


# In-memory cache for full table scan results (avoids repeated 19s scans within one Lambda invocation)
_latest_cache: Optional[Dict[str, Dict]] = None
_latest_cache_time: float = 0
_CACHE_TTL_SECONDS = 300  # 5 minutes


def clear_latest_cache():
    """Clear the in-memory cache. Useful for testing."""
    global _latest_cache, _latest_cache_time
    _latest_cache = None
    _latest_cache_time = 0


def _get_latest_per_ticker(tickers: Optional[List[str]] = None) -> Dict[str, Dict]:
    """
    Get the most recent quarter for each ticker from metrics-history.

    If tickers is None, scans the full table (for screening/ranking).
    Uses an in-memory cache with 5-min TTL to avoid repeated scans
    within the same Lambda invocation.

    If tickers is a list of ≤20, queries each ticker individually (faster).
    """
    global _latest_cache, _latest_cache_time
    import time as _time

    if tickers and len(tickers) <= 20:
        # Query each ticker individually — faster for small lists
        latest = {}
        for ticker in tickers:
            resp = metrics_table.query(
                KeyConditionExpression=Key('ticker').eq(ticker),
                ScanIndexForward=False,
                Limit=1
            )
            if resp.get('Items'):
                latest[ticker] = resp['Items'][0]
        return latest

    # Check cache for full scan
    now = _time.time()
    if _latest_cache is not None and (now - _latest_cache_time) < _CACHE_TTL_SECONDS:
        logger.info(f"Using cached scan results ({len(_latest_cache)} tickers, age={now - _latest_cache_time:.0f}s)")
        if tickers is None:
            return dict(_latest_cache)
        ticker_set = set(tickers)
        return {t: d for t, d in _latest_cache.items() if t in ticker_set}

    # Full scan
    logger.info("Performing full metrics-history scan (cache miss or expired)")
    latest = {}
    response = metrics_table.scan()
    for item in response.get('Items', []):
        t = item.get('ticker', '')
        fd = item.get('fiscal_date', '')
        if t and fd and (t not in latest or fd > latest[t].get('fiscal_date', '')):
            latest[t] = item

    while 'LastEvaluatedKey' in response:
        response = metrics_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
        for item in response.get('Items', []):
            t = item.get('ticker', '')
            fd = item.get('fiscal_date', '')
            if t and fd and (t not in latest or fd > latest[t].get('fiscal_date', '')):
                latest[t] = item

    # Filter to SP500 and cache
    sp500_set = set(SP500_TICKERS)
    sp500_latest = {t: d for t, d in latest.items() if t in sp500_set}

    _latest_cache = sp500_latest
    _latest_cache_time = now
    logger.info(f"Cached {len(sp500_latest)} tickers")

    if tickers is None:
        return dict(sp500_latest)

    ticker_set = set(tickers)
    return {t: d for t, d in sp500_latest.items() if t in ticker_set}


# =============================================================================
# METRIC RESOLUTION — maps user-friendly names to category.metric paths
# =============================================================================

METRIC_MAP = {
    # Revenue & Profit
    'revenue': ('revenue_profit', 'revenue'),
    'net_income': ('revenue_profit', 'net_income'),
    'gross_margin': ('revenue_profit', 'gross_margin'),
    'operating_margin': ('revenue_profit', 'operating_margin'),
    'net_margin': ('revenue_profit', 'net_margin'),
    'revenue_growth_yoy': ('revenue_profit', 'revenue_growth_yoy'),
    'eps': ('revenue_profit', 'eps'),
    'roe': ('revenue_profit', 'roe'),
    # Cash Flow
    'fcf_margin': ('cashflow', 'fcf_margin'),
    'free_cash_flow': ('cashflow', 'free_cash_flow'),
    'operating_cash_flow': ('cashflow', 'operating_cash_flow'),
    'capex_intensity': ('cashflow', 'capex_intensity'),
    'fcf_payout_ratio': ('cashflow', 'fcf_payout_ratio'),
    # Debt & Leverage
    'debt_to_equity': ('debt_leverage', 'debt_to_equity'),
    'current_ratio': ('debt_leverage', 'current_ratio'),
    'interest_coverage': ('debt_leverage', 'interest_coverage'),
    'net_debt_to_ebitda': ('debt_leverage', 'net_debt_to_ebitda'),
    # Valuation
    'roic': ('valuation', 'roic'),
    'roa': ('valuation', 'roa'),
    'asset_turnover': ('valuation', 'asset_turnover'),
    # Earnings Quality
    'sbc_to_revenue_pct': ('earnings_quality', 'sbc_to_revenue_pct'),
    # Earnings Events
    'eps_surprise_pct': ('earnings_events', 'eps_surprise_pct'),
    # Dividend
    'dividend_yield': ('dividend', 'dividend_yield'),
    'dps': ('dividend', 'dps'),
    # Market Valuation (TTM multiples)
    'pe_ratio': ('market_valuation', 'pe_ratio'),
    'ev_to_ebitda': ('market_valuation', 'ev_to_ebitda'),
    'ev_to_sales': ('market_valuation', 'ev_to_sales'),
    'ev_to_fcf': ('market_valuation', 'ev_to_fcf'),
    'price_to_fcf': ('market_valuation', 'price_to_fcf'),
    'market_cap': ('market_valuation', 'market_cap'),
    'enterprise_value': ('market_valuation', 'enterprise_value'),
    'earnings_yield': ('market_valuation', 'earnings_yield'),
    'fcf_yield': ('market_valuation', 'fcf_yield'),
}


VALUATION_METRIC_META = {
    "pe_ratio": {
        "label": "Price-to-Earnings (P/E)",
        "plain_english": "How many years of profit it would take to earn back the stock price. Lower = cheaper.",
        "source": ("market_valuation", "pe_ratio"),
        "direction": "lower_is_cheaper",
    },
    "pb_ratio": {
        "label": "Price-to-Book (P/B)",
        "plain_english": "How the stock price compares to the company's net worth on paper. Below 1 means you're paying less than the company's accounting value.",
        "source": "derived_pb",
        "direction": "lower_is_cheaper",
    },
    "ev_to_ebitda": {
        "label": "Enterprise Value / EBITDA",
        "plain_english": "Total company value (stock + debt - cash) compared to its cash profit from operations. Popular with pros because it ignores debt differences.",
        "source": ("market_valuation", "ev_to_ebitda"),
        "direction": "lower_is_cheaper",
    },
    "price_to_fcf": {
        "label": "Price / Free Cash Flow",
        "plain_english": "Stock price compared to the cash profit per share after the business pays its bills.",
        "source": "derived_price_to_fcf",
        "direction": "lower_is_cheaper",
    },
    "earnings_yield": {
        "label": "Earnings Yield",
        "plain_english": "Profit you'd earn per dollar invested, expressed like an interest rate. Higher is better — it's the flip side of P/E.",
        "source": ("market_valuation", "earnings_yield"),
        "direction": "higher_is_cheaper",
    },
    "fcf_yield": {
        "label": "Free Cash Flow Yield",
        "plain_english": "Actual cash return per dollar invested. Higher is better — this is money the business could return to you.",
        "source": ("market_valuation", "fcf_yield"),
        "direction": "higher_is_cheaper",
    },
    "roic": {
        "label": "Return on Invested Capital",
        "plain_english": "How efficiently the company turns every dollar of investor money into new profit. Higher is better — a sign of a well-run business.",
        "source": ("valuation", "roic"),
        "direction": "higher_is_cheaper",
    },
    "roe": {
        "label": "Return on Equity",
        "plain_english": "Profit earned for every dollar of shareholder money. Higher is better, but watch for high debt inflating it.",
        "source": ("revenue_profit", "roe"),
        "direction": "higher_is_cheaper",
    },
    "roa": {
        "label": "Return on Assets",
        "plain_english": "Profit earned for every dollar of company assets. Higher is better and harder to fake with debt.",
        "source": ("valuation", "roa"),
        "direction": "higher_is_cheaper",
    },
}


def _resolve_metric(metric_name: str):
    """Resolve a metric name to (category, metric) tuple."""
    # Direct match
    if metric_name in METRIC_MAP:
        return METRIC_MAP[metric_name]
    # Try with category.metric format
    parts = metric_name.split('.', 1)
    if len(parts) == 2:
        return (parts[0], parts[1])
    return None


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================

def _screen_stocks(params: Dict) -> Dict:
    """Filter S&P 500 companies by metric thresholds."""
    metric_name = params.get('metric', '')
    operator = params.get('operator', '>')
    value = params.get('value')
    sector = params.get('sector')
    limit = min(params.get('limit', 20), 50)

    if not metric_name or value is None:
        return {"success": False, "error": "metric and value are required"}

    resolved = _resolve_metric(metric_name)
    if not resolved:
        return {"success": False, "error": f"Unknown metric: {metric_name}. Available: {', '.join(sorted(METRIC_MAP.keys()))}"}

    category, metric = resolved
    threshold = float(value)


    latest = _get_latest_per_ticker()
    matches = []

    for ticker, item in latest.items():
        # Sector filter
        if sector:
            ticker_sector = SP500_SECTORS.get(ticker, {}).get('sector', '')
            if ticker_sector.lower() != sector.lower():
                continue

        val = _extract_metric(item, category, metric)
        if val is None:
            continue

        # Apply operator
        if operator == '>' and val > threshold:
            matches.append((ticker, val))
        elif operator == '>=' and val >= threshold:
            matches.append((ticker, val))
        elif operator == '<' and val < threshold:
            matches.append((ticker, val))
        elif operator == '<=' and val <= threshold:
            matches.append((ticker, val))
        elif operator == '=' and abs(val - threshold) < 0.01:
            matches.append((ticker, val))

    # Sort by metric value descending
    matches.sort(key=lambda x: x[1], reverse=(operator in ('>', '>=')))

    total_matches = len(matches)
    matches = matches[:limit]

    return {
        "success": True,
        "metric": metric_name,
        "operator": operator,
        "value": threshold,
        "sector_filter": sector,
        "total_matches": total_matches,
        "showing": len(matches),
        "companies": [
            {
                "ticker": t,
                "name": SP500_SECTORS.get(t, {}).get('name', t),
                "sector": SP500_SECTORS.get(t, {}).get('sector', 'Unknown'),
                metric_name: round(v, 2)
            }
            for t, v in matches
        ]
    }


def _get_sector_overview(params: Dict) -> Dict:
    """Get sector-level aggregate data."""
    sector = params.get('sector')

    if sector:
        # Single sector
        resp = aggregates_table.get_item(
            Key={'aggregate_type': 'SECTOR', 'aggregate_key': sector}
        )
        item = resp.get('Item')
        if not item:
            return {"success": False, "error": f"Sector '{sector}' not found"}
        return {"success": True, "sector": _clean_aggregate(item)}
    else:
        # All sectors
        resp = aggregates_table.query(
            KeyConditionExpression=Key('aggregate_type').eq('SECTOR')
        )
        sectors = [_clean_aggregate(item) for item in resp.get('Items', [])]
        sectors.sort(key=lambda s: s.get('totals', {}).get('revenue', 0), reverse=True)
        return {"success": True, "sectors": sectors, "count": len(sectors)}


def _get_top_companies(params: Dict) -> Dict:
    """Rank S&P 500 companies by a specified metric.

    Tries pre-computed RANKING items from sp500-aggregates first (sub-second).
    Falls back to full metrics-history scan if no ranking exists or sector filter needed.
    """
    metric_name = params.get('metric', '')
    n = min(params.get('n', 10), 50)
    sector = params.get('sector')
    sort_order = params.get('sort', 'desc')  # 'desc' (highest first) or 'asc' (lowest first)

    if not metric_name:
        return {"success": False, "error": "metric is required"}

    resolved = _resolve_metric(metric_name)
    if not resolved:
        return {"success": False, "error": f"Unknown metric: {metric_name}. Available: {', '.join(sorted(METRIC_MAP.keys()))}"}

    category, metric = resolved
    ascending = (sort_order == 'asc')

    # Try pre-computed ranking first (no sector filter — rankings are index-wide)
    if not sector:
        ranking_key = f"{metric}_asc" if ascending else metric
        ranking = _read_ranking(ranking_key)
        if ranking:
            entries = ranking.get('rankings', [])[:n]
            return {
                "success": True,
                "metric": metric_name,
                "sort": sort_order,
                "sector_filter": None,
                "total_companies": ranking.get('total_with_data', 0),
                "showing": len(entries),
                "source": "pre-computed",
                "rankings": [
                    {
                        "rank": e['rank'],
                        "ticker": e['ticker'],
                        "name": e['name'],
                        "sector": e['sector'],
                        metric_name: e['value']
                    }
                    for e in entries
                ]
            }

    # Fallback: full scan (sector filter or no pre-computed ranking)

    latest = _get_latest_per_ticker()
    ranked = []

    for ticker, item in latest.items():
        if sector:
            ticker_sector = SP500_SECTORS.get(ticker, {}).get('sector', '')
            if ticker_sector.lower() != sector.lower():
                continue

        val = _extract_metric(item, category, metric)
        if val is not None:
            ranked.append((ticker, val))

    ranked.sort(key=lambda x: x[1], reverse=(not ascending))
    top = ranked[:n]

    return {
        "success": True,
        "metric": metric_name,
        "sector_filter": sector,
        "total_companies": len(ranked),
        "showing": len(top),
        "source": "scan",
        "rankings": [
            {
                "rank": i + 1,
                "ticker": t,
                "name": SP500_SECTORS.get(t, {}).get('name', t),
                "sector": SP500_SECTORS.get(t, {}).get('sector', 'Unknown'),
                metric_name: round(v, 2)
            }
            for i, (t, v) in enumerate(top)
        ]
    }


def _get_index_snapshot(params: Dict) -> Dict:
    """Get overall S&P 500 index-level metrics."""
    resp = aggregates_table.get_item(
        Key={'aggregate_type': 'INDEX', 'aggregate_key': 'OVERALL'}
    )
    item = resp.get('Item')
    if not item:
        return {"success": False, "error": "Index snapshot not available. Run sp500_aggregator first."}

    return {"success": True, "index": _clean_aggregate(item)}


def _get_company_profile(params: Dict) -> Dict:
    """Get a single company's metrics with sector context."""
    ticker = params.get('ticker', '').upper()
    if not ticker:
        return {"success": False, "error": "ticker is required"}


    # Get latest quarter for this ticker
    resp = metrics_table.query(
        KeyConditionExpression=Key('ticker').eq(ticker),
        ScanIndexForward=False,
        Limit=1
    )
    items = resp.get('Items', [])
    if not items:
        return {"success": False, "error": f"No data found for {ticker}"}

    item = items[0]
    company_info = SP500_SECTORS.get(ticker, {})
    sector_name = company_info.get('sector', 'Unknown')

    # Get sector aggregate for context
    sector_resp = aggregates_table.get_item(
        Key={'aggregate_type': 'SECTOR', 'aggregate_key': sector_name}
    )
    sector_agg = sector_resp.get('Item', {})

    # Build profile
    profile = {
        "ticker": ticker,
        "name": company_info.get('name', ticker),
        "sector": sector_name,
        "industry": company_info.get('industry', 'Unknown'),
        "fiscal_date": item.get('fiscal_date'),
        "fiscal_quarter": item.get('fiscal_quarter'),
    }

    # Add key metrics from each category
    for category in ['revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
                     'earnings_quality', 'dilution', 'valuation', 'market_valuation']:
        cat_data = item.get(category, {})
        if cat_data:
            profile[category] = {k: _safe_float(v) for k, v in cat_data.items() if v is not None}

    # Add earnings events if available
    ee = item.get('earnings_events', {})
    if ee:
        profile['earnings_events'] = {k: _safe_float(v) if k != 'earnings_date' else v
                                       for k, v in ee.items() if v is not None}

    # Add dividend if available
    div = item.get('dividend', {})
    if div:
        profile['dividend'] = {k: _safe_float(v) if k != 'frequency' else v
                                for k, v in div.items() if v is not None}

    # Add sector context
    if sector_agg:
        sector_metrics = sector_agg.get('metrics', {})
        profile['sector_context'] = {
            'company_count': sector_agg.get('company_count'),
            'sector_medians': {
                metric: _safe_float(data.get('median'))
                for metric, data in sector_metrics.items()
                if isinstance(data, dict)
            }
        }

    return {"success": True, "profile": profile}


def _compare_companies(params: Dict) -> Dict:
    """Compare 2-10 companies side by side."""
    tickers = params.get('tickers', [])
    metric_type = params.get('metric_type', 'all')

    if not tickers or len(tickers) < 2:
        return {"success": False, "error": "At least 2 tickers required"}
    if len(tickers) > 10:
        return {"success": False, "error": "Maximum 10 tickers allowed"}


    tickers = [t.upper() for t in tickers]
    latest = _get_latest_per_ticker(tickers)

    categories = ['revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
                  'earnings_quality', 'dilution', 'valuation', 'market_valuation']
    if metric_type != 'all':
        categories = [c for c in categories if c == metric_type]

    comparison = {}
    not_found = []
    for ticker in tickers:
        item = latest.get(ticker)
        if not item:
            not_found.append(ticker)
            continue

        company_data = {
            "name": SP500_SECTORS.get(ticker, {}).get('name', ticker),
            "sector": SP500_SECTORS.get(ticker, {}).get('sector', 'Unknown'),
            "fiscal_date": item.get('fiscal_date'),
        }
        for cat in categories:
            cat_data = item.get(cat, {})
            if cat_data:
                company_data[cat] = {k: _safe_float(v) for k, v in cat_data.items() if v is not None}

        comparison[ticker] = company_data

    result = {
        "success": True,
        "tickers_compared": list(comparison.keys()),
        "metric_type": metric_type,
        "comparison": comparison,
    }
    if not_found:
        result["tickers_not_found"] = not_found
    return result


def _get_metric_trend(params: Dict) -> Dict:
    """Get quarterly trajectory of a metric for one company."""
    ticker = params.get('ticker', '').upper()
    metric_name = params.get('metric', '')
    category = params.get('category', '')
    quarters = min(params.get('quarters', 20), 20)

    if not ticker:
        return {"success": False, "error": "ticker is required"}
    if not metric_name:
        return {"success": False, "error": "metric is required"}

    # Resolve metric
    if category:
        resolved = (category, metric_name)
    else:
        resolved = _resolve_metric(metric_name)

    if not resolved:
        return {"success": False, "error": f"Unknown metric: {metric_name}. Available: {', '.join(sorted(METRIC_MAP.keys()))}"}

    cat, met = resolved

    # Query all quarters for this ticker
    resp = metrics_table.query(
        KeyConditionExpression=Key('ticker').eq(ticker),
        ScanIndexForward=True
    )
    items = resp.get('Items', [])

    if not items:
        return {"success": False, "error": f"No data found for {ticker}"}

    # Take the most recent N quarters
    items = items[-quarters:]

    trend = []
    for item in items:
        val = _extract_metric(item, cat, met)
        trend.append({
            "fiscal_date": item.get('fiscal_date'),
            "fiscal_quarter": item.get('fiscal_quarter'),
            "fiscal_year": _safe_float(item.get('fiscal_year')),
            "value": round(val, 4) if val is not None else None,
        })

    return {
        "success": True,
        "ticker": ticker,
        "metric": metric_name,
        "category": cat,
        "quarters": len(trend),
        "trend": trend,
    }


def _get_historical_valuation(params: Dict) -> Dict:
    """Get historical valuation percentiles for a single ticker across 9 metrics."""
    ticker = params.get('ticker', '').upper()
    if not ticker:
        return {"success": False, "error": "ticker is required"}

    # Clamp to [1, 20] — prevents quarters=0 from triggering Python's `items[-0:]` quirk
    # (which returns the full list instead of an empty slice) and rejects negative values.
    quarters = max(1, min(int(params.get('quarters', 20)), 20))

    resp = metrics_table.query(
        KeyConditionExpression=Key('ticker').eq(ticker),
        ScanIndexForward=True
    )
    items = resp.get('Items', [])

    if not items:
        return {"success": False, "error": f"No data found for {ticker}. This tool only supports S&P 500 tickers."}

    items = items[-quarters:]

    # Build time series per metric
    series_map: Dict[str, List[Optional[float]]] = {k: [] for k in VALUATION_METRIC_META}

    for item in items:
        for metric_key, meta in VALUATION_METRIC_META.items():
            source = meta['source']
            if isinstance(source, tuple):
                cat, field = source
                val = _safe_float(item.get(cat, {}).get(field))
            elif source == "derived_pb":
                val = _derive_pb_ratio(item)
            elif source == "derived_price_to_fcf":
                # fcf_yield is stored as a percent (e.g. 4.0 = 4%), so P/FCF = 100 / fcf_yield.
                fcf_yield = _safe_float(item.get('market_valuation', {}).get('fcf_yield'))
                if fcf_yield and fcf_yield > 0:
                    val = round(100.0 / fcf_yield, 4)
                else:
                    val = None
            else:
                val = None
            series_map[metric_key].append(val)

    # Compute current (last non-None) and stats for each metric
    metrics_out: Dict[str, Dict] = {}
    for metric_key, meta in VALUATION_METRIC_META.items():
        series = series_map[metric_key]
        current: Optional[float] = None
        for v in reversed(series):
            if v is not None:
                current = v
                break

        stats = _compute_metric_stats(series, current, meta['direction'])
        entry = {
            "label": meta['label'],
            "plain_english": meta['plain_english'],
            "direction": meta['direction'],
        }
        entry.update(stats)
        metrics_out[metric_key] = entry

    # Sector context
    company_info = SP500_SECTORS.get(ticker, {})
    sector_name = company_info.get('sector', 'Unknown')

    sector_agg: Dict = {}
    try:
        sector_resp = aggregates_table.get_item(
            Key={'aggregate_type': 'SECTOR', 'aggregate_key': sector_name}
        )
        sector_agg = sector_resp.get('Item', {}) or {}
    except Exception as e:
        logger.warning(f"Failed to load sector aggregate for {sector_name}: {e}")

    sector_metrics = sector_agg.get('metrics', {}) if isinstance(sector_agg, dict) else {}
    sector_medians: Dict[str, Optional[float]] = {}
    for metric_key in VALUATION_METRIC_META:
        entry = sector_metrics.get(metric_key) if isinstance(sector_metrics, dict) else None
        if isinstance(entry, dict):
            median_val = _safe_float(entry.get('median'))
            if median_val is not None:
                sector_medians[metric_key] = median_val

    return {
        "success": True,
        "ticker": ticker,
        "name": company_info.get('name', ticker),
        "sector": sector_name,
        "quarters_analyzed": len(items),
        "fiscal_date_range": {
            "start": items[0].get('fiscal_date'),
            "end": items[-1].get('fiscal_date'),
        },
        "metrics": metrics_out,
        "sector_context": {
            "sector": sector_name,
            "company_count": _safe_float(sector_agg.get('company_count')) if sector_agg else None,
            "sector_medians": sector_medians,
        },
    }



def _get_earnings_surprises(params: Dict) -> Dict:
    """Get companies ranked by EPS surprise — biggest beats or worst misses.

    Tries pre-computed RANKING items first (sub-second).
    Falls back to full scan if no ranking exists or sector filter needed.
    """
    sort_order = params.get('sort', 'best')  # 'best' or 'worst'
    n = min(params.get('n', 10), 50)
    sector = params.get('sector')

    # Try pre-computed ranking first (no sector filter)
    if not sector:
        ranking_key = 'eps_surprise_pct' if sort_order == 'best' else 'eps_surprise_pct_asc'
        ranking = _read_ranking(ranking_key)
        if ranking:
            entries = ranking.get('rankings', [])[:n]
            return {
                "success": True,
                "sort": sort_order,
                "sector_filter": None,
                "total_with_earnings": ranking.get('total_with_data', 0),
                "showing": len(entries),
                "source": "pre-computed",
                "surprises": [
                    {
                        "ticker": e['ticker'],
                        "name": e['name'],
                        "sector": e['sector'],
                        "eps_surprise_pct": e['value'],
                    }
                    for e in entries
                ]
            }

    # Fallback: full scan

    latest = _get_latest_per_ticker()
    surprises = []

    for ticker, item in latest.items():
        if sector:
            ticker_sector = SP500_SECTORS.get(ticker, {}).get('sector', '')
            if ticker_sector.lower() != sector.lower():
                continue

        ee = item.get('earnings_events', {})
        if not ee:
            continue

        surprise = _safe_float(ee.get('eps_surprise_pct'))
        if surprise is None:
            continue

        surprises.append({
            "ticker": ticker,
            "name": SP500_SECTORS.get(ticker, {}).get('name', ticker),
            "sector": SP500_SECTORS.get(ticker, {}).get('sector', 'Unknown'),
            "eps_actual": _safe_float(ee.get('eps_actual')),
            "eps_estimated": _safe_float(ee.get('eps_estimated')),
            "eps_surprise_pct": round(surprise, 2),
            "eps_beat": bool(ee.get('eps_beat')),
            "earnings_date": ee.get('earnings_date'),
        })

    reverse = (sort_order == 'best')
    surprises.sort(key=lambda x: x['eps_surprise_pct'], reverse=reverse)
    top = surprises[:n]

    return {
        "success": True,
        "sort": sort_order,
        "sector_filter": sector,
        "total_with_earnings": len(surprises),
        "showing": len(top),
        "source": "scan",
        "surprises": top,
    }


def _compare_sectors(params: Dict) -> Dict:
    """Compare 2-5 sectors side by side."""
    sectors = params.get('sectors', [])
    metrics = params.get('metrics')  # Optional: specific metrics to compare

    if not sectors or len(sectors) < 2:
        return {"success": False, "error": "At least 2 sectors required"}
    if len(sectors) > 5:
        return {"success": False, "error": "Maximum 5 sectors allowed"}

    comparison = {}
    not_found = []

    for sector in sectors:
        resp = aggregates_table.get_item(
            Key={'aggregate_type': 'SECTOR', 'aggregate_key': sector}
        )
        item = resp.get('Item')
        if not item:
            not_found.append(sector)
            continue

        sector_data = {
            "company_count": item.get('company_count'),
            "earnings_summary": _clean_dict(item.get('earnings_summary', {})),
            "dividend_summary": _clean_dict(item.get('dividend_summary', {})),
        }

        # Add metrics (filtered if specific metrics requested)
        all_metrics = item.get('metrics', {})
        if metrics:
            sector_data["metrics"] = {
                m: _clean_dict(all_metrics.get(m, {}))
                for m in metrics if m in all_metrics
            }
        else:
            sector_data["metrics"] = {
                m: _clean_dict(data)
                for m, data in all_metrics.items()
                if isinstance(data, dict)
            }

        comparison[sector] = sector_data

    result = {
        "success": True,
        "sectors_compared": list(comparison.keys()),
        "comparison": comparison,
    }
    if not_found:
        result["sectors_not_found"] = not_found
    return result


# =============================================================================
# HELPERS
# =============================================================================

def _read_ranking(metric_name: str) -> Optional[Dict]:
    """Read a pre-computed ranking from sp500-aggregates table.

    Returns the ranking item if found, None otherwise.
    """
    try:
        resp = aggregates_table.get_item(
            Key={'aggregate_type': 'RANKING', 'aggregate_key': metric_name}
        )
        item = resp.get('Item')
        if item and item.get('rankings'):
            return _clean_aggregate(item)
        return None
    except Exception as e:
        logger.warning(f"Failed to read ranking for {metric_name}: {e}")
        return None


def _clean_aggregate(item: Dict) -> Dict:
    """Clean a DynamoDB aggregate item for JSON serialization."""
    cleaned = {}
    for key, value in item.items():
        if key in ('expires_at',):
            continue
        if isinstance(value, dict):
            cleaned[key] = _clean_dict(value)
        elif isinstance(value, Decimal):
            cleaned[key] = float(value) if value % 1 else int(value)
        elif isinstance(value, list):
            cleaned[key] = [_clean_dict(v) if isinstance(v, dict) else
                           (float(v) if isinstance(v, Decimal) else v) for v in value]
        else:
            cleaned[key] = value
    return cleaned


def _clean_dict(d: Dict) -> Dict:
    """Recursively convert Decimals in a dict."""
    if not isinstance(d, dict):
        return d
    cleaned = {}
    for k, v in d.items():
        if isinstance(v, Decimal):
            cleaned[k] = float(v) if v % 1 else int(v)
        elif isinstance(v, dict):
            cleaned[k] = _clean_dict(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_dict(i) if isinstance(i, dict) else
                         (float(i) if isinstance(i, Decimal) else i) for i in v]
        else:
            cleaned[k] = v
    return cleaned
