"""
Earnings Update Lambda — Daily Automated Earnings Ingestion

Checks the FMP earnings calendar for S&P 500 companies that recently reported,
then fetches full financials + earnings + dividends + TTM valuations and updates
the metrics-history DynamoDB table via update_item (preserves existing attributes).

Runs twice daily via EventBridge:
  - 5:00 PM ET Mon-Fri — catches after-hours earnings reports
  - 9:30 AM ET Mon-Fri — catches pre-market earnings reports

Event payload options:
  {}                                — auto mode: check calendar, process recently reported
  {"tickers": ["AAPL", "MSFT"]}    — manual mode: skip calendar, process specific tickers
  {"lookback_days": 3}             — custom calendar lookback window (default: 2)
  {"include_upcoming": true}       — also return upcoming earnings in response

Response includes structured data for future notifications:
  {
    "tickers_checked": 12,
    "tickers_updated": ["AAPL", "MSFT"],
    "results": [{"ticker": "AAPL", "earnings_date": "...", "eps_beat": true, ...}],
    "upcoming": [{"ticker": "NVDA", "earnings_date": "2026-05-20", "eps_estimated": 1.75}]
  }

Environment Variables:
  FMP_SECRET_NAME              — Secrets Manager name for FMP API key
  METRICS_HISTORY_CACHE_TABLE  — DynamoDB table for quarterly metrics
  ENVIRONMENT                  — dev/staging/prod
  LOG_LEVEL                    — DEBUG/INFO/WARNING
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
import httpx

from utils.fmp_client import (
    get_financial_data,
    fetch_earnings,
    fetch_dividends,
    fetch_ttm_valuations,
)
from utils.feature_extractor import extract_quarterly_trends, prepare_metrics_for_cache, SUSPECT_EQUITY_TO_REVENUE_RATIO

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, log_level))

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
METRICS_TABLE = os.environ.get('METRICS_HISTORY_CACHE_TABLE', f'metrics-history-{ENVIRONMENT}')
AGGREGATES_TABLE = os.environ.get('SP500_AGGREGATES_TABLE', f'buffett-{ENVIRONMENT}-sp500-aggregates')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_RATE_LIMIT_DELAY = 0.5  # Seconds between FMP calls (300 calls/min limit)
FEED_TTL_DAYS = 90  # How long to keep earnings feed records
UPCOMING_LOOKAHEAD_DAYS = 30  # How far forward to query upcoming earnings

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------
dynamodb = boto3.resource('dynamodb')
metrics_table = dynamodb.Table(METRICS_TABLE)
aggregates_table = dynamodb.Table(AGGREGATES_TABLE)
secrets_client = boto3.client('secretsmanager')

_fmp_api_key = None


def _get_fmp_api_key() -> str:
    global _fmp_api_key
    if _fmp_api_key is None:
        response = secrets_client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        _fmp_api_key = secret['FMP_API_KEY']
    return _fmp_api_key


# ---------------------------------------------------------------------------
# Earnings Calendar
# ---------------------------------------------------------------------------
def _check_earnings_calendar(lookback_days: int = 2) -> Dict[str, List]:
    """
    Check FMP earnings calendar for S&P 500 tickers that recently reported.

    Queries FMP in weekly chunks to avoid the 4000-result API cap.
    A single 30-day query exceeds 4000 entries (all stocks, not just S&P 500),
    causing FMP to silently drop near-term dates.

    Returns dict with 'reported' (tickers with new earnings) and 'upcoming'.
    """
    from investment_research.index_tickers import SP500_TICKERS, to_fmp_format

    api_key = _get_fmp_api_key()
    sp500_fmp = {to_fmp_format(t): t for t in SP500_TICKERS}

    today = datetime.now()
    today_str = today.strftime('%Y-%m-%d')
    start = today - timedelta(days=lookback_days)
    end = today + timedelta(days=UPCOMING_LOOKAHEAD_DAYS)

    # Query in weekly chunks to stay under FMP's 4000-result cap
    url = "https://financialmodelingprep.com/stable/earnings-calendar"
    all_entries = []
    chunk_start = start
    with httpx.Client(timeout=30.0) as client:
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=7), end)
            response = client.get(url, params={
                'from': chunk_start.strftime('%Y-%m-%d'),
                'to': chunk_end.strftime('%Y-%m-%d'),
                'apikey': api_key,
            })
            response.raise_for_status()
            all_entries.extend(response.json())
            chunk_start = chunk_end + timedelta(days=1)
            time.sleep(FMP_RATE_LIMIT_DELAY)

    # Dedupe by (symbol, date) in case chunks overlap
    seen = set()
    reported = []
    upcoming = []

    for entry in all_entries:
        fmp_symbol = entry.get('symbol', '')
        if fmp_symbol not in sp500_fmp:
            continue

        earnings_date = entry.get('date', '')
        dedup_key = (fmp_symbol, earnings_date)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        original_ticker = sp500_fmp[fmp_symbol]
        record = {
            'ticker': original_ticker,
            'fmp_ticker': fmp_symbol,
            'earnings_date': earnings_date,
            'eps_estimated': entry.get('epsEstimated'),
            'eps_actual': entry.get('epsActual'),
            'revenue_estimated': entry.get('revenueEstimated'),
        }

        if earnings_date <= today_str:
            reported.append(record)
        else:
            upcoming.append(record)

    logger.info(f"Earnings calendar: {len(reported)} reported, {len(upcoming)} upcoming "
                f"(checked {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}, "
                f"{len(all_entries)} total FMP entries)")

    return {
        'reported': reported,
        'upcoming': sorted(upcoming, key=lambda x: x['earnings_date']),
    }


# ---------------------------------------------------------------------------
# Freshness Check — Skip Already-Processed Tickers
# ---------------------------------------------------------------------------
def _already_updated_since_earnings(ticker: str, earnings_date: str, fmp_eps_actual) -> bool:
    """
    Check if this ticker was already processed for the announced earnings cycle.

    Skip iff ALL three hold:
      1. FMP reports an eps_actual for the quarter (quarter has been reported).
      2. Stored earnings_events.earnings_date matches the announced cycle.
      3. Stored earnings_events.eps_actual is not None (we captured the actual).
    """
    if fmp_eps_actual is None:
        return False

    try:
        response = metrics_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('ticker').eq(ticker),
            ScanIndexForward=False,
            Limit=1,
            ProjectionExpression='ticker, earnings_events',
        )
        items = response.get('Items', [])
        if not items:
            return False

        ee = items[0].get('earnings_events', {}) or {}
        stored_date = ee.get('earnings_date', '') or ''
        if stored_date[:10] != earnings_date[:10]:
            return False

        if ee.get('eps_actual') is None:
            return False

        logger.debug(
            f"{ticker}: already updated for earnings_date={earnings_date} "
            f"(stored eps_actual={ee.get('eps_actual')})"
        )
        return True

    except Exception as e:
        logger.warning(f"Freshness check failed for {ticker}: {e}")
        return False  # On error, process the ticker


def _get_stored_max_fiscal_date(ticker: str) -> Optional[str]:
    """
    Return the latest fiscal_date already stored in metrics-history for this ticker,
    or None if the ticker has no existing rows (first-ever run).
    """
    try:
        response = metrics_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('ticker').eq(ticker),
            ScanIndexForward=False,
            Limit=1,
            ProjectionExpression='fiscal_date',
        )
        items = response.get('Items', [])
        if not items:
            return None
        return items[0].get('fiscal_date')
    except Exception as e:
        logger.warning(f"_get_stored_max_fiscal_date failed for {ticker}: {e}")
        return None


# ---------------------------------------------------------------------------
# Per-Ticker Processing
# ---------------------------------------------------------------------------
def _process_ticker(
    ticker: str,
    earnings_date: Optional[str] = None,
    full_reingest: bool = False,
) -> Dict[str, Any]:
    """
    Fetch full financials + earnings + dividends + TTM for a single ticker
    and update all categories in metrics-history via update_item.

    When earnings_date is provided, force-refreshes the FMP cache and validates
    fresh data reflects the reported quarter.

    When full_reingest is True, writes ALL 20 quarters (backward-compatible with
    the original batch-ingest behavior). When False (default), writes only the
    reported quarter after sanity + no-new-quarter gates.

    Returns a summary dict for the response.
    """
    from investment_research.index_tickers import to_fmp_format

    fmp_ticker = to_fmp_format(ticker)
    result = {'ticker': ticker, 'status': 'success'}

    # 1. Fetch financial data (income, balance sheet, cash flow)
    financial_data = get_financial_data(fmp_ticker, force_refresh=True)
    raw_financials = financial_data.get('raw_financials', {})
    if not raw_financials:
        result['status'] = 'no_financial_data'
        return result

    # Propagation-lag guard: verify FMP's fresh response reflects the reported quarter.
    # If earnings_date provided but FMP's latest income_statement is older than
    # earnings_date - 10 days, FMP hasn't propagated the 10-Q yet. Log + flag the result.
    if earnings_date:
        income_statements = raw_financials.get('income_statement', [])
        if income_statements:
            latest_date = income_statements[0].get('date', '')
            if latest_date and latest_date < earnings_date:
                from datetime import datetime as _dt
                try:
                    gap_days = (_dt.strptime(earnings_date[:10], '%Y-%m-%d') -
                                _dt.strptime(latest_date[:10], '%Y-%m-%d')).days
                    if gap_days > 10:
                        logger.warning(
                            f"{ticker}: FMP income_statement latest={latest_date} is "
                            f"{gap_days} days older than earnings_date={earnings_date} — "
                            f"FMP propagation lag, will retry next run"
                        )
                        result['status'] = 'fmp_propagation_lag'
                        result['latest_statement_date'] = latest_date
                        result['earnings_date'] = earnings_date
                        return result
                except ValueError:
                    pass  # Date parse errors fall through to normal processing

    currency = financial_data.get('currency_info', {}).get('code', 'USD')
    cache_key = financial_data.get('cache_key', f'v3:{ticker}:{datetime.now().year}')

    # 2. Extract quarterly trends (78 metrics across 7 categories)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # 3. Fetch earnings + dividends (always — this is the whole point)
    earnings_history = None
    dividend_history = None
    try:
        earnings_history = fetch_earnings(fmp_ticker)
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch earnings for {ticker}: {e}")

    try:
        dividend_history = fetch_dividends(fmp_ticker)
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch dividends for {ticker}: {e}")

    # 4. Prepare items (7 base categories + earnings_events + dividend)
    items = prepare_metrics_for_cache(
        ticker=ticker,
        quarterly_trends=quarterly_trends,
        currency=currency,
        source_cache_key=cache_key,
        earnings_history=earnings_history,
        dividend_history=dividend_history,
    )

    if not items:
        result['status'] = 'no_items_generated'
        return result

    # 5. Fetch TTM valuations and attach to latest quarter
    try:
        ttm = fetch_ttm_valuations(fmp_ticker)
        if ttm:
            latest_item = max(items, key=lambda x: x.get('fiscal_date', ''))
            latest_item['market_valuation'] = ttm
        time.sleep(FMP_RATE_LIMIT_DELAY)
    except Exception as e:
        logger.warning(f"Failed to fetch TTM for {ticker}: {e}")

    # 6. Narrow-scope write (default) OR full reingest (operator opt-in)
    latest_item = max(items, key=lambda x: x.get('fiscal_date', ''))

    if full_reingest:
        _update_items(items)
        logger.info(f"{ticker}: full reingest — wrote {len(items)} quarters")
    else:
        # Gate 1: Suspect-data sanity check on the reported quarter's balance sheet.
        # If equity is implausibly small relative to revenue, FMP's current-quarter
        # response is likely corrupted (tonight's SCHW crash source).
        balance_sheet = latest_item.get('balance_sheet', {}) or {}
        revenue_profit = latest_item.get('revenue_profit', {}) or {}
        total_equity = balance_sheet.get('total_equity')
        revenue = revenue_profit.get('revenue')

        if (total_equity is not None and revenue is not None
                and abs(revenue) > 0
                and abs(total_equity) < abs(revenue) * SUSPECT_EQUITY_TO_REVENUE_RATIO):
            logger.warning(
                f"{ticker}: suspect FMP balance sheet — equity={total_equity} vs "
                f"revenue={revenue} (ratio {abs(total_equity)/abs(revenue):.5f} < "
                f"{SUSPECT_EQUITY_TO_REVENUE_RATIO}); refusing to write"
            )
            result['status'] = 'fmp_suspect_data'
            result['latest_fiscal_date'] = latest_item.get('fiscal_date')
            result['total_equity'] = float(total_equity) if total_equity is not None else None
            result['revenue'] = float(revenue) if revenue is not None else None
            return result

        # Gate 2: No-new-quarter check — FMP may return the same fiscal_date we
        # already have stored. Distinguish three sub-cases via earnings_events.earnings_date:
        #   - Missing earnings_date → skip as fmp_earnings_date_missing
        #   - Mismatched earnings_date → skip as fmp_no_new_quarter (FMP lag)
        #   - Matched earnings_date → proceed (restatement / idempotent rewrite)
        if earnings_date:
            stored_max = _get_stored_max_fiscal_date(ticker)
            latest_fd = latest_item.get('fiscal_date')
            if stored_max and latest_fd == stored_max:
                ee = latest_item.get('earnings_events', {}) or {}
                stored_ee_date = (ee.get('earnings_date') or '')[:10]
                input_ed = earnings_date[:10]
                if not stored_ee_date:
                    logger.warning(
                        f"{ticker}: FMP latest fiscal_date={latest_fd} matches stored max, "
                        f"but earnings_events.earnings_date is missing — FMP press-release lag"
                    )
                    result['status'] = 'fmp_earnings_date_missing'
                    result['latest_fiscal_date'] = latest_fd
                    return result
                if stored_ee_date != input_ed:
                    logger.warning(
                        f"{ticker}: FMP latest fiscal_date={latest_fd} matches stored max, "
                        f"but earnings_events.earnings_date={stored_ee_date!r} does not match "
                        f"input earnings_date={input_ed!r} — FMP has not advanced past prior cycle"
                    )
                    result['status'] = 'fmp_no_new_quarter'
                    result['latest_fiscal_date'] = latest_fd
                    return result
                # Matched — proceed (restatement or idempotent re-write)

        _update_items([latest_item])
        logger.info(f"{ticker}: narrow-scope write — wrote 1 row ({latest_item.get('fiscal_date')})")

    # 7. Build result summary
    latest = max(items, key=lambda x: x.get('fiscal_date', ''))
    ee = latest.get('earnings_events', {})
    result.update({
        'quarters_written': len(items) if full_reingest else 1,
        'latest_fiscal_date': latest.get('fiscal_date'),
        'latest_fiscal_quarter': latest.get('fiscal_quarter'),
        'earnings_date': ee.get('earnings_date'),
        'eps_actual': float(ee['eps_actual']) if ee.get('eps_actual') is not None else None,
        'eps_estimated': float(ee['eps_estimated']) if ee.get('eps_estimated') is not None else None,
        'eps_beat': ee.get('eps_beat'),
        'eps_surprise_pct': float(ee['eps_surprise_pct']) if ee.get('eps_surprise_pct') is not None else None,
        'has_market_valuation': 'market_valuation' in latest,
    })

    return result


# ---------------------------------------------------------------------------
# DynamoDB update_item (safe writes — preserves existing attributes)
# ---------------------------------------------------------------------------
ALL_CATEGORIES = [
    'revenue_profit', 'cashflow', 'balance_sheet', 'debt_leverage',
    'earnings_quality', 'dilution', 'valuation',
    'earnings_events', 'dividend', 'market_valuation',
]
META_FIELDS = ['fiscal_year', 'fiscal_quarter', 'currency', 'source_cache_key', 'cached_at', 'expires_at']


def _update_items(items: List[Dict[str, Any]]) -> None:
    """
    Update items in metrics-history using update_item (not put_item).
    Preserves existing attributes not included in the current write.
    """
    for item in items:
        ticker = item.get('ticker')
        fiscal_date = item.get('fiscal_date')
        if not ticker or not fiscal_date:
            continue

        item_decimal = json.loads(
            json.dumps(item, default=str),
            parse_float=Decimal
        )

        set_parts = []
        attr_values = {}
        attr_names = {}

        for field in META_FIELDS:
            if field in item_decimal:
                safe_name = f'#{field}'
                safe_val = f':{field}'
                set_parts.append(f'{safe_name} = {safe_val}')
                attr_names[safe_name] = field
                attr_values[safe_val] = item_decimal[field]

        for category in ALL_CATEGORIES:
            if category in item_decimal:
                safe_name = f'#{category}'
                safe_val = f':{category}'
                set_parts.append(f'{safe_name} = {safe_val}')
                attr_names[safe_name] = category
                attr_values[safe_val] = item_decimal[category]

        if not set_parts:
            continue

        try:
            metrics_table.update_item(
                Key={'ticker': ticker, 'fiscal_date': fiscal_date},
                UpdateExpression='SET ' + ', '.join(set_parts),
                ExpressionAttributeNames=attr_names,
                ExpressionAttributeValues=attr_values,
            )
        except Exception as e:
            logger.error(f"Failed to update {ticker}/{fiscal_date}: {e}")


# ---------------------------------------------------------------------------
# Earnings Feed — persist event records for the dashboard
# ---------------------------------------------------------------------------
def _write_feed_record(result: Dict[str, Any]) -> None:
    """Write a single earnings result to sp500-aggregates as an EARNINGS_RECENT record."""
    from investment_research.index_tickers import SP500_SECTORS

    ticker = result.get('ticker', '')
    earnings_date = result.get('earnings_date', '')
    if not ticker or not earnings_date or result.get('status') != 'success':
        return

    company_info = SP500_SECTORS.get(ticker, {})
    now = datetime.now()
    ttl = int(now.timestamp()) + (FEED_TTL_DAYS * 24 * 60 * 60)

    item = {
        'aggregate_type': 'EARNINGS_RECENT',
        'aggregate_key': f'{earnings_date}#{ticker}',
        'ticker': ticker,
        'company_name': company_info.get('name', ticker),
        'sector': company_info.get('sector', 'Unknown'),
        'earnings_date': earnings_date,
        'eps_actual': Decimal(str(result['eps_actual'])) if result.get('eps_actual') is not None else None,
        'eps_estimated': Decimal(str(result['eps_estimated'])) if result.get('eps_estimated') is not None else None,
        'eps_beat': result.get('eps_beat'),
        'eps_surprise_pct': Decimal(str(result['eps_surprise_pct'])) if result.get('eps_surprise_pct') is not None else None,
        'updated_at': now.isoformat(),
        'expires_at': ttl,
    }

    # Remove None values (DynamoDB doesn't accept None)
    item = {k: v for k, v in item.items() if v is not None}

    try:
        aggregates_table.put_item(Item=item)
    except Exception as e:
        logger.warning(f"Failed to write feed record for {ticker}: {e}")


def _write_upcoming_records(upcoming: List[Dict[str, Any]]) -> None:
    """Write upcoming earnings to sp500-aggregates as EARNINGS_UPCOMING records."""
    from investment_research.index_tickers import SP500_SECTORS

    now = datetime.now()
    ttl = int(now.timestamp()) + (UPCOMING_LOOKAHEAD_DAYS * 24 * 60 * 60)

    with aggregates_table.batch_writer() as batch:
        for entry in upcoming:
            ticker = entry.get('ticker', '')
            earnings_date = entry.get('earnings_date', '')
            if not ticker or not earnings_date:
                continue

            company_info = SP500_SECTORS.get(ticker, {})
            item = {
                'aggregate_type': 'EARNINGS_UPCOMING',
                'aggregate_key': f'{earnings_date}#{ticker}',
                'ticker': ticker,
                'company_name': company_info.get('name', ticker),
                'sector': company_info.get('sector', 'Unknown'),
                'earnings_date': earnings_date,
                'updated_at': now.isoformat(),
                'expires_at': ttl,
            }

            if entry.get('eps_estimated') is not None:
                item['eps_estimated'] = Decimal(str(entry['eps_estimated']))
            if entry.get('revenue_estimated') is not None:
                item['revenue_estimated'] = Decimal(str(entry['revenue_estimated']))

            batch.put_item(Item=item)

    logger.info(f"Wrote {len(upcoming)} upcoming earnings records")


def _ensure_feed_record(ticker: str, earnings_date: str) -> None:
    """Write an EARNINGS_RECENT feed record for a skipped (already-processed) ticker.

    Reads existing data from metrics-history so we don't need to re-fetch from FMP.
    No-ops if a feed record already exists for this ticker+date.
    """
    from investment_research.index_tickers import SP500_SECTORS

    # Check if feed record already exists
    try:
        existing = aggregates_table.get_item(
            Key={'aggregate_type': 'EARNINGS_RECENT', 'aggregate_key': f'{earnings_date}#{ticker}'}
        )
        if existing.get('Item'):
            return  # Already have a feed record
    except Exception:
        pass  # Proceed to write

    # Read latest quarter from metrics-history
    try:
        resp = metrics_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('ticker').eq(ticker),
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get('Items', [])
        if not items:
            logger.warning(f"_ensure_feed_record: no metrics data for {ticker}")
            return

        item = items[0]
        ee = item.get('earnings_events', {})
        if isinstance(ee, str):
            try:
                ee = json.loads(ee)
            except (json.JSONDecodeError, TypeError):
                ee = {}

        stored_date = ee.get('earnings_date', '')[:10] if ee.get('earnings_date') else ''
        if stored_date != earnings_date[:10]:
            logger.warning(
                f"_ensure_feed_record: {ticker} stored earnings_date={stored_date!r} "
                f"does not match requested {earnings_date!r}; refusing to write stale feed record"
            )
            return

        eps_actual = ee.get('eps_actual')
        eps_estimated = ee.get('eps_estimated')

        # Compute beat/miss
        eps_beat = None
        eps_surprise_pct = None
        if eps_actual is not None and eps_estimated is not None:
            eps_beat = float(eps_actual) >= float(eps_estimated)
            if float(eps_estimated) != 0:
                eps_surprise_pct = round(
                    (float(eps_actual) - float(eps_estimated)) / abs(float(eps_estimated)) * 100, 2
                )

        result = {
            'ticker': ticker,
            'status': 'success',
            'earnings_date': earnings_date,
            'eps_actual': float(eps_actual) if eps_actual is not None else None,
            'eps_estimated': float(eps_estimated) if eps_estimated is not None else None,
            'eps_beat': eps_beat,
            'eps_surprise_pct': eps_surprise_pct,
        }
        _write_feed_record(result)
        logger.info(f"Wrote feed record for skipped ticker {ticker} (earnings {earnings_date})")

    except Exception as e:
        logger.warning(f"_ensure_feed_record failed for {ticker}: {e}")


# ---------------------------------------------------------------------------
# SNS Notifications
# ---------------------------------------------------------------------------
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN', '')
_sns_client = None


def _get_sns_client():
    global _sns_client
    if _sns_client is None:
        _sns_client = boto3.client('sns')
    return _sns_client


def _publish_sns_summary(response: Dict[str, Any]) -> None:
    """Publish a run summary to SNS. Failures are logged but never raise."""
    if not SNS_TOPIC_ARN:
        return
    try:
        updated = response.get('total_updated', 0)
        failures = response.get('total_failures', 0)
        mode = response.get('mode', 'unknown')
        checked = response.get('tickers_checked', 0)

        if checked == 0 and not response.get('tickers_updated'):
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: No tickers to process"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: NO WORK\n"
                f"No companies recently reported earnings."
            )
        elif failures > 0:
            failed_tickers = ', '.join(f.get('ticker', '?') for f in response.get('failures', []))
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: {updated} updated, {failures} failed"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: COMPLETED WITH ERRORS\n"
                f"Tickers checked: {checked}\n"
                f"Tickers updated: {', '.join(response.get('tickers_updated', []))}\n"
                f"Failures ({failures}): {failed_tickers}"
            )
        else:
            tickers_list = ', '.join(response.get('tickers_updated', []))
            subject = f"[buffett-{ENVIRONMENT}] Earnings Update: {updated} updated"
            message = (
                f"Earnings Update — {mode.title()} Mode\n"
                f"Status: SUCCESS\n"
                f"Tickers checked: {checked}\n"
                f"Tickers updated ({updated}): {tickers_list}"
            )
            suspect = response.get('suspect_data', [])
            no_new = response.get('no_new_quarter', [])
            missing = response.get('earnings_date_missing', [])
            extra_parts = []
            if suspect:
                extra_parts.append(f"Suspect data ({len(suspect)}): {', '.join(suspect)}")
            if no_new:
                extra_parts.append(f"No new quarter ({len(no_new)}): {', '.join(no_new)}")
            if missing:
                extra_parts.append(f"Earnings date missing ({len(missing)}): {', '.join(missing)}")
            if extra_parts:
                message = message + "\n" + "\n".join(extra_parts)

        _get_sns_client().publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],
            Message=message,
        )
    except Exception as e:
        logger.warning(f"Failed to publish SNS notification: {e}")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entry point. Triggered by EventBridge twice daily or manually.

    Auto mode (default): checks earnings calendar, processes recently reported tickers.
    Manual mode: processes specific tickers from event payload.
    """
    manual_tickers = event.get('tickers')
    lookback_days = event.get('lookback_days', 2)
    include_upcoming = event.get('include_upcoming', True)
    full_reingest = bool(event.get('full_reingest', False))

    response = {
        'mode': 'manual' if manual_tickers else 'auto',
        'started_at': datetime.now().isoformat(),
        'tickers_updated': [],
        'results': [],
        'failures': [],
    }

    # Determine which tickers to process
    earnings_dates_by_ticker = {}
    if manual_tickers:
        tickers_to_process = sorted(manual_tickers)
        logger.info(f"Manual mode: processing {len(tickers_to_process)} tickers")
    else:
        calendar = _check_earnings_calendar(lookback_days)
        reported = calendar['reported']
        # Build earnings_date + FMP eps_actual lookup for freshness check
        for r in reported:
            earnings_dates_by_ticker[r['ticker']] = {
                'earnings_date': r['earnings_date'],
                'fmp_eps_actual': r.get('eps_actual'),
            }
        tickers_to_process = sorted(set(r['ticker'] for r in reported))
        if include_upcoming:
            response['upcoming'] = calendar['upcoming']
        logger.info(f"Auto mode: {len(tickers_to_process)} tickers recently reported")

    response['tickers_checked'] = len(tickers_to_process)

    # Persist upcoming earnings regardless of whether any tickers reported
    if response.get('upcoming'):
        try:
            _write_upcoming_records(response['upcoming'])
        except Exception as e:
            logger.warning(f"Failed to write upcoming earnings: {e}")

    if not tickers_to_process:
        response['message'] = 'No tickers to process'
        logger.info("No tickers to process — no recent earnings reports")
        _publish_sns_summary(response)
        return response

    # Filter out tickers already processed for this earnings cycle.
    # Skipped tickers still get feed records written (for the dashboard).
    skipped_fresh = []
    skipped_awaiting_fmp = []
    if not manual_tickers:  # Only skip in auto mode — manual mode always processes
        filtered = []
        for ticker in tickers_to_process:
            earnings_info = earnings_dates_by_ticker.get(ticker, {})
            earnings_date = earnings_info.get('earnings_date', '')
            fmp_eps_actual = earnings_info.get('fmp_eps_actual')
            if fmp_eps_actual is None:
                # FMP hasn't propagated actuals yet — defer to next run. Do NOT
                # write a feed record (would pollute aggregates with stale data).
                skipped_awaiting_fmp.append(ticker)
            elif earnings_date and _already_updated_since_earnings(ticker, earnings_date, fmp_eps_actual):
                skipped_fresh.append(ticker)
                # Still write a feed record from existing metrics-history data
                _ensure_feed_record(ticker, earnings_date)
            else:
                filtered.append(ticker)
        if skipped_fresh:
            logger.info(f"Skipping {len(skipped_fresh)} already-processed tickers "
                        f"(feed records ensured): {skipped_fresh}")
        if skipped_awaiting_fmp:
            logger.info(f"Deferring {len(skipped_awaiting_fmp)} tickers awaiting FMP actuals: "
                        f"{skipped_awaiting_fmp}")
        tickers_to_process = filtered

    response['skipped_already_processed'] = skipped_fresh
    response['skipped_awaiting_fmp'] = skipped_awaiting_fmp

    # Process each ticker
    for i, ticker in enumerate(tickers_to_process):
        # Check Lambda timeout (leave 30s buffer)
        if context and hasattr(context, 'get_remaining_time_in_millis'):
            remaining_ms = context.get_remaining_time_in_millis()
            if remaining_ms < 30_000:
                logger.warning(f"Timeout approaching at ticker {i}/{len(tickers_to_process)}")
                response['stopped_early'] = True
                break

        try:
            ticker_earnings_info = earnings_dates_by_ticker.get(ticker, {})
            result = _process_ticker(
                ticker,
                earnings_date=ticker_earnings_info.get('earnings_date'),
                full_reingest=full_reingest,
            )
            response['results'].append(result)
            if result['status'] == 'success':
                response['tickers_updated'].append(ticker)
                _write_feed_record(result)

            if (i + 1) % 10 == 0:
                logger.info(f"Progress: {i + 1}/{len(tickers_to_process)} processed")

        except Exception as e:
            logger.error(f"Failed to process {ticker}: {e}")
            response['failures'].append({'ticker': ticker, 'error': str(e)})

        # Rate limit between tickers
        if i + 1 < len(tickers_to_process):
            time.sleep(FMP_RATE_LIMIT_DELAY)

    response['completed_at'] = datetime.now().isoformat()
    response['total_updated'] = len(response['tickers_updated'])
    response['propagation_lag'] = [
        r['ticker'] for r in response['results']
        if r.get('status') == 'fmp_propagation_lag'
    ]
    response['suspect_data'] = [
        r['ticker'] for r in response['results']
        if r.get('status') == 'fmp_suspect_data'
    ]
    response['no_new_quarter'] = [
        r['ticker'] for r in response['results']
        if r.get('status') == 'fmp_no_new_quarter'
    ]
    response['earnings_date_missing'] = [
        r['ticker'] for r in response['results']
        if r.get('status') == 'fmp_earnings_date_missing'
    ]
    response['total_failures'] = len(response['failures'])

    # NOTE: upcoming earnings already written above (before early-return check)

    logger.info(f"Earnings update complete: {response['total_updated']} updated, "
                f"{response['total_failures']} failures")

    _publish_sns_summary(response)
    return response
