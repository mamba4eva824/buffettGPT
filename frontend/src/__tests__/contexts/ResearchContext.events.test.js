/**
 * ResearchContext Event Parsing Tests
 *
 * P0 Tests for SSE event parsing in the investment research system.
 * Tests all event types and edge cases.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MOCK_TOC, MOCK_RATINGS } from '../mocks/researchFixtures';

// Action types (mirrors ResearchContext.jsx)
const ACTIONS = {
  SET_STATUS: 'SET_STATUS',
  SET_REPORT_META: 'SET_REPORT_META',
  SECTION_START: 'SECTION_START',
  SECTION_CHUNK: 'SECTION_CHUNK',
  SECTION_END: 'SECTION_END',
  SET_ERROR: 'SET_ERROR',
  FOLLOWUP_START: 'FOLLOWUP_START',
  FOLLOWUP_CHUNK: 'FOLLOWUP_CHUNK',
  FOLLOWUP_END: 'FOLLOWUP_END',
};

/**
 * SSE Event Handler (mirrors ResearchContext.jsx handleSSEEvent)
 * Extracted for testing purposes
 */
function handleSSEEvent(eventType, data, dispatch) {
  // Guard against null/undefined data to prevent crashes from malformed SSE events
  if (!data) {
    console.warn('SSE event received with null/undefined data:', eventType);
    return;
  }

  switch (eventType) {
    case 'connected':
      dispatch({ type: ACTIONS.SET_STATUS, status: 'streaming' });
      break;

    case 'executive_meta':
      dispatch({
        type: ACTIONS.SET_REPORT_META,
        meta: {
          toc: data.toc || [],
          ratings: data.ratings || {},
          total_word_count: data.total_word_count || 0,
          generated_at: data.generated_at || null,
        },
      });
      break;

    case 'section_start':
      dispatch({
        type: ACTIONS.SECTION_START,
        section: {
          section_id: data.section_id,
          title: data.title,
          part: data.part,
          icon: data.icon,
          word_count: data.word_count,
        },
      });
      break;

    case 'section_chunk':
      dispatch({
        type: ACTIONS.SECTION_CHUNK,
        sectionId: data.section_id,
        text: data.text,
      });
      break;

    case 'section_end':
      dispatch({
        type: ACTIONS.SECTION_END,
        sectionId: data.section_id,
      });
      break;

    case 'complete':
      dispatch({ type: ACTIONS.SET_STATUS, status: 'complete' });
      break;

    case 'error':
      dispatch({ type: ACTIONS.SET_ERROR, error: data.message || 'Unknown error' });
      break;

    case 'progress':
      // Progress events are informational - no state change needed
      break;

    case 'followup_start':
      dispatch({
        type: ACTIONS.FOLLOWUP_START,
        messageId: data.message_id,
      });
      break;

    case 'followup_chunk':
      dispatch({
        type: ACTIONS.FOLLOWUP_CHUNK,
        messageId: data.message_id,
        text: data.text,
      });
      break;

    case 'followup_end':
      dispatch({
        type: ACTIONS.FOLLOWUP_END,
        messageId: data.message_id,
      });
      break;

    default:
      console.warn('Unknown SSE event:', eventType, data);
  }
}

