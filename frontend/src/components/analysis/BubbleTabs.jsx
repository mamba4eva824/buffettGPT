import { motion } from 'framer-motion';

/**
 * BubbleTabs - Safari/iOS style pill display for prediction summary
 *
 * Features:
 * - Pill-shaped container with frosted glass effect
 * - Signal emoji indicators (red/yellow/green circles)
 * - Confidence ring visualization
 * - Strong/Moderate/Weak confidence labels
 * - Streaming indicator animation
 * - readOnly mode: displays all predictions without tab switching
 * - Interactive mode (legacy): allows clicking to switch active tab
 */

// Confidence ring component - shows confidence level with signal-colored ring
const ConfidenceRing = ({ confidence, signal }) => {
  const radius = 14;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference * (1 - (confidence || 0));
  const percentage = Math.round((confidence || 0) * 100);

  // Ring color matches the prediction signal
  const colors = {
    SELL: { ring: 'stroke-red-500', bg: 'stroke-red-200 dark:stroke-red-900', text: 'fill-red-600 dark:fill-red-400' },
    HOLD: { ring: 'stroke-yellow-500', bg: 'stroke-yellow-200 dark:stroke-yellow-900', text: 'fill-yellow-600 dark:fill-yellow-400' },
    BUY: { ring: 'stroke-green-500', bg: 'stroke-green-200 dark:stroke-green-900', text: 'fill-green-600 dark:fill-green-400' }
  };

  const color = colors[signal] || { ring: 'stroke-slate-500', bg: 'stroke-slate-200', text: 'fill-slate-600' };

  return (
    <svg width="36" height="36" className="flex-shrink-0">
      {/* Background circle */}
      <circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        strokeWidth="3"
        className={color.bg}
      />
      {/* Animated progress circle */}
      <motion.circle
        cx="18"
        cy="18"
        r={radius}
        fill="none"
        strokeWidth="3"
        className={color.ring}
        strokeDasharray={circumference}
        strokeLinecap="round"
        transform="rotate(-90 18 18)"
        initial={{ strokeDashoffset: circumference }}
        animate={{ strokeDashoffset }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      />
      {/* Percentage text in center */}
      <text
        x="18"
        y="18"
        textAnchor="middle"
        dominantBaseline="central"
        className={`text-[10px] font-semibold ${color.text}`}
      >
        {percentage}
      </text>
    </svg>
  );
};

const BubbleTabs = ({
  activeTab,
  onTabChange,
  results = {},
  readOnly = false  // When true, displays as summary without tab switching
}) => {
  const tabs = [
    { id: 'debt', label: 'Debt', emoji: '📊' },
    { id: 'cashflow', label: 'Cashflow', emoji: '💰' },
    { id: 'growth', label: 'Growth', emoji: '📈' }
  ];

  const getSignalEmoji = (signal) => {
    const signalMap = {
      'SELL': '🔴',
      'HOLD': '🟡',
      'BUY': '🟢'
    };
    return signalMap[signal] || '⚪';
  };

  return (
    <div className="flex justify-center mb-4">
      {/* Outer container - Safari-style gray rounded bar */}
      <div className="
        inline-flex gap-1 p-1
        bg-gray-200/80 dark:bg-gray-700/80
        backdrop-blur-sm
        rounded-full
        shadow-inner
      ">
        {tabs.map((tab) => {
          const result = results[tab.id] || {};
          const isActive = !readOnly && activeTab === tab.id;
          const isStreaming = result.isStreaming;
          const hasResult = result.prediction && !isStreaming;

          // In readOnly mode, use div instead of button
          const Component = readOnly ? 'div' : motion.button;
          const interactiveProps = readOnly ? {} : {
            onClick: () => onTabChange?.(tab.id),
            whileTap: { scale: 0.97 }
          };

          return (
            <Component
              key={tab.id}
              {...interactiveProps}
              className={`
                relative flex items-center justify-center gap-2
                px-4 py-2
                rounded-full
                text-sm font-medium
                transition-all duration-200 ease-out
                ${!readOnly ? 'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1' : ''}
                ${readOnly
                  ? 'bg-white/60 dark:bg-gray-600/60 text-gray-700 dark:text-gray-200'
                  : isActive
                    ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-gray-600/50 cursor-pointer'
                }
              `}
            >
              {/* Signal emoji (shows after inference completes) */}
              {hasResult && (
                <motion.span
                  className="text-base"
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ type: 'spring', stiffness: 500, damping: 25 }}
                >
                  {getSignalEmoji(result.prediction)}
                </motion.span>
              )}

              {/* Loading indicator while streaming */}
              {isStreaming && (
                <motion.span
                  className="w-2 h-2 bg-blue-500 rounded-full"
                  animate={{
                    opacity: [1, 0.3, 1],
                    scale: [1, 0.8, 1]
                  }}
                  transition={{
                    repeat: Infinity,
                    duration: 1,
                    ease: 'easeInOut'
                  }}
                />
              )}

              {/* Tab label */}
              <span>{tab.label}</span>

              {/* Confidence ring with percentage inside (neutral color) */}
              {hasResult && result.confidence && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: 0.25, type: 'spring', stiffness: 400 }}
                >
                  <ConfidenceRing confidence={result.confidence} signal={result.prediction} />
                </motion.div>
              )}
            </Component>
          );
        })}
      </div>
    </div>
  );
};

export default BubbleTabs;
