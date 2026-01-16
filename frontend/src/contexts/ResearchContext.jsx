import React, { createContext, useContext, useReducer, useRef, useCallback } from 'react';

// API base URL from environment - Investment Research uses API Gateway
const API_BASE = import.meta.env.VITE_RESEARCH_API_URL || 'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev';

// Initial state
const initialState = {
  selectedTicker: null,
  activeSectionId: null,
  isStreaming: false,
  streamStatus: 'idle', // 'idle' | 'connecting' | 'streaming' | 'complete' | 'error'
  reportMeta: null, // { toc, ratings, total_word_count, generated_at }
  streamedContent: {}, // { [section_id]: { title, content, isComplete, part, icon, word_count } }
  error: null,
  currentStreamingSection: null, // Track which section is currently streaming
};

// Action types
const ACTIONS = {
  START_RESEARCH: 'START_RESEARCH',
  SET_STATUS: 'SET_STATUS',
  SET_REPORT_META: 'SET_REPORT_META',
  SECTION_START: 'SECTION_START',
  SECTION_CHUNK: 'SECTION_CHUNK',
  SECTION_END: 'SECTION_END',
  SET_ACTIVE_SECTION: 'SET_ACTIVE_SECTION',
  SET_SECTION: 'SET_SECTION',
  SET_ERROR: 'SET_ERROR',
  RESET: 'RESET',
};

// Reducer
function researchReducer(state, action) {
  switch (action.type) {
    case ACTIONS.START_RESEARCH:
      return {
        ...initialState,
        selectedTicker: action.ticker,
        streamStatus: 'connecting',
        isStreaming: true,
      };

    case ACTIONS.SET_STATUS:
      return {
        ...state,
        streamStatus: action.status,
        isStreaming: action.status === 'connecting' || action.status === 'streaming',
      };

    case ACTIONS.SET_REPORT_META:
      return {
        ...state,
        reportMeta: action.meta,
        streamStatus: 'streaming',
        // Auto-set Executive Summary as active (first section in ToC with merged schema)
        activeSectionId: state.activeSectionId || (action.meta?.toc?.[0]?.section_id || '01_executive_summary'),
      };

    case ACTIONS.SECTION_START:
      return {
        ...state,
        currentStreamingSection: action.section.section_id,
        streamedContent: {
          ...state.streamedContent,
          [action.section.section_id]: {
            title: action.section.title,
            content: '',
            isComplete: false,
            part: action.section.part,
            icon: action.section.icon,
            word_count: action.section.word_count,
          },
        },
      };

    case ACTIONS.SECTION_CHUNK:
      return {
        ...state,
        streamedContent: {
          ...state.streamedContent,
          [action.sectionId]: {
            ...state.streamedContent[action.sectionId],
            content: (state.streamedContent[action.sectionId]?.content || '') + action.text,
          },
        },
      };

    case ACTIONS.SECTION_END:
      return {
        ...state,
        currentStreamingSection: null,
        streamedContent: {
          ...state.streamedContent,
          [action.sectionId]: {
            ...state.streamedContent[action.sectionId],
            isComplete: true,
          },
        },
      };

    case ACTIONS.SET_ACTIVE_SECTION:
      return {
        ...state,
        activeSectionId: action.sectionId,
      };

    case ACTIONS.SET_SECTION:
      return {
        ...state,
        streamedContent: {
          ...state.streamedContent,
          [action.sectionId]: {
            title: action.title,
            content: action.content,
            isComplete: true,
            part: action.part,
            icon: action.icon,
            word_count: action.word_count,
          },
        },
      };

    case ACTIONS.SET_ERROR:
      return {
        ...state,
        error: action.error,
        streamStatus: 'error',
        isStreaming: false,
      };

    case ACTIONS.RESET:
      return initialState;

    default:
      return state;
  }
}

// Context
const ResearchContext = createContext(null);

// Provider component
export function ResearchProvider({ children }) {
  const [state, dispatch] = useReducer(researchReducer, initialState);
  const abortControllerRef = useRef(null);

  // Abort current stream
  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Start research for a ticker
  const startResearch = useCallback(async (ticker, token = null) => {
    // Abort any existing stream
    abortStream();

    // Reset state and start new research
    dispatch({ type: ACTIONS.START_RESEARCH, ticker: ticker.toUpperCase() });

    // Create new AbortController
    abortControllerRef.current = new AbortController();

    try {
      const url = `${API_BASE}/research/report/${ticker.toUpperCase()}/stream`;
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      const response = await fetch(url, {
        signal: abortControllerRef.current.signal,
        headers,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(currentEvent, data, dispatch);
            } catch (e) {
              console.warn('Failed to parse SSE data:', e);
            }
          }
        }
      }

      dispatch({ type: ACTIONS.SET_STATUS, status: 'complete' });
    } catch (error) {
      if (error.name === 'AbortError') {
        // Stream was intentionally aborted, not an error
        return;
      }
      console.error('Research stream error:', error);
      dispatch({ type: ACTIONS.SET_ERROR, error: error.message });
    }
  }, [abortStream]);

  // Fetch a specific section on-demand
  const fetchSection = useCallback(async (ticker, sectionId, token = null) => {
    try {
      const url = `${API_BASE}/research/report/${ticker.toUpperCase()}/section/${sectionId}`;
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      const response = await fetch(url, { headers });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      dispatch({
        type: ACTIONS.SET_SECTION,
        sectionId: data.section_id,
        title: data.title,
        content: data.content,
        part: data.part,
        icon: data.icon,
        word_count: data.word_count,
      });

      return data;
    } catch (error) {
      console.error('Fetch section error:', error);
      dispatch({ type: ACTIONS.SET_ERROR, error: error.message });
      throw error;
    }
  }, []);

  // Set active section
  const setActiveSection = useCallback((sectionId) => {
    dispatch({ type: ACTIONS.SET_ACTIVE_SECTION, sectionId });
  }, []);

  // Reset state
  const reset = useCallback(() => {
    abortStream();
    dispatch({ type: ACTIONS.RESET });
  }, [abortStream]);

  const value = {
    ...state,
    startResearch,
    abortStream,
    fetchSection,
    setActiveSection,
    reset,
  };

  return (
    <ResearchContext.Provider value={value}>
      {children}
    </ResearchContext.Provider>
  );
}

// Custom hook
export function useResearch() {
  const context = useContext(ResearchContext);
  if (!context) {
    throw new Error('useResearch must be used within a ResearchProvider');
  }
  return context;
}

// SSE event handler
function handleSSEEvent(eventType, data, dispatch) {
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
      // StreamingIndicator tracks progress via completed sections
      break;

    default:
      console.warn('Unknown SSE event:', eventType, data);
  }
}

export default ResearchContext;
