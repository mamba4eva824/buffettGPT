const CARD = 'bg-sand-100 dark:bg-warm-900 rounded-xl';

function BeatMissBadge({ beat }) {
  if (beat == null) return <span className="text-sand-400 dark:text-warm-500 text-xs">—</span>;
  return beat ? (
    <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-widest bg-vi-sage/20 text-vi-sage">Beat</span>
  ) : (
    <span className="px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-widest bg-vi-rose/20 text-vi-rose">Miss</span>
  );
}

function SurpriseChip({ value }) {
  if (value == null) return <span className="text-sand-400 dark:text-warm-500">—</span>;
  const isPositive = value >= 0;
  const color = isPositive ? 'text-vi-sage' : 'text-vi-rose';
  const sign = isPositive ? '+' : '';
  return (
    <span className={`font-bold ${color}`}>
      {sign}{value.toFixed(2)}%
    </span>
  );
}

export default function RecentFeed({ data, onSelectTicker }) {
  const events = data?.events || [];

  if (events.length === 0) {
    return (
      <div className={`${CARD} p-8 text-center`}>
        <span className="material-symbols-outlined text-4xl text-sand-300 dark:text-warm-700 mb-3 block">event_busy</span>
        <p className="text-sand-500 dark:text-warm-400">No recent earnings reports yet.</p>
        <p className="text-sm text-sand-400 dark:text-warm-500 mt-1">Data updates at 11:30 AM and 5:00 PM ET on weekdays.</p>
      </div>
    );
  }

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-sand-200/50 dark:bg-warm-800/50">
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Company</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Sector</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300">Date</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">EPS Actual</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">EPS Est.</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-center">Result</th>
              <th className="px-6 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 text-right">Surprise</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
            {events.map((event, i) => (
              <tr
                key={`${event.earnings_date}-${event.ticker}`}
                className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors cursor-pointer ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}
                onClick={() => onSelectTicker?.(event.ticker)}
              >
                <td className="px-6 py-4">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-vi-gold">{event.ticker}</span>
                    <span className="text-sm text-sand-500 dark:text-warm-400 hidden md:inline truncate max-w-[180px]">{event.company_name}</span>
                  </div>
                </td>
                <td className="px-6 py-4 text-sm text-sand-500 dark:text-warm-400 hidden lg:table-cell">{event.sector}</td>
                <td className="px-6 py-4 text-sm text-sand-600 dark:text-warm-200">{event.earnings_date}</td>
                <td className="px-6 py-4 text-right font-medium text-sand-800 dark:text-warm-50">
                  {event.eps_actual != null ? `$${event.eps_actual.toFixed(2)}` : '—'}
                </td>
                <td className="px-6 py-4 text-right text-sand-500 dark:text-warm-400">
                  {event.eps_estimated != null ? `$${event.eps_estimated.toFixed(2)}` : '—'}
                </td>
                <td className="px-6 py-4 text-center">
                  <BeatMissBadge beat={event.eps_beat} />
                </td>
                <td className="px-6 py-4 text-right">
                  <SurpriseChip value={event.eps_surprise_pct} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
