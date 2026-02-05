"""
Unit tests for migrate_to_v2.py migration script.

Tests the ReportMigrator class that converts v1 reports (single-blob)
to v2 section-based schema.

Tests:
- ReportMigrator initialization
- get_v1_reports() - Fetching reports from v1 table
- check_v2_exists() - Checking if already migrated
- migrate_report() - Core migration logic
- run_migration() - Full migration workflow

Run:
    cd chat-api/backend
    pytest investment_research/tests/test_migrate_to_v2.py -v

Or directly:
    python -m pytest investment_research/tests/test_migrate_to_v2.py -v
"""

import os
import sys
import json
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, call

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from investment_research.migrate_to_v2 import ReportMigrator


# =============================================================================
# MOCK DATA
# =============================================================================

SAMPLE_V1_REPORT_CONTENT = '''
## TL;DR

Apple is the digital bouncer for premium tech. Revenue is flat but they're swimming in cash.

## What Does AAPL Actually Do?

Apple sells premium hardware and services.

## Apple's 2024 Report Card

| Question | What's Happening | Flag |
|----------|------------------|------|
| **How fast are they growing?** | 3% | Y |

## Investment Fit Assessment

| Investor Type | Verdict |
|---------------|---------|
| Building first portfolio | Y |

## The Verdict

| Category | Rating |
|----------|--------|
| Are they growing? | 3 stars |

**Overall:** HOLD - Conviction: High

## From 3% to 4%: The Growth Crawl

Apple's growth has slowed.

**Bottom line:** ~ steady

## 77% Margins: The Profit Machine

Apple keeps 77 cents of every dollar.

**Bottom line:** + pristine margins

## 30% Off: Apple's Cheapest in 5 Years

Valuation looks good.

**Bottom line:** + on sale

## Clean Books: What You See Is What You Get

Clean earnings.

**Bottom line:** + trustworthy

## The Cash Machine

Strong cash flow.

**Bottom line:** + cash machine

## The War Chest

Net cash position.

**Bottom line:** + fortress balance sheet

## Buying Back Faster Than They're Printing

Strong buybacks.

**Bottom line:** + buyback king

## Bull Case

1. Services growth
2. Cash machine

## Bear Case

1. Hardware saturation
2. China risk

## Warning Signs Checklist

| The Question | Status |
|--------------|--------|
| Are sales growing? | Y |

## 6-Point Vibe Check

| Apple's Story | What's Happening |
|---------------|------------------|
| **Growth** | 3% |

## Real Talk

Apple is the blue chip of blue chips.

```json
{
  "growth": {"rating": "Stable", "confidence": "High", "key_factors": ["3% revenue growth"]},
  "profitability": {"rating": "Very Strong", "confidence": "High", "key_factors": ["77% gross margin"]},
  "overall_verdict": "HOLD",
  "conviction": "High"
}
```
'''

SAMPLE_V1_ITEM = {
    'ticker': 'AAPL',
    'fiscal_year': 2024,
    'report_content': SAMPLE_V1_REPORT_CONTENT,
    'ratings': {
        'debt': {'rating': 'Strong', 'confidence': 'High'},
        'cashflow': {'rating': 'Very Strong', 'confidence': 'High'},
        'growth': {'rating': 'Stable', 'confidence': 'High'},
        'overall_verdict': 'HOLD',
        'conviction': 'High'
    },
    'generated_at': '2024-01-01T12:00:00Z',
    'model': 'claude-3-sonnet-20240229',
    'ttl': Decimal(str(int((datetime.utcnow() + timedelta(days=90)).timestamp())))
}


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_dynamodb():
    """Mock DynamoDB resources."""
    with patch('investment_research.migrate_to_v2.boto3') as mock_boto:
        mock_resource = MagicMock()
        mock_boto.resource.return_value = mock_resource

        mock_v1_table = MagicMock()
        mock_v2_table = MagicMock()

        def table_factory(name):
            if 'v2' in name:
                return mock_v2_table
            return mock_v1_table

        mock_resource.Table = table_factory

        yield {
            'boto': mock_boto,
            'resource': mock_resource,
            'v1_table': mock_v1_table,
            'v2_table': mock_v2_table
        }


@pytest.fixture
def migrator(mock_dynamodb):
    """Create ReportMigrator with mocked DynamoDB."""
    return ReportMigrator(environment='dev', region='us-east-1')


# =============================================================================
# INITIALIZATION TESTS
# =============================================================================

