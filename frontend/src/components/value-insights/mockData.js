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

// MOCK: Replace with real stock prices from DynamoDB when available
// Approximate AAPL closing prices at each fiscal quarter-end
const MOCK_STOCK_PRICES = {
  '2020-12-26': 131.97,
  '2021-03-27': 121.21,
  '2021-06-26': 136.96,
  '2021-09-25': 141.91,
  '2021-12-25': 179.45,
  '2022-03-26': 174.61,
  '2022-06-25': 141.66,
  '2022-09-24': 150.43,
  '2022-12-31': 129.93,
  '2023-04-01': 164.90,
  '2023-07-01': 193.97,
  '2023-09-30': 171.21,
  '2023-12-30': 192.53,
  '2024-03-30': 171.48,
  '2024-06-29': 210.62,
  '2024-09-28': 227.52,
  '2024-12-28': 259.02,
  '2025-03-29': 222.13,
  '2025-06-28': 214.24,
  '2025-09-27': 226.47,
  '2025-12-27': 258.20,
};

// Compute valuation multiples that require stock price (P/E, P/B, EV/EBITDA, P/FCF)
export function computeValuationMultiples(quarters) {
  for (let i = 0; i < quarters.length; i++) {
    const q = quarters[i];
    const price = MOCK_STOCK_PRICES[q.fiscal_date] ?? null;
    const val = q.valuation;
    val.stock_price = price;

    // TTM (trailing twelve months) requires 4 quarters of history
    if (i < 3 || price == null) {
      val.ttm_eps = null;
      val.pe_ratio = null;
      val.earnings_yield = null;
      val.book_value_per_share = null;
      val.pb_ratio = null;
      val.ttm_ebitda = null;
      val.enterprise_value = null;
      val.ev_ebitda = null;
      val.ttm_fcf = null;
      val.fcf_per_share = null;
      val.price_to_fcf = null;
      val.market_cap = null;
      val.fcf_yield = null;
      continue;
    }

    const last4 = quarters.slice(i - 3, i + 1);
    const dilutedShares = q.dilution.diluted_shares;

    // TTM EPS & P/E
    val.ttm_eps = last4.reduce((sum, qq) => sum + qq.revenue_profit.eps, 0);
    val.pe_ratio = val.ttm_eps > 0 ? price / val.ttm_eps : null;
    val.earnings_yield = val.ttm_eps > 0 ? val.ttm_eps / price : null;

    // Book value per share & P/B
    const totalEquity = q.balance_sheet.total_equity;
    val.book_value_per_share = dilutedShares > 0 ? totalEquity / dilutedShares : null;
    val.pb_ratio = val.book_value_per_share > 0 ? price / val.book_value_per_share : null;

    // EV/EBITDA
    val.market_cap = price * dilutedShares;
    val.ttm_ebitda = last4.reduce((sum, qq) => sum + qq.revenue_profit.ebitda, 0);
    val.enterprise_value = val.market_cap + q.balance_sheet.total_debt - q.balance_sheet.cash_position;
    val.ev_ebitda = val.ttm_ebitda > 0 ? val.enterprise_value / val.ttm_ebitda : null;

    // Price-to-FCF & FCF Yield
    val.ttm_fcf = last4.reduce((sum, qq) => sum + qq.cashflow.free_cash_flow, 0);
    val.fcf_per_share = dilutedShares > 0 ? val.ttm_fcf / dilutedShares : null;
    val.price_to_fcf = val.fcf_per_share > 0 ? price / val.fcf_per_share : null;
    val.fcf_yield = val.fcf_per_share > 0 ? val.fcf_per_share / price : null;
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
  dilution:         { rating: "Strong",   confidence: "High",   key_factors: ["Aggressive buyback program", "Share count declining 3% annually", "Dilution well below 1%"] },
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
  {
    id: 'dilution',
    label: 'Dilution',
    icon: 'group_add',
    title: 'Dilution Analysis',
    description: 'Share count trends and buyback effectiveness — is management creating or destroying value?',
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
