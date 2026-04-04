"""
Unit tests for the S&P 500 Daily EOD 4-Hour Candle Ingestion Lambda.

Tests cover:
- Decimal conversion helper
- DynamoDB item building (key schema, GSI, field mapping)
- Idempotency check (already_ingested)
- Trade date computation (weekday/weekend logic)
- Lambda handler: skip on idempotency, force override, empty data, full e2e
"""

import json
import os
import sys
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone, timedelta
from decimal import Decimal

# Ensure src and project root are in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

# Set environment variables before importing the handler module
os.environ['ENVIRONMENT'] = 'test'
os.environ['STOCK_DATA_4H_TABLE'] = 'stock-data-4h-test'
os.environ['FMP_SECRET_NAME'] = 'buffett-test-fmp'


# ============================================================================
# Sample FMP response data (matches actual API shape)
# ============================================================================
SAMPLE_FMP_CANDLES = [
    {
        "date": "2026-04-02 13:30:00",
        "open": 255.35,
        "low": 254.31,
        "high": 256.13,
        "close": 255.92,
        "volume": 7012489,
    },
    {
        "date": "2026-04-02 09:30:00",
        "open": 254.19,
        "low": 250.65,
        "high": 255.73,
        "close": 255.31,
        "volume": 11322815,
    },
]

# Candles from a different date (should be filtered out)
SAMPLE_FMP_CANDLES_MIXED = SAMPLE_FMP_CANDLES + [
    {
        "date": "2026-04-01 13:30:00",
        "open": 250.00,
        "low": 249.00,
        "high": 251.00,
        "close": 250.50,
        "volume": 5000000,
    },
]


