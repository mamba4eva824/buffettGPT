import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search, Send, Settings, Loader2, Trash2, MessageSquare, Archive, FolderOpen, X, Menu, ChevronDown, LogOut, Sun, Moon, PanelLeftClose } from "lucide-react";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import AnalysisView from "./components/analysis/AnalysisView.jsx";
import StreamingText from "./components/analysis/StreamingText.jsx";
import { AuthProvider, useAuth, GoogleLoginButton } from "./auth.jsx";
import { useConversations } from "./hooks/useConversations.js";
import { ConversationList } from "./components/ConversationList.jsx";
import { loadConversationHistory, conversationsApi } from "./api/conversationsApi.js";
import { Avatar } from "./components/Avatar.jsx";
import logger from "./utils/logger.js";
import { ResearchProvider, useResearch } from "./contexts/ResearchContext.jsx";
import SectionCard from "./components/research/SectionCard.jsx";
import ResearchLayout from "./components/research/ResearchLayout.jsx";
import { useCompanySearch } from "./hooks/useCompanySearch.js";

// Research API URL for status checks
const RESEARCH_API_URL = import.meta.env.VITE_RESEARCH_API_URL || 'https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev';

/**
 * Check if a research report exists and is not expired.
 * Used when loading conversations with reference-only format.
 */
async function checkReportStatus(ticker, token = null) {
  try {
    const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
    const response = await fetch(`${RESEARCH_API_URL}/research/report/${ticker.toUpperCase()}/status`, { headers });

    if (!response.ok) {
      if (response.status === 404) {
        return { exists: false, expired: true };
      }
      throw new Error(`Status check failed: ${response.status}`);
    }

    return await response.json();
  } catch (error) {
    logger.error('Error checking report status:', error);
    return { exists: false, expired: true, error: error.message };
  }
}

// Helper to detect if content is analysis output
function isAnalysisContent(content) {
  if (!content) return false;

  // Check for structured JSON format (new supervisor analysis format)
  if (content.startsWith('{')) {
    try {
      const data = JSON.parse(content);
      if (data._type === 'supervisor_analysis') return true;
    } catch (e) {
      // Not valid JSON, continue with other checks
    }
  }

  // Check for specific analyst markers
  const hasAnalystMarkers = content.includes('## DEBT ANALYST:') ||
         content.includes('## CASHFLOW ANALYST:') ||
         content.includes('## GROWTH ANALYST:') ||
         content.includes('DEBT ANALYST:') ||
         content.includes('CASHFLOW ANALYST:') ||
         content.includes('GROWTH ANALYST:');

  if (hasAnalystMarkers) return true;

  // Check for supervisor/analysis patterns (more flexible detection)
  const hasAnalysisPatterns = (
    (content.includes('Investment') || content.includes('investment')) &&
    (content.includes('Analysis') || content.includes('analysis') ||
     content.includes('Recommendation') || content.includes('recommendation'))
  ) || (
    // Check for signal patterns like "BUY", "HOLD", "SELL" with confidence
    /\b(BUY|HOLD|SELL)\b.*\d+%/i.test(content)
  ) || (
    // Check for structured analysis sections
    content.includes('## Summary') ||
    content.includes('## Recommendation') ||
    content.includes('## Investment Thesis') ||
    content.includes('**Debt Analysis**') ||
    content.includes('**Cashflow Analysis**') ||
    content.includes('**Growth Analysis**')
  );

  return hasAnalysisPatterns;
}

// Helper to extract company/ticker from a user query
// Handles: "What's Tesla's growth?", "Analyze Apple", "AAPL", "Tell me about Microsoft"
function extractCompanyFromQuery(query) {
  if (!query) return null;
  const text = query.trim();

  // If it looks like a ticker already (1-5 uppercase letters), return as-is
  if (/^[A-Z]{1,5}$/.test(text.toUpperCase()) && text.length <= 5) {
    return text.toUpperCase();
  }

  // Common patterns for company mentions
  const patterns = [
    // "Analyze X" or "analyze X"
    /analyze\s+(.+?)(?:\s*$|\s+(?:debt|cashflow|growth|position|outlook))/i,
    // "What's X's outlook?" or "What is X's growth?"
    /what(?:'s|'s| is)\s+(.+?)(?:'s|'s)\s+(?:debt|cashflow|growth|outlook|position|analysis)/i,
    // "Tell me about X" or "Tell me about X's debt"
    /tell me about\s+(.+?)(?:'s|'s|\s+debt|\s+cashflow|\s+growth|\s*$)/i,
    // "X's debt analysis" or "X debt analysis"
    /^(.+?)(?:'s|'s)?\s+(?:debt|cashflow|growth|financial)\s*(?:analysis|outlook|position)?/i,
    // "How is X doing?" or "How's X?"
    /how(?:'s|'s| is)\s+(.+?)(?:\s+doing|\?|$)/i,
    // Simple "X" if it's 2+ words that look like a company name
    /^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)$/,
  ];

  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match && match[1]) {
      // Clean up the extracted company name
      let company = match[1].trim();
      // Remove trailing punctuation
      company = company.replace(/[?.!,]+$/, '').trim();
      // Remove possessive 's if present at end
      company = company.replace(/'s$|'s$/, '').trim();
      if (company.length > 0) {
        return company;
      }
    }
  }

  // Fallback: just return the input as-is (backend will try to normalize it)
  return text;
}

