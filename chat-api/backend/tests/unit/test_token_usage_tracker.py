"""
Unit tests for the Token Usage Tracker Module.

Tests the token usage tracking, limiting, and anniversary-based billing
functionality for the monthly token limiting system.

Run with: pytest tests/unit/test_token_usage_tracker.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from botocore.exceptions import ClientError
from freezegun import freeze_time

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['TOKEN_USAGE_TABLE'] = 'test-token-usage'
os.environ['DEFAULT_TOKEN_LIMIT'] = '1000000'


class TestTokenUsageTrackerInit:
    """Tests for TokenUsageTracker initialization."""

    def test_default_table_name_uses_environment(self):
        """Test that default table name follows naming convention."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()

            assert tracker.table_name == 'buffett-test-token-usage'

    def test_custom_table_name_override(self):
        """Test that custom table name can be provided."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker(table_name='custom-table')

            assert tracker.table_name == 'custom-table'

    def test_default_limits_configuration(self):
        """Test that DEFAULT_LIMITS has correct tier configuration."""
        with patch('boto3.resource'):
            from utils.token_usage_tracker import TokenUsageTracker

            assert TokenUsageTracker.DEFAULT_LIMITS['anonymous'] == 0
            assert TokenUsageTracker.DEFAULT_LIMITS['free'] == 0
            assert TokenUsageTracker.DEFAULT_LIMITS['plus'] == 1000000


class TestGetAnniversaryResetDate:
    """Tests for get_anniversary_reset_date static method."""

    @freeze_time("2025-01-10 10:30:00", tz_offset=0)
    def test_reset_before_billing_day_this_month(self):
        """Test reset date when we're before the billing day this month."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is 10th -> reset on Jan 15
        result = TokenUsageTracker.get_anniversary_reset_date(15)

        assert '2025-01-15' in result
        assert result.endswith('Z')

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_reset_after_billing_day_next_month(self):
        """Test reset date when we're after the billing day this month."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is 20th -> reset on Feb 15
        result = TokenUsageTracker.get_anniversary_reset_date(15)

        assert '2025-02-15' in result
        assert result.endswith('Z')

    @freeze_time("2025-01-31 10:30:00", tz_offset=0)
    def test_february_with_billing_day_31(self):
        """Test that billing day 31 in February uses Feb 28."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 31st, but Feb only has 28 days
        result = TokenUsageTracker.get_anniversary_reset_date(31)

        # Should reset on Feb 28, 2025
        assert '2025-02-28' in result

    @freeze_time("2024-01-31 10:30:00", tz_offset=0)
    def test_leap_year_february_with_billing_day_30(self):
        """Test that billing day 30 in leap year February uses Feb 29."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 30th, but Feb 2024 (leap year) has 29 days
        result = TokenUsageTracker.get_anniversary_reset_date(30)

        # Should reset on Feb 29, 2024
        assert '2024-02-29' in result

    @freeze_time("2025-12-20 10:30:00", tz_offset=0)
    def test_december_wraps_to_january(self):
        """Test that December correctly wraps to January next year."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is Dec 20 -> reset on Jan 15, 2026
        result = TokenUsageTracker.get_anniversary_reset_date(15)

        assert '2026-01-15' in result
        assert result.endswith('Z')

    @freeze_time("2025-04-01 10:30:00", tz_offset=0)
    def test_april_with_billing_day_31(self):
        """Test that billing day 31 in April uses April 30."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 31st, but April only has 30 days
        # On April 1 with billing_day=31, next reset should be April 30
        result = TokenUsageTracker.get_anniversary_reset_date(31)

        # Should reset on April 30 (last day of April)
        assert '2025-04-30' in result

    @freeze_time("2025-01-15 00:00:00", tz_offset=0)
    def test_reset_on_billing_day_exactly(self):
        """Test reset date when we're exactly on the billing day."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is 15th at midnight -> already passed
        result = TokenUsageTracker.get_anniversary_reset_date(15)

        # Since we're at midnight on the 15th, the period started today
        # Next reset is Feb 15
        assert '2025-02-15' in result


