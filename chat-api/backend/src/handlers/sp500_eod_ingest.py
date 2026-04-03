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
FMP_RATE_LIMIT_DELAY = 0.35  # Seconds between FMP calls

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


def fetch_4h_candles(ticker: str, trade_date: str) -> List[Dict]:
    """
    Fetch 4-hour candles for a single ticker from FMP stable API.

    The /stable/historical-chart/4hour endpoint returns recent 4h OHLCV candles.
    We filter to only keep candles matching the target trade_date.

    Returns list of candle dicts with keys: date, open, high, low, close, volume.
    """
    import urllib3
    http = urllib3.PoolManager()
    api_key = get_fmp_api_key()

    # FMP uses dash notation for share classes (BRK.B -> BRK-B)
    fmp_ticker = ticker.replace('.', '-')

    url = f"{FMP_BASE_URL}/historical-chart/4hour"
    params = f"symbol={fmp_ticker}&apikey={api_key}"
    full_url = f"{url}?{params}"

    try:
        resp = http.request("GET", full_url, timeout=15.0)
        if resp.status == 429:
            logger.warning(f"Rate limited on {ticker}, waiting 2s")
            time.sleep(2)
            resp = http.request("GET", full_url, timeout=15.0)

        if resp.status != 200:
            logger.error(f"FMP error for {ticker}: HTTP {resp.status}")
            return []

        data = json.loads(resp.data.decode("utf-8"))
        if not isinstance(data, list):
            logger.warning(f"Unexpected response for {ticker}: {type(data)}")
            return []

        # Filter candles to the target trade date
        candles = [c for c in data if c.get("date", "").startswith(trade_date)]
        return candles

    except Exception as e:
        logger.error(f"Failed to fetch 4h candles for {ticker}: {e}")
        return []


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


def build_dynamo_items(ticker: str, candles: List[Dict], trade_date: str) -> List[Dict]:
    """
    Convert FMP 4h candle records to DynamoDB items.

    Key schema:
      PK     = TICKER#{symbol}
      SK     = DATETIME#{YYYY-MM-DD HH:MM:SS}  (candle timestamp)
      GSI_PK = DATE#{YYYY-MM-DD}
      GSI_SK = TICKER#{symbol}
    """
    items = []
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    # TTL: expire records after 365 days
    expires_at = int((now + timedelta(days=365)).timestamp())

    for candle in candles:
        candle_datetime = candle.get("date", "")
        if not candle_datetime:
            continue

        items.append({
            "PK": f"TICKER#{ticker}",
            "SK": f"DATETIME#{candle_datetime}",
            "GSI_PK": f"DATE#{trade_date}",
            "GSI_SK": f"TICKER#{ticker}",
            "symbol": ticker,
            "date": trade_date,
            "datetime": candle_datetime,
            "open": _to_decimal(candle.get("open")),
            "high": _to_decimal(candle.get("high")),
            "low": _to_decimal(candle.get("low")),
            "close": _to_decimal(candle.get("close")),
            "volume": int(candle.get("volume") or 0),
            "ingested_at": now_iso,
            "expires_at": expires_at,
        })

    return items


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
# US market holidays (observed dates shift year-to-year, but these are fixed)
US_MARKET_HOLIDAYS_MMDD = {
    "01-01",  # New Year's Day
    "01-20",  # MLK Day (3rd Monday Jan — approximate)
    "02-17",  # Presidents' Day (3rd Monday Feb — approximate)
    "04-18",  # Good Friday (varies — update annually)
    "05-26",  # Memorial Day (last Monday May — approximate)
    "06-19",  # Juneteenth
    "07-04",  # Independence Day
    "09-01",  # Labor Day (1st Monday Sep — approximate)
    "11-27",  # Thanksgiving (4th Thursday Nov — approximate)
    "12-25",  # Christmas
}


def is_market_closed(trade_date: str) -> bool:
    """Check if a date is a weekend or known US market holiday."""
    import calendar
    year, month, day = (int(x) for x in trade_date.split("-"))
    weekday = calendar.weekday(year, month, day)  # Mon=0 ... Sun=6
    if weekday >= 5:  # Saturday=5, Sunday=6
        return True
    mmdd = trade_date[5:]  # "YYYY-MM-DD" -> "MM-DD"
    return mmdd in US_MARKET_HOLIDAYS_MMDD


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
                ":sk_prefix": f"DATETIME#{trade_date}",
            },
            Limit=1,
        )
        return len(response.get("Items", [])) > 0
    except ClientError:
        return False


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
        return {"statusCode": 200, "body": msg, "recordsWritten": 0, "skipped": True}

    # --- Idempotency guard ---
    if not force and already_ingested(target_date):
        msg = f"4h data for {target_date} already exists — skipping (pass force=true to overwrite)"
        logger.info(msg)
        return {"statusCode": 200, "body": msg, "recordsWritten": 0, "skipped": True}

    # --- 1. Get tickers ---
    custom_tickers = event.get("tickers")
    if custom_tickers:
        tickers = sorted(custom_tickers)
        logger.info(f"Processing {len(tickers)} custom tickers")
    else:
        tickers = get_sp500_tickers()

    # --- 2. Fetch 4h candles per ticker ---
    all_items = []
    tickers_with_data = 0
    tickers_empty = 0

    for i, ticker in enumerate(tickers):
        candles = fetch_4h_candles(ticker, target_date)

        if candles:
            items = build_dynamo_items(ticker, candles, target_date)
            all_items.extend(items)
            tickers_with_data += 1
        else:
            tickers_empty += 1

        # Progress logging every 50 tickers
        if (i + 1) % 50 == 0:
            logger.info(f"Progress: {i + 1}/{len(tickers)} tickers processed, {len(all_items)} candles collected")

        # Rate limit between FMP calls
        if i + 1 < len(tickers):
            time.sleep(FMP_RATE_LIMIT_DELAY)

    logger.info(
        f"Fetch complete: {tickers_with_data} tickers with data, "
        f"{tickers_empty} empty, {len(all_items)} total candles"
    )

    if not all_items:
        msg = f"No 4h candles returned for {target_date} — possible market holiday"
        logger.warning(msg)
        return {"statusCode": 200, "body": msg, "recordsWritten": 0}

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
        "body": f"Ingested {written} 4h candles for {target_date}",
        "date": target_date,
        "tickersProcessed": len(tickers),
        "tickersWithData": tickers_with_data,
        "tickersEmpty": tickers_empty,
        "totalCandles": len(all_items),
        "recordsWritten": written,
        "recordsFailed": failed,
    }
    logger.info("Ingestion complete", extra=result)
    return result
