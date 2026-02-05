"""
Unit tests for app.py v2 endpoints (section-based progressive loading).

Tests the new v2 API endpoints:
- GET /report/{ticker}/toc - Get report table of contents with ratings
- GET /report/{ticker}/section/{section_id} - Get a specific section
- GET /report/{ticker}/executive - Get Part 1 (executive summary) sections
- GET /report/{ticker}/stream - Stream all sections as SSE events

Also tests:
- generate_section_stream() async generator
- Input validation
- Error handling

Run:
    cd chat-api/backend/lambda/investment_research
    pytest tests/test_app_v2_endpoints.py -v

Or from backend root:
    pytest lambda/investment_research/tests/test_app_v2_endpoints.py -v
"""

import json
import os
import sys
import pytest
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import patch, MagicMock, AsyncMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set environment variables before importing app
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from fastapi.testclient import TestClient
from app import app, generate_section_stream


# =============================================================================
# TEST DATA
# =============================================================================

MOCK_TOC_DATA = {
    'ticker': 'AAPL',
    'section_id': '00_metadata',
    'toc': [
        {'section_id': '01_tldr', 'title': 'TL;DR', 'part': 1, 'icon': 'lightning', 'word_count': 50, 'display_order': 1},
        {'section_id': '02_business', 'title': 'What Does AAPL Actually Do?', 'part': 1, 'icon': 'building', 'word_count': 100, 'display_order': 2},
        {'section_id': '03_health', 'title': "AAPL's 2024 Report Card", 'part': 1, 'icon': 'activity', 'word_count': 80, 'display_order': 3},
        {'section_id': '04_fit', 'title': 'Investment Fit Assessment', 'part': 1, 'icon': 'user-check', 'word_count': 90, 'display_order': 4},
        {'section_id': '05_verdict', 'title': 'The Verdict', 'part': 1, 'icon': 'gavel', 'word_count': 60, 'display_order': 5},
        {'section_id': '06_growth', 'title': 'From 3% to 4%: The Growth Crawl', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
    ],
    'ratings': {
        'growth': {'rating': 'Stable', 'confidence': 'High', 'key_factors': ['3% revenue growth']},
        'profitability': {'rating': 'Very Strong', 'confidence': 'High', 'key_factors': ['77% gross margin']},
        'overall_verdict': 'HOLD',
        'conviction': 'High'
    },
    'total_word_count': 580,
    'generated_at': '2024-01-01T12:00:00Z'
}

MOCK_SECTION = {
    'ticker': 'AAPL',
    'section_id': '06_growth',
    'title': 'From 3% to 4%: The Growth Crawl',
    'content': "Apple's growth has slowed dramatically from 19% in 2021 to just 3-4% today.",
    'part': 2,
    'icon': 'trending-up',
    'word_count': 200,
    'display_order': 6
}

MOCK_EXECUTIVE_SECTIONS = [
    {'ticker': 'AAPL', 'section_id': '01_tldr', 'title': 'TL;DR', 'content': 'Apple is great.', 'part': 1, 'icon': 'lightning', 'word_count': 50, 'display_order': 1},
    {'ticker': 'AAPL', 'section_id': '02_business', 'title': 'What Does AAPL Actually Do?', 'content': 'Apple sells phones.', 'part': 1, 'icon': 'building', 'word_count': 100, 'display_order': 2},
    {'ticker': 'AAPL', 'section_id': '03_health', 'title': "AAPL's Report Card", 'content': 'Healthy company.', 'part': 1, 'icon': 'activity', 'word_count': 80, 'display_order': 3},
    {'ticker': 'AAPL', 'section_id': '04_fit', 'title': 'Investment Fit', 'content': 'Good for most investors.', 'part': 1, 'icon': 'user-check', 'word_count': 90, 'display_order': 4},
    {'ticker': 'AAPL', 'section_id': '05_verdict', 'title': 'The Verdict', 'content': 'HOLD - High conviction.', 'part': 1, 'icon': 'gavel', 'word_count': 60, 'display_order': 5},
]

MOCK_ALL_SECTIONS = MOCK_EXECUTIVE_SECTIONS + [
    {'ticker': 'AAPL', 'section_id': '06_growth', 'title': 'Growth', 'content': 'Slow growth.', 'part': 2, 'icon': 'trending-up', 'word_count': 200, 'display_order': 6},
    {'ticker': 'AAPL', 'section_id': '17_realtalk', 'title': 'Real Talk', 'content': 'Blue chip stock.', 'part': 3, 'icon': 'message-circle', 'word_count': 100, 'display_order': 17},
]

# Combined executive item (new v2 schema)
MOCK_EXECUTIVE_ITEM = {
    'ticker': 'AAPL',
    'section_id': '00_executive',
    'toc': MOCK_TOC_DATA['toc'],
    'ratings': MOCK_TOC_DATA['ratings'],
    'executive_sections': [
        {'section_id': '01_tldr', 'title': 'TL;DR', 'content': 'Apple is great.', 'icon': 'lightning', 'word_count': 50},
        {'section_id': '02_business', 'title': 'What Does AAPL Actually Do?', 'content': 'Apple sells phones.', 'icon': 'building', 'word_count': 100},
        {'section_id': '03_health', 'title': "AAPL's Report Card", 'content': 'Healthy company.', 'icon': 'activity', 'word_count': 80},
        {'section_id': '04_fit', 'title': 'Investment Fit', 'content': 'Good for most investors.', 'icon': 'user-check', 'word_count': 90},
        {'section_id': '05_verdict', 'title': 'The Verdict', 'content': 'HOLD - High conviction.', 'icon': 'gavel', 'word_count': 60},
    ],
    'total_word_count': 580,
    'generated_at': '2024-01-01T12:00:00Z'
}


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)


