import { useEffect, useCallback } from 'react';
import { X, User, Crown, Zap, Info, Quote, Check } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { Avatar } from './Avatar.jsx';
import TokenUsageDisplay from './TokenUsageDisplay.jsx';
import SubscriptionManagement from './SubscriptionManagement.jsx';

/**
 * SettingsPanel — Slide-out settings panel with organized sections.
 *
 * Sections:
 *  1. Profile — avatar, name, email (auth) or username input (unauth)
 *  2. Subscription & Usage — TokenUsageDisplay + SubscriptionManagement
 *  3. About — tagline, version, links
 */
export default function SettingsPanel({
  isOpen,
  onClose,
  // Auth
  user,
  isAuthenticated,
  // Profile
  userName,
  onUserNameChange,
  // Subscription & usage
  tokenUsage,
  token,
  showUpgradeModal,
  onShowUpgradeModalChange,
  onTokenUsageUpdate,
}) {
  // Close on Escape key
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
      return () => document.removeEventListener('keydown', handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed right-0 top-0 z-50 h-full w-full md:max-w-xl overflow-y-auto bg-sand-50 dark:bg-warm-950 shadow-xl"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-sand-100 dark:border-warm-800 px-4 md:px-6 py-4 sticky top-0 bg-sand-50 dark:bg-warm-950 z-10">
              <h2 className="text-base font-semibold text-sand-900 dark:text-warm-50">Settings</h2>
              <button
                onClick={onClose}
                className="rounded-lg p-2 text-sand-500 dark:text-warm-300 hover:bg-sand-100 dark:hover:bg-warm-800 transition-colors"
                aria-label="Close settings"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            {/* Content */}
            <div className="px-4 md:px-6 py-5 space-y-8">
              {/* ── Section 1: Profile ── */}
              <SettingsSection icon={User} title="Profile">
                {isAuthenticated && user ? (
                  <div className="space-y-3">
                    {/* User card */}
                    <div className="flex items-center gap-4 p-3 rounded-lg bg-sand-100/50 dark:bg-warm-900/50">
                      <Avatar
                        src={user?.picture || ''}
                        alt={user?.name || user?.email || 'User'}
                        size="w-12 h-12"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-sm font-semibold text-sand-900 dark:text-warm-50 truncate">
                          {user?.name || 'User'}
                        </div>
                        <div className="text-xs text-sand-500 dark:text-warm-300 truncate">
                          {user?.email || ''}
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-sand-500 dark:text-warm-300">Display Name</label>
                      <input
                        value={userName}
                        onChange={(e) => onUserNameChange(e.target.value)}
                        className="w-full rounded-lg border border-sand-200 dark:border-warm-800 bg-sand-50 dark:bg-warm-900 px-3 py-2 text-sm text-sand-900 dark:text-warm-50 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100 dark:focus:ring-indigo-900"
                        placeholder="Enter a display name"
                      />
                    </div>
                    <p className="text-[11px] text-sand-400 dark:text-warm-400">
                      Sign in with Google for a persistent profile and full features.
                    </p>
                  </div>
                )}
              </SettingsSection>

              {/* ── Section 2: Subscription & Usage ── */}
              {/* ── Section 2: Usage ── */}
              <SettingsSection icon={Zap} title="Usage">
                <TokenUsageDisplay
                  tokenUsage={tokenUsage}
                  isAuthenticated={isAuthenticated}
                  onUpgrade={() => onShowUpgradeModalChange(true)}
                />
              </SettingsSection>

              {/* ── Section 3: Subscription ── */}
              <SettingsSection icon={Crown} title="Subscription">
                <SubscriptionManagement
                  token={token}
                  isAuthenticated={isAuthenticated}
                  showUpgradeModal={showUpgradeModal}
                  onShowUpgradeModalChange={onShowUpgradeModalChange}
                  onTokenUsageUpdate={onTokenUsageUpdate}
                />
              </SettingsSection>

              {/* ── Section 3: About ── */}
              <SettingsSection icon={Info} title="About">
                <div className="space-y-4">
                  {/* Mission */}
                  <div className="rounded-lg bg-sand-100/50 dark:bg-warm-900/50 p-4">
                    <div className="text-base font-semibold text-sand-800 dark:text-warm-100 mb-1">BuffettGPT</div>
                    <p className="text-sm text-sand-500 dark:text-warm-300 leading-relaxed">
                      Making investment research accessible to everyone &mdash; not just Wall Street.
                    </p>
                  </div>

                  {/* Feature highlights */}
                  <div className="space-y-2">
                    <div className="text-sm font-medium text-sand-600 dark:text-warm-200">What you can do</div>
                    {[
                      'In-depth research reports on any public company',
                      'Follow-up Q&A with an AI trained on investing principles',
                      'Track and compare companies across key financial metrics',
                    ].map((feature) => (
                      <div key={feature} className="flex items-start gap-2">
                        <Check className="h-4 w-4 text-green-500 dark:text-green-400 mt-0.5 shrink-0" />
                        <span className="text-sm text-sand-500 dark:text-warm-300">{feature}</span>
                      </div>
                    ))}
                  </div>

                  {/* Buffett quote */}
                  <div className="rounded-lg border border-sand-200 dark:border-warm-800 p-4">
                    <Quote className="h-5 w-5 text-sand-300 dark:text-warm-600 mb-2" />
                    <p className="text-sm italic text-sand-600 dark:text-warm-200 leading-relaxed">
                      &ldquo;Price is what you pay. Value is what you get.&rdquo;
                    </p>
                    <p className="text-xs text-sand-400 dark:text-warm-400 mt-1">
                      &mdash; Warren Buffett
                    </p>
                  </div>

                  {/* Version */}
                  <div className="text-sm text-sand-400 dark:text-warm-400 text-center">
                    Version 1.0.0
                  </div>
                </div>
              </SettingsSection>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

/**
 * Reusable section wrapper with icon + title header and divider.
 */
function SettingsSection({ icon: Icon, title, children }) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="h-4 w-4 text-sand-400 dark:text-warm-400" />
        <h3 className="text-xs font-semibold uppercase tracking-wider text-sand-400 dark:text-warm-400">
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}
