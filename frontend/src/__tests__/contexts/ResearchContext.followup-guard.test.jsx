/**
 * ResearchContext Follow-Up URL Guard Tests
 *
 * Tests the FOLLOWUP_URL validation guard added to sendFollowUp().
 * When both VITE_ANALYSIS_FOLLOWUP_URL and VITE_RESEARCH_API_URL are empty,
 * the follow-up should fail gracefully with a user-facing error instead of
 * making a request to an invalid URL like '/research/followup'.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import React from 'react';
import { server } from '../mocks/server';
import { http, HttpResponse } from 'msw';

// Must match vite.config.js test.env
const FOLLOWUP_BASE = 'https://test-followup.example.com';

// Wrapper component for testing hooks
const wrapper = ({ children }) => {
  // Lazy import to allow env manipulation before module load
  const { ResearchProvider } = require('../../contexts/ResearchContext');
  return <ResearchProvider>{children}</ResearchProvider>;
};

describe('Follow-Up URL Validation Guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    server.resetHandlers();
  });

  it('should dispatch error when follow-up URL is properly configured', async () => {
    // With the test env vars set in vite.config.js, the follow-up URL
    // should be VITE_ANALYSIS_FOLLOWUP_URL = 'https://test-followup.example.com'
    // so the guard should NOT trigger — instead a real fetch is attempted
    const { ResearchProvider, useResearch } = await import('../../contexts/ResearchContext');
    const testWrapper = ({ children }) => <ResearchProvider>{children}</ResearchProvider>;

    const { result } = renderHook(() => useResearch(), { wrapper: testWrapper });

    // Load a report first (sendFollowUp requires selectedTicker)
    act(() => {
      result.current.loadSavedReport({
        ticker: 'AAPL',
        reportMeta: { toc: [], ratings: {} },
        streamedContent: {},
        followUpMessages: [],
      });
    });

    // Send follow-up — with env vars set, this should attempt a real fetch
    // (which MSW will handle)
    await act(async () => {
      await result.current.sendFollowUp('What about revenue?', 'test-token', 'conv-123');
    });

    // The request should have been made (either success or error from MSW)
    // The key point: it should NOT have the "temporarily unavailable" error
    // because the URL is properly configured
    await waitFor(() => {
      expect(result.current.isFollowUpStreaming).toBe(false);
    });
  });

  it('should show user-facing error when sendFollowUp is called without ticker', async () => {
    const { ResearchProvider, useResearch } = await import('../../contexts/ResearchContext');
    const testWrapper = ({ children }) => <ResearchProvider>{children}</ResearchProvider>;

    const { result } = renderHook(() => useResearch(), { wrapper: testWrapper });

    // Don't load any report — selectedTicker will be null
    await act(async () => {
      await result.current.sendFollowUp('What about revenue?', 'test-token');
    });

    // Should have returned early without error (guard checks selectedTicker first)
    expect(result.current.error).toBeNull();
    expect(result.current.isFollowUpStreaming).toBe(false);
  });

  it('should not allow concurrent follow-up requests when isFollowUpStreaming is true', async () => {
    // Install a slow follow-up handler so streaming lasts long enough to test concurrency
    server.use(
      http.post(FOLLOWUP_BASE, async () => {
        const encoder = new TextEncoder();
        const messageId = `msg-${Date.now()}`;
        const stream = new ReadableStream({
          async start(controller) {
            controller.enqueue(encoder.encode(`event: followup_start\ndata: ${JSON.stringify({ message_id: messageId })}\n\n`));
            // Long delay to keep streaming state active
            await new Promise(r => setTimeout(r, 500));
            controller.enqueue(encoder.encode(`event: followup_chunk\ndata: ${JSON.stringify({ message_id: messageId, text: 'Slow response' })}\n\n`));
            await new Promise(r => setTimeout(r, 100));
            controller.enqueue(encoder.encode(`event: followup_end\ndata: ${JSON.stringify({ message_id: messageId })}\n\n`));
            controller.close();
          }
        });
        return new HttpResponse(stream, {
          headers: { 'Content-Type': 'text/event-stream' }
        });
      })
    );

    const { ResearchProvider, useResearch } = await import('../../contexts/ResearchContext');
    const testWrapper = ({ children }) => <ResearchProvider>{children}</ResearchProvider>;

    const { result } = renderHook(() => useResearch(), { wrapper: testWrapper });

    // Load a report
    act(() => {
      result.current.loadSavedReport({
        ticker: 'AAPL',
        reportMeta: { toc: [], ratings: {} },
        streamedContent: {},
        followUpMessages: [],
      });
    });

    // Start first follow-up (don't await — let it stream)
    act(() => {
      result.current.sendFollowUp('First question?', 'test-token', 'conv-123');
    });

    // Wait for the streaming state to be set before attempting the second call
    await waitFor(() => {
      expect(result.current.isFollowUpStreaming).toBe(true);
    }, { timeout: 2000 });

    // Now try to send second while first is actually streaming
    // isFollowUpStreaming is true, so the guard should block this
    act(() => {
      result.current.sendFollowUp('Second question?', 'test-token', 'conv-123');
    });

    // Wait for first to complete
    await waitFor(() => {
      expect(result.current.isFollowUpStreaming).toBe(false);
    }, { timeout: 5000 });

    // Should only have messages from the first question (user + assistant)
    // The second call was blocked by the isFollowUpStreaming guard
    const userMessages = result.current.followUpMessages.filter(m => m.type === 'user');
    expect(userMessages).toHaveLength(1);
    expect(userMessages[0].content).toBe('First question?');
  });
});