class TestGetCurrentBillingPeriod:
    """Tests for get_current_billing_period static method."""

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_returns_current_period_after_billing_day(self):
        """Test billing period when after the billing day this month."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is 20th -> period started Jan 15
        period_key, start, end = TokenUsageTracker.get_current_billing_period(15)

        assert period_key == '2025-01-15'
        assert '2025-01-15' in start
        assert '2025-02-15' in end

    @freeze_time("2025-01-10 10:30:00", tz_offset=0)
    def test_returns_previous_period_before_billing_day(self):
        """Test billing period when before the billing day this month."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is 10th -> period started Dec 15
        period_key, start, end = TokenUsageTracker.get_current_billing_period(15)

        assert period_key == '2024-12-15'
        assert '2024-12-15' in start
        assert '2025-01-15' in end

    @freeze_time("2025-03-05 10:30:00", tz_offset=0)
    def test_february_edge_case_billing_day_31(self):
        """Test period calculation when billing day is 31 and prev month is Feb."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 31st, current is Mar 5 -> prev period started Feb 28
        period_key, start, end = TokenUsageTracker.get_current_billing_period(31)

        assert period_key == '2025-02-28'
        assert '2025-02-28' in start
        assert '2025-03-31' in end

    @freeze_time("2025-01-01 10:30:00", tz_offset=0)
    def test_year_boundary_previous_year(self):
        """Test period calculation at year boundary."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Billing day is 15th, current is Jan 1 -> period started Dec 15, 2024
        period_key, start, end = TokenUsageTracker.get_current_billing_period(15)

        assert period_key == '2024-12-15'
        assert '2024-12-15' in start
        assert '2025-01-15' in end


class TestGetBillingDay:
    """Tests for get_billing_day method."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    def test_returns_stored_billing_day(self, tracker_with_mock_table):
        """Test that stored billing_day is returned."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }

        result = tracker.get_billing_day('user-123')

        assert result == 15

    def test_fallback_to_subscribed_at(self, tracker_with_mock_table):
        """Test fallback to subscribed_at day when billing_day not set."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'subscribed_at': '2025-01-20T10:00:00Z'}]
        }

        result = tracker.get_billing_day('user-123')

        assert result == 20

    @freeze_time("2025-01-25 10:30:00", tz_offset=0)
    def test_default_to_current_day_for_new_user(self, tracker_with_mock_table):
        """Test default to current day for new users."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': []}

        result = tracker.get_billing_day('new-user')

        assert result == 25


