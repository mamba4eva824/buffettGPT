# Follow-up Agent Architecture

This document covers the technical architecture of the Bedrock follow-up agent.

## Overview

The follow-up agent enables users to ask questions about investment reports using natural language. It leverages AWS Bedrock's agent framework with action groups.

## Components

### Bedrock Agent
- Model: Claude Haiku 4.5
- Action Group: ReportResearch
- Lambda: followup-action

### Action Group APIs

| Operation | Description |
|-----------|-------------|
| getReportSection | Retrieve specific report section |
| getReportRatings | Get investment ratings |
| getMetricsHistory | Historical financial metrics |

## Data Flow

```
User Question → Investment Research Lambda → Bedrock Agent
                                                   ↓
                                          Action Group Lambda
                                                   ↓
                                              DynamoDB
```

## Related

- [Follow-up Agent Executive Report](../investment-research/followup-agent.md)
- [System Overview](system-overview.md)