class TestReportMigratorInit:
    """Tests for ReportMigrator initialization."""

    def test_init_sets_table_names(self, mock_dynamodb):
        """Should set v1 and v2 table names based on environment."""
        migrator = ReportMigrator(environment='dev', region='us-east-1')

        assert migrator.v1_table_name == 'investment-reports-dev'
        assert migrator.v2_table_name == 'investment-reports-v2-dev'

    def test_init_prod_environment(self, mock_dynamodb):
        """Should use prod table names for prod environment."""
        migrator = ReportMigrator(environment='prod', region='us-east-1')

        assert migrator.v1_table_name == 'investment-reports-prod'
        assert migrator.v2_table_name == 'investment-reports-v2-prod'

    def test_init_creates_dynamodb_resource(self, mock_dynamodb):
        """Should create DynamoDB resource with correct region."""
        ReportMigrator(environment='dev', region='us-west-2')

        mock_dynamodb['boto'].resource.assert_called_with(
            'dynamodb', region_name='us-west-2'
        )


# =============================================================================
# GET_V1_REPORTS TESTS
# =============================================================================

class TestGetV1Reports:
    """Tests for get_v1_reports method."""

    def test_get_v1_reports_specific_tickers(self, migrator, mock_dynamodb):
        """Should fetch specific tickers when provided."""
        mock_dynamodb['v1_table'].get_item.return_value = {'Item': SAMPLE_V1_ITEM}

        reports = migrator.get_v1_reports(tickers=['AAPL', 'MSFT'])

        assert len(reports) == 2
        assert mock_dynamodb['v1_table'].get_item.call_count == 2

    def test_get_v1_reports_handles_missing_ticker(self, migrator, mock_dynamodb):
        """Should handle tickers not found in v1 table."""
        mock_dynamodb['v1_table'].get_item.return_value = {}  # No Item

        reports = migrator.get_v1_reports(tickers=['NOTFOUND'])

        assert len(reports) == 0

    def test_get_v1_reports_scan_all(self, migrator, mock_dynamodb):
        """Should scan all reports when no tickers specified."""
        # Mock paginator
        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Items': [SAMPLE_V1_ITEM]},
            {'Items': [{'ticker': 'MSFT', 'fiscal_year': 2024, 'report_content': 'content'}]}
        ]

        reports = migrator.get_v1_reports()  # No tickers

        assert len(reports) == 2
        mock_dynamodb['v1_table'].meta.client.get_paginator.assert_called_with('scan')

    def test_get_v1_reports_uppercases_tickers(self, migrator, mock_dynamodb):
        """Should uppercase ticker symbols."""
        mock_dynamodb['v1_table'].get_item.return_value = {'Item': SAMPLE_V1_ITEM}

        migrator.get_v1_reports(tickers=['aapl'])

        # Check that uppercase ticker was used in the key
        call_args = mock_dynamodb['v1_table'].get_item.call_args
        assert call_args[1]['Key']['ticker'] == 'AAPL'


# =============================================================================
# CHECK_V2_EXISTS TESTS
# =============================================================================

class TestCheckV2Exists:
    """Tests for check_v2_exists method."""

    def test_check_v2_exists_returns_true_when_found(self, migrator, mock_dynamodb):
        """Should return True if executive item exists in v2."""
        mock_dynamodb['v2_table'].get_item.return_value = {
            'Item': {'ticker': 'AAPL', 'section_id': '00_executive'}
        }

        result = migrator.check_v2_exists('AAPL')

        assert result is True
        mock_dynamodb['v2_table'].get_item.assert_called_once()

    def test_check_v2_exists_returns_false_when_not_found(self, migrator, mock_dynamodb):
        """Should return False if executive item not found."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        result = migrator.check_v2_exists('NOTFOUND')

        assert result is False

    def test_check_v2_exists_checks_executive_key(self, migrator, mock_dynamodb):
        """Should check for 00_executive section_id."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        migrator.check_v2_exists('AAPL')

        call_args = mock_dynamodb['v2_table'].get_item.call_args
        assert call_args[1]['Key'] == {
            'ticker': 'AAPL',
            'section_id': '00_executive'
        }


# =============================================================================
# MIGRATE_REPORT TESTS
# =============================================================================

