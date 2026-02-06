# Implementation Guide: Token Tracking, Limits, Persistence & Prompt Upgrade for Docker Lambda

## Context

The Docker Lambda (`lambda/investment_research/`) handles followup Q&A with true SSE streaming via FastAPI + LWA. However, it is missing 4 critical features that the zip Lambda (`src/handlers/analysis_followup.py`) has:

1. **Token tracking** - extract usage from Bedrock `converse_stream` metadata events
2. **Token limit enforcement** - pre-request `check_limit()` before streaming
3. **Message persistence** - save user/assistant messages to DynamoDB for conversation history
4. **Production system prompt** - missing jargon entries, tone examples, and AVAILABLE TOOLS section

Additionally, there is a **critical bug**: `user_id` is extracted by JWT middleware but never passed to the followup service.

## Pre-conditions (Already in Place - No Terraform Changes Needed)

- **IAM**: Docker Lambda has DynamoDB access to `token-usage-dev-buffett` and `buffett-dev-chat-messages`
- **Env vars**: `TOKEN_USAGE_TABLE`, `CHAT_MESSAGES_TABLE`, `DEFAULT_TOKEN_LIMIT`, `JWT_SECRET_ARN` already passed via Terraform `common_env_vars` (see `terraform/environments/dev/main.tf:49-79`)
- **Bedrock**: `bedrock:InvokeModelWithResponseStream` permission exists (see `terraform/modules/core/main.tf:102-111`)
- **Function URL**: `RESPONSE_STREAM` mode configured (see `terraform/modules/lambda/investment_research_docker.tf:148-162`)

## Files to Modify

| File | Action | Description |
|------|--------|-------------|
| `lambda/investment_research/services/token_usage_tracker.py` | **CREATE** | Copy from `src/utils/token_usage_tracker.py` |
| `lambda/investment_research/services/followup_service.py` | **MODIFY** | Main implementation (all 4 features) |
| `lambda/investment_research/services/streaming.py` | **MODIFY** | Enrich `followup_end_event` with token usage |
| `lambda/investment_research/app.py` | **MODIFY** | Thread `user_id` from JWT middleware |
| `lambda/investment_research/Dockerfile` | **NO CHANGE** | `COPY services/` already copies all files |

## Reference Files (Read-Only)

| File | Purpose |
|------|---------|
| `src/handlers/analysis_followup.py` | Reference implementation for all 4 features |
| `src/utils/token_usage_tracker.py` | Source file to copy |
| `terraform/environments/dev/main.tf:49-79` | Env vars passed to Docker Lambda |
| `terraform/modules/core/main.tf:64-90` | IAM DynamoDB permissions |

---

## Step 1: Copy TokenUsageTracker into Docker Lambda

**Create**: `lambda/investment_research/services/token_usage_tracker.py`

Copy the entire contents of `src/utils/token_usage_tracker.py` (~940 lines) into `services/token_usage_tracker.py`. No modifications needed.

**Why no changes**: The class is completely self-contained. Dependencies (boto3, datetime, logging, calendar, Decimal, botocore.ClientError) are all available in the Docker image already.

**Why `services/` not `utils/`**: The Docker Lambda has no `utils/` directory. All shared modules live in `services/`. The Dockerfile already has `COPY services/ ./services/` (line 56), so the new file is automatically included in the Docker image.

---

## Step 2: Fix `user_id` Threading (Critical Bug)

**Problem**: JWT middleware extracts `user_id` into `request.state.user_id` (app.py:255) but the `/followup` endpoint never reads it. Without this fix, token tracking and message persistence cannot identify the user.

### app.py changes

**2a.** In the `/followup` endpoint (around line 547), after parsing the request, extract `user_id`:

```python
# Extract user_id from JWT middleware (set by JWTAuthMiddleware)
user_id = getattr(raw_request.state, 'user_id', None)
```

**2b.** Pass `user_id` to `generate_followup_stream()` (around line 549-556):

```python
return EventSourceResponse(
    generate_followup_stream(
        ticker,
        request.question,
        request.conversation_id,
        request.section_id,
        user_id          # NEW PARAMETER
    ),
    media_type="text/event-stream"
)
```

