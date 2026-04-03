// Real AAPL data from metrics-history-dev DynamoDB, normalized for the dashboard.
// When the API is wired up, this file will be replaced by a fetch call.

import { AAPL_QUARTERS } from './aaplData';

// Normalize DynamoDB schema → dashboard schema
// DynamoDB stores margins as percentages (39.8), dashboard expects decimals (0.398)
// Helper: safe divide by 100 (null-safe for missing fields)
function pct(v) { return v != null ? v / 100 : null; }
function val(v) { return v ?? null; }

export function normalizeQuarter(q) {
  const rp = q.revenue_profit || {};
  const cf = q.cashflow || {};
  const bs = q.balance_sheet || {};
  const dl = q.debt_leverage || {};
  const eq = q.earnings_quality || {};
  const di = q.dilution || {};
  const va = q.valuation || {};

  return {
    ticker: q.ticker,
    fiscal_date: q.fiscal_date,
    fiscal_year: Math.round(q.fiscal_year),
    fiscal_quarter: q.fiscal_quarter,
    currency: q.currency,
    revenue_profit: {
      revenue: val(rp.revenue),
      net_income: val(rp.net_income),
      gross_profit: val(rp.gross_profit),
      operating_income: val(rp.operating_income),
      ebitda: val(rp.ebitda),
      gross_margin: pct(rp.gross_margin),
      operating_margin: pct(rp.operating_margin),
      net_margin: pct(rp.net_margin),
      eps: val(rp.eps),
      roe: pct(rp.roe),
    },
    cashflow: {
      operating_cash_flow: val(cf.operating_cash_flow),
      free_cash_flow: val(cf.free_cash_flow),
      fcf_margin: pct(cf.fcf_margin),
      capex: val(cf.capex),
      capex_intensity: pct(cf.capex_intensity),
      ocf_to_revenue: pct(cf.ocf_to_revenue),
      fcf_to_net_income: val(cf.fcf_to_net_income),
      fcf_payout_ratio: pct(cf.fcf_payout_ratio),
      reinvestment_rate: pct(cf.reinvestment_rate),
      share_buybacks: val(cf.share_buybacks),
      dividends_paid: val(cf.dividends_paid),
    },
    balance_sheet: {
      total_debt: val(bs.total_debt),
      cash_position: val(bs.cash_position),
      net_debt: val(bs.net_debt),
      total_equity: val(bs.total_equity),
      long_term_debt: val(bs.long_term_debt),
      short_term_debt: val(bs.short_term_debt),
      working_capital: val(bs.working_capital),
    },
    debt_leverage: {
      debt_to_equity: val(dl.debt_to_equity),
      interest_coverage: val(dl.interest_coverage),
      current_ratio: val(dl.current_ratio),
      quick_ratio: val(dl.quick_ratio),
      debt_to_assets: val(dl.debt_to_assets),
      net_debt_to_ebitda: val(dl.net_debt_to_ebitda),
      fcf_to_debt: val(dl.fcf_to_debt),
      interest_expense: val(dl.interest_expense),
    },
    earnings_quality: {
      gaap_net_income: val(eq.gaap_net_income),
      sbc_actual: val(eq.sbc_actual),
      sbc_to_revenue_pct: pct(eq.sbc_to_revenue_pct),
      adjusted_earnings: val(eq.adjusted_earnings),
      d_and_a: val(eq.d_and_a),
      gaap_adjusted_gap_pct: pct(eq.gaap_adjusted_gap_pct),
    },
    dilution: {
      basic_shares: val(di.basic_shares),
      diluted_shares: val(di.diluted_shares),
      dilution_pct: val(di.dilution_pct),
      share_buybacks: val(di.share_buybacks),
    },
    valuation: {
      roe: pct(va.roe),
      roic: pct(va.roic),
      roa: pct(va.roa),
      asset_turnover: val(va.asset_turnover),
      equity_multiplier: val(va.equity_multiplier),
    },
    // Pre-computed valuation ratios from FMP key-metrics (populated by sp500_backfill)
    market_valuation: q.market_valuation || null,
  };
}

// Normalize and sort chronologically
const normalized = AAPL_QUARTERS
  .map(normalizeQuarter)
  .sort((a, b) => a.fiscal_date.localeCompare(b.fiscal_date));

// Helper: safe YoY growth = (current - prior) / |prior|, or null
export function yoyGrowth(current, prior) {
  if (current == null || prior == null || prior === 0) return null;
  return (current - prior) / Math.abs(prior);
}

