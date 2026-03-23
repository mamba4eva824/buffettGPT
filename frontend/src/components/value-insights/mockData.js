// Real AAPL data from metrics-history-dev DynamoDB, normalized for the dashboard.
// When the API is wired up, this file will be replaced by a fetch call.

import { AAPL_QUARTERS } from './aaplData';

// Normalize DynamoDB schema → dashboard schema
// DynamoDB stores margins as percentages (39.8), dashboard expects decimals (0.398)
function normalizeQuarter(q) {
  return {
    ticker: q.ticker,
    fiscal_date: q.fiscal_date,
    fiscal_year: Math.round(q.fiscal_year),
    fiscal_quarter: q.fiscal_quarter,
    currency: q.currency,
    revenue_profit: {
      revenue: q.revenue_profit.revenue,
      net_income: q.revenue_profit.net_income,
      gross_profit: q.revenue_profit.gross_profit,
      operating_income: q.revenue_profit.operating_income,
      ebitda: q.revenue_profit.ebitda,
      gross_margin: q.revenue_profit.gross_margin / 100,
      operating_margin: q.revenue_profit.operating_margin / 100,
      net_margin: q.revenue_profit.net_margin / 100,
      eps: q.revenue_profit.eps,
      roe: q.revenue_profit.roe / 100,
      // revenue_growth_yoy computed below
    },
    cashflow: {
      operating_cash_flow: q.cashflow.operating_cash_flow,
      free_cash_flow: q.cashflow.free_cash_flow,
      fcf_margin: q.cashflow.fcf_margin / 100,
      capex: q.cashflow.capex,
      capex_intensity: q.cashflow.capex_intensity / 100,
      ocf_to_revenue: q.cashflow.ocf_to_revenue / 100,
      fcf_to_net_income: q.cashflow.fcf_to_net_income,
      fcf_payout_ratio: q.cashflow.fcf_payout_ratio / 100,
      reinvestment_rate: q.cashflow.reinvestment_rate / 100,
      share_buybacks: q.cashflow.share_buybacks,
      dividends_paid: q.cashflow.dividends_paid,
    },
    balance_sheet: {
      total_debt: q.balance_sheet.total_debt,
      cash_position: q.balance_sheet.cash_position,
      net_debt: q.balance_sheet.net_debt,
      total_equity: q.balance_sheet.total_equity,
      long_term_debt: q.balance_sheet.long_term_debt,
      short_term_debt: q.balance_sheet.short_term_debt,
      working_capital: q.balance_sheet.working_capital,
    },
    debt_leverage: {
      debt_to_equity: q.debt_leverage.debt_to_equity,
      interest_coverage: q.debt_leverage.interest_coverage,
      current_ratio: q.debt_leverage.current_ratio,
      quick_ratio: q.debt_leverage.quick_ratio,
      debt_to_assets: q.debt_leverage.debt_to_assets,
      net_debt_to_ebitda: q.debt_leverage.net_debt_to_ebitda,
      fcf_to_debt: q.debt_leverage.fcf_to_debt,
      interest_expense: q.debt_leverage.interest_expense,
    },
    earnings_quality: {
      gaap_net_income: q.earnings_quality.gaap_net_income,
      sbc_actual: q.earnings_quality.sbc_actual,
      sbc_to_revenue_pct: q.earnings_quality.sbc_to_revenue_pct / 100,
      adjusted_earnings: q.earnings_quality.adjusted_earnings,
      d_and_a: q.earnings_quality.d_and_a,
      gaap_adjusted_gap_pct: q.earnings_quality.gaap_adjusted_gap_pct / 100,
    },
    dilution: {
      basic_shares: q.dilution.basic_shares,
      diluted_shares: q.dilution.diluted_shares,
      dilution_pct: q.dilution.dilution_pct,
      share_buybacks: q.dilution.share_buybacks,
    },
    valuation: {
      roe: q.valuation.roe / 100,
      roic: q.valuation.roic / 100,
      roa: q.valuation.roa / 100,
      asset_turnover: q.valuation.asset_turnover,
      equity_multiplier: q.valuation.equity_multiplier,
    },
  };
}

// Normalize and sort chronologically
const normalized = AAPL_QUARTERS
  .map(normalizeQuarter)
  .sort((a, b) => a.fiscal_date.localeCompare(b.fiscal_date));

// Helper: safe YoY growth = (current - prior) / |prior|, or null
function yoyGrowth(current, prior) {
  if (current == null || prior == null || prior === 0) return null;
  return (current - prior) / Math.abs(prior);
}

// Compute all YoY / QoQ growth fields by matching same fiscal_quarter from prior year
function computeGrowthFields(quarters) {
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

export const MOCK_QUARTERS = computeGrowthFields(normalized);

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
