import React from 'react';
import { X, RefreshCw, AlertCircle } from 'lucide-react';
import TableOfContents from './TableOfContents';
import RatingsHeader from './RatingsHeader';
import StreamingIndicator from './StreamingIndicator';
import ExpiredReportBanner from './ExpiredReportBanner';

/**
 * ResearchLayout - 2-column layout for research mode (content + ToC)
 *
 * This component handles the layout structure for the research view:
 * - Scrollable main content area (research sections, follow-up chat)
 * - Fixed ToC sidebar on the right (desktop only)
 * - Bottom composer area
 *
 * The parent App.jsx handles the outer sidebar (conversation list).
 */
export default function ResearchLayout({
  // Research state
  ticker,
  reportMeta,
  streamedContent,
  activeSectionId,
  currentStreamingSection,
  isStreaming,
  streamStatus,
  error,
  progress,

  // Expired report state
  reportExpired,
  expiredReportMeta,

  // ToC state
  tocWidth = 300,

  // Callbacks
  onSectionClick,
  onClose,
  onRetry,
  onRegenerateExpired,
  onDismissExpired,

  // Token for retry
  token,

  // Children - main content (messages, sections, follow-up)
  children,

  // Composer - rendered at bottom
  composer,
}) {
  const hasToc = reportMeta?.toc?.length > 0;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Main content area with ToC */}
      <div className="flex-1 flex min-h-0">
        {/* Scrollable content area */}
        <div className="flex-1 overflow-y-auto px-4 md:px-6 py-4 transition-all duration-300 ease-in-out scrollbar-thin scrollbar-track-transparent scrollbar-thumb-sand-300 dark:scrollbar-thumb-warm-700">
          <div className="mx-auto max-w-3xl space-y-4">
            {/* Research header */}
            {reportMeta && (
              <div className="mb-4 pb-4 border-b border-sand-200 dark:border-warm-800">
                <div className="flex items-center justify-between">
                  <RatingsHeader
                    ticker={ticker}
                    ratings={reportMeta?.ratings}
                    generatedAt={reportMeta?.generated_at}
                  />
                  <button
                    onClick={onClose}
                    className="p-2 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800 rounded-full transition-colors"
                    title="Close"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Streaming indicator */}
                {(isStreaming || streamStatus === 'connecting') && (
                  <div className="mt-3">
                    <StreamingIndicator
                      currentSection={streamedContent[currentStreamingSection]?.title}
                      progress={progress?.total > 0 ? progress : null}
                      isStreaming={isStreaming}
                      status={streamStatus}
                    />
                  </div>
                )}

                {/* Error state */}
                {error && (
                  <div className="mt-3 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg flex items-center gap-3">
                    <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                    <div className="flex-1">
                      <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
                    </div>
                    <button
                      onClick={onRetry}
                      className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
                    >
                      <RefreshCw className="h-4 w-4" />
                      Retry
                    </button>
                  </div>
                )}

                {/* Expired report banner */}
                {reportExpired && expiredReportMeta && (
                  <ExpiredReportBanner
                    ticker={expiredReportMeta.ticker}
                    generatedAt={expiredReportMeta.generated_at}
                    ratings={expiredReportMeta.ratings}
                    onRegenerate={onRegenerateExpired}
                    onDismiss={onDismissExpired}
                  />
                )}
              </div>
            )}

            {/* Main content - messages, research sections, follow-up */}
            {children}
          </div>
        </div>

        {/* Table of Contents - right side, desktop only */}
        {hasToc && (
          <div
            className="hidden md:block flex-shrink-0 border-l border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-800/50"
            style={{ width: tocWidth }}
          >
            <TableOfContents
              toc={reportMeta.toc}
              activeSectionId={activeSectionId}
              onSectionClick={onSectionClick}
              streamedSections={streamedContent}
              currentStreamingSection={currentStreamingSection}
            />
          </div>
        )}
      </div>

      {/* Bottom composer - centered to align with main content, offset for ToC on desktop */}
      {composer && (
        <div
          className="border-t border-sand-100 dark:border-warm-800 p-4 md:p-4 pb-6 md:pb-4 transition-all duration-300 ease-in-out"
          style={{ paddingRight: hasToc ? `calc(1rem + ${tocWidth}px)` : undefined }}
        >
          <div className="mx-auto max-w-3xl">
            {composer}
          </div>
        </div>
      )}
    </div>
  );
}
