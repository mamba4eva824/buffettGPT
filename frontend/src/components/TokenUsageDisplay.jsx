import { Zap, Calendar, AlertTriangle, TrendingUp, Crown } from 'lucide-react';

/**
 * TokenUsageDisplay - Shows monthly token usage in settings
 *
 * Displays:
 * - Progress bar showing tokens used vs limit
 * - Percentage remaining
 * - Reset date
 * - Warning when approaching limit
 * - Upgrade prompt for free users
 */
export default function TokenUsageDisplay({ tokenUsage, isAuthenticated, onUpgrade }) {
  // Default values when no usage data available
  const {
    token_limit = 0,
    percent_used = 0,
    remaining_tokens = 0,
    reset_date = null,
    request_count = 0,
    subscription_tier = 'free'
  } = tokenUsage || {};

  // Calculate percentage remaining (inverse of percent_used)
  const percentRemaining = Math.max(0, 100 - percent_used);

  // Determine status color based on usage
  const getStatusColor = () => {
    if (percent_used >= 100) return { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' };
    if (percent_used >= 90) return { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' };
    if (percent_used >= 75) return { bar: 'bg-yellow-500', text: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-900/20' };
    if (percent_used >= 50) return { bar: 'bg-blue-500', text: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20' };
    return { bar: 'bg-green-500', text: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/20' };
  };

  const statusColor = getStatusColor();

  // Format reset date (supports anniversary-based billing)
  const formatResetDate = (dateStr) => {
    if (!dateStr) return 'next billing date';
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) return 'next billing date';
      return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== new Date().getFullYear() ? 'numeric' : undefined
      });
    } catch {
      return 'next billing date';
    }
  };

  // Format large numbers
  const formatNumber = (num) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toLocaleString();
  };

  // Get tier display info
  const getTierInfo = () => {
    const tiers = {
      free: { name: 'Free', color: 'text-slate-600 dark:text-slate-400', badge: 'bg-slate-100 dark:bg-slate-700' },
      plus: { name: 'Plus', color: 'text-indigo-600 dark:text-indigo-400', badge: 'bg-indigo-100 dark:bg-indigo-900/30' },
    };
    return tiers[subscription_tier] || tiers.free;
  };

  const tierInfo = getTierInfo();
  const showWarning = percent_used >= 75;
  const limitReached = percent_used >= 100;

  // Always show usage tracking regardless of tier (for development)
  return (
    <div className="space-y-4">
      {/* Header with tier badge */}
      <div className="flex items-center justify-between">
        <label className="flex items-center gap-2 text-xs font-medium text-slate-500 dark:text-slate-400">
          <Zap className="h-3.5 w-3.5" />
          Monthly Token Usage
        </label>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${tierInfo.badge} ${tierInfo.color}`}>
          {tierInfo.name}
        </span>
      </div>

      {/* Main usage card */}
      <div className={`rounded-lg border ${showWarning ? 'border-yellow-200 dark:border-yellow-800' : 'border-slate-200 dark:border-slate-600'} ${statusColor.bg} p-4`}>
        {/* Progress section */}
        <div className="mb-3">
          {/* Stats row */}
          <div className="flex items-baseline justify-between mb-2">
            <div className="flex items-baseline gap-1">
              <span className={`text-2xl font-bold ${statusColor.text}`}>
                {percentRemaining.toFixed(0)}%
              </span>
              <span className="text-xs text-slate-500 dark:text-slate-400">remaining</span>
            </div>
            <div className="text-right">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {formatNumber(remaining_tokens)}
              </span>
              <span className="text-xs text-slate-400 dark:text-slate-500"> / {formatNumber(token_limit)}</span>
            </div>
          </div>

          {/* Progress bar */}
          <div className="h-2.5 bg-slate-200 dark:bg-slate-600 rounded-full overflow-hidden">
            <div
              className={`h-full ${statusColor.bar} transition-all duration-500 ease-out rounded-full`}
              style={{ width: `${Math.min(percent_used, 100)}%` }}
            />
          </div>
        </div>

        {/* Details row */}
        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
          <div className="flex items-center gap-1">
            <TrendingUp className="h-3 w-3" />
            <span>{request_count} requests this month</span>
          </div>
          <div className="flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            <span>Resets {formatResetDate(reset_date)}</span>
          </div>
        </div>

        {/* Warning message */}
        {showWarning && (
          <div className={`mt-3 pt-3 border-t ${limitReached ? 'border-red-200 dark:border-red-800' : 'border-yellow-200 dark:border-yellow-800'}`}>
            <div className="flex items-start gap-2">
              <AlertTriangle className={`h-4 w-4 flex-shrink-0 mt-0.5 ${limitReached ? 'text-red-500' : 'text-yellow-500'}`} />
              <div className="flex-1">
                <p className={`text-xs font-medium ${limitReached ? 'text-red-700 dark:text-red-300' : 'text-yellow-700 dark:text-yellow-300'}`}>
                  {limitReached
                    ? 'Monthly token limit reached'
                    : `You've used ${percent_used.toFixed(0)}% of your monthly tokens`
                  }
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {limitReached
                    ? `Usage resets on ${formatResetDate(reset_date)}.`
                    : ''
                  }
                </p>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Upgrade prompt for free users */}
      {subscription_tier === 'free' && isAuthenticated && onUpgrade && (
        <div className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-lg border border-indigo-200 dark:border-indigo-800 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-100 dark:bg-indigo-900/50 rounded-lg">
                <Crown className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200">
                  Need more tokens?
                </p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Get 2M tokens/month with Buffett Plus
                </p>
              </div>
            </div>
            <button
              onClick={onUpgrade}
              className="px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors"
            >
              Upgrade
            </button>
          </div>
        </div>
      )}

      {/* Helper text */}
      <p className="text-[11px] text-slate-400 dark:text-slate-500">
        Tokens measure AI usage. Each follow-up question uses approximately 2,000-5,000 tokens depending on complexity.
      </p>
    </div>
  );
}
