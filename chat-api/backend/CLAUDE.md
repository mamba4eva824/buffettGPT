# Backend - Lambda & Docker Rules

## 🏗️ Agent Architecture

Two live agents, both using **Bedrock Runtime** (`converse_stream`) with inline `tools`:

| Agent | Handler | API | Tools |
|-------|---------|-----|-------|
| **Follow-up Q&A** | `src/handlers/analysis_followup.py` | `bedrock_runtime.converse_stream` | 6 inline tools (getReportSection, getReportRatings, getMetricsHistory, getAvailableReports, compareStocks, getFinancialSnapshot) |
| **Market Intelligence** | `src/handlers/market_intel_chat.py` | `bedrock_runtime.converse_stream` | 9 inline tools (screenStocks, getSectorOverview, getTopCompanies, etc.) |

Tool dispatch is unified in `src/utils/unified_tool_executor.py` — both agents share the same `execute_tool(tool_name, tool_input)` entry point.

**Deprecated patterns (do not reintroduce):**
- Bedrock **Agents** (`bedrock-agent-runtime.invoke_agent`) with **action groups** — removed 2025-01 (expert agents) and 2026-05 (follow-up agent).
- Docker action-group Lambdas (e.g. `followup-action`, `prediction-ensemble`) — removed alongside their Bedrock Agents.

When adding a new tool, extend `unified_tool_executor.py` and the agent's `*_TOOLS` schema array. Do **not** create a Bedrock Agent or action group.

---

## 📦 Lambda Packaging

All Lambda deployment packages (.zip files) MUST be placed in:
```
build/
```

### Build Requirements
1. All .zip files go to `build/`
2. Maintain consistent packaging format
3. Include all required dependencies
4. Remove old builds before creating new ones

## 🐳 Docker Image Testing (Prediction Ensemble)

### Platform Architecture
AWS Lambda runs on x86_64 (amd64). On Apple Silicon:
```bash
docker build --platform linux/amd64 -t <image>:<tag> .
```

### Required Testing Before ECR Push
```bash
# 1. Build
docker build --platform linux/amd64 -t prediction-ensemble:vX.X .

# 2. Test imports
docker run --rm \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e ENVIRONMENT=dev \
  prediction-ensemble:vX.X python -c "
from services.inference import run_inference
from handlers.action_group import handle_action_group_request
import app
print('All imports successful!')
"

# 3. Test health endpoint
docker run --rm -d --name test -p 8080:8080 \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e ENVIRONMENT=dev \
  prediction-ensemble:vX.X
sleep 3
curl http://localhost:8080/health
docker stop test

# 4. Only then push to ECR
```

## 🔐 AWS Configuration

| Setting | Value |
|---------|-------|
| **AWS Account** | `430118826061` |
| **AWS Profile** | `default` (website-admin) |
| **Region** | `us-east-1` |
| **ECR Repository** | `430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble` |

### ECR Push Commands
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 430118826061.dkr.ecr.us-east-1.amazonaws.com

# Tag and push
docker tag prediction-ensemble:vX.X 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble:vX.X
docker push 430118826061.dkr.ecr.us-east-1.amazonaws.com/buffett/prediction-ensemble:vX.X
```
