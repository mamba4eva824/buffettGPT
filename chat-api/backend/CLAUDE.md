# Backend - Lambda & Docker Rules

## 🏗️ Supervisor Agent Architecture

### Agent Types & APIs

| Agent | API | Prompt Location | Streaming | Action Groups |
|-------|-----|-----------------|-----------|---------------|
| **Expert Agents** (debt, cashflow, growth) | `invoke_agent()` | Terraform `.txt` files | No (full response → supervisor) | Yes |
| **Supervisor** | `converse_stream()` | `orchestrator.py:520-640` | Yes (token → frontend) | No |

- **Expert agents** use `invoke_agent()` (bedrock-agent-runtime) which supports action groups
- **Supervisor** uses `converse_stream()` (bedrock-runtime) for true token streaming but no action groups

### Inference Flow (Hybrid Mode)

```
Stage 1: Connection
Stage 2: orchestrator.py → fetch_and_run_inference()
         └─ Runs ML inference for all 3 models (debt, cashflow, growth)
         └─ Emits inference events to frontend bubbles

Stage 3: Expert Agents (parallel via asyncio.gather)
         └─ User message includes pre-computed inference
         └─ Agents call action group with skip_inference=true
         └─ Action group returns value_metrics only (no duplicate inference)

Stage 4: Supervisor (streaming)
         └─ Receives 3 expert analyses
         └─ Synthesizes into final verdict
         └─ Streams tokens to frontend
```

### Feature Flag: USE_ACTION_GROUP_MODE

| Mode | Inference Source | Metrics Source |
|------|------------------|----------------|
| `true` (hybrid) | Orchestrator Stage 2 → passed in prompt | Action group (skip_inference=true) |
| `false` (pre-computed) | Orchestrator Stage 2 → passed in prompt | Passed in prompt (no action group call) |

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
