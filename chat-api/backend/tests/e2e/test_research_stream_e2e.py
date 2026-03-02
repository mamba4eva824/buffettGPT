"""
E2E tests for the research report SSE stream endpoint.

Validates:
- GET /report/{ticker}/stream returns SSE events in correct order
- GET /report/{ticker}/toc returns valid JSON
- GET /report/{ticker}/section/{section_id} returns section content
- POST /report/{ticker}/sections batch endpoint works
- GET /report/{ticker}/status returns existence/expiration info
- Auth enforcement (JWT required)
- Input validation (invalid tickers rejected)

These tests hit the deployed Docker Lambda but do NOT call Bedrock —
they only read cached reports from DynamoDB.

Run with:
    cd chat-api/backend
    AWS_PROFILE=default BUFFETT_JWT_SECRET='...' \
        pytest tests/e2e/test_research_stream_e2e.py -v -s -m e2e

Requires:
    - AWS credentials with DynamoDB access
    - BUFFETT_JWT_SECRET environment variable
    - DOCKER_LAMBDA_URL environment variable (optional, has default)
"""

import os
import sys
import uuid

import pytest
import requests

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from tests.e2e.conftest import parse_sse_stream

pytestmark = [pytest.mark.e2e, pytest.mark.slow]


# =============================================================================
# SSE Stream Tests
# =============================================================================

