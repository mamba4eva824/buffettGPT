# DynamoDB Schema

This document covers the DynamoDB table schemas used in BuffettGPT.

## Investment Reports V2 Schema

The v2 schema uses section-based storage for progressive loading.

### Table: `investment-reports-v2`

**Primary Key:**
- Partition Key: `ticker` (String)
- Sort Key: `section_id` (String)

### Item Types

#### Metadata Item (section_id: `00_executive`)

| Attribute | Type | Description |
|-----------|------|-------------|
| ticker | S | Stock symbol |
| section_id | S | "00_executive" |
| toc | L | Array of 13 section entries |
| ratings | M | Investment ratings object |
| executive_summary | S | Merged Part 1 content |
| total_word_count | N | Report word count |
| generated_at | S | ISO timestamp |
| ttl | N | Unix expiration |

#### Section Items

| Attribute | Type | Description |
|-----------|------|-------------|
| ticker | S | Stock symbol |
| section_id | S | "06_growth", "07_profit", etc. |
| title | S | Section title |
| content | S | Markdown content |
| part | N | 1, 2, or 3 |
| icon | S | Lucide icon name |
| word_count | N | Section word count |
| display_order | N | Sort order |

### Section IDs

| ID | Title | Part |
|----|-------|------|
| 00_executive | Metadata + ToC | - |
| 01_executive_summary | Executive Summary | 1 |
| 06_growth | Growth | 2 |
| 07_profit | Profitability | 2 |
| 08_valuation | Valuation | 2 |
| 09_earnings | Earnings Quality | 2 |
| 10_cashflow | Cash Flow | 2 |
| 11_debt | Debt | 2 |
| 12_dilution | Dilution | 2 |
| 13_bull | Bull Case | 2 |
| 14_bear | Bear Case | 2 |
| 15_warnings | Warning Signs | 2 |
| 16_vibe | Vibe Check | 2 |
| 17_realtalk | Real Talk | 3 |

### Global Secondary Indexes

| Index | Hash Key | Range Key | Use Case |
|-------|----------|-----------|----------|
| part-index | ticker | part | Query sections by part |
| generated-at-index | ticker | generated_at | Track generation times |

## Migration History

### V1 → V2 Migration

The v1 schema stored entire reports as a single blob. V2 splits reports into sections for:

- Progressive loading
- Faster initial render
- On-demand section fetching

**Migration Script:**
```bash
python investment_research/migrate_to_v2.py --execute --env dev
```

## Related

- [System Architecture](../architecture/system-overview.md)
- [Changelog](../changelog/CHANGELOG.md)
