# Architecture

This section provides a comprehensive overview of BuffettGPT's system architecture and design decisions.

## Overview

BuffettGPT is built as a serverless, event-driven application on AWS. The architecture emphasizes:

- **Scalability**: Auto-scaling Lambda functions and DynamoDB
- **Security**: KMS encryption, OAuth authentication, rate limiting
- **Real-time Communication**: WebSocket API for streaming responses
- **AI Integration**: Amazon Bedrock with custom knowledge bases and guardrails

## High-Level Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Frontend  │────▶│ API Gateway │────▶│   Lambda    │
│   (React)   │◀────│  (HTTP/WS)  │◀────│  Functions  │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                    ┌──────────────────────────┼──────────────────────────┐
                    │                          │                          │
                    ▼                          ▼                          ▼
             ┌─────────────┐           ┌─────────────┐           ┌─────────────┐
             │  DynamoDB   │           │   Bedrock   │           │     SQS     │
             │  (8 tables) │           │   (Claude)  │           │   (FIFO)    │
             └─────────────┘           └─────────────┘           └─────────────┘
```

## Documentation

| Document | Description |
|----------|-------------|
| [System Overview](system-overview.md) | End-to-end request flow and component interactions |
| [Follow-up Agent](followup-agent.md) | Bedrock agent architecture for Q&A functionality |
| [Multi-Agent Orchestrator](multi-agent-orchestrator.md) | Three-expert system with supervisor |
| [Context Management](context-management.md) | Memory and context handling in Bedrock agents |

## Key Components

### Lambda Functions (9 handlers)

| Handler | Purpose |
|---------|---------|
| `chat_http_handler` | HTTP endpoint for chat requests |
| `chat_processor` | Async SQS consumer with Bedrock |
| `websocket_*` | WebSocket connection management |
| `auth_*` | Google OAuth and JWT verification |
| `conversations_handler` | Chat history management |

### DynamoDB Tables (8 tables)

- `chat-sessions` - Session metadata with TTL
- `chat-messages` - Message history
- `conversations` - Conversation details
- `websocket-connections` - Active connections
- `enhanced-rate-limits` - Device fingerprinting
- `usage-tracking` - Monthly quotas
- `anonymous-sessions` - Anonymous users
- `users` - User profiles

## Design Principles

1. **Infrastructure as Code**: All resources defined in Terraform
2. **Event-Driven**: SQS for async processing, WebSocket for real-time
3. **Security First**: Encryption at rest, rate limiting, input validation
4. **Observable**: CloudWatch dashboards and alerts
