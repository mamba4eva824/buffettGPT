import { useState, useEffect, forwardRef, useRef, useCallback, useMemo } from 'react';
import { flushSync } from 'react-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { X, ChevronDown } from 'lucide-react';
import BubbleTabs from './BubbleTabs';
import StreamingText from './StreamingText';
import useVerdictParser from '../../hooks/useVerdictParser';

/**
 * AnalysisView - Main container for supervisor multi-agent analysis
 *
 * Features:
 * - Displays company ticker and consensus header
 * - BubbleTabs shows all 3 predictions as summary (not switchable tabs)
 * - Single streaming view for supervisor's unified analysis
 * - Supports pre-loaded results for viewing saved analysis from history
 *
 * API: POST {VITE_ANALYSIS_API_URL}/supervisor
 * - Body: { company, fiscal_year, conversation_id }
 * - Header: Authorization: Bearer <token>
 * - Returns SSE stream with inference events + supervisor chunks
 */
const AnalysisView = forwardRef(({
  ticker,
  fiscalYear,
  onClose,
  analysisApiUrl,
  token,
  conversationId,
  savedResults = null,  // Pre-loaded results from conversation history
  isLoadedFromHistory = false,  // If true, don't start new analysis (viewing saved)
  onSuggestionsReady    // Callback to provide suggestions to parent
}, ref) => {
  // Predictions from all 3 models (displayed as summary, not tabs)
  const [predictions, setPredictions] = useState(() => {
    if (savedResults) {
      return {
        debt: { prediction: savedResults.debt?.prediction, confidence: savedResults.debt?.confidence },
        cashflow: { prediction: savedResults.cashflow?.prediction, confidence: savedResults.cashflow?.confidence },
        growth: { prediction: savedResults.growth?.prediction, confidence: savedResults.growth?.confidence }
      };
    }
    return {
      debt: { prediction: null, confidence: null, isLoading: false },
      cashflow: { prediction: null, confidence: null, isLoading: false },
      growth: { prediction: null, confidence: null, isLoading: false }
    };
  });

  // Supervisor's unified streaming text
  const [supervisorText, setSupervisorText] = useState(() => {
    // For saved results, combine all expert texts into supervisor format
    if (savedResults) {
      const parts = [];
      if (savedResults.debt?.text) parts.push(savedResults.debt.text);
      if (savedResults.cashflow?.text) parts.push(savedResults.cashflow.text);
      if (savedResults.growth?.text) parts.push(savedResults.growth.text);
      return parts.join('\n\n---\n\n');
    }
    return '';
  });

  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [analysisComplete, setAnalysisComplete] = useState(!!savedResults);
  const [error, setError] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Track if analysis has already started (prevent duplicate runs)
  const analysisStartedRef = useRef(false);
  // Capture if component was created for viewing history (computed once at mount)
  // This prevents race conditions where props update async after mount
  const isHistoricalViewRef = useRef(!!savedResults || isLoadedFromHistory);
  const contentRef = useRef(null);
  const bottomRef = useRef(null);

  // Handle scroll to detect if user is not at the bottom
  const handleScroll = useCallback(() => {
    if (contentRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = contentRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 100;
      setShowScrollButton(!isNearBottom && analysisComplete);
    }
  }, [analysisComplete]);

  // Scroll to bottom function
  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Update state when savedResults prop changes (switching between saved conversations)
  useEffect(() => {
    if (savedResults) {
      setPredictions({
        debt: { prediction: savedResults.debt?.prediction, confidence: savedResults.debt?.confidence },
        cashflow: { prediction: savedResults.cashflow?.prediction, confidence: savedResults.cashflow?.confidence },
        growth: { prediction: savedResults.growth?.prediction, confidence: savedResults.growth?.confidence }
      });
      const parts = [];
      if (savedResults.debt?.text) parts.push(savedResults.debt.text);
      if (savedResults.cashflow?.text) parts.push(savedResults.cashflow.text);
      if (savedResults.growth?.text) parts.push(savedResults.growth.text);
      setSupervisorText(parts.join('\n\n---\n\n'));
      setAnalysisComplete(true);
    }
  }, [savedResults]);

  // Notify parent when analysis is complete (to show suggestions)
  useEffect(() => {
    if (onSuggestionsReady) {
      onSuggestionsReady(analysisComplete);
    }
  }, [analysisComplete, onSuggestionsReady]);

  // Start analysis when component mounts (only if no saved results and not loaded from history)
  useEffect(() => {
    // CRITICAL: Use the ref captured at mount time, not current prop value
    // This prevents race conditions where props update async after mount
    if (isHistoricalViewRef.current) {
      return; // This component was created for viewing history - never start analysis
    }

    // Don't start if no ticker or already started
    if (!ticker || analysisStartedRef.current) {
      return;
    }

    analysisStartedRef.current = true;
    const abortController = new AbortController();

    // Small delay to ensure all state updates from parent have settled
    // This prevents race condition when React batches state updates async
    const timeoutId = setTimeout(() => {
      startSupervisorAnalysis(abortController.signal);
    }, 50);

    // Cleanup: abort request and reset ref for StrictMode compatibility
    // The isHistoricalViewRef guard protects saved analyses from re-streaming
    return () => {
      clearTimeout(timeoutId);
      abortController.abort();
      analysisStartedRef.current = false;
    };
  }, [ticker]); // Only depend on ticker - isHistoricalViewRef is captured at mount

  const startSupervisorAnalysis = async (abortSignal) => {
    setError(null);
    setAnalysisComplete(false);
    setIsStreaming(true);
    setSupervisorText('');
    setStatusMessage('Connecting...');

    // Mark all predictions as loading
    setPredictions({
      debt: { prediction: null, confidence: null, isLoading: true },
      cashflow: { prediction: null, confidence: null, isLoading: true },
      growth: { prediction: null, confidence: null, isLoading: true }
    });

    const baseUrl = analysisApiUrl || import.meta.env.VITE_ANALYSIS_API_URL;

    if (!baseUrl) {
      setSupervisorText('*Analysis API not configured. Set VITE_ANALYSIS_API_URL.*');
      setIsStreaming(false);
      setAnalysisComplete(true);
      return;
    }

    // Build supervisor URL - append /supervisor if not already present
    let url = baseUrl;
    if (!url.endsWith('/supervisor')) {
      url = url.replace(/\/+$/, '') + '/supervisor';
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        signal: abortSignal,  // Cancel request if component unmounts or re-renders
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` })
        },
        body: JSON.stringify({
          company: ticker,
          fiscal_year: fiscalYear,
          conversation_id: conversationId
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Handle SSE streaming
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let streamComplete = false;  // Guard to stop processing after complete event

      while (true) {
        const { done, value } = await reader.read();
        if (done || streamComplete) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (streamComplete) break;  // Stop processing if complete received
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(data);
              // Check if this was the complete event
              if (data.type === 'complete') {
                streamComplete = true;
                break;
              }
            } catch (e) {
              // Ignore parse errors for incomplete data
            }
          }
        }
      }

      // Streaming completed successfully
      setIsStreaming(false);
      setAnalysisComplete(true);
      setStatusMessage('');
    } catch (err) {
      // Ignore abort errors (intentional cancellation from StrictMode or unmount)
      if (err.name === 'AbortError') {
        console.log('Analysis request was cancelled');
        return;  // Don't update state - a new request is starting
      }
      console.error('Supervisor analysis error:', err);
      setError(err.message);
      setSupervisorText(`*Error: ${err.message}*`);
      setIsStreaming(false);
      setAnalysisComplete(true);
      setStatusMessage('');
    }
  };

  const handleSSEEvent = (data) => {
    switch (data.type) {
      case 'connected':
        setStatusMessage('Connected');
        break;

      case 'status':
        setStatusMessage(data.message || '');
        break;

      case 'inference':
        // Update specific expert's prediction
        const agentType = data.agent_type;
        if (agentType && ['debt', 'cashflow', 'growth'].includes(agentType)) {
          setPredictions(prev => ({
            ...prev,
            [agentType]: {
              prediction: data.prediction,
              confidence: data.confidence,
              ciWidth: data.ci_width,
              probabilities: data.probabilities,
              isLoading: false
            }
          }));
        }
        break;

      case 'chunk':
        // Append supervisor text - use flushSync for immediate render
        if (data.agent_type === 'supervisor' || !data.agent_type) {
          flushSync(() => {
            setSupervisorText(prev => prev + (data.text || ''));
          });
        }
        break;

      case 'complete':
        // Analysis complete
        setIsStreaming(false);
        setAnalysisComplete(true);
        if (data.session_id) {
          setSessionId(data.session_id);
        }
        break;

      case 'error':
        setError(data.message);
        setSupervisorText(prev => prev + `\n\n*Error: ${data.message}*`);
        break;
    }
  };

  // Calculate consensus from 3 models
  const getConsensus = () => {
    const predictionValues = ['debt', 'cashflow', 'growth']
      .map(agent => predictions[agent]?.prediction)
      .filter(Boolean);

    if (predictionValues.length === 0) return null;

    const counts = predictionValues.reduce((acc, p) => {
      acc[p] = (acc[p] || 0) + 1;
      return acc;
    }, {});

    const consensus = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return {
      signal: consensus[0],
      agreement: `${consensus[1]}/${predictionValues.length}`
    };
  };

  const consensus = getConsensus();

  // Parse supervisor's verdict from streaming text
  const supervisorVerdict = useVerdictParser(supervisorText);

  // Determine what verdict to display in header
  // Supervisor verdict takes priority when available
  const displayVerdict = useMemo(() => {
    // Supervisor verdict takes priority
    if (supervisorVerdict) {
      return {
        signal: supervisorVerdict.signal,
        source: 'supervisor',
        label: 'Verdict'
      };
    }
    // Fall back to ML consensus while waiting
    if (consensus) {
      return {
        signal: consensus.signal,
        source: 'ml',
        label: `ML ${consensus.agreement}`
      };
    }
    return null;
  }, [supervisorVerdict, consensus]);

  // Format predictions for BubbleTabs (expects results object format)
  const resultsForTabs = {
    debt: {
      prediction: predictions.debt?.prediction,
      confidence: predictions.debt?.confidence,
      ciWidth: predictions.debt?.ciWidth,
      probabilities: predictions.debt?.probabilities,
      isStreaming: predictions.debt?.isLoading
    },
    cashflow: {
      prediction: predictions.cashflow?.prediction,
      confidence: predictions.cashflow?.confidence,
      ciWidth: predictions.cashflow?.ciWidth,
      probabilities: predictions.cashflow?.probabilities,
      isStreaming: predictions.cashflow?.isLoading
    },
    growth: {
      prediction: predictions.growth?.prediction,
      confidence: predictions.growth?.confidence,
      ciWidth: predictions.growth?.ciWidth,
      probabilities: predictions.growth?.probabilities,
      isStreaming: predictions.growth?.isLoading
    }
  };

  return (
    <div className="relative flex flex-col flex-1 min-h-0 bg-white dark:bg-slate-800 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-slate-900 dark:text-white">
            {ticker}
          </span>
          <span className="text-sm text-slate-500 dark:text-slate-400">
            FY {fiscalYear}
          </span>
          {displayVerdict && (
            <motion.div
              className={`flex items-center gap-2 px-3 py-1 rounded-full ${
                displayVerdict.source === 'supervisor'
                  ? 'bg-indigo-100 dark:bg-indigo-900/30 ring-2 ring-indigo-500/20'
                  : 'bg-slate-100 dark:bg-slate-700'
              }`}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              key={`verdict-${displayVerdict.source}-${displayVerdict.signal}`}
            >
              <span className="text-lg">
                {displayVerdict.signal === 'SELL' ? '🔴' : displayVerdict.signal === 'HOLD' ? '🟡' : '🟢'}
              </span>
              <span className={`text-sm font-medium ${
                displayVerdict.source === 'supervisor'
                  ? 'text-indigo-700 dark:text-indigo-300'
                  : 'text-slate-700 dark:text-slate-300'
              }`}>
                {displayVerdict.signal}
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                ({displayVerdict.source === 'supervisor' ? 'Supervisor' : displayVerdict.label})
              </span>
            </motion.div>
          )}
          {!displayVerdict && isStreaming && (
            <motion.div
              className="flex items-center gap-2 px-3 py-1 bg-slate-100 dark:bg-slate-700 rounded-full"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <motion.span
                className="w-2 h-2 bg-blue-500 rounded-full"
                animate={{ opacity: [1, 0.3, 1] }}
                transition={{ repeat: Infinity, duration: 1 }}
              />
              <span className="text-sm text-slate-500 dark:text-slate-400">Analyzing...</span>
            </motion.div>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 rounded-full hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      {/* Prediction Summary (BubbleTabs as read-only display) */}
      <div className="px-4 py-3">
        <BubbleTabs
          results={resultsForTabs}
          readOnly={true}
        />
      </div>

      {/* Status Message */}
      {statusMessage && isStreaming && (
        <div className="px-4 py-2 text-sm text-slate-500 dark:text-slate-400 italic text-center">
          {statusMessage}
        </div>
      )}

      {/* Supervisor Analysis Content (Single View) */}
      <div
        ref={contentRef}
        onScroll={handleScroll}
        className="relative flex-1 overflow-y-auto px-4 pb-4 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600"
      >
        <div className="mx-auto max-w-3xl">
          <StreamingText
            text={supervisorText}
            isStreaming={isStreaming}
          />
          {/* Scroll anchor at the bottom */}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Scroll to bottom button - appears when not at bottom and analysis is complete */}
      <AnimatePresence>
        {showScrollButton && (
          <motion.button
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            onClick={scrollToBottom}
            className="absolute bottom-6 left-1/2 -translate-x-1/2 p-3 rounded-full bg-slate-900/80 dark:bg-slate-100/90 text-white dark:text-slate-900 shadow-lg backdrop-blur-sm hover:bg-slate-900 dark:hover:bg-white hover:scale-110 transition-all"
            title="Scroll to bottom"
          >
            <ChevronDown className="h-5 w-5" />
          </motion.button>
        )}
      </AnimatePresence>

      {/* Error display */}
      {error && (
        <div className="px-4 py-3 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
});

export default AnalysisView;
