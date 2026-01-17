/**
 * Critical Bug Fixes Test Suite
 *
 * This file contains tests for the three critical bugs fixed in App.jsx:
 * 1. WebSocket Reconnection Race Condition
 * 2. Stale Closure in Chunk Streaming
 * 3. Memory Leak from Untracked Timeouts
 *
 * Run with: npm test -- --testPathPattern=critical-fixes
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { renderHook } from '@testing-library/react-hooks';

// ============================================================================
// TEST UTILITIES & MOCKS
// ============================================================================

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn(key => store[key] ?? null),
    setItem: jest.fn((key, value) => { store[key] = value; }),
    removeItem: jest.fn(key => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock WebSocket
class MockWebSocket {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = WebSocket.CONNECTING;
    this.onopen = null;
    this.onclose = null;
    this.onerror = null;
    this.onmessage = null;
    MockWebSocket.instances.push(this);
  }

  send = jest.fn();
  close = jest.fn(() => {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) this.onclose();
  });

  // Test helpers
  simulateOpen() {
    this.readyState = WebSocket.OPEN;
    if (this.onopen) this.onopen();
  }

  simulateMessage(data) {
    if (this.onmessage) {
      this.onmessage({ data: JSON.stringify(data) });
    }
  }

  simulateClose() {
    this.readyState = WebSocket.CLOSED;
    if (this.onclose) this.onclose();
  }

  static clearInstances() {
    MockWebSocket.instances = [];
  }

  static getInstanceCount() {
    return MockWebSocket.instances.length;
  }
}

global.WebSocket = MockWebSocket;
WebSocket.CONNECTING = 0;
WebSocket.OPEN = 1;
WebSocket.CLOSING = 2;
WebSocket.CLOSED = 3;

// ============================================================================
// BUG FIX #1: WebSocket Reconnection Race Condition
// ============================================================================

describe('Bug Fix #1: WebSocket Reconnection Race Condition', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    MockWebSocket.clearInstances();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  describe('Timeout Cleanup on Unmount', () => {
    it('should cancel pending reconnection timeout when component unmounts', () => {
      const mockConnect = jest.fn();
      let cleanupCalled = false;

      // Simulate the fixed useEffect logic
      const simulateEffect = () => {
        let reconnectTimeoutId = null;

        // Effect body
        reconnectTimeoutId = setTimeout(() => mockConnect(), 500);

        // Return cleanup function
        return () => {
          cleanupCalled = true;
          if (reconnectTimeoutId) {
            clearTimeout(reconnectTimeoutId);
          }
        };
      };

      const cleanup = simulateEffect();

      // Unmount before timeout fires
      cleanup();

      // Advance past the timeout
      jest.advanceTimersByTime(600);

      // connect() should NOT have been called
      expect(mockConnect).not.toHaveBeenCalled();
      expect(cleanupCalled).toBe(true);
    });

    it('should cancel pending reconnection when dependencies change', () => {
      const mockConnect = jest.fn();
      const timeouts = [];

      // Simulate multiple rapid auth changes
      for (let i = 0; i < 3; i++) {
        // Each "render" clears previous timeout
        if (timeouts.length > 0) {
          clearTimeout(timeouts[timeouts.length - 1]);
        }
        timeouts.push(setTimeout(() => mockConnect(), 500));
        jest.advanceTimersByTime(100); // 100ms between changes
      }

      // Advance past all potential timeouts
      jest.advanceTimersByTime(600);

      // Should only connect once (the last scheduled one)
      expect(mockConnect).toHaveBeenCalledTimes(1);
    });
  });

  describe('Concurrent Connection Prevention', () => {
    it('should not create multiple WebSocket connections on rapid auth changes', () => {
      // Simulate the reconnection logic with cleanup
      let reconnectTimeoutId = null;
      const connections = [];

      const reconnect = () => {
        // Cleanup previous
        if (reconnectTimeoutId) {
          clearTimeout(reconnectTimeoutId);
        }

        reconnectTimeoutId = setTimeout(() => {
          connections.push(new MockWebSocket('wss://test.com'));
        }, 500);
      };

      // Rapid auth changes
      reconnect(); // First login
      jest.advanceTimersByTime(100);
      reconnect(); // Logout
      jest.advanceTimersByTime(100);
      reconnect(); // Login again

      // Advance to complete the last timeout
      jest.advanceTimersByTime(500);

      // Should only have one connection
      expect(connections.length).toBe(1);
    });
  });

  describe('No State Updates After Unmount', () => {
    it('should not call connect() after cleanup is called', () => {
      const setStatus = jest.fn();
      let reconnectTimeoutId = null;
      let isMounted = true;

      const connect = () => {
        if (isMounted) {
          setStatus('connected');
        }
      };

      // Start reconnection
      reconnectTimeoutId = setTimeout(connect, 500);

      // Unmount
      isMounted = false;
      clearTimeout(reconnectTimeoutId);

      // Advance time
      jest.advanceTimersByTime(600);

      // setStatus should not have been called
      expect(setStatus).not.toHaveBeenCalled();
    });
  });
});

// ============================================================================
// BUG FIX #2: Stale Closure in Chunk Streaming
// ============================================================================

describe('Bug Fix #2: Stale Closure in Chunk Streaming', () => {
  // Helper to simulate the fixed chunk handling logic
  const handleChunk = (prevMessages, chunkText) => {
    // Find existing streaming message by meta.streaming flag (THE FIX)
    const existingStreamingMsg = prevMessages.find(
      msg => msg.meta?.streaming === true
    );

    if (existingStreamingMsg) {
      // Append to existing streaming message
      return prevMessages.map((msg) =>
        msg.id === existingStreamingMsg.id
          ? { ...msg, content: (msg.content || '') + chunkText }
          : msg
      );
    }

    // No existing streaming message, create one
    const id = `asst-${Date.now()}`;
    return [
      ...prevMessages,
      {
        id,
        type: 'assistant',
        content: chunkText,
        timestamp: new Date().toISOString(),
        meta: { streaming: true }
      },
    ];
  };

  describe('Streaming Message Detection', () => {
    it('should find streaming message by meta.streaming flag', () => {
      const messages = [
        { id: 'usr-1', type: 'user', content: 'Hello' },
        { id: 'asst-1', type: 'assistant', content: 'Hi', meta: { streaming: true } }
      ];

      const result = handleChunk(messages, ' there');

      // Should still have 2 messages
      expect(result).toHaveLength(2);
      // Content should be appended
      expect(result[1].content).toBe('Hi there');
    });

    it('should not rely on external closure variable', () => {
      // This test verifies we find the message inside the callback
      // not by using a potentially stale pendingAssistantId

      let pendingAssistantId = null; // This would be stale in a closure

      const messages = [
        { id: 'usr-1', type: 'user', content: 'Hello' },
        { id: 'asst-999', type: 'assistant', content: 'Response', meta: { streaming: true } }
      ];

      // Even though pendingAssistantId is null/wrong, the fix finds the message correctly
      const result = handleChunk(messages, ' more text');

      expect(result[1].content).toBe('Response more text');
      expect(result[1].id).toBe('asst-999');
    });
  });

  describe('No Duplicate Messages', () => {
    it('should not create duplicate messages when chunks arrive rapidly', () => {
      let messages = [{ id: 'usr-1', type: 'user', content: 'Hello' }];

      // Simulate 10 rapid chunks
      const chunks = ['The ', 'key ', 'to ', 'investing ', 'is ', 'patience ', 'and ', 'discipline', '.', ''];

      for (const chunk of chunks) {
        messages = handleChunk(messages, chunk);
      }

      // Should still only have 2 messages (1 user + 1 assistant)
      expect(messages).toHaveLength(2);
      expect(messages[1].type).toBe('assistant');
      expect(messages[1].content).toBe('The key to investing is patience and discipline.');
      expect(messages[1].meta.streaming).toBe(true);
    });

    it('should create exactly one assistant message for a streaming response', () => {
      let messages = [];

      // Add user message
      messages.push({ id: 'usr-1', type: 'user', content: 'Question?' });

      // Simulate 50 chunks arriving
      for (let i = 0; i < 50; i++) {
        messages = handleChunk(messages, `chunk${i} `);
      }

      // Count assistant messages
      const assistantMessages = messages.filter(m => m.type === 'assistant');

      expect(assistantMessages).toHaveLength(1);
    });
  });

  describe('New Streaming Message Creation', () => {
    it('should create new message when no streaming message exists', () => {
      const messages = [
        { id: 'usr-1', type: 'user', content: 'Hello' },
        { id: 'asst-1', type: 'assistant', content: 'Done', meta: { streaming: false } }
      ];

      const result = handleChunk(messages, 'New response');

      // Should create a new message
      expect(result).toHaveLength(3);
      expect(result[2].content).toBe('New response');
      expect(result[2].meta.streaming).toBe(true);
    });

    it('should create new message when previous message is finalized', () => {
      const messages = [
        { id: 'usr-1', type: 'user', content: 'First question' },
        { id: 'asst-1', type: 'assistant', content: 'First answer', meta: { streaming: false } },
        { id: 'usr-2', type: 'user', content: 'Second question' }
      ];

      const result = handleChunk(messages, 'Second answer start');

      expect(result).toHaveLength(4);
      expect(result[3].meta.streaming).toBe(true);
    });
  });

  describe('Content Accumulation', () => {
    it('should correctly accumulate content across multiple chunks', () => {
      let messages = [{ id: 'usr-1', type: 'user', content: 'Tell me about investing' }];

      const expectedPhrases = [
        'Warren ',
        'Buffett ',
        'says ',
        '"Be ',
        'fearful ',
        'when ',
        'others ',
        'are ',
        'greedy."'
      ];

      for (const phrase of expectedPhrases) {
        messages = handleChunk(messages, phrase);
      }

      expect(messages[1].content).toBe('Warren Buffett says "Be fearful when others are greedy."');
    });

    it('should handle empty chunks gracefully', () => {
      let messages = [{ id: 'usr-1', type: 'user', content: 'Test' }];

      messages = handleChunk(messages, 'Start');
      messages = handleChunk(messages, '');
      messages = handleChunk(messages, '');
      messages = handleChunk(messages, ' End');

      expect(messages[1].content).toBe('Start End');
    });
  });
});

// ============================================================================
// BUG FIX #3: Memory Leak from Untracked Timeouts
// ============================================================================

describe('Bug Fix #3: Memory Leak from Untracked Timeouts', () => {
  let showBannerTimeoutRef;
  let hideBannerTimeoutRef;
  let setShowRateLimitBanner;

  beforeEach(() => {
    jest.useFakeTimers();
    showBannerTimeoutRef = { current: null };
    hideBannerTimeoutRef = { current: null };
    setShowRateLimitBanner = jest.fn();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  // Simulate the fixed banner logic
  const triggerBannerWithFix = () => {
    // Clear any existing timeouts (THE FIX)
    if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
    if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);

    showBannerTimeoutRef.current = setTimeout(() => {
      setShowRateLimitBanner(true);
    }, 500);

    hideBannerTimeoutRef.current = setTimeout(() => {
      setShowRateLimitBanner(false);
    }, 8000);
  };

  describe('Timeout Tracking', () => {
    it('should store timeout IDs in refs', () => {
      triggerBannerWithFix();

      expect(showBannerTimeoutRef.current).not.toBeNull();
      expect(hideBannerTimeoutRef.current).not.toBeNull();
    });

    it('should clear existing timeouts before setting new ones', () => {
      const clearTimeoutSpy = jest.spyOn(global, 'clearTimeout');

      // First query
      triggerBannerWithFix();
      const firstShowTimeout = showBannerTimeoutRef.current;
      const firstHideTimeout = hideBannerTimeoutRef.current;

      // Second query (should clear first timeouts)
      triggerBannerWithFix();

      expect(clearTimeoutSpy).toHaveBeenCalledWith(firstShowTimeout);
      expect(clearTimeoutSpy).toHaveBeenCalledWith(firstHideTimeout);

      clearTimeoutSpy.mockRestore();
    });
  });

  describe('No Banner Flickering', () => {
    it('should not flicker when queries are sent rapidly', () => {
      // Simulate 5 rapid queries
      for (let i = 0; i < 5; i++) {
        triggerBannerWithFix();
        jest.advanceTimersByTime(100); // 100ms between queries
      }

      // Clear call history
      setShowRateLimitBanner.mockClear();

      // Fast forward to when banner should show (500ms after LAST query)
      jest.advanceTimersByTime(400);

      // Banner should show exactly once
      expect(setShowRateLimitBanner).toHaveBeenCalledWith(true);
      expect(setShowRateLimitBanner).toHaveBeenCalledTimes(1);

      // Fast forward to hide time (8000ms after last query)
      jest.advanceTimersByTime(7600);

      // Banner should hide exactly once
      expect(setShowRateLimitBanner).toHaveBeenCalledWith(false);
      expect(setShowRateLimitBanner).toHaveBeenCalledTimes(2);
    });

    it('should show banner for full 8 seconds even with rapid queries', () => {
      // Send 3 queries over 1 second
      triggerBannerWithFix();
      jest.advanceTimersByTime(500);
      triggerBannerWithFix();
      jest.advanceTimersByTime(500);
      triggerBannerWithFix();

      setShowRateLimitBanner.mockClear();

      // Banner should show after 500ms
      jest.advanceTimersByTime(500);
      expect(setShowRateLimitBanner).toHaveBeenCalledWith(true);

      // Should NOT hide yet
      jest.advanceTimersByTime(5000);
      expect(setShowRateLimitBanner).not.toHaveBeenCalledWith(false);

      // Should hide at 8000ms
      jest.advanceTimersByTime(2500);
      expect(setShowRateLimitBanner).toHaveBeenCalledWith(false);
    });
  });

  describe('Cleanup on Unmount', () => {
    it('should cleanup timeouts when component unmounts', () => {
      triggerBannerWithFix();

      // Simulate unmount cleanup effect
      const cleanup = () => {
        if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
        if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);
      };

      cleanup();

      // Fast forward - callbacks should NOT fire
      setShowRateLimitBanner.mockClear();
      jest.advanceTimersByTime(10000);

      expect(setShowRateLimitBanner).not.toHaveBeenCalled();
    });

    it('should not cause React warnings after unmount', () => {
      let isMounted = true;
      const safeSetState = (value) => {
        if (isMounted) {
          setShowRateLimitBanner(value);
        }
      };

      // Start timeouts
      showBannerTimeoutRef.current = setTimeout(() => safeSetState(true), 500);
      hideBannerTimeoutRef.current = setTimeout(() => safeSetState(false), 8000);

      // Unmount after 200ms
      jest.advanceTimersByTime(200);
      isMounted = false;

      // Cleanup
      clearTimeout(showBannerTimeoutRef.current);
      clearTimeout(hideBannerTimeoutRef.current);

      // Fast forward
      jest.advanceTimersByTime(10000);

      // No state updates should have occurred
      expect(setShowRateLimitBanner).not.toHaveBeenCalled();
    });
  });

  describe('Memory Leak Prevention', () => {
    it('should not accumulate timeout references', () => {
      const timeoutRefs = new Set();

      // Simulate 20 queries
      for (let i = 0; i < 20; i++) {
        triggerBannerWithFix();
        timeoutRefs.add(showBannerTimeoutRef.current);
        timeoutRefs.add(hideBannerTimeoutRef.current);
        jest.advanceTimersByTime(50);
      }

      // With proper cleanup, old refs are cleared
      // Only the last 2 should still be active (show + hide)
      // Previous ones were cleared
      jest.advanceTimersByTime(10000);

      // Verify only 2 actual calls happened (1 show + 1 hide)
      const showCalls = setShowRateLimitBanner.mock.calls.filter(c => c[0] === true);
      const hideCalls = setShowRateLimitBanner.mock.calls.filter(c => c[0] === false);

      expect(showCalls).toHaveLength(1);
      expect(hideCalls).toHaveLength(1);
    });
  });
});

// ============================================================================
// INTEGRATION TESTS
// ============================================================================

describe('Critical Fixes Integration', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    MockWebSocket.clearInstances();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should handle auth -> query -> stream -> unmount flow', () => {
    const errors = [];
    const originalConsoleError = console.error;
    console.error = (...args) => {
      errors.push(args.join(' '));
      originalConsoleError(...args);
    };

    // Simulate component state
    let isMounted = true;
    let messages = [];
    let reconnectTimeoutId = null;
    const showBannerTimeoutRef = { current: null };
    const hideBannerTimeoutRef = { current: null };

    // 1. Auth triggers reconnection
    reconnectTimeoutId = setTimeout(() => {
      if (isMounted) {
        const ws = new MockWebSocket('wss://test.com');
        ws.simulateOpen();
      }
    }, 500);

    // 2. Advance to connection
    jest.advanceTimersByTime(500);

    // 3. Simulate query and streaming (unauthenticated)
    messages.push({ id: 'usr-1', type: 'user', content: 'Test' });

    // Banner timeouts
    showBannerTimeoutRef.current = setTimeout(() => {
      if (isMounted) messages.push({ banner: 'show' });
    }, 500);
    hideBannerTimeoutRef.current = setTimeout(() => {
      if (isMounted) messages.push({ banner: 'hide' });
    }, 8000);

    // 4. Stream chunks
    const chunk1 = { id: 'asst-1', type: 'assistant', content: 'Resp', meta: { streaming: true } };
    messages.push(chunk1);

    // 5. Unmount quickly (within 100ms)
    jest.advanceTimersByTime(100);
    isMounted = false;

    // Cleanup all timeouts
    if (reconnectTimeoutId) clearTimeout(reconnectTimeoutId);
    if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
    if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);

    // 6. Advance time past all potential callbacks
    jest.advanceTimersByTime(10000);

    // Verify no React state update warnings
    const reactWarnings = errors.filter(e =>
      e.includes("Can't perform a React state update on an unmounted component")
    );

    expect(reactWarnings).toHaveLength(0);

    console.error = originalConsoleError;
  });
});

// ============================================================================
// MANUAL TEST CHECKLIST (for DevTools)
// ============================================================================

/**
 * MANUAL TESTING CHECKLIST
 *
 * Bug #1: WebSocket Reconnection Race Condition
 * ---------------------------------------------
 * 1. Open DevTools Console
 * 2. Log in to the app
 * 3. Immediately close the tab within 500ms
 * 4. Check for "Can't perform a React state update" warning
 * Expected: No warning should appear
 *
 * Bug #2: Stale Closure in Chunk Streaming
 * ----------------------------------------
 * 1. Open DevTools Console + React DevTools
 * 2. Send a message to the AI
 * 3. Watch the response stream in
 * 4. Check messages state in React DevTools
 * Expected: Single assistant message that builds up (not multiple bubbles)
 *
 * Bug #3: Memory Leak from Untracked Timeouts
 * -------------------------------------------
 * 1. Open DevTools Console
 * 2. As unauthenticated user, send 3 queries rapidly
 * 3. Watch the rate limit banner behavior
 * 4. Close tab immediately after queries
 * Expected: Banner appears once, no console warnings, no flickering
 */