**2c.** Update `generate_followup_stream()` signature (around line 560-565) and pass through:

```python
async def generate_followup_stream(
    ticker: str,
    question: str,
    session_id: str = None,
    section_id: str = None,
    user_id: str = None          # NEW PARAMETER
) -> AsyncGenerator[dict, None]:
```

At line ~583, pass `user_id` to `invoke_followup_agent`:

```python
async for event in invoke_followup_agent(ticker, question, session_id, section_id, user_id):
    yield event
```

### followup_service.py changes

**2d.** Update `invoke_followup_agent` signature (line ~430):

```python
async def invoke_followup_agent(
    ticker: str,
    question: str,
    session_id: Optional[str] = None,
    section_id: Optional[str] = None,
    user_id: Optional[str] = None        # NEW PARAMETER
) -> AsyncGenerator[Dict[str, Any], None]:
```

**2e.** Pass `user_id` and `session_id` to `_stream_claude_response` (line ~477):

```python
async for event in _stream_claude_response(ticker, question, section_context, user_id, session_id):
    yield event
```

**2f.** Update `_stream_claude_response` signature (line ~673):

```python
async def _stream_claude_response(
    ticker: str,
    question: str,
    section_context: Optional[str] = None,
    user_id: Optional[str] = None,       # NEW PARAMETER
    session_id: Optional[str] = None     # NEW PARAMETER (needed for persistence)
) -> AsyncGenerator[Dict[str, Any], None]:
```

---

## Step 3: Fix Env Var Mismatch

**File**: `followup_service.py` line 22

```python
# BEFORE (wrong env var name - works by accident due to hardcoded default):
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_TABLE_V2', 'investment-reports-v2-dev')

# AFTER (matches Terraform's INVESTMENT_REPORTS_V2_TABLE at main.tf:70):
REPORTS_TABLE_V2 = os.environ.get('INVESTMENT_REPORTS_V2_TABLE', 'investment-reports-v2-dev')
```

---

## Step 4: Update Model ID

**File**: `followup_service.py` lines 31-34

```python
# BEFORE (Claude 3.5 Haiku - older):
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-3-5-haiku-20241022-v1:0'
)

# AFTER (Claude Haiku 4.5 - matches zip Lambda at analysis_followup.py:113):
FOLLOWUP_MODEL_ID = os.environ.get(
    'FOLLOWUP_MODEL_ID',
    'us.anthropic.claude-haiku-4-5-20251001-v1:0'
)
```

---

## Step 5: Upgrade System Prompt

**File**: `followup_service.py` - the `system_prompt` string in `_stream_claude_response` (lines ~703-729)

Replace the current system prompt with the production version from the zip Lambda (`analysis_followup.py:452-494`). The differences are:

**Add 2 jargon entries** (after "Net Debt" line):
```
- Operating Cash Flow -> "cash that actually came in"
- Net Cash -> "extra savings after paying all debt"
```

**Add 2 tone examples** (replace the sparse TONE section):
```
TONE:
- Casual and conversational -- like texting a smart friend
- Use analogies: "It's like having a $50K mortgage while keeping $80K in savings"
- Make numbers tangible: "$99B is enough to buy every NFL team... twice"
- Be direct: "Here's the deal..." or "Bottom line:"
```

**Add AVAILABLE TOOLS section** (after TOOL USAGE):
```
AVAILABLE TOOLS:
1. getReportSection(ticker, section_id) - Get report sections:
   07_profit (margins), 06_growth, 08_valuation, 10_cashflow, 11_debt,
   13_bull (bull case), 14_bear (risks), 15_warnings, 01_executive_summary

2. getReportRatings(ticker) - Investment ratings and verdict

3. getMetricsHistory(ticker, metric_type, quarters) - Historical metrics:
   metric_types: revenue_profit, cashflow, balance_sheet, debt_leverage, all
   quarters: 8 (recent) to 20 (long-term)

4. getAvailableReports() - List available company reports
```

**Update context suffix**:
```python
# BEFORE:
Current context: {ticker} investment report{f' | viewing section: {section_context[:200]}' if section_context else ''}

# AFTER:
Current context: {ticker} | followup analysis{f' | viewing section: {section_context[:200]}' if section_context else ''}
```

