# Technical Interview Prep: AWS Bedrock Action Group Integration

**Context:** Multi-Agent Financial Analysis System
**Problem Type:** Distributed Systems / API Integration / Debugging
**Duration:** 3 weeks investigation, 2 days implementation

---

## Interview Talking Points Summary

> "I built a multi-agent financial analysis system using AWS Bedrock that leverages XGBoost ML models to provide value investor insights. During integration, I encountered a critical bug where Bedrock rejected all Lambda responses. After extensive debugging and exploring multiple solutions, I resolved it by implementing a Two-Lambda Architecture that separates concerns between HTTP streaming and Bedrock action groups."

---

## Part 1: The Problem

### System Context

I was building a financial analysis platform with the following architecture:

```
Frontend (React) → API Gateway → Lambda → Bedrock Supervisor Agent
                                              ↓
                           ┌─────────────────┼─────────────────┐
                           ↓                 ↓                 ↓
                     Debt Expert      Cashflow Expert    Growth Expert
                           ↓                 ↓                 ↓
                           └─────────────────┴─────────────────┘
                                              ↓
                                    Action Group Lambda
                                    (ML Inference + Data)
```

The system needed to:
1. Accept user queries ("Analyze Tesla as an investment")
2. Route to specialized expert agents for different analysis types
3. Fetch real financial data and run XGBoost ML inference
4. Return predictions (BUY/HOLD/SELL) with confidence scores

### The Error

After deploying the Lambda that handles action group invocations, every call failed with:

```
dependencyFailedException:
The server encountered an error processing the Lambda response.
The response body from Bedrock agent must be of type 'application/json',
but 'null' was returned.
```

### Why This Was Challenging

1. **Lambda was succeeding** - CloudWatch logs showed successful data fetching and ML inference
2. **Response format looked correct** - I was returning the documented Bedrock format
3. **No clear error message** - "null was returned" was misleading; data was clearly being returned
4. **Multiple layers of abstraction** - Lambda Web Adapter + FastAPI + Bedrock middleware

---

## Part 2: The Debugging Journey

### Initial Architecture (That Failed)

```
Lambda Event → Lambda Web Adapter → FastAPI/Uvicorn → /analyze endpoint
                                          ↓
              Bedrock Agent Middleware (transforms request/response)
                                          ↓
                                    JSON Response
                                          ↓
              Lambda Web Adapter converts back to Lambda response
                                          ↓
                        Bedrock receives and REJECTS
```

### Attempted Solutions

**Version 1.9.1 - Platform Fix**
- **Hypothesis:** Docker architecture mismatch
- **Investigation:** Lambda showed `Extension.LaunchError` on cold start
- **Solution:** Added `--platform linux/amd64` to Docker build
- **Result:** Lambda started, but `dependencyFailedException` appeared

**Version 1.9.2 - NaN Sanitization**
- **Hypothesis:** NaN/Infinity in ML inference breaking JSON serialization
- **Investigation:** XGBoost sometimes produces NaN for edge cases
- **Solution:** Added `sanitize_for_json()` to convert NaN → None
- **Result:** Did not resolve - values were already clean

**Version 1.9.3 - Pre-wrapped Response**
- **Hypothesis:** Middleware not formatting response correctly
- **Investigation:** Read Bedrock docs - specific nested format required
- **Solution:** Returned complete Bedrock format directly from endpoint
- **Result:** Failed - middleware double-wrapped the already-wrapped response

**Version 1.9.4 - Explicit Content-Type**
- **Hypothesis:** Content-Type header causing issues
- **Investigation:** Traced through middleware code
- **Solution:** Explicitly set `media_type="application/json"` on JSONResponse
- **Result:** Still failed

### The Breakthrough

After 4 failed attempts, I dug deeper into the middleware source code and discovered the **exact key requirement**:

```python
# What FastAPI produces:
headers = {"content-type": "application/json; charset=utf-8"}
# The middleware uses this as the response key:
responseBody = {
    "application/json; charset=utf-8": {...}  # WRONG KEY!
}

# What Bedrock requires:
responseBody = {
    "application/json": {...}  # EXACT KEY - no charset!
}
```

**Root Cause:** AWS Bedrock does a **strict string match** on `"application/json"`. The `; charset=utf-8` suffix that FastAPI automatically adds causes Bedrock's parser to return `null` because it can't find the expected key.

---

## Part 3: Solution Options Analysis

### Option A: Patch the Middleware
**Approach:** Fork `lwa-fastapi-middleware-bedrock-agent` and fix key generation

**Pros:**
- Minimal code changes
- Could contribute fix upstream

