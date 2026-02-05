# API Reference

This section provides complete documentation for BuffettGPT's HTTP and WebSocket APIs.

## Overview

BuffettGPT exposes two API types:

- **HTTP API**: REST endpoints for chat, authentication, and data retrieval
- **WebSocket API**: Real-time bidirectional communication for streaming responses

## API Endpoints

### HTTP Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat` | Submit a chat message |
| `GET` | `/health` | Health check endpoint |
| `GET` | `/conversations` | Retrieve conversation history |
| `GET` | `/auth/callback` | OAuth callback handler |

### WebSocket Endpoints

| Action | Description |
|--------|-------------|
| `$connect` | Establish WebSocket connection |
| `$disconnect` | Clean up connection |
| `message` | Send chat message |

## Documentation

| Document | Description |
|----------|-------------|
| [Routes](routes.md) | Complete endpoint reference with examples |
| [WebSocket](websocket.md) | WebSocket protocol and message formats |
| [Authentication](authentication.md) | OAuth flow and JWT handling |

## Base URLs

| Environment | HTTP API | WebSocket API |
|-------------|----------|---------------|
| Development | `https://api-dev.your-domain.com` | `wss://ws-dev.your-domain.com` |
| Staging | `https://api-staging.your-domain.com` | `wss://ws-staging.your-domain.com` |
| Production | `https://api.your-domain.com` | `wss://ws.your-domain.com` |

## Authentication

All protected endpoints require a valid JWT token in the `Authorization` header:

```
Authorization: Bearer <jwt_token>
```

Anonymous users receive limited functionality based on device fingerprinting.

## Rate Limiting

| User Type | Monthly Limit |
|-----------|---------------|
| Anonymous | 5 requests |
| Authenticated | 500 requests |

Rate limits are tracked per device fingerprint (IP + User-Agent + CloudFront headers).

## Response Format

All API responses follow a consistent JSON format:

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

Error responses:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message"
  }
}
```
