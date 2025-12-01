import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Send, Loader2, MessageCircle } from 'lucide-react';

/**
 * FollowUpChat - Chat interface for follow-up questions after analysis
 *
 * Features:
 * - Uses same sessionId to maintain conversation context
 * - Streaming responses from Bedrock agent
 * - Chat history display
 * - Example question suggestions
 */
const FollowUpChat = ({
  sessionId,
  agentType,
  ticker,
  apiUrl
}) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  // Example questions based on agent type
  const exampleQuestions = {
    debt: [
      "Why is rising debt a concern here?",
      "What would improve the debt rating?",
      "How does this compare to industry peers?"
    ],
    cashflow: [
      "Is the shareholder return sustainable?",
      "Why is FCF declining?",
      "What's driving the capex increase?"
    ],
    growth: [
      "Why is growth decelerating?",
      "What would accelerate growth?",
      "Are the margins sustainable?"
    ]
  };

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input when expanded
  useEffect(() => {
    if (isExpanded) {
      inputRef.current?.focus();
    }
  }, [isExpanded]);

  const handleSubmit = async (e, questionOverride = null) => {
    e?.preventDefault();
    const question = questionOverride || input.trim();
    if (!question || isLoading) return;

    // Add user message
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setInput('');
    setIsLoading(true);
    setIsExpanded(true);

    // Add placeholder for assistant response
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    try {
      const followUpUrl = apiUrl?.replace('/analyze', '/analyze/followup') ||
        import.meta.env.VITE_FOLLOWUP_API_URL;

      if (!followUpUrl) {
        // Mock response if no API configured
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: 'assistant',
            content: `*Follow-up API not configured.*\n\nYou asked about ${ticker}'s ${agentType} analysis: "${question}"`,
            isStreaming: false
          };
          return updated;
        });
        setIsLoading(false);
        return;
      }

      const response = await fetch(followUpUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          session_id: sessionId,
          agent_type: agentType,
          ticker
        })
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      // Handle SSE streaming
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullResponse = '';

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

              if (data.type === 'chunk' && data.text) {
                fullResponse += data.text;
                // Update the last message with accumulated text
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: 'assistant',
                    content: fullResponse,
                    isStreaming: true
                  };
                  return updated;
                });
              }

              if (data.type === 'complete') {
                setMessages(prev => {
                  const updated = [...prev];
                  updated[updated.length - 1] = {
                    role: 'assistant',
                    content: fullResponse,
                    isStreaming: false
                  };
                  return updated;
                });
              }

              if (data.type === 'error') {
                throw new Error(data.message);
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (err) {
      console.error('Follow-up error:', err);
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: 'assistant',
          content: `*Error: ${err.message}*`,
          isStreaming: false
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleExampleClick = (question) => {
    handleSubmit(null, question);
  };

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
      {/* Collapsed state - just show prompt */}
      {!isExpanded && messages.length === 0 && (
        <div className="px-4 py-3">
          <div className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 mb-2">
            <MessageCircle size={16} />
            <span>Ask follow-up questions about this analysis</span>
          </div>

          {/* Example questions */}
          <div className="flex flex-wrap gap-2">
            {exampleQuestions[agentType]?.map((q, idx) => (
              <button
                key={idx}
                onClick={() => handleExampleClick(q)}
                className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-400 bg-white dark:bg-gray-800 rounded-full border border-gray-200 dark:border-gray-700 hover:border-blue-500 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Expanded state - show messages and input */}
      <AnimatePresence>
        {(isExpanded || messages.length > 0) && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            {/* Messages */}
            {messages.length > 0 && (
              <div className="max-h-64 overflow-y-auto px-4 py-3 space-y-3">
                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[80%] px-3 py-2 rounded-lg text-sm ${
                        msg.role === 'user'
                          ? 'bg-blue-500 text-white'
                          : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700'
                      }`}
                    >
                      {msg.content}
                      {msg.isStreaming && (
                        <motion.span
                          className="inline-block w-1.5 h-4 bg-blue-500 ml-1 align-middle"
                          animate={{ opacity: [1, 0, 1] }}
                          transition={{ repeat: Infinity, duration: 0.8 }}
                        />
                      )}
                    </div>
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}

            {/* Input form */}
            <form onSubmit={handleSubmit} className="px-4 py-3 border-t border-gray-200 dark:border-gray-700">
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask a follow-up question..."
                  disabled={isLoading}
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={isLoading || !input.trim()}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? (
                    <Loader2 size={18} className="animate-spin" />
                  ) : (
                    <Send size={18} />
                  )}
                </button>
              </div>
            </form>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default FollowUpChat;