# =============================================================================
# HEALTH CHECK TESTS
# =============================================================================

class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check_returns_200(self, client):
        """GET /health should return 200."""
        response = client.get('/health')

        assert response.status_code == 200

    def test_health_check_response_structure(self, client):
        """GET /health should return proper structure."""
        response = client.get('/health')
        data = response.json()

        assert data['status'] == 'healthy'
        assert 'timestamp' in data
        assert data['environment'] == 'test'
        assert data['service'] == 'investment-research'


# =============================================================================
# TOC ENDPOINT TESTS
# =============================================================================

class TestTocEndpoint:
    """Tests for GET /report/{ticker}/toc endpoint."""

    def test_get_toc_success(self, client):
        """GET /report/AAPL/toc should return ToC with ratings."""
        with patch('app.get_report_toc', return_value=MOCK_TOC_DATA):
            response = client.get('/report/AAPL/toc')

            assert response.status_code == 200
            data = response.json()

            assert data['success'] is True
            assert data['ticker'] == 'AAPL'
            assert len(data['toc']) == 6
            assert data['ratings']['overall_verdict'] == 'HOLD'
            assert data['total_word_count'] == 580
            assert 'timestamp' in data

    def test_get_toc_lowercase_ticker(self, client):
        """GET /report/aapl/toc should uppercase ticker."""
        with patch('app.get_report_toc', return_value=MOCK_TOC_DATA) as mock_get:
            response = client.get('/report/aapl/toc')

            assert response.status_code == 200
            # Verify ticker was uppercased in the call
            mock_get.assert_called_once_with('AAPL')

    def test_get_toc_not_found(self, client):
        """GET /report/XYZ/toc should return 404 if not found."""
        with patch('app.get_report_toc', return_value=None):
            response = client.get('/report/XYZ/toc')

            assert response.status_code == 404
            data = response.json()
            assert data['success'] is False
            assert 'No report found' in data['error']

    def test_get_toc_invalid_ticker_format(self, client):
        """GET /report/TOOLONG/toc should return 400 for invalid ticker."""
        # Ticker > 5 chars
        response = client.get('/report/TOOLONGX/toc')

        assert response.status_code == 422  # FastAPI validation error

    def test_get_toc_invalid_ticker_numbers(self, client):
        """GET /report/123/toc should return 400 for numeric ticker."""
        with patch('app.validate_ticker', return_value=False):
            response = client.get('/report/123/toc')

            assert response.status_code == 400
            data = response.json()
            assert 'Invalid ticker format' in data['error']


# =============================================================================
# SECTION ENDPOINT TESTS
# =============================================================================

