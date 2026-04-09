import { useMemo, useState, useRef } from 'react';

// Shared sub-components for Value Insights panels

// Hover tooltip for explaining financial metrics in plain language
export function MetricTooltip({ tip, children }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = useRef(null);
  if (!tip) return children;
  const handleEnter = () => {
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      const spaceAbove = rect.top;
      const showBelow = spaceAbove < 120;
      setPos({
        top: showBelow ? rect.bottom + 6 : rect.top - 6,
        left: Math.min(rect.left, window.innerWidth - 300),
        below: showBelow,
      });
    }
    setShow(true);
  };
  return (
    <span ref={ref} className="relative inline-flex items-center gap-1 cursor-help" onMouseEnter={handleEnter} onMouseLeave={() => setShow(false)}>
      {children}
      <span className="material-symbols-outlined text-[14px] text-sand-400 dark:text-warm-500 hover:text-vi-gold transition-colors">info</span>
      {show && (
        <span
          className="fixed z-50 w-72 bg-sand-50 dark:bg-warm-900 border border-sand-200 dark:border-warm-700 rounded-lg shadow-xl px-4 py-3 text-xs leading-relaxed pointer-events-none text-sand-600 dark:text-warm-200 font-normal normal-case tracking-normal"
          style={{ top: pos.below ? pos.top : undefined, bottom: pos.below ? undefined : `${window.innerHeight - pos.top}px`, left: pos.left }}
        >
          {tip}
        </span>
      )}
    </span>
  );
}

export function MetricBar({ label, value, displayValue, maxValue = 1, color = 'bg-vi-accent', tip }) {
  const width = Math.min((value / maxValue) * 100, 100);
  const labelEl = <span className="text-sm font-semibold text-sand-600 dark:text-warm-200">{label}</span>;
  return (
    <div>
      <div className="flex justify-between items-end mb-2">
        {tip ? <MetricTooltip tip={tip}>{labelEl}</MetricTooltip> : labelEl}
        <span className="text-lg font-bold text-vi-accent">{displayValue}</span>
      </div>
      <div className="h-4 bg-sand-200 dark:bg-warm-800 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all duration-700`} style={{ width: `${width}%` }} />
      </div>
    </div>
  );
}