// Compute all YoY / QoQ growth fields by matching same fiscal_quarter from prior year
export function computeGrowthFields(quarters) {
  const byQY = {};
  for (const q of quarters) {
    byQY[`${q.fiscal_quarter}-${q.fiscal_year}`] = q;
  }

  for (let i = 0; i < quarters.length; i++) {
    const q = quarters[i];
    const prior = byQY[`${q.fiscal_quarter}-${q.fiscal_year - 1}`];
    const rp = q.revenue_profit;

    // --- Revenue YoY ---
    rp.revenue_growth_yoy = prior ? yoyGrowth(rp.revenue, prior.revenue_profit.revenue) : null;

    // --- EPS YoY ---
    rp.eps_growth_yoy = prior ? yoyGrowth(rp.eps, prior.revenue_profit.eps) : null;

    // --- Net Income YoY ---
    rp.net_income_growth_yoy = prior ? yoyGrowth(rp.net_income, prior.revenue_profit.net_income) : null;

    // --- Gross Profit YoY ---
    rp.gross_profit_growth_yoy = prior ? yoyGrowth(rp.gross_profit, prior.revenue_profit.gross_profit) : null;

    // --- Revenue QoQ (compare to previous quarter in sorted array) ---
    const prev = i > 0 ? quarters[i - 1] : null;
    rp.revenue_growth_qoq = prev ? yoyGrowth(rp.revenue, prev.revenue_profit.revenue) : null;

    // --- Margin changes (1yr, in percentage-point terms) ---
    if (prior) {
      rp.gross_margin_change_1yr = rp.gross_margin - prior.revenue_profit.gross_margin;
      rp.operating_margin_change_1yr = rp.operating_margin - prior.revenue_profit.operating_margin;
      rp.net_margin_change_1yr = rp.net_margin - prior.revenue_profit.net_margin;
      rp.is_margin_expanding = rp.operating_margin > prior.revenue_profit.operating_margin ? 1 : 0;
    } else {
      rp.gross_margin_change_1yr = null;
      rp.operating_margin_change_1yr = null;
      rp.net_margin_change_1yr = null;
      rp.is_margin_expanding = null;
    }

    // --- FCF YoY ---
    const cf = q.cashflow;
    cf.fcf_change_yoy = prior ? yoyGrowth(cf.free_cash_flow, prior.cashflow.free_cash_flow) : null;
  }

  return quarters;
}

// Merge pre-computed FMP valuation ratios (from market_valuation) into each quarter's
// valuation object.  Falls back to deriving P/B and stock_price from balance sheet +
// dilution data when possible.  No mock data — quarters without market_valuation get nulls.
export function computeValuationMultiples(quarters) {
  for (const q of quarters) {
    const v = q.valuation;
    const mv = q.market_valuation;
    const dilutedShares = q.dilution?.diluted_shares;
    const totalEquity = q.balance_sheet?.total_equity;

    if (mv && mv.pe_ratio != null) {
      // Use FMP pre-computed ratios (field-name mapping + unit conversion)
      v.pe_ratio = mv.pe_ratio;
      v.ev_ebitda = mv.ev_to_ebitda ?? null;
      v.earnings_yield = mv.earnings_yield != null ? mv.earnings_yield / 100 : null;
      v.fcf_yield = mv.fcf_yield != null ? mv.fcf_yield / 100 : null;
      v.market_cap = mv.market_cap ?? null;
      v.enterprise_value = mv.enterprise_value ?? null;

      // Derive price_to_fcf from fcf_yield (P/FCF ≈ 1 / fcf_yield)
      v.price_to_fcf = v.fcf_yield && v.fcf_yield > 0 ? 1 / v.fcf_yield : null;

      // Derive P/B from market_cap / total_equity
      v.pb_ratio = (v.market_cap && totalEquity && totalEquity > 0)
        ? v.market_cap / totalEquity : null;

      // Derive stock_price and book_value_per_share from per-share math
      v.stock_price = (v.market_cap && dilutedShares && dilutedShares > 0)
        ? v.market_cap / dilutedShares : null;
      v.book_value_per_share = (totalEquity && dilutedShares && dilutedShares > 0)
        ? totalEquity / dilutedShares : null;
    } else {
      // No market_valuation data — set all price-derived fields to null
      v.pe_ratio = null;
      v.earnings_yield = null;
      v.pb_ratio = null;
      v.ev_ebitda = null;
      v.price_to_fcf = null;
      v.fcf_yield = null;
      v.market_cap = null;
      v.enterprise_value = null;
      v.stock_price = null;
      v.book_value_per_share = (totalEquity && dilutedShares && dilutedShares > 0)
        ? totalEquity / dilutedShares : null;
    }
  }
  return quarters;
}

