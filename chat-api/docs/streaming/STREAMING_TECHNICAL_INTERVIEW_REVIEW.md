# Technical Interview Review: AWS Serverless Streaming Architecture

**Project:** Real-Time Financial Analysis API with SSE Streaming
**Technologies:** AWS Lambda, API Gateway, Bedrock, Terraform, Python, FastAPI, Docker

---

## Project Overview

Designed and implemented a real-time streaming API that combines machine learning inference with large language model analysis to provide investment recommendations. The system streams responses progressively using Server-Sent Events (SSE), reducing perceived latency from 30+ seconds to under 3 seconds for first content.

---

## Technical Challenges & Solutions

### Challenge 1: API Gateway Streaming Limitations

**Problem Statement:**
AWS API Gateway's native Lambda integration (`AWS_PROXY`) doesn't support standard SSE streaming. When Lambda returns a streaming response, API Gateway requires a proprietary format with 8-null-byte delimiters between chunks, which browsers cannot parse natively.

**Investigation Process:**
1. Tested `AWS_PROXY` integration with Lambda response streaming
2. Observed "Missing delimiter in response" errors in CloudWatch
3. Researched AWS documentation on Lambda response streaming
4. Discovered the delimiter requirement is specific to `AWS_PROXY` type

**Solution Implemented:**
Used `HTTP_PROXY` integration type that routes requests to a Lambda Function URL:

```terraform
resource "aws_api_gateway_integration" "analysis_lambda" {
  type                    = "HTTP_PROXY"
  integration_http_method = "POST"
  uri = "${trimsuffix(var.ensemble_analyzer_function_url, "/")}/analysis/{agent_type}"

  request_parameters = {
    "integration.request.path.agent_type" = "method.request.path.agent_type"
  }
}
```

**Why This Works:**
- Lambda Function URLs support native HTTP streaming
- `HTTP_PROXY` passes the response through unchanged
- Browsers receive standard SSE format directly

**Trade-offs Considered:**
| Option | Pros | Cons |
|--------|------|------|
| AWS_PROXY + custom parsing | Single endpoint | Requires client-side delimiter parsing |
| HTTP_PROXY to Function URL | Native SSE support | Additional endpoint to secure |
| WebSocket API | Bidirectional | More complex client implementation |

---

### Challenge 2: Authentication Architecture

**Problem Statement:**
Lambda Function URLs are public endpoints. We needed centralized JWT authentication without exposing the Function URL directly to users.

**Solution Architecture:**

```
┌──────────┐    ┌─────────────────┐    ┌──────────────┐    ┌────────────────┐
│  Client  │───▶│  REST API GW    │───▶│  Function    │───▶│  Lambda        │
│          │    │  + JWT Auth     │    │  URL         │    │  (FastAPI)     │
└──────────┘    └─────────────────┘    └──────────────┘    └────────────────┘
                       │
                 ┌─────▼─────┐
                 │ Custom    │
                 │ Authorizer│
                 │ Lambda    │
                 └───────────┘
```

**Implementation Details:**

1. **Custom Lambda Authorizer:**
```python
def lambda_handler(event, context):
    token = event.get('authorizationToken', '').replace('Bearer ', '')

    try:
        payload = jwt.decode(token, secret, algorithms=['HS256'])
        return generate_policy(payload['sub'], 'Allow', event['methodArn'])
    except jwt.ExpiredSignatureError:
        raise Exception('Unauthorized')
```

2. **API Gateway Authorizer Configuration:**
```terraform
resource "aws_api_gateway_authorizer" "analysis_jwt" {
  name                             = "jwt-authorizer"
  rest_api_id                      = aws_api_gateway_rest_api.analysis[0].id
  type                             = "TOKEN"
  authorizer_uri                   = var.auth_verify_invoke_arn
  identity_source                  = "method.request.header.Authorization"
  authorizer_result_ttl_in_seconds = 300  # Cache for 5 minutes
}
```

**Security Consideration:**
The Function URL is technically public, but:
- Users only know the API Gateway endpoint (documented)
- Function URL is not advertised
- Could add IAM auth to Function URL for defense-in-depth

