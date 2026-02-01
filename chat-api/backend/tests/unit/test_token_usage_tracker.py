"""
Unit tests for the Token Usage Tracker Module.

Tests the token usage tracking, limiting, and subscription tier functionality
for the monthly token limiting system.

Run with: pytest tests/unit/test_token_usage_tracker.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from decimal import Decimal
from botocore.exceptions import ClientError

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

            assert tracker.table_name == 'test-token-usage'

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


class TestGetCurrentMonth:
    """Tests for get_current_month static method."""

    def test_returns_yyyy_mm_format(self):
        """Test that current month is returned in YYYY-MM format."""
        from utils.token_usage_tracker import TokenUsageTracker

        result = TokenUsageTracker.get_current_month()

        # Should match pattern YYYY-MM
        assert len(result) == 7
        assert result[4] == '-'
        year, month = result.split('-')
        assert 2020 <= int(year) <= 2100
        assert 1 <= int(month) <= 12


class TestGetResetDate:
    """Tests for get_reset_date static method."""

    def test_returns_iso_format(self):
        """Test that reset date is returned in ISO format."""
        from utils.token_usage_tracker import TokenUsageTracker

        result = TokenUsageTracker.get_reset_date()

        # Should end with Z for UTC
        assert result.endswith('Z')
        # Should be parseable as ISO format
        datetime.fromisoformat(result.replace('Z', '+00:00'))

    def test_reset_date_is_first_of_next_month(self):
        """Test that reset date is the 1st of next month."""
        from utils.token_usage_tracker import TokenUsageTracker

        result = TokenUsageTracker.get_reset_date()
        reset_dt = datetime.fromisoformat(result.replace('Z', '+00:00'))

        # Should be the 1st
        assert reset_dt.day == 1
        # Should be midnight
        assert reset_dt.hour == 0
        assert reset_dt.minute == 0
        assert reset_dt.second == 0

    def test_december_wraps_to_january(self):
        """Test that December correctly wraps to January next year."""
        from utils.token_usage_tracker import TokenUsageTracker

        with patch('utils.token_usage_tracker.datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = datetime(2025, 12, 15, 10, 30, 0)

            result = TokenUsageTracker.get_reset_date()

            # Should be January 1st, 2026
            assert '2026-01-01' in result


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

    def test_allows_request_when_under_limit(self, tracker_with_mock_table):
        """Test that requests are allowed when under the limit."""
        tracker, mock_table = tracker_with_mock_table

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

    def test_denies_request_when_at_limit(self, tracker_with_mock_table):
        """Test that requests are denied when at the limit."""
        tracker, mock_table = tracker_with_mock_table

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

    def test_denies_request_when_over_limit(self, tracker_with_mock_table):
        """Test that requests are denied when over the limit."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {
            'Item': {
                'total_tokens': 1500000,
                'token_limit': 1000000
            }
        }

        result = tracker.check_limit('user-123')

        assert result['allowed'] is False

    def test_new_user_has_zero_usage(self, tracker_with_mock_table):
        """Test that new users start with zero usage."""
        tracker, mock_table = tracker_with_mock_table

        # No item found - new user
        mock_table.get_item.return_value = {}

        result = tracker.check_limit('new-user')

        assert result['allowed'] is True
        assert result['total_tokens'] == 0

    def test_fails_open_on_dynamodb_error(self, tracker_with_mock_table):
        """Test that requests are allowed on DynamoDB errors (fail open)."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'Test error'}},
            'GetItem'
        )

        result = tracker.check_limit('user-123')

        # Should fail open - allow the request
        assert result['allowed'] is True

    def test_includes_reset_date_in_response(self, tracker_with_mock_table):
        """Test that reset_date is included in the response."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {'Item': {'total_tokens': 0, 'token_limit': 1000000}}

        result = tracker.check_limit('user-123')

        assert 'reset_date' in result
        assert result['reset_date'].endswith('Z')


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

    def test_records_token_usage_atomically(self, tracker_with_mock_table):
        """Test that token usage is recorded with atomic update."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 5000,
                'token_limit': 1000000,
                'input_tokens': 2000,
                'output_tokens': 3000,
                'request_count': 1,
                'subscribed_at': '2025-01-01T00:00:00Z',
                'reset_date': '2025-02-01T00:00:00Z',
                'subscription_tier': 'plus'
            }
        }

        result = tracker.record_usage('user-123', input_tokens=2000, output_tokens=3000)

        # Verify update_item was called
        mock_table.update_item.assert_called_once()
        call_kwargs = mock_table.update_item.call_args[1]

        # Verify atomic ADD operation in UpdateExpression
        assert 'ADD input_tokens' in call_kwargs['UpdateExpression']
        assert 'ADD' in call_kwargs['UpdateExpression']

        # Verify result
        assert result['total_tokens'] == 5000
        assert result['remaining_tokens'] == 995000

    def test_persists_subscribed_at_on_first_usage(self, tracker_with_mock_table):
        """Test that subscribed_at is set on first usage via if_not_exists."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000,
                'token_limit': 1000000,
                'subscribed_at': '2025-01-15T10:00:00Z',
                'subscription_tier': 'free'
            }
        }

        tracker.record_usage('new-user', 500, 500)

        call_kwargs = mock_table.update_item.call_args[1]

        # Verify subscribed_at uses if_not_exists
        assert 'subscribed_at = if_not_exists(subscribed_at' in call_kwargs['UpdateExpression']

    def test_persists_reset_date(self, tracker_with_mock_table):
        """Test that reset_date is persisted in the record."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000,
                'token_limit': 1000000,
                'reset_date': '2025-02-01T00:00:00Z'
            }
        }

        tracker.record_usage('user-123', 500, 500)

        call_kwargs = mock_table.update_item.call_args[1]

        # Verify reset_date uses if_not_exists
        assert 'reset_date = if_not_exists(reset_date' in call_kwargs['UpdateExpression']
        assert ':reset' in call_kwargs['ExpressionAttributeValues']

    def test_persists_subscription_tier(self, tracker_with_mock_table):
        """Test that subscription_tier is persisted with default 'free'."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000,
                'token_limit': 1000000,
                'subscription_tier': 'free'
            }
        }

        tracker.record_usage('user-123', 500, 500)

        call_kwargs = mock_table.update_item.call_args[1]

        # Verify subscription_tier uses if_not_exists with 'free' default
        assert 'subscription_tier = if_not_exists(subscription_tier' in call_kwargs['UpdateExpression']
        assert call_kwargs['ExpressionAttributeValues'][':default_tier'] == 'free'

    def test_returns_threshold_reached_at_80_percent(self, tracker_with_mock_table):
        """Test that 80% threshold notification is returned."""
        tracker, mock_table = tracker_with_mock_table

        # Usage at 80%
        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 800000,
                'token_limit': 1000000,
                'notified_80': False
            }
        }

        result = tracker.record_usage('user-123', 50000, 50000)

        assert result['threshold_reached'] == '80%'

    def test_returns_threshold_reached_at_90_percent(self, tracker_with_mock_table):
        """Test that 90% threshold notification is returned."""
        tracker, mock_table = tracker_with_mock_table

        # Usage at 90%
        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 900000,
                'token_limit': 1000000,
                'notified_80': True,  # Already notified at 80%
                'notified_90': False
            }
        }

        result = tracker.record_usage('user-123', 50000, 50000)

        assert result['threshold_reached'] == '90%'

    def test_returns_threshold_reached_at_100_percent(self, tracker_with_mock_table):
        """Test that 100% threshold notification is returned."""
        tracker, mock_table = tracker_with_mock_table

        # Usage at 100%
        mock_table.update_item.return_value = {
            'Attributes': {
                'total_tokens': 1000000,
                'token_limit': 1000000,
                'notified_80': True,
                'notified_90': True,
                'limit_reached_at': None
            }
        }

        result = tracker.record_usage('user-123', 50000, 50000)

        assert result['threshold_reached'] == '100%'

    def test_handles_dynamodb_error_gracefully(self, tracker_with_mock_table):
        """Test that DynamoDB errors are handled gracefully."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.update_item.side_effect = ClientError(
            {'Error': {'Code': 'ServiceUnavailable', 'Message': 'Test error'}},
            'UpdateItem'
        )

        result = tracker.record_usage('user-123', 500, 500)

        # Should return error in result but not raise
        assert 'error' in result


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

    def test_returns_full_usage_statistics(self, tracker_with_mock_table):
        """Test that get_usage returns complete usage statistics."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {
            'Item': {
                'input_tokens': 200000,
                'output_tokens': 300000,
                'total_tokens': 500000,
                'token_limit': 1000000,
                'request_count': 50,
                'last_request_at': '2025-01-15T10:00:00Z',
                'subscribed_at': '2025-01-01T00:00:00Z',
                'reset_date': '2025-02-01T00:00:00Z',
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
        assert result['subscribed_at'] == '2025-01-01T00:00:00Z'
        assert result['subscription_tier'] == 'plus'

    def test_returns_empty_usage_for_new_user(self, tracker_with_mock_table):
        """Test that new users get empty usage response."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {}

        result = tracker.get_usage('new-user')

        assert result['total_tokens'] == 0
        assert result['request_count'] == 0
        assert result['subscribed_at'] is None
        assert result['subscription_tier'] == 'free'

    def test_includes_reset_date(self, tracker_with_mock_table):
        """Test that reset_date is included from stored value or computed."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {
            'Item': {
                'total_tokens': 100000,
                'token_limit': 1000000,
                'reset_date': '2025-02-01T00:00:00Z'
            }
        }

        result = tracker.get_usage('user-123')

        assert result['reset_date'] == '2025-02-01T00:00:00Z'


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

    def test_sets_custom_limit_for_user(self, tracker_with_mock_table):
        """Test that custom token limit can be set for a user."""
        tracker, mock_table = tracker_with_mock_table

        result = tracker.set_user_limit('user-123', 2000000)

        assert result is True
        mock_table.update_item.assert_called_once()

        call_kwargs = mock_table.update_item.call_args[1]
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


