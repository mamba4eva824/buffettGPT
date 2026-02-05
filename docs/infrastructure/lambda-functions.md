# Lambda Functions

This document covers the Lambda function handlers in BuffettGPT.

## Overview

BuffettGPT uses 11 Lambda functions for different purposes:

| Handler | Trigger | Purpose |
|---------|---------|---------|
| `chat_http_handler` | API Gateway (HTTP) | HTTP chat endpoint |
| `chat_processor` | SQS FIFO | Async message processing |
| `websocket_connect` | API Gateway (WS) | WebSocket connection |
| `websocket_message` | API Gateway (WS) | WebSocket messages |
| `websocket_disconnect` | API Gateway (WS) | Connection cleanup |
| `auth_callback` | API Gateway (HTTP) | OAuth callback |
| `auth_verify` | API Gateway (Authorizer) | JWT verification |
| `conversations_handler` | API Gateway (HTTP) | History retrieval |
| `search_handler` | API Gateway (HTTP) | Search functionality |
| `investment_research` | Function URL | Report streaming |
| `analysis_followup` | Function URL + API Gateway | Follow-up Q&A |

---

## Chat Handlers

### chat_http_handler

**Location**: `chat-api/backend/src/handlers/chat_http_handler.py`

**Purpose**: Handles HTTP-based chat requests for the main BuffettGPT advisor.

**Endpoints**:
- `POST /chat` - Submit chat message
- `GET /health` - Health check

**Business Logic**:
1. Validates incoming chat request
2. Enqueues message to SQS for async processing
3. Returns acknowledgment to client

**Environment Variables**:
- `DYNAMODB_TABLE` - Messages table name
- `SQS_QUEUE_URL` - Processing queue URL

```python
def lambda_handler(event, context):
    path = event.get('rawPath', '')
    method = event.get('requestContext', {}).get('http', {}).get('method')

    if method == 'GET' and path == '/health':
        return health_check()
    elif method == 'POST' and path == '/chat':
        return handle_chat(event)
```

### chat_processor

**Location**: `chat-api/backend/src/handlers/chat_processor.py`

**Trigger**: SQS FIFO Queue

**Purpose**: Processes chat messages asynchronously with Bedrock Agent.

**Business Logic**:
1. Receives message from SQS FIFO queue
2. Invokes Bedrock agent with user message
3. Streams response chunks via WebSocket
4. Stores conversation in DynamoDB

**Flow**:
```
SQS Message → Lambda → Bedrock Agent → WebSocket → DynamoDB
```

```python
def lambda_handler(event, context):
    for record in event['Records']:
        message = json.loads(record['body'])
        process_chat_message(message)
```

---

## WebSocket Handlers

### websocket_connect

**Location**: `chat-api/backend/src/handlers/websocket_connect.py`

**Trigger**: WebSocket `$connect` route

**Purpose**: Establishes WebSocket connection and stores connection metadata.

**Business Logic**:
1. Extracts connection ID from event
2. Optionally validates JWT from query params
3. Stores connection in DynamoDB with user info and timestamp
4. Returns 200 to allow connection

```python
def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    connections_table.put_item(
        Item={
            'connectionId': connection_id,
            'userId': get_user_id(event),
            'connectedAt': datetime.utcnow().isoformat()
        }
    )
```

### websocket_message

**Location**: `chat-api/backend/src/handlers/websocket_message.py`

**Trigger**: WebSocket `message` route

**Purpose**: Receives messages from WebSocket clients and enqueues for processing.

**Business Logic**:
1. Parses message from WebSocket event
2. Validates message format
3. Sends to SQS FIFO queue for ordered processing
4. Uses connection ID as message group for ordering

```python
def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    body = json.loads(event['body'])

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            'connectionId': connection_id,
            'message': body['data']['message']
        }),
        MessageGroupId=connection_id
    )
```

### websocket_disconnect

**Location**: `chat-api/backend/src/handlers/websocket_disconnect.py`

**Trigger**: WebSocket `$disconnect` route

**Purpose**: Cleans up connection state when client disconnects.

**Business Logic**:
1. Extracts connection ID
2. Removes connection record from DynamoDB
3. Optionally logs disconnection for analytics

```python
def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']
    connections_table.delete_item(
        Key={'connectionId': connection_id}
    )
```

---

## Authentication Handlers

