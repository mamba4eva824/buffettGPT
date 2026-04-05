import { RatingBadge, Sparkline, useFilteredData } from './shared';
import { CATEGORIES, fmt } from './mockData';

const SCORECARD_CONFIG = {
  growth: {
    sparklineFn: (q) => q.revenue_profit.revenue,
    sparklineColor: '#a0d6ad',
    metrics: [
      { label: 'Revenue YoY', valueFn: (q) => q.revenue_profit.revenue_growth_yoy, format: 'pctSigned' },
      { label: 'EPS YoY', valueFn: (q) => q.revenue_profit.eps_growth_yoy, format: 'pctSigned' },
    ],
  },
  profitability: {
    sparklineFn: (q) => q.revenue_profit.operating_margin,
    sparklineColor: '#f2c35b',
    metrics: [
      { label: 'Op. Margin', valueFn: (q) => q.revenue_profit.operating_margin, format: 'pct' },
      { label: 'ROE', valueFn: (q) => q.revenue_profit.roe, format: 'pct' },
    ],
  },
  valuation: {
    sparklineFn: (q) => q.valuation.pe_ratio,
    sparklineColor: '#6d28d9',
    metrics: [
      { label: 'P/E', valueFn: (q) => q.valuation.pe_ratio, format: 'x' },
      { label: 'Earn. Yield', valueFn: (q) => q.valuation.earnings_yield, format: 'pct' },
    ],
  },
  cashflow: {
    sparklineFn: (q) => q.cashflow.free_cash_flow,
    sparklineColor: '#a0d6ad',
    metrics: [
      { label: 'FCF Margin', valueFn: (q) => q.cashflow.fcf_margin, format: 'pct' },
      { label: 'FCF YoY', valueFn: (q) => q.cashflow.fcf_change_yoy, format: 'pctSigned' },
    ],
  },
  debt: {
    sparklineFn: (q) => q.debt_leverage.debt_to_equity,
    sparklineColor: '#ffb4ab',
    metrics: [
      { label: 'D/E Ratio', valueFn: (q) => q.debt_leverage.debt_to_equity, format: 'ratio' },
      { label: 'Interest Cov.', valueFn: (q) => q.debt_leverage.interest_coverage, format: 'x' },
    ],
  },
  earnings_quality: {
    sparklineFn: (q) => q.earnings_quality.sbc_to_revenue_pct,
    sparklineColor: '#f2c35b',
    metrics: [
      { label: 'SBC/Revenue', valueFn: (q) => q.earnings_quality.sbc_to_revenue_pct, format: 'pct' },
      { label: 'GAAP Gap', valueFn: (q) => q.earnings_quality.gaap_adjusted_gap_pct, format: 'pct' },
    ],
  },
  moat: {
    sparklineFn: (q) => q.valuation.roic,
    sparklineColor: '#6d28d9',
    metrics: [
      { label: 'ROIC', valueFn: (q) => q.valuation.roic, format: 'pct' },
      { label: 'Gross Margin', valueFn: (q) => q.revenue_profit.gross_margin, format: 'pct' },
    ],
  },
};

const FORMAT_MAP = {
  pct: fmt.pct,
  pctSigned: fmt.pctSigned,
  ratio: fmt.ratio,
  x: fmt.x,
  billions: fmt.billions,
};

function metricColor(value, format) {
  if (value == null) return 'text-sand-600 dark:text-warm-200';
  if (format === 'pctSigned') {
    if (value > 0) return 'text-vi-sage';
    if (value < 0) return 'text-vi-rose';
    return 'text-vi-gold';
  }
  return 'text-sand-800 dark:text-warm-50';
}

// One-line insight per category for the scorecard
const SCORECARD_INSIGHTS = {
  growth: (latest) => {
    const g = latest?.revenue_profit?.revenue_growth_yoy;
    if (g == null) return null;
    return g > 0.1 ? 'Strong revenue momentum' : g > 0 ? 'Modest growth trajectory' : 'Revenue under pressure';
  },
  profitability: (latest) => {
    const m = latest?.revenue_profit?.operating_margin;
    if (m == null) return null;
    return m > 0.25 ? 'High-margin business model' : m > 0.15 ? 'Healthy operating margins' : 'Margins need monitoring';
  },
  valuation: (latest) => {
    const pe = latest?.valuation?.pe_ratio;
    if (pe == null) return null;
    return pe > 35 ? 'Premium valuation — growth priced in' : pe > 20 ? 'Moderately valued' : 'Attractively priced relative to earnings';
  },
  cashflow: (latest) => {
    const fcf = latest?.cashflow?.fcf_margin;
    if (fcf == null) return null;
    return fcf > 0.25 ? 'Exceptional cash generation' : fcf > 0.15 ? 'Solid free cash flow' : 'Cash flow could improve';
  },
  debt: (latest) => {
    const de = latest?.debt_leverage?.debt_to_equity;
    if (de == null) return null;
    return de < 0.5 ? 'Conservative balance sheet' : de < 1.5 ? 'Moderate leverage' : 'Elevated debt levels';
  },
  earnings_quality: (latest) => {
    const sbc = latest?.earnings_quality?.sbc_to_revenue_pct;
    if (sbc == null) return null;
    return sbc < 0.03 ? 'High-quality earnings' : sbc < 0.08 ? 'Moderate SBC dilution' : 'Significant SBC cost';
  },
  moat: (latest) => {
    const roic = latest?.valuation?.roic;
    if (roic == null) return null;
    const spread = roic - 0.10;
    return spread > 0.15 ? 'Wide moat — exceptional returns on capital' : spread > 0.05 ? 'Narrow moat — above cost of capital' : spread > 0 ? 'Thin moat — marginally above cost of capital' : 'No moat signal — below cost of capital';
  },
};

