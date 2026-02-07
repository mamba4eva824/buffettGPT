import React from 'react';
import { Loader2 } from 'lucide-react';

export default function StreamingIndicator({
  currentSection = null,
  progress = null,
  isStreaming = false,
  status = 'idle'
}) {
  if (!isStreaming && status !== 'connecting') return null;

  return (
    <div className="flex items-center gap-2 text-sm text-sand-500 dark:text-warm-300">
      <Loader2 className="h-4 w-4 animate-spin text-indigo-500" />
      <span>
        {status === 'connecting' && 'Connecting...'}
        {status === 'streaming' && currentSection && (
          <>Loading {currentSection}...</>
        )}
        {status === 'streaming' && !currentSection && 'Loading report...'}
        {progress && (
          <span className="ml-2 text-sand-400 dark:text-warm-400">
            ({progress.current}/{progress.total})
          </span>
        )}
      </span>
    </div>
  );
}
