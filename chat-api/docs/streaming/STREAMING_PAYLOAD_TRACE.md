# Streaming Payload Trace

**Date:** December 6, 2025
**Project:** Buffett Chat API - Ensemble Analyzer
**Version:** v1.6.1

---

## Complete Request Flow - Payload Snapshots

### 1. Browser (React Frontend)

**Outgoing Request:**
```javascript
// AnalysisView.jsx - fetch call
fetch('https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/analysis/debt', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...'
  },
  body: JSON.stringify({
    company: 'NVDA',
    fiscal_year: 2024,
    conversation_id: 'conv_abc123'
  })
})
```

---

### 2. API Gateway - CORS Preflight (OPTIONS)

**Incoming:**
```
HTTP Method: OPTIONS
Resource Path: /analysis/debt
Headers: {
  origin: 'http://localhost:3000',
  access-control-request-method: 'POST',
  access-control-request-headers: 'authorization,content-type'
}
```

**Response (Mock Integration):**
```
Status: 200 OK
Headers: {
  Access-Control-Allow-Headers: 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
  Access-Control-Allow-Methods: 'POST,OPTIONS',
  Access-Control-Allow-Origin: '*'
}
```

---

### 3. API Gateway - JWT TOKEN Authorizer

**Payload sent to `buffett-dev-auth-verify` Lambda:**
```json
{
  "type": "TOKEN",
  "methodArn": "arn:aws:execute-api:us-east-1:430118826061:t5wvlwfo5b/dev/POST/analysis/debt",
  "authorizationToken": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiMTA5MDk5NjY2Nzg5OTkxMDc2MTI1IiwiZW1haWwiOiJ3ZWlucmVpY2hjaHJpc0BnbWFpbC5jb20iLCJuYW1lIjoiQ2hyaXN0b3BoZXIgV2VpbnJlaWNoIiwic3Vic2NyaXB0aW9uX3RpZXIiOiJmcmVlIiwiZXhwIjoxNzY1NTE1NzQ2LCJpYXQiOjE3NjQ5MTA5NDYsImlzcyI6ImJ1ZmZldHQifQ.gUhI681nE31y9McXSVFYnOZ3EnN1S-qt0UUMJFqWR_Q"
}
```

**Decoded JWT Claims:**
```json
{
  "user_id": "109099666789991076125",
  "email": "weinreichchris@gmail.com",
  "name": "Christopher Weinreich",
  "subscription_tier": "free",
  "exp": 1765515746,
  "iat": 1764910946,
  "iss": "buffett"
}
```

**Authorizer Response (IAM Policy with Wildcard):**
```json
{
  "principalId": "109099666789991076125",
  "policyDocument": {
    "Version": "2012-10-17",
    "Statement": [{
      "Action": "execute-api:Invoke",
      "Effect": "Allow",
      "Resource": "arn:aws:execute-api:us-east-1:430118826061:t5wvlwfo5b/dev/*"
    }]
  },
  "context": {
    "user_id": "109099666789991076125",
    "environment": "dev",
    "project": "buffett-chat-api"
  }
}
```

---

### 4. API Gateway - HTTP_PROXY to Lambda Function URL

**Request forwarded to Lambda Function URL:**
```
URL: https://[function-url].lambda-url.us-east-1.on.aws/analysis/debt
Method: POST
Headers: {
  Content-Type: 'application/json',
  X-Forwarded-For: '47.39.79.237',
  X-Amzn-Trace-Id: 'Root=1-69339296-233432aa...'
}
Body: {
  "company": "NVDA",
  "fiscal_year": 2024,
  "conversation_id": "conv_abc123"
}
```

---

### 5. Lambda (FastAPI) - Request Processing

**FastAPI receives (via Lambda Web Adapter):**
```python
# app.py - /analysis/{agent_type} endpoint
@app.post("/analysis/{agent_type}")
async def analyze(agent_type: str, request: AnalysisRequest):
    # request object:
    {
        "company": "NVDA",
        "fiscal_year": 2024,
        "conversation_id": "conv_abc123"
    }
    # agent_type from path: "debt"
```

---

### 6. Lambda - FMP Data Fetch

**Request to Financial Modeling Prep API:**
```
GET https://financialmodelingprep.com/api/v3/balance-sheet-statement/NVDA?period=quarter&limit=20&apikey=***
GET https://financialmodelingprep.com/api/v3/income-statement/NVDA?period=quarter&limit=20&apikey=***
GET https://financialmodelingprep.com/api/v3/cash-flow-statement/NVDA?period=quarter&limit=20&apikey=***
```