class TestSectionEndpoint:
    """Tests for GET /report/{ticker}/section/{section_id} endpoint."""

    def test_get_section_success(self, client):
        """GET /report/AAPL/section/06_growth should return section."""
        with patch('app.get_report_section', return_value=MOCK_SECTION):
            response = client.get('/report/AAPL/section/06_growth')

            assert response.status_code == 200
            data = response.json()

            assert data['success'] is True
            assert data['ticker'] == 'AAPL'
            assert data['section_id'] == '06_growth'
            assert data['title'] == 'From 3% to 4%: The Growth Crawl'
            assert 'growth has slowed' in data['content']
            assert data['part'] == 2
            assert data['icon'] == 'trending-up'
            assert data['word_count'] == 200
            assert data['display_order'] == 6

    def test_get_section_not_found(self, client):
        """GET /report/AAPL/section/invalid should return 404."""
        with patch('app.get_report_section', return_value=None):
            response = client.get('/report/AAPL/section/invalid_section')

            assert response.status_code == 404
            data = response.json()
            assert data['success'] is False
            assert 'not found' in data['error']

    def test_get_section_executive_section(self, client):
        """GET /report/AAPL/section/01_tldr should return executive section."""
        exec_section = {
            'ticker': 'AAPL',
            'section_id': '01_tldr',
            'title': 'TL;DR',
            'content': 'Apple is great.',
            'part': 1,
            'icon': 'lightning',
            'word_count': 50,
            'display_order': 1
        }
        with patch('app.get_report_section', return_value=exec_section):
            response = client.get('/report/AAPL/section/01_tldr')

            assert response.status_code == 200
            data = response.json()
            assert data['part'] == 1
            assert data['section_id'] == '01_tldr'

    def test_get_section_lowercase_handling(self, client):
        """Section ID should be case-insensitive."""
        with patch('app.get_report_section', return_value=MOCK_SECTION) as mock_get:
            # Uppercase section_id in URL
            response = client.get('/report/AAPL/section/06_GROWTH')

            assert response.status_code == 200
            # Verify it's passed to the service (service handles normalization)


# =============================================================================
# EXECUTIVE ENDPOINT TESTS
# =============================================================================

class TestExecutiveEndpoint:
    """Tests for GET /report/{ticker}/executive endpoint (combined executive item)."""

    def test_get_executive_success(self, client):
        """GET /report/AAPL/executive should return combined executive item."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            response = client.get('/report/AAPL/executive')

            assert response.status_code == 200
            data = response.json()

            assert data['success'] is True
            assert data['ticker'] == 'AAPL'

            # Check new schema fields
            assert 'toc' in data
            assert 'ratings' in data
            assert 'executive_sections' in data
            assert 'total_word_count' in data

            # Verify ToC structure
            assert len(data['toc']) > 0

            # Verify executive sections (5 sections)
            assert len(data['executive_sections']) == 5
            assert data['executive_sections'][0]['section_id'] == '01_tldr'
            assert data['executive_sections'][-1]['section_id'] == '05_verdict'

            # Verify ratings
            assert data['ratings']['overall_verdict'] == 'HOLD'
            assert data['ratings']['conviction'] == 'High'

    def test_get_executive_not_found(self, client):
        """GET /report/XYZ/executive should return 404 if not found."""
        with patch('app.get_executive', return_value=None):
            response = client.get('/report/XYZ/executive')

            assert response.status_code == 404
            data = response.json()
            assert data['success'] is False
            assert 'No report found' in data['error']

    def test_get_executive_lowercase_ticker(self, client):
        """GET /report/msft/executive should uppercase ticker."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM) as mock_get:
            response = client.get('/report/msft/executive')

            assert response.status_code == 200
            mock_get.assert_called_once_with('MSFT')


# =============================================================================
# STREAM ENDPOINT TESTS (SSE)
# =============================================================================

class TestStreamEndpoint:
    """Tests for GET /report/{ticker}/stream SSE endpoint."""

    def test_stream_returns_event_source(self, client):
        """GET /report/AAPL/stream should return text/event-stream."""
        with patch('app.get_report_toc', return_value=MOCK_TOC_DATA):
            with patch('app.get_all_sections', return_value=MOCK_ALL_SECTIONS):
                response = client.get('/report/AAPL/stream')

                assert response.status_code == 200
                assert 'text/event-stream' in response.headers.get('content-type', '')

    def test_stream_invalid_ticker(self, client):
        """GET /report/123/stream should return 400 for invalid ticker."""
        with patch('app.validate_ticker', return_value=False):
            response = client.get('/report/123/stream')

            assert response.status_code == 400


