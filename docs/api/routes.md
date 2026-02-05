# API Routes Reference

This document provides a complete reference of all API routes, their associated API Gateways, authentication requirements, and backend Lambda handlers.

## API Gateways

| Gateway | Type | Purpose |
|---------|------|---------|
| HTTP API (v2) | HTTP | Chat, conversations, auth |
| REST API (v1) | REST | Investment research |
| WebSocket API | WebSocket | Real-time chat |

## HTTP API Routes

### Health & System

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/health` | None | `chat-http-handler` | System health check |

### Authentication

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/auth/callback` | None | `auth-callback` | Google OAuth callback |
| OPTIONS | `/auth/callback` | None | `auth-callback` | CORS preflight |

### Chat

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/chat` | JWT | `chat-http-handler` | Send chat message |
| OPTIONS | `/chat` | None | `chat-http-handler` | CORS preflight |
| GET | `/api/v1/chat/history/{session_id}` | JWT | `chat-http-handler` | Get chat history |

### Conversations

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/conversations` | JWT | `conversations-handler` | List user conversations |
| POST | `/conversations` | JWT | `conversations-handler` | Create new conversation |
| GET | `/conversations/{id}` | JWT | `conversations-handler` | Get conversation details |
| PUT | `/conversations/{id}` | JWT | `conversations-handler` | Update conversation |
| DELETE | `/conversations/{id}` | JWT | `conversations-handler` | Delete conversation |
| GET | `/conversations/{id}/messages` | JWT | `conversations-handler` | Get messages |
| POST | `/conversations/{id}/messages` | JWT | `conversations-handler` | Add message |

### Search

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/search` | None | `search-handler` | Experimental search |

## REST API Routes (Investment Research)

### Reports

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| GET | `/research/report/{ticker}/status` | JWT | `investment-research` | Check report status |
| GET | `/research/report/{ticker}/stream` | JWT | `investment-research` | Stream full report (SSE) |
| GET | `/research/report/{ticker}/section/{id}` | JWT | `investment-research` | Fetch single section |

### Follow-up Agent

| Method | Route | Auth | Lambda | Description |
|--------|-------|------|--------|-------------|
| POST | `/research/followup` | JWT | `analysis-followup` | Follow-up Q&A |

## WebSocket API Routes

| Route | Lambda | Description |
|-------|--------|-------------|
| `$connect` | `websocket-connect` | Connection established |
| `$disconnect` | `websocket-disconnect` | Connection closed |
| `$default` | `websocket-message` | Handle incoming messages |

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
  │                           │         │               │
  │                           │         ▼               │
  │                           │    SQS Queue            │
  │                           │         │               │
  │                           │         ▼               │
  │                           │    chat-processor       │
  │◀─── Response ─────────────│◀─── Send to Connection │
```

## Authentication

### JWT Authorizer

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

## CORS Configuration

```
Allow Origins:
  - http://localhost:3000
  - http://localhost:5173
  - (production CloudFront URL)

Allow Methods: GET, POST, PUT, DELETE, OPTIONS

Allow Headers:
  - Content-Type
  - Authorization
  - x-api-key
  - x-session-id
  - x-conversation-id

Expose Headers:
  - x-session-id
  - x-conversation-id
  - x-request-id

Max Age: 86400 (24 hours)
Allow Credentials: true
```

## Lambda Functions Summary

| Lambda | Handler File | Purpose |
|--------|--------------|---------|
| `chat-http-handler` | `chat_http_handler.py` | HTTP chat, health check |
| `chat-processor` | `chat_processor.py` | Async message processing |
| `websocket-connect` | `websocket_connect.py` | WebSocket connection |
| `websocket-message` | `websocket_message.py` | WebSocket messages |
| `websocket-disconnect` | `websocket_disconnect.py` | WebSocket cleanup |
| `auth-callback` | `auth_callback.py` | Google OAuth callback |
| `auth-verify` | `auth_verify.py` | JWT authorizer |
| `conversations-handler` | `conversations_handler.py` | Conversation CRUD |
| `search-handler` | `search_handler.py` | Search functionality |
| `investment-research` | `investment_research/app.py` | Report streaming |
| `analysis-followup` | `analysis_followup.py` | Follow-up Q&A |

## Testing Endpoints

### Health Check (No Auth)

```bash
curl https://your-api-url/health
```

### Report Status (Requires Auth)

```bash
curl -H "Authorization: Bearer <token>" \
  https://your-api-url/research/report/AAPL/status
```

### Follow-up Question (Requires Auth)

```bash
curl -X POST \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"report_id": "AAPL_2024", "question": "What is the revenue growth?"}' \
  https://your-api-url/research/followup
```
