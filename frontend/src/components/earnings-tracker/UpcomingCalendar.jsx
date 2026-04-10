import { useState, useMemo } from 'react';

const CARD = 'bg-sand-100 dark:bg-warm-900 rounded-xl';

const SECTOR_COLORS = {
  'Technology':             'bg-vi-gold/10 border-vi-gold/20',
  'Financial Services':     'bg-vi-sage/10 border-vi-sage/20',
  'Healthcare':             'bg-vi-rose/10 border-vi-rose/20',
  'Consumer Cyclical':      'bg-violet-500/10 border-violet-500/20',
  'Industrials':            'bg-amber-500/10 border-amber-500/20',
  'Communication Services': 'bg-cyan-500/10 border-cyan-500/20',
  'Consumer Defensive':     'bg-emerald-500/10 border-emerald-500/20',
  'Energy':                 'bg-orange-500/10 border-orange-500/20',
  'Utilities':              'bg-teal-500/10 border-teal-500/20',
  'Real Estate':            'bg-indigo-500/10 border-indigo-500/20',
  'Basic Materials':        'bg-lime-500/10 border-lime-500/20',
};

function getDayLabel(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffDays = Math.floor((date - today) / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Tomorrow';
  return date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
}

function groupByDay(events) {
  const groups = {};
  for (const event of events) {
    const day = event.earnings_date;
    if (!groups[day]) groups[day] = [];
    groups[day].push(event);
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
}

function groupBySector(events) {
  const groups = {};
  for (const event of events) {
    const sector = event.sector || 'Other';
    if (!groups[sector]) groups[sector] = [];
    groups[sector].push(event);
  }
  return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
}

// --- Sub-components ---

function SectorFilterBar({ sectorCounts, activeSectors, onToggle, onClear }) {
  const sectors = Object.entries(sectorCounts).sort(([, a], [, b]) => b - a);

  return (
    <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1">
      {sectors.map(([sector, count]) => {
        const isActive = activeSectors.has(sector);
        return (
          <button
            key={sector}
            onClick={() => onToggle(sector)}
            className={`shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border ${
              isActive
                ? 'bg-vi-gold/20 text-vi-gold border-vi-gold/30'
                : 'bg-sand-50 dark:bg-warm-950/50 text-sand-500 dark:text-warm-400 border-sand-200 dark:border-warm-700 hover:border-sand-300 dark:hover:border-warm-600'
            }`}
          >
            {sector} ({count})
          </button>
        );
      })}
      {activeSectors.size > 0 && (
        <button
          onClick={onClear}
          className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-semibold text-vi-rose border border-vi-rose/30 hover:bg-vi-rose/10 transition-all"
        >
          Clear
        </button>
      )}
    </div>
  );
}

function EarningsChip({ event, onSelectTicker }) {
  return (
    <button
      onClick={() => onSelectTicker?.(event.ticker)}
      className="flex items-center justify-between px-3 py-2 rounded-lg bg-sand-50 dark:bg-warm-950/50 hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors cursor-pointer text-left w-full"
    >
      <div className="flex items-center gap-2 min-w-0">
        <span className="font-bold text-vi-gold text-sm">{event.ticker}</span>
        <span className="text-xs text-sand-500 dark:text-warm-400 hidden md:inline truncate">{event.company_name}</span>
      </div>
      <span className="text-xs font-medium text-sand-700 dark:text-warm-200 shrink-0 ml-2">
        {event.eps_estimated != null ? `$${event.eps_estimated.toFixed(2)}` : '—'}
      </span>
    </button>
  );
}

function SectorGroup({ sector, events, onSelectTicker }) {
  const colorClass = SECTOR_COLORS[sector] || 'bg-sand-200/50 border-sand-300/30';

  return (
    <div className="space-y-1.5">
      <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-widest border ${colorClass}`}>
        <span className="text-sand-600 dark:text-warm-300">{sector}</span>
        <span className="text-sand-400 dark:text-warm-500">({events.length})</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-1.5">
        {events.map(event => (
          <EarningsChip key={event.ticker} event={event} onSelectTicker={onSelectTicker} />
        ))}
      </div>
    </div>
  );
}

function DaySection({ dateStr, events, activeSectors, isExpanded, onToggle, onSelectTicker }) {
  const filteredEvents = activeSectors.size > 0
    ? events.filter(e => activeSectors.has(e.sector))
    : events;

  if (filteredEvents.length === 0) return null;

  const sectorGroups = groupBySector(filteredEvents);
  const label = getDayLabel(dateStr);

  return (
    <div className={`${CARD} overflow-hidden`}>
      <button
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-sand-200/30 dark:hover:bg-warm-800/30 transition-colors"
      >
        <span className="material-symbols-outlined text-sand-400 dark:text-warm-500 text-lg transition-transform" style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}>
          expand_more
        </span>
        <span className="font-semibold text-sm text-sand-800 dark:text-warm-50">{label}</span>
        <span className="text-xs text-sand-400 dark:text-warm-500">{dateStr}</span>
        <span className="ml-auto px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-widest bg-sand-200/50 dark:bg-warm-800/50 text-sand-500 dark:text-warm-400">
          {filteredEvents.length} {filteredEvents.length === 1 ? 'company' : 'companies'}
        </span>
      </button>
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4">
          {sectorGroups.map(([sector, sectorEvents]) => (
            <SectorGroup key={sector} sector={sector} events={sectorEvents} onSelectTicker={onSelectTicker} />
          ))}
        </div>
      )}
    </div>
  );
}

// --- Main Component ---

export default function UpcomingCalendar({ data, onSelectTicker, onLoadMore, loadingMore, hasMore }) {
  const events = useMemo(() => data?.events || [], [data]);

  const [expandedDays, setExpandedDays] = useState(() => {
    const evts = data?.events || [];
    if (evts.length > 0) return new Set([evts[0].earnings_date]);
    return new Set();
  });
  const [activeSectors, setActiveSectors] = useState(new Set());

  // Recompute when events change (e.g., after load more)
  const dayGroups = useMemo(() => groupByDay(events), [events]);

  const sectorCounts = useMemo(() => {
    const counts = {};
    for (const event of events) {
      const sector = event.sector || 'Other';
      counts[sector] = (counts[sector] || 0) + 1;
    }
    return counts;
  }, [events]);

  const uniqueDays = dayGroups.length;

  if (events.length === 0) {
    return (
      <div className={`${CARD} p-8 text-center`}>
        <span className="material-symbols-outlined text-4xl text-sand-300 dark:text-warm-700 mb-3 block">calendar_month</span>
        <p className="text-sand-500 dark:text-warm-400">No upcoming earnings in the next 30 days.</p>
        <p className="text-sm text-sand-400 dark:text-warm-500 mt-1">Calendar updates daily via EventBridge.</p>
      </div>
    );
  }

  const toggleDay = (dateStr) => {
    setExpandedDays(prev => {
      const next = new Set(prev);
      if (next.has(dateStr)) next.delete(dateStr);
      else next.add(dateStr);
      return next;
    });
  };

  const toggleSector = (sector) => {
    setActiveSectors(prev => {
      const next = new Set(prev);
      if (next.has(sector)) next.delete(sector);
      else next.add(sector);
      return next;
    });
  };

  // Check if any days are visible after sector filtering
  const hasVisibleDays = dayGroups.some(([, dayEvents]) => {
    if (activeSectors.size === 0) return true;
    return dayEvents.some(e => activeSectors.has(e.sector));
  });

  return (
    <div className="space-y-4">
      {/* Summary */}
      <div className={`${CARD} px-4 py-3 flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-vi-gold text-lg">calendar_month</span>
          <span className="text-sm text-sand-600 dark:text-warm-300">
            <span className="font-bold text-sand-800 dark:text-warm-50">{events.length}</span> companies across{' '}
            <span className="font-bold text-sand-800 dark:text-warm-50">{uniqueDays}</span> days
          </span>
        </div>
        {hasMore && (
          <span className="text-xs text-sand-400 dark:text-warm-500">More available</span>
        )}
      </div>

      {/* Sector Filter */}
      <SectorFilterBar
        sectorCounts={sectorCounts}
        activeSectors={activeSectors}
        onToggle={toggleSector}
        onClear={() => setActiveSectors(new Set())}
      />

      {/* Empty filter state */}
      {!hasVisibleDays && (
        <div className={`${CARD} p-6 text-center`}>
          <span className="material-symbols-outlined text-2xl text-sand-300 dark:text-warm-700 mb-2 block">filter_list_off</span>
          <p className="text-sm text-sand-500 dark:text-warm-400">No earnings in selected sectors.</p>
          <button
            onClick={() => setActiveSectors(new Set())}
            className="mt-2 text-xs text-vi-gold hover:underline"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Day Sections */}
      {dayGroups.map(([dateStr, dayEvents]) => (
        <DaySection
          key={dateStr}
          dateStr={dateStr}
          events={dayEvents}
          activeSectors={activeSectors}
          isExpanded={expandedDays.has(dateStr)}
          onToggle={() => toggleDay(dateStr)}
          onSelectTicker={onSelectTicker}
        />
      ))}

      {/* Load More */}
      {hasMore && (
        <div className="text-center py-2">
          <button
            onClick={onLoadMore}
            disabled={loadingMore}
            className="px-6 py-2.5 rounded-lg text-sm font-semibold bg-sand-100 dark:bg-warm-900 text-sand-600 dark:text-warm-300 hover:bg-sand-200 dark:hover:bg-warm-800 border border-sand-200 dark:border-warm-700 transition-all disabled:opacity-50"
          >
            {loadingMore ? (
              <span className="flex items-center gap-2">
                <span className="material-symbols-outlined animate-spin text-sm">progress_activity</span>
                Loading...
              </span>
            ) : (
              'Load More Earnings'
            )}
          </button>
        </div>
      )}
    </div>
  );
}