**Response (cached in DynamoDB):**
```json
{
  "cache_key": "NVDA:2024",
  "ticker": "NVDA",
  "fiscal_year": 2024,
  "cached_at": 1765039673,
  "expires_at": 1772815673,
  "raw_financials": {
    "balance_sheet": [
      {
        "date": "2025-10-26",
        "totalAssets": 161148000000,
        "totalLiabilities": 42251000000,
        "totalDebt": 10822000000,
        "cashAndCashEquivalents": 11486000000,
        "totalStockholdersEquity": 118897000000,
        "netDebt": -664000000
      }
    ],
    "income_statement": [
      {
        "date": "2025-10-26",
        "revenue": 35082000000,
        "operatingIncome": 21869000000,
        "netIncome": 19309000000,
        "interestExpense": 61000000
      }
    ],
    "cash_flow": [
      {
        "date": "2025-10-26",
        "operatingCashFlow": 17629000000,
        "freeCashFlow": 16757000000,
        "capitalExpenditure": -872000000
      }
    ]
  }
}
```

---

### 7. Lambda - XGBoost Inference

**Feature Vector (88 features):**
```python
feature_vector = [
  0.262,   # debt_to_equity_ratio
  0.089,   # debt_to_assets_ratio
  23.4,    # interest_coverage_ratio
  -0.041,  # net_debt_ratio
  0.157,   # current_ratio_inverse
  0.738,   # equity_ratio
  1.35,    # debt_to_ebitda
  0.847,   # operating_margin
  0.551,   # net_profit_margin
  2.76,    # revenue_growth_yoy
  ...      # 78 more features
]
```

**Model Output:**
```json
{
  "prediction": "BUY",
  "confidence": 0.847,
  "ci_width": 0.12,
  "probabilities": {
    "BUY": 0.847,
    "HOLD": 0.112,
    "SELL": 0.041
  }
}
```

---

### 8. Lambda - Bedrock ConverseStream Request

**Request to Bedrock:**
```python
bedrock_runtime_client.converse_stream(
    modelId='us.anthropic.claude-haiku-4-5-20251001-v1:0',
    messages=[{
        'role': 'user',
        'content': [{
            'text': '''Analyze NVDA (NVIDIA Corporation) for fiscal year 2024.

MODEL PREDICTION: BUY with 84.7% confidence (±12%)

FINANCIAL DATA:
- Total Debt: $10.8B
- Cash & Equivalents: $11.5B
- Net Debt: -$0.66B (net cash position)
- Debt/Equity: 26.2%
- Interest Coverage: 23.4x
- Total Assets: $161.1B
- Total Liabilities: $42.3B
- Stockholders Equity: $118.9B

INCOME METRICS:
- Revenue: $35.1B (Q3 2025)
- Operating Income: $21.9B
- Net Income: $19.3B
- Operating Margin: 62.3%

CASH FLOW:
- Operating Cash Flow: $17.6B
- Free Cash Flow: $16.8B

Please provide your expert debt analysis.'''
        }]
    }],
    system=[{
        'text': '''You are a debt analysis expert specializing in value investing principles.
Analyze the company's debt profile and financial health. Focus on:
1. Debt sustainability and coverage ratios
2. Liquidity position and cash reserves
3. Capital structure efficiency
4. Risk factors and concerns
5. Investment recommendation aligned with the ML model prediction.'''
    }],
    inferenceConfig={
        'maxTokens': 2048,
        'temperature': 0.3
    }
)
```

---

### 9. Bedrock - Streaming Response

**Stream Events (token-by-token):**
```python
# Event 1: messageStart
{'messageStart': {'role': 'assistant'}}

# Event 2-N: contentBlockDelta (repeated for each token/word)
{'contentBlockDelta': {'delta': {'text': '## '}}}
{'contentBlockDelta': {'delta': {'text': 'DEBT '}}}
{'contentBlockDelta': {'delta': {'text': 'ANALYST'}}}
{'contentBlockDelta': {'delta': {'text': '\n\n'}}}
{'contentBlockDelta': {'delta': {'text': 'Based '}}}
{'contentBlockDelta': {'delta': {'text': 'on '}}}
{'contentBlockDelta': {'delta': {'text': 'my '}}}
{'contentBlockDelta': {'delta': {'text': 'analysis '}}}
{'contentBlockDelta': {'delta': {'text': 'of '}}}
{'contentBlockDelta': {'delta': {'text': 'NVIDIA'}}}
{'contentBlockDelta': {'delta': {'text': "'s "}}}
{'contentBlockDelta': {'delta': {'text': 'debt '}}}
{'contentBlockDelta': {'delta': {'text': 'profile...'}}}
# ... hundreds more chunks ...

# Final Event: messageStop
{'messageStop': {'stopReason': 'end_turn'}}

# Metadata Event
{'metadata': {
  'usage': {
    'inputTokens': 868,
    'outputTokens': 1126,
    'totalTokens': 1994
  },
  'metrics': {
    'latencyMs': 9847
  }
}}
```

