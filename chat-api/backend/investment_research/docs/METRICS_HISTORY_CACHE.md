# Metrics History Cache - Executive Report

## Overview

The `metrics-history-cache` DynamoDB table provides pre-computed financial metrics for the Investment Research Follow-up Agent. This enables efficient, category-specific queries with ~85% token savings compared to querying raw financial data.

**Table Name:** `metrics-history-{environment}` (e.g., `metrics-history-dev`)

---

## Schema Design

### Primary Key Structure

| Attribute | Type | Description |
|-----------|------|-------------|
| `ticker` | String (PK) | Stock symbol (e.g., "AAPL") |
| `fiscal_date` | String (SK) | Fiscal period end date (e.g., "2025-09-27") |

### Design Rationale

The schema uses a **quarter-based** approach where each DynamoDB item represents one fiscal quarter with all 7 metric categories embedded. This design was chosen over a category-per-item approach for the following reasons:

1. **Reduced Item Count**: 20 items per ticker (one per quarter) vs 140 items (7 categories × 20 quarters)
2. **Human-Readable Sort Key**: `fiscal_date` (e.g., "2025-09-27") is more intuitive than opaque identifiers like "Q0" or "2024-Q3"
3. **Simple Query Pattern**: Single query returns all data; client-side filtering selects needed categories
4. **No GSIs Required**: Queries by ticker with fiscal_date ordering cover all use cases

### Item Structure

```json
{
  "ticker": "AAPL",
  "fiscal_date": "2025-09-27",
  "fiscal_year": 2025,
  "fiscal_quarter": "Q4",
  "cached_at": 1737321600,
  "expires_at": 1745097600,
  "currency": "USD",
  "source_cache_key": "v3:AAPL:2025",

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

---

## Metric Categories

| Category | Description | Example Metrics |
|----------|-------------|-----------------|
| `revenue_profit` | Revenue & Profitability | revenue, net_income, gross_margin, eps |
| `cashflow` | Cash Flow | operating_cash_flow, free_cash_flow, fcf_margin |
| `balance_sheet` | Balance Sheet | total_debt, cash_position, net_debt, total_equity |
| `debt_leverage` | Debt & Leverage Ratios | debt_to_equity, interest_coverage, current_ratio |
| `earnings_quality` | Earnings Quality | gaap_net_income, sbc_actual, sbc_to_revenue_pct |
| `dilution` | Share Dilution | basic_shares, diluted_shares, dilution_pct |
| `valuation` | Valuation & Returns | roe, roic, roa |

---

## Agent Action Group Integration

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Bedrock Follow-up Agent                       │
│                  (buffett-dev-followup-agent)                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Invokes Action Group
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   ReportResearch Action Group                    │
│                                                                  │
│  Actions:                                                        │
│  - getReportSection(ticker, section_id)                         │
│  - getReportRatings(ticker)                                     │
│  - getMetricsHistory(ticker, metric_type, quarters)  ◄──────────│
│  - getAvailableReports()                                        │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Lambda Invocation
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                followup-action Lambda Function                   │
│                 (buffett-dev-followup-action)                    │
│                                                                  │
│  Handler: followup_action_handler.py                            │
│  Service: report_service.py → get_metrics_history()             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ DynamoDB Query
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   metrics-history-dev Table                      │
│                                                                  │
│  PK: ticker    SK: fiscal_date                                  │
│  ────────────────────────────────────────                       │
│  AAPL          2025-09-27          ← Most recent                │
│  AAPL          2025-06-28                                       │
│  AAPL          2025-03-29                                       │
│  ...           ...                                              │
│  AAPL          2020-12-26          ← 20 quarters back           │
└─────────────────────────────────────────────────────────────────┘
```

### Action Group Definition

The `getMetricsHistory` action is defined in the Bedrock Action Group OpenAPI schema:

```yaml
/getMetricsHistory:
  post:
    summary: Retrieve historical financial metrics for a ticker
    operationId: getMetricsHistory
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              ticker:
                type: string
                description: Stock ticker symbol (e.g., "AAPL")
              metric_type:
                type: string
                enum: [revenue_profit, cashflow, balance_sheet, debt_leverage,
                       earnings_quality, dilution, valuation, all]
                description: Category of metrics to retrieve
              quarters:
                type: integer
                default: 20
                description: Number of quarters to retrieve (max 20)
```

### Query Flow

1. **User Question**: "How has Apple's debt changed over the last 3 years?"

2. **Agent Processing**: The Follow-up Agent identifies this as a debt-related question and invokes the `getMetricsHistory` action with:
   ```json
   {
     "ticker": "AAPL",
     "metric_type": "debt_leverage",
     "quarters": 12
   }
   ```

3. **Lambda Execution**: The `followup-action` Lambda receives the request and calls `get_metrics_history()`:
   ```python
   response = table.query(
       KeyConditionExpression=Key('ticker').eq('AAPL'),
       Limit=12,
       ScanIndexForward=False  # Most recent first
   )
   ```

4. **Client-Side Filtering**: The function filters the response to include only the `debt_leverage` category:
   ```python
   for item in items:
       category_metrics = item.get('debt_leverage', {})
       if category_metrics:
           result['data']['debt_leverage']['quarters'].append({
               'fiscal_date': item['fiscal_date'],
               'fiscal_year': item['fiscal_year'],
               'fiscal_quarter': item['fiscal_quarter'],
               'metrics': category_metrics
           })
   ```

