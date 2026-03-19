# Ralph Loop: DynamoDB Integration Testing for Investment Research

## Context Summary

Testing the Investment Research system's DynamoDB read/write operations, focusing on:
1. **Report reading**: `/report/{ticker}/section/{section_id}` GET request from `investment_reports_v2` table
2. **Conversation persistence**: PUT `/conversations/{id}` saves `research_state` to `conversations` table
3. **Message persistence**: POST `/conversations/{id}/messages` saves follow-up Q&A to `chat_messages` table
4. **Multi-user concurrency**: Shared reports (by ticker) + user-specific conversation state

## Architecture Reference

See: `chat-api/backend/investment_research/docs/RESEARCH_SYSTEM_ARCHITECTURE.md`

### Table Relationships

```
conversations table                    investment-reports-v2 table
┌─────────────────────────┐           ┌─────────────────────────────┐
│ conversation_id (PK)    │           │ ticker (PK) + section_id (SK)│
│ metadata.research_state │───ref────▶│                             │
│   .ticker: "AAPL"       │           │ "AAPL" / "00_executive"     │
│   .toc[].section_id     │           │ "AAPL" / "06_growth"        │
│   .active_section_id    │           │ ...                         │
│   .visible_sections     │           └─────────────────────────────┘
└─────────────────────────┘           (SHARED - one copy per ticker)
        (USER-SPECIFIC)

chat-messages table
┌─────────────────────────┐
│ conversation_id (PK)    │◀──── Links to conversations
│ timestamp (SK)          │
│ content._type           │ followup_question | followup_response
└─────────────────────────┘
```

## Tasks

### Phase 1: Unit Test - Section Endpoint Read Operations

Create unit tests in `chat-api/backend/lambda/investment_research/tests/test_section_endpoints.py`:

1. **Test GET /report/{ticker}/section/{section_id}**
   - Mock DynamoDB GetItem response
   - Verify correct key construction: `(ticker.upper(), section_id.lower())`
   - Verify TTL expiration check
   - Verify response format: `{section_id, title, content, part, icon, word_count}`

2. **Test GET /report/{ticker}/toc**
   - Mock DynamoDB GetItem for executive item (`00_executive`)
   - Verify ToC extraction from executive item
   - Verify ratings extraction

3. **Test GET /report/{ticker}/status**
   - Mock report exists (with TTL)
   - Mock report expired (TTL passed)
   - Mock report not found

### Phase 2: Unit Test - Conversation Metadata Persistence

Create unit tests in `chat-api/backend/src/handlers/tests/test_conversations_research_state.py`:

1. **Test PUT /conversations/{id} with research_state**
   - Mock existing conversation without metadata
   - Verify metadata is created with research_state
   - Verify float-to-Decimal conversion for DynamoDB

2. **Test partial metadata update**
   - Mock existing conversation WITH metadata
   - Verify research_state is updated without clobbering other metadata keys
   - Verify nested attribute update expression syntax

3. **Test research_state schema validation**
   - Verify required fields: `ticker`, `active_section_id`, `visible_sections`
   - Verify ToC structure saved correctly
   - Verify ratings saved correctly

### Phase 3: Integration Test - End-to-End Flow

Create integration tests in `chat-api/backend/tests/integration/test_research_flow.py`:

1. **Test: New Analysis Flow**
   ```
   1. POST /conversations → Create "Research: AAPL"
   2. GET /report/AAPL/stream → Stream report (mock SSE)
   3. PUT /conversations/{id} → Save research_state with toc, ratings
   4. GET /conversations/{id} → Verify research_state persisted
   ```

2. **Test: Load Saved Conversation**
   ```
   1. GET /conversations → List conversations
   2. GET /conversations/{id} → Load research_state
   3. GET /report/AAPL/status → Verify report exists
   4. GET /report/AAPL/section/06_growth → Fetch section on-demand
   ```

3. **Test: Follow-up Message Persistence**
   ```
   1. POST /conversations/{id}/messages → Save followup_question
   2. POST /conversations/{id}/messages → Save followup_response
   3. GET /conversations/{id}/messages → Verify messages retrieved in order
   ```

### Phase 4: Concurrency Test - Multi-User Access

Test that shared reports work correctly with multiple users:

1. **Test: Same Report, Different Users**
   - User A and User B both access AAPL report
   - Each user has their own conversation with different active_section_id
   - Verify no cross-contamination of conversation state

2. **Test: Conversation Ownership**
   - User A creates conversation
   - User B tries to access User A's conversation → 403 Access Denied
   - Verify user_id ownership check in conversations_handler.py

3. **Test: Concurrent Metadata Updates**
   - Simulate rapid consecutive PUT requests to same conversation
   - Verify DynamoDB handles updates correctly (no lost updates)
   - Use update expressions (not replace) for safety

### Phase 5: Edge Cases

1. **Report Expiration**
   - Mock report with expired TTL
   - Verify /status returns `{expired: true}`
   - Verify /section returns appropriate error

2. **Missing Section**
   - Request section_id that doesn't exist
   - Verify 404 response

3. **Invalid Conversation ID**
   - Request conversation that doesn't exist
   - Verify 404 response

4. **Malformed research_state**
   - Send research_state missing required fields
   - Verify appropriate error handling

## Key Files to Test

| File | Purpose | Test Priority |
|------|---------|---------------|
| `lambda/investment_research/app.py` | Section endpoints | HIGH |
| `lambda/investment_research/services/report_service.py` | DynamoDB queries | HIGH |
| `src/handlers/conversations_handler.py` | Metadata updates | HIGH |
| `terraform/modules/dynamodb/reports_table.tf` | Schema reference | LOW |
| `terraform/modules/dynamodb/conversations.tf` | Schema reference | LOW |

## Success Criteria

1. All unit tests pass with 100% coverage of critical paths
2. Integration tests verify end-to-end flow
3. Concurrency tests confirm multi-user isolation
4. Edge cases handled gracefully with appropriate error messages

## Multi-User Design Evaluation

**Question from user**: Is having tables reference each other good for concurrent multi-user access?

**Answer**: YES, the current design is appropriate:

1. **Reports are SHARED** (one copy per ticker in `investment_reports_v2`)
   - Multiple users read the same report data
   - No write conflicts since reports are generated once and cached
   - TTL handles expiration automatically

2. **Conversations are USER-SPECIFIC** (filtered by `user_id`)
   - Each user has their own viewing state
   - `research_state` stores which sections they've viewed
   - No cross-user interference

3. **Reference Pattern** (not foreign keys):
   - `research_state.ticker` references report data by ticker
   - No DynamoDB enforced constraints
   - Application code handles missing data gracefully

4. **Potential Improvement**:
   - Consider adding `version` or `etag` to research_state for optimistic locking
   - Would prevent lost updates if same user has multiple browser tabs

## Run Command

```bash
# From project root
cd chat-api/backend

# Run all tests
pytest lambda/investment_research/tests/test_section_endpoints.py -v
pytest src/handlers/tests/test_conversations_research_state.py -v
pytest tests/integration/test_research_flow.py -v

# Or run with coverage
pytest --cov=lambda/investment_research --cov=src/handlers -v
```

---

*Prompt Version: 1.0*
*Created: January 2026*
*Purpose: Ralph Loop testing for DynamoDB integration*
