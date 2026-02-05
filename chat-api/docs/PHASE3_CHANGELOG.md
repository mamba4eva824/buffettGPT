# Phase 3 Changelog - Investment Research Lambda

## Date: 2026-01-06

## Summary

Implemented the Investment Research Lambda - a Docker-based Lambda that serves cached investment reports from DynamoDB via SSE streaming. This Lambda follows the prediction_ensemble pattern but is significantly simpler (no ML dependencies).

---

## New Files Created

| File | Purpose |
|------|---------|
| `lambda/investment_research/Dockerfile` | Docker config with LWA v0.8.4 (NO ML deps) |
| `lambda/investment_research/requirements.txt` | Minimal deps: boto3, fastapi, uvicorn, sse-starlette, pydantic |
| `lambda/investment_research/app.py` | FastAPI application with SSE streaming |
| `lambda/investment_research/handler.py` | Direct Lambda invocation handler (optional) |
| `lambda/investment_research/config/__init__.py` | Config module exports |
| `lambda/investment_research/config/settings.py` | Environment configuration |
| `lambda/investment_research/models/__init__.py` | Models module exports |
| `lambda/investment_research/models/schemas.py` | Pydantic models, DecimalEncoder |
| `lambda/investment_research/services/__init__.py` | Services module exports |
| `lambda/investment_research/services/report_service.py` | DynamoDB report retrieval |
| `lambda/investment_research/services/streaming.py` | SSE event formatting helpers |

**Total: 11 new files**

---

## Changes to Existing Files

| File | Change Description |
|------|-------------------|
| (none) | No existing files were modified |

---

## Dependencies Added

```
boto3>=1.34.0
botocore>=1.34.0
fastapi>=0.109.0
uvicorn>=0.27.0
sse-starlette>=1.6.0
pydantic>=2.0.0
```

**Note**: NO ML dependencies (xgboost, sklearn, numpy) - reports are pre-cached in DynamoDB.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check for Lambda Web Adapter |
| GET | `/report/{ticker}` | Stream cached report as SSE events |
| POST | `/followup` | Follow-up questions (STUB for Phase 4) |

---

## SSE Event Flow

```
1. connected    → {"type": "connected", "timestamp": "..."}
2. rating (x3)  → {"type": "rating", "domain": "debt|cashflow|growth", ...}
3. report       → {"type": "report", "content": "...", "metadata": {...}}
4. complete     → {"type": "complete", "ticker": "AAPL", "fiscal_year": 2024}
```

---

## Testing Results

- [x] Docker build: PASS
- [x] Import test: PASS
- [x] Health endpoint: PASS
- [ ] Report streaming: NOT TESTED (requires AWS credentials + cached reports)

### Test Commands Used

```bash
# Build
docker build --platform linux/amd64 -t investment-research:v1.0.0 .

# Test imports
docker run --rm -e AWS_DEFAULT_REGION=us-east-1 -e ENVIRONMENT=dev \
  investment-research:v1.0.0 python -c "
from services.report_service import get_cached_report
from services.streaming import connected_event
import app
print('All imports successful!')
"

# Test health endpoint
docker run --rm -d --name ir-test -p 8080:8080 \
  -e AWS_DEFAULT_REGION=us-east-1 -e ENVIRONMENT=dev \
  investment-research:v1.0.0
curl http://localhost:8080/health
docker stop ir-test
```

---

## Architecture Decisions

### 1. Lightweight Copy over Layer Import
- Created standalone DynamoDB retrieval logic instead of importing from `investment_research.report_generator`
- Rationale: Simpler Lambda, no layer dependencies, faster cold starts

### 2. Docker + LWA over Zip-based
- SSE streaming requires HTTP response streaming (LWA provides this)
- Consistent UX with existing "Buffett" mode (prediction_ensemble)
- Trade-off: ~2-5s cold starts vs ~500ms for zip-based

### 3. Stub Follow-up Endpoint
- `/followup` returns placeholder response
- Phase 4 will integrate with Bedrock agent + action group

---

## Key Differences from prediction_ensemble

| Aspect | prediction_ensemble | investment_research |
|--------|---------------------|---------------------|
| ML Dependencies | xgboost, sklearn, numpy | None |
| System Deps | gcc, g++ | None |
| Image Size | ~500MB+ | ~200MB |
| FMP Client | Yes | No (reports pre-cached) |
| Bedrock Agents | Multi-agent orchestration | Stub (Phase 4) |
| Endpoints | /supervisor, /analyze | /report/{ticker}, /followup |

---

## Next Steps (Phase 4-6)

1. **Phase 4**: Implement Bedrock follow-up agent + action group Lambda
2. **Phase 5**: Frontend mode dropdown + SSE handling
3. **Phase 6**: Terraform for ECR, Lambda, Function URL

---

## Deployment Notes

Before deploying to AWS:
1. Push Docker image to ECR
2. Create Terraform configuration for Lambda + Function URL
3. Ensure DynamoDB table `investment-reports-{env}` exists with cached reports
4. Configure IAM permissions for DynamoDB access

---

## Issues Encountered

None - implementation proceeded as planned.

---

## Reviewer Notes

- All files follow existing patterns from prediction_ensemble
- Code is well-documented with docstrings
- SSE event format matches frontend expectations from Phase 5 spec
- Direct invocation handler provides fallback for non-streaming use cases