class TestCheckLimit:
    """Tests for check_limit method."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_allows_request_when_under_limit(self, tracker_with_mock_table):
        """Test that requests are allowed when under the limit."""
        tracker, mock_table = tracker_with_mock_table

        # Mock get_billing_day query
        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }

        mock_table.get_item.return_value = {
            'Item': {
                'total_tokens': 500000,
                'token_limit': 1000000
            }
        }

        result = tracker.check_limit('user-123')

        assert result['allowed'] is True
        assert result['total_tokens'] == 500000
        assert result['token_limit'] == 1000000
        assert result['remaining_tokens'] == 500000
        assert result['percent_used'] == 50.0
        assert result['billing_day'] == 15

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_denies_request_when_at_limit(self, tracker_with_mock_table):
        """Test that requests are denied when at the limit."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }

        mock_table.get_item.return_value = {
            'Item': {
                'total_tokens': 1000000,
                'token_limit': 1000000,
                'limit_reached_at': '2025-01-15T10:00:00Z'
            }
        }

        result = tracker.check_limit('user-123')

        assert result['allowed'] is False
        assert result['remaining_tokens'] == 0
        assert result['percent_used'] == 100.0
        assert '2025-02-15' in result['reset_date']

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_uses_billing_period_key(self, tracker_with_mock_table):
        """Test that billing_period is used as the sort key."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }
        mock_table.get_item.return_value = {'Item': {'total_tokens': 0, 'token_limit': 1000000}}

        tracker.check_limit('user-123')

        # Verify the key uses billing_period
        call_kwargs = mock_table.get_item.call_args[1]
        key = call_kwargs['Key']

        assert 'user_id' in key
        assert 'billing_period' in key
        assert key['billing_period'] == '2025-01-15'

    def test_fails_open_on_dynamodb_error(self, tracker_with_mock_table):
        """Test that requests are allowed on DynamoDB errors (fail open)."""
        tracker, mock_table = tracker_with_mock_table

        # Mock get_billing_day to succeed (returns default day)
        mock_table.query.return_value = {'Items': []}

        # But get_item fails with a DynamoDB error
        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'Test error'}},
            'GetItem'
        )

        result = tracker.check_limit('user-123')

        # Should fail open - allow the request
        assert result['allowed'] is True


class TestRecordUsage:
    """Tests for record_usage method."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_records_token_usage_with_billing_period(self, tracker_with_mock_table):
        """Test that token usage is recorded with billing_period key."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 5000,
                'token_limit': 1000000,
                'input_tokens': 2000,
                'output_tokens': 3000,
                'request_count': 1,
                'billing_day': 15,
                'subscribed_at': '2025-01-15T00:00:00Z',
                'reset_date': '2025-02-15T00:00:00Z',
                'subscription_tier': 'plus'
            }
        }

        result = tracker.record_usage('user-123', input_tokens=2000, output_tokens=3000)

        # Verify update_item was called with billing_period key
        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs['Key']['billing_period'] == '2025-01-15'

        # Verify result
        assert result['total_tokens'] == 5000
        assert result['remaining_tokens'] == 995000
        assert result['billing_day'] == 15
        assert '2025-02-15' in result['reset_date']

    @freeze_time("2025-01-25 10:30:00", tz_offset=0)
    def test_sets_billing_day_on_first_usage(self, tracker_with_mock_table):
        """Test that billing_day is set on first usage via if_not_exists."""
        tracker, mock_table = tracker_with_mock_table

        # New user - no existing records
        mock_table.query.return_value = {'Items': []}

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000,
                'token_limit': 1000000,
                'billing_day': 25,
                'subscribed_at': '2025-01-25T10:30:00Z',
                'subscription_tier': 'free'
            }
        }

        result = tracker.record_usage('new-user', 500, 500)

        call_kwargs = mock_table.update_item.call_args[1]

        # Verify billing_day uses if_not_exists
        assert 'billing_day = if_not_exists(billing_day' in call_kwargs['UpdateExpression']
        # New user should get billing_day = 25 (current day)
        assert result['billing_day'] == 25

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_persists_billing_period_timestamps(self, tracker_with_mock_table):
        """Test that billing_period_start and billing_period_end are persisted."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000,
                'token_limit': 1000000,
                'billing_day': 15
            }
        }

        tracker.record_usage('user-123', 500, 500)

        call_kwargs = mock_table.update_item.call_args[1]

        # Verify billing period timestamps are set
        assert 'billing_period_start = if_not_exists(billing_period_start' in call_kwargs['UpdateExpression']
        assert 'billing_period_end = if_not_exists(billing_period_end' in call_kwargs['UpdateExpression']
        assert ':period_start' in call_kwargs['ExpressionAttributeValues']
        assert ':period_end' in call_kwargs['ExpressionAttributeValues']

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_returns_threshold_reached_at_80_percent(self, tracker_with_mock_table):
        """Test that 80% threshold notification is returned."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': [{'billing_day': 15}]}

        # Usage at 80%
        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 800000,
                'token_limit': 1000000,
                'billing_day': 15,
                'notified_80': False
            }
        }

        result = tracker.record_usage('user-123', 50000, 50000)

        assert result['threshold_reached'] == '80%'


class TestGetUsage:
    """Tests for get_usage method."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_returns_full_usage_statistics(self, tracker_with_mock_table):
        """Test that get_usage returns complete usage statistics."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': [{'billing_day': 15}]}

        mock_table.get_item.return_value = {
            'Item': {
                'input_tokens': 200000,
                'output_tokens': 300000,
                'total_tokens': 500000,
                'token_limit': 1000000,
                'request_count': 50,
                'billing_day': 15,
                'last_request_at': '2025-01-15T10:00:00Z',
                'subscribed_at': '2025-01-15T00:00:00Z',
                'reset_date': '2025-02-15T00:00:00Z',
                'billing_period_start': '2025-01-15T00:00:00Z',
                'billing_period_end': '2025-02-15T00:00:00Z',
                'subscription_tier': 'plus'
            }
        }

        result = tracker.get_usage('user-123')

        assert result['input_tokens'] == 200000
        assert result['output_tokens'] == 300000
        assert result['total_tokens'] == 500000
        assert result['token_limit'] == 1000000
        assert result['percent_used'] == 50.0
        assert result['remaining_tokens'] == 500000
        assert result['request_count'] == 50
        assert result['billing_day'] == 15
        assert result['subscribed_at'] == '2025-01-15T00:00:00Z'
        assert result['subscription_tier'] == 'plus'
        assert '2025-02-15' in result['reset_date']

    @freeze_time("2025-01-25 10:30:00", tz_offset=0)
    def test_returns_empty_usage_for_new_user(self, tracker_with_mock_table):
        """Test that new users get empty usage response with correct billing day."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': []}
        mock_table.get_item.return_value = {}

        result = tracker.get_usage('new-user')

        assert result['total_tokens'] == 0
        assert result['request_count'] == 0
        assert result['subscribed_at'] is None
        assert result['subscription_tier'] == 'free'
        assert result['billing_day'] == 25  # Current day for new user

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_uses_billing_period_key(self, tracker_with_mock_table):
        """Test that get_usage uses billing_period key."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': [{'billing_day': 15}]}
        mock_table.get_item.return_value = {'Item': {'total_tokens': 0, 'billing_day': 15}}

        tracker.get_usage('user-123')

        call_kwargs = mock_table.get_item.call_args[1]
        key = call_kwargs['Key']

        assert 'billing_period' in key
        assert key['billing_period'] == '2025-01-15'


class TestSetUserLimit:
    """Tests for set_user_limit method."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_sets_custom_limit_for_user(self, tracker_with_mock_table):
        """Test that custom token limit can be set for a user."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {'Items': [{'billing_day': 15}]}

        result = tracker.set_user_limit('user-123', 2000000)

        assert result is True
        mock_table.update_item.assert_called_once()

        call_kwargs = mock_table.update_item.call_args[1]
        assert call_kwargs['Key']['billing_period'] == '2025-01-15'
        assert call_kwargs['ExpressionAttributeValues'][':limit'] == 2000000


class TestSubscriptionTiers:
    """Tests for subscription tier functionality."""

    def test_free_tier_has_zero_limit(self):
        """Test that free tier users have zero token limit."""
        with patch('boto3.resource'):
            from utils.token_usage_tracker import TokenUsageTracker

            assert TokenUsageTracker.DEFAULT_LIMITS['free'] == 0

    def test_plus_tier_has_one_million_limit(self):
        """Test that plus tier users have 1M token limit."""
        with patch('boto3.resource'):
            from utils.token_usage_tracker import TokenUsageTracker

            assert TokenUsageTracker.DEFAULT_LIMITS['plus'] == 1000000

    def test_anonymous_has_zero_limit(self):
        """Test that anonymous users have zero token limit."""
        with patch('boto3.resource'):
            from utils.token_usage_tracker import TokenUsageTracker

            assert TokenUsageTracker.DEFAULT_LIMITS['anonymous'] == 0


class TestAnniversaryBasedReset:
    """Tests for anniversary-based reset behavior."""

    @pytest.fixture
    def tracker_with_mock_table(self):
        """Create tracker with mocked DynamoDB table."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            from utils.token_usage_tracker import TokenUsageTracker
            tracker = TokenUsageTracker()
            tracker.table = mock_table

            yield tracker, mock_table

    @freeze_time("2025-02-10 10:30:00", tz_offset=0)
    def test_mid_month_subscription_uses_correct_period(self, tracker_with_mock_table):
        """Test user subscribed mid-month has correct billing period."""
        tracker, mock_table = tracker_with_mock_table

        # User subscribed on Jan 15
        mock_table.query.return_value = {
            'Items': [{'billing_day': 15, 'subscribed_at': '2025-01-15T10:00:00Z'}]
        }
        mock_table.get_item.return_value = {'Item': {'total_tokens': 0}}

        tracker.check_limit('user-123')

        call_kwargs = mock_table.get_item.call_args[1]
        # On Feb 10 with billing_day 15, the current period started Jan 15
        assert call_kwargs['Key']['billing_period'] == '2025-01-15'

    @freeze_time("2025-02-20 10:30:00", tz_offset=0)
    def test_new_period_starts_on_billing_day(self, tracker_with_mock_table):
        """Test that new period starts exactly on billing day."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.query.return_value = {
            'Items': [{'billing_day': 15}]
        }
        mock_table.get_item.return_value = {'Item': {'total_tokens': 0}}

        tracker.check_limit('user-123')

        call_kwargs = mock_table.get_item.call_args[1]
        # On Feb 20 with billing_day 15, current period started Feb 15
        assert call_kwargs['Key']['billing_period'] == '2025-02-15'

    @freeze_time("2025-03-15 10:30:00", tz_offset=0)
    def test_end_of_month_subscription_february(self, tracker_with_mock_table):
        """Test user subscribed on 31st uses Feb 28 for February period."""
        tracker, mock_table = tracker_with_mock_table

        # User subscribed on Jan 31
        mock_table.query.return_value = {
            'Items': [{'billing_day': 31}]
        }
        mock_table.get_item.return_value = {'Item': {'total_tokens': 0}}

        tracker.check_limit('user-123')

        call_kwargs = mock_table.get_item.call_args[1]
        # On Mar 15 with billing_day 31, current period started Feb 28 (Feb has 28 days in 2025)
        assert call_kwargs['Key']['billing_period'] == '2025-02-28'


class TestEdgeCases:
    """Tests for edge cases in anniversary-based billing."""

    @freeze_time("2025-01-31 23:59:59", tz_offset=0)
    def test_end_of_month_at_midnight(self):
        """Test billing period at end of month just before midnight."""
        from utils.token_usage_tracker import TokenUsageTracker

        # User with billing day 31
        period_key, start, end = TokenUsageTracker.get_current_billing_period(31)

        assert period_key == '2025-01-31'
        assert '2025-01-31' in start
        assert '2025-02-28' in end  # Feb has 28 days in 2025

    @freeze_time("2024-02-29 10:30:00", tz_offset=0)
    def test_leap_year_february_29(self):
        """Test billing period on leap year February 29."""
        from utils.token_usage_tracker import TokenUsageTracker

        # User with billing day 29
        period_key, start, end = TokenUsageTracker.get_current_billing_period(29)

        assert period_key == '2024-02-29'
        assert '2024-02-29' in start
        assert '2024-03-29' in end

    @freeze_time("2025-12-31 10:30:00", tz_offset=0)
    def test_year_rollover_billing_day_31(self):
        """Test year rollover with billing day 31."""
        from utils.token_usage_tracker import TokenUsageTracker

        reset_date = TokenUsageTracker.get_anniversary_reset_date(31)

        # Next occurrence of 31st is Jan 31, 2026
        assert '2026-01-31' in reset_date

    def test_billing_day_clamped_to_valid_range(self):
        """Test that billing_day is clamped to 1-31 range."""
        from utils.token_usage_tracker import TokenUsageTracker

        # Test with out-of-range values
        reset_low = TokenUsageTracker.get_anniversary_reset_date(0)
        reset_high = TokenUsageTracker.get_anniversary_reset_date(50)

        # Both should produce valid dates (clamped to 1 and 31)
        assert 'T00:00:00Z' in reset_low
        assert 'T00:00:00Z' in reset_high


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_check_token_limit_function(self):
        """Test the check_token_limit convenience function."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            mock_table.query.return_value = {'Items': [{'billing_day': 15}]}
            mock_table.get_item.return_value = {
                'Item': {'total_tokens': 100000, 'token_limit': 1000000}
            }

            from utils.token_usage_tracker import check_token_limit

            result = check_token_limit('user-123')

            assert result['allowed'] is True

    @freeze_time("2025-01-20 10:30:00", tz_offset=0)
    def test_record_token_usage_function(self):
        """Test the record_token_usage convenience function."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            mock_table.query.return_value = {'Items': [{'billing_day': 15}]}
            mock_table.update_item.return_value = {
                'Attributes': {
                    'total_tokens': 5000,
                    'token_limit': 1000000,
                    'billing_day': 15
                }
            }

            from utils.token_usage_tracker import record_token_usage

            result = record_token_usage('user-123', 2500, 2500)

            assert result['total_tokens'] == 5000
            assert result['billing_day'] == 15


class TestLegacyCompatibility:
    """Tests for backwards compatibility with legacy methods."""

    def test_get_current_month_still_works(self):
        """Test that get_current_month still returns YYYY-MM format."""
        from utils.token_usage_tracker import TokenUsageTracker

        result = TokenUsageTracker.get_current_month()

        assert len(result) == 7
        assert result[4] == '-'

    def test_get_reset_date_still_works(self):
        """Test that legacy get_reset_date still returns 1st of next month."""
        from utils.token_usage_tracker import TokenUsageTracker

        result = TokenUsageTracker.get_reset_date()

        assert result.endswith('Z')
        # Parse and verify it's the 1st
        dt = datetime.fromisoformat(result.replace('Z', '+00:00'))
        assert dt.day == 1
