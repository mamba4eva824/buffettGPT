# Buffett Chat API - Two Lambda Architecture

**Document Version:** 1.1
**Date:** December 12, 2025
**Status:** Proposed Solution for Action Group Response Format Issue

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Architecture Overview](#current-architecture-overview)
3. [The Problem: Action Group Response Format](#the-problem-action-group-response-format)
4. [Proposed Solution: Separate Action Group Lambda](#proposed-solution-separate-action-group-lambda)
   - [Architecture with Two Lambdas](#architecture-with-two-lambdas)
   - [Key Connection: How the Two Lambdas Communicate via Bedrock](#key-connection-how-the-two-lambdas-communicate-via-bedrock)
   - [New Lambda: prediction-ensemble-action](#new-lambda-prediction-ensemble-action)
5. [Complete Data Flow](#complete-data-flow)
6. [Component Reference](#component-reference)

---

## Executive Summary

The Buffett Chat API is a multi-agent financial analysis system that uses:
- **AWS Bedrock** agents (Claude Haiku) for expert analysis
- **XGBoost ML models** for BUY/HOLD/SELL predictions
- **Server-Sent Events (SSE)** for real-time streaming to users

### Current Issue

Bedrock action groups cannot receive financial data from Lambda due to response format incompatibility. The Lambda Web Adapter + FastAPI middleware produces `application/json; charset=utf-8` but Bedrock requires exactly `application/json`.

### Proposed Solution

Create a separate Lambda (`prediction-ensemble-action`) for Bedrock action groups that bypasses Lambda Web Adapter entirely, returning the exact JSON format Bedrock expects.

---

## Current Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                 FRONTEND                                     │
│                                                                              │
│   React Application                                                          │
│   ┌────────────────┐  ┌──────────────┐  ┌───────────────┐  ┌─────────────┐  │
│   │ AnalysisView   │─►│ SSE Reader   │─►│ StreamingText │─►│ BubbleTabs  │  │
│   │ (POST request) │  │ (fetch API)  │  │ (Markdown)    │  │ (Predictions)│  │
│   └────────────────┘  └──────────────┘  └───────────────┘  └─────────────┘  │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
                                           │ HTTPS POST /supervisor
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                     │
│                                                                              │
│   ┌─────────────────────────────┐    ┌────────────────────────────────────┐ │
│   │ HTTP API (APIGatewayV2)     │    │ REST API                           │ │
│   │ - JWT Authentication        │    │ - /analysis/{type} (HTTP_PROXY)    │ │
│   │ - CORS Configuration        │    │ - Routes to Lambda Function URL    │ │
│   └─────────────────────────────┘    └────────────────────────────────────┘ │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   PREDICTION-ENSEMBLE LAMBDA (Docker Container)                              │
│   ════════════════════════════════════════════                               │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │ Lambda Web Adapter (aws-lambda-adapter:0.8.4)                         │ │
│   │ - Converts Lambda events to HTTP requests                             │ │
│   │ - Enables response streaming (AWS_LWA_INVOKE_MODE=RESPONSE_STREAM)    │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                              │                                               │
│                              ▼                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │ Uvicorn + FastAPI                                                     │ │
│   │                                                                        │ │
│   │ Endpoints:                                                             │ │
│   │ ┌─────────────────────────────────────────────────────────────────┐   │ │
│   │ │ POST /supervisor    - Multi-agent orchestration with streaming  │   │ │
│   │ │ POST /analysis/*    - Single expert analysis                    │   │ │
│   │ │ POST /analyze       - Action group handler (PROBLEMATIC)        │   │ │
│   │ │ GET  /health        - Health check                              │   │ │
│   │ └─────────────────────────────────────────────────────────────────┘   │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                              │                                               │
│                              ▼                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │ Services                                                              │ │
│   │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │ │
│   │ │ orchestrator │ │ bedrock.py   │ │ inference.py │ │ streaming.py │  │ │
│   │ │ (multi-agent)│ │ (boto3 calls)│ │ (XGBoost ML) │ │ (SSE format) │  │ │
│   │ └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└──────────────────────────────────────────┬──────────────────────────────────┘
                                           │
                                           │ boto3.invoke_agent()
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   AWS BEDROCK AGENTS (Claude Haiku 4.5)                                      │
│   ═════════════════════════════════════                                      │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                        SUPERVISOR AGENT                                │ │
│   │                     buffett-dev-supervisor                             │ │
│   │                                                                        │ │
│   │   - Receives expert analyses as context                                │ │
│   │   - Synthesizes with value investing principles                        │ │
│   │   - Streams final recommendation via ConverseStream API                │ │
│   │   - Optional: Knowledge base (Warren Buffett letters)                  │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                              ▲                                               │
│                              │ Expert analyses                               │
│          ┌───────────────────┼───────────────────┐                          │
│          │                   │                   │                          │
│   ┌──────┴───────┐    ┌──────┴───────┐    ┌──────┴───────┐                  │
│   │ DEBT EXPERT  │    │  CASHFLOW    │    │   GROWTH     │                  │
│   │              │    │   EXPERT     │    │   EXPERT     │                  │
│   │ Analyzes:    │    │              │    │              │                  │
│   │ - Leverage   │    │ Analyzes:    │    │ Analyzes:    │                  │
│   │ - Interest   │    │ - FCF        │    │ - ROE/ROIC   │                  │
│   │   coverage   │    │ - Cash       │    │ - Margins    │                  │
│   │ - Debt       │    │   conversion │    │ - Revenue    │                  │
│   │   maturity   │    │ - CapEx      │    │   growth     │                  │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│          │                   │                   │                          │
│          │ Action Group      │ Action Group      │ Action Group             │
│          │ "FinancialAnalysis"                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              │                                               │
│                              ▼                                               │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                    ACTION GROUP INVOCATION                             │ │
│   │                         (THE PROBLEM)                                  │ │
│   │                                                                        │ │
│   │   Currently points to: prediction-ensemble Lambda                      │ │
│   │   Issue: Lambda Web Adapter + Middleware format incompatibility        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXTERNAL SERVICES                                   │
│                                                                              │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│   │ FMP API         │  │ S3              │  │ DynamoDB                    │ │
│   │                 │  │                 │  │                             │ │
│   │ - Income stmt   │  │ ML Models:      │  │ - Conversations             │ │
│   │ - Balance sheet │  │ - debt.pkl      │  │ - Chat messages             │ │
│   │ - Cash flow     │  │ - cashflow.pkl  │  │ - User sessions             │ │
│   │ - Key metrics   │  │ - growth.pkl    │  │ - Analysis cache            │ │
│   └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## The Problem: Action Group Response Format

### Root Cause

AWS Bedrock Action Groups require a **specific JSON response format**:

```json
{
    "messageVersion": "1.0",
    "response": {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "httpStatusCode": 200,
        "responseBody": {
            "application/json": {
                "body": "{\"ticker\":\"AAPL\",\"prediction\":\"BUY\",...}"
            }
        }
    }
}
```

**Critical Requirements:**
1. Content-type key must be exactly `"application/json"` (no charset suffix)
2. The `body` field must contain a **JSON string**, not a nested object

### What's Happening

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   BEDROCK ACTION GROUP INVOCATION                                            │
│                                                                              │
│   Bedrock sends:                          Lambda Web Adapter receives:       │
│   ┌────────────────────────┐              ┌────────────────────────────┐    │
│   │ {                      │              │ Converts to HTTP POST      │    │
│   │   "actionGroup":       │     ───►     │ /analyze                   │    │
│   │     "FinancialAnalysis"│              │ Content-Type: app/json     │    │
│   │   "apiPath": "/analyze"│              │ Body: {ticker, type}       │    │
│   │ }                      │              └────────────────────────────┘    │
│   └────────────────────────┘                           │                    │
│                                                        ▼                    │
│                                           ┌────────────────────────────┐    │
│                                           │ BedrockAgentMiddleware     │    │
│                                           │ Routes to FastAPI          │    │
│                                           └────────────────────────────┘    │
│                                                        │                    │
│                                                        ▼                    │
│                                           ┌────────────────────────────┐    │
│                                           │ FastAPI /analyze endpoint  │    │
│                                           │ - Fetches FMP data         │    │
│                                           │ - Runs ML inference        │    │
│                                           │ - Returns JSONResponse     │    │
│                                           └────────────────────────────┘    │
│                                                        │                    │
│   ┌────────────────────────────────────────────────────┼────────────────┐   │
│   │                    THE PROBLEM                     │                │   │
│   │                                                    ▼                │   │
│   │   FastAPI returns:                 Middleware produces:             │   │
│   │   ┌────────────────────┐           ┌──────────────────────────────┐│   │
│   │   │ Content-Type:      │           │ {                            ││   │
│   │   │   application/json;│    ───►   │   "responseBody": {          ││   │
│   │   │   charset=utf-8    │           │     "application/json;       ││   │
│   │   │                    │           │      charset=utf-8": {...}   ││   │
│   │   │ Body: {...}        │           │   }                          ││   │
│   │   └────────────────────┘           │ }                            ││   │
│   │                                    └──────────────────────────────┘│   │
│   │                                                    │                │   │
│   │   Bedrock EXPECTS:                                 │                │   │
│   │   ┌────────────────────┐           ╔═══════════════╧══════════════╗│   │
│   │   │ "responseBody": {  │           ║ dependencyFailedException    ║│   │
│   │   │   "application/    │    ◄──    ║ "The server encountered an   ║│   │
│   │   │    json": {...}    │           ║  error processing the        ║│   │
│   │   │ }                  │           ║  Lambda response"            ║│   │
│   │   └────────────────────┘           ╚══════════════════════════════╝│   │
│   │                                                                     │   │
│   │   KEY MISMATCH:                                                     │   │
│   │   Expected: "application/json"                                      │   │
│   │   Received: "application/json; charset=utf-8"                       │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Proposed Solution: Separate Action Group Lambda

### Architecture with Two Lambdas

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   USER PATH (unchanged)                                                      │
│   ═════════════════════                                                      │
│                                                                              │
│   User ──► API Gateway ──► prediction-ensemble (LWA + FastAPI)              │
│                                     │                                        │
│                                     ▼                                        │
│                              SSE Stream to User  ✓                           │
│                                                                              │
│   - Lambda Web Adapter enables HTTP streaming                                │
│   - FastAPI handles SSE response formatting                                  │
│   - boto3 calls Bedrock agents                                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   BEDROCK PATH (NEW - completely separate)                                   │
│   ════════════════════════════════════════                                   │
│                                                                              │
│   Bedrock Agent ──► prediction-ensemble-action (Pure Python)                │
│   Action Group              │                                                │
│   invokes                   │  NO Lambda Web Adapter                         │
│                             │  NO FastAPI                                    │
│                             │  NO HTTP transformation                        │
│                             ▼                                                │
│                      ┌──────────────────┐                                    │
│                      │ def handler():   │                                    │
│                      │   return {       │                                    │
│                      │     "response":  │──────► ✓ Exact Bedrock format      │
│                      │       {...}      │                                    │
│                      │   }              │                                    │
│                      └──────────────────┘                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Key Connection: How the Two Lambdas Communicate via Bedrock

**Critical Understanding:** The two Lambdas never call each other directly. **Bedrock is the bridge.**

```
THE CONNECTION FLOW
════════════════════════════════════════════════════════════════════════════════

prediction-ensemble                     Bedrock                      prediction-ensemble-action
     │                                    │                                    │
     │  boto3.invoke_agent(               │                                    │
     │    inputText="Analyze AAPL"        │                                    │
     │  )                                 │                                    │
     │                                    │                                    │
     │ ─────── text prompt ─────────────► │                                    │
     │         (just a string)            │                                    │
     │                                    │                                    │
     │                                    │  Agent thinks...                   │
     │                                    │  "I need financial data"           │
     │                                    │                                    │
     │                                    │ ──── action group invocation ────► │
     │                                    │      (Bedrock controls this)       │
     │                                    │                                    │
     │                                    │                                    │ Fetches data
     │                                    │                                    │ Runs ML
     │                                    │                                    │ Returns JSON
     │                                    │                                    │
     │                                    │ ◄─── exact Bedrock format ──────── │
     │                                    │      (no LWA, no FastAPI)          │
     │                                    │                                    │
     │                                    │  Agent generates analysis          │
     │                                    │  using the data                    │
     │                                    │                                    │
     │ ◄──── analysis text ────────────── │                                    │
     │       (streaming chunks)           │                                    │
     │                                    │                                    │
     ▼                                    │                                    │
  Streams to user                         │                                    │
```

**Key Points:**

| # | Point | Explanation |
|---|-------|-------------|
| 1 | **boto3.invoke_agent() sends text** | Just a string prompt - no special formatting needed |
| 2 | **Bedrock decides when to call action groups** | Your code doesn't control this - the agent decides |
| 3 | **Bedrock invokes Lambda directly** | Configured in Terraform, not in your application code |
| 4 | **prediction-ensemble-action has no LWA/FastAPI** | Returns dict directly to Lambda runtime |
| 5 | **No HTTP↔JSON translation** | The incompatible conversion never happens |

**Terraform Configuration (wires action group to new Lambda):**

```hcl
# In bedrock/main.tf - action group points to NEW lambda
resource "aws_bedrockagent_agent_action_group" "financial_analysis" {
  action_group_executor {
    lambda = var.action_group_lambda_arn  # ← prediction-ensemble-action
  }
}
```

**Why This Works:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  prediction-ensemble              prediction-ensemble-action                 │
│  (user-facing)                    (Bedrock-facing)                          │
│        │                                  ▲                                  │
│        │                                  │                                  │
│        │   boto3.invoke_agent()           │  Bedrock invokes                │
│        └──────────────► BEDROCK ──────────┘   action group                  │
│                         AGENT                                                │
│                                                                              │
│  The two Lambdas never call each other directly.                            │
│  Bedrock is the bridge between them.                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### New Lambda: prediction-ensemble-action

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   PREDICTION-ENSEMBLE-ACTION (Pure Python - NO LWA)                          │
│   ═════════════════════════════════════════════════                          │
│                                                                              │
│   Purpose: Handle Bedrock action group invocations only                      │
│   Runtime: Python 3.11 (zip package, not Docker)                             │
│   No Lambda Web Adapter, No FastAPI, No Uvicorn                              │
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────────┐ │
│   │                                                                        │ │
│   │   def lambda_handler(event, context):                                  │ │
│   │       """                                                              │ │
│   │       Handles Bedrock action group invocations directly.               │ │
│   │       Returns exact format Bedrock expects.                            │ │
│   │       """                                                              │ │
│   │       # Parse Bedrock action group event                               │ │
│   │       action_group = event['actionGroup']                              │ │
│   │       api_path = event['apiPath']                                      │ │
│   │       request_body = event['requestBody']                              │ │
│   │                                                                        │ │
│   │       # Extract parameters from Bedrock format                         │ │
│   │       properties = request_body['content']['application/json']         │ │
│   │                                  ['properties']                        │ │
│   │       ticker = get_property(properties, 'ticker')                      │ │
│   │       analysis_type = get_property(properties, 'analysis_type')        │ │
│   │                                                                        │ │
│   │       # Business logic (shared with prediction-ensemble)               │ │
│   │       financial_data = fmp_client.get_financials(ticker)               │ │
│   │       features = feature_extractor.extract(financial_data)             │ │
│   │       inference = ml_inference.predict(features, analysis_type)        │ │
│   │       metrics = compute_value_metrics(financial_data, analysis_type)   │ │
│   │                                                                        │ │
│   │       # Build response body                                            │ │
│   │       response_body = {                                                │ │
│   │           'ticker': ticker,                                            │ │
│   │           'model_inference': inference,                                │ │
│   │           'value_metrics': metrics                                     │ │
│   │       }                                                                │ │
│   │                                                                        │ │
│   │       # Return EXACT Bedrock format                                    │ │
│   │       return {                                                         │ │
│   │           'messageVersion': '1.0',                                     │ │
│   │           'response': {                                                │ │
│   │               'actionGroup': action_group,                             │ │
│   │               'apiPath': api_path,                                     │ │
│   │               'httpMethod': 'POST',                                    │ │
│   │               'httpStatusCode': 200,                                   │ │
│   │               'responseBody': {                                        │ │
│   │                   'application/json': {  # ◄── Exact key, no charset   │ │
│   │                       'body': json.dumps(response_body)  # ◄── String  │ │
│   │                   }                                                    │ │
│   │               }                                                        │ │
│   │           }                                                            │ │
│   │       }                                                                │ │
│   │                                                                        │ │
│   └───────────────────────────────────────────────────────────────────────┘ │
│                                                                              │
│   Shared Modules (via Lambda Layer):                                         │
│   ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│   │ fmp_client   │ │ feature_     │ │ inference    │ │ ensemble_    │       │
│   │ (FMP API)    │ │ extractor    │ │ (XGBoost)    │ │ metrics      │       │
│   └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Complete Data Flow

### Step-by-Step Request Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE END-TO-END DATA FLOW                         │
└─────────────────────────────────────────────────────────────────────────────┘


STEP 1: USER REQUEST
════════════════════════════════════════════════════════════════════════════════

    User clicks "Analyze AAPL"
            │
            ▼
    ┌─────────────────────┐     HTTPS POST      ┌─────────────────────┐
    │  Frontend           │ ──────────────────► │  API Gateway        │
    │  AnalysisView.jsx   │  /supervisor        │  (JWT Auth)         │
    │                     │  {company: "AAPL"}  │                     │
    └─────────────────────┘                     └──────────┬──────────┘
                                                           │
                                                           ▼

STEP 2: STREAMING LAMBDA RECEIVES REQUEST
════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                          │
    │   PREDICTION-ENSEMBLE (LWA + FastAPI)                                   │
    │                                                                          │
    │   orchestrator.py:                                                       │
    │   ┌───────────────────────────────────────────────────────────────────┐ │
    │   │  async def orchestrate_supervisor_analysis(ticker):               │ │
    │   │                                                                    │ │
    │   │      # Open SSE stream to frontend                                 │ │
    │   │      yield {"event": "connected"}                                  │ │
    │   │                                                                    │ │
    │   │      # Invoke 3 experts in parallel via boto3                      │ │
    │   │      results = await asyncio.gather(                               │ │
    │   │          invoke_expert_agent('debt', ticker),                      │ │
    │   │          invoke_expert_agent('cashflow', ticker),                  │ │
    │   │          invoke_expert_agent('growth', ticker)                     │ │
    │   │      )                                                             │ │
    │   └───────────────────────────────────────────────────────────────────┘ │
    │                     │                                                    │
    └─────────────────────┼────────────────────────────────────────────────────┘
                          │
                          │ boto3.invoke_agent(inputText="Analyze AAPL debt")
                          ▼

STEPS 3-4: PARALLEL EXPERT AGENT PROCESSING (x3)
════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                          │
    │   THREE PARALLEL PATHS (asyncio.gather)                                  │
    │                                                                          │
    │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
    │   │   DEBT PATH     │  │  CASHFLOW PATH  │  │   GROWTH PATH   │         │
    │   │   (parallel)    │  │   (parallel)    │  │   (parallel)    │         │
    │   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
    │            │                    │                    │                   │
    │            ▼                    ▼                    ▼                   │
    └────────────┼────────────────────┼────────────────────┼───────────────────┘
                 │                    │                    │
                 │                    │                    │
    ┌────────────┼────────────────────┼────────────────────┼───────────────────┐
    │            │                    │                    │                   │
    │  STEP 3: BEDROCK AGENTS PROCESS REQUESTS (3 in parallel)                │
    │                                                                          │
    │  ┌─────────▼─────────┐  ┌───────▼─────────┐  ┌───────▼─────────┐        │
    │  │   DEBT EXPERT     │  │ CASHFLOW EXPERT │  │  GROWTH EXPERT  │        │
    │  │                   │  │                 │  │                 │        │
    │  │ "Analyze AAPL     │  │ "Analyze AAPL   │  │ "Analyze AAPL   │        │
    │  │  debt position"   │  │  cash flows"    │  │  growth metrics"│        │
    │  │                   │  │                 │  │                 │        │
    │  │ Agent thinks:     │  │ Agent thinks:   │  │ Agent thinks:   │        │
    │  │ "I need debt      │  │ "I need FCF     │  │ "I need ROE     │        │
    │  │  metrics data"    │  │  metrics data"  │  │  metrics data"  │        │
    │  │                   │  │                 │  │                 │        │
    │  │ Invokes action    │  │ Invokes action  │  │ Invokes action  │        │
    │  │ group with:       │  │ group with:     │  │ group with:     │        │
    │  │ - ticker: AAPL    │  │ - ticker: AAPL  │  │ - ticker: AAPL  │        │
    │  │ - type: debt      │  │ - type: cashflow│  │ - type: growth  │        │
    │  └─────────┬─────────┘  └────────┬────────┘  └────────┬────────┘        │
    │            │                     │                    │                  │
    │            │ action group        │ action group       │ action group     │
    │            │ invocation          │ invocation         │ invocation       │
    │            ▼                     ▼                    ▼                  │
    └────────────┼─────────────────────┼────────────────────┼──────────────────┘
                 │                     │                    │
                 │                     │                    │
    ┌────────────┼─────────────────────┼────────────────────┼──────────────────┐
    │            │                     │                    │                  │
    │  STEP 4: ACTION GROUP LAMBDA INVOKED 3 TIMES (can be concurrent)        │
    │                                                                          │
    │  ┌─────────────────────────────────────────────────────────────────────┐│
    │  │                                                                      ││
    │  │   PREDICTION-ENSEMBLE-ACTION (Pure Python - NO LWA)                 ││
    │  │                                                                      ││
    │  │   Handles 3 separate invocations (one per expert agent):            ││
    │  │                                                                      ││
    │  │   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       ││
    │  │   │ Invocation #1   │ │ Invocation #2   │ │ Invocation #3   │       ││
    │  │   │ type: "debt"    │ │ type: "cashflow"│ │ type: "growth"  │       ││
    │  │   └────────┬────────┘ └────────┬────────┘ └────────┬────────┘       ││
    │  │            │                   │                   │                 ││
    │  │            ▼                   ▼                   ▼                 ││
    │  │   ┌─────────────────────────────────────────────────────────────┐   ││
    │  │   │ For each invocation:                                        │   ││
    │  │   │                                                              │   ││
    │  │   │ 1. Parse event ──► ticker, analysis_type                    │   ││
    │  │   │ 2. Fetch FMP Data ──► 5 years of financials                 │   ││
    │  │   │ 3. Extract Features ──► 50+ ratios & trends                 │   ││
    │  │   │ 4. ML Inference ──► XGBoost prediction for that type        │   ││
    │  │   │ 5. Compute Metrics ──► Type-specific value metrics          │   ││
    │  │   └─────────────────────────────────────────────────────────────┘   ││
    │  │                                                                      ││
    │  │   Returns 3 separate responses:                                     ││
    │  │                                                                      ││
    │  │   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐       ││
    │  │   │ Response #1     │ │ Response #2     │ │ Response #3     │       ││
    │  │   │                 │ │                 │ │                 │       ││
    │  │   │ prediction:     │ │ prediction:     │ │ prediction:     │       ││
    │  │   │   SELL (54%)    │ │   BUY (83%)     │ │   BUY (77%)     │       ││
    │  │   │                 │ │                 │ │                 │       ││
    │  │   │ metrics:        │ │ metrics:        │ │ metrics:        │       ││
    │  │   │ - debt_to_equity│ │ - fcf_margin    │ │ - roe           │       ││
    │  │   │ - interest_cov  │ │ - fcf_yield     │ │ - roic          │       ││
    │  │   │ - net_debt_ebitda│ │ - cash_conv    │ │ - revenue_growth│       ││
    │  │   └────────┬────────┘ └────────┬────────┘ └────────┬────────┘       ││
    │  │            │                   │                   │                 ││
    │  └────────────┼───────────────────┼───────────────────┼─────────────────┘│
    │               │                   │                   │                  │
    │               │ ✓ Bedrock accepts │ ✓ Bedrock accepts │ ✓ Bedrock accepts│
    │               ▼                   ▼                   ▼                  │
    └───────────────┼───────────────────┼───────────────────┼──────────────────┘
                    │                   │                   │
                    │                   │                   │
    ┌───────────────┼───────────────────┼───────────────────┼──────────────────┐
    │               │                   │                   │                  │
    │  STEP 4b: EACH EXPERT GENERATES ANALYSIS WITH DATA                      │
    │                                                                          │
    │  ┌────────────▼────────┐ ┌────────▼────────┐ ┌────────▼────────┐        │
    │  │   DEBT EXPERT      │ │ CASHFLOW EXPERT │ │  GROWTH EXPERT  │        │
    │  │   generates:       │ │ generates:      │ │  generates:     │        │
    │  │                    │ │                 │ │                 │        │
    │  │ "ML: SELL (54%)    │ │ "ML: BUY (83%)  │ │ "ML: BUY (77%)  │        │
    │  │  Debt-to-equity    │ │  FCF margin of  │ │  ROE of 147%    │        │
    │  │  improving from    │ │  26% indicates  │ │  demonstrates   │        │
    │  │  1.2x to 0.85x..." │ │  strong cash..."│ │  exceptional..."│        │
    │  └────────────┬───────┘ └────────┬────────┘ └────────┬────────┘        │
    │               │                  │                   │                  │
    │               └──────────────────┼───────────────────┘                  │
    │                                  │                                      │
    │                                  ▼                                      │
    │                         All 3 complete                                  │
    │                         (asyncio.gather returns)                        │
    │                                                                          │
    └──────────────────────────────────┼───────────────────────────────────────┘
                                       │
                                       ▼

STEP 5: EXPERT RESULTS RETURN TO ORCHESTRATOR
════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                          │
    │   boto3.invoke_agent() returns for each expert (3 parallel calls)       │
    │                                                                          │
    │   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
    │   │ DEBT RESULT     │  │ CASHFLOW RESULT │  │ GROWTH RESULT   │         │
    │   │                 │  │                 │  │                 │         │
    │   │ prediction:     │  │ prediction:     │  │ prediction:     │         │
    │   │   SELL (54%)    │  │   BUY (83%)     │  │   BUY (77%)     │         │
    │   │                 │  │                 │  │                 │         │
    │   │ analysis:       │  │ analysis:       │  │ analysis:       │         │
    │   │ "Debt-to-equity │  │ "FCF margin of  │  │ "ROE of 147%    │         │
    │   │  improving..."  │  │  26% shows..."  │  │  demonstrates..." │         │
    │   └────────┬────────┘  └────────┬────────┘  └────────┬────────┘         │
    │            │                    │                    │                   │
    │            └────────────────────┼────────────────────┘                   │
    │                                 │                                        │
    │                                 ▼                                        │
    │                    asyncio.gather() completes                            │
    │                    All 3 experts finished                                │
    │                                                                          │
    └─────────────────────────────────┬────────────────────────────────────────┘
                                      │
                                      │ Results available in orchestrator
                                      ▼

STEP 6: ORCHESTRATOR STREAMS TO USER
════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                          │
    │   PREDICTION-ENSEMBLE (orchestrator.py continues)                        │
    │                                                                          │
    │   # All 3 experts complete (parallel)                                    │
    │   expert_results = {                                                     │
    │       'debt': {"prediction": "SELL", "analysis": "..."},                │
    │       'cashflow': {"prediction": "BUY", "analysis": "..."},             │
    │       'growth': {"prediction": "BUY", "analysis": "..."}                │
    │   }                                                                      │
    │                                                                          │
    │   # Stream inference events                                              │
    │   yield {"event": "inference", "agent": "debt", "prediction": "SELL"}   │
    │   yield {"event": "inference", "agent": "cashflow", "prediction": "BUY"}│
    │   yield {"event": "inference", "agent": "growth", "prediction": "BUY"}  │
    │                                                                          │
    │   # Invoke supervisor with ConverseStream                                │
    │   async for chunk in supervisor_stream(expert_results):                  │
    │       yield {"event": "chunk", "text": chunk}                            │
    │                          │                                               │
    └──────────────────────────┼───────────────────────────────────────────────┘
                               │
                               │ SSE stream
                               ▼

STEP 7: FRONTEND RENDERS RESPONSE
════════════════════════════════════════════════════════════════════════════════

    ┌─────────────────────────────────────────────────────────────────────────┐
    │                                                                          │
    │   FRONTEND - Real-time Rendering                                         │
    │                                                                          │
    │   ┌───────────────────────────────────────────────────────────────────┐ │
    │   │                     BUFFETT ANALYSIS: AAPL                        │ │
    │   │                                                                    │ │
    │   │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │ │
    │   │   │  DEBT       │  │  CASHFLOW   │  │  GROWTH     │              │ │
    │   │   │  SELL 54%   │  │  BUY  83%   │  │  BUY  77%   │              │ │
    │   │   └─────────────┘  └─────────────┘  └─────────────┘              │ │
    │   │                                                                    │ │
    │   │   ## Investment Recommendation: CAUTIOUS BUY                      │ │
    │   │                                                                    │ │
    │   │   Based on the expert analyses, Apple presents a mixed but        │ │
    │   │   generally positive investment picture...                        │ │
    │   │                                                                    │ │
    │   │   **Strengths:**                                                   │ │
    │   │   - Exceptional free cash flow generation█                        │ │
    │   │                                          ▲                         │ │
    │   │                                          └── Streaming cursor      │ │
    │   └───────────────────────────────────────────────────────────────────┘ │
    │                                                                          │
    └─────────────────────────────────────────────────────────────────────────┘
```

---

## Component Reference

### Lambda Functions

| Function | Purpose | Runtime | Streaming |
|----------|---------|---------|-----------|
| prediction-ensemble | User-facing API, orchestration | Docker (LWA + FastAPI) | SSE via Function URL |
| prediction-ensemble-action | Bedrock action groups | Python 3.11 (zip) | N/A |

### Bedrock Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| buffett-dev-supervisor | Claude Haiku 4.5 | Synthesizes expert analyses |
| buffett-dev-debt-expert | Claude Haiku 4.5 | Debt/leverage analysis |
| buffett-dev-cashflow-expert | Claude Haiku 4.5 | Cash flow analysis |
| buffett-dev-growth-expert | Claude Haiku 4.5 | Growth/profitability analysis |

### Data Sources

| Source | Purpose |
|--------|---------|
| FMP API | Financial statements, metrics |
| S3 (buffett-dev-models) | XGBoost ML models |
| DynamoDB | Conversations, messages, cache |

### Terraform Configuration Changes

```hcl
# Action groups point to NEW lambda (not prediction-ensemble)
module "debt_expert" {
  action_group_lambda_arn = module.lambda.prediction_ensemble_action_arn
}

module "cashflow_expert" {
  action_group_lambda_arn = module.lambda.prediction_ensemble_action_arn
}

module "growth_expert" {
  action_group_lambda_arn = module.lambda.prediction_ensemble_action_arn
}
```

---

*Document generated: December 12, 2025*
