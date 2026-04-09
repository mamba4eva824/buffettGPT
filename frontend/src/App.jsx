import { useCallback, useEffect, useMemo, useRef, useState, Suspense, lazy } from "react";
import { Routes, Route, useParams, useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Search, Send, Settings, Loader2, Trash2, MessageSquare, Archive, FolderOpen, X, Menu, ChevronDown, ChevronRight, LogOut, Sun, Moon, PanelLeftClose, BookOpen, HelpCircle, FileText, Shield, Crown, ExternalLink } from "lucide-react";
import SettingsPanel from "./components/SettingsPanel.jsx";
import UpgradeModal from "./components/UpgradeModal.jsx";
import { stripeApi } from "./api/stripeApi.js";
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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
import ValueInsights from "./components/value-insights/ValueInsights.jsx";
import MarketIntelligence from "./components/market-intelligence/MarketIntelligence.jsx";
import EarningsTracker from "./components/earnings-tracker/EarningsTracker.jsx";

// Lazy-loaded waitlist page (code-split)
const WaitlistPage = lazy(() => import("./components/waitlist/WaitlistPage.jsx"));

/*************************
 * Environment Configuration *
 *************************/
const ENV_CONFIG = {
  REST_API_URL: import.meta.env.VITE_REST_API_URL || "",
  APP_NAME: import.meta.env.VITE_APP_NAME || "Buffett",
  ENVIRONMENT: import.meta.env.VITE_ENVIRONMENT || "development",
  ENABLE_DEBUG_LOGS: import.meta.env.VITE_ENABLE_DEBUG_LOGS === "true",
  ENABLE_DEMO_MODE: import.meta.env.VITE_ENABLE_DEMO_MODE === "true",
  ENABLE_WAITLIST: import.meta.env.VITE_ENABLE_WAITLIST === "true",
  DEFAULT_USER_NAME: import.meta.env.VITE_DEFAULT_USER_NAME || "guest"
};

/*************************
 * Local Storage Settings *
 *************************/