export function DataTable({ columns, rows }) {
  return (
    <div className="bg-sand-100 dark:bg-warm-900 rounded-xl overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-sand-200/50 dark:bg-warm-800/50">
              {columns.map((col, i) => (
                <th key={i} className={`px-8 py-4 text-[10px] font-bold uppercase tracking-widest text-sand-500 dark:text-warm-300 ${i === columns.length - 1 ? 'text-right' : ''}`}>
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-sand-200/50 dark:divide-warm-800/50">
            {rows.map((row, i) => (
              <tr key={i} className={`hover:bg-sand-200/50 dark:hover:bg-warm-800 transition-colors ${i % 2 === 1 ? 'bg-sand-50 dark:bg-warm-950/50' : ''}`}>
                {row.map((cell, j) => (
                  <td key={j} className={`px-8 py-5 font-medium ${j === 0 ? 'font-bold text-sand-800 dark:text-warm-50' : ''} ${j === row.length - 1 ? 'text-right' : ''} ${typeof cell === 'string' && cell.startsWith('-') ? 'text-vi-rose' : j > 0 ? 'text-sand-600 dark:text-warm-200' : ''}`}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function RatingBadge({ rating }) {
  const colors = {
    Strong: 'bg-vi-sage/20 text-vi-sage',
    Moderate: 'bg-vi-gold/20 text-vi-gold',
    Weak: 'bg-vi-rose/20 text-vi-rose',
  };
  const cls = colors[rating] || colors.Moderate;
  return (
    <span className={`px-3 py-1 rounded text-[10px] font-bold uppercase tracking-widest ${cls}`}>
      {rating}
    </span>
  );
}

export const CARD = "bg-sand-100 dark:bg-warm-900 rounded-xl p-8";

// QoQ delta chip — small inline arrow showing quarter-over-quarter change
export function DeltaChip({ value }) {
  if (value == null) return null;
  const isPositive = value >= 0;
  const color = isPositive ? 'text-vi-sage' : 'text-vi-rose';
  const arrow = isPositive ? 'arrow_upward' : 'arrow_downward';
  return (
    <span className={`inline-flex items-center ml-1.5 text-[10px] ${color}`}>
      <span className="material-symbols-outlined text-[12px]">{arrow}</span>
      {Math.abs(value * 100).toFixed(0)}%
    </span>
  );
}

// Bento tile with optional sparkline or icon
export function BentoTile({ label, value, sparkline, color, icon, tip }) {
  const labelEl = <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400">{label}</span>;
  return (
    <div className={`${CARD} !p-4 relative`}>
      <div className="mb-1">{tip ? <MetricTooltip tip={tip}>{labelEl}</MetricTooltip> : labelEl}</div>
      <div className="text-2xl font-serif text-sand-900 dark:text-warm-50">{value}</div>
      {sparkline && sparkline.length > 1 && (
        <Sparkline data={sparkline} color={color} />
      )}
      {icon && (
        <span className="absolute right-3 bottom-2 material-symbols-outlined text-3xl text-sand-300 dark:text-warm-700 opacity-50">{icon}</span>
      )}
    </div>
  );
}

// Tiny inline sparkline SVG
export function Sparkline({ data, color = '#a0d6ad', width = 80, height = 24 }) {
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg className="absolute right-3 bottom-3 opacity-40" width={width} height={height}>
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Growth chart — actual values as solid line with rolling 4Q average dashed overlay
// Interactive: hover crosshair + tooltip showing quarter, value, and rolling avg
// refLine: optional { value, label, color } to draw a horizontal reference line (e.g., sector median)
export function CagrChart({ data, quarters, cagr, label, color, formatFn, summaryLabel, refLine }) {
  const [hoveredIdx, setHoveredIdx] = useState(null);

  if (!data || data.length < 2 || cagr == null) return null;

  const W = 320;
  const H = 150;
  const PAD = { top: 8, right: 12, bottom: 28, left: 42 };
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;

  // Rolling 4Q average — compute before min/max so trendline is included in scale
  const rolling4Q = data.map((_, i) => {
    if (i < 3) return null; // need 4 quarters
    return (data[i] + data[i - 1] + data[i - 2] + data[i - 3]) / 4;
  });
  const rollingValid = rolling4Q.filter(v => v != null);

  // Min/max across both actual, rolling, and reference line to keep them on the same scale.
  // Filter non-finite values, then clamp outliers so one extreme quarter can't compress
  // the entire chart into a flat line (e.g., ROIC = -875158% during COVID).
  const validData = data.filter(v => v != null && isFinite(v));
  const allVals = [...validData, ...rollingValid];
  if (refLine?.value != null) allVals.push(refLine.value);

  let min = Math.min(...allVals);
  let max = Math.max(...allVals);

  // Use 2nd-smallest/2nd-largest as anchors with 2x inner-range padding
  // to prevent a single extreme outlier from dominating the Y-axis
  if (validData.length >= 4) {
    const sorted = [...validData].sort((a, b) => a - b);
    const lo = sorted[1];
    const hi = sorted[sorted.length - 2];
    const inner = hi - lo;
    if (inner > 0) {
      min = Math.max(min, lo - inner * 2);
      max = Math.min(max, hi + inner * 2);
    }
  }

  const range = max - min || 1;

  const toX = (i) => PAD.left + (i / (data.length - 1)) * plotW;
  const toY = (v) => PAD.top + plotH - ((v - min) / range) * plotH;

  // Actual data polyline
  const actualPoints = data.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');

  // Rolling 4Q average polyline (starts at index 3)
  const rollingPoints = rolling4Q
    .map((v, i) => (v != null ? `${toX(i)},${toY(v)}` : null))
    .filter(Boolean)
    .join(' ');

  // Y-axis tick values (3 ticks)
  const yTicks = [min, min + range / 2, max];

  // X-axis year labels — show a tick at the first quarter of each fiscal year
  const xLabels = [];
  if (quarters && quarters.length === data.length) {
    const seenYears = new Set();
    quarters.forEach((q, i) => {
      const yr = q.fiscal_year;
      if (!seenYears.has(yr)) {
        seenYears.add(yr);
        xLabels.push({ index: i, label: String(yr) });
      }
    });
  }

  // Mouse tracking: map client coords to nearest data point index
  const handleMouseMove = (e) => {
    const svgEl = e.currentTarget;
    const rect = svgEl.getBoundingClientRect();
    const mouseX = ((e.clientX - rect.left) / rect.width) * W;

    if (mouseX < PAD.left || mouseX > W - PAD.right) {
      setHoveredIdx(null);
      return;
    }

    let nearest = 0;
    let minDist = Infinity;
    for (let i = 0; i < data.length; i++) {
      const dist = Math.abs(mouseX - toX(i));
      if (dist < minDist) {
        minDist = dist;
        nearest = i;
      }
    }
    setHoveredIdx(nearest);
  };

  const hq = hoveredIdx != null ? quarters?.[hoveredIdx] : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400">{label}</span>
        <span className="text-xs font-bold" style={{ color }}>{summaryLabel || `CAGR ${(cagr * 100).toFixed(1)}%`}</span>
      </div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="w-full cursor-crosshair"
          preserveAspectRatio="xMidYMid meet"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredIdx(null)}
        >
          {/* Horizontal grid lines + Y-axis labels */}
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={PAD.left} y1={toY(tick)} x2={W - PAD.right} y2={toY(tick)}
                stroke="currentColor" strokeWidth="0.5" className="text-sand-200 dark:text-warm-700"
              />
              <text x={PAD.left - 4} y={toY(tick) + 3} textAnchor="end" className="text-sand-400 dark:text-warm-500 fill-current" fontSize="8">
                {formatFn(tick)}
              </text>
            </g>
          ))}
          {/* X-axis year labels + vertical tick marks */}
          {xLabels.map(({ index, label: yr }) => (
            <g key={yr}>
              <line
                x1={toX(index)} y1={PAD.top} x2={toX(index)} y2={PAD.top + plotH}
                stroke="currentColor" strokeWidth="0.3" className="text-sand-200 dark:text-warm-700"
              />
              <text
                x={toX(index)} y={PAD.top + plotH + 14}
                textAnchor="middle" className="text-sand-400 dark:text-warm-500 fill-current" fontSize="8"
              >
                {yr}
              </text>
            </g>
          ))}
          {/* Reference line (e.g., sector median) */}
          {refLine?.value != null && refLine.value >= min && refLine.value <= max && (
            <g>
              <line
                x1={PAD.left} y1={toY(refLine.value)} x2={W - PAD.right} y2={toY(refLine.value)}
                stroke={refLine.color || '#6d28d9'} strokeWidth="1" strokeDasharray="6 3" opacity="0.5"
              />
              <text
                x={W - PAD.right + 2} y={toY(refLine.value) + 3}
                fill={refLine.color || '#6d28d9'} fontSize="7" opacity="0.7"
              >
                {refLine.label || ''}
              </text>
            </g>
          )}
          {/* Rolling 4Q average (dashed) */}
          {rollingPoints && (
            <polyline points={rollingPoints} fill="none" stroke={color} strokeWidth="1.5" strokeDasharray="4 3" opacity="0.5" />
          )}
          {/* Actual values (solid) */}
          <polyline points={actualPoints} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          {/* Data points */}
          {data.map((v, i) => (
            <circle key={i} cx={toX(i)} cy={toY(v)} r="2.5" fill={color} opacity={hoveredIdx != null && hoveredIdx !== i ? 0.3 : 0.7} />
          ))}
          {/* Shaded area under actual line */}
          <polygon
            points={`${toX(0)},${toY(min)} ${actualPoints} ${toX(data.length - 1)},${toY(min)}`}
            fill={color} opacity="0.06"
          />
          {/* Crosshair + highlighted points on hover */}
          {hoveredIdx != null && (
            <>
              <line
                x1={toX(hoveredIdx)} y1={PAD.top} x2={toX(hoveredIdx)} y2={PAD.top + plotH}
                stroke={color} strokeWidth="0.5" strokeDasharray="3 2" opacity="0.4"
              />
              <circle cx={toX(hoveredIdx)} cy={toY(data[hoveredIdx])} r="4.5" fill={color} stroke="white" strokeWidth="1.5" />
              {rolling4Q[hoveredIdx] != null && (
                <circle cx={toX(hoveredIdx)} cy={toY(rolling4Q[hoveredIdx])} r="3" fill={color} opacity="0.5" stroke="white" strokeWidth="1" />
              )}
            </>
          )}
        </svg>

        {/* Floating tooltip */}
        {hoveredIdx != null && hq && (
          <div
            className="absolute z-20 pointer-events-none"
            style={{
              left: `${(toX(hoveredIdx) / W) * 100}%`,
              top: `${(toY(data[hoveredIdx]) / H) * 100}%`,
              transform: 'translate(-50%, -100%) translateY(-6px)',
            }}
          >
            <div className="bg-sand-100 dark:bg-warm-900 px-2.5 py-1.5 rounded shadow-lg border border-sand-200 dark:border-warm-700 text-[10px] font-mono text-sand-600 dark:text-warm-200 whitespace-nowrap">
              <div className="font-bold text-sand-800 dark:text-warm-50">{hq.fiscal_quarter} {hq.fiscal_year}</div>
              <div style={{ color }}>{formatFn(data[hoveredIdx])}</div>
              {rolling4Q[hoveredIdx] != null && (
                <div className="text-sand-400 dark:text-warm-500">4Q Avg: {formatFn(rolling4Q[hoveredIdx])}</div>
              )}
              {refLine?.value != null && (
                <div style={{ color: refLine.color || '#6d28d9' }}>{refLine.label}: {formatFn(refLine.value)}</div>
              )}
            </div>
          </div>
        )}
      </div>
      <div className="flex justify-center mt-1">
        <div className="flex items-center gap-3 text-[9px] text-sand-400 dark:text-warm-500">
          <span className="flex items-center gap-1"><span className="inline-block w-3 border-t-2" style={{ borderColor: color }} />Quarterly</span>
          <span className="flex items-center gap-1"><span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: color, opacity: 0.5 }} />4Q Avg</span>
          {refLine?.label && <span className="flex items-center gap-1"><span className="inline-block w-3 border-t border-dashed" style={{ borderColor: refLine.color || '#6d28d9', opacity: 0.5 }} />{refLine.label}</span>}
        </div>
      </div>
    </div>
  );
}

// DuPont block sub-component
export function DuPontBlock({ label, value, color, highlight }) {
  return (
    <div className={`${highlight ? CARD + ' !p-4 border-2 border-vi-gold/30' : CARD + ' !p-4'}`}>
      <div className="text-[10px] uppercase font-bold text-sand-500 dark:text-warm-400 mb-1">{label}</div>
      <div className={`text-2xl font-serif font-bold ${color}`}>{value}</div>
    </div>
  );
}

// Hook to filter data by time range
// eslint-disable-next-line react-refresh/only-export-components
export const useFilteredData = (data, timeRange) => {
  return useMemo(() => {
    if (!data?.length) return [];
    const sorted = [...data].sort((a, b) => a.fiscal_date.localeCompare(b.fiscal_date));
    const quarterCount = { '5Y': 20, '3Y': 12, '1Y': 4 };
    const count = quarterCount[timeRange] || 20;
    return sorted.slice(-count);
  }, [data, timeRange]);
};
