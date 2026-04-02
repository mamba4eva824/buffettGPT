import { useMemo, useCallback } from 'react';
import { fmt } from './mockData';
import { MetricBar, DataTable, RatingBadge, CARD, DeltaChip, BentoTile, CagrChart, DuPontBlock, useFilteredData } from './shared';

export function GrowthPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  // Chart bars — last 8 quarters
  const chartQuarters = filtered.slice(-8);
  const maxRevenue = Math.max(...chartQuarters.map(q => q.revenue_profit.revenue));

  // --- CAGR calculations (#1 + #6) ---
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
  const niCagr = useMemo(() => calcCagr(latest?.revenue_profit.net_income, earliest?.revenue_profit.net_income), [latest, earliest, calcCagr]);
  const fcfCagr = useMemo(() => calcCagr(latest?.cashflow.free_cash_flow, earliest?.cashflow.free_cash_flow), [latest, earliest, calcCagr]);
  const roicCagr = useMemo(() => calcCagr(latest?.valuation.roic, earliest?.valuation.roic), [latest, earliest, calcCagr]);

  // #6 Acceleration: latest YoY vs CAGR
  const latestRevYoY = latest?.revenue_profit.revenue_growth_yoy;
  const isAccelerating = (latestRevYoY != null && revCagr != null) ? latestRevYoY > revCagr : null;

  // --- TTM calculations (#4) ---
  const ttm = useMemo(() => {
    if (filtered.length < 4) return null;
    const last4 = filtered.slice(-4);
    const prior4 = filtered.length >= 8 ? filtered.slice(-8, -4) : null;
    const sum = (arr, fn) => arr.reduce((s, q) => s + fn(q), 0);
    const ttmRev = sum(last4, q => q.revenue_profit.revenue);
    const ttmNI = sum(last4, q => q.revenue_profit.net_income);
    const ttmEPS = sum(last4, q => q.revenue_profit.eps);
    const ttmFCF = sum(last4, q => q.cashflow.free_cash_flow);
    const ttmGP = sum(last4, q => q.revenue_profit.gross_profit);
    let revGrowth = null, niGrowth = null, epsGrowth = null;
    if (prior4) {
      const pRev = sum(prior4, q => q.revenue_profit.revenue);
      const pNI = sum(prior4, q => q.revenue_profit.net_income);
      const pEPS = sum(prior4, q => q.revenue_profit.eps);
      if (pRev > 0) revGrowth = (ttmRev - pRev) / Math.abs(pRev);
      if (pNI !== 0) niGrowth = (ttmNI - pNI) / Math.abs(pNI);
      if (pEPS !== 0) epsGrowth = (ttmEPS - pEPS) / Math.abs(pEPS);
    }
    return { revenue: ttmRev, netIncome: ttmNI, eps: ttmEPS, fcf: ttmFCF, grossProfit: ttmGP, revGrowth, niGrowth, epsGrowth };
  }, [filtered]);

  // --- Growth consistency (#3) ---
  const consistency = useMemo(() => {
    const withGrowth = filtered.filter(q => q.revenue_profit.revenue_growth_yoy != null);
    if (withGrowth.length === 0) return null;
    const positive = withGrowth.filter(q => q.revenue_profit.revenue_growth_yoy > 0).length;
    return { positive, total: withGrowth.length };
  }, [filtered]);

  // Table data — most recent first, with QoQ deltas + new YoY columns (#1, #7)
  const reversed = filtered.slice().reverse();
  const tableData = reversed.map((q, i) => {
    const prev = reversed[i + 1];
    return {
      quarter: `${q.fiscal_quarter} ${q.fiscal_year}`,
      revenue: q.revenue_profit.revenue,
      netIncome: q.revenue_profit.net_income,
      eps: q.revenue_profit.eps,
      yoyGrowth: q.revenue_profit.revenue_growth_yoy,
      epsYoY: q.revenue_profit.eps_growth_yoy,
      niYoY: q.revenue_profit.net_income_growth_yoy,
      gpYoY: q.revenue_profit.gross_profit_growth_yoy,
      revDelta: prev ? fmt.delta(q.revenue_profit.revenue, prev.revenue_profit.revenue) : null,
      niDelta: prev ? fmt.delta(q.revenue_profit.net_income, prev.revenue_profit.net_income) : null,
      epsDelta: prev ? fmt.delta(q.revenue_profit.eps, prev.revenue_profit.eps) : null,
    };
  });

  // Sparkline data for bento tiles
  const revenueSparkline = filtered.map(q => q.revenue_profit.revenue);
  const epsSparkline = filtered.map(q => q.revenue_profit.eps);
  const niSparkline = filtered.map(q => q.revenue_profit.net_income);
  const fcfSparkline = filtered.map(q => q.cashflow.free_cash_flow);
  const roicSparkline = filtered.map(q => q.valuation.roic);

  // Color helper for YoY cells
  const yoyColor = (v) => v == null ? 'text-sand-400 dark:text-warm-400' : v < 0 ? 'text-vi-rose font-bold' : 'text-vi-sage font-bold';

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column: Chart + TTM + Table */}
      <section className="xl:col-span-8 space-y-6">
        {/* Bar Chart */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-8">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Revenue & Net Income Growth</h3>
          </div>

          {/* Bar visualization */}
          <div className="relative h-[320px] w-full mt-4 flex items-end justify-between gap-2 md:gap-4 px-2">
            {chartQuarters.map((q) => {
              const revHeight = (q.revenue_profit.revenue / maxRevenue) * 100;
              const niRatio = q.revenue_profit.net_income / q.revenue_profit.revenue;
              const growth = q.revenue_profit.revenue_growth_yoy;
              const barColor = growth == null
                ? 'bg-sand-300 dark:bg-warm-700'
                : growth >= 0
                  ? 'bg-vi-sage/30 dark:bg-vi-sage/20'
                  : 'bg-vi-rose/30 dark:bg-vi-rose/20';
              const barHover = growth == null
                ? 'group-hover:bg-sand-400 dark:group-hover:bg-warm-600'
                : growth >= 0
                  ? 'group-hover:bg-vi-sage/50'
                  : 'group-hover:bg-vi-rose/50';
              return (
                <div key={q.fiscal_date} className="relative flex-1 group" style={{ height: `${revHeight}%` }}>
                  <div className={`absolute inset-0 ${barColor} ${barHover} rounded-t-lg transition-all`} />
                  <div
                    className="absolute inset-x-0 bottom-0 bg-vi-gold/50 rounded-t-lg group-hover:bg-vi-gold/70 transition-all"
                    style={{ height: `${niRatio * 100}%` }}
                  />
                  <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-[9px] font-medium text-sand-400 dark:text-warm-400 whitespace-nowrap">
                    {q.fiscal_quarter}
                  </div>
                  <div className="absolute -top-[72px] left-1/2 -translate-x-1/2 text-[10px] font-mono text-sand-600 dark:text-warm-200 opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg z-10 border border-sand-200 dark:border-warm-700">
                    <div className="font-bold">{q.fiscal_quarter} {q.fiscal_year}</div>
                    <div>Rev: {fmt.billions(q.revenue_profit.revenue)}</div>
                    <div>NI: {fmt.billions(q.revenue_profit.net_income)}</div>
                    {growth != null && (
                      <div className={growth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}>YoY: {fmt.pctSigned(growth)}</div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Growth line SVG overlay */}
            <svg className="absolute inset-0 h-full w-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="none">
              <polyline
                points={chartQuarters.map((q, i) => {
                  const maxGrowth = Math.max(...chartQuarters.map(d => Math.abs(d.revenue_profit.revenue_growth_yoy || 0)), 0.01);
                  const x = ((i + 0.5) / chartQuarters.length) * 100;
                  const g = q.revenue_profit.revenue_growth_yoy || 0;
                  const y = 50 - (g / maxGrowth) * 40;
                  return `${x},${y}`;
                }).join(' ')}
                fill="none"
                stroke="#a0d6ad"
                strokeWidth="0.5"
                strokeDasharray="1.5"
                className="opacity-80"
              />
            </svg>
          </div>

          {/* Legend */}
          <div className="mt-10 flex flex-wrap items-center gap-6 justify-center text-xs font-medium text-sand-500 dark:text-warm-300">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-vi-sage/30 rounded-sm border border-vi-sage/50" />
              Revenue (growth)
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-vi-rose/30 rounded-sm border border-vi-rose/50" />
              Revenue (decline)
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 bg-vi-gold/60 rounded-sm" />
              Net Income
            </div>
            <div className="flex items-center gap-2">
              <span className="w-4 border-b border-dashed border-vi-sage" />
              YoY Growth
            </div>
          </div>
        </div>

        {/* #4 TTM Summary */}
        {ttm && (
          <div className={CARD}>
            <div className="flex items-center gap-2 mb-4">
              <span className="material-symbols-outlined text-vi-gold text-lg">calendar_today</span>
              <h3 className="font-serif text-lg text-sand-800 dark:text-warm-50">Trailing Twelve Months (TTM)</h3>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Revenue</div>
                <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{fmt.billions(ttm.revenue)}</div>
                {ttm.revGrowth != null && (
                  <div className={`text-xs mt-1 ${ttm.revGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    {fmt.pctSigned(ttm.revGrowth)} vs prior TTM
                  </div>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Net Income</div>
                <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{fmt.billions(ttm.netIncome)}</div>
                {ttm.niGrowth != null && (
                  <div className={`text-xs mt-1 ${ttm.niGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    {fmt.pctSigned(ttm.niGrowth)} vs prior TTM
                  </div>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">EPS</div>
                <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{fmt.eps(ttm.eps)}</div>
                {ttm.epsGrowth != null && (
                  <div className={`text-xs mt-1 ${ttm.epsGrowth >= 0 ? 'text-vi-sage' : 'text-vi-rose'}`}>
                    {fmt.pctSigned(ttm.epsGrowth)} vs prior TTM
                  </div>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Free Cash Flow</div>
                <div className="text-xl font-serif text-sand-900 dark:text-warm-50">{fmt.billions(ttm.fcf)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Enhanced Data Table — #1 EPS YoY, NI YoY + #7 GP YoY columns */}
        <div className="bg-sand-100 dark:bg-warm-900 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-sand-200/50 dark:border-warm-800/50">
            <h3 className="font-serif text-lg text-sand-800 dark:text-warm-50">Quarterly Performance Breakdown</h3>
          </div>
          <div className="overflow-x-auto max-h-[480px] overflow-y-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-sand-200/50 dark:bg-warm-800/50 text-[10px] uppercase tracking-wider text-sand-500 dark:text-warm-300 sticky top-0 z-10">
                <tr>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Quarter</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Revenue</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Rev YoY</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">GP YoY</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">Net Income</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">NI YoY</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">EPS</th>
                  <th className="px-4 py-4 font-semibold bg-sand-200/80 dark:bg-warm-800/80 backdrop-blur-sm">EPS YoY</th>
                </tr>
              </thead>
              <tbody className="text-sm divide-y divide-sand-200/30 dark:divide-warm-800/30">
                {tableData.map((row, i) => (
                  <tr
                    key={i}
                    className={`hover:bg-sand-200/40 dark:hover:bg-warm-800/40 transition-colors ${i % 2 === 1 ? 'bg-sand-50/50 dark:bg-warm-950/30' : ''}`}
                  >
                    <td className="px-4 py-4 font-medium text-sand-800 dark:text-warm-50 whitespace-nowrap">{row.quarter}</td>
                    <td className="px-4 py-4 text-sand-600 dark:text-warm-200 whitespace-nowrap">
                      {fmt.billions(row.revenue)}
                      <DeltaChip value={row.revDelta} />
                    </td>
                    <td className={`px-4 py-4 whitespace-nowrap ${yoyColor(row.yoyGrowth)}`}>
                      {row.yoyGrowth != null ? fmt.pctSigned(row.yoyGrowth) : '—'}
                    </td>
                    <td className={`px-4 py-4 whitespace-nowrap ${yoyColor(row.gpYoY)}`}>
                      {row.gpYoY != null ? fmt.pctSigned(row.gpYoY) : '—'}
                    </td>
                    <td className="px-4 py-4 text-sand-600 dark:text-warm-200 whitespace-nowrap">
                      {fmt.billions(row.netIncome)}
                      <DeltaChip value={row.niDelta} />
                    </td>
                    <td className={`px-4 py-4 whitespace-nowrap ${yoyColor(row.niYoY)}`}>
                      {row.niYoY != null ? fmt.pctSigned(row.niYoY) : '—'}
                    </td>
                    <td className="px-4 py-4 text-sand-600 dark:text-warm-200 whitespace-nowrap">
                      {fmt.eps(row.eps)}
                      <DeltaChip value={row.epsDelta} />
                    </td>
                    <td className={`px-4 py-4 whitespace-nowrap ${yoyColor(row.epsYoY)}`}>
                      {row.epsYoY != null ? fmt.pctSigned(row.epsYoY) : '—'}
                    </td>
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
            &ldquo;Buffett looks for consistent earnings power. {latest?.ticker || 'AAPL'} shows {fmt.pct(latest?.revenue_profit.revenue_growth_yoy)} growth with net margin at {fmt.pct(latest?.revenue_profit.net_margin)} — high margins remain their moat.&rdquo;
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

        {/* Growth CAGR Charts + Metrics */}
        <div className="grid grid-cols-2 gap-4">
          {/* Revenue CAGR chart with #6 acceleration badge */}
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
          {/* EPS & NI CAGR Charts */}
          <div className={`col-span-2 ${CARD} !p-4 space-y-4`}>
            <CagrChart data={epsSparkline} quarters={filtered} cagr={epsCagr} label="EPS Growth" color="#f2c35b" formatFn={fmt.eps} />
            <div className="border-t border-sand-200/30 dark:border-warm-800/30 pt-4">
              <CagrChart data={niSparkline} quarters={filtered} cagr={niCagr} label="Net Income Growth" color="#6d28d9" formatFn={fmt.billions} />
            </div>
          </div>
          {/* #5 FCF Growth chart */}
          <div className={`col-span-2 ${CARD} !p-4`}>
            <CagrChart data={fcfSparkline} quarters={filtered} cagr={fcfCagr} label="Free Cash Flow" color="#38bdf8" formatFn={fmt.billions} />
          </div>
          {/* #8 ROIC Trend chart */}
          <div className={`col-span-2 ${CARD} !p-4`}>
            <CagrChart data={roicSparkline} quarters={filtered} cagr={roicCagr} label="Return on Invested Capital" color="#f59e0b" formatFn={fmt.pct} />
          </div>
          {/* #3 Growth Consistency */}
          <div className={`${CARD} !p-4 relative overflow-hidden`}>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Consistency</div>
            {consistency ? (
              <>
                <div className="text-2xl font-serif text-sand-900 dark:text-warm-50">
                  {consistency.positive}/{consistency.total}
                </div>
                <div className="text-[10px] text-sand-500 dark:text-warm-400 mt-0.5">
                  quarters with YoY growth
                </div>
                {/* Mini donut */}
                <svg className="absolute right-3 bottom-3 opacity-40" width="28" height="28" viewBox="0 0 36 36">
                  <circle cx="18" cy="18" r="14" fill="none" stroke="currentColor" strokeWidth="4" className="text-sand-200 dark:text-warm-700" />
                  <circle
                    cx="18" cy="18" r="14" fill="none" stroke="#a0d6ad" strokeWidth="4"
                    strokeDasharray={`${(consistency.positive / consistency.total) * 88} 88`}
                    strokeDashoffset="22" strokeLinecap="round"
                  />
                </svg>
              </>
            ) : (
              <div className="text-2xl font-serif text-sand-900 dark:text-warm-50">—</div>
            )}
          </div>
        </div>

        {/* #2 Margin Expansion Card */}
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

        {/* Growth Rating */}
        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Growth Rating</div>
            <div className="text-xl font-serif text-vi-sage">
              {ratings?.growth?.rating || 'Moderate'} <span className="text-sm font-sans text-sand-500 dark:text-warm-400">Conviction</span>
            </div>
          </div>
          <span className="material-symbols-outlined text-3xl text-vi-sage/30">visibility</span>
        </div>

        {/* Market Context */}
        <div className={`${CARD} relative overflow-hidden group`}>
          <div className="absolute -right-8 -bottom-8 opacity-5 group-hover:opacity-10 transition-opacity">
            <span className="material-symbols-outlined text-[120px]">public</span>
          </div>
          <h4 className="font-serif text-lg mb-3">Market Context</h4>
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">
            Revenue growth of {fmt.pct(latest?.revenue_profit.revenue_growth_yoy)} with net margin at {fmt.pct(latest?.revenue_profit.net_margin)} demonstrates pricing power. CapEx intensity at just {fmt.pct(latest?.cashflow.capex_intensity)} signals an asset-light model — a hallmark Buffett trait.
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
  const chartQuarters = filtered.slice(-8);

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

export function ValuationPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];

  // Quarters with valid valuation multiples (non-null P/E)
  const withMultiples = useMemo(() => filtered.filter(q => q.valuation.pe_ratio != null), [filtered]);

  // Historical averages for assessment
  const histAvg = useMemo(() => {
    if (withMultiples.length === 0) return {};
    const avg = (arr, fn) => arr.reduce((s, q) => s + fn(q), 0) / arr.length;
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

  const roicCagr = useMemo(() => {
    if (!latest?.valuation.roic || !earliest?.valuation.roic || earliest.valuation.roic <= 0 || years <= 0) return null;
    return Math.pow(latest.valuation.roic / earliest.valuation.roic, 1 / years) - 1;
  }, [latest, earliest, years]);

  // Sparkline data
  const peSparkline = withMultiples.map(q => q.valuation.pe_ratio);
  const evEbitdaSparkline = withMultiples.map(q => q.valuation.ev_ebitda).filter(v => v != null);
  const earningsYieldSparkline = withMultiples.map(q => q.valuation.earnings_yield);
  const pFcfSparkline = withMultiples.map(q => q.valuation.price_to_fcf).filter(v => v != null);
  const roicSparkline = filtered.map(q => q.valuation.roic);

  // Assessment helper: compare current to historical average
  const assess = (current, avg) => {
    if (current == null || avg == null || avg === 0) return { label: '—', color: 'text-sand-400' };
    const ratio = current / avg;
    if (ratio < 0.8) return { label: 'Below Average', color: 'text-vi-sage', bg: 'bg-vi-sage/10' };
    if (ratio > 1.2) return { label: 'Above Average', color: 'text-vi-rose', bg: 'bg-vi-rose/10' };
    return { label: 'Near Average', color: 'text-vi-gold', bg: 'bg-vi-gold/10' };
  };

  // Price multiple cards config
  const multipleCards = [
    {
      label: 'Price-to-Earnings',
      abbr: 'P/E',
      value: latest?.valuation.pe_ratio,
      avg: histAvg.pe,
      explain: 'How many years of profits you\'re paying for',
      format: fmt.x,
    },
    {
      label: 'Price-to-Book',
      abbr: 'P/B',
      value: latest?.valuation.pb_ratio,
      avg: histAvg.pb,
      explain: 'What premium you\'re paying over the company\'s net assets',
      format: fmt.x,
    },
    {
      label: 'Enterprise Value Multiple',
      abbr: 'EV/EBITDA',
      value: latest?.valuation.ev_ebitda,
      avg: histAvg.evEbitda,
      explain: 'What the entire business costs relative to its cash earnings',
      format: fmt.x,
    },
    {
      label: 'Price-to-Free Cash',
      abbr: 'P/FCF',
      value: latest?.valuation.price_to_fcf,
      avg: histAvg.pFcf,
      explain: 'What you pay per dollar the business actually generates',
      format: fmt.x,
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
        {/* Price Multiples Overview */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">What Are You Paying?</h3>
            <RatingBadge rating={ratings?.valuation?.rating} />
          </div>
          <div className="flex items-center gap-2 mb-6">
            <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-vi-gold/15 text-vi-gold border border-vi-gold/30">
              <span className="material-symbols-outlined text-[10px] mr-0.5 align-middle">info</span>
              Mock Price Data
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {multipleCards.map((m) => {
              const assessment = assess(m.value, m.avg);
              return (
                <div key={m.abbr} className={`${CARD} !p-5 relative overflow-hidden`}>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400">{m.label}</span>
                    {assessment.bg && (
                      <span className={`text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${assessment.bg} ${assessment.color}`}>
                        {assessment.label}
                      </span>
                    )}
                  </div>
                  <div className="text-3xl font-serif font-bold text-sand-900 dark:text-warm-50 mb-1">
                    {m.value != null ? m.format(m.value) : '—'}
                  </div>
                  <p className="text-[11px] text-sand-500 dark:text-warm-400 leading-snug italic">{m.explain}</p>
                  {m.avg != null && (
                    <div className="text-[10px] text-sand-400 dark:text-warm-500 mt-2">
                      Avg: {m.format(m.avg)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Valuation Over Time */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Valuation Over Time</h3>
          <div className="space-y-6">
            <CagrChart
              data={peSparkline}
              quarters={withMultiples}
              cagr={histAvg.pe || 0}
              label="P/E Ratio"
              color="#6d28d9"
              formatFn={fmt.x}
              summaryLabel={histAvg.pe != null ? `Avg ${fmt.x(histAvg.pe)}` : ''}
            />
            <div className="border-t border-sand-200/30 dark:border-warm-800/30 pt-6">
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
        </div>

        {/* Capital Efficiency */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-8">Capital Efficiency</h3>
          <div className="space-y-10">
            <MetricBar label="Return on Equity (ROE)" value={latest?.valuation.roe} displayValue={fmt.pct(latest?.valuation.roe)} maxValue={2} color="bg-vi-accent" />
            <MetricBar label="Return on Invested Capital (ROIC)" value={latest?.valuation.roic} displayValue={fmt.pct(latest?.valuation.roic)} maxValue={1} color="bg-vi-accent/80" />
            <MetricBar label="Return on Assets (ROA)" value={latest?.valuation.roa} displayValue={fmt.pct(latest?.valuation.roa)} maxValue={0.5} color="bg-vi-accent/60" />
          </div>
          <div className="mt-8">
            <CagrChart data={roicSparkline} quarters={filtered} cagr={roicCagr} label="ROIC Trend" color="#6d28d9" formatFn={fmt.pct} />
          </div>
        </div>

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
                : <>&ldquo;At {fmt.x(currentPE)} earnings, the market expects continued growth. With ROIC at {fmt.pct(latest?.valuation.roic)}, every dollar of capital generates strong returns — but the price demands conviction.&rdquo;</>
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

        {/* Bento Tiles */}
        <div className="grid grid-cols-2 gap-4">
          <BentoTile label="P/E Ratio" value={latest?.valuation.pe_ratio != null ? fmt.x(latest.valuation.pe_ratio) : '—'} sparkline={peSparkline} color="#6d28d9" />
          <BentoTile label="Earnings Yield" value={latest?.valuation.earnings_yield != null ? fmt.pct(latest.valuation.earnings_yield) : '—'} sparkline={earningsYieldSparkline} color="#a0d6ad" />
          <BentoTile label="Price / FCF" value={latest?.valuation.price_to_fcf != null ? fmt.x(latest.valuation.price_to_fcf) : '—'} sparkline={pFcfSparkline} color="#f2c35b" />
          <BentoTile label="Book Value / Share" value={latest?.valuation.book_value_per_share != null ? fmt.eps(latest.valuation.book_value_per_share) : '—'} icon="menu_book" />
        </div>

        {/* Margin of Safety */}
        <div className={CARD}>
          <div className="flex items-center gap-2 mb-4">
            <span className="material-symbols-outlined text-vi-accent text-lg">shield</span>
            <h4 className="font-serif text-lg text-sand-800 dark:text-warm-50">Margin of Safety</h4>
          </div>
          {currentPE != null && avgPE != null ? (
            <>
              <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-3">P/E vs Historical Average</div>
              {/* Range bar */}
              <div className="relative h-3 bg-sand-200 dark:bg-warm-800 rounded-full mb-2">
                {/* Average marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-vi-gold z-10"
                  style={{ left: `${((avgPE - peRange.min) / (peRange.max - peRange.min)) * 100}%` }}
                />
                {/* Current P/E dot */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 border-white dark:border-warm-900 shadow-md z-20"
                  style={{
                    left: `${Math.max(0, Math.min(100, ((currentPE - peRange.min) / (peRange.max - peRange.min)) * 100))}%`,
                    transform: 'translate(-50%, -50%)',
                    backgroundColor: marginOfSafety > 0 ? '#a0d6ad' : marginOfSafety < -0.2 ? '#ffb4ab' : '#f2c35b',
                  }}
                />
              </div>
              <div className="flex justify-between text-[9px] text-sand-400 dark:text-warm-500 mb-4">
                <span>{fmt.x(peRange.min)}</span>
                <span className="text-vi-gold font-bold">Avg {fmt.x(avgPE)}</span>
                <span>{fmt.x(peRange.max)}</span>
              </div>
              <p className={`text-sm leading-relaxed italic ${marginOfSafety > 0 ? 'text-vi-sage' : marginOfSafety < -0.2 ? 'text-vi-rose' : 'text-vi-gold'}`}>
                {marginOfSafety > 0
                  ? `Trading ${Math.abs(marginOfSafety * 100).toFixed(0)}% below its historical average P/E. "Be greedy when others are fearful."`
                  : marginOfSafety < -0.2
                    ? `Trading ${Math.abs(marginOfSafety * 100).toFixed(0)}% above its historical average. Premium pricing demands premium conviction.`
                    : 'Near its historical fair value. Focus on the quality of the business.'}
              </p>
            </>
          ) : (
            <p className="text-sm text-sand-500 dark:text-warm-400 italic">Price data required for margin of safety analysis.</p>
          )}
        </div>

        {/* Valuation Rating */}
        <div className={`${CARD} !p-4 flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">Valuation Rating</div>
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
  const rows = filtered.slice().reverse().map(q => [
    `${q.fiscal_quarter} ${q.fiscal_year}`,
    fmt.billions(q.cashflow.operating_cash_flow),
    fmt.billions(Math.abs(q.cashflow.capex)),
    fmt.billions(q.cashflow.free_cash_flow),
    fmt.pct(q.cashflow.fcf_margin),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className={`col-span-12 lg:col-span-5 ${CARD}`}>
        <div className="flex justify-between items-center mb-8">
          <h3 className="font-serif text-xl font-bold">Cash Generation</h3>
          <RatingBadge rating={ratings?.cashflow?.rating} />
        </div>
        <div className="space-y-10">
          <MetricBar label="Operating Cash Flow" value={latest?.cashflow.operating_cash_flow} displayValue={fmt.billions(latest?.cashflow.operating_cash_flow)} maxValue={Math.max(...filtered.map(d => d.cashflow.operating_cash_flow)) * 1.2} color="bg-vi-sage" />
          <MetricBar label="Free Cash Flow" value={latest?.cashflow.free_cash_flow} displayValue={fmt.billions(latest?.cashflow.free_cash_flow)} maxValue={Math.max(...filtered.map(d => d.cashflow.operating_cash_flow)) * 1.2} color="bg-vi-gold" />
          <MetricBar label="FCF Margin" value={latest?.cashflow.fcf_margin} displayValue={fmt.pct(latest?.cashflow.fcf_margin)} maxValue={0.4} color="bg-vi-accent" />
        </div>
      </div>

      <div className="col-span-12 lg:col-span-7">
        <DataTable columns={['Quarter', 'Op. CF', 'CapEx', 'FCF', 'FCF Margin']} rows={rows} />
      </div>
    </div>
  );
}

export function DebtPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const rows = filtered.slice().reverse().map(q => [
    `${q.fiscal_quarter} ${q.fiscal_year}`,
    fmt.billions(q.balance_sheet.total_debt),
    fmt.billions(q.balance_sheet.cash_position),
    fmt.billions(q.balance_sheet.net_debt),
    fmt.ratio(q.debt_leverage.debt_to_equity),
    fmt.x(q.debt_leverage.interest_coverage),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className={`col-span-12 lg:col-span-5 ${CARD}`}>
        <div className="flex justify-between items-center mb-8">
          <h3 className="font-serif text-xl font-bold">Balance Sheet Strength</h3>
          <RatingBadge rating={ratings?.debt?.rating} />
        </div>
        <div className="space-y-10">
          <MetricBar label="Total Debt" value={latest?.balance_sheet.total_debt} displayValue={fmt.billions(latest?.balance_sheet.total_debt)} maxValue={Math.max(...filtered.map(d => d.balance_sheet.total_debt)) * 1.2} color="bg-vi-rose" />
          <MetricBar label="Cash Position" value={latest?.balance_sheet.cash_position} displayValue={fmt.billions(latest?.balance_sheet.cash_position)} maxValue={Math.max(...filtered.map(d => d.balance_sheet.total_debt)) * 1.2} color="bg-vi-sage" />
          <MetricBar label="D/E Ratio" value={latest?.debt_leverage.debt_to_equity} displayValue={fmt.ratio(latest?.debt_leverage.debt_to_equity)} maxValue={3} color="bg-vi-gold" />
        </div>
      </div>

      <div className="col-span-12 lg:col-span-7">
        <DataTable columns={['Quarter', 'Total Debt', 'Cash', 'Net Debt', 'D/E', 'Int. Coverage']} rows={rows} />
      </div>
    </div>
  );
}

export function EarningsQualityPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const rows = filtered.slice().reverse().map(q => [
    `${q.fiscal_quarter} ${q.fiscal_year}`,
    fmt.billions(q.earnings_quality.gaap_net_income),
    fmt.billions(q.earnings_quality.sbc_actual),
    fmt.pct(q.earnings_quality.sbc_to_revenue_pct),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className={`col-span-12 lg:col-span-5 ${CARD}`}>
        <div className="flex justify-between items-center mb-8">
          <h3 className="font-serif text-xl font-bold">Earnings Authenticity</h3>
          <RatingBadge rating={ratings?.earnings_quality?.rating} />
        </div>
        <div className="space-y-10">
          <MetricBar label="GAAP Net Income" value={latest?.earnings_quality.gaap_net_income} displayValue={fmt.billions(latest?.earnings_quality.gaap_net_income)} maxValue={Math.max(...filtered.map(d => d.earnings_quality.gaap_net_income)) * 1.2} color="bg-vi-sage" />
          <MetricBar label="Stock-Based Comp" value={latest?.earnings_quality.sbc_actual} displayValue={fmt.billions(latest?.earnings_quality.sbc_actual)} maxValue={Math.max(...filtered.map(d => d.earnings_quality.gaap_net_income)) * 1.2} color="bg-vi-rose" />
          <MetricBar label="SBC / Revenue" value={latest?.earnings_quality.sbc_to_revenue_pct} displayValue={fmt.pct(latest?.earnings_quality.sbc_to_revenue_pct)} maxValue={0.1} color="bg-vi-gold" />
        </div>
      </div>

      <div className="col-span-12 lg:col-span-7">
        <DataTable columns={['Quarter', 'GAAP Income', 'SBC', 'SBC/Revenue']} rows={rows} />
      </div>
    </div>
  );
}

export function DilutionPanel({ data, ratings, timeRange }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];
  const earliest = filtered[0];
  const shareChange = earliest && latest
    ? ((latest.dilution.diluted_shares - earliest.dilution.diluted_shares) / earliest.dilution.diluted_shares * 100).toFixed(1)
    : 0;

  const rows = filtered.slice().reverse().map(q => [
    `${q.fiscal_quarter} ${q.fiscal_year}`,
    fmt.shares(q.dilution.basic_shares),
    fmt.shares(q.dilution.diluted_shares),
    fmt.pct(q.dilution.dilution_pct / 100),
  ]);

  return (
    <div className="grid grid-cols-12 gap-6">
      <div className={`col-span-12 lg:col-span-5 ${CARD}`}>
        <div className="flex justify-between items-center mb-8">
          <h3 className="font-serif text-xl font-bold">Shareholder Value</h3>
          <RatingBadge rating={ratings?.dilution?.rating} />
        </div>
        <div className="space-y-10">
          <MetricBar label="Diluted Shares" value={latest?.dilution.diluted_shares} displayValue={fmt.shares(latest?.dilution.diluted_shares)} maxValue={Math.max(...filtered.map(d => d.dilution.diluted_shares)) * 1.05} color="bg-vi-accent" />
          <MetricBar label="Dilution %" value={latest?.dilution.dilution_pct} displayValue={`${latest?.dilution.dilution_pct}%`} maxValue={2} color="bg-vi-gold" />
        </div>
        <p className="mt-8 text-xs text-sand-500 dark:text-warm-300 leading-relaxed italic border-l-2 border-vi-sage pl-4">
          Share count changed {shareChange}% over {filtered.length} quarters — {parseFloat(shareChange) < 0 ? 'buybacks reducing float' : 'dilution increasing'}.
        </p>
      </div>

      <div className="col-span-12 lg:col-span-7">
        <DataTable columns={['Quarter', 'Basic Shares', 'Diluted Shares', 'Dilution']} rows={rows} />
      </div>
    </div>
  );
}

