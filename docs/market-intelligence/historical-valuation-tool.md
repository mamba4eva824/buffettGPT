# getHistoricalValuation — Market Intelligence Tool

A new inline Bedrock tool that answers *"Is this stock cheap or expensive compared to its own history?"* in a single call. Returns 9 frontend-parity valuation metrics with pre-computed historical statistics, retail-friendly verdicts, and sector-relative context.

## Overview

| Property | Value |
|----------|-------|
| **Tool name** | `getHistoricalValuation` |
| **Lambda** | `buffett-dev-analysis-followup` (shared with market intel chatbot) |
| **API style** | Bedrock `converse_stream()` inline tool (not a Bedrock Agent action group) |
| **Data source** | `metrics-history-{env}` + `buffett-{env}-sp500-aggregates` (DynamoDB) |
| **FMP calls** | **None** — entirely offline, no live API quota consumed |
| **Scope** | S&P 500 tickers only |
| **Status** | Implemented, tests green, awaiting deploy |

---

## Executive Summary

### The problem
The Market Intelligence chatbot previously had 9 tools, but none of them let a user ask *"Is Apple expensive right now compared to its own recent history?"* The closest existing tool, `getMetricTrend`, returned a raw 20-quarter series for a single metric at a time and forced the LLM to do statistics on a long table — producing inconsistent, error-prone verdicts.

Meanwhile, the frontend Valuation tab in Value Insights already showed historical P/E range bars, percentile positioning, and margin-of-safety gauges. The data existed, the math existed — but a retail investor asking the chatbot "Is Microsoft cheap?" couldn't get a crisp answer.

### The solution
`getHistoricalValuation` bundles all 9 frontend-parity valuation metrics into one tool call. For each metric, it returns the current value plus pre-computed min/max/mean/median/percentile/z-score statistics, a cheap/fair/expensive categorical label, and a natural-language verdict ready for the LLM to quote directly — e.g., *"Cheaper than 94% of its last 5 years of history."* Sector medians for the same metrics are included for sector-relative context.

### Who benefits
- **Retail investors** — get Warren-Buffett-style historical valuation commentary without needing to know what "EV/EBITDA at the 6th percentile" means. Every metric carries a plain-English label and explanation inside the tool response.
- **The chatbot LLM** — gets all 9 metrics in one call with pre-computed statistics, eliminating flaky math on 20-quarter tables. Ready-to-quote verdicts mean the LLM doesn't invent phrasing.
- **Product** — enables a category of valuation questions (historical context, cheap-vs-history, margin of safety) that the bot previously fumbled.

### Design tension resolved
Retail investors need plain-English language, but the baseline system prompt is paid on every single inference call. We resolved this by **pushing all retail-friendly translation into the tool response itself** (paid only when the tool is called) and keeping the system prompt change to **exactly one bullet line** (paid on every inference). Baseline inference cost grew by ~20 tokens; per-call cost grew by ~1,260 tokens but only when a user actually asks a valuation question.

---

## Business Value

| Benefit | Description |
|---------|-------------|
| **Closes a feature gap** | First chatbot tool that answers historical valuation questions — previously impossible without client-side math |
| **Retail-accessible by design** | Plain-English labels + natural verdicts mean even users who don't know what "percentile" means get a usable answer |
| **Zero FMP quota cost** | Entirely served from pre-computed DynamoDB tables; no live API calls |
| **Consistent with Valuation tab** | Uses the same 9 metrics shown in the frontend Value Insights dashboard, so chatbot and UI tell the same story |
| **Sub-second latency** | Single DynamoDB query per call; no in-memory scan, no FMP roundtrip |
| **Negligible cost** | ~$0.0016 per user query at Claude Haiku 4.5 pricing |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    USER: "Is MSFT cheap vs its own history?"                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│          MARKET INTEL CHAT LAMBDA (analysis_followup)                       │
│                                                                              │
│   Claude Haiku 4.5 supervisor (converse_stream + 10 inline tools)           │
│   System prompt advertises: getHistoricalValuation                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ tool_use: getHistoricalValuation
                                    │   { "ticker": "MSFT" }
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│          _get_historical_valuation() handler                                 │
│                                                                              │
│   1. Query metrics-history-dev   (ticker=MSFT, ascending)                   │
│   2. Build 9 time series (last 20 quarters)                                 │
│       • 6 direct reads       (pe_ratio, ev_to_ebitda, yields, roic/roa)    │
│       • 1 cross-category     (roe from revenue_profit)                     │
│       • 2 derived            (pb_ratio, price_to_fcf)                       │
│   3. Compute stats per metric via _compute_metric_stats()                   │
│       • percentile, z_score, assessment, verdict                            │
│       • polarity inversion for higher_is_cheaper metrics                    │
│   4. Query sp500-aggregates     (aggregate_type=SECTOR, key=Technology)    │
│   5. Assemble response with label + plain_english + verdict per metric      │
└─────────────────────────────────────────────────────────────────────────────┘
          │                               │
          │ query                         │ get_item
          ▼                               ▼