// Helper to extract ticker from analysis messages
function extractTickerFromMessages(messages) {
  // Look through user messages for company/ticker
  for (const msg of messages) {
    if (msg.type === 'user' && msg.content) {
      const content = msg.content.trim();

      // Try pattern with parentheses first: "Analyze X (debt analysis)"
      let match = content.match(/Analyze\s+(.+?)\s*\(/i);
      if (match) {
        return match[1].trim();
      }
      // Try simple "Analyze X" pattern
      match = content.match(/Analyze\s+(.+)/i);
      if (match) {
        return match[1].trim();
      }
      // Check if it's just a ticker (1-5 uppercase letters)
      if (/^[A-Z]{1,5}$/.test(content.toUpperCase()) && content.length <= 5) {
        return content.toUpperCase();
      }
      // Check if it looks like a company name (first user message in analysis conversation)
      // If we have analysis content but couldn't match patterns, use the first user message as-is
      if (content.length > 0 && content.length < 50) {
        return content;
      }
    }
  }
  return null;
}

// Helper to parse saved messages into AnalysisView results format
function parseAnalysisResults(messages) {
  const results = {
    debt: { isStreaming: false, text: '', prediction: null, confidence: null },
    cashflow: { isStreaming: false, text: '', prediction: null, confidence: null },
    growth: { isStreaming: false, text: '', prediction: null, confidence: null }
  };

  // Find assistant messages with analysis content
  for (const msg of messages) {
    if (msg.type !== 'assistant' || !msg.content) continue;

    const content = msg.content;

    // Try to parse as structured JSON (new format from supervisor analysis)
    if (content.startsWith('{')) {
      try {
        const data = JSON.parse(content);
        if (data._type === 'supervisor_analysis' && data.predictions) {
          // Map structured data to results format
          for (const [agentType, pred] of Object.entries(data.predictions)) {
            if (['debt', 'cashflow', 'growth'].includes(agentType) && pred) {
              results[agentType] = {
                isStreaming: false,
                text: data.synthesis || '',
                prediction: pred.prediction,
                confidence: pred.confidence
              };
            }
          }
          // Found structured analysis, return early
          return results;
        }
      } catch (e) {
        // Not valid JSON, fall through to marker-based parsing
      }
    }

    // Fallback: Detect which analyst type by markers (legacy format)
    let agentType = null;
    if (content.includes('DEBT ANALYST:')) {
      agentType = 'debt';
    } else if (content.includes('CASHFLOW ANALYST:')) {
      agentType = 'cashflow';
    } else if (content.includes('GROWTH ANALYST:')) {
      agentType = 'growth';
    }

    if (agentType && !results[agentType].text) {
      // Extract prediction and confidence from header
      // Pattern: "DEBT ANALYST: HOLD (33% confidence)"
      const headerMatch = content.match(/(\w+)\s+ANALYST:\s*(SELL|HOLD|BUY)\s*\((\d+)%\s*confidence\)/i);

      results[agentType] = {
        isStreaming: false,
        text: content,
        prediction: headerMatch ? headerMatch[2].toUpperCase() : 'HOLD',
        confidence: headerMatch ? parseInt(headerMatch[3]) / 100 : 0.33
      };
    }
  }

  return results;
}

// Check if messages contain analysis content
function hasAnalysisMessages(messages) {
  return messages.some(msg => msg.type === 'assistant' && isAnalysisContent(msg.content));
}

/*************************
 * Environment Configuration *
 *************************/
const ENV_CONFIG = {
  WEBSOCKET_URL: import.meta.env.VITE_WEBSOCKET_URL || "",
  REST_API_URL: import.meta.env.VITE_REST_API_URL || "",
  APP_NAME: import.meta.env.VITE_APP_NAME || "Buffett",
  ENVIRONMENT: import.meta.env.VITE_ENVIRONMENT || "development",
  ENABLE_DEBUG_LOGS: import.meta.env.VITE_ENABLE_DEBUG_LOGS === "true",
  ENABLE_DEMO_MODE: import.meta.env.VITE_ENABLE_DEMO_MODE === "true",
  DEFAULT_USER_NAME: import.meta.env.VITE_DEFAULT_USER_NAME || "guest"
};

/*************************
 * Local Storage Settings *
 *************************/
const LS_KEYS = {
  wsUrl: "chat.ai.wsUrl",
  restUrl: "chat.ai.restUrl",
  sessions: "chat.ai.sessions",
  userName: "chat.ai.userName",
  manualConfig: "chat.ai.manualConfig", // Track if user overrode defaults
  darkMode: "chat.ai.darkMode",
  dailyQueries: "chat.ai.dailyQueries",
  queryDate: "chat.ai.queryDate"
};

const getLS = (k, def = "") => {
  try { const v = localStorage.getItem(k); return v ?? def; } catch { return def; }
};
const setLS = (k, v) => { try { localStorage.setItem(k, v); } catch {} };

/*********************
 * Rate Limiting     *
 *********************/
const DAILY_QUERY_LIMIT = 10;

const getTodayString = () => new Date().toISOString().split('T')[0];

const getDailyQueryCount = () => {
  const today = getTodayString();
  const savedDate = getLS(LS_KEYS.queryDate);
  const savedCount = parseInt(getLS(LS_KEYS.dailyQueries, "0"));

  // Reset count if it's a new day
  if (savedDate !== today) {
    setLS(LS_KEYS.queryDate, today);
    setLS(LS_KEYS.dailyQueries, "0");
    return 0;
  }

  return savedCount;
};

const incrementQueryCount = () => {
  const currentCount = getDailyQueryCount();
  const newCount = currentCount + 1;
  setLS(LS_KEYS.dailyQueries, newCount.toString());
  return newCount;
};

const getRemainingQueries = () => {
  const currentCount = getDailyQueryCount();
  return Math.max(0, DAILY_QUERY_LIMIT - currentCount);
};

/*********************
 * Helper utilities   *
 *********************/
function classNames(...xs) { return xs.filter(Boolean).join(" "); }
function uid8() { return Math.random().toString(36).slice(2, 10); }
function nowIso() { return new Date().toISOString(); }

/************************
 * useWebSocket hook     *
 ************************/
function useAwsWebSocket({ wsUrl, userId, token, conversationId, fetchConversations, setIsEvaluating }) {
  const socketRef = useRef(null);
  const heartbeatIntervalRef = useRef(null);
  const idleTimeoutRef = useRef(null);
  const lastPongRef = useRef(null);
  const lastActivityRef = useRef(Date.now());
  const reconnectingRef = useRef(false); // Track reconnection state to prevent race conditions
  const [status, setStatus] = useState("disconnected");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]); // {id,type:'user'|'assistant'|'system',content,timestamp,meta}
  const [pendingAssistantId, setPendingAssistantId] = useState(null);

  // Connect
  const connect = useCallback(() => {
    if (!wsUrl) {
      logger.log('❌ No WebSocket URL provided');
      return;
    }

    // Prevent concurrent connection attempts
    if (reconnectingRef.current) {
      logger.log('⏳ Reconnection already in progress, skipping');
      return;
    }

    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) return;

    // Build URL with user_id (only for authenticated users) and token (for authentication)
    let url = wsUrl;
    const params = new URLSearchParams();

    // Only add user_id for authenticated users - anonymous users let backend generate ID
    if (userId) {
      params.append('user_id', userId);
    }

    // Add token if available (for WebSocket authorization)
    if (token) {
      params.append('token', token);
    }

    // Add conversation_id if available (to continue existing conversation)
    if (conversationId) {
      params.append('conversation_id', conversationId);
    }

    // Append parameters if any exist
    if (params.toString()) {
      url += `${wsUrl.includes("?") ? "&" : "?"}${params.toString()}`;
    }

    logger.log('🔌 Connecting to WebSocket:', url, token ? '(with auth token)' : '(no token)');

    reconnectingRef.current = true; // Set flag to prevent concurrent reconnections
    const ws = new WebSocket(url);
    socketRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      logger.log('✅ WebSocket connected');
      reconnectingRef.current = false; // Clear flag on successful connection
      setStatus("connected");
      lastActivityRef.current = Date.now();

      // Start idle timeout (5 minutes)
      const resetIdleTimeout = () => {
        lastActivityRef.current = Date.now();
        if (idleTimeoutRef.current) {
          clearTimeout(idleTimeoutRef.current);
        }
        idleTimeoutRef.current = setTimeout(() => {
          logger.log('🚫 Disconnecting due to 5 minutes of inactivity');
          // Close the WebSocket directly instead of calling disconnect
          if (socketRef.current) {
            socketRef.current.close();
          }
        }, 5 * 60 * 1000); // 5 minutes
      };
      resetIdleTimeout();

      // Store reset function for use in message handlers
      ws.resetIdleTimeout = resetIdleTimeout;

      // Start heartbeat mechanism
      lastPongRef.current = Date.now();
      heartbeatIntervalRef.current = setInterval(() => {
        if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
          // Check if we've received a pong recently (within 45 seconds)
          const timeSinceLastPong = Date.now() - lastPongRef.current;
          if (timeSinceLastPong > 45000) {
            logger.warn('⚠️ No pong received in 45s, reconnecting...');
            // Connection seems dead, close the socket
            // The useEffect hooks will handle reconnection
            if (socketRef.current) {
              socketRef.current.close();
            }
            return;
          }

          // Send ping
          logger.log('🏓 Sending ping');
          socketRef.current.send(JSON.stringify({ action: "ping" }));
        }
      }, 30000); // Send ping every 30 seconds
    };
    ws.onclose = () => {
      logger.log('🔌 WebSocket disconnected');
      reconnectingRef.current = false; // Clear reconnection flag
      setStatus("disconnected");
      socketRef.current = null;

      // Clear heartbeat and idle timeout
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
        heartbeatIntervalRef.current = null;
      }
      if (idleTimeoutRef.current) {
        clearTimeout(idleTimeoutRef.current);
        idleTimeoutRef.current = null;
      }
    };
    ws.onerror = (error) => {
      logger.error('❌ WebSocket error:', error);
      reconnectingRef.current = false; // Clear reconnection flag on error
      setStatus("error");
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data || "{}");

        // Reset idle timeout on any message
        if (ws.resetIdleTimeout) {
          ws.resetIdleTimeout();
        }
        logger.log('📨 Received WebSocket message:', data);
        if (data.type === "pong" || data.action === "pong") {
          // Update last pong timestamp
          lastPongRef.current = Date.now();
          logger.log('🏓 Received pong');
        } else if (data.type === "welcome") {
          // Use conversation_id as session_id if available, otherwise fall back to session_id
          const effectiveSessionId = data.conversation_id || data.session_id || "";
          setSessionId(effectiveSessionId);
          setMessages((m) => [
            ...m,
            { id: `sys-${uid8()}`, type: "system", content: data.message || "Welcome!", timestamp: data.timestamp || nowIso() },
          ]);
        } else if (data.type === "messageReceived" || data.action === "message_received") {
          // Message acknowledgment - could show a checkmark or "sent" indicator
          logger.log('✅ Message acknowledged by server');
        } else if (data.action === "typing") {
          // Typing indicator
          logger.log(`⌨️ ${data.is_typing ? 'Started' : 'Stopped'} typing`);
          // You could show a typing indicator in the UI here
        } else if (data.type === "chunk") {
          // live streaming chunk from backend (optional)
          // Clear evaluating state when streaming starts
          setIsEvaluating(false);
          setMessages((prevMessages) => {
            // Find existing streaming message instead of relying on stale pendingAssistantId closure
            const existingStreamingMsg = prevMessages.find(msg => msg.meta?.streaming === true);

            if (existingStreamingMsg) {
              // Append to existing streaming message
              return prevMessages.map((msg) =>
                msg.id === existingStreamingMsg.id
                  ? { ...msg, content: (msg.content || "") + (data.text || "") }
                  : msg
              );
            }

            // No existing streaming message, create one
            const id = `asst-${uid8()}`;
            setPendingAssistantId(id);
            return [
              ...prevMessages,
              { id, type: "assistant", content: data.text || "", timestamp: data.timestamp || nowIso(), meta: { streaming: true } },
            ];
          });
        } else if (data.type === "chatResponse" || data.action === "message_response") {
          // finalize assistant message - support both message formats
          const messageContent = data.message || data.content || "";
          const messageId = data.message_id || `asst-${uid8()}`;
          const processingTime = data.processing_time_ms || data.processing_time;
          
          setMessages((m) => {
            if (pendingAssistantId) {
              const finalized = m.map((msg) => (msg.id === pendingAssistantId ? { ...msg, meta: { ...msg.meta, streaming: false }, content: messageContent } : msg));
              setPendingAssistantId(null);
              return finalized;
            }
            return [
              ...m,
              {
                id: messageId,
                type: "assistant",
                content: messageContent,
                timestamp: data.timestamp || nowIso(),
                meta: { processingTime: processingTime }
              },
            ];
          });

          // Clear evaluating state when response is received
          setIsEvaluating(false);

          // Refresh conversations to update inbox ordering
          if (fetchConversations) {
            fetchConversations();
          }
        } else if (data.type === "error") {
          setMessages((m) => [ ...m, { id: `err-${uid8()}`, type: "system", content: data.message || "Error.", timestamp: data.timestamp || nowIso() } ]);
        }
      } catch (e) { /* ignore */ }
    };
  }, [wsUrl, userId, token, conversationId, pendingAssistantId, fetchConversations, setIsEvaluating]);

  const disconnect = useCallback(() => {
    setPendingAssistantId(null);
    reconnectingRef.current = false; // Clear reconnection flag

    // Clear heartbeat and idle timeout
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (idleTimeoutRef.current) {
      clearTimeout(idleTimeoutRef.current);
      idleTimeoutRef.current = null;
    }

    if (socketRef.current) {
      try {
        // Remove all event listeners before closing to prevent spurious error events
        const socket = socketRef.current;
        socket.onopen = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;

        // Close the socket
        if (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING) {
          socket.close();
        }
      } catch {}

      // Clear the reference immediately
      socketRef.current = null;
    }

    setStatus("disconnected");
  }, []);

  const sendMessage = useCallback((text, currentConversationId) => {
    if (!text?.trim()) return;

    // Reset idle timeout on user activity
    lastActivityRef.current = Date.now();

    logger.log('🚀 Sending message:', text.trim());
    logger.log('📡 WebSocket status:', socketRef.current?.readyState);
    logger.log('🔗 Connection URL:', wsUrl);
    logger.log('💬 Conversation ID:', currentConversationId || 'none');

    // Add user message immediately
    const userMsg = { id: `usr-${uid8()}`, type: "user", content: text.trim(), timestamp: nowIso() };
    setMessages((m) => [ ...m, userMsg ]);

    // If WebSocket is connected, send the message with conversation_id
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const msg = {
        action: "message",
        message: text.trim(),
        conversation_id: currentConversationId // Include conversation ID in payload
      };
      logger.log('📤 Sending WebSocket message:', msg);
      socketRef.current.send(JSON.stringify(msg));
    } else {
      logger.log('⚠️ WebSocket not connected, using demo mode');
      // Demo mode: simulate AI response after a delay
      setTimeout(() => {
        const aiMsg = {
          id: `ai-${uid8()}`,
          type: "assistant",
          content: `This is a demo response to: "${text.trim()}". Connect to your AWS WebSocket in Settings to get real Warren Buffett AI responses!`,
          timestamp: nowIso(),
          meta: { processingTime: 1500 }
        };
        setMessages((m) => [ ...m, aiMsg ]);
        // Clear evaluating state
        setIsEvaluating(false);
      }, 1500);
    }
  }, [wsUrl, setIsEvaluating]);

  // Add switchConversation function for changing conversations without reconnecting
  const switchConversation = useCallback((newConversationId) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      logger.log('📝 Switching to conversation:', newConversationId);
      socketRef.current.send(JSON.stringify({
        action: "switch_conversation",
        conversation_id: newConversationId
      }));
    }
  }, []);

  return { status, sessionId, messages, connect, disconnect, sendMessage, setMessages, switchConversation };
}


/************************
 * Message bubble        *
 ************************/
function MessageBubble({ msg, user, messageRef }) {
  const isUser = msg.type === "user";
  const isSystem = msg.type === "system";
  const isAnalysis = !isUser && !isSystem && isAnalysisContent(msg.content);

  // For analysis content, render with StreamingText for proper markdown
  if (isAnalysis) {
    return (
      <div ref={messageRef} className="w-full">
        <div className="bg-white dark:bg-slate-800 rounded-xl p-4 md:p-6 shadow-sm border border-slate-100 dark:border-slate-700">
          <StreamingText text={msg.content} isStreaming={false} />
        </div>
      </div>
    );
  }

  // For user "Analyze X" messages, show a compact pill
  if (isUser && msg.content?.startsWith('Analyze ')) {
    return (
      <div ref={messageRef} className="flex justify-end">
        <div className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-full text-sm">
          <span>📊</span>
          <span>{msg.content}</span>
        </div>
      </div>
    );
  }

  return (
    <div ref={messageRef} className={classNames("flex gap-2 md:gap-3", isUser ? "justify-end" : "justify-start") }>
      {!isUser && (
        <div className="h-7 w-7 md:h-8 md:w-8 shrink-0">
          <img
            src="/buffett-memoji.png"
            alt="Warren Buffett AI"
            className="w-full h-full rounded-full"
          />
        </div>
      )}
      <div className={classNames("max-w-[85%] md:max-w-[80%] rounded-2xl px-3 md:px-4 py-2.5 md:py-3 text-sm md:text-[15px] leading-relaxed shadow-sm", isSystem ? "bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200" : isUser ? "bg-indigo-600 text-white" : "bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-slate-100")}>
        <div className="whitespace-pre-wrap break-words">{msg.content}</div>
      </div>
      {isUser && (
        <Avatar
          src={user?.picture || ''}
          alt={user?.name || user?.email || "User"}
          size="h-7 w-7 md:h-8 md:w-8"
          className="shrink-0"
        />
      )}
    </div>
  );
}

function deriveTitle(msgs) {
  const firstUser = msgs.find((m)=>m.type==='user');
  if (!firstUser) return "New chat";
  const t = firstUser.content.replace(/\s+/g, " ").trim();
  return t.slice(0, 40) + (t.length>40?"…":"");
}

/*********************
 * Main UI component  *
 *********************/