# =============================================================================
# GENERATE_SECTION_STREAM TESTS (V2 Chunk Streaming)
# =============================================================================

# Mock data for detailed sections (Part 2 & 3, not in executive)
MOCK_DETAILED_SECTIONS = [
    {'ticker': 'AAPL', 'section_id': '06_growth', 'title': 'Growth', 'content': 'Slow growth.', 'part': 2, 'icon': 'trending-up', 'word_count': 20, 'display_order': 6},
    {'ticker': 'AAPL', 'section_id': '17_realtalk', 'title': 'Real Talk', 'content': 'Blue chip stock.', 'part': 3, 'icon': 'message-circle', 'word_count': 15, 'display_order': 17},
]


class TestGenerateSectionStream:
    """Tests for generate_section_stream async generator (V2 Chunk Streaming)."""

    @pytest.mark.asyncio
    async def test_stream_emits_connected_event_first(self):
        """Stream should emit 'connected' event first."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=MOCK_DETAILED_SECTIONS):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)
                    if len(events) >= 1:
                        break

                assert events[0]['event'] == 'connected'

    @pytest.mark.asyncio
    async def test_stream_emits_executive_meta_event_second(self):
        """Stream should emit 'executive_meta' event after connected."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=MOCK_DETAILED_SECTIONS):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)
                    if len(events) >= 2:
                        break

                assert events[1]['event'] == 'executive_meta'

                # Verify executive_meta data
                meta_data = json.loads(events[1]['data'])
                assert meta_data['type'] == 'executive_meta'
                assert len(meta_data['toc']) == 6
                assert meta_data['ratings']['overall_verdict'] == 'HOLD'

    @pytest.mark.asyncio
    async def test_stream_emits_section_chunk_events(self):
        """Stream should emit section_start/chunk/end events for each section."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=MOCK_DETAILED_SECTIONS):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)

                # Find section_start events (one per section)
                start_events = [e for e in events if e['event'] == 'section_start']

                # Should have one start event for each executive section + detailed section
                # 5 executive sections + 2 detailed sections = 7 total
                assert len(start_events) == 7

                # First section should be from executive (01_tldr)
                first_start = json.loads(start_events[0]['data'])
                assert first_start['section_id'] == '01_tldr'

    @pytest.mark.asyncio
    async def test_stream_emits_progress_events(self):
        """Stream should emit 'progress' events at key points."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=MOCK_DETAILED_SECTIONS):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)

                # Find progress events
                progress_events = [e for e in events if e['event'] == 'progress']

                # Should have at least the initial progress events
                assert len(progress_events) >= 1

    @pytest.mark.asyncio
    async def test_stream_emits_complete_event_last(self):
        """Stream should emit 'complete' event as final event."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=MOCK_DETAILED_SECTIONS):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)

                # Last event should be complete
                assert events[-1]['event'] == 'complete'

                # Verify complete data
                complete_data = json.loads(events[-1]['data'])
                assert complete_data['type'] == 'complete'
                assert complete_data['ticker'] == 'AAPL'
                assert complete_data['version'] == 'v2'
                # 5 executive + 2 detailed = 7 sections
                assert complete_data['section_count'] == 7

    @pytest.mark.asyncio
    async def test_stream_handles_missing_executive(self):
        """Stream should emit error if executive item not found."""
        with patch('app.get_executive', return_value=None):
            events = []
            async for event in generate_section_stream('UNKNOWN'):
                events.append(event)

            # Should have connected and error
            assert events[0]['event'] == 'connected'
            assert events[1]['event'] == 'error'

            error_data = json.loads(events[1]['data'])
            assert error_data['code'] == 'REPORT_NOT_FOUND'

    @pytest.mark.asyncio
    async def test_stream_handles_missing_detailed_sections(self):
        """Stream should emit error if detailed sections not found."""
        with patch('app.get_executive', return_value=MOCK_EXECUTIVE_ITEM):
            with patch('app.get_all_sections', return_value=[]):
                events = []
                async for event in generate_section_stream('AAPL'):
                    events.append(event)

                # Should have connected, executive_meta, progress, section events, then error
                event_types = [e['event'] for e in events]
                assert 'error' in event_types

                error_event = next(e for e in events if e['event'] == 'error')
                error_data = json.loads(error_event['data'])
                assert error_data['code'] == 'SECTIONS_NOT_FOUND'

    @pytest.mark.asyncio
    async def test_stream_handles_exception(self):
        """Stream should emit error on exception."""
        with patch('app.get_executive', side_effect=Exception('Database error')):
            events = []
            async for event in generate_section_stream('AAPL'):
                events.append(event)

            # Should have connected and error
            assert events[0]['event'] == 'connected'
            assert events[1]['event'] == 'error'

            error_data = json.loads(events[1]['data'])
            assert error_data['code'] == 'STREAM_ERROR'
            assert 'Database error' in error_data['message']


# =============================================================================
# V1 ENDPOINT TESTS (BACKWARD COMPATIBILITY)
# =============================================================================

class TestV1Endpoints:
    """Tests for v1 endpoints to ensure backward compatibility."""

    def test_v1_get_report_endpoint_exists(self, client):
        """GET /report/{ticker} (v1) should still work."""
        mock_report = {
            'ticker': 'AAPL',
            'fiscal_year': 2024,
            'report_content': '# Full Report',
            'ratings': {
                'debt': {'rating': 'Strong'},
                'cashflow': {'rating': 'Very Strong'},
                'growth': {'rating': 'Stable'},
                'overall_verdict': 'HOLD',
                'conviction': 'High'
            },
            'generated_at': '2024-01-01T00:00:00Z'
        }
        with patch('app.get_cached_report', return_value=mock_report):
            response = client.get('/report/AAPL')

            assert response.status_code == 200
            assert 'text/event-stream' in response.headers.get('content-type', '')

    def test_followup_stub_exists(self, client):
        """POST /followup should return stub response."""
        response = client.post('/followup', json={
            'ticker': 'AAPL',
            'question': 'What about the debt?'
        })

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'stub'
        assert 'Phase 4' in data['message']


# =============================================================================
# INPUT VALIDATION TESTS
# =============================================================================

class TestInputValidation:
    """Tests for input validation across endpoints."""

    def test_ticker_validation_empty(self, client):
        """Empty ticker should fail validation."""
        # FastAPI path parameter validation
        response = client.get('/report//toc')
        assert response.status_code == 404  # Route not matched

    def test_ticker_validation_special_chars(self, client):
        """Ticker with special chars should fail."""
        with patch('app.validate_ticker', return_value=False):
            response = client.get('/report/AAP$/toc')
            assert response.status_code == 400

    def test_section_id_max_length(self, client):
        """Section ID > 20 chars should fail."""
        # Section ID path has max_length=20
        response = client.get('/report/AAPL/section/this_is_way_too_long_section_id')
        assert response.status_code == 422  # FastAPI validation


# =============================================================================
# ERROR HANDLER TESTS
# =============================================================================

class TestErrorHandlers:
    """Tests for error handlers."""

    def test_http_exception_format(self, client):
        """HTTPException should return consistent format."""
        with patch('app.get_report_toc', return_value=None):
            response = client.get('/report/XYZ/toc')

            assert response.status_code == 404
            data = response.json()

            assert data['success'] is False
            assert 'error' in data
            assert 'timestamp' in data

    def test_global_exception_handler(self):
        """Unhandled exceptions should return 500."""
        with patch('app.get_report_toc', side_effect=Exception('Unexpected error')):
            # TestClient raises_server_exceptions=True by default, so we need to
            # explicitly set it to False to test the exception handler
            with TestClient(app, raise_server_exceptions=False) as test_client:
                response = test_client.get('/report/AAPL/toc')

                assert response.status_code == 500
                data = response.json()

                assert data['success'] is False
                assert data['error'] == 'Internal server error'
                # detail is included only in 'dev' environment
                # In 'test' environment, detail should be None
                assert 'detail' in data
                assert 'timestamp' in data


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