┌─────────────────────────┐     ┌──────────────────────────────────────────────┐
│  metrics-history-dev    │     │  buffett-dev-sp500-aggregates                │
│                         │     │                                               │
│  PK: ticker (MSFT)      │     │  PK: aggregate_type (SECTOR)                 │
│  SK: fiscal_date        │     │  SK: aggregate_key (Technology)              │
│  20 quarters × 9 cats   │     │  company_count + per-metric medians          │
└─────────────────────────┘     └──────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│          LLM receives tool_result (~1,260 tokens of structured JSON)        │
│          + composes a retail-friendly reply quoting pre-written verdicts    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Nine Metrics

All metrics are stored in [VALUATION_METRIC_META](../../chat-api/backend/src/utils/market_intel_tools.py) with `label`, `plain_english`, `source`, and `direction` fields.

| # | Key | Label | Plain-English | Source | Direction |
|---|---|---|---|---|---|
| 1 | `pe_ratio` | Price-to-Earnings (P/E) | Years of profit to earn back the stock price | `market_valuation.pe_ratio` | lower = cheaper |
| 2 | `pb_ratio` | Price-to-Book (P/B) | Stock price vs company net worth on paper | derived: `market_cap / total_equity` | lower = cheaper |
| 3 | `ev_to_ebitda` | Enterprise Value / EBITDA | Total company value vs cash profit from operations | `market_valuation.ev_to_ebitda` | lower = cheaper |
| 4 | `price_to_fcf` | Price / Free Cash Flow | Stock price vs cash profit after expenses | derived: `100 / fcf_yield` | lower = cheaper |
| 5 | `earnings_yield` | Earnings Yield | Profit per dollar invested, like an interest rate | `market_valuation.earnings_yield` (percent) | **higher = cheaper** |
| 6 | `fcf_yield` | Free Cash Flow Yield | Actual cash return per dollar invested | `market_valuation.fcf_yield` (percent) | **higher = cheaper** |
| 7 | `roic` | Return on Invested Capital | How efficiently capital is turned into profit | `valuation.roic` | **higher = cheaper** |
| 8 | `roe` | Return on Equity | Profit per dollar of shareholder money | `revenue_profit.roe` | **higher = cheaper** |
| 9 | `roa` | Return on Assets | Profit per dollar of assets (harder to fake with debt) | `valuation.roa` | **higher = cheaper** |

### Polarity handling
"Cheap" always means "good for the investor." For return/yield metrics (5-9) the polarity is inverted — a high ROIC is reported as "cheap" internally (for consistent machine-readable assessment fields) but surfaces in the verdict as natural language: *"Higher than 95% of its last 5 years of history (good for the investor)"*, not *"Cheaper than 95%"*.

---

## Statistical Engine

`_compute_metric_stats(values, current, direction)` — pure function, no I/O, 100% unit-tested.

```python
clean = [v for v in values if v is not None]

# Degenerate cases
if current is None:        → assessment = "unavailable"
if len(clean) < 4:         → assessment = "insufficient_history"

# Normal case
mean, median, min, max = statistics.*
stdev = statistics.stdev(clean)
z_score = (current - mean) / stdev

percentile = round(100 * count(clean <= current) / len(clean))
effective_pct = percentile if lower_is_cheaper else 100 - percentile

if effective_pct < 25:     assessment = "cheap"
elif effective_pct > 75:   assessment = "expensive"
else:                      assessment = "fair"

cheapness_pct = 100 - percentile if lower_is_cheaper else percentile

# Retail-friendly verdict (direction-specific phrasing)
if lower_is_cheaper:
    cheap     → "Cheaper than {cheapness_pct}% of its last 5 years of history."
    expensive → "More expensive than {100 - cheapness_pct}% of its last 5 years of history."
else:  # higher_is_cheaper (returns and yields)
    cheap     → "Higher than {cheapness_pct}% of its last 5 years of history (good for the investor)."
    expensive → "Lower than {100 - cheapness_pct}% of its last 5 years of history (worse than usual)."
```

