# WebSocket API

This document covers the WebSocket protocol for real-time communication in BuffettGPT.

## Overview

The WebSocket API enables:

- Real-time bidirectional communication
- Streaming AI responses with typewriter effect
- Connection state management
- Message ordering via SQS FIFO

## Connection Lifecycle

```
┌─────────┐     ┌─────────────┐     ┌─────────────┐
│ Client  │────▶│  $connect   │────▶│  DynamoDB   │
│         │     │   Lambda    │     │ connections │
└─────────┘     └─────────────┘     └─────────────┘
     │
     │ message
     ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  message    │────▶│    SQS      │────▶│    chat     │
│   Lambda    │     │   FIFO      │     │  processor  │
└─────────────┘     └─────────────┘     └─────────────┘
     │
     │ response
     ▼
┌─────────────┐
│  Client     │◀──── streaming chunks
└─────────────┘
```

## Connecting

### Endpoint

```
wss://{ws-api-id}.execute-api.{region}.amazonaws.com/{stage}
```

### Authentication

Include JWT token as query parameter:

```javascript
const ws = new WebSocket(`${WS_URL}?token=${jwtToken}`);
```

## Message Format

### Client → Server

```json
{
  "action": "message",
  "data": {
    "message": "What is Apple's revenue growth?",
    "sessionId": "uuid-session-id",
    "conversationId": "uuid-conversation-id"
  }
}
```

### Server → Client (Streaming)

Messages are sent as 256-character chunks:

```json
{
  "type": "chunk",
  "data": "Apple's revenue has grown significantly over the past...",
  "sequence": 1
}
```

### Message Types

| Type | Description |
|------|-------------|
| `chunk` | Streaming response chunk |
| `complete` | Response complete signal |
| `error` | Error message |
| `status` | Connection status update |

## Error Handling

### Error Response Format

```json
{
  "type": "error",
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Monthly message limit reached"
  }
}
```

### Common Error Codes

| Code | Description |
|------|-------------|
| `RATE_LIMIT_EXCEEDED` | Monthly quota exhausted |
| `INVALID_SESSION` | Session expired or invalid |
| `CONNECTION_ERROR` | WebSocket connection issue |
| `PROCESSING_ERROR` | AI processing failed |

## Client Implementation

### JavaScript Example

```javascript
class BuffettWebSocket {
  constructor(url, token) {
    this.url = `${url}?token=${token}`;
    this.ws = null;
    this.messageHandlers = [];
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('Connected to BuffettGPT');
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    this.ws.onclose = () => {
      console.log('Disconnected from BuffettGPT');
    };
  }

  sendMessage(message, sessionId, conversationId) {
    this.ws.send(JSON.stringify({
      action: 'message',
      data: { message, sessionId, conversationId }
    }));
  }

  handleMessage(data) {
    switch (data.type) {
      case 'chunk':
        // Append to response display
        this.onChunk(data.data);
        break;
      case 'complete':
        // Response finished
        this.onComplete();
        break;
      case 'error':
        // Handle error
        this.onError(data.error);
        break;
    }
  }
}
```

## Connection Management

### Heartbeat

The API Gateway handles WebSocket keepalive automatically. For long-running connections, implement client-side reconnection:

```javascript
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;

function reconnect() {
  if (reconnectAttempts < maxReconnectAttempts) {
    reconnectAttempts++;
    setTimeout(() => {
      connect();
    }, Math.pow(2, reconnectAttempts) * 1000);
  }
}
```

### Graceful Disconnection

```javascript
ws.close(1000, 'User initiated disconnect');
```

## Rate Limiting

WebSocket connections are subject to the same rate limits as HTTP:

| User Type | Monthly Limit |
|-----------|---------------|
| Anonymous | 5 messages |
| Authenticated | 500 messages |

Rate limit status is sent via `status` messages.
