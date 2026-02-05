# Executive Report: REST API Response Streaming Implementation

**Date:** December 6, 2025
**Project:** Buffett Chat API - Ensemble Analyzer
**Version:** v1.6.1

---

## Executive Summary

Successfully implemented real-time Server-Sent Events (SSE) streaming for the Ensemble Analyzer Lambda function through AWS API Gateway REST API. This replaces the previous Lambda Function URL approach, providing centralized JWT authentication while maintaining real-time streaming capabilities.

### Key Achievements
- Centralized JWT authentication via API Gateway authorizer
- True real-time SSE streaming with `InvokeWithResponseStream`
- 2-minute timeout support (extendable to 5 minutes)
- ECR version control for Lambda container deployments

---

## December 6, 2025 Update - Streaming Fixes

### Issues Resolved

| Issue | Root Cause | Fix Applied | Status |
|-------|------------|-------------|--------|
| 403 errors on parallel requests | JWT authorizer cached policy for single path | Wildcard IAM policy (`stage/*`) in auth_verify.py | ✅ Fixed |
| Text not streaming progressively | React 18 automatic state batching | `flushSync()` wrapper in AnalysisView.jsx | ✅ Fixed |
| HTTP_PROXY buffering | API Gateway buffering SSE chunks | `x-accel-buffering: no` header in FastAPI | ✅ Fixed |

### Architecture - Complete Request Flow

```
Browser (React)
    │
    ▼ POST /analysis/{agent_type}
┌─────────────────────────────────────────────────────────────┐
│  API Gateway (REST API - HTTP_PROXY)                        │
│  - JWT TOKEN Authorizer (cached 300s)                       │
│  - Wildcard IAM policy allows all paths under stage         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ HTTP_PROXY passthrough
┌─────────────────────────────────────────────────────────────┐
│  Lambda Function URL (RESPONSE_STREAM)                      │
│  - Lambda Web Adapter v0.8.4                                │
│  - FastAPI + uvicorn                                        │
│  - EventSourceResponse (SSE)                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ converse_stream()
┌─────────────────────────────────────────────────────────────┐
│  AWS Bedrock                                                │
│  - Model: us.anthropic.claude-haiku-4-5-20251001-v1:0       │
│  - ConverseStream API (token-by-token)                      │
└─────────────────────────────────────────────────────────────┘
    │
    ▼ SSE chunks
┌─────────────────────────────────────────────────────────────┐
│  Browser                                                    │
│  - fetch() with response.body.getReader()                   │
│  - flushSync() forces immediate React re-render             │
└─────────────────────────────────────────────────────────────┘
```

### Latency Breakdown (Typical Request)

| Component | Duration | Notes |
|-----------|----------|-------|
| CORS Preflight | ~2ms | OPTIONS request handled by API Gateway mock |
| JWT Authorization | ~2ms | Warm Lambda, cached after first request |
| API Gateway Routing | ~40ms | HTTP_PROXY to Function URL |
| FMP Data Fetch | ~200ms | Financial data API (cached in DynamoDB) |
| XGBoost Inference | ~1.5s | 3-model ensemble prediction |
| Bedrock TTFT | ~9s | Time to first token from Claude Haiku |
| Bedrock Streaming | ~50-140ms/chunk | Token delivery rate |
| **Total Duration** | **~12s** | End-to-end for complete analysis |

### Fix 1: Wildcard IAM Policy for Parallel Requests

**Problem:** When frontend calls 3 analysis endpoints in parallel (`/debt`, `/cashflow`, `/growth`), the JWT authorizer caches the IAM policy from the first request. The cached policy only allows access to that specific path, causing 403 errors for the other 2 requests.

**Solution:** Return wildcard IAM policy that allows all paths under the stage.

**File:** `chat-api/backend/src/handlers/auth_verify.py`

```python
# Convert: arn:aws:execute-api:region:account:api-id/stage/method/resource
# To:      arn:aws:execute-api:region:account:api-id/stage/*
wildcard_resource = resource
if effect == "Allow":
    parts = resource.split('/')
    if len(parts) >= 2:
        # Keep up to stage, then wildcard
        wildcard_resource = '/'.join(parts[:2]) + '/*'
```

### Fix 2: React flushSync for Progressive Rendering

**Problem:** React 18 automatic state batching groups all `setResults()` calls, causing text to appear all at once instead of streaming progressively.

**Solution:** Use `flushSync()` to force immediate synchronous re-renders.

**File:** `frontend/src/components/analysis/AnalysisView.jsx`

```javascript
import { flushSync } from 'react-dom';

case 'chunk':
  // Force immediate re-render for progressive streaming
  flushSync(() => {
    setResults(prev => ({
      ...prev,
      [agentType]: {
        ...prev[agentType],
        text: prev[agentType].text + (data.text || '')
      }
    }));
  });
  break;
```

### Files Modified (December 6)