class TestMonthlyReset:
    """Tests for monthly reset behavior."""

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

    def test_month_key_format_enables_automatic_reset(self, tracker_with_mock_table):
        """Test that month is used as sort key enabling automatic monthly reset."""
        tracker, mock_table = tracker_with_mock_table

        mock_table.get_item.return_value = {'Item': {'total_tokens': 0}}

        tracker.check_limit('user-123')

        # Verify the key includes month in YYYY-MM format
        call_kwargs = mock_table.get_item.call_args[1]
        key = call_kwargs['Key']

        assert 'user_id' in key
        assert 'month' in key
        assert len(key['month']) == 7  # YYYY-MM format

    def test_new_month_starts_fresh(self, tracker_with_mock_table):
        """Test that a new month starts with zero usage."""
        tracker, mock_table = tracker_with_mock_table

        # Simulate no record for current month (new month started)
        mock_table.get_item.return_value = {}

        result = tracker.check_limit('user-123')

        assert result['allowed'] is True
        assert result['total_tokens'] == 0


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_check_token_limit_function(self):
        """Test the check_token_limit convenience function."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            mock_table.get_item.return_value = {
                'Item': {'total_tokens': 100000, 'token_limit': 1000000}
            }

            from utils.token_usage_tracker import check_token_limit

            result = check_token_limit('user-123')

            assert result['allowed'] is True

    def test_record_token_usage_function(self):
        """Test the record_token_usage convenience function."""
        with patch('boto3.resource') as mock_resource:
            mock_dynamodb = MagicMock()
            mock_table = MagicMock()
            mock_dynamodb.Table.return_value = mock_table
            mock_resource.return_value = mock_dynamodb

            mock_table.update_item.return_value = {
                'Attributes': {
                    'total_tokens': 5000,
                    'token_limit': 1000000
                }
            }

            from utils.token_usage_tracker import record_token_usage

            result = record_token_usage('user-123', 2500, 2500)

            assert result['total_tokens'] == 5000
