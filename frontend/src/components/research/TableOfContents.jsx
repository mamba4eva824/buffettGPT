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
  Percent,
  BarChart3,
  Gem,
  Users,
  Target,
  Rocket,
  AlertTriangle,
  MessageSquare,
  FileText
} from 'lucide-react';

// Icon mapping from backend icon names
const iconMap = {
  'lightning': Zap,
  'zap': Zap,
  'building': Building2,
  'building-2': Building2,
  'heart': Heart,
  'dollar': DollarSign,
  'dollar-sign': DollarSign,
  'shield': Shield,
  'trending-up': TrendingUp,
  'percent': Percent,
  'bar-chart': BarChart3,
  'bar-chart-3': BarChart3,
  'gem': Gem,
  'users': Users,
  'target': Target,
  'rocket': Rocket,
  'alert-triangle': AlertTriangle,
  'message-square': MessageSquare,
  'file-text': FileText,
};

// Group sections by part
const partLabels = {
  1: 'Executive Summary',
  2: 'Detailed Analysis',
  3: 'Real Talk',
};

export default function TableOfContents({
  toc = [],
  activeSectionId = null,
  onSectionClick,
  streamedSections = {}, // Object with section_id keys and { isComplete, content } values
  currentStreamingSection = null,
}) {
  // Group ToC entries by part
  const groupedToc = toc.reduce((acc, item) => {
    const part = item.part || 1;
    if (!acc[part]) acc[part] = [];
    acc[part].push(item);
    return acc;
  }, {});

  // Sort parts
  const sortedParts = Object.keys(groupedToc).sort((a, b) => Number(a) - Number(b));

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

  return (
    <nav className="h-full overflow-y-auto py-4 scrollbar-thin scrollbar-thumb-slate-300 dark:scrollbar-thumb-slate-600 scrollbar-track-transparent">
      <h3 className="px-4 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-3">
        Contents
      </h3>

      {sortedParts.map((part) => {
        const sections = groupedToc[part] || [];
        const showPartLabel = sections.length > 1; // Hide redundant label when only 1 section in part

        return (
        <div key={part} className="mb-4">
          {/* Part label - hidden when only 1 section (e.g., Executive Summary) */}
          {showPartLabel && (
            <div className="px-4 py-1.5 text-xs font-medium text-slate-400 dark:text-slate-500">
              {partLabels[part] || `Part ${part}`}
            </div>
          )}

          {/* Section items */}
          <ul className="space-y-0.5">
            {sections
              .sort((a, b) => (a.display_order || 0) - (b.display_order || 0))
              .map((item) => {
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
                          ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 border-l-2 border-indigo-500'
                          : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800/50 border-l-2 border-transparent'
                        }
                      `}
                    >
                      {/* Icon */}
                      <Icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-indigo-500' : 'text-slate-400 dark:text-slate-500'}`} />

                      {/* Title */}
                      <span className="flex-1 truncate">
                        {item.title}
                      </span>

                      {/* Status indicator */}
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
                          <ChevronRight className="h-3.5 w-3.5 text-slate-400" />
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
        );
      })}

      {/* Empty state */}
      {toc.length === 0 && (
        <div className="px-4 py-8 text-center text-sm text-slate-400 dark:text-slate-500">
          Loading table of contents...
        </div>
      )}
    </nav>
  );
}
