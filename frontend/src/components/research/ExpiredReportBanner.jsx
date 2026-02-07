import React from 'react';
import { AlertTriangle, RefreshCw, X, Calendar } from 'lucide-react';

/**
 * Banner displayed when a research report has expired (TTL passed).
 * Offers options to regenerate the report or dismiss and return to chat.
 */
export default function ExpiredReportBanner({
  ticker,
  generatedAt,
  ratings,
  onRegenerate,
  onDismiss
}) {
  // Format date if available
  const formatDate = (dateString) => {
    if (!dateString) return 'Unknown date';
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
      });
    } catch {
      return 'Unknown date';
    }
  };

  const formattedDate = formatDate(generatedAt);
  const verdict = ratings?.overall_verdict || 'N/A';

  return (
    <div className="mx-4 my-4 p-4 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700 rounded-lg shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-0.5">
          <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-amber-800 dark:text-amber-200">
            Report Expired
          </h3>

          <p className="mt-1 text-sm text-amber-700 dark:text-amber-300">
            The <span className="font-medium">{ticker}</span> research report you previously viewed
            has expired. It was generated on <span className="font-medium">{formattedDate}</span>
            {verdict !== 'N/A' && (
              <> with a <span className="font-medium">{verdict}</span> recommendation</>
            )}.
          </p>

          <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
            Would you like to generate a fresh analysis with the latest financial data?
          </p>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              onClick={onRegenerate}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-warm-800"
            >
              <RefreshCw className="h-4 w-4" />
              Generate New Report
            </button>

            <button
              onClick={onDismiss}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-sand-700 dark:text-warm-100 bg-sand-50 dark:bg-warm-900 border border-sand-300 dark:border-warm-800 hover:bg-sand-50 dark:hover:bg-warm-700 rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-sand-500 focus:ring-offset-2 dark:focus:ring-offset-warm-800"
            >
              <X className="h-4 w-4" />
              Return to Chat
            </button>
          </div>
        </div>
      </div>

      {/* Optional: Show previous ratings summary */}
      {ratings && (ratings.debt || ratings.cashflow || ratings.growth) && (
        <div className="mt-4 pt-3 border-t border-amber-200 dark:border-amber-700">
          <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
            Previous ratings (may be outdated):
          </p>
          <div className="flex flex-wrap gap-2">
            {ratings.debt?.rating && (
              <span className="px-2 py-1 text-xs rounded bg-amber-100 dark:bg-amber-800/40 text-amber-700 dark:text-amber-300">
                Debt: {ratings.debt.rating}
              </span>
            )}
            {ratings.cashflow?.rating && (
              <span className="px-2 py-1 text-xs rounded bg-amber-100 dark:bg-amber-800/40 text-amber-700 dark:text-amber-300">
                Cashflow: {ratings.cashflow.rating}
              </span>
            )}
            {ratings.growth?.rating && (
              <span className="px-2 py-1 text-xs rounded bg-amber-100 dark:bg-amber-800/40 text-amber-700 dark:text-amber-300">
                Growth: {ratings.growth.rating}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