---

### 10. Lambda - SSE Response to Client

**SSE Events (sent through API Gateway to browser):**
```
data: {"type":"status","message":"Fetching financial data for NVDA..."}

data: {"type":"status","message":"Running XGBoost inference..."}

data: {"type":"inference","prediction":"BUY","confidence":0.847,"ci_width":0.12,"probabilities":{"BUY":0.847,"HOLD":0.112,"SELL":0.041}}

data: {"type":"status","message":"Generating expert analysis with Claude Haiku 4.5..."}

data: {"type":"chunk","text":"## DEBT ANALYST\n\n"}

data: {"type":"chunk","text":"Based on my analysis of NVIDIA's "}

data: {"type":"chunk","text":"debt profile for fiscal year 2024, "}

data: {"type":"chunk","text":"I see **exceptional financial strength**.\n\n"}

data: {"type":"chunk","text":"### Key Observations\n\n"}

data: {"type":"chunk","text":"1. **Net Cash Position**: "}

data: {"type":"chunk","text":"With $11.5B in cash against $10.8B in debt, "}

data: {"type":"chunk","text":"NVIDIA maintains a net cash position of $664M.\n\n"}

data: {"type":"chunk","text":"2. **Interest Coverage**: "}

data: {"type":"chunk","text":"An extraordinary 23.4x coverage ratio "}

data: {"type":"chunk","text":"indicates minimal debt servicing risk.\n\n"}

... (many more chunks) ...

data: {"type":"chunk","text":"### Recommendation\n\n"}

data: {"type":"chunk","text":"**BUY** - The debt profile is exemplary."}

data: {"type":"complete","session_id":"sess_nvda_debt_abc123","ticker":"NVDA","agent_type":"debt"}
```

---

### 11. Browser - Processing SSE Stream

**React state updates (with flushSync for immediate rendering):**
```javascript
// AnalysisView.jsx - handleSSEEvent function

// Chunk 1
handleSSEEvent('debt', {type: 'chunk', text: '## DEBT ANALYST\n\n'});
// flushSync forces immediate render
// results.debt.text = '## DEBT ANALYST\n\n'
// UI updates immediately

// Chunk 2
handleSSEEvent('debt', {type: 'chunk', text: 'Based on my analysis of NVIDIA\'s '});
// flushSync forces immediate render
// results.debt.text = '## DEBT ANALYST\n\nBased on my analysis of NVIDIA\'s '
// UI updates immediately

// Chunk 3
handleSSEEvent('debt', {type: 'chunk', text: 'debt profile for fiscal year 2024, '});
// flushSync forces immediate render
// results.debt.text = '## DEBT ANALYST\n\nBased on my analysis of NVIDIA\'s debt profile for fiscal year 2024, '
// UI updates immediately

// ... continues for each chunk ...

// Final state after all chunks
results.debt = {
  isStreaming: false,
  text: '## DEBT ANALYST\n\nBased on my analysis of NVIDIA\'s debt profile...[full analysis]',
  prediction: 'BUY',
  confidence: 0.847,
  ciWidth: 0.12,
  probabilities: { BUY: 0.847, HOLD: 0.112, SELL: 0.041 }
}
```

---

## Latency Timeline