---

### Challenge 3: Bedrock Model Inference Profile

**Problem Statement:**
Claude Haiku 4.5 returned an error when invoked directly:
```
Invocation of model ID anthropic.claude-haiku-4-5-20251001-v1:0
with on-demand throughput isn't supported.
```

**Root Cause Analysis:**
Newer Anthropic models on Bedrock require cross-region inference profiles for on-demand invocation. This is AWS's mechanism for load balancing across regions.

**Solution:**
Changed model ID format from direct to inference profile:

```python
# Before (doesn't work)
model_id = "anthropic.claude-haiku-4-5-20251001-v1:0"

# After (works)
model_id = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
```

**Key Learning:**
The `us.` prefix indicates a US cross-region inference profile, which routes requests through AWS's inference infrastructure.

---

### Challenge 4: Model Parameter Constraints

**Problem Statement:**
After fixing the model ID, received a new error:
```
temperature and top_p cannot both be specified for this model
```

**Solution:**
Removed `topP` from the inference configuration:

```python
# Before
inferenceConfig = {
    "maxTokens": 2048,
    "temperature": 0.7,
    "topP": 0.9  # Causes error with Claude Haiku 4.5
}

# After
inferenceConfig = {
    "maxTokens": 2048,
    "temperature": 0.7
    # Claude Haiku 4.5 doesn't allow both temperature and topP
}
```

**Technical Insight:**
Different LLMs have different parameter constraints. Always check model-specific documentation and handle parameter validation gracefully.

---

## Architecture Deep Dive

### Lambda Container Architecture

```dockerfile
# Base: AWS Lambda Python runtime
FROM public.ecr.aws/lambda/python:3.11

# Lambda Web Adapter for HTTP streaming
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 \
     /lambda-adapter /opt/extensions/lambda-adapter

# FastAPI application
COPY app.py handler.py ./

# Configuration for response streaming
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080

# Run FastAPI directly (not Lambda handler)
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Key Points:**
- Lambda Web Adapter acts as a proxy between Lambda runtime and HTTP app
- `RESPONSE_STREAM` mode enables chunked transfer encoding
- Standard ASGI server (uvicorn) handles HTTP natively

### SSE Generator Pattern

```python
async def generate_analysis_stream(ticker: str, agent_type: str) -> AsyncGenerator:
    """Async generator that yields SSE-formatted events."""

    # 1. Connection event
    yield {"event": "connected", "data": json.dumps({"type": "connected"})}

    # 2. Progress events
    yield {"event": "status", "data": json.dumps({"message": "Fetching data..."})}

    # 3. ML inference result
    inference_result = run_xgboost_inference(ticker, agent_type)
    yield {"event": "inference", "data": json.dumps(inference_result)}

    # 4. Stream Bedrock response
    async for chunk in stream_bedrock_converse(ticker, inference_result):
        yield {"event": "chunk", "data": json.dumps({"text": chunk})}

    # 5. Completion event
    yield {"event": "complete", "data": json.dumps({"status": "done"})}
```

### Bedrock ConverseStream Integration

```python
async def stream_bedrock_converse(ticker: str, inference_result: dict):
    """Stream responses from Bedrock using ConverseStream API."""

    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

    response = bedrock.converse_stream(
        modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
        messages=[{
            "role": "user",
            "content": [{"text": build_prompt(ticker, inference_result)}]
        }],
        inferenceConfig={"maxTokens": 2048, "temperature": 0.7}
    )

    for event in response.get('stream', []):
        if 'contentBlockDelta' in event:
            delta = event['contentBlockDelta'].get('delta', {})
            if 'text' in delta:
                yield delta['text']

        if 'metadata' in event:
            # Token usage available here
            usage = event['metadata'].get('usage', {})
            logger.info(f"Tokens: {usage}")
