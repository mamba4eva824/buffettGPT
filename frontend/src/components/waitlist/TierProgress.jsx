import { Check, Zap, Crown, Gift } from 'lucide-react';

const TIERS = [
  { threshold: 1, label: 'Early Access', icon: Zap, reward: 'Skip the waitlist' },
  { threshold: 3, label: '1 Month Free', icon: Gift, reward: '1 month free Plus' },
  { threshold: 5, label: '3 Months Free', icon: Crown, reward: '3 months free Plus' },
];

export default function TierProgress({ referralCount = 0 }) {
  const maxThreshold = TIERS[TIERS.length - 1].threshold;
  const progressPercent = Math.min((referralCount / maxThreshold) * 100, 100);

  return (
    <div className="w-full">
      {/* Progress bar */}
      <div className="relative mb-8">
        <div className="h-2 bg-sand-200 dark:bg-warm-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-600 to-indigo-400 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${progressPercent}%` }}
          />
        </div>

        {/* Milestone markers */}
        <div className="absolute top-0 left-0 right-0 flex justify-between" style={{ transform: 'translateY(-3px)' }}>
          {TIERS.map((tier) => {
            const achieved = referralCount >= tier.threshold;
            const position = (tier.threshold / maxThreshold) * 100;
            const Icon = tier.icon;

            return (
              <div
                key={tier.threshold}
                className="absolute flex flex-col items-center"
                style={{ left: `${position}%`, transform: 'translateX(-50%)' }}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center border-2 transition-colors ${
                    achieved
                      ? 'bg-indigo-600 border-indigo-600 text-white'
                      : 'bg-sand-100 dark:bg-warm-900 border-sand-300 dark:border-warm-700 text-sand-400 dark:text-warm-400'
                  }`}
                >
                  {achieved ? <Check size={14} /> : <Icon size={14} />}
                </div>
                <span className={`mt-2 text-xs font-medium text-center whitespace-nowrap ${
                  achieved ? 'text-indigo-600' : 'text-sand-500 dark:text-warm-300'
                }`}>
                  {tier.threshold} referral{tier.threshold > 1 ? 's' : ''}
                </span>
                <span className={`text-xs text-center whitespace-nowrap ${
                  achieved ? 'text-sand-700 dark:text-warm-200' : 'text-sand-400 dark:text-warm-400'
                }`}>
                  {tier.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Spacer for milestone labels */}
      <div className="h-10" />

      {/* Current status */}
      <div className="text-center">
        <span className="text-2xl font-bold text-sand-900 dark:text-warm-50">{referralCount}</span>
        <span className="text-sand-500 dark:text-warm-300 ml-1">
          referral{referralCount !== 1 ? 's' : ''}
        </span>
      </div>
    </div>
  );
}
