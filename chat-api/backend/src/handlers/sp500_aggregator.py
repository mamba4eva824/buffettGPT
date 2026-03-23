"""
S&P 500 Aggregate Analytics Lambda

Reads per-company data from metrics-history DynamoDB table,
computes sector-level and index-level aggregates, and writes
results to the sp500-aggregates table.

Aggregates include:
- Per-sector: medians for key metrics, top companies, company count
- Index-level: overall medians, sector weights, concentration
- Earnings: median EPS surprise %, % of companies beating estimates
- Dividends: median yield, % of payers, median payout ratio

Invocation: manual, after sp500_pipeline completes, or on schedule.
"""

import json
import logging
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

# Environment
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')

# DynamoDB
dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)
aggregates_table = dynamodb.Table(AGGREGATES_TABLE)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Compute and store S&P 500 aggregate analytics.

    Event payload options:
        {} — compute all aggregates (sector + index)
    """
    from investment_research.index_tickers import SP500_TICKERS, SP500_SECTORS

    logger.info("Starting S&P 500 aggregate computation")
    start = time.time()

    # Step 1: Scan metrics-history for latest quarter per ticker
    latest_data = _get_latest_quarters(SP500_TICKERS)
    logger.info(f"Retrieved latest quarter data for {len(latest_data)} tickers")

    # Step 2: Group by sector
    sector_data = _group_by_sector(latest_data, SP500_SECTORS)

    # Step 3: Compute per-sector aggregates
    sector_items = []
    for sector, tickers_data in sector_data.items():
        item = _compute_sector_aggregate(sector, tickers_data)
        sector_items.append(item)

    # Step 4: Compute index-level aggregate
    index_item = _compute_index_aggregate(latest_data, sector_items)

    # Step 5: Compute pre-computed rankings for key metrics
    ranking_items = _compute_rankings(latest_data, SP500_SECTORS)
    logger.info(f"Computed {len(ranking_items)} ranking items")

    # Step 6: Write to DynamoDB
    all_items = sector_items + [index_item] + ranking_items
    _write_aggregates(all_items)

    elapsed = time.time() - start
    result = {
        'sectors_computed': len(sector_items),
        'rankings_computed': len(ranking_items),
        'tickers_covered': len(latest_data),
        'elapsed_seconds': round(elapsed, 1),
        'computed_at': datetime.now().isoformat(),
    }
    logger.info(f"Aggregation complete: {json.dumps(result)}")
    return result


def _get_latest_quarters(tickers: list) -> Dict[str, Dict]:
    """
    Scan metrics-history to get the most recent quarter for each ticker.

    Uses a full table scan (PAY_PER_REQUEST handles this fine for ~10k items).
    """
    logger.info("Scanning metrics-history for latest quarters...")

    # Scan all items, keeping only the latest per ticker
    latest = {}
    scan_kwargs = {
        'ProjectionExpression': (
            'ticker, fiscal_date, fiscal_year, fiscal_quarter, currency, '
            'revenue_profit, cashflow, balance_sheet, debt_leverage, '
            'earnings_quality, dilution, valuation, earnings_events, dividend, '
            'market_valuation'
        ),
    }

    response = metrics_table.scan(**scan_kwargs)
    _process_scan_page(response['Items'], latest)

    while 'LastEvaluatedKey' in response:
        scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']
        response = metrics_table.scan(**scan_kwargs)
        _process_scan_page(response['Items'], latest)

    # Filter to only S&P 500 tickers
    sp500_set = set(tickers)
    return {t: d for t, d in latest.items() if t in sp500_set}


def _process_scan_page(items: list, latest: dict):
    """Keep only the most recent quarter per ticker."""
    for item in items:
        ticker = item.get('ticker', '')
        fiscal_date = item.get('fiscal_date', '')
        if not ticker or not fiscal_date:
            continue
        if ticker not in latest or fiscal_date > latest[ticker].get('fiscal_date', ''):
            latest[ticker] = item


def _group_by_sector(
    latest_data: Dict[str, Dict],
    sectors: Dict[str, Dict]
) -> Dict[str, List[Dict]]:
    """Group ticker data by sector."""
    grouped = defaultdict(list)
    for ticker, data in latest_data.items():
        sector_info = sectors.get(ticker, {})
        sector = sector_info.get('sector', 'Unknown')
        data['_ticker'] = ticker
        data['_company_name'] = sector_info.get('name', ticker)
        data['_industry'] = sector_info.get('industry', 'Unknown')
        grouped[sector].append(data)
    return dict(grouped)


def _safe_float(value) -> Optional[float]:
    """Convert DynamoDB Decimal/string/None to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _extract_metric(data: Dict, category: str, metric: str) -> Optional[float]:
    """Extract a numeric metric from a ticker's data."""
    cat_data = data.get(category, {})
    if not cat_data or not isinstance(cat_data, dict):
        return None
    return _safe_float(cat_data.get(metric))