---

## Step 6: Add Token Limit Enforcement (Pre-Request)

**File**: `followup_service.py`

### 6a. Add imports and module-level initialization

At top of file, add import:
```python
from services.token_usage_tracker import TokenUsageTracker
```

After the existing boto3 client initialization (around line 39), add:
```python
# Token usage tracking
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')
token_tracker = TokenUsageTracker(table_name=TOKEN_USAGE_TABLE) if TOKEN_USAGE_TABLE else TokenUsageTracker()
```

### 6b. Add pre-request check in `_stream_claude_response`

Right after `yield followup_start_event(message_id, ticker)` (line ~743), add:

```python
# TOKEN LIMIT CHECK - Pre-request validation
if user_id:
    limit_check = token_tracker.check_limit(user_id)
    if not limit_check.get('allowed', True):
        logger.warning(f"Token limit exceeded for user {user_id}: {limit_check}")
        yield {
            'event': 'error',
            'data': json.dumps({
                'type': 'token_limit_exceeded',
                'error': 'token_limit_exceeded',
                'message': 'Monthly token limit reached. Usage resets at the start of your next billing period.',
                'usage': {
                    'total_tokens': limit_check.get('total_tokens', 0),
                    'token_limit': limit_check.get('token_limit', 0),
                    'percent_used': limit_check.get('percent_used', 100.0),
                    'reset_date': limit_check.get('reset_date', '')
                },
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            })
        }
        return
```

Reference: zip Lambda at `analysis_followup.py:427-435`

---

## Step 7: Add Token Tracking (Metadata Extraction)

**File**: `followup_service.py` in `_stream_claude_response`

### 7a. Add tracking variables

After the `messages` list initialization (around line ~737), add:

```python
# Track tokens across all orchestration turns
total_input_tokens = 0
total_output_tokens = 0
full_response = ""
```

### 7b. Handle `metadata` stream events

In the streaming loop, after the `messageStop` handling (around line ~816), add:

```python
# Metadata - extract token counts
if 'metadata' in stream_event:
    usage = stream_event['metadata'].get('usage', {})
    total_input_tokens += usage.get('inputTokens', 0)
    total_output_tokens += usage.get('outputTokens', 0)
    logger.info(f"Turn {turn_count} tokens: input={usage.get('inputTokens', 0)}, output={usage.get('outputTokens', 0)}")
```

### 7c. Accumulate full response text

In the text delta handling (around line ~785), add accumulation:

```python
if 'text' in delta:
    chunk_text = delta['text']
    current_text_block += chunk_text
    full_response += chunk_text  # NEW: accumulate for persistence
    yield followup_chunk_event(message_id, chunk_text)
```

### 7d. Record usage after orchestration loop

After the orchestration loop exits and before the final `followup_end_event`, add:

```python
# Record token usage (accumulated across all turns)
usage_result = {}
if user_id:
    if total_input_tokens == 0 and total_output_tokens == 0:
        # Fallback estimation if no metadata received
        total_input_tokens = max(1, int(len(question) / 3.5))
        total_output_tokens = max(1, int(len(full_response) / 3.5))
        logger.warning("No token metadata received, using estimation")

    usage_result = token_tracker.record_usage(user_id, total_input_tokens, total_output_tokens)
    logger.info(f"Token usage recorded for {user_id}: input={total_input_tokens}, output={total_output_tokens}, "
                f"total={usage_result.get('total_tokens')}, percent={usage_result.get('percent_used')}%")
```

Reference: zip Lambda at `analysis_followup.py:496-499, 676-688`

---

## Step 8: Add Message Persistence

**File**: `followup_service.py`

### 8a. Add module-level initialization

Near the existing DynamoDB initialization (around line 37-39):

```python
# Message persistence
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE) if CHAT_MESSAGES_TABLE else None
```

### 8b. Add `save_followup_message` function

Add this function (ported from `analysis_followup.py:265-322`):

