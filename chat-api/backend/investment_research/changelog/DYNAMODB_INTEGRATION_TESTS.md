# DynamoDB Integration Tests for Investment Research

## Overview

This document describes the unit tests created for DynamoDB read/write operations in the Investment Research system. These tests cover two primary areas:

1. **Conversation research_state persistence** - Testing PUT/GET operations for saving and retrieving ToC section selections
2. **Investment research section endpoints** - Testing V2 section-based report retrieval from DynamoDB

**Date Created:** January 24, 2026
**Test Framework:** pytest with unittest.mock
**Test Location:** `chat-api/backend/tests/`

---

## Test Files

| File | Tests | Purpose |
|------|-------|---------|
| [test_conversations_research_state.py](chat-api/backend/tests/test_conversations_research_state.py) | 20 | Conversation metadata persistence |
| [test_investment_research_sections.py](chat-api/backend/tests/test_investment_research_sections.py) | 34 | Investment report section endpoints |

**Total Tests:** 54

---

## Running Tests

```bash
# Navigate to backend directory
cd chat-api/backend

# Run all DynamoDB integration tests
pytest tests/test_conversations_research_state.py tests/test_investment_research_sections.py -v

# Run with coverage
pytest tests/test_conversations_research_state.py tests/test_investment_research_sections.py -v --cov=src --cov=lambda

# Run specific test class
pytest tests/test_conversations_research_state.py::TestUpdateConversationWithResearchState -v

# Run single test
pytest tests/test_investment_research_sections.py::TestGetExecutive::test_returns_none_when_expired -v
```

---

## Test File 1: test_conversations_research_state.py

### Purpose
Tests DynamoDB operations for the conversations table, specifically for persisting research_state metadata (ToC section selections).

### Test Classes

#### 1. TestConvertFloatsToDecimal (5 tests)

Tests the `convert_floats_to_decimal()` utility function required for DynamoDB compatibility.

| Test | Description |
|------|-------------|
| `test_converts_simple_float` | Single float to Decimal conversion |
| `test_converts_nested_floats` | Nested dict floats to Decimal |
| `test_converts_floats_in_lists` | List of floats to Decimal |
| `test_preserves_non_float_types` | Non-float types remain unchanged |
| `test_converts_research_state` | Full research_state structure conversion |

#### 2. TestUpdateConversationWithResearchState (7 tests)

Tests PUT /conversations/{id} with research_state in metadata.

| Test | Description |
|------|-------------|
| `test_creates_metadata_when_not_exists` | Creates metadata attribute when conversation has none |
| `test_partial_metadata_update_preserves_existing_keys` | Merge + replace preserves existing metadata keys |
| `test_research_state_floats_converted_to_decimal` | Float confidence values converted for DynamoDB |
| `test_research_state_toc_saved_correctly` | ToC array structure saved properly |
| `test_merge_preserves_all_existing_metadata_keys` | All existing keys preserved (source, version, theme, etc.) |
| `test_update_overwrites_existing_research_state` | Updating research_state replaces previous value |
| `test_handles_empty_existing_metadata` | Works when metadata exists but is empty `{}` |

#### 3. TestGetConversationWithResearchState (2 tests)

Tests GET /conversations/{id} retrieval of research_state.

| Test | Description |
|------|-------------|
| `test_returns_research_state_in_metadata` | research_state returned in conversation metadata |
| `test_returns_empty_metadata_when_not_exists` | No error when metadata doesn't exist |

#### 4. TestConversationOwnership (3 tests)

Tests user authorization for conversation access.

| Test | Description |
|------|-------------|
| `test_access_denied_for_different_user` | 403 returned when user doesn't own conversation |
| `test_update_denied_for_different_user` | 403 returned on PUT for non-owner |
| `test_access_allowed_for_owner` | 200 returned for conversation owner |

#### 5. TestErrorHandling (2 tests)

Tests error handling for DynamoDB failures.

| Test | Description |
|------|-------------|
| `test_returns_404_for_nonexistent_conversation` | 404 for missing conversation |
| `test_handles_dynamodb_error` | 500 returned on DynamoDB ClientError |

#### 6. TestCreateConversationWithMetadata (1 test)

Tests POST /conversations with initial metadata.

| Test | Description |
|------|-------------|
| `test_creates_conversation_with_initial_metadata` | Conversation created with metadata including research_state |

### Key Mock Structure

