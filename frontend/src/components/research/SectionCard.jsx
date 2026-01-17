import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, FileText } from 'lucide-react';
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
  autoScroll = true
}) {
  const contentRef = useRef(null);
  const lastContentLengthRef = useRef(0);

  // Get the icon component
  const Icon = iconMap[section?.icon] || FileText;

  // ChatGPT-style streaming effect
  const { displayText, isTyping } = useTypewriter(section?.content || '', {
    speed: 1.5,
    isActive: isStreaming,
    alwaysAnimate: true
  });

  // Auto-scroll as content streams in
  useEffect(() => {
    if (autoScroll && (isStreaming || isTyping) && displayText.length > lastContentLengthRef.current && contentRef.current) {
      // Scroll the card into view smoothly
      contentRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    lastContentLengthRef.current = displayText.length;
  }, [displayText, isStreaming, isTyping, autoScroll]);

  if (!section) return null;

  return (
    <div className="w-full mb-4">
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm overflow-hidden">
        {/* Header - clickable to collapse */}
        <button
          onClick={onToggleCollapse}
          className="w-full flex items-center gap-3 px-6 py-4 bg-slate-50 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-700/50 transition-colors text-left"
        >
          <Icon className="w-5 h-5 text-indigo-500 flex-shrink-0" />
          <h2 className="font-semibold text-lg text-slate-800 dark:text-slate-100 flex-1">
            {section.title}
          </h2>
          <ChevronDown
            className={`w-4 h-4 text-slate-400 transition-transform duration-200 ${
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
            className="px-6 py-4 prose dark:prose-invert prose-slate max-w-none prose-headings:font-semibold prose-h2:text-xl prose-h3:text-lg prose-p:text-slate-700 dark:prose-p:text-slate-300 prose-li:text-slate-700 dark:prose-li:text-slate-300 prose-strong:text-slate-900 dark:prose-strong:text-white prose-a:text-indigo-600 dark:prose-a:text-indigo-400"
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
            <div className="px-6 pb-4 flex items-center gap-2 text-slate-500 dark:text-slate-400">
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
