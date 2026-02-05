# Testing

This document covers the testing strategy and test suites for BuffettGPT.

## Overview

BuffettGPT uses multiple testing approaches:

- **Unit Tests** - Python pytest for backend logic
- **Integration Tests** - DynamoDB and API Gateway testing
- **E2E Tests** - Frontend SSE and state management

## Backend Tests

### Running Tests

```bash
cd chat-api/backend
make test           # Run all tests
pytest tests/ -v    # Verbose output
pytest --cov=src    # With coverage
```

### Test Structure

```
chat-api/backend/tests/
├── test_report_generator.py     # Report generation tests
├── test_section_parser.py       # Section parsing tests (22 tests)
├── test_migrate_to_v2.py        # Migration tests
└── investment_research/
    └── batch_generation/
        └── tests/               # Batch generation tests
```

### Key Test Files

| File | Tests | Purpose |
|------|-------|---------|
| test_section_parser.py | 22 | Markdown parsing, ToC building |
| test_report_generator.py | ~20 | Report generation, DynamoDB operations |
| test_migrate_to_v2.py | ~15 | V1 to V2 schema migration |

## Frontend Tests

### E2E Test Suite

The frontend has 92 passing tests:

| Category | Count | Focus |
|----------|-------|-------|
| Reducer Tests | 43 | State management |
| SSE Tests | 21 | Connection handling |
| Event Parsing | 28 | Event processing |

### Running Frontend Tests

```bash
cd frontend
npm run lint        # ESLint (0 warnings policy)
npm run test        # Run test suite
```

## Integration Tests

### DynamoDB Tests

Tests use moto for AWS mocking:

```python
import pytest
from moto import mock_dynamodb

@mock_dynamodb
def test_save_report():
    # Test DynamoDB operations
    pass
```

### API Gateway Tests

Test endpoints locally:

```bash
cd chat-api/backend
make run-http

# In another terminal
curl http://localhost:8000/health
```

## Test Coverage

### Coverage Requirements

- **Backend**: Minimum 80% coverage for core modules
- **Frontend**: All reducers and event handlers tested

### Generating Coverage Report

```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## Best Practices

1. **Mock External Services** - Use moto for AWS, mock FMP API
2. **Test Edge Cases** - Empty data, invalid inputs, timeouts
3. **Maintain Test Data** - Keep fixtures up to date
4. **Run Before Commit** - All tests must pass

## Related

- [Development Guide](index.md)
- [Deployment](../infrastructure/deployment.md)
