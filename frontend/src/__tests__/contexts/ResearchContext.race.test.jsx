/**
 * ResearchContext Race Condition Tests
 *
 * Tests for the SSE race condition fix (researchIdRef).
 * Verifies that stale streams from previous requests don't corrupt state
 * when a newer request has already started.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { ResearchProvider, useResearch } from '../../contexts/ResearchContext';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';

// Must match VITE_RESEARCH_API_URL in vite.config.js test.env
const API_BASE = 'https://test-api.example.com/dev';

// Wrapper component for testing hooks
const wrapper = ({ children }) => (
  <ResearchProvider>{children}</ResearchProvider>
);

// Helper to create a slow SSE stream that takes `durationMs` to complete
function createSlowStream(ticker, durationMs = 200) {
  return http.get(`${API_BASE}/research/report/:ticker/stream`, async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
        await delay(20);

        controller.enqueue(encoder.encode(`event: executive_meta\ndata: ${JSON.stringify({
          toc: [{ section_id: '01_exec', title: `Summary for ${ticker}`, part: 1 }],
          ratings: { overall_verdict: 'HOLD' },
        })}\n\n`));

        await delay(durationMs);

        controller.enqueue(encoder.encode(`event: section_start\ndata: ${JSON.stringify({
          section_id: '01_exec',
          title: `Summary for ${ticker}`,
          part: 1,
        })}\n\n`));

        controller.enqueue(encoder.encode(`event: section_chunk\ndata: ${JSON.stringify({
          section_id: '01_exec',
          text: `Content for ${ticker}`,
        })}\n\n`));

        controller.enqueue(encoder.encode(`event: section_end\ndata: ${JSON.stringify({
          section_id: '01_exec',
        })}\n\n`));

        controller.enqueue(encoder.encode('event: complete\ndata: {}\n\n'));
        controller.close();
      }
    });

    return new HttpResponse(stream, {
      headers: { 'Content-Type': 'text/event-stream' }
    });
  });
}

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

describe('ResearchContext Race Condition Prevention', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    server.resetHandlers();
  });

  it('should not apply stale stream data when a newer request starts', async () => {
    // Use a slow stream so the first request is still in-flight when the second starts
    server.use(createSlowStream('AAPL', 300));

    const { result } = renderHook(() => useResearch(), { wrapper });

    // Start first research (AAPL) — this will be slow
    act(() => {
      result.current.startResearch('AAPL');
    });

    expect(result.current.selectedTicker).toBe('AAPL');
    expect(result.current.isStreaming).toBe(true);

    // Wait a bit for the first stream to connect
    await delay(50);

    // Start second research (NVDA) — this aborts the first and starts fresh
    act(() => {
      result.current.startResearch('NVDA');
    });

    expect(result.current.selectedTicker).toBe('NVDA');

    // Wait for completion
    await waitFor(() => {
      expect(result.current.streamStatus).toBe('complete');
    }, { timeout: 2000 });

    // Final state should only reflect NVDA, not AAPL
    expect(result.current.selectedTicker).toBe('NVDA');
    expect(result.current.error).toBeNull();
  });

  it('should handle 5 rapid ticker switches and only keep the last', async () => {
    const { result } = renderHook(() => useResearch(), { wrapper });

    const tickers = ['AAPL', 'MSFT', 'GOOG', 'AMZN', 'NVDA'];

    // Fire all 5 in rapid succession
    for (const ticker of tickers) {
      act(() => {
        result.current.startResearch(ticker);
      });
    }

    // Should immediately reflect the last ticker
    expect(result.current.selectedTicker).toBe('NVDA');

    // Wait for stream to complete
    await waitFor(() => {
      expect(result.current.streamStatus).toBe('complete');
    }, { timeout: 3000 });

    // Verify only the last ticker's data is present
    expect(result.current.selectedTicker).toBe('NVDA');
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('should not dispatch complete for a stale request after a new one starts', async () => {
    // Use a very slow handler to ensure the first stream is still in-flight
    server.use(createSlowStream('AAPL', 500));

    const { result } = renderHook(() => useResearch(), { wrapper });

    // Start slow AAPL request
    act(() => {
      result.current.startResearch('AAPL');
    });

    // Let it connect
    await delay(30);

    // Now switch to NVDA (uses default fast handler after resetHandlers)
    server.resetHandlers();
    await act(async () => {
      await result.current.startResearch('NVDA');
    });

    await waitFor(() => {
      expect(result.current.streamStatus).toBe('complete');
    });

    // The state should be clean NVDA, not a mix of AAPL/NVDA
    expect(result.current.selectedTicker).toBe('NVDA');
  });

  it('should not set error state from a stale stream that fails', async () => {
    // First stream will fail after a delay
    let requestCount = 0;
    server.use(
      http.get(`${API_BASE}/research/report/:ticker/stream`, async () => {
        requestCount++;
        if (requestCount === 1) {
          // First request: slow, then error
          await delay(200);
          return HttpResponse.json({ error: 'Server Error' }, { status: 500 });
        }
        // Second request: fast success
        const encoder = new TextEncoder();
        const stream = new ReadableStream({
          async start(controller) {
            controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
            controller.enqueue(encoder.encode(`event: executive_meta\ndata: ${JSON.stringify({
              toc: [], ratings: {},
            })}\n\n`));
            controller.enqueue(encoder.encode('event: complete\ndata: {}\n\n'));
            controller.close();
          }
        });
        return new HttpResponse(stream, {
          headers: { 'Content-Type': 'text/event-stream' }
        });
      })
    );

    const { result } = renderHook(() => useResearch(), { wrapper });

    // Start first (will fail slowly)
    act(() => {
      result.current.startResearch('AAPL');
    });

    // Immediately start second (will succeed quickly)
    await act(async () => {
      await result.current.startResearch('NVDA');
    });

    await waitFor(() => {
      expect(result.current.streamStatus).toBe('complete');
    });

    // The error from the stale AAPL request should NOT have overwritten NVDA's success
    expect(result.current.error).toBeNull();
    expect(result.current.selectedTicker).toBe('NVDA');
  });

  it('should handle abort + new request without leaking state', async () => {
    const { result } = renderHook(() => useResearch(), { wrapper });

    // Start research
    act(() => {
      result.current.startResearch('AAPL');
    });

    // Abort it
    act(() => {
      result.current.abortStream();
    });

    // Start new research
    await act(async () => {
      await result.current.startResearch('NVDA');
    });

    await waitFor(() => {
      expect(result.current.streamStatus).toBe('complete');
    });

    // Clean state for NVDA
    expect(result.current.selectedTicker).toBe('NVDA');
    expect(result.current.error).toBeNull();
    expect(result.current.isStreaming).toBe(false);
  });
});
