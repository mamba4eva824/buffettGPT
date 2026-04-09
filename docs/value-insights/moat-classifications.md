# Moat Classifications

The MOAT tab on Value Insights classifies each stock across four dimensions to give a complete picture of competitive advantage.

---

## Moat Width

*How far above cost of capital on average?*

Uses average ROIC across all available quarters compared to a 10% cost of capital benchmark.

| Label | Criteria | Interpretation |
|-------|----------|----------------|
| **Wide** | Avg ROIC > 20% (10pp+ spread) | Strong competitive position — consistently earns well above what investors require. Think Visa, Apple, Microsoft. |
| **Narrow** | Avg ROIC 10-20% | Some competitive advantage, but the margin of safety is thin. Common for airlines, banks, industrials. |
| **None** | Avg ROIC <= 10% | No quantitative moat evidence — returns don't justify the capital invested. Commodity businesses or turnarounds. |

**Scorecard pass/fail**: Pass if Width is Wide or Narrow.

---

## Moat Durability

*How consistent are those returns?*

Combines two signals: ROIC volatility (coefficient of variation) and the percentage of quarters where ROIC exceeds the cost of capital.

| Label | Criteria | Interpretation |
|-------|----------|----------------|
| **Durable** | CV < 0.25 AND >80% quarters above CoC | Low volatility with consistent returns — the advantage is persistent. Think Coca-Cola, Johnson & Johnson. |
| **Cyclical** | CV >= 0.25 AND avg ROIC above CoC | High volatility but mean-reverts above cost of capital — seasonal or cyclical business. Airlines, autos, banks. |
| **Fragile** | Otherwise (frequent dips below CoC or avg below CoC) | Returns are inconsistent — the advantage may be temporary or eroding. |

**Scorecard pass/fail**: Pass if Durability is Durable or Cyclical.

### Why this matters

A Wide moat with Fragile durability is a red flag — the company earns high returns but can't sustain them. A Narrow moat with Durable returns can be more investable than a Wide but Fragile one.

---

## Moat Trend

*Is the competitive advantage getting stronger or weaker?*

Compares average ROIC in the first half of available quarters vs the second half, with a volatility-aware threshold to prevent seasonal noise from producing false signals.

| Label | Criteria | Interpretation |
|-------|----------|----------------|
| **Strengthening** | Half-over-half ROIC change > max(2pp, 1 std dev) | ROIC is trending higher — the competitive advantage appears to be widening. |
| **Stable** | Change within +/- max(2pp, 1 std dev) | ROIC is holding steady — the moat appears durable with consistent returns on capital. |
| **Eroding** | Half-over-half ROIC change < -max(2pp, 1 std dev) | ROIC is trending lower — competitors may be closing the gap. |

### Volatility-aware threshold

The threshold scales with the stock's own ROIC standard deviation. A cyclical stock like Delta (std dev = 6.4pp) needs a >6.4pp shift to trigger a trend signal, while a steady compounder like Visa (std dev ~1pp) only needs a >2pp shift. This prevents seasonal swings in cyclical businesses from being misread as moat erosion.

**Scorecard pass/fail**: Pass if Trend is Strengthening or Stable.

---

## Capital Allocation

*What does the company do with its returns?*

Evaluates reinvestment behavior vs shareholder returns using the most recent 4 quarters.

| Label | Criteria | Interpretation |
|-------|----------|----------------|
| **Compounder** | ROIC > CoC + payout ratio < 30% + capex intensity > 5% | Reinvesting heavily while earning above cost of capital — growing the moat. Think Amazon in growth mode. |
| **Cash Cow** | ROIC > CoC + payout ratio > 50% | Returning majority of FCF to shareholders via dividends and buybacks — harvesting the moat. |
| **Balanced** | ROIC > CoC + moderate payout and reinvestment | Balancing reinvestment with shareholder returns. Think Microsoft — grows and returns capital. |
| **Value Destroyer** | Avg ROIC < CoC | Returns don't justify capital invested regardless of how it's allocated. |

### Definitions

- **Payout ratio**: (Dividends + Buybacks) / Free Cash Flow over the last 4 quarters
- **Capex intensity**: CapEx / Revenue, averaged over the last 4 quarters

**Scorecard pass/fail**: Pass if not Value Destroyer.

---

## Example Classifications

| Stock | Width | Durability | Trend | Capital | Summary |
|-------|-------|------------|-------|---------|---------|
| DAL (Delta) | Narrow | Cyclical | Stable | Cash Cow | Thin but real advantage, seasonal ROIC swings, returning capital |
| AAPL (Apple) | Wide | Durable | Stable | Cash Cow | Strong moat, consistent returns, massive buyback program |
| AMZN (Amazon) | Wide | Durable | Strengthening | Compounder | Wide moat growing wider, reinvesting at high rates |
| F (Ford) | None | Fragile | Eroding | Value Destroyer | Returns below cost of capital, inconsistent, declining |

---

## Implementation

- **Frontend**: `CategoryPanels.jsx` — `MoatPanel` component, computed via `useMemo` hooks
- **Data source**: `valuation.roic`, `cashflow.*`, `revenue_profit.*` from normalized quarter objects
- **Backend**: ROIC calculated in `feature_extractor.py`, stored in `metrics-history-dev` DynamoDB table
