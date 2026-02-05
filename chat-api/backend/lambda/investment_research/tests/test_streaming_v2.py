"""
Unit tests for streaming.py v2 SSE events.

Tests the v2 section-based streaming events:
- toc_event() - Table of contents with ratings (like prediction_ensemble's inference event)
- section_event() - Individual section content (like chunk event)
- progress_event() - Progress indicator (like status event)
- complete_v2_event() - V2 completion event with version marker

Run:
    cd chat-api/backend/lambda/investment_research
    pytest tests/test_streaming_v2.py -v

Or from backend root:
    pytest lambda/investment_research/tests/test_streaming_v2.py -v
"""

import json
import os
import sys
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.streaming import (
    # V1 events (for comparison testing)
    connected_event,
    rating_event,
    report_event,
    complete_event,
    error_event,
    # V2 events (main focus)
    toc_event,
    section_event,
    progress_event,
    complete_v2_event,
)


# =============================================================================
# TEST DATA
# =============================================================================

SAMPLE_TOC = [
    {'section_id': '01_tldr', 'title': 'TL;DR', 'part': 1, 'icon': 'lightning', 'word_count': 50, 'display_order': 1},
    {'section_id': '02_business', 'title': 'What Does AAPL Actually Do?', 'part': 1, 'icon': 'building', 'word_count': 100, 'display_order': 2},
    {'section_id': '06_growth', 'title': 'From 3% to 4%: The Growth Crawl', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
]

SAMPLE_RATINGS = {
    'growth': {'rating': 'Stable', 'confidence': 'High', 'key_factors': ['3% revenue growth']},
    'profitability': {'rating': 'Very Strong', 'confidence': 'High', 'key_factors': ['77% gross margin']},
    'overall_verdict': 'HOLD',
    'conviction': 'High'
}


# =============================================================================
# V1 EVENT TESTS (Baseline)
# =============================================================================

class TestV1Events:
    """Tests for V1 events to ensure backward compatibility."""

    def test_connected_event_structure(self):
        """connected_event should return proper SSE dict structure."""
        event = connected_event()

        assert 'event' in event
        assert 'data' in event
        assert event['event'] == 'connected'

        # Parse the JSON data
        data = json.loads(event['data'])
        assert data['type'] == 'connected'
        assert 'timestamp' in data

    def test_rating_event_structure(self):
        """rating_event should include domain and rating details."""
        rating_data = {
            'rating': 'Very Strong',
            'confidence': 'High',
            'key_factors': ['Low debt', 'High cash']
        }
        event = rating_event('debt', rating_data)

        assert event['event'] == 'rating'

        data = json.loads(event['data'])
        assert data['type'] == 'rating'
        assert data['domain'] == 'debt'
        assert data['rating'] == 'Very Strong'
        assert data['confidence'] == 'High'
        assert data['key_factors'] == ['Low debt', 'High cash']
        assert 'timestamp' in data

    def test_rating_event_handles_missing_fields(self):
        """rating_event should handle missing optional fields."""
        rating_data = {'rating': 'Stable'}  # No confidence or key_factors
        event = rating_event('growth', rating_data)

        data = json.loads(event['data'])
        assert data['rating'] == 'Stable'
        assert data['confidence'] is None
        assert data['key_factors'] == []

    def test_report_event_with_metadata(self):
        """report_event should include content and metadata."""
        content = "# Full Report\n\nContent here."
        metadata = {
            'ticker': 'AAPL',
            'fiscal_year': 2024,
            'overall_verdict': 'HOLD'
        }
        event = report_event(content, metadata)

        assert event['event'] == 'report'

        data = json.loads(event['data'])
        assert data['type'] == 'report'
        assert data['content'] == content
        assert data['metadata'] == metadata
        assert 'timestamp' in data

    def test_report_event_without_metadata(self):
        """report_event should work without metadata."""
        content = "# Report Content"
        event = report_event(content)

        data = json.loads(event['data'])
        assert data['content'] == content
        assert 'metadata' not in data

    def test_complete_event_structure(self):
        """complete_event should include ticker and fiscal_year."""
        event = complete_event('AAPL', 2024)

        assert event['event'] == 'complete'

        data = json.loads(event['data'])
        assert data['type'] == 'complete'
        assert data['ticker'] == 'AAPL'
        assert data['fiscal_year'] == 2024
        assert 'timestamp' in data

    def test_error_event_with_code(self):
        """error_event should include message and optional code."""
        event = error_event('Report not found', code='REPORT_NOT_FOUND')

        assert event['event'] == 'error'

        data = json.loads(event['data'])
        assert data['type'] == 'error'
        assert data['message'] == 'Report not found'
        assert data['code'] == 'REPORT_NOT_FOUND'

    def test_error_event_without_code(self):
        """error_event should work without code."""
        event = error_event('Something went wrong')

        data = json.loads(event['data'])
        assert data['message'] == 'Something went wrong'
        assert 'code' not in data


# =============================================================================
# V2 TOC EVENT TESTS
# =============================================================================

class TestTocEvent:
    """Tests for toc_event function."""

    def test_toc_event_structure(self):
        """toc_event should return proper SSE structure with toc and ratings."""
        event = toc_event(SAMPLE_TOC, SAMPLE_RATINGS, 350, '2024-01-01T00:00:00Z')

        assert event['event'] == 'toc'

        data = json.loads(event['data'])
        assert data['type'] == 'toc'
        assert data['toc'] == SAMPLE_TOC
        assert data['ratings'] == SAMPLE_RATINGS
        assert data['total_word_count'] == 350
        assert data['generated_at'] == '2024-01-01T00:00:00Z'
        assert 'timestamp' in data

    def test_toc_event_without_generated_at(self):
        """toc_event should work without generated_at."""
        event = toc_event(SAMPLE_TOC, SAMPLE_RATINGS, 350)

        data = json.loads(event['data'])
        assert data['generated_at'] is None
        assert data['toc'] == SAMPLE_TOC

    def test_toc_event_empty_toc(self):
        """toc_event should handle empty toc list."""
        event = toc_event([], {}, 0)

        data = json.loads(event['data'])
        assert data['toc'] == []
        assert data['ratings'] == {}
        assert data['total_word_count'] == 0

    def test_toc_event_empty_ratings(self):
        """toc_event should handle empty ratings dict."""
        event = toc_event(SAMPLE_TOC, {}, 350)

        data = json.loads(event['data'])
        assert data['ratings'] == {}
        assert len(data['toc']) == 3

    def test_toc_event_with_all_rating_categories(self):
        """toc_event should preserve all rating categories."""
        full_ratings = {
            'growth': {'rating': 'Stable', 'confidence': 'High'},
            'profitability': {'rating': 'Very Strong', 'confidence': 'High'},
            'valuation': {'rating': 'Strong', 'confidence': 'Medium'},
            'earnings_quality': {'rating': 'Very Strong', 'confidence': 'High'},
            'cashflow': {'rating': 'Very Strong', 'confidence': 'High'},
            'debt': {'rating': 'Strong', 'confidence': 'High'},
            'dilution': {'rating': 'Very Strong', 'confidence': 'High'},
            'overall_verdict': 'HOLD',
            'conviction': 'High'
        }
        event = toc_event(SAMPLE_TOC, full_ratings, 350)

        data = json.loads(event['data'])
        assert data['ratings']['overall_verdict'] == 'HOLD'
        assert data['ratings']['conviction'] == 'High'
        assert len(data['ratings']) == 9


# =============================================================================
# V2 SECTION EVENT TESTS
# =============================================================================

class TestSectionEvent:
    """Tests for section_event function."""

    def test_section_event_structure(self):
        """section_event should include all section metadata."""
        event = section_event(
            section_id='06_growth',
            title='From 3% to 4%: The Growth Crawl',
            content='Apple growth has slowed dramatically...',
            part=2,
            icon='trending-up',
            word_count=200,
            display_order=6
        )

        assert event['event'] == 'section'

        data = json.loads(event['data'])
        assert data['type'] == 'section'
        assert data['section_id'] == '06_growth'
        assert data['title'] == 'From 3% to 4%: The Growth Crawl'
        assert data['content'] == 'Apple growth has slowed dramatically...'
        assert data['part'] == 2
        assert data['icon'] == 'trending-up'
        assert data['word_count'] == 200
        assert data['display_order'] == 6
        assert 'timestamp' in data

    def test_section_event_executive_summary(self):
        """section_event should handle Part 1 (executive) sections."""
        event = section_event(
            section_id='01_tldr',
            title='TL;DR',
            content='Apple is the digital bouncer for premium tech.',
            part=1,
            icon='lightning',
            word_count=50,
            display_order=1
        )

        data = json.loads(event['data'])
        assert data['part'] == 1
        assert data['display_order'] == 1
        assert data['section_id'] == '01_tldr'

    def test_section_event_realtalk(self):
        """section_event should handle Part 3 (real talk) section."""
        event = section_event(
            section_id='17_realtalk',
            title='Real Talk',
            content='Apple is the blue chip of blue chips...',
            part=3,
            icon='message-circle',
            word_count=100,
            display_order=17
        )

        data = json.loads(event['data'])
        assert data['part'] == 3
        assert data['display_order'] == 17

    def test_section_event_preserves_markdown(self):
        """section_event should preserve markdown formatting in content."""
        markdown_content = """
## Key Points

| Metric | Value |
|--------|-------|
| Revenue | $100B |

**Bottom line:** ~ steady but not exciting
"""
        event = section_event(
            section_id='06_growth',
            title='Growth',
            content=markdown_content,
            part=2,
            icon='trending-up',
            word_count=20,
            display_order=6
        )

        data = json.loads(event['data'])
        assert '## Key Points' in data['content']
        assert '| Metric | Value |' in data['content']
        assert '**Bottom line:**' in data['content']

    def test_section_event_handles_empty_content(self):
        """section_event should handle empty content."""
        event = section_event(
            section_id='01_tldr',
            title='TL;DR',
            content='',
            part=1,
            icon='lightning',
            word_count=0,
            display_order=1
        )

        data = json.loads(event['data'])
        assert data['content'] == ''
        assert data['word_count'] == 0


# =============================================================================
# V2 PROGRESS EVENT TESTS
# =============================================================================

class TestProgressEvent:
    """Tests for progress_event function."""

    def test_progress_event_structure(self):
        """progress_event should include current, total, and percentage."""
        event = progress_event(5, 17, 'Loading detailed analysis...')

        assert event['event'] == 'progress'

        data = json.loads(event['data'])
        assert data['type'] == 'progress'
        assert data['current'] == 5
        assert data['total'] == 17
        assert data['percentage'] == 29  # 5/17 * 100 rounded
        assert data['message'] == 'Loading detailed analysis...'
        assert 'timestamp' in data

    def test_progress_event_without_message(self):
        """progress_event should work without message."""
        event = progress_event(10, 17)

        data = json.loads(event['data'])
        assert data['current'] == 10
        assert data['total'] == 17
        assert 'message' not in data

    def test_progress_event_at_start(self):
        """progress_event should handle 0 progress."""
        event = progress_event(0, 17, 'Starting...')

        data = json.loads(event['data'])
        assert data['current'] == 0
        assert data['percentage'] == 0
        assert data['message'] == 'Starting...'

    def test_progress_event_at_completion(self):
        """progress_event should handle 100% progress."""
        event = progress_event(17, 17, 'Complete!')

        data = json.loads(event['data'])
        assert data['current'] == 17
        assert data['total'] == 17
        assert data['percentage'] == 100

    def test_progress_event_percentage_calculation(self):
        """progress_event should correctly calculate percentages."""
        test_cases = [
            (1, 17, 6),    # 5.88% -> 6
            (5, 17, 29),   # 29.41% -> 29
            (8, 17, 47),   # 47.06% -> 47
            (16, 17, 94),  # 94.12% -> 94
            (17, 17, 100), # 100%
        ]

        for current, total, expected_pct in test_cases:
            event = progress_event(current, total)
            data = json.loads(event['data'])
            assert data['percentage'] == expected_pct, \
                f"Expected {expected_pct}% for {current}/{total}, got {data['percentage']}%"

    def test_progress_event_handles_zero_total(self):
        """progress_event should handle zero total gracefully."""
        event = progress_event(0, 0)

        data = json.loads(event['data'])
        assert data['percentage'] == 0


# =============================================================================
# V2 COMPLETE EVENT TESTS
# =============================================================================

class TestCompleteV2Event:
    """Tests for complete_v2_event function."""

    def test_complete_v2_event_structure(self):
        """complete_v2_event should include ticker, section_count, and version."""
        event = complete_v2_event('AAPL', 17)

        assert event['event'] == 'complete'

        data = json.loads(event['data'])
        assert data['type'] == 'complete'
        assert data['ticker'] == 'AAPL'
        assert data['section_count'] == 17
        assert data['version'] == 'v2'
        assert 'timestamp' in data

    def test_complete_v2_event_has_version_marker(self):
        """complete_v2_event must include version='v2' to differentiate from v1."""
        event = complete_v2_event('MSFT', 17)

        data = json.loads(event['data'])
        assert data['version'] == 'v2'

    def test_complete_v2_event_different_section_counts(self):
        """complete_v2_event should handle various section counts."""
        for count in [5, 11, 17, 20]:
            event = complete_v2_event('TEST', count)
            data = json.loads(event['data'])
            assert data['section_count'] == count

    def test_complete_v2_vs_v1_event_structure(self):
        """complete_v2_event should differ from v1 complete_event."""
        v1 = complete_event('AAPL', 2024)
        v2 = complete_v2_event('AAPL', 17)

        v1_data = json.loads(v1['data'])
        v2_data = json.loads(v2['data'])

        # Both have 'complete' event type
        assert v1['event'] == 'complete'
        assert v2['event'] == 'complete'

        # V1 has fiscal_year, V2 has section_count
        assert 'fiscal_year' in v1_data
        assert 'fiscal_year' not in v2_data
        assert 'section_count' in v2_data
        assert 'section_count' not in v1_data

        # V2 has version marker
        assert 'version' in v2_data
        assert 'version' not in v1_data


# =============================================================================
# DECIMAL HANDLING TESTS
# =============================================================================

class TestDecimalHandling:
    """Tests for Decimal serialization in events."""

    def test_toc_event_handles_decimal_word_count(self):
        """toc_event should serialize Decimal word counts correctly."""
        toc_with_decimal = [
            {'section_id': '01_tldr', 'title': 'TL;DR', 'word_count': Decimal('50')},
        ]
        event = toc_event(toc_with_decimal, {}, Decimal('350'))

        # Should not raise - Decimal should be serialized
        data = json.loads(event['data'])
        assert data['total_word_count'] == 350

    def test_ratings_with_decimal_values(self):
        """toc_event should handle Decimal values in ratings."""
        ratings_with_decimal = {
            'growth': {
                'rating': 'Stable',
                'pe_ratio': Decimal('25.5'),
                'growth_rate': Decimal('3')
            }
        }
        event = toc_event([], ratings_with_decimal, 0)

        data = json.loads(event['data'])
        assert data['ratings']['growth']['pe_ratio'] == 25.5
        assert data['ratings']['growth']['growth_rate'] == 3


# =============================================================================
# TIMESTAMP TESTS
# =============================================================================

class TestTimestamps:
    """Tests for timestamp generation in events."""

    def test_timestamps_are_iso_format(self):
        """All events should include ISO-formatted timestamps."""
        events = [
            connected_event(),
            toc_event([], {}, 0),
            section_event('01_tldr', 'Test', 'Content', 1, 'icon', 10, 1),
            progress_event(1, 10),
            complete_v2_event('TEST', 10),
        ]

        for event in events:
            data = json.loads(event['data'])
            timestamp = data['timestamp']

            # Should end with 'Z' for UTC
            assert timestamp.endswith('Z'), f"Timestamp should end with Z: {timestamp}"

            # Should be parseable as ISO format
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(f"Timestamp is not valid ISO format: {timestamp}")

    def test_timestamps_are_current(self):
        """Timestamps should be close to current time."""
        before = datetime.utcnow()
        event = connected_event()
        after = datetime.utcnow()

        data = json.loads(event['data'])
        timestamp_str = data['timestamp'].replace('Z', '+00:00')
        timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=None)

        assert before <= timestamp <= after


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
