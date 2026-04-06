"""
S&P 500 Daily EOD 4-Hour Candle Ingestion Lambda

Fetches 4-hour interval OHLCV data for all S&P 500 tickers after market close
and stores it in DynamoDB.

Uses FMP stable API: /stable/historical-chart/4hour?symbol={ticker}

Scheduled via EventBridge: cron(0 22 ? * MON-FRI *)  — 10 PM UTC (6 PM ET)
Runs ~2 hours after US market close to ensure data availability.

Environment Variables:
  FMP_SECRET_NAME       — Secrets Manager name holding the FMP API key
  STOCK_DATA_4H_TABLE   — DynamoDB table name for 4-hour candle data
  ENVIRONMENT           — dev/staging/prod
  LOG_LEVEL             — DEBUG/INFO/WARNING
"""

import json
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

import boto3
from botocore.exceptions import ClientError

try:
    from aws_lambda_powertools import Logger, Metrics
    from aws_lambda_powertools.metrics import MetricUnit
    logger = Logger()
    metrics = Metrics()
    _has_powertools = True
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
    metrics = None
    _has_powertools = False

ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
TABLE_NAME = os.environ.get('STOCK_DATA_4H_TABLE', f'stock-data-4h-{ENVIRONMENT}')
FMP_SECRET_NAME = os.environ.get('FMP_SECRET_NAME', f'buffett-{ENVIRONMENT}-fmp')
FMP_BASE_URL = "https://financialmodelingprep.com/stable"

BATCH_WRITE_SIZE = 25
MAX_DDB_RETRIES = 5
FMP_BATCH_SIZE = 5  # Tickers per FMP request (stable API is per-ticker)
FMP_RATE_LIMIT_DELAY = 0.5  # Seconds between FMP calls (300 calls/min FMP limit)

# ---------------------------------------------------------------------------
# AWS Clients
# ---------------------------------------------------------------------------
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

# Cache the API key for warm invocations
_fmp_api_key: str | None = None


# ---------------------------------------------------------------------------
# Secrets Manager
# ---------------------------------------------------------------------------
def get_fmp_api_key() -> str:
    """Retrieve FMP API key from Secrets Manager (cached in-memory)."""
    global _fmp_api_key
    if _fmp_api_key is None:
        response = secrets_client.get_secret_value(SecretId=FMP_SECRET_NAME)
        secret = json.loads(response['SecretString'])
        _fmp_api_key = secret['FMP_API_KEY']
    return _fmp_api_key


# ---------------------------------------------------------------------------
# FMP API
# ---------------------------------------------------------------------------
def get_sp500_tickers() -> List[str]:
    """Get S&P 500 ticker list. Uses investment_research module if available."""
    try:
        from investment_research.index_tickers import SP500_TICKERS
        tickers = sorted(SP500_TICKERS)
        logger.info(f"Loaded {len(tickers)} tickers from index_tickers")
        return tickers
    except ImportError:
        logger.warning("index_tickers not available, fetching from FMP API")
        return _fetch_sp500_from_fmp()


def _fetch_sp500_from_fmp() -> List[str]:
    """Fallback: fetch S&P 500 constituents from FMP API."""
    import urllib3
    http = urllib3.PoolManager()
    api_key = get_fmp_api_key()
    url = f"https://financialmodelingprep.com/api/v3/sp500_constituent?apikey={api_key}"
    resp = http.request("GET", url)
    if resp.status != 200:
        raise RuntimeError(f"Failed to fetch S&P 500 list: HTTP {resp.status}")
    data = json.loads(resp.data.decode("utf-8"))
    return sorted({item["symbol"] for item in data})


def fetch_daily_eod(ticker: str, trade_date: str) -> Dict | None:
    """
    Fetch single-day EOD price from FMP stable API.

    Uses /stable/historical-price-eod/full with from/to set to trade_date.
    Returns a single dict with date, open, high, low, close, volume, change,
    changePercent, vwap — or None if unavailable.
    """
    import urllib3
    http = urllib3.PoolManager()
    api_key = get_fmp_api_key()

    fmp_ticker = ticker.replace('.', '-')
    url = (
        f"{FMP_BASE_URL}/historical-price-eod/full"
        f"?symbol={fmp_ticker}&from={trade_date}&to={trade_date}&apikey={api_key}"
    )

    try:
        resp = http.request("GET", url, timeout=15.0)
        if resp.status == 429:
            logger.warning(f"Rate limited on {ticker} (daily EOD), waiting 2s")
            time.sleep(2)
            resp = http.request("GET", url, timeout=15.0)

        if resp.status != 200:
            return None

        data = json.loads(resp.data.decode("utf-8"))
        if isinstance(data, list) and data:
            return data[0]
        return None

    except Exception as e:
        logger.error(f"Failed to fetch daily EOD for {ticker}: {e}")
        return None


