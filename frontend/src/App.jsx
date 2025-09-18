import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Plus, Search, Send, Settings, Wifi, WifiOff, Loader2, Trash2, MessageSquare, Zap, ThumbsUp, ThumbsDown, RefreshCcw, Archive, FolderOpen } from "lucide-react";
import { AuthProvider, AuthButton, useAuth } from "./auth.jsx";
import { useConversations } from "./hooks/useConversations.js";
import { ConversationList } from "./components/ConversationList.jsx";
import { loadConversationHistory } from "./api/conversationsApi.js";

/*************************
 * Environment Configuration *
 *************************/
const ENV_CONFIG = {
  WEBSOCKET_URL: import.meta.env.VITE_WEBSOCKET_URL || "",
  REST_API_URL: import.meta.env.VITE_REST_API_URL || "",
  APP_NAME: import.meta.env.VITE_APP_NAME || "Warren Buffett Chat AI",
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
  manualConfig: "chat.ai.manualConfig" // Track if user overrode defaults
};

const getLS = (k, def = "") => {
  try { const v = localStorage.getItem(k); return v ?? def; } catch { return def; }
};
const setLS = (k, v) => { try { localStorage.setItem(k, v); } catch {} };

/*********************
 * Helper utilities   *
 *********************/
function classNames(...xs) { return xs.filter(Boolean).join(" "); }
function uid8() { return Math.random().toString(36).slice(2, 10); }
function nowIso() { return new Date().toISOString(); }
function prettyTime(ts) { try { return new Date(ts).toLocaleTimeString(); } catch { return ""; } }

/************************
 * useWebSocket hook     *
 ************************/
function useAwsWebSocket({ wsUrl, userId, token, conversationId, fetchConversations }) {
  const socketRef = useRef(null);
  const [status, setStatus] = useState("disconnected");
  const [sessionId, setSessionId] = useState("");
  const [messages, setMessages] = useState([]); // {id,type:'user'|'assistant'|'system',content,timestamp,meta}
  const [pendingAssistantId, setPendingAssistantId] = useState(null);

  // Connect
  const connect = useCallback(() => {
    if (!wsUrl) {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('❌ No WebSocket URL provided');
      }
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
    
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('🔌 Connecting to WebSocket:', url, token ? '(with auth token)' : '(no token)');
    }
    
    const ws = new WebSocket(url);
    socketRef.current = ws;
    setStatus("connecting");

    ws.onopen = () => {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('✅ WebSocket connected');
      }
      setStatus("connected");
    };
    ws.onclose = () => { 
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🔌 WebSocket disconnected');
      }
      setStatus("disconnected"); 
      socketRef.current = null; 
    };
    ws.onerror = (error) => {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('❌ WebSocket error:', error);
      }
      setStatus("error");
    };

    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data || "{}");
        if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
          console.log('📨 Received WebSocket message:', data);
        }
        if (data.type === "welcome") {
          // Use conversation_id as session_id if available, otherwise fall back to session_id
          const effectiveSessionId = data.conversation_id || data.session_id || "";
          setSessionId(effectiveSessionId);
          setMessages((m) => [
            ...m,
            { id: `sys-${uid8()}`, type: "system", content: data.message || "Welcome!", timestamp: data.timestamp || nowIso() },
          ]);
        } else if (data.type === "messageReceived" || data.action === "message_received") {
          // Message acknowledgment - could show a checkmark or "sent" indicator
          if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
            console.log('✅ Message acknowledged by server');
          }
        } else if (data.action === "typing") {
          // Typing indicator
          if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
            console.log(`⌨️ ${data.is_typing ? 'Started' : 'Stopped'} typing`);
          }
          // You could show a typing indicator in the UI here
        } else if (data.type === "chunk") {
          // live streaming chunk from backend (optional)
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

          // Refresh conversations to update inbox ordering
          if (fetchConversations) {
            fetchConversations();
          }
        } else if (data.type === "error") {
          setMessages((m) => [ ...m, { id: `err-${uid8()}`, type: "system", content: data.message || "Error.", timestamp: data.timestamp || nowIso() } ]);
        }
      } catch (e) { /* ignore */ }
    };
  }, [wsUrl, userId, token, conversationId, pendingAssistantId, fetchConversations]);

  const disconnect = useCallback(() => {
    setPendingAssistantId(null);
    if (socketRef.current) { try { socketRef.current.close(); } catch {} }
  }, []);

  const sendMessage = useCallback((text) => {
    if (!text?.trim()) return;
    
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('🚀 Sending message:', text.trim());
      console.log('📡 WebSocket status:', socketRef.current?.readyState);
      console.log('🔗 Connection URL:', wsUrl);
    }
    
    // Add user message immediately
    const userMsg = { id: `usr-${uid8()}`, type: "user", content: text.trim(), timestamp: nowIso() };
    setMessages((m) => [ ...m, userMsg ]);
    
    // If WebSocket is connected, send the message
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const msg = { action: "message", message: text.trim() };
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('📤 Sending WebSocket message:', msg);
      }
      socketRef.current.send(JSON.stringify(msg));
    } else {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('⚠️ WebSocket not connected, using demo mode');
      }
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
      }, 1500);
    }
  }, [wsUrl]);

  return { status, sessionId, messages, connect, disconnect, sendMessage, setMessages };
}

