import { useState, useEffect, useCallback } from 'react';
import { Loader2, RefreshCw, AlertCircle } from 'lucide-react';
import { stripeApi } from '../api/stripeApi';
import { waitlistApi } from '../api/waitlistApi';
import SubscriptionCard from './SubscriptionCard';
import UpgradeModal from './UpgradeModal';
import logger from '../utils/logger';

// Referral tier thresholds (must match backend REFERRAL_TRIAL_TIERS)
const REFERRAL_TRIAL_TIERS = [
  { threshold: 5, trialDays: 90 },
  { threshold: 3, trialDays: 30 },
];

/**
 * SubscriptionManagement - Full subscription management section
 *
 * Integrates:
 * - SubscriptionCard for displaying current plan
 * - UpgradeModal for upgrading to Plus
 * - Stripe Customer Portal for managing subscription
 */
export default function SubscriptionManagement({
  token,
  isAuthenticated,
  showUpgradeModal: externalShowUpgradeModal,
  onShowUpgradeModalChange,
  onTokenUsageUpdate
}) {
  // Subscription state
  const [subscriptionData, setSubscriptionData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modal state - use external control if provided for TokenUsageDisplay integration
  const [internalShowUpgradeModal, setInternalShowUpgradeModal] = useState(false);
  const showUpgradeModal = externalShowUpgradeModal !== undefined ? externalShowUpgradeModal : internalShowUpgradeModal;
  const setShowUpgradeModal = onShowUpgradeModalChange || setInternalShowUpgradeModal;
  const [isCheckoutLoading, setIsCheckoutLoading] = useState(false);
  const [checkoutError, setCheckoutError] = useState(null);

  // Referral trial eligibility
  const [referralTrialDays, setReferralTrialDays] = useState(0);

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

      // Propagate token usage to parent for settings display
      if (data.token_usage && onTokenUsageUpdate) {
        onTokenUsageUpdate(data.token_usage);
      }
    } catch (err) {
      logger.error('Failed to fetch subscription status:', err);
      setError('Failed to load subscription status');
    } finally {
      setIsLoading(false);
    }
  }, [token, isAuthenticated, onTokenUsageUpdate]);

  // Fetch on mount and when token changes
  useEffect(() => {
    fetchSubscriptionStatus();
  }, [fetchSubscriptionStatus]);

  // Check referral trial eligibility from waitlist
  useEffect(() => {
    const checkReferralEligibility = async () => {
      try {
        const waitlistEmail = localStorage.getItem('waitlist.email');
        const waitlistCode = localStorage.getItem('waitlist.referralCode');
        if (!waitlistEmail || !waitlistCode) return;

        const status = await waitlistApi.getStatus(waitlistEmail, waitlistCode);
        const referralCount = status?.referral_count || 0;

        // Determine trial days from referral count (highest tier first)
        for (const tier of REFERRAL_TRIAL_TIERS) {
          if (referralCount >= tier.threshold) {
            setReferralTrialDays(tier.trialDays);
            return;
          }
        }
      } catch {
        // Silently fail — referral check is non-critical
      }
    };

    if (isAuthenticated) {
      checkReferralEligibility();
    }
  }, [isAuthenticated]);

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
      logger.error('Checkout failed:', err);
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
      logger.error('Portal redirect failed:', err);
      setError(err.message || 'Failed to open subscription management');
      setIsPortalLoading(false);
    }
  };

  // Not authenticated
  if (!isAuthenticated) {
    return (
      <div className="bg-sand-50 dark:bg-warm-950/50 rounded-xl p-6 text-center">
        <p className="text-sand-500 dark:text-warm-300">
          Sign in to manage your subscription
        </p>
      </div>
    );
  }

  // Error state
  if (error && !subscriptionData) {
    return (
      <div className="bg-sand-50 dark:bg-warm-950 rounded-xl border border-red-200 dark:border-red-800 p-6">
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
        <div className="flex items-center justify-center gap-2 p-3 bg-sand-100 dark:bg-warm-900 rounded-lg">
          <Loader2 className="h-4 w-4 animate-spin text-sand-500" />
          <span className="text-sm text-sand-600 dark:text-warm-300">
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
        trialDays={referralTrialDays}
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