const LS_KEYS = {
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
const setLS = (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

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
      <div className={classNames("max-w-[85%] md:max-w-[82%] rounded-2xl px-3 md:px-4 py-2.5 md:py-3 text-sm md:text-[15px] leading-relaxed shadow-sm", isSystem ? "bg-amber-50 dark:bg-amber-900/20 text-amber-900 dark:text-amber-200" : isUser ? "bg-indigo-600 text-white" : "bg-sand-50 dark:bg-warm-900 text-sand-800 dark:text-warm-50")}>
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
  // URL routing
  const { conversationId: urlConversationId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // Get authentication state
  const { user, isAuthenticated, token } = useAuth();

  // Extract first name for personalized greeting
  const userFirstName = user?.name?.split(' ')[0];

  // Refs for auto-scroll functionality
  const messagesEndRef = useRef(null);
  const lastUserMessageRef = useRef(null);
  const chatScrollRef = useRef(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);

  // Refs for rate limit banner timeouts (to prevent memory leaks)
  const showBannerTimeoutRef = useRef(null);
  const hideBannerTimeoutRef = useRef(null);

  // Cache for loaded conversation API responses: { [conversationId]: { conversation, messages, timestamp } }
  const conversationCacheRef = useRef({});

  // Staleness guard: tracks the most recently requested conversation to prevent race conditions
  // when the user rapidly switches between conversations (async responses arriving out of order)
  const latestRequestedConversationRef = useRef(null);

  // Log environment config only once on component mount
  useEffect(() => {
    logger.log('🌍 Environment Config:', ENV_CONFIG);
  }, []);

  const [userName, setUserName] = useState(() => {
    const saved = getLS(LS_KEYS.userName);
    return saved || `${ENV_CONFIG.DEFAULT_USER_NAME}_${uid8()}`;
  });

  // Local sidebar state (simple client-side sessions list for now)
  const [sessions, setSessions] = useState(() => {
    try { return JSON.parse(getLS(LS_KEYS.sessions, "[]")); } catch { return []; }
  });

  // UI state
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [showInvestmentResearch, setShowInvestmentResearch] = useState(false);
  const [appMode, setAppMode] = useState(() => {
    const mode = new URLSearchParams(window.location.search).get('mode');
    return mode === 'value-insights' || mode === 'market-intelligence' || mode === 'earnings-tracker' ? mode : 'chat';
  }); // 'chat' | 'value-insights' | 'market-intelligence'
  const [marketIntelConversationId, setMarketIntelConversationId] = useState(null);
  const [marketIntelMessages, setMarketIntelMessages] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const isConnecting = false; // Simplified - no connection waiting needed for analysis mode
  const [sidebarOpen, setSidebarOpen] = useState(isAuthenticated);
  const [accountDropdownOpen, setAccountDropdownOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    const saved = getLS(LS_KEYS.darkMode);
    // Default to true (warm palette) unless explicitly set to false
    return saved === null ? true : saved === "true";
  });
  const [showRateLimitBanner, setShowRateLimitBanner] = useState(false);
  const [remainingQueries, setRemainingQueries] = useState(() => getRemainingQueries());
  const [hasStartedQuerying, setHasStartedQuerying] = useState(false);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [isCheckoutLoading, setIsCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);
  const [settingsTokenUsage, setSettingsTokenUsage] = useState(null);

  // Research mode state - for unified research view
  const [collapsedSections, setCollapsedSections] = useState([]);
  const [visibleSections, setVisibleSections] = useState([]); // Sections to display (on-demand via ToC clicks)
  const [userExpandedSections, setUserExpandedSections] = useState(['01_executive_summary']); // Only sections user explicitly clicked (persisted)
  const [researchTocWidth] = useState(300);
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
    fetchSection,
    fetchSectionsBatch,
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
    // Token usage tracking
    tokenUsage,
  } = useResearch();

  // Merge token usage from settings fetch (proactive) with SSE updates (reactive)
  // Settings data takes priority when available for freshness on settings open
  const effectiveTokenUsage = settingsTokenUsage || tokenUsage;

  // Company search autocomplete
  const {
    results: searchResults,
    loading: isSearching,
    search: searchCompanies,
    clearResults: clearSearchResults,
  } = useCompanySearch();

  // Handle company search input change
  const handleSearchInputChange = useCallback((value) => {
    // Don't search in follow-up mode (already viewing a report)
    const isInFollowUpMode = showInvestmentResearch && reportMeta && researchTicker;
    if (!isInFollowUpMode) {
      searchCompanies(value);
    }
  }, [showInvestmentResearch, reportMeta, researchTicker, searchCompanies]);

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
    logger.log('[ExecSummary Effect DEBUG] Effect triggered:', {
      currentStreamingSection,
      isResearchStreaming,
      condition1: !!currentStreamingSection,
      condition2: !!isResearchStreaming,
      isExecSummary: currentStreamingSection === '01_executive_summary',
    });

    if (currentStreamingSection && isResearchStreaming) {
      // Only auto-add executive summary - other sections require ToC click
      if (currentStreamingSection === '01_executive_summary') {
        logger.log('[ExecSummary Effect DEBUG] Adding exec summary to all arrays');
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
        logger.log('[ExecSummary Effect DEBUG] Calling logSectionInteraction for exec summary');
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
          sectionEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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
            sectionEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
          }
        }, 100);
      } catch (err) {
        logger.error('Failed to fetch section:', err);
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
    logger.log('[interactionTimeline DEBUG] Computing timeline:', {
      interactionLogLength: interactionLog?.length,
      interactionLogEntries: interactionLog?.map(e => e.id),
      hasExecSummary: interactionLog?.some(e => e.id === '01_executive_summary'),
    });

    if (!showInvestmentResearch || !reportMeta?.toc) return [];

    // If no interaction log, fall back to old behavior (sections first, then follow-ups)
    if (!interactionLog || interactionLog.length === 0) {
      logger.log('[interactionTimeline DEBUG] Using fallback (orderedSections)');
      return [
        ...orderedSections.map(section => ({ type: 'section', data: section })),
        ...followUpMessages.map(msg => ({ type: 'followup', data: msg })),
      ];
    }

    logger.log('[interactionTimeline DEBUG] Using interactionLog path');
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
    loadMoreConversations,
    loadingMore: conversationsLoadingMore,
    hasMore: hasMoreConversations,
    createConversation,
    updateConversation,
    archiveConversation,
    deleteConversation,
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
    logger.log('[ToC Save DEBUG]', {
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
      logger.log('[ToC Save DEBUG] Saving research state to API:', {
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
        logger.log('[ToC Save DEBUG] Save successful for visible_sections:', researchStateToSave.visible_sections);
      }).catch(err => {
        logger.error('Failed to save research state to conversation metadata:', err);
        logger.error('[ToC Save DEBUG] Save FAILED:', err);
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

  // Messages state (WebSocket chat deprecated - now using REST+SSE for research/follow-up)
  const [messages, setMessages] = useState([]);

  // Persist settings
  useEffect(() => { setLS(LS_KEYS.userName, userName); }, [userName]);

  // Sync appMode to URL search params
  useEffect(() => {
    const params = new URLSearchParams(searchParams);
    if (appMode === 'chat') {
      params.delete('mode');
      params.delete('ticker');
      params.delete('tab');
      params.delete('range');
    } else {
      params.set('mode', appMode);
    }
    setSearchParams(params, { replace: true });
  }, [appMode]); // eslint-disable-line react-hooks/exhaustive-deps

  // Dark mode toggle and persistence
  const toggleDarkMode = useCallback(() => {
    setDarkMode(prev => {
      const newValue = !prev;
      setLS(LS_KEYS.darkMode, newValue.toString());
      return newValue;
    });
  }, []);

  // Handle upgrade checkout (used by top-level UpgradeModal)
  const handleUpgradeCheckout = useCallback(async () => {
    if (!token) return;
    setIsCheckoutLoading(true);
    setCheckoutError(null);
    try {
      await stripeApi.redirectToCheckout(token, {
        successUrl: `${window.location.origin}?subscription=success`,
        cancelUrl: `${window.location.origin}?subscription=canceled`
      });
    } catch (err) {
      logger.error('Checkout failed:', err);
      setCheckoutError(err.message || 'Failed to start checkout');
      setIsCheckoutLoading(false);
    }
  }, [token]);

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

  // Auto-scroll to bottom when messages change (skip in research mode to avoid page shift)
  useEffect(() => {
    if (showInvestmentResearch) return;

    const scrollTimeout = setTimeout(() => {
      if (messagesEndRef.current && messages.length > 0) {
        messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
      }
    }, 100);

    return () => clearTimeout(scrollTimeout);
  }, [messages, showInvestmentResearch]);

  // Track scroll position to show/hide "scroll to bottom" button
  const handleChatScroll = useCallback(() => {
    const el = chatScrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollToBottom(distanceFromBottom > 200);
  }, []);

  const scrollToBottom = useCallback(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, []);

  // Auto-open sidebar when user authenticates
  useEffect(() => {
    if (isAuthenticated) {
      setSidebarOpen(true);
    }
  }, [isAuthenticated]);

  // Update conversation title in backend when messages change
  useEffect(() => {
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
  }, [messages, isAuthenticated, selectedConversation, updateConversation]);

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

    // Invalidate cache for current conversation since new messages will be added
    if (selectedConversation?.conversation_id) {
      delete conversationCacheRef.current[selectedConversation.conversation_id];
    }

    // Create conversation if needed (for authenticated users)
    let newConversationId = selectedConversation?.conversation_id;
    if (isAuthenticated && !selectedConversation && messages.length === 0) {
      const title = `Research: ${messageText.slice(0, 40)}${messageText.length > 40 ? '...' : ''}`;
      const newConv = await createConversation(title);
      if (newConv) {
        setSelectedConversation(newConv);
        navigate(`/c/${newConv.conversation_id}`, { replace: true });
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

    // Use ticker from autocomplete if set, otherwise use the message text
    const extractedCompany = tickerFromAutocomplete || messageText;

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
    setCollapsedSections([]); // Reset collapsed state for new research
    setUserExpandedSections(['01_executive_summary']); // Reset user-clicked sections for new research
    setVisibleSections(['01_executive_summary']); // Auto-show executive summary
    // Track which conversation this research state belongs to (prevents cross-contamination on switch)
    researchStateConversationRef.current = newConversationId;
    lastSavedInteractionLogLengthRef.current = 1; // Start at 1 (exec summary added below)

    // Start the research stream
    startResearch(extractedCompany, token);

    // CRITICAL FIX: Add exec summary to interactionLog immediately after research starts
    logSectionInteraction('01_executive_summary');

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
  }, [input, isAuthenticated, selectedConversation, messages.length, createConversation, setSelectedConversation, navigate, startResearch, token, showInvestmentResearch, reportMeta, researchTicker, sendFollowUp, clearFollowUp, logSectionInteraction]);

  const newChat = useCallback(() => {
    setMessages([]);
    setShowInvestmentResearch(false);

    // Reset research state (includes clearing follow-up)
    resetResearch();
    setCollapsedSections([]);
    setUserExpandedSections(['01_executive_summary']);
    setVisibleSections([]);

    // Clear market intelligence state
    setMarketIntelConversationId(null);
    setMarketIntelMessages(null);

    // Clear selection - conversation will be created in doSend when user submits a company
    setSelectedConversation(null);
  }, [setMessages, setSelectedConversation, resetResearch]);

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

    // Mark this as the latest requested conversation (staleness guard)
    latestRequestedConversationRef.current = conversationId;

    try {
      // Check cache for previously loaded conversation data
      const cached = conversationCacheRef.current[conversationId];
      let conversation, messages;

      if (cached) {
        // Use cached data immediately for instant UI
        conversation = cached.conversation;
        messages = cached.messages;

        // Background revalidation: fetch fresh data and update cache silently
        loadConversationHistory(conversationId, token).then(fresh => {
          conversationCacheRef.current[conversationId] = {
            conversation: fresh.conversation,
            messages: fresh.messages,
            timestamp: Date.now()
          };
        }).catch(() => { /* background refresh failed, cached data still valid */ });
      } else {
        // No cache — fetch from API
        const result = await loadConversationHistory(conversationId, token);
        conversation = result.conversation;
        messages = result.messages;

        // Store in cache
        conversationCacheRef.current[conversationId] = {
          conversation, messages, timestamp: Date.now()
        };
      }

      // Staleness check #1: bail out if user has already clicked a different conversation
      if (latestRequestedConversationRef.current !== conversationId) return;

      // DEBUG: Log raw API response to trace visible_sections persistence issue
      logger.log('[ToC Load DEBUG] loadConversationHistory response:', {
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
            // Handle both number and string timestamps (DynamoDB Decimal comes as string)
            const tsValue = typeof m.timestamp === 'string' ? parseFloat(m.timestamp) : m.timestamp;
            if (!isNaN(tsValue)) {
              // Determine if timestamp is in seconds or milliseconds
              // Milliseconds will be 13+ digits (> 10000000000)
              const msTimestamp = tsValue > 10000000000 ? tsValue : tsValue * 1000;
              timestamp = new Date(msTimestamp).toISOString();
            } else {
              // Assume it's already an ISO string timestamp
              timestamp = m.timestamp;
            }
          }

          return {
            id: m.message_id || uid8(),
            type: m.message_type || "user",
            content: m.content || "",
            timestamp: timestamp,
            metadata: m.metadata || null,
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

      // Check if this is a Research conversation (title prefix OR metadata contains research_state)
      const isResearchConversation = (conversationTitle &&
        conversationTitle.toLowerCase().startsWith('research:')) ||
        !!conversation?.metadata?.research_state;

      if (isResearchConversation) {
        // NEW: Check conversation metadata first for research state
        const researchState = conversation?.metadata?.research_state;
        let savedResearchData = null;

        // DEBUG: Log raw conversation object to see what's coming from API
        logger.log('[ToC Load DEBUG] Raw conversation from API:', {
          conversation_id: conversation?.conversation_id,
          metadata: conversation?.metadata,
          metadata_research_state: conversation?.metadata?.research_state,
          metadata_keys: conversation?.metadata ? Object.keys(conversation.metadata) : 'no metadata',
        });

        if (researchState) {
          // Found research state in conversation metadata (new format)
          logger.log('[ToC Load DEBUG] Found research state in metadata:', {
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
                  logger.log('[ToC Load DEBUG] Found saved research message (legacy)', foundCount, 'activeSectionId:', data.activeSectionId, 'savedAt:', data.savedAt);
                  savedResearchData = data;
                  // Don't break - continue to find the most recent message
                }
              } catch (e) {
                // Not valid JSON, continue
              }
            }
          }
        }

        logger.log('[ToC Load DEBUG] Final savedResearchData activeSectionId:', savedResearchData?.activeSectionId);

        // Parse follow-up messages from conversation history
        // Detect follow-ups by: (1) JSON content with _type field (legacy), or
        // (2) metadata.source === 'investment_research_followup' (current backend format)
        const savedFollowUpMessages = formattedMessages
          .filter(msg => {
            // Current format: backend saves plain text with metadata.source
            if (msg.metadata?.source === 'investment_research_followup') {
              return true;
            }
            // Legacy format: JSON content with _type field
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
            // Current format: plain text content with metadata
            if (msg.metadata?.source === 'investment_research_followup') {
              return {
                id: msg.id || `msg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
                type: msg.type,
                content: msg.content,
                isStreaming: false,
                timestamp: msg.timestamp,
              };
            }
            // Legacy format: JSON content
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
          // Clean up previous state before entering research view
          // (moved from onSelectConversation to avoid intermediate layout flash)
          setCollapsedSections([]);
          setUserExpandedSections(['01_executive_summary']);
          setVisibleSections([]);
          researchStateConversationRef.current = null;

          // Set up research view
          setShowInvestmentResearch(true);

          // Determine format type
          const isReferenceFormat = savedResearchData?._type === 'research_report_ref';
          const isLegacyFormat = savedResearchData?._type === 'research_report' && savedResearchData?.streamedContent;

          if (isReferenceFormat) {
            // NEW FORMAT: Reference-only - fetch sections on-demand from investment_reports_v2
            // Use length check instead of || to handle empty array (which is truthy but should default)
            logger.log('[ToC Load DEBUG] isReferenceFormat - computing savedVisibleSections:', {
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
            logger.log('[ToC Load DEBUG] Computed savedVisibleSections:', savedVisibleSections);
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

            // Load metadata first, then batch fetch sections (replaces checkReportStatus + N individual fetches)
            setUserExpandedSections(savedVisibleSections);
            setVisibleSections(savedVisibleSections);
            setCollapsedSections([...savedVisibleSections]);

            loadSavedReport({
              ticker: ticker,
              reportMeta: savedResearchData.reportMeta,
              streamedContent: {},  // Empty - batch fetch will populate
              activeSectionId: savedActiveSectionId,
              followUpMessages: savedFollowUpMessages,
              interactionLog: savedInteractionLog,
            });
            researchStateConversationRef.current = conversationId;
            lastSavedInteractionLogLengthRef.current = savedInteractionLog.length;
            lastSavedSectionsRef.current = savedVisibleSections.length;

            // Single batch fetch: gets all sections + report_exists in one request
            try {
              const batchResult = await fetchSectionsBatch(ticker, savedVisibleSections, token);

              // Staleness check #2: bail out if user switched conversations during batch fetch
              if (latestRequestedConversationRef.current !== conversationId) return;

              if (!batchResult.report_exists) {
                // Report expired or doesn't exist — metadata is still shown, sections will be empty
                logger.warn(`Report for ${ticker} not found or expired`);
              } else {
                // Scroll to restored active section after content loads
                setTimeout(() => {
                  const sectionEl = document.getElementById(`section-${savedActiveSectionId}`);
                  if (sectionEl) {
                    sectionEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                  }
                }, 150);
              }
            } catch (err) {
              logger.error('Error batch fetching sections:', err);
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
                sectionEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
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

          // Filter out the research report JSON messages and follow-up messages from display
          // Follow-ups are rendered in the interactionTimeline at the bottom, not as regular messages
          const displayMessages = formattedMessages.filter(msg => {
            // Current format: follow-ups saved with metadata.source by backend
            if (msg.metadata?.source === 'investment_research_followup') {
              return false;
            }
            // Legacy format: JSON content with _type field
            if (msg.content?.startsWith('{')) {
              try {
                const data = JSON.parse(msg.content);
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

      // Check if this is a Market Intelligence conversation
      const isMarketIntelConversation =
        conversation?.metadata?.type === 'market-intelligence' ||
        (conversationTitle && conversationTitle.startsWith('MI:'));

      if (isMarketIntelConversation) {
        resetResearch();
        setShowInvestmentResearch(false);
        setAppMode('market-intelligence');
        setMarketIntelConversationId(conversationId);
        setMarketIntelMessages(formattedMessages);
        setMessages([]);
        return;
      }

      // Regular conversation (including legacy "Analysis:" conversations) - show messages as chat
      // Clean up research state to avoid stale data from previous research conversation
      resetResearch();
      setCollapsedSections([]);
      setUserExpandedSections(['01_executive_summary']);
      setVisibleSections([]);
      researchStateConversationRef.current = null;
      setShowInvestmentResearch(false);
      setMessages(formattedMessages);
    } catch (error) {
      logger.error('Error loading conversation messages:', error);
      // Don't alert on error, just log it
    }
  }, [token, setMessages, startResearch, loadSavedReport, fetchSection, fetchSectionsBatch, setInteractionLog, resetResearch]);

  // Sync URL → conversation state
  // Fires on: initial mount with /c/:id, browser back/forward, navigate() calls
  // Sparse dep array is intentional — adding selectedConversation/conversations would cause infinite loops
  useEffect(() => {
    if (!urlConversationId) {
      // URL is "/" — new chat mode
      if (selectedConversation) {
        newChat();
      }
      return;
    }

    // URL has a conversation ID — load if different from current
    if (urlConversationId !== selectedConversation?.conversation_id) {
      const conv = conversations.find(c => c.conversation_id === urlConversationId);
      if (conv) {
        setSelectedConversation(conv);
        loadConversationMessages(urlConversationId, conv.title);
      } else if (token) {
        // Deep link or conversation not yet in sidebar list
        setSelectedConversation({ conversation_id: urlConversationId, title: '' });
        loadConversationMessages(urlConversationId);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlConversationId, token]);

  return (
    <div className="h-screen w-screen overflow-hidden bg-sand-50 dark:bg-warm-950 text-sand-800 dark:text-warm-50">
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
              "shrink-0 border-r border-transparent hover:border-indigo-400 dark:hover:border-indigo-400 transition-all duration-300 ease-in-out",
              // Mobile: fixed overlay that slides in from left
              "fixed inset-y-0 left-0 z-50 bg-sand-50 dark:bg-warm-950",
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
                    onClick={() => navigate('/')}
                    className="text-xs tracking-[0.35em] text-sand-600 dark:text-warm-200 font-semibold hover:text-indigo-600 transition-colors cursor-pointer"
                    title="Start new chat"
                  >
                    {ENV_CONFIG.APP_NAME.toUpperCase()}
                  </button>
                  <button
                    onClick={() => setSidebarOpen(false)}
                    className="rounded-md p-1 text-sand-400 hover:bg-sand-100 hover:text-sand-600"
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
                    className="rounded-md p-2 text-sand-400 hover:bg-sand-100 dark:hover:bg-warm-800 hover:text-sand-600 dark:hover:text-warm-200"
                    title="Open sidebar"
                  >
                    <Menu className="h-4 w-4" />
                  </button>
                  <button
                    onClick={() => navigate('/')}
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
                    className="rounded-md p-2 text-sand-400 hover:bg-sand-100 dark:hover:bg-warm-800 hover:text-sand-600 dark:hover:text-warm-200"
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
                    <Avatar
                      src={user?.picture || ''}
                      alt={user?.name || user?.email || 'User'}
                      size="w-8 h-8"
                    />
                  </button>
                </div>
              </>
            )}

            {sidebarOpen && (
              <div className="flex flex-col h-full pb-4">
            <div className="flex items-center justify-center gap-2">
              <button onClick={() => navigate('/')} className="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white shadow-lg hover:bg-indigo-700 hover:shadow-indigo-200 dark:hover:shadow-warm-900/30 transition-all">
                <Plus className="h-4 w-4"/> New Analysis
              </button>
            </div>

            <div className="mt-4 h-8 flex items-center gap-2 rounded-full border border-transparent bg-sand-50/90 dark:bg-warm-900/50 backdrop-blur-sm px-3 hover:border-indigo-400 dark:hover:border-indigo-400 focus-within:border-indigo-400 dark:focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/30 transition-all">
              <Search className="h-3.5 w-3.5 text-sand-400"/>
              <input value={search} onChange={(e)=>setSearch(e.target.value)} placeholder="Search" className="w-full bg-transparent text-xs outline-none placeholder:text-sand-400 dark:placeholder:text-warm-400"/>
            </div>


            <div className="mt-6 relative flex items-center">
              <div className="text-xs uppercase tracking-wide text-sand-400">
                {isAuthenticated ? 'Financial Advice' : 'Local Sessions'}
              </div>
              {isAuthenticated && (
                <button
                  onClick={() => setShowArchived(!showArchived)}
                  className={classNames(
                    "absolute right-0 rounded-md p-1 text-xs",
                    showArchived
                      ? "text-indigo-600 hover:bg-indigo-50"
                      : "text-sand-400 hover:bg-sand-50"
                  )}
                  title={showArchived ? "Show active" : "Show archived"}
                >
                  {showArchived ? <FolderOpen className="h-4 w-4" /> : <Archive className="h-4 w-4" />}
                </button>
              )}
            </div>

            <div className="mt-2 space-y-1 overflow-y-auto pr-1 pb-4 scrollbar-thin scrollbar-track-transparent scrollbar-thumb-sand-300 dark:scrollbar-thumb-warm-700" style={{ maxHeight: 'calc(100vh - 280px)' }}>
              {/* Show conversation list for authenticated users */}
              {isAuthenticated ? (
                <ConversationList
                  conversations={conversations.filter(c =>
                    c.title?.toLowerCase().includes(search.toLowerCase())
                  )}
                  selectedConversation={selectedConversation}
                  onSelectConversation={(conv) => {
                    navigate(`/c/${conv.conversation_id}`);
                  }}
                  onUpdateConversation={updateConversation}
                  onArchiveConversation={async (convId) => {
                    const wasSelected = selectedConversation?.conversation_id === convId;
                    await archiveConversation(convId);
                    if (wasSelected) navigate('/', { replace: true });
                  }}
                  onDeleteConversation={async (convId) => {
                    const wasSelected = selectedConversation?.conversation_id === convId;
                    await deleteConversation(convId);
                    if (wasSelected) navigate('/', { replace: true });
                  }}
                  showArchived={showArchived}
                  loading={conversationsLoading}
                  onLoadMore={loadMoreConversations}
                  loadingMore={conversationsLoadingMore}
                  hasMore={hasMoreConversations}
                />
              ) : (
                /* Show local sessions for non-authenticated users or local tab */
                <>
                  {sessions.filter(s => s.title?.toLowerCase().includes(search.toLowerCase())).map((s) => (
                    <div key={s.id} className="group flex items-center justify-between rounded-lg px-2 py-2 hover:bg-sand-50">
                      <div className="flex min-w-0 items-center gap-2">
                        <MessageSquare className="h-4 w-4 shrink-0 text-sand-400"/>
                        <div className="min-w-0">
                          <div className="truncate text-sm text-sand-700">{s.title || s.id}</div>
                          <div className="truncate text-[11px] text-sand-400">{new Date(s.updatedAt || s.createdAt).toLocaleString()}</div>
                        </div>
                      </div>
                      <button onClick={()=>removeSession(s.id)} className="invisible ml-2 rounded-md p-1 text-sand-300 hover:bg-sand-100 hover:text-sand-600 group-hover:visible" title="Remove">
                        <Trash2 className="h-4 w-4"/>
                      </button>
                    </div>
                  ))}
                  {sessions.length === 0 && (
                    <div className="rounded-lg border border-dashed border-sand-200 p-3 text-center text-xs text-sand-500">
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
                subscriptionTier={effectiveTokenUsage?.subscription_tier || 'free'}
                onPlanClick={() => {
                  const tier = effectiveTokenUsage?.subscription_tier || 'free';
                  if (tier !== 'plus') {
                    setShowUpgradeModal(true);
                  } else {
                    setSettingsOpen(true);
                  }
                }}
              />
            </div>
              </div>
            )}
          </aside>
          )}

          {/* Main panel */}
          <main className="relative flex min-w-0 flex-1 flex-col min-h-0 overflow-hidden">
            {/* Header - minimal, only for mobile menu and non-authenticated users */}
            <div className="flex items-center justify-between px-4 md:px-6 py-2">
              <div className="flex items-center gap-2 md:gap-3">
                {/* Mobile hamburger menu - only show on mobile when authenticated */}
                {isAuthenticated && (
                  <button
                    onClick={() => setSidebarOpen(true)}
                    className="md:hidden rounded-md p-2 text-sand-600 dark:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800 transition-colors"
                    title="Open menu"
                  >
                    <Menu className="h-5 w-5" />
                  </button>
                )}
              </div>

              {/* Mode pill toggle — Chat / Value Insights / Market Intelligence */}
              <div className="flex items-center bg-sand-200 dark:bg-warm-800 rounded-full p-1 gap-1">
                <button
                  onClick={() => {
                    setAppMode('chat');
                    setMarketIntelConversationId(null);
                    setMarketIntelMessages(null);
                  }}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
                    appMode === 'chat'
                      ? 'bg-white dark:bg-warm-600 text-sand-900 dark:text-warm-50 shadow-sm'
                      : 'text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100'
                  }`}
                >
                  Chat
                </button>
                <button
                  onClick={() => setAppMode('value-insights')}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
                    appMode === 'value-insights'
                      ? 'bg-white dark:bg-warm-600 text-sand-900 dark:text-warm-50 shadow-sm'
                      : 'text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100'
                  }`}
                >
                  Value Insights
                </button>
                <button
                  onClick={() => {
                    setAppMode('market-intelligence');
                    if (appMode !== 'market-intelligence') {
                      setMarketIntelConversationId(null);
                      setMarketIntelMessages(null);
                    }
                  }}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
                    appMode === 'market-intelligence'
                      ? 'bg-white dark:bg-warm-600 text-sand-900 dark:text-warm-50 shadow-sm'
                      : 'text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100'
                  }`}
                >
                  Market Intel
                </button>
                <button
                  onClick={() => setAppMode('earnings-tracker')}
                  className={`px-4 py-1.5 rounded-full text-xs font-semibold tracking-wide transition-all ${
                    appMode === 'earnings-tracker'
                      ? 'bg-white dark:bg-warm-600 text-sand-900 dark:text-warm-50 shadow-sm'
                      : 'text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100'
                  }`}
                >
                  Earnings
                </button>
              </div>

              <div className="flex items-center gap-2">
                {/* Account dropdown moved to sidebar - show login button for non-authenticated users */}
                {!isAuthenticated && (
                  <AccountDropdown
                    isOpen={accountDropdownOpen}
                    onToggle={setAccountDropdownOpen}
                    onSettingsClick={() => setSettingsOpen(true)}
                    darkMode={darkMode}
                    onDarkModeToggle={toggleDarkMode}
                    subscriptionTier={effectiveTokenUsage?.subscription_tier || 'free'}
                    onPlanClick={() => {
                      const tier = effectiveTokenUsage?.subscription_tier || 'free';
                      if (tier !== 'plus') {
                        setShowUpgradeModal(true);
                      } else {
                        setSettingsOpen(true);
                      }
                    }}
                  />
                )}
              </div>
            </div>

            {/* Dynamic Layout Based on Mode */}
            {appMode === 'market-intelligence' ? (
              /* MARKET INTELLIGENCE MODE */
              <div className="flex-1 flex flex-col overflow-hidden min-h-0">
                <MarketIntelligence
                  conversationId={marketIntelConversationId}
                  initialMessages={marketIntelMessages}
                  createConversation={createConversation}
                  onConversationCreated={(newConv) => {
                    setMarketIntelConversationId(newConv.conversation_id);
                    setSelectedConversation(newConv);
                    navigate(`/c/${newConv.conversation_id}`, { replace: true });
                  }}
                />
              </div>
            ) : appMode === 'value-insights' ? (
              /* VALUE INSIGHTS MODE */
              <div className="flex-1 flex flex-col overflow-hidden min-h-0">
                <ValueInsights />
              </div>
            ) : appMode === 'earnings-tracker' ? (
              /* EARNINGS TRACKER MODE */
              <div className="flex-1 flex flex-col overflow-hidden min-h-0">
                <EarningsTracker
                  onNavigateToInsights={(ticker) => {
                    const params = new URLSearchParams(searchParams);
                    params.set('mode', 'value-insights');
                    params.set('ticker', ticker);
                    params.set('tab', 'earnings_performance');
                    setSearchParams(params, { replace: true });
                    setAppMode('value-insights');
                  }}
                  isAuthenticated={isAuthenticated}
                  token={token}
                />
              </div>
            ) : messages.length === 0 && !showInvestmentResearch ? (
              /* CENTERED LAYOUT - No messages (landing, auth, new chat) */
              <div className="flex-1 flex flex-col overflow-hidden min-h-0">
                <div className="flex-1 flex flex-col items-center justify-center px-4 md:px-6 pb-24">
                  <div className="text-center mb-8">
                    <div className="text-sand-400 dark:text-warm-50 text-3xl font-medium">
                      Welcome{isAuthenticated && userFirstName ? `, ${userFirstName}` : ''} to {ENV_CONFIG.APP_NAME}
                    </div>
                  </div>

                  <div className="w-full max-w-3xl">
                    <SearchComposer
                      input={input}
                      setInput={setInput}
                      doSend={doSend}
                      isConnecting={isConnecting}
                      searchResults={searchResults}
                      isSearching={isSearching}
                      onResultSelect={handleCompanySelect}
                      onInputChange={handleSearchInputChange}
                    />
                  </div>
                </div>
              </div>
            ) : (
              /* SPLIT LAYOUT - Messages exist (active conversation) */
              <>
                {/* Research or Chat Area */}
                {showInvestmentResearch ? (
                  /* RESEARCH MODE - Uses dedicated ResearchLayout */
                  <ResearchLayout
                    ticker={researchTicker}
                    reportMeta={reportMeta}
                    streamedContent={streamedContent}
                    activeSectionId={activeSectionId}
                    currentStreamingSection={currentStreamingSection}
                    isStreaming={isResearchStreaming}
                    streamStatus={streamStatus}
                    error={researchError}
                    progress={researchProgress}
                    tocWidth={researchTocWidth}
                    visibleSections={visibleSections}
                    onSectionClick={handleTocSectionClick}
                    onClose={() => {
                      setShowInvestmentResearch(false);
                      resetResearch();
                      setVisibleSections([]);
                    }}
                    onRetry={() => {
                      startResearch(researchTicker, token);
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
                          <div key={`section-${section.section_id}`} id={`section-${section.section_id}`} className="mx-auto w-full max-w-3xl">
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
                          <div key={`followup-${msg.id}`} className="mx-auto w-full max-w-3xl">
                            {isFirstFollowup && (
                              <div className="mt-6 pt-6 border-t border-sand-200 dark:border-warm-800">
                                <div className="text-xs uppercase tracking-wide text-sand-400 dark:text-warm-400 mb-4 px-4">
                                  Follow-up Questions
                                </div>
                              </div>
                            )}
                            <div className="mb-4 px-4">
                              {msg.type === 'user' ? (
                                <div className="flex justify-end">
                                  <div className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-100 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 rounded-full text-sm max-w-[80%]">
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
                                  <div className="flex-1 bg-sand-50 dark:bg-warm-900 rounded-xl p-4 text-sm prose prose-sm dark:prose-invert max-w-none prose-headings:font-semibold prose-h2:text-lg prose-h3:text-base prose-p:text-sand-700 dark:prose-p:text-warm-200 prose-li:text-sand-700 dark:prose-li:text-warm-200 prose-strong:text-sand-900 dark:prose-strong:text-warm-50 prose-table:text-xs prose-th:bg-sand-100 dark:prose-th:bg-warm-800 prose-th:p-2 prose-td:p-2 relative">
                                    {/* Collapse/Expand button */}
                                    {!msg.isStreaming && hasMoreContent && (
                                      <button
                                        onClick={() => toggleFollowUpCollapse(msg.id)}
                                        className="absolute top-2 right-2 text-xs text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-100 transition-colors flex items-center gap-1 bg-sand-100 dark:bg-warm-700 px-2 py-1 rounded-md"
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
                                        <div className="text-sand-400 dark:text-warm-400 text-xs mt-2 italic">
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
                      <div className="flex items-center justify-center h-32 text-sand-400 dark:text-warm-400">
                        <p>Loading research report...</p>
                      </div>
                    )}

                    {/* Follow-up streaming indicator */}
                    {isFollowUpStreaming && followUpMessages.length === 0 && (
                      <div className="mx-auto w-full max-w-3xl mt-4 px-4">
                        <div className="flex gap-3">
                          <div className="h-7 w-7 shrink-0">
                            <img
                              src="/buffett-memoji.png"
                              alt="Assistant"
                              className="w-full h-full rounded-full"
                            />
                          </div>
                          <div className="text-sand-400 dark:text-warm-400 text-sm">
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
                  <div className="flex-1 flex min-h-0 relative">
                    <div ref={chatScrollRef} onScroll={handleChatScroll} className="flex-1 overflow-y-auto px-4 md:px-6 py-4 transition-all duration-300 ease-in-out scrollbar-thin scrollbar-track-transparent scrollbar-thumb-sand-300 dark:scrollbar-thumb-warm-700">
                      <div className="mx-auto max-w-4xl space-y-4">
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

                        {/* Invisible element at the end for auto-scrolling */}
                        <div ref={messagesEndRef} />
                      </div>
                    </div>

                    {/* Scroll to bottom button */}
                    {showScrollToBottom && messages.length > 0 && (
                      <button
                        onClick={scrollToBottom}
                        className="absolute bottom-4 left-1/2 -translate-x-1/2 z-10 rounded-full bg-sand-100 dark:bg-warm-800 border border-sand-200 dark:border-warm-700 shadow-md px-3 py-1.5 text-xs font-medium text-sand-600 dark:text-warm-200 hover:bg-sand-200 dark:hover:bg-warm-700 transition-all"
                        aria-label="Scroll to bottom"
                      >
                        <ChevronDown className="h-4 w-4 inline-block mr-1" />
                        New messages
                      </button>
                    )}
                  </div>
                )}

                {/* Bottom Composer - visible for regular chat (not analysis or research mode) */}
                {!showInvestmentResearch && (
                <div className="border-t border-sand-100 dark:border-warm-800 p-4 md:p-4 pb-6 md:pb-4 transition-all duration-300 ease-in-out">
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
      <SettingsPanel
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        user={user}
        isAuthenticated={isAuthenticated}
        userName={userName}
        onUserNameChange={setUserName}
        tokenUsage={effectiveTokenUsage}
        token={token}
        showUpgradeModal={showUpgradeModal}
        onShowUpgradeModalChange={setShowUpgradeModal}
        onTokenUsageUpdate={setSettingsTokenUsage}
      />

      {/* Top-level Upgrade Modal (shown directly from Upgrade Plan button) */}
      <UpgradeModal
        isOpen={showUpgradeModal && !settingsOpen}
        onClose={() => {
          setShowUpgradeModal(false);
          setCheckoutError(null);
          setIsCheckoutLoading(false);
        }}
        onUpgrade={handleUpgradeCheckout}
        isLoading={isCheckoutLoading}
        error={checkoutError}
      />
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
    <div className={`mx-auto max-w-4xl mb-4 px-4 transform transition-all duration-1000 ease-in-out ${
      isVisible ? 'translate-y-0 opacity-100' : 'translate-y-8 opacity-0'
    }`}>
      <div className="flex items-center justify-between px-4 py-3 bg-sand-50 dark:bg-warm-900 rounded-lg text-white text-sm shadow-sm">
        <div className="flex items-center gap-2">
          {getMessage()}
        </div>
        <button
          onClick={onClose}
          className="text-sand-300 hover:text-white ml-4"
        >
          <X className="h-4 w-4" />
        </button>
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
  suggestions = [],
  onSuggestionClick,
  suggestionsLoading = false,
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
        <div className="relative flex items-center rounded-full border border-sand-200/80 dark:border-warm-800/50 bg-sand-50/90 dark:bg-warm-900/80 backdrop-blur-xl shadow-lg px-5 py-2.5 focus-within:border-indigo-400 dark:focus-within:border-indigo-400 focus-within:ring-2 focus-within:ring-indigo-100 dark:focus-within:ring-indigo-900/30 transition-all">
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
            className="peer block w-full bg-transparent text-sm md:text-[15px] placeholder:text-sand-400 dark:placeholder:text-warm-400 focus:outline-none dark:text-warm-50"
            autoComplete="off"
          />

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
            className="absolute z-50 w-full mt-2 py-2 bg-sand-50 dark:bg-warm-950 rounded-xl border border-sand-200 dark:border-warm-800 shadow-xl max-h-64 overflow-y-auto"
          >
            {isSearching ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-indigo-500" />
                <span className="ml-2 text-sm text-sand-500 dark:text-warm-300">Searching...</span>
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
                      ? "bg-indigo-50 dark:bg-indigo-900/20"
                      : "hover:bg-sand-50 dark:hover:bg-warm-800/50"
                  )}
                >
                  <span className="font-semibold text-indigo-600 dark:text-indigo-400 min-w-[60px]">
                    {result.ticker}
                  </span>
                  <span className="text-sm text-sand-600 dark:text-warm-200 truncate flex-1">
                    {result.name}
                  </span>
                  {result.has_report && (
                    <span className="flex-shrink-0 text-[10px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/30 px-1.5 py-0.5 rounded-full">
                      Report
                    </span>
                  )}
                </button>
              ))
            ) : input.trim().length > 0 ? (
              <div className="px-4 py-3 text-sm text-sand-500 dark:text-warm-300 text-center">
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
                className="px-4 py-2.5 text-sm text-sand-600 dark:text-warm-300 bg-sand-50 dark:bg-warm-950 rounded-full border border-sand-200 dark:border-warm-800 hover:border-indigo-500 hover:text-indigo-600 dark:hover:text-indigo-400 hover:scale-105 transition-all duration-200 whitespace-nowrap flex-shrink-0"
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
        <div className="text-sand-400 dark:text-warm-400">
          <Moon className="h-4 w-4" />
        </div>
        <button
          onClick={onToggle}
          className={classNames(
            "relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:ring-offset-2",
            darkMode ? "bg-indigo-600" : "bg-sand-200"
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
        <div className="text-sand-400 dark:text-warm-400">
          <Sun className="h-4 w-4" />
        </div>
      </div>
      <span className="text-sm text-sand-700 dark:text-warm-200 font-medium">
        Light Mode
      </span>
    </div>
  );
}

// Account Dropdown Component
function AccountDropdown({ isOpen, onToggle, onSettingsClick, darkMode, onDarkModeToggle, dropdownPosition = "bottom", subscriptionTier = "free", onPlanClick }) {
  const { user, isAuthenticated, logout } = useAuth();
  const dropdownRef = useRef(null);
  const [learnMoreOpen, setLearnMoreOpen] = useState(false);

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
        className="flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors w-full"
      >
        {isAuthenticated && user ? (
          <>
            <Avatar
              src={user?.picture || ''}
              alt={user?.name || user?.email || 'User'}
              size="w-6 h-6"
            />
            <span className="text-sm font-medium text-sand-700 dark:text-warm-50 truncate">{user?.name || user?.email || 'User'}</span>
          </>
        ) : (
          <>
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-sand-700 dark:text-warm-50">Log In</span>
              <span className="text-xs text-sand-500 dark:text-warm-300">/ Sign up for free</span>
            </div>
          </>
        )}
        <ChevronDown className={classNames(
          "h-4 w-4 text-sand-400 transition-transform ml-auto",
          isOpen ? "rotate-180" : ""
        )} />
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className={classNames(
          "absolute w-56 bg-sand-50 dark:bg-warm-950 border border-sand-200 dark:border-warm-800 rounded-lg shadow-lg z-50 transition-all duration-200",
          dropdownPosition === "top"
            ? "bottom-full mb-3 left-0"
            : "top-full mt-2 right-0"
        )}>
          {isAuthenticated && user ? (
            <>
              {/* User Info Header */}
              <div className="px-4 py-3 border-b border-sand-100 dark:border-warm-800">
                <div className="flex items-center gap-3">
                  <Avatar
                    src={user?.picture || ''}
                    alt={user?.name || user?.email || 'User'}
                    size="w-8 h-8"
                  />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-sand-900 dark:text-warm-50 truncate">{user?.name || user?.email || 'User'}</div>
                    <div className="text-xs text-sand-500 dark:text-warm-300 truncate">{user?.email || ''}</div>
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
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors"
                >
                  <Settings className="h-4 w-4" />
                  Settings
                </button>
                <button
                  onClick={() => {
                    onPlanClick?.();
                    onToggle(false);
                  }}
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors"
                >
                  <Crown className="h-4 w-4" />
                  {subscriptionTier === 'plus' ? 'Manage Plan' : 'Upgrade Plan'}
                </button>
                <div className="relative">
                  <button
                    onClick={() => setLearnMoreOpen(!learnMoreOpen)}
                    className="flex items-center gap-3 w-full px-4 py-2 text-sm text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors"
                  >
                    <BookOpen className="h-4 w-4" />
                    <span className="flex-1 text-left">Learn More</span>
                    <ChevronRight className={classNames(
                      "h-3.5 w-3.5 text-sand-400 transition-transform duration-200",
                      learnMoreOpen ? "rotate-90" : ""
                    )} />
                  </button>
                  {learnMoreOpen && (
                    <div className="absolute left-full top-0 ml-1 w-48 bg-sand-50 dark:bg-warm-950 border border-sand-200 dark:border-warm-800 rounded-lg shadow-lg py-1 z-50">
                      <a
                        href="#"
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => { e.preventDefault(); onToggle(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-sand-600 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-800 transition-colors"
                      >
                        <Shield className="h-3.5 w-3.5" />
                        <span className="flex-1">Privacy Policy</span>
                        <ExternalLink className="h-3 w-3 text-sand-400 dark:text-warm-500" />
                      </a>
                      <a
                        href="#"
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => { e.preventDefault(); onToggle(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-sand-600 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-800 transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        <span className="flex-1">Terms of Service</span>
                        <ExternalLink className="h-3 w-3 text-sand-400 dark:text-warm-500" />
                      </a>
                      <a
                        href="#"
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => { e.preventDefault(); onToggle(false); }}
                        className="flex items-center gap-2.5 w-full px-3 py-2 text-xs text-sand-600 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-800 transition-colors"
                      >
                        <FileText className="h-3.5 w-3.5" />
                        <span className="flex-1">Data Disclaimer</span>
                        <ExternalLink className="h-3 w-3 text-sand-400 dark:text-warm-500" />
                      </a>
                    </div>
                  )}
                </div>
                <a
                  href="#"
                  onClick={(e) => { e.preventDefault(); onToggle(false); }}
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors"
                >
                  <HelpCircle className="h-4 w-4" />
                  Get Help
                </a>
                <button
                  onClick={() => {
                    logout();
                    onToggle(false);
                  }}
                  className="flex items-center gap-3 w-full px-4 py-2 text-sm text-sand-700 dark:text-warm-200 hover:bg-sand-50 dark:hover:bg-warm-800 transition-colors"
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
  const [showWaitlist, setShowWaitlist] = useState(() => {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.has('ref')
      || window.location.hash.includes('waitlist')
      || ENV_CONFIG.ENABLE_WAITLIST;
  });

  if (showWaitlist) {
    return (
      <Suspense fallback={<div className="min-h-screen bg-sand-50 dark:bg-warm-950" />}>
        <WaitlistPage onEnterApp={() => setShowWaitlist(false)} />
      </Suspense>
    );
  }

  return (
    <AuthProvider>
      <ResearchProvider>
        <Routes>
          <Route path="/c/:conversationId" element={<ChatApp />} />
          <Route path="*" element={<ChatApp />} />
        </Routes>
      </ResearchProvider>
    </AuthProvider>
  );
}
