/**
 * Staleness Guard Test
 *
 * Verifies that rapidly switching between conversations doesn't cause
 * cross-contamination (e.g., clicking Netflix then Home Depot shows
 * Netflix's report instead of Home Depot's).
 *
 * The fix: latestRequestedConversationRef tracks the most recently
 * requested conversation. After each async boundary, we check if the
 * conversation is still current before applying state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { server } from './mocks/server';

const API_BASE = 'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev';

// Two mock conversations: one slow (Netflix), one fast (Home Depot)
const NETFLIX_CONV = {
  conversation_id: 'conv-netflix-123',
  title: 'Research: Netflix',
  user_id: 'user-1',
  metadata: {
    research_state: {
      ticker: 'NFLX',
      toc: [{ section_id: '01_executive_summary', title: 'Executive Summary' }],
      ratings: { overall_verdict: 'HOLD' },
      visible_sections: ['01_executive_summary'],
      active_section_id: '01_executive_summary',
    }
  }
};

const HOMEDEPOT_CONV = {
  conversation_id: 'conv-homedepot-456',
  title: 'Research: Home Depot',
  user_id: 'user-1',
  metadata: {
    research_state: {
      ticker: 'HD',
      toc: [{ section_id: '01_executive_summary', title: 'Executive Summary' }],
      ratings: { overall_verdict: 'BUY' },
      visible_sections: ['01_executive_summary'],
      active_section_id: '01_executive_summary',
    }
  }
};

const NETFLIX_MESSAGES = {
  messages: [
    { message_id: 'msg-1', content: 'Tell me about Netflix', message_type: 'user', timestamp: 1700000000000 },
    { message_id: 'msg-2', content: 'Netflix analysis...', message_type: 'assistant', timestamp: 1700000001000 },
  ]
};

const HOMEDEPOT_MESSAGES = {
  messages: [
    { message_id: 'msg-3', content: 'Tell me about Home Depot', message_type: 'user', timestamp: 1700000002000 },
    { message_id: 'msg-4', content: 'Home Depot analysis...', message_type: 'assistant', timestamp: 1700000003000 },
  ]
};

/**
 * Simulate the core staleness guard logic extracted from App.jsx's
 * loadConversationMessages. This mirrors the real implementation
 * without needing to render the full App component.
 */
function createConversationLoader() {
  // This ref mirrors latestRequestedConversationRef in App.jsx
  const latestRequestedConversationRef = { current: null };

  // Track state mutations for assertions
  const stateLog = [];

  async function loadConversationMessages(conversationId, fetchConversation, fetchMessages) {
    // Set the ref (mirrors App.jsx line ~812)
    latestRequestedConversationRef.current = conversationId;

    // Fetch conversation + messages (the async boundary)
    const [conversation, messagesResponse] = await Promise.all([
      fetchConversation(conversationId),
      fetchMessages(conversationId),
    ]);

    // Staleness check #1 (mirrors App.jsx line ~845)
    if (latestRequestedConversationRef.current !== conversationId) {
      stateLog.push({ type: 'STALE_BAIL', conversationId });
      return;
    }

    // State mutations that would happen (setMessages, loadSavedReport, etc.)
    const messages = messagesResponse.messages || [];
    const ticker = conversation?.metadata?.research_state?.ticker;

    stateLog.push({
      type: 'STATE_APPLIED',
      conversationId,
      ticker,
      messageCount: messages.length,
    });
  }

  return { loadConversationMessages, stateLog, latestRequestedConversationRef };
}