**Cons:**
- Dependency on custom fork
- Maintenance burden
- Might break other functionality

### Option B: Custom Middleware
**Approach:** Write custom middleware that produces correct format

**Pros:**
- Full control over response transformation
- Clean integration with FastAPI

**Cons:**
- Significant development effort
- Still uses Lambda Web Adapter complexity

### Option C: Bypass Lambda Web Adapter
**Approach:** Detect action group events at Lambda handler level, skip LWA entirely

**Pros:**
- Direct control over response format
- Simplest transformation

**Cons:**
- Complex conditional logic in handler
- Mixing HTTP and action group concerns

### Option D: Two-Lambda Architecture (Chosen)
**Approach:** Separate Lambda for Bedrock action groups, pure Python handler

**Pros:**
- Clean separation of concerns
- Each Lambda optimized for its use case
- Reuses existing inference code via layers

**Cons:**
- Additional infrastructure to manage
- Slight code duplication

---

## Part 4: The Solution

### Why I Chose Two Lambdas

1. **Single Responsibility Principle** - Each Lambda does one thing well
2. **No Middleware Complexity** - Pure Python handler = direct control
3. **Code Reuse** - Both Lambdas share the same layers (inference, FMP client)
4. **Future Flexibility** - Can evolve independently

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React)                             │
└─────────────────────────────────────────────────────────────────────┘
                    │                              │
      HTTP Streaming│                              │ Analysis Request
     (SSE responses)│                              │ (via Bedrock)
                    │                              │
                    ▼                              ▼
┌─────────────────────────┐          ┌────────────────────────────────┐
│  PREDICTION ENSEMBLE    │          │        SUPERVISOR AGENT        │
│  (Docker + LWA)         │          │      (Claude Haiku 4.5)        │
│                         │          │                                │
│  • Function URL access  │          │  Orchestrates expert agents    │
│  • SSE streaming output │          │  Synthesizes final response    │
│  • FastAPI + Uvicorn    │          │                                │
│                         │          └────────────┬───────────────────┘
│  For: Direct frontend   │                       │
│  calls requiring        │          ┌────────────┼────────────┐
│  streaming responses    │          ▼            ▼            ▼
└─────────────────────────┘    ┌─────────┐  ┌─────────┐  ┌─────────┐
                               │  Debt   │  │Cashflow │  │ Growth  │
                               │ Expert  │  │ Expert  │  │ Expert  │
                               └────┬────┘  └────┬────┘  └────┬────┘
                                    │            │            │
                                    └────────────┼────────────┘
                                                 │
                                    Action Group Invocation
                                                 ▼
                              ┌────────────────────────────────────────┐
                              │       DATA FETCHER LAMBDA               │
                              │       (Pure Python Handler)             │
                              │                                         │
                              │  • No Lambda Web Adapter                │
                              │  • No FastAPI/Uvicorn                   │
                              │  • Direct Bedrock format return         │
                              │  • Exact "application/json" key         │
                              │                                         │
                              │  For: Bedrock action group calls        │
                              │  requiring strict format compliance     │
                              └────────────────────────────────────────┘
```

### Key Implementation Details

**Lambda Handler (data_fetcher_action.py):**

```python
def lambda_handler(event, context):
    """Pure Python handler - no middleware, direct control."""

    # Parse Bedrock action group event
    ticker = extract_ticker_from_event(event)
    analysis_type = extract_analysis_type_from_event(event)

    # Reuse existing services
    data = fetch_financial_data(ticker)  # From shared layer
    features = extract_features(data, analysis_type)
    prediction = run_inference(features, analysis_type)  # XGBoost

    # Return EXACT Bedrock format
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup'),
            'apiPath': event.get('apiPath'),
            'httpMethod': event.get('httpMethod'),
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {        # <-- EXACT KEY
                    'body': json.dumps({     # <-- STRING, not object
                        'ticker': ticker,
                        'prediction': prediction['signal'],
                        'confidence': prediction['confidence'],
                        'metrics': value_metrics
                    })
                }
            }
        }
    }
