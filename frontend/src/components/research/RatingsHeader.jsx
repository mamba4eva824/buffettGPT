import React from 'react';
import { TrendingUp, TrendingDown, Minus, Calendar } from 'lucide-react';

// Simple header displaying report metadata (placeholder for future enhancements)
// Unlike Buffett mode (ML inference), Investment Research uses pre-generated reports
export default function RatingsHeader({ ticker, ratings = {}, generatedAt = null }) {
  const verdict = ratings?.overall_verdict;
  const conviction = ratings?.conviction;

  // Format date if available
  const formatDate = (dateString) => {
    if (!dateString) return null;
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
      });
    } catch {
      return null;
    }
  };

  const formattedDate = formatDate(generatedAt);

  // Verdict styling
  const getVerdictStyle = () => {
    switch (verdict?.toUpperCase()) {
      case 'BUY':
        return {
          bg: 'bg-emerald-50 dark:bg-emerald-900/30',
          text: 'text-emerald-700 dark:text-emerald-400',
          border: 'border-emerald-200 dark:border-emerald-800',
          icon: TrendingUp,
        };
      case 'SELL':
        return {
          bg: 'bg-red-50 dark:bg-red-900/30',
          text: 'text-red-700 dark:text-red-400',
          border: 'border-red-200 dark:border-red-800',
          icon: TrendingDown,
        };
      case 'HOLD':
      default:
        return {
          bg: 'bg-amber-50 dark:bg-amber-900/30',
          text: 'text-amber-700 dark:text-amber-400',
          border: 'border-amber-200 dark:border-amber-800',
          icon: Minus,
        };
    }
  };

  const style = verdict ? getVerdictStyle() : null;
  const VerdictIcon = style?.icon;

  return (
    <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-700 pb-4 mb-6">
      {/* Ticker and date */}
      <div className="flex items-center gap-4">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {ticker}
        </h1>
        {formattedDate && (
          <div className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
            <Calendar className="h-4 w-4" />
            <span>{formattedDate}</span>
          </div>
        )}
      </div>

      {/* Verdict badge (if available) */}
      {verdict && style && (
        <div className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${style.bg} ${style.border}`}>
          <VerdictIcon className={`h-4 w-4 ${style.text}`} />
          <span className={`font-semibold ${style.text}`}>
            {verdict}
          </span>
          {conviction && (
            <span className={`text-sm opacity-75 ${style.text}`}>
              ({conviction} conviction)
            </span>
          )}
        </div>
      )}
    </div>
  );
}
