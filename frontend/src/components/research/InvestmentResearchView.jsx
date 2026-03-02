import React, { useEffect, useCallback, useState, useRef } from 'react';
import { X, RefreshCw, AlertCircle, GripVertical } from 'lucide-react';
import { useResearch, ResearchProvider } from '../../contexts/ResearchContext';
import logger from '../../utils/logger';
import RatingsHeader from './RatingsHeader';
import ReportDisplay from './ReportDisplay';
import TableOfContents from './TableOfContents';
import StreamingIndicator from './StreamingIndicator';

// Inner component that uses the research context
function InvestmentResearchContent({ ticker, onClose, token = null }) {
  const {
    selectedTicker,
    activeSectionId,
    isStreaming,
    streamStatus,
    reportMeta,
    streamedContent,
    error,
    currentStreamingSection,
    startResearch,
    abortStream,
    fetchSection,
    setActiveSection,
    reset,
  } = useResearch();

  // Resizable ToC panel state
  const [tocWidth, setTocWidth] = useState(340); // Default wider to show more text
  const isResizingRef = useRef(false);
  const startXRef = useRef(0);
  const startWidthRef = useRef(0);

  // Handle resize start
  const handleResizeStart = useCallback((e) => {
    e.preventDefault();
    isResizingRef.current = true;
    startXRef.current = e.clientX;
    startWidthRef.current = tocWidth;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, [tocWidth]);

  // Handle resize move and end
  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizingRef.current) return;
      // Dragging left increases width (since ToC is on the right)
      const delta = startXRef.current - e.clientX;
      const newWidth = Math.min(Math.max(startWidthRef.current + delta, 200), 600);
      setTocWidth(newWidth);
    };

    const handleMouseUp = () => {
      if (isResizingRef.current) {
        isResizingRef.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, []);

  // Start research when ticker changes
  useEffect(() => {
    if (ticker && ticker !== selectedTicker) {
      startResearch(ticker, token);
    }
  }, [ticker, selectedTicker, startResearch, token]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortStream();
    };
  }, [abortStream]);

  // Handle section click
  const handleSectionClick = useCallback(async (sectionId) => {
    setActiveSection(sectionId);

    // If section already has complete content, just switch view
    if (streamedContent[sectionId]?.isComplete) {
      return;
    }

    // If currently streaming and section has partial content, let it continue
    if (isStreaming && streamedContent[sectionId]?.content) {
      return;
    }

    // Fetch section on-demand if not available
    if (!streamedContent[sectionId]?.content && !isStreaming) {
      try {
        await fetchSection(ticker, sectionId, token);
      } catch (err) {
        logger.error('Failed to fetch section:', err);
      }
    }
  }, [setActiveSection, streamedContent, isStreaming, fetchSection, ticker, token]);

  // Handle retry
  const handleRetry = useCallback(() => {
    if (ticker) {
      startResearch(ticker, token);
    }
  }, [ticker, startResearch, token]);

  // Handle close
  const handleClose = useCallback(() => {
    reset();
    onClose?.();
  }, [reset, onClose]);

  // Get active section content
  const activeContent = activeSectionId ? streamedContent[activeSectionId] : null;
  const isActiveSectionStreaming = currentStreamingSection === activeSectionId;

  // Calculate progress
  const totalSections = reportMeta?.toc?.length || 0;
  const completedSections = Object.values(streamedContent).filter(s => s?.isComplete).length;

  return (
    <div className="flex flex-col h-full bg-sand-50 dark:bg-warm-900">
      {/* Header */}
      <div className="flex-shrink-0 px-6 pt-6">
        <div className="flex items-center justify-between mb-4">
          <RatingsHeader
            ticker={selectedTicker || ticker}
            ratings={reportMeta?.ratings}
            generatedAt={reportMeta?.generated_at}
          />
          <button
            onClick={handleClose}
            className="p-2 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800 rounded-full transition-colors"
            title="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Streaming indicator */}
        {(isStreaming || streamStatus === 'connecting') && (
          <div className="mb-4">
            <StreamingIndicator
              currentSection={activeContent?.title}
              progress={totalSections > 0 ? { current: completedSections, total: totalSections } : null}
              isStreaming={isStreaming}
              status={streamStatus}
            />
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className="mb-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
            <div className="flex-1">
              <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
            </div>
            <button
              onClick={handleRetry}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          </div>
        )}
      </div>

      {/* Main content area - two pane layout */}
      <div className="flex-1 flex min-h-0">
        {/* Report display - center/left */}
        <div className="flex-1 min-w-0 border-r border-sand-200 dark:border-warm-800">
          <ReportDisplay
            key={activeSectionId}
            content={activeContent?.content || ''}
            isStreaming={isActiveSectionStreaming}
            sectionTitle={activeContent?.title || ''}
            sectionIcon={activeContent?.icon}
          />
        </div>

        {/* Table of contents - right (resizable) */}
        <div
          className="flex-shrink-0 bg-sand-50 dark:bg-warm-800/50 relative"
          style={{ width: tocWidth }}
        >
          {/* Resize handle */}
          <div
            onMouseDown={handleResizeStart}
            className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-indigo-400 active:bg-indigo-500 transition-colors group flex items-center justify-center z-10"
            title="Drag to resize"
          >
            {/* Visible grip indicator on hover */}
            <div className="absolute left-[-4px] w-3 h-12 rounded bg-sand-300 dark:bg-warm-800 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
              <GripVertical className="h-4 w-4 text-sand-500 dark:text-warm-300" />
            </div>
          </div>

          {/* Border line */}
          <div className="absolute left-0 top-0 bottom-0 w-px bg-sand-200 dark:bg-warm-700" />

          <TableOfContents
            toc={reportMeta?.toc || []}
            activeSectionId={activeSectionId}
            onSectionClick={handleSectionClick}
            streamedSections={streamedContent}
            currentStreamingSection={currentStreamingSection}
          />
        </div>
      </div>
    </div>
  );
}

// Main component with provider wrapper
export default function InvestmentResearchView({ ticker, onClose, token = null }) {
  return (
    <ResearchProvider>
      <InvestmentResearchContent
        ticker={ticker}
        onClose={onClose}
        token={token}
      />
    </ResearchProvider>
  );
}