function ChatApp() {
  // Get authentication state
  const { user, isAuthenticated, token } = useAuth();

  // Extract first name for personalized greeting
  const userFirstName = user?.name?.split(' ')[0];

  // Refs for auto-scroll functionality
  const messagesEndRef = useRef(null);
  const lastUserMessageRef = useRef(null);

  // Refs for rate limit banner timeouts (to prevent memory leaks)
  const showBannerTimeoutRef = useRef(null);
  const hideBannerTimeoutRef = useRef(null);

  // Log environment config only once on component mount
  useEffect(() => {
    logger.log('🌍 Environment Config:', ENV_CONFIG);
  }, []);
  
  // Use environment variables directly - no user override needed
  const wsUrl = ENV_CONFIG.WEBSOCKET_URL;
  const [userName, setUserName] = useState(() => {
    const saved = getLS(LS_KEYS.userName);
    return saved || `${ENV_CONFIG.DEFAULT_USER_NAME}_${uid8()}`;
  });
  
  // Use authenticated user's Google sub ID if available, otherwise let backend generate anonymous ID
  const userId = useMemo(() => {
    if (isAuthenticated && user?.id) {
      logger.log('🔑 Using authenticated user ID:', user.id);
      return user.id; // This is the Google sub ID
    }
    // For anonymous users, return null to let backend generate device fingerprint-based ID
    logger.log('👤 Anonymous user - letting backend generate user ID');
    return null;
  }, [isAuthenticated, user?.id]);

  // Local sidebar state (simple client-side sessions list for now)
  const [sessions, setSessions] = useState(() => {
    try { return JSON.parse(getLS(LS_KEYS.sessions, "[]")); } catch { return []; }
  });

  // UI state
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [selectedMode, setSelectedMode] = useState('investment-research');
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [showInvestmentResearch, setShowInvestmentResearch] = useState(false);
  const [analysisTicker, setAnalysisTicker] = useState('');
  const [savedAnalysisResults, setSavedAnalysisResults] = useState(null);  // For viewing saved analysis from history
  const [analysisComplete, setAnalysisComplete] = useState(false);  // Track when to show follow-up suggestions
  const [isLoadedFromHistory, setIsLoadedFromHistory] = useState(false);  // Prevent re-analysis when viewing saved
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const isConnecting = false; // Simplified - no connection waiting needed for analysis mode
  const [sidebarOpen, setSidebarOpen] = useState(isAuthenticated);
  const [accountDropdownOpen, setAccountDropdownOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = getLS(LS_KEYS.darkMode);
    return saved === "true";
  });
  const [showRateLimitBanner, setShowRateLimitBanner] = useState(false);
  const [remainingQueries, setRemainingQueries] = useState(() => getRemainingQueries());
  const [hasStartedQuerying, setHasStartedQuerying] = useState(false);
  const [isEvaluating, setIsEvaluating] = useState(false);

  // Research mode state - for unified research view
  const [collapsedSections, setCollapsedSections] = useState([]);
  const [visibleSections, setVisibleSections] = useState([]); // Sections to display (on-demand via ToC clicks)
  const [userExpandedSections, setUserExpandedSections] = useState(['01_executive_summary']); // Only sections user explicitly clicked (persisted)
  const [researchTocWidth, setResearchTocWidth] = useState(300);
  const researchScrollRef = useRef(null);
  const [reportExpired, setReportExpired] = useState(false);  // Track if loaded report has expired
  const [expiredReportMeta, setExpiredReportMeta] = useState(null);  // Metadata for expired report UI

  // Research context - provides streaming state and actions
  const {
    selectedTicker: researchTicker,
    activeSectionId,
    isStreaming: isResearchStreaming,
    streamStatus,
    reportMeta,
    streamedContent,
    error: researchError,
    currentStreamingSection,
    startResearch,
    abortStream,
    fetchSection,
    setActiveSection,
    reset: resetResearch,
    loadSavedReport,  // Load report from history without streaming
    // Follow-up chat
    followUpMessages,
    isFollowUpStreaming,
    sendFollowUp,
    clearFollowUp,
    collapsedFollowUpIds,
    toggleFollowUpCollapse,
    // Interaction timeline
    interactionLog,
    logSectionInteraction,
    setInteractionLog,
  } = useResearch();

  // Company search autocomplete
  const {
    results: searchResults,
    loading: isSearching,
    search: searchCompanies,
    clearResults: clearSearchResults,
  } = useCompanySearch();

  // Handle company search input change
  const handleSearchInputChange = useCallback((value) => {
    // Only search in investment-research mode and not in follow-up mode
    const isInFollowUpMode = showInvestmentResearch && reportMeta && researchTicker;
    if (selectedMode === 'investment-research' && !isInFollowUpMode) {
      searchCompanies(value);
    }
  }, [selectedMode, showInvestmentResearch, reportMeta, researchTicker, searchCompanies]);

  // Store selected ticker from autocomplete to pass to doSend
  const selectedTickerRef = useRef(null);

  // Handle company selection from autocomplete
  const handleCompanySelect = useCallback((result) => {
    // Store the ticker for doSend to use
    selectedTickerRef.current = result.ticker;
    // Set input to company name for display
    setInput(result.name);
    clearSearchResults();
  }, [clearSearchResults]);

  // Only auto-show executive summary when streaming starts
  // Other sections appear only when user clicks ToC items
  useEffect(() => {
    // DEBUG: Log every time this effect runs
    console.log('[ExecSummary Effect DEBUG] Effect triggered:', {
      currentStreamingSection,
      isResearchStreaming,
      condition1: !!currentStreamingSection,
      condition2: !!isResearchStreaming,
      isExecSummary: currentStreamingSection === '01_executive_summary',
    });

    if (currentStreamingSection && isResearchStreaming) {
      // Only auto-add executive summary - other sections require ToC click
      if (currentStreamingSection === '01_executive_summary') {
        console.log('[ExecSummary Effect DEBUG] Adding exec summary to all arrays');
        setVisibleSections(prev => {
          if (prev.includes(currentStreamingSection)) return prev;
          return [...prev, currentStreamingSection];
        });
        // IMPORTANT: Also add to userExpandedSections for persistence
        // This ensures exec summary is saved even if user only clicks other sections
        setUserExpandedSections(prev => {
          if (prev.includes(currentStreamingSection)) return prev;
          return [...prev, currentStreamingSection];
        });
        // CRITICAL FIX: Also add to interactionLog for persistence
        // Use logSectionInteraction (not setInteractionLog) because setInteractionLog doesn't support
        // functional updates - it dispatches the value directly. logSectionInteraction properly uses
        // the reducer which has built-in duplicate detection.
        console.log('[ExecSummary Effect DEBUG] Calling logSectionInteraction for exec summary');
        logSectionInteraction(currentStreamingSection);
      }
    }
  }, [currentStreamingSection, isResearchStreaming, logSectionInteraction]);

  // Toggle section collapse
  const toggleSectionCollapse = useCallback((sectionId) => {
    setCollapsedSections(prev =>
      prev.includes(sectionId)
        ? prev.filter(id => id !== sectionId)
        : [...prev, sectionId]
    );
  }, []);

  // Handle ToC section click - add section to visible list and scroll/fetch
  const handleTocSectionClick = useCallback(async (sectionId) => {
    setActiveSection(sectionId);

    // Track this as a user-initiated expansion (persists to conversation history)
    setUserExpandedSections(prev => {
      if (prev.includes(sectionId)) return prev;
      return [...prev, sectionId];
    });

    // Add to visible sections (will render as new card if not already there)
    setVisibleSections(prev => {
      if (prev.includes(sectionId)) return prev;
      return [...prev, sectionId];
    });

    // Log to interaction timeline (tracks chronological order with follow-ups)
    logSectionInteraction(sectionId);

    // Expand section if collapsed
    setCollapsedSections(prev => prev.filter(id => id !== sectionId));

    // If section already has content, scroll to it after a brief delay for DOM update
    if (streamedContent[sectionId]?.content) {
      setTimeout(() => {
        const sectionEl = document.getElementById(`section-${sectionId}`);
        if (sectionEl) {
          sectionEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      }, 100);
      return;
    }

    // Fetch section on-demand if not available
    if (!streamedContent[sectionId]?.content && !isResearchStreaming) {
      try {
        await fetchSection(researchTicker, sectionId, token);
        // Scroll after fetch completes
        setTimeout(() => {
          const sectionEl = document.getElementById(`section-${sectionId}`);
          if (sectionEl) {
            sectionEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }, 100);
      } catch (err) {
        console.error('Failed to fetch section:', err);
      }
    }
  }, [setActiveSection, streamedContent, isResearchStreaming, fetchSection, researchTicker, token, logSectionInteraction]);

  // Get ordered sections from ToC for rendering - filtered by visibility (on-demand loading)
  const orderedSections = useMemo(() => {
    if (!reportMeta?.toc || !showInvestmentResearch) return [];

    // Only show sections that are in visibleSections (maintains click order)
    return visibleSections
      .map(sectionId => {
        const tocItem = reportMeta.toc.find(t => t.section_id === sectionId);
        if (!tocItem) return null;
        return {
          ...tocItem,
          ...streamedContent[sectionId],
          section_id: sectionId,
        };
      })
      .filter(section => section && section.content); // Only show sections with content
  }, [reportMeta?.toc, streamedContent, visibleSections, showInvestmentResearch]);

  // Build interleaved timeline from interaction log (sections and follow-ups in chronological order)
  const interactionTimeline = useMemo(() => {
    // DEBUG: Log interactionLog state
    console.log('[interactionTimeline DEBUG] Computing timeline:', {
      interactionLogLength: interactionLog?.length,
      interactionLogEntries: interactionLog?.map(e => e.id),
      hasExecSummary: interactionLog?.some(e => e.id === '01_executive_summary'),
    });

    if (!showInvestmentResearch || !reportMeta?.toc) return [];

    // If no interaction log, fall back to old behavior (sections first, then follow-ups)
    if (!interactionLog || interactionLog.length === 0) {
      console.log('[interactionTimeline DEBUG] Using fallback (orderedSections)');
      return [
        ...orderedSections.map(section => ({ type: 'section', data: section })),
        ...followUpMessages.map(msg => ({ type: 'followup', data: msg })),
      ];
    }

    console.log('[interactionTimeline DEBUG] Using interactionLog path');
    // Build timeline: sections from interactionLog, then all follow-ups
    // Note: We don't match follow-ups by ID since backend generates different IDs than frontend.
    // Follow-ups are fetched directly from messages table and already sorted by timestamp.
    const sectionEntries = interactionLog
      .filter(entry => entry.type === 'section')
      .map(entry => {
        const tocItem = reportMeta.toc.find(t => t.section_id === entry.id);
        const sectionContent = streamedContent[entry.id];
        if (!tocItem || !sectionContent?.content) return null;
        return {
          type: 'section',
          data: {
            ...tocItem,
            ...sectionContent,
            section_id: entry.id,
          },
        };
      })
      .filter(Boolean);

    // Append all follow-ups (already sorted by timestamp from loading logic)
    return [
      ...sectionEntries,
      ...followUpMessages.map(msg => ({ type: 'followup', data: msg })),
    ];
  }, [showInvestmentResearch, reportMeta?.toc, interactionLog, orderedSections, followUpMessages, streamedContent]);

  // Calculate progress for streaming indicator
  const researchProgress = useMemo(() => {
    const total = reportMeta?.toc?.length || 0;
    const completed = Object.values(streamedContent).filter(s => s?.isComplete).length;
    return { current: completed, total };
  }, [reportMeta?.toc, streamedContent]);

  // Track if we've saved this research report to avoid duplicate saves
  const savedResearchRef = useRef(null);
  // Track how many sections were saved to detect new on-demand fetches
  const lastSavedSectionsRef = useRef(0);
  // Track last saved activeSectionId to detect ToC clicks
  const lastSavedActiveSectionRef = useRef(null);
  // Track which conversation the current research state belongs to (prevents cross-contamination)
  const researchStateConversationRef = useRef(null);

  // Use conversations hook for managing chat history
  const {
    conversations,
    loading: conversationsLoading,
    selectedConversation,
    setSelectedConversation,
    createConversation,
    updateConversation,
    archiveConversation,
    deleteConversation,
    fetchConversations
  } = useConversations({ token, userId: user?.id, includeArchived: isAuthenticated ? showArchived : false });

  // Reset save tracking when conversation changes
  useEffect(() => {
    lastSavedSectionsRef.current = 0;
    lastSavedActiveSectionRef.current = null;
  }, [selectedConversation?.conversation_id]);

  // Save research report reference to conversation when streaming completes OR sections/active section change
  // NOTE: We only save metadata + reference, NOT full content (stored in investment_reports_v2)
  const lastSavedInteractionLogLengthRef = useRef(0);
  useEffect(() => {
    // Only save when:
    // 1. Streaming completed (streamStatus === 'complete') OR we have loaded sections
    // 2. We have report data to save
    // 3. We have a conversation to save to
    // 4. EITHER: Initial save (savedResearchRef not set) OR sections have increased OR active section changed OR interaction log changed
    // 5. CRITICAL: Research state belongs to the current conversation (prevents cross-contamination)
    const isInitialSave = savedResearchRef.current !== selectedConversation?.conversation_id;
    const sectionsIncreased = userExpandedSections.length > lastSavedSectionsRef.current;
    const activeSectionChanged = activeSectionId && activeSectionId !== lastSavedActiveSectionRef.current;
    const interactionLogChanged = interactionLog.length > lastSavedInteractionLogLengthRef.current;

    // CRITICAL: Prevent saving stale research state to wrong conversation during switch
    // This guards against the race condition where selectedConversation changes but researchTicker
    // is still from the previous conversation's research context
    const isResearchStateForCurrentConversation = researchStateConversationRef.current === selectedConversation?.conversation_id;

    // DEBUG: Log state for ToC persistence debugging
    console.log('[ToC Save DEBUG]', {
      streamStatus,
      activeSectionId,
      lastSavedActiveSectionRef: lastSavedActiveSectionRef.current,
      activeSectionChanged,
      isInitialSave,
      sectionsIncreased,
      interactionLogChanged,
      interactionLogLength: interactionLog.length,
      hasReportMeta: !!reportMeta,
      conversationId: selectedConversation?.conversation_id,
      researchStateConversationRef: researchStateConversationRef.current,
      isResearchStateForCurrentConversation,
      researchTicker,
    });

    // Allow save when streaming is complete OR when we have loaded content (for ToC clicks after load)
    const isReadyToSave = streamStatus === 'complete' || (streamStatus === 'loading' && Object.keys(streamedContent).length > 0);

    const shouldSave = isReadyToSave &&
      showInvestmentResearch &&
      reportMeta &&
      Object.keys(streamedContent).length > 0 &&
      selectedConversation?.conversation_id &&
      token &&
      isResearchStateForCurrentConversation &&  // CRITICAL: Only save if research state belongs to this conversation
      (isInitialSave || sectionsIncreased || activeSectionChanged || interactionLogChanged);

    if (shouldSave) {
      // Mark as saved to prevent duplicate saves
      savedResearchRef.current = selectedConversation.conversation_id;
      lastSavedSectionsRef.current = userExpandedSections.length;
      lastSavedActiveSectionRef.current = activeSectionId;
      lastSavedInteractionLogLengthRef.current = interactionLog.length;

      // DEBUG: Log exactly what we're about to save
      // IMPORTANT: Always ensure executive summary is included in visible_sections
      // This handles the case where exec summary is shown by default but user only clicks other sections
      const sectionsToSave = userExpandedSections.includes('01_executive_summary')
        ? userExpandedSections
        : ['01_executive_summary', ...userExpandedSections];

      // IMPORTANT: Also ensure executive summary is in interaction_log for rendering after load
      // This is a defensive safeguard - the streaming auto-add effect should add it, but this ensures consistency
      const interactionLogToSave = interactionLog.some(e => e.type === 'section' && e.id === '01_executive_summary')
        ? interactionLog
        : [{ type: 'section', id: '01_executive_summary', timestamp: new Date().toISOString() }, ...interactionLog];

      const researchStateToSave = {
        ticker: researchTicker,
        generated_at: reportMeta?.generated_at,
        report_table: 'investment-reports-v2',
        active_section_id: activeSectionId,
        visible_sections: sectionsToSave,
        interaction_log: interactionLogToSave,  // Chronological order of sections and follow-ups (with exec summary safeguard)
        toc: reportMeta?.toc,
        ratings: reportMeta?.ratings,
        total_word_count: reportMeta?.total_word_count,
        last_updated: new Date().toISOString(),
      };
      console.log('[ToC Save DEBUG] Saving research state to API:', {
        conversationId: selectedConversation.conversation_id,
        visible_sections: researchStateToSave.visible_sections,
        visible_sections_length: researchStateToSave.visible_sections?.length,
        active_section_id: researchStateToSave.active_section_id,
        fullPayload: researchStateToSave,
      });

      // Save research state to conversation metadata (not messages table)
      // This is cleaner than creating new message records on each ToC click
      conversationsApi.updateResearchState(
        selectedConversation.conversation_id,
        researchStateToSave,
        token
      ).then(() => {
        console.log('[ToC Save DEBUG] Save successful for visible_sections:', researchStateToSave.visible_sections);
      }).catch(err => {
        logger.error('Failed to save research state to conversation metadata:', err);
        console.error('[ToC Save DEBUG] Save FAILED:', err);
        // Reset saved ref so it can retry
        savedResearchRef.current = null;
      });
    }
  }, [streamStatus, showInvestmentResearch, reportMeta, streamedContent, userExpandedSections, activeSectionId, interactionLog, selectedConversation?.conversation_id, token, researchTicker]);

  // NOTE: Removed the re-save effect for on-demand sections since we no longer store content.
  // Sections are now fetched from investment_reports_v2 on-demand when conversation loads.

  // NOTE: Follow-up messages are now saved by the backend (analysis_followup.py) as the single
  // source of truth. The frontend only fetches messages via GET request on conversation load.
  // This prevents duplicate saves and timestamp collision issues in DynamoDB.

  const { status, sessionId, messages, connect, disconnect, setMessages, switchConversation } = useAwsWebSocket({
    wsUrl,
    userId,
    token,
    conversationId: selectedConversation?.conversation_id,
    fetchConversations,
    setIsEvaluating
  });

  // Persist settings
  useEffect(() => { setLS(LS_KEYS.userName, userName); }, [userName]);

  // Dark mode toggle and persistence
  const toggleDarkMode = useCallback(() => {
    setDarkMode(prev => {
      const newValue = !prev;
      setLS(LS_KEYS.darkMode, newValue.toString());
      return newValue;
    });
  }, []);

  // Apply dark mode class to document
  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [darkMode]);

  // Cleanup rate limit banner timeouts on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
      if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);
    };
  }, []);

  // Auto-scroll behavior: center on user message when evaluating, scroll to bottom when complete
  useEffect(() => {
    // Small delay to ensure DOM is updated
    const scrollTimeout = setTimeout(() => {
      if (isEvaluating && lastUserMessageRef.current) {
        // When evaluating, scroll to center the last user message so user can see previous context
        lastUserMessageRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else if (messagesEndRef.current && !isEvaluating && messages.length > 0) {
        // When response is complete, scroll to bottom to show full response
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
      }
    }, 100);

    return () => clearTimeout(scrollTimeout);
  }, [messages, isEvaluating]);

  // Auto-open sidebar when user authenticates
  useEffect(() => {
    if (isAuthenticated) {
      setSidebarOpen(true);
    }
  }, [isAuthenticated]);

  // Auto connect when WS URL is present
  useEffect(() => {
    if (wsUrl) {
      logger.log('🔄 Auto-connecting to WebSocket...');
      connect();
    }
  }, [wsUrl, connect]);

  // Reconnect WebSocket when authentication state changes
  useEffect(() => {
    let reconnectTimeoutId = null;

    if (wsUrl && isAuthenticated && token) {
      logger.log('🔐 Reconnecting WebSocket after authentication...');
      disconnect();
      // Longer delay to ensure clean disconnection before reconnecting
      // This prevents race conditions where the old connection triggers errors
      reconnectTimeoutId = setTimeout(() => connect(), 500);
    }

    // Cleanup: cancel pending reconnection on unmount or dependency change
    return () => {
      if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId);
      }
    };
  }, [isAuthenticated, token, wsUrl, connect, disconnect]);

  // Switch conversation context when conversation changes (without reconnecting)
  useEffect(() => {
    if (wsUrl && selectedConversation && status === "connected") {
      switchConversation(selectedConversation.conversation_id);
    }
  }, [selectedConversation?.conversation_id, wsUrl, status, switchConversation]);

  // Track sessions list and update conversation if authenticated
  useEffect(() => {
    if (!sessionId) return;

    // Update local sessions for fallback
    setSessions((prev) => {
      const existing = prev.find((s) => s.id === sessionId);
      const title = deriveTitle(messages);
      const next = existing
        ? prev.map((s) => (s.id === sessionId ? { ...s, title: title || s.title, updatedAt: nowIso() } : s))
        : [{ id: sessionId, title: title || "New chat", createdAt: nowIso(), updatedAt: nowIso() }, ...prev];
      setLS(LS_KEYS.sessions, JSON.stringify(next));
      return next;
    });

    // Update conversation in backend if authenticated and has selected conversation
    if (isAuthenticated && selectedConversation && messages.length > 0) {
      const title = deriveTitle(messages);
      if (title !== selectedConversation.title) {
        updateConversation(selectedConversation.conversation_id, {
          title,
          message_count: messages.length,
          updated_at: new Date().toISOString()
        });
      }
    }
  }, [sessionId, messages, isAuthenticated, selectedConversation, updateConversation]);

  const doSend = useCallback(async (overrideText = null) => {
    const textToSend = overrideText || input;
    if (!textToSend?.trim()) return;

    // Check rate limit for unauthorized users
    if (!isAuthenticated) {
      const currentRemaining = getRemainingQueries();
      if (currentRemaining === 0) {
        setShowRateLimitBanner(true);
        return;
      }
    }

    const messageText = textToSend.trim();
    if (!overrideText) {
      setInput("");
    }

    // Get ticker from autocomplete ref if set, then clear it
    const tickerFromAutocomplete = selectedTickerRef.current;
    selectedTickerRef.current = null;

    // Create conversation if needed (for authenticated users)
    // Use different title prefix based on mode to enable proper history loading
    let newConversationId = selectedConversation?.conversation_id;
    if (isAuthenticated && !selectedConversation && messages.length === 0) {
      const modePrefix = selectedMode === 'investment-research' ? 'Research' : 'Analysis';
      const title = `${modePrefix}: ${messageText.slice(0, 40)}${messageText.length > 40 ? '...' : ''}`;
      const newConv = await createConversation(title);
      if (newConv) {
        setSelectedConversation(newConv);
        newConversationId = newConv.conversation_id;
      }
    }

    // Check if we're in follow-up mode (viewing a completed research report)
    // Use reportMeta as source of truth - it proves we have a loaded report
    // This is more robust than streamStatus which can have timing issues
    const isInFollowUpMode = showInvestmentResearch &&
                             reportMeta &&
                             researchTicker;

    if (isInFollowUpMode) {
      // Follow-up question about the current report
      // Note: Interaction logging happens inside sendFollowUp in ResearchContext
      // Pass conversation_id so backend can save messages to correct conversation
      sendFollowUp(messageText, token, selectedConversation?.conversation_id);
      if (!overrideText) {
        setInput("");
      }

      // For unauthorized users, increment query count
      if (!isAuthenticated) {
        const newCount = incrementQueryCount();
        const newRemaining = DAILY_QUERY_LIMIT - newCount;
        setRemainingQueries(newRemaining);
        setHasStartedQuerying(true);

        // Clear any existing timeouts to prevent memory leaks
        if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
        if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);

        // Only show banner after first query and with delay for animation
        showBannerTimeoutRef.current = setTimeout(() => {
          setShowRateLimitBanner(true);
        }, 500);

        // Auto-hide banner after 8 seconds
        hideBannerTimeoutRef.current = setTimeout(() => {
          setShowRateLimitBanner(false);
        }, 8000);
      }

      return;
    }

    // Use ticker from autocomplete if set, otherwise extract from text
    const extractedCompany = tickerFromAutocomplete || extractCompanyFromQuery(messageText);
    setAnalysisTicker(extractedCompany);

    // Mode-based routing: Investment Research vs Buffett (Prediction Ensemble)
    if (selectedMode === 'investment-research') {
      // Investment Research mode - uses pre-generated reports from Investment Research Lambda
      // Sections render as cards in the unified chat interface

      // Clear any previous follow-up messages when starting new research
      clearFollowUp();

      // Add user query as a message bubble first
      const userMessage = {
        id: Date.now().toString(),
        type: 'user',
        content: messageText,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, userMessage]);

      setShowInvestmentResearch(true);
      setShowAnalysis(false);
      setSavedAnalysisResults(null);
      setIsLoadedFromHistory(false);
      setCollapsedSections([]); // Reset collapsed state for new research
      setUserExpandedSections(['01_executive_summary']); // Reset user-clicked sections for new research
      setVisibleSections(['01_executive_summary']); // Auto-show executive summary
      // Track which conversation this research state belongs to (prevents cross-contamination on switch)
      researchStateConversationRef.current = newConversationId;
      lastSavedInteractionLogLengthRef.current = 1; // Start at 1 (exec summary added below)

      // Start the research stream
      startResearch(extractedCompany, token);

      // CRITICAL FIX: Add exec summary to interactionLog immediately after research starts
      // The effect-based approach (relying on currentStreamingSection changes) is unreliable
      // because React batches state updates and the effect may never see the intermediate state.
      // By calling logSectionInteraction directly, we guarantee exec summary is in interactionLog.
      logSectionInteraction('01_executive_summary');
    } else {
      // Buffett mode (default) - uses ML inference via Prediction Ensemble Lambda
      setShowAnalysis(true);
      setShowInvestmentResearch(false);
      setSavedAnalysisResults(null);
      setIsLoadedFromHistory(false);  // This is a new analysis, not loaded from history
    }

    // For unauthorized users, increment query count and show banner
    if (!isAuthenticated) {
      const newCount = incrementQueryCount();
      const newRemaining = DAILY_QUERY_LIMIT - newCount;
      setRemainingQueries(newRemaining);
      setHasStartedQuerying(true);

      // Clear any existing timeouts to prevent memory leaks
      if (showBannerTimeoutRef.current) clearTimeout(showBannerTimeoutRef.current);
      if (hideBannerTimeoutRef.current) clearTimeout(hideBannerTimeoutRef.current);

      // Only show banner after first query and with delay for animation
      showBannerTimeoutRef.current = setTimeout(() => {
        setShowRateLimitBanner(true);
      }, 500);

      // Auto-hide banner after 8 seconds
      hideBannerTimeoutRef.current = setTimeout(() => {
        setShowRateLimitBanner(false);
      }, 8000);
    }
  }, [input, isAuthenticated, selectedConversation, messages.length, createConversation, setSelectedConversation, selectedMode, startResearch, token, showInvestmentResearch, reportMeta, researchTicker, sendFollowUp, clearFollowUp]);

  const newChat = useCallback(() => {
    // Clear messages and reset analysis view state
    setMessages([]);
    setShowAnalysis(false);
    setShowInvestmentResearch(false);
    setSavedAnalysisResults(null);
    setAnalysisComplete(false);
    setAnalysisTicker('');
    setIsLoadedFromHistory(false);

    // Reset research state (includes clearing follow-up)
    resetResearch();
    setCollapsedSections([]);
    setUserExpandedSections(['01_executive_summary']);
    setVisibleSections([]);

    // Clear selection - conversation will be created in doSend when user submits a company
    setSelectedConversation(null);
    disconnect();
    setTimeout(() => connect(), 50);
  }, [disconnect, connect, setMessages, setSelectedConversation, resetResearch]);

  const removeSession = useCallback((id) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      setLS(LS_KEYS.sessions, JSON.stringify(next));
      return next;
    });
  }, []);

  // Load conversation messages when switching conversations
  const loadConversationMessages = useCallback(async (conversationId, conversationTitle = null) => {
    if (!token || !conversationId) return;

    try {
      const { conversation, messages } = await loadConversationHistory(conversationId, token);

      // DEBUG: Log raw API response to trace visible_sections persistence issue
      console.log('[ToC Load DEBUG] loadConversationHistory response:', {
        conversationId,
        conversation_metadata: conversation?.metadata,
        research_state: conversation?.metadata?.research_state,
        visible_sections_from_api: conversation?.metadata?.research_state?.visible_sections,
        messages_count: messages?.length,
      });

      // Format messages for display
      const formattedMessages = messages
        .map((m) => {
          // Prioritize timestamp_iso (UTC ISO string) from backend, then Unix timestamp
          let timestamp = m.timestamp_iso || nowIso();

          // If no timestamp_iso but we have Unix timestamp, convert it
          if (!m.timestamp_iso && m.timestamp) {
            if (typeof m.timestamp === 'number') {
              // Unix timestamp - convert to ISO string (UTC)
              timestamp = new Date(m.timestamp * 1000).toISOString();
            } else {
              // Assume it's already a string timestamp
              timestamp = m.timestamp;
            }
          }

          return {
            id: m.message_id || uid8(),
            type: m.message_type || "user",
            content: m.content || "",
            timestamp: timestamp,
            meta: {
              tokens_used: m.tokens_used,
              model: m.model,
              processingTime: m.processing_time_ms
            }
          };
        })
        .sort((a, b) => {
          // Ensure proper chronological order (oldest to newest)
          const timeA = new Date(a.timestamp).getTime();
          const timeB = new Date(b.timestamp).getTime();

          // Handle invalid timestamps - if either is NaN, maintain array order
          if (isNaN(timeA) && isNaN(timeB)) return 0;
          if (isNaN(timeA)) return 1;  // Put invalid timestamps at end
          if (isNaN(timeB)) return -1;

          return timeA - timeB;
        });

      // Check if this is a Research conversation (title starts with "Research:")
      const isResearchConversation = conversationTitle &&
        conversationTitle.toLowerCase().startsWith('research:');

      if (isResearchConversation) {
        // NEW: Check conversation metadata first for research state
        const researchState = conversation?.metadata?.research_state;
        let savedResearchData = null;

        // DEBUG: Log raw conversation object to see what's coming from API
        console.log('[ToC Load DEBUG] Raw conversation from API:', {
          conversation_id: conversation?.conversation_id,
          metadata: conversation?.metadata,
          metadata_research_state: conversation?.metadata?.research_state,
          metadata_keys: conversation?.metadata ? Object.keys(conversation.metadata) : 'no metadata',
        });

        if (researchState) {
          // Found research state in conversation metadata (new format)
          console.log('[ToC Load DEBUG] Found research state in metadata:', {
            ticker: researchState.ticker,
            active_section_id: researchState.active_section_id,
            visible_sections: researchState.visible_sections,
            visible_sections_type: typeof researchState.visible_sections,
            visible_sections_isArray: Array.isArray(researchState.visible_sections),
            visible_sections_length: researchState.visible_sections?.length,
            interaction_log: researchState.interaction_log,
          });

          // Convert metadata format to expected savedResearchData format
          savedResearchData = {
            _type: 'research_report_ref',
            ticker: researchState.ticker,
            generated_at: researchState.generated_at,
            reportMeta: {
              toc: researchState.toc,
              ratings: researchState.ratings,
              total_word_count: researchState.total_word_count,
            },
            visibleSections: researchState.visible_sections,
            activeSectionId: researchState.active_section_id,
            interactionLog: researchState.interaction_log || [],  // Restore interaction timeline
          };
        } else {
          // FALLBACK: Try to find saved research report data in the messages (legacy format)
          // Support both legacy format (research_report with full content) and reference format (research_report_ref)
          // IMPORTANT: Use the LAST (most recent) message to get the latest activeSectionId and visibleSections
          let foundCount = 0;
          for (const msg of formattedMessages) {
            if (msg.type === 'assistant' && msg.content?.startsWith('{')) {
              try {
                const data = JSON.parse(msg.content);
                if (data._type === 'research_report' || data._type === 'research_report_ref') {
                  foundCount++;
                  console.log('[ToC Load DEBUG] Found saved research message (legacy)', foundCount, 'activeSectionId:', data.activeSectionId, 'savedAt:', data.savedAt);
                  savedResearchData = data;
                  // Don't break - continue to find the most recent message
                }
              } catch (e) {
                // Not valid JSON, continue
              }
            }
          }
        }

        console.log('[ToC Load DEBUG] Final savedResearchData activeSectionId:', savedResearchData?.activeSectionId);

        // Parse follow-up messages from conversation history
        const savedFollowUpMessages = formattedMessages
          .filter(msg => {
            if (msg.content?.startsWith('{')) {
              try {
                const data = JSON.parse(msg.content);
                return data._type === 'followup_question' || data._type === 'followup_response';
              } catch (e) {
                return false;
              }
            }
            return false;
          })
          .map(msg => {
            const data = JSON.parse(msg.content);
            return {
              id: msg.id || `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
              type: data._type === 'followup_question' ? 'user' : 'assistant',
              content: data.question || data.response,
              isStreaming: false,
              timestamp: data.timestamp || msg.timestamp,
            };
          })
          // Sort by inner JSON timestamp (ensures correct Q&A order even if DB save order was wrong)
          .sort((a, b) => {
            const timeA = new Date(a.timestamp).getTime();
            const timeB = new Date(b.timestamp).getTime();
            if (isNaN(timeA) && isNaN(timeB)) return 0;
            if (isNaN(timeA)) return 1;
            if (isNaN(timeB)) return -1;
            return timeA - timeB;
          })
          // Deduplicate messages with identical content (legacy bug fix)
          .filter((msg, index, arr) => {
            // Keep only the first occurrence of each unique content
            return arr.findIndex(m => m.content === msg.content && m.type === msg.type) === index;
          });

        // Extract ticker from saved data or from title
        let ticker = savedResearchData?.ticker;
        if (!ticker) {
          const titleMatch = conversationTitle.match(/Research:\s*(.+?)(?:\.\.\.|$)/i);
          if (titleMatch) {
            ticker = titleMatch[1].trim();
          }
        }

        if (ticker) {
          // Reset analysis state
          setShowAnalysis(false);
          setSavedAnalysisResults(null);
          setAnalysisComplete(false);
          setIsLoadedFromHistory(false);
          setReportExpired(false);
          setExpiredReportMeta(null);

          // Set up research view
          setShowInvestmentResearch(true);

          // Determine format type
          const isReferenceFormat = savedResearchData?._type === 'research_report_ref';
          const isLegacyFormat = savedResearchData?._type === 'research_report' && savedResearchData?.streamedContent;

          if (isReferenceFormat) {
            // NEW FORMAT: Reference-only - fetch sections on-demand from investment_reports_v2
            // Use length check instead of || to handle empty array (which is truthy but should default)
            console.log('[ToC Load DEBUG] isReferenceFormat - computing savedVisibleSections:', {
              'savedResearchData.visibleSections': savedResearchData.visibleSections,
              'type': typeof savedResearchData.visibleSections,
              'isArray': Array.isArray(savedResearchData.visibleSections),
              'length': savedResearchData.visibleSections?.length,
              'lengthCheck': savedResearchData.visibleSections?.length > 0,
            });
            // IMPORTANT: Always ensure executive summary is included when loading
            // Start with the saved sections or default to exec summary only
            let savedVisibleSections = savedResearchData.visibleSections?.length > 0
              ? [...savedResearchData.visibleSections]
              : ['01_executive_summary'];
            // Always include exec summary if not already present
            if (!savedVisibleSections.includes('01_executive_summary')) {
              savedVisibleSections = ['01_executive_summary', ...savedVisibleSections];
            }
            console.log('[ToC Load DEBUG] Computed savedVisibleSections:', savedVisibleSections);
            const savedActiveSectionId = savedResearchData.activeSectionId || savedVisibleSections[0] || '01_executive_summary';
            // Load interaction log and ensure exec summary is included for rendering
            let savedInteractionLog = savedResearchData.interactionLog || [];
            if (savedVisibleSections.includes('01_executive_summary') &&
                !savedInteractionLog.some(e => e.type === 'section' && e.id === '01_executive_summary')) {
              // Prepend exec summary to interaction log so it renders
              savedInteractionLog = [
                { type: 'section', id: '01_executive_summary', timestamp: new Date().toISOString() },
                ...savedInteractionLog
              ];
            }

            // Check if report still exists and is not expired
            const status = await checkReportStatus(ticker, token);

            if (!status.exists || status.expired) {
              // Report has expired or doesn't exist - show expiration banner
              setReportExpired(true);
              setExpiredReportMeta({
                ticker: ticker,
                generated_at: savedResearchData.generated_at,
                ratings: savedResearchData.reportMeta?.ratings,
                toc: savedResearchData.reportMeta?.toc,
              });
              setUserExpandedSections(savedVisibleSections);
              setVisibleSections(savedVisibleSections);

              // Load metadata-only (no content to display)
              loadSavedReport({
                ticker: ticker,
                reportMeta: savedResearchData.reportMeta,
                streamedContent: {},  // Empty - report expired
                activeSectionId: savedActiveSectionId,  // Restore ToC highlight
                followUpMessages: savedFollowUpMessages,
                interactionLog: savedInteractionLog,  // Restore interaction timeline
              });
              // Track which conversation this research state belongs to (prevents cross-contamination on switch)
              researchStateConversationRef.current = conversationId;
              // Set counters to prevent re-saving loaded data
              lastSavedInteractionLogLengthRef.current = savedInteractionLog.length;
              lastSavedSectionsRef.current = savedVisibleSections.length;
            } else {
              // Report exists - load metadata and fetch sections on-demand
              console.log('[ToC Load DEBUG] Report exists - calling setUserExpandedSections and setVisibleSections with:', savedVisibleSections);
              setUserExpandedSections(savedVisibleSections);
              setVisibleSections(savedVisibleSections);
              setCollapsedSections([...savedVisibleSections]);

              // Load with metadata, empty content (will be populated by fetchSection)
              loadSavedReport({
                ticker: ticker,
                reportMeta: savedResearchData.reportMeta,
                streamedContent: {},  // Empty - fetch on-demand
                activeSectionId: savedActiveSectionId,  // Restore ToC highlight
                followUpMessages: savedFollowUpMessages,
                interactionLog: savedInteractionLog,  // Restore interaction timeline
              });
              // Track which conversation this research state belongs to (prevents cross-contamination on switch)
              researchStateConversationRef.current = conversationId;
              // Set counters to prevent re-saving loaded data
              lastSavedInteractionLogLengthRef.current = savedInteractionLog.length;
              lastSavedSectionsRef.current = savedVisibleSections.length;

              // Fetch visible sections in parallel from investment_reports_v2
              // Use animate: false for instant display when restoring saved conversations
              try {
                await Promise.all(
                  savedVisibleSections.map(sectionId => fetchSection(ticker, sectionId, token, { animate: false }))
                );
                // Scroll to restored active section after content loads
                setTimeout(() => {
                  const sectionEl = document.getElementById(`section-${savedActiveSectionId}`);
                  if (sectionEl) {
                    sectionEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }
                }, 150);
              } catch (err) {
                logger.error('Error fetching sections on-demand:', err);
                // Continue anyway - partial content is better than none
              }
            }
          } else if (isLegacyFormat) {
            // LEGACY FORMAT: Full content embedded - load directly (backward compatible)
            // Use length check instead of || to handle empty array (which is truthy but should default)
            // IMPORTANT: Always ensure executive summary is included when loading
            let savedVisibleSections = savedResearchData.visibleSections?.length > 0
              ? [...savedResearchData.visibleSections]
              : ['01_executive_summary'];
            // Always include exec summary if not already present
            if (!savedVisibleSections.includes('01_executive_summary')) {
              savedVisibleSections = ['01_executive_summary', ...savedVisibleSections];
            }
            // Legacy format may not have activeSectionId, fall back to first visible section
            const savedActiveSectionId = savedResearchData.activeSectionId || savedVisibleSections[0] || '01_executive_summary';
            // Legacy format won't have interaction log, use empty array (fallback behavior)
            // Ensure exec summary is included for rendering
            let savedInteractionLog = savedResearchData.interactionLog || [];
            if (savedVisibleSections.includes('01_executive_summary') &&
                !savedInteractionLog.some(e => e.type === 'section' && e.id === '01_executive_summary')) {
              // Prepend exec summary to interaction log so it renders
              savedInteractionLog = [
                { type: 'section', id: '01_executive_summary', timestamp: new Date().toISOString() },
                ...savedInteractionLog
              ];
            }
            setUserExpandedSections(savedVisibleSections);
            setVisibleSections(savedVisibleSections);
            setCollapsedSections([...savedVisibleSections]);

            loadSavedReport({
              ticker: ticker,
              reportMeta: savedResearchData.reportMeta,
              streamedContent: savedResearchData.streamedContent,
              activeSectionId: savedActiveSectionId,  // Restore ToC highlight
              followUpMessages: savedFollowUpMessages,
              interactionLog: savedInteractionLog,  // Restore interaction timeline (empty for legacy)
            });
            // Track which conversation this research state belongs to (prevents cross-contamination on switch)
            researchStateConversationRef.current = conversationId;
            // Set counters to prevent re-saving loaded data
            lastSavedInteractionLogLengthRef.current = savedInteractionLog.length;
            lastSavedSectionsRef.current = savedVisibleSections.length;

            // Scroll to restored active section after content renders
            setTimeout(() => {
              const sectionEl = document.getElementById(`section-${savedActiveSectionId}`);
              if (sectionEl) {
                sectionEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }
            }, 150);
          } else {
            // No saved data found, re-stream the report
            // (Fallback for older conversations before this feature)
            setUserExpandedSections(['01_executive_summary']);
            setVisibleSections(['01_executive_summary']);
            setInteractionLog([{ type: 'section', id: '01_executive_summary', timestamp: new Date().toISOString() }]);
            // Track which conversation this research state belongs to (prevents cross-contamination on switch)
            researchStateConversationRef.current = conversationId;
            lastSavedInteractionLogLengthRef.current = 1; // Reset for fresh research
            startResearch(ticker, token);
          }

          // Filter out the research report JSON messages from display
          // This includes both assistant messages (report data, followup responses)
          // AND user messages (followup questions) that are stored as JSON
          const displayMessages = formattedMessages.filter(msg => {
            if (msg.content?.startsWith('{')) {
              try {
                const data = JSON.parse(msg.content);
                // Filter out report data and follow-up messages (handled separately)
                return !['research_report', 'research_report_ref', 'followup_question', 'followup_response'].includes(data._type);
              } catch (e) {
                return true;
              }
            }
            return true;
          });
          setMessages(displayMessages);
          return;
        }
      }

      // Check if this conversation has analysis content OR title indicates analysis
      const isAnalysisConversation = hasAnalysisMessages(formattedMessages) ||
        (conversationTitle && conversationTitle.toLowerCase().startsWith('analysis:'));

      if (isAnalysisConversation) {
        // Extract ticker and parse results for AnalysisView
        let ticker = extractTickerFromMessages(formattedMessages);

        // Fallback: try to extract from conversation title (e.g., "Analysis: Apple...")
        if (!ticker && conversationTitle) {
          const titleMatch = conversationTitle.match(/Analysis:\s*(.+?)(?:\.\.\.|$)/i);
          if (titleMatch) {
            ticker = titleMatch[1].trim();
          }
        }

        const analysisResults = parseAnalysisResults(formattedMessages);

        // Check if we actually have analysis content to display
        const hasContent = analysisResults.debt?.text ||
                          analysisResults.cashflow?.text ||
                          analysisResults.growth?.text;

        // Even if we can't parse results, show analysis view if we have a ticker
        if (ticker) {
          // IMPORTANT: Order matters for preventing race conditions!
          // Set guards FIRST (isLoadedFromHistory, savedResults) before setting
          // the trigger (analysisTicker) to prevent useEffect from firing prematurely
          setIsLoadedFromHistory(true);  // 1. Guard - prevents new analysis
          setSavedAnalysisResults(hasContent ? analysisResults : null);  // 2. Results
          setAnalysisComplete(hasContent);  // 3. Completion state
          setShowInvestmentResearch(false);  // 4. Make sure research is off
          // Clear research state tracking since this is an analysis conversation, not research
          researchStateConversationRef.current = null;
          setShowAnalysis(true);  // 5. Show the view
          setAnalysisTicker(ticker);  // 6. TRIGGER - set last!
          // Don't set messages - we'll show AnalysisView instead
          setMessages([]);
          return;
        }
      }

      // Regular conversation - show messages
      setSavedAnalysisResults(null);
      setShowAnalysis(false);
      setShowInvestmentResearch(false);
      setAnalysisComplete(false);
      // Clear research state tracking since this is not a research conversation
      researchStateConversationRef.current = null;
      setMessages(formattedMessages);
    } catch (error) {
      logger.error('Error loading conversation messages:', error);
      // Don't alert on error, just log it
    }
  }, [token, setMessages, startResearch, loadSavedReport, fetchSection]);



  return (
    <div className="h-screen w-screen overflow-hidden bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100">
      {/* App shell - full width, no pane */}
      <div className="h-full">
        <div className="flex h-full">
          {/* Mobile backdrop overlay - only visible when sidebar open on mobile */}
          {isAuthenticated && sidebarOpen && (
            <div
              className="fixed inset-0 bg-black/50 z-40 md:hidden"
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Sidebar - Show for authenticated users (visible in all modes including Research) */}
          {isAuthenticated && (
            <aside className={classNames(
              "shrink-0 border-r border-slate-100 dark:border-slate-700 transition-all duration-300 ease-in-out",
              // Mobile: fixed overlay that slides in from left
              "fixed inset-y-0 left-0 z-50 bg-white dark:bg-slate-800",
              // Desktop: relative positioning (normal flow)
              "md:relative md:z-0",
              // Width and padding
              sidebarOpen ? "w-[280px] p-6 md:p-4" : "w-0 p-0 md:w-16 md:p-2",
              // Visibility
              sidebarOpen ? "block" : "hidden md:block"
            )}>
            {sidebarOpen ? (
              <>
                <div className="mb-8 md:mb-6 flex items-center justify-between">
                  <button
                    onClick={newChat}
                    className="text-xs tracking-[0.35em] text-slate-600 dark:text-slate-300 font-semibold hover:text-indigo-600 transition-colors cursor-pointer"
                    title="Start new chat"
                  >
                    {ENV_CONFIG.APP_NAME.toUpperCase()}
                  </button>
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="rounded-md p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    title="Collapse sidebar"
                  >
                    <PanelLeftClose className="h-4 w-4" />
                  </button>
                </div>
              </>
            ) : (
              <>
                {/* Collapsed sidebar content */}
                <div className="flex flex-col items-center gap-3 h-full">
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="rounded-md p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-300"
                    title="Open sidebar"
                  >
                    <Menu className="h-4 w-4" />
                  </button>
                  <button
                    onClick={newChat}
                    className="rounded-md p-2 bg-indigo-600 text-white hover:bg-indigo-700"
                    title="New Analysis"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => {
                      setSidebarOpen(true);
                      // Focus search input after sidebar opens
                      setTimeout(() => {
                        const searchInput = document.querySelector('input[placeholder="Search"]');
                        if (searchInput) searchInput.focus();
                      }, 300);
                    }}
                    className="rounded-md p-2 text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 hover:text-slate-600 dark:hover:text-slate-300"
                    title="Search chats"
                  >
                    <Search className="h-4 w-4" />
                  </button>

                  {/* Spacer to push profile to bottom */}
                  <div className="flex-1" />

                  {/* Profile picture at bottom with connection status */}
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="rounded-full hover:ring-2 hover:ring-indigo-500 transition-all"
                    title={user?.name || "Account"}
                  >
                    <div className="relative">
                      <Avatar
                        src={user?.picture || ''}
                        alt={user?.name || user?.email || 'User'}
                        size="w-8 h-8"
                      />
                      {/* Connection status dot */}
                      {status && (
                        <span className={classNames(
                          "absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-slate-800",
                          status === "connected" ? "bg-emerald-500" :
                          status === "connecting" ? "bg-amber-500 animate-pulse" :
                          "bg-slate-400"
                        )} />
                      )}
                    </div>
                  </button>
                </div>
              </>
            )}

            {sidebarOpen && (
              <div className="flex flex-col h-full pb-4">
            <div className="flex items-center gap-2">
              <button onClick={newChat} className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg hover:bg-indigo-700 hover:shadow-indigo-200 dark:hover:shadow-indigo-900/30 transition-all">
                <Plus className="h-4 w-4"/> New Analysis
              </button>
            </div>

            <div className="mt-4 h-8 flex items-center gap-2 rounded-full border border-slate-200/80 dark:border-slate-600/50 bg-slate-50/90 dark:bg-slate-700/50 backdrop-blur-sm px-3 focus-within:border-indigo-400 dark:focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/30 transition-all">
              <Search className="h-3.5 w-3.5 text-slate-400"/>
              <input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="Search" className="w-full bg-transparent text-xs outline-none placeholder:text-slate-400 dark:placeholder:text-slate-500"/>
            </div>


            <div className="mt-6 relative flex items-center">
              <div className="text-xs uppercase tracking-wide text-slate-400">
                {isAuthenticated ? 'Financial Advice' : 'Local Sessions'}
              </div>
              {isAuthenticated && (
                <button
                  onClick={() => setShowArchived(!showArchived)}
                  className={classNames(
                    "absolute right-0 rounded-md p-1 text-xs",
                    showArchived
                      ? "text-indigo-600 hover:bg-indigo-50"
                      : "text-slate-400 hover:bg-slate-50"
                  )}
                  title={showArchived ? "Show active" : "Show archived"}
                >
                  {showArchived ? <FolderOpen className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                </button>
              )}
            </div>

            <div className="mt-2 space-y-1 overflow-y-auto pr-1 pb-4 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600" style={{ maxHeight: 'calc(100vh - 280px)' }}>
              {/* Show conversation list for authenticated users */}
              {isAuthenticated ? (
                <ConversationList
                  conversations={conversations.filter(c =>
                    c.title?.toLowerCase().includes(search.toLowerCase())
                  )}
                  selectedConversation={selectedConversation}
                  onSelectConversation={async (conv) => {
                    setSelectedConversation(conv);
                    // Load messages for this conversation
                    if (conv.conversation_id) {
                      await loadConversationMessages(conv.conversation_id, conv.title);
                      // useEffect will handle WebSocket reconnection with conversation_id
                    }
                  }}
                  onUpdateConversation={updateConversation}
                  onArchiveConversation={archiveConversation}
                  onDeleteConversation={deleteConversation}
                  showArchived={showArchived}
                  loading={conversationsLoading}
                />
              ) : (
                /* Show local sessions for non-authenticated users or local tab */
                <>
                  {sessions.filter(s => s.title?.toLowerCase().includes(search.toLowerCase())).map((s) => (
                    <div key={s.id} className="group flex items-center justify-between rounded-lg px-2 py-2 hover:bg-slate-50">
                      <div className="flex min-w-0 items-center gap-2">
                        <MessageSquare className="h-4 w-4 shrink-0 text-slate-400"/>
                        <div className="min-w-0">
                          <div className="truncate text-sm text-slate-700">{s.title || s.id}</div>
                          <div className="truncate text-[11px] text-slate-400">{new Date(s.updatedAt || s.createdAt).toLocaleString()}</div>
                        </div>
                      </div>
                      <button onClick={()=>removeSession(s.id)} className="invisible ml-2 rounded-md p-1 text-slate-300 hover:bg-slate-100 hover:text-slate-600 group-hover:visible" title="Remove">
                        <Trash2 className="h-4 w-4"/>
                      </button>
                    </div>
                  ))}
                  {sessions.length === 0 && (
                    <div className="rounded-lg border border-dashed border-slate-200 p-3 text-center text-xs text-slate-500">
                      {!isAuthenticated ? "Sign in to save conversations" : "No local sessions"}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Account section at bottom of sidebar */}
            <div className="mt-auto shrink-0 mb-6">
              <AccountDropdown
                isOpen={accountDropdownOpen}
                onToggle={setAccountDropdownOpen}
                onSettingsClick={() => setSettingsOpen(true)}
                darkMode={darkMode}
                onDarkModeToggle={toggleDarkMode}
                dropdownPosition="top"
                connectionStatus={status}
              />
            </div>
              </div>
            )}
          </aside>
          )}

          {/* Main panel */}
          <main className="relative flex min-w-0 flex-1 flex-col">
            {/* Header - minimal, only for mobile menu and non-authenticated users */}
            <div className="flex items-center justify-between px-4 md:px-6 py-2">
              <div className="flex items-center gap-2 md:gap-3">
                {/* Mobile hamburger menu - only show on mobile when authenticated */}
                {isAuthenticated && (
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="md:hidden rounded-md p-2 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                    title="Open menu"
                  >
                    <Menu className="h-5 w-5" />
                  </button>
                )}
              </div>
              <div className="flex items-center gap-2">
                {!wsUrl && (
                  <div className="rounded-lg bg-amber-50 px-3 py-1 text-xs text-amber-700">Add your WebSocket URL in Settings →</div>
                )}
                {/* Account dropdown moved to sidebar - show login button for non-authenticated users */}
                {!isAuthenticated && (
                  <AccountDropdown
                    isOpen={accountDropdownOpen}
                    onToggle={setAccountDropdownOpen}
                    onSettingsClick={() => setSettingsOpen(true)}
                    darkMode={darkMode}
                    onDarkModeToggle={toggleDarkMode}
                  />
                )}
              </div>
            </div>

            {/* Dynamic Layout Based on Message State */}
            {messages.length === 0 && !showAnalysis && !showInvestmentResearch ? (
              /* CENTERED LAYOUT - No messages (landing, auth, new chat) */
              <div className="flex-1 flex flex-col items-center justify-center px-4 md:px-6 pb-24 transition-all duration-300 ease-in-out">
                <div className="text-center mb-8">
                  <div className="text-slate-400 dark:text-white text-3xl font-medium">
                    Welcome{isAuthenticated && userFirstName ? `, ${userFirstName}` : ''} to {ENV_CONFIG.APP_NAME}
                  </div>
                </div>

                <div className="w-full max-w-3xl">
                  <SearchComposer
                    input={input}
                    setInput={setInput}
                    doSend={doSend}
                    isConnecting={isConnecting}
                    selectedMode={selectedMode}
                    onModeChange={setSelectedMode}
                    searchResults={searchResults}
                    isSearching={isSearching}
                    onResultSelect={handleCompanySelect}
                    onInputChange={handleSearchInputChange}
                  />
                </div>
              </div>
            ) : (
              /* SPLIT LAYOUT - Messages exist (active conversation) */
              <>
                {/* Analysis View or Unified Messages + Research Area */}
                {showAnalysis ? (
                  <div className="flex-1 flex flex-col min-h-0 p-4">
                    <AnalysisView
                      key={`analysis-${selectedConversation?.conversation_id || 'new'}-${analysisTicker}`}
                      ticker={analysisTicker}
                      fiscalYear={new Date().getFullYear()}
                      onClose={() => {
                        setShowAnalysis(false);
                        setSavedAnalysisResults(null);
                        setAnalysisComplete(false);
                        setIsLoadedFromHistory(false);
                      }}
                      analysisApiUrl={import.meta.env.VITE_ANALYSIS_API_URL}
                      token={token}
                      conversationId={selectedConversation?.conversation_id}
                      savedResults={savedAnalysisResults}
                      isLoadedFromHistory={isLoadedFromHistory}
                      onSuggestionsReady={setAnalysisComplete}
                    />
                  </div>
                ) : showInvestmentResearch ? (
                  /* RESEARCH MODE - Uses dedicated ResearchLayout */
                  <ResearchLayout
                    ticker={researchTicker || analysisTicker}
                    reportMeta={reportMeta}
                    streamedContent={streamedContent}
                    activeSectionId={activeSectionId}
                    currentStreamingSection={currentStreamingSection}
                    isStreaming={isResearchStreaming}
                    streamStatus={streamStatus}
                    error={researchError}
                    progress={researchProgress}
                    reportExpired={reportExpired}
                    expiredReportMeta={expiredReportMeta}
                    tocWidth={researchTocWidth}
                    onSectionClick={handleTocSectionClick}
                    onClose={() => {
                      setShowInvestmentResearch(false);
                      setAnalysisTicker('');
                      resetResearch();
                      setVisibleSections([]);
                    }}
                    onRetry={() => {
                      startResearch(analysisTicker, token);
                    }}
                    onRegenerateExpired={() => {
                      setReportExpired(false);
                      setExpiredReportMeta(null);
                      startResearch(expiredReportMeta.ticker, token);
                    }}
                    onDismissExpired={() => {
                      setReportExpired(false);
                      setExpiredReportMeta(null);
                      setShowInvestmentResearch(false);
                      resetResearch();
                    }}
                    composer={
                      <>
                        {showRateLimitBanner && !isAuthenticated && hasStartedQuerying && (
                          <RateLimitBanner
                            remainingQueries={remainingQueries}
                            onClose={() => setShowRateLimitBanner(false)}
                            onSignUp={() => setAccountDropdownOpen(true)}
                            isVisible={showRateLimitBanner}
                          />
                        )}
                        <SearchComposer
                          input={input}
                          setInput={setInput}
                          doSend={doSend}
                          isConnecting={isConnecting}
                          selectedMode={selectedMode}
                          onModeChange={setSelectedMode}
                          isFollowUpMode={!!reportMeta && !!researchTicker}
                          searchResults={searchResults}
                          isSearching={isSearching}
                          onResultSelect={handleCompanySelect}
                          onInputChange={handleSearchInputChange}
                        />
                      </>
                    }
                  >
                    {/* User messages */}
                    {messages.map((m) => {
                      const userMessages = messages.filter(msg => msg.type === 'user');
                      const lastUserMsg = userMessages[userMessages.length - 1];
                      const isLastUserMessage = m.type === 'user' && m.id === lastUserMsg?.id;

                      return (
                        <MessageBubble
                          key={m.id}
                          msg={m}
                          user={user}
                          messageRef={isLastUserMessage ? lastUserMessageRef : null}
                        />
                      );
                    })}

                    {/* Interleaved timeline: sections and follow-ups in chronological order */}
                    {interactionTimeline.map((item, index) => {
                      if (item.type === 'section') {
                        const section = item.data;
                        return (
                          <div key={`section-${section.section_id}`} id={`section-${section.section_id}`} className="mx-auto w-full max-w-2xl">
                            <SectionCard
                              section={section}
                              isStreaming={currentStreamingSection === section.section_id}
                              isCollapsed={collapsedSections.includes(section.section_id)}
                              onToggleCollapse={() => toggleSectionCollapse(section.section_id)}
                            />
                          </div>
                        );
                      } else if (item.type === 'followup') {
                        const msg = item.data;
                        const isCollapsed = collapsedFollowUpIds.includes(msg.id);
                        const contentLines = msg.content.split('\n');
                        const previewLineCount = 5;
                        const hasMoreContent = contentLines.length > previewLineCount;
                        const previewContent = contentLines.slice(0, previewLineCount).join('\n');

                        // Check if this is the first followup in the timeline (show header)
                        const isFirstFollowup = interactionTimeline.slice(0, index).every(i => i.type !== 'followup');

                        return (
                          <div key={`followup-${msg.id}`} className="mx-auto w-full max-w-2xl">
                            {isFirstFollowup && (
                              <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-700">
                                <div className="text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-4 px-4">
                                  Follow-up Questions
                                </div>
                              </div>
                            )}
                            <div className="mb-4 px-4">
                              {msg.type === 'user' ? (
                                <div className="flex justify-end">
                                  <div className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 rounded-full text-sm max-w-[80%]">
                                    {msg.content}
                                  </div>
                                </div>
                              ) : (
                                <div className="flex gap-3">
                                  <div className="h-7 w-7 shrink-0">
                                    <img
                                      src="/buffett-memoji.png"
                                      alt="Assistant"
                                      className="w-full h-full rounded-full"
                                    />
                                  </div>
                                  <div className="flex-1 bg-slate-50 dark:bg-slate-700 rounded-xl p-4 text-sm prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-h2:text-lg prose-h3:text-base prose-p:text-slate-700 dark:prose-p:text-slate-300 prose-li:text-slate-700 dark:prose-li:text-slate-300 prose-strong:text-slate-900 dark:prose-strong:text-white prose-table:text-xs prose-th:bg-slate-100 dark:prose-th:bg-slate-600 prose-th:p-2 prose-td:p-2 relative">
                                    {/* Collapse/Expand button */}
                                    {!msg.isStreaming && hasMoreContent && (
                                      <button
                                        onClick={() => toggleFollowUpCollapse(msg.id)}
                                        className="absolute top-2 right-2 text-xs text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 transition-colors flex items-center gap-1 bg-slate-100 dark:bg-slate-600 px-2 py-1 rounded-md"
                                      >
                                        {isCollapsed ? (
                                          <>
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                            </svg>
                                            Expand
                                          </>
                                        ) : (
                                          <>
                                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                            </svg>
                                            Collapse
                                          </>
                                        )}
                                      </button>
                                    )}
                                    <div className={isCollapsed ? 'pr-20' : ''}>
                                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                        {isCollapsed ? previewContent : msg.content}
                                      </ReactMarkdown>
                                      {isCollapsed && hasMoreContent && (
                                        <div className="text-slate-400 dark:text-slate-500 text-xs mt-2 italic">
                                          ...content collapsed
                                        </div>
                                      )}
                                    </div>
                                    {msg.isStreaming && (
                                      <span className="inline-block w-2 h-4 bg-indigo-500 animate-pulse ml-0.5 align-middle" />
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      }
                      return null;
                    })}

                    {/* Loading state when research started but no sections yet */}
                    {interactionTimeline.length === 0 && !researchError && (isResearchStreaming || streamStatus === 'connecting') && (
                      <div className="flex items-center justify-center h-32 text-slate-400 dark:text-slate-500">
                        <p>Loading research report...</p>
                      </div>
                    )}

                    {/* Follow-up streaming indicator */}
                    {isFollowUpStreaming && followUpMessages.length === 0 && (
                      <div className="mx-auto w-full max-w-2xl mt-4 px-4">
                        <div className="flex gap-3">
                          <div className="h-7 w-7 shrink-0">
                            <img
                              src="/buffett-memoji.png"
                              alt="Assistant"
                              className="w-full h-full rounded-full"
                            />
                          </div>
                          <div className="text-slate-400 dark:text-slate-500 text-sm">
                            Thinking...
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Invisible element at the end for auto-scrolling */}
                    <div ref={messagesEndRef} />
                  </ResearchLayout>
                ) : (
                  /* REGULAR CHAT VIEW */
                  <div className="flex-1 flex min-h-0">
                    <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 transition-all duration-300 ease-in-out scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600">
                      <div className="mx-auto max-w-3xl space-y-4">
                        {/* User messages */}
                        {messages.map((m) => {
                          const userMessages = messages.filter(msg => msg.type === 'user');
                          const lastUserMsg = userMessages[userMessages.length - 1];
                          const isLastUserMessage = m.type === 'user' && m.id === lastUserMsg?.id;

                          return (
                            <MessageBubble
                              key={m.id}
                              msg={m}
                              user={user}
                              messageRef={isLastUserMessage ? lastUserMessageRef : null}
                            />
                          );
                        })}

                        {/* Evaluating indicator */}
                        {isEvaluating && (
                          <div className="flex justify-start">
                            <div className="ml-11 text-slate-400 dark:text-white text-base fade-pulse-evaluating">
                              Evaluating...
                            </div>
                          </div>
                        )}

                        {/* Invisible element at the end for auto-scrolling */}
                        <div ref={messagesEndRef} />
                      </div>
                    </div>
                  </div>
                )}

                {/* Bottom Composer - visible for regular chat (not analysis or research mode) */}
                {!showAnalysis && !showInvestmentResearch && (
                <div className="border-t border-slate-100 dark:border-slate-700 p-4 md:p-4 pb-6 md:pb-4 transition-all duration-300 ease-in-out">
                  {/* Rate Limit Banner */}
                  {showRateLimitBanner && !isAuthenticated && hasStartedQuerying && (
                    <RateLimitBanner
                      remainingQueries={remainingQueries}
                      onClose={() => setShowRateLimitBanner(false)}
                      onSignUp={() => setAccountDropdownOpen(true)}
                      isVisible={showRateLimitBanner}
                    />
                  )}
                  <SearchComposer
                    input={input}
                    setInput={setInput}
                    doSend={doSend}
                    isConnecting={isConnecting}
                    selectedMode={selectedMode}
                    onModeChange={setSelectedMode}
                    isFollowUpMode={showInvestmentResearch && !!reportMeta && !!researchTicker}
                    searchResults={searchResults}
                    isSearching={isSearching}
                    onResultSelect={handleCompanySelect}
                    onInputChange={handleSearchInputChange}
                  />
                </div>
                )}
              </>
            )}

          </main>
        </div>
      </div>


      {/* Settings Panel */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" onClick={()=>setSettingsOpen(false)}>
          <div className="absolute right-0 top-0 h-full w-full md:max-w-xl overflow-y-auto bg-white dark:bg-slate-800 shadow-xl" onClick={(e)=>e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 px-4 md:px-6 py-4">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">Settings</div>
              <button onClick={()=>setSettingsOpen(false)} className="rounded-md border border-slate-200 dark:border-slate-600 px-3 py-2 md:px-2 md:py-1 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 active:bg-slate-100 dark:active:bg-slate-600">Close</button>
            </div>
            <div className="space-y-6 p-4 md:p-6">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">User ID</label>
                {isAuthenticated ? (
                  <div className="w-full rounded-lg border border-green-200 dark:border-green-700 bg-green-50 dark:bg-green-900/20 px-3 py-2 text-sm text-green-800 dark:text-green-300">
                    {user?.id} (Google ID)
                  </div>
                ) : (
                  <input value={userName} onChange={(e)=>setUserName(e.target.value)} className="w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"/>
                )}
                <div className="mt-1 text-[11px] text-slate-400 dark:text-slate-500">
                  {isAuthenticated ?
                    "Using your authenticated Google ID for consistent message tracking." :
                    "Sign in to use your Google ID, or use a custom name for demo mode."
                  }
                </div>
              </div>



              <div className="rounded-lg bg-slate-50 dark:bg-slate-700 p-3 text-sm text-slate-600 dark:text-slate-300">
                <div className="font-medium text-slate-800 dark:text-slate-200 mb-2">About Buffett</div>
                <p>Your personal AI assistant trained on Warren Buffett's investing wisdom and business philosophy. All connections are automatically configured and ready to use.</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Rate Limit Banner Component
function RateLimitBanner({ remainingQueries, onClose, onSignUp, isVisible }) {
  const getMessage = () => {
    if (remainingQueries === 0) {
      return (
        <>
          Daily limit reached. Please{" "}
          <button onClick={onSignUp} className="underline hover:no-underline font-medium">
            sign up
          </button>{" "}
          to continue
        </>
      );
    }
    const questionsText = remainingQueries === 1 ? "question" : "questions";
    return (
      <>
        {remainingQueries} more {questionsText} can be asked today.{" "}
        <button onClick={onSignUp} className="underline hover:no-underline font-medium">
          Sign up
        </button>{" "}
        for more access
      </>
    );
  };

  return (
    <div className={`mx-auto max-w-3xl mb-4 px-4 transform transition-all duration-1000 ease-in-out ${
      isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
    }`}>
      <div className="flex items-center justify-between px-4 py-3 bg-slate-50 dark:bg-slate-700 rounded-lg text-white text-sm shadow-sm">
        <div className="flex items-center gap-2">
          {getMessage()}
        </div>
        <button
          onClick={onClose}
          className="text-slate-300 hover:text-white ml-4"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

// Analysis Mode Dropdown Component
function AnalysisModeDropdown({ selectedMode, onModeChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const modes = [
    { id: 'buffett', name: 'Buffett', description: 'Value investing analysis' },
    { id: 'investment-research', name: 'Investment Research', description: 'Comprehensive research' },
  ];

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const currentMode = modes.find(m => m.id === selectedMode) || modes[0];

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-slate-600 dark:text-slate-300 bg-slate-100/80 dark:bg-slate-600/50 hover:bg-slate-200/80 dark:hover:bg-slate-500/50 rounded-full transition-all duration-200"
      >
        <span>{currentMode.name}</span>
        <ChevronDown className={`h-3.5 w-3.5 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-52 bg-white dark:bg-slate-800 rounded-xl shadow-xl border border-slate-200 dark:border-slate-700 py-1.5 z-50 animate-in fade-in slide-in-from-top-2 duration-200">
          {modes.map((mode) => (
            <button
              key={mode.id}
              type="button"
              onClick={() => {
                onModeChange(mode.id);
                setIsOpen(false);
              }}
              className={classNames(
                "w-full text-left px-4 py-2.5 text-sm transition-colors",
                mode.id === selectedMode
                  ? "bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400"
                  : "text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700/50"
              )}
            >
              <div className="font-medium">{mode.name}</div>
              <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{mode.description}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// Search Composer Component
function SearchComposer({
  input,
  setInput,
  doSend,
  isConnecting,
  suggestions = [],
  onSuggestionClick,
  suggestionsLoading = false,
  selectedMode = 'buffett',
  onModeChange,
  isFollowUpMode = false,
  // Autocomplete props
  searchResults = [],
  isSearching = false,
  onResultSelect,
  onInputChange
}) {
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);

  // Determine placeholder text
  const placeholderText = isConnecting
    ? "Connecting..."
    : isFollowUpMode
      ? "Ask a follow-up question about the report..."
      : "Enter a company name or ticker...";

  // Show dropdown when there are results or loading, and in investment-research mode
  const shouldShowDropdown = showDropdown &&
    selectedMode === 'investment-research' &&
    !isFollowUpMode &&
    (searchResults.length > 0 || isSearching);

  // Handle input change
  const handleInputChange = (e) => {
    const value = e.target.value;
    setInput(value);
    setShowDropdown(true);
    setHighlightedIndex(-1);
    onInputChange?.(value);
  };

  // Handle result selection
  const handleSelect = (result) => {
    setShowDropdown(false);
    setHighlightedIndex(-1);
    onResultSelect?.(result);
  };

  // Handle keyboard navigation
  const handleKeyDown = (e) => {
    if (!shouldShowDropdown) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (input.trim()) doSend();
      }
      return;
    }

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex(prev =>
          prev < searchResults.length - 1 ? prev + 1 : prev
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex(prev => prev > 0 ? prev - 1 : -1);
        break;
      case "Enter":
        e.preventDefault();
        if (highlightedIndex >= 0 && searchResults[highlightedIndex]) {
          handleSelect(searchResults[highlightedIndex]);
        } else if (input.trim()) {
          setShowDropdown(false);
          doSend();
        }
        break;
      case "Escape":
        setShowDropdown(false);
        setHighlightedIndex(-1);
        break;
      default:
        break;
    }
  };

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target) &&
          inputRef.current && !inputRef.current.contains(event.target)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-2 md:px-0">
      {/* Search Bar Container - iOS 26 liquid glass style */}
      <div className="relative">
        <div className="relative flex items-center rounded-full border border-slate-200/80 dark:border-slate-600/50 bg-white/90 dark:bg-slate-700/80 backdrop-blur-xl shadow-lg px-5 py-3.5 focus-within:border-indigo-400 dark:focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/30 transition-all">
          {/* Input */}
          <input
            ref={inputRef}
            type="text"
            placeholder={placeholderText}
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => setShowDropdown(true)}
            disabled={isConnecting}
            className="peer block w-full bg-transparent text-sm md:text-[15px] placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none dark:text-slate-100"
            autoComplete="off"
          />

          {/* Analysis Mode Dropdown */}
          <div className="ml-3 mr-1 flex-shrink-0">
            <AnalysisModeDropdown
              selectedMode={selectedMode}
              onModeChange={onModeChange}
            />
          </div>

          {/* Send button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (!input.trim() || isConnecting) return;
              setShowDropdown(false);
              doSend();
            }}
            disabled={!input.trim() || isConnecting}
            className={classNames(
              "flex-shrink-0 inline-flex h-10 w-10 items-center justify-center rounded-full shadow-sm transition-all duration-200",
              (!input.trim() || isConnecting)
                ? "bg-indigo-400 dark:bg-indigo-600/50 cursor-not-allowed text-white"
                : "bg-indigo-600 hover:bg-indigo-700 hover:scale-105 dark:bg-indigo-600 dark:hover:bg-indigo-500 cursor-pointer text-white"
            )}
          >
            {isConnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>

        {/* Autocomplete Dropdown */}
        {shouldShowDropdown && (
          <div
            ref={dropdownRef}
            className="absolute z-50 w-full mt-2 py-2 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-xl max-h-64 overflow-y-auto"
          >
            {isSearching ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
                <span className="ml-2 text-sm text-slate-500 dark:text-slate-400">Searching...</span>
              </div>
            ) : searchResults.length > 0 ? (
              searchResults.slice(0, 7).map((result, index) => (
                <button
                  key={result.ticker}
                  type="button"
                  onClick={() => handleSelect(result)}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  className={classNames(
                    "w-full px-4 py-2.5 text-left flex items-center gap-3 transition-colors",
                    highlightedIndex === index
                      ? "bg-indigo-50 dark:bg-indigo-900/30"
                      : "hover:bg-slate-50 dark:hover:bg-slate-700/50"
                  )}
                >
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400 min-w-[60px]">
                    {result.ticker}
                  </span>
                  <span className="text-sm text-slate-600 dark:text-slate-300 truncate">
                    {result.name}
                  </span>
                </button>
              ))
            ) : input.trim().length > 0 ? (
              <div className="px-4 py-3 text-sm text-slate-500 dark:text-slate-400 text-center">
                No companies found for &quot;{input.trim()}&quot;
              </div>
            ) : null}
          </div>
        )}
      </div>

      {/* Follow-up suggestion pills */}
      {suggestions.length > 0 && (
        <div className="flex gap-2 justify-center mt-3 pb-2 px-2 overflow-x-auto scrollbar-hide">
          {suggestionsLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
          ) : (
            suggestions.map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => onSuggestionClick?.(q)}
                className="px-4 py-2.5 text-sm text-slate-600 dark:text-slate-400 bg-white dark:bg-slate-800 rounded-full border border-slate-200 dark:border-slate-700 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:scale-105 transition-all duration-200 whitespace-nowrap flex-shrink-0"
              >
                {q}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}

// Dark Mode Toggle Component
function DarkModeToggle({ darkMode, onToggle }) {
  return (
    <div className="flex items-center gap-3 px-4 py-2">
      <div className="flex items-center gap-2 flex-1">
        <div className="text-slate-400 dark:text-slate-500">
          <Sun className="h-4 w-4" />
        </div>
        <button
          onClick={onToggle}
          className={classNames(
            "relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2",
            darkMode ? "bg-indigo-600" : "bg-slate-200"
          )}
          role="switch"
          aria-checked={darkMode}
        >
          <span
            aria-hidden="true"
            className={classNames(
              "pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out",
              darkMode ? "translate-x-5" : "translate-x-0"
            )}
          />
        </button>
        <div className="text-slate-400 dark:text-slate-500">
          <Moon className="h-4 w-4" />
        </div>
      </div>
      <span className="text-sm text-slate-700 dark:text-slate-300 font-medium">
        Dark Mode
      </span>
    </div>
  );
}

// Account Dropdown Component
function AccountDropdown({ isOpen, onToggle, onSettingsClick, darkMode, onDarkModeToggle, dropdownPosition = "bottom", connectionStatus }) {
  const { user, isAuthenticated, logout } = useAuth();
  const dropdownRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        onToggle(false);
      }
    }

    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isOpen, onToggle]);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Dropdown Trigger */}
      <button
        onClick={() => onToggle(!isOpen)}
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors w-full"
      >
        {isAuthenticated && user ? (
          <>
            <div className="relative">
              <Avatar
                src={user?.picture || ''}
                alt={user?.name || user?.email || 'User'}
                size="w-6 h-6"
              />
              {/* Connection status dot */}
              {connectionStatus && (
                <span className={classNames(
                  "absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-slate-800",
                  connectionStatus === "connected" ? "bg-emerald-500" :
                  connectionStatus === "connecting" ? "bg-amber-500 animate-pulse" :
                  "bg-slate-400"
                )} />
              )}
            </div>
            <span className="text-sm font-medium text-slate-700 dark:text-white truncate">{user?.name || user?.email || 'User'}</span>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-700 dark:text-white">Log In</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">/ Sign up for free</span>
            </div>
          </>
        )}
        <ChevronDown className={classNames(
          "h-4 w-4 text-slate-400 transition-transform ml-auto",
          isOpen ? "rotate-180" : ""
        )} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className={classNames(
          "absolute w-56 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-50 transition-all duration-200",
          dropdownPosition === "top"
            ? "bottom-full mb-3 left-0"
            : "top-full mt-2 right-0"
        )}>
          {isAuthenticated && user ? (
            <>
              {/* User Info Header */}
              <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-700">
                <div className="flex items-center gap-3">
                  <Avatar
                    src={user?.picture || ''}
                    alt={user?.name || user?.email || 'User'}
                    size="w-8 h-8"
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">{user?.name || user?.email || 'User'}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400 truncate">{user?.email || ''}</div>
                  </div>
                </div>
              </div>

              {/* Dark Mode Toggle */}
              <DarkModeToggle darkMode={darkMode} onToggle={onDarkModeToggle} />

              {/* Menu Items */}
              <div className="py-1">
                <button
                  onClick={() => {
                    onSettingsClick();
                    onToggle(false);
                  }}
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </button>
                <button
                  onClick={() => {
                    logout();
                    onToggle(false);
                  }}
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            </>
          ) : (
            <>
              {/* Not authenticated menu */}
              <div className="py-1">
                <div className="px-4 py-3">
                  <GoogleLoginButton />
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ResearchProvider>
        <ChatApp />
      </ResearchProvider>
    </AuthProvider>
  );
}
