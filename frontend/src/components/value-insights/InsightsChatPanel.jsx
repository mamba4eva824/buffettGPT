import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../../auth.jsx';

const FOLLOWUP_URL = import.meta.env.VITE_ANALYSIS_FOLLOWUP_URL || '';

const SUGGESTED_QUESTIONS = {
  dashboard: [
    "What are the biggest strengths of this company?",
    "What risks should I watch out for?",
    "How does this compare to its sector peers?",
  ],
  growth: [
    "Is revenue growth accelerating or decelerating?",
    "What's driving top-line growth?",
    "How sustainable is the current growth rate?",
  ],
  profitability: [
    "Are margins expanding or contracting?",
    "How does operating efficiency compare to peers?",
    "What's the trend in return on equity?",
  ],
  moat: [
    "What is this company's competitive advantage?",
    "How durable is the pricing power?",
    "Is the moat widening or narrowing?",
  ],
  valuation: [
    "Is this stock undervalued or overvalued?",
    "What's a fair intrinsic value estimate?",
    "How does the P/E compare to historical averages?",
  ],
  earnings_performance: [
    "How often does this company beat earnings?",
    "What's the average earnings surprise?",
    "How does the stock react after earnings?",
  ],
  cashflow: [
    "Is free cash flow growing consistently?",
    "How much of earnings convert to cash?",
    "What's the capex trend?",
  ],
  debt: [
    "Is the debt level manageable?",
    "How does leverage compare to peers?",
    "Can the company comfortably service its debt?",
  ],
  earnings_quality: [
    "How much stock-based compensation dilutes earnings?",
    "Is cash earnings quality improving?",
    "Are GAAP earnings overstating real profitability?",
  ],
  triggers: [
    "What conditions would trigger a buy?",
    "What are the key sell signals?",
    "What metrics should I monitor going forward?",
  ],
};

function generateSessionId() {
  return 'vi-' + crypto.randomUUID();
}

