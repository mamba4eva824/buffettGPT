# BuffettGPT API Routes Reference

## Overview

This document provides a complete reference of all API routes, their associated API Gateways, authentication requirements, and backend Lambda handlers.

---

## API Gateways

| Gateway | Type | Endpoint | Purpose |
|---------|------|----------|---------|
| `buffett-dev-http-api` | HTTP API (v2) | `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev` | Chat, conversations, auth |
| `buffett-dev-analysis-api` | REST API (v1) | `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev` | Investment research |
| `buffett-dev-websocket-api` | WebSocket | `wss://2df7w41edl.execute-api.us-east-1.amazonaws.com/dev` | Real-time chat |

---

## HTTP API Routes (`buffett-dev-http-api`)

**Base URL:** `https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev`

### Health & System

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/health` | None | `buffett-dev-chat-http-handler` | System health check |

### Authentication

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/auth/callback` | None | `buffett-dev-auth-callback` | Google OAuth callback |
| OPTIONS | `/auth/callback` | None | `buffett-dev-auth-callback` | CORS preflight |

### Chat

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/chat` | JWT | `buffett-dev-chat-http-handler` | Send chat message |
| OPTIONS | `/chat` | None | `buffett-dev-chat-http-handler` | CORS preflight |
| GET | `/api/v1/chat/history/{session_id}` | JWT | `buffett-dev-chat-http-handler` | Get chat history |

### Conversations

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/conversations` | JWT | `buffett-dev-conversations-handler` | List user conversations |
| POST | `/conversations` | JWT | `buffett-dev-conversations-handler` | Create new conversation |
| OPTIONS | `/conversations` | None | `buffett-dev-conversations-handler` | CORS preflight |
| GET | `/conversations/{conversation_id}` | JWT | `buffett-dev-conversations-handler` | Get conversation details |
| PUT | `/conversations/{conversation_id}` | JWT | `buffett-dev-conversations-handler` | Update conversation (metadata/state) |
| DELETE | `/conversations/{conversation_id}` | JWT | `buffett-dev-conversations-handler` | Delete conversation |
| OPTIONS | `/conversations/{conversation_id}` | None | `buffett-dev-conversations-handler` | CORS preflight |
| GET | `/conversations/{conversation_id}/messages` | JWT | `buffett-dev-conversations-handler` | Get conversation messages |
| POST | `/conversations/{conversation_id}/messages` | JWT | `buffett-dev-conversations-handler` | Add message to conversation |
| OPTIONS | `/conversations/{conversation_id}/messages` | None | `buffett-dev-conversations-handler` | CORS preflight |

### Search

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/search` | None | `buffett-dev-search-handler` | Experimental search |
| OPTIONS | `/search` | None | `buffett-dev-search-handler` | CORS preflight |

---

## REST API Routes (`buffett-dev-analysis-api`)

**Base URL:** `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev`

### Investment Research

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/research/report/{ticker}/status` | JWT | `buffett-dev-investment-research` | Check report existence/expiration |
| OPTIONS | `/research/report/{ticker}/status` | None | `buffett-dev-investment-research` | CORS preflight |
| GET | `/research/report/{ticker}/stream` | JWT | `buffett-dev-investment-research` | Stream full report (SSE) |
| OPTIONS | `/research/report/{ticker}/stream` | None | `buffett-dev-investment-research` | CORS preflight |
| GET | `/research/report/{ticker}/section/{section_id}` | JWT | `buffett-dev-investment-research` | Fetch single section |
| OPTIONS | `/research/report/{ticker}/section/{section_id}` | None | `buffett-dev-investment-research` | CORS preflight |

### Follow-up Agent

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/research/followup` | JWT | `buffett-dev-analysis-followup` | Ask follow-up questions about reports |
| OPTIONS | `/research/followup` | None | `buffett-dev-analysis-followup` | CORS preflight |

---

## WebSocket API Routes (`buffett-dev-websocket-api`)

**Endpoint:** `wss://2df7w41edl.execute-api.us-east-1.amazonaws.com/dev`

| Route | Lambda | Description |
|-------|--------|-------------|
| `$connect` | `buffett-dev-websocket-connect` | Connection established |
| `$disconnect` | `buffett-dev-websocket-disconnect` | Connection closed |
| `$default` | `buffett-dev-websocket-message` | Handle incoming messages |

