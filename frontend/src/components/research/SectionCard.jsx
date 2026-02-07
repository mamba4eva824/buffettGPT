import React, { useEffect, useRef, useState, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, FileText, ArrowDown } from 'lucide-react';
import {
  Zap,
  Building2,
  Heart,
  DollarSign,
  Shield,
  TrendingUp,
  Percent,
  BarChart3,
  Gem,
  Users,
  Target,
  Rocket,
  AlertTriangle,
  MessageSquare
} from 'lucide-react';
import useTypewriter from '../../hooks/useTypewriter';

// Icon mapping from backend icon names
const iconMap = {
  'lightning': Zap,
  'zap': Zap,
  'building': Building2,
  'building-2': Building2,
  'heart': Heart,
  'dollar': DollarSign,
  'dollar-sign': DollarSign,
  'shield': Shield,
  'trending-up': TrendingUp,
  'percent': Percent,
  'bar-chart': BarChart3,
  'bar-chart-3': BarChart3,
  'gem': Gem,
  'users': Users,
  'target': Target,
  'rocket': Rocket,
  'alert-triangle': AlertTriangle,
  'message-square': MessageSquare,
  'file-text': FileText,
};

/**
 * SectionCard - Renders a research section as a styled card
 *
 * Used in the unified chat interface to display research sections
 * as cards that stack like messages but are not styled as chat bubbles.
 */
export default function SectionCard({
  section,
  isStreaming = false,
  isCollapsed = false,
  onToggleCollapse,
  autoScroll = true,
  scrollContainerRef = null  // Parent scroll container to detect user scroll
}) {
  const contentRef = useRef(null);
  const lastContentLengthRef = useRef(0);
  const [userHasScrolledAway, setUserHasScrolledAway] = useState(false);

  // Get the icon component
  const Icon = iconMap[section?.icon] || FileText;

  // ChatGPT-style streaming effect
  // Only animate when actively streaming - loaded from history should display instantly
  const { displayText, isTyping } = useTypewriter(section?.content || '', {
    speed: 1.5,
    isActive: isStreaming,
    alwaysAnimate: isStreaming  // Only animate during actual streaming, not history loads
  });

  // Detect user scroll intent - if user scrolls up during streaming, pause auto-scroll
  const handleScroll = useCallback((e) => {
    if (!isStreaming && !isTyping) return;

    const container = e.target;
    const { scrollTop, scrollHeight, clientHeight } = container;
    const distanceFromBottom = scrollHeight - scrollTop - clientHeight;

    // If user scrolled more than 100px from bottom, they want to read earlier content
    if (distanceFromBottom > 100) {
      setUserHasScrolledAway(true);
    } else {
      setUserHasScrolledAway(false);
    }
  }, [isStreaming, isTyping]);

  // Attach scroll listener to parent container
  useEffect(() => {
    const container = scrollContainerRef?.current;
    if (!container) return;

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => container.removeEventListener('scroll', handleScroll);
  }, [scrollContainerRef, handleScroll]);

  // Reset scroll state when streaming starts
  useEffect(() => {
    if (isStreaming) {
      setUserHasScrolledAway(false);
    }
  }, [isStreaming]);

  // Auto-scroll as content streams in (only if user hasn't scrolled away)
  useEffect(() => {
    const shouldAutoScroll = autoScroll &&
      (isStreaming || isTyping) &&
      !userHasScrolledAway &&
      displayText.length > lastContentLengthRef.current &&
      contentRef.current;

    if (shouldAutoScroll) {
      contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    lastContentLengthRef.current = displayText.length;
  }, [displayText, isStreaming, isTyping, autoScroll, userHasScrolledAway]);

  // Scroll to bottom handler
  const scrollToBottom = useCallback(() => {
    if (contentRef.current) {
      contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
      setUserHasScrolledAway(false);
    }
  }, []);

  if (!section) return null;

  return (
    <div className="w-full mb-4">
      <div className="relative bg-sand-50 dark:bg-warm-950 rounded-xl border border-sand-200 dark:border-warm-800 shadow-sm overflow-hidden">
        {/* Header - clickable to collapse */}
        <button
          onClick={onToggleCollapse}
          className="w-full flex items-center gap-3 px-6 py-4 bg-sand-50 dark:bg-warm-950/50 hover:bg-sand-100 dark:hover:bg-warm-800/50 transition-colors text-left"
        >
          <Icon className="w-5 h-5 text-indigo-500 flex-shrink-0" />
          <h2 className="font-semibold text-lg text-sand-800 dark:text-warm-50 flex-1">
            {section.title}
          </h2>
          <ChevronDown
            className={`w-4 h-4 text-sand-400 transition-transform duration-200 ${
              isCollapsed ? '-rotate-90' : ''
            }`}
          />
        </button>

        {/* Content - collapsible */}
        <div
          className={`
            transition-all duration-300 ease-in-out overflow-hidden
            ${isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[5000px] opacity-100'}
          `}
        >
          <div
            ref={contentRef}
            className="px-6 py-4 prose dark:prose-invert prose-sand max-w-none prose-headings:font-semibold prose-h2:text-xl prose-h3:text-lg prose-p:text-sand-700 dark:prose-p:text-warm-200 prose-li:text-sand-700 dark:prose-li:text-warm-200 prose-strong:text-sand-900 dark:prose-strong:text-warm-50 prose-a:text-indigo-600 dark:prose-a:text-indigo-400"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {displayText}
            </ReactMarkdown>

            {/* Streaming cursor - show when typing or streaming */}
            {(isStreaming || isTyping) && (
              <span className="inline-block w-2 h-5 bg-indigo-500 animate-pulse ml-0.5 align-middle" />
            )}
          </div>

          {/* Loading state when starting to stream */}
          {isStreaming && !section.content && (
            <div className="px-6 pb-4 flex items-center gap-2 text-sand-500 dark:text-warm-300">
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          )}
        </div>

        {/* Scroll to bottom button - shows when user scrolled away during streaming */}
        {(isStreaming || isTyping) && userHasScrolledAway && (
          <button
            onClick={scrollToBottom}
            className="absolute bottom-4 right-4 flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-full shadow-lg transition-all hover:scale-105"
          >
            <ArrowDown className="w-3.5 h-3.5" />
            <span>Follow</span>
          </button>
        )}
      </div>
    </div>
  );
}
