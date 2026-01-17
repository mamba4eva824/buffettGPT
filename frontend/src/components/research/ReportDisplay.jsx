import React, { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import useTypewriter from '../../hooks/useTypewriter';

export default function ReportDisplay({
  content = '',
  isStreaming = false,
  sectionTitle = '',
  sectionIcon = null
}) {
  const containerRef = useRef(null);
  const lastContentLengthRef = useRef(0);

  // ChatGPT-style streaming effect with natural pacing
  const { displayText, isTyping } = useTypewriter(content, {
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
      <div className="flex items-center justify-center h-full text-slate-400 dark:text-slate-500">
        <p>Select a section from the table of contents to view its content.</p>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-6 py-4 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600 scrollbar-track-transparent"
    >
      {/* Section title */}
      {sectionTitle && (
        <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-4 flex items-center gap-2">
          {sectionTitle}
        </h2>
      )}

      {/* Markdown content with prose styling */}
      <article className="prose dark:prose-invert prose-slate max-w-none prose-headings:font-semibold prose-h2:text-xl prose-h3:text-lg prose-p:text-slate-700 dark:prose-p:text-slate-300 prose-li:text-slate-700 dark:prose-li:text-slate-300 prose-strong:text-slate-900 dark:prose-strong:text-white prose-a:text-indigo-600 dark:prose-a:text-indigo-400">
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
        <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400">
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <div className="w-2 h-2 bg-indigo-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      )}
    </div>
  );
}