def build_daily_item(ticker: str, eod: Dict, trade_date: str) -> Dict:
    """Convert a daily EOD record to a DynamoDB item with SK prefix DAILY#."""
    now = datetime.now(timezone.utc)
    expires_at = int((now + timedelta(days=365)).timestamp())

    return {
        "PK": f"TICKER#{ticker}",
        "SK": f"DAILY#{trade_date}",
        "GSI_PK": f"DATE#{trade_date}",
        "GSI_SK": f"TICKER#{ticker}",
        "symbol": ticker,
        "date": trade_date,
        "open": _to_decimal(eod.get("open")),
        "high": _to_decimal(eod.get("high")),
        "low": _to_decimal(eod.get("low")),
        "close": _to_decimal(eod.get("close")),
        "volume": int(eod.get("volume") or 0),
        "change": _to_decimal(eod.get("change")),
        "change_percent": _to_decimal(eod.get("changePercent")),
        "vwap": _to_decimal(eod.get("vwap")),
        "ingested_at": now.isoformat(),
        "expires_at": expires_at,
    }


# ---------------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------------
def _to_decimal(value: Any) -> Decimal:
    """Safely convert a numeric value to Decimal for DynamoDB."""
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def batch_write_items(items: List[Dict]) -> Tuple[int, int]:
    """
    Write items via BatchWriteItem with exponential backoff.
    Returns (written_count, failed_count).
    """
    written = 0
    failed = 0

    for i in range(0, len(items), BATCH_WRITE_SIZE):
        chunk = items[i: i + BATCH_WRITE_SIZE]
        request_items = {
            TABLE_NAME: [{"PutRequest": {"Item": item}} for item in chunk]
        }

        for attempt in range(MAX_DDB_RETRIES):
            try:
                response = dynamodb.meta.client.batch_write_item(
                    RequestItems=request_items
                )
                unprocessed = response.get("UnprocessedItems", {})
                if not unprocessed:
                    written += len(chunk)
                    break

                remaining = len(unprocessed.get(TABLE_NAME, []))
                written += len(chunk) - remaining
                request_items = unprocessed
                chunk = [r["PutRequest"]["Item"] for r in unprocessed[TABLE_NAME]]
                wait = min(2 ** attempt * 0.5, 16)
                logger.warning(f"Unprocessed items: {remaining}, retrying in {wait}s")
                time.sleep(wait)

            except ClientError as e:
                code = e.response["Error"]["Code"]
                if code in ("ProvisionedThroughputExceededException", "ThrottlingException"):
                    wait = min(2 ** attempt * 0.5, 16)
                    logger.warning(f"DynamoDB throttled, waiting {wait}s")
                    time.sleep(wait)
                else:
                    logger.exception(f"DynamoDB write error: {code}")
                    raise
        else:
            failed += len(chunk)
            logger.error(f"Batch write failed after {MAX_DDB_RETRIES} retries: {len(chunk)} items")

    return written, failed


# ---------------------------------------------------------------------------
# Market Holiday Check
# ---------------------------------------------------------------------------


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime:
    """Return the nth occurrence of a weekday in a given month.
    weekday: 0=Mon, 1=Tue, ..., 6=Sun.  n: 1=first, 2=second, etc.
    """
    import calendar
    first_day_wd, days_in_month = calendar.monthrange(year, month)
    # Day of first occurrence of the target weekday
    first_occ = 1 + (weekday - first_day_wd) % 7
    day = first_occ + (n - 1) * 7
    return datetime(year, month, day)


def _last_weekday(year: int, month: int, weekday: int) -> datetime:
    """Return the last occurrence of a weekday in a given month."""
    import calendar
    _, days_in_month = calendar.monthrange(year, month)
    last_day = datetime(year, month, days_in_month)
    diff = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=diff)