def _compute_percentiles(values: List[float]) -> Dict[str, float]:
    """Compute median, P25, P75 for a list of values."""
    if not values:
        return {'median': None, 'p25': None, 'p75': None, 'count': 0}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return {
        'median': round(statistics.median(sorted_vals), 2),
        'p25': round(sorted_vals[max(0, n // 4 - 1)], 2) if n >= 4 else round(sorted_vals[0], 2),
        'p75': round(sorted_vals[min(n - 1, 3 * n // 4)], 2) if n >= 4 else round(sorted_vals[-1], 2),
        'count': n,
    }


# Metrics to aggregate across sectors
AGGREGATE_METRICS = [
    ('revenue_profit', 'revenue_growth_yoy', 'Revenue Growth YoY'),
    ('revenue_profit', 'gross_margin', 'Gross Margin'),
    ('revenue_profit', 'operating_margin', 'Operating Margin'),
    ('revenue_profit', 'net_margin', 'Net Margin'),
    ('revenue_profit', 'roe', 'ROE'),
    ('cashflow', 'fcf_margin', 'FCF Margin'),
    ('cashflow', 'capex_intensity', 'Capex Intensity'),
    ('debt_leverage', 'debt_to_equity', 'Debt/Equity'),
    ('debt_leverage', 'current_ratio', 'Current Ratio'),
    ('debt_leverage', 'interest_coverage', 'Interest Coverage'),
    ('valuation', 'roic', 'ROIC'),
    ('valuation', 'roa', 'ROA'),
    ('valuation', 'asset_turnover', 'Asset Turnover'),
    ('earnings_quality', 'sbc_to_revenue_pct', 'SBC/Revenue'),
    # Market Valuation (TTM multiples - only on latest quarter items)
    ('market_valuation', 'pe_ratio', 'P/E Ratio'),
    ('market_valuation', 'ev_to_ebitda', 'EV/EBITDA'),
    ('market_valuation', 'ev_to_sales', 'EV/Sales'),
    ('market_valuation', 'market_cap', 'Market Cap'),
]


def _compute_sector_aggregate(sector: str, tickers_data: List[Dict]) -> Dict:
    """Compute aggregate metrics for a single sector."""
    now = datetime.now()

    # Core metrics: percentiles
    metrics = {}
    for category, metric, label in AGGREGATE_METRICS:
        values = []
        for data in tickers_data:
            val = _extract_metric(data, category, metric)
            if val is not None:
                values.append(val)
        metrics[metric] = _compute_percentiles(values)

    # Top 5 companies by revenue
    revenue_ranked = []
    for data in tickers_data:
        rev = _extract_metric(data, 'revenue_profit', 'revenue')
        if rev is not None:
            revenue_ranked.append((data['_ticker'], data['_company_name'], rev))
    revenue_ranked.sort(key=lambda x: x[2], reverse=True)
    top_by_revenue = [{'ticker': t, 'name': n, 'revenue': r} for t, n, r in revenue_ranked[:5]]

    # Top 5 by FCF margin
    fcf_ranked = []
    for data in tickers_data:
        fcf = _extract_metric(data, 'cashflow', 'fcf_margin')
        if fcf is not None:
            fcf_ranked.append((data['_ticker'], data['_company_name'], fcf))
    fcf_ranked.sort(key=lambda x: x[2], reverse=True)
    top_by_fcf = [{'ticker': t, 'name': n, 'fcf_margin': f} for t, n, f in fcf_ranked[:5]]

    # Top 5 by revenue growth
    growth_ranked = []
    for data in tickers_data:
        g = _extract_metric(data, 'revenue_profit', 'revenue_growth_yoy')
        if g is not None:
            growth_ranked.append((data['_ticker'], data['_company_name'], g))
    growth_ranked.sort(key=lambda x: x[2], reverse=True)
    top_by_growth = [{'ticker': t, 'name': n, 'revenue_growth_yoy': g} for t, n, g in growth_ranked[:5]]

    # Earnings surprise summary
    eps_surprises = []
    eps_beats = 0
    eps_total = 0
    for data in tickers_data:
        surprise = _extract_metric(data, 'earnings_events', 'eps_surprise_pct')
        beat = data.get('earnings_events', {}).get('eps_beat')
        if surprise is not None:
            eps_surprises.append(surprise)
        if beat is not None:
            eps_total += 1
            if beat:
                eps_beats += 1

    earnings_summary = {
        'median_eps_surprise_pct': round(statistics.median(eps_surprises), 2) if eps_surprises else None,
        'pct_beat_eps': round(eps_beats / eps_total * 100, 1) if eps_total > 0 else None,
        'companies_with_earnings': eps_total,
    }

    # Dividend summary
    div_yields = []
    div_payers = 0
    payout_ratios = []
    for data in tickers_data:
        dy = _extract_metric(data, 'dividend', 'dividend_yield')
        if dy is not None and dy > 0:
            div_yields.append(dy)
            div_payers += 1
        pr = _extract_metric(data, 'cashflow', 'fcf_payout_ratio')
        if pr is not None and dy is not None and dy > 0:
            payout_ratios.append(pr)

    dividend_summary = {
        'median_yield': round(statistics.median(div_yields), 4) if div_yields else None,
        'pct_payers': round(div_payers / len(tickers_data) * 100, 1) if tickers_data else 0,
        'median_payout_ratio': round(statistics.median(payout_ratios), 1) if payout_ratios else None,
        'dividend_payers': div_payers,
    }

    # Sector totals
    total_revenue = sum(
        _extract_metric(d, 'revenue_profit', 'revenue') or 0 for d in tickers_data
    )
    total_net_income = sum(
        _extract_metric(d, 'revenue_profit', 'net_income') or 0 for d in tickers_data
    )

    return {
        'aggregate_type': 'SECTOR',
        'aggregate_key': sector,
        'company_count': len(tickers_data),
        'data_coverage': len(tickers_data),
        'metrics': metrics,
        'top_companies': {
            'by_revenue': top_by_revenue,
            'by_fcf_margin': top_by_fcf,
            'by_revenue_growth': top_by_growth,
        },
        'earnings_summary': earnings_summary,
        'dividend_summary': dividend_summary,
        'totals': {
            'revenue': total_revenue,
            'net_income': total_net_income,
        },
        'computed_at': now.isoformat(),
        'expires_at': int(now.timestamp()) + (7 * 24 * 60 * 60),  # 7 days
    }


def _compute_index_aggregate(
    latest_data: Dict[str, Dict],
    sector_items: List[Dict]
) -> Dict:
    """Compute index-level (overall S&P 500) aggregate."""
    now = datetime.now()
    all_tickers_data = list(latest_data.values())

    # Same metric percentiles as sectors
    metrics = {}
    for category, metric, label in AGGREGATE_METRICS:
        values = []
        for data in all_tickers_data:
            val = _extract_metric(data, category, metric)
            if val is not None:
                values.append(val)
        metrics[metric] = _compute_percentiles(values)

    # Sector weights by revenue
    sector_weights = {}
    total_revenue = sum(s.get('totals', {}).get('revenue', 0) for s in sector_items)
    for s in sector_items:
        sector_rev = s.get('totals', {}).get('revenue', 0)
        weight = round(sector_rev / total_revenue * 100, 1) if total_revenue > 0 else 0
        sector_weights[s['aggregate_key']] = {
            'revenue_weight_pct': weight,
            'company_count': s['company_count'],
        }

    # Concentration: top 10 companies by revenue
    revenue_list = []
    for data in all_tickers_data:
        rev = _extract_metric(data, 'revenue_profit', 'revenue')
        if rev:
            revenue_list.append((data.get('_ticker', ''), rev))
    revenue_list.sort(key=lambda x: x[1], reverse=True)
    top_10_revenue = sum(r for _, r in revenue_list[:10])
    concentration = {
        'top_10_revenue_pct': round(top_10_revenue / total_revenue * 100, 1) if total_revenue > 0 else 0,
        'top_10_tickers': [t for t, _ in revenue_list[:10]],
    }

    # Index-level earnings summary
    eps_surprises = []
    eps_beats = 0
    eps_total = 0
    for data in all_tickers_data:
        surprise = _extract_metric(data, 'earnings_events', 'eps_surprise_pct')
        beat = data.get('earnings_events', {}).get('eps_beat')
        if surprise is not None:
            eps_surprises.append(surprise)
        if beat is not None:
            eps_total += 1
            if beat:
                eps_beats += 1

    # Index-level dividend summary
    div_yields = []
    div_payers = 0
    for data in all_tickers_data:
        dy = _extract_metric(data, 'dividend', 'dividend_yield')
        if dy is not None and dy > 0:
            div_yields.append(dy)
            div_payers += 1

    return {
        'aggregate_type': 'INDEX',
        'aggregate_key': 'OVERALL',
        'company_count': len(all_tickers_data),
        'data_coverage': len(all_tickers_data),
        'metrics': metrics,
        'sector_weights': sector_weights,
        'concentration': concentration,
        'earnings_summary': {
            'median_eps_surprise_pct': round(statistics.median(eps_surprises), 2) if eps_surprises else None,
            'pct_beat_eps': round(eps_beats / eps_total * 100, 1) if eps_total > 0 else None,
            'companies_with_earnings': eps_total,
        },
        'dividend_summary': {
            'median_yield': round(statistics.median(div_yields), 4) if div_yields else None,
            'pct_payers': round(div_payers / len(all_tickers_data) * 100, 1) if all_tickers_data else 0,
            'dividend_payers': div_payers,
        },
        'totals': {
            'revenue': total_revenue,
        },
        'computed_at': now.isoformat(),
        'expires_at': int(now.timestamp()) + (7 * 24 * 60 * 60),
    }


# Metrics to pre-compute rankings for (most commonly queried)
RANKING_METRICS = [
    ('revenue_profit', 'revenue', False),              # Top by revenue (descending)
    ('revenue_profit', 'net_margin', False),            # Top by net margin
    ('revenue_profit', 'operating_margin', False),      # Top by operating margin
    ('revenue_profit', 'revenue_growth_yoy', False),    # Top by revenue growth
    ('revenue_profit', 'roe', False),                   # Top by ROE
    ('cashflow', 'fcf_margin', False),                  # Top by FCF margin
    ('debt_leverage', 'debt_to_equity', True),          # Lowest D/E (ascending)
    ('valuation', 'roic', False),                       # Top by ROIC
    ('dividend', 'dividend_yield', False),              # Top by dividend yield
    ('earnings_events', 'eps_surprise_pct', False),     # Best earnings beats
    ('earnings_events', 'eps_surprise_pct', True),      # Worst earnings misses
    ('earnings_quality', 'sbc_to_revenue_pct', True),   # Lowest SBC (ascending)
    # Market Valuation
    ('market_valuation', 'pe_ratio', True),              # Lowest P/E (cheapest)
    ('market_valuation', 'ev_to_ebitda', True),          # Lowest EV/EBITDA (cheapest)
    ('market_valuation', 'market_cap', False),           # Largest market cap
]


def _compute_rankings(
    latest_data: Dict[str, Dict],
    sectors: Dict[str, Dict],
    top_n: int = 50
) -> List[Dict]:
    """
    Compute pre-computed rankings for key metrics.

    Stores as RANKING items in sp500-aggregates:
      PK: "RANKING", SK: metric_name (e.g., "fcf_margin", "eps_surprise_pct_worst")

    Each item contains the top 50 companies sorted by that metric.
    """
    now = datetime.now()
    ranking_items = []

    for category, metric, ascending in RANKING_METRICS:
        values = []
        for ticker, data in latest_data.items():
            val = _extract_metric(data, category, metric)
            if val is not None:
                company_info = sectors.get(ticker, {})
                values.append({
                    'ticker': ticker,
                    'name': company_info.get('name', ticker),
                    'sector': company_info.get('sector', 'Unknown'),
                    'value': round(val, 4),
                })

        # Sort
        values.sort(key=lambda x: x['value'], reverse=(not ascending))
        top = values[:top_n]

        # Build ranking key
        ranking_key = metric
        if ascending:
            ranking_key = f"{metric}_asc"

        # Add rank numbers
        for i, entry in enumerate(top):
            entry['rank'] = i + 1

        ranking_items.append({
            'aggregate_type': 'RANKING',
            'aggregate_key': ranking_key,
            'category': category,
            'metric': metric,
            'sort_order': 'ascending' if ascending else 'descending',
            'total_with_data': len(values),
            'showing': len(top),
            'rankings': top,
            'computed_at': now.isoformat(),
            'expires_at': int(now.timestamp()) + (7 * 24 * 60 * 60),
        })

    return ranking_items


def _write_aggregates(items: List[Dict]):
    """Batch write aggregate items to DynamoDB with Decimal conversion."""
    logger.info(f"Writing {len(items)} aggregate items to {AGGREGATES_TABLE}")
    with aggregates_table.batch_writer() as batch:
        for item in items:
            item_decimal = json.loads(
                json.dumps(item, default=str),
                parse_float=Decimal
            )
            batch.put_item(Item=item_decimal)
