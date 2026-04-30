const CARD = 'bg-sand-100 dark:bg-warm-900 rounded-xl';

function beatRateColor(pctBeat) {
  if (pctBeat == null) return 'bg-sand-200 dark:bg-warm-800';
  if (pctBeat >= 80) return 'bg-vi-sage/30';
  if (pctBeat >= 65) return 'bg-vi-sage/15';
  if (pctBeat >= 50) return 'bg-vi-gold/15';
  return 'bg-vi-rose/15';
}

function beatRateText(pctBeat) {
  if (pctBeat == null) return 'text-sand-500 dark:text-warm-400';
  if (pctBeat >= 80) return 'text-vi-sage';
  if (pctBeat >= 65) return 'text-vi-sage';
  if (pctBeat >= 50) return 'text-vi-gold';
  return 'text-vi-rose';
}

export default function SeasonHeatmap({ data }) {
  const sectors = data?.sectors || [];
  const overall = data?.overall || {};
  const topBeats = data?.top_beats || [];
  const topMisses = data?.top_misses || [];

  if (sectors.length === 0) {
    return (
      <div className={`${CARD} p-8 text-center`}>
        <span className="material-symbols-outlined text-4xl text-sand-300 dark:text-warm-700 mb-3 block">bar_chart</span>
        <p className="text-sand-500 dark:text-warm-400">Season overview data not yet available.</p>
        <p className="text-sm text-sand-400 dark:text-warm-500 mt-1">Aggregated after the S&P 500 aggregator runs.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overall S&P 500 Summary */}
      <div className={`${CARD} p-6 md:p-8`}>
        <h3 className="text-lg font-serif font-bold text-sand-800 dark:text-warm-50 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-vi-gold">monitoring</span>
          S&P 500 Earnings Season
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Beat Rate</div>
            <div className={`text-2xl font-serif font-bold ${beatRateText(overall.pct_beat_eps)}`}>
              {overall.pct_beat_eps != null ? `${overall.pct_beat_eps.toFixed(1)}%` : '—'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Median Surprise</div>
            <div className={`text-2xl font-serif font-bold ${overall.median_eps_surprise_pct >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
              {overall.median_eps_surprise_pct != null ? `${overall.median_eps_surprise_pct >= 0 ? '+' : ''}${overall.median_eps_surprise_pct.toFixed(2)}%` : '—'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Reported</div>
            <div className="text-2xl font-serif font-bold text-sand-800 dark:text-warm-50">
              {overall.companies_with_earnings || '—'}
            </div>
          </div>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Total Companies</div>
            <div className="text-2xl font-serif font-bold text-sand-800 dark:text-warm-50">
              {overall.company_count || '—'}
            </div>
          </div>
        </div>
      </div>

      {/* Sector Heatmap */}
      <div className={`${CARD} p-6 md:p-8`}>
        <h3 className="text-lg font-serif font-bold text-sand-800 dark:text-warm-50 mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-vi-gold">grid_view</span>
          Sector Breakdown
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {sectors.map((sector) => (
            <div
              key={sector.sector}
              className={`${beatRateColor(sector.pct_beat_eps)} rounded-lg p-4 transition-all hover:ring-1 hover:ring-vi-gold/30`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-sm text-sand-800 dark:text-warm-50 truncate">{sector.sector}</span>
                <span className="text-xs text-sand-400 dark:text-warm-500">{sector.companies_with_earnings}/{sector.company_count}</span>
              </div>
              <div className="flex items-end justify-between">
                <div>
                  <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400">Beat Rate</div>
                  <div className={`text-xl font-serif font-bold ${beatRateText(sector.pct_beat_eps)}`}>
                    {sector.pct_beat_eps != null ? `${sector.pct_beat_eps.toFixed(1)}%` : '—'}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400">Median Surprise</div>
                  <div className={`text-lg font-serif ${sector.median_eps_surprise_pct != null && sector.median_eps_surprise_pct >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    {sector.median_eps_surprise_pct != null ? `${sector.median_eps_surprise_pct >= 0 ? '+' : ''}${sector.median_eps_surprise_pct.toFixed(2)}%` : '—'}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Top Beats & Misses */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Top Beats */}
        <div className={`${CARD} p-6`}>
          <h3 className="text-base font-serif font-bold text-sand-800 dark:text-warm-50 mb-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-vi-sage">trending_up</span>
            Biggest Beats
          </h3>
          {topBeats.length > 0 ? (
            <div className="space-y-2">
              {topBeats.map((item, i) => (
                <div key={item.ticker || i} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-sand-400 dark:text-warm-500 w-5">{i + 1}</span>
                    <span className="font-bold text-vi-gold">{item.ticker}</span>
                    <span className="text-xs text-sand-500 dark:text-warm-400 hidden md:inline truncate max-w-[120px]">{item.name}</span>
                  </div>
                  <span className="font-bold text-vi-sage">+{(item.value || 0).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-sand-400 dark:text-warm-500">No data available</p>
          )}
        </div>

        {/* Top Misses */}
        <div className={`${CARD} p-6`}>
          <h3 className="text-base font-serif font-bold text-sand-800 dark:text-warm-50 mb-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-vi-rose">trending_down</span>
            Biggest Misses
          </h3>
          {topMisses.length > 0 ? (
            <div className="space-y-2">
              {topMisses.map((item, i) => (
                <div key={item.ticker || i} className="flex items-center justify-between py-1.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-sand-400 dark:text-warm-500 w-5">{i + 1}</span>
                    <span className="font-bold text-vi-gold">{item.ticker}</span>
                    <span className="text-xs text-sand-500 dark:text-warm-400 hidden md:inline truncate max-w-[120px]">{item.name}</span>
                  </div>
                  <span className="font-bold text-vi-rose">{(item.value || 0).toFixed(2)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-sand-400 dark:text-warm-500">No data available</p>
          )}
        </div>
      </div>
    </div>
  );
}
