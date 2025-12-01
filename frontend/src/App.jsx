import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search, Send, Settings, Wifi, WifiOff, Loader2, Trash2, MessageSquare, Zap, ThumbsUp, ThumbsDown, RefreshCcw, Archive, FolderOpen, X, Menu, ChevronDown, User, LogOut, Sun, Moon, PanelLeftClose, Sparkles, Lightbulb, BarChart3 } from "lucide-react";
import AnalysisView from "./components/analysis/AnalysisView.jsx";
import { AuthProvider, AuthButton, useAuth, GoogleLoginButton } from "./auth.jsx";
import { useConversations } from "./hooks/useConversations.js";
import { ConversationList } from "./components/ConversationList.jsx";
import { loadConversationHistory } from "./api/conversationsApi.js";
import { Avatar } from "./components/Avatar.jsx";
import logger from "./utils/logger.js";

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
          setMessages((m) => {
            // append or create a temp assistant message
            if (!pendingAssistantId) {
              const id = `asst-${uid8()}`;
              setPendingAssistantId(id);
              return [
                ...m,
                { id, type: "assistant", content: data.text || "", timestamp: data.timestamp || nowIso(), meta: { streaming: true } },
              ];
            }
            return m.map((msg) => (msg.id === pendingAssistantId ? { ...msg, content: (msg.content || "") + (data.text || "") } : msg));
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
 * REST helpers          *
 ************************/

async function sendChatMessage(restBaseUrl, message, sessionId, token) {
  // Send chat message via REST API
  const baseUrl = restBaseUrl.replace(/\/$/, "");
  const url = `${baseUrl}/chat`;

  const headers = {
    "Content-Type": "application/json"
  };

  // Add authorization header if token is available
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const body = {
    message: message,
    session_id: sessionId
  };

  logger.log('📤 Sending REST API message:', url, body);

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Chat request failed (${res.status}): ${errorText}`);
  }

  return res.json();
}

async function sendSearchQuery(restBaseUrl, query, conversationId, token) {
  // Send search query via REST API to Perplexity
  const baseUrl = restBaseUrl.replace(/\/$/, "");
  const url = `${baseUrl}/search`;

  const headers = {
    "Content-Type": "application/json"
  };

  // Add authorization header if token is available
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const body = {
    query: query,
    conversation_id: conversationId,
    model: "sonar"
  };

  logger.log('🔍 Sending search query:', url, body);

  const res = await fetch(url, {
    method: "POST",
    headers,
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Search request failed (${res.status}): ${errorText}`);
  }

  return res.json();
}

/************************
 * Message bubble        *
 ************************/
