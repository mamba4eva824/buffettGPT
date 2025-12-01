import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, X, Loader2 } from 'lucide-react';
import BubbleTabs from './BubbleTabs';
import StreamingText from './StreamingText';
import FollowUpChat from './FollowUpChat';

/**
 * AnalysisView - Main container for ensemble analysis
 *
 * Features:
 * - Displays company ticker and consensus header
 * - BubbleTabs for switching between Debt/Cashflow/Growth experts
 * - Streaming markdown display for each expert's analysis
 * - Follow-up chat after analysis completes
 */
const AnalysisView = ({
  ticker,
  fiscalYear,
  onClose,
  analysisApiUrl
}) => {
  const [activeTab, setActiveTab] = useState('debt');
  const [results, setResults] = useState({
    debt: { isStreaming: false, text: '', prediction: null, confidence: null },
    cashflow: { isStreaming: false, text: '', prediction: null, confidence: null },
    growth: { isStreaming: false, text: '', prediction: null, confidence: null }
  });
  const [sessionIds, setSessionIds] = useState({});
  const [analysisComplete, setAnalysisComplete] = useState(false);
  const [error, setError] = useState(null);

  // Start analysis when component mounts
  useEffect(() => {
    if (ticker) {
      startAnalysis();
    }
  }, [ticker]);

  // Check if all analyses are complete
  useEffect(() => {
    const allComplete = ['debt', 'cashflow', 'growth'].every(
      agent => results[agent]?.prediction && !results[agent]?.isStreaming
    );
    if (allComplete) {
      setAnalysisComplete(true);
    }
  }, [results]);

  const startAnalysis = async () => {
    setError(null);
    setAnalysisComplete(false);

    // Start all 3 analyses in parallel
    const agentTypes = ['debt', 'cashflow', 'growth'];

    agentTypes.forEach(agentType => {
      // Mark as streaming
      setResults(prev => ({
        ...prev,
        [agentType]: { ...prev[agentType], isStreaming: true, text: '', prediction: null }
      }));

      // Start SSE connection for each agent
      analyzeWithAgent(agentType);
    });
  };

  const analyzeWithAgent = async (agentType) => {
    const url = analysisApiUrl || import.meta.env.VITE_ANALYSIS_API_URL;

    if (!url) {
      setResults(prev => ({
        ...prev,
        [agentType]: {
          ...prev[agentType],
          isStreaming: false,
          text: `## ${agentType.toUpperCase()} ANALYST\n\n*Analysis API not configured. Set VITE_ANALYSIS_API_URL.*`,
          prediction: 'HOLD',
          confidence: 0.5
        }
      }));
      return;
    }

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company: ticker,
          agent_type: agentType,
          fiscal_year: fiscalYear
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      // Handle SSE streaming
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // Parse SSE events
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(agentType, data);
            } catch (e) {
              // Ignore parse errors for incomplete data
            }
          }
        }
      }
    } catch (err) {
      console.error(`Analysis error for ${agentType}:`, err);
      setResults(prev => ({
        ...prev,
        [agentType]: {
          ...prev[agentType],
          isStreaming: false,
          text: `## ${agentType.toUpperCase()} ANALYST\n\n*Error: ${err.message}*`,
          prediction: 'HOLD',
          confidence: 0.33
        }
      }));
    }
  };

  const handleSSEEvent = (agentType, data) => {
    switch (data.type) {
      case 'inference':
        // Update prediction/confidence from model inference
        setResults(prev => ({
          ...prev,
          [agentType]: {
            ...prev[agentType],
            prediction: data.prediction,
            confidence: data.confidence,
            ciWidth: data.ci_width,
            probabilities: data.probabilities
          }
        }));
        break;

      case 'chunk':
        // Append streaming text
        setResults(prev => ({
          ...prev,
          [agentType]: {
            ...prev[agentType],
            text: prev[agentType].text + (data.text || '')
          }
        }));
        break;

      case 'complete':
        // Analysis complete
        setResults(prev => ({
          ...prev,
          [agentType]: {
            ...prev[agentType],
            isStreaming: false
          }
        }));
        // Store session ID for follow-up questions
        if (data.session_id) {
          setSessionIds(prev => ({
            ...prev,
            [agentType]: data.session_id
          }));
        }
        break;

      case 'error':
        setResults(prev => ({
          ...prev,
          [agentType]: {
            ...prev[agentType],
            isStreaming: false,
            text: prev[agentType].text + `\n\n*Error: ${data.message}*`
          }
        }));
        break;

      case 'status':
        // Could show status messages if desired
        console.log(`${agentType}: ${data.message}`);
        break;
    }
  };

  // Calculate consensus from 3 models
  const getConsensus = () => {
    const predictions = ['debt', 'cashflow', 'growth']
      .map(agent => results[agent]?.prediction)
      .filter(Boolean);

    if (predictions.length === 0) return null;

    const counts = predictions.reduce((acc, p) => {
      acc[p] = (acc[p] || 0) + 1;
      return acc;
    }, {});

    const consensus = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
    return {
      signal: consensus[0],
      agreement: `${consensus[1]}/${predictions.length}`
    };
  };

  const consensus = getConsensus();

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-gray-900 dark:text-white">
            {ticker}
          </span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            FY {fiscalYear}
          </span>
          {consensus && (
            <motion.div
              className="flex items-center gap-2 px-3 py-1 bg-gray-100 dark:bg-gray-700 rounded-full"
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
            >
              <span className="text-lg">
                {consensus.signal === 'SELL' ? '🔴' : consensus.signal === 'HOLD' ? '🟡' : '🟢'}
              </span>
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                {consensus.signal}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                ({consensus.agreement})
              </span>
            </motion.div>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
        >
          <X size={20} />
        </button>
      </div>

      {/* Bubble Tabs */}
      <div className="px-4 py-3">
        <BubbleTabs
          activeTab={activeTab}
          onTabChange={setActiveTab}
          results={results}
        />
      </div>

      {/* Analysis Content */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            <StreamingText
              text={results[activeTab]?.text || ''}
              isStreaming={results[activeTab]?.isStreaming}
            />
          </motion.div>
        </AnimatePresence>
      </div>

      {/* Follow-up Chat (shows after analysis complete) */}
      {analysisComplete && (
        <FollowUpChat
          sessionId={sessionIds[activeTab]}
          agentType={activeTab}
          ticker={ticker}
          apiUrl={analysisApiUrl}
        />
      )}

      {/* Error display */}
      {error && (
        <div className="px-4 py-3 bg-red-50 dark:bg-red-900/20 border-t border-red-200 dark:border-red-800">
          <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
        </div>
      )}
    </div>
  );
};

export default AnalysisView;