```python
# Mock conversation with research_state
def get_mock_conversation(user_id, with_metadata=False, with_research_state=False):
    conv = {
        'conversation_id': 'test-conv-123',
        'user_id': user_id,
        'title': 'Research: AAPL',
        'created_at': '2024-01-01T10:00:00Z',
        'updated_at': 1704099600,
        'message_count': 5,
        'is_archived': False,
        'user_type': 'authenticated'
    }
    if with_metadata:
        conv['metadata'] = {'source': 'research', 'version': '2.0'}
        if with_research_state:
            conv['metadata']['research_state'] = get_mock_research_state()
    return conv

# Mock research_state structure
def get_mock_research_state():
    return {
        'ticker': 'AAPL',
        'active_section_id': '06_growth',
        'visible_sections': ['01_executive_summary', '06_growth', '11_debt'],
        'toc': [...],
        'ratings': {
            'growth': {'rating': 'Stable', 'confidence': 0.85},
            'debt': {'rating': 'Strong', 'confidence': 0.9},
            'overall_verdict': 'HOLD',
            'conviction': 'High'
        },
        'report_generated_at': '2024-01-01T12:00:00Z',
        'report_expires_at': '2024-04-01T12:00:00Z'
    }
```

---

## Test File 2: test_investment_research_sections.py

### Purpose
Tests DynamoDB operations for the investment_reports_v2 table (section-based progressive loading).

### Test Classes

#### 1. TestDecimalToFloat (5 tests)

Tests `decimal_to_float()` utility for JSON serialization.

| Test | Description |
|------|-------------|
| `test_converts_decimal_to_int_for_whole_numbers` | Decimal('100') → int 100 |
| `test_converts_decimal_to_float_for_fractions` | Decimal('0.85') → float 0.85 |
| `test_converts_nested_decimals_in_dict` | Nested dicts converted recursively |
| `test_converts_decimals_in_lists` | Lists converted recursively |
| `test_preserves_non_decimal_types` | Strings, bools, etc. unchanged |

#### 2. TestValidateTicker (5 tests)

Tests ticker symbol validation.

| Test | Description |
|------|-------------|
| `test_accepts_valid_tickers` | 'AAPL', 'MSFT', 'A', 'GOOGL' accepted |
| `test_rejects_empty_ticker` | Empty string and None rejected |
| `test_rejects_ticker_with_numbers` | 'AAP1', '123' rejected |
| `test_rejects_too_long_ticker` | 'TOOLONG' (>5 chars) rejected |
| `test_handles_lowercase` | 'aapl' accepted (converted to uppercase) |

#### 3. TestGetExecutive (5 tests)

Tests GET /report/{ticker}/executive endpoint.

| Test | Description |
|------|-------------|
| `test_returns_executive_item_when_exists` | Returns toc, ratings, executive_summary |
| `test_returns_none_when_not_found` | None for non-existent ticker |
| `test_returns_none_when_expired` | None when TTL has passed |
| `test_converts_decimals_to_floats` | Decimal values converted for JSON |
| `test_normalizes_ticker_to_uppercase` | 'aapl' → 'AAPL' in DynamoDB query |

#### 4. TestGetReportToc (2 tests)

Tests GET /report/{ticker}/toc endpoint.

| Test | Description |
|------|-------------|
| `test_returns_toc_from_executive_item` | ToC extracted from executive item |
| `test_returns_none_when_not_found` | None for non-existent ticker |

#### 5. TestGetReportSection (4 tests)

Tests GET /report/{ticker}/section/{section_id} endpoint.

| Test | Description |
|------|-------------|
| `test_returns_section_when_exists` | Section with content, title, part returned |
| `test_returns_none_when_not_found` | None for non-existent section |
| `test_returns_none_when_expired` | None when section TTL has passed |
| `test_normalizes_section_id_to_lowercase` | '06_GROWTH' → '06_growth' |

#### 6. TestGetAllSections (3 tests)

Tests retrieving all sections for a ticker.

| Test | Description |
|------|-------------|
| `test_returns_sections_sorted_by_display_order` | Sections sorted by display_order |
| `test_excludes_executive_item` | '00_executive' filtered out |
| `test_returns_empty_list_when_no_sections` | Empty list for missing ticker |

#### 7. TestCheckReportExistsV2 (3 tests)

Tests report existence checking.

| Test | Description |
|------|-------------|
| `test_returns_true_when_exists_and_not_expired` | True for valid, non-expired report |
| `test_returns_false_when_not_found` | False for non-existent ticker |
| `test_returns_false_when_expired` | False when TTL has passed |

#### 8. TestGetReportStatus (3 tests)

Tests GET /report/{ticker}/status endpoint.

| Test | Description |
|------|-------------|
| `test_returns_status_with_remaining_days` | Returns exists, expired, ttl_remaining_days |
| `test_returns_expired_true_when_ttl_passed` | expired=True, ttl_remaining_days=0 |
| `test_returns_none_when_not_found` | None for non-existent ticker |