### auth_callback

**Location**: `chat-api/backend/src/handlers/auth_callback.py`

**Trigger**: `GET /auth/callback`

**Purpose**: Handles Google OAuth callback and issues JWT tokens.

**Business Logic**:
1. Receives authorization code from Google OAuth
2. Exchanges code for access/refresh tokens
3. Fetches user profile from Google API
4. Creates or updates user in DynamoDB
5. Issues JWT token with user claims
6. Redirects to frontend with token

```python
def lambda_handler(event, context):
    code = event['queryStringParameters']['code']

    # Exchange code for tokens
    tokens = exchange_code_for_tokens(code)

    # Get user profile
    profile = get_google_profile(tokens['access_token'])

    # Create/update user
    user = upsert_user(profile)

    # Issue JWT
    jwt_token = create_jwt(user)

    return redirect_with_token(jwt_token)
```

### auth_verify

**Location**: `chat-api/backend/src/handlers/auth_verify.py`

**Trigger**: API Gateway Lambda Authorizer

**Purpose**: Validates JWT tokens for protected endpoints.

**Business Logic**:
1. Extracts token from Authorization header or query params
2. Validates JWT signature and expiration
3. Returns IAM policy (Allow/Deny)
4. Caches policy for repeated requests (via API Gateway)

**Supports Multiple Formats**:
- REST API TOKEN authorizer
- HTTP API v2 authorizer
- WebSocket authorizer

```python
def lambda_handler(event, context):
    token = extract_token(event)

    try:
        payload = verify_jwt(token)
        return generate_allow_policy(payload['sub'])
    except InvalidTokenError:
        return generate_deny_policy()
```

---

## Data Handlers

### conversations_handler

**Location**: `chat-api/backend/src/handlers/conversations_handler.py`

**Trigger**: API Gateway (HTTP)

**Purpose**: Manages conversation history and message persistence.

**Endpoints**:
- `GET /conversations` - List user's conversations
- `GET /conversations/{id}` - Get conversation details
- `GET /conversations/{id}/messages` - Get messages in conversation
- `POST /conversations/{id}/messages` - Save new message

**Business Logic**:
1. Validates JWT and extracts user ID
2. Queries DynamoDB for user's conversations
3. Supports pagination and filtering
4. Handles message persistence for follow-up Q&A

```python
def lambda_handler(event, context):
    user_id = event['requestContext']['authorizer']['userId']

    conversations = conversations_table.query(
        KeyConditionExpression=Key('userId').eq(user_id)
    )

    return {
        'statusCode': 200,
        'body': json.dumps(conversations['Items'])
    }
```

### search_handler

**Location**: `chat-api/backend/src/handlers/search_handler.py`

**Purpose**: Experimental search functionality (under development).

---

## Investment Research Handlers

### investment_research

**Location**: `chat-api/backend/lambda/investment_research/`

**Trigger**: Lambda Function URL (streaming)

**Purpose**: Streams investment research reports section by section.

**Business Logic**:
1. Receives ticker symbol and user credentials
2. Fetches pre-generated report sections from DynamoDB
3. Streams sections via Server-Sent Events (SSE)
4. Supports report generation via Claude Opus (when needed)

**Endpoints**:
- `GET /health` - Health check
- `GET /report/{ticker}/toc` - Get table of contents
- `GET /report/{ticker}/section/{id}` - Stream section content
- `POST /generate` - Generate new report (if not cached)

**Key Features**:
- Section-by-section streaming for fast TTFB
- Report caching in DynamoDB
- Rating extraction and storage
- FMP API integration for financial data

### analysis_followup

**Location**: `chat-api/backend/src/handlers/analysis_followup.py`

**Trigger**: Lambda Function URL (streaming) + API Gateway (non-streaming)

**Purpose**: Handles follow-up Q&A about investment reports using Bedrock Converse API with tool use.

