import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';

/**
 * StreamingText - Real-time markdown display with auto-scroll
 *
 * Features:
 * - Renders markdown-like text (headers, bold, lists)
 * - Auto-scrolls as new content streams in
 * - Blinking cursor while streaming
 * - Smooth content fade-in
 */
const StreamingText = ({ text, isStreaming }) => {
  const containerRef = useRef(null);

  // Auto-scroll as text streams in
  useEffect(() => {
    if (containerRef.current && isStreaming) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [text, isStreaming]);

  // Simple markdown-to-JSX renderer
  const renderMarkdown = (content) => {
    if (!content) {
      return isStreaming ? (
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
          <motion.span
            className="w-2 h-2 bg-blue-500 rounded-full"
            animate={{ opacity: [1, 0.3, 1] }}
            transition={{ repeat: Infinity, duration: 1 }}
          />
          <span>Loading analysis...</span>
        </div>
      ) : null;
    }

    const lines = content.split('\n');

    return lines.map((line, idx) => {
      // Headers
      if (line.startsWith('## ')) {
        return (
          <h2 key={idx} className="text-xl font-bold text-gray-900 dark:text-white mt-6 mb-3">
            {renderInlineMarkdown(line.slice(3))}
          </h2>
        );
      }
      if (line.startsWith('### ')) {
        return (
          <h3 key={idx} className="text-lg font-semibold text-gray-800 dark:text-gray-100 mt-4 mb-2">
            {renderInlineMarkdown(line.slice(4))}
          </h3>
        );
      }

      // Bullet points
      if (line.startsWith('- ')) {
        return (
          <li key={idx} className="ml-4 text-gray-700 dark:text-gray-300 mb-1">
            {renderInlineMarkdown(line.slice(2))}
          </li>
        );
      }

      // Indented bullet points
      if (line.startsWith('  - ')) {
        return (
          <li key={idx} className="ml-8 text-gray-600 dark:text-gray-400 text-sm mb-1">
            {renderInlineMarkdown(line.slice(4))}
          </li>
        );
      }

      // Blockquotes
      if (line.startsWith('"') && line.endsWith('"')) {
        return (
          <blockquote key={idx} className="border-l-4 border-blue-500 pl-4 py-2 my-3 bg-blue-50 dark:bg-blue-900/20 rounded-r italic text-gray-700 dark:text-gray-300">
            {line}
          </blockquote>
        );
      }

      // Empty lines
      if (line.trim() === '') {
        return <div key={idx} className="h-2" />;
      }

      // Regular paragraphs
      return (
        <p key={idx} className="text-gray-700 dark:text-gray-300 mb-2">
          {renderInlineMarkdown(line)}
        </p>
      );
    });
  };

  // Render inline markdown (bold, italic, code)
  const renderInlineMarkdown = (text) => {
    if (!text) return null;

    // Bold: **text** or __text__
    const boldRegex = /\*\*(.+?)\*\*|__(.+?)__/g;
    // Italic: *text* or _text_
    const italicRegex = /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)|(?<!_)_(?!_)(.+?)(?<!_)_(?!_)/g;
    // Inline code: `code`
    const codeRegex = /`([^`]+)`/g;

    let result = text;

    // Replace bold
    result = result.replace(boldRegex, '<strong>$1$2</strong>');
    // Replace code
    result = result.replace(codeRegex, '<code class="bg-gray-200 dark:bg-gray-700 px-1 rounded text-sm">$1</code>');

    // Return as dangerouslySetInnerHTML for simplicity
    // In production, use a proper markdown parser like react-markdown
    return <span dangerouslySetInnerHTML={{ __html: result }} />;
  };

  return (
    <div
      ref={containerRef}
      className="prose dark:prose-invert max-w-none overflow-y-auto"
      style={{ maxHeight: 'calc(100vh - 300px)' }}
    >
      {renderMarkdown(text)}

      {/* Blinking cursor while streaming */}
      {isStreaming && text && (
        <motion.span
          className="inline-block w-2 h-5 bg-blue-500 ml-1 align-middle"
          animate={{ opacity: [1, 0, 1] }}
          transition={{ repeat: Infinity, duration: 0.8 }}
        />
      )}
    </div>
  );
};

export default StreamingText;
