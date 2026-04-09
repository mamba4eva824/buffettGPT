const CARD = 'bg-sand-100 dark:bg-warm-900 rounded-xl';

function getWeekLabel(dateStr) {
  const date = new Date(dateStr + 'T00:00:00');
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const diffDays = Math.floor((date - today) / (1000 * 60 * 60 * 24));
  if (diffDays <= 0) return 'Today';
  if (diffDays <= 7) return 'This Week';
  if (diffDays <= 14) return 'Next Week';

  // Format as "Week of Mon DD"
  const weekStart = new Date(date);
  weekStart.setDate(weekStart.getDate() - weekStart.getDay() + 1); // Monday
  return `Week of ${weekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
}

function groupByWeek(events) {
  const groups = {};
  for (const event of events) {
    const week = getWeekLabel(event.earnings_date);
    if (!groups[week]) groups[week] = [];
    groups[week].push(event);
  }
  return groups;
}

function WeekBadge({ label }) {
  const isThisWeek = label === 'This Week' || label === 'Today';
  return (
    <span className={`px-3 py-1 rounded text-[10px] font-bold uppercase tracking-widest ${
      isThisWeek ? 'bg-vi-gold/20 text-vi-gold' : 'bg-sand-200 dark:bg-warm-800 text-sand-500 dark:text-warm-400'
    }`}>
      {label}
    </span>
  );
}

export default function UpcomingCalendar({ data, onSelectTicker }) {
  const events = data?.events || [];

  if (events.length === 0) {
    return (
      <div className={`${CARD} p-8 text-center`}>
        <span className="material-symbols-outlined text-4xl text-sand-300 dark:text-warm-700 mb-3 block">calendar_month</span>
        <p className="text-sand-500 dark:text-warm-400">No upcoming earnings in the next 30 days.</p>
        <p className="text-sm text-sand-400 dark:text-warm-500 mt-1">Calendar updates daily via EventBridge.</p>
      </div>
    );
  }

  const grouped = groupByWeek(events);

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([weekLabel, weekEvents]) => (
        <div key={weekLabel}>
          <div className="flex items-center gap-3 mb-3">
            <WeekBadge label={weekLabel} />
            <span className="text-sm text-sand-400 dark:text-warm-500">{weekEvents.length} {weekEvents.length === 1 ? 'company' : 'companies'}</span>
          </div>
          <div className={`${CARD} overflow-hidden`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                    <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Company</th>
                    <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Sector</th>
                    <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Date</th>
                    <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">EPS Est.</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                  {weekEvents.map((event, i) => (
                    <tr
                      key={`${event.earnings_date}-${event.ticker}`}
                      className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors cursor-pointer ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}
                      onClick={() => onSelectTicker?.(event.ticker)}
                    >
                      <td className="px-6 py-3.5">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-vi-gold">{event.ticker}</span>
                          <span className="text-sm text-sand-500 dark:text-warm-400 hidden md:inline truncate max-w-[180px]">{event.company_name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-3.5 text-sm text-sand-500 dark:text-warm-400 hidden lg:table-cell">{event.sector}</td>
                      <td className="px-6 py-3.5 text-sm text-sand-600 dark:text-warm-200">{event.earnings_date}</td>
                      <td className="px-6 py-3.5 text-right font-medium text-sand-800 dark:text-warm-50">
                        {event.eps_estimated != null ? `$${event.eps_estimated.toFixed(2)}` : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
