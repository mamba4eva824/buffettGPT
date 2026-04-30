s# Stitch Prompt: Buffett Value Insights Dashboard

## What I'm Building

A financial data visualization dashboard called **"Value Insights"** for an existing Warren Buffett-themed AI investment advisor app. The dashboard displays 5 years (20 quarters) of fundamental financial data in interactive charts and tables across 7 analytical categories. The ethos: **Buffett AI brings deep value insights to help users make more informed investment decisions, adopting Warren Buffett's long-term business analysis philosophy.**

The dashboard lives alongside an existing Chat interface. Users toggle between **"Chat"** and **"Value Insights"** using a centered slider/pill toggle at the top of the page.

---

## UI Layout

### Navigation
- Top center: **Pill toggle** with two options: `Chat` | `Value Insights`
- Default view: Chat (existing)
- When "Value Insights" is selected, the main content area swaps to the dashboard

### Value Insights Dashboard Layout
```
┌──────────────────────────────────────────────────────────┐
│  [Logo]     [ Chat | Value Insights ]        [Profile]   │
├──────────────────────────────────────────────────────────┤
│  🔍 Search ticker: [______AAPL______] [Analyze]         │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  COMPANY HEADER                                     │ │
│  │  Apple Inc (AAPL) · $182.52 · Overall: BUY (High)  │ │
│  │  Fiscal Year 2025 · Currency: USD                   │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Category Tabs ─────────────────────────────────────┐ │
│  │ Growth │ Profitability │ Valuation │ Cash Flow │     │ │
│  │ Debt │ Earnings Quality │ Dilution                  │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  ┌─ Active Category Panel ─────────────────────────────┐ │
│  │                                                     │ │
│  │  [Rating Badge: e.g. "Strong" / "Moderate" / "Weak"]│ │
│  │                                                     │ │
│  │  ┌─ Chart Area ──────────────────────────────────┐  │ │
│  │  │  Line/bar chart showing 20 quarters of data   │  │ │
│  │  │  Toggle: 5Y | 3Y | 1Y view                   │  │ │
│  │  │  Hover tooltips with exact values             │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  │                                                     │ │
│  │  ┌─ Data Table ──────────────────────────────────┐  │ │
│  │  │  Quarterly data in clean table format         │  │ │
│  │  │  Columns: Quarter | Metric1 | Metric2 | ...  │  │ │
│  │  │  Color-coded: green = improving, red = declining│ │
│  │  └───────────────────────────────────────────────┘  │ │
│  │                                                     │ │
│  │  ┌─ Buffett Insight Card ────────────────────────┐  │ │
│  │  │  "What would Buffett think?"                  │  │ │
│  │  │  Brief AI-generated insight about this metric │  │ │
│  │  └───────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## Data Model

The backend stores financial data in a DynamoDB table partitioned by ticker and fiscal quarter. Each item contains 7 metric categories. Here is the exact schema:

### DynamoDB Item (1 per quarter, ~20 items per ticker for 5 years)

```json
{
  "ticker": "AAPL",
  "fiscal_date": "2025-09-27",
  "fiscal_year": 2025,
  "fiscal_quarter": "Q4",

  "revenue_profit": {
    "revenue": 391035000000,
    "net_income": 93736000000,
    "gross_margin": 0.462,
    "operating_margin": 0.304,
    "net_margin": 0.24,
    "eps": 6.13,
    "revenue_growth_yoy": 0.02
  },

  "cashflow": {
    "operating_cash_flow": 118254000000,
    "free_cash_flow": 111443000000,
    "fcf_margin": 0.285,
    "capex": -6811000000
  },

  "balance_sheet": {
    "total_debt": 101304000000,
    "cash_position": 29943000000,
    "net_debt": 71361000000,
    "total_equity": 56950000000
  },

  "debt_leverage": {
    "debt_to_equity": 1.779,
    "interest_coverage": 29.5,
    "current_ratio": 0.867
  },

  "earnings_quality": {
    "gaap_net_income": 93736000000,
    "sbc_actual": 11688000000,
    "sbc_to_revenue_pct": 0.030
  },

  "dilution": {
    "basic_shares": 15204137000,
    "diluted_shares": 15287519000,
    "dilution_pct": 0.55
  },

  "valuation": {
    "roe": 1.646,
    "roic": 0.714,
    "roa": 0.251
  }
}
```

### API Endpoint

The dashboard will call a REST API endpoint:
```
GET /metrics/{ticker}?quarters=20
```

Response: Array of the above items sorted by fiscal_date ascending.

There is also a ratings object from the investment report:
```json
{
  "growth": { "rating": "Strong", "confidence": "High", "key_factors": ["..."] },
  "profitability": { "rating": "Strong", "confidence": "High", "key_factors": ["..."] },
  "valuation": { "rating": "Moderate", "confidence": "Medium", "key_factors": ["..."] },
  "earnings_quality": { "rating": "Strong", "confidence": "High", "key_factors": ["..."] },
  "cashflow": { "rating": "Strong", "confidence": "High", "key_factors": ["..."] },
  "debt": { "rating": "Moderate", "confidence": "Medium", "key_factors": ["..."] },
  "dilution": { "rating": "Strong", "confidence": "High", "key_factors": ["..."] },
  "overall_verdict": "BUY",
  "conviction": "High"
}
```

---

## 7 Category Tabs — Chart + Table Specifications

### 1. Growth Tab
**Metrics**: Revenue, Net Income, EPS, Revenue Growth YoY
**Chart**: Dual-axis — bar chart for Revenue + Net Income (left axis, formatted as $B), line for Revenue Growth % (right axis)
**Table columns**: Quarter | Revenue ($B) | Net Income ($B) | EPS | YoY Growth (%)
**Color logic**: Growth > 10% = green, 0-10% = amber, negative = red

### 2. Profitability Tab
**Metrics**: Gross Margin, Operating Margin, Net Margin, ROE, ROIC, ROA
**Chart**: Multi-line chart showing all 3 margins over time (0-100% scale). Secondary chart or row for ROE/ROIC/ROA.
**Table columns**: Quarter | Gross Margin | Op Margin | Net Margin | ROE | ROIC | ROA
**Color logic**: Expanding margins = green, compressing = red

### 3. Valuation Tab
**Metrics**: ROE, ROIC, ROA (capital efficiency as proxy for intrinsic value)
**Chart**: Bar chart comparing ROE, ROIC, ROA across quarters
**Table columns**: Quarter | ROE | ROIC | ROA
**Insight**: "Buffett looks for consistent ROE above 15% — it signals a durable competitive advantage."

### 4. Cash Flow Tab
**Metrics**: Operating Cash Flow, Free Cash Flow, FCF Margin, CapEx
**Chart**: Stacked area chart — Operating CF on bottom, CapEx shaded area showing the difference = FCF. Line overlay for FCF Margin %.
**Table columns**: Quarter | Operating CF ($B) | CapEx ($B) | FCF ($B) | FCF Margin (%)
**Color logic**: FCF growing = green, declining = red

### 5. Debt & Leverage Tab
**Metrics**: Total Debt, Cash Position, Net Debt, Total Equity, D/E Ratio, Interest Coverage, Current Ratio
**Chart**: Stacked bar for Debt vs Cash position. Line overlay for D/E ratio.
**Table columns**: Quarter | Total Debt ($B) | Cash ($B) | Net Debt ($B) | D/E | Interest Coverage | Current Ratio
**Color logic**: Improving leverage = green, deteriorating = red
**Insight**: "Buffett avoids companies where debt could threaten survival in a downturn."

### 6. Earnings Quality Tab
**Metrics**: GAAP Net Income, Stock-Based Compensation, SBC as % of Revenue
**Chart**: Bar chart for GAAP Income with SBC overlay bar (showing how much SBC eats into real earnings). Line for SBC/Revenue %.
**Table columns**: Quarter | GAAP Income ($B) | SBC ($B) | SBC/Revenue (%)
**Color logic**: SBC/Revenue < 3% = green, 3-8% = amber, > 8% = red
**Insight**: "Real earnings power means cash, not paper. Buffett discounts companies that pay in stock instead of cash."

### 7. Dilution Tab
**Metrics**: Basic Shares, Diluted Shares, Dilution %
**Chart**: Area chart for share count over time (declining = buybacks, good). Line for dilution %.
**Table columns**: Quarter | Basic Shares (B) | Diluted Shares (B) | Dilution (%)
**Color logic**: Decreasing shares = green (buybacks), increasing = red (dilution)
**Insight**: "Buffett loves companies that buy back shares — it means management believes the stock is undervalued."

---

## Visual Design Requirements

### Color Palette
- **Primary**: Deep navy (#1a1a2e) background with warm gold (#d4a843) accents — evoking Berkshire Hathaway annual reports
- **Secondary**: Soft cream (#f5f0e8) for cards, muted sage (#4a7c59) for positive, dusty rose (#c44536) for negative
- **Text**: Off-white (#e8e0d0) on dark backgrounds
- **Charts**: Gold (#d4a843), sage (#4a7c59), steel blue (#5b8fa8), warm amber (#d4944a)

### Typography
- Headers: Serif font (Georgia, Playfair Display, or similar) — classic, authoritative
- Body/Data: Clean sans-serif (Inter, system-ui)
- Numbers in tables: Monospace/tabular figures for alignment

### Component Style
- Cards with subtle cream (#f5f0e8) borders, slight shadow
- Rounded corners (8px) on cards and buttons
- Category tabs styled as a horizontal pill bar
- Rating badges: pill-shaped with color coding (Strong=sage, Moderate=amber, Weak=rose)
- Charts should have subtle gridlines, no heavy borders
- Tables should be clean with alternating row shading (very subtle)
- Hover states on chart data points showing tooltip with exact values

### Buffett Insight Cards
- Styled as a quote card with a subtle left gold border
- Small Warren Buffett silhouette icon or quote marks
- Background slightly different shade to stand out
- Contains 1-2 sentence insight relevant to the category

### Responsive
- Desktop: Full dashboard as shown
- Tablet: Stack chart above table
- Mobile: Single column, swipeable category tabs

---

## Interactions

1. **Ticker Search**: User types ticker, hits Analyze → fetches data → populates all tabs
2. **Tab Navigation**: Clicking a category tab swaps the chart + table + insight
3. **Time Range Toggle**: 5Y (default) | 3Y | 1Y filters the displayed quarters
4. **Chart Hover**: Tooltip shows exact values for that quarter
5. **Table Sort**: Click column headers to sort ascending/descending
6. **Smooth Transitions**: Fade/slide when switching tabs, charts animate on load

---

## Tech Stack

- **React 18** with functional components and hooks
- **Tailwind CSS** for styling
- **Recharts** or **Chart.js** for data visualization (prefer Recharts for React integration)
- **Vite** as build tool
- Data fetched from REST API, cached in component state
- Format large numbers as $XXB or $XXM with 1 decimal place
- Format percentages to 1 decimal place with % suffix
- Format ratios to 2 decimal places

---

## Sample Mock Data for Development

Use this to render the UI before the real API is connected:

```javascript
const mockData = [
  {
    ticker: "AAPL",
    fiscal_date: "2021-09-25",
    fiscal_year: 2021,
    fiscal_quarter: "Q4",
    revenue_profit: { revenue: 365817000000, net_income: 94680000000, gross_margin: 0.418, operating_margin: 0.298, net_margin: 0.259, eps: 5.67, revenue_growth_yoy: 0.33 },
    cashflow: { operating_cash_flow: 104038000000, free_cash_flow: 92953000000, fcf_margin: 0.254, capex: -11085000000 },
    balance_sheet: { total_debt: 124719000000, cash_position: 34940000000, net_debt: 89779000000, total_equity: 63090000000 },
    debt_leverage: { debt_to_equity: 1.977, interest_coverage: 41.2, current_ratio: 1.075 },
    earnings_quality: { gaap_net_income: 94680000000, sbc_actual: 7906000000, sbc_to_revenue_pct: 0.022 },
    dilution: { basic_shares: 16701272000, diluted_shares: 16864919000, dilution_pct: 0.98 },
    valuation: { roe: 1.501, roic: 0.563, roa: 0.269 }
  },
  {
    ticker: "AAPL",
    fiscal_date: "2022-09-24",
    fiscal_year: 2022,
    fiscal_quarter: "Q4",
    revenue_profit: { revenue: 394328000000, net_income: 99803000000, gross_margin: 0.434, operating_margin: 0.303, net_margin: 0.253, eps: 6.15, revenue_growth_yoy: 0.08 },
    cashflow: { operating_cash_flow: 122151000000, free_cash_flow: 111443000000, fcf_margin: 0.283, capex: -10708000000 },
    balance_sheet: { total_debt: 120069000000, cash_position: 23646000000, net_debt: 96423000000, total_equity: 50672000000 },
    debt_leverage: { debt_to_equity: 2.370, interest_coverage: 33.4, current_ratio: 0.879 },
    earnings_quality: { gaap_net_income: 99803000000, sbc_actual: 9038000000, sbc_to_revenue_pct: 0.023 },
    dilution: { basic_shares: 16215963000, diluted_shares: 16325819000, dilution_pct: 0.68 },
    valuation: { roe: 1.970, roic: 0.705, roa: 0.283 }
  },
  {
    ticker: "AAPL",
    fiscal_date: "2023-09-30",
    fiscal_year: 2023,
    fiscal_quarter: "Q4",
    revenue_profit: { revenue: 383285000000, net_income: 96995000000, gross_margin: 0.441, operating_margin: 0.298, net_margin: 0.253, eps: 6.16, revenue_growth_yoy: -0.03 },
    cashflow: { operating_cash_flow: 110543000000, free_cash_flow: 99584000000, fcf_margin: 0.260, capex: -10959000000 },
    balance_sheet: { total_debt: 111088000000, cash_position: 29965000000, net_debt: 81123000000, total_equity: 62146000000 },
    debt_leverage: { debt_to_equity: 1.787, interest_coverage: 29.1, current_ratio: 0.988 },
    earnings_quality: { gaap_net_income: 96995000000, sbc_actual: 10833000000, sbc_to_revenue_pct: 0.028 },
    dilution: { basic_shares: 15744231000, diluted_shares: 15812547000, dilution_pct: 0.43 },
    valuation: { roe: 1.561, roic: 0.648, roa: 0.268 }
  },
  {
    ticker: "AAPL",
    fiscal_date: "2024-09-28",
    fiscal_year: 2024,
    fiscal_quarter: "Q4",
    revenue_profit: { revenue: 391035000000, net_income: 93736000000, gross_margin: 0.462, operating_margin: 0.304, net_margin: 0.240, eps: 6.13, revenue_growth_yoy: 0.02 },
    cashflow: { operating_cash_flow: 118254000000, free_cash_flow: 111443000000, fcf_margin: 0.285, capex: -6811000000 },
    balance_sheet: { total_debt: 101304000000, cash_position: 29943000000, net_debt: 71361000000, total_equity: 56950000000 },
    debt_leverage: { debt_to_equity: 1.779, interest_coverage: 29.5, current_ratio: 0.867 },
    earnings_quality: { gaap_net_income: 93736000000, sbc_actual: 11688000000, sbc_to_revenue_pct: 0.030 },
    dilution: { basic_shares: 15204137000, diluted_shares: 15287519000, dilution_pct: 0.55 },
    valuation: { roe: 1.646, roic: 0.714, roa: 0.251 }
  },
  {
    ticker: "AAPL",
    fiscal_date: "2025-09-27",
    fiscal_year: 2025,
    fiscal_quarter: "Q4",
    revenue_profit: { revenue: 410500000000, net_income: 100200000000, gross_margin: 0.471, operating_margin: 0.312, net_margin: 0.244, eps: 6.68, revenue_growth_yoy: 0.05 },
    cashflow: { operating_cash_flow: 125000000000, free_cash_flow: 118000000000, fcf_margin: 0.287, capex: -7000000000 },
    balance_sheet: { total_debt: 95000000000, cash_position: 32000000000, net_debt: 63000000000, total_equity: 60000000000 },
    debt_leverage: { debt_to_equity: 1.583, interest_coverage: 31.2, current_ratio: 0.912 },
    earnings_quality: { gaap_net_income: 100200000000, sbc_actual: 12500000000, sbc_to_revenue_pct: 0.030 },
    dilution: { basic_shares: 14900000000, diluted_shares: 14980000000, dilution_pct: 0.54 },
    valuation: { roe: 1.670, roic: 0.730, roa: 0.260 }
  }
];

