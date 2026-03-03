import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import useTypewriter from '../../hooks/useTypewriter';

/** Strip trailing JSON ratings block from section content (safety net for existing data). */
const stripTrailingJsonBlock = (text) =>
  text ? text.replace(/\n*---\s*\n*```json\s*\{[\s\S]*?\}\s*```\s*$/, '').replace(/\n*```json\s*\{[\s\S]*?\}\s*```\s*$/, '').trim() : '';

export default function ReportDisplay({
  content = '',
  isStreaming = false,
  sectionTitle = '',
  sectionIcon = null
}) {
  const containerRef = useRef(null);
  const lastContentLengthRef = useRef(0);

  // Strip trailing JSON ratings block from content (safety net for legacy data)
  const cleanContent = stripTrailingJsonBlock(content);

  // ChatGPT-style streaming effect with natural pacing
  const { displayText, isTyping } = useTypewriter(cleanContent, {
    speed: 1.5,           // Speed multiplier (1.0 = normal, 2.0 = 2x faster)
    isActive: isStreaming,
    alwaysAnimate: true   // Always animate from start on mount
  });

  // Auto-scroll as content streams in
  useEffect(() => {
    if ((isStreaming || isTyping) && displayText.length > lastContentLengthRef.current && containerRef.current) {
      const container = containerRef.current;
      // Smooth scroll to bottom as new content arrives
      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth'
      });
    }
    lastContentLengthRef.current = displayText.length;
  }, [displayText, isStreaming, isTyping]);

  // Show placeholder when no content
  if (!content && !isStreaming) {
    return (
      <div className="flex items-center justify-center h-full text-sand-400 dark:text-warm-400">
        <p>Select a section from the table of contents to view its content.</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-6 py-4 scrollbar-thin scrollbar-thumb-sand-300 dark:scrollbar-thumb-warm-600 scrollbar-track-transparent"
    >
      {/* Section title */}
      {sectionTitle && (
        <h2 className="text-xl font-semibold text-sand-900 dark:text-warm-50 mb-4 flex items-center gap-2">
          {sectionTitle}
        </h2>
      )}

      {/* Markdown content with prose styling */}
      <article className="prose dark:prose-invert prose-sand max-w-none prose-headings:font-semibold prose-h2:text-xl prose-h3:text-lg prose-p:text-sand-700 dark:prose-p:text-warm-200 prose-li:text-sand-700 dark:prose-li:text-warm-200 prose-strong:text-sand-900 dark:prose-strong:text-warm-50 prose-a:text-indigo-600 dark:prose-a:text-indigo-400">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {displayText}
        </ReactMarkdown>

        {/* Streaming cursor - show when typing or streaming */}
        {(isStreaming || isTyping) && (
          <span className="inline-block w-2 h-5 bg-indigo-500 animate-pulse ml-0.5 align-middle" />
        )}
      </article>

      {/* Loading state when starting to stream */}
      {isStreaming && !content && (
        <div className="flex items-center gap-2 text-sand-500 dark:text-warm-300">
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      )}
    </div>
  );
}
