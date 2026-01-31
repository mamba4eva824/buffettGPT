# Prediction Ensemble (Archived)

**Archived Date:** January 2025
**Reason:** Not under active development; replaced by investment research reports for detailed analysis

## What This Was

A multi-agent ML stock prediction system providing buy/hold/sell recommendations using Warren Buffett's value investing principles.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PREDICTION ENSEMBLE                          │
└─────────────────────────────────────────────────────────────────┘

                         ┌──────────────┐
                         │   Frontend   │
                         └──────┬───────┘
                                │
                    POST /analysis/{agent_type}
                                │
                         ┌──────▼───────┐
                         │  API Gateway │ (JWT Auth)
                         └──────┬───────┘
                                │
              ┌─────────────────▼─────────────────┐
              │   Prediction Ensemble Lambda      │
              │   (Docker, FastAPI, LWA)          │
              │   - SSE Streaming                 │
              │   - Multi-agent orchestration     │
              └─────────────────┬─────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
┌───────▼───────┐       ┌───────▼───────┐       ┌───────▼───────┐
│ Debt Expert   │       │ Cashflow Expert│      │ Growth Expert │
│ Agent         │       │ Agent          │      │ Agent         │
│ (Bedrock)     │       │ (Bedrock)      │      │ (Bedrock)     │
└───────┬───────┘       └───────┬───────┘       └───────┬───────┘
        │                       │                       │
        └───────────────────────┼───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Action Group Lambda  │
                    │  (Data Fetcher)       │
                    │  - FMP API calls      │
                    │  - XGBoost inference  │
                    └───────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Supervisor Agent    │
                    │   (Synthesizes)       │
                    │   → Final Verdict     │
                    └───────────────────────┘
```

### Components

| Component | Description |
|-----------|-------------|
| **3 Expert Agents** | Debt, Cashflow, Growth analysis using Claude Haiku 4.5 + XGBoost ML |
| **Supervisor Agent** | Synthesizes expert opinions into final buy/hold/sell recommendation |
| **Action Group Lambda** | Fetches financial data from FMP API, runs ML inference |
| **Docker Lambda** | FastAPI + Lambda Web Adapter for SSE streaming |

### ML Models

- **Location:** S3 bucket `buffett-{env}-models/ensemble/v1/`
- **Models:** XGBoost classifiers for debt, cashflow, and growth analysis
- **Features:** 60+ financial metrics extracted from FMP API data

## Directory Structure

```
archived/prediction_ensemble/
├── lambda/                    # Main Lambda code (Docker, FastAPI)
│   ├── app.py                 # FastAPI application
│   ├── handler.py             # Lambda handler
│   ├── Dockerfile
│   ├── config/                # Settings
│   ├── handlers/              # Analysis, supervisor handlers
│   ├── models/                # Schemas, metrics definitions
│   ├── services/              # Orchestrator, inference, bedrock
│   └── utils/                 # Feature extraction, FMP client
├── local_testing/             # CLI tools for local development
├── docs/                      # Architecture documentation
├── tests/                     # Test files
├── utils/                     # Shared utilities
├── legacy/                    # Previously archived code
└── terraform/                 # Infrastructure configs
    ├── lambda/                # Lambda TF configs
    │   ├── prediction_ensemble_docker.tf
    │   └── data_fetcher_action.tf
    ├── bedrock/
    │   ├── prompts/           # Value investor agent prompts
    │   └── schemas/           # Action group API schemas
    └── s3/                    # S3 models bucket config
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```

## To Revive This Feature

1. **Move Terraform files back:**
   ```bash
   # Lambda configs
   mv archived/prediction_ensemble/terraform/lambda/*.tf chat-api/terraform/modules/lambda/

   # Bedrock prompts and schemas
   mv archived/prediction_ensemble/terraform/bedrock/prompts/* chat-api/terraform/modules/bedrock/prompts/
   mv archived/prediction_ensemble/terraform/bedrock/schemas/* chat-api/terraform/modules/bedrock/schemas/

   # S3 models bucket module
   mkdir -p chat-api/terraform/modules/s3
   mv archived/prediction_ensemble/terraform/s3/*.tf chat-api/terraform/modules/s3/
   ```

2. **Move Lambda code back:**
   ```bash
   mv archived/prediction_ensemble/lambda chat-api/backend/lambda/prediction_ensemble
   mv archived/prediction_ensemble/local_testing chat-api/backend/prediction_ensemble_local
   ```

3. **Restore Terraform module references:**
   - Add S3 module back to `environments/dev/main.tf`
   - Add expert agent modules back to `modules/bedrock/main.tf`
   - Add action group variables back to `modules/bedrock/variables.tf`
   - Add API Gateway `/analysis/*` routes back to `modules/api-gateway/analysis_streaming.tf`
   - Add prediction_ensemble variables back to `modules/api-gateway/variables.tf`
   - Add ML layer and model_s3_bucket back to `modules/lambda/main.tf` and `variables.tf`
   - Re-add idempotency-cache table to `modules/dynamodb/ml_tables.tf`
   - Update `environments/dev/main.tf` with ensemble configuration

4. **Deploy:**
   ```bash
   cd chat-api/terraform/environments/dev
   terraform init
   terraform plan -out=tfplan
   terraform apply tfplan
   ```

5. **Push Docker image:**
   ```bash
   # Build and push to ECR
   docker build -t prediction-ensemble:v2.4.6 .
   aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_URL
   docker tag prediction-ensemble:v2.4.6 $ECR_URL/buffett/prediction-ensemble:v2.4.6
   docker push $ECR_URL/buffett/prediction-ensemble:v2.4.6
   ```

## Archived AWS Resources

These resources were archived along with the prediction ensemble:

- **S3 Models Bucket:** `buffett-{env}-models` - contained ML models and layer packages
  - `ensemble/v1/` - XGBoost models for debt, cashflow, growth analysis
  - `layers/ml-layer.zip` - ML dependencies layer (~60MB)
- **Lambda Layer:** `ml_dependencies_layer` - numpy, scikit-learn, xgboost, scipy
- **DynamoDB Table:** `idempotency-cache` - request deduplication for ML agents (24h TTL)

## Related Resources (Still Active)

These resources were kept active as they are used by investment research:

- **DynamoDB Cache Tables:** `financial-data-cache`, `ticker-lookup`, `forex-cache`, `metrics-history-cache`

## Version History

- **v2.4.6** (Final): Fixed race condition - cache verification before agent invocation
- **v2.4.5**: Improved confidence interval calculations
- **v2.4.0**: Added supervisor agent synthesis
- **v2.0.0**: Multi-agent architecture with expert agents
- **v1.0.0**: Initial single-agent implementation
