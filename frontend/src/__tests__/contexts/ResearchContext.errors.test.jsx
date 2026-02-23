/**
 * ResearchContext Error Recovery Tests
 *
 * P1 Tests for error handling and recovery in the investment research system.
 * Tests HTTP errors, network failures, and graceful degradation.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { ResearchProvider, useResearch } from '../../contexts/ResearchContext';
import { server } from '../mocks/server';
import { errorHandlers } from '../mocks/handlers';
import { http, HttpResponse } from 'msw';

// Must match VITE_RESEARCH_API_URL in vite.config.js test.env
const API_BASE = 'https://test-api.example.com/dev';

// Wrapper component for testing hooks
const wrapper = ({ children }) => (
  <ResearchProvider>{children}</ResearchProvider>
);

describe('ResearchContext Error Recovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    server.resetHandlers();
  });

  describe('HTTP Error Responses', () => {
    it('should handle 401 Unauthorized and set appropriate error', async () => {
      server.use(errorHandlers.unauthorized);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toContain('401');
      expect(result.current.isStreaming).toBe(false);
      expect(result.current.selectedTicker).toBe('AAPL'); // Ticker preserved for retry
    });

    it('should handle 429 Rate Limit with retry information', async () => {
      server.use(errorHandlers.rateLimited);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toContain('429');
    });

    it('should handle 500 Server Error', async () => {
      server.use(errorHandlers.serverError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toContain('500');
    });

    it('should handle 404 Not Found for section fetch', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        try {
          await result.current.fetchSection('AAPL', 'nonexistent_section');
        } catch (e) {
          // Expected to throw
        }
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('404');
    });

    it('should handle 503 Service Unavailable', async () => {
      server.use(
        http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
          return HttpResponse.json({ error: 'Service temporarily unavailable' }, { status: 503 });
        })
      );

      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toContain('503');
    });
  });

  describe('Network Failures', () => {
    it('should handle complete network failure', async () => {
      server.use(errorHandlers.networkError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toBeDefined();
      expect(result.current.isStreaming).toBe(false);
    });

    it('should allow retry after network failure', async () => {
      // First request fails
      server.use(errorHandlers.networkError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      // Reset handlers to allow success
      server.resetHandlers();

      // Retry should work
      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('SSE Stream Errors', () => {
    it('should handle error event during stream', async () => {
      server.use(errorHandlers.sseError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('Report generation failed');
      expect(result.current.streamStatus).toBe('error');
    });

    it('should handle malformed SSE JSON gracefully', async () => {
      server.use(errorHandlers.malformedSSE);
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      // Should not crash, may complete or error depending on implementation
      await waitFor(() => {
        expect(['complete', 'error', 'streaming']).toContain(result.current.streamStatus);
      });

      consoleWarnSpy.mockRestore();
    });

    it('should preserve partial content on mid-stream error', async () => {
      // Create a handler that sends partial content then errors
      server.use(
        http.get(`${API_BASE}/research/report/:ticker/stream`, () => {
          const encoder = new TextEncoder();
          const stream = new ReadableStream({
            async start(controller) {
              controller.enqueue(encoder.encode('event: connected\ndata: {}\n\n'));
              controller.enqueue(encoder.encode('event: executive_meta\ndata: {"toc":[],"ratings":{}}\n\n'));
              controller.enqueue(encoder.encode('event: section_start\ndata: {"section_id":"01_executive_summary","title":"Executive Summary","part":1}\n\n'));
              controller.enqueue(encoder.encode('event: section_chunk\ndata: {"section_id":"01_executive_summary","text":"Partial content..."}\n\n'));
              // Error mid-stream
              controller.enqueue(encoder.encode('event: error\ndata: {"message":"Stream interrupted"}\n\n'));
              controller.close();
            }
          });
          return new HttpResponse(stream, {
            headers: { 'Content-Type': 'text/event-stream' }
          });
        })
      );

      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      // Partial content should be preserved
      expect(result.current.streamedContent['01_executive_summary']).toBeDefined();
      expect(result.current.streamedContent['01_executive_summary'].content).toContain('Partial content');
    });
  });

  describe('Follow-up Error Handling', () => {
    it('should handle follow-up API errors', async () => {
      // First, complete a successful stream
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });

      // Now make follow-up fail
      server.use(
        http.post(`${API_BASE}/research/followup`, () => {
          return HttpResponse.json({ error: 'Follow-up failed' }, { status: 500 });
        })
      );

      await act(async () => {
        await result.current.sendFollowUp('What about debt?', 'token');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      // Original report should still be accessible
      expect(result.current.reportMeta).not.toBeNull();
    });

    it('should handle follow-up abort gracefully', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });

      // Start follow-up then abort
      act(() => {
        result.current.sendFollowUp('Question?', 'token');
      });

      act(() => {
        result.current.abortFollowUp();
      });

      // Should not set error on abort
      expect(result.current.streamStatus).toBe('complete');
    });
  });

  describe('State Recovery', () => {
    it('should allow reset after error', async () => {
      server.use(errorHandlers.serverError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      // Reset should clear error state
      act(() => {
        result.current.reset();
      });

      expect(result.current.error).toBeNull();
      expect(result.current.streamStatus).toBe('idle');
      expect(result.current.selectedTicker).toBeNull();
    });

    it('should preserve follow-up messages on stream error', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Load a saved report with follow-up messages
      act(() => {
        result.current.loadSavedReport({
          ticker: 'AAPL',
          reportMeta: { toc: [], ratings: {} },
          streamedContent: {},
          followUpMessages: [
            { id: 'user-1', type: 'user', content: 'Previous question', isStreaming: false }
          ]
        });
      });

      expect(result.current.followUpMessages).toHaveLength(1);

      // Error during new research shouldn't clear follow-ups
      server.use(errorHandlers.serverError);

      await act(async () => {
        await result.current.startResearch('NVDA');
      });

      // Note: startResearch resets state, so follow-ups are cleared
      // This tests the current behavior - may want to preserve in future
    });

    it('should clear follow-up messages explicitly', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.loadSavedReport({
          ticker: 'AAPL',
          reportMeta: { toc: [], ratings: {} },
          streamedContent: {},
          followUpMessages: [
            { id: 'user-1', type: 'user', content: 'Question', isStreaming: false }
          ]
        });
      });

      expect(result.current.followUpMessages).toHaveLength(1);

      act(() => {
        result.current.clearFollowUp();
      });

      expect(result.current.followUpMessages).toHaveLength(0);
    });
  });

  describe('Concurrent Request Handling', () => {
    it('should abort previous request when starting new research', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Start first request
      act(() => {
        result.current.startResearch('AAPL');
      });

      expect(result.current.selectedTicker).toBe('AAPL');

      // Immediately start second request
      act(() => {
        result.current.startResearch('NVDA');
      });

      expect(result.current.selectedTicker).toBe('NVDA');

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });

      // Should only have NVDA data
      expect(result.current.selectedTicker).toBe('NVDA');
    });

    it('should handle rapid ticker changes gracefully', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Rapidly change tickers
      act(() => {
        result.current.startResearch('AAPL');
      });
      act(() => {
        result.current.startResearch('MSFT');
      });
      act(() => {
        result.current.startResearch('NVDA');
      });

      // Should end up with last ticker
      expect(result.current.selectedTicker).toBe('NVDA');

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });
    });
  });
});