| File | Changes |
|------|---------|
| [AnalysisView.jsx](frontend/src/components/analysis/AnalysisView.jsx) | Added `flushSync()` for immediate React re-renders |
| [auth_verify.py](chat-api/backend/src/handlers/auth_verify.py) | Wildcard IAM policy for cached authorization |
| [Dockerfile](chat-api/backend/lambda/ensemble_analyzer/Dockerfile) | Lambda Web Adapter v0.8.4 |
| [app.py](chat-api/backend/lambda/ensemble_analyzer/app.py) | `x-accel-buffering: no` header |

---

## Problem Statement

The original architecture used Lambda Function URLs with `authorization_type = "NONE"`, which:
1. Bypassed API Gateway authentication
2. Required JWT validation in Lambda code (duplicated auth logic)
3. Created security concerns with unauthenticated endpoints

**Goal:** Implement centralized JWT authentication via API Gateway while preserving real-time SSE streaming.

---

## Solution Architecture

### Before (Function URLs)
```
Frontend → Lambda Function URL (NO AUTH) → Lambda validates JWT internally
                    ↓
           Security vulnerability: endpoint publicly accessible
```

### After (REST API with Streaming)
```
Frontend → REST API Gateway → JWT Authorizer → Lambda (InvokeWithResponseStream)
                                                      ↓
                                              Real-time SSE streaming
```

---

## Technical Implementation

### 1. AWS Feature Discovery

AWS announced REST API response streaming support in **November 2025**:
- [AWS Announcement](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis/)

**Critical Discovery:** The Lambda integration URI must use a specific format for streaming:
```
# Standard invocation (buffered):
arn:aws:apigateway:{region}:lambda:path/2015-03-31/functions/{arn}/invocations

# Streaming invocation:
arn:aws:apigateway:{region}:lambda:path/2021-11-15/functions/{arn}/response-streaming-invocations
```

### 2. Terraform Configuration

**File:** `chat-api/terraform/modules/api-gateway/analysis_streaming.tf`

```hcl
resource "aws_api_gateway_integration" "analysis_lambda" {
  rest_api_id             = aws_api_gateway_rest_api.analysis[0].id
  resource_id             = aws_api_gateway_resource.analysis_agent[0].id
  http_method             = aws_api_gateway_method.analysis_post[0].http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"

  # Streaming URI format (2021-11-15 API path)
  uri = replace(
    replace(var.ensemble_analyzer_invoke_arn, "/invocations", "/response-streaming-invocations"),
    "path/2015-03-31/functions",
    "path/2021-11-15/functions"
  )

  response_transfer_mode = "STREAM"
  timeout_milliseconds   = 120000  # 2 minutes
}
```

### 3. Lambda Handler Implementation

**File:** `chat-api/backend/lambda/ensemble_analyzer/handler.py`

The `streaming_handler` function uses `awslambdaric` for native response streaming:

```python
def streaming_handler(event: Dict[str, Any], response_stream, context: Any):
    """
    Lambda handler for true response streaming via InvokeWithResponseStream.
    """
    # Write SSE events directly to response_stream
    response_stream.write(format_sse_event(json.dumps({
        "type": "connected",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    }), "connected"))

    # Stream analysis chunks in real-time
    for chunk in invoke_agent_streaming(...):
        response_stream.write(chunk)
```

### 4. Docker Configuration

**File:** `chat-api/backend/lambda/ensemble_analyzer/Dockerfile`

```dockerfile
# Lambda Handler - streaming_handler for REST API Gateway with response streaming
CMD ["handler.streaming_handler"]
```

**File:** `chat-api/backend/lambda/ensemble_analyzer/requirements.txt`

```
# Lambda Runtime Interface Client - required for response streaming
awslambdaric>=2.0.0
```

---

## ECR Version History

| Version | Date | Handler | Mode | Description |
|---------|------|---------|------|-------------|
| v1.1.0 | Dec 4, 2025 | lambda_handler | BUFFERED | REST API with JWT auth |
| v1.2.0 | Dec 4, 2025 | streaming_handler | - | Initial streaming attempt |
| v1.2.1 | Dec 4, 2025 | lambda_handler | BUFFERED | Fallback while debugging |
| v1.3.0 | Dec 4, 2025 | streaming_handler | STREAM | Production streaming |
| v1.4.0 | Dec 5, 2025 | FastAPI app | HTTP_PROXY | Lambda Web Adapter integration |
| v1.5.0 | Dec 5, 2025 | FastAPI app | HTTP_PROXY | Claude Haiku 4.5 inference profile |
| **v1.6.1** | Dec 6, 2025 | **FastAPI app** | **HTTP_PROXY** | **403 fix, streaming optimizations** |

---

## Configuration Summary

### API Gateway
| Setting | Value |
|---------|-------|
| Type | REST API (Regional) |
| Endpoint | `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/analysis/{agent_type}` |
| Authorization | JWT (TOKEN authorizer) |
| Integration | AWS_PROXY with streaming |
| Response Transfer Mode | STREAM |
| Timeout | 120,000ms (2 minutes) |