export default function InsightsChatPanel({ ticker, activeCategory, isOpen, onClose }) {
  const { token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const sessionIdRef = useRef(generateSessionId());
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Reset session when ticker changes
  useEffect(() => {
    setMessages([]);
    setError(null);
    sessionIdRef.current = generateSessionId();
  }, [ticker]);

  // Auto-scroll on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when panel opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const suggestions = useMemo(() => {
    return SUGGESTED_QUESTIONS[activeCategory] || SUGGESTED_QUESTIONS.dashboard;
  }, [activeCategory]);

  const categoryLabel = useMemo(() => {
    const labels = {
      dashboard: 'Overview',
      growth: 'Growth',
      profitability: 'Profitability',
      moat: 'Moat',
      valuation: 'Valuation',
      earnings_performance: 'Earnings',
      cashflow: 'Cash Flow',
      debt: 'Debt',
      earnings_quality: 'Earnings Quality',
      triggers: 'Decision Triggers',
    };
    return labels[activeCategory] || activeCategory;
  }, [activeCategory]);

  const sendMessage = useCallback(async (messageText) => {
    const trimmed = messageText.trim();
    if (!trimmed || isStreaming) return;

    if (!FOLLOWUP_URL) {
      setError('Follow-up endpoint not configured.');
      return;
    }

    setError(null);
    const userMsg = { role: 'user', content: trimmed };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsStreaming(true);

    // Add placeholder for assistant response
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    // Abort any existing stream
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    try {
      const response = await fetch(FOLLOWUP_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          question: trimmed,
          ticker: ticker,
          agent_type: activeCategory,
          session_id: sessionIdRef.current,
        }),
        signal: abortRef.current.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Parse SSE stream (same pattern as ResearchContext)
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let currentEvent = '';
      let fullText = '';

      // eslint-disable-next-line no-constant-condition
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

              if (currentEvent === 'followup_chunk' && data.text) {
                fullText += data.text;
                const captured = fullText;
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: 'assistant',
                    content: captured,
                    isStreaming: true,
                  };
                  return updated;
                });
              } else if (currentEvent === 'followup_end') {
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    ...updated[updated.length - 1],
                    isStreaming: false,
                  };
                  return updated;
                });
              } else if (currentEvent === 'error') {
                setError(data.message || 'An error occurred');
              }
            } catch {
              // skip malformed SSE data
            }
          }
        }
      }

      // Mark streaming complete
      setMessages(prev => {
        const updated = [...prev];
        if (updated.length > 0) {
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            isStreaming: false,
          };
        }
        return updated;
      });
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message);
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setIsStreaming(false);
    }
  }, [token, ticker, activeCategory, isStreaming]);

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(inputValue);
  };

  if (!isOpen) return null;

  return (
    <>
      {/* Mobile overlay backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40 lg:hidden"
        onClick={onClose}
      />

      {/* Panel */}
      <div className={`
        fixed right-0 top-0 bottom-0 z-50 w-[350px] max-w-[90vw]
        lg:relative lg:z-auto lg:w-[350px] lg:shrink-0
        flex flex-col
        bg-sand-50 dark:bg-warm-950
        border-l border-sand-200 dark:border-warm-800
      `}>
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-4 py-3 border-b border-sand-200 dark:border-warm-800">
          <div className="flex items-center gap-2 min-w-0">
            <span className="material-symbols-outlined text-vi-gold text-lg">chat</span>
            <span className="text-sm font-semibold text-sand-800 dark:text-warm-50 truncate">
              Ask about {categoryLabel}
            </span>
          </div>
          <button
            onClick={onClose}
            className="lg:hidden p-1 rounded hover:bg-sand-200 dark:hover:bg-warm-800 transition-colors"
          >
            <span className="material-symbols-outlined text-sand-500 dark:text-warm-400 text-lg">close</span>
          </button>
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3 min-h-0">
          {/* Empty state with suggestions */}
          {messages.length === 0 && !isStreaming && (
            <div className="flex flex-col gap-3 pt-4">
              <p className="text-xs text-sand-400 dark:text-warm-500 text-center px-2">
                Ask questions about {ticker}&apos;s {categoryLabel.toLowerCase()} metrics. The AI has access to the financial data shown in this tab.
              </p>
              <div className="flex flex-col gap-1.5 mt-2">
                {suggestions.map((q, i) => (
                  <button
                    key={i}
                    onClick={() => sendMessage(q)}
                    className="text-left px-3 py-2.5 rounded-lg border border-sand-200 dark:border-warm-700
                      text-xs text-sand-600 dark:text-warm-200
                      hover:bg-sand-100 dark:hover:bg-warm-900 hover:border-sand-300 dark:hover:border-warm-600
                      transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Message list */}
          {messages.map((msg, i) => (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`rounded-xl px-3 py-2 text-xs leading-relaxed max-w-[85%] ${
                msg.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : 'bg-sand-100 dark:bg-warm-900 text-sand-800 dark:text-warm-50'
              }`}>
                {msg.role === 'user' ? (
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                ) : msg.content ? (
                  <div className="prose prose-xs dark:prose-invert max-w-none prose-p:my-1 prose-headings:my-2 prose-ul:my-1 prose-li:my-0.5">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                    {msg.isStreaming && (
                      <span className="inline-block w-1.5 h-3.5 bg-vi-gold animate-pulse ml-0.5 align-middle" />
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 text-sand-400 dark:text-warm-500">
                    <span className="inline-block w-1.5 h-3.5 bg-vi-gold animate-pulse" />
                    Analyzing...
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Error display */}
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg px-3 py-2 text-xs text-red-700 dark:text-red-300">
              {error}
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input bar */}
        <div className="shrink-0 border-t border-sand-200 dark:border-warm-800 px-3 py-2.5">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <input
              ref={inputRef}
              type="text"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder={`Ask about ${ticker}...`}
              disabled={isStreaming}
              className="flex-1 rounded-lg border border-sand-200 dark:border-warm-700
                bg-white dark:bg-warm-900 px-3 py-2 text-xs
                text-sand-800 dark:text-warm-50
                placeholder:text-sand-400 dark:placeholder:text-warm-500
                focus:outline-none focus:ring-2 focus:ring-vi-gold/50 focus:border-vi-gold
                disabled:opacity-50 transition-all"
            />
            <button
              type="submit"
              disabled={!inputValue.trim() || isStreaming}
              className="shrink-0 rounded-lg bg-vi-gold px-3 py-2 text-xs font-semibold text-[#402d00]
                hover:bg-vi-gold/80 disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors"
            >
              {isStreaming ? '...' : 'Send'}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