**Business Logic**:

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATION LOOP                                │
│                                                                      │
│  1. Validate JWT token (from header or Secrets Manager)             │
│  2. Check monthly token usage limit                                  │
│  3. Save user question to DynamoDB                                   │
│  4. Build system prompt with tool definitions                        │
│  5. Call Bedrock converse/converse_stream API                       │
│  6. If stop_reason == "tool_use":                                   │
│     a. Execute tool (getReportSection, getMetricsHistory, etc.)     │
│     b. Append tool result to messages                                │
│     c. Loop back to step 5                                           │
│  7. If stop_reason == "end_turn":                                   │
│     a. Extract final response                                        │
│     b. Save assistant message to DynamoDB                            │
│     c. Record token usage                                            │
│     d. Return response                                               │
└─────────────────────────────────────────────────────────────────────┘
```

**Endpoints**:
- `GET /health` - Health check (no auth required)
- `POST /research/followup` - Submit follow-up question

**Environment Variables**:
| Variable | Purpose |
|----------|---------|
| `FOLLOWUP_MODEL_ID` | Bedrock model (`us.anthropic.claude-haiku-4-5-20251001-v1:0`) |
| `INVESTMENT_REPORTS_V2_TABLE` | Report sections table |
| `METRICS_HISTORY_CACHE_TABLE` | Historical metrics table |
| `TOKEN_USAGE_TABLE` | Token tracking table |
| `CHAT_MESSAGES_TABLE` | Conversation history table |
| `JWT_SECRET_ARN` | Secrets Manager ARN for JWT secret |
| `DEFAULT_TOKEN_LIMIT` | Monthly token limit per user (default: 50000) |

**Tool Definitions**:

| Tool | Purpose | DynamoDB Table |
|------|---------|----------------|
| `getReportSection` | Retrieve report section by ID | investment-reports-v2-dev |
| `getReportRatings` | Get investment ratings/verdict | investment-reports-v2-dev |
| `getMetricsHistory` | Query historical financial metrics | metrics-history-dev |
| `getAvailableReports` | List all available reports | investment-reports-v2-dev |

**Invocation Mode Detection**:

The Lambda detects its invocation source and responds appropriately:

```python
is_function_url = 'http' in request_context
is_api_gateway = (
    event.get('httpMethod') or
    request_context.get('httpMethod') or
    headers.get('x-amzn-apigateway-api-id')
)
```

| Source | Response Format | Streaming |
|--------|-----------------|-----------|
| Function URL | SSE Generator | Yes |
| API Gateway | JSON with statusCode | No |

**Performance**:
- Cold start: ~800ms
- Execution time: 4-8 seconds
- Tokens per query: ~4,000-5,000
- Cost per query: ~$0.006

---

## Building Lambda Packages

### Build All Functions

```bash
cd chat-api/backend
./scripts/build_lambdas.sh
```

### Build Dependencies Layer

```bash
./scripts/build_layer.sh
```

### Output Location

All packages are placed in:
```
chat-api/backend/build/
├── dependencies-layer.zip
├── chat_http_handler.zip
├── chat_processor.zip
├── websocket_connect.zip
├── websocket_message.zip
├── websocket_disconnect.zip
├── auth_callback.zip
├── auth_verify.zip
├── conversations_handler.zip
├── search_handler.zip
└── analysis_followup.zip
```

---

## Environment Variables

### Common Variables

| Variable | Description |
|----------|-------------|
| `ENVIRONMENT` | dev/staging/prod |
| `LOG_LEVEL` | DEBUG/INFO/WARNING/ERROR |
| `AWS_REGION` | AWS region |
| `PROJECT_NAME` | Project identifier (buffett) |

### Handler-Specific Variables

See individual handler sections above for specific environment variables.

---

## Error Handling

All handlers use consistent error handling:

```python
try:
    result = process_request(event)
    return success_response(result)
except ValidationError as e:
    return error_response(400, str(e))
except AuthorizationError as e:
    return error_response(401, str(e))
except TokenLimitExceeded as e:
    return error_response(429, str(e))
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return error_response(500, "Internal server error")
```

---

## Logging

Use environment-controlled log levels:

```python
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
```

### Log Prefixes

For handlers with multiple code paths:
- `[STREAMING]` - Function URL streaming requests
- `[NON-STREAMING]` - API Gateway non-streaming requests
- `[TOOL]` - Tool execution events

---

## Testing

### Run Unit Tests

```bash
cd chat-api/backend
make test
```

### Test Locally

```bash
make run-http
```

### Smoke Tests

CI/CD runs smoke tests via `scripts/smoke_test.sh`:

```bash
./scripts/smoke_test.sh dev
```

Tests health endpoints for:
- Investment Research Lambda
- Analysis Followup Lambda
