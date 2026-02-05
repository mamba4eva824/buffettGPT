# Buffett Chat API - Complete System Architecture Overview

## Table of Contents
1. [System Overview](#system-overview)
2. [Infrastructure Stack](#infrastructure-stack)
3. [Authentication & Authorization](#authentication--authorization)
4. [Data Flow Architecture](#data-flow-architecture)
5. [API Routes & Endpoints](#api-routes--endpoints)
6. [Database Architecture](#database-architecture)
7. [Frontend Integration](#frontend-integration)
8. [Deployment & Infrastructure as Code](#deployment--infrastructure-as-code)

## System Overview

The Buffett Chat API is a serverless, event-driven architecture built on AWS that provides a conversational AI interface with Google OAuth authentication. The system uses WebSocket connections for real-time chat and HTTP APIs for conversation management.

### Key Components
- **Frontend**: React-based web application
- **API Layer**: AWS API Gateway (HTTP API v2 and WebSocket API)
- **Compute**: AWS Lambda functions (Python runtime)
- **Storage**: DynamoDB tables for conversations and messages
- **Authentication**: Google OAuth 2.0 with JWT tokens
- **Infrastructure**: Terraform for Infrastructure as Code
- **Secrets Management**: AWS Secrets Manager

## Infrastructure Stack

### AWS Services Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend (React)                      │
│                   Hosted on CloudFront/S3                    │
└──────────────────┬──────────────────┬──────────────────────┘
                   │                  │
                   ▼                  ▼
        ┌──────────────────┐  ┌──────────────────┐
        │  HTTP API Gateway │  │ WebSocket Gateway │
        │   (API Gateway v2) │  │  (API Gateway v2)  │
        └──────┬───────────┘  └──────┬───────────┘
               │                      │
               ▼                      ▼
    ┌──────────────────────────────────────────────┐
    │           JWT Authorizer Lambda              │
    │         (auth_verify function)               │
    └──────────────────────────────────────────────┘
               │                      │
               ▼                      ▼
    ┌─────────────────┐      ┌─────────────────┐
    │ Lambda Functions │      │ Lambda Functions │
    │   (HTTP APIs)    │      │  (WebSocket)     │
    └────────┬─────────┘      └────────┬─────────┘
             │                          │
             ▼                          ▼
    ┌──────────────────────────────────────────────┐
    │              DynamoDB Tables                  │
    │  • chat-sessions-dev                          │
    │  • chat-messages-dev                          │
    └──────────────────────────────────────────────┘
```

### Lambda Functions
1. **auth_callback** - Handles Google OAuth callback
2. **auth_verify** - JWT token verification for API Gateway
3. **conversations_handler** - Manages conversation CRUD operations
4. **chat_http_handler** - Processes HTTP chat requests
5. **chat_processor** - Core chat processing logic
6. **websocket_connect** - WebSocket connection handler
7. **websocket_message** - WebSocket message handler

### DynamoDB Tables
- **chat-sessions-dev**: Stores conversation metadata
- **chat-messages-dev**: Stores individual messages

## Authentication & Authorization

### Google OAuth 2.0 Flow

```
User → Google OAuth → Callback → JWT Generation → API Access
```

#### Detailed Authentication Flow:

1. **Initial Request**
   ```
   User clicks "Sign in with Google"
   ↓
   Frontend redirects to Google OAuth URL:
   https://accounts.google.com/o/oauth2/v2/auth?
     client_id={GOOGLE_CLIENT_ID}
     &redirect_uri={CALLBACK_URL}
     &response_type=code
     &scope=openid email profile
   ```

2. **Google Authentication**
   ```
   User authenticates with Google
   ↓
   Google redirects to callback URL with authorization code:
   https://api.example.com/auth/callback?code={AUTH_CODE}
   ```

3. **Token Exchange (auth_callback Lambda)**
   ```python
   # Lambda processes the callback
   def lambda_handler(event, context):
       code = event['queryStringParameters']['code']

       # Exchange code for Google tokens
       token_response = requests.post(
           'https://oauth2.googleapis.com/token',
           data={
               'code': code,
               'client_id': GOOGLE_CLIENT_ID,
               'client_secret': GOOGLE_CLIENT_SECRET,
               'redirect_uri': REDIRECT_URI,
               'grant_type': 'authorization_code'
           }
       )

       # Get user info from Google
       user_info = requests.get(
           'https://www.googleapis.com/oauth2/v2/userinfo',
           headers={'Authorization': f'Bearer {access_token}'}
       )

       # Generate JWT token
       jwt_token = jwt.encode({
           'user_id': user_info['id'],
           'email': user_info['email'],
           'iat': current_time,
           'exp': expiry_time
       }, JWT_SECRET, algorithm='HS256')

       # Store user in DynamoDB
       # Return JWT to frontend
   ```

4. **JWT Authorization (auth_verify Lambda)**
   ```python
   def lambda_handler(event, context):
       # Extract token from Authorization header
       token = extract_token(event['headers']['Authorization'])

       # Verify JWT
       payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])

       # Return authorization response
       return {
           "isAuthorized": True,
           "context": {
               "user_id": payload['user_id'],
               "environment": "dev",
               "project": "buffett"
           }
       }
   ```

### Authorization Configuration
- **API Gateway Authorizer**: Custom REQUEST type authorizer
- **Identity Source**: `$request.header.Authorization`
- **Simple Responses**: Enabled for HTTP API v2 compatibility
- **Payload Format**: Version 2.0

## Data Flow Architecture

### 1. Chat Message Flow (WebSocket)

```
User Input → WebSocket API → Lambda → DynamoDB → AI Processing → Response
```

**Detailed Flow:**
1. User connects via WebSocket (`wss://api.example.com/dev`)
2. Connection authenticated by auth_verify Lambda
3. websocket_connect Lambda stores connection in DynamoDB
4. User sends message through WebSocket
5. websocket_message Lambda processes message
6. Message stored in chat-messages-dev table
7. AI response generated and sent back via WebSocket

### 2. Conversation Retrieval Flow (HTTP)

```
Frontend Request → HTTP API → Authorizer → Lambda → DynamoDB → Response
```

**Detailed Flow:**
1. Frontend sends GET request with JWT token
2. API Gateway invokes auth_verify Lambda
3. On successful authorization, conversations_handler invoked
4. Lambda queries DynamoDB for user's conversations
5. Results returned to frontend

## API Routes & Endpoints

### HTTP API Endpoints

#### Base URL: `https://api.buffettchat.com/dev`

| Method | Endpoint | Description | Authorization | Handler |
|--------|----------|-------------|---------------|---------|
| OPTIONS | /conversations | CORS preflight | None | conversations_handler |
| GET | /conversations | List user conversations | JWT Required | conversations_handler |
| POST | /conversations | Create new conversation | JWT Required | conversations_handler |
| GET | /conversations/{id} | Get specific conversation | JWT Required | conversations_handler |
| PUT | /conversations/{id} | Update conversation | JWT Required | conversations_handler |
| DELETE | /conversations/{id} | Delete conversation | JWT Required | conversations_handler |
| GET | /conversations/{id}/messages | Get conversation messages | JWT Required | conversations_handler |
| POST | /chat | Send chat message (HTTP) | JWT Required | chat_http_handler |
| GET | /auth/callback | Google OAuth callback | None | auth_callback |

### WebSocket API Endpoints

#### Base URL: `wss://ws.buffettchat.com/dev`

| Route | Description | Handler |
|-------|-------------|---------|
| $connect | WebSocket connection | websocket_connect |
| $disconnect | WebSocket disconnection | Built-in |
| $default | Message routing | websocket_message |

### Request/Response Formats

#### Authentication Header
```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

#### Conversation List Response
```json
{
  "conversations": [
    {
      "conversation_id": "uuid",
      "user_id": "google_user_id",
      "title": "Chat Title",
      "created_at": "timestamp",
      "updated_at": "timestamp",
      "message_count": "2",
      "is_archived": false,
      "user_type": "authenticated",
      "metadata": {}
    }
  ],
  "count": 16
}
```

#### WebSocket Message Format
```json
{
  "action": "sendMessage",
  "message": "User message text",
  "conversation_id": "uuid"
}
```

## Database Architecture

### DynamoDB Schema

#### Table: chat-sessions-dev
**Primary Key**: conversation_id (String)
**Global Secondary Index**: user_id-updated_at-index

| Attribute | Type | Description |
|-----------|------|-------------|
| conversation_id | String | UUID for conversation |
| user_id | String | Google OAuth user ID |
| title | String | Conversation title |
| created_at | String/Number | Creation timestamp |
| updated_at | String/Number | Last update timestamp |
| message_count | String | Number of messages |
| is_archived | Boolean | Archive status |
| user_type | String | "authenticated" or "guest" |
| metadata | Map | Additional conversation data |

#### Table: chat-messages-dev
**Primary Key**: conversation_id (String)
**Sort Key**: message_id (String)

| Attribute | Type | Description |
|-----------|------|-------------|
| conversation_id | String | Reference to parent conversation |
| message_id | String | UUID for message |
| user_id | String | Message sender ID |
| content | String | Message content |
| role | String | "user" or "assistant" |
| timestamp | String/Number | Message timestamp |
| metadata | Map | Additional message data |

### Database Access Patterns

1. **Get User Conversations**
   - Query: GSI on user_id with updated_at sort
   - Access pattern: List all conversations for a user

2. **Get Conversation Messages**
   - Query: Primary key on conversation_id
   - Access pattern: Retrieve all messages in a conversation

3. **WebSocket Connection Tracking**
   - Item: connection_id as key
   - Access pattern: Store/retrieve WebSocket connections

## Frontend Integration

### Technology Stack
- **Framework**: React
- **State Management**: React Hooks (useState, useEffect)
- **API Client**: Fetch API
- **Authentication**: localStorage for JWT storage

### API Integration Points

#### conversationsApi.js
```javascript
const API_BASE_URL = 'https://api.buffettchat.com/dev';

export const conversationsApi = {
  getConversations: async () => {
    const token = localStorage.getItem('authToken');
    const response = await fetch(`${API_BASE_URL}/conversations`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    });
    return response.json();
  },

  createConversation: async (data) => {
    // POST implementation
  },

  getMessages: async (conversationId) => {
    // GET messages implementation
  }
};
```

### Authentication Flow in Frontend
1. User clicks "Sign in with Google"
2. Redirected to Google OAuth
3. Callback returns JWT token
4. Token stored in localStorage
5. Token included in all API requests
6. Token refresh handled on expiration

## Deployment & Infrastructure as Code

### Terraform Structure
```
terraform/
├── environments/
│   └── dev/
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars
└── modules/
    ├── api-gateway/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── auth/
    │   ├── main.tf
    │   └── variables.tf
    ├── dynamodb/
    │   ├── main.tf
    │   └── variables.tf
    └── lambda/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

### Key Terraform Resources

#### API Gateway Configuration
```hcl
resource "aws_apigatewayv2_api" "http_api" {
  name          = "${var.project}-${var.environment}-http-api"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins     = ["http://localhost:3000", "https://app.buffettchat.com"]
    allow_methods     = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    allow_headers     = ["*"]
    expose_headers    = ["*"]
    max_age          = 86400
  }
}

resource "aws_apigatewayv2_authorizer" "http_jwt_authorizer" {
  api_id                           = aws_apigatewayv2_api.http_api.id
  authorizer_type                  = "REQUEST"
  authorizer_uri                   = var.authorizer_function_arn
  name                            = "jwt-authorizer"
  authorizer_payload_format_version = "2.0"
  identity_sources                = ["$request.header.Authorization"]
  enable_simple_responses         = true
}
```

#### Lambda Function Configuration
```hcl
resource "aws_lambda_function" "conversations" {
  function_name = "${var.project}-${var.environment}-conversations"
  runtime       = "python3.11"
  handler       = "conversations_handler.lambda_handler"

  environment {
    variables = {
      SESSIONS_TABLE = var.sessions_table_name
      MESSAGES_TABLE = var.messages_table_name
      ENVIRONMENT    = var.environment
    }
  }

  layers = [var.lambda_layer_arn]
}
```

#### DynamoDB Configuration
```hcl
resource "aws_dynamodb_table" "chat_sessions" {
  name           = "chat-sessions-${var.environment}"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "conversation_id"

  attribute {
    name = "conversation_id"
    type = "S"
  }

  attribute {
    name = "user_id"
    type = "S"
  }

  attribute {
    name = "updated_at"
    type = "S"
  }

  global_secondary_index {
    name            = "user_id-updated_at-index"
    hash_key        = "user_id"
    range_key       = "updated_at"
    projection_type = "ALL"
  }
}
```

### Deployment Process

1. **Build Lambda Packages**
   ```bash
   cd chat-api/backend
   ./scripts/build_lambdas.sh
   # Creates .zip files in build/ directory
   ```

2. **Deploy Infrastructure**
   ```bash
   cd terraform/environments/dev
   terraform init
   terraform plan
   terraform apply
   ```

3. **Environment Variables**
   - JWT_SECRET: Stored in AWS Secrets Manager
   - GOOGLE_CLIENT_ID: Stored in Secrets Manager
   - GOOGLE_CLIENT_SECRET: Stored in Secrets Manager
   - Environment configs in Lambda environment variables

### Security Considerations

1. **Secrets Management**
   - All secrets stored in AWS Secrets Manager
   - Accessed via IAM roles, not hardcoded
   - Automatic rotation supported

2. **Network Security**
   - API Gateway handles TLS termination
   - CORS configured for specific origins
   - WebSocket connections require authentication

3. **Authorization**
   - JWT tokens expire after configured duration
   - Each request validated by authorizer
   - User context passed to Lambda functions

4. **Data Protection**
   - DynamoDB encryption at rest
   - CloudWatch logs encrypted
   - Sensitive data never logged

## Monitoring & Observability

### CloudWatch Integration
- **Lambda Metrics**: Invocation count, duration, errors
- **API Gateway Metrics**: Request count, latency, 4XX/5XX errors
- **DynamoDB Metrics**: Read/write capacity, throttles
- **Custom Metrics**: Business logic metrics

### Logging Strategy
- **Structured Logging**: JSON format for easy parsing
- **Correlation IDs**: Track requests across services
- **Log Levels**: INFO, WARN, ERROR based on severity

## Scalability & Performance

### Serverless Benefits
- **Auto-scaling**: Lambda and DynamoDB scale automatically
- **Pay-per-use**: Cost scales with usage
- **No server management**: AWS handles infrastructure

### Performance Optimizations
- **Lambda Layers**: Shared dependencies reduce package size
- **Connection Pooling**: Reuse database connections
- **Caching**: CloudFront for static assets
- **Async Processing**: WebSocket for real-time communication

## Future Enhancements

### Planned Features
1. **Multi-region Support**: Deploy across AWS regions
2. **Advanced Analytics**: User behavior tracking
3. **Rate Limiting**: API throttling per user
4. **Backup & Recovery**: Automated DynamoDB backups
5. **CI/CD Pipeline**: GitHub Actions for automated deployment

### Architecture Evolution
- Consider EventBridge for event-driven patterns
- Implement Step Functions for complex workflows
- Add ElastiCache for session management
- Integrate Amazon Bedrock for AI capabilities

## Chat History Retrieval - End-to-End Architecture

This section provides a comprehensive overview of how an authorized user can retrieve their chat history, detailing every step from authentication through data retrieval.

### Authentication & Authorization Flow

#### Step 1: JWT Token Generation
When a user authenticates via Google OAuth, the `auth_callback` Lambda generates a JWT token containing:
- `user_id`: Google OAuth user ID
- `email`: User's email address
- `exp`: Token expiration timestamp
- `iat`: Token issued at timestamp

#### Step 2: Token Verification
For every API request to retrieve chat history, the `auth_verify` Lambda:
1. Extracts JWT token from `Authorization: Bearer <token>` header
2. Retrieves JWT secret from AWS Secrets Manager (cached for performance)
3. Verifies token signature using HS256 algorithm
4. Validates token expiration
5. Returns authorization context with user_id to API Gateway

### API Gateway Request Flow

#### HTTP API Configuration
The API Gateway HTTP API v2 is configured with:
- **Custom Authorizer**: Points to `auth_verify` Lambda
- **Authorization Type**: REQUEST authorizer with payload format 2.0
- **Identity Source**: `$request.header.Authorization`
- **Simple Responses**: Enabled for streamlined authorization

#### Protected Endpoints for Chat History
All conversation endpoints require JWT authentication:
```
GET /conversations                          - List all user conversations
GET /conversations/{id}                     - Get specific conversation details
GET /conversations/{id}/messages            - Retrieve messages for a conversation
```

### Lambda Handler Processing

#### conversations_handler.py - User ID Extraction
The handler implements multiple fallback mechanisms to extract user_id:

1. **Primary Path**: `event['requestContext']['authorizer']['lambda']['user_id']`
   - This is where API Gateway v2 places the context from the authorizer

2. **Secondary Paths** (fallbacks):
   - Direct authorizer context: `event['requestContext']['authorizer']['user_id']`
   - JWT decoding from Authorization header (if authorizer fails)
   - Query parameters (for backward compatibility)

#### Request Processing Flow
```python
def list_conversations(event):
    # Extract user_id from authorization context
    user_id = get_user_id(event)

    # Query DynamoDB using Global Secondary Index
    response = conversations_table.query(
        IndexName='user-conversations-index',
        KeyConditionExpression='user_id = :user_id',
        ExpressionAttributeValues={':user_id': user_id},
        ScanIndexForward=False  # Most recent first
    )

    # Filter and format results
    conversations = response.get('Items', [])

    # Return formatted response
    return create_response(200, {
        'conversations': conversations,
        'count': len(conversations)
    })
```

### DynamoDB Data Architecture

#### Conversations Table Schema
**Table Name**: `buffett-{environment}-conversations`
- **Primary Key**: `conversation_id` (String) - Partition key
- **Global Secondary Index**: `user-conversations-index`
  - Partition Key: `user_id` (String)
  - Sort Key: `updated_at` (Number)
  - Projection: ALL attributes

**Attributes**:
- `conversation_id`: UUID v4
- `user_id`: Google OAuth user ID
- `title`: Conversation title
- `created_at`: ISO 8601 timestamp
- `updated_at`: Unix timestamp (for sorting)
- `message_count`: Integer
- `is_archived`: Boolean
- `user_type`: "authenticated" or "anonymous"
- `metadata`: Additional JSON data

#### Messages Table Schema
**Table Name**: `buffett-{environment}-chat-messages`
- **Composite Primary Key**:
  - Partition Key: `conversation_id` (String)
  - Sort Key: `message_id` (String)
- **Local Secondary Index**: `timestamp-index`
  - Sort Key: `timestamp` (Number)

**Attributes**:
- `conversation_id`: Links to parent conversation
- `message_id`: UUID v4
- `user_message`: User's input text
- `assistant_message`: AI response
- `timestamp`: Unix timestamp
- `model_config`: Model parameters used

### Frontend Integration

#### API Client Implementation (conversationsApi.js)
```javascript
// List all conversations for authenticated user
export async function listConversations(token) {
    const response = await fetch(`${API_BASE_URL}/conversations`, {
        method: 'GET',
        headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        }
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
}

// Retrieve complete conversation history
export async function loadConversationHistory(conversationId, token) {
    // Get conversation metadata
    const conversation = await conversationsApi.get(conversationId, token);

    // Get all messages
    const messages = await conversationsApi.getMessages(conversationId, token);

    return {
        conversation,
        messages: messages.messages || []
    };
}
```

### Security & Access Control

#### Ownership Verification
Every operation validates that the requesting user owns the resource:
```python
# In get_conversation handler
conversation = conversations_table.get_item(
    Key={'conversation_id': conversation_id}
)

# Verify ownership
if conversation['user_id'] != user_id:
    return create_response(403, {'error': 'Access denied'})
```

#### DynamoDB Conditional Updates
Archive operations use conditions to ensure ownership:
```python
conversations_table.update_item(
    Key={'conversation_id': conversation_id},
    UpdateExpression='SET is_archived = :archived',
    ConditionExpression='user_id = :user',  # Ownership check
    ExpressionAttributeValues={
        ':archived': True,
        ':user': user_id
    }
)
```

### Complete Request Flow Sequence

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API Gateway
    participant Auth Lambda
    participant Conv Handler
    participant DynamoDB
    participant Secrets Manager

    User->>Frontend: Click "View Chat History"
    Frontend->>Frontend: Retrieve JWT from localStorage
    Frontend->>API Gateway: GET /conversations<br/>Authorization: Bearer {JWT}

    Note over API Gateway: Invoke Authorizer
    API Gateway->>Auth Lambda: Verify JWT token
    Auth Lambda->>Secrets Manager: Get JWT secret (cached)
    Secrets Manager->>Auth Lambda: Return secret
    Auth Lambda->>Auth Lambda: Decode & validate JWT
    Auth Lambda->>API Gateway: Return authorization<br/>context with user_id

    Note over API Gateway: Route to Handler
    API Gateway->>Conv Handler: Forward request<br/>with auth context
    Conv Handler->>Conv Handler: Extract user_id<br/>from context
    Conv Handler->>DynamoDB: Query GSI<br/>user-conversations-index
    DynamoDB->>Conv Handler: Return user's<br/>conversations
    Conv Handler->>Conv Handler: Filter archived<br/>Format timestamps
    Conv Handler->>API Gateway: Return response
    API Gateway->>Frontend: JSON response<br/>200 OK
    Frontend->>User: Display chat history
```

### Performance Optimizations

#### Database Query Optimization
- **GSI Usage**: Queries use `user-conversations-index` for O(1) partition lookup
- **Projection**: ALL attributes projected to avoid additional fetches
- **Sort Order**: `ScanIndexForward=False` returns most recent conversations first

#### Lambda Optimizations
- **Connection Pooling**: DynamoDB clients reused across invocations
- **Secret Caching**: JWT secret cached via `@lru_cache` decorator
- **Minimal Cold Starts**: Python runtime with optimized imports

#### API Gateway Features
- **Request/Response Caching**: Available for GET endpoints
- **Throttling**: Configured per environment (dev: 100 RPS, prod: 1000 RPS)
- **CloudFront Integration**: Static content and API responses cached at edge

### Error Handling & Edge Cases

#### Common Error Scenarios
1. **401 Unauthorized**: Missing or expired JWT token
2. **403 Forbidden**: Valid token but accessing another user's data
3. **404 Not Found**: Conversation doesn't exist
4. **500 Internal Error**: DynamoDB throttling or Lambda errors

#### Error Response Format
```json
{
    "statusCode": 403,
    "body": {
        "error": "Access denied",
        "message": "User does not own this conversation"
    },
    "headers": {
        "X-Environment": "dev",
        "X-Project": "buffett-chat-api"
    }
}
```

### Monitoring & Observability

#### CloudWatch Metrics
- **API Gateway**: Request count, latency, 4XX/5XX errors per endpoint
- **Lambda**: Invocations, duration, concurrent executions, errors
- **DynamoDB**: ConsumedReadCapacityUnits, UserErrors, SystemErrors

#### Structured Logging
```python
logger.info("Listing conversations", extra={
    'user_id': user_id,
    'environment': ENVIRONMENT,
    'request_id': context.aws_request_id,
    'found_count': len(conversations)
})
```

#### Distributed Tracing
- X-Ray integration for request tracing across services
- Request IDs propagated via `x-request-id` headers
- Performance bottleneck identification

### Scalability Considerations

#### Current Limits
- **DynamoDB**: PAY_PER_REQUEST billing (auto-scales)
- **Lambda Concurrency**: 1000 concurrent executions (default)
- **API Gateway**: 10,000 requests per second (default)

#### Future Enhancements
1. **DynamoDB Global Tables**: Multi-region replication
2. **API Response Caching**: CloudFront or API Gateway caching
3. **Read Replicas**: DynamoDB Global Secondary Indexes for read scaling
4. **Pagination**: Implement cursor-based pagination for large conversation lists

## Conclusion

The Buffett Chat API architecture provides a scalable, secure, and maintainable foundation for a conversational AI application. The serverless approach ensures cost-effectiveness while maintaining high availability and performance. The use of Terraform for Infrastructure as Code ensures reproducible deployments and easy environment management.