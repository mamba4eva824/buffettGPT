import { Crown, Check, Zap, Calendar, AlertCircle } from 'lucide-react';

/**
 * SubscriptionCard - Displays current subscription plan and status
 *
 * Shows:
 * - Current tier (Free or Buffett Plus)
 * - Subscription benefits
 * - Status (active, past_due, canceling)
 * - Token limit for tier
 */
export default function SubscriptionCard({
  subscriptionTier = 'free',
  subscriptionStatus = null,
  tokenLimit = 0,
  cancelAtPeriodEnd = false,
  currentPeriodEnd = null,
  onUpgrade,
  onManage,
  isLoading = false
}) {
  const isPlusActive = subscriptionTier === 'plus' && ['active', 'trialing'].includes(subscriptionStatus);
  const isPastDue = subscriptionStatus === 'past_due';
  const isCanceling = cancelAtPeriodEnd && isPlusActive;

  // Format period end date
  const formatPeriodEnd = (timestamp) => {
    if (!timestamp) return null;
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  // Format token limit
  const formatTokens = (num) => {
    if (num >= 1000000) return `${(num / 1000000).toFixed(0)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(0)}K`;
    return num.toLocaleString();
  };

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 animate-pulse">
        <div className="h-6 bg-slate-200 dark:bg-slate-700 rounded w-1/3 mb-4" />
        <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-2/3 mb-2" />
        <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-1/2" />
      </div>
    );
  }

  return (
    <div className={`
      bg-white dark:bg-slate-800 rounded-xl border-2 p-6
      ${isPlusActive ? 'border-indigo-500 dark:border-indigo-400' : 'border-slate-200 dark:border-slate-700'}
    `}>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          {isPlusActive ? (
            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
              <Crown className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
          ) : (
            <div className="p-2 bg-slate-100 dark:bg-slate-700 rounded-lg">
              <Zap className="h-5 w-5 text-slate-600 dark:text-slate-400" />
            </div>
          )}
          <div>
            <h3 className="font-semibold text-slate-900 dark:text-white">
              {isPlusActive ? 'Buffett Plus' : 'Free Plan'}
            </h3>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {isPlusActive ? '$10/month' : 'No cost'}
            </p>
          </div>
        </div>

        {/* Status badge */}
        {isPlusActive && (
          <span className={`
            px-2.5 py-1 text-xs font-medium rounded-full
            ${isCanceling
              ? 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400'
              : isPastDue
                ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                : 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400'
            }
          `}>
            {isCanceling ? 'Canceling' : isPastDue ? 'Past Due' : 'Active'}
          </span>
        )}
      </div>

      {/* Warning for past due */}
      {isPastDue && (
        <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-red-700 dark:text-red-300">
                Payment failed
              </p>
              <p className="text-xs text-red-600 dark:text-red-400 mt-0.5">
                Please update your payment method to keep your subscription active.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Canceling notice */}
      {isCanceling && currentPeriodEnd && (
        <div className="mb-4 p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
          <div className="flex items-start gap-2">
            <Calendar className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
            <div>
              <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
                Subscription ends {formatPeriodEnd(currentPeriodEnd)}
              </p>
              <p className="text-xs text-amber-600 dark:text-amber-400 mt-0.5">
                You will retain access until then. Reactivate anytime to keep your benefits.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Benefits list */}
      <div className="space-y-2 mb-5">
        {isPlusActive ? (
          <>
            <BenefitItem active>
              {formatTokens(tokenLimit)} tokens/month for follow-up questions
            </BenefitItem>
            <BenefitItem active>
              Unlimited investment reports
            </BenefitItem>
            <BenefitItem active>
              Priority response times
            </BenefitItem>
            <BenefitItem active>
              Full conversation history
            </BenefitItem>
          </>
        ) : (
          <>
            <BenefitItem>
              Investment reports only
            </BenefitItem>
            <BenefitItem inactive>
              No follow-up questions
            </BenefitItem>
            <BenefitItem inactive>
              Limited history
            </BenefitItem>
          </>
        )}
      </div>

      {/* Action button */}
      {isPlusActive ? (
        <button
          onClick={onManage}
          className="w-full py-2.5 px-4 text-sm font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 rounded-lg transition-colors"
        >
          Manage Subscription
        </button>
      ) : (
        <button
          onClick={onUpgrade}
          className="w-full py-2.5 px-4 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors flex items-center justify-center gap-2"
        >
          <Crown className="h-4 w-4" />
          Upgrade to Plus
        </button>
      )}
    </div>
  );
}

/**
 * Benefit item component
 */
function BenefitItem({ children, active = false, inactive = false }) {
  return (
    <div className="flex items-center gap-2">
      <Check className={`h-4 w-4 flex-shrink-0 ${
        inactive
          ? 'text-slate-300 dark:text-slate-600'
          : active
            ? 'text-indigo-500 dark:text-indigo-400'
            : 'text-slate-400 dark:text-slate-500'
      }`} />
      <span className={`text-sm ${
        inactive
          ? 'text-slate-400 dark:text-slate-500 line-through'
          : 'text-slate-600 dark:text-slate-300'
      }`}>
        {children}
      </span>
    </div>
  );
}
