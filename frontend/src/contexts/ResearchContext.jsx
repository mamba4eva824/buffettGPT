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
  // Follow-up chat state
  followUpMessages: [], // [{id, type:'user'|'assistant', content, isStreaming, timestamp}]
  isFollowUpStreaming: false,
  currentFollowUpMessageId: null,
  collapsedFollowUpIds: [], // Track which follow-up messages are collapsed
  // Interaction timeline - tracks chronological order of section views and follow-ups
  interactionLog: [], // [{type: 'section'|'followup', id: string, timestamp: string}]
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
  CLEAR_STREAMING_SECTION: 'CLEAR_STREAMING_SECTION',  // Clear currentStreamingSection after animation
  SET_ERROR: 'SET_ERROR',
  RESET: 'RESET',
  LOAD_SAVED_REPORT: 'LOAD_SAVED_REPORT',  // Load pre-saved report from history
  // Follow-up chat actions
  FOLLOWUP_USER_MESSAGE: 'FOLLOWUP_USER_MESSAGE',
  FOLLOWUP_START: 'FOLLOWUP_START',
  FOLLOWUP_CHUNK: 'FOLLOWUP_CHUNK',
  FOLLOWUP_END: 'FOLLOWUP_END',
  FOLLOWUP_ERROR: 'FOLLOWUP_ERROR',
  CLEAR_FOLLOWUP: 'CLEAR_FOLLOWUP',
  TOGGLE_FOLLOWUP_COLLAPSE: 'TOGGLE_FOLLOWUP_COLLAPSE',
  // Interaction timeline actions
  LOG_SECTION_INTERACTION: 'LOG_SECTION_INTERACTION',
  LOG_FOLLOWUP_INTERACTION: 'LOG_FOLLOWUP_INTERACTION',
  SET_INTERACTION_LOG: 'SET_INTERACTION_LOG',
};

