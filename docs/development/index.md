# Development Guide

This section covers development workflows, testing strategies, and contribution guidelines for BuffettGPT.

## Overview

BuffettGPT development involves three main areas:

- **Backend**: Python Lambda functions with boto3
- **Frontend**: React components with Vite
- **Infrastructure**: Terraform modules

## Documentation

| Document | Description |
|----------|-------------|
| [Testing](testing.md) | Test suites and coverage requirements |
| [Streaming](streaming.md) | SSE chunk streaming implementation |
| [UI Guidelines](ui-guidelines.md) | Frontend patterns and best practices |

## Development Setup

### Backend

```bash
cd chat-api/backend
make venv                    # Create virtual environment
source venv/bin/activate     # Activate environment
make dev-install             # Install dependencies

# Run tests
make test

# Build Lambda packages
./scripts/build_layer.sh     # Build dependencies layer
./scripts/build_lambdas.sh   # Package all functions
```

### Frontend

```bash
cd frontend
npm install                  # Install dependencies
npm run dev                  # Start dev server (port 3000)
npm run build                # Production build
npm run lint                 # ESLint (0 warnings policy)
```

## Code Standards

### Python (Backend)

- **Style**: PEP 8 with Black formatting
- **Type Hints**: Required for public functions
- **Testing**: pytest with moto for AWS mocking
- **Error Handling**: Custom exceptions with boto3 ClientError handling

### JavaScript (Frontend)

- **Style**: ESLint with 0 warnings policy
- **Components**: Functional components with hooks
- **State**: React Context for global state
- **Styling**: Tailwind CSS utility classes

### Terraform

- **Variables**: `snake_case` naming
- **Resources**: Follow AWS naming conventions
- **Modules**: Reusable, single-purpose modules

## Testing Strategy

### Backend Tests

```bash
cd chat-api/backend
make test                    # Run all tests
pytest tests/ -v             # Verbose output
pytest tests/ --cov=src      # With coverage
```

### Frontend Linting

```bash
cd frontend
npm run lint                 # Must pass with 0 warnings
```

## Common Tasks

### Add a New Lambda Function

1. Create handler in `chat-api/backend/src/handlers/`
2. Add to `scripts/build_lambdas.sh`
3. Define in `chat-api/terraform/modules/lambda/`
4. Add API Gateway route if needed
5. Run build and deploy

### Add a New API Endpoint

1. Define Lambda handler
2. Add route in `chat-api/terraform/modules/api-gateway/`
3. Update IAM policies if needed
4. Test locally, then deploy

### Debug WebSocket Issues

1. Check CloudWatch logs for `websocket_*` handlers
2. Verify `websocket-connections` DynamoDB table
3. Check SQS queue metrics for backlog