function MessageBubble({ msg, user, messageRef }) {
  const isUser = msg.type === "user";
  const isSystem = msg.type === "system";
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
        {!isUser && !isSystem && (
          <div className={classNames("mt-2 flex items-center gap-3 md:gap-2 text-[11px] text-slate-400")}>
            <button className="inline-flex items-center hover:opacity-70 active:opacity-50 min-h-[44px] md:min-h-0 -my-2 md:my-0" title="Like"><ThumbsUp className="h-3.5 w-3.5 md:h-3 md:w-3"/></button>
            <button className="inline-flex items-center hover:opacity-70 active:opacity-50 min-h-[44px] md:min-h-0 -my-2 md:my-0" title="Dislike"><ThumbsDown className="h-3.5 w-3.5 md:h-3 md:w-3"/></button>
            <button className="inline-flex items-center gap-1 hover:opacity-70 active:opacity-50 min-h-[44px] md:min-h-0 -my-2 md:my-0"><RefreshCcw className="h-3.5 w-3.5 md:h-3 md:w-3"/> Retry</button>
          </div>
        )}
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

  // Log environment config only once on component mount
  useEffect(() => {
    logger.log('🌍 Environment Config:', ENV_CONFIG);
  }, []);
  
  // Use environment variables directly - no user override needed
  const wsUrl = ENV_CONFIG.WEBSOCKET_URL;
  const restUrl = ENV_CONFIG.REST_API_URL;
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
  const [mode, setMode] = useState('bedrock'); // 'search', 'bedrock', or 'analysis'
  const [showAnalysis, setShowAnalysis] = useState(false);
  const [analysisTicker, setAnalysisTicker] = useState('');
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [isConnecting, setIsConnecting] = useState(false);
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

  const { status, sessionId, messages, connect, disconnect, sendMessage, setMessages, switchConversation } = useAwsWebSocket({
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
    if (wsUrl && isAuthenticated && token) {
      logger.log('🔐 Reconnecting WebSocket after authentication...');
      disconnect();
      // Longer delay to ensure clean disconnection before reconnecting
      // This prevents race conditions where the old connection triggers errors
      setTimeout(() => connect(), 500);
    }
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

  const doSend = useCallback(async (overrideText = null, currentMode = 'bedrock') => {
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

    // Set evaluating state when sending message
    setIsEvaluating(true);

    // Create conversation if needed (for authenticated users)
    if (isAuthenticated && !selectedConversation && messages.length === 0) {
      const title = messageText.slice(0, 50) + (messageText.length > 50 ? '...' : '');
      const newConv = await createConversation(title);
      if (newConv) {
        setSelectedConversation(newConv);
        // useEffect will handle WebSocket reconnection with the new conversation_id
        // Wait for the WebSocket to reconnect before sending
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }

    // ANALYSIS MODE: Open Deep Value Analysis view
    if (currentMode === 'analysis') {
      setAnalysisTicker(messageText.trim());
      setShowAnalysis(true);
      if (!overrideText) setInput("");
      setIsEvaluating(false);
      return;
    }

    // SEARCH MODE: Use REST API to call Perplexity
    if (currentMode === 'search' && restUrl) {
      // Add user message immediately
      const userMsg = {
        id: `usr-${uid8()}`,
        type: "user",
        content: messageText,
        timestamp: nowIso()
      };
      setMessages((m) => [...m, userMsg]);

      try {
        // Send search query via REST API
        const effectiveConversationId = selectedConversation?.conversation_id || sessionId || uid8();
        const response = await sendSearchQuery(restUrl, messageText, effectiveConversationId, token);

        // Add AI response
        const aiMsg = {
          id: response.ai_message_id || `ai-${uid8()}`,
          type: "assistant",
          content: response.response || "No response received",
          timestamp: response.timestamp || nowIso(),
          meta: { processingTime: response.processing_time_ms, model: response.model }
        };
        setMessages((m) => [...m, aiMsg]);

        // Clear evaluating state
        setIsEvaluating(false);

        // Refresh conversations to update inbox ordering
        if (fetchConversations) {
          fetchConversations();
        }

      } catch (error) {
        logger.error('Search API error:', error);
        // Add error message
        const errorMsg = {
          id: `err-${uid8()}`,
          type: "system",
          content: `Search error: ${error.message}`,
          timestamp: nowIso()
        };
        setMessages((m) => [...m, errorMsg]);

        // Clear evaluating state on error
        setIsEvaluating(false);
      }

      // For unauthorized users, increment query count
      if (!isAuthenticated) {
        const newCount = incrementQueryCount();
        const newRemaining = DAILY_QUERY_LIMIT - newCount;
        setRemainingQueries(newRemaining);
        setHasStartedQuerying(true);

        // Only show banner after first query and with delay for animation
        setTimeout(() => {
          setShowRateLimitBanner(true);
        }, 500);

        // Auto-hide banner after 8 seconds
        setTimeout(() => {
          setShowRateLimitBanner(false);
        }, 8000);
      }

      return;
    }

    // BEDROCK MODE: Use WebSocket or fallback to REST
    // For authenticated users, wait for WebSocket connection if it's in progress
    if (isAuthenticated && token && (status === "connecting" || status === "disconnected")) {
      setIsConnecting(true);
      // Wait up to 5 seconds for connection
      let attempts = 0;
      const maxAttempts = 25;
      while ((status === "connecting" || status === "disconnected") && attempts < maxAttempts) {
        await new Promise(resolve => setTimeout(resolve, 200));
        attempts++;
      }
      setIsConnecting(false);

      // If still not connected after waiting, log warning
      if (status !== "connected") {
        logger.warn('⚠️ WebSocket failed to connect after waiting, status:', status);
      }
    }

    // Check if we should use REST API (authenticated and has REST URL)
    if (isAuthenticated && token && restUrl && status !== "connected") {
      // Add user message immediately
      const userMsg = {
        id: `usr-${uid8()}`,
        type: "user",
        content: messageText,
        timestamp: nowIso()
      };
      setMessages((m) => [...m, userMsg]);

      try {
        // Send via REST API - use conversation_id if available, otherwise sessionId
        const effectiveSessionId = selectedConversation?.conversation_id || sessionId || uid8();
        const response = await sendChatMessage(restUrl, messageText, effectiveSessionId, token);

        // Add AI response
        const aiMsg = {
          id: response.ai_message_id || `ai-${uid8()}`,
          type: "assistant",
          content: response.response || "No response received",
          timestamp: response.timestamp || nowIso(),
          meta: { processingTime: response.processing_time }
        };
        setMessages((m) => [...m, aiMsg]);

        // Clear evaluating state
        setIsEvaluating(false);

        // Refresh conversations to update inbox ordering
        if (fetchConversations) {
          fetchConversations();
        }

      } catch (error) {
        logger.error('REST API error:', error);
        // Add error message
        const errorMsg = {
          id: `err-${uid8()}`,
          type: "system",
          content: `Error: ${error.message}`,
          timestamp: nowIso()
        };
        setMessages((m) => [...m, errorMsg]);

        // Clear evaluating state on error
        setIsEvaluating(false);
      }
    } else {
      // Use WebSocket or demo mode - pass conversation_id
      sendMessage(messageText, selectedConversation?.conversation_id);
    }

    // For unauthorized users, increment query count and show banner
    if (!isAuthenticated) {
      const newCount = incrementQueryCount();
      const newRemaining = DAILY_QUERY_LIMIT - newCount;
      setRemainingQueries(newRemaining);
      setHasStartedQuerying(true);

      // Only show banner after first query and with delay for animation
      setTimeout(() => {
        setShowRateLimitBanner(true);
      }, 500);

      // Auto-hide banner after 8 seconds
      setTimeout(() => {
        setShowRateLimitBanner(false);
      }, 8000);
    }
  }, [input, sendMessage, isAuthenticated, token, restUrl, status, sessionId, setMessages, selectedConversation, createConversation, fetchConversations]);

  const newChat = useCallback(async () => {
    // Clear messages first
    setMessages([]);

    // If authenticated, create a new conversation in the backend
    if (isAuthenticated && token) {
      const title = `Chat ${new Date().toLocaleDateString()}`;
      const newConv = await createConversation(title);
      if (newConv) {
        setSelectedConversation(newConv);
        // Don't manually reconnect here - let useEffect handle it
        return; // Exit early, conversation change will trigger reconnect
      }
    }

    // For non-authenticated users or if conversation creation failed
    // Clear selection and start fresh session
    setSelectedConversation(null);
    disconnect();
    setTimeout(() => connect(), 50);
  }, [disconnect, connect, setMessages, setSelectedConversation, isAuthenticated, token, createConversation]);

  const removeSession = useCallback((id) => {
    setSessions((prev) => {
      const next = prev.filter((s) => s.id !== id);
      setLS(LS_KEYS.sessions, JSON.stringify(next));
      return next;
    });
  }, []);

  // Load conversation messages when switching conversations
  const loadConversationMessages = useCallback(async (conversationId) => {
    if (!token || !conversationId) return;

    try {
      const { messages } = await loadConversationHistory(conversationId, token);

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

      setMessages(formattedMessages);
    } catch (error) {
      logger.error('Error loading conversation messages:', error);
      // Don't alert on error, just log it
    }
  }, [token, setMessages]);


  const connectionBadge = status === "connected" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-700 px-2 py-1 text-xs"><Wifi className="h-3 w-3"/> Connected</span>
  ) : status === "connecting" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 text-amber-700 px-2 py-1 text-xs"><Loader2 className="h-3 w-3 animate-spin"/> Connecting</span>
  ) : status === "error" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-700 px-2 py-1 text-xs"><WifiOff className="h-3 w-3"/> Error</span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 text-slate-600 px-2 py-1 text-xs"><WifiOff className="h-3 w-3"/> Disconnected</span>
  );

  return (
    <div className="h-screen w-screen overflow-hidden bg-[#e6eef9] dark:bg-slate-900 text-slate-800 dark:text-slate-100">
      {/* App shell */}
      <div className="mx-auto h-full max-w-[1400px] md:px-4 md:py-6">
        <div className="flex h-full md:rounded-3xl bg-white dark:bg-slate-800 md:shadow-xl md:ring-1 md:ring-black/5 md:ring-slate-700/50">
          {/* Mobile backdrop overlay - only visible when sidebar open on mobile */}
          {isAuthenticated && sidebarOpen && (
            <div
              className="fixed inset-0 bg-black/50 z-40 md:hidden"
              onClick={() => setSidebarOpen(false)}
            />
          )}

          {/* Sidebar - Only show for authenticated users */}
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
                <div className="flex flex-col items-center gap-3">
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    title="Open sidebar"
                  >
                    <Menu className="h-4 w-4" />
                  </button>
                  <button
                    onClick={newChat}
                    className="rounded-md p-2 bg-indigo-600 text-white hover:bg-indigo-700"
                    title="New chat"
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
                    className="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    title="Search chats"
                  >
                    <Search className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => setSettingsOpen(true)}
                    className="rounded-md p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                    title="Settings"
                  >
                    <Settings className="h-4 w-4" />
                  </button>
                </div>
              </>
            )}

            {sidebarOpen && (
              <>
            <div className="flex items-center gap-2">
              <button onClick={newChat} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700">
                <Plus className="h-4 w-4"/> New chat
              </button>
              <button onClick={() => setSettingsOpen(true)} className="ml-auto rounded-xl border border-slate-200 dark:border-slate-600 p-2 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300" title="Settings">
                <Settings className="h-4 w-4"/>
              </button>
            </div>

            <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2">
              <Search className="h-4 w-4 text-slate-400"/>
              <input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="Search" className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"/>
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

            <div className="mt-2 space-y-1 overflow-y-auto pr-1 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600" style={{maxHeight: "calc(100vh - 320px)"}}>
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
                      await loadConversationMessages(conv.conversation_id);
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

            <div className="mt-4 text-xs text-center text-slate-400">Last 7 days</div>
              </>
            )}
          </aside>
          )}

          {/* Main panel */}
          <main className="relative flex min-w-0 flex-1 flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-700 px-4 md:px-6 py-4">
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
                <button
                  onClick={newChat}
                  className="rounded-full bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 dark:hover:bg-indigo-900/50 transition-colors cursor-pointer"
                  title="Start new chat"
                >
                  {ENV_CONFIG.APP_NAME}
                </button>
                {/* Hide connection badge and session info on small mobile screens */}
                <div className="hidden sm:block">
                  {connectionBadge}
                </div>
                {selectedConversation ? (
                  <div className="hidden sm:block rounded-full bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1 text-xs text-indigo-600 dark:text-indigo-300">
                    {selectedConversation.title}
                  </div>
                ) : sessionId ? (
                  <div className="hidden sm:block rounded-full bg-slate-50 dark:bg-slate-700 px-3 py-1 text-xs text-slate-500 dark:text-slate-400">Session: {sessionId.slice(0,8)}…</div>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {!wsUrl && (
                  <div className="rounded-lg bg-amber-50 px-3 py-1 text-xs text-amber-700">Add your WebSocket URL in Settings →</div>
                )}
                <AccountDropdown
                  isOpen={accountDropdownOpen}
                  onToggle={setAccountDropdownOpen}
                  onSettingsClick={() => setSettingsOpen(true)}
                  darkMode={darkMode}
                  onDarkModeToggle={toggleDarkMode}
                />
              </div>
            </div>

            {/* Dynamic Layout Based on Message State */}
            {messages.length === 0 ? (
              /* CENTERED LAYOUT - No messages (landing, auth, new chat) */
              <div className="flex-1 flex flex-col items-center justify-center px-4 md:px-6 transition-all duration-300 ease-in-out">
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
                    status={status}
                    newChat={newChat}
                    setSettingsOpen={setSettingsOpen}
                    showTopicButtons={true}
                    isAuthenticated={isAuthenticated}
                    mode={mode}
                    setMode={setMode}
                  />
                </div>
              </div>
            ) : (
              /* SPLIT LAYOUT - Messages exist (active conversation) */
              <>
                {/* Analysis View or Messages Area */}
                {showAnalysis ? (
                  <div className="flex-1 overflow-hidden p-4">
                    <AnalysisView
                      ticker={analysisTicker}
                      fiscalYear={new Date().getFullYear()}
                      onClose={() => setShowAnalysis(false)}
                      analysisApiUrl={import.meta.env.VITE_ANALYSIS_API_URL}
                    />
                  </div>
                ) : (
                <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 transition-all duration-300 ease-in-out">
                  <div className="mx-auto max-w-3xl space-y-4">
                    {messages.map((m, index) => {
                      // Find the last user message in the entire array
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
                )}

                {/* Bottom Composer */}
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
                    status={status}
                    newChat={newChat}
                    setSettingsOpen={setSettingsOpen}
                    showTopicButtons={false}
                    isAuthenticated={isAuthenticated}
                    mode={mode}
                    setMode={setMode}
                  />
                </div>
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

// Main App component wrapped with AuthProvider
// Topic Buttons Component
function TopicButtons({ onPromptSelect }) {
  const [openDropdown, setOpenDropdown] = useState(null);
  const dropdownRef = useRef(null);

  const topics = {
    buffett_wisdom: {
      label: "Buffett Wisdom",
      prompts: [
        "What does \"be fearful when others are greedy\" mean?",
        "What is an \"economic moat\"?",
        "Does Buffett recommend diversification or concentration?",
        "What does Buffett look for in company management?",
        "How should investors react to market crashes?"
      ]
    },
    wealth_planning: {
      label: "Wealth Planning",
      prompts: [
        "How much should I save for retirement at age 30?",
        "Pay off mortgage early or invest the money?",
        "Roth IRA vs. Traditional IRA - which is better?",
        "Should I pay off debt before investing?",
        "How much do I need in an emergency fund?"
      ]
    },
    learn_investing: {
      label: "Learn Investing",
      prompts: [
        "What is intrinsic value?",
        "What's the difference between growth and value investing?",
        "How does compound interest work?",
        "What financial metrics should I analyze?",
        "How do I know if a stock is overvalued?"
      ]
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setOpenDropdown(null);
      }
    }

    if (openDropdown) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [openDropdown]);

  const handlePromptClick = (prompt) => {
    onPromptSelect(prompt);
    setOpenDropdown(null);
  };

  return (
    <div className="mx-auto max-w-3xl mt-8 md:mt-6 mb-2 md:mb-0">
      <div className="flex justify-center gap-3 md:gap-4" ref={dropdownRef}>
        {Object.entries(topics).map(([key, topic]) => (
          <div key={key} className="relative">
            <button
              onClick={() => setOpenDropdown(openDropdown === key ? null : key)}
              className="px-4 md:px-4 py-2.5 md:py-2 text-sm md:text-base rounded-full bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-600 dark:hover:bg-indigo-600 hover:text-white dark:hover:text-white hover:shadow-lg hover:shadow-indigo-200 dark:hover:shadow-indigo-900/50 transition-all duration-200 border border-indigo-200 dark:border-indigo-700"
            >
              {topic.label}
            </button>

            {openDropdown === key && (
              <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 md:left-0 md:translate-x-0 w-[calc(100vw-2rem)] md:w-80 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-50 transition-all duration-200">
                <div className="py-2">
                  {topic.prompts.map((prompt, index) => (
                    <button
                      key={index}
                      onClick={() => handlePromptClick(prompt)}
                      className="w-full text-left px-4 py-3 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors border-b border-slate-100 dark:border-slate-700 last:border-b-0"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// Search Composer Component
function SearchComposer({
  input,
  setInput,
  doSend,
  isConnecting,
  status,
  newChat,
  setSettingsOpen,
  showTopicButtons = false,
  isAuthenticated,
  mode,
  setMode
}) {
  const inputRef = useRef(null);

  const handlePromptSelect = async (prompt) => {
    // Use the main doSend function with the prompt text as override
    doSend(prompt, mode);

    // Clear the input after sending
    setInput('');
  };

  return (
    <>
      <div className="mx-auto max-w-3xl px-2 md:px-0">
        {/* Search Bar Container */}
        <div className="relative flex items-center rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 shadow-sm px-3 py-3 focus-within:border-indigo-300 dark:focus-within:border-indigo-500">
          {/* Left toggles */}
          <div className="flex items-center gap-1 pr-3">
            <button
              type="button"
              onClick={() => setMode('search')}
              className={classNames(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-all",
                mode === 'search'
                  ? "border-indigo-600 dark:border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400"
                  : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-600"
              )}
              title="Search mode (Perplexity)"
              aria-label="Search mode"
            >
              <Search className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setMode('bedrock')}
              className={classNames(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-all",
                mode === 'bedrock'
                  ? "border-indigo-600 dark:border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400"
                  : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-600"
              )}
              title="Buffett Agent mode"
              aria-label="Buffett Agent mode"
            >
              <Lightbulb className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setMode('analysis')}
              className={classNames(
                "inline-flex h-8 w-8 items-center justify-center rounded-md border transition-all",
                mode === 'analysis'
                  ? "border-indigo-600 dark:border-indigo-500 bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-400"
                  : "border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-600"
              )}
              title="Deep Value Analysis"
              aria-label="Deep Value Analysis"
            >
              <BarChart3 className="h-4 w-4" />
            </button>
            <span className="mx-1 h-6 w-px bg-slate-200 dark:bg-slate-600" />
          </div>

          {/* Input */}
          <input
            ref={inputRef}
            type="text"
            placeholder={isConnecting ? "Connecting..." : "Ask Warren Buffett about investing and business..."}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (input.trim()) doSend(null, mode);
              }
            }}
            disabled={isConnecting}
            className="peer block w-full bg-transparent text-sm md:text-[15px] placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:outline-none dark:text-slate-100"
          />

          {/* Send button */}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              if (!input.trim() || isConnecting) return;
              doSend(null, mode);
            }}
            disabled={!input.trim() || isConnecting}
            className={classNames(
              "ml-2 inline-flex h-9 w-9 items-center justify-center rounded-lg shadow-sm transition-colors",
              (!input.trim() || isConnecting)
                ? "bg-indigo-400 dark:bg-indigo-600/50 cursor-not-allowed text-white"
                : "bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-600 dark:hover:bg-indigo-500 cursor-pointer text-white"
            )}
          >
            {isConnecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </button>
        </div>

        {/* Mode label */}
        <div className="mt-2 text-xs text-slate-500 dark:text-slate-400 px-2">
          <span className="font-medium">
            {mode === 'search' ? '🔍 Search' : mode === 'analysis' ? '📊 Deep Value Analysis' : '💡 Buffett Agent'}
          </span>
          {mode === 'analysis' && (
            <span className="ml-2 text-slate-400 dark:text-slate-500">
              Enter a company name (e.g., Apple, MSFT)
            </span>
          )}
        </div>
      </div>

      {showTopicButtons && isAuthenticated && (
        <TopicButtons onPromptSelect={handlePromptSelect} />
      )}
    </>
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
function AccountDropdown({ isOpen, onToggle, onSettingsClick, darkMode, onDarkModeToggle }) {
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
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
      >
        {isAuthenticated && user ? (
          <>
            <Avatar
              src={user?.picture || ''}
              alt={user?.name || user?.email || 'User'}
              size="w-6 h-6"
            />
            <span className="text-sm font-medium text-slate-700 dark:text-white">{user?.name || user?.email || 'User'}</span>
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
          "h-4 w-4 text-slate-400 transition-transform",
          isOpen ? "rotate-180" : ""
        )} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg z-50 transition-all duration-200">
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
      <ChatApp />
    </AuthProvider>
  );
}
