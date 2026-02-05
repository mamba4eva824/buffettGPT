# API Gateway Architecture Guide

This guide provides a comprehensive overview of the API Gateway configuration for the Buffett Chat API, covering both HTTP and WebSocket APIs, their routes, integrations, and operational aspects.

## Table of Contents

1. [Overview](#overview)
2. [Module Structure](#module-structure)
3. [HTTP API Configuration](#http-api-configuration)
4. [WebSocket API Configuration](#websocket-api-configuration)
5. [CORS Configuration](#cors-configuration)
6. [Lambda Integrations](#lambda-integrations)
7. [Authorization & Authentication](#authorization--authentication)
8. [Throttling & Rate Limiting](#throttling--rate-limiting)
9. [Logging & Monitoring](#logging--monitoring)
10. [Environment-Specific Settings](#environment-specific-settings)
11. [API Usage Examples](#api-usage-examples)
12. [Module Inputs & Outputs](#module-inputs--outputs)

---

## Overview

The Buffett Chat API uses AWS API Gateway v2 to provide two types of APIs:

| API Type | Protocol | Purpose |
|----------|----------|---------|
| **HTTP API** | REST/HTTP | Synchronous operations (CRUD, search, auth) |
| **WebSocket API** | WebSocket | Real-time bidirectional chat communication |

**Key Design Decisions:**
- HTTP API for stateless operations (conversations, search, authentication)
- WebSocket API for real-time chat with persistent connections
- Lambda proxy integrations for all routes
- Optional JWT-based authorization
- Environment-specific throttling and logging

---

## Module Structure

**Location:** `chat-api/terraform/modules/api-gateway/`

```
api-gateway/
├── main.tf          # Primary resource definitions (HTTP & WebSocket APIs)
├── variables.tf     # Input variables and configuration
└── outputs.tf       # Module outputs (endpoints, ARNs)
```

**Module Architecture:**
- HTTP API Gateway resources
- WebSocket API Gateway resources
- CloudWatch logging configuration
- JWT authorizers (optional)
- Route definitions and Lambda integrations
- Lambda permissions for API Gateway invocation

---

## HTTP API Configuration

### API Resource

```terraform
Name: {project_name}-{environment}-http-api
Protocol: HTTP
Description: HTTP API for chat functionality
```

### Route Definitions

| Route | Method | Lambda Target | Auth | Purpose |
|-------|--------|---------------|------|---------|
| `/chat` | POST | chat_http_handler | CUSTOM* | Process chat messages |
| `/chat` | OPTIONS | chat_http_handler | NONE | CORS preflight |
| `/health` | GET | chat_http_handler | NONE | Health check endpoint |
| `/api/v1/chat/history/{session_id}` | GET | chat_http_handler | CUSTOM* | Retrieve chat history |
| `/conversations` | GET | conversations_handler | CUSTOM* | List all conversations |
| `/conversations` | POST | conversations_handler | CUSTOM* | Create new conversation |
| `/conversations` | OPTIONS | conversations_handler | NONE | CORS preflight |
| `/conversations/{conversation_id}` | GET | conversations_handler | CUSTOM* | Get specific conversation |
| `/conversations/{conversation_id}` | PUT | conversations_handler | CUSTOM* | Update conversation |
| `/conversations/{conversation_id}` | DELETE | conversations_handler | CUSTOM* | Delete conversation |
| `/conversations/{conversation_id}` | OPTIONS | conversations_handler | NONE | CORS preflight |
| `/conversations/{conversation_id}/messages` | GET | conversations_handler | CUSTOM* | Get conversation messages |
| `/conversations/{conversation_id}/messages` | OPTIONS | conversations_handler | NONE | CORS preflight |
| `/search` | POST | search_handler | NONE | AI-powered search |
| `/search` | OPTIONS | search_handler | NONE | CORS preflight |
| `/auth/callback` | POST | auth_callback | NONE | OAuth callback handler |
| `/auth/callback` | OPTIONS | auth_callback | NONE | CORS preflight |

*CUSTOM authorization enabled when `enable_authorization = true`

### Integration Configuration

```terraform
Integration Type: AWS_PROXY (Lambda proxy)
Payload Format Version: 2.0
Integration Method: POST
Timeout: 30,000ms (30 seconds)
Request Parameters:
  - overwrite:header.x-request-id = $request.header.x-request-id
```

### Stage Configuration

```terraform
Stage Name: {environment} (dev/staging/prod)
Auto Deploy: true
Detailed Metrics: enabled
Logging Level: INFO
Data Trace: enabled (dev/staging), disabled (prod)
```

---

## WebSocket API Configuration

### API Resource

```terraform
Name: {project_name}-{environment}-websocket-api
Protocol: WEBSOCKET
Route Selection Expression: $request.body.action
Description: WebSocket API for real-time chat
```

### Route Definitions

| Route | Lambda Target | Auth | Purpose |
|-------|---------------|------|---------|
| `$connect` | websocket_connect | CUSTOM* | Handle new connections |
| `$disconnect` | websocket_disconnect | NONE | Handle disconnections |
| `$default` | websocket_message | NONE | Handle unnamed messages |
| `ping` | websocket_message | NONE | Keepalive ping handler |

*CUSTOM authorization enabled when `enable_authorization = true`

### Connection Management

**Query Parameters Supported:**
```
?session_id=xxx           # User session identifier
?conversation_id=yyy      # Link to existing conversation
?token=zzz               # JWT token (if auth enabled)
```

**Connection Tracking:**
- Connection IDs stored in DynamoDB `websocket_connections` table
- Supports both authenticated and anonymous users
- Automatic cleanup on disconnect

### Integration Configuration

```terraform
Integration Type: AWS_PROXY
Payload Format Version: 1.0
Integration Method: POST
```

---

## CORS Configuration

### Allowed Headers

```
content-type
x-amz-date
authorization
x-api-key
x-amz-security-token
x-amz-user-agent
x-session-id
x-conversation-id
```

### Allowed Methods

```
GET, POST, PUT, DELETE, OPTIONS
```

### Exposed Headers

```
x-session-id
x-request-id
x-conversation-id
```

### Allowed Origins by Environment

| Environment | Allowed Origins |
|-------------|-----------------|
| **Dev** | `http://localhost:5173`, `http://localhost:5174`, `http://localhost:3000`, `http://localhost:4173`, `http://127.0.0.1:5173` |
| **Staging** | CloudFront URL (if configured) |
| **Prod** | CloudFront URL only |

### Configuration Details

```terraform
Allow Credentials: true
Max Age: 86400 seconds (24 hours)
```

---

## Lambda Integrations

### Function Mappings

| Function Name | Handler | Timeout | Memory | Routes |
|---------------|---------|---------|--------|--------|
| `chat_http_handler` | chat_http_handler.lambda_handler | 30s | 256MB | /chat, /health, /api/v1/chat/history/* |
| `websocket_connect` | websocket_connect.lambda_handler | 30s | 256MB | $connect |
| `websocket_disconnect` | websocket_disconnect.lambda_handler | 30s | 256MB | $disconnect |
| `websocket_message` | websocket_message.lambda_handler | 30s | 256MB | $default, ping |
| `conversations_handler` | conversations_handler.lambda_handler | 30s | 256MB | /conversations/* |
| `search_handler` | search_handler.lambda_handler | 60s | 256MB | /search |
| `auth_callback` | auth_callback.lambda_handler | 30s | 256MB | /auth/callback |

### Lambda Permissions

API Gateway is granted permission to invoke each Lambda function:

```terraform
Statement ID: AllowExecutionFromHTTPAPI / AllowExecutionFromWebSocketAPI
Action: lambda:InvokeFunction
Principal: apigateway.amazonaws.com
Source ARN: {api_execution_arn}/*/*
```

### Environment Variables

Common variables passed to all handlers:

```
ENVIRONMENT                    = dev|staging|prod
PROJECT_NAME                   = buffett
LOG_LEVEL                      = DEBUG|INFO|WARNING
CHAT_SESSIONS_TABLE            = buffett-{env}-chat-sessions
CHAT_MESSAGES_TABLE            = buffett-{env}-chat-messages
CONVERSATIONS_TABLE            = buffett-{env}-conversations
WEBSOCKET_CONNECTIONS_TABLE    = buffett-{env}-websocket-connections
ENHANCED_RATE_LIMITS_TABLE     = buffett-{env}-enhanced-rate-limits
KMS_KEY_ID                     = {kms-key-id}
CHAT_PROCESSING_QUEUE_URL      = {sqs-queue-url}
BEDROCK_AGENT_ID               = {agent-id}
BEDROCK_AGENT_ALIAS            = {agent-alias}
WEBSOCKET_API_ENDPOINT         = {api-id}.execute-api.us-east-1.amazonaws.com/{stage}
```

---

## Authorization & Authentication

### Authorizer Configuration

**HTTP API Authorizer:**
```terraform
Type: REQUEST
Identity Sources: $request.header.Authorization
Payload Format: 2.0
Simple Responses: enabled
```

**WebSocket API Authorizer:**
```terraform
Type: REQUEST
Trigger: $connect route only
```

### Authentication Flow

**HTTP API with Auth Enabled:**
1. Client sends request with `Authorization: Bearer {jwt_token}`
2. API Gateway invokes authorizer Lambda (auth_verify)
3. Authorizer validates JWT and returns allow/deny policy
4. If allowed, request proceeds with authorizer context

**WebSocket with Auth Enabled:**
1. Client connects with `?token={jwt_token}` query parameter
2. `$connect` route triggers authorizer
3. Authorizer validates JWT and returns policy
4. Connection metadata stored in DynamoDB

**Anonymous Access:**
- When `enable_authorization = false`, routes are public
- Users identified via device fingerprinting and session IDs
- Application-level rate limiting still enforced

### Auth Module (Optional)

Located at `chat-api/terraform/modules/auth/`:
- OAuth Provider: Google OAuth 2.0
- Auth Callback: Handles OAuth redirects, generates JWT
- Auth Verify: Validates JWT tokens for authorizer
- Storage: Users table in DynamoDB
- Secrets: Google OAuth credentials in AWS Secrets Manager

---

## Throttling & Rate Limiting

### API Gateway Level

| Setting | Dev | Staging | Prod |
|---------|-----|---------|------|
| **Burst Limit** | 500 | 500 | 2000 |
| **Rate Limit** | 100 req/s | 100 req/s | 1000 req/s |

**Behavior:**
- **Rate Limit:** Maximum sustained request rate
- **Burst Limit:** Maximum concurrent requests
- **Exceeding Limits:** Returns HTTP 429 (Too Many Requests)

### Application Level

Additional rate limiting implemented in Lambda handlers:

```python
ANONYMOUS_MONTHLY_LIMIT = 5
AUTHENTICATED_MONTHLY_LIMIT = 500
ENABLE_RATE_LIMITING = true
RATE_LIMIT_GRACE_PERIOD_HOURS = 1
ENABLE_DEVICE_FINGERPRINTING = true
```

**Storage:** `buffett-{env}-enhanced-rate-limits` DynamoDB table

### Rate Limit Headers

Responses include tracking headers:
- `x-request-id`: Request identifier
- `x-session-id`: Session identifier
- `x-conversation-id`: Conversation identifier

---

## Logging & Monitoring

### CloudWatch Log Groups

```
HTTP API:      /aws/apigateway/{project_name}-{environment}-http-api
WebSocket API: /aws/apigateway/{project_name}-{environment}-websocket-api
Lambda:        /aws/lambda/{project_name}-{environment}-{function_name}
```

### Log Retention

| Environment | API Gateway Logs | Lambda Logs |
|-------------|------------------|-------------|
| Dev | 30 days | 7 days |
| Staging | 30 days | 14 days |
| Prod | 90 days | 30 days |

### Access Log Format (JSON)

```json
{
  "requestId": "$context.requestId",
  "ip": "$context.identity.sourceIp",
  "caller": "$context.identity.caller",
  "user": "$context.identity.user",
  "requestTime": "$context.requestTime",
  "httpMethod": "$context.httpMethod",
  "resourcePath": "$context.resourcePath",
  "status": "$context.status",
  "protocol": "$context.protocol",
  "responseLength": "$context.responseLength",
  "error": "$context.error.message",
  "integrationError": "$context.integration.error"
}
```

### Monitoring Features

- **Detailed Metrics:** Enabled for all stages
- **Logging Level:** INFO (dev uses DEBUG)
- **Data Trace:** Full request/response logging (disabled in prod)

---

## Environment-Specific Settings

### Dev Environment

```terraform
Location: chat-api/terraform/environments/dev/

Log Level: DEBUG
Data Trace: Enabled
Search Routes: Enabled
Authentication: Optional (disabled by default)
DynamoDB: On-demand billing
Lambda Concurrency: 2
CORS Origins: Localhost variants
Throttling: 100 req/s, 500 burst
```

### Staging Environment

```terraform
Location: chat-api/terraform/environments/staging/

Log Level: INFO
Data Trace: Enabled
Search Routes: Variable
Authentication: Optional
DynamoDB: Provisioned billing
Lambda Concurrency: Scalable
CORS Origins: CloudFront URL + staging domains
Throttling: 100 req/s, 500 burst
```

### Production Environment

```terraform
Location: chat-api/terraform/environments/prod/

Log Level: INFO
Data Trace: Disabled (security)
Search Routes: Variable
Authentication: Required
DynamoDB: Provisioned with PITR
Lambda Concurrency: Production scale
CORS Origins: CloudFront URL only
Throttling: 1000 req/s, 2000 burst
```

---

## API Usage Examples

### HTTP API Requests

**Health Check:**
```bash
GET https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/health
```

**Chat Request (with auth):**
```bash
POST https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/chat
Headers:
  Authorization: Bearer {jwt_token}
  Content-Type: application/json
Body:
  {
    "message": "What is Warren Buffett's investment philosophy?"
  }
```

**List Conversations:**
```bash
GET https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/conversations
Headers:
  Authorization: Bearer {jwt_token}
```

**Create Conversation:**
```bash
POST https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/conversations
Headers:
  Authorization: Bearer {jwt_token}
  Content-Type: application/json
Body:
  {
    "title": "Investment Strategy",
    "description": "Discuss long-term investing"
  }
```

**Get Conversation Messages:**
```bash
GET https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/conversations/{id}/messages
Headers:
  Authorization: Bearer {jwt_token}
```

**Search:**
```bash
POST https://{api-id}.execute-api.us-east-1.amazonaws.com/dev/search
Content-Type: application/json
Body:
  {
    "query": "dividend stocks"
  }
```

### WebSocket Connection

**Connect with Conversation ID:**
```javascript
const ws = new WebSocket(
  'wss://{api-id}.execute-api.us-east-1.amazonaws.com/dev?conversation_id=conv-123'
);
```

**Connect with Auth Token:**
```javascript
const ws = new WebSocket(
  'wss://{api-id}.execute-api.us-east-1.amazonaws.com/dev?token={jwt_token}'
);
```

**Send Message:**
```javascript
ws.send(JSON.stringify({
  action: "send_message",
  message: "Tell me about value investing"
}));
```

**Keepalive Ping:**
```javascript
ws.send(JSON.stringify({ action: "ping" }));
```

---

## Module Inputs & Outputs

### Required Variables

```terraform
variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/staging/prod)"
  type        = string
}

variable "lambda_arns" {
  description = "Map of Lambda function ARNs"
  type        = map(string)
  # Required keys: chat_http_handler, websocket_connect,
  # websocket_disconnect, websocket_message, conversations_handler
}
```

### Optional Variables

```terraform
variable "enable_cors" {
  description = "Enable CORS for API Gateway"
  type        = bool
  default     = true
}

variable "enable_authorization" {
  description = "Enable JWT authorization"
  type        = bool
  default     = false
}

variable "enable_conversations_routes" {
  description = "Enable conversation management routes"
  type        = bool
  default     = true
}

variable "enable_auth_routes" {
  description = "Enable auth callback routes"
  type        = bool
  default     = true
}

variable "enable_search" {
  description = "Enable AI search routes"
  type        = bool
  default     = false
}

variable "cloudfront_url" {
  description = "CloudFront URL for CORS allowed origins"
  type        = string
  default     = ""
}

variable "authorizer_function_arn" {
  description = "ARN of authorizer Lambda (if auth enabled)"
  type        = string
  default     = null
}
```

### Outputs

```terraform
output "http_api_id" {
  description = "ID of the HTTP API Gateway"
}

output "http_api_endpoint" {
  description = "HTTP API endpoint URL"
  # Format: https://{api-id}.execute-api.{region}.amazonaws.com/{stage}
}

output "websocket_api_id" {
  description = "ID of the WebSocket API Gateway"
}

output "websocket_api_endpoint" {
  description = "WebSocket API endpoint URL"
  # Format: wss://{api-id}.execute-api.{region}.amazonaws.com/{stage}
}

output "http_api_execution_arn" {
  description = "Execution ARN for HTTP API"
}

output "websocket_api_execution_arn" {
  description = "Execution ARN for WebSocket API"
}

output "api_gateway_log_groups" {
  description = "CloudWatch log group names"
}
```

---

## Important Notes

1. **Timeout Limits:** API Gateway has a maximum timeout of 30 seconds. The `chat_processor` Lambda (120s timeout) is triggered asynchronously via SQS, not directly through API Gateway.

2. **Payload Format Versions:**
   - HTTP API: Version 2.0 (newer format with simplified event structure)
   - WebSocket API: Version 1.0 (legacy format)

3. **Circular Dependency Prevention:** WebSocket API endpoint is passed to Lambda via environment variables to avoid circular dependency between API Gateway and Lambda modules.

4. **Request ID Propagation:** The `x-request-id` header is overwritten at the integration level to ensure consistent request tracking across logs.

5. **Custom Domains:** Not configured directly in API Gateway. Custom domains are handled via CloudFront, which provides HTTPS with custom domain support.

---

*Last updated: November 2024*
