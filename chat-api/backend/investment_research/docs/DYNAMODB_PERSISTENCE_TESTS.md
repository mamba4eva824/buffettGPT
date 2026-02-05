# DynamoDB Persistence Tests Documentation

## Overview

This document details the test suite that validates DynamoDB persistence for the Investment Research system. The tests ensure that user interactions (ToC clicks, section selections, follow-up messages) are correctly persisted and restored across sessions.

---

## Table of Contents

1. [Architecture Summary](#1-architecture-summary)
2. [Test Suite Organization](#2-test-suite-organization)
3. [API Persistence Flows](#3-api-persistence-flows)
4. [Test Coverage Details](#4-test-coverage-details)
5. [Running the Tests](#5-running-the-tests)
6. [Key Assertions](#6-key-assertions)

---

## 1. Architecture Summary

### 1.1 Three-Table Persistence Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DynamoDB Persistence Model                          │
├─────────────────────────┬─────────────────────────┬─────────────────────────┤
│   investment_reports_v2 │      conversations      │     chat_messages       │
│      (SHARED DATA)      │    (USER-SPECIFIC)      │    (USER-SPECIFIC)      │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ • Report content        │ • research_state        │ • Follow-up Q&A         │
│ • ToC structure         │   - ticker (reference)  │ • Question/response     │
│ • Section markdown      │   - active_section_id   │   pairs                 │
│ • Ratings/verdict       │   - visible_sections    │ • Chronological order   │
│ • TTL expiration        │   - toc (cached copy)   │                         │
│                         │   - ratings (cached)    │                         │
├─────────────────────────┼─────────────────────────┼─────────────────────────┤
│ PK: ticker              │ PK: conversation_id     │ PK: conversation_id     │
│ SK: section_id          │                         │ SK: timestamp           │
└─────────────────────────┴─────────────────────────┴─────────────────────────┘
```

### 1.2 Key Persistence Principle

**Reports are SHARED, State is ISOLATED**

- Multiple users can read the same report (by `ticker`) from `investment_reports_v2`
- Each user has their own `conversation` with their own `research_state`
- The conversation stores a **reference** (`ticker`) to the shared report, not a copy

---

## 2. Test Suite Organization

### 2.1 Test Files

| File | Location | Purpose |
|------|----------|---------|
| `test_section_endpoints.py` | `lambda/investment_research/tests/` | Section API DynamoDB operations |
| `test_conversations_research_state.py` | `tests/` | Conversation metadata persistence |
| `test_research_flow.py` | `tests/integration/` | End-to-end integration tests |

### 2.2 Test Count by Category

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Test Suite Summary (59 tests)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  test_section_endpoints.py (26 tests)                                       │
│  ├── TestGetReportSection (8 tests)       Key construction, TTL, Decimal    │
│  ├── TestGetExecutive (5 tests)           ToC retrieval, ratings            │
│  ├── TestGetReportStatus (6 tests)        Expiration logic                  │
│  ├── TestSectionEndpointDynamoDB (2 tests) API → DynamoDB flow              │
│  ├── TestStatusEndpointDynamoDB (2 tests)  Status endpoint validation       │
│  └── TestEdgeCases (3 tests)              Decimal conversion, errors        │
│                                                                             │
│  test_conversations_research_state.py (17 tests)                            │
│  ├── TestConvertFloatsToDecimal (5 tests) DynamoDB Decimal handling         │
│  ├── TestUpdateConversationWithResearchState (7 tests) PUT persistence      │
│  ├── TestGetConversationWithResearchState (2 tests) GET restoration         │
│  ├── TestConversationOwnership (3 tests)  User access control               │
│  ├── TestErrorHandling (2 tests)          DynamoDB errors                   │
│  └── TestCreateConversationWithMetadata (1 test) Initial creation           │
│                                                                             │
│  test_research_flow.py (16 tests)                                           │
│  ├── TestNewAnalysisFlow (3 tests)        Create → Stream → Save            │
│  ├── TestLoadSavedConversation (3 tests)  Restore state after refresh       │
│  ├── TestFollowupMessagePersistence (3 tests) Q&A message storage           │
│  ├── TestMultiUserConcurrency (3 tests)   Shared reports, isolated state    │
│  └── TestEdgeCasesIntegration (4 tests)   Expiration, missing data          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. API Persistence Flows

### 3.1 ToC Click → Save Active Section

**User Action:** Clicks a section in the Table of Contents

**API Call:** `PUT /conversations/{conversation_id}`

```
┌──────────────┐                    ┌─────────────────┐                    ┌─────────────┐
│   Frontend   │                    │   Lambda        │                    │  DynamoDB   │
│  (React)     │                    │ conversations   │                    │conversations│
└──────┬───────┘                    │   _handler.py   │                    │   table     │
       │                            └────────┬────────┘                    └──────┬──────┘
       │ PUT /conversations/{id}             │                                    │
       │ {                                   │                                    │
       │   "metadata": {                     │                                    │
       │     "research_state": {             │                                    │
       │       "active_section_id":          │                                    │
       │         "06_growth",  ◄─────────────┼── User clicked "Growth" section    │
       │       "visible_sections": [         │                                    │
       │         "01_executive_summary",     │                                    │
       │         "06_growth"                 │                                    │
       │       ]                             │                                    │
       │     }                               │                                    │
       │   }                                 │                                    │
       │ }                                   │                                    │
       │────────────────────────────────────▶│                                    │
       │                                     │ 1. Get existing conversation       │
       │                                     │────────────────────────────────────▶│
       │                                     │◀────────────────────────────────────│
       │                                     │                                    │
       │                                     │ 2. Verify user ownership           │
       │                                     │    (user_id == requester)          │
       │                                     │                                    │
       │                                     │ 3. Merge metadata (preserve        │
       │                                     │    existing keys like 'source')    │
       │                                     │                                    │
       │                                     │ 4. Convert floats → Decimal        │
       │                                     │                                    │
       │                                     │ 5. UpdateItem                      │
       │                                     │────────────────────────────────────▶│
       │                                     │    SET #metadata = :merged_meta    │
       │                                     │◀────────────────────────────────────│
       │◀────────────────────────────────────│                                    │
       │ 200 OK                              │                                    │
```

**Test Validation:** `test_partial_metadata_update_preserves_existing_keys`

```python
# Verifies existing metadata keys are NOT clobbered
merged_metadata = attr_values[':metadata']
assert 'source' in merged_metadata       # Original key preserved
assert 'version' in merged_metadata      # Original key preserved
assert 'research_state' in merged_metadata  # New key added
```

---

### 3.2 Page Refresh → Restore State

**User Action:** Refreshes browser or returns to saved conversation

**API Calls:**
1. `GET /conversations/{conversation_id}` - Retrieve research_state
2. `GET /report/{ticker}/status` - Check if report still valid
3. `GET /report/{ticker}/section/{section_id}` - Fetch section content on-demand

```
┌──────────────┐                    ┌─────────────────┐                    ┌─────────────┐
│   Frontend   │                    │   Lambda        │                    │  DynamoDB   │
│  (React)     │                    │                 │                    │             │
└──────┬───────┘                    └────────┬────────┘                    └──────┬──────┘
       │                                     │                                    │
       │ 1. GET /conversations/{id}          │                                    │
       │────────────────────────────────────▶│                                    │
       │                                     │ GetItem(conversation_id)           │
       │                                     │────────────────────────────────────▶│
       │                                     │◀────────────────────────────────────│
       │◀────────────────────────────────────│                                    │
       │ {                                   │                                    │
       │   "metadata": {                     │                                    │
       │     "research_state": {             │                                    │
       │       "ticker": "AAPL",  ◄──────────┼── Reference to shared report       │
       │       "active_section_id":          │                                    │
       │         "06_growth",     ◄──────────┼── Restore ToC highlight            │
       │       "visible_sections": [...],    │                                    │
       │       "toc": [...],      ◄──────────┼── Cached ToC for instant render    │
       │       "ratings": {...}   ◄──────────┼── Cached ratings                   │
       │     }                               │                                    │
       │   }                                 │                                    │
       │ }                                   │                                    │
       │                                     │                                    │
       │ 2. GET /report/AAPL/status          │                                    │
       │────────────────────────────────────▶│                                    │
       │                                     │ GetItem(ticker, "00_executive")    │
       │                                     │────────────────────────────────────▶│
       │                                     │◀────────────────────────────────────│
       │◀────────────────────────────────────│   (Check TTL expiration)           │
       │ {                                   │                                    │
       │   "exists": true,                   │                                    │
       │   "expired": false,                 │                                    │
       │   "ttl_remaining_days": 25          │                                    │
       │ }                                   │                                    │
       │                                     │                                    │
       │ 3. GET /report/AAPL/section/06_growth  (on ToC click)                    │
       │────────────────────────────────────▶│                                    │
       │                                     │ GetItem(ticker, section_id)        │
       │                                     │────────────────────────────────────▶│
       │                                     │◀────────────────────────────────────│
       │◀────────────────────────────────────│                                    │
       │ {                                   │                                    │
       │   "content": "## Revenue Growth..." │                                    │
       │ }                                   │                                    │
```

**Test Validation:** `test_returns_research_state_in_metadata`

```python
# Verifies research_state is returned for restoration
body = json.loads(response['body'])
assert 'metadata' in body
assert 'research_state' in body['metadata']
assert body['metadata']['research_state']['ticker'] == 'AAPL'
```

---

### 3.3 Section Fetch → DynamoDB Read

**User Action:** Clicks ToC item for unloaded section

**API Call:** `GET /report/{ticker}/section/{section_id}`

```
┌──────────────┐                    ┌─────────────────┐                    ┌───────────────────┐
│   Frontend   │                    │   Lambda        │                    │ investment_       │
│  (React)     │                    │ investment_     │                    │ reports_v2        │
└──────┬───────┘                    │ research/app.py │                    │ table             │
       │                            └────────┬────────┘                    └─────────┬─────────┘
       │                                     │                                       │
       │ GET /report/AAPL/section/06_growth  │                                       │
       │────────────────────────────────────▶│                                       │
       │                                     │                                       │
       │                                     │ Key Construction:                     │
       │                                     │ ticker.upper() = "AAPL"               │
       │                                     │ section_id.lower() = "06_growth"      │
       │                                     │                                       │
       │                                     │ GetItem(                              │
       │                                     │   Key={                               │
       │                                     │     'ticker': 'AAPL',                 │
       │                                     │     'section_id': '06_growth'         │
       │                                     │   }                                   │
       │                                     │ )                                     │
       │                                     │──────────────────────────────────────▶│
       │                                     │◀──────────────────────────────────────│
       │                                     │                                       │
       │                                     │ TTL Expiration Check:                 │
       │                                     │ if item['ttl'] < now():               │
       │                                     │   return {"expired": true}            │
       │                                     │                                       │
       │                                     │ Decimal → float/int conversion:       │
       │                                     │ word_count: Decimal('200') → 200      │
       │                                     │                                       │
       │◀────────────────────────────────────│                                       │
       │ {                                   │                                       │
       │   "section_id": "06_growth",        │                                       │
       │   "title": "Growth Analysis",       │                                       │
       │   "content": "## Revenue...",       │                                       │
       │   "part": 2,                        │                                       │
       │   "icon": "trending-up",            │                                       │
       │   "word_count": 200                 │                                       │
       │ }                                   │                                       │
```

**Test Validation:** `test_get_section_correct_key_construction`

```python
# Verifies key normalization
mock_table.get_item.assert_called_once_with(
    Key={
        'ticker': 'AAPL',      # Uppercased
        'section_id': '06_growth'  # Lowercased
    }
)
```

---

## 4. Test Coverage Details

### 4.1 Conversation Metadata Tests

#### `test_creates_metadata_when_not_exists`
**Purpose:** Validates that research_state can be created on conversations without existing metadata.

```python
# Scenario: Conversation has no metadata field
existing_conv = {'conversation_id': 'abc', 'user_id': 'user-123'}  # No metadata

# Action: PUT with research_state
body = {'metadata': {'research_state': {...}}}

# Assertion: UpdateExpression creates metadata
assert '#metadata = :metadata' in update_expr
```

#### `test_partial_metadata_update_preserves_existing_keys`
**Purpose:** Validates that updating research_state doesn't clobber other metadata keys.

```python
# Scenario: Conversation has existing metadata
existing_metadata = {'source': 'research', 'version': '2.0'}

# Action: Add research_state
body = {'metadata': {'research_state': {...}}}

# Assertion: All keys preserved
merged = attr_values[':metadata']
assert merged['source'] == 'research'     # Preserved
assert merged['version'] == '2.0'         # Preserved
assert 'research_state' in merged         # Added
```

#### `test_update_overwrites_existing_research_state`
**Purpose:** Validates that subsequent ToC clicks properly update the active section.

```python
# Scenario: User was on '06_growth', clicks '11_debt'
existing_state = {'active_section_id': '06_growth'}
new_state = {'active_section_id': '11_debt'}

# Assertion: New state overwrites old
assert merged['research_state']['active_section_id'] == '11_debt'
```

### 4.2 Section Endpoint Tests

#### `test_get_section_ttl_expired_returns_none`
**Purpose:** Validates expired reports are handled correctly.

```python
# Scenario: Report TTL has passed
mock_item = {'ticker': 'AAPL', 'ttl': Decimal(str(past_timestamp))}

# Assertion: Service returns None (not the expired content)
result = get_report_section('AAPL', '06_growth')
assert result is None
```

#### `test_status_endpoint_returns_expiration_info`
**Purpose:** Validates status endpoint provides TTL information.

```python
# Assertion: Response includes expiration details
assert data['exists'] is True
assert data['expired'] is False
assert data['ttl_remaining_days'] == 75
```

### 4.3 Multi-User Concurrency Tests

#### `test_same_report_different_users`
**Purpose:** Validates that reports are shared but conversation states are isolated.

```python
# Scenario: User A and User B both researching AAPL
conv_a = {'user_id': 'user-A', 'metadata': {'research_state': {'active_section_id': '06_growth'}}}
conv_b = {'user_id': 'user-B', 'metadata': {'research_state': {'active_section_id': '01_exec'}}}

# Assertion: Same report, different active sections
report_a = get_section('AAPL', '06_growth')
report_b = get_section('AAPL', '06_growth')
assert report_a == report_b  # Same shared content

# But different states
assert conv_a['active_section_id'] != conv_b['active_section_id']
```

#### `test_conversation_ownership_prevents_cross_access`
**Purpose:** Validates users cannot access other users' conversations.

```python
# Scenario: User B tries to access User A's conversation
conv_owner = 'user-A-123'
requester = 'user-B-456'

# Assertion: 403 Forbidden returned
response = get_conversation(event_with_user_b)
assert response['statusCode'] == 403
```

### 4.4 DynamoDB Type Conversion Tests

#### `test_research_state_floats_converted_to_decimal`
**Purpose:** Validates float → Decimal conversion for DynamoDB compatibility.

```python
# Scenario: research_state contains floats
body = {
    'metadata': {
        'research_state': {
            'ratings': {'confidence': 0.85}  # Float
        }
    }
}

# Assertion: Stored as Decimal
confidence = saved_metadata['ratings']['confidence']
assert isinstance(confidence, Decimal)
```

#### `test_decimal_to_float_conversion_nested`
**Purpose:** Validates Decimal → float conversion when reading from DynamoDB.

```python
# Scenario: DynamoDB returns Decimals
item = {'word_count': Decimal('200'), 'ratings': {'confidence': Decimal('0.85')}}

# Assertion: Converted to native Python types
result = decimal_to_native(item)
assert isinstance(result['word_count'], int)
assert isinstance(result['ratings']['confidence'], float)
```

---

## 5. Running the Tests

### 5.1 Run All Persistence Tests

```bash
cd chat-api/backend

# Run all three test files
pytest tests/test_conversations_research_state.py \
       tests/integration/test_research_flow.py \
       lambda/investment_research/tests/test_section_endpoints.py \
       -v
```

### 5.2 Run Specific Test Categories

```bash
# Section endpoint tests only
pytest lambda/investment_research/tests/test_section_endpoints.py -v

# Conversation metadata tests only
pytest tests/test_conversations_research_state.py -v

# Integration tests only
pytest tests/integration/test_research_flow.py -v
```

### 5.3 Run with Coverage

```bash
pytest tests/test_conversations_research_state.py \
       tests/integration/test_research_flow.py \
       lambda/investment_research/tests/test_section_endpoints.py \
       --cov=src.handlers.conversations_handler \
       --cov=lambda.investment_research.services.report_service \
       --cov-report=term-missing
```

### 5.4 Expected Output

```
============================= test session starts ==============================
collected 59 items

test_section_endpoints.py::TestGetReportSection::test_get_section_correct_key_construction PASSED
test_section_endpoints.py::TestGetReportSection::test_get_section_returns_content PASSED
test_section_endpoints.py::TestGetReportSection::test_get_section_ttl_valid_returns_content PASSED
test_section_endpoints.py::TestGetReportSection::test_get_section_ttl_expired_returns_none PASSED
...
test_conversations_research_state.py::TestUpdateConversationWithResearchState::test_creates_metadata_when_not_exists PASSED
test_conversations_research_state.py::TestUpdateConversationWithResearchState::test_partial_metadata_update_preserves_existing_keys PASSED
...
test_research_flow.py::TestMultiUserConcurrency::test_same_report_different_users PASSED
test_research_flow.py::TestMultiUserConcurrency::test_conversation_ownership_prevents_cross_access PASSED

============================= 59 passed in 2.34s ===============================
```

---

## 6. Key Assertions

### 6.1 Persistence Guarantees

| Scenario | Assertion | Test |
|----------|-----------|------|
| ToC click saves active section | `active_section_id` persisted to DynamoDB | `test_research_state_toc_saved_correctly` |
| Page refresh restores state | `research_state` returned in GET response | `test_returns_research_state_in_metadata` |
| Metadata merge preserves keys | Existing keys not clobbered | `test_partial_metadata_update_preserves_existing_keys` |
| Users cannot cross-access | 403 returned for non-owner | `test_access_denied_for_different_user` |
| Reports are shared | Same content for different users | `test_same_report_different_users` |
| State is isolated | Different users have different states | `test_no_cross_contamination_of_state` |
| Expired reports handled | Returns `expired: true` | `test_report_expiration_check` |
| Floats converted for DynamoDB | `Decimal` type used | `test_research_state_floats_converted_to_decimal` |

### 6.2 Data Flow Verification

```
User clicks ToC → PUT /conversations/{id}
                         │
                         ▼
        ┌────────────────────────────────┐
        │ Test: update_conversation()    │
        │ Asserts:                       │
        │ • get_item called to fetch     │
        │ • user_id ownership verified   │
        │ • metadata merged correctly    │
        │ • update_item called with SET  │
        └────────────────────────────────┘
                         │
                         ▼
              DynamoDB conversations table
                         │
                         ▼
User refreshes → GET /conversations/{id}
                         │
                         ▼
        ┌────────────────────────────────┐
        │ Test: get_conversation()       │
        │ Asserts:                       │
        │ • research_state in response   │
        │ • ticker present               │
        │ • active_section_id present    │
        └────────────────────────────────┘
                         │
                         ▼
       Frontend restores UI state from metadata
```

---

## Appendix A: research_state Schema

```typescript
interface ResearchState {
  // Reference to shared report
  ticker: string;                    // "AAPL" - used to fetch from investment_reports_v2

  // UI State (persisted per-user)
  active_section_id: string;         // "06_growth" - ToC highlight
  visible_sections: string[];        // ["01_exec", "06_growth"] - expanded sections

  // Cached Report Metadata (for instant restore without re-fetching)
  toc: {
    section_id: string;
    title: string;
    part: 1 | 2 | 3;
    icon: string;
    word_count: number;
    display_order: number;
  }[];

  ratings: {
    growth: { rating: string; confidence: number };
    debt: { rating: string; confidence: number };
    cashflow: { rating: string; confidence: number };
    overall_verdict: "BUY" | "HOLD" | "SELL";
    conviction: "High" | "Medium" | "Low";
  };

  // Timestamps
  report_generated_at: string;       // ISO timestamp of report creation
  report_expires_at: string;         // ISO timestamp of TTL expiration
}
```

---

## Appendix B: DynamoDB Key Schemas

### investment_reports_v2

```
Primary Key:
  ticker (String, HASH) + section_id (String, RANGE)

Example Keys:
  ("AAPL", "00_executive")     → Metadata item with ToC, ratings
  ("AAPL", "01_executive_summary") → Executive summary content
  ("AAPL", "06_growth")        → Growth analysis content
```

### conversations

```
Primary Key:
  conversation_id (String, HASH)

GSI: user-conversations-index
  user_id (HASH) + updated_at (RANGE)
```

### chat_messages

```
Primary Key:
  conversation_id (String, HASH) + timestamp (Number, RANGE)
```

---

*Document Version: 1.0*
*Last Updated: January 2025*
*Test Suite Version: 59 tests across 3 files*