describe('SSE Event Parsing', () => {
  let dispatch;
  let consoleWarnSpy;

  beforeEach(() => {
    dispatch = vi.fn();
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  describe('connected event', () => {
    it('should set streamStatus to streaming', () => {
      handleSSEEvent('connected', {}, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_STATUS,
        status: 'streaming'
      });
    });
  });

  describe('executive_meta event', () => {
    it('should correctly populate reportMeta with toc, ratings, word_count, generated_at', () => {
      const data = {
        toc: MOCK_TOC,
        ratings: MOCK_RATINGS,
        total_word_count: 15000,
        generated_at: '2026-01-24T10:00:00Z'
      };

      handleSSEEvent('executive_meta', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_REPORT_META,
        meta: {
          toc: MOCK_TOC,
          ratings: MOCK_RATINGS,
          total_word_count: 15000,
          generated_at: '2026-01-24T10:00:00Z'
        }
      });
    });

    it('should handle missing fields with defaults', () => {
      handleSSEEvent('executive_meta', {}, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_REPORT_META,
        meta: {
          toc: [],
          ratings: {},
          total_word_count: 0,
          generated_at: null
        }
      });
    });

    it('should handle partial data', () => {
      const data = { toc: MOCK_TOC };

      handleSSEEvent('executive_meta', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_REPORT_META,
        meta: {
          toc: MOCK_TOC,
          ratings: {},
          total_word_count: 0,
          generated_at: null
        }
      });
    });
  });

  describe('section_start event', () => {
    it('should initialize section in streamedContent with metadata', () => {
      const data = {
        section_id: '01_executive_summary',
        title: 'Executive Summary',
        part: 1,
        icon: 'file-text',
        word_count: 600
      };

      handleSSEEvent('section_start', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SECTION_START,
        section: {
          section_id: '01_executive_summary',
          title: 'Executive Summary',
          part: 1,
          icon: 'file-text',
          word_count: 600
        }
      });
    });

    it('should handle all section fields', () => {
      const data = {
        section_id: '06_growth',
        title: 'Growth Analysis',
        part: 2,
        icon: 'trending-up',
        word_count: 800
      };

      handleSSEEvent('section_start', data, dispatch);

      const call = dispatch.mock.calls[0][0];
      expect(call.section.section_id).toBe('06_growth');
      expect(call.section.part).toBe(2);
    });
  });

  describe('section_chunk event', () => {
    it('should append text to correct section', () => {
      const data = {
        section_id: '01_executive_summary',
        text: 'This is chunk content.'
      };

      handleSSEEvent('section_chunk', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SECTION_CHUNK,
        sectionId: '01_executive_summary',
        text: 'This is chunk content.'
      });
    });

    it('should handle empty text chunk', () => {
      const data = {
        section_id: '01_executive_summary',
        text: ''
      };

      handleSSEEvent('section_chunk', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SECTION_CHUNK,
        sectionId: '01_executive_summary',
        text: ''
      });
    });

    it('should handle special characters in chunk', () => {
      const data = {
        section_id: '01_executive_summary',
        text: '## Heading\n\n- Bullet 1\n- Bullet 2\n\n| Col1 | Col2 |\n|------|------|\n'
      };

      handleSSEEvent('section_chunk', data, dispatch);

      const call = dispatch.mock.calls[0][0];
      expect(call.text).toContain('##');
      expect(call.text).toContain('|');
    });
  });

  describe('section_end event', () => {
    it('should mark section as complete', () => {
      const data = { section_id: '01_executive_summary' };

      handleSSEEvent('section_end', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SECTION_END,
        sectionId: '01_executive_summary'
      });
    });
  });

  describe('complete event', () => {
    it('should set streamStatus to complete', () => {
      handleSSEEvent('complete', {}, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_STATUS,
        status: 'complete'
      });
    });
  });

  describe('error event', () => {
    it('should dispatch SET_ERROR with message', () => {
      const data = { message: 'Report generation failed' };

      handleSSEEvent('error', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_ERROR,
        error: 'Report generation failed'
      });
    });

    it('should use default error message when message is missing', () => {
      handleSSEEvent('error', {}, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.SET_ERROR,
        error: 'Unknown error'
      });
    });
  });

  describe('progress event', () => {
    it('should not dispatch any action (informational only)', () => {
      handleSSEEvent('progress', { message: 'Processing section 3/13' }, dispatch);

      expect(dispatch).not.toHaveBeenCalled();
    });
  });

  describe('followup_start event', () => {
    it('should create new follow-up message entry', () => {
      const data = { message_id: 'msg-12345' };

      handleSSEEvent('followup_start', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.FOLLOWUP_START,
        messageId: 'msg-12345'
      });
    });
  });

  describe('followup_chunk event', () => {
    it('should append to correct message by message_id', () => {
      const data = {
        message_id: 'msg-12345',
        text: 'Response chunk'
      };

      handleSSEEvent('followup_chunk', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.FOLLOWUP_CHUNK,
        messageId: 'msg-12345',
        text: 'Response chunk'
      });
    });
  });

  describe('followup_end event', () => {
    it('should mark follow-up complete', () => {
      const data = { message_id: 'msg-12345' };

      handleSSEEvent('followup_end', data, dispatch);

      expect(dispatch).toHaveBeenCalledWith({
        type: ACTIONS.FOLLOWUP_END,
        messageId: 'msg-12345'
      });
    });
  });

  describe('Edge Cases', () => {
    it('should handle unknown event types with warning', () => {
      handleSSEEvent('unknown_event', { foo: 'bar' }, dispatch);

      expect(dispatch).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalledWith('Unknown SSE event:', 'unknown_event', { foo: 'bar' });
    });

    it('should handle null data gracefully with warning', () => {
      // FIX: Added null guard to handleSSEEvent (2026-01-24)
      expect(() => {
        handleSSEEvent('section_chunk', null, dispatch);
      }).not.toThrow();

      expect(dispatch).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalledWith('SSE event received with null/undefined data:', 'section_chunk');
    });

    it('should handle undefined data gracefully with warning', () => {
      expect(() => {
        handleSSEEvent('section_start', undefined, dispatch);
      }).not.toThrow();

      expect(dispatch).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalledWith('SSE event received with null/undefined data:', 'section_start');
    });

    it('should handle undefined event type', () => {
      handleSSEEvent(undefined, {}, dispatch);

      expect(dispatch).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });

    it('should handle empty string event type', () => {
      handleSSEEvent('', {}, dispatch);

      expect(dispatch).not.toHaveBeenCalled();
      expect(consoleWarnSpy).toHaveBeenCalled();
    });
  });
});