5. **Response to Agent**: The Lambda returns a structured response containing only debt metrics:
   ```json
   {
     "success": true,
     "ticker": "AAPL",
     "metric_type": "debt_leverage",
     "quarters_available": 12,
     "data": {
       "debt_leverage": {
         "description": "Debt & Leverage Ratios",
         "quarters": [
           {
             "fiscal_date": "2025-09-27",
             "fiscal_year": 2025,
             "fiscal_quarter": "Q4",
             "metrics": {
               "debt_to_equity": 1.779,
               "interest_coverage": 29.5,
               "current_ratio": 0.867
             }
           }
         ]
       }
     }
   }
   ```

6. **Agent Response**: The agent synthesizes the metrics into a natural language answer for the user.

---

## Token Savings Analysis

The category-filtering approach provides significant token savings when answering specific questions:

| Query Type | All Metrics | Category Filter | Savings |
|------------|-------------|-----------------|---------|
| Debt question | ~60 metrics × 20 quarters = 1,200 values | ~10 metrics × 20 quarters = 200 values | **83%** |
| Profit question | ~60 metrics × 20 quarters = 1,200 values | ~11 metrics × 20 quarters = 220 values | **82%** |
| Valuation question | ~60 metrics × 20 quarters = 1,200 values | ~8 metrics × 20 quarters = 160 values | **87%** |
| Cash flow question | ~60 metrics × 20 quarters = 1,200 values | ~11 metrics × 20 quarters = 220 values | **82%** |

---

## Population Process

Metrics are populated during investment report generation:

### Source Files
- **Extractor**: [feature_extractor.py](../../../src/utils/feature_extractor.py) - `prepare_metrics_for_cache()`
- **Writer**: [report_generator.py](../report_generator.py) - `_batch_write_metrics_cache()`

### Population Flow

```python
# In report_generator.py during prepare_data()

# 1. Extract quarterly trends from raw financial data
quarterly_trends = extract_quarterly_trends(raw_financials)

# 2. Transform into cache items (20 per ticker)
cache_items = prepare_metrics_for_cache(
    ticker=ticker,
    quarterly_trends=quarterly_trends,
    currency=currency_info.get('code', 'USD'),
    source_cache_key=cache_key
)

# 3. Batch write to DynamoDB
self._batch_write_metrics_cache(cache_items)
```

### Batch Write Implementation

```python
def _batch_write_metrics_cache(self, items: List[Dict[str, Any]]) -> None:
    """Batch write metrics items to metrics-history-cache table."""
    table_name = os.environ.get('METRICS_HISTORY_CACHE_TABLE')
    if not table_name:
        logger.warning("METRICS_HISTORY_CACHE_TABLE not configured")
        return

    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(table_name)

    with table.batch_writer() as batch:
        for item in items:
            # Convert floats to Decimal for DynamoDB
            item_decimal = json.loads(
                json.dumps(item, cls=DecimalEncoder),
                parse_float=Decimal
            )
            batch.put_item(Item=item_decimal)

    logger.info(f"Cached {len(items)} metric items for {items[0]['ticker']}")
```

---

## Table Configuration

### Terraform Definition

Located in [ml_tables.tf](../../../terraform/modules/dynamodb/ml_tables.tf):

```hcl
resource "aws_dynamodb_table" "metrics_history_cache" {
  name         = "metrics-history-${var.environment}"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "ticker"
  range_key = "fiscal_date"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "fiscal_date"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "metrics-history-${var.environment}"
      Purpose = "Pre-computed metrics by quarter for follow-up agent"
      TTL     = "90 days"
    }
  )
}
```

### Key Settings

| Setting | Value | Rationale |
|---------|-------|-----------|
| Billing Mode | PAY_PER_REQUEST | Unpredictable query patterns |
| TTL | 90 days | Matches financial data cache |
| Encryption | KMS | Security compliance |
| PITR | Configurable | Disaster recovery |

---

## Verification Commands

### Check Item Count for Ticker

```bash
aws dynamodb query \
  --table-name metrics-history-dev \
  --key-condition-expression "ticker = :t" \
  --expression-attribute-values '{":t":{"S":"AAPL"}}' \
  --select COUNT
# Expected: 20 items
```

### Query Specific Quarter

```bash
aws dynamodb get-item \
  --table-name metrics-history-dev \
  --key '{"ticker":{"S":"AAPL"},"fiscal_date":{"S":"2025-09-27"}}'
```

### Test Action Group via Lambda

```bash
aws lambda invoke \
  --function-name buffett-dev-followup-action \
  --payload '{
    "actionGroup": "ReportResearch",
    "apiPath": "/getMetricsHistory",
    "httpMethod": "POST",
    "requestBody": {
      "content": {
        "application/json": {
          "properties": [
            {"name": "ticker", "value": "AAPL"},
            {"name": "metric_type", "value": "debt_leverage"},
            {"name": "quarters", "value": "12"}
          ]
        }
      }
    }
  }' response.json
```

---

## Related Documentation

- [Follow-up Agent Architecture](./FOLLOWUP_AGENT.md)
- [Section Schema Changelog](./SECTION_SCHEMA_CHANGELOG.md)
- [Chunk Streaming Plan](./CHUNK_STREAMING_PLAN.md)

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-01-19 | 2.0 | Optimized schema: 20 items per ticker with embedded categories, fiscal_date sort key |
| 2026-01-18 | 1.0 | Initial schema: 140 items per ticker (7 categories × 20 quarters) |