```

---

## Part 5: Results and Metrics

### Before vs After

| Metric | Before | After |
|--------|--------|-------|
| Action Group Success Rate | 0% | 100% |
| Error Type | `dependencyFailedException` | None |
| ML Predictions Delivered | 0 | All 3 expert types |
| Response Time | N/A | 50-400ms |

### Test Results (TSLA)

```
Expert       Prediction   Confidence   Quality
─────────────────────────────────────────────
Debt         SELL         46%          WEAK
Cashflow     BUY          85%          STRONG
Growth       BUY          71%          WEAK
```

### Performance Characteristics

- **Cold Start:** ~2 seconds (loading XGBoost models)
- **Warm Invocation:** 50-400ms
- **Memory Usage:** ~245MB of 1024MB allocated
- **Layer Size:** 60MB (numpy, sklearn 1.3.x, xgboost)

---

## Part 6: Key Learnings

### Technical Lessons

1. **AWS Services Have Undocumented Strict Requirements**
   - Bedrock does exact string matching on content-type keys
   - Documentation didn't clearly specify this constraint
   - Had to debug via source code analysis

2. **Abstraction Layers Hide Problems**
   - Lambda Web Adapter + FastAPI middleware = 3 transformation layers
   - Error manifested far from actual cause
   - Sometimes simpler architecture is better

3. **Reuse Through Layers, Not Code Duplication**
   - Both Lambdas share inference, data fetching, feature extraction
   - Layers enable code sharing across different handler patterns

4. **Version Pinning Matters for ML**
   - sklearn 1.7.2 produced warnings with models trained on 1.3.0
   - Pinned to `scikit-learn>=1.3.0,<1.4.0` for compatibility

### Process Lessons

1. **Systematic Debugging**
   - Documented each attempt with hypothesis/test/result
   - Kept CloudWatch logs correlation
   - Eventually traced to exact root cause

2. **Know When to Pivot**
   - Spent time trying to fix existing architecture
   - Two-Lambda solution was cleaner than fighting middleware

3. **Separation of Concerns Wins**
   - HTTP streaming has different requirements than action groups
   - Clean separation made both work correctly

---

## Part 7: Interview Q&A

### Q: "Walk me through how you debugged this issue."

> "The error message was misleading - it said 'null was returned' but my Lambda was clearly returning data. I verified this via CloudWatch logs showing successful ML inference. So I knew the issue was in how the response was formatted, not the data itself.

> I systematically tried different approaches: first checking for serialization issues like NaN values, then trying to pre-format the response, then setting explicit content types. Each attempt taught me more about the system.

> The breakthrough came when I traced through the middleware source code and discovered Bedrock does exact string matching on 'application/json'. FastAPI adds '; charset=utf-8' automatically, which broke the match. The error message made sense then - Bedrock couldn't find the key it was looking for, so it returned null."

### Q: "Why didn't you just modify the middleware?"

> "I considered it, but I chose the Two-Lambda approach for several reasons:

> First, separation of concerns - HTTP streaming and Bedrock action groups have fundamentally different requirements. Mixing them in one handler adds complexity.

> Second, maintainability - relying on a custom fork of third-party middleware creates long-term maintenance burden.

> Third, reusability - both Lambdas share the same code through Lambda Layers. The inference logic, data fetching, and feature extraction are identical. Only the request/response handling differs."

### Q: "What would you do differently?"

> "I would have investigated the middleware source code earlier. I spent time trying fixes at the wrong layer. When you're debugging distributed systems with multiple abstraction layers, it pays to trace through the actual transformations happening at each step.

> Also, I'd set up better observability from the start - capturing the exact Lambda response before Bedrock processed it would have revealed the key mismatch immediately."

### Q: "How does this demonstrate value investor analysis?"

> "The system implements Warren Buffett's value investing principles through specialized ML models:

> - Debt Expert analyzes leverage ratios and interest coverage
> - Cashflow Expert evaluates free cash flow quality and capital allocation
> - Growth Expert assesses sustainable competitive advantage through margins and returns

> Each expert gets 5 years of financial data and an XGBoost prediction. The Supervisor synthesizes their analyses, grounding recommendations in Buffett's documented philosophy from shareholder letters stored in a Pinecone knowledge base."

---

## Appendix: Technical References

### Files Modified/Created

| File | Purpose |
|------|---------|
| `action_group_handler.py` | Pure Python Lambda handler for Bedrock |
| `data_fetcher_action.tf` | Terraform for new Lambda + IAM |
| `requirements-ml.txt` | Pinned sklearn version |
| `value_investor_action.yaml` | OpenAPI schema for action group |

### Infrastructure

| Component | Value |
|-----------|-------|
| Lambda Runtime | Python 3.11 (zip deployment) |
| ML Layer | 60MB via S3 upload |
| Memory | 1024 MB |
| Timeout | 30 seconds |

### Key AWS Services Used

- **Bedrock Agents:** Multi-agent orchestration
- **Bedrock Action Groups:** Lambda integration
- **Lambda Layers:** Code sharing (inference, data)
- **DynamoDB:** Financial data cache
- **S3:** XGBoost model storage
- **Secrets Manager:** API keys (FMP)

---

*Document prepared for technical interview discussions*
*Last updated: December 15, 2025*