```python
def save_followup_message(
    session_id: str,
    message_type: str,
    content: str,
    user_id: str,
    ticker: str = ''
) -> Optional[str]:
    """Save a follow-up message to DynamoDB for conversation history."""
    if not messages_table:
        logger.warning("Messages table not configured, skipping persistence")
        return None

    try:
        from datetime import timezone
        timestamp_unix = int(datetime.now(timezone.utc).timestamp() * 1000)
        timestamp_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        message_id = str(uuid.uuid4())

        message_record = {
            'conversation_id': session_id,
            'timestamp': timestamp_unix,
            'message_id': message_id,
            'message_type': message_type,
            'content': content,
            'user_id': user_id,
            'created_at': timestamp_iso,
            'status': 'completed' if message_type == 'assistant' else 'received',
            'environment': ENVIRONMENT,
            'project': PROJECT_NAME,
            'metadata': {
                'source': 'investment_research_followup',
                'agent_type': 'followup',
                'ticker': ticker
            }
        }

        messages_table.put_item(Item=message_record)
        logger.info(f"Saved {message_type} message {message_id} for session {session_id}")
        return message_id

    except Exception as e:
        logger.error(f"Failed to save {message_type} message: {e}", exc_info=True)
        return None
```

Note: `uuid` is already imported in `_stream_claude_response` (line ~693). Move `import uuid` to the module-level imports at the top of the file.

### 8c. Save messages in `_stream_claude_response`

After token recording (Step 7d) and before the final `followup_end_event`:

```python
# Save messages to DynamoDB for conversation history
user_message_id = None
assistant_message_id = None
if user_id and session_id:
    user_message_id = save_followup_message(
        session_id=session_id,
        message_type='user',
        content=question,
        user_id=user_id,
        ticker=ticker
    )
    assistant_message_id = save_followup_message(
        session_id=session_id,
        message_type='assistant',
        content=full_response,
        user_id=user_id,
        ticker=ticker
    )
```

---

## Step 9: Enrich `followup_end` Event

**File**: `services/streaming.py`

Update `followup_end_event` signature (around line ~529) to accept optional token usage data:

```python
def followup_end_event(
    message_id: str,
    token_usage: dict = None,
    user_message_id: str = None,
    assistant_message_id: str = None
) -> dict:
    """Signal end of follow-up response streaming."""
    data = {
        "type": "followup_end",
        "message_id": message_id,
        "timestamp": _timestamp()
    }
    if token_usage:
        data["token_usage"] = token_usage
    if user_message_id:
        data["user_message_id"] = user_message_id
    if assistant_message_id:
        data["assistant_message_id"] = assistant_message_id
    return {
        "event": "followup_end",
        "data": _json_dumps(data)
    }
```

Then update the final yield in `_stream_claude_response`:

```python
# Build token usage payload for followup_end event
token_usage_payload = None
if user_id and usage_result:
    token_usage_payload = {
        'input_tokens': total_input_tokens,
        'output_tokens': total_output_tokens,
        'total_tokens': usage_result.get('total_tokens'),
        'token_limit': usage_result.get('token_limit'),
        'percent_used': usage_result.get('percent_used'),
        'remaining_tokens': usage_result.get('remaining_tokens'),
        'threshold_reached': usage_result.get('threshold_reached'),
    }

yield followup_end_event(
    message_id,
    token_usage=token_usage_payload,
    user_message_id=user_message_id,
    assistant_message_id=assistant_message_id
)
```

---

## Step 10: Build, Test, Deploy

No Terraform changes needed. No Dockerfile changes needed.

### Build Docker image
```bash
cd chat-api/backend/lambda/investment_research
docker build --platform linux/amd64 --no-cache -t buffett/investment-research:v2.0.0-token-tracking .
```

### Push to ECR
```bash
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com"

aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${ECR_REGISTRY}

docker tag buffett/investment-research:v2.0.0-token-tracking ${ECR_REGISTRY}/buffett/investment-research:v2.0.0-token-tracking
docker push ${ECR_REGISTRY}/buffett/investment-research:v2.0.0-token-tracking
```

### Update Lambda
```bash
aws lambda update-function-code \
  --function-name buffett-dev-investment-research \
  --image-uri ${ECR_REGISTRY}/buffett/investment-research:v2.0.0-token-tracking \
  --region us-east-1
```

---

