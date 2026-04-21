import { fmt } from './mockData';
import { CARD, BentoTile, RatingBadge, useFilteredData } from './shared';

function classifyTrigger(text) {
  const lower = text.toLowerCase();
  if (lower.includes('buy') || lower.includes('accumulate') || lower.includes('add'))
    return { accent: 'border-l-vi-sage', bg: 'bg-vi-sage/5', icon: 'trending_up', iconColor: 'text-vi-sage' };
  if (lower.includes('sell') || lower.includes('exit') || lower.includes('reduce'))
    return { accent: 'border-l-vi-rose', bg: 'bg-vi-rose/5', icon: 'trending_down', iconColor: 'text-vi-rose' };
  return { accent: 'border-l-vi-gold', bg: 'bg-vi-gold/5', icon: 'pause_circle', iconColor: 'text-vi-gold' };
}

function parseTriggerItems(markdown) {
  if (!markdown) return [];
  const lines = markdown.split('\n').filter(l => l.trim());
  const items = [];
  let current = null;

  for (const line of lines) {
    const match = line.match(/^\d+\.\s+(.*)/);
    if (match) {
      if (current) items.push(current);
      current = match[1];
    } else if (current) {
      current += ' ' + line.trim();
    }
  }
  if (current) items.push(current);

  if (items.length === 0) {
    const paragraphs = markdown.split(/\n\n+/).filter(p => p.trim());
    return paragraphs.map(p => p.trim());
  }

  return items;
}

export default function DecisionTriggersPanel({ data, ratings, timeRange, triggers }) {
  const filtered = useFilteredData(data, timeRange);
  const latest = filtered[filtered.length - 1];

  const verdictColors = {
    BUY: 'text-vi-sage',
    SELL: 'text-vi-rose',
    HOLD: 'text-vi-gold',
  };
  const verdict = ratings?.overall_verdict;
  const conviction = ratings?.conviction;

  const peRatio = latest?.valuation?.pe_ratio;
  const fcfYield = latest?.valuation?.fcf_yield;
  const debtToEquity = latest?.debt_leverage?.debt_to_equity;
  const revGrowthYoY = latest?.revenue_profit?.revenue_growth_yoy;

  const triggerItems = parseTriggerItems(triggers);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
      {/* Left column */}
      <section className="xl:col-span-8 space-y-6">
        {/* Verdict card */}
        <div className={CARD}>
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50">Overall Verdict</h3>
            <RatingBadge rating={conviction === 'High' ? 'Strong' : conviction === 'Low' ? 'Weak' : 'Moderate'} />
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-4xl font-serif font-bold ${verdictColors[verdict] || 'text-sand-600 dark:text-warm-200'}`}>
              {verdict || '---'}
            </span>
            {conviction && (
              <span className="text-sm text-sand-500 dark:text-warm-400">
                {conviction} Conviction
              </span>
            )}
          </div>
        </div>

        {/* Triggers content */}
        <div className={CARD}>
          <h3 className="text-xl font-serif text-sand-800 dark:text-warm-50 mb-6">Decision Triggers</h3>
          {triggerItems.length > 0 ? (
            <div className="space-y-3">
              {triggerItems.map((item, i) => {
                const style = classifyTrigger(item);
                return (
                  <div
                    key={i}
                    className={`${style.bg} border-l-4 ${style.accent} rounded-r-lg p-4 flex items-start gap-3`}
                  >
                    <span className={`material-symbols-outlined text-xl mt-0.5 ${style.iconColor}`}>{style.icon}</span>
                    <p className="text-sm text-sand-700 dark:text-warm-200 leading-relaxed"
                       dangerouslySetInnerHTML={{ __html: item.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') }}
                    />
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-sand-400 dark:text-warm-500 text-sm">
              Decision triggers not yet available for this company.
            </p>
          )}
        </div>
      </section>

      {/* Right column — Key metrics */}
      <section className="xl:col-span-4 space-y-6">
        <div className={CARD}>
          <h4 className="text-[10px] uppercase font-bold tracking-widest text-sand-500 dark:text-warm-400 mb-4">Key Decision Metrics</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-1 gap-4">
            <BentoTile
              label="P/E Ratio"
              value={fmt.x(peRatio)}
              icon="analytics"
              tip="Price-to-Earnings ratio — how much investors pay per dollar of earnings"
            />
            <BentoTile
              label="FCF Yield"
              value={fmt.pct(fcfYield)}
              icon="savings"
              tip="Free cash flow yield — higher means more cash generated relative to price"
            />
            <BentoTile
              label="Debt / Equity"
              value={fmt.ratio(debtToEquity)}
              icon="account_balance"
              tip="Debt-to-equity ratio — lower means less financial leverage"
            />
            <BentoTile
              label="Revenue Growth YoY"
              value={fmt.pctSigned(revGrowthYoY)}
              icon="trending_up"
              tip="Year-over-year revenue growth for the most recent quarter"
            />
          </div>
        </div>
      </section>
    </div>
  );
}