const mockRatings = {
  growth: { rating: "Moderate", confidence: "Medium", key_factors: ["Revenue growth slowed to 2-5%", "Services segment driving growth", "iPhone cycle dependency"] },
  profitability: { rating: "Strong", confidence: "High", key_factors: ["Gross margins expanding to 47%", "Operating leverage improving", "ROE consistently above 150%"] },
  valuation: { rating: "Moderate", confidence: "Medium", key_factors: ["Premium multiple justified by quality", "FCF yield attractive", "Buybacks boosting per-share value"] },
  earnings_quality: { rating: "Strong", confidence: "High", key_factors: ["Low SBC relative to revenue", "Cash conversion excellent", "Minimal accounting adjustments"] },
  cashflow: { rating: "Strong", confidence: "High", key_factors: ["FCF margin near 29%", "Capex declining as % of revenue", "Massive cash generation"] },
  debt: { rating: "Moderate", confidence: "Medium", key_factors: ["D/E elevated but manageable", "Interest coverage strong at 29x", "Debt used for buybacks"] },
  dilution: { rating: "Strong", confidence: "High", key_factors: ["Aggressive buyback program", "Share count declining 3% annually", "Dilution well below 1%"] },
  overall_verdict: "BUY",
  conviction: "High"
};
```

---

## Key Behavioral Notes

- When no ticker is searched yet, show a welcoming empty state: "Search for any public company to unlock deep value insights" with example tickers (AAPL, MSFT, AMZN, BRK.B)
- Loading state: Skeleton shimmer on charts and tables while data loads
- Error state: Friendly message if ticker not found or data unavailable
- The overall verdict (BUY/HOLD/SELL) badge should be prominent in the company header
- Numbers should feel authoritative — use proper formatting ($391.0B not $391035000000)
- The whole experience should feel like reading a premium Berkshire Hathaway annual report — sophisticated, data-rich, but not overwhelming
