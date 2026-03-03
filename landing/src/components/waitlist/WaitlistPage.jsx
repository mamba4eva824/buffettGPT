import { useState, useEffect, useCallback } from 'react';
import { Mail, Copy, CheckCircle, ArrowRight, BarChart3, MessageSquare, BookOpen, Users, ExternalLink, TrendingUp, AlertTriangle, Calendar, ChevronRight, ChevronDown } from 'lucide-react';
import TierProgress from './TierProgress';
import { waitlistApi } from '../../api/waitlistApi';
import logger from '../../utils/logger';

const LS_KEYS = {
  email: 'waitlist.email',
  referralCode: 'waitlist.referralCode',
};

const getLS = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
const setLS = (k, v) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

const FEATURES = [
  {
    icon: BarChart3,
    title: 'Research Reports, No Jargon',
    description: 'Hedge-fund-caliber analysis translated into language you actually understand. No $500/month paywall required.',
  },
  {
    icon: MessageSquare,
    title: 'Ask Follow-Up Questions',
    description: 'Not a static PDF — it\'s a conversation. Ask "explain like I\'m 25 with $5K to invest" and get real answers.',
  },
  {
    icon: BookOpen,
    title: 'Build Real Financial Literacy',
    description: 'Each report teaches you how to think about investing. Build intuition over time, not just stock picks.',
  },
];

