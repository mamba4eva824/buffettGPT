/**
 * ResearchContext SSE Connection Tests
 *
 * P0 Tests for SSE streaming connection handling.
 * Tests connection lifecycle, abort handling, and error scenarios.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { ResearchProvider, useResearch } from '../../contexts/ResearchContext';
import { server } from '../mocks/server';
import { errorHandlers } from '../mocks/handlers';

// Wrapper component for testing hooks
const wrapper = ({ children }) => (
  <ResearchProvider>{children}</ResearchProvider>
);

describe('ResearchContext SSE Connection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    server.resetHandlers();
  });

  describe('Connection Establishment', () => {
    it('should establish SSE connection with correct URL', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch');
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        result.current.startResearch('AAPL', 'test-token');
      });

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      const callUrl = fetchSpy.mock.calls[0][0];
      expect(callUrl).toContain('/research/report/AAPL/stream');
    });

    it('should include authorization header when token provided', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch');
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        result.current.startResearch('AAPL', 'test-token');
      });

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      const callOptions = fetchSpy.mock.calls[0][1];
      expect(callOptions.headers.Authorization).toBe('Bearer test-token');
    });

    it('should uppercase ticker in URL', async () => {
      const fetchSpy = vi.spyOn(global, 'fetch');
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        result.current.startResearch('aapl');
      });

      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled();
      });

      const callUrl = fetchSpy.mock.calls[0][0];
      expect(callUrl).toContain('/AAPL/');
    });

    it('should set streamStatus to connecting initially', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Start research without waiting
      act(() => {
        result.current.startResearch('AAPL');
      });

      // Check immediate state
      expect(result.current.streamStatus).toBe('connecting');
      expect(result.current.isStreaming).toBe(true);
    });

    it('should set selectedTicker on start', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.startResearch('NVDA');
      });

      expect(result.current.selectedTicker).toBe('NVDA');
    });
  });

  describe('Stream Completion', () => {
    it('should set streamStatus to complete after stream ends', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('complete');
      });

      expect(result.current.isStreaming).toBe(false);
    });

    it('should populate reportMeta from executive_meta event', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.reportMeta).not.toBeNull();
      });

      expect(result.current.reportMeta.toc).toBeDefined();
      expect(result.current.reportMeta.ratings).toBeDefined();
    });

    it('should stream section content', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamedContent['01_executive_summary']).toBeDefined();
      });

      expect(result.current.streamedContent['01_executive_summary'].isComplete).toBe(true);
    });
  });

  describe('Abort Handling', () => {
    it('should abort stream on component unmount via reset', async () => {
      const { result, unmount } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.startResearch('AAPL');
      });

      // Unmount should trigger cleanup
      unmount();

      // No error should be thrown
    });

    it('should abort stream when abortStream is called', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.startResearch('AAPL');
      });

      act(() => {
        result.current.abortStream();
      });

      // AbortError should not set error state
      expect(result.current.error).toBeNull();
    });

    it('should abort previous stream when starting new research', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Start first research
      act(() => {
        result.current.startResearch('AAPL');
      });

      // Start second research immediately
      act(() => {
        result.current.startResearch('NVDA');
      });

      expect(result.current.selectedTicker).toBe('NVDA');
    });

    it('should not set error state on AbortError', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.startResearch('AAPL');
      });

      // Abort the stream
      act(() => {
        result.current.abortStream();
      });

      expect(result.current.error).toBeNull();
      expect(result.current.streamStatus).not.toBe('error');
    });
  });

  describe('Error Handling', () => {
    it('should handle 401 Unauthorized error', async () => {
      server.use(errorHandlers.unauthorized);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('401');
      expect(result.current.streamStatus).toBe('error');
      expect(result.current.isStreaming).toBe(false);
    });

    it('should handle 429 Rate Limit error', async () => {
      server.use(errorHandlers.rateLimited);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('429');
      expect(result.current.streamStatus).toBe('error');
    });

    it('should handle 500 Server Error', async () => {
      server.use(errorHandlers.serverError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('500');
      expect(result.current.streamStatus).toBe('error');
    });

    it('should handle network errors', async () => {
      server.use(errorHandlers.networkError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.streamStatus).toBe('error');
      });

      expect(result.current.error).toBeDefined();
    });

    it('should handle SSE error event', async () => {
      server.use(errorHandlers.sseError);
      const { result } = renderHook(() => useResearch(), { wrapper });

      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.error).toBeDefined();
      });

      expect(result.current.error).toContain('Report generation failed');
    });
  });

  describe('Reset Functionality', () => {
    it('should reset state and abort streams', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Start research and wait for it to complete
      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      await waitFor(() => {
        expect(result.current.reportMeta).not.toBeNull();
      });

      // Reset
      act(() => {
        result.current.reset();
      });

      expect(result.current.selectedTicker).toBeNull();
      expect(result.current.reportMeta).toBeNull();
      expect(result.current.streamedContent).toEqual({});
      expect(result.current.streamStatus).toBe('idle');
    });
  });

  describe('Section Fetching', () => {
    it('should fetch individual section on demand', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      // Set up initial state
      await act(async () => {
        await result.current.startResearch('AAPL');
      });

      // Fetch a section
      await act(async () => {
        await result.current.fetchSection('AAPL', '06_growth');
      });

      await waitFor(() => {
        expect(result.current.streamedContent['06_growth']).toBeDefined();
      });

      expect(result.current.streamedContent['06_growth'].isComplete).toBe(true);
    });

    it('should handle section fetch error', async () => {
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
    });
  });

  describe('Active Section Management', () => {
    it('should update activeSectionId', async () => {
      const { result } = renderHook(() => useResearch(), { wrapper });

      act(() => {
        result.current.setActiveSection('06_growth');
      });

      expect(result.current.activeSectionId).toBe('06_growth');
    });
  });
});