class TestMigrateReport:
    """Tests for migrate_report method."""

    def test_migrate_report_dry_run_does_not_write(self, migrator, mock_dynamodb):
        """Dry run should not write to v2 table."""
        mock_dynamodb['v2_table'].get_item.return_value = {}  # Not exists

        result = migrator.migrate_report(SAMPLE_V1_ITEM, dry_run=True)

        assert result is True
        mock_dynamodb['v2_table'].put_item.assert_not_called()

    def test_migrate_report_skips_if_exists(self, migrator, mock_dynamodb):
        """Should skip if report already exists in v2."""
        mock_dynamodb['v2_table'].get_item.return_value = {
            'Item': {'ticker': 'AAPL'}
        }

        result = migrator.migrate_report(SAMPLE_V1_ITEM, dry_run=False)

        assert result is True
        mock_dynamodb['v2_table'].put_item.assert_not_called()

    def test_migrate_report_writes_executive_item(self, migrator, mock_dynamodb):
        """Should write executive item with ToC, ratings, and executive sections."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        # Mock batch_writer context manager
        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(SAMPLE_V1_ITEM, dry_run=False)

        assert result is True

        # Check executive put_item was called
        put_item_calls = mock_dynamodb['v2_table'].put_item.call_args_list
        assert len(put_item_calls) == 1

        executive_item = put_item_calls[0][1]['Item']
        assert executive_item['ticker'] == 'AAPL'
        assert executive_item['section_id'] == '00_executive'
        assert 'toc' in executive_item
        assert 'ratings' in executive_item
        assert 'executive_sections' in executive_item  # New field in v2 schema
        assert 'total_word_count' in executive_item
        assert 'ttl' in executive_item

    def test_migrate_report_writes_section_items(self, migrator, mock_dynamodb):
        """Should write individual section items."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        # Mock batch_writer
        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(SAMPLE_V1_ITEM, dry_run=False)

        assert result is True

        # Check batch_writer was used for sections
        assert mock_batch_writer.put_item.call_count > 0

        # Verify section items have correct structure
        section_calls = mock_batch_writer.put_item.call_args_list
        for call_obj in section_calls:
            item = call_obj[1]['Item']
            assert 'ticker' in item
            assert 'section_id' in item
            assert 'content' in item
            assert 'part' in item
            assert 'display_order' in item

    def test_migrate_report_skips_invalid_report(self, migrator, mock_dynamodb):
        """Should skip reports without ticker or content."""
        invalid_item = {'ticker': '', 'fiscal_year': 2024, 'report_content': ''}

        result = migrator.migrate_report(invalid_item, dry_run=False)

        assert result is False
        mock_dynamodb['v2_table'].put_item.assert_not_called()

    def test_migrate_report_extracts_ratings_from_json(self, migrator, mock_dynamodb):
        """Should extract ratings from embedded JSON block."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(SAMPLE_V1_ITEM, dry_run=False)

        assert result is True

        # Check ratings were extracted (stored as dict in executive item)
        put_item_calls = mock_dynamodb['v2_table'].put_item.call_args_list
        executive_item = put_item_calls[0][1]['Item']

        # In the new schema, ratings are stored as a dict (not JSON string)
        ratings = executive_item['ratings']
        assert ratings['overall_verdict'] == 'HOLD'
        assert ratings['conviction'] == 'High'

    def test_migrate_report_fallback_to_v1_ratings(self, migrator, mock_dynamodb):
        """Should fall back to v1 ratings if no JSON block."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        # Report without JSON block
        item_without_json = {
            'ticker': 'TEST',
            'fiscal_year': 2024,
            'report_content': '## TL;DR\n\nSimple report without JSON ratings.',
            'ratings': {'overall_verdict': 'BUY', 'conviction': 'Medium'},
            'generated_at': '2024-01-01T00:00:00Z',
            'model': 'test'
        }

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(item_without_json, dry_run=False)

        # Migration should still succeed using v1 ratings
        assert result is True


# =============================================================================
# RUN_MIGRATION TESTS
# =============================================================================

