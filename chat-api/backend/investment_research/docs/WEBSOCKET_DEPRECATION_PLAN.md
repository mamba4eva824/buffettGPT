# WebSocket Infrastructure Deprecation Plan

> **Status**: ✅ Completed
> **Created**: 2026-02-04
> **Completed**: 2026-02-04
> **Decision**: Research + Follow-up flow (REST+SSE) is sufficient for the product. WebSocket chat infrastructure has been deprecated.

## GSD AUDIT SNAPSHOT

### Knowns / Evidence
1. **WebSocket chat is non-functional**: Environment variables `BEDROCK_AGENT_ID` and `BEDROCK_AGENT_ALIAS` are empty strings - the WebSocket chat processor cannot invoke any Bedrock agent
2. **Two separate agent systems exist**: Follow-up Agent (working) and WebSocket Chat Agent (broken/undefined)
3. **Research + Follow-up flow is sufficient**: User confirmed REST+SSE architecture meets product needs
4. **WebSocket infrastructure is extensive but isolated**: 3 Lambda handlers, API Gateway WebSocket routes, SQS queue, 2 DynamoDB tables

### Unknowns / Gaps
1. ~~Are there any active WebSocket connections in production?~~ → Not relevant since user wants deprecation
2. ~~Should `chat_http_handler.py` also be removed?~~ → **Yes, confirmed for removal**

### Constraints
- Follow-up Agent and REST+SSE architecture must remain untouched
- DynamoDB tables `chat-messages` and `conversations` are shared - must be preserved
- Terraform state must be managed carefully to avoid orphaned resources

### Risks
1. **Incomplete cleanup**: Orphaned resources if removal is partial
2. **Shared dependencies**: SQS queue and some DynamoDB tables are referenced by multiple handlers
3. **Frontend regression**: If WebSocket code removal is incomplete, could break unrelated features

---

## PRD - ACCEPTANCE CRITERIA