def _good_friday(year: int) -> datetime:
    """Compute Good Friday for a given year using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    easter = datetime(year, month, day + 1)
    return easter - timedelta(days=2)


def _us_market_holidays(year: int) -> set:
    """Compute all NYSE/NASDAQ market holidays for a given year.
    Returns a set of 'MM-DD' strings.
    """
    holidays = set()

    # Fixed-date holidays
    fixed = [
        (1, 1),   # New Year's Day
        (6, 19),  # Juneteenth
        (7, 4),   # Independence Day
        (12, 25), # Christmas
    ]
    for month, day in fixed:
        d = datetime(year, month, day)
        wd = d.weekday()
        if wd == 5:      # Saturday → observe Friday
            d -= timedelta(days=1)
        elif wd == 6:    # Sunday → observe Monday
            d += timedelta(days=1)
        holidays.add(d.strftime("%m-%d"))

    # Floating holidays
    holidays.add(_nth_weekday(year, 1, 0, 3).strftime("%m-%d"))   # MLK Day: 3rd Monday Jan
    holidays.add(_nth_weekday(year, 2, 0, 3).strftime("%m-%d"))   # Presidents' Day: 3rd Monday Feb
    holidays.add(_good_friday(year).strftime("%m-%d"))             # Good Friday
    holidays.add(_last_weekday(year, 5, 0).strftime("%m-%d"))     # Memorial Day: last Monday May
    holidays.add(_nth_weekday(year, 9, 0, 1).strftime("%m-%d"))   # Labor Day: 1st Monday Sep
    holidays.add(_nth_weekday(year, 11, 3, 4).strftime("%m-%d"))  # Thanksgiving: 4th Thursday Nov

    return holidays


# Cache per year to avoid recomputation on warm invocations
_holiday_cache: Dict[int, set] = {}


def is_market_closed(trade_date: str) -> bool:
    """Check if a date is a weekend or known US market holiday."""
    import calendar
    year, month, day = (int(x) for x in trade_date.split("-"))
    weekday = calendar.weekday(year, month, day)  # Mon=0 ... Sun=6
    if weekday >= 5:
        return True
    if year not in _holiday_cache:
        _holiday_cache[year] = _us_market_holidays(year)
    mmdd = trade_date[5:]
    return mmdd in _holiday_cache[year]


# ---------------------------------------------------------------------------
# Idempotency Check
# ---------------------------------------------------------------------------
def already_ingested(trade_date: str) -> bool:
    """Spot-check AAPL to see if today's 4h data is already loaded."""
    try:
        response = table.query(
            KeyConditionExpression="PK = :pk AND begins_with(SK, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": "TICKER#AAPL",
                ":sk_prefix": f"DAILY#{trade_date}",
            },
            Limit=1,
        )
        return len(response.get("Items", [])) > 0
    except ClientError:
        return False


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


def _publish_sns_summary(result: Dict[str, Any]) -> None:
    """Publish a run summary to SNS. Failures are logged but never raise."""
    if not SNS_TOPIC_ARN:
        return
    try:
        skipped = result.get('skipped', False)
        date = result.get('date', 'unknown')
        written = result.get('recordsWritten', 0)
        failed = result.get('recordsFailed', 0)

        if skipped:
            subject = f"[buffett-{ENVIRONMENT}] EOD Ingest: Skipped ({date})"
            message = f"S&P 500 Daily EOD Ingestion — {date}\nStatus: SKIPPED\n{result.get('body', '')}"
        elif failed > 0:
            subject = f"[buffett-{ENVIRONMENT}] EOD Ingest: {written} written, {failed} failed ({date})"
            message = (
                f"S&P 500 Daily EOD Ingestion — {date}\n"
                f"Status: COMPLETED WITH ERRORS\n"
                f"Tickers processed: {result.get('tickersProcessed', 0)}\n"
                f"Tickers with data: {result.get('tickersWithData', 0)}\n"
                f"Tickers empty: {result.get('tickersEmpty', 0)}\n"
                f"Records written: {written}\n"
                f"Records failed: {failed}"
            )
        else:
            subject = f"[buffett-{ENVIRONMENT}] EOD Ingest: {written} records written ({date})"
            message = (
                f"S&P 500 Daily EOD Ingestion — {date}\n"
                f"Status: SUCCESS\n"
                f"Tickers processed: {result.get('tickersProcessed', 0)}\n"
                f"Tickers with data: {result.get('tickersWithData', 0)}\n"
                f"Tickers empty: {result.get('tickersEmpty', 0)}\n"
                f"Records written: {written}"
            )

        _get_sns_client().publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject[:100],  # SNS subject max 100 chars
            Message=message,
        )
    except Exception as e:
        logger.warning(f"Failed to publish SNS notification: {e}")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------