export default function WaitlistPage({ appUrl }) {
  const [email, setEmail] = useState('');
  const [referralCodeInput, setReferralCodeInput] = useState('');
  const [showReferralInput, setShowReferralInput] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [honeypot, setHoneypot] = useState('');
  const [showDecisionTriggers, setShowDecisionTriggers] = useState(false);

  // Dashboard state (after signup)
  const [dashboard, setDashboard] = useState(null);

  // Extract referral code from URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ref = params.get('ref');
    if (ref) {
      setReferralCodeInput(ref.toUpperCase());
      setShowReferralInput(true);
    }
  }, []);

  // Check if user already signed up (restore from localStorage)
  useEffect(() => {
    const savedEmail = getLS(LS_KEYS.email);
    const savedCode = getLS(LS_KEYS.referralCode);
    if (savedEmail && savedCode) {
      loadDashboard(savedEmail, savedCode);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const loadDashboard = useCallback(async (userEmail, userCode) => {
    try {
      const status = await waitlistApi.getStatus(userEmail, userCode);
      setDashboard(status);
    } catch (err) {
      logger.warn('Failed to load waitlist status:', err.message);
      // Clear invalid saved data
      localStorage.removeItem(LS_KEYS.email);
      localStorage.removeItem(LS_KEYS.referralCode);
    }
  }, []);

  const handleSignup = async (e) => {
    e.preventDefault();
    if (isLoading) return;
    setError('');
    setIsLoading(true);

    try {
      const result = await waitlistApi.signup(
        email.trim().toLowerCase(),
        referralCodeInput || null,
        honeypot ? { website: honeypot } : {},
      );

      // Save to localStorage for returning visits
      const userCode = result.referral_code;
      const userEmail = result.alreadyRegistered ? email.trim().toLowerCase() : result.email;
      setLS(LS_KEYS.email, userEmail);
      setLS(LS_KEYS.referralCode, userCode);

      // Load full dashboard
      await loadDashboard(userEmail, userCode);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const copyToClipboard = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const shareOnTwitter = () => {
    const text = `I just joined this waitlist — AI-powered investment research that actually makes sense. No jargon, no paywalls. Join me and skip the line:`;
    const url = dashboard?.referral_link || window.location.href;
    window.open(`https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}&url=${encodeURIComponent(url)}`, '_blank');
  };

  const shareOnLinkedIn = () => {
    const url = dashboard?.referral_link || window.location.href;
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(url)}`, '_blank');
  };

  // ========== DASHBOARD VIEW ==========
  if (dashboard) {
    return (
      <div className="min-h-screen bg-sand-50 dark:bg-warm-950">
        <div className="max-w-2xl mx-auto px-4 py-12">
          {/* Header */}
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold text-sand-900 dark:text-warm-50 mb-2">
              You&apos;re on the list!
            </h1>
            <div className="inline-flex items-center gap-2 bg-indigo-600/10 text-indigo-600 px-4 py-2 rounded-full text-sm font-medium">
              <Users size={16} />
              #{dashboard.position} in line
            </div>
          </div>

          {/* Referral Code Card */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6 mb-6">
            <h2 className="text-sm font-medium text-sand-500 dark:text-warm-300 uppercase tracking-wider mb-3">
              Your Referral Code
            </h2>
            <div className="flex items-center gap-3">
              <code className="flex-1 text-2xl font-mono font-bold text-sand-900 dark:text-warm-50 bg-sand-100 dark:bg-warm-800 px-4 py-3 rounded-lg text-center tracking-widest">
                {dashboard.referral_code}
              </code>
              <button
                onClick={() => copyToClipboard(dashboard.referral_code)}
                className="p-3 rounded-lg bg-sand-100 dark:bg-warm-800 hover:bg-sand-200 dark:hover:bg-warm-700 text-sand-600 dark:text-warm-200 transition-colors"
                title="Copy code"
              >
                {copied ? <CheckCircle size={20} className="text-green-500" /> : <Copy size={20} />}
              </button>
            </div>
          </div>

          {/* Share Link Card */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6 mb-6">
            <h2 className="text-sm font-medium text-sand-500 dark:text-warm-300 uppercase tracking-wider mb-3">
              Share Your Link
            </h2>
            <div className="flex items-center gap-2 mb-4">
              <input
                type="text"
                readOnly
                value={dashboard.referral_link}
                className="flex-1 text-sm text-sand-700 dark:text-warm-200 bg-sand-100 dark:bg-warm-800 px-3 py-2.5 rounded-lg border border-sand-200 dark:border-warm-700"
              />
              <button
                onClick={() => copyToClipboard(dashboard.referral_link)}
                className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium transition-colors"
              >
                Copy
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={shareOnTwitter}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-sand-100 dark:bg-warm-800 hover:bg-sand-200 dark:hover:bg-warm-700 text-sand-700 dark:text-warm-200 text-sm font-medium transition-colors"
              >
                <ExternalLink size={14} /> Share on X
              </button>
              <button
                onClick={shareOnLinkedIn}
                className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-sand-100 dark:bg-warm-800 hover:bg-sand-200 dark:hover:bg-warm-700 text-sand-700 dark:text-warm-200 text-sm font-medium transition-colors"
              >
                <ExternalLink size={14} /> Share on LinkedIn
              </button>
            </div>
          </div>

          {/* Tier Progress */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6 mb-6">
            <h2 className="text-sm font-medium text-sand-500 dark:text-warm-300 uppercase tracking-wider mb-6">
              Referral Rewards
            </h2>
            <TierProgress referralCount={dashboard.referral_count} />

            {dashboard.current_tier && (
              <div className="mt-6 p-3 bg-indigo-600/10 rounded-lg text-center">
                <span className="text-sm font-medium text-indigo-600">
                  Current reward: {dashboard.current_tier.reward}
                </span>
              </div>
            )}
            {dashboard.next_tier && (
              <p className="mt-3 text-sm text-sand-500 dark:text-warm-300 text-center">
                {dashboard.next_tier.referrals_needed} more referral{dashboard.next_tier.referrals_needed !== 1 ? 's' : ''} for {dashboard.next_tier.reward}
              </p>
            )}
          </div>

          {/* Navigation Links */}
          <div className="text-center space-y-2">
            <button
              onClick={() => setDashboard(null)}
              className="block mx-auto text-sm text-sand-500 dark:text-warm-300 hover:text-indigo-600 transition-colors"
            >
              &larr; Back to home
            </button>
            {appUrl && (
              <a
                href={appUrl}
                className="block mx-auto text-sm text-sand-500 dark:text-warm-300 hover:text-indigo-600 transition-colors"
              >
                Already have access? Log in &rarr;
              </a>
            )}
          </div>
        </div>
      </div>
    );
  }

  // ========== SIGNUP VIEW (Landing Page) ==========
  return (
    <div className="min-h-screen bg-sand-50 dark:bg-warm-950">
      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-5xl mx-auto">
        <span className="text-xl font-bold text-sand-900 dark:text-warm-50">
          Buffett
        </span>
        {appUrl && (
          <a
            href={appUrl}
            className="text-sm text-sand-500 dark:text-warm-300 hover:text-indigo-600 flex items-center gap-1 transition-colors"
          >
            Log in <ArrowRight size={14} />
          </a>
        )}
      </nav>

      {/* Hero */}
      <section className="max-w-3xl mx-auto px-6 pt-16 pb-12 text-center">
        <h1 className="text-4xl sm:text-5xl font-bold text-sand-900 dark:text-warm-50 mb-6">
          <span className="block">Finally Understand</span>
          <span className="block mt-2 text-indigo-600">What You&apos;re Investing In</span>
        </h1>
        <p className="text-lg text-sand-600 dark:text-warm-200 max-w-xl mx-auto mb-10">
          AI-powered research reports that turn impenetrable financial data into plain English you can actually use.
          Ask follow-up questions, get real answers — no jargon, no $500 paywalls.
        </p>

        {/* Signup Form */}
        <form onSubmit={handleSignup} className="max-w-md mx-auto">
          <div className="flex gap-2 mb-3">
            <div className="relative flex-1">
              <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-sand-400 dark:text-warm-400" />
              <input
                type="email"
                required
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-lg border border-sand-300 dark:border-warm-700 bg-white dark:bg-warm-900 text-sand-900 dark:text-warm-50 placeholder-sand-400 dark:placeholder-warm-400 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="px-6 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold transition-colors whitespace-nowrap"
            >
              {isLoading ? 'Joining...' : 'Join Waitlist'}
            </button>
          </div>
          {/* Honeypot — invisible to humans, catches bots */}
          <input
            type="text"
            name="website"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            style={{ position: 'absolute', left: '-9999px', opacity: 0, height: 0, width: 0 }}
          />

          {/* Referral code toggle */}
          {!showReferralInput ? (
            <button
              type="button"
              onClick={() => setShowReferralInput(true)}
              className="text-sm text-sand-500 dark:text-warm-300 hover:text-indigo-600 transition-colors"
            >
              Have a referral code?
            </button>
          ) : (
            <input
              type="text"
              placeholder="Enter referral code (e.g. BUFF-A3X9)"
              value={referralCodeInput}
              onChange={(e) => setReferralCodeInput(e.target.value.toUpperCase())}
              className="w-full px-4 py-2.5 rounded-lg border border-sand-300 dark:border-warm-700 bg-white dark:bg-warm-900 text-sand-900 dark:text-warm-50 placeholder-sand-400 dark:placeholder-warm-400 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent text-sm text-center tracking-widest font-mono"
            />
          )}

          {error && (
            <p className="mt-3 text-sm text-red-500">{error}</p>
          )}
        </form>
      </section>

      {/* Feature Cards */}
      <section className="max-w-5xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6"
              >
                <div className="w-10 h-10 rounded-lg bg-indigo-600/10 flex items-center justify-center mb-4">
                  <Icon size={20} className="text-indigo-600" />
                </div>
                <h3 className="text-lg font-semibold text-sand-900 dark:text-warm-50 mb-2">
                  {feature.title}
                </h3>
                <p className="text-sm text-sand-600 dark:text-warm-200">
                  {feature.description}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Pricing Tiers */}
      <section className="bg-sand-100/60 dark:bg-warm-900/30 py-12">
      <div className="max-w-4xl mx-auto px-6">
        <h2 className="text-2xl font-bold text-sand-900 dark:text-warm-50 text-center mb-3">
          Pricing
        </h2>
        <p className="text-sm text-sand-500 dark:text-warm-300 text-center mb-8 max-w-lg mx-auto">
          Start free. Upgrade when you want more.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 max-w-2xl mx-auto">
          {/* Free Tier */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6">
            <div className="mb-4">
              <h3 className="text-lg font-bold text-sand-900 dark:text-warm-50">Free</h3>
              <div className="mt-1">
                <span className="text-3xl font-bold text-sand-900 dark:text-warm-50">$0</span>
                <span className="text-sm text-sand-500 dark:text-warm-300 ml-1">/month</span>
              </div>
            </div>
            <ul className="space-y-3 text-sm">
              <li className="flex items-start gap-2 text-sand-600 dark:text-warm-200">
                <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" />
                Up to 10 investment reports/month
              </li>
              <li className="flex items-start gap-2 text-sand-400 dark:text-warm-400">
                <span className="w-4 h-4 mt-0.5 shrink-0 flex items-center justify-center text-xs">—</span>
                No follow-up questions
              </li>
              <li className="flex items-start gap-2 text-sand-400 dark:text-warm-400">
                <span className="w-4 h-4 mt-0.5 shrink-0 flex items-center justify-center text-xs">—</span>
                No earnings tracker
              </li>
            </ul>
          </div>

          {/* Plus Tier */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border-2 border-indigo-600 p-6">
            <div className="mb-4">
              <h3 className="text-lg font-bold text-sand-900 dark:text-warm-50">Plus</h3>
              <div className="mt-1">
                <span className="text-3xl font-bold text-sand-900 dark:text-warm-50">$10</span>
                <span className="text-sm text-sand-500 dark:text-warm-300 ml-1">/month</span>
              </div>
            </div>
            <ul className="space-y-3 text-sm">
              <li className="flex items-start gap-2 text-sand-600 dark:text-warm-200">
                <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" />
                Unlimited investment reports
              </li>
              <li className="flex items-start gap-2 text-sand-600 dark:text-warm-200">
                <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" />
                Follow-up questions on any report
              </li>
              <li className="flex items-start gap-2 text-sand-600 dark:text-warm-200">
                <CheckCircle size={16} className="text-green-500 mt-0.5 shrink-0" />
                Earnings tracker <span className="text-sand-400 dark:text-warm-400 ml-1">(coming soon)</span>
              </li>
            </ul>
          </div>
        </div>
      </div>
      </section>

      {/* Sample Report Preview */}
      <section className="max-w-4xl mx-auto px-6 py-12">
        <h2 className="text-2xl font-bold text-sand-900 dark:text-warm-50 text-center mb-3">
          See What You Get
        </h2>
        <p className="text-sm text-sand-500 dark:text-warm-300 text-center mb-8 max-w-lg mx-auto">
          Every report has 17 sections you can jump between — here&apos;s a peek at the executive summary and decision triggers from a real Netflix analysis.
        </p>

        <div className="space-y-6">
          {/* Executive Summary */}
          <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6 sm:p-8">
            <div className="flex items-center gap-2 mb-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600 bg-indigo-600/10 px-2.5 py-1 rounded-full">
                NFLX
              </span>
              <span className="text-xs text-sand-400 dark:text-warm-400">
                Executive Summary
              </span>
            </div>

            {/* TL;DR */}
            <h3 className="text-lg font-bold text-sand-900 dark:text-warm-50 mb-3">
              TL;DR
            </h3>
            <p className="text-sand-600 dark:text-warm-200 leading-relaxed mb-6">
              Netflix is your household&apos;s entertainment landlord — collecting rent from 300M+ homes every month,
              and almost nobody moves out. Revenue hit $45.2B (up 16% YoY), margins exploded from 14.2% to 24.3%
              in three years, and they&apos;re generating $9.5B in free cash flow while aggressively paying down debt.
              At 31.4x earnings — 22% below their 5-year average — you&apos;re getting a proven profit machine at a
              historical discount. If you&apos;re investing for the long haul, NFLX deserves a serious look.
            </p>

            {/* Quick Health Check */}
            <h4 className="text-base font-bold text-sand-900 dark:text-warm-50 mb-3">
              Quick Health Check
            </h4>
            <div className="overflow-x-auto mb-6">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-sand-200 dark:border-warm-700">
                    <th className="text-left py-2 pr-3 text-sand-500 dark:text-warm-300 font-medium">Category</th>
                    <th className="text-left py-2 pr-3 text-sand-500 dark:text-warm-300 font-medium">Question</th>
                    <th className="text-center py-2 pr-3 text-sand-500 dark:text-warm-300 font-medium w-10"></th>
                    <th className="text-left py-2 text-sand-500 dark:text-warm-300 font-medium">So What?</th>
                  </tr>
                </thead>
                <tbody className="text-sand-600 dark:text-warm-200">
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Growth</td>
                    <td className="py-2.5 pr-3">How fast are they growing?</td>
                    <td className="py-2.5 pr-3 text-center">🟢</td>
                    <td className="py-2.5">Speeding up — rare for a $45B company</td>
                  </tr>
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Profit</td>
                    <td className="py-2.5 pr-3">Are profits growing?</td>
                    <td className="py-2.5 pr-3 text-center">🟢</td>
                    <td className="py-2.5">Keeping 10 more cents per dollar than 3 years ago</td>
                  </tr>
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Cash</td>
                    <td className="py-2.5 pr-3">Is the money real?</td>
                    <td className="py-2.5 pr-3 text-center">🟢</td>
                    <td className="py-2.5">$0.92 cash for every $1 profit</td>
                  </tr>
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Quality</td>
                    <td className="py-2.5 pr-3">Is profit real or inflated?</td>
                    <td className="py-2.5 pr-3 text-center">🟡</td>
                    <td className="py-2.5">Content amortization inflates earnings — normal for streaming</td>
                  </tr>
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Debt</td>
                    <td className="py-2.5 pr-3">Do they have savings or debt?</td>
                    <td className="py-2.5 pr-3 text-center">🟡</td>
                    <td className="py-2.5">$5.4B still owed — down from $12.1B, actively paying off</td>
                  </tr>
                  <tr className="border-b border-sand-100 dark:border-warm-800">
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Dilution</td>
                    <td className="py-2.5 pr-3">Is your slice shrinking?</td>
                    <td className="py-2.5 pr-3 text-center">🟢</td>
                    <td className="py-2.5">Your slice is actually GROWING — $9.1B in buybacks</td>
                  </tr>
                  <tr>
                    <td className="py-2.5 pr-3 font-medium text-sand-700 dark:text-warm-100">Value</td>
                    <td className="py-2.5 pr-3">Is the stock cheap or expensive?</td>
                    <td className="py-2.5 pr-3 text-center">🟢</td>
                    <td className="py-2.5">22% below 5-year average — on sale vs its own history</td>
                  </tr>
                </tbody>
              </table>
            </div>

          </div>

          {/* Decision Triggers Toggle */}
          {!showDecisionTriggers ? (
            <button
              onClick={() => setShowDecisionTriggers(true)}
              className="w-full flex items-center justify-center gap-2 py-4 rounded-xl border border-dashed border-sand-300 dark:border-warm-700 text-sm font-medium text-sand-500 dark:text-warm-300 hover:text-indigo-600 hover:border-indigo-600/50 transition-colors"
            >
              <ChevronDown size={16} />
              See another section — Decision Triggers
            </button>
          ) : (
            <div className="bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800 p-6 sm:p-8">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600 bg-indigo-600/10 px-2.5 py-1 rounded-full">
                  NFLX
                </span>
                <span className="text-xs text-sand-400 dark:text-warm-400">
                  Section 17 of 17
                </span>
              </div>
              <h3 className="text-lg font-bold text-sand-900 dark:text-warm-50 mb-4">
                Decision Triggers: Watching NFLX&apos;s 17.6% Growth Line
              </h3>
              <div className="space-y-3">
                <div className="flex items-start gap-3 p-3 rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200/50 dark:border-green-800/30">
                  <TrendingUp size={16} className="text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-green-700 dark:text-green-300">Bullish signal</span>
                    <span className="text-xs text-sand-400 dark:text-warm-400 ml-2">Net margin crossing 28%</span>
                    <p className="text-sm text-sand-600 dark:text-warm-200 mt-0.5">
                      Currently 24.3% — if margins cross 28%, it would confirm operating leverage is kicking into a higher gear.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-green-50 dark:bg-green-900/10 border border-green-200/50 dark:border-green-800/30">
                  <TrendingUp size={16} className="text-green-600 dark:text-green-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-green-700 dark:text-green-300">Bullish signal</span>
                    <span className="text-xs text-sand-400 dark:text-warm-400 ml-2">Ad tier revenue exceeds $5B ARR</span>
                    <p className="text-sm text-sand-600 dark:text-warm-200 mt-0.5">
                      Not yet disclosed — would suggest a new revenue engine is proven and sustainable, strengthening the growth thesis.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200/50 dark:border-red-800/30">
                  <AlertTriangle size={16} className="text-red-500 dark:text-red-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-red-600 dark:text-red-300">Caution signal</span>
                    <span className="text-xs text-sand-400 dark:text-warm-400 ml-2">Revenue growth &lt; 10% for 2 Qs</span>
                    <p className="text-sm text-sand-600 dark:text-warm-200 mt-0.5">
                      Currently 17.6% — if growth drops below 10% for 2 consecutive quarters, it could mean the growth engine is stalling.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-red-50 dark:bg-red-900/10 border border-red-200/50 dark:border-red-800/30">
                  <AlertTriangle size={16} className="text-red-500 dark:text-red-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-red-600 dark:text-red-300">Caution signal</span>
                    <span className="text-xs text-sand-400 dark:text-warm-400 ml-2">Net margin &lt; 20% for 2 Qs</span>
                    <p className="text-sm text-sand-600 dark:text-warm-200 mt-0.5">
                      Currently 24.3% — if margins reverse below 20%, it may indicate content costs or competition are pressuring the business model.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 rounded-lg bg-sand-100 dark:bg-warm-800/50 border border-sand-200/50 dark:border-warm-700/30">
                  <Calendar size={16} className="text-sand-500 dark:text-warm-300 mt-0.5 shrink-0" />
                  <div>
                    <span className="text-sm font-medium text-sand-700 dark:text-warm-200">Check-in date</span>
                    <span className="text-xs text-sand-400 dark:text-warm-400 ml-2">Q1 2026 earnings (April 2026)</span>
                    <p className="text-sm text-sand-600 dark:text-warm-200 mt-0.5">
                      New data drops — revisit this analysis after earnings. Set a calendar reminder.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Section navigation note */}
        <div className="flex items-center justify-center gap-2 mt-6 text-sm text-sand-500 dark:text-warm-300">
          <ChevronRight size={14} />
          <span>Jump to any of 17 sections — from debt health to valuation deep dives</span>
        </div>
      </section>

      {/* Second CTA */}
      <section className="bg-sand-100/60 dark:bg-warm-900/30 py-12">
      <div className="max-w-md mx-auto px-6 text-center">
        <h2 className="text-2xl font-bold text-sand-900 dark:text-warm-50 mb-3">
          Ready to get started?
        </h2>
        <p className="text-sm text-sand-500 dark:text-warm-300 mb-6">
          Join the waitlist and be first in line when we launch.
        </p>
        <form onSubmit={handleSignup}>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <Mail size={18} className="absolute left-3 top-1/2 -translate-y-1/2 text-sand-400 dark:text-warm-400" />
              <input
                type="email"
                required
                placeholder="Enter your email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full pl-10 pr-4 py-3 rounded-lg border border-sand-300 dark:border-warm-700 bg-white dark:bg-warm-900 text-sand-900 dark:text-warm-50 placeholder-sand-400 dark:placeholder-warm-400 focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={isLoading}
              className="px-6 py-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-semibold transition-colors whitespace-nowrap"
            >
              {isLoading ? 'Joining...' : 'Join Waitlist'}
            </button>
          </div>
          {/* Honeypot */}
          <input
            type="text"
            name="website"
            value={honeypot}
            onChange={(e) => setHoneypot(e.target.value)}
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            style={{ position: 'absolute', left: '-9999px', opacity: 0, height: 0, width: 0 }}
          />
        </form>
      </div>
      </section>

      {/* Referral Rewards Section */}
      <section className="max-w-3xl mx-auto px-6 py-12">
        <h2 className="text-2xl font-bold text-sand-900 dark:text-warm-50 text-center mb-8">
          Refer Friends, Earn Rewards
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {[
            { count: '3 referrals', reward: '1 Month Free', desc: 'Plus subscription ($10 value)' },
            { count: '5 referrals', reward: '3 Months Free', desc: 'Plus subscription ($30 value)' },
          ].map((tier) => (
            <div
              key={tier.count}
              className="text-center p-6 bg-white dark:bg-warm-900 rounded-xl border border-sand-200 dark:border-warm-800"
            >
              <div className="text-sm font-medium text-indigo-600 mb-1">{tier.count}</div>
              <div className="text-lg font-bold text-sand-900 dark:text-warm-50">{tier.reward}</div>
              <div className="text-sm text-sand-500 dark:text-warm-300 mt-1">{tier.desc}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="max-w-5xl mx-auto px-6 py-8 text-center">
        <p className="text-sm text-sand-500 dark:text-warm-300">
          Your money. Your questions. Real answers.
        </p>
      </footer>
    </div>
  );
}