## Verification Checklist

### 1. Unit tests pass
```bash
cd chat-api/backend && make test
```
Expected: 232/232 pass (Docker Lambda tests are separate from main suite)

### 2. Streaming still works (curl test)
```bash
# Generate JWT
JWT_SECRET=$(aws secretsmanager get-secret-value --secret-id buffett-dev-jwt-secret --query SecretString --output text)
TOKEN=$(python3 -c "import jwt, time; print(jwt.encode({'user_id': 'test-token-tracking', 'email': 'test@example.com', 'iat': int(time.time()), 'exp': int(time.time()) + 3600}, '${JWT_SECRET}', algorithm='HS256'))")

# Invoke followup
curl -s -N -X POST "https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/followup" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"ticker": "AMZN", "question": "What is the overall rating?", "conversation_id": "test-session-001"}'
```

Expected:
- `followup_start`, multiple `followup_chunk` events, then `followup_end`
- `followup_end` event includes `token_usage` field with `input_tokens`, `output_tokens`, etc.

### 3. Token usage table updated
```bash
aws dynamodb query \
  --table-name token-usage-dev-buffett \
  --key-condition-expression "user_id = :uid" \
  --expression-attribute-values '{":uid": {"S": "test-token-tracking"}}' \
  --region us-east-1
```

Expected: `total_tokens > 0`, `request_count >= 1`, `last_request_at` updated

### 4. Messages persisted
```bash
aws dynamodb query \
  --table-name buffett-dev-chat-messages \
  --key-condition-expression "conversation_id = :cid" \
  --expression-attribute-values '{":cid": {"S": "test-session-001"}}' \
  --region us-east-1
```

Expected: 2 items (1 user message, 1 assistant message) with correct `ticker`, `user_id`, `content`

### 5. Token limit enforcement
```bash
# Set token limit to 1 to trigger limit
aws dynamodb update-item \
  --table-name token-usage-dev-buffett \
  --key '{"user_id": {"S": "test-token-tracking"}, "billing_period": {"S": "2026-02-05"}}' \
  --update-expression "SET token_limit = :limit" \
  --expression-attribute-values '{":limit": {"N": "1"}}' \
  --region us-east-1

# Invoke again - should get token_limit_exceeded error event
curl -s -N -X POST "https://gls4xkzsobkxlzeatdfhz4ng740ynrfb.lambda-url.us-east-1.on.aws/followup" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"ticker": "AMZN", "question": "Test limit", "conversation_id": "test-session-002"}'
```

Expected: `error` event with `type: token_limit_exceeded`

---

## Automated Test Suite

All features above are covered by a comprehensive test suite that runs against the deployed AWS dev environment. Tests live in `chat-api/backend/tests/`.

### Test Architecture

| Level | Directory | What's Mocked | What's Real |
|-------|-----------|---------------|-------------|
| **Unit** | `tests/unit/` | All AWS services (boto3, DynamoDB, Bedrock) | Business logic only |
| **Integration** | `tests/integration/` | Bedrock only (`boto3.client`) | DynamoDB (dev tables) |
| **E2E** | `tests/e2e/` | Nothing | Docker Lambda, Bedrock, DynamoDB, JWT auth |

### Shared Test Infrastructure

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Global pytest config, custom markers (`e2e`, `integration`, `slow`), autouse env var fixture |
| `tests/e2e/conftest.py` | E2E fixtures: SSE parsing, JWT generation, Docker Lambda URL, data seeding/cleanup |
| `tests/fixtures/data_seeding.py` | DynamoDB seed/cleanup utilities shared across integration and e2e tests |
| `tests/__init__.py` | Required for `from tests.fixtures.xxx import` to work |

### E2E Tests — Docker Lambda (`tests/e2e/test_docker_lambda_e2e.py`)

These tests hit the **real deployed Docker Lambda** at its Function URL, with **real Bedrock** and **real DynamoDB**. They validate the full request lifecycle end-to-end.

**Run command:**
```bash
cd chat-api/backend
AWS_PROFILE=default BUFFETT_JWT_SECRET='...' \
    pytest tests/e2e/test_docker_lambda_e2e.py -v -s -m e2e
```