/************************
 * REST helpers          *
 ************************/
async function fetchHistory(restBaseUrl, sessionId, token, limit = 60) {
  // Clean the base URL and build the history endpoint
  const baseUrl = restBaseUrl.replace(/\/$/, "");
  const url = `${baseUrl}/user/history${sessionId ? `?session_id=${encodeURIComponent(sessionId)}&limit=${limit}` : `?limit=${limit}`}`;
  
  console.log('Fetching history from:', url); // Debug log
  
  const headers = { 
    "Content-Type": "application/json"
  };
  
  // Add authorization header if token is available
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  
  const res = await fetch(url, { 
    method: "GET", 
    headers 
  });
  
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`History fetch failed (${res.status}): ${errorText}`);
  }
  
  return res.json();
}

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
  
  if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
    console.log('📤 Sending REST API message:', url, body);
  }
  
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

/************************
 * Message bubble        *
 ************************/
function MessageBubble({ msg }) {
  const isUser = msg.type === "user";
  const isSystem = msg.type === "system";
  return (
    <div className={classNames("flex gap-3", isUser ? "justify-end" : "justify-start") }>
      {!isUser && (
        <div className="h-8 w-8 shrink-0 rounded-full bg-indigo-600/10 text-indigo-700 grid place-items-center text-xs font-bold">AI</div>
      )}
      <div className={classNames("max-w-[80%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed shadow-sm", isSystem ? "bg-amber-50 text-amber-900" : isUser ? "bg-indigo-600 text-white" : "bg-slate-50 text-slate-800")}>
        <div className="whitespace-pre-wrap">{msg.content}</div>
        <div className={classNames("mt-2 flex items-center gap-2 text-[11px]", isUser?"text-indigo-100":"text-slate-400") }>
          <span>{prettyTime(msg.timestamp)}</span>
          {!isUser && !isSystem && (
            <>
              <span>•</span>
              <button className="inline-flex items-center gap-1 hover:opacity-70"><ThumbsUp className="h-3 w-3"/> Like</button>
              <button className="inline-flex items-center gap-1 hover:opacity-70"><ThumbsDown className="h-3 w-3"/> Dislike</button>
              <button className="inline-flex items-center gap-1 hover:opacity-70"><RefreshCcw className="h-3 w-3"/> Regenerate</button>
            </>
          )}
        </div>
      </div>
      {isUser && (
        <div className="h-8 w-8 shrink-0 rounded-full bg-slate-900 text-white grid place-items-center text-xs font-bold">U</div>
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
  } = useConversations({ token, userId: user?.id });
  
  // Log environment config only once on component mount
  useEffect(() => {
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('🌍 Environment Config:', ENV_CONFIG);
    }
  }, []);
  
  // Settings - Use environment variables as defaults, allow localStorage override
  const [wsUrl, setWsUrl] = useState(() => {
    const saved = getLS(LS_KEYS.wsUrl);
    // Migration: Clear old URLs that don't match current environment
    if (saved && saved !== ENV_CONFIG.WEBSOCKET_URL) {
      localStorage.removeItem(LS_KEYS.wsUrl);
      localStorage.removeItem(LS_KEYS.restUrl); // Also clear REST URL for consistency
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🧹 Cleared old URLs from localStorage for migration');
      }
      return ENV_CONFIG.WEBSOCKET_URL;
    }
    const url = saved || ENV_CONFIG.WEBSOCKET_URL;
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('🔗 WebSocket URL:', url, saved ? '(from localStorage)' : '(from env)');
    }
    return url;
  });
  const [restUrl, setRestUrl] = useState(() => {
    const saved = getLS(LS_KEYS.restUrl);
    return saved || ENV_CONFIG.REST_API_URL;
  });
  const [userName, setUserName] = useState(() => {
    const saved = getLS(LS_KEYS.userName);
    return saved || `${ENV_CONFIG.DEFAULT_USER_NAME}_${uid8()}`;
  });
  
  // Use authenticated user's Google sub ID if available, otherwise let backend generate anonymous ID
  const userId = useMemo(() => {
    if (isAuthenticated && user?.id) {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🔑 Using authenticated user ID:', user.id);
      }
      return user.id; // This is the Google sub ID
    }
    // For anonymous users, return null to let backend generate device fingerprint-based ID
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('👤 Anonymous user - letting backend generate user ID');
    }
    return null;
  }, [isAuthenticated, user?.id]);

  const { status, sessionId, messages, connect, disconnect, sendMessage, setMessages } = useAwsWebSocket({
    wsUrl,
    userId,
    token,
    conversationId: selectedConversation?.conversation_id,
    fetchConversations
  });

  // Local sidebar state (simple client-side sessions list for now)
  const [sessions, setSessions] = useState(() => {
    try { return JSON.parse(getLS(LS_KEYS.sessions, "[]")); } catch { return []; }
  });

  // UI state
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [historyLoadId, setHistoryLoadId] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [activeTab, setActiveTab] = useState('conversations'); // 'conversations' or 'local'
  const [isConnecting, setIsConnecting] = useState(false);

  // Persist settings
  useEffect(() => { setLS(LS_KEYS.wsUrl, wsUrl); }, [wsUrl]);
  useEffect(() => { setLS(LS_KEYS.restUrl, restUrl); }, [restUrl]);
  useEffect(() => { setLS(LS_KEYS.userName, userName); }, [userName]);

  // Auto connect when WS URL is present
  useEffect(() => {
    if (wsUrl) {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🔄 Auto-connecting to WebSocket...');
      }
      connect();
    }
  }, [wsUrl, connect]);

  // Reconnect WebSocket when authentication state changes
  useEffect(() => {
    if (wsUrl && isAuthenticated && token) {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🔐 Reconnecting WebSocket after authentication...');
      }
      disconnect();
      // Short delay to ensure clean reconnection
      setTimeout(() => connect(), 200);
    }
  }, [isAuthenticated, token, wsUrl, connect, disconnect]);

  // Reconnect WebSocket when selected conversation changes
  useEffect(() => {
    if (wsUrl && selectedConversation) {
      if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
        console.log('🔄 Reconnecting WebSocket for conversation:', selectedConversation.conversation_id);
      }
      disconnect();
      setTimeout(() => connect(), 100);
    }
  }, [selectedConversation?.conversation_id, wsUrl, connect, disconnect]);

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
          updated_at: Math.floor(Date.now() / 1000)
        });
      }
    }
  }, [sessionId, messages, isAuthenticated, selectedConversation, updateConversation]);

  const doSend = useCallback(async () => {
    if (!input.trim()) return;

    const messageText = input.trim();
    setInput("");

    // Create conversation if needed (for authenticated users)
    if (isAuthenticated && !selectedConversation && messages.length === 0) {
      const title = messageText.slice(0, 50) + (messageText.length > 50 ? '...' : '');
      const newConv = await createConversation(title);
      if (newConv) {
        setSelectedConversation(newConv);
        // useEffect will handle WebSocket reconnection with the new conversation_id
        // Wait a moment for the WebSocket to reconnect before sending
        await new Promise(resolve => setTimeout(resolve, 300));
      }
    }

    // For authenticated users, wait for WebSocket connection if it's in progress
    if (isAuthenticated && token && status === "connecting") {
      setIsConnecting(true);
      // Wait up to 3 seconds for connection
      let attempts = 0;
      while (status === "connecting" && attempts < 15) {
        await new Promise(resolve => setTimeout(resolve, 200));
        attempts++;
      }
      setIsConnecting(false);
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

        // Refresh conversations to update inbox ordering
        if (fetchConversations) {
          fetchConversations();
        }

      } catch (error) {
        console.error('REST API error:', error);
        // Add error message
        const errorMsg = {
          id: `err-${uid8()}`,
          type: "system",
          content: `Error: ${error.message}`,
          timestamp: nowIso()
        };
        setMessages((m) => [...m, errorMsg]);
      }
    } else {
      // Use WebSocket or demo mode
      sendMessage(messageText);
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
      setLoadingHistory(true);
      const { messages } = await loadConversationHistory(conversationId, token);

      // Format messages for display
      const formattedMessages = messages.map((m) => ({
        id: m.message_id || uid8(),
        type: m.message_type || "user",
        content: m.content || "",
        timestamp: m.timestamp || nowIso(),
        meta: {
          tokens_used: m.tokens_used,
          model: m.model,
          processingTime: m.processing_time_ms
        }
      }));

      setMessages(formattedMessages);
    } catch (error) {
      console.error('Error loading conversation messages:', error);
      // Don't alert on error, just log it
    } finally {
      setLoadingHistory(false);
    }
  }, [token, setMessages]);

  const loadHistory = useCallback(async () => {
    if (!restUrl) return;
    if (!isAuthenticated) {
      alert("Please sign in to load your chat history");
      return;
    }
    try {
      setLoadingHistory(true);
      const data = await fetchHistory(restUrl, historyLoadId, token, 200);

      // Handle different response formats from your user-history lambda
      let items = [];
      if (historyLoadId && data?.messages) {
        // Specific session format
        items = data.messages.map((m) => ({
          id: m.message_id || uid8(),
          type: m.message_type || "user",
          content: m.content || "",
          timestamp: m.timestamp || nowIso(),
        }));
      } else if (data?.conversations) {
        // All conversations format - show first conversation's messages if available
        const firstConv = data.conversations[0];
        if (firstConv?.recent_messages) {
          items = firstConv.recent_messages.map((m) => ({
            id: m.message_id || uid8(),
            type: m.message_type || "user",
            content: m.content || "",
            timestamp: m.timestamp || nowIso(),
          }));
        }
      }

      setMessages(items);
    } catch (e) {
      alert(e.message || "Failed to load history");
    } finally { setLoadingHistory(false); }
  }, [restUrl, historyLoadId, token, isAuthenticated, setMessages]);

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
    <div className="h-screen w-screen overflow-hidden bg-[#e6eef9] text-slate-800">
      {/* App shell */}
      <div className="mx-auto h-full max-w-[1400px] px-4 py-6">
        <div className="flex h-full rounded-3xl bg-white shadow-xl ring-1 ring-black/5">
          {/* Sidebar */}
          <aside className="w-[280px] shrink-0 border-r border-slate-100 p-4">
            <div className="mb-6">
              <div className="text-xs tracking-[0.35em] text-slate-400">{ENV_CONFIG.APP_NAME.toUpperCase()}</div>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={newChat} className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-3 py-2 text-sm font-medium text-white shadow hover:bg-indigo-700">
                <Plus className="h-4 w-4"/> New chat
              </button>
              <button onClick={() => setSettingsOpen(true)} className="ml-auto rounded-xl border border-slate-200 p-2 hover:bg-slate-50" title="Settings">
                <Settings className="h-4 w-4"/>
              </button>
            </div>

            <div className="mt-4 flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2">
              <Search className="h-4 w-4 text-slate-400"/>
              <input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="Search" className="w-full bg-transparent text-sm outline-none placeholder:text-slate-400"/>
            </div>

            {/* Conversation Tabs */}
            {isAuthenticated && (
              <div className="mt-4 flex gap-1 rounded-lg bg-slate-100 p-1">
                <button
                  onClick={() => setActiveTab('conversations')}
                  className={classNames(
                    "flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    activeTab === 'conversations'
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  Cloud
                </button>
                <button
                  onClick={() => setActiveTab('local')}
                  className={classNames(
                    "flex-1 rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    activeTab === 'local'
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  )}
                >
                  Local
                </button>
              </div>
            )}

            <div className="mt-6 flex items-center justify-between">
              <div className="text-xs uppercase tracking-wide text-slate-400">
                {activeTab === 'conversations' && isAuthenticated ? 'Cloud Conversations' : 'Local Sessions'}
              </div>
              {activeTab === 'conversations' && isAuthenticated && (
                <button
                  onClick={() => setShowArchived(!showArchived)}
                  className={classNames(
                    "rounded-md p-1 text-xs",
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

            <div className="mt-2 space-y-1 overflow-y-auto pr-1" style={{maxHeight: "calc(100vh - 320px)"}}>
              {/* Show conversation list for authenticated users */}
              {activeTab === 'conversations' && isAuthenticated ? (
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

            <div className="mt-4 text-xs text-right text-slate-400">Last 7 days</div>
          </aside>

          {/* Main panel */}
          <main className="relative flex min-w-0 flex-1 flex-col">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div className="flex items-center gap-3">
                <div className="rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700">{ENV_CONFIG.APP_NAME}</div>
                {connectionBadge}
                {selectedConversation ? (
                  <div className="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-600">
                    {selectedConversation.title}
                  </div>
                ) : sessionId ? (
                  <div className="rounded-full bg-slate-50 px-3 py-1 text-xs text-slate-500">Session: {sessionId.slice(0,8)}…</div>
                ) : null}
              </div>
              <div className="flex items-center gap-2">
                {!wsUrl && (
                  <div className="rounded-lg bg-amber-50 px-3 py-1 text-xs text-amber-700">Add your WebSocket URL in Settings →</div>
                )}
                <button onClick={() => setSettingsOpen(true)} className="rounded-xl border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50">
                  Settings
                </button>
                <AuthButton />
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="mx-auto max-w-3xl space-y-4">
                {messages.length === 0 && (
                  <div className="text-center py-12">
                    <div className="text-slate-400 text-lg mb-2">Welcome to {ENV_CONFIG.APP_NAME}</div>
                    <div className="text-slate-500 text-sm">
                      {ENV_CONFIG.WEBSOCKET_URL ? 
                        "Ready to chat! Your API is pre-configured." : 
                        "Configure your API URLs in Settings to get started."
                      }
                    </div>
                    {ENV_CONFIG.ENABLE_DEBUG_LOGS && (
                      <div className="mt-2 text-xs text-amber-600">Debug mode enabled ({ENV_CONFIG.ENVIRONMENT})</div>
                    )}
                  </div>
                )}
                {messages.map((m) => (
                  <MessageBubble key={m.id} msg={m} />
                ))}
              </div>
            </div>

            {/* Composer */}
            <div className="border-t border-slate-100 p-4">
              <div className="mx-auto flex max-w-3xl items-end gap-2">
                <textarea
                  rows={1}
                  placeholder={isConnecting ? "Connecting..." : status!=="connected"?"Try demo mode! Ask anything, or connect in Settings for real AI…":"Ask Warren Buffett about investing and business..."}
                  value={input}
                  onChange={(e)=>setInput(e.target.value)}
                  onKeyDown={(e)=>{ if(e.key==="Enter" && !e.shiftKey){ e.preventDefault(); doSend(); } }}
                  className="min-h-[44px] max-h-40 flex-1 resize-none rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none placeholder:text-slate-400 focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                  disabled={isConnecting}
                />
                <button onClick={doSend} disabled={!input.trim() || isConnecting} className={classNames("inline-flex h-[44px] items-center gap-2 rounded-2xl px-4 text-sm font-medium shadow-sm", (!input.trim() || isConnecting)?"bg-slate-200 text-slate-500":"bg-indigo-600 text-white hover:bg-indigo-700") }>
                  {isConnecting ? <Loader2 className="h-4 w-4 animate-spin"/> : <Send className="h-4 w-4"/>}
                </button>
              </div>
              <div className="mx-auto mt-2 flex max-w-3xl items-center justify-between text-xs text-slate-400">
                <div className="flex items-center gap-2">
                  <button onClick={newChat} className="rounded-md px-2 py-1 hover:bg-slate-50">New chat</button>
                  <span>•</span>
                  <button onClick={()=>setSettingsOpen(true)} className="rounded-md px-2 py-1 hover:bg-slate-50">Load history…</button>
                </div>
                <div className="flex items-center gap-1 text-indigo-600"><Zap className="h-3 w-3"/> Powered by Bedrock</div>
              </div>
            </div>

            {/* Sticky Upgrade chip (decorative) */}
            <div className="pointer-events-auto absolute right-2 top-1/2 hidden -translate-y-1/2 md:block">
              <div className="rotate-90 rounded-b-lg rounded-t-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white shadow">Upgrade to Pro</div>
            </div>
          </main>
        </div>
      </div>

      {/* Settings Panel */}
      {settingsOpen && (
        <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" onClick={()=>setSettingsOpen(false)}>
          <div className="absolute right-0 top-0 h-full w-full max-w-xl overflow-y-auto bg-white shadow-xl" onClick={(e)=>e.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
              <div className="text-sm font-semibold">Settings</div>
              <button onClick={()=>setSettingsOpen(false)} className="rounded-md border border-slate-200 px-2 py-1 text-sm hover:bg-slate-50">Close</button>
            </div>
            <div className="space-y-6 p-6">
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">User ID</label>
                {isAuthenticated ? (
                  <div className="w-full rounded-lg border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-800">
                    {user?.id} (Google ID)
                  </div>
                ) : (
                  <input value={userName} onChange={(e)=>setUserName(e.target.value)} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"/>
                )}
                <div className="mt-1 text-[11px] text-slate-400">
                  {isAuthenticated ? 
                    "Using your authenticated Google ID for consistent message tracking." :
                    "Sign in to use your Google ID, or use a custom name for demo mode."
                  }
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">API Gateway WebSocket URL</label>
                <input value={wsUrl} onChange={(e)=>setWsUrl(e.target.value)} placeholder={ENV_CONFIG.WEBSOCKET_URL || "wss://abc123.execute-api.us-east-1.amazonaws.com/dev"} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"/>
                {ENV_CONFIG.WEBSOCKET_URL && (
                  <div className="mt-1 text-[11px] text-green-600">✓ Default configured for {ENV_CONFIG.ENVIRONMENT}</div>
                )}
                <div className="mt-2 flex items-center gap-2">
                  <button onClick={connect} className="rounded-lg bg-indigo-600 px-3 py-2 text-xs font-medium text-white hover:bg-indigo-700">Connect</button>
                  <button onClick={disconnect} className="rounded-lg border border-slate-200 px-3 py-2 text-xs hover:bg-slate-50">Disconnect</button>
                  <div>{connectionBadge}</div>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">REST Base URL (for chat history)</label>
                <input value={restUrl} onChange={(e)=>setRestUrl(e.target.value)} placeholder={ENV_CONFIG.REST_API_URL || "https://xyz.execute-api.us-east-1.amazonaws.com/dev"} className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"/>
                {ENV_CONFIG.REST_API_URL && (
                  <div className="mt-1 text-[11px] text-green-600">✓ Default configured for {ENV_CONFIG.ENVIRONMENT}</div>
                )}
                <div className="mt-3 rounded-lg border border-slate-200 p-3">
                  <div className="text-xs font-medium text-slate-500">Load history by Session ID</div>
                  <div className="mt-2 flex items-end gap-2">
                    <input value={historyLoadId} onChange={(e)=>setHistoryLoadId(e.target.value)} placeholder="paste session_id…" className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"/>
                    <button disabled={!restUrl || !historyLoadId || loadingHistory} onClick={loadHistory} className={classNames("inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium", (!restUrl||!historyLoadId||loadingHistory)?"bg-slate-200 text-slate-500":"bg-slate-900 text-white hover:bg-slate-800")}>{loadingHistory?<Loader2 className="h-3 w-3 animate-spin"/>:<RefreshCcw className="h-3 w-3"/>} Load</button>
                  </div>
                  <div className="mt-1 text-[11px] text-slate-400">Endpoint: GET {restUrl || "https://your-api-id.execute-api.region.amazonaws.com/dev"}/api/v1/chat/history/{"{"}"session_id"{"}"}</div>
                </div>
              </div>

              <div className="rounded-lg bg-slate-50 p-3 text-[11px] text-slate-500">
                <div className="font-medium">Tips</div>
                <ul className="list-disc pl-4">
                  <li>New chat creates a fresh WebSocket connection so your connect Lambda issues a new session_id.</li>
                  <li>If your backend streams Bedrock tokens, emit {"{"}type:"chunk", text:"…"{"}"} events for smooth typing.</li>
                  <li>To expose this demo, host the static build on CloudFront; route <code>/api/*</code> to your API Gateway and everything else to the site.</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Main App component wrapped with AuthProvider
export default function App() {
  return (
    <AuthProvider>
      <ChatApp />
    </AuthProvider>
  );
}
