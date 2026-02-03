import { useEffect } from 'react';
import { X, Crown, Check, Zap, Loader2, AlertCircle } from 'lucide-react';

/**
 * UpgradeModal - Modal for upgrading to Buffett Plus
 *
 * Displays:
 * - Plan comparison (Free vs Plus)
 * - Pricing ($10/month)
 * - Benefits list
 * - Checkout button
 */
export default function UpgradeModal({
  isOpen,
  onClose,
  onUpgrade,
  isLoading = false,
  error = null
}) {
  // Close on escape key - must be before early return to satisfy hooks rules
  useEffect(() => {
    if (!isOpen) return;

    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleUpgrade = () => {
    if (!isLoading) {
      onUpgrade();
    }
  };

  // Close on backdrop click
  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={handleBackdropClick}
    >
      <div className="bg-white dark:bg-slate-800 rounded-2xl shadow-xl max-w-md w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-slate-200 dark:border-slate-700">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
              <Crown className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
                Upgrade to Buffett Plus
              </h2>
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Unlock the full experience
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5">
          {/* Price display */}
          <div className="text-center mb-6">
            <div className="flex items-baseline justify-center gap-1">
              <span className="text-4xl font-bold text-slate-900 dark:text-white">$10</span>
              <span className="text-slate-500 dark:text-slate-400">/month</span>
            </div>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Cancel anytime
            </p>
          </div>

          {/* Benefits */}
          <div className="space-y-3 mb-6">
            <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">
              What you get:
            </h3>
            <PlusBenefit icon={<Zap className="h-4 w-4" />}>
              <span className="font-medium">2,000,000 tokens/month</span> for follow-up questions
            </PlusBenefit>
            <PlusBenefit icon={<Check className="h-4 w-4" />}>
              Ask unlimited follow-up questions on any report
            </PlusBenefit>
            <PlusBenefit icon={<Check className="h-4 w-4" />}>
              Full conversation history saved across sessions
            </PlusBenefit>
            <PlusBenefit icon={<Check className="h-4 w-4" />}>
              Priority response times
            </PlusBenefit>
            <PlusBenefit icon={<Check className="h-4 w-4" />}>
              Early access to new features
            </PlusBenefit>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-800">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0" />
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            </div>
          )}

          {/* Upgrade button */}
          <button
            onClick={handleUpgrade}
            disabled={isLoading}
            className="w-full py-3 px-4 text-base font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 disabled:cursor-not-allowed rounded-xl transition-colors flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                Redirecting to checkout...
              </>
            ) : (
              <>
                <Crown className="h-5 w-5" />
                Continue to Checkout
              </>
            )}
          </button>

          {/* Security note */}
          <p className="text-xs text-center text-slate-400 dark:text-slate-500 mt-4">
            Secure payment powered by Stripe.
            <br />
            You can cancel or change your plan at any time.
          </p>
        </div>

        {/* Comparison section */}
        <div className="px-5 pb-5">
          <div className="bg-slate-50 dark:bg-slate-700/50 rounded-xl p-4">
            <h4 className="text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
              Free vs Plus
            </h4>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="font-medium text-slate-600 dark:text-slate-400 mb-2">Free</p>
                <ul className="space-y-1.5 text-slate-500 dark:text-slate-400">
                  <li className="flex items-center gap-2">
                    <span className="w-4 h-4 flex items-center justify-center rounded-full bg-slate-200 dark:bg-slate-600 text-xs">-</span>
                    Reports only
                  </li>
                  <li className="flex items-center gap-2">
                    <span className="w-4 h-4 flex items-center justify-center rounded-full bg-slate-200 dark:bg-slate-600 text-xs">-</span>
                    No follow-ups
                  </li>
                </ul>
              </div>
              <div>
                <p className="font-medium text-indigo-600 dark:text-indigo-400 mb-2">Plus</p>
                <ul className="space-y-1.5 text-slate-600 dark:text-slate-300">
                  <li className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-indigo-500" />
                    Unlimited reports
                  </li>
                  <li className="flex items-center gap-2">
                    <Check className="w-4 h-4 text-indigo-500" />
                    2M tokens/mo
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Plus benefit item
 */
function PlusBenefit({ children, icon }) {
  return (
    <div className="flex items-start gap-3">
      <div className="p-1 bg-indigo-100 dark:bg-indigo-900/30 rounded text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-0.5">
        {icon}
      </div>
      <span className="text-sm text-slate-600 dark:text-slate-300">{children}</span>
    </div>
  );
}