**Requires:**
- AWS credentials with DynamoDB access
- `BUFFETT_JWT_SECRET` environment variable (fetch from Secrets Manager: `buffett-dev-jwt-secret`)
- Network access to the Docker Lambda Function URL

**Cost:** ~$0.01-0.05 per test run (Bedrock API costs)

#### Test Classes and Acceptance Criteria

| Class | Test | AC | What It Verifies |
|-------|------|----|-----------------|
| `TestSSEStreaming` | `test_sse_event_sequence` | AC-1 | Events arrive in order: `connected` → `followup_start` → `followup_chunk(s)` → `followup_end` |
| | `test_followup_start_has_message_id` | AC-1 | `followup_start` contains `message_id` and `ticker` |
| | `test_followup_chunks_contain_text` | AC-1 | Chunks contain non-empty text (>20 chars total) |
| | `test_health_check` | — | GET `/health` returns 200 with `status=healthy` |
| `TestTokenTracking` | `test_followup_end_includes_token_usage` | AC-2 | `followup_end` has `token_usage` with `input_tokens > 0`, `output_tokens > 0`, `total_tokens`, `percent_used` |
| | `test_token_usage_recorded_in_dynamodb` | AC-3 | After request, `token-usage-dev-buffett` has `total_tokens > 0` and `request_count >= 1` |
| `TestTokenLimitEnforcement` | `test_token_limit_exceeded_returns_error_event` | AC-4 | User with `total_tokens > token_limit` gets error SSE event with `type=token_limit_exceeded`, no Bedrock call made |
| `TestMessagePersistence` | `test_messages_saved_to_dynamodb` | AC-5 | `buffett-dev-chat-messages` has 2 messages (user + assistant) with correct `user_id`, `ticker`, `metadata.source` |
| | `test_followup_end_includes_message_ids` | AC-6 | `followup_end` contains `user_message_id` and `assistant_message_id` matching DynamoDB records |
| `TestAuthValidation` | `test_invalid_jwt_rejected` | AC-7 | Invalid JWT returns 401 or 403 |
| | `test_missing_auth_rejected` | AC-8 | Missing `Authorization` header returns 401 or 403 |

**Total: 11 tests, all passing against AWS dev environment.**

#### Key Test Fixtures

**`docker_test_data`** (module scope) — Seeds a unique test user and ticker into DynamoDB, cleans up after all tests:
```python
@pytest.fixture(scope='module')
def docker_test_data():
    ticker = f'D{_random_alpha(4)}'  # 5-char alpha-only (no digits)
    user_id = f'docker-e2e-{uuid.uuid4().hex[:8]}'
    seed_test_report(ticker)
    seed_test_metrics(ticker, quarters=8)
    seed_token_usage(user_id, total_tokens=0, limit=100000)
    yield {'ticker': ticker, 'user_id': user_id, 'session_id': ...}
    cleanup_test_data(ticker, user_id)  # deletes all seeded data
```

**`reset_tokens`** (autouse in TestTokenTracking and TestMessagePersistence) — Resets the user to 0 tokens before each test so assertions are deterministic:
```python
@pytest.fixture(autouse=True)
def reset_tokens(self, docker_test_data):
    seed_token_usage(docker_test_data['user_id'], total_tokens=0, limit=100000)
```

**`message_cleanup`** — Collects session IDs during tests and deletes messages from `buffett-dev-chat-messages` after:
```python
@pytest.fixture
def message_cleanup():
    session_ids = []
    yield session_ids
    cleanup_messages(session_ids)
```

#### SSE Parsing

Tests use a custom SSE parser (no external dependency) in `tests/e2e/conftest.py`:
- `parse_sse_stream(response)` — parses `text/event-stream` into `[(event_type, data_dict), ...]`
- `post_followup_sse(base_url, token, payload)` — POST + parse helper returning `(status_code, events)`

#### Important: Ticker Validation

Test tickers must be **1-5 uppercase alpha characters only** (no digits) to pass `validate_ticker()` in `report_service.py`. The fixture uses `_random_alpha(4)` with prefix `D` to generate valid 5-char tickers like `DXMWQ`.

### Integration Tests (`tests/integration/test_followup_agent_integration.py`)

