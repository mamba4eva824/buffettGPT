# Buffett Chat API - Architecture Overview

## Table of Contents

1. [Project Overview](#project-overview)
2. [Technology Stack](#technology-stack)
3. [Project Structure](#project-structure)
4. [Frontend Architecture](#frontend-architecture)
5. [Backend Architecture](#backend-architecture)
6. [Infrastructure & AWS Services](#infrastructure--aws-services)
7. [Data Models & Database Schema](#data-models--database-schema)
8. [Integration Patterns & Data Flow](#integration-patterns--data-flow)
9. [AWS Bedrock Agent Configuration](#aws-bedrock-agent-configuration)
10. [API Gateway Configuration](#api-gateway-configuration)
11. [Key Architectural Decisions](#key-architectural-decisions)
12. [Deployment & Operations](#deployment--operations)

---

## Project Overview

The Buffett Chat API is a multi-tiered financial advisory chatbot system built on AWS serverless architecture. It provides investment advice based on Warren Buffett's philosophy and includes specialized debt analysis capabilities powered by AWS Bedrock agents.

**Key Features:**
- Real-time WebSocket-based chat interface
- AI-powered investment advice using Claude 3.5 Sonnet
- Conversational debt analysis with streaming responses
- Persistent conversation history
- Multi-environment deployment (dev/staging/prod)

**Primary AWS Region:** us-east-1

---

## Technology Stack

### Frontend

| Component | Technology | Version |
|-----------|------------|---------|
| Framework | React | 18.2.0 |
| Build Tool | Vite | 5.0.8 |
| Styling | Tailwind CSS | 3.3.6 |
| Icons | Lucide React | 0.294.0 |
| Animation | Framer Motion | 12.23.22 |

### Backend

| Component | Technology | Version |
|-----------|------------|---------|
| Language | Python | 3.11 |
| Runtime | AWS Lambda | Custom containers |
| Core Libraries | boto3, botocore | Latest |
| Authentication | PyJWT, Google Auth | 2.8.0+ |

### Infrastructure

| Component | Technology |
|-----------|------------|
| IaC Tool | Terraform 1.0+ |
| Cloud Provider | AWS |
| State Backend | S3 + DynamoDB |

---

## Project Structure

```
buffett_chat_api/
├── chat-api/
│   ├── backend/
│   │   ├── src/
│   │   │   ├── handlers/           # Lambda function handlers
│   │   │   └── utils/              # Shared utilities
│   │   ├── build/                  # Lambda deployment packages (.zip)
│   │   ├── layer/                  # Lambda layer dependencies
│   │   └── scripts/                # Build and deployment scripts
│   └── terraform/
│       ├── modules/
│       │   ├── core/               # KMS, IAM, SQS
│       │   ├── dynamodb/           # DynamoDB tables
│       │   ├── lambda/             # Lambda functions & layers
│       │   ├── api-gateway/        # HTTP and WebSocket APIs
│       │   └── bedrock/            # Bedrock agents, KB, guardrails
│       │       └── modules/
│       │           ├── agent/
│       │           ├── knowledge-base/
│       │           ├── action-group/
│       │           ├── iam/
│       │           └── guardrails/
│       ├── environments/
│       │   ├── dev/
│       │   ├── staging/
│       │   └── prod/
│       └── prompts/                # Agent instruction prompts
├── frontend/
│   └── src/
│       ├── components/             # React components
│       ├── api/                    # API clients
│       ├── hooks/                  # Custom React hooks
│       └── utils/                  # Utility functions
├── deep_value_insights/            # ML model training infrastructure
└── extract_inference_pipeline/     # Data processing pipelines
```

---

## Frontend Architecture

### Component Structure

```
frontend/src/
├── App.jsx                    # Main app with WebSocket management
├── auth.jsx                   # Google OAuth authentication
├── components/
│   ├── ConversationList.jsx   # Sidebar conversation list
│   ├── DeleteConfirmationModal.jsx
│   └── Avatar.jsx             # User avatar component
├── api/
│   ├── conversationsApi.js    # Conversations CRUD operations
│   ├── analysisApi.js         # Debt analysis API integration
│   └── sseClient.js           # Server-sent events client
├── hooks/
│   └── useConversations.js    # Conversation management hook
└── utils/
    └── logger.js              # Client-side logging
```

### Key Features

**WebSocket Management:**
- Real-time bidirectional communication
- Automatic reconnection with exponential backoff
- Heartbeat mechanism (ping/pong) for connection health
- Session persistence via conversation IDs

**Authentication:**
- Google OAuth 2.0 integration
- JWT token-based API authentication
- Optional anonymous mode for development

**API Clients:**

1. **Conversations API** - CRUD operations for conversation history
   - `GET/POST /conversations`
   - `GET/PUT/DELETE /conversations/{id}`
   - `GET/POST /conversations/{id}/messages`

2. **Analysis API** - Financial analysis endpoints
   - `POST /api/analyze/debt` - Direct debt analysis
   - `POST /api/analyze/debt/conversational` - Conversational analysis
   - `GET /api/analyze/debt/conversational` - Streaming SSE analysis

**Rate Limiting:**
- Client-side daily query limit: 10 queries/day
- Tracked in localStorage with date-based reset

### Environment Configuration

```
VITE_APP_NAME=BuffettGPT
VITE_ENVIRONMENT=development|staging|production
VITE_WEBSOCKET_URL=wss://...
VITE_REST_API_URL=https://...
VITE_DEBT_ANALYSIS_STREAMING_URL=https://...
VITE_ENABLE_DEBUG_LOGS=true|false
```

---

## Backend Architecture

### Lambda Functions

| Function | Timeout | Memory | Purpose |
|----------|---------|--------|---------|
| **chat_http_handler** | 30s | 256 MB | HTTP API chat endpoint |
| **websocket_connect** | 30s | 256 MB | WebSocket connection handler |
| **websocket_disconnect** | 30s | 256 MB | Connection cleanup |
| **websocket_message** | 30s | 256 MB | Routes messages to SQS |
| **chat_processor** | 120s | 512 MB | Processes messages via Bedrock |
| **conversations_handler** | 30s | 256 MB | Conversation CRUD |
| **search_handler** | 60s | 256 MB | AI search with streaming |
| **debt_analysis_agent_handler** | 30s | 256 MB | Debt analysis via Bedrock |

### Handler Details

**websocket_connect.py:**
- Accepts query parameters: `user_id`, `conversation_id`, `token`
- Creates connection record in DynamoDB
- Supports authenticated and anonymous users

**chat_processor.py (SQS Triggered):**
- Consumes messages from chat_processing_queue
- Invokes AWS Bedrock Agent runtime
- Sends streaming responses via WebSocket
- Error handling with DLQ fallback

**conversations_handler.py:**
- Full CRUD operations for conversations
- Message management endpoints
- Supports filtering, pagination, sorting

**debt_analysis_agent_handler.py:**
- Invokes Bedrock Debt Analyst Agent
- Streaming response via Server-Sent Events (SSE)
- CORS handling for cross-origin requests

### Utility Modules

| Module | Purpose |
|--------|---------|
| `logger.py` | Structured logging |
| `rate_limiter.py` | Server-side rate limiting |
| `tiered_rate_limiter.py` | Advanced rate limiting with tiers |
| `device_fingerprint.py` | Device identification |
| `conversation_updater.py` | Conversation metadata helper |

### Lambda Layer

**File:** `chat-api/backend/build/dependencies-layer.zip` (~9.3 MB)

Contains: boto3, botocore, PyJWT, google-auth, requests, python-dateutil

---

## Infrastructure & AWS Services

### AWS Services Used

**Compute:**
- AWS Lambda (8 core functions)

**Messaging & Queuing:**
- Amazon SQS (chat processing queue)
- DLQ (dead-letter queue)

**Data Storage:**
- Amazon DynamoDB (10+ tables)
- Amazon S3 (Terraform state, knowledge base)

**AI/ML Services:**
- Amazon Bedrock (Agent runtime, model inference)
- Bedrock Knowledge Bases (document retrieval)
- Bedrock Guardrails (content safety)
- Claude 3.5 Sonnet (primary model)

**API & Network:**
- API Gateway v2 (HTTP API)
- API Gateway v2 (WebSocket API)
- CloudFront (static assets)

**Security & Encryption:**
- AWS KMS (encryption at rest)
- AWS Secrets Manager (API keys)
- AWS IAM (role-based access)

**Monitoring:**
- Amazon CloudWatch (logs, metrics)
- AWS X-Ray (optional tracing)

---

## Data Models & Database Schema

### Core DynamoDB Tables

**1. Chat Sessions Table**
```
PK: conversation_id (String)
SK: timestamp (Number)
GSI: user-conversations-index (user_id, timestamp)
TTL: expires_at
```

**2. Chat Messages Table**
```
PK: conversation_id
SK: message_id (UUID)
LSI: timestamp-index
TTL: expires_at
```

**3. Conversations Table**
```
PK: conversation_id (UUID)
Attributes: user_id, title, created_at, updated_at, message_count, is_archived
```

**4. WebSocket Connections Table**
```
PK: connection_id
Attributes: user_id, session_id, connected_at, last_activity, expires_at
```

**5. Enhanced Rate Limits Table**
```
PK: device_id | user_id | connection_id
SK: timestamp (day)
Attributes: query_count, reset_at, tier, quota
```

**6. Financial Data Cache Table**
```
PK: ticker (stock symbol)
SK: fiscal_year
Attributes: company_data, financial_metrics, cached_at, ttl
```

### Encryption & Protection

- All tables encrypted with KMS key: `alias/buffett-{environment}`
- Point-in-time recovery: Enabled in prod
- Deletion protection: Enabled in prod
- Billing mode: On-demand (dev), provisioned (prod)

---

## Integration Patterns & Data Flow

### WebSocket Chat Flow

```
User (Browser)
    │
    ▼
API Gateway WebSocket
    │
    ▼
Lambda: websocket_connect
    │ (Creates connection record)
    ▼
DynamoDB: websocket_connections
    │
    ▼
User sends message
    │
    ▼
Lambda: websocket_message
    │ (Routes to SQS)
    ▼
SQS: chat_processing_queue
    │
    ▼
Lambda: chat_processor
    │ (Invokes Bedrock Agent)
    ▼
Bedrock Agent Runtime
    │ (Claude 3.5 Sonnet + Knowledge Base)
    ▼
Lambda: chat_processor
    │ (Formats response)
    ▼
API Gateway Management API
    │ (Sends via WebSocket)
    ▼
User receives real-time response
```

### HTTP REST API Flow

```
Frontend
    │
    ▼
API Gateway HTTP
    │
    ▼
Lambda Functions
    │ (conversations_handler, search_handler, etc.)
    ▼
DynamoDB / Bedrock Agent
    │
    ▼
Response to Frontend
```

### Debt Analysis Streaming Flow

```
Frontend (analysisApi)
    │
    ▼
Lambda Function URL
    │ (debt_analysis_agent_handler)
    ▼
Bedrock Agent Runtime
    │ (Debt Analyst)
    ▼
Server-Sent Events (SSE) Stream
    │
    ▼
Frontend SSEClient
    │ (Real-time UI updates)
```

---

## AWS Bedrock Agent Configuration

### Deployed Agents

**1. BuffettGPT Investment Advisor**
- **Agent ID:** QTFYZ6BBSE
- **Purpose:** Investment advice based on Warren Buffett philosophy
- **Foundation Model:** Claude 3.5 Sonnet
- **Knowledge Base:** Buffett letters, investment documents

**2. Debt Analyst Agent**
- **Agent ID:** ZCIAI0BCN8
- **Purpose:** Conversational debt analysis for companies
- **Foundation Model:** Claude 3.5 Sonnet
- **Input:** Ticker symbol + optional fiscal year

### Versioning Strategy

- **DRAFT:** Mutable working copy
- **Numbered Versions:** Immutable snapshots (v1, v2, etc.)
- **Aliases:** Point to specific versions for routing

**Update Workflow:**
1. Modify Terraform config
2. Run `terraform apply` → Creates new version
3. Test new version via alias
4. Update `agent_version_number` in Terraform
5. Apply → Alias routes to new version

### Prompts Location

`chat-api/terraform/modules/bedrock/prompts/`
- `buffett_advisor_instruction.txt`
- `debt_analyst_instruction.txt`
- `orchestration.txt`
- `kb_response.txt`

---

## API Gateway Configuration

### HTTP API Routes

```
GET    /conversations              → conversations_handler
POST   /conversations              → conversations_handler
GET    /conversations/{id}         → conversations_handler
PUT    /conversations/{id}         → conversations_handler
DELETE /conversations/{id}         → conversations_handler
GET    /conversations/{id}/messages → conversations_handler
POST   /conversations/{id}/messages → conversations_handler

POST   /api/analyze/debt           → debt_analysis_agent_handler
POST   /api/analyze/debt/conversational → debt_analysis_agent_handler
GET    /api/analyze/debt/conversational → debt_analysis_agent_handler
```

### WebSocket API Routes

```
$connect    → websocket_connect
$default    → websocket_message
$disconnect → websocket_disconnect
```

### CORS Configuration

- **Allowed origins:** localhost:* (dev), CloudFront URL (prod)
- **Allowed headers:** content-type, authorization, x-session-id
- **Allowed methods:** GET, POST, PUT, DELETE, OPTIONS
- **Max age:** 86400 seconds (24 hours)

---

## Key Architectural Decisions

### 1. Async Processing with SQS
- **Why:** Decouples WebSocket ingestion from Bedrock processing
- **Benefit:** Handles timeouts, retries, load distribution

### 2. Bedrock Agent Versioning
- **Why:** Enables safe updates without breaking production
- **Benefit:** Instant rollback, canary testing, version history

### 3. WebSocket for Real-time Chat
- **Why:** True bidirectional streaming reduces latency
- **Benefit:** Instant message delivery, efficient bandwidth

### 4. Lambda Layers for Shared Dependencies
- **Why:** Reduces package size, faster uploads
- **Benefit:** Easier updates to shared libraries

### 5. DynamoDB TTL for Session Cleanup
- **Why:** Automatic cleanup of expired sessions
- **Benefit:** Reduces storage costs, improves performance

### 6. Lambda Function URLs for Streaming
- **Why:** Direct Lambda invocation supports response streaming
- **Benefit:** True SSE support for debt analysis

### 7. Two-Agent Architecture
- **Main Agent:** BuffettGPT (general investment advice)
- **Specialized Agent:** Debt Analyst (financial analysis)
- **Benefit:** Specialized prompts, independent versioning

---

## Deployment & Operations

### Terraform Workflow

```bash
cd chat-api/terraform/environments/dev
terraform init          # Initialize state backend
terraform plan          # Review changes
terraform apply         # Deploy to AWS
terraform destroy       # Cleanup (careful!)
```

### Lambda Package Building

- **Location:** `chat-api/backend/build/`
- **Format:** ZIP files per function
- **Build Scripts:** `chat-api/backend/scripts/`

### Monitoring

- **CloudWatch Logs:** All Lambda function logs
- **CloudWatch Metrics:** API latency, error rates
- **Dashboard:** Custom metrics for key flows

### Secrets Management

- Bedrock API keys: AWS Secrets Manager
- Google OAuth credentials: Terraform variables (sensitive)
- JWT secret: Environment variables

---

## Feature Status

### Implemented
- WebSocket-based chat
- Conversation history with CRUD
- Bedrock Agent integration
- Debt analysis with conversational AI
- Authentication (disabled in dev)
- Rate limiting (client + server)
- Real-time streaming responses
- Multi-environment deployment

### In Development
- ML model training infrastructure
- Advanced financial analysis features
- Caching layer optimization

### Planned
- Cashflow analysis endpoint
- Valuation analysis endpoint
- Knowledge base sync
- Advanced user profiling
- Custom action groups for agents

---

*Last updated: November 2024*