### WebSocket Message Flow

```
Client                    API Gateway                Lambda
  │                           │                         │
  │──── WSS Connect ─────────▶│                         │
  │                           │──── $connect ──────────▶│
  │                           │◀─── 200 OK ────────────│
  │◀─── Connection ID ────────│                         │
  │                           │                         │
  │──── Send Message ────────▶│                         │
  │     {action: "chat"}      │──── $default ─────────▶│
  │                           │     (websocket-message) │
  │                           │         │               │
  │                           │         ▼               │
  │                           │    SQS Queue            │
  │                           │         │               │
  │                           │         ▼               │
  │                           │    chat-processor       │
  │◀─── Response ─────────────│◀─── Send to Connection │
  │                           │                         │
```

---

## Authentication

### JWT Authorizer

**Lambda:** `buffett-dev-auth-verify`

All JWT-protected routes use a Lambda authorizer that validates:
- Token signature (HMAC-SHA256)
- Token expiration (`exp` claim)
- Issuer (`iss` = "buffett-chat-api")

**Header Format:**
```
Authorization: Bearer <jwt_token>
```

### Unauthenticated Response

Routes requiring JWT return `401 Unauthorized` when:
- No `Authorization` header present
- Invalid or expired token

```json
{
  "message": "Unauthorized"
}
```

---

## CORS Configuration

### HTTP API CORS Settings

```
Allow Origins:
  - http://localhost:3000
  - http://localhost:5173
  - http://localhost:5174
  - http://127.0.0.1:5173
  - http://localhost:4173

Allow Methods: GET, POST, PUT, DELETE, OPTIONS

Allow Headers:
  - Content-Type
  - Authorization
  - x-api-key
  - x-session-id
  - x-conversation-id
  - x-amz-date
  - x-amz-security-token
  - x-amz-user-agent

Expose Headers:
  - x-session-id
  - x-conversation-id
  - x-request-id

Max Age: 86400 (24 hours)
Allow Credentials: true
```

---

## Lambda Functions Summary

| Lambda | Handler File | Purpose |
|--------|--------------|---------|
| `buffett-dev-chat-http-handler` | `chat_http_handler.py` | HTTP chat, health check |
| `buffett-dev-chat-processor` | `chat_processor.py` | Async message processing with Bedrock |
| `buffett-dev-websocket-connect` | `websocket_connect.py` | WebSocket connection management |
| `buffett-dev-websocket-message` | `websocket_message.py` | WebSocket message handling |
| `buffett-dev-websocket-disconnect` | `websocket_disconnect.py` | WebSocket cleanup |
| `buffett-dev-auth-callback` | `auth_callback.py` | Google OAuth callback |
| `buffett-dev-auth-verify` | `auth_verify.py` | JWT authorizer |
| `buffett-dev-conversations-handler` | `conversations_handler.py` | Conversation CRUD |
| `buffett-dev-search-handler` | `search_handler.py` | Search functionality |
| `buffett-dev-investment-research` | `investment_research/app.py` | Report streaming & sections |
| `buffett-dev-analysis-followup` | `analysis_followup.py` | Follow-up Q&A with Bedrock agent |
| `buffett-dev-followup-action` | `followup_action.py` | Bedrock agent action group |

---

## Bedrock Agents

| Agent | ID | Purpose |
|-------|-----|---------|
| `buffett-dev-followup` | `LWY2A9T2DQ` | Follow-up Q&A about investment reports |

---

## Testing Endpoints

### Health Check (No Auth)
```bash
curl https://yn9nj0b654.execute-api.us-east-1.amazonaws.com/dev/health
```

### Report Status (Requires Auth)
```bash
curl -H "Authorization: Bearer <token>" \
  https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/research/report/AAPL/status
```

### Follow-up Question (Requires Auth)
```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"report_id": "AAPL_2024", "question": "What is the revenue growth?"}' \
  https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/research/followup
```

---

## Archived Routes (Removed)

The following routes were removed as part of the prediction ensemble archival (January 2026):

| Method | Route | Previous Purpose |
|--------|-------|------------------|
| POST | `/analysis/{agent_type}` | Multi-agent ML predictions (debt, cashflow, growth, supervisor) |

See `archived/prediction_ensemble/README.md` for details on the archived system.

---

*Document Version: 1.0*
*Last Updated: January 2026*
