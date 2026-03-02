import React from 'react';
import {
  Check,
  Loader2,
  ChevronRight,
  Zap,
  Building2,
  Heart,
  DollarSign,
  Shield,
  TrendingUp,
  TrendingDown,
  Percent,
  BarChart3,
  Gem,
  Users,
  Target,
  Rocket,
  AlertTriangle,
  MessageSquare,
  MessageCircle,
  FileText,
  ClipboardCheck,
  Gavel,
  PiggyBank,
  Calculator,
  Eye,
  Banknote,
  Landmark,
  PieChart,
  Crosshair,
  PanelRightClose,
  PanelRightOpen,
} from 'lucide-react';

// Icon mapping from backend section icon names to lucide-react components
const iconMap = {
  // Section-specific icons (from section_parser.py SECTION_ICONS)
  'lightning': Zap,
  'building': Building2,
  'clipboard': ClipboardCheck,
  'target': Target,
  'gavel': Gavel,
  'chart-up': TrendingUp,
  'piggy-bank': PiggyBank,
  'calculator': Calculator,
  'eye': Eye,
  'cash': Banknote,
  'bank': Landmark,
  'pie-chart': PieChart,
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  'message-circle': MessageCircle,
  'crosshair': Crosshair,
  // Aliases and fallbacks
  'zap': Zap,
  'building-2': Building2,
  'heart': Heart,
  'dollar': DollarSign,
  'dollar-sign': DollarSign,
  'shield': Shield,
  'percent': Percent,
  'bar-chart': BarChart3,
  'bar-chart-3': BarChart3,
  'gem': Gem,
  'users': Users,
  'rocket': Rocket,
  'alert-triangle': AlertTriangle,
  'message-square': MessageSquare,
  'file-text': FileText,
  'banknote': Banknote,
};

export default function TableOfContents({
  toc = [],
  activeSectionId = null,
  onSectionClick,
  onCollapse,
  onExpand,
  isCollapsed = false,
  streamedSections = {}, // Object with section_id keys and { isComplete, content } values
  currentStreamingSection = null,
}) {
  // Sort all sections by display_order
  const sortedSections = [...toc].sort((a, b) => (a.display_order || 0) - (b.display_order || 0));

  const getIcon = (iconName) => {
    const Icon = iconMap[iconName] || FileText;
    return Icon;
  };

  const getSectionStatus = (sectionId) => {
    if (currentStreamingSection === sectionId) return 'streaming';
    if (streamedSections[sectionId]?.isComplete) return 'complete';
    if (streamedSections[sectionId]?.content) return 'partial';
    return 'pending';
  };

  // Collapsed view: icon strip
  if (isCollapsed) {
    return (
      <nav className="h-full overflow-y-auto py-2 scrollbar-none flex flex-col relative">
        {onExpand && (
          <div className="flex justify-center py-1 mb-1">
            <button
              onClick={onExpand}
              className="p-1.5 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800 rounded-md transition-colors"
              title="Show contents"
            >
              <PanelRightOpen className="h-4 w-4" />
            </button>
          </div>
        )}
        <div className="flex flex-col items-center gap-1 flex-1 justify-center">
          {sortedSections.map((item) => {
            const Icon = getIcon(item.icon);
            const isActive = item.section_id === activeSectionId;
            return (
              <div key={item.section_id} className="relative group">
                <button
                  onClick={() => onSectionClick?.(item.section_id)}
                  className={`p-2 rounded-md transition-colors ${
                    isActive
                      ? 'text-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                      : 'text-sand-400 dark:text-warm-400 hover:text-sand-600 dark:hover:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </button>
                <div className="pointer-events-none absolute right-full top-1/2 -translate-y-1/2 mr-2 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap rounded-md bg-indigo-600 px-2.5 py-1.5 text-xs font-medium text-white shadow-lg">
                  {item.title}
                </div>
              </div>
            );
          })}
        </div>
      </nav>
    );
  }

  // Expanded view: full list
  return (
    <nav className="h-full overflow-y-auto py-2 scrollbar-none flex flex-col justify-center relative">
      {onCollapse && (
        <div className="absolute top-2 left-3">
          <button
            onClick={onCollapse}
            className="p-1.5 text-sand-400 hover:text-sand-600 dark:hover:text-warm-200 hover:bg-sand-100 dark:hover:bg-warm-800 rounded-md transition-colors"
            title="Hide contents"
          >
            <PanelRightClose className="h-4 w-4" />
          </button>
        </div>
      )}

      <ul className="space-y-0.5">
        {sortedSections.map((item) => {
          const Icon = getIcon(item.icon);
          const isActive = item.section_id === activeSectionId;
          const status = getSectionStatus(item.section_id);

          return (
            <li key={item.section_id}>
              <button
                onClick={() => onSectionClick?.(item.section_id)}
                className={`
                  w-full flex items-center gap-2 px-4 py-2 text-sm text-left transition-colors
                  ${isActive
                    ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border-l-2 border-indigo-500'
                    : 'text-sand-600 dark:text-warm-300 hover:bg-sand-50 dark:hover:bg-warm-900 border-l-2 border-transparent'
                  }
                `}
              >
                <Icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-indigo-500' : 'text-sand-400 dark:text-warm-400'}`} />
                <span className="flex-1 truncate">
                  {item.title}
                </span>
                <span className="flex-shrink-0">
                  {status === 'streaming' && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
                  )}
                  {status === 'complete' && (
                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                  )}
                  {status === 'partial' && (
                    <div className="h-2 w-2 rounded-full bg-amber-400" />
                  )}
                  {status === 'pending' && isActive && (
                    <ChevronRight className="h-3.5 w-3.5 text-sand-400" />
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Empty state */}
      {toc.length === 0 && (
        <div className="px-4 py-8 text-center text-sm text-sand-400 dark:text-warm-400">
          Loading table of contents...
        </div>
      )}
    </nav>
  );
}
