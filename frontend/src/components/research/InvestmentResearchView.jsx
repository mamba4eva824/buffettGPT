import React, { useEffect, useCallback } from 'react';
import { X, RefreshCw, AlertCircle } from 'lucide-react';
import { useResearch, ResearchProvider } from '../../contexts/ResearchContext';
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
        console.error('Failed to fetch section:', err);
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
    <div className="flex flex-col h-full bg-white dark:bg-slate-900">
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
            className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-full transition-colors"
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
        <div className="flex-1 min-w-0 border-r border-slate-200 dark:border-slate-700">
          <ReportDisplay
            content={activeContent?.content || ''}
            isStreaming={isActiveSectionStreaming}
            sectionTitle={activeContent?.title || ''}
            sectionIcon={activeContent?.icon}
          />
        </div>

        {/* Table of contents - right */}
        <div className="w-72 flex-shrink-0 border-l border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
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
