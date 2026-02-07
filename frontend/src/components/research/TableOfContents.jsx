import React, { useState, useEffect } from 'react';
import {
  Check,
  Loader2,
  ChevronRight,
  ChevronDown,
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
  // Track which parts are expanded (default: all expanded)
  const [expandedParts, setExpandedParts] = useState({});

  // Group ToC entries by part
  const groupedToc = toc.reduce((acc, item) => {
    const part = item.part || 1;
    if (!acc[part]) acc[part] = [];
    acc[part].push(item);
    return acc;
  }, {});

  // Sort parts
  const sortedParts = Object.keys(groupedToc).sort((a, b) => Number(a) - Number(b));

  // Initialize expanded state when toc loads (all expanded by default)
  useEffect(() => {
    if (sortedParts.length > 0 && Object.keys(expandedParts).length === 0) {
      const initialExpanded = {};
      sortedParts.forEach(part => {
        initialExpanded[part] = true;
      });
      setExpandedParts(initialExpanded);
    }
  }, [sortedParts.length]);

  // Auto-expand the part containing the active section
  useEffect(() => {
    if (activeSectionId) {
      const activeItem = toc.find(item => item.section_id === activeSectionId);
      if (activeItem) {
        const part = activeItem.part || 1;
        setExpandedParts(prev => ({
          ...prev,
          [part]: true,
        }));
      }
    }
  }, [activeSectionId, toc]);

  // Toggle part expansion
  const togglePart = (part) => {
    setExpandedParts(prev => ({
      ...prev,
      [part]: !prev[part],
    }));
  };

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
    <nav className="h-full overflow-y-auto py-4 scrollbar-thin scrollbar-thumb-sand-300 dark:scrollbar-thumb-warm-700 scrollbar-track-transparent">
      <h3 className="px-4 text-xs font-semibold text-sand-500 dark:text-warm-300 uppercase tracking-wider mb-3">
        Contents
      </h3>

      {sortedParts.map((part) => {
        const sections = groupedToc[part] || [];
        const isExpanded = expandedParts[part] !== false;
        const completedCount = sections.filter(s => streamedSections[s.section_id]?.isComplete).length;
        const hasActiveSection = sections.some(s => s.section_id === activeSectionId);

        return (
        <div key={part} className="mb-2">
          {/* Part header - clickable to expand/collapse */}
          <button
            onClick={() => togglePart(part)}
            className={`
              w-full flex items-center gap-2 px-4 py-2 text-xs font-semibold uppercase tracking-wider
              text-sand-500 dark:text-warm-300 hover:text-sand-700 dark:hover:text-warm-200
              hover:bg-sand-100 dark:hover:bg-warm-700/50 transition-colors rounded-md mx-1
              ${hasActiveSection && !isExpanded ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''}
            `}
          >
            {/* Expand/collapse chevron */}
            {isExpanded ? (
              <ChevronDown className="h-3.5 w-3.5 flex-shrink-0" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 flex-shrink-0" />
            )}

            {/* Part label */}
            <span className="flex-1 text-left">
              {partLabels[part] || `Part ${part}`}
            </span>

            {/* Progress badge */}
            <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-sand-200 dark:bg-warm-800 text-sand-600 dark:text-warm-200">
              {completedCount}/{sections.length}
            </span>
          </button>

          {/* Section items - collapsible */}
          <div
            className={`
              overflow-hidden transition-all duration-200 ease-in-out
              ${isExpanded ? 'max-h-[1000px] opacity-100' : 'max-h-0 opacity-0'}
            `}
          >
            <ul className="space-y-0.5 mt-1">
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
                            ? 'bg-indigo-50 dark:bg-indigo-900/20 text-indigo-700 dark:text-indigo-300 border-l-2 border-indigo-500'
                            : 'text-sand-600 dark:text-warm-300 hover:bg-sand-50 dark:hover:bg-warm-700/50 border-l-2 border-transparent'
                          }
                        `}
                      >
                        {/* Icon */}
                        <Icon className={`h-4 w-4 flex-shrink-0 ${isActive ? 'text-indigo-500' : 'text-sand-400 dark:text-warm-400'}`} />

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
                            <ChevronRight className="h-3.5 w-3.5 text-sand-400" />
                          )}
                        </span>
                      </button>
                    </li>
                  );
                })}
            </ul>
          </div>
        </div>
        );
      })}

      {/* Empty state */}
      {toc.length === 0 && (
        <div className="px-4 py-8 text-center text-sm text-sand-400 dark:text-warm-400">
          Loading table of contents...
        </div>
      )}
    </nav>
  );
}
