# Follow-up Agent Architecture

This document covers the technical architecture of the follow-up Q&A agent.

## Overview

The follow-up agent enables users to ask questions about investment reports using natural language. It runs on **AWS Bedrock Runtime** (`converse_stream`) with **inline tools** — it is NOT a Bedrock Agent, and does not use action groups.

## Components

| Component | Implementation |
|-----------|----------------|
| Lambda handler | `chat-api/backend/src/handlers/analysis_followup.py` |
| API | `bedrock_runtime.converse_stream` (Bedrock Runtime, not Bedrock Agents) |
| Model | Claude Haiku 4.5 (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) |
| Tool schemas | `FOLLOWUP_TOOLS` array in the handler (~6 tools) |
| Tool dispatch | `chat-api/backend/src/utils/unified_tool_executor.py::execute_tool()` |
| Streaming | Server-Sent Events via Lambda Function URL + Lambda Web Adapter |

## Tools

| Tool name | Purpose |
|-----------|---------|
| `getReportSection` | Retrieve a specific section of the investment report |
| `getReportRatings` | Get investment ratings (debt / cashflow / growth) |
| `getMetricsHistory` | Historical financial metrics by quarter |
| `getAvailableReports` | List reports cached for a ticker |
| `compareStocks` | Compare metrics across tickers |
| `getFinancialSnapshot` | Latest snapshot of key financials |

Tool definitions are versioned alongside the handler. Adding a tool means: extend `FOLLOWUP_TOOLS` in `analysis_followup.py` AND extend `unified_tool_executor.py::execute_tool()`.

## Data flow

```
User question
    ↓
Function URL (Lambda Function URL with LWA)
    ↓
analysis_followup.py
    ↓
bedrock_runtime.converse_stream(toolConfig=FOLLOWUP_TOOLS)
    ↓
While stop_reason == 'tool_use':
    unified_execute(tool_name, tool_input) → DynamoDB read
    append tool result to messages
    converse_stream(...) again
    ↓
SSE stream → frontend
```

## History

- **2024-12 → 2026-04**: Used Bedrock Agents (`bedrock-agent-runtime.invoke_agent`) with a `ReportResearch` action group routed to a `followup-action` Docker Lambda.
- **2026-05**: Migrated to Bedrock Runtime + inline tools. Bedrock Agent, action group, Docker Lambda, ECR repo, and OpenAPI schema all removed.

## Related

- [Follow-up Agent Executive Report](../investment-research/followup-agent.md)
- [System Overview](system-overview.md)