**AC-1**: Given the dev environment, when Terraform apply completes, then NO WebSocket API Gateway exists (no wss:// endpoint)

**AC-2**: Given the backend/build/ directory, when build_lambdas.sh runs, then NO websocket_*.zip or chat_processor.zip files are created

**AC-3**: Given the frontend application, when a user loads the page, then NO WebSocket connection is attempted (no wss:// network requests)

**AC-4**: Given a user navigates to the Research page, when they generate a report and use follow-up chat, then it works via REST+SSE (unchanged)

**AC-5**: Given the codebase, when searching for WebSocket references, then only historical/archived references remain (no active code paths)

---

## IMPLEMENTATION PLAN

### Objective
Remove all WebSocket chat infrastructure while preserving the Follow-up Agent and REST+SSE research flow.

### Approach Summary
Phased removal starting from frontend (safest) → backend handlers → Terraform infrastructure → cleanup. Each phase is independently deployable and testable.

---

## PHASE 1: Frontend WebSocket Removal

### Step 1.1: Remove useAwsWebSocket hook from App.jsx
**File**: `frontend/src/App.jsx`
- Delete lines 314-622 (useAwsWebSocket hook definition)
- Delete WebSocket-related state and effects that call this hook
- Remove WebSocket URL from environment variable usage

### Step 1.2: Remove WebSocket chat UI components
**File**: `frontend/src/App.jsx`
- Remove any UI that displays WebSocket connection status
- Remove chat input that uses WebSocket sendMessage
- Keep conversation list (uses HTTP API)

### Step 1.3: Remove WebSocket environment variable
**File**: `frontend/.env.development` and related
- Remove `VITE_WEBSOCKET_URL` if present

**Verification**:
```bash
cd frontend && npm run build && npm run lint
# Verify no wss:// references in built output
grep -r "wss://" dist/ || echo "No WebSocket URLs found"
```

---

## PHASE 2: Backend Lambda Handler Removal

### Step 2.1: Remove WebSocket handlers from build script
**File**: `chat-api/backend/scripts/build_lambdas.sh`
- Remove from FUNCTIONS array:
  - `websocket_connect`
  - `websocket_disconnect`
  - `websocket_message`
  - `chat_processor`

### Step 2.2: Delete WebSocket handler files
**Files to delete**:
- `chat-api/backend/src/handlers/websocket_connect.py`
- `chat-api/backend/src/handlers/websocket_message.py`
- `chat-api/backend/src/handlers/websocket_disconnect.py`
- `chat-api/backend/src/handlers/chat_processor.py`

### Step 2.3: Delete HTTP chat handler
**File**: `chat-api/backend/src/handlers/chat_http_handler.py`
- This handler uses the same undefined BEDROCK_AGENT_ID as WebSocket chat
- User confirmed removal - all chat functionality is via Research + Follow-up flow

**Verification**:
```bash
cd chat-api/backend && ./scripts/build_lambdas.sh
ls -la build/ | grep -E "(websocket|chat_processor)" || echo "No WebSocket zips"
```

---

## PHASE 3: Terraform Infrastructure Removal

### Step 3.1: Remove WebSocket API Gateway
**File**: `chat-api/terraform/modules/api-gateway/main.tf`
- Remove `aws_apigatewayv2_api.websocket_api` (lines ~110-124)
- Remove `aws_apigatewayv2_stage.websocket_stage` (lines ~127-147)
- Remove `aws_cloudwatch_log_group.websocket_api_logs` (lines ~167-179)
- Remove `aws_apigatewayv2_authorizer.websocket_jwt_authorizer` (lines ~197-206)
- Remove all WebSocket routes (`$connect`, `$disconnect`, `$default`, `ping`)
- Remove all WebSocket integrations
- Remove all WebSocket Lambda permissions

### Step 3.2: Remove WebSocket outputs
**File**: `chat-api/terraform/modules/api-gateway/outputs.tf`
- Remove `websocket_api_id`
- Remove `websocket_api_endpoint`
- Remove `websocket_api_execution_arn`

### Step 3.3: Remove Lambda function configurations
**File**: `chat-api/terraform/modules/lambda/main.tf`
- Remove from `lambda_configs` map:
  - `websocket_connect`
  - `websocket_disconnect`
  - `websocket_message`
  - `chat_processor`

### Step 3.4: Remove SQS queue (chat-processing)
**File**: `chat-api/terraform/modules/core/main.tf`
- Remove `aws_sqs_queue.chat_processing_queue` (lines ~190-212)
- Remove `aws_sqs_queue.chat_dlq` (lines ~214-227)
- Remove SQS event source mapping from Lambda

### Step 3.5: Remove DynamoDB tables (deprecated)
**File**: `chat-api/terraform/modules/dynamodb/main.tf`
- Remove `websocket-connections` table definition (if still exists)
- Remove `chat-sessions` table definition (if still exists)
- NOTE: Keep `chat-messages` and `conversations` tables (used by conversation management)

### Step 3.6: Remove environment variables from main.tf
**File**: `chat-api/terraform/environments/dev/main.tf`
- Remove `WEBSOCKET_API_ENDPOINT` from common environment variables
- Remove `CHAT_SESSIONS_TABLE` reference
- Remove `BEDROCK_AGENT_ID` and `BEDROCK_AGENT_ALIAS` (unused)
- Remove `CHAT_PROCESSING_QUEUE_URL` reference

**Verification**:
```bash
cd chat-api/terraform/environments/dev
terraform validate
terraform plan -out=tfplan
# Review plan to confirm only WebSocket resources being destroyed
```

---

## PHASE 4: Bedrock Agent Cleanup

### Step 4.1: Remove orphaned Bedrock prompt
**File**: `chat-api/terraform/modules/bedrock/prompts/buffett_advisor_instruction.txt`
- This prompt was for the undefined WebSocket chat agent
- Safe to delete (Follow-up Agent uses `followup_agent_v1.txt`)

### Step 4.2: Remove Bedrock agent environment variables
Already covered in Step 3.6 - remove `BEDROCK_AGENT_ID` and `BEDROCK_AGENT_ALIAS`

**Note**: The Follow-up Agent (`FOLLOWUP_AGENT_ID`, `FOLLOWUP_AGENT_ALIAS`) must be PRESERVED

---

## PHASE 5: Final Cleanup

### Step 5.1: Update CLAUDE.md documentation
**File**: `CLAUDE.md`
- Remove WebSocket references from architecture documentation
- Update Lambda functions list
- Remove WebSocket environment variables from documentation

### Step 5.2: Archive or delete related test files
- Check `chat-api/backend/tests/` for WebSocket-related tests
- Remove or archive tests for deleted handlers

### Step 5.3: Remove any WebSocket sample events
**Directory**: `chat-api/events/`
- Remove sample WebSocket event JSON files if present

---

## FILES TO MODIFY/DELETE

### Files to DELETE:
| File | Reason |
|------|--------|
| `chat-api/backend/src/handlers/websocket_connect.py` | WebSocket handler |
| `chat-api/backend/src/handlers/websocket_message.py` | WebSocket handler |
| `chat-api/backend/src/handlers/websocket_disconnect.py` | WebSocket handler |
| `chat-api/backend/src/handlers/chat_processor.py` | SQS consumer for WebSocket |
| `chat-api/backend/src/handlers/chat_http_handler.py` | HTTP chat handler - uses broken agent |
| `chat-api/terraform/modules/bedrock/prompts/buffett_advisor_instruction.txt` | Orphaned prompt |

### Files to MODIFY:
| File | Changes |
|------|---------|
| `frontend/src/App.jsx` | Remove useAwsWebSocket hook (~300 lines) |
| `chat-api/backend/scripts/build_lambdas.sh` | Remove 4 functions from FUNCTIONS array |
| `chat-api/terraform/modules/api-gateway/main.tf` | Remove WebSocket API, routes, integrations |
| `chat-api/terraform/modules/api-gateway/outputs.tf` | Remove WebSocket outputs |
| `chat-api/terraform/modules/lambda/main.tf` | Remove lambda_configs for 4 handlers |
| `chat-api/terraform/modules/core/main.tf` | Remove SQS queue |
| `chat-api/terraform/modules/dynamodb/main.tf` | Remove deprecated tables |
| `chat-api/terraform/environments/dev/main.tf` | Remove env vars |
| `CLAUDE.md` | Update documentation |

### Files to KEEP (Must NOT modify):
| File | Reason |
|------|--------|
| `chat-api/backend/src/handlers/analysis_followup.py` | Follow-up Agent handler |
| `chat-api/terraform/modules/bedrock/prompts/followup_agent_v1.txt` | Follow-up Agent prompt |
| `chat-api/backend/src/handlers/conversations_handler.py` | HTTP conversation management |
| All investment_research/ files | Research system |

---

## VERIFICATION CHECKLIST

### Pre-deployment:
- [ ] `terraform validate` passes
- [ ] `terraform plan` shows only WebSocket resources being destroyed
- [ ] `npm run build` succeeds for frontend
- [ ] `npm run lint` passes for frontend
- [ ] No `wss://` references in frontend build output

### Post-deployment:
- [ ] Research report generation works via REST+SSE
- [ ] Follow-up chat works via REST+SSE
- [ ] Conversation list loads via HTTP API
- [ ] No 404/500 errors in CloudWatch from missing handlers
- [ ] WebSocket endpoint returns 404 (or doesn't exist)

### Regression test:
```bash
# Test research flow still works
curl -X POST https://your-api.execute-api.us-east-1.amazonaws.com/dev/research/generate \
  -H "Authorization: Bearer YOUR_JWT" \
  -d '{"ticker": "AAPL"}'

# Test follow-up still works
curl -X POST https://your-api.execute-api.us-east-1.amazonaws.com/dev/analysis/followup \
  -H "Authorization: Bearer YOUR_JWT" \
  -d '{"report_id": "...", "question": "What about the dividend?"}'
```

---

## ROLLBACK PLAN

If issues arise after deployment:
1. Revert Terraform changes: `terraform apply` with previous state
2. Redeploy Lambda packages with handlers included
3. Frontend: Deploy previous build from S3 backup

Git commits should be atomic per phase for easy rollback.
