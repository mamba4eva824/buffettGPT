# Bedrock Lambda Data Formatting Issue

## Executive Summary

**Status**: UNRESOLVED
**Date**: December 10, 2025
**Affected Component**: AWS Bedrock Action Group Lambda Integration
**Impact**: Financial data from Lambda cannot be delivered to Bedrock expert agents

### Problem Statement
The Lambda function successfully retrieves financial data and runs ML inference, but AWS Bedrock rejects the Lambda response with `dependencyFailedException`. This prevents the multi-agent financial analysis system from functioning correctly.

### Business Impact
- Users cannot receive detailed financial analysis with real data
- Expert agents (debt, cashflow, growth) cannot access ML predictions
- Supervisor synthesis operates without underlying financial data
- System falls back to generic responses without company-specific insights

---

## Technical Analysis

### Architecture Overview

```
User Search Request
       │
       ▼
┌──────────────────┐
│ Lambda Function  │
│ (prediction-     │
│  ensemble)       │
└────────┬─────────┘
         │ Lambda Web Adapter
         │ + FastAPI + Uvicorn
         ▼
┌──────────────────┐
│ /analyze         │
│ endpoint         │
│ (via middleware) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐      ┌──────────────────┐
│ BedrockAgent     │ ───► │ AWS Bedrock      │
│ Middleware       │      │ Agent Runtime    │
│ (lwa-fastapi-    │      │                  │
│  middleware-     │      │ Expects specific │
│  bedrock-agent)  │      │ JSON format      │
└──────────────────┘      └──────────────────┘
                                   │
                                   ▼
                          dependencyFailedException
```

### The Root Cause

AWS Bedrock Action Groups require a **very specific JSON response format**:

```json
{
    "messageVersion": "1.0",
    "response": {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "httpStatusCode": 200,
        "responseBody": {
            "application/json": {        ← EXACT KEY REQUIRED
                "body": "{...}"          ← MUST BE JSON STRING, NOT OBJECT
            }
        }
    }
}
```

**Critical Requirements**:
1. The `responseBody` content-type key must be exactly `"application/json"` (no charset suffix)
2. The `body` field must contain a **JSON string**, not a nested object
3. The `messageVersion` must be `"1.0"`

### What's Happening

The Lambda Web Adapter architecture creates a complex response transformation chain:

1. **Lambda Event Received**: Bedrock sends action group invocation
2. **Lambda Web Adapter**: Converts Lambda event to HTTP request
3. **BedrockAgentMiddleware**: Translates HTTP request for FastAPI
4. **FastAPI /analyze**: Processes request, returns response
5. **BedrockAgentMiddleware**: Transforms HTTP response back to Lambda format
6. **Lambda Web Adapter**: Returns response to Bedrock
7. **Bedrock**: Rejects with `dependencyFailedException`

**The middleware transformation is the problem**. When FastAPI returns a response:
- FastAPI sets `Content-Type: application/json; charset=utf-8` (with charset!)
- The middleware uses this content-type as the key in `responseBody`
- Result: `"application/json; charset=utf-8"` instead of `"application/json"`
- Bedrock cannot parse this format

### Evidence from CloudWatch Logs

```
[ANALYZE_ENDPOINT] growth inference: BUY (77%)
[ANALYZE_ENDPOINT] debt inference: SELL (54%)
[ANALYZE_ENDPOINT] cashflow inference: BUY (83%)
[ANALYZE_ENDPOINT] Successfully processed AAPL
...
dependencyFailedException: The server encountered an error processing
the Lambda response. Check the Lambda response and retry the request
```

The Lambda successfully:
- Retrieves financial data from DynamoDB
- Extracts features from raw financials
- Runs XGBoost ML inference for each expert type
- Returns success status

But Bedrock immediately rejects the response format.

---

## Attempted Solutions

### Version 1.9.1 - Platform Architecture Fix
**Problem**: `Extension.LaunchError` - Lambda couldn't start
**Cause**: Docker built ARM64 on M1/M2 Mac, Lambda requires x86_64
**Fix**: `docker build --platform linux/amd64`
**Result**: Lambda starts correctly, but `dependencyFailedException` appeared

### Version 1.9.2 - NaN Sanitization
**Hypothesis**: NaN/Infinity values in response causing JSON serialization issues
**Fix**: Added `sanitize_for_json()` to convert NaN/Infinity to `None`
**Result**: Did not resolve issue - NaN sanitization was not the root cause

