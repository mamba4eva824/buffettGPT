"""
Earnings Tracker for Investment Research Reports

Tracks company earnings dates to determine when reports need refreshing.
Uses FMP Earnings Calendar API to check if new earnings have been released.

This module focuses on checking EXISTING reports in DynamoDB for staleness,
not pre-fetching earnings for all possible tickers.

Key Functions:
- get_existing_reports(): Get all reports currently in DynamoDB
- check_needs_refresh(ticker): Check if a specific report needs refresh
- get_stale_reports(): Get list of existing reports needing refresh due to new earnings
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

import boto3
import requests
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)

# FMP API endpoints
FMP_STABLE_URL = "https://financialmodelingprep.com/stable"


def _get_fmp_api_key_from_secrets(region: str = 'us-east-1') -> Optional[str]:
    """
    Retrieve FMP API key from AWS Secrets Manager.
    Secret structure: {"FMP_API_KEY": "<actual-key>"}
    """
    secret_name = os.environ.get('FMP_SECRET_NAME', 'buffett-dev-fmp')
    try:
        secrets_client = boto3.client('secretsmanager', region_name=region)
        response = secrets_client.get_secret_value(SecretId=secret_name)
        secret_dict = json.loads(response['SecretString'])
        return secret_dict['FMP_API_KEY']
    except Exception as e:
        logger.error(f"Failed to retrieve FMP API key from secrets: {e}")
        return None


class EarningsTracker:
    """
    Tracks earnings dates for companies with existing reports in DynamoDB.

    Focused approach: Only check staleness for reports we've already generated,
    not all possible tickers.

    Usage:
        tracker = EarningsTracker()

        # Get all existing reports
        reports = tracker.get_existing_reports()

        # Check if a specific report needs refresh
        needs_refresh = tracker.check_needs_refresh('AAPL')

        # Get all stale reports
        stale = tracker.get_stale_reports()
    """

    def __init__(self, environment: str = None, region: str = 'us-east-1'):
        """
        Initialize the earnings tracker.

        Args:
            environment: Environment name (dev, staging, prod). Auto-detected if not provided.
            region: AWS region for DynamoDB access
        """
        self.environment = environment or os.environ.get('ENVIRONMENT', 'dev')
        self.region = region

        # Get FMP API key from environment or AWS Secrets Manager
        self.fmp_api_key = os.environ.get('FMP_API_KEY')
        if not self.fmp_api_key:
            self.fmp_api_key = _get_fmp_api_key_from_secrets(region)

        # Initialize DynamoDB for report metadata lookup
        self.dynamodb = boto3.resource('dynamodb', region_name=region)
        self.reports_table_v2 = self.dynamodb.Table(f'investment-reports-v2-{self.environment}')

        # Cache for earnings calendar (avoid repeated API calls)
        self._earnings_calendar_cache: Optional[Dict[str, List[Dict]]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=6)  # Cache earnings calendar for 6 hours

    def get_existing_reports(self) -> List[Dict[str, Any]]:
        """
        Get all existing reports from DynamoDB (executive items only).

        Returns:
            List of report metadata dicts with ticker, generated_at, last_earnings_date
        """
        reports = []

        try:
            # Scan for all 00_executive items (one per report)
            response = self.reports_table_v2.scan(
                FilterExpression='section_id = :sid',
                ExpressionAttributeValues={':sid': '00_executive'},
                ProjectionExpression='ticker, generated_at, last_earnings_date, company_name'
            )

            reports = response.get('Items', [])

            # Handle pagination
            while 'LastEvaluatedKey' in response:
                response = self.reports_table_v2.scan(
                    FilterExpression='section_id = :sid',
                    ExpressionAttributeValues={':sid': '00_executive'},
                    ProjectionExpression='ticker, generated_at, last_earnings_date, company_name',
                    ExclusiveStartKey=response['LastEvaluatedKey']
                )
                reports.extend(response.get('Items', []))

            logger.info(f"Found {len(reports)} existing reports in DynamoDB")
            return reports

        except Exception as e:
            logger.error(f"Failed to get existing reports: {e}")
            return []

    def _fetch_earnings_calendar(self, days_back: int = 90, days_forward: int = 30) -> Dict[str, List[Dict]]:
        """
        Fetch earnings calendar and index by ticker.

        Uses the stable FMP endpoint with date range.
        Results are cached to avoid repeated API calls.

        Args:
            days_back: Days in the past to fetch
            days_forward: Days in the future to fetch

        Returns:
            Dict mapping ticker -> list of earnings events
        """
        # Check cache
        if (self._earnings_calendar_cache is not None and
            self._cache_timestamp is not None and
            datetime.utcnow() - self._cache_timestamp < self._cache_ttl):
            return self._earnings_calendar_cache

        if not self.fmp_api_key:
            logger.warning("FMP_API_KEY not set, cannot fetch earnings calendar")
            return {}

        today = datetime.utcnow()
        from_date = (today - timedelta(days=days_back)).strftime('%Y-%m-%d')
        to_date = (today + timedelta(days=days_forward)).strftime('%Y-%m-%d')

        try:
            url = f"{FMP_STABLE_URL}/earnings-calendar"
            params = {
                'apikey': self.fmp_api_key,
                'from': from_date,
                'to': to_date
            }

            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Fetched {len(data)} earnings events from {from_date} to {to_date}")

            # Index by ticker
            earnings_by_ticker: Dict[str, List[Dict]] = {}
            for event in data:
                ticker = event.get('symbol', '').upper()
                if ticker:
                    if ticker not in earnings_by_ticker:
                        earnings_by_ticker[ticker] = []
                    earnings_by_ticker[ticker].append(event)

            # Sort each ticker's events by date
            for ticker in earnings_by_ticker:
                earnings_by_ticker[ticker].sort(key=lambda x: x.get('date', ''), reverse=True)

            # Cache results
            self._earnings_calendar_cache = earnings_by_ticker
            self._cache_timestamp = datetime.utcnow()

            return earnings_by_ticker

        except requests.RequestException as e:
            logger.error(f"Failed to fetch earnings calendar: {e}")
            return {}

    def get_latest_earnings_date(self, ticker: str) -> Optional[str]:
        """
        Get the most recent earnings date for a ticker (with actual results).

        Args:
            ticker: Stock symbol (e.g., 'AAPL')

        Returns:
            ISO date string (YYYY-MM-DD) of most recent earnings, or None if not found
        """
        ticker = ticker.upper()
        earnings_calendar = self._fetch_earnings_calendar()

        if ticker not in earnings_calendar:
            logger.info(f"No earnings data found for {ticker} in calendar")
            return None

        today = datetime.utcnow().date()

        # Find most recent past earnings with actual results
        for event in earnings_calendar[ticker]:
            event_date_str = event.get('date')
            if not event_date_str:
                continue

            try:
                event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                # Must be in the past and have actual results
                if event_date <= today and event.get('epsActual') is not None:
                    logger.info(f"Latest earnings for {ticker}: {event_date_str}")
                    return event_date_str
            except ValueError:
                continue

        logger.info(f"No past earnings with actual results found for {ticker}")
        return None

    def get_upcoming_earnings_date(self, ticker: str) -> Optional[str]:
        """
        Get the next scheduled earnings date for a ticker.

        Args:
            ticker: Stock symbol (e.g., 'AAPL')

        Returns:
            ISO date string (YYYY-MM-DD) of next earnings, or None if not found
        """
        ticker = ticker.upper()
        earnings_calendar = self._fetch_earnings_calendar()

        if ticker not in earnings_calendar:
            return None

        today = datetime.utcnow().date()

        # Find next future earnings (reverse since sorted desc)
        for event in reversed(earnings_calendar[ticker]):
            event_date_str = event.get('date')
            if not event_date_str:
                continue

            try:
                event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
                if event_date > today:
                    logger.info(f"Upcoming earnings for {ticker}: {event_date_str}")
                    return event_date_str
            except ValueError:
                continue

        return None

    def check_needs_refresh(self, ticker: str) -> Dict[str, Any]:
        """
        Check if a report needs refresh based on new earnings.

        A report needs refresh if:
        1. New earnings have been released since the report was generated
        2. The report's last_earnings_date is older than current latest earnings
        3. The report doesn't have a last_earnings_date (legacy report)

        Args:
            ticker: Stock symbol

        Returns:
            Dict with:
                - needs_refresh: bool
                - reason: str (why refresh is needed)
                - report_date: str (when report was generated)
                - last_earnings_stored: str (earnings date stored with report)
                - current_latest_earnings: str (latest earnings from FMP)
                - upcoming_earnings: str (next scheduled earnings)
        """
        ticker = ticker.upper()
        result = {
            'ticker': ticker,
            'needs_refresh': False,
            'reason': None,
            'report_date': None,
            'last_earnings_stored': None,
            'current_latest_earnings': None,
            'upcoming_earnings': None
        }

        # Get report metadata from DynamoDB
        try:
            response = self.reports_table_v2.get_item(
                Key={'ticker': ticker, 'section_id': '00_executive'},
                ProjectionExpression='ticker, generated_at, last_earnings_date'
            )
        except Exception as e:
            logger.error(f"Failed to get report for {ticker}: {e}")
            result['reason'] = f'db_error: {e}'
            return result

        if 'Item' not in response:
            result['reason'] = 'no_report_exists'
            return result

        report = response['Item']
        result['report_date'] = report.get('generated_at')
        result['last_earnings_stored'] = report.get('last_earnings_date')

        # Get current earnings info
        result['current_latest_earnings'] = self.get_latest_earnings_date(ticker)
        result['upcoming_earnings'] = self.get_upcoming_earnings_date(ticker)

        # Check if refresh is needed
        if not result['report_date']:
            result['needs_refresh'] = True
            result['reason'] = 'missing_report_date'
            return result

        # If we have stored earnings date, compare with current
        if result['last_earnings_stored'] and result['current_latest_earnings']:
            if result['current_latest_earnings'] > result['last_earnings_stored']:
                result['needs_refresh'] = True
                result['reason'] = 'new_earnings_released'
                return result

        # If no stored earnings but we found current earnings, check against report date
        if not result['last_earnings_stored'] and result['current_latest_earnings']:
            try:
                report_date = datetime.fromisoformat(
                    result['report_date'].replace('Z', '+00:00')
                ).date()
                earnings_date = datetime.strptime(
                    result['current_latest_earnings'], '%Y-%m-%d'
                ).date()

                if earnings_date > report_date:
                    result['needs_refresh'] = True
                    result['reason'] = 'earnings_after_report_generation'
                    return result
            except (ValueError, TypeError) as e:
                logger.warning(f"Date comparison error for {ticker}: {e}")

        result['reason'] = 'up_to_date'
        return result

    def get_stale_reports(self) -> List[Dict[str, Any]]:
        """
        Get all existing reports that need refresh due to new earnings.

        Scans all reports in DynamoDB and checks each against FMP earnings calendar.

        Returns:
            List of stale report dicts with ticker, reason, dates, etc.
        """
        existing_reports = self.get_existing_reports()

        if not existing_reports:
            logger.info("No existing reports found in DynamoDB")
            return []

        stale_reports = []
        tickers = [r['ticker'] for r in existing_reports]

        logger.info(f"Checking {len(tickers)} reports for staleness...")

        for ticker in tickers:
            result = self.check_needs_refresh(ticker)
            if result['needs_refresh']:
                stale_reports.append(result)
                logger.info(
                    f"  {ticker}: STALE - {result['reason']} "
                    f"(stored: {result['last_earnings_stored']}, "
                    f"current: {result['current_latest_earnings']})"
                )

        logger.info(f"Found {len(stale_reports)} stale reports out of {len(tickers)}")
        return stale_reports

    def get_reports_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all reports and their staleness status.

        Returns:
            Dict with counts and lists of fresh/stale reports
        """
        existing_reports = self.get_existing_reports()
        tickers = [r['ticker'] for r in existing_reports]

        fresh = []
        stale = []
        unknown = []

        for ticker in tickers:
            result = self.check_needs_refresh(ticker)
            if result['needs_refresh']:
                stale.append(result)
            elif result['reason'] == 'up_to_date':
                fresh.append(result)
            else:
                unknown.append(result)

        return {
            'total_reports': len(tickers),
            'fresh_count': len(fresh),
            'stale_count': len(stale),
            'unknown_count': len(unknown),
            'fresh_reports': fresh,
            'stale_reports': stale,
            'unknown_reports': unknown
        }


