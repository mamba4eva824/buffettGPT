import React from 'react';
import { Calendar } from 'lucide-react';

// Key categories to display as signal pills (ordered by importance)
const SIGNAL_CATEGORIES = [
  { key: 'growth', label: 'Growth' },
  { key: 'profitability', label: 'Profit' },
  { key: 'valuation', label: 'Value' },
  { key: 'cashflow', label: 'Cash' },
  { key: 'debt', label: 'Debt' },
];

// Map rating text to color tier: green (strong), yellow (moderate), red (weak)
const RATING_COLORS = {
  green: {
    bg: 'bg-emerald-50 dark:bg-emerald-900/30',
    text: 'text-emerald-700 dark:text-emerald-400',
    dot: 'bg-emerald-500',
  },
  yellow: {
    bg: 'bg-amber-50 dark:bg-amber-900/30',
    text: 'text-amber-700 dark:text-amber-400',
    dot: 'bg-amber-500',
  },
  red: {
    bg: 'bg-red-50 dark:bg-red-900/30',
    text: 'text-red-700 dark:text-red-400',
    dot: 'bg-red-500',
  },
};

function getRatingColor(rating) {
  if (!rating) return RATING_COLORS.yellow;
  const r = rating.toLowerCase();
  if (['exceptional', 'excellent', 'strong', 'attractive'].includes(r)) return RATING_COLORS.green;
  if (['weak', 'poor', 'concerning', 'unattractive', 'overvalued'].includes(r)) return RATING_COLORS.red;
  return RATING_COLORS.yellow; // Good, Moderate, Fair, etc.
}

export default function RatingsHeader({ ticker, ratings = {}, generatedAt = null }) {
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

  // Build signal pills from ratings categories
  const signalPills = SIGNAL_CATEGORIES
    .filter(({ key }) => ratings?.[key]?.rating)
    .map(({ key, label }) => ({
      label,
      rating: ratings[key].rating,
      color: getRatingColor(ratings[key].rating),
    }));

  return (
    <div className="pb-1">
      <div className="flex items-center justify-center gap-3 flex-wrap">
        <h1 className="text-2xl font-bold text-sand-900 dark:text-warm-50">
          {ticker}
        </h1>
        {signalPills.length > 0 && signalPills.map(({ label, rating, color }) => (
          <span
            key={label}
            className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${color.bg} ${color.text}`}
          >
            <span className={`h-1.5 w-1.5 rounded-full ${color.dot}`} />
            {label}: {rating}
          </span>
        ))}
        {formattedDate && (
          <div className="flex items-center gap-1.5 text-sm text-sand-500 dark:text-warm-300">
            <Calendar className="h-4 w-4" />
            <span>{formattedDate}</span>
          </div>
        )}
      </div>
    </div>
  );
}
