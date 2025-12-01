import { motion } from 'framer-motion';

/**
 * BubbleTabs - Safari/iOS 26 style pill tabs for switching between expert analyses
 *
 * Features:
 * - Pill-shaped container with frosted glass effect
 * - Signal emoji indicators (red/yellow/green circles)
 * - Confidence percentage badges
 * - Streaming indicator animation
 * - Smooth tab switching with Framer Motion
 */
const BubbleTabs = ({ activeTab, onTabChange, results = {} }) => {
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

  const getSignalColor = (signal) => {
    const colorMap = {
      'SELL': 'text-red-500',
      'HOLD': 'text-yellow-500',
      'BUY': 'text-green-500'
    };
    return colorMap[signal] || 'text-gray-400';
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
          const isActive = activeTab === tab.id;
          const isStreaming = result.isStreaming;
          const hasResult = result.prediction && !isStreaming;

          return (
            <motion.button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`
                relative flex items-center justify-center gap-2
                px-4 py-2
                rounded-full
                text-sm font-medium
                transition-all duration-200 ease-out
                focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-1
                ${isActive
                  ? 'bg-white dark:bg-gray-600 shadow-sm text-gray-900 dark:text-white'
                  : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-gray-600/50'
                }
              `}
              whileTap={{ scale: 0.97 }}
              layout
            >
              {/* Signal emoji (shows after inference completes) */}
              {hasResult && (
                <motion.span
                  className="text-sm"
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

              {/* Confidence percentage (subtle, shows after inference) */}
              {hasResult && result.confidence && (
                <motion.span
                  className="text-xs text-gray-400 dark:text-gray-500 tabular-nums"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.2 }}
                >
                  {Math.round(result.confidence * 100)}%
                </motion.span>
              )}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
};

export default BubbleTabs;