#### 9. TestErrorHandling (4 tests)

Tests error handling for DynamoDB failures.

| Test | Description |
|------|-------------|
| `test_get_executive_handles_dynamodb_error` | Returns None on DynamoDB error |
| `test_get_report_section_handles_dynamodb_error` | Returns None on DynamoDB error |
| `test_get_all_sections_handles_dynamodb_error` | Returns empty list on error |
| `test_check_report_exists_handles_dynamodb_error` | Returns False on error |

### Key Mock Structure

```python
# Mock executive item (00_executive in v2 table)
def get_mock_executive_item(ticker='AAPL', expired=False):
    ttl = int((datetime.utcnow() + timedelta(days=90 if not expired else -1)).timestamp())
    return {
        'ticker': ticker,
        'section_id': '00_executive',
        'toc': get_mock_toc(),  # 13 entries
        'ratings': get_mock_ratings(),
        'executive_summary': {
            'section_id': '01_executive_summary',
            'title': 'Executive Summary',
            'content': f'# {ticker} Executive Summary...',
            'part': 1,
            'icon': '📋',
            'word_count': 2300,
            'display_order': 1
        },
        'total_word_count': Decimal('15000'),
        'generated_at': '2025-01-15T10:30:00Z',
        'ttl': Decimal(str(ttl))
    }

# Mock individual section item
def get_mock_section(section_id, ticker='AAPL', expired=False):
    return {
        'ticker': ticker,
        'section_id': section_id,
        'title': 'Growth Analysis',
        'content': f'# Growth Analysis\n\nDetailed analysis...',
        'part': 2,
        'icon': '📈',
        'word_count': Decimal('650'),
        'display_order': 6,
        'ttl': Decimal(str(ttl))
    }
```

---

## DynamoDB Table Schemas Tested

### conversations Table

```
Primary Key: conversation_id (S)

Attributes tested:
- conversation_id (S) - Partition key
- user_id (S) - Owner user ID
- title (S) - Conversation title
- metadata (M) - Map containing:
  - source (S)
  - version (S)
  - research_state (M) - Map containing:
    - ticker (S)
    - active_section_id (S)
    - visible_sections (L)
    - toc (L)
    - ratings (M)
- updated_at (N) - Unix timestamp
- created_at (S) - ISO timestamp
```

### investment_reports_v2 Table

```
Primary Key: ticker (S), section_id (S)

Attributes tested:
- ticker (S) - Partition key
- section_id (S) - Sort key ('00_executive', '06_growth', etc.)
- toc (L) - Table of contents (on executive item)
- ratings (M) - Investment ratings (on executive item)
- executive_summary (M) - Merged Part 1 content (on executive item)
- content (S) - Section markdown content
- title (S) - Section title
- part (N) - Section part number (1, 2, or 3)
- icon (S) - Section icon
- word_count (N) - Word count
- display_order (N) - Sort order
- ttl (N) - TTL timestamp for auto-expiration
- generated_at (S) - Generation timestamp
- total_word_count (N) - Total report word count
```

---

## Test Results

```
============================== test session starts ==============================
platform darwin -- Python 3.11.5, pytest-9.0.2

tests/test_conversations_research_state.py: 20 passed
tests/test_investment_research_sections.py: 34 passed

============================== 54 passed in 0.25s ==============================
```

---

## Coverage Areas

| Area | Tests | Functions Covered |
|------|-------|-------------------|
| Metadata Persistence | 7 | `update_conversation()`, `convert_floats_to_decimal()` |
| Metadata Retrieval | 2 | `get_conversation()` |
| Authorization | 3 | `get_user_id()`, ownership checks |
| Section Endpoints | 17 | `get_executive()`, `get_report_toc()`, `get_report_section()`, `get_all_sections()` |
| Status Endpoints | 6 | `check_report_exists_v2()`, `get_report_status()` |
| Utility Functions | 10 | `decimal_to_float()`, `validate_ticker()` |
| Error Handling | 6 | Exception handling in all service functions |
| TTL Expiration | 4 | TTL checks in section retrieval |

---

## Future Test Additions

Consider adding tests for:

1. **Concurrent Updates** - Race conditions when multiple updates occur
2. **Large Metadata** - Behavior with very large research_state objects
3. **GSI Queries** - Testing part-index GSI for executive sections
4. **Pagination** - Testing pagination for large section lists
5. **Integration Tests** - End-to-end tests with moto or LocalStack

---

## Maintenance Notes

1. **Update mock data** when schema changes
2. **Run tests before deployment** to catch regressions
3. **Add tests for new endpoints** following existing patterns
4. **Keep TTL tests updated** if expiration logic changes
