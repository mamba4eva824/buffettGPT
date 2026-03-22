import { useState, useRef, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useAuth } from '../../auth.jsx';

const MARKET_INTEL_URL = import.meta.env.VITE_MARKET_INTEL_URL || '';

const SUGGESTED_QUERIES = [
  "How is the S&P 500 doing overall?",
  "Show me the technology sector overview",
  "Top 10 companies by FCF margin",
  "Compare AAPL, MSFT, and GOOGL margins",
  "Who had the biggest earnings beats?",
  "Companies with >30% operating margin in tech",
  "Compare tech vs healthcare profitability",
  "How has NVDA's revenue growth changed over 5 years?",
];

export default function MarketIntelligence() {
  const { user, isAuthenticated, token } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);
  const abortRef = useRef(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(async (messageText) => {
    if (!messageText.trim() || isStreaming) return;
    if (!MARKET_INTEL_URL) {
      setError('Market Intelligence endpoint not configured. Set VITE_MARKET_INTEL_URL.');
      return;
    }

    setError(null);
    const userMsg = { role: 'user', content: messageText.trim() };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsStreaming(true);

    // Add placeholder for assistant response
    const assistantMsg = { role: 'assistant', content: '', isStreaming: true };
    setMessages(prev => [...prev, assistantMsg]);

    // Abort any existing stream
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    try {
      const response = await fetch(MARKET_INTEL_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: messageText.trim(),
          messages: messages
            .filter(m => m.role === 'user' || (m.role === 'assistant' && m.content))
            .map(m => ({
              role: m.role,
              content: [{ text: m.content }],
            })),
        }),
        signal: abortRef.current.signal,
      });

      if (response.status === 401) {
        setError('Please sign in to use Market Intelligence.');
        setMessages(prev => prev.slice(0, -1)); // Remove placeholder
        setIsStreaming(false);
        return;
      }

      if (response.status === 403) {
        setError('Plus subscription required for Market Intelligence.');
        setMessages(prev => prev.slice(0, -1));
        setIsStreaming(false);
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Parse SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullText = '';
      let tokenUsage = null;

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));

              if (data.type === 'chunk') {
                fullText += data.text;
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: 'assistant',
                    content: fullText,
                    isStreaming: true,
                  };
                  return updated;
                });
              } else if (data.type === 'complete') {
                tokenUsage = data.token_usage;
              } else if (data.type === 'error') {
                setError(data.message);
              }
            } catch {
              // Skip unparseable lines
            }
          }
        }
      }

      // Finalize assistant message
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: fullText,
          isStreaming: false,
          tokenUsage,
        };
        return updated;
      });
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message);
      setMessages(prev => prev.slice(0, -1));
    } finally {
      setIsStreaming(false);
    }
  }, [token, messages, isStreaming]);

  const handleSubmit = (e) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleSuggestionClick = (query) => {
    sendMessage(query);
  };

  // Not authenticated
  if (!isAuthenticated) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">&#128202;</div>
          <h2 className="text-xl font-bold text-sand-900 dark:text-warm-50 mb-2">Market Intelligence</h2>
          <p className="text-sand-500 dark:text-warm-400 mb-4">
            Sign in to access S&P 500 market analysis powered by AI.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && !isStreaming && (
          <div className="max-w-2xl mx-auto">
            <div className="text-center mb-8">
              <h2 className="text-xl font-bold text-sand-900 dark:text-warm-50 mb-2">
                Market Intelligence
              </h2>
              <p className="text-sand-500 dark:text-warm-400 text-sm">
                Ask questions about the S&P 500 — sectors, companies, rankings, trends, and earnings.
              </p>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {SUGGESTED_QUERIES.map((query, i) => (
                <button
                  key={i}
                  onClick={() => handleSuggestionClick(query)}
                  className="text-left px-4 py-3 rounded-xl border border-sand-200 dark:border-warm-700
                    text-sm text-sand-700 dark:text-warm-200
                    hover:bg-sand-50 dark:hover:bg-warm-800 hover:border-sand-300 dark:hover:border-warm-600
                    transition-colors"
                >
                  {query}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-3 max-w-3xl mx-auto ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="h-7 w-7 shrink-0 rounded-full bg-indigo-100 dark:bg-indigo-900 flex items-center justify-center text-xs">
                MI
              </div>
            )}
            <div className={`rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
              msg.role === 'user'
                ? 'bg-indigo-600 text-white max-w-[80%]'
                : 'bg-sand-50 dark:bg-warm-900 text-sand-800 dark:text-warm-50 max-w-[90%]'
            }`}>
              {msg.role === 'user' ? (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              ) : (
                <div className="prose prose-sm dark:prose-invert max-w-none prose-table:text-xs prose-th:px-2 prose-td:px-2">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                  {msg.isStreaming && (
                    <span className="inline-block w-2 h-4 bg-indigo-500 animate-pulse ml-0.5 align-middle" />
                  )}
                </div>
              )}
              {msg.tokenUsage && (
                <div className="mt-2 pt-2 border-t border-sand-200 dark:border-warm-700 text-xs text-sand-400 dark:text-warm-500">
                  Tokens: {msg.tokenUsage.input_tokens?.toLocaleString()} in / {msg.tokenUsage.output_tokens?.toLocaleString()} out
                </div>
              )}
            </div>
            {msg.role === 'user' && user?.picture && (
              <img src={user.picture} alt="" className="h-7 w-7 rounded-full shrink-0" />
            )}
          </div>
        ))}

        {error && (
          <div className="max-w-3xl mx-auto">
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
              {error}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-sand-200 dark:border-warm-700 px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the S&P 500..."
            disabled={isStreaming}
            className="flex-1 rounded-full border border-sand-300 dark:border-warm-600
              bg-white dark:bg-warm-800 px-4 py-2.5 text-sm
              text-sand-900 dark:text-warm-50
              placeholder:text-sand-400 dark:placeholder:text-warm-500
              focus:outline-none focus:ring-2 focus:ring-indigo-500
              disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="rounded-full bg-indigo-600 px-5 py-2.5 text-sm font-medium text-white
              hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors"
          >
            {isStreaming ? 'Thinking...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  );
}