### Graceful degradation
If historical `market_valuation` hasn't been backfilled for a ticker (only the latest quarter has data), the per-metric series may have fewer than 4 non-null points. In that case the handler still returns `current` but sets `assessment: "insufficient_history"` and a clear verdict — the tool never errors out due to sparse data.

---

## Sample Outputs (from real dev DynamoDB)

Sample run: `getHistoricalValuation({"ticker": "MSFT"})` — 20 quarters 2021-03 → 2025-12

| Metric | Current | Assessment | Verdict |
|---|---|---|---|
| P/E | 23.79 | cheap | Cheaper than 94% of its last 5 years of history. |
| P/B | 7.25 | cheap | Cheaper than 94% of its last 5 years of history. |
| EV/EBITDA | 15.33 | cheap | Cheaper than 94% of its last 5 years of history. |
| P/FCF | 36.63 | fair | Around the middle of its last 5 years of history. |
| Earnings Yield | 4.20% | cheap | Higher than 100% of its last 5 years of history (good for the investor). |
| FCF Yield | 2.73% | fair | Around the middle of its last 5 years of history. |
| ROIC | 26.70% | expensive | Lower than 95% of its last 5 years of history (worse than usual). |
| ROE | 39.40% | fair | Around the middle of its last 5 years of history. |
| ROA | 23.10% | cheap | Higher than 95% of its last 5 years of history (good for the investor). |

The chatbot can read this and compose: *"Microsoft's price multiples (P/E, P/B, EV/EBITDA) are all at historical lows — cheaper than 94% of the last five years. But watch ROIC, which has dropped to a 5-year low and is worse than 95% of historical observations — likely the AI capex hangover compressing capital efficiency."*

---

## Token Cost Analysis

| Component | Tokens (est.) | When paid |
|---|---|---|
| Tool spec in system prompt | **~337** | Every inference, regardless of whether tool is called |
| Tool response (avg) | **~1,260** | Only when LLM calls `getHistoricalValuation` |
| 3-ticker comparison (AAPL + MSFT + NVDA) | ~3,780 | Rare — only on multi-ticker questions |

**Per-query cost estimate (Claude Haiku 4.5 @ $1/MTok input, $5/MTok output):**
- Baseline inference overhead: ~$0.0003 per chat turn
- Tool call: ~$0.0013 additional when invoked
- **Total per valuation question: ~$0.0016**

Budget vs actual: plan budgeted ≤1,000 tokens per response; actual ~1,260 (25% over) due to verbose retail-friendly verdicts and plain-English strings. Reviewer judged this acceptable as a direct trade for the "translate finance terms for retail investors" requirement.

---

## Code Locations

| Concern | File | Key lines |
|---|---|---|
| Tool metadata + statistical engine + handler | [chat-api/backend/src/utils/market_intel_tools.py](../../chat-api/backend/src/utils/market_intel_tools.py) | `VALUATION_METRIC_META` constant, `_compute_metric_stats`, `_derive_pb_ratio`, `_get_historical_valuation`, dispatcher entry |
| Bedrock tool spec + one-line system prompt bullet | [chat-api/backend/src/handlers/market_intel_chat.py](../../chat-api/backend/src/handlers/market_intel_chat.py) | `MARKET_INTEL_TOOLS` (entry 10 of 10), system prompt bullet list |
| Lambda-routing registration | [chat-api/backend/src/utils/unified_tool_executor.py](../../chat-api/backend/src/utils/unified_tool_executor.py) | `MARKET_INTEL_TOOL_NAMES` set |
| Unit tests (7 cases) | [chat-api/backend/tests/unit/test_market_intel_tools.py](../../chat-api/backend/tests/unit/test_market_intel_tools.py) | `TestGetHistoricalValuation` class |

---

## Testing