| Step | Timestamp | Duration | Cumulative |
|------|-----------|----------|------------|
| Browser sends POST | T+0ms | - | 0ms |
| CORS preflight completes | T+2ms | 2ms | 2ms |
| JWT authorizer invoked | T+3ms | - | 3ms |
| JWT authorizer returns | T+5ms | 2ms | 5ms |
| API Gateway routes to Lambda | T+45ms | 40ms | 45ms |
| Lambda cold start (if applicable) | T+545ms | 500ms | 545ms |
| FMP data fetch (cached) | T+745ms | 200ms | 745ms |
| XGBoost model load | T+1245ms | 500ms | 1245ms |
| XGBoost inference | T+1745ms | 500ms | 1745ms |
| Bedrock API call initiated | T+1800ms | 55ms | 1800ms |
| Bedrock TTFT (time to first token) | T+11300ms | 9500ms | 11300ms |
| First SSE chunk to browser | T+11355ms | 55ms | 11355ms |
| Streaming continues | T+11355ms - T+12500ms | ~50-140ms/chunk | - |
| Complete analysis delivered | T+12500ms | - | 12500ms |

---

## Request/Response Headers

### API Gateway Request Headers
```
Host: t5wvlwfo5b.execute-api.us-east-1.amazonaws.com
Content-Type: application/json
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
Origin: http://localhost:3000
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)...
Accept: */*
Accept-Encoding: gzip, deflate, br, zstd
Accept-Language: en-US,en;q=0.9
sec-fetch-dest: empty
sec-fetch-mode: cors
sec-fetch-site: cross-site
```

### SSE Response Headers
```
HTTP/1.1 200 OK
Content-Type: text/event-stream; charset=utf-8
Cache-Control: no-cache
Connection: keep-alive
X-Accel-Buffering: no
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
```

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           BROWSER (React)                                │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ AnalysisView.jsx                                                 │   │
│  │  - fetch() with ReadableStream                                   │   │
│  │  - flushSync() for immediate re-renders                          │   │
│  │  - StreamingText component displays markdown                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ POST /analysis/{agent_type}
                                 │ Authorization: Bearer <JWT>
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (REST API)                                │
│  ┌──────────────────┐    ┌──────────────────┐    ┌─────────────────┐   │
│  │ CORS (OPTIONS)   │    │ JWT Authorizer   │    │ HTTP_PROXY      │   │
│  │ - Mock response  │    │ - auth_verify.py │    │ - 120s timeout  │   │
│  │ - Allow-Origin:* │    │ - Wildcard IAM   │    │ - Passthrough   │   │
│  └──────────────────┘    └──────────────────┘    └─────────────────┘   │
│                                                                          │
│  Endpoint: t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev           │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │ HTTP_PROXY passthrough
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    LAMBDA FUNCTION URL                                   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Lambda Web Adapter v0.8.4                                        │   │
│  │  - Converts Lambda events to HTTP                                │   │
│  │  - RESPONSE_STREAM invoke mode                                   │   │
│  │  - Port 8080                                                     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ FastAPI + uvicorn                                                │   │
│  │  - EventSourceResponse (sse-starlette)                           │   │
│  │  - x-accel-buffering: no                                         │   │
│  │  - Async generator yields SSE events                             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  Function: buffett-dev-ensemble-analyzer                                │
│  Image: v1.6.1                                                          │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
┌─────────────────────┐ ┌─────────────────┐ ┌─────────────────────┐
│   FMP API           │ │   S3 (Models)   │ │   DynamoDB          │
│  - Balance Sheet    │ │  - debt.pkl     │ │  - Financial Cache  │
│  - Income Statement │ │  - cashflow.pkl │ │  - 90-day TTL       │
│  - Cash Flow        │ │  - growth.pkl   │ │                     │
└─────────────────────┘ └─────────────────┘ └─────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    AWS BEDROCK                                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ Model: us.anthropic.claude-haiku-4-5-20251001-v1:0               │   │
│  │ API: ConverseStream                                              │   │
│  │ Output: Token-by-token streaming                                 │   │
│  │ Latency: ~9s TTFT, ~50-140ms per token                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Token Usage (Typical Request)

| Metric | Value |
|--------|-------|
| Input Tokens | ~868 |
| Output Tokens | ~1,126 |
| Total Tokens | ~1,994 |
| Cost (Haiku 4.5) | ~$0.0002 input + $0.0014 output = $0.0016 |

---

## Related Documentation

- [STREAMING_IMPLEMENTATION_REPORT.md](STREAMING_IMPLEMENTATION_REPORT.md) - Implementation details
- [ENSEMBLE_EXECUTIVE_REVIEW.md](ENSEMBLE_EXECUTIVE_REVIEW.md) - Architecture overview
- [auth_verify.py](chat-api/backend/src/handlers/auth_verify.py) - JWT authorizer
- [AnalysisView.jsx](frontend/src/components/analysis/AnalysisView.jsx) - Frontend SSE handler