describe('SSE Line Parsing', () => {
  /**
   * Test SSE line buffering and parsing
   * Simulates how ResearchContext processes incoming SSE data
   */

  function parseSSELines(rawData) {
    const events = [];
    let buffer = '';
    let currentEvent = '';

    // Simulate streaming chunks
    buffer += rawData;
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6));
          events.push({ event: currentEvent, data });
        } catch (e) {
          // Skip malformed JSON
          events.push({ event: currentEvent, error: 'JSON parse error' });
        }
      }
    }

    return { events, buffer };
  }

  it('should parse complete SSE message', () => {
    const rawData = 'event: connected\ndata: {}\n\n';
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('connected');
    expect(events[0].data).toEqual({});
  });

  it('should parse multiple SSE messages', () => {
    const rawData = 'event: connected\ndata: {}\n\nevent: section_start\ndata: {"section_id":"01"}\n\n';
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(2);
    expect(events[0].event).toBe('connected');
    expect(events[1].event).toBe('section_start');
    expect(events[1].data.section_id).toBe('01');
  });

  it('should handle partial message in buffer', () => {
    const rawData = 'event: section_chunk\ndata: {"text":"partial';
    const { events, buffer } = parseSSELines(rawData);

    expect(events).toHaveLength(0);
    expect(buffer).toBe('data: {"text":"partial');
  });

  it('should handle malformed JSON gracefully', () => {
    const rawData = 'event: executive_meta\ndata: {invalid json}\n\n';
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(1);
    expect(events[0].error).toBe('JSON parse error');
  });

  it('should handle complex JSON data', () => {
    const complexData = {
      toc: [{ section_id: '01', title: 'Test' }],
      ratings: { growth: { rating: 'A+' } },
      total_word_count: 15000
    };
    const rawData = `event: executive_meta\ndata: ${JSON.stringify(complexData)}\n\n`;
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(1);
    expect(events[0].data.toc).toHaveLength(1);
    expect(events[0].data.ratings.growth.rating).toBe('A+');
  });

  it('should handle newlines in content', () => {
    const data = { text: 'Line 1\\nLine 2\\nLine 3' };
    const rawData = `event: section_chunk\ndata: ${JSON.stringify(data)}\n\n`;
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(1);
    expect(events[0].data.text).toContain('\\n');
  });

  it('should handle empty data payload', () => {
    const rawData = 'event: complete\ndata: {}\n\n';
    const { events } = parseSSELines(rawData);

    expect(events).toHaveLength(1);
    expect(events[0].data).toEqual({});
  });
});