`TestGetHistoricalValuation` in [test_market_intel_tools.py](../../chat-api/backend/tests/unit/test_market_intel_tools.py) covers:

1. **Happy path (12 quarters, all metrics)** — all 9 metric keys present; P/E correctly assessed as "expensive" when latest is the highest; sector context populated
2. **Polarity inversion (earnings yield)** — higher value → `cheap` assessment with "Higher than" verdict language (not "Cheaper than")
3. **Insufficient history** — only 2 quarters with `market_valuation` → P/E has `assessment: "insufficient_history"` while ROIC (present in all 10 quarters) does not
4. **Missing ticker** — empty params → `{"success": false, "error": "..."}`
5. **Non-S&P 500 / no data** — empty DynamoDB result → clear error message
6. **pb_ratio derivation** — `market_cap / total_equity` computed correctly across quarters; `total_equity = 0` gracefully skipped
7. **price_to_fcf derivation** — `100 / fcf_yield` computed correctly; current value at max → `expensive` assessment

Full gate status at time of implementation:

| Gate | Result |
|---|---|
| `pytest tests/unit/` | **410 passed** |
| `terraform validate` | **PASS** (pre-existing deprecation warnings only) |
| `./scripts/build_lambdas.sh` | **PASS** — all 20+ Lambda zips rebuilt successfully |
| `npm run lint` | FAIL — pre-existing [ResearchContext.jsx](../../frontend/src/contexts/ResearchContext.jsx) errors, not caused by this work |

---

## Known Limitations & Future Work

### Limitations

- **Historical `market_valuation` depth depends on backfill state.** The EOD pipeline ([sp500_pipeline.py](../../chat-api/backend/src/handlers/sp500_pipeline.py)) only writes `market_valuation` to the latest quarter. Historical quarters are populated by [sp500_backfill.compute_quarterly_valuations](../../chat-api/backend/src/handlers/sp500_backfill.py), which derives `pe_ratio, ev_to_ebitda, earnings_yield, fcf_yield, market_cap, enterprise_value` from price data + TTM financial statements. Tickers for which backfill hasn't run will report `insufficient_history` for these 6 metrics. `roic`, `roa`, `roe` are always historically available because they're computed per-quarter by the feature extractor from raw statements.
- **`ev_to_sales` and `ev_to_fcf` are not exposed.** These exist in FMP's TTM payload but are not computed historically and are not shown in the frontend Valuation tab. They were intentionally dropped from scope to match frontend parity.
- **Sector medians are sparse.** The `sp500-aggregates` table only carries sector medians for 5 of the 9 metrics (`pe_ratio`, `ev_to_ebitda`, `roic`, `roe`, `roa`). The handler gracefully omits keys the aggregate doesn't carry.
- **S&P 500 only.** No FMP fallback for non-S&P 500 tickers — the tool returns a clear error.
- **Quarters clamped to [1, 20].** Max 20 quarters (5 years) of history is returned; quarters=0 edge case is explicitly handled.

### Future enhancements

- **Extend `compute_quarterly_valuations`** to also derive `ev_to_sales`, `ev_to_fcf`, and `price_to_sales` from the same price + financial statement data — would expand the historical depth of those metrics from "latest only" to "full 20 quarters."
- **Emit sector medians for all 9 metrics** from [sp500_aggregator.py](../../chat-api/backend/src/handlers/sp500_aggregator.py) so the handler can always fill `sector_context.sector_medians` completely.
- **Frontend parity for bot responses.** Consider a companion React component that visually renders the tool's structured output as range bars and sparklines, matching the Value Insights Valuation tab exactly.
- **Cross-ticker percentile comparison.** Extend the tool with an optional `compare_to` list so the LLM can answer *"Is AAPL cheaper than its peers right now?"* without calling `compareCompanies` separately.

---

## Related Documentation

- [Follow-up Research Agent](../investment-research/followup-agent.md) — sibling tool pattern for converse_stream inline tools
- [Metrics Cache](../investment-research/metrics-cache.md) — `metrics-history-{env}` DynamoDB schema reference
- [EOD Price Pipeline](../data-pipeline/sp500-eod-price-pipeline.md) — the source of latest-quarter `market_valuation` updates
- [CHANGELOG](./CHANGELOG.md) — full Market Intelligence change history