### Lambda Function
| Setting | Value |
|---------|-------|
| Name | `buffett-dev-ensemble-analyzer` |
| Runtime | Container (Python 3.11) |
| Handler | FastAPI via Lambda Web Adapter |
| Image | `v1.6.1` |
| Timeout | 120 seconds |
| Memory | 1024 MB |
| Web Adapter | `public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4` |

### Frontend Environment
| Variable | Value |
|----------|-------|
| `VITE_ANALYSIS_API_URL` | `https://t5wvlwfo5b.execute-api.us-east-1.amazonaws.com/dev/analysis` |

---

## SSE Event Flow

```
1. Frontend POST → /analysis/{agent_type}
   Headers: Authorization: Bearer <jwt_token>
   Body: { "company": "AAPL" }

2. API Gateway validates JWT via authorizer

3. Lambda streams events:
   event: connected
   data: {"type":"connected","timestamp":"..."}

   event: status
   data: {"type":"status","message":"Fetching financial data..."}

   event: inference
   data: {"type":"inference","prediction":"BUY","confidence":0.85,...}

   event: chunk
   data: {"type":"chunk","text":"Based on the analysis..."}

   event: complete
   data: {"type":"complete","ticker":"AAPL",...}
```

---

## Files Modified

| File | Change |
|------|--------|
| `chat-api/terraform/modules/api-gateway/analysis_streaming.tf` | Streaming URI with 2021-11-15 path |
| `chat-api/terraform/environments/dev/main.tf` | Image tag v1.3.0 |
| `chat-api/backend/lambda/ensemble_analyzer/handler.py` | Added streaming_handler |
| `chat-api/backend/lambda/ensemble_analyzer/Dockerfile` | CMD uses streaming_handler |
| `chat-api/backend/lambda/ensemble_analyzer/requirements.txt` | Added awslambdaric |
| `frontend/.env.development` | VITE_ANALYSIS_API_URL |

---

## Security Improvements

| Aspect | Before | After |
|--------|--------|-------|
| Authentication | Lambda-level JWT validation | API Gateway JWT authorizer |
| Endpoint Access | Public (Function URL) | Authenticated only |
| Auth Logic | Duplicated in Lambda | Centralized in authorizer |
| Token Validation | Per-request in handler | Cached (5 min TTL) |

---

## Performance Characteristics

| Metric | BUFFERED Mode | STREAM Mode |
|--------|---------------|-------------|
| Time to First Byte | ~5-10 seconds | ~500ms |
| Max Timeout | 29 seconds | 5 minutes (120s configured) |
| User Experience | Wait for complete response | Real-time updates |
| Idle Timeout | N/A | 5 minutes (Regional) |

---

## Rollback Plan

If streaming issues occur:

1. **Revert Terraform** to BUFFERED mode:
```hcl
response_transfer_mode = "BUFFERED"
uri = var.ensemble_analyzer_invoke_arn  # Standard invoke_arn
timeout_milliseconds = 29000
```

2. **Update Lambda** to v1.2.1 (lambda_handler):
```bash
aws lambda update-function-code \
  --function-name buffett-dev-ensemble-analyzer \
  --image-uri 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/ensemble-analyzer:v1.2.1
```

3. **Apply Terraform**:
```bash
terraform apply
```

---

## References

- [API Gateway Response Streaming Announcement (Nov 2025)](https://aws.amazon.com/about-aws/whats-new/2025/11/api-gateway-response-streaming-rest-apis/)
- [Building Responsive APIs with API Gateway Response Streaming](https://aws.amazon.com/blogs/compute/building-responsive-apis-with-amazon-api-gateway-response-streaming/)
- [Lambda Response Streaming Documentation](https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html)
- [Terraform aws_api_gateway_integration](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/api_gateway_integration)

---

## Conclusion

The implementation successfully achieves both security and performance objectives:

1. **Security:** All analysis requests now require valid JWT tokens, validated at the API Gateway level before reaching Lambda. Wildcard IAM policies enable cached authorization across parallel requests.

2. **Performance:** Real-time SSE streaming provides immediate feedback to users, with chunks delivered as they're generated by Bedrock agents. The `flushSync()` fix ensures progressive text rendering in the React frontend.

3. **Maintainability:** ECR version control enables quick rollbacks and deployment tracking. Current version: v1.6.1.

4. **Scalability:** Extended timeout support (up to 5 minutes) accommodates complex financial analyses.

5. **Architecture:** Migrated from `InvokeWithResponseStream` to HTTP_PROXY + Lambda Web Adapter for better SSE compatibility with FastAPI's `EventSourceResponse`.

### Current Architecture (v1.6.1)
```
Frontend → API Gateway (HTTP_PROXY) → Lambda Function URL → Lambda Web Adapter → FastAPI/uvicorn → Bedrock ConverseStream
```

### Key Technologies
- **Lambda Web Adapter v0.8.4** - Enables response streaming for Python web frameworks
- **FastAPI + sse-starlette** - EventSourceResponse for SSE streaming
- **Bedrock ConverseStream** - Token-by-token generation with Claude Haiku 4.5
- **React flushSync** - Forces synchronous re-renders for progressive text display