class TestResearchStream:
    """Validate the GET /report/{ticker}/stream SSE endpoint."""

    def test_stream_returns_sse_events(self, docker_url, docker_test_data, docker_jwt):
        """Stream returns connected, executive_meta, section_start/chunk/end, complete."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/stream',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            stream=True,
            timeout=60,
        )

        assert response.status_code == 200, (
            f'Expected 200, got {response.status_code}: {response.text[:200]}'
        )
        assert 'text/event-stream' in response.headers.get('Content-Type', ''), (
            f'Expected text/event-stream content type, got: {response.headers.get("Content-Type")}'
        )

        events = parse_sse_stream(response)
        event_types = [e[0] for e in events]

        assert len(events) >= 3, f'Expected >= 3 events, got {len(events)}'
        assert event_types[0] == 'connected', f'First event should be connected, got {event_types[0]}'

        # executive_meta should come early (contains ToC and ratings)
        assert 'executive_meta' in event_types, 'Missing executive_meta event'

        meta_event = next(e for e in events if e[0] == 'executive_meta')
        assert 'toc' in meta_event[1], 'executive_meta missing toc'
        assert 'ratings' in meta_event[1], 'executive_meta missing ratings'

    def test_stream_contains_section_events(self, docker_url, docker_test_data, docker_jwt):
        """Stream should contain section_start, section_chunk, and section_end events."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/stream',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            stream=True,
            timeout=60,
        )

        assert response.status_code == 200
        events = parse_sse_stream(response)
        event_types = [e[0] for e in events]

        assert 'section_start' in event_types, 'Missing section_start event'
        assert 'section_chunk' in event_types, 'Missing section_chunk event'
        assert 'section_end' in event_types, 'Missing section_end event'

        # Verify section_start has required fields
        start_event = next(e for e in events if e[0] == 'section_start')
        assert 'section_id' in start_event[1], 'section_start missing section_id'
        assert 'title' in start_event[1], 'section_start missing title'

        # Verify chunks have text content
        chunks = [e for e in events if e[0] == 'section_chunk']
        total_text = ''.join(c[1].get('text', '') for c in chunks)
        assert len(total_text) > 10, f'Section content too short: {total_text[:100]}'

    def test_stream_ends_with_complete(self, docker_url, docker_test_data, docker_jwt):
        """Stream should end with a complete event."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/stream',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            stream=True,
            timeout=60,
        )

        assert response.status_code == 200
        events = parse_sse_stream(response)
        event_types = [e[0] for e in events]

        assert event_types[-1] == 'complete', (
            f'Last event should be complete, got {event_types[-1]}'
        )

    def test_stream_invalid_ticker_returns_error(self, docker_url, docker_jwt):
        """Invalid ticker format returns error (400 or error SSE event)."""
        response = requests.get(
            f'{docker_url}/report/INVALID123!/stream',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            stream=True,
            timeout=30,
        )

        # Should either be a 400/422 HTTP error or an SSE stream with error event
        if response.status_code == 200:
            events = parse_sse_stream(response)
            event_types = [e[0] for e in events]
            assert 'error' in event_types, (
                f'Expected error event for invalid ticker, got: {event_types}'
            )
        else:
            assert response.status_code in (400, 422), (
                f'Expected 400 or 422, got {response.status_code}'
            )

    def test_stream_nonexistent_ticker(self, docker_url, docker_jwt):
        """Ticker with no report returns appropriate error."""
        response = requests.get(
            f'{docker_url}/report/ZZZQQ/stream',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            stream=True,
            timeout=30,
        )

        if response.status_code == 200:
            events = parse_sse_stream(response)
            event_types = [e[0] for e in events]
            # Should get an error event since no report exists
            assert 'error' in event_types, (
                f'Expected error event for nonexistent ticker, got: {event_types}'
            )
        else:
            assert response.status_code in (404, 400), (
                f'Expected 404 or 400, got {response.status_code}'
            )


# =============================================================================
# JSON Endpoint Tests
# =============================================================================

class TestResearchJsonEndpoints:
    """Validate the JSON API endpoints for research reports."""

    def test_toc_endpoint(self, docker_url, docker_test_data, docker_jwt):
        """GET /report/{ticker}/toc returns ToC with ratings."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/toc',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            timeout=30,
        )

        assert response.status_code == 200
        body = response.json()

        assert 'toc' in body, f'Missing toc in response: {body.keys()}'
        assert 'ratings' in body, f'Missing ratings in response: {body.keys()}'
        assert isinstance(body['toc'], list), 'toc should be a list'
        assert len(body['toc']) > 0, 'toc should not be empty'

        # Verify ToC entries have required fields
        first_entry = body['toc'][0]
        for field in ('section_id', 'title', 'part'):
            assert field in first_entry, f'ToC entry missing {field}: {first_entry}'

    def test_section_endpoint(self, docker_url, docker_test_data, docker_jwt):
        """GET /report/{ticker}/section/{section_id} returns section content."""
        ticker = docker_test_data['ticker']

        # First get the ToC to find a valid section_id
        toc_response = requests.get(
            f'{docker_url}/report/{ticker}/toc',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            timeout=30,
        )
        assert toc_response.status_code == 200
        toc = toc_response.json()['toc']
        assert len(toc) > 0

        section_id = toc[0]['section_id']

        # Now fetch the section
        response = requests.get(
            f'{docker_url}/report/{ticker}/section/{section_id}',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            timeout=30,
        )

        assert response.status_code == 200
        body = response.json()

        assert 'content' in body, f'Missing content: {body.keys()}'
        assert 'title' in body, f'Missing title: {body.keys()}'
        assert len(body['content']) > 10, f'Content too short: {body["content"][:50]}'

    def test_status_endpoint(self, docker_url, docker_test_data, docker_jwt):
        """GET /report/{ticker}/status returns existence info."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/status',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            timeout=30,
        )

        assert response.status_code == 200
        body = response.json()
        assert 'exists' in body, f'Missing exists field: {body.keys()}'
        assert body['exists'] is True, 'Seeded report should exist'

    def test_batch_sections_endpoint(self, docker_url, docker_test_data, docker_jwt):
        """POST /report/{ticker}/sections returns multiple sections."""
        ticker = docker_test_data['ticker']

        # First get ToC for valid section IDs
        toc_response = requests.get(
            f'{docker_url}/report/{ticker}/toc',
            headers={'Authorization': f'Bearer {docker_jwt}'},
            timeout=30,
        )
        assert toc_response.status_code == 200
        toc = toc_response.json()['toc']

        if len(toc) < 2:
            pytest.skip('Need at least 2 sections for batch test')

        section_ids = [toc[0]['section_id'], toc[1]['section_id']]

        response = requests.post(
            f'{docker_url}/report/{ticker}/sections',
            headers={
                'Authorization': f'Bearer {docker_jwt}',
                'Content-Type': 'application/json',
            },
            json={'section_ids': section_ids},
            timeout=30,
        )

        assert response.status_code == 200
        body = response.json()
        assert 'sections' in body, f'Missing sections: {body.keys()}'
        assert len(body['sections']) == len(section_ids), (
            f'Expected {len(section_ids)} sections, got {len(body["sections"])}'
        )


# =============================================================================
# Auth Tests
# =============================================================================

class TestResearchAuth:
    """Verify auth enforcement on research endpoints."""

    def test_stream_requires_auth(self, docker_url, docker_test_data):
        """GET /report/{ticker}/stream without JWT returns 401/403."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/stream',
            timeout=30,
        )
        assert response.status_code in (401, 403), (
            f'Expected 401/403, got {response.status_code}'
        )

    def test_toc_requires_auth(self, docker_url, docker_test_data):
        """GET /report/{ticker}/toc without JWT returns 401/403."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/toc',
            timeout=30,
        )
        assert response.status_code in (401, 403), (
            f'Expected 401/403, got {response.status_code}'
        )

    def test_invalid_jwt_rejected(self, docker_url, docker_test_data):
        """Invalid JWT returns 401/403."""
        ticker = docker_test_data['ticker']
        response = requests.get(
            f'{docker_url}/report/{ticker}/stream',
            headers={'Authorization': 'Bearer invalid.jwt.token'},
            timeout=30,
        )
        assert response.status_code in (401, 403), (
            f'Expected 401/403, got {response.status_code}'
        )
