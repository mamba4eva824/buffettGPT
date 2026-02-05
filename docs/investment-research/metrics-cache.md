# Metrics History Cache

The metrics cache stores historical financial data for trend analysis in follow-up questions.

## Overview

When users ask about financial trends, the system retrieves cached historical metrics rather than making live API calls.

## Data Stored

| Metric Type | Data Points | Source |
|-------------|-------------|--------|
| Revenue | 20 quarters | FMP Income Statement |
| Net Income | 20 quarters | FMP Income Statement |
| Cash Flow | 20 quarters | FMP Cash Flow Statement |
| Debt Levels | 20 quarters | FMP Balance Sheet |
| Margins | 20 quarters | Calculated |
| Valuation | 5 years | FMP Key Metrics |

## Cache Structure

Data is cached in DynamoDB (future implementation):

```json
{
  "ticker": "AAPL",
  "metric_type": "revenue",
  "periods": [
    {"period": "Q3 2024", "value": 94.93, "yoy_growth": 0.06},
    {"period": "Q2 2024", "value": 85.78, "yoy_growth": 0.05}
  ],
  "cached_at": "2026-01-15T10:00:00Z",
  "ttl": 86400
}
```

## Usage

### Retrieve Cached Metrics

```python
from investment_research.services.metrics_cache import MetricsCache

cache = MetricsCache()
revenue_history = cache.get_metrics('AAPL', 'revenue', periods=8)
```

### Cache Invalidation

Cache is invalidated when:

1. New earnings are announced
2. TTL expires (24 hours)
3. Manual refresh triggered

## Benefits

- **Faster Responses** - No live API calls during Q&A
- **Consistent Data** - Same data used across session
- **Cost Savings** - Reduced FMP API usage

## Related

- [Follow-up Agent](followup-agent.md)
- [Earnings Tracker](earnings-tracker.md)