def _emit_metric(name: str, value: float, unit: str = "Count"):
    """Emit a CloudWatch custom metric via Powertools (no-op if unavailable)."""
    if metrics and _has_powertools:
        metrics.add_metric(name=name, unit=getattr(MetricUnit, unit, MetricUnit.Count), value=value)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Entry point. Triggered by EventBridge on a cron schedule.

    Event payload options:
        {}                              — ingest yesterday's data (default)
        {"date": "YYYY-MM-DD"}          — ingest specific date
        {"force": true}                 — overwrite existing data
        {"tickers": ["AAPL", "MSFT"]}   — process specific tickers only
    """
    # --- Determine trade date ---
    target_date = event.get("date")
    force = event.get("force", False)

    if not target_date:
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)
        wd = yesterday.weekday()
        if wd == 6:  # Sunday → Friday
            yesterday -= timedelta(days=2)
        elif wd == 5:  # Saturday → Friday
            yesterday -= timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")

    logger.info(f"Starting 4h EOD ingestion for {target_date} (force={force})")

    # --- Market closed guard (weekends + holidays) ---
    if not force and is_market_closed(target_date):
        msg = f"Market closed on {target_date} (weekend or holiday) — skipping"
        logger.info(msg)
        result = {"statusCode": 200, "body": msg, "date": target_date, "recordsWritten": 0, "skipped": True}
        _publish_sns_summary(result)
        return result

    # --- Idempotency guard ---
    if not force and already_ingested(target_date):
        msg = f"4h data for {target_date} already exists — skipping (pass force=true to overwrite)"
        logger.info(msg)
        result = {"statusCode": 200, "body": msg, "date": target_date, "recordsWritten": 0, "skipped": True}
        _publish_sns_summary(result)
        return result

    # --- 1. Get tickers ---
    custom_tickers = event.get("tickers")
    if custom_tickers:
        tickers = sorted(custom_tickers)
        logger.info(f"Processing {len(tickers)} custom tickers")
    else:
        tickers = get_sp500_tickers()

    # --- 2. Fetch daily EOD + 4h candles per ticker ---
    all_items = []
    tickers_with_data = 0
    tickers_empty = 0

    for i, ticker in enumerate(tickers):
        # Fetch daily EOD price (primary data source)
        eod = fetch_daily_eod(ticker, target_date)
        if eod:
            all_items.append(build_daily_item(ticker, eod, target_date))
            tickers_with_data += 1
        else:
            tickers_empty += 1

        # Rate limit between FMP calls
        if i + 1 < len(tickers):
            time.sleep(FMP_RATE_LIMIT_DELAY)

        # Progress logging every 50 tickers
        if (i + 1) % 50 == 0:
            logger.info(f"Progress: {i + 1}/{len(tickers)} tickers processed, {len(all_items)} records collected")

    logger.info(
        f"Fetch complete: {tickers_with_data} tickers with data, "
        f"{tickers_empty} empty, {len(all_items)} total records"
    )

    if not all_items:
        msg = f"No EOD data returned for {target_date} — possible market holiday"
        logger.warning(msg)
        result = {"statusCode": 200, "body": msg, "date": target_date, "recordsWritten": 0}
        _publish_sns_summary(result)
        return result

    # --- 3. Write to DynamoDB ---
    written, failed = batch_write_items(all_items)

    # --- 4. Emit CloudWatch metrics ---
    _emit_metric("RecordsWritten", written)
    _emit_metric("TickersProcessed", len(tickers))
    _emit_metric("TickersWithData", tickers_with_data)
    _emit_metric("TickersEmpty", tickers_empty)
    if failed:
        _emit_metric("RecordsFailed", failed)

    result = {
        "statusCode": 200,
        "body": f"Ingested {written} daily EOD records for {target_date}",
        "date": target_date,
        "tickersProcessed": len(tickers),
        "tickersWithData": tickers_with_data,
        "tickersEmpty": tickers_empty,
        "totalCandles": len(all_items),
        "recordsWritten": written,
        "recordsFailed": failed,
    }
    logger.info("Ingestion complete", extra=result)
    _publish_sns_summary(result)
    return result
