# Reference

This section provides quick reference materials, glossary, and troubleshooting guides.

## Quick Links

| Resource | Description |
|----------|-------------|
| [Company Tickers](company-tickers.md) | DJIA 30 ticker list and metadata |
| [Troubleshooting](troubleshooting.md) | Common issues and solutions |

## Environment Variables

### Backend

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Current environment (dev/staging/prod) | - |
| `BEDROCK_AGENT_ID` | Bedrock agent identifier | - |
| `BEDROCK_AGENT_ALIAS` | Agent alias name | - |
| `ANONYMOUS_MONTHLY_LIMIT` | Rate limit for anonymous users | 5 |
| `AUTHENTICATED_MONTHLY_LIMIT` | Rate limit for authenticated users | 500 |

### Frontend

| Variable | Description |
|----------|-------------|
| `VITE_WEBSOCKET_URL` | WebSocket API endpoint |
| `VITE_REST_API_URL` | HTTP API endpoint |
| `VITE_GOOGLE_CLIENT_ID` | OAuth client ID |
| `VITE_ENVIRONMENT` | Current environment |

## AWS Resources

### Secrets Manager

| Secret Name | Purpose |
|-------------|---------|
| `buffett-{env}-google-oauth` | OAuth credentials |
| `buffett-{env}-jwt-secret` | JWT signing secret |
| `buffett-{env}-pinecone-api-key` | Vector DB API key |

### DynamoDB Tables

| Table | Purpose |
|-------|---------|
| `chat-sessions` | Session metadata |
| `chat-messages` | Message history |
| `conversations` | Conversation details |
| `websocket-connections` | Active connections |
| `enhanced-rate-limits` | Rate limiting |
| `usage-tracking` | Monthly quotas |
| `anonymous-sessions` | Anonymous users |
| `users` | User profiles |

## Glossary

| Term | Definition |
|------|------------|
| **Bedrock** | AWS managed service for foundation models |
| **Knowledge Base** | Vector database for RAG retrieval |
| **Guardrails** | Content filtering for AI responses |
| **FIFO Queue** | First-in-first-out SQS message ordering |
| **SSE** | Server-Sent Events for streaming |
| **Device Fingerprint** | Unique identifier from IP + headers |

## Key Files

| File | Purpose |
|------|---------|
| `chat-api/terraform/environments/dev/main.tf` | Dev environment root |
| `chat-api/backend/src/handlers/*.py` | Lambda handlers |
| `frontend/src/App.jsx` | Main React app |
| `.github/workflows/*.yml` | CI/CD pipelines |