# ============================================================================
# Test _to_decimal
# ============================================================================
class TestToDecimal:
    """AC-8: Decimal conversion for DynamoDB compatibility."""

    def test_valid_integer(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal(42) == Decimal("42")

    def test_valid_float(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal(255.35) == Decimal("255.35")

    def test_valid_string_number(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal("123.45") == Decimal("123.45")

    def test_none_returns_zero(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal(None) == Decimal("0")

    def test_invalid_string_returns_zero(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal("not_a_number") == Decimal("0")

    def test_empty_string_returns_zero(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal("") == Decimal("0")

    def test_zero(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal(0) == Decimal("0")

    def test_negative(self):
        from handlers.sp500_eod_ingest import _to_decimal
        assert _to_decimal(-5.25) == Decimal("-5.25")


# ============================================================================
# Test build_dynamo_items
# ============================================================================
class TestBuildDynamoItems:
    """AC-1: Correct PK/SK/GSI keys and Decimal-converted values."""

    def test_correct_key_schema(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", SAMPLE_FMP_CANDLES, "2026-04-02")

        assert len(items) == 2

        item = items[0]
        assert item["PK"] == "TICKER#AAPL"
        assert item["SK"] == "DATETIME#2026-04-02 13:30:00"
        assert item["GSI_PK"] == "DATE#2026-04-02"
        assert item["GSI_SK"] == "TICKER#AAPL"

    def test_decimal_conversion(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", SAMPLE_FMP_CANDLES, "2026-04-02")

        item = items[0]
        assert item["open"] == Decimal("255.35")
        assert item["high"] == Decimal("256.13")
        assert item["low"] == Decimal("254.31")
        assert item["close"] == Decimal("255.92")
        assert isinstance(item["volume"], int)
        assert item["volume"] == 7012489

    def test_metadata_fields(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("MSFT", SAMPLE_FMP_CANDLES, "2026-04-02")

        item = items[0]
        assert item["symbol"] == "MSFT"
        assert item["date"] == "2026-04-02"
        assert item["datetime"] == "2026-04-02 13:30:00"
        assert "ingested_at" in item

    def test_empty_candles(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", [], "2026-04-02")
        assert items == []

    def test_candle_missing_date_skipped(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        candles = [{"open": 100, "close": 101, "high": 102, "low": 99, "volume": 1000}]
        items = build_dynamo_items("AAPL", candles, "2026-04-02")
        assert items == []

    def test_second_item_sort_key(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", SAMPLE_FMP_CANDLES, "2026-04-02")

        assert items[1]["SK"] == "DATETIME#2026-04-02 09:30:00"


# ============================================================================
# Test already_ingested
# ============================================================================
class TestAlreadyIngested:
    """AC-2: Idempotency check via DynamoDB query."""

    def test_returns_true_when_data_exists(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"PK": "TICKER#AAPL"}]}

        with patch("handlers.sp500_eod_ingest.table", mock_table):
            from handlers.sp500_eod_ingest import already_ingested
            assert already_ingested("2026-04-02") is True

        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert ":pk" in str(call_kwargs)

    def test_returns_false_when_no_data(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}

        with patch("handlers.sp500_eod_ingest.table", mock_table):
            from handlers.sp500_eod_ingest import already_ingested
            assert already_ingested("2026-04-02") is False

    def test_returns_false_on_client_error(self):
        from botocore.exceptions import ClientError
        mock_table = MagicMock()
        mock_table.query.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Table not found"}},
            "Query"
        )

        with patch("handlers.sp500_eod_ingest.table", mock_table):
            from handlers.sp500_eod_ingest import already_ingested
            assert already_ingested("2026-04-02") is False


# ============================================================================
# Test trade date computation
# ============================================================================
class TestTradeDateComputation:
    """AC-3: Correct date logic for weekdays and weekends."""

    def _run_handler_with_date(self, mock_now):
        """Helper: run handler with mocked datetime and return the target_date used."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"PK": "exists"}]}  # trigger skip

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.datetime") as mock_dt, \
             patch("handlers.sp500_eod_ingest.get_sp500_tickers", return_value=["AAPL"]):
            mock_dt.now.return_value = mock_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            # timedelta needs to work
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({}, None)

        return result

    def test_tuesday_returns_monday(self):
        """Tuesday 10PM UTC → Monday's date."""
        mock_now = datetime(2026, 4, 7, 22, 0, 0, tzinfo=timezone.utc)  # Tuesday
        result = self._run_handler_with_date(mock_now)
        assert "2026-04-06" in result.get("body", "")  # Monday

    def test_monday_returns_friday(self):
        """Monday 10PM UTC → Friday's date (skip weekend)."""
        mock_now = datetime(2026, 4, 6, 22, 0, 0, tzinfo=timezone.utc)  # Monday
        result = self._run_handler_with_date(mock_now)
        assert "2026-04-03" in result.get("body", "")  # Friday

    def test_sunday_returns_friday(self):
        """Sunday → Friday (skip Sat+Sun)."""
        mock_now = datetime(2026, 4, 5, 22, 0, 0, tzinfo=timezone.utc)  # Sunday
        result = self._run_handler_with_date(mock_now)
        assert "2026-04-03" in result.get("body", "")  # Friday

    def test_explicit_date_overrides_computation(self):
        """Explicit date in event bypasses date computation."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"PK": "exists"}]}

        with patch("handlers.sp500_eod_ingest.table", mock_table):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-03-15"}, None)

        assert "2026-03-15" in result.get("body", "")


# ============================================================================
# Test lambda_handler idempotency
# ============================================================================
class TestHandlerIdempotency:
    """AC-4, AC-5: Skip on duplicate, override with force."""

    def test_skips_when_data_exists(self):
        """AC-4: Returns skipped=True when data already ingested."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"PK": "TICKER#AAPL"}]}

        with patch("handlers.sp500_eod_ingest.table", mock_table):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-04-02"}, None)

        assert result["skipped"] is True
        assert result["recordsWritten"] == 0

    def test_force_overrides_idempotency(self):
        """AC-5: force=True proceeds even when data exists."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": [{"PK": "TICKER#AAPL"}]}

        mock_dynamodb = MagicMock()
        mock_dynamodb.meta.client.batch_write_item.return_value = {"UnprocessedItems": {}}

        # Mock FMP response
        mock_http_response = MagicMock()
        mock_http_response.status = 200
        mock_http_response.data = json.dumps(SAMPLE_FMP_CANDLES).encode("utf-8")

        mock_eod = {"date": "2026-04-02", "open": 255, "high": 256, "low": 254, "close": 255.92, "volume": 31000000, "change": 1.7, "changePercent": 0.67, "vwap": 254.5}

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.dynamodb", mock_dynamodb), \
             patch("handlers.sp500_eod_ingest.get_sp500_tickers", return_value=["AAPL"]), \
             patch("handlers.sp500_eod_ingest.fetch_daily_eod", return_value=mock_eod), \
             patch("handlers.sp500_eod_ingest.batch_write_items", return_value=(1, 0)):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-04-02", "force": True}, None)

        assert "skipped" not in result
        assert result["recordsWritten"] == 1


# ============================================================================
# Test empty data (market holiday)
# ============================================================================
class TestHandlerEmptyData:
    """AC-6: Graceful handling when FMP returns no candles."""

    def test_no_candles_returns_zero(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}  # not ingested

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.get_sp500_tickers", return_value=["AAPL", "MSFT"]), \
             patch("handlers.sp500_eod_ingest.fetch_4h_candles", return_value=[]), \
             patch("handlers.sp500_eod_ingest.time"):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-12-25"}, None)

        assert result["recordsWritten"] == 0
        assert "holiday" in result["body"].lower() or result["recordsWritten"] == 0


# ============================================================================
# Test end-to-end handler with mocked FMP + DynamoDB
# ============================================================================
class TestHandlerEndToEnd:
    """AC-7: Full pipeline with 3 tickers, verify DynamoDB writes."""

    def test_full_ingestion_three_tickers(self):
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}  # not ingested yet

        written_items = []

        def mock_batch_write(RequestItems=None, **kwargs):
            if RequestItems:
                table_name = list(RequestItems.keys())[0]
                for put_req in RequestItems[table_name]:
                    written_items.append(put_req["PutRequest"]["Item"])
            return {"UnprocessedItems": {}}

        mock_dynamodb = MagicMock()
        mock_dynamodb.meta.client.batch_write_item.side_effect = mock_batch_write

        def mock_fetch_eod(ticker, trade_date):
            return {
                "date": trade_date, "open": 100.0, "high": 105.0, "low": 99.0,
                "close": 104.0, "volume": 1000000, "change": 2.0,
                "changePercent": 1.96, "vwap": 102.0,
            }

        tickers = ["AAPL", "MSFT", "GOOGL"]

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.dynamodb", mock_dynamodb), \
             patch("handlers.sp500_eod_ingest.get_sp500_tickers", return_value=tickers), \
             patch("handlers.sp500_eod_ingest.fetch_daily_eod", side_effect=mock_fetch_eod), \
             patch("handlers.sp500_eod_ingest.TABLE_NAME", "stock-data-4h-test"), \
             patch("handlers.sp500_eod_ingest.time"):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-04-02"}, None)

        assert result["statusCode"] == 200
        assert result["tickersProcessed"] == 3
        assert result["tickersWithData"] == 3
        assert result["totalCandles"] == 3  # 1 daily record per ticker
        assert result["recordsWritten"] == 3
        assert result["recordsFailed"] == 0

        assert len(written_items) == 3
        tickers_written = {item["symbol"] for item in written_items}
        assert tickers_written == {"AAPL", "MSFT", "GOOGL"}
        assert written_items[0]["PK"].startswith("TICKER#")
        assert written_items[0]["SK"].startswith("DAILY#")

    def test_custom_tickers_override(self):
        """Event with custom tickers list uses those instead of full S&P 500."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}

        mock_eod = {"date": "2026-04-02", "open": 255, "high": 256, "low": 254, "close": 255.92, "volume": 31000000, "change": 1.7, "changePercent": 0.67, "vwap": 254.5}

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.dynamodb") as mock_ddb, \
             patch("handlers.sp500_eod_ingest.fetch_daily_eod", return_value=mock_eod), \
             patch("handlers.sp500_eod_ingest.batch_write_items", return_value=(2, 0)), \
             patch("handlers.sp500_eod_ingest.time"):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({
                "date": "2026-04-02",
                "tickers": ["AAPL", "TSLA"]
            }, None)

        assert result["tickersProcessed"] == 2
        assert result["tickersWithData"] == 2


# ============================================================================
# Test fetch_4h_candles date filtering
# ============================================================================
class TestFetch4hCandles:
    """Test that candles are filtered to the target trade date."""

    def test_filters_by_date(self):
        """Only candles matching target date are returned."""
        mock_http_response = MagicMock()
        mock_http_response.status = 200
        mock_http_response.data = json.dumps(SAMPLE_FMP_CANDLES_MIXED).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_http_response

        import urllib3
        with patch.object(urllib3, "PoolManager", return_value=mock_pool), \
             patch("handlers.sp500_eod_ingest.get_fmp_api_key", return_value="test-key"):
            from handlers.sp500_eod_ingest import fetch_4h_candles
            result = fetch_4h_candles("AAPL", "2026-04-02")

        assert len(result) == 2
        for candle in result:
            assert candle["date"].startswith("2026-04-02")

    def test_handles_non_200_response(self):
        mock_http_response = MagicMock()
        mock_http_response.status = 500

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_http_response

        import urllib3
        with patch.object(urllib3, "PoolManager", return_value=mock_pool), \
             patch("handlers.sp500_eod_ingest.get_fmp_api_key", return_value="test-key"):
            from handlers.sp500_eod_ingest import fetch_4h_candles
            result = fetch_4h_candles("AAPL", "2026-04-02")
            assert result == []

    def test_handles_rate_limit_429(self):
        """429 triggers a retry after delay."""
        mock_response_429 = MagicMock()
        mock_response_429.status = 429

        mock_response_ok = MagicMock()
        mock_response_ok.status = 200
        mock_response_ok.data = json.dumps(SAMPLE_FMP_CANDLES).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.side_effect = [mock_response_429, mock_response_ok]

        import urllib3
        with patch.object(urllib3, "PoolManager", return_value=mock_pool), \
             patch("handlers.sp500_eod_ingest.get_fmp_api_key", return_value="test-key"), \
             patch("handlers.sp500_eod_ingest.time"):
            from handlers.sp500_eod_ingest import fetch_4h_candles
            result = fetch_4h_candles("AAPL", "2026-04-02")
            assert len(result) == 2


# ============================================================================
# Test batch_write_items
# ============================================================================
class TestBatchWriteItems:
    """Test DynamoDB batch write with retry logic."""

    def test_successful_write(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", SAMPLE_FMP_CANDLES, "2026-04-02")

        mock_dynamodb = MagicMock()
        mock_dynamodb.meta.client.batch_write_item.return_value = {"UnprocessedItems": {}}

        with patch("handlers.sp500_eod_ingest.dynamodb", mock_dynamodb), \
             patch("handlers.sp500_eod_ingest.TABLE_NAME", "stock-data-4h-test"):
            from handlers.sp500_eod_ingest import batch_write_items
            written, failed = batch_write_items(items)

        assert written == 2
        assert failed == 0

    def test_empty_items(self):
        from handlers.sp500_eod_ingest import batch_write_items
        written, failed = batch_write_items([])
        assert written == 0
        assert failed == 0


# ============================================================================
# Test ticker format conversion (BRK.B -> BRK-B)
# ============================================================================
class TestTickerFormatConversion:
    """Dot-notation tickers are converted to dash for FMP API."""

    def test_dot_converted_to_dash_in_url(self):
        """BRK.B should call FMP with BRK-B."""
        mock_http_response = MagicMock()
        mock_http_response.status = 200
        mock_http_response.data = json.dumps(SAMPLE_FMP_CANDLES).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_http_response

        import urllib3
        with patch.object(urllib3, "PoolManager", return_value=mock_pool), \
             patch("handlers.sp500_eod_ingest.get_fmp_api_key", return_value="test-key"):
            from handlers.sp500_eod_ingest import fetch_4h_candles
            fetch_4h_candles("BRK.B", "2026-04-02")

        # Verify the URL used dash notation
        call_args = mock_pool.request.call_args
        url_called = call_args[0][1]
        assert "BRK-B" in url_called
        assert "BRK.B" not in url_called

    def test_regular_ticker_unchanged(self):
        """AAPL should remain AAPL in the URL."""
        mock_http_response = MagicMock()
        mock_http_response.status = 200
        mock_http_response.data = json.dumps(SAMPLE_FMP_CANDLES).encode("utf-8")

        mock_pool = MagicMock()
        mock_pool.request.return_value = mock_http_response

        import urllib3
        with patch.object(urllib3, "PoolManager", return_value=mock_pool), \
             patch("handlers.sp500_eod_ingest.get_fmp_api_key", return_value="test-key"):
            from handlers.sp500_eod_ingest import fetch_4h_candles
            fetch_4h_candles("AAPL", "2026-04-02")

        url_called = mock_pool.request.call_args[0][1]
        assert "symbol=AAPL" in url_called


# ============================================================================
# Test market closed check (weekends + holidays)
# ============================================================================
class TestMarketClosedCheck:
    """is_market_closed returns True for weekends and holidays."""

    def test_saturday_is_closed(self):
        from handlers.sp500_eod_ingest import is_market_closed
        assert is_market_closed("2026-04-04") is True  # Saturday

    def test_sunday_is_closed(self):
        from handlers.sp500_eod_ingest import is_market_closed
        assert is_market_closed("2026-04-05") is True  # Sunday

    def test_weekday_is_open(self):
        from handlers.sp500_eod_ingest import is_market_closed
        assert is_market_closed("2026-04-02") is False  # Thursday

    def test_christmas_is_closed(self):
        from handlers.sp500_eod_ingest import is_market_closed
        assert is_market_closed("2026-12-25") is True

    def test_july_4th_is_closed(self):
        from handlers.sp500_eod_ingest import is_market_closed
        assert is_market_closed("2026-07-04") is True

    def test_handler_skips_on_weekend(self):
        """Handler returns skipped=True for a Saturday date."""
        from handlers.sp500_eod_ingest import lambda_handler
        result = lambda_handler({"date": "2026-04-04"}, None)
        assert result["skipped"] is True
        assert "weekend or holiday" in result["body"].lower()

    def test_handler_skips_on_holiday(self):
        """Handler returns skipped=True for Christmas."""
        from handlers.sp500_eod_ingest import lambda_handler
        result = lambda_handler({"date": "2026-12-25"}, None)
        assert result["skipped"] is True

    def test_force_overrides_market_closed(self):
        """force=True should proceed even on a holiday."""
        mock_table = MagicMock()
        mock_table.query.return_value = {"Items": []}

        with patch("handlers.sp500_eod_ingest.table", mock_table), \
             patch("handlers.sp500_eod_ingest.get_sp500_tickers", return_value=["AAPL"]), \
             patch("handlers.sp500_eod_ingest.fetch_daily_eod", return_value=None), \
             patch("handlers.sp500_eod_ingest.time"):
            from handlers.sp500_eod_ingest import lambda_handler
            result = lambda_handler({"date": "2026-12-25", "force": True}, None)

        assert "skipped" not in result or result.get("skipped") is not True


# ============================================================================
# Test TTL (expires_at) on built items
# ============================================================================
class TestTTL:
    """Items include expires_at for DynamoDB TTL."""

    def test_items_have_expires_at(self):
        from handlers.sp500_eod_ingest import build_dynamo_items
        items = build_dynamo_items("AAPL", SAMPLE_FMP_CANDLES, "2026-04-02")

        for item in items:
            assert "expires_at" in item
            assert isinstance(item["expires_at"], int)
            # Should be roughly 365 days from now (within 2 days tolerance)
            import time as _time
            expected_min = int(_time.time()) + 363 * 86400
            expected_max = int(_time.time()) + 367 * 86400
            assert expected_min <= item["expires_at"] <= expected_max
