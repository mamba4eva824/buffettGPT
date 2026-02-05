# Multi-Agent Orchestrator

This document describes the multi-agent orchestration system for investment analysis.

## Overview

The orchestrator coordinates three specialized expert agents plus a supervisor for comprehensive investment analysis.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    SUPERVISOR                            │
│              (Coordinates analysis)                      │
└─────────────────────────────────────────────────────────┘
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
┌─────────┐         ┌─────────┐         ┌─────────┐
│  Debt   │         │ Cashflow│         │ Growth  │
│ Expert  │         │ Expert  │         │ Expert  │
└─────────┘         └─────────┘         └─────────┘
```

## Expert Agents

| Agent | Focus Area |
|-------|------------|
| Debt Expert | Balance sheet health, leverage analysis |
| Cashflow Expert | Operating cash flow, free cash flow |
| Growth Expert | Revenue trends, earnings momentum |
| Supervisor | Coordinates experts, synthesizes recommendations |

## Implementation

Located in: `chat-api/backend/investment_research/multi_agent/`

- `orchestrator.py` - Main orchestration logic
- `task_state.py` - Agent task state tracking

## Related

- [Context Management](context-management.md)
- [System Overview](system-overview.md)