### Version 1.9.3 - Pre-wrapped Bedrock Response
**Hypothesis**: Bypass middleware by returning full Bedrock format directly
**Fix**: Used `format_action_group_response()` to return complete Bedrock format
**Result**: Did not resolve - middleware double-wrapped the already-wrapped response

### Version 1.9.4 - Explicit Content-Type
**Hypothesis**: Middleware uses response Content-Type as key
**Fix**: Return `JSONResponse(content=response_body, media_type="application/json")`
**Result**: Did not resolve - middleware still produces incompatible format

---

## Files Involved

### Lambda Application
| File | Purpose |
|------|---------|
| `app.py` | FastAPI application with `/analyze` endpoint |
| `handlers/action_group.py` | Action group response formatting utilities |
| `models/schemas.py` | JSON serialization, NaN sanitization |
| `services/inference.py` | XGBoost ML model inference |
| `utils/fmp_client.py` | Financial data retrieval |

### Response Formatting Code

**Current Implementation** (`app.py:619-627`):
```python
logger.info(f"[ANALYZE_ENDPOINT] Successfully processed {ticker}")
return JSONResponse(
    content=response_body,
    media_type="application/json"
)
```

**Correct Bedrock Format** (`handlers/action_group.py:44-64`):
```python
def format_action_group_response(action_group, api_path, response_body):
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {      # No charset!
                    'body': json_dumps(response_body)  # String!
                }
            }
        }
    }
```

---

## Potential Solutions to Explore

### Option A: Bypass Lambda Web Adapter Entirely
Change the Lambda to use `handler.py` directly instead of uvicorn:
- Detect action group events at Lambda handler level
- Return properly formatted response directly to Lambda runtime
- Use FastAPI only for HTTP requests (Function URL)

**Pros**: Direct control over response format
**Cons**: Requires significant architectural change

### Option B: Custom Middleware
Replace `lwa-fastapi-middleware-bedrock-agent` with custom middleware that:
- Uses exact `"application/json"` key (no charset)
- Properly stringifies the response body
- Handles all Bedrock format requirements

**Pros**: Clean integration with existing FastAPI app
**Cons**: Maintenance burden for custom code

### Option C: Lambda Response Streaming
Use a different Lambda invocation mode:
- Configure Lambda for direct invocation (not HTTP proxy)
- Handle action groups without Lambda Web Adapter
- Return responses directly to Bedrock runtime

**Pros**: Eliminates middleware layer
**Cons**: Requires infrastructure changes

### Option D: Debug Middleware Source
Investigate `lwa-fastapi-middleware-bedrock-agent`:
- Find where content-type key is set
- Determine if configuration option exists
- Consider contributing fix upstream

**Pros**: Could benefit community
**Cons**: Depends on third-party package maintainer

---

## Current Lambda Configuration

| Setting | Value |
|---------|-------|
| **Function Name** | buffett-dev-prediction-ensemble |
| **Runtime** | Container (Python 3.11) |
| **Architecture** | x86_64 |
| **Memory** | 1024 MB |
| **Image Version** | v1.9.4 |
| **Entry Point** | uvicorn app:app |
| **Web Adapter** | aws-lambda-adapter:0.8.4 |
| **Middleware** | lwa-fastapi-middleware-bedrock-agent>=0.0.4 |

---

## Recommended Next Steps

1. **Immediate**: Investigate Option A - bypass Lambda Web Adapter for action groups
2. **Short-term**: Research Option D - middleware source code analysis
3. **Medium-term**: Consider Option B if no upstream fix available
4. **Fallback**: Direct Bedrock API integration without action groups

---

## Appendix: Bedrock Action Group Event Format

### Incoming Event from Bedrock
```json
{
    "messageVersion": "1.0",
    "actionGroup": "FinancialAnalysis",
    "apiPath": "/analyze",
    "httpMethod": "POST",
    "requestBody": {
        "content": {
            "application/json": {
                "properties": [
                    {"name": "ticker", "type": "string", "value": "AAPL"},
                    {"name": "analysis_type", "type": "string", "value": "debt"}
                ]
            }
        }
    },
    "agent": {
        "name": "buffett-dev-debt-expert",
        "id": "LUOMTWUFPI",
        "alias": "TSTALIASID"
    },
    "sessionId": "supervisor-xxx-debt"
}
```

### Expected Response Format
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
                "body": "{\"ticker\":\"AAPL\",\"model_inference\":{\"debt\":{\"prediction\":\"SELL\",\"confidence\":0.54}},\"value_metrics\":{...}}"
            }
        }
    }
}
```

---

*Document last updated: December 10, 2025*