These tests use **real DynamoDB** but **mock Bedrock**, allowing fast verification of tool execution, message persistence, token tracking math, and JWT auth without incurring Bedrock costs.

**Run command:**
```bash
cd chat-api/backend
AWS_PROFILE=default pytest tests/integration/test_followup_agent_integration.py -v -m integration
```

| Class | Tests | What It Verifies |
|-------|-------|-----------------|
| `TestToolExecutionIntegration` | 4 tests | `getReportSection`, `getReportRatings`, `getMetricsHistory`, `getAvailableReports` against real DynamoDB |
| `TestMessagePersistenceIntegration` | 2 tests | Messages saved with correct metadata (`source`, `agent_type`, `ticker`) |
| `TestTokenTrackingIntegration` | 2 tests | Token usage in response matches mock values, multi-turn token accumulation math |
| `TestAuthenticationIntegration` | 3 tests | Valid JWT passes, invalid/missing JWT returns 401 |

**Key pattern:** The `handler_with_mock_bedrock` fixture patches `boto3.client` (Bedrock, Secrets Manager) but NOT `boto3.resource` (DynamoDB), so tools read/write to real dev tables.

### Token Accumulation Verification (CloudWatch Evidence)

E2E tests confirmed that DynamoDB's atomic `ADD` operation correctly accumulates tokens across multiple requests for the same `user_id`. From CloudWatch logs:

**Request lifecycle per invocation:**
1. JWT verified → `user_id` extracted
2. `check_limit` → `get_item` reads current `total_tokens` from `token-usage-dev-buffett`
3. If allowed → Bedrock `converse_stream` executes
4. `record_usage` → `update_item` with `ADD total_tokens :total` (atomic increment)
5. DynamoDB returns `ALL_NEW` attributes showing accumulated total

**Example — 3 sequential requests, same user, no reset:**

| Request | ADD Amount | DynamoDB `total_tokens` After | Math Check |
|---------|-----------|------------------------------|------------|
| 1 | +3,722 | 3,722 | 0 + 3,722 = 3,722 |
| 2 | +3,941 | 7,663 | 3,722 + 3,941 = 7,663 |
| 3 | +6,293 | 13,956 | 7,663 + 6,293 = 13,956 |

**Token limit enforcement — same user, seeded over limit:**

| State | Action | Result |
|-------|--------|--------|
| `total_tokens=200,000`, `token_limit=100,000` | `check_limit` | `allowed: False` |
| | No Bedrock call | No `followup_chunk` events |
| | No `record_usage` | No `update_item` in CloudWatch |
| | SSE error event | `type: token_limit_exceeded` |

### Data Seeding Utilities (`tests/fixtures/data_seeding.py`)

| Function | Target Table | What It Does |
|----------|-------------|-------------|
| `seed_test_report(ticker)` | `investment-reports-v2-dev` | Seeds 3 sections: `00_executive`, `06_growth`, `11_debt` |
| `seed_test_metrics(ticker, quarters)` | `metrics-history-dev` | Seeds quarterly revenue, net income, FCF, debt, equity |
| `seed_token_usage(user_id, total_tokens, limit)` | `token-usage-dev-buffett` | Seeds token usage with anniversary-based `billing_period` (YYYY-MM-DD) |
| `cleanup_test_data(ticker, user_id)` | All above | Queries and deletes all records for given ticker/user |
| `cleanup_messages(session_ids)` | `buffett-dev-chat-messages` | Queries and deletes messages by `conversation_id` |

### Running All Test Levels

```bash
cd chat-api/backend

# Unit tests only (no AWS credentials needed)
pytest tests/unit/ -v

# Integration tests (requires AWS credentials, DynamoDB access)
AWS_PROFILE=default pytest tests/integration/ -v -m integration

# E2E tests (requires AWS credentials, JWT secret, network to Lambda URL)
AWS_PROFILE=default BUFFETT_JWT_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-jwt-secret --query SecretString --output text) \
    pytest tests/e2e/test_docker_lambda_e2e.py -v -s -m e2e

# All tests except e2e (fast, good for CI)
pytest -m "not e2e and not integration" -v
```
