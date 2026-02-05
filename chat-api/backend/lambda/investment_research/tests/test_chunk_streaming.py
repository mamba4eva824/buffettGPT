"""
Unit tests for chunk streaming implementation.

Tests the V2 chunk streaming events and stream_section_chunks async generator:
- executive_meta_event() - ToC + ratings without section content
- section_start_event() - Section metadata before content chunks
- section_chunk_event() - Individual content chunks
- section_end_event() - Section completion signal
- stream_section_chunks() - Async generator for typewriter effect

Run:
    cd chat-api/backend/lambda/investment_research
    pytest tests/test_chunk_streaming.py -v

Or from backend root:
    pytest lambda/investment_research/tests/test_chunk_streaming.py -v
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

# Set environment variables before importing app
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from services.streaming import (
    executive_meta_event,
    section_start_event,
    section_chunk_event,
    section_end_event,
)
from app import stream_section_chunks, CHUNK_SIZE, CHUNK_DELAY_SECONDS


# =============================================================================
# TEST DATA
# =============================================================================

SAMPLE_EXECUTIVE_ITEM = {
    'ticker': 'AAPL',
    'section_id': '00_executive',
    'toc': [
        {'section_id': '01_tldr', 'title': 'TL;DR', 'part': 1, 'icon': 'lightning', 'word_count': 50, 'display_order': 1},
        {'section_id': '02_business', 'title': 'What Does AAPL Actually Do?', 'part': 1, 'icon': 'building', 'word_count': 100, 'display_order': 2},
        {'section_id': '06_growth', 'title': 'From 3% to 4%: The Growth Crawl', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
    ],
    'ratings': {
        'growth': {'rating': 'Stable', 'confidence': 'High', 'key_factors': ['3% revenue growth']},
        'profitability': {'rating': 'Very Strong', 'confidence': 'High', 'key_factors': ['77% gross margin']},
        'overall_verdict': 'HOLD',
        'conviction': 'High'
    },
    'total_word_count': 350,
    'generated_at': '2024-01-01T12:00:00Z'
}

SAMPLE_SECTION = {
    'content': 'Apple growth has slowed dramatically from 19% in 2021 to just 3-4% today. The company is now a mature cash cow.',
    'section_id': '06_growth',
    'title': 'From 3% to 4%: The Growth Crawl',
    'part': 2,
    'icon': 'trending-up',
    'word_count': 20,
    'display_order': 6
}


# =============================================================================
# EXECUTIVE_META_EVENT TESTS
# =============================================================================

class TestExecutiveMetaEvent:
    """Tests for executive_meta_event function."""

    def test_executive_meta_event_structure(self):
        """executive_meta_event should return proper SSE structure."""
        event = executive_meta_event(SAMPLE_EXECUTIVE_ITEM)

        assert 'event' in event
        assert 'data' in event
        assert event['event'] == 'executive_meta'

        # Parse the JSON data
        data = json.loads(event['data'])
        assert data['type'] == 'executive_meta'
        assert data['ticker'] == 'AAPL'
        assert 'timestamp' in data

    def test_executive_meta_event_includes_toc(self):
        """executive_meta_event should include full ToC."""
        event = executive_meta_event(SAMPLE_EXECUTIVE_ITEM)
        data = json.loads(event['data'])

        assert 'toc' in data
        assert len(data['toc']) == 3
        assert data['toc'][0]['section_id'] == '01_tldr'
        assert data['toc'][2]['section_id'] == '06_growth'

    def test_executive_meta_event_includes_ratings(self):
        """executive_meta_event should include ratings."""
        event = executive_meta_event(SAMPLE_EXECUTIVE_ITEM)
        data = json.loads(event['data'])

        assert 'ratings' in data
        assert data['ratings']['overall_verdict'] == 'HOLD'
        assert data['ratings']['conviction'] == 'High'
        assert 'growth' in data['ratings']

    def test_executive_meta_event_includes_metadata(self):
        """executive_meta_event should include total_word_count and generated_at."""
        event = executive_meta_event(SAMPLE_EXECUTIVE_ITEM)
        data = json.loads(event['data'])

        assert data['total_word_count'] == 350
        assert data['generated_at'] == '2024-01-01T12:00:00Z'

    def test_executive_meta_event_excludes_section_content(self):
        """executive_meta_event should NOT include executive_sections content."""
        item_with_sections = {
            **SAMPLE_EXECUTIVE_ITEM,
            'executive_sections': [
                {'section_id': '01_tldr', 'content': 'This should not be in meta event'}
            ]
        }
        event = executive_meta_event(item_with_sections)
        data = json.loads(event['data'])

        # executive_meta should not include the section content
        assert 'executive_sections' not in data
        assert 'content' not in data

    def test_executive_meta_event_handles_empty_item(self):
        """executive_meta_event should handle empty item gracefully."""
        empty_item = {}
        event = executive_meta_event(empty_item)
        data = json.loads(event['data'])

        assert data['type'] == 'executive_meta'
        assert data['ticker'] is None
        assert data['toc'] == []
        assert data['ratings'] == {}
        assert data['total_word_count'] == 0
        assert data['generated_at'] is None

    def test_executive_meta_event_handles_decimal_values(self):
        """executive_meta_event should serialize Decimal values."""
        item_with_decimal = {
            **SAMPLE_EXECUTIVE_ITEM,
            'total_word_count': Decimal('350')
        }
        event = executive_meta_event(item_with_decimal)
        data = json.loads(event['data'])

        assert data['total_word_count'] == 350


# =============================================================================
# SECTION_START_EVENT TESTS
# =============================================================================

class TestSectionStartEvent:
    """Tests for section_start_event function."""

    def test_section_start_event_structure(self):
        """section_start_event should return proper SSE structure."""
        event = section_start_event(
            section_id='06_growth',
            title='From 3% to 4%: The Growth Crawl',
            part=2,
            icon='trending-up',
            word_count=200,
            display_order=6,
            total_chunks=3
        )

        assert event['event'] == 'section_start'

        data = json.loads(event['data'])
        assert data['type'] == 'section_start'
        assert 'timestamp' in data

    def test_section_start_event_includes_all_metadata(self):
        """section_start_event should include all section metadata."""
        event = section_start_event(
            section_id='06_growth',
            title='Growth Analysis',
            part=2,
            icon='trending-up',
            word_count=200,
            display_order=6,
            total_chunks=3
        )

        data = json.loads(event['data'])
        assert data['section_id'] == '06_growth'
        assert data['title'] == 'Growth Analysis'
        assert data['part'] == 2
        assert data['icon'] == 'trending-up'
        assert data['word_count'] == 200
        assert data['display_order'] == 6
        assert data['total_chunks'] == 3

    def test_section_start_event_excludes_content(self):
        """section_start_event should NOT include content."""
        event = section_start_event(
            section_id='01_tldr',
            title='TL;DR',
            part=1,
            icon='lightning',
            word_count=50,
            display_order=1,
            total_chunks=1
        )

        data = json.loads(event['data'])
        assert 'content' not in data

    def test_section_start_event_part1_executive(self):
        """section_start_event should handle Part 1 (executive) sections."""
        event = section_start_event(
            section_id='01_tldr',
            title='TL;DR',
            part=1,
            icon='lightning',
            word_count=50,
            display_order=1,
            total_chunks=1
        )

        data = json.loads(event['data'])
        assert data['part'] == 1
        assert data['display_order'] == 1

    def test_section_start_event_part3_realtalk(self):
        """section_start_event should handle Part 3 (real talk) section."""
        event = section_start_event(
            section_id='17_realtalk',
            title='Real Talk',
            part=3,
            icon='message-circle',
            word_count=100,
            display_order=17,
            total_chunks=1
        )

        data = json.loads(event['data'])
        assert data['part'] == 3
        assert data['display_order'] == 17

    def test_section_start_event_single_chunk(self):
        """section_start_event should indicate total_chunks=1 for small content."""
        event = section_start_event(
            section_id='01_tldr',
            title='TL;DR',
            part=1,
            icon='lightning',
            word_count=30,
            display_order=1,
            total_chunks=1
        )

        data = json.loads(event['data'])
        assert data['total_chunks'] == 1

    def test_section_start_event_multiple_chunks(self):
        """section_start_event should indicate total_chunks for large content."""
        event = section_start_event(
            section_id='11_debt',
            title='Debt Deep Dive',
            part=2,
            icon='credit-card',
            word_count=500,
            display_order=11,
            total_chunks=8
        )

        data = json.loads(event['data'])
        assert data['total_chunks'] == 8


# =============================================================================
# SECTION_CHUNK_EVENT TESTS
# =============================================================================

class TestSectionChunkEvent:
    """Tests for section_chunk_event function."""

    def test_section_chunk_event_structure(self):
        """section_chunk_event should return proper SSE structure."""
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=0,
            text='Apple growth has slowed dramatically...',
            is_final=False
        )

        assert event['event'] == 'section_chunk'

        data = json.loads(event['data'])
        assert data['type'] == 'section_chunk'
        assert 'timestamp' in data

    def test_section_chunk_event_first_chunk(self):
        """section_chunk_event should correctly mark first chunk."""
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=0,
            text='First chunk of content...',
            is_final=False
        )

        data = json.loads(event['data'])
        assert data['chunk_index'] == 0
        assert data['is_final'] is False

    def test_section_chunk_event_middle_chunk(self):
        """section_chunk_event should correctly mark middle chunk."""
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=2,
            text='Middle chunk of content...',
            is_final=False
        )

        data = json.loads(event['data'])
        assert data['chunk_index'] == 2
        assert data['is_final'] is False

    def test_section_chunk_event_final_chunk(self):
        """section_chunk_event should correctly mark final chunk."""
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=4,
            text='Final chunk of content.',
            is_final=True
        )

        data = json.loads(event['data'])
        assert data['chunk_index'] == 4
        assert data['is_final'] is True

    def test_section_chunk_event_preserves_text(self):
        """section_chunk_event should preserve exact text content."""
        text = '**Bold text** and _italic_ with special chars: <>&"'
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=0,
            text=text,
            is_final=True
        )

        data = json.loads(event['data'])
        assert data['text'] == text

    def test_section_chunk_event_empty_text(self):
        """section_chunk_event should handle empty text."""
        event = section_chunk_event(
            section_id='01_tldr',
            chunk_index=0,
            text='',
            is_final=True
        )

        data = json.loads(event['data'])
        assert data['text'] == ''

    def test_section_chunk_event_max_chunk_text(self):
        """section_chunk_event should handle max chunk size text (256 chars)."""
        text = 'X' * 256
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=0,
            text=text,
            is_final=True
        )

        data = json.loads(event['data'])
        assert len(data['text']) == 256

    def test_section_chunk_event_includes_section_id(self):
        """section_chunk_event should include section_id for client routing."""
        event = section_chunk_event(
            section_id='11_debt',
            chunk_index=0,
            text='Debt analysis chunk...',
            is_final=True
        )

        data = json.loads(event['data'])
        assert data['section_id'] == '11_debt'

    def test_section_chunk_event_unicode_text(self):
        """section_chunk_event should handle unicode text correctly."""
        text = 'Apple has 45% market share in premium smartphones'
        event = section_chunk_event(
            section_id='06_growth',
            chunk_index=0,
            text=text,
            is_final=True
        )

        data = json.loads(event['data'])
        assert '45%' in data['text']


# =============================================================================
# SECTION_END_EVENT TESTS
# =============================================================================

class TestSectionEndEvent:
    """Tests for section_end_event function."""

    def test_section_end_event_structure(self):
        """section_end_event should return proper SSE structure."""
        event = section_end_event(
            section_id='06_growth',
            total_chunks=3
        )

        assert event['event'] == 'section_end'

        data = json.loads(event['data'])
        assert data['type'] == 'section_end'
        assert 'timestamp' in data

    def test_section_end_event_includes_section_id(self):
        """section_end_event should include section_id."""
        event = section_end_event(
            section_id='06_growth',
            total_chunks=3
        )

        data = json.loads(event['data'])
        assert data['section_id'] == '06_growth'

    def test_section_end_event_includes_total_chunks(self):
        """section_end_event should include total_chunks for verification."""
        event = section_end_event(
            section_id='11_debt',
            total_chunks=8
        )

        data = json.loads(event['data'])
        assert data['total_chunks'] == 8

    def test_section_end_event_single_chunk(self):
        """section_end_event should handle single chunk sections."""
        event = section_end_event(
            section_id='01_tldr',
            total_chunks=1
        )

        data = json.loads(event['data'])
        assert data['total_chunks'] == 1

    def test_section_end_event_many_chunks(self):
        """section_end_event should handle sections with many chunks."""
        event = section_end_event(
            section_id='17_realtalk',
            total_chunks=20
        )

        data = json.loads(event['data'])
        assert data['total_chunks'] == 20


# =============================================================================
# STREAM_SECTION_CHUNKS TESTS
# =============================================================================

class TestStreamSectionChunks:
    """Tests for stream_section_chunks async generator."""

    @pytest.mark.asyncio
    async def test_stream_emits_correct_event_sequence(self):
        """stream_section_chunks should emit start -> chunk(s) -> end."""
        events = []
        async for event in stream_section_chunks(SAMPLE_SECTION):
            events.append(event)

        event_types = [e['event'] for e in events]

        # First event should be section_start
        assert event_types[0] == 'section_start'

        # Last event should be section_end
        assert event_types[-1] == 'section_end'

        # Middle events should be section_chunk
        for event_type in event_types[1:-1]:
            assert event_type == 'section_chunk'

    @pytest.mark.asyncio
    async def test_stream_handles_empty_content(self):
        """stream_section_chunks should handle empty content gracefully."""
        empty_section = {
            'content': '',
            'section_id': '01_tldr',
            'title': 'Empty',
            'part': 1,
            'icon': 'test',
            'word_count': 0,
            'display_order': 1
        }

        events = []
        async for event in stream_section_chunks(empty_section):
            events.append(event)

        # Should still emit start, one chunk (empty), and end
        assert len(events) == 3
        assert events[0]['event'] == 'section_start'
        assert events[1]['event'] == 'section_chunk'
        assert events[2]['event'] == 'section_end'

        # Chunk should have empty text
        chunk_data = json.loads(events[1]['data'])
        assert chunk_data['text'] == ''
        assert chunk_data['is_final'] is True

    @pytest.mark.asyncio
    async def test_stream_small_content_single_chunk(self):
        """stream_section_chunks should emit single chunk for small content."""
        small_section = {
            'content': 'Small content',  # 13 chars < 256
            'section_id': '01_tldr',
            'title': 'Small',
            'part': 1,
            'icon': 'test',
            'word_count': 2,
            'display_order': 1
        }

        events = []
        async for event in stream_section_chunks(small_section):
            events.append(event)

        # Should be: start, 1 chunk, end = 3 events
        assert len(events) == 3

        chunk_events = [e for e in events if e['event'] == 'section_chunk']
        assert len(chunk_events) == 1

        chunk_data = json.loads(chunk_events[0]['data'])
        assert chunk_data['text'] == 'Small content'
        assert chunk_data['is_final'] is True

    @pytest.mark.asyncio
    async def test_stream_exact_chunk_size(self):
        """stream_section_chunks should handle content exactly CHUNK_SIZE."""
        exact_section = {
            'content': 'X' * CHUNK_SIZE,  # Exactly 256 chars
            'section_id': '02_test',
            'title': 'Exact',
            'part': 1,
            'icon': 'test',
            'word_count': 1,
            'display_order': 2
        }

        events = []
        async for event in stream_section_chunks(exact_section):
            events.append(event)

        # Should be: start, 1 chunk, end = 3 events
        chunk_events = [e for e in events if e['event'] == 'section_chunk']
        assert len(chunk_events) == 1

        chunk_data = json.loads(chunk_events[0]['data'])
        assert len(chunk_data['text']) == CHUNK_SIZE

    @pytest.mark.asyncio
    async def test_stream_multiple_chunks(self):
        """stream_section_chunks should split large content into multiple chunks."""
        large_content = 'A' * (CHUNK_SIZE * 3 + 50)  # 818 chars = 4 chunks
        large_section = {
            'content': large_content,
            'section_id': '06_growth',
            'title': 'Large',
            'part': 2,
            'icon': 'test',
            'word_count': 1,
            'display_order': 6
        }

        events = []
        async for event in stream_section_chunks(large_section):
            events.append(event)

        chunk_events = [e for e in events if e['event'] == 'section_chunk']
        assert len(chunk_events) == 4

        # First 3 chunks should be 256 chars, last should be 50
        for i, chunk_event in enumerate(chunk_events[:-1]):
            data = json.loads(chunk_event['data'])
            assert len(data['text']) == CHUNK_SIZE
            assert data['is_final'] is False
            assert data['chunk_index'] == i

        last_data = json.loads(chunk_events[-1]['data'])
        assert len(last_data['text']) == 50
        assert last_data['is_final'] is True
        assert last_data['chunk_index'] == 3

    @pytest.mark.asyncio
    async def test_stream_chunk_indices_sequential(self):
        """stream_section_chunks should emit sequential chunk indices."""
        content = 'B' * (CHUNK_SIZE * 5)  # 5 chunks
        section = {
            'content': content,
            'section_id': '06_growth',
            'title': 'Multi-chunk',
            'part': 2,
            'icon': 'test',
            'word_count': 1,
            'display_order': 6
        }

        events = []
        async for event in stream_section_chunks(section):
            events.append(event)

        chunk_events = [e for e in events if e['event'] == 'section_chunk']

        for expected_idx, chunk_event in enumerate(chunk_events):
            data = json.loads(chunk_event['data'])
            assert data['chunk_index'] == expected_idx

    @pytest.mark.asyncio
    async def test_stream_start_event_has_correct_total_chunks(self):
        """stream_section_chunks start event should predict correct total_chunks."""
        content = 'C' * (CHUNK_SIZE * 3 + 100)  # 868 chars = 4 chunks
        section = {
            'content': content,
            'section_id': '06_growth',
            'title': 'Test',
            'part': 2,
            'icon': 'test',
            'word_count': 1,
            'display_order': 6
        }

        events = []
        async for event in stream_section_chunks(section):
            events.append(event)

        start_data = json.loads(events[0]['data'])
        end_data = json.loads(events[-1]['data'])

        # total_chunks in start should match actual chunks and end event
        actual_chunks = len([e for e in events if e['event'] == 'section_chunk'])
        assert start_data['total_chunks'] == actual_chunks
        assert end_data['total_chunks'] == actual_chunks

    @pytest.mark.asyncio
    async def test_stream_preserves_section_metadata(self):
        """stream_section_chunks should preserve all section metadata in start event."""
        events = []
        async for event in stream_section_chunks(SAMPLE_SECTION):
            events.append(event)

        start_data = json.loads(events[0]['data'])

        assert start_data['section_id'] == SAMPLE_SECTION['section_id']
        assert start_data['title'] == SAMPLE_SECTION['title']
        assert start_data['part'] == SAMPLE_SECTION['part']
        assert start_data['icon'] == SAMPLE_SECTION['icon']
        assert start_data['word_count'] == SAMPLE_SECTION['word_count']
        assert start_data['display_order'] == SAMPLE_SECTION['display_order']

    @pytest.mark.asyncio
    async def test_stream_handles_missing_fields(self):
        """stream_section_chunks should handle missing optional fields."""
        minimal_section = {
            'content': 'Some content',
            'section_id': '01_test'
        }

        events = []
        async for event in stream_section_chunks(minimal_section):
            events.append(event)

        start_data = json.loads(events[0]['data'])

        # Should have defaults for missing fields
        assert start_data['section_id'] == '01_test'
        assert start_data['title'] == ''
        assert start_data['part'] == 0
        assert start_data['icon'] == ''
        assert start_data['word_count'] == 0
        assert start_data['display_order'] == 0

    @pytest.mark.asyncio
    async def test_stream_chunk_plus_one(self):
        """stream_section_chunks should handle CHUNK_SIZE + 1 correctly."""
        content = 'D' * (CHUNK_SIZE + 1)  # 257 chars = 2 chunks
        section = {
            'content': content,
            'section_id': '06_growth',
            'title': 'Test',
            'part': 2,
            'icon': 'test',
            'word_count': 1,
            'display_order': 6
        }

        events = []
        async for event in stream_section_chunks(section):
            events.append(event)

        chunk_events = [e for e in events if e['event'] == 'section_chunk']
        assert len(chunk_events) == 2

        first_data = json.loads(chunk_events[0]['data'])
        second_data = json.loads(chunk_events[1]['data'])

        assert len(first_data['text']) == CHUNK_SIZE
        assert len(second_data['text']) == 1
        assert first_data['is_final'] is False
        assert second_data['is_final'] is True

    @pytest.mark.asyncio
    async def test_stream_section_id_consistent_across_events(self):
        """stream_section_chunks should include same section_id in all events."""
        events = []
        async for event in stream_section_chunks(SAMPLE_SECTION):
            events.append(event)

        expected_section_id = SAMPLE_SECTION['section_id']

        for event in events:
            data = json.loads(event['data'])
            assert data['section_id'] == expected_section_id


# =============================================================================
# CONFIGURATION TESTS
# =============================================================================

class TestChunkStreamingConfiguration:
    """Tests for chunk streaming configuration constants."""

    def test_chunk_size_is_256(self):
        """CHUNK_SIZE should be 256 characters."""
        assert CHUNK_SIZE == 256

    def test_chunk_delay_is_10ms(self):
        """CHUNK_DELAY_SECONDS should be 0.01 (10ms)."""
        assert CHUNK_DELAY_SECONDS == 0.01


# =============================================================================
# TIMESTAMP TESTS
# =============================================================================

class TestChunkStreamingTimestamps:
    """Tests for timestamp generation in chunk streaming events."""

    def test_executive_meta_event_has_timestamp(self):
        """executive_meta_event should include ISO timestamp."""
        event = executive_meta_event(SAMPLE_EXECUTIVE_ITEM)
        data = json.loads(event['data'])

        assert 'timestamp' in data
        assert data['timestamp'].endswith('Z')

    def test_section_start_event_has_timestamp(self):
        """section_start_event should include ISO timestamp."""
        event = section_start_event('01_test', 'Test', 1, 'icon', 10, 1, 1)
        data = json.loads(event['data'])

        assert 'timestamp' in data
        assert data['timestamp'].endswith('Z')

    def test_section_chunk_event_has_timestamp(self):
        """section_chunk_event should include ISO timestamp."""
        event = section_chunk_event('01_test', 0, 'Text', True)
        data = json.loads(event['data'])

        assert 'timestamp' in data
        assert data['timestamp'].endswith('Z')

    def test_section_end_event_has_timestamp(self):
        """section_end_event should include ISO timestamp."""
        event = section_end_event('01_test', 1)
        data = json.loads(event['data'])

        assert 'timestamp' in data
        assert data['timestamp'].endswith('Z')

    def test_timestamps_are_parseable(self):
        """All timestamps should be valid ISO format."""
        events = [
            executive_meta_event(SAMPLE_EXECUTIVE_ITEM),
            section_start_event('01_test', 'Test', 1, 'icon', 10, 1, 1),
            section_chunk_event('01_test', 0, 'Text', True),
            section_end_event('01_test', 1),
        ]

        for event in events:
            data = json.loads(event['data'])
            timestamp = data['timestamp']

            # Should be parseable as ISO format
            try:
                datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                pytest.fail(f"Timestamp is not valid ISO format: {timestamp}")


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