export const MOCK_QUARTERS = computeValuationMultiples(computeGrowthFields(normalized));

export const MOCK_RATINGS = {
  growth:           { rating: "Moderate", confidence: "Medium", key_factors: ["Revenue growth slowed to 2-5%", "Services segment driving growth", "iPhone cycle dependency"] },
  profitability:    { rating: "Strong",   confidence: "High",   key_factors: ["Gross margins expanding to 47%", "Operating leverage improving", "ROE consistently above 150%"] },
  valuation:        { rating: "Moderate", confidence: "Medium", key_factors: ["Premium multiple justified by quality", "FCF yield attractive", "Buybacks boosting per-share value"] },
  earnings_quality: { rating: "Strong",   confidence: "High",   key_factors: ["Low SBC relative to revenue", "Cash conversion excellent", "Minimal accounting adjustments"] },
  cashflow:         { rating: "Strong",   confidence: "High",   key_factors: ["FCF margin near 29%", "Capex declining as % of revenue", "Massive cash generation"] },
  debt:             { rating: "Moderate", confidence: "Medium", key_factors: ["D/E elevated but manageable", "Interest coverage strong at 29x", "Debt used for buybacks"] },
  overall_verdict: "BUY",
  conviction: "High"
};

export const CATEGORIES = [
  {
    id: 'dashboard',
    label: 'Overview',
    icon: 'dashboard',
    title: 'Executive Summary',
    description: 'A comprehensive overview of financial health across all categories.',
  },
  {
    id: 'growth',
    label: 'Growth',
    icon: 'trending_up',
    title: 'Growth Analysis',
    description: 'Revenue trajectory and earnings momentum over the last 5 years.',
  },
  {
    id: 'profitability',
    label: 'Profitability',
    icon: 'payments',
    title: 'Profitability Framework',
    description: 'Margin trends and operational efficiency through the lens of owner earnings.',
  },
  {
    id: 'valuation',
    label: 'Valuation',
    icon: 'analytics',
    title: 'Valuation Framework',
    description: 'Intrinsic value and capital allocation efficiency through the lens of concentrated value investing.',
  },
  {
    id: 'cashflow',
    label: 'Cash Flow',
    icon: 'savings',
    title: 'Cash Flow Deep Dive',
    description: 'Free cash flow generation and capital expenditure trends that reveal true earning power.',
  },
  {
    id: 'debt',
    label: 'Debt',
    icon: 'account_balance',
    title: 'Debt & Leverage',
    description: 'Balance sheet strength and leverage ratios that determine resilience in downturns.',
  },
  {
    id: 'earnings_quality',
    label: 'Earnings Quality',
    icon: 'verified',
    title: 'Earnings Quality',
    description: 'Real earnings power beyond GAAP — stock-based compensation and cash conversion analysis.',
  },
];

// Format helpers
export const fmt = {
  billions: (n) => {
    if (n == null) return '—';
    const abs = Math.abs(n);
    if (abs >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
    if (abs >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
    return `$${n.toLocaleString()}`;
  },
  pct: (n) => {
    if (n == null) return '—';
    return `${(n * 100).toFixed(1)}%`;
  },
  pctSigned: (n) => {
    if (n == null) return '—';
    const val = (n * 100).toFixed(1);
    return n >= 0 ? `+${val}%` : `${val}%`;
  },
  ratio: (n) => {
    if (n == null) return '—';
    return n.toFixed(2);
  },
  eps: (n) => {
    if (n == null) return '—';
    return `$${n.toFixed(2)}`;
  },
  shares: (n) => {
    if (n == null) return '—';
    return `${(n / 1e9).toFixed(2)}B`;
  },
  x: (n) => {
    if (n == null) return '—';
    return `${n.toFixed(1)}x`;
  },
  delta: (current, previous) => {
    if (current == null || previous == null || previous === 0) return null;
    return (current - previous) / Math.abs(previous);
  },
  // Percentage-point change (margins stored as decimals, display as pp)
  pctPts: (n) => {
    if (n == null) return '—';
    const val = (n * 100).toFixed(1);
    return n >= 0 ? `+${val}pp` : `${val}pp`;
  },
};