```

---

## Infrastructure as Code (Terraform)

### Module Structure

```
terraform/
├── environments/
│   └── dev/
│       └── main.tf           # Environment orchestration
└── modules/
    ├── api-gateway/
    │   ├── main.tf           # HTTP API (existing)
    │   └── analysis_streaming.tf  # REST API for SSE
    ├── lambda/
    │   ├── main.tf           # Zip-based Lambdas
    │   └── ensemble_analyzer_docker.tf  # Container Lambda
    └── bedrock/
        └── main.tf           # Agent configuration
```

### Deployment Pipeline

```bash
# 1. Build and push Docker image
docker build --platform linux/amd64 \
  -t $ECR_REPO:v1.6.4 .
docker push $ECR_REPO:v1.6.4

# 2. Update Terraform configuration
# main.tf: ensemble_analyzer_image_tag = "v1.6.4"

# 3. Apply infrastructure changes
terraform plan
terraform apply

# 4. Verify deployment
aws lambda get-function --function-name buffett-dev-ensemble-analyzer \
  --query 'Code.ImageUri'
```

---

## Testing & Debugging

### Local Testing

```bash
# Test Lambda Function URL directly (bypasses auth)
curl -X POST "https://<function-url>/analysis/debt" \
  -H "Content-Type: application/json" \
  -d '{"company":"AAPL","fiscal_year":2024}'
```

### Production Testing

```bash
# Test via API Gateway (with auth)
curl -X POST "https://<api-gw>/dev/analysis/debt" \
  -H "Authorization: Bearer <jwt>" \
  -H "Content-Type: application/json" \
  -d '{"company":"AAPL","fiscal_year":2024}'
```

### CloudWatch Debugging

```bash
# API Gateway execution logs
aws logs tail "API-Gateway-Execution-Logs_<api-id>/dev" --follow

# Lambda logs
aws logs tail "/aws/lambda/buffett-dev-ensemble-analyzer" --follow
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Cold start time | ~3-5 seconds |
| Time to first SSE event | ~2 seconds |
| ML inference time | ~15-18 seconds |
| Bedrock streaming start | ~1 second after inference |
| Total analysis time | 30-45 seconds |
| Chunk delivery latency | ~100ms |

---

## Key Takeaways

1. **API Gateway Streaming:** `AWS_PROXY` integration doesn't support browser-compatible SSE; use `HTTP_PROXY` to Lambda Function URLs instead.

2. **Authentication Patterns:** Centralize auth at API Gateway even when using Function URLs; authorizer caching reduces latency.

3. **Model Versioning:** Bedrock model IDs change format over time; use inference profiles for newer models.

4. **Container Lambdas:** Lambda Web Adapter enables standard web frameworks; great for complex applications.

5. **Infrastructure as Code:** Terraform enables reproducible deployments and clear documentation of architecture decisions.

---

## Questions I Can Answer

1. **Why not use WebSocket instead of SSE?**
   - SSE is simpler for one-way streaming
   - Better browser support without additional libraries
   - WebSocket would be appropriate if we needed bidirectional communication

2. **How would you scale this to handle more traffic?**
   - Lambda scales automatically
   - Bedrock has per-account quotas; would request increases
   - Consider provisioned concurrency for consistent cold starts
   - Response caching for frequently requested tickers

3. **What if the streaming connection drops mid-response?**
   - Client implements reconnection logic
   - Could add checkpointing/resumption with session IDs
   - Consider idempotency keys for exactly-once delivery

4. **How do you handle errors during streaming?**
   - Send error event type in SSE stream
   - Client handles gracefully with user feedback
   - CloudWatch alarms on error rates

---

## Repository Structure

```
buffett_chat_api/
├── chat-api/
│   ├── backend/
│   │   ├── lambda/
│   │   │   └── ensemble_analyzer/
│   │   │       ├── Dockerfile
│   │   │       ├── app.py          # FastAPI endpoints
│   │   │       ├── handler.py      # Business logic
│   │   │       └── requirements.txt
│   │   └── src/
│   │       └── utils/              # Shared utilities
│   └── terraform/
│       ├── environments/dev/
│       └── modules/
│           ├── api-gateway/
│           ├── lambda/
│           └── bedrock/
└── frontend/
    └── src/
        └── components/
            └── analysis/           # SSE consumer components
```
