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
    sparklineFn: (q) => q.valuation.roic,
    sparklineColor: '#6d28d9',
    metrics: [
      { label: 'ROIC', valueFn: (q) => q.valuation.roic, format: 'pct' },
      { label: 'ROA', valueFn: (q) => q.valuation.roa, format: 'pct' },
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
  dilution: {
    sparklineFn: (q) => q.dilution.diluted_shares,
    sparklineColor: '#6d28d9',
    metrics: [
      { label: 'Dilution', valueFn: (q) => q.dilution.dilution_pct, format: 'pct' },
      { label: 'Buybacks', valueFn: (q) => q.dilution.share_buybacks, format: 'billions' },
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

function VerdictBadge({ verdict }) {
  const colors = {
    BUY: 'bg-vi-sage/20 text-vi-sage border-vi-sage/30',
    HOLD: 'bg-vi-gold/20 text-vi-gold border-vi-gold/30',
    SELL: 'bg-vi-rose/20 text-vi-rose border-vi-rose/30',
  };
  const cls = colors[verdict] || colors.HOLD;
  return (
    <span className={`px-5 py-2 rounded-lg text-2xl font-bold uppercase tracking-widest border ${cls}`}>
      {verdict}
    </span>
  );
}

export default function ExecutiveDashboard({ data, ratings, timeRange, onSelectCategory }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered.length > 0 ? filtered[filtered.length - 1] : null;
  const categories = CATEGORIES.filter((c) => c.id !== 'dashboard');

  return (
    <div className="space-y-6">
      {/* Verdict Header Card */}
      <div className="bg-sand-100 dark:bg-warm-900 rounded-xl p-8 md:p-10 text-center border border-sand-200/50 dark:border-warm-700/50">
        <p className="text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 mb-4">
          Overall Verdict
        </p>
        <div className="flex items-center justify-center gap-4 mb-3">
          <VerdictBadge verdict={ratings?.overall_verdict} />
        </div>
        <p className="text-sm font-semibold text-sand-500 dark:text-warm-300">
          Conviction: <span className="text-sand-800 dark:text-warm-50">{ratings?.conviction}</span>
        </p>
      </div>

      {/* Category Scorecards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 md:gap-6">
        {categories.map((cat) => {
          const config = SCORECARD_CONFIG[cat.id];
          const catRating = ratings?.[cat.id];
          if (!config) return null;

          const sparklineData = filtered.map(config.sparklineFn).filter((v) => v != null);

          return (
            <div
              key={cat.id}
              className="bg-sand-100 dark:bg-warm-900 rounded-xl p-5 md:p-6 cursor-pointer hover:ring-2 hover:ring-vi-gold/50 transition-all relative overflow-hidden"
              onClick={() => onSelectCategory(cat.id)}
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-vi-gold text-xl">{cat.icon}</span>
                  <h3 className="font-serif font-bold text-sand-800 dark:text-warm-50">{cat.label}</h3>
                </div>
                {catRating && <RatingBadge rating={catRating.rating} />}
              </div>

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
            </div>
          );
        })}
      </div>
    </div>
  );
}