class TestRunMigration:
    """Tests for run_migration method."""

    def test_run_migration_dry_run_summary(self, migrator, mock_dynamodb):
        """Dry run should return summary without writing."""
        mock_dynamodb['v2_table'].get_item.return_value = {}  # Not exists

        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Items': [SAMPLE_V1_ITEM]}
        ]

        results = migrator.run_migration(dry_run=True)

        assert results['mode'] == 'DRY RUN'
        assert results['total'] == 1
        assert results['migrated'] == 1
        assert results['skipped'] == 0
        assert results['failed'] == 0

    def test_run_migration_execute_mode(self, migrator, mock_dynamodb):
        """Execute mode should write to v2 table."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Items': [SAMPLE_V1_ITEM]}
        ]

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = migrator.run_migration(dry_run=False)

        assert results['mode'] == 'EXECUTE'
        assert results['migrated'] == 1
        mock_dynamodb['v2_table'].put_item.assert_called()

    def test_run_migration_counts_skipped(self, migrator, mock_dynamodb):
        """Should count already migrated reports as skipped."""
        # V2 already has this report
        mock_dynamodb['v2_table'].get_item.return_value = {
            'Item': {'ticker': 'AAPL'}
        }

        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Items': [SAMPLE_V1_ITEM]}
        ]

        results = migrator.run_migration(dry_run=False)

        assert results['skipped'] == 1
        assert results['migrated'] == 0

    def test_run_migration_specific_tickers(self, migrator, mock_dynamodb):
        """Should only migrate specified tickers."""
        mock_dynamodb['v2_table'].get_item.return_value = {}
        mock_dynamodb['v1_table'].get_item.return_value = {'Item': SAMPLE_V1_ITEM}

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = migrator.run_migration(tickers=['AAPL', 'MSFT'], dry_run=False)

        # Should have called get_item for each ticker
        assert mock_dynamodb['v1_table'].get_item.call_count == 2

    def test_run_migration_empty_v1_table(self, migrator, mock_dynamodb):
        """Should handle empty v1 table gracefully."""
        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [{'Items': []}]

        results = migrator.run_migration(dry_run=True)

        assert results['total'] == 0
        assert results['migrated'] == 0

    def test_run_migration_tracks_results(self, migrator, mock_dynamodb):
        """Should track migration results per ticker."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        mock_paginator = MagicMock()
        mock_dynamodb['v1_table'].meta.client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Items': [
                SAMPLE_V1_ITEM,
                {'ticker': 'MSFT', 'fiscal_year': 2024, 'report_content': SAMPLE_V1_REPORT_CONTENT}
            ]}
        ]

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        results = migrator.run_migration(dry_run=False)

        assert results['total'] == 2
        assert len(results['tickers']) == 2


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestMigrationEdgeCases:
    """Tests for edge cases in migration."""

    def test_handles_decimal_ttl(self, migrator, mock_dynamodb):
        """Should handle Decimal TTL values from DynamoDB."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        item_with_decimal_ttl = SAMPLE_V1_ITEM.copy()
        item_with_decimal_ttl['ttl'] = Decimal('1735689600')

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(item_with_decimal_ttl, dry_run=False)

        assert result is True

    def test_handles_string_ratings(self, migrator, mock_dynamodb):
        """Should handle ratings stored as JSON string."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        item_with_string_ratings = {
            'ticker': 'TEST',
            'fiscal_year': 2024,
            'report_content': '## TL;DR\n\nTest report.',
            'ratings': '{"overall_verdict": "HOLD"}',  # String, not dict
            'generated_at': '2024-01-01T00:00:00Z',
            'model': 'test'
        }

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(item_with_string_ratings, dry_run=False)

        assert result is True

    def test_handles_missing_generated_at(self, migrator, mock_dynamodb):
        """Should use current time if generated_at missing."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        item_without_generated_at = {
            'ticker': 'TEST',
            'fiscal_year': 2024,
            'report_content': '## TL;DR\n\nTest report.',
            'ratings': {},
            'model': 'test'
            # No generated_at
        }

        mock_batch_writer = MagicMock()
        mock_dynamodb['v2_table'].batch_writer.return_value.__enter__ = MagicMock(
            return_value=mock_batch_writer
        )
        mock_dynamodb['v2_table'].batch_writer.return_value.__exit__ = MagicMock(
            return_value=False
        )

        result = migrator.migrate_report(item_without_generated_at, dry_run=False)

        assert result is True

        # Check generated_at was set
        put_item_calls = mock_dynamodb['v2_table'].put_item.call_args_list
        executive_item = put_item_calls[0][1]['Item']
        assert 'generated_at' in executive_item

    def test_handles_report_parse_failure(self, migrator, mock_dynamodb):
        """Should return False if report cannot be parsed."""
        mock_dynamodb['v2_table'].get_item.return_value = {}

        # Report with no valid sections
        item_unparseable = {
            'ticker': 'BAD',
            'fiscal_year': 2024,
            'report_content': 'No valid markdown headers here',
            'ratings': {},
            'generated_at': '2024-01-01T00:00:00Z'
        }

        result = migrator.migrate_report(item_unparseable, dry_run=False)

        # Should fail since no sections could be parsed
        assert result is False


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