// Count ratings by type for the health summary
function ratingCounts(ratings) {
  let strong = 0, moderate = 0, weak = 0;
  for (const key of ['growth', 'profitability', 'valuation', 'cashflow', 'debt', 'earnings_quality', 'moat']) {
    const r = ratings?.[key]?.rating;
    if (r === 'Strong') strong++;
    else if (r === 'Moderate') moderate++;
    else if (r === 'Weak') weak++;
  }
  return { strong, moderate, weak };
}

export default function ExecutiveDashboard({ data, ratings, latestPrice, timeRange, onSelectCategory }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered.length > 0 ? filtered[filtered.length - 1] : null;
  const categories = CATEGORIES.filter((c) => c.id !== 'dashboard');
  const counts = ratingCounts(ratings);

  // Health summary sentence
  const healthSummary = counts.strong + counts.moderate + counts.weak > 0
    ? counts.strong >= 4
      ? 'Fundamentals are strong across most categories — a well-rounded financial profile.'
      : counts.weak >= 2
        ? 'Several areas show weakness — worth investigating the underlying trends before drawing conclusions.'
        : 'A mixed financial profile with areas of strength and areas to watch.'
    : null;

  return (
    <div className="space-y-6">
      {/* Company Health Summary */}
      <div className="bg-sand-100 dark:bg-warm-900 rounded-xl p-6 md:p-8 border border-sand-200/50 dark:border-warm-700/50">
        <div className="flex flex-wrap items-center gap-4 mb-4">
          {latest?.ticker && (
            <span className="text-2xl font-serif font-bold text-vi-gold">{latest.ticker}</span>
          )}
          {latestPrice && (
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-serif font-bold text-sand-900 dark:text-warm-50">${latestPrice.price.toFixed(2)}</span>
              {latestPrice.date && (
                <span className="text-[11px] text-sand-400 dark:text-warm-500">as of {latestPrice.date}</span>
              )}
            </div>
          )}
          <div className="flex items-center gap-2 ml-auto">
            {counts.strong > 0 && <span className="text-xs font-bold px-2 py-1 rounded bg-vi-sage/15 text-vi-sage">{counts.strong} Strong</span>}
            {counts.moderate > 0 && <span className="text-xs font-bold px-2 py-1 rounded bg-vi-gold/15 text-vi-gold">{counts.moderate} Moderate</span>}
            {counts.weak > 0 && <span className="text-xs font-bold px-2 py-1 rounded bg-vi-rose/15 text-vi-rose">{counts.weak} Weak</span>}
          </div>
        </div>
        {healthSummary && (
          <p className="text-sm text-sand-600 dark:text-warm-200 leading-relaxed">{healthSummary}</p>
        )}
      </div>

      {/* Category Scorecards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-6">
        {categories.map((cat) => {
          const config = SCORECARD_CONFIG[cat.id];
          const catRating = ratings?.[cat.id];
          if (!config) return null;

          const sparklineData = filtered.map(config.sparklineFn).filter((v) => v != null);
          const insight = SCORECARD_INSIGHTS[cat.id]?.(latest);

          return (
            <div
              key={cat.id}
              className="bg-sand-100 dark:bg-warm-900 rounded-xl p-5 md:p-6 cursor-pointer hover:ring-2 hover:ring-vi-gold/50 transition-all relative overflow-hidden group"
              onClick={() => onSelectCategory(cat.id)}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-vi-gold text-xl">{cat.icon}</span>
                  <h3 className="font-serif font-bold text-sand-800 dark:text-warm-50">{cat.label}</h3>
                </div>
                {catRating && <RatingBadge rating={catRating.rating} />}
              </div>

              {/* One-line insight */}
              {insight && (
                <p className="text-xs text-sand-500 dark:text-warm-400 mb-3 italic">{insight}</p>
              )}

              {/* Metrics */}
              <div className="space-y-2">
                {config.metrics.map((m) => {
                  const value = latest ? m.valueFn(latest) : null;
                  const formatFn = FORMAT_MAP[m.format] || fmt.pct;
                  const color = metricColor(value, m.format);
                  return (
                    <div key={m.label} className="flex justify-between items-center">
                      <span className="text-[11px] font-semibold text-sand-500 dark:text-warm-300">{m.label}</span>
                      <span className={`text-sm font-bold ${color}`}>{formatFn(value)}</span>
                    </div>
                  );
                })}
              </div>

              {/* Sparkline */}
              {sparklineData.length > 1 && (
                <Sparkline data={sparklineData} color={config.sparklineColor} width={80} height={24} />
              )}

              {/* Click hint */}
              <div className="absolute bottom-2 right-3 text-[10px] text-sand-400 dark:text-warm-500 opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1">
                <span>Explore</span>
                <span className="material-symbols-outlined text-[14px]">arrow_forward</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
