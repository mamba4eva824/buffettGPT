# Conversation Loading Performance Optimization

## Executive Summary

Two-phase performance audit and optimization of the research conversation loading flow, targeting the critical path from conversation open to full report render.

**Overall Results:**
- Phase 1 (Lambda execution): **55.8% faster** warm Lambda execution (372.4ms → 164.6ms)
- Phase 2 (E2E wall time): **52% faster** end-to-end loading (2.709s → 1.307s)
- Section fetch specifically: **4.1x faster** (1.980s → 0.484s)
- HTTP calls reduced: **6 → 3** per conversation load

---

## Phase 1: Lambda-Side Fixes

### Bug 1: Unbounded Conversation List Scan (Priority: Critical)
**Problem:** `GET /conversations` scanned the entire DynamoDB table with no pagination, returning all conversations for a user regardless of how many existed.

**Fix:** Added `Limit` parameter and `LastEvaluatedKey`-based pagination to `conversations_handler.py`. Default page size: 20.

**Impact:** Reduced payload size and DynamoDB read capacity consumption proportional to conversation count.

### Bug 2: Missing ConditionExpression on Conversation Update (Priority: High)
**Problem:** `update_item` on the conversations table used unconditional writes, risking overwrites and consuming unnecessary write capacity on no-op updates.

**Fix:** Added `ConditionExpression` to ensure the conversation exists before updating, preventing phantom writes.

### Bug 3: Missing ProjectionExpression on Conversation Update Response (Priority: High)
**Problem:** The `update_item` call returned all attributes via `ReturnValues='ALL_NEW'` even though only a subset was needed by the caller.

**Fix:** Added `ProjectionExpression` to limit returned attributes to only those used by the frontend.

### Phase 1 Results
- Warm Lambda execution: **372.4ms → 164.6ms (55.8% improvement)**
- Measured via CloudWatch Lambda duration metrics

---

## Phase 2: End-to-End Flow Optimization

### Fix 1: Batch Sections Endpoint
**Problem:** Loading a research report required N individual `GET /report/{ticker}/section/{section_id}` calls (one per visible section, typically 5-8 calls). Each call was a separate HTTP round-trip through API Gateway → Lambda → DynamoDB.

**Fix:** Created `POST /report/{ticker}/sections` endpoint that accepts a JSON body with `section_ids` array and uses DynamoDB `batch_get_item` to fetch all sections in a single call.

**Files changed:**
- `lambda/investment_research/app.py` - Added POST endpoint handler
- `lambda/investment_research/services/report_service.py` - Added `get_report_sections_batch()` using `batch_get_item`
- `terraform/modules/api-gateway/analysis_streaming.tf` - Added API Gateway route (resource, method, integration, CORS)

**Impact:** Section fetch: **1.980s → 0.484s (4.1x faster)**

### Fix 2: ProjectionExpression on GET Conversation
**Problem:** `GET /conversations/{id}` returned the full conversation object including all metadata fields, even though the frontend only needed a subset for initial render.

**Fix:** Added `ProjectionExpression` to the DynamoDB `get_item` call, returning only 8 fields: `conversation_id`, `user_id`, `title`, `created_at`, `updated_at`, `#metadata`, `research_state`, `last_message_preview`.

**Files changed:**
- `backend/src/handlers/conversations_handler.py` - Added ProjectionExpression with `ExpressionAttributeNames` for reserved word `metadata`

### Fix 3: Eliminated Redundant checkReportStatus Call
**Problem:** The frontend flow was: (1) fetch conversation, (2) call `checkReportStatus` to see if a report exists, (3) fetch individual sections. Step 2 was redundant because the batch endpoint returns `report_exists` in its response.

**Fix:** Replaced the three-step flow with: (1) fetch conversation with projection, (2) batch-fetch all visible sections (which also confirms report existence).

**Files changed:**
- `frontend/src/contexts/ResearchContext.jsx` - Added `fetchSectionsBatch` callback
- `frontend/src/App.jsx` - Replaced `checkReportStatus` + N `fetchSection` calls with single `fetchSectionsBatch`

### Phase 2 Results
| Metric | Old Flow | New Flow | Improvement |
|--------|----------|----------|-------------|
| Total wall time | 2.709s | 1.307s | **52% faster** |
| HTTP calls | 6 | 3 | **50% fewer** |
| Section fetch | 1.980s | 0.484s | **4.1x faster** |
| Conversation fetch | 0.431s | 0.382s | 11% faster |

---

## Integration Test Results

### Batch Sections Endpoint
| Test | Result |
|------|--------|
| Batch fetch 5 sections (NVDA) | 200 OK, all sections returned |
| Sequential vs batch comparison | 2.062s vs 0.460s = 4.5x faster |
| Empty section_ids array | 400 Bad Request |
| Nonexistent ticker | 200, `report_exists: false`, 0 sections |
| No auth token | 401 Unauthorized |

### GET Conversation with ProjectionExpression
| Test | Result |
|------|--------|
| Projected fields returned | Exactly 8 fields |
| research_state preserved | Full object intact |
| Response size | 3,938 chars (reduced from full object) |
| Messages pagination (limit=5) | Correct subset returned |

---

## Bugs Found During Deployment

### DynamoDB batch_get_item Parameter Name
- **Bug:** Used `RequestKeys` instead of `RequestItems` in `batch_get_item` call
- **Symptom:** Batch endpoint returned `report_exists: false` with 0 sections
- **Lambda error:** `In function keys(), invalid type for value: None`
- **Fix:** Changed `RequestKeys` → `RequestItems` in `report_service.py`

### Missing API Gateway Route
- **Bug:** New POST endpoint had no API Gateway route configured
- **Symptom:** 403 Forbidden on `POST /research/report/{ticker}/sections`
- **Fix:** Added 8 Terraform resources to `analysis_streaming.tf`

---

## Architecture Decisions

1. **batch_get_item over Query:** Used `batch_get_item` with explicit keys rather than a Query with `begins_with` because the frontend knows exactly which sections it needs. This avoids fetching sections the user hasn't scrolled to yet.

2. **POST method for batch fetch:** Used POST instead of GET because the request includes a JSON body with the list of section IDs. GET with query parameters would hit URL length limits for many sections.

3. **ProjectionExpression with reserved words:** DynamoDB's `metadata` is a reserved word requiring `ExpressionAttributeNames={'#metadata': 'metadata'}` aliasing.

4. **Docker Lambda deployment flow:** The Terraform config uses `lifecycle { ignore_changes = [image_uri] }`, so Docker Lambda updates require: build → push to ECR → `aws lambda update-function-code --image-uri ...` → wait for function-updated.

---

## Deployed Versions
- **Investment research Lambda:** Docker image `v1.3.1` (ECR)
- **Conversations handler Lambda:** Zip package via Terraform
- **Environment:** dev
- **Date:** 2025-06-14
