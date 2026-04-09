import { useMemo, useCallback } from 'react';
import { fmt } from './mockData';
import { MetricBar, RatingBadge, CARD, DeltaChip, BentoTile, CagrChart, DuPontBlock, MetricTooltip, useFilteredData } from './shared';

export function GrowthPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  // Chart bars — all quarters in the selected time range
  const chartQuarters = filtered;
  const maxRevenue = Math.max(...chartQuarters.map(q => q.revenue_profit.revenue));

  // CAGR calculations
  const years = useMemo(() => {
    if (!earliest || !latest) return 0;
    return (new Date(latest.fiscal_date) - new Date(earliest.fiscal_date)) / (365.25 * 24 * 3600 * 1000);
  }, [earliest, latest]);

  const calcCagr = useCallback((latestVal, earliestVal) => {
    if (!latestVal || !earliestVal || earliestVal <= 0 || years <= 0) return null;
    return Math.pow(latestVal / earliestVal, 1 / years) - 1;
  }, [years]);

  const revCagr = useMemo(() => calcCagr(latest?.revenue_profit.revenue, earliest?.revenue_profit.revenue), [latest, earliest, calcCagr]);
  const epsCagr = useMemo(() => calcCagr(latest?.revenue_profit.eps, earliest?.revenue_profit.eps), [latest, earliest, calcCagr]);

  // Acceleration: latest YoY vs CAGR
  const latestRevYoY = latest?.revenue_profit.revenue_growth_yoy;
  const isAccelerating = (latestRevYoY != null && revCagr != null) ? latestRevYoY > revCagr : null;

  // TTM calculations
  const ttm = useMemo(() => {
    if (filtered.length < 4) return null;
    const last4 = filtered.slice(-4);
    const prior4 = filtered.length >= 8 ? filtered.slice(-8, -4) : null;
    const sum = (arr, fn) => arr.reduce((s, q) => s + fn(q), 0);
    const ttmRev = sum(last4, q => q.revenue_profit.revenue);
    const ttmNI = sum(last4, q => q.revenue_profit.net_income);
    const ttmEPS = sum(last4, q => q.revenue_profit.eps);
    const ttmFCF = sum(last4, q => q.cashflow.free_cash_flow);
    let revGrowth = null, epsGrowth = null;
    if (prior4) {
      const pRev = sum(prior4, q => q.revenue_profit.revenue);
      const pEPS = sum(prior4, q => q.revenue_profit.eps);
      if (pRev > 0) revGrowth = (ttmRev - pRev) / Math.abs(pRev);
      if (pEPS !== 0) epsGrowth = (ttmEPS - pEPS) / Math.abs(pEPS);
    }
    return { revenue: ttmRev, netIncome: ttmNI, eps: ttmEPS, fcf: ttmFCF, revGrowth, epsGrowth };
  }, [filtered]);

  // Growth consistency
  const consistency = useMemo(() => {
    const withGrowth = filtered.filter(q => q.revenue_profit.revenue_growth_yoy != null);
    if (withGrowth.length === 0) return null;
    const positive = withGrowth.filter(q => q.revenue_profit.revenue_growth_yoy > 0).length;
    return { positive, total: withGrowth.length };
  }, [filtered]);

  // Growth quality: revenue growth vs EPS growth
  const growthQuality = useMemo(() => {
    if (!ttm?.revGrowth || !ttm?.epsGrowth) return null;
    const diff = ttm.epsGrowth - ttm.revGrowth;
    if (diff > 0.05) return { label: 'Buyback Boosted', desc: 'EPS growing faster than revenue due to share repurchases', color: 'text-vi-gold', bg: 'bg-vi-gold/10' };
    if (diff < -0.05) return { label: 'Margin Pressure', desc: 'Earnings lagging revenue — costs growing faster', color: 'text-vi-rose', bg: 'bg-vi-rose/10' };
    return { label: 'Organic Growth', desc: 'Earnings keep pace with revenue — healthy fundamental growth', color: 'text-vi-sage', bg: 'bg-vi-sage/10' };
  }, [ttm]);

  // Table data — simplified to 6 columns
  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      revenue: q.revenue_profit.revenue,
      revYoY: q.revenue_profit.revenue_growth_yoy,
      netIncome: q.revenue_profit.net_income,
      niYoY: q.revenue_profit.net_income_growth_yoy,
      eps: q.revenue_profit.eps,
      revDelta: prev ? fmt.delta(q.revenue_profit.revenue, prev.revenue_profit.revenue) : null,
      epsDelta: prev ? fmt.delta(q.revenue_profit.eps, prev.revenue_profit.eps) : null,
    };
  });

  // Sparkline data
  const revenueSparkline = filtered.map(q => q.revenue_profit.revenue);
  const epsSparkline = filtered.map(q => q.revenue_profit.eps);
  const netMarginSparkline = filtered.map(q => q.revenue_profit.net_margin);
  const grossProfitSparkline = filtered.map(q => q.revenue_profit.gross_profit);

  const yoyColor = (v) => v == null ? 'text-sand-400 dark:text-warm-400' : v < 0 ? 'text-vi-rose font-bold' : 'text-vi-sage font-bold';

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column */}
      <section className="xl:col-span-8 space-y-6">
        {/* Revenue & Earnings Bar Chart */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Revenue & Net Income Growth</h3>
            <RatingBadge rating={ratings?.growth?.rating} />
          </div>
          <div className="relative h-[320px] w-full mt-4 flex items-end justify-between gap-1 md:gap-2 px-2">
            {chartQuarters.map((q) => {
              const revHeight = (q.revenue_profit.revenue / maxRevenue) * 100;
              const niRatio = q.revenue_profit.net_income / q.revenue_profit.revenue;
              const growth = q.revenue_profit.revenue_growth_yoy;
              const barColor = growth == null ? 'bg-sand-300 dark:bg-warm-700' : growth >= 0 ? 'bg-vi-sage/30 dark:bg-vi-sage/20' : 'bg-vi-rose/30 dark:bg-vi-rose/20';
              const barHover = growth == null ? 'group-hover:bg-sand-400 dark:group-hover:bg-warm-600' : growth >= 0 ? 'group-hover:bg-vi-sage/50' : 'group-hover:bg-vi-rose/50';
              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${revHeight}%` }}>
                  <div className={`absolute inset-0 ${barColor} ${barHover} rounded-t-lg transition-all`} />
                  <div className="absolute inset-x-0 bottom-0 bg-vi-gold/50 rounded-t-lg group-hover:bg-vi-gold/70 transition-all" style={{ height: `${niRatio * 100}%` }} />
                  {growth != null && (
                    <div className={`absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] font-bold whitespace-nowrap ${growth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {growth >= 0 ? '+' : ''}{(growth * 100).toFixed(0)}%
                    </div>
                  )}
                  <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-500 dark:text-warm-300 whitespace-nowrap">{q.fiscal_quarter}</div>
                  <div className="absolute -bottom-[18px] left-1/2 -translate-x-1/2 text-[8px] text-sand-400 dark:text-warm-500 whitespace-nowrap">{q.fiscal_year}</div>
                  <div className="absolute -top-[82px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div>Rev: {fmt.billions(q.revenue_profit.revenue)}</div>
                    <div>NI: {fmt.billions(q.revenue_profit.net_income)}</div>
                    <div>Margin: {fmt.pct(q.revenue_profit.net_margin)}</div>
                    {growth != null && (<div className={growth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}>YoY: {fmt.pctSigned(growth)}</div>)}
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-6 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/30 rounded-sm border border-vi-sage/50" />Revenue (growth)</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-rose/30 rounded-sm border border-vi-rose/50" />Revenue (decline)</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-gold/60 rounded-sm" />Net Income</div>
          </div>
        </div>

        {/* Growth Snapshot — BentoTiles replacing flat TTM */}
        <div className={CARD}>
          <div className="flex items-center gap-2 mb-2">
            <span className="material-symbols-outlined text-vi-gold text-lg">calendar_today</span>
            <h3 className="font-serif text-lg text-sand-800 dark:text-warm-50">Growth Snapshot</h3>
          </div>
          <p className="text-[11px] text-sand-500 dark:text-warm-400 mb-4 italic">Trailing twelve months vs prior period</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className={`${CARD} !p-4 relative overflow-hidden`}>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">TTM Revenue</div>
              <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{ttm ? fmt.billions(ttm.revenue) : '—'}</div>
              {ttm?.revGrowth != null && (<div className={`text-[10px] mt-1 font-bold ${ttm.revGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>{fmt.pctSigned(ttm.revGrowth)} YoY</div>)}
              {revenueSparkline.length > 1 && <div className="absolute right-2 bottom-2 opacity-40"><svg width="60" height="20"><polyline points={revenueSparkline.map((v, i) => `${(i / (revenueSparkline.length - 1)) * 60},${20 - ((v - Math.min(...revenueSparkline)) / (Math.max(...revenueSparkline) - Math.min(...revenueSparkline) || 1)) * 16 - 2}`).join(' ')} fill="none" stroke="#a0d6ad" strokeWidth="1.5" /></svg></div>}
            </div>
            <div className={`${CARD} !p-4 relative overflow-hidden`}>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">TTM EPS</div>
              <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{ttm ? fmt.eps(ttm.eps) : '—'}</div>
              {ttm?.epsGrowth != null && (<div className={`text-[10px] mt-1 font-bold ${ttm.epsGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>{fmt.pctSigned(ttm.epsGrowth)} YoY</div>)}
              {epsSparkline.length > 1 && <div className="absolute right-2 bottom-2 opacity-40"><svg width="60" height="20"><polyline points={epsSparkline.map((v, i) => `${(i / (epsSparkline.length - 1)) * 60},${20 - ((v - Math.min(...epsSparkline)) / (Math.max(...epsSparkline) - Math.min(...epsSparkline) || 1)) * 16 - 2}`).join(' ')} fill="none" stroke="#f2c35b" strokeWidth="1.5" /></svg></div>}
            </div>
            <div className={`${CARD} !p-4`}>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Revenue CAGR</div>
              <div className={`text-xl font-serif ${revCagr != null && revCagr >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>{revCagr != null ? fmt.pctSigned(revCagr) : '—'}</div>
              <div className="text-[10px] text-sand-500 dark:text-warm-400 mt-0.5">avg annual growth rate</div>
            </div>
            <div className={`${CARD} !p-4 relative overflow-hidden`}>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Consistency</div>
              {consistency ? (
                <>
                  <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{consistency.positive}/{consistency.total}</div>
                  <div className="text-[10px] text-sand-500 dark:text-warm-400 mt-0.5">quarters with growth</div>
                  <svg className="absolute right-2 bottom-2 opacity-40" width="24" height="24" viewBox="0 0 36 36">
                    <circle cx="18" cy="18" r="14" fill="none" stroke="currentColor" strokeWidth="4" className="text-sand-200 dark:text-warm-700" />
                    <circle cx="18" cy="18" r="14" fill="none" stroke="#a0d6ad" strokeWidth="4" strokeDasharray={`${(consistency.positive / consistency.total) * 88} 88`} strokeDashoffset="22" strokeLinecap="round" />
                  </svg>
                </>
              ) : (<div className="text-xl font-serif text-sand-900 dark:text-warm-50">—</div>)}
            </div>
          </div>
        </div>

        {/* Growth Quality Signal */}
        {growthQuality && ttm && (
          <div className={CARD}>
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-lg text-sand-500 dark:text-warm-300">compare_arrows</span>
              <h3 className="font-serif text-lg text-sand-800 dark:text-warm-50">Growth Quality</h3>
              <span className={`ml-auto text-[9px] font-bold uppercase tracking-wider px-2 py-1 rounded ${growthQuality.bg} ${growthQuality.color}`}>{growthQuality.label}</span>
            </div>
            <div className="grid grid-cols-2 gap-6 mb-4">
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-2">Revenue Growth (TTM)</div>
                <div className={`text-2xl font-serif font-bold ${ttm.revGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>{fmt.pctSigned(ttm.revGrowth)}</div>
                <div className="h-2 bg-sand-200 dark:bg-warm-800 rounded-full mt-2 overflow-hidden">
                  <div className={`h-full rounded-full ${ttm.revGrowth >= 0 ? 'bg-vi-sage' : 'bg-vi-rose'}`} style={{ width: `${Math.min(Math.abs(ttm.revGrowth) * 200, 100)}%` }} />
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-2">EPS Growth (TTM)</div>
                <div className={`text-2xl font-serif font-bold ${ttm.epsGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>{fmt.pctSigned(ttm.epsGrowth)}</div>
                <div className="h-2 bg-sand-200 dark:bg-warm-800 rounded-full mt-2 overflow-hidden">
                  <div className={`h-full rounded-full ${ttm.epsGrowth >= 0 ? 'bg-vi-sage' : 'bg-vi-rose'}`} style={{ width: `${Math.min(Math.abs(ttm.epsGrowth) * 200, 100)}%` }} />
                </div>
              </div>
            </div>
            <p className="text-[11px] text-sand-500 dark:text-warm-400 italic">{growthQuality.desc}</p>
          </div>
        )}

        {/* Quarterly Performance Table — simplified */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Quarterly Performance</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[600px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'Revenue', 'Rev YoY', 'Net Income', 'NI YoY', 'EPS'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 0 ? 'text-right' : ''}`}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className={`px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap border-l-2 ${row.revYoY == null ? 'border-sand-300 dark:border-warm-600' : row.revYoY >= 0 ? 'border-vi-sage' : 'border-vi-rose'}`}>{row.quarter}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">{fmt.billions(row.revenue)}<DeltaChip value={row.revDelta} /></td>
                    <td className={`px-4 py-4 text-right whitespace-nowrap ${yoyColor(row.revYoY)}`}>{row.revYoY != null ? fmt.pctSigned(row.revYoY) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.netIncome)}</td>
                    <td className={`px-4 py-4 text-right whitespace-nowrap ${yoyColor(row.niYoY)}`}>{row.niYoY != null ? fmt.pctSigned(row.niYoY) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">{fmt.eps(row.eps)}<DeltaChip value={row.epsDelta} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Right column: Insights */}
      <aside className="xl:col-span-4 space-y-6">
        {/* Oracle's Perspective — dynamic */}
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            {isAccelerating && latest?.revenue_profit.is_margin_expanding
              ? <>&ldquo;Revenue is accelerating and margins are expanding — the hallmark of a business hitting its stride. {latest?.ticker || 'AAPL'} is growing {fmt.pct(latestRevYoY)} while widening its moat. This is compound growth in action.&rdquo;</>
              : isAccelerating === false && latest?.revenue_profit.is_margin_expanding
                ? <>&ldquo;The top line is slowing but margins are still expanding — management is finding efficiency. {latest?.ticker || 'AAPL'} earns more per dollar even as revenue growth moderates to {fmt.pct(latestRevYoY)}.&rdquo;</>
                : isAccelerating === false && !latest?.revenue_profit.is_margin_expanding
                  ? <>&ldquo;Both growth and margins are under pressure. At {fmt.pct(latestRevYoY)} revenue growth with compressing margins, focus on whether this is cyclical or structural. The best businesses bounce back.&rdquo;</>
                  : <>&ldquo;Consistent earnings power is what matters. {latest?.ticker || 'AAPL'} shows {fmt.pct(latestRevYoY)} growth with net margin at {fmt.pct(latest?.revenue_profit.net_margin)} — steady compounding creates the most wealth over time.&rdquo;</>
            }
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700">
              <span className="material-symbols-outlined text-vi-gold text-lg">psychology</span>
            </div>
            <div>
              <div className="text-sm font-bold">Insight Engine</div>
              <div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div>
            </div>
          </div>
        </div>

        {/* Revenue CAGR Chart with acceleration badge */}
        <div className="grid grid-cols-2 gap-4">
          <div className={`col-span-2 ${CARD} !p-4`}>
            <div className="flex items-center gap-2 mb-1">
              {isAccelerating != null && (
                <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${isAccelerating ? 'bg-vi-sage/20 text-vi-sage' : 'bg-vi-rose/20 text-vi-rose'}`}>
                  <span className="material-symbols-outlined text-[11px] mr-0.5 align-middle">{isAccelerating ? 'trending_up' : 'trending_down'}</span>
                  {isAccelerating ? 'Accelerating' : 'Decelerating'}
                </span>
              )}
            </div>
            <CagrChart data={revenueSparkline} quarters={filtered} cagr={revCagr} label="Revenue Growth" color="#a0d6ad" formatFn={fmt.billions} />
          </div>
          <div className={`col-span-2 ${CARD} !p-4`}>
            <CagrChart data={epsSparkline} quarters={filtered} cagr={epsCagr} label="Earnings Per Share" color="#f2c35b" formatFn={fmt.eps} />
          </div>
        </div>

        {/* Margin Trend Card */}
        <div className={CARD}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-lg text-sand-500 dark:text-warm-300">expand</span>
            <h4 className="font-serif text-lg text-sand-800 dark:text-warm-50">Margin Trend</h4>
            {latest?.revenue_profit.is_margin_expanding != null && (
              <span className={`ml-auto text-[9px] font-bold uppercase tracking-wider px-2 py-1 rounded ${latest.revenue_profit.is_margin_expanding ? 'bg-vi-sage/20 text-vi-sage' : 'bg-vi-rose/20 text-vi-rose'}`}>
                {latest.revenue_profit.is_margin_expanding ? 'Expanding' : 'Compressing'}
              </span>
            )}
          </div>
          {[
            { label: 'Gross Margin', value: latest?.revenue_profit.gross_margin, change: latest?.revenue_profit.gross_margin_change_1yr },
            { label: 'Operating Margin', value: latest?.revenue_profit.operating_margin, change: latest?.revenue_profit.operating_margin_change_1yr },
            { label: 'Net Margin', value: latest?.revenue_profit.net_margin, change: latest?.revenue_profit.net_margin_change_1yr },
          ].map((m) => (
            <div key={m.label} className="flex items-center justify-between py-2.5 border-b border-sand-200/30 dark:border-warm-800/30 last:border-0">
              <span className="text-sm text-sand-600 dark:text-warm-200">{m.label}</span>
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold text-sand-800 dark:text-warm-50">{fmt.pct(m.value)}</span>
                {m.change != null && (
                  <span className={`inline-flex items-center text-[10px] font-bold ${m.change >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    <span className="material-symbols-outlined text-[12px]">{m.change >= 0 ? 'arrow_upward' : 'arrow_downward'}</span>
                    {fmt.pctPts(m.change)}
                  </span>
                )}
              </div>
            </div>
          ))}
          <div className="text-[10px] text-sand-400 dark:text-warm-500 mt-2">vs same quarter 1 year ago</div>
        </div>

        {/* Bento Tiles */}
        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="Net Margin" value={fmt.pct(latest?.revenue_profit.net_margin)} sparkline={netMarginSparkline} color="#6d28d9" />
          <BentoTile label="Rev QoQ" value={latest?.revenue_profit.revenue_growth_qoq != null ? fmt.pctSigned(latest.revenue_profit.revenue_growth_qoq) : '—'} icon="swap_vert" />
          <BentoTile label="Gross Profit" value={fmt.billions(latest?.revenue_profit.gross_profit)} sparkline={grossProfitSparkline} color="#a0d6ad" />
          <BentoTile label="CapEx Intensity" value={fmt.pct(latest?.cashflow.capex_intensity)} icon="precision_manufacturing" />
        </div>

        {/* Growth Rating */}
        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Growth Rating</div>
            <div className="text-xl font-serif text-vi-sage">
              {ratings?.growth?.rating || 'Moderate'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span>
            </div>
          </div>
          <span className="material-symbols-outlined text-3xl text-vi-sage/30">trending_up</span>
        </div>

        {/* Market Context */}
        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <span className="material-symbols-outlined text-[120px]">public</span>
          </div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            Revenue growth of {fmt.pct(latest?.revenue_profit.revenue_growth_yoy)} with net margin at {fmt.pct(latest?.revenue_profit.net_margin)} demonstrates pricing power. {latest?.cashflow.capex_intensity < 0.05 ? `CapEx intensity at just ${fmt.pct(latest?.cashflow.capex_intensity)} signals an asset-light model — a hallmark Buffett trait.` : `The business reinvests ${fmt.pct(latest?.cashflow.capex_intensity)} of revenue back into growth.`}
          </p>
        </div>
      </aside>
    </div>
  );
}

export function ProfitabilityPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];
  const chartQuarters = filtered;

  // Margin trend direction (expanding or compressing vs prior quarter)
  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      grossMargin: q.revenue_profit.gross_margin,
      opMargin: q.revenue_profit.operating_margin,
      netMargin: q.revenue_profit.net_margin,
      roe: q.valuation.roe,
      roic: q.valuation.roic,
      grossDelta: prev ? fmt.delta(q.revenue_profit.gross_margin, prev.revenue_profit.gross_margin) : null,
      opDelta: prev ? fmt.delta(q.revenue_profit.operating_margin, prev.revenue_profit.operating_margin) : null,
      netDelta: prev ? fmt.delta(q.revenue_profit.net_margin, prev.revenue_profit.net_margin) : null,
    };
  });

  // Operating Leverage — ratio of operating income growth to revenue growth (QoQ)
  const opLeverageData = useMemo(() => {
    return filtered.slice(1).map((q, i) => {
      const prev = filtered[i];
      const revGrowth = prev.revenue_profit.revenue > 0
        ? (q.revenue_profit.revenue - prev.revenue_profit.revenue) / prev.revenue_profit.revenue
        : null;
      const opIncGrowth = prev.revenue_profit.operating_income > 0
        ? (q.revenue_profit.operating_income - prev.revenue_profit.operating_income) / prev.revenue_profit.operating_income
        : null;
      const leverage = (revGrowth && revGrowth !== 0) ? opIncGrowth / revGrowth : null;
      return {
        label: `${q.fiscal_quarter} ${q.fiscal_year}`,
        revGrowth,
        opIncGrowth,
        leverage,
        fiscal_year: q.fiscal_year,
      };
    });
  }, [filtered]);

  // Yearly operating leverage (aggregate by fiscal year)
  const yearlyLeverage = useMemo(() => {
    const byYear = {};
    for (const d of opLeverageData) {
      if (!byYear[d.fiscal_year]) byYear[d.fiscal_year] = [];
      if (d.leverage != null && isFinite(d.leverage)) byYear[d.fiscal_year].push(d.leverage);
    }
    return Object.entries(byYear)
      .map(([year, vals]) => ({ year: Number(year), avg: vals.reduce((a, b) => a + b, 0) / vals.length }))
      .sort((a, b) => a.year - b.year);
  }, [opLeverageData]);

  // Sparkline data
  const grossMarginSparkline = filtered.map(q => q.revenue_profit.gross_margin);
  const roicSparkline = filtered.map(q => q.valuation.roic);
  const assetTurnoverSparkline = filtered.map(q => q.valuation.asset_turnover);

  // DuPont components for latest
  const dupont = latest ? {
    netMargin: latest.revenue_profit.net_margin,
    assetTurnover: latest.valuation.asset_turnover,
    equityMultiplier: latest.valuation.equity_multiplier,
    roe: latest.valuation.roe,
  } : null;

  // Margin expansion check (first vs last of filtered range)
  const marginExpanding = earliest && latest
    ? latest.revenue_profit.gross_margin > earliest.revenue_profit.gross_margin
    : null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column: Charts + Table */}
      <section className="xl:col-span-8 space-y-6">
        {/* Margin Waterfall Chart */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Margin Waterfall</h3>
            <RatingBadge rating={ratings?.profitability?.rating} />
          </div>

          {/* Stacked waterfall bars */}
          <div className="relative h-[300px] w-full flex items-end justify-between gap-2 md:gap-3 px-1">
            {chartQuarters.map((q) => {
              const rev = q.revenue_profit.revenue;
              const gp = q.revenue_profit.gross_profit || rev * q.revenue_profit.gross_margin;
              const oi = q.revenue_profit.operating_income || rev * q.revenue_profit.operating_margin;
              const ni = q.revenue_profit.net_income;
              const maxRev = Math.max(...chartQuarters.map(d => d.revenue_profit.revenue));
              const scale = (v) => (v / maxRev) * 100;

              // Margin expanding or compressing vs previous quarter
              const idx = chartQuarters.indexOf(q);
              const prev = idx > 0 ? chartQuarters[idx - 1] : null;
              const expanding = prev ? q.revenue_profit.gross_margin >= prev.revenue_profit.gross_margin : true;

              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${scale(rev)}%` }}>
                  {/* Revenue (full bar, lightest) */}
                  <div className={`absolute inset-0 rounded-t-lg transition-all ${expanding ? 'bg-vi-sage/15' : 'bg-vi-rose/15'} group-hover:${expanding ? 'bg-vi-sage/25' : 'bg-vi-rose/25'}`} />
                  {/* Gross Profit */}
                  <div className="absolute inset-x-0 bottom-0 bg-vi-sage/30 rounded-t-lg transition-all" style={{ height: `${(gp / rev) * 100}%` }} />
                  {/* Operating Income */}
                  <div className="absolute inset-x-0 bottom-0 bg-vi-sage/50 rounded-t-lg transition-all" style={{ height: `${(oi / rev) * 100}%` }} />
                  {/* Net Income */}
                  <div className="absolute inset-x-0 bottom-0 bg-vi-gold/60 rounded-t-lg transition-all group-hover:bg-vi-gold/80" style={{ height: `${(ni / rev) * 100}%` }} />

                  {/* Quarter label */}
                  <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-400 dark:text-warm-400 whitespace-nowrap">
                    {q.fiscal_quarter}
                  </div>

                  {/* Hover tooltip */}
                  <div className="absolute -top-[90px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div>Gross: {fmt.pct(q.revenue_profit.gross_margin)}</div>
                    <div>Operating: {fmt.pct(q.revenue_profit.operating_margin)}</div>
                    <div>Net: {fmt.pct(q.revenue_profit.net_margin)}</div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Legend */}
          <div className="mt-10 flex flex-wrap items-center gap-5 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/15 rounded-sm border border-vi-sage/30" /> Revenue</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/30 rounded-sm" /> Gross Profit</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/50 rounded-sm" /> Operating Income</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-gold/60 rounded-sm" /> Net Income</div>
          </div>
        </div>

        {/* DuPont Decomposition */}
        {dupont && (
          <div className={CARD}>
            <h3 className="text-lg font-serif text-sand-800 dark:text-warm-50 mb-6">DuPont ROE Decomposition</h3>
            <div className="flex flex-wrap items-center justify-center gap-3 md:gap-4 text-center">
              <DuPontBlock label="Net Margin" value={fmt.pct(dupont.netMargin)} color="text-vi-sage" />
              <span className="text-xl text-sand-400 dark:text-warm-400 font-light">&times;</span>
              <DuPontBlock label="Asset Turnover" value={`${dupont.assetTurnover.toFixed(2)}x`} color="text-vi-gold" />
              <span className="text-xl text-sand-400 dark:text-warm-400 font-light">&times;</span>
              <DuPontBlock label="Equity Multiplier" value={`${dupont.equityMultiplier.toFixed(2)}x`} color="text-vi-accent" />
              <span className="text-xl text-sand-400 dark:text-warm-400 font-light">=</span>
              <DuPontBlock label="ROE" value={fmt.pct(dupont.roe)} color="text-vi-gold" highlight />
            </div>
            <p className="mt-5 text-xs text-sand-500 dark:text-warm-300 text-center italic">
              {dupont.equityMultiplier > 3
                ? 'High equity multiplier — leverage is amplifying returns. Watch for sustainability.'
                : dupont.netMargin > 0.2
                  ? 'Margin-driven ROE — the healthiest form of return. Classic Buffett territory.'
                  : 'Balanced ROE drivers — no single component dominates.'}
            </p>
          </div>
        )}

        {/* Data Table with sticky headers + QoQ deltas */}
        <div className="bg-sand-100 dark:bg-warm-900 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-sand-200/50 dark:border-warm-800/50">
            <h3 className="font-serif text-lg text-sand-800 dark:text-warm-50">Quarterly Margin Detail</h3>
          </div>
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-left border-collapse">
              <thead className="text-[11px] uppercase tracking-wider text-sand-500 dark:text-warm-300 sticky top-0 z-10">
                <tr>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Quarter</th>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Gross</th>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Operating</th>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Net</th>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">ROE</th>
                  <th className="px-6 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">ROIC</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-sand-200/30 dark:divide-warm-800/30">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/40 dark:hover:bg-warm-800/40 transition-colors ${i % 2 === 1 ? 'bg-sand-50/50 dark:bg-warm-950/30' : ''}`}>
                    <td className="px-6 py-4 font-medium text-sand-800 dark:text-warm-50">{row.quarter}</td>
                    <td className="px-6 py-4 text-sand-600 dark:text-warm-200">
                      {fmt.pct(row.grossMargin)}<DeltaChip value={row.grossDelta} />
                    </td>
                    <td className="px-6 py-4 text-sand-600 dark:text-warm-200">
                      {fmt.pct(row.opMargin)}<DeltaChip value={row.opDelta} />
                    </td>
                    <td className="px-6 py-4 text-sand-600 dark:text-warm-200">
                      {fmt.pct(row.netMargin)}<DeltaChip value={row.netDelta} />
                    </td>
                    <td className="px-6 py-4 text-sand-600 dark:text-warm-200 font-bold">{fmt.pct(row.roe)}</td>
                    <td className="px-6 py-4 text-sand-600 dark:text-warm-200">{fmt.pct(row.roic)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Right column: Insights */}
      <aside className="xl:col-span-4 space-y-6">
        {/* Oracle's Perspective */}
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            &ldquo;Margins tell you who has pricing power. {latest?.ticker || 'AAPL'}&apos;s gross margin at {fmt.pct(latest?.revenue_profit.gross_margin)} with {fmt.pct(latest?.revenue_profit.net_margin)} falling to the bottom line — that&apos;s a {marginExpanding ? 'widening' : 'narrowing'} moat.&rdquo;
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700">
              <span className="material-symbols-outlined text-vi-gold text-lg">psychology</span>
            </div>
            <div>
              <div className="text-sm font-bold">Insight Engine</div>
              <div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div>
            </div>
          </div>
        </div>

        {/* Bento tiles with sparklines */}
        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="Gross Margin" value={fmt.pct(latest?.revenue_profit.gross_margin)} sparkline={grossMarginSparkline} color="#a0d6ad" />
          <BentoTile label="ROIC" value={fmt.pct(latest?.valuation.roic)} sparkline={roicSparkline} color="#6d28d9" />
          <BentoTile label="Asset Turnover" value={`${latest?.valuation.asset_turnover?.toFixed(2) || '—'}x`} sparkline={assetTurnoverSparkline} color="#f2c35b" />
          <BentoTile label="FCF / Net Income" value={`${latest?.cashflow.fcf_to_net_income?.toFixed(2) || '—'}x`} icon="account_balance_wallet" />
          <div className={`col-span-2 ${CARD} !p-4 flex items-center justify-between`}>
            <div>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Profitability Rating</div>
              <div className="text-xl font-serif text-vi-sage">
                {ratings?.profitability?.rating || 'Strong'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span>
              </div>
            </div>
            <span className="material-symbols-outlined text-3xl text-vi-sage/30">workspace_premium</span>
          </div>
        </div>

        {/* Operating Leverage Widget */}
        <div className={`${CARD} relative overflow-hidden`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-accent text-lg">speed</span>
            <h4 className="font-serif text-lg">Operating Leverage</h4>
          </div>

          {/* Quarterly trend bars */}
          <div className="mb-4">
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-2">Quarterly Trend</div>
            <div className="flex items-end gap-1 h-16">
              {opLeverageData.slice(-12).map((d, i) => {
                if (d.leverage == null || !isFinite(d.leverage)) {
                  return <div key={i} className="flex-1 bg-sand-200 dark:bg-warm-800 rounded-t h-1" />;
                }
                const clamped = Math.max(-3, Math.min(3, d.leverage));
                const isPositive = clamped > 1;
                const barH = Math.abs(clamped) / 3 * 100;
                return (
                  <div key={i} className="flex-1 flex flex-col justify-end h-full group relative">
                    <div
                      className={`rounded-t transition-all ${isPositive ? 'bg-vi-sage/60 group-hover:bg-vi-sage' : 'bg-vi-rose/40 group-hover:bg-vi-rose/70'}`}
                      style={{ height: `${Math.max(barH, 8)}%` }}
                    />
                    <div className="absolute -top-8 left-1/2 -translate-x-1/2 text-[9px] font-mono opacity-0 group-hover:opacity-100 bg-sand-100 dark:bg-warm-900 px-1 rounded whitespace-nowrap z-10">
                      {d.leverage.toFixed(1)}x
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex justify-between text-[9px] text-sand-400 dark:text-warm-400 mt-1">
              <span>{opLeverageData.slice(-12)[0]?.label || ''}</span>
              <span>{opLeverageData[opLeverageData.length - 1]?.label || ''}</span>
            </div>
          </div>

          {/* Yearly summary */}
          <div className="border-t border-sand-200 dark:border-warm-800 pt-3">
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-2">Yearly Average</div>
            <div className="space-y-2">
              {yearlyLeverage.slice(-4).map(({ year, avg }) => (
                <div key={year} className="flex items-center justify-between">
                  <span className="text-xs font-medium text-sand-600 dark:text-warm-200">FY {year}</span>
                  <div className="flex items-center gap-2">
                    <div className="w-20 h-2 bg-sand-200 dark:bg-warm-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${avg > 1 ? 'bg-vi-sage' : 'bg-vi-rose/60'}`}
                        style={{ width: `${Math.min(Math.abs(avg) / 3 * 100, 100)}%` }}
                      />
                    </div>
                    <span className={`text-xs font-bold w-10 text-right ${avg > 1 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {avg.toFixed(1)}x
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <p className="mt-3 text-[10px] text-sand-400 dark:text-warm-400 italic">
            &gt;1x = operating income grows faster than revenue (positive leverage)
          </p>
        </div>
      </aside>
    </div>
  );
}

export function ValuationPanel({ data, ratings, latestPrice, timeRange, sectorAggregate, sector }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  // Live P/E from latest market close + most recent TTM earnings
  const livePE = useMemo(() => {
    if (!latestPrice?.price || !latest?.valuation.earnings_yield) return null;
    // earnings_yield is already decimal (e.g., 0.035 = 3.5%)
    const ey = latest.valuation.earnings_yield;
    if (!ey || ey <= 0) return null;
    const ttmEPS = ey * (latest.valuation.stock_price || 0);
    if (!ttmEPS || ttmEPS <= 0) return null;
    return latestPrice.price / ttmEPS;
  }, [latestPrice, latest]);

  // Quarters with valid valuation multiples (non-null P/E)
  const withMultiples = useMemo(() => filtered.filter(q => q.valuation.pe_ratio != null), [filtered]);

  // Historical averages for assessment
  const histAvg = useMemo(() => {
    if (withMultiples.length === 0) return {};
    const avg = (arr, fn) => arr.length === 0 ? null : arr.reduce((s, q) => s + fn(q), 0) / arr.length;
    return {
      pe: avg(withMultiples, q => q.valuation.pe_ratio),
      pb: avg(withMultiples.filter(q => q.valuation.pb_ratio != null), q => q.valuation.pb_ratio),
      evEbitda: avg(withMultiples.filter(q => q.valuation.ev_ebitda != null), q => q.valuation.ev_ebitda),
      pFcf: avg(withMultiples.filter(q => q.valuation.price_to_fcf != null), q => q.valuation.price_to_fcf),
    };
  }, [withMultiples]);

  // Min/max P/E for margin of safety gauge
  const peRange = useMemo(() => {
    if (withMultiples.length === 0) return { min: 0, max: 1 };
    const values = withMultiples.map(q => q.valuation.pe_ratio);
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [withMultiples]);

  // CAGR for ROIC trend
  const years = useMemo(() => {
    if (!earliest || !latest) return 0;
    return (new Date(latest.fiscal_date) - new Date(earliest.fiscal_date)) / (365.25 * 24 * 3600 * 1000);
  }, [earliest, latest]);

  const calcCagr = useCallback((latestVal, earliestVal) => {
    if (!latestVal || !earliestVal || earliestVal <= 0 || years <= 0) return null;
    return Math.pow(latestVal / earliestVal, 1 / years) - 1;
  }, [years]);

  const roicCagr = useMemo(() => calcCagr(latest?.valuation.roic, earliest?.valuation.roic), [latest, earliest, calcCagr]);
  const roeCagr = useMemo(() => calcCagr(latest?.valuation.roe, earliest?.valuation.roe), [latest, earliest, calcCagr]);
  const roaCagr = useMemo(() => calcCagr(latest?.valuation.roa, earliest?.valuation.roa), [latest, earliest, calcCagr]);

  // Sparkline data
  const peSparkline = withMultiples.map(q => q.valuation.pe_ratio);
  const evEbitdaSparkline = withMultiples.map(q => q.valuation.ev_ebitda).filter(v => v != null);
  const earningsYieldSparkline = withMultiples.map(q => q.valuation.earnings_yield).filter(v => v != null);
  const pFcfSparkline = withMultiples.map(q => q.valuation.price_to_fcf).filter(v => v != null);
  const roicSparkline = filtered.map(q => q.valuation.roic);
  const roeSparkline = filtered.map(q => q.valuation.roe);
  const roaSparkline = filtered.map(q => q.valuation.roa);

  // Percentile helper: where does `value` sit within sorted `arr`? Returns 0–100.
  const percentile = (value, arr) => {
    if (value == null || arr.length === 0) return null;
    const sorted = arr.filter(v => v != null).sort((a, b) => a - b);
    if (sorted.length === 0) return null;
    const below = sorted.filter(v => v < value).length;
    return Math.round((below / sorted.length) * 100);
  };

  // Historical min/max for each multiple (for range bar display)
  const histRange = useMemo(() => {
    const range = (arr) => {
      const valid = arr.filter(v => v != null);
      if (valid.length === 0) return { min: null, max: null };
      return { min: Math.min(...valid), max: Math.max(...valid) };
    };
    return {
      pe: range(withMultiples.map(q => q.valuation.pe_ratio)),
      pb: range(withMultiples.map(q => q.valuation.pb_ratio).filter(v => v != null)),
      evEbitda: range(withMultiples.map(q => q.valuation.ev_ebitda).filter(v => v != null)),
      pFcf: range(withMultiples.map(q => q.valuation.price_to_fcf).filter(v => v != null)),
    };
  }, [withMultiples]);

  // Assessment helper: compare current to historical average + percentile
  const timeLabel = timeRange === '1Y' ? '1-year' : timeRange === '3Y' ? '3-year' : '5-year';
  const assess = (current, avg, allValues) => {
    if (current == null || avg == null || avg === 0) return { label: '—', color: 'text-sand-400' };
    const pct = allValues ? percentile(current, allValues) : null;
    const ratio = current / avg;
    const discount = Math.abs((1 - ratio) * 100).toFixed(0);
    if (ratio < 0.8) return {
      label: 'Below Average',
      color: 'text-vi-sage', bg: 'bg-vi-sage/10', percentile: pct,
      hint: `${discount}% below its ${timeLabel} average — you're paying less than usual for this stock relative to its own history.`,
    };
    if (ratio > 1.2) return {
      label: 'Above Average',
      color: 'text-vi-rose', bg: 'bg-vi-rose/10', percentile: pct,
      hint: `${discount}% above its ${timeLabel} average — the market is pricing in higher growth expectations than usual.`,
    };
    return {
      label: 'Fair Range',
      color: 'text-vi-gold', bg: 'bg-vi-gold/10', percentile: pct,
      hint: `Within normal range of its ${timeLabel} average — priced roughly in line with what investors have typically paid.`,
    };
  };

  // Price multiple cards config — includes historical values for percentile computation
  const multipleCards = [
    {
      label: 'Price-to-Earnings',
      abbr: 'P/E',
      value: latest?.valuation.pe_ratio,
      avg: histAvg.pe,
      range: histRange.pe,
      allValues: withMultiples.map(q => q.valuation.pe_ratio),
      explain: 'How many years of profits you\'re paying for',
      format: fmt.x,
      tip: 'The P/E ratio divides the stock price by the company\'s earnings per share over the last 12 months. A P/E of 30x means you\'re paying $30 for every $1 the company earns. Lower P/E can mean a cheaper stock, but very low P/E might signal problems. Compare it to the company\'s own history, not just other companies.',
    },
    {
      label: 'Price-to-Book',
      abbr: 'P/B',
      value: latest?.valuation.pb_ratio,
      avg: histAvg.pb,
      range: histRange.pb,
      allValues: withMultiples.map(q => q.valuation.pb_ratio).filter(v => v != null),
      explain: 'What premium you\'re paying over the company\'s net assets',
      format: fmt.x,
      tip: 'Price-to-Book compares what the stock market values the company at vs. what the company actually owns minus what it owes (its "book value"). A P/B of 40x means investors pay $40 for every $1 of net assets — common for tech companies with valuable brands and IP that don\'t show up on the balance sheet.',
    },
    {
      label: 'Enterprise Value Multiple',
      abbr: 'EV/EBITDA',
      value: latest?.valuation.ev_ebitda,
      avg: histAvg.evEbitda,
      range: histRange.evEbitda,
      allValues: withMultiples.map(q => q.valuation.ev_ebitda).filter(v => v != null),
      explain: 'What the entire business costs relative to its cash earnings',
      format: fmt.x,
      tip: 'EV/EBITDA looks at the total cost to buy the entire business (including its debt, minus its cash) relative to its operating earnings before interest, taxes, and accounting adjustments. It\'s often considered more accurate than P/E because it accounts for debt and isn\'t distorted by tax strategies.',
    },
    {
      label: 'Price-to-Free Cash',
      abbr: 'P/FCF',
      value: latest?.valuation.price_to_fcf,
      avg: histAvg.pFcf,
      range: histRange.pFcf,
      allValues: withMultiples.map(q => q.valuation.price_to_fcf).filter(v => v != null),
      explain: 'What you pay per dollar the business actually generates',
      format: fmt.x,
      tip: 'Free cash flow is the actual cash left over after the company pays all its bills and invests in its business. P/FCF tells you how much you\'re paying for each dollar of real cash the company generates. Many investors consider this the most honest valuation metric because cash is harder to manipulate than earnings.',
    },
  ];

  // Table data — most recent first with QoQ deltas
  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      price: q.valuation.stock_price,
      pe: q.valuation.pe_ratio,
      pb: q.valuation.pb_ratio,
      evEbitda: q.valuation.ev_ebitda,
      pFcf: q.valuation.price_to_fcf,
      earningsYield: q.valuation.earnings_yield,
      roe: q.valuation.roe,
      roic: q.valuation.roic,
      peDelta: prev && q.valuation.pe_ratio != null && prev.valuation.pe_ratio != null
        ? fmt.delta(q.valuation.pe_ratio, prev.valuation.pe_ratio)
        : null,
    };
  });

  // Margin of safety (P/E vs historical average)
  const currentPE = latest?.valuation.pe_ratio;
  const avgPE = histAvg.pe;
  const marginOfSafety = (currentPE != null && avgPE != null && avgPE > 0)
    ? ((avgPE - currentPE) / avgPE)
    : null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column: Charts + Data */}
      <section className="xl:col-span-8 space-y-6">
        {/* Current Market Price Banner */}
        {latestPrice && (
          <div className={`${CARD} !py-4 border-l-4 border-vi-gold`}>
            <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mr-2">Last Close</span>
                <span className="text-2xl font-serif font-bold text-sand-900 dark:text-warm-50">${latestPrice.price.toFixed(2)}</span>
              </div>
              {livePE != null && (
                <div>
                  <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mr-2">Live P/E</span>
                  <span className="text-2xl font-serif font-bold text-sand-900 dark:text-warm-50">{fmt.x(livePE)}</span>
                  {latest?.valuation.pe_ratio != null && (
                    <span className={`ml-2 text-xs font-bold ${livePE > latest.valuation.pe_ratio ? 'text-vi-rose' : 'text-vi-sage'}`}>
                      {livePE > latest.valuation.pe_ratio ? '+' : ''}{fmt.x(livePE - latest.valuation.pe_ratio)} vs last quarter
                    </span>
                  )}
                </div>
              )}
              <span className="text-[10px] text-sand-400 dark:text-warm-500 ml-auto">
                as of {latestPrice.date}
              </span>
            </div>
          </div>
        )}

        {/* Price Multiples Overview */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">What Are You Paying?</h3>
            <RatingBadge rating={ratings?.valuation?.rating} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-4">
            {multipleCards.map((m) => {
              const assessment = assess(m.value, m.avg, m.allValues);
              const rangeMin = m.range?.min;
              const rangeMax = m.range?.max;
              const rangeSpan = (rangeMin != null && rangeMax != null && rangeMax > rangeMin) ? rangeMax - rangeMin : null;
              const rangePosition = (rangeSpan && m.value != null) ? Math.max(0, Math.min(1, (m.value - rangeMin) / rangeSpan)) : null;
              return (
                <div key={m.abbr} className={`${CARD} !p-6 relative flex flex-col`}>
                  <div className="flex items-center justify-between mb-2">
                    <MetricTooltip tip={m.tip}>
                      <span className="text-xs uppercase font-bold text-sand-500 dark:text-warm-400 tracking-wide">{m.label}</span>
                    </MetricTooltip>
                    {assessment.bg && (
                      <span className={`text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${assessment.bg} ${assessment.color}`}>
                        {assessment.label}
                      </span>
                    )}
                  </div>
                  <div className="text-4xl font-serif font-bold text-sand-900 dark:text-warm-50 mb-2">
                    {m.value != null ? m.format(m.value) : '—'}
                  </div>
                  <p className="text-sm text-sand-500 dark:text-warm-400 leading-snug italic mb-1">{m.explain}</p>
                  {/* Historical range bar */}
                  <div className="mt-auto pt-3">
                    {rangePosition != null && (
                      <>
                        <div className="flex items-center justify-between text-[11px] text-sand-400 dark:text-warm-500 mb-1.5">
                          <span>{timeLabel} low: {m.format(rangeMin)}</span>
                          {m.avg != null && <span className="text-vi-gold font-bold">avg: {m.format(m.avg)}</span>}
                          <span>high: {m.format(rangeMax)}</span>
                        </div>
                        <div className="relative h-2 bg-sand-200/60 dark:bg-warm-800/60 rounded-full overflow-hidden">
                          <div
                            className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
                            style={{
                              width: `${rangePosition * 100}%`,
                              background: rangePosition < 0.33 ? '#6d9e78' : rangePosition > 0.66 ? '#c47a7a' : '#d4a843',
                            }}
                          />
                        </div>
                        {assessment.hint && (
                          <p className={`text-xs leading-relaxed mt-2.5 ${assessment.color}`}>
                            {assessment.hint}
                          </p>
                        )}
                      </>
                    )}
                    {/* Fallback: show average without range bar */}
                    {rangePosition == null && m.avg != null && (
                      <div className="text-xs text-sand-400 dark:text-warm-500">
                        {timeLabel} avg: {m.format(m.avg)}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Capital Efficiency — with sector comparison */}
        {(() => {
          const sectorMetrics = sectorAggregate?.metrics || {};
          const sMedianROE = sectorMetrics.roe?.median != null ? sectorMetrics.roe.median / 100 : null;
          const sMedianROIC = sectorMetrics.roic?.median != null ? sectorMetrics.roic.median / 100 : null;
          const sMedianROA = sectorMetrics.roa?.median != null ? sectorMetrics.roa.median / 100 : null;

          // Grade helper: compare company value to sector median
          const grade = (val, median) => {
            if (val == null || median == null || median === 0) return { letter: '—', color: 'text-sand-400', bg: 'bg-sand-200 dark:bg-warm-700' };
            const ratio = val / median;
            if (ratio >= 2.0) return { letter: 'A+', color: 'text-vi-sage', bg: 'bg-vi-sage/20' };
            if (ratio >= 1.5) return { letter: 'A', color: 'text-vi-sage', bg: 'bg-vi-sage/15' };
            if (ratio >= 1.0) return { letter: 'B', color: 'text-vi-gold', bg: 'bg-vi-gold/15' };
            if (ratio >= 0.7) return { letter: 'C', color: 'text-vi-gold', bg: 'bg-vi-gold/10' };
            return { letter: 'D', color: 'text-vi-rose', bg: 'bg-vi-rose/15' };
          };

          const metrics = [
            {
              label: 'Return on Invested Capital',
              abbr: 'ROIC',
              value: latest?.valuation.roic,
              sectorMedian: sMedianROIC,
              sparkline: roicSparkline,
              cagr: roicCagr,
              color: '#6d28d9',
              tip: 'ROIC measures how efficiently a company uses ALL the capital invested in it to generate profits. It\'s considered the single best measure of business quality. An ROIC above 15% suggests a durable competitive moat.',
              primary: true,
            },
            {
              label: 'Return on Equity',
              abbr: 'ROE',
              value: latest?.valuation.roe,
              sectorMedian: sMedianROE,
              sparkline: roeSparkline,
              cagr: roeCagr,
              color: '#f59e0b',
              tip: 'ROE measures profit generated per dollar of shareholder equity. Very high ROE (like Apple\'s) can be inflated by share buybacks reducing equity — compare with ROIC for a clearer picture.',
            },
            {
              label: 'Return on Assets',
              abbr: 'ROA',
              value: latest?.valuation.roa,
              sectorMedian: sMedianROA,
              sparkline: roaSparkline,
              cagr: roaCagr,
              color: '#a0d6ad',
              tip: 'ROA shows how efficiently a company uses everything it owns to generate profits. Higher ROA means the company does more with less — it doesn\'t need expensive assets to make money.',
            },
          ];

          // Build rich dynamic narrative from actual data
          const roicGrade = grade(latest?.valuation.roic, sMedianROIC);
          const tk = latest?.ticker || 'This company';
          const roicPct = latest?.valuation.roic != null ? (latest.valuation.roic * 100).toFixed(1) : null;
          const roePct = latest?.valuation.roe != null ? (latest.valuation.roe * 100).toFixed(1) : null;
          const sMedianROICPct = sMedianROIC != null ? (sMedianROIC * 100).toFixed(1) : null;
          const roicMultiple = (latest?.valuation.roic && sMedianROIC) ? (latest.valuation.roic / sMedianROIC).toFixed(1) : null;

          // ROE vs ROIC divergence check (buyback signal)
          const roeRoicDivergence = (latest?.valuation.roe && latest?.valuation.roic)
            ? latest.valuation.roe / latest.valuation.roic
            : null;

          // All-metrics grade check
          const allGrades = [grade(latest?.valuation.roic, sMedianROIC), grade(latest?.valuation.roe, sMedianROE), grade(latest?.valuation.roa, sMedianROA)];
          const allStrong = allGrades.every(g => g.letter === 'A+' || g.letter === 'A');

          let summaryLines = [];
          if (roicPct != null && sMedianROICPct != null) {
            // Primary ROIC narrative
            if (parseFloat(roicMultiple) >= 2.0) {
              summaryLines.push(`${tk} earns ${roicPct} cents of profit on every dollar of capital — ${roicMultiple}x the ${sector} sector median of ${sMedianROICPct}%. This exceptional capital efficiency, sustained over multiple years, is the clearest signal of a durable competitive moat.`);
            } else if (parseFloat(roicMultiple) >= 1.2) {
              summaryLines.push(`${tk} earns ${roicPct}% return on invested capital, above the ${sector} median of ${sMedianROICPct}%. Solid efficiency that suggests competitive advantages are working in the company's favor.`);
            } else if (parseFloat(roicMultiple) >= 1.0) {
              summaryLines.push(`${tk} earns ${roicPct}% on invested capital, roughly in line with the ${sector} median of ${sMedianROICPct}%. Adequate but not exceptional — the business competes but doesn't dominate.`);
            } else if (latest.valuation.roic >= 0.10) {
              summaryLines.push(`${tk} earns ${roicPct}% on invested capital — below the ${sector} sector median of ${sMedianROICPct}%. Still above the cost of capital, but there's room for improvement.`);
            } else {
              summaryLines.push(`${tk} earns ${roicPct}% on invested capital — half the ${sector} sector median of ${sMedianROICPct}%. When ROIC falls below the cost of capital (~10%), the business may be destroying value rather than creating it.`);
            }

            // ROE vs ROIC divergence narrative
            if (roeRoicDivergence != null && roeRoicDivergence > 2.0 && roePct) {
              summaryLines.push(`ROE of ${roePct}% looks extraordinary, but ROIC of ${roicPct}% tells the real story. The gap means share buybacks have shrunk equity, inflating ROE. Focus on ROIC — it's the truer measure.`);
            }

            // All-strong narrative
            if (allStrong) {
              summaryLines.push('A+ across the board: ROIC, ROE, and ROA all exceed their sector medians by wide margins. This is rare and suggests pricing power, operational efficiency, and low capital needs working together.');
            }
          }

          return (
            <div className={CARD}>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Capital Efficiency</h3>
                {sector && <span className="text-xs font-bold text-sand-400 dark:text-warm-500 uppercase tracking-wider">vs {sector} Sector</span>}
              </div>

              {/* Rich dynamic summary */}
              {summaryLines.length > 0 && (
                <div className="space-y-2 mb-6">
                  {summaryLines.map((line, i) => (
                    <p key={i} className={`text-sm leading-relaxed ${i === 0 ? roicGrade.color : 'text-sand-500 dark:text-warm-400 italic'}`}>{line}</p>
                  ))}
                </div>
              )}

              {/* Metric cards — compact 3-column grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {metrics.map((m) => {
                  const g = grade(m.value, m.sectorMedian);
                  const companyPct = m.value != null ? (m.value * 100).toFixed(1) : null;
                  const sectorPct = m.sectorMedian != null ? (m.sectorMedian * 100).toFixed(1) : null;

                  return (
                    <div key={m.abbr} className={`${CARD} !p-4 ${m.primary ? 'border-t-2 border-vi-accent' : ''}`}>
                      <div className="flex items-center justify-between mb-1">
                        <MetricTooltip tip={m.tip}>
                          <span className="text-xs font-bold text-sand-700 dark:text-warm-100">{m.abbr}</span>
                        </MetricTooltip>
                        <span className={`text-sm font-serif font-bold w-8 h-8 rounded-lg flex items-center justify-center ${g.bg} ${g.color}`}>
                          {g.letter}
                        </span>
                      </div>

                      <div className="mb-1">
                        <span className="text-2xl font-serif font-bold text-sand-900 dark:text-warm-50">{companyPct != null ? `${companyPct}%` : '—'}</span>
                      </div>
                      {sectorPct != null && (
                        <div className="text-[11px] text-sand-400 dark:text-warm-500 mb-2">
                          vs <span className="font-bold text-vi-accent">{sectorPct}%</span> median
                        </div>
                      )}

                      {/* Compact trend chart with sector median reference line */}
                      <CagrChart
                        data={m.sparkline}
                        quarters={filtered}
                        cagr={m.cagr}
                        label={`${m.abbr} Trend`}
                        color={m.color}
                        formatFn={fmt.pct}
                        refLine={m.sectorMedian != null ? { value: m.sectorMedian, label: `${sector} median`, color: '#6d28d9' } : undefined}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        {/* Quarterly Valuation Detail Table */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Quarterly Valuation Detail</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[800px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'Price', 'P/E', 'P/B', 'EV/EBITDA', 'P/FCF', 'Earn. Yield', 'ROE', 'ROIC'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 0 ? 'text-right' : ''}`}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className="px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap">{row.quarter}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{row.price != null ? `$${row.price.toFixed(2)}` : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">
                      {row.pe != null ? fmt.x(row.pe) : '—'}
                      <DeltaChip value={row.peDelta} />
                    </td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{row.pb != null ? fmt.x(row.pb) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{row.evEbitda != null ? fmt.x(row.evEbitda) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{row.pFcf != null ? fmt.x(row.pFcf) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{row.earningsYield != null ? fmt.pct(row.earningsYield) : '—'}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.pct(row.roe)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.pct(row.roic)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Right column: Insights */}
      <aside className="xl:col-span-4 space-y-6">
        {/* Oracle's Perspective */}
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            {currentPE != null && avgPE != null ? (
              currentPE < avgPE
                ? <>&ldquo;At {fmt.x(currentPE)} earnings, {latest?.ticker || 'AAPL'} trades below its historical average of {fmt.x(avgPE)}. Price is reasonable for a business generating {fmt.pct(latest?.valuation.roic)} return on every dollar of capital.&rdquo;</>
                : <>&ldquo;At {fmt.x(currentPE)} earnings, the market expects continued growth. With ROIC at {fmt.pct(latest?.valuation.roic)}, every dollar of capital generates strong returns — understanding whether the premium is justified requires examining the growth trajectory.&rdquo;</>
            ) : (
              <>&ldquo;Focus on what you get for what you pay. Return on capital of {fmt.pct(latest?.valuation.roic)} means this business turns every dollar into meaningful profit — that&apos;s the foundation of intrinsic value.&rdquo;</>
            )}
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700">
              <span className="material-symbols-outlined text-vi-gold text-lg">psychology</span>
            </div>
            <div>
              <div className="text-sm font-bold">Insight Engine</div>
              <div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div>
            </div>
          </div>
        </div>

        {/* Valuation Over Time — moved from left column */}
        <div className="grid grid-cols-2 gap-4">
          <div className={`col-span-2 ${CARD} !p-4`}>
            <CagrChart
              data={peSparkline}
              quarters={withMultiples}
              cagr={histAvg.pe || 0}
              label="P/E Ratio"
              color="#6d28d9"
              formatFn={fmt.x}
              summaryLabel={histAvg.pe != null ? `Avg ${fmt.x(histAvg.pe)}` : ''}
            />
          </div>
          <div className={`col-span-2 ${CARD} !p-4`}>
            <CagrChart
              data={evEbitdaSparkline}
              quarters={withMultiples}
              cagr={histAvg.evEbitda || 0}
              label="EV / EBITDA"
              color="#f59e0b"
              formatFn={fmt.x}
              summaryLabel={histAvg.evEbitda != null ? `Avg ${fmt.x(histAvg.evEbitda)}` : ''}
            />
          </div>
        </div>

        {/* Bento Tiles */}
        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="P/E Ratio" value={latest?.valuation.pe_ratio != null ? fmt.x(latest.valuation.pe_ratio) : '—'} sparkline={peSparkline} color="#6d28d9" tip="Price divided by trailing 12-month earnings per share. Shows how the market values each dollar of profit." />
          <BentoTile label="Earnings Yield" value={latest?.valuation.earnings_yield != null ? fmt.pct(latest.valuation.earnings_yield) : '—'} sparkline={earningsYieldSparkline} color="#a0d6ad" tip="The inverse of P/E — shows the percentage return the stock 'earns' for you. Compare this to bond yields or savings account rates to gauge if the stock offers a better return." />
          <BentoTile label="Price / FCF" value={latest?.valuation.price_to_fcf != null ? fmt.x(latest.valuation.price_to_fcf) : '—'} sparkline={pFcfSparkline} color="#f2c35b" tip="Price relative to the actual cash the business generates after all expenses and reinvestment. Lower means more cash per dollar you invest." />
          <BentoTile label="Book Value / Share" value={latest?.valuation.book_value_per_share != null ? fmt.eps(latest.valuation.book_value_per_share) : '—'} icon="menu_book" tip="The company's total assets minus its total debts, divided by the number of shares. This is what each share would theoretically be worth if the company sold everything and paid off all debts." />
        </div>

        {/* Margin of Safety */}
        <div className={CARD}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-accent text-lg">shield</span>
            <MetricTooltip tip="Warren Buffett's core principle: only buy when the price is meaningfully below what you think the business is worth. The 'margin of safety' is the gap between the current price and fair value — the bigger the gap, the more room for error in your analysis. This chart shows how today's P/E compares to its own historical range.">
              <h4 className="font-serif text-lg text-sand-800 dark:text-warm-50">Margin of Safety</h4>
            </MetricTooltip>
          </div>
          {currentPE != null && avgPE != null ? (
            <>
              <div className="text-xs uppercase font-bold text-sand-500 dark:text-warm-400 mb-3">P/E vs {timeLabel} average</div>
              {/* Range bar */}
              <div className="relative h-3.5 bg-sand-200 dark:bg-warm-800 rounded-full mb-2">
                {/* Average marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-vi-gold z-10"
                  style={{ left: `${((avgPE - peRange.min) / (peRange.max - peRange.min)) * 100}%` }}
                />
                {/* Current P/E dot */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-5 h-5 rounded-full border-2 border-white dark:border-warm-900 shadow-md z-20"
                  style={{
                    left: `${Math.max(0, Math.min(100, ((currentPE - peRange.min) / (peRange.max - peRange.min)) * 100))}%`,
                    transform: 'translate(-50%, -50%)',
                    backgroundColor: marginOfSafety > 0 ? '#a0d6ad' : marginOfSafety < -0.2 ? '#ffb4ab' : '#f2c35b',
                  }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-sand-400 dark:text-warm-500 mb-4">
                <span>{fmt.x(peRange.min)}</span>
                <span className="text-vi-gold font-bold">Avg {fmt.x(avgPE)}</span>
                <span>{fmt.x(peRange.max)}</span>
              </div>
              <p className={`text-sm leading-relaxed ${marginOfSafety > 0 ? 'text-vi-sage' : marginOfSafety < -0.2 ? 'text-vi-rose' : 'text-vi-gold'}`}>
                {marginOfSafety > 0
                  ? `Trading ${Math.abs(marginOfSafety * 100).toFixed(0)}% below its ${timeLabel} average P/E. Historically, this stock has traded at higher valuations — worth understanding why the market is pricing it lower today.`
                  : marginOfSafety < -0.2
                    ? `Trading ${Math.abs(marginOfSafety * 100).toFixed(0)}% above its ${timeLabel} average. The market is pricing in higher expectations than usual — consider whether the business fundamentals support this premium.`
                    : `Near its ${timeLabel} fair value. The current price is in line with what investors have historically paid for this stock.`}
              </p>
            </>
          ) : (
            <p className="text-sm text-sand-500 dark:text-warm-400 italic">Price data required for margin of safety analysis.</p>
          )}
        </div>

        {/* Valuation Rating */}
        <div className={`${CARD} !p-5 flex items-center justify-between`}>
          <div>
            <div className="text-xs uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Valuation Rating</div>
            <div className="text-xl font-serif text-vi-accent">
              {ratings?.valuation?.rating || 'Moderate'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span>
            </div>
          </div>
          <span className="material-symbols-outlined text-3xl text-vi-accent/30">shield</span>
        </div>

        {/* Market Context */}
        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <span className="material-symbols-outlined text-[120px]">analytics</span>
          </div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            {currentPE != null
              ? `At ${fmt.x(currentPE)} earnings with ROIC at ${fmt.pct(latest?.valuation.roic)}, ${latest?.ticker || 'AAPL'} commands a premium — but its ${fmt.pct(latest?.valuation.fcf_yield)} free cash flow yield suggests cash generation supports the valuation.`
              : `ROIC of ${fmt.pct(latest?.valuation.roic)} with ROE at ${fmt.pct(latest?.valuation.roe)} signals strong capital efficiency — the foundation of durable value creation.`}
          </p>
        </div>
      </aside>
    </div>
  );
}

export function CashFlowPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  // CAGR calculations
  const years = useMemo(() => {
    if (!earliest || !latest) return 0;
    return (new Date(latest.fiscal_date) - new Date(earliest.fiscal_date)) / (365.25 * 24 * 3600 * 1000);
  }, [earliest, latest]);

  const calcCagr = useCallback((latestVal, earliestVal) => {
    if (!latestVal || !earliestVal || earliestVal <= 0 || years <= 0) return null;
    return Math.pow(latestVal / earliestVal, 1 / years) - 1;
  }, [years]);

  const fcfCagr = useMemo(() => calcCagr(latest?.cashflow.free_cash_flow, earliest?.cashflow.free_cash_flow), [latest, earliest, calcCagr]);
  const ocfCagr = useMemo(() => calcCagr(latest?.cashflow.operating_cash_flow, earliest?.cashflow.operating_cash_flow), [latest, earliest, calcCagr]);

  // Sparkline data
  const fcfSparkline = filtered.map(q => q.cashflow.free_cash_flow);
  const ocfSparkline = filtered.map(q => q.cashflow.operating_cash_flow);
  const fcfMarginSparkline = filtered.map(q => q.cashflow.fcf_margin);
  const capexSparkline = filtered.map(q => Math.abs(q.cashflow.capex));

  // Bar chart — all quarters in selected time range
  const chartQuarters = filtered;
  const maxOCF = Math.max(...chartQuarters.map(q => q.cashflow.operating_cash_flow));

  // Cash conversion ratio (FCF / Net Income)
  const cashConversion = latest?.cashflow.free_cash_flow && latest?.revenue_profit.net_income
    ? latest.cashflow.free_cash_flow / latest.revenue_profit.net_income
    : null;

  // Table data
  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      ocf: q.cashflow.operating_cash_flow,
      capex: q.cashflow.capex,
      fcf: q.cashflow.free_cash_flow,
      fcfMargin: q.cashflow.fcf_margin,
      ocfToRev: q.cashflow.ocf_to_revenue,
      fcfDelta: prev ? fmt.delta(q.cashflow.free_cash_flow, prev.cashflow.free_cash_flow) : null,
      fcfYoY: q.cashflow.fcf_change_yoy,
    };
  });

  const yoyColor = (v) => v == null ? 'text-sand-400 dark:text-warm-400' : v < 0 ? 'text-vi-rose font-bold' : 'text-vi-sage font-bold';

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      <section className="xl:col-span-8 space-y-6">
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Cash Flow Generation</h3>
            <RatingBadge rating={ratings?.cashflow?.rating} />
          </div>
          <div className="relative h-[280px] w-full flex items-end justify-between gap-1 md:gap-2 px-2">
            {chartQuarters.map((q) => {
              const ocfHeight = (q.cashflow.operating_cash_flow / maxOCF) * 100;
              const fcfRatio = q.cashflow.free_cash_flow / q.cashflow.operating_cash_flow;
              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${ocfHeight}%` }}>
                  <div className="absolute inset-0 bg-vi-sage/25 group-hover:bg-vi-sage/40 rounded-t-lg transition-all" />
                  <div className="absolute inset-x-0 bottom-0 bg-vi-gold/50 rounded-t-lg group-hover:bg-vi-gold/70 transition-all" style={{ height: `${fcfRatio * 100}%` }} />
                  <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-400 dark:text-warm-400 whitespace-nowrap">{q.fiscal_quarter}</div>
                  <div className="absolute -bottom-[18px] left-1/2 -translate-x-1/2 text-[8px] text-sand-400 dark:text-warm-500 whitespace-nowrap">{q.fiscal_year}</div>
                  <div className="absolute -top-[72px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div>OCF: {fmt.billions(q.cashflow.operating_cash_flow)}</div>
                    <div>FCF: {fmt.billions(q.cashflow.free_cash_flow)}</div>
                    <div>Margin: {fmt.pct(q.cashflow.fcf_margin)}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-6 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/30 rounded-sm border border-vi-sage/50" />Operating Cash Flow</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-gold/60 rounded-sm" />Free Cash Flow</div>
          </div>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-8">Cash Efficiency</h3>
          <div className="space-y-10">
            <MetricBar label="Operating Cash Flow" value={latest?.cashflow.operating_cash_flow} displayValue={fmt.billions(latest?.cashflow.operating_cash_flow)} maxValue={Math.max(...filtered.map(d => d.cashflow.operating_cash_flow)) * 1.2} color="bg-vi-sage" />
            <MetricBar label="Free Cash Flow" value={latest?.cashflow.free_cash_flow} displayValue={fmt.billions(latest?.cashflow.free_cash_flow)} maxValue={Math.max(...filtered.map(d => d.cashflow.operating_cash_flow)) * 1.2} color="bg-vi-gold" />
            <MetricBar label="FCF Margin" value={latest?.cashflow.fcf_margin} displayValue={fmt.pct(latest?.cashflow.fcf_margin)} maxValue={0.4} color="bg-vi-accent" />
          </div>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Quarterly Cash Flow Detail</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[700px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'Op. Cash Flow', 'CapEx', 'Free Cash Flow', 'FCF Margin', 'OCF/Revenue', 'FCF YoY'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 0 ? 'text-right' : ''}`}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className="px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap">{row.quarter}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.ocf)}</td>
                    <td className="px-4 py-4 text-right text-vi-rose">{fmt.billions(row.capex)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">{fmt.billions(row.fcf)}<DeltaChip value={row.fcfDelta} /></td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.pct(row.fcfMargin)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.pct(row.ocfToRev)}</td>
                    <td className={`px-4 py-4 text-right whitespace-nowrap ${yoyColor(row.fcfYoY)}`}>{row.fcfYoY != null ? fmt.pctSigned(row.fcfYoY) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <aside className="xl:col-span-4 space-y-6">
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            &ldquo;Free cash flow is what a business actually earns for its owners. {latest?.ticker || 'AAPL'} converts {fmt.pct(latest?.cashflow.fcf_margin)} of revenue into free cash — that&apos;s the real earning power behind the earnings.&rdquo;
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700"><span className="material-symbols-outlined text-vi-gold text-lg">psychology</span></div>
            <div><div className="text-sm font-bold">Insight Engine</div><div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div></div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className={`col-span-2 ${CARD} !p-4`}><CagrChart data={fcfSparkline} quarters={filtered} cagr={fcfCagr} label="Free Cash Flow" color="#f2c35b" formatFn={fmt.billions} /></div>
          <div className={`col-span-2 ${CARD} !p-4`}><CagrChart data={ocfSparkline} quarters={filtered} cagr={ocfCagr} label="Operating Cash Flow" color="#a0d6ad" formatFn={fmt.billions} /></div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="FCF Margin" value={fmt.pct(latest?.cashflow.fcf_margin)} sparkline={fcfMarginSparkline} color="#6d28d9" />
          <BentoTile label="CapEx" value={fmt.billions(Math.abs(latest?.cashflow.capex))} sparkline={capexSparkline} color="#ffb4ab" />
          <BentoTile label="Cash Conversion" value={cashConversion != null ? `${(cashConversion * 100).toFixed(0)}%` : '—'} icon="swap_vert" />
          <BentoTile label="OCF / Revenue" value={fmt.pct(latest?.cashflow.ocf_to_revenue)} icon="percent" />
        </div>

        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Cash Flow Rating</div>
            <div className="text-xl font-serif text-vi-sage">{ratings?.cashflow?.rating || 'Moderate'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span></div>
          </div>
          <span className="material-symbols-outlined text-3xl text-vi-sage/30">savings</span>
        </div>

        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity"><span className="material-symbols-outlined text-[120px]">savings</span></div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            FCF margin of {fmt.pct(latest?.cashflow.fcf_margin)} with CapEx at just {fmt.pct(latest?.cashflow.capex_intensity)} of revenue signals an asset-light model. {cashConversion != null && cashConversion > 1 ? 'Cash conversion above 100% means the business generates more cash than its reported earnings — a quality signal.' : 'Strong cash generation supports dividends and buybacks.'}
          </p>
        </div>
      </aside>
    </div>
  );
}

export function DebtPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  const deSparkline = filtered.map(q => q.debt_leverage.debt_to_equity);
  const icSparkline = filtered.map(q => q.debt_leverage.interest_coverage);
  const netDebtSparkline = filtered.map(q => q.balance_sheet.net_debt);
  const currentRatioSparkline = filtered.map(q => q.debt_leverage.current_ratio);

  const debtTrend = earliest && latest
    ? ((latest.balance_sheet.total_debt - earliest.balance_sheet.total_debt) / earliest.balance_sheet.total_debt)
    : null;

  const chartQuarters = filtered;
  const maxDebt = Math.max(...chartQuarters.map(q => q.balance_sheet.total_debt));

  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      totalDebt: q.balance_sheet.total_debt,
      cash: q.balance_sheet.cash_position,
      netDebt: q.balance_sheet.net_debt,
      de: q.debt_leverage.debt_to_equity,
      ic: q.debt_leverage.interest_coverage,
      currentRatio: q.debt_leverage.current_ratio,
      deDelta: prev ? fmt.delta(q.debt_leverage.debt_to_equity, prev.debt_leverage.debt_to_equity) : null,
    };
  });

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      <section className="xl:col-span-8 space-y-6">
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Debt vs Cash Position</h3>
            <RatingBadge rating={ratings?.debt?.rating} />
          </div>
          <div className="relative h-[280px] w-full flex items-end justify-between gap-1 md:gap-2 px-2">
            {chartQuarters.map((q) => {
              const debtHeight = (q.balance_sheet.total_debt / maxDebt) * 100;
              const cashRatio = q.balance_sheet.cash_position / q.balance_sheet.total_debt;
              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${debtHeight}%` }}>
                  <div className="absolute inset-0 bg-vi-rose/25 group-hover:bg-vi-rose/40 rounded-t-lg transition-all" />
                  <div className="absolute inset-x-0 bottom-0 bg-vi-sage/50 rounded-t-lg group-hover:bg-vi-sage/70 transition-all" style={{ height: `${Math.min(cashRatio * 100, 100)}%` }} />
                  <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-400 dark:text-warm-400 whitespace-nowrap">{q.fiscal_quarter}</div>
                  <div className="absolute -bottom-[18px] left-1/2 -translate-x-1/2 text-[8px] text-sand-400 dark:text-warm-500 whitespace-nowrap">{q.fiscal_year}</div>
                  <div className="absolute -top-[82px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div className="text-vi-rose">Debt: {fmt.billions(q.balance_sheet.total_debt)}</div>
                    <div className="text-vi-sage">Cash: {fmt.billions(q.balance_sheet.cash_position)}</div>
                    <div>D/E: {fmt.ratio(q.debt_leverage.debt_to_equity)}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-6 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-rose/30 rounded-sm border border-vi-rose/50" />Total Debt</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/50 rounded-sm border border-vi-sage/60" />Cash Position</div>
          </div>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-8">Balance Sheet Strength</h3>
          <div className="space-y-10">
            <MetricBar label="Total Debt" value={latest?.balance_sheet.total_debt} displayValue={fmt.billions(latest?.balance_sheet.total_debt)} maxValue={Math.max(...filtered.map(d => d.balance_sheet.total_debt)) * 1.2} color="bg-vi-rose" />
            <MetricBar label="Cash Position" value={latest?.balance_sheet.cash_position} displayValue={fmt.billions(latest?.balance_sheet.cash_position)} maxValue={Math.max(...filtered.map(d => d.balance_sheet.total_debt)) * 1.2} color="bg-vi-sage" />
            <MetricBar label="D/E Ratio" value={latest?.debt_leverage.debt_to_equity} displayValue={fmt.ratio(latest?.debt_leverage.debt_to_equity)} maxValue={3} color="bg-vi-gold" />
          </div>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Quarterly Debt Detail</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[700px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'Total Debt', 'Cash', 'Net Debt', 'D/E Ratio', 'Int. Coverage', 'Current Ratio'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 0 ? 'text-right' : ''}`}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className="px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap">{row.quarter}</td>
                    <td className="px-4 py-4 text-right text-vi-rose">{fmt.billions(row.totalDebt)}</td>
                    <td className="px-4 py-4 text-right text-vi-sage">{fmt.billions(row.cash)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.netDebt)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">{fmt.ratio(row.de)}<DeltaChip value={row.deDelta} /></td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.x(row.ic)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.ratio(row.currentRatio)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <aside className="xl:col-span-4 space-y-6">
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            {latest?.debt_leverage.interest_coverage > 10
              ? <>&ldquo;Interest coverage at {fmt.x(latest?.debt_leverage.interest_coverage)} means this company earns its interest expense many times over. Debt used wisely — like borrowing at low rates to buy back shares — can create value.&rdquo;</>
              : <>&ldquo;A D/E ratio of {fmt.ratio(latest?.debt_leverage.debt_to_equity)} warrants attention. The balance sheet should be a fortress, not a liability. Look for declining debt and growing cash reserves.&rdquo;</>
            }
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700"><span className="material-symbols-outlined text-vi-gold text-lg">psychology</span></div>
            <div><div className="text-sm font-bold">Insight Engine</div><div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div></div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className={`col-span-2 ${CARD} !p-4`}><CagrChart data={deSparkline} quarters={filtered} cagr={deSparkline.length > 1 ? deSparkline.reduce((a, b) => a + b, 0) / deSparkline.length : 0} label="Debt-to-Equity Trend" color="#ffb4ab" formatFn={fmt.ratio} summaryLabel={`Avg ${fmt.ratio(deSparkline.reduce((a, b) => a + b, 0) / deSparkline.length)}`} /></div>
          <div className={`col-span-2 ${CARD} !p-4`}><CagrChart data={icSparkline} quarters={filtered} cagr={icSparkline.length > 1 ? icSparkline.reduce((a, b) => a + b, 0) / icSparkline.length : 0} label="Interest Coverage" color="#a0d6ad" formatFn={fmt.x} summaryLabel={`Avg ${fmt.x(icSparkline.reduce((a, b) => a + b, 0) / icSparkline.length)}`} /></div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="D/E Ratio" value={fmt.ratio(latest?.debt_leverage.debt_to_equity)} sparkline={deSparkline} color="#ffb4ab" />
          <BentoTile label="Interest Cov." value={fmt.x(latest?.debt_leverage.interest_coverage)} sparkline={icSparkline} color="#a0d6ad" />
          <BentoTile label="Net Debt" value={fmt.billions(latest?.balance_sheet.net_debt)} sparkline={netDebtSparkline} color="#f2c35b" />
          <BentoTile label="Current Ratio" value={fmt.ratio(latest?.debt_leverage.current_ratio)} sparkline={currentRatioSparkline} color="#6d28d9" />
        </div>

        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Debt Trajectory</div>
            <div className={`text-xl font-serif ${debtTrend != null && debtTrend < 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
              {debtTrend != null ? (debtTrend < 0 ? 'Deleveraging' : 'Increasing') : '—'}
              <span className="text-sm font-sans text-sand-500 dark:text-warm-400 ml-2">{debtTrend != null ? fmt.pctSigned(debtTrend) : ''}</span>
            </div>
          </div>
          <span className={`material-symbols-outlined text-3xl ${debtTrend != null && debtTrend < 0 ? 'text-vi-sage/30' : 'text-vi-rose/30'}`}>{debtTrend != null && debtTrend < 0 ? 'trending_down' : 'trending_up'}</span>
        </div>

        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity"><span className="material-symbols-outlined text-[120px]">account_balance</span></div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            D/E ratio at {fmt.ratio(latest?.debt_leverage.debt_to_equity)} with interest coverage of {fmt.x(latest?.debt_leverage.interest_coverage)} — {latest?.debt_leverage.interest_coverage > 15 ? 'the company can service its debt comfortably. Cash reserves of ' + fmt.billions(latest?.balance_sheet.cash_position) + ' provide a strong buffer.' : 'leverage requires monitoring but remains manageable.'}
          </p>
        </div>
      </aside>
    </div>
  );
}

export function EarningsQualityPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  const sbcSparkline = filtered.map(q => q.earnings_quality.sbc_actual);
  const sbcPctSparkline = filtered.map(q => q.earnings_quality.sbc_to_revenue_pct);
  const gaapSparkline = filtered.map(q => q.earnings_quality.gaap_net_income);

  const years = useMemo(() => {
    if (!earliest || !latest) return 0;
    return (new Date(latest.fiscal_date) - new Date(earliest.fiscal_date)) / (365.25 * 24 * 3600 * 1000);
  }, [earliest, latest]);

  const gaapCagr = useMemo(() => {
    if (!latest?.earnings_quality.gaap_net_income || !earliest?.earnings_quality.gaap_net_income || earliest.earnings_quality.gaap_net_income <= 0 || years <= 0) return null;
    return Math.pow(latest.earnings_quality.gaap_net_income / earliest.earnings_quality.gaap_net_income, 1 / years) - 1;
  }, [latest, earliest, years]);

  const gaapGap = latest?.earnings_quality.gaap_adjusted_gap_pct;

  const sbcTrend = earliest && latest && earliest.earnings_quality.sbc_to_revenue_pct > 0
    ? latest.earnings_quality.sbc_to_revenue_pct - earliest.earnings_quality.sbc_to_revenue_pct
    : null;

  const chartQuarters = filtered;
  const maxEarnings = Math.max(...chartQuarters.map(q => Math.max(q.earnings_quality.gaap_net_income, q.earnings_quality.adjusted_earnings)));

  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      gaap: q.earnings_quality.gaap_net_income,
      sbc: q.earnings_quality.sbc_actual,
      sbcPct: q.earnings_quality.sbc_to_revenue_pct,
      adjusted: q.earnings_quality.adjusted_earnings,
      gaapGap: q.earnings_quality.gaap_adjusted_gap_pct,
      dna: q.earnings_quality.d_and_a,
      sbcDelta: prev ? fmt.delta(q.earnings_quality.sbc_to_revenue_pct, prev.earnings_quality.sbc_to_revenue_pct) : null,
    };
  });

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      <section className="xl:col-span-8 space-y-6">
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">GAAP vs Adjusted Earnings</h3>
            <RatingBadge rating={ratings?.earnings_quality?.rating} />
          </div>
          <div className="relative h-[280px] w-full flex items-end justify-between gap-1 md:gap-2 px-2">
            {chartQuarters.map((q) => {
              const adjustedHeight = (q.earnings_quality.adjusted_earnings / maxEarnings) * 100;
              const gaapRatio = q.earnings_quality.gaap_net_income / q.earnings_quality.adjusted_earnings;
              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${adjustedHeight}%` }}>
                  <div className="absolute inset-0 bg-vi-gold/25 group-hover:bg-vi-gold/40 rounded-t-lg transition-all" />
                  <div className="absolute inset-x-0 bottom-0 bg-vi-sage/50 rounded-t-lg group-hover:bg-vi-sage/70 transition-all" style={{ height: `${Math.min(gaapRatio * 100, 100)}%` }} />
                  <div className="absolute -bottom-5 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-400 dark:text-warm-400 whitespace-nowrap">{q.fiscal_quarter}</div>
                  <div className="absolute -bottom-[18px] left-1/2 -translate-x-1/2 text-[8px] text-sand-400 dark:text-warm-500 whitespace-nowrap">{q.fiscal_year}</div>
                  <div className="absolute -top-[72px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div className="text-vi-sage">GAAP: {fmt.billions(q.earnings_quality.gaap_net_income)}</div>
                    <div className="text-vi-gold">Adjusted: {fmt.billions(q.earnings_quality.adjusted_earnings)}</div>
                    <div>SBC: {fmt.billions(q.earnings_quality.sbc_actual)}</div>
                  </div>
                </div>
              );
            })}
          </div>
          <div className="mt-10 flex flex-wrap items-center gap-6 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-sage/50 rounded-sm border border-vi-sage/60" />GAAP Net Income</div>
            <div className="flex items-center gap-2"><span className="w-3 h-3 bg-vi-gold/30 rounded-sm border border-vi-gold/50" />Adjusted Earnings</div>
          </div>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-8">Earnings Authenticity</h3>
          <div className="space-y-10">
            <MetricBar label="GAAP Net Income" value={latest?.earnings_quality.gaap_net_income} displayValue={fmt.billions(latest?.earnings_quality.gaap_net_income)} maxValue={Math.max(...filtered.map(d => d.earnings_quality.gaap_net_income)) * 1.2} color="bg-vi-sage" />
            <MetricBar label="Stock-Based Compensation" value={latest?.earnings_quality.sbc_actual} displayValue={fmt.billions(latest?.earnings_quality.sbc_actual)} maxValue={Math.max(...filtered.map(d => d.earnings_quality.gaap_net_income)) * 1.2} color="bg-vi-rose" />
            <MetricBar label="SBC / Revenue" value={latest?.earnings_quality.sbc_to_revenue_pct} displayValue={fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} maxValue={0.1} color="bg-vi-gold" />
          </div>
          <p className="mt-6 text-[11px] text-sand-500 dark:text-warm-400 italic">SBC is a real cost — it dilutes existing shareholders. Low SBC relative to revenue means more of the reported profit is actual cash profit.</p>
        </div>

        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Quarterly Earnings Quality</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[700px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'GAAP Income', 'SBC', 'SBC/Revenue', 'Adjusted', 'GAAP Gap', 'D&A'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 0 ? 'text-right' : ''}`}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {tableData.map((row, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className="px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap">{row.quarter}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.gaap)}</td>
                    <td className="px-4 py-4 text-right text-vi-rose">{fmt.billions(row.sbc)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200 whitespace-nowrap">{fmt.pct(row.sbcPct)}<DeltaChip value={row.sbcDelta} /></td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.adjusted)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.pct(row.gaapGap)}</td>
                    <td className="px-4 py-4 text-right text-sand-600 dark:text-warm-200">{fmt.billions(row.dna)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <aside className="xl:col-span-4 space-y-6">
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            {latest?.earnings_quality.sbc_to_revenue_pct < 0.03
              ? <>&ldquo;SBC at just {fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} of revenue is remarkably low. This means nearly all reported earnings translate into real cash — a hallmark of shareholder-friendly management.&rdquo;</>
              : <>&ldquo;Stock-based compensation at {fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} of revenue is a hidden cost. True owner earnings should subtract SBC — it&apos;s real dilution even if it doesn&apos;t hit the cash flow statement.&rdquo;</>
            }
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700"><span className="material-symbols-outlined text-vi-gold text-lg">psychology</span></div>
            <div><div className="text-sm font-bold">Insight Engine</div><div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div></div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className={`col-span-2 ${CARD} !p-4`}><CagrChart data={gaapSparkline} quarters={filtered} cagr={gaapCagr} label="GAAP Net Income" color="#a0d6ad" formatFn={fmt.billions} /></div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="SBC / Revenue" value={fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} sparkline={sbcPctSparkline} color="#ffb4ab" />
          <BentoTile label="GAAP Gap" value={fmt.pct(gaapGap)} icon="compare_arrows" />
          <BentoTile label="SBC (Quarterly)" value={fmt.billions(latest?.earnings_quality.sbc_actual)} sparkline={sbcSparkline} color="#f2c35b" />
          <BentoTile label="D&A" value={fmt.billions(latest?.earnings_quality.d_and_a)} icon="engineering" />
        </div>

        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">SBC Trend</div>
            <div className={`text-xl font-serif ${sbcTrend != null && sbcTrend < 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
              {sbcTrend != null ? (sbcTrend < 0 ? 'Declining' : 'Rising') : '—'}
              <span className="text-sm font-sans text-sand-500 dark:text-warm-400 ml-2">{sbcTrend != null ? fmt.pctPts(sbcTrend) : ''}</span>
            </div>
          </div>
          <span className={`material-symbols-outlined text-3xl ${sbcTrend != null && sbcTrend < 0 ? 'text-vi-sage/30' : 'text-vi-rose/30'}`}>{sbcTrend != null && sbcTrend < 0 ? 'trending_down' : 'trending_up'}</span>
        </div>

        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity"><span className="material-symbols-outlined text-[120px]">verified</span></div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            {latest?.earnings_quality.sbc_to_revenue_pct < 0.03
              ? `With SBC at just ${fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} of revenue, earnings quality is high. The gap between GAAP and adjusted earnings of ${fmt.pct(gaapGap)} reflects depreciation, not accounting games.`
              : `SBC of ${fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} relative to revenue should be monitored. Compare this to the company's buyback spending to see if management is offsetting dilution.`}
          </p>
        </div>
      </aside>
    </div>
  );
}

export function EarningsPerformancePanel({ data, postEarnings }) {
  // postEarnings is an array of quarterly earnings with price performance, most recent first
  const quarters = useMemo(() => postEarnings || [], [postEarnings]);
  const latest = quarters[0];
  const upcoming = data?.find(q => {
    const ee = q.earnings_events;
    return ee?.earnings_date && !ee?.eps_actual && ee.earnings_date > new Date().toISOString().slice(0, 10);
  });

  // Stats across all quarters
  const stats = useMemo(() => {
    const reported = quarters.filter(q => q.eps_actual != null);
    if (reported.length === 0) return null;
    const beats = reported.filter(q => q.eps_beat);
    const avgSurprise = reported.reduce((s, q) => s + (q.eps_surprise_pct || 0), 0) / reported.length;
    const avg1d = reported.filter(q => q.price_change_1d != null);
    const avg1dVal = avg1d.length > 0 ? avg1d.reduce((s, q) => s + q.price_change_1d, 0) / avg1d.length : null;
    return {
      totalQuarters: reported.length,
      beatCount: beats.length,
      beatRate: Math.round((beats.length / reported.length) * 100),
      avgSurprise: avgSurprise,
      avg1dMove: avg1dVal,
    };
  }, [quarters]);

  // Sparkline data: EPS surprise % over time (oldest first for chart)
  const surpriseSparkline = useMemo(() =>
    quarters.filter(q => q.eps_surprise_pct != null).reverse().map(q => q.eps_surprise_pct),
  [quarters]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column */}
      <section className="xl:col-span-8 space-y-6">
        {/* Latest Earnings Card */}
        {latest && (
          <div className={`${CARD} border-l-4 ${latest.eps_beat ? 'border-vi-sage' : 'border-vi-rose'}`}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Latest Earnings</h3>
              <span className={`text-xs font-bold uppercase tracking-wider px-2 py-1 rounded ${
                latest.eps_beat ? 'bg-vi-sage/10 text-vi-sage' : 'bg-vi-rose/10 text-vi-rose'
              }`}>
                {latest.eps_beat ? 'BEAT' : 'MISS'}
              </span>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">Reported</span>
                <span className="text-lg font-serif font-bold text-sand-900 dark:text-warm-50">{latest.earnings_date}</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">EPS</span>
                <span className="text-lg font-serif font-bold text-sand-900 dark:text-warm-50">
                  ${latest.eps_actual?.toFixed(2)} <span className="text-sm text-sand-400">vs ${latest.eps_estimated?.toFixed(2)}</span>
                </span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">EPS Surprise</span>
                <span className={`text-lg font-serif font-bold ${latest.eps_surprise_pct > 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                  {latest.eps_surprise_pct != null ? `${latest.eps_surprise_pct > 0 ? '+' : ''}${latest.eps_surprise_pct.toFixed(1)}%` : '—'}
                </span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">Revenue Surprise</span>
                <span className={`text-lg font-serif font-bold ${(latest.revenue_surprise_pct || 0) > 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                  {latest.revenue_surprise_pct != null ? `${latest.revenue_surprise_pct > 0 ? '+' : ''}${latest.revenue_surprise_pct.toFixed(1)}%` : '—'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Post-Earnings Price Reaction */}
        {latest?.price_on_earnings_date != null && (
          <div className={CARD}>
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-4">Post-Earnings Price Reaction</h3>
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: '1-Day After', value: latest.price_change_1d },
                { label: '5-Day After', value: latest.price_change_5d },
                { label: '30-Day After', value: latest.price_change_30d },
              ].map(({ label, value }) => (
                <div key={label} className={`${CARD} !p-5 text-center`}>
                  <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block mb-1">{label}</span>
                  <span className={`text-3xl font-serif font-bold ${
                    value == null ? 'text-sand-300' : value >= 0 ? 'text-vi-sage' : 'text-vi-rose'
                  }`}>
                    {value != null ? `${value >= 0 ? '+' : ''}${value.toFixed(1)}%` : '—'}
                  </span>
                  <span className="text-[10px] text-sand-400 dark:text-warm-500 block mt-1">
                    from ${latest.price_on_earnings_date?.toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* EPS Surprise Trend */}
        {surpriseSparkline.length > 2 && (
          <div className={CARD}>
            <CagrChart
              data={surpriseSparkline}
              quarters={quarters.filter(q => q.eps_surprise_pct != null).reverse()}
              cagr={stats?.avgSurprise || 0}
              label="EPS Surprise %"
              color="#6d9e78"
              formatFn={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
              summaryLabel={stats ? `Avg ${stats.avgSurprise > 0 ? '+' : ''}${stats.avgSurprise.toFixed(1)}%` : ''}
            />
          </div>
        )}

        {/* Earnings History Table (12-16 quarters) */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Earnings History ({quarters.length} Quarters)</h3>
          <div className="overflow-x-auto -mx-8">
            <table className="w-full text-left min-w-[900px]">
              <thead>
                <tr className="bg-sand-200/50 dark:bg-warm-800/50">
                  {['Quarter', 'Date', 'EPS', 'Est.', 'Surprise', 'Result', 'Rev Surprise', '1-Day', '5-Day', '30-Day'].map((col, i) => (
                    <th key={i} className={`px-4 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i > 1 ? 'text-right' : ''}`}>
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
                {quarters.map((q, i) => (
                  <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                    <td className="px-4 py-4 font-bold text-sand-800 dark:text-warm-50 whitespace-nowrap">
                      {q.fiscal_quarter} {q.fiscal_year}
                    </td>
                    <td className="px-4 py-4 text-sand-600 dark:text-warm-200 whitespace-nowrap text-sm">{q.earnings_date}</td>
                    <td className="px-4 py-4 text-right font-bold text-sand-800 dark:text-warm-50">${q.eps_actual?.toFixed(2)}</td>
                    <td className="px-4 py-4 text-right text-sand-400 dark:text-warm-400">${q.eps_estimated?.toFixed(2)}</td>
                    <td className={`px-4 py-4 text-right font-bold ${(q.eps_surprise_pct || 0) >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {q.eps_surprise_pct != null ? `${q.eps_surprise_pct >= 0 ? '+' : ''}${q.eps_surprise_pct.toFixed(1)}%` : '—'}
                    </td>
                    <td className="px-4 py-4 text-right">
                      <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
                        q.eps_beat ? 'bg-vi-sage/10 text-vi-sage' : 'bg-vi-rose/10 text-vi-rose'
                      }`}>
                        {q.eps_beat ? 'BEAT' : 'MISS'}
                      </span>
                    </td>
                    <td className={`px-4 py-4 text-right ${(q.revenue_surprise_pct || 0) >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {q.revenue_surprise_pct != null ? `${q.revenue_surprise_pct >= 0 ? '+' : ''}${q.revenue_surprise_pct.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`px-4 py-4 text-right ${(q.price_change_1d || 0) >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {q.price_change_1d != null ? `${q.price_change_1d >= 0 ? '+' : ''}${q.price_change_1d.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`px-4 py-4 text-right ${(q.price_change_5d || 0) >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {q.price_change_5d != null ? `${q.price_change_5d >= 0 ? '+' : ''}${q.price_change_5d.toFixed(1)}%` : '—'}
                    </td>
                    <td className={`px-4 py-4 text-right ${(q.price_change_30d || 0) >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                      {q.price_change_30d != null ? `${q.price_change_30d >= 0 ? '+' : ''}${q.price_change_30d.toFixed(1)}%` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Right column — Insights */}
      <aside className="xl:col-span-4 space-y-6">
        {/* Beat Rate Summary */}
        {stats && (
          <div className={`${CARD} border-l-4 border-vi-gold`}>
            <h4 className="text-sm font-bold uppercase tracking-wider text-sand-500 dark:text-warm-400 mb-4">Track Record</h4>
            <div className="space-y-4">
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">Beat Rate</span>
                <span className="text-3xl font-serif font-bold text-sand-900 dark:text-warm-50">{stats.beatRate}%</span>
                <span className="text-sm text-sand-400 ml-2">{stats.beatCount}/{stats.totalQuarters} quarters</span>
              </div>
              <div>
                <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">Avg EPS Surprise</span>
                <span className={`text-2xl font-serif font-bold ${stats.avgSurprise >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                  {stats.avgSurprise >= 0 ? '+' : ''}{stats.avgSurprise.toFixed(1)}%
                </span>
              </div>
              {stats.avg1dMove != null && (
                <div>
                  <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 block">Avg 1-Day Move</span>
                  <span className={`text-2xl font-serif font-bold ${stats.avg1dMove >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    {stats.avg1dMove >= 0 ? '+' : ''}{stats.avg1dMove.toFixed(1)}%
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Next Earnings Countdown */}
        {upcoming && (
          <div className={CARD}>
            <h4 className="text-sm font-bold uppercase tracking-wider text-sand-500 dark:text-warm-400 mb-3">Next Earnings</h4>
            <span className="text-2xl font-serif font-bold text-vi-gold block">
              {upcoming.earnings_events?.earnings_date}
            </span>
            {upcoming.earnings_events?.eps_estimated && (
              <span className="text-sm text-sand-400 dark:text-warm-400 block mt-1">
                Consensus EPS: ${Number(upcoming.earnings_events.eps_estimated).toFixed(2)}
              </span>
            )}
            <span className="text-[10px] text-sand-400 dark:text-warm-500 block mt-2">
              {(() => {
                const d = upcoming.earnings_events?.earnings_date;
                if (!d) return '';
                const diff = Math.ceil((new Date(d) - new Date()) / (1000 * 60 * 60 * 24));
                return diff > 0 ? `${diff} days away` : diff === 0 ? 'Today' : `${Math.abs(diff)} days ago`;
              })()}
            </span>
          </div>
        )}

        {/* No data state */}
        {!latest && (
          <div className={CARD}>
            <p className="text-sand-400 dark:text-warm-400 text-sm italic">
              No reported earnings data available for this ticker.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}

export function MoatPanel({ data, ratings, timeRange, sectorAggregate, sector }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  const COST_OF_CAPITAL = 0.10;

  const roicData = filtered.map(q => q.valuation.roic);
  const grossMarginData = filtered.map(q => q.revenue_profit.gross_margin);
  const opMarginData = filtered.map(q => q.revenue_profit.operating_margin);
  const capexData = filtered.map(q => q.cashflow.capex_intensity);

  const fcfConversionData = filtered.map(q => {
    if (!q.revenue_profit.net_income || q.revenue_profit.net_income <= 0) return null;
    const ratio = q.cashflow.free_cash_flow / q.revenue_profit.net_income;
    return Math.max(-10, Math.min(10, ratio)); // Cap at +/-10x (1000%)
  });
  const fcfConversionValid = fcfConversionData.filter(v => v != null);
  const fcfConversionQuarters = filtered.filter((_, i) => fcfConversionData[i] != null);

  const years = useMemo(() => {
    if (!earliest || !latest) return 0;
    return (new Date(latest.fiscal_date) - new Date(earliest.fiscal_date)) / (365.25 * 24 * 3600 * 1000);
  }, [earliest, latest]);

  const roicCagr = useMemo(() => {
    if (!latest?.valuation.roic || !earliest?.valuation.roic || earliest.valuation.roic <= 0 || years <= 0) return null;
    return Math.pow(latest.valuation.roic / earliest.valuation.roic, 1 / years) - 1;
  }, [latest, earliest, years]);

  const sectorMetrics = sectorAggregate?.metrics || {};
  const sMedianGrossMargin = sectorMetrics.gross_margin?.median != null ? sectorMetrics.gross_margin.median / 100 : null;

  const marginStability = useMemo(() => {
    const margins = filtered.map(q => q.revenue_profit.operating_margin).filter(v => v != null);
    if (margins.length < 4) return null;
    const mean = margins.reduce((a, b) => a + b, 0) / margins.length;
    const variance = margins.reduce((sum, v) => sum + (v - mean) ** 2, 0) / margins.length;
    const cv = mean > 0 ? Math.sqrt(variance) / mean : 1;
    if (cv < 0.05) return { label: 'Very Stable', color: 'text-vi-sage', bg: 'bg-vi-sage/15' };
    if (cv < 0.15) return { label: 'Stable', color: 'text-vi-sage', bg: 'bg-vi-sage/10' };
    if (cv < 0.30) return { label: 'Moderate', color: 'text-vi-gold', bg: 'bg-vi-gold/10' };
    return { label: 'Volatile', color: 'text-vi-rose', bg: 'bg-vi-rose/10' };
  }, [filtered]);

  const moatTrend = useMemo(() => {
    if (filtered.length < 8) return null;
    const mid = Math.floor(filtered.length / 2);
    const avgFirst = filtered.slice(0, mid).reduce((s, q) => s + q.valuation.roic, 0) / mid;
    const avgSecond = filtered.slice(mid).reduce((s, q) => s + q.valuation.roic, 0) / (filtered.length - mid);
    const change = avgSecond - avgFirst;
    if (change > 0.02) return { label: 'Strengthening', icon: 'trending_up', color: 'text-vi-sage', border: 'border-vi-sage', desc: 'ROIC is trending higher — the competitive advantage appears to be widening over time.' };
    if (change < -0.02) return { label: 'Eroding', icon: 'trending_down', color: 'text-vi-rose', border: 'border-vi-rose', desc: 'ROIC is trending lower — competitors may be closing the gap. Watch margins and reinvestment rates.' };
    return { label: 'Stable', icon: 'trending_flat', color: 'text-vi-gold', border: 'border-vi-gold', desc: 'ROIC is holding steady — the moat appears durable with consistent returns on capital.' };
  }, [filtered]);

  const avgFCFConversion = fcfConversionValid.length > 0
    ? fcfConversionValid.reduce((a, b) => a + b, 0) / fcfConversionValid.length : null;

  const currentSpread = latest?.valuation.roic != null ? latest.valuation.roic - COST_OF_CAPITAL : null;
  const spreadPct = currentSpread != null ? (currentSpread * 100).toFixed(1) : null;

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      <section className="xl:col-span-8 space-y-6">
        {/* Moat Trend Indicator */}
        {moatTrend && (
          <div className={`${CARD} !py-5 border-l-4 ${moatTrend.border}`}>
            <div className="flex items-center gap-3">
              <span className={`material-symbols-outlined text-2xl ${moatTrend.color}`}>{moatTrend.icon}</span>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-lg font-serif font-bold text-sand-800 dark:text-warm-50">Moat Trend:</span>
                  <span className={`text-lg font-serif font-bold ${moatTrend.color}`}>{moatTrend.label}</span>
                </div>
                <p className="text-sm text-sand-500 dark:text-warm-400">{moatTrend.desc}</p>
              </div>
            </div>
          </div>
        )}

        {/* Value Creation: ROIC vs Cost of Capital */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <MetricTooltip tip="Return on Invested Capital measures how much profit the company generates per dollar of capital. When ROIC exceeds the cost of capital (roughly 10%), the business is creating real value. A consistent gap above 10% over many years is the strongest quantitative evidence of a competitive moat.">
              <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Value Creation</h3>
            </MetricTooltip>
            <span className="text-xs font-bold text-sand-400 dark:text-warm-500 uppercase tracking-wider">ROIC vs 10% benchmark</span>
          </div>
          <p className="text-sm text-sand-500 dark:text-warm-400 mb-4 italic">Does this company earn more than its cost of capital?</p>

          {currentSpread != null && (
            <div className={`flex items-baseline gap-3 mb-5 px-4 py-3 rounded-lg ${currentSpread > 0 ? 'bg-vi-sage/10' : 'bg-vi-rose/10'}`}>
              <span className={`text-3xl font-serif font-bold ${currentSpread > 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                {currentSpread > 0 ? '+' : ''}{spreadPct}%
              </span>
              <span className="text-sm text-sand-600 dark:text-warm-200">
                {currentSpread > 0
                  ? 'above cost of capital — this business creates value for investors'
                  : 'below cost of capital — the business is currently destroying value'}
              </span>
            </div>
          )}

          <CagrChart data={roicData} quarters={filtered} cagr={roicCagr} label="ROIC" color="#6d28d9" formatFn={fmt.pct}
            refLine={{ value: COST_OF_CAPITAL, label: '10% benchmark', color: '#ef4444' }} />
        </div>

        {/* Pricing Power: Margin Stability */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <MetricTooltip tip="Stable or rising margins over time indicate pricing power — the company can maintain or increase prices without losing customers. Volatile or declining margins suggest competitive pressure or commodity-like products.">
              <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Pricing Power</h3>
            </MetricTooltip>
            {marginStability && (
              <span className={`text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${marginStability.bg} ${marginStability.color}`}>{marginStability.label}</span>
            )}
          </div>
          <p className="text-sm text-sand-500 dark:text-warm-400 mb-4 italic">Can this company maintain its margins without competing on price?</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <CagrChart data={grossMarginData} quarters={filtered}
              cagr={grossMarginData.reduce((a, b) => a + b, 0) / grossMarginData.length || 0}
              label="Gross Margin" color="#a0d6ad" formatFn={fmt.pct}
              summaryLabel={`Avg ${fmt.pct(grossMarginData.reduce((a, b) => a + b, 0) / grossMarginData.length)}`}
              refLine={sMedianGrossMargin != null ? { value: sMedianGrossMargin, label: `${sector} median`, color: '#6d28d9' } : undefined} />
            <CagrChart data={opMarginData} quarters={filtered}
              cagr={opMarginData.reduce((a, b) => a + b, 0) / opMarginData.length || 0}
              label="Operating Margin" color="#f2c35b" formatFn={fmt.pct}
              summaryLabel={`Avg ${fmt.pct(opMarginData.reduce((a, b) => a + b, 0) / opMarginData.length)}`} />
          </div>
        </div>

        {/* Cash Conversion */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <MetricTooltip tip="FCF Conversion compares actual cash generated to reported accounting profits. A ratio above 100% means the company produces more cash than it reports in earnings — the strongest sign of real profitability. Consistently below 70% may indicate earnings quality concerns.">
              <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Cash Conversion</h3>
            </MetricTooltip>
            {avgFCFConversion != null && (
              <span className={`text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded ${avgFCFConversion >= 1 ? 'bg-vi-sage/15 text-vi-sage' : avgFCFConversion >= 0.7 ? 'bg-vi-gold/15 text-vi-gold' : 'bg-vi-rose/15 text-vi-rose'}`}>
                {avgFCFConversion >= 1 ? 'Excellent' : avgFCFConversion >= 0.7 ? 'Adequate' : 'Poor'}
              </span>
            )}
          </div>
          <p className="text-sm text-sand-500 dark:text-warm-400 mb-4 italic">Are the reported profits backed by real cash?</p>

          {avgFCFConversion != null && (
            <div className={`flex items-baseline gap-3 mb-5 px-4 py-3 rounded-lg ${avgFCFConversion >= 1 ? 'bg-vi-sage/10' : avgFCFConversion >= 0.7 ? 'bg-vi-gold/10' : 'bg-vi-rose/10'}`}>
              <span className={`text-3xl font-serif font-bold ${avgFCFConversion >= 1 ? 'text-vi-sage' : avgFCFConversion >= 0.7 ? 'text-vi-gold' : 'text-vi-rose'}`}>
                {(avgFCFConversion * 100).toFixed(0)}%
              </span>
              <span className="text-sm text-sand-600 dark:text-warm-200">
                {avgFCFConversion >= 1 ? 'every dollar of profit is backed by real cash' : avgFCFConversion >= 0.7 ? 'most reported profits convert to cash' : 'reported profits aren\'t fully translating into cash'}
              </span>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <CagrChart data={fcfConversionValid} quarters={fcfConversionQuarters}
              cagr={avgFCFConversion || 0}
              label="FCF / Net Income" color="#38bdf8"
              formatFn={(v) => `${(v * 100).toFixed(0)}%`}
              summaryLabel={avgFCFConversion != null ? `Avg ${(avgFCFConversion * 100).toFixed(0)}%` : ''}
              refLine={{ value: 1.0, label: '100%', color: '#a0d6ad' }} />
            <CagrChart data={capexData} quarters={filtered}
              cagr={capexData.reduce((a, b) => a + b, 0) / capexData.length || 0}
              label="CapEx / Revenue" color="#ffb4ab"
              formatFn={fmt.pct}
              summaryLabel={`Avg ${fmt.pct(capexData.reduce((a, b) => a + b, 0) / capexData.length)}`} />
          </div>
        </div>
      </section>

      <aside className="xl:col-span-4 space-y-6">
        {/* Oracle's Perspective */}
        <div className={`${CARD} border-l-4 border-vi-gold-container shadow-xl`}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-gold" style={{ fontVariationSettings: "'FILL' 1" }}>format_quote</span>
            <span className="text-xs font-bold uppercase tracking-widest text-vi-gold-dim">Oracle&apos;s Perspective</span>
          </div>
          <p className="font-serif italic text-lg leading-relaxed text-sand-700 dark:text-warm-100 mb-6">
            {currentSpread != null && currentSpread > 0.1
              ? <>&ldquo;A wide moat isn&apos;t about one good year — it&apos;s about sustained returns on capital that competitors can&apos;t replicate. A ROIC of {fmt.pct(latest?.valuation.roic)} with {marginStability?.label?.toLowerCase() || 'steady'} margins is the financial fingerprint of a durable competitive advantage.&rdquo;</>
              : currentSpread != null && currentSpread > 0
                ? <>&ldquo;This business earns above its cost of capital, which is the minimum bar for value creation. The question is whether these returns can persist — the margin trend and cash conversion offer important clues.&rdquo;</>
                : <>&ldquo;A business that can&apos;t earn above its cost of capital is renting its position, not owning it. Look for improving ROIC trends and stabilizing margins as signs the moat may be rebuilding.&rdquo;</>
            }
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sand-200 dark:bg-warm-800 flex items-center justify-center border border-sand-300 dark:border-warm-700">
              <span className="material-symbols-outlined text-vi-gold text-lg">psychology</span>
            </div>
            <div>
              <div className="text-sm font-bold">Insight Engine</div>
              <div className="text-[10px] text-sand-500 dark:text-warm-400 uppercase tracking-tighter">Value Synthesis AI</div>
            </div>
          </div>
        </div>

        {/* Moat Scorecard */}
        <div className={CARD}>
          <h4 className="font-serif text-lg text-sand-800 dark:text-warm-50 mb-4">Moat Scorecard</h4>
          {[
            { label: 'ROIC vs Cost of Capital', value: currentSpread != null ? (currentSpread > 0.05 ? 'Wide Spread' : currentSpread > 0 ? 'Narrow Spread' : 'Negative') : '—', pass: currentSpread != null && currentSpread > 0 },
            { label: 'Margin Stability', value: marginStability?.label || '—', pass: marginStability && (marginStability.label === 'Very Stable' || marginStability.label === 'Stable') },
            { label: 'FCF Conversion', value: avgFCFConversion != null ? `${(avgFCFConversion * 100).toFixed(0)}%` : '—', pass: avgFCFConversion != null && avgFCFConversion >= 0.8 },
            { label: 'Moat Direction', value: moatTrend?.label || '—', pass: moatTrend && moatTrend.label !== 'Eroding' },
          ].map((item) => (
            <div key={item.label} className="flex items-center justify-between py-2.5 border-b border-sand-200/30 dark:border-warm-800/30 last:border-0">
              <span className="text-sm text-sand-600 dark:text-warm-200">{item.label}</span>
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-sand-800 dark:text-warm-50">{item.value}</span>
                <span className={`material-symbols-outlined text-base ${item.pass ? 'text-vi-sage' : 'text-vi-rose'}`}>
                  {item.pass ? 'check_circle' : 'cancel'}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Bento Tiles */}
        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="ROIC" value={fmt.pct(latest?.valuation.roic)} sparkline={roicData} color="#6d28d9" />
          <BentoTile label="Gross Margin" value={fmt.pct(latest?.revenue_profit.gross_margin)} sparkline={grossMarginData} color="#a0d6ad" />
          <BentoTile label="FCF Conversion" value={avgFCFConversion != null ? `${(avgFCFConversion * 100).toFixed(0)}%` : '—'} icon="swap_vert" />
          <BentoTile label="CapEx Intensity" value={fmt.pct(latest?.cashflow.capex_intensity)} sparkline={capexData} color="#ffb4ab" />
        </div>

        {/* Moat Rating */}
        <div className={`${CARD} !p-5 flex items-center justify-between`}>
          <div>
            <div className="text-xs uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Moat Rating</div>
            <div className="text-xl font-serif text-vi-accent">
              {ratings?.moat?.rating || 'Moderate'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span>
            </div>
          </div>
          <span className="material-symbols-outlined text-3xl text-vi-accent/30">shield</span>
        </div>

        {/* Educational Context */}
        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <span className="material-symbols-outlined text-[120px]">shield</span>
          </div>
          <h4 className="font-serif text-lg mb-3">What Makes a Moat?</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            A competitive moat comes from advantages that are hard to copy: strong brands, network effects, cost advantages, or high switching costs. The metrics above measure the financial evidence of a moat — they reveal whether a competitive advantage exists, even if they can&apos;t identify the source.
          </p>
        </div>
      </aside>
    </div>
  );
}

