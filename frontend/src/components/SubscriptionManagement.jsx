import { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';
import { stripeApi } from '../api/stripeApi';
import SubscriptionCard from './SubscriptionCard';
import UpgradeModal from './UpgradeModal';

/**
 * SubscriptionManagement - Full subscription management section
 *
 * Integrates:
 * - SubscriptionCard for displaying current plan
 * - UpgradeModal for upgrading to Plus
 * - Stripe Customer Portal for managing subscription
 */
export default function SubscriptionManagement({ token, isAuthenticated }) {
  // Subscription state
  const [subscriptionData, setSubscriptionData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal state
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const [isCheckoutLoading, setIsCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);

  // Portal loading state
  const [isPortalLoading, setIsPortalLoading] = useState(false);

  /**
   * Fetch subscription status
   */
  const fetchSubscriptionStatus = useCallback(async () => {
    if (!token || !isAuthenticated) {
      setIsLoading(false);
      return;
    }

    setError(null);

    try {
      const data = await stripeApi.getSubscriptionStatus(token);
      setSubscriptionData(data);
    } catch (err) {
      console.error('Failed to fetch subscription status:', err);
      setError('Failed to load subscription status');
    } finally {
      setIsLoading(false);
    }
  }, [token, isAuthenticated]);

  // Fetch on mount and when token changes
  useEffect(() => {
    fetchSubscriptionStatus();
  }, [fetchSubscriptionStatus]);

  // Check for subscription success/cancel from URL
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const subscriptionParam = urlParams.get('subscription');

    if (subscriptionParam === 'success') {
      // Refresh subscription status after successful checkout
      fetchSubscriptionStatus();
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname);
    } else if (subscriptionParam === 'canceled') {
      // Clean up URL
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [fetchSubscriptionStatus]);

  /**
   * Handle upgrade to Plus
   */
  const handleUpgrade = async () => {
    if (!token) return;

    setIsCheckoutLoading(true);
    setCheckoutError(null);

    try {
      await stripeApi.redirectToCheckout(token, {
        successUrl: `${window.location.origin}?subscription=success`,
        cancelUrl: `${window.location.origin}?subscription=canceled`
      });
    } catch (err) {
      console.error('Checkout failed:', err);
      setCheckoutError(err.message || 'Failed to start checkout');
      setIsCheckoutLoading(false);
    }
  };

  /**
   * Handle manage subscription (open Stripe Portal)
   */
  const handleManage = async () => {
    if (!token) return;

    setIsPortalLoading(true);

    try {
      await stripeApi.redirectToPortal(token);
    } catch (err) {
      console.error('Portal redirect failed:', err);
      setError(err.message || 'Failed to open subscription management');
      setIsPortalLoading(false);
    }
  };

  // Not authenticated
  if (!isAuthenticated) {
    return (
      <div className="bg-slate-50 dark:bg-slate-800/50 rounded-xl p-6 text-center">
        <p className="text-slate-500 dark:text-slate-400">
          Sign in to manage your subscription
        </p>
      </div>
    );
  }

  // Error state
  if (error && !subscriptionData) {
    return (
      <div className="bg-white dark:bg-slate-800 rounded-xl border border-red-200 dark:border-red-800 p-6">
        <div className="flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-700 dark:text-red-300">{error}</p>
            <button
              onClick={fetchSubscriptionStatus}
              className="mt-2 text-sm text-red-600 dark:text-red-400 hover:underline flex items-center gap-1"
            >
              <RefreshCw className="h-3 w-3" />
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Subscription Card */}
      <SubscriptionCard
        subscriptionTier={subscriptionData?.subscription_tier || 'free'}
        subscriptionStatus={subscriptionData?.subscription_status}
        tokenLimit={subscriptionData?.token_limit || 0}
        cancelAtPeriodEnd={subscriptionData?.cancel_at_period_end || false}
        currentPeriodEnd={subscriptionData?.current_period_end}
        onUpgrade={() => setShowUpgradeModal(true)}
        onManage={handleManage}
        isLoading={isLoading}
      />

      {/* Portal loading indicator */}
      {isPortalLoading && (
        <div className="flex items-center justify-center gap-2 p-3 bg-slate-100 dark:bg-slate-700 rounded-lg">
          <Loader2 className="h-4 w-4 animate-spin text-slate-500" />
          <span className="text-sm text-slate-600 dark:text-slate-400">
            Opening subscription portal...
          </span>
        </div>
      )}

      {/* Upgrade Modal */}
      <UpgradeModal
        isOpen={showUpgradeModal}
        onClose={() => {
          setShowUpgradeModal(false);
          setCheckoutError(null);
        }}
        onUpgrade={handleUpgrade}
        isLoading={isCheckoutLoading}
        error={checkoutError}
      />

      {/* Inline error display */}
      {error && subscriptionData && (
        <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-500 flex-shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-300">{error}</p>
          </div>
        </div>
      )}
    </div>
  );
}