// Reducer
function researchReducer(state, action) {
  switch (action.type) {
    case ACTIONS.START_RESEARCH:
      console.log('[Reducer DEBUG] START_RESEARCH - resetting interactionLog to []');
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
        // Update status to 'complete' if we were in 'loading' state (reference format fetch)
        streamStatus: state.streamStatus === 'loading' ? 'complete' : state.streamStatus,
        // If animate flag is set, mark this section as streaming to trigger typewriter effect
        currentStreamingSection: action.animate ? action.sectionId : state.currentStreamingSection,
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

    case ACTIONS.CLEAR_STREAMING_SECTION:
      return {
        ...state,
        currentStreamingSection: null,
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

    case ACTIONS.LOAD_SAVED_REPORT:
      // Load a report from saved history
      // For reference format: streamedContent may be empty initially (fetch on-demand)
      // For legacy format: streamedContent contains full content
      return {
        ...initialState,
        selectedTicker: action.ticker,
        // If streamedContent is empty, set status to 'loading' to indicate sections need fetching
        streamStatus: Object.keys(action.streamedContent || {}).length > 0 ? 'complete' : 'loading',
        isStreaming: false,
        reportMeta: action.reportMeta,
        streamedContent: action.streamedContent || {},
        // Restore saved activeSectionId, or fall back to first ToC item
        activeSectionId: action.activeSectionId || action.reportMeta?.toc?.[0]?.section_id || '01_executive_summary',
        followUpMessages: action.followUpMessages || [],
        // Restore interaction log for chronological ordering
        interactionLog: action.interactionLog || [],
      };

    // Follow-up chat actions
    case ACTIONS.FOLLOWUP_USER_MESSAGE:
      return {
        ...state,
        followUpMessages: [
          ...state.followUpMessages,
          {
            id: action.messageId,
            type: 'user',
            content: action.content,
            isStreaming: false,
            timestamp: new Date().toISOString(),
          },
        ],
      };

    case ACTIONS.FOLLOWUP_START:
      return {
        ...state,
        isFollowUpStreaming: true,
        currentFollowUpMessageId: action.messageId,
        followUpMessages: [
          ...state.followUpMessages,
          {
            id: action.messageId,
            type: 'assistant',
            content: '',
            isStreaming: true,
            timestamp: new Date().toISOString(),
          },
        ],
      };

    case ACTIONS.FOLLOWUP_CHUNK:
      return {
        ...state,
        followUpMessages: state.followUpMessages.map((msg) =>
          msg.id === action.messageId
            ? { ...msg, content: msg.content + action.text }
            : msg
        ),
      };

    case ACTIONS.FOLLOWUP_END:
      return {
        ...state,
        isFollowUpStreaming: false,
        currentFollowUpMessageId: null,
        followUpMessages: state.followUpMessages.map((msg) =>
          msg.id === action.messageId
            ? { ...msg, isStreaming: false }
            : msg
        ),
      };

    case ACTIONS.FOLLOWUP_ERROR:
      return {
        ...state,
        isFollowUpStreaming: false,
        currentFollowUpMessageId: null,
        error: action.error,
      };

    case ACTIONS.CLEAR_FOLLOWUP:
      return {
        ...state,
        followUpMessages: [],
        isFollowUpStreaming: false,
        currentFollowUpMessageId: null,
        collapsedFollowUpIds: [],
        // Keep section interactions, remove follow-up interactions
        interactionLog: state.interactionLog.filter(entry => entry.type === 'section'),
      };

    case ACTIONS.TOGGLE_FOLLOWUP_COLLAPSE:
      return {
        ...state,
        collapsedFollowUpIds: state.collapsedFollowUpIds.includes(action.messageId)
          ? state.collapsedFollowUpIds.filter(id => id !== action.messageId)
          : [...state.collapsedFollowUpIds, action.messageId],
      };

    // Interaction timeline actions
    case ACTIONS.LOG_SECTION_INTERACTION:
      // DEBUG: Log when this action is received
      console.log('[Reducer DEBUG] LOG_SECTION_INTERACTION:', {
        sectionId: action.sectionId,
        currentInteractionLog: state.interactionLog.map(e => e.id),
        isDuplicate: state.interactionLog.some(entry => entry.type === 'section' && entry.id === action.sectionId),
      });
      // Don't log duplicate section interactions
      if (state.interactionLog.some(entry => entry.type === 'section' && entry.id === action.sectionId)) {
        console.log('[Reducer DEBUG] Skipping duplicate');
        return state;
      }
      console.log('[Reducer DEBUG] Adding to interactionLog');
      return {
        ...state,
        interactionLog: [
          ...state.interactionLog,
          { type: 'section', id: action.sectionId, timestamp: action.timestamp || new Date().toISOString() },
        ],
      };

    case ACTIONS.LOG_FOLLOWUP_INTERACTION:
      return {
        ...state,
        interactionLog: [
          ...state.interactionLog,
          { type: 'followup', id: action.messageId, timestamp: action.timestamp || new Date().toISOString() },
        ],
      };

    case ACTIONS.SET_INTERACTION_LOG:
      return {
        ...state,
        interactionLog: action.interactionLog || [],
      };

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
  const followUpAbortRef = useRef(null);

  // Abort current stream
  const abortStream = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  }, []);

  // Abort follow-up stream
  const abortFollowUp = useCallback(() => {
    if (followUpAbortRef.current) {
      followUpAbortRef.current.abort();
      followUpAbortRef.current = null;
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
      let hasError = false;  // Track if error event was received during stream

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
              // Track error events to prevent overwriting with 'complete'
              if (currentEvent === 'error') {
                hasError = true;
              }
              handleSSEEvent(currentEvent, data, dispatch);
            } catch (e) {
              console.warn('Failed to parse SSE data:', e);
            }
          }
        }
      }

      // Only dispatch complete if no error occurred during stream
      if (!hasError) {
        dispatch({ type: ACTIONS.SET_STATUS, status: 'complete' });
      }
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
  // Options: { animate: true } - triggers typewriter effect (default for ToC clicks)
  //          { animate: false } - instant display (for bulk restore)
  const fetchSection = useCallback(async (ticker, sectionId, token = null, options = {}) => {
    const { animate = true } = options;

    try {
      const url = `${API_BASE}/research/report/${ticker.toUpperCase()}/section/${sectionId}`;
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};

      const response = await fetch(url, { headers });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Set section content - with animate flag to trigger typewriter effect
      dispatch({
        type: ACTIONS.SET_SECTION,
        sectionId: data.section_id,
        title: data.title,
        content: data.content,
        part: data.part,
        icon: data.icon,
        word_count: data.word_count,
        animate: animate,  // When true, sets currentStreamingSection for typewriter
      });

      // Clear streaming state after animation has time to start
      if (animate) {
        setTimeout(() => {
          dispatch({ type: ACTIONS.CLEAR_STREAMING_SECTION });
        }, 100);
      }

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
    abortFollowUp();
    dispatch({ type: ACTIONS.RESET });
  }, [abortStream, abortFollowUp]);

  // Clear follow-up messages
  const clearFollowUp = useCallback(() => {
    abortFollowUp();
    dispatch({ type: ACTIONS.CLEAR_FOLLOWUP });
  }, [abortFollowUp]);

  // Toggle collapse state for a follow-up message
  const toggleFollowUpCollapse = useCallback((messageId) => {
    dispatch({ type: ACTIONS.TOGGLE_FOLLOWUP_COLLAPSE, messageId });
  }, []);

  // Load a saved report from conversation history (no streaming)
  const loadSavedReport = useCallback((savedData) => {
    // Abort any existing streams
    abortStream();
    abortFollowUp();

    dispatch({
      type: ACTIONS.LOAD_SAVED_REPORT,
      ticker: savedData.ticker,
      reportMeta: savedData.reportMeta,
      streamedContent: savedData.streamedContent,
      activeSectionId: savedData.activeSectionId,  // Restore ToC highlight state
      followUpMessages: savedData.followUpMessages || [],
      interactionLog: savedData.interactionLog || [],  // Restore interaction timeline
    });
  }, [abortStream, abortFollowUp]);

  // Log a section interaction to the timeline
  const logSectionInteraction = useCallback((sectionId) => {
    dispatch({
      type: ACTIONS.LOG_SECTION_INTERACTION,
      sectionId,
      timestamp: new Date().toISOString(),
    });
  }, []);

  // Log a follow-up interaction to the timeline
  const logFollowUpInteraction = useCallback((messageId) => {
    dispatch({
      type: ACTIONS.LOG_FOLLOWUP_INTERACTION,
      messageId,
      timestamp: new Date().toISOString(),
    });
  }, []);

  // Set interaction log directly (for restoring from saved state)
  const setInteractionLog = useCallback((interactionLog) => {
    dispatch({ type: ACTIONS.SET_INTERACTION_LOG, interactionLog });
  }, []);

  // Send follow-up question
  // conversationId is required for backend to save messages to DynamoDB
  const sendFollowUp = useCallback(async (question, token = null, conversationId = null) => {
    // DEBUG: Log state before validation
    console.log('[FollowUp DEBUG] State before request:', {
      selectedTicker: state.selectedTicker,
      activeSectionId: state.activeSectionId,
      isFollowUpStreaming: state.isFollowUpStreaming,
      question: question,
      questionLength: question?.length,
      questionType: typeof question,
      conversationId: conversationId,
    });

    if (!state.selectedTicker || state.isFollowUpStreaming) {
      console.warn('[FollowUp DEBUG] Early return - validation failed:', {
        selectedTicker: state.selectedTicker,
        isFollowUpStreaming: state.isFollowUpStreaming,
      });
      return;
    }

    // Add user message immediately
    const userMessageId = `user-${Date.now()}`;
    dispatch({
      type: ACTIONS.FOLLOWUP_USER_MESSAGE,
      messageId: userMessageId,
      content: question,
    });
    // Log to interaction timeline
    dispatch({
      type: ACTIONS.LOG_FOLLOWUP_INTERACTION,
      messageId: userMessageId,
      timestamp: new Date().toISOString(),
    });

    // Abort any existing follow-up stream
    abortFollowUp();
    followUpAbortRef.current = new AbortController();

    // Build request body
    // session_id is required by backend to save messages to the correct conversation
    const requestBody = {
      ticker: state.selectedTicker,
      question: question,
      section_id: state.activeSectionId,
      session_id: conversationId,  // Maps to conversation_id in DynamoDB
    };

    // DEBUG: Log the exact request being sent
    console.log('[FollowUp DEBUG] Request details:', {
      url: `${API_BASE}/research/followup`,
      method: 'POST',
      body: requestBody,
      bodyStringified: JSON.stringify(requestBody),
    });

    try {
      const response = await fetch(`${API_BASE}/research/followup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(requestBody),
        signal: followUpAbortRef.current.signal,
      });

      // DEBUG: Log response status
      console.log('[FollowUp DEBUG] Response received:', {
        status: response.status,
        statusText: response.statusText,
        ok: response.ok,
        headers: Object.fromEntries(response.headers.entries()),
      });

      if (!response.ok) {
        // DEBUG: Try to get error details from response body
        let errorBody = null;
        try {
          errorBody = await response.clone().text();
          console.error('[FollowUp DEBUG] Error response body:', errorBody);
        } catch (e) {
          console.error('[FollowUp DEBUG] Could not read error body:', e);
        }
        throw new Error(`HTTP ${response.status}: ${response.statusText}${errorBody ? ` - ${errorBody}` : ''}`);
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
              console.warn('Failed to parse follow-up SSE data:', e);
            }
          }
        }
      }
    } catch (error) {
      if (error.name === 'AbortError') return;
      console.error('Follow-up error:', error);
      dispatch({ type: ACTIONS.FOLLOWUP_ERROR, error: error.message });
    }
  }, [state.selectedTicker, state.activeSectionId, state.isFollowUpStreaming, abortFollowUp]);

  const value = {
    ...state,
    startResearch,
    abortStream,
    fetchSection,
    setActiveSection,
    reset,
    loadSavedReport,  // Load report from history without streaming
    // Follow-up methods
    sendFollowUp,
    clearFollowUp,
    abortFollowUp,
    toggleFollowUpCollapse,
    // Interaction timeline methods
    logSectionInteraction,
    logFollowUpInteraction,
    setInteractionLog,
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
      // StreamingIndicator tracks progress via completed sections
      break;

    // Follow-up chat events
    case 'followup_start':
      dispatch({
        type: ACTIONS.FOLLOWUP_START,
        messageId: data.message_id,
      });
      // Log assistant response to interaction timeline
      dispatch({
        type: ACTIONS.LOG_FOLLOWUP_INTERACTION,
        messageId: data.message_id,
        timestamp: new Date().toISOString(),
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
      console.log('[ResearchContext] Received followup_end event:', data.message_id);
      dispatch({
        type: ACTIONS.FOLLOWUP_END,
        messageId: data.message_id,
      });
      break;

    default:
      console.warn('Unknown SSE event:', eventType, data);
  }
}

export default ResearchContext;