# Convenience functions for CLI/script usage

def get_stale_tickers() -> List[str]:
    """Get list of tickers whose reports need refresh."""
    tracker = EarningsTracker()
    stale_reports = tracker.get_stale_reports()
    return [r['ticker'] for r in stale_reports]


def check_ticker(ticker: str) -> Dict[str, Any]:
    """Check if a specific ticker's report needs refresh."""
    tracker = EarningsTracker()
    return tracker.check_needs_refresh(ticker)


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python earnings_tracker.py [check <TICKER> | stale | summary]")
        sys.exit(1)

    action = sys.argv[1].lower()
    tracker = EarningsTracker()

    if action == 'check' and len(sys.argv) > 2:
        ticker = sys.argv[2].upper()
        result = tracker.check_needs_refresh(ticker)
        print(f"\n{ticker} Report Status:")
        print(f"  Needs Refresh: {result['needs_refresh']}")
        print(f"  Reason: {result['reason']}")
        print(f"  Report Date: {result['report_date']}")
        print(f"  Stored Earnings: {result['last_earnings_stored']}")
        print(f"  Current Earnings: {result['current_latest_earnings']}")
        print(f"  Upcoming Earnings: {result['upcoming_earnings']}")

    elif action == 'stale':
        stale = tracker.get_stale_reports()
        print(f"\nStale Reports ({len(stale)}):")
        for r in stale:
            print(f"  {r['ticker']}: {r['reason']}")

    elif action == 'summary':
        summary = tracker.get_reports_summary()
        print(f"\nReports Summary:")
        print(f"  Total: {summary['total_reports']}")
        print(f"  Fresh: {summary['fresh_count']}")
        print(f"  Stale: {summary['stale_count']}")
        print(f"  Unknown: {summary['unknown_count']}")

        if summary['stale_reports']:
            print(f"\nStale Reports:")
            for r in summary['stale_reports']:
                print(f"  {r['ticker']}: {r['reason']}")

    else:
        print(f"Unknown action: {action}")
        sys.exit(1)