describe('Conversation Staleness Guard', () => {
  beforeEach(() => {
    server.resetHandlers();
  });

  it('applies state for a single conversation load', async () => {
    // Set up MSW handlers for Home Depot (fast response)
    server.use(
      http.get(`${API_BASE}/conversations/conv-homedepot-456`, () => {
        return HttpResponse.json(HOMEDEPOT_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456/messages`, () => {
        return HttpResponse.json(HOMEDEPOT_MESSAGES);
      }),
    );

    const { loadConversationMessages, stateLog } = createConversationLoader();

    const fetchConv = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}`);
      return res.json();
    };
    const fetchMsgs = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
      return res.json();
    };

    await loadConversationMessages('conv-homedepot-456', fetchConv, fetchMsgs);

    expect(stateLog).toHaveLength(1);
    expect(stateLog[0]).toEqual({
      type: 'STATE_APPLIED',
      conversationId: 'conv-homedepot-456',
      ticker: 'HD',
      messageCount: 2,
    });
  });

  it('discards slow response when user switches to another conversation', async () => {
    // Netflix responds slowly (300ms), Home Depot responds fast (10ms)
    server.use(
      http.get(`${API_BASE}/conversations/conv-netflix-123`, async () => {
        await delay(300);
        return HttpResponse.json(NETFLIX_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-netflix-123/messages`, async () => {
        await delay(300);
        return HttpResponse.json(NETFLIX_MESSAGES);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456`, async () => {
        await delay(10);
        return HttpResponse.json(HOMEDEPOT_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456/messages`, async () => {
        await delay(10);
        return HttpResponse.json(HOMEDEPOT_MESSAGES);
      }),
    );

    const { loadConversationMessages, stateLog } = createConversationLoader();

    const fetchConv = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}`);
      return res.json();
    };
    const fetchMsgs = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
      return res.json();
    };

    // Simulate rapid switching: click Netflix, then immediately click Home Depot
    const netflixPromise = loadConversationMessages('conv-netflix-123', fetchConv, fetchMsgs);
    const homedepotPromise = loadConversationMessages('conv-homedepot-456', fetchConv, fetchMsgs);

    // Wait for both to complete
    await Promise.all([netflixPromise, homedepotPromise]);

    // Home Depot (the last clicked) should be applied
    // Netflix (the first clicked, slower) should be discarded
    const applied = stateLog.filter(e => e.type === 'STATE_APPLIED');
    const stale = stateLog.filter(e => e.type === 'STALE_BAIL');

    expect(applied).toHaveLength(1);
    expect(applied[0].ticker).toBe('HD');
    expect(applied[0].conversationId).toBe('conv-homedepot-456');

    expect(stale).toHaveLength(1);
    expect(stale[0].conversationId).toBe('conv-netflix-123');
  });

  it('keeps only the last conversation when rapidly switching through 3', async () => {
    // Conv A (slowest) → Conv B (medium) → Conv C (fastest)
    const CONV_A = { ...NETFLIX_CONV, conversation_id: 'conv-a' };
    const CONV_B = { ...HOMEDEPOT_CONV, conversation_id: 'conv-b' };
    const CONV_C = {
      conversation_id: 'conv-c',
      title: 'Research: Apple',
      user_id: 'user-1',
      metadata: { research_state: { ticker: 'AAPL', toc: [], ratings: {}, visible_sections: [], active_section_id: '01_executive_summary' } }
    };

    server.use(
      http.get(`${API_BASE}/conversations/conv-a`, async () => {
        await delay(500);
        return HttpResponse.json(CONV_A);
      }),
      http.get(`${API_BASE}/conversations/conv-a/messages`, async () => {
        await delay(500);
        return HttpResponse.json({ messages: [] });
      }),
      http.get(`${API_BASE}/conversations/conv-b`, async () => {
        await delay(200);
        return HttpResponse.json(CONV_B);
      }),
      http.get(`${API_BASE}/conversations/conv-b/messages`, async () => {
        await delay(200);
        return HttpResponse.json({ messages: [] });
      }),
      http.get(`${API_BASE}/conversations/conv-c`, async () => {
        await delay(10);
        return HttpResponse.json(CONV_C);
      }),
      http.get(`${API_BASE}/conversations/conv-c/messages`, async () => {
        await delay(10);
        return HttpResponse.json({ messages: [] });
      }),
    );

    const { loadConversationMessages, stateLog } = createConversationLoader();

    const fetchConv = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}`);
      return res.json();
    };
    const fetchMsgs = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
      return res.json();
    };

    // Rapid triple click: A → B → C
    const a = loadConversationMessages('conv-a', fetchConv, fetchMsgs);
    const b = loadConversationMessages('conv-b', fetchConv, fetchMsgs);
    const c = loadConversationMessages('conv-c', fetchConv, fetchMsgs);

    await Promise.all([a, b, c]);

    const applied = stateLog.filter(e => e.type === 'STATE_APPLIED');
    const stale = stateLog.filter(e => e.type === 'STALE_BAIL');

    // Only conv-c (last clicked) should be applied
    expect(applied).toHaveLength(1);
    expect(applied[0].conversationId).toBe('conv-c');
    expect(applied[0].ticker).toBe('AAPL');

    // A and B should be discarded
    expect(stale).toHaveLength(2);
    expect(stale.map(e => e.conversationId).sort()).toEqual(['conv-a', 'conv-b']);
  });

  it('allows same conversation clicked twice (harmless duplicate)', async () => {
    server.use(
      http.get(`${API_BASE}/conversations/conv-homedepot-456`, () => {
        return HttpResponse.json(HOMEDEPOT_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456/messages`, () => {
        return HttpResponse.json(HOMEDEPOT_MESSAGES);
      }),
    );

    const { loadConversationMessages, stateLog } = createConversationLoader();

    const fetchConv = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}`);
      return res.json();
    };
    const fetchMsgs = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
      return res.json();
    };

    // Double-click same conversation
    const p1 = loadConversationMessages('conv-homedepot-456', fetchConv, fetchMsgs);
    const p2 = loadConversationMessages('conv-homedepot-456', fetchConv, fetchMsgs);

    await Promise.all([p1, p2]);

    // Both should pass the staleness check (same ID), which is harmless
    const applied = stateLog.filter(e => e.type === 'STATE_APPLIED');
    expect(applied).toHaveLength(2);
    expect(applied.every(e => e.ticker === 'HD')).toBe(true);
  });

  it('ref always reflects the most recent request', async () => {
    server.use(
      http.get(`${API_BASE}/conversations/conv-netflix-123`, async () => {
        await delay(100);
        return HttpResponse.json(NETFLIX_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-netflix-123/messages`, async () => {
        await delay(100);
        return HttpResponse.json(NETFLIX_MESSAGES);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456`, async () => {
        await delay(10);
        return HttpResponse.json(HOMEDEPOT_CONV);
      }),
      http.get(`${API_BASE}/conversations/conv-homedepot-456/messages`, async () => {
        await delay(10);
        return HttpResponse.json(HOMEDEPOT_MESSAGES);
      }),
    );

    const { loadConversationMessages, latestRequestedConversationRef } = createConversationLoader();

    const fetchConv = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}`);
      return res.json();
    };
    const fetchMsgs = async (id) => {
      const res = await fetch(`${API_BASE}/conversations/${id}/messages`);
      return res.json();
    };

    // After clicking Netflix
    const netflixPromise = loadConversationMessages('conv-netflix-123', fetchConv, fetchMsgs);
    expect(latestRequestedConversationRef.current).toBe('conv-netflix-123');

    // After clicking Home Depot (synchronously overwrites the ref)
    const homedepotPromise = loadConversationMessages('conv-homedepot-456', fetchConv, fetchMsgs);
    expect(latestRequestedConversationRef.current).toBe('conv-homedepot-456');

    await Promise.all([netflixPromise, homedepotPromise]);

    // Still Home Depot after everything resolves
    expect(latestRequestedConversationRef.current).toBe('conv-homedepot-456');
  });
});
