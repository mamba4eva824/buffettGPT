# Ensemble Prediction Models & Inference Pipeline

## Overview

This document summarizes the implementation of the 3-model ensemble system for Deep Value Analysis, including the inference pipeline and frontend integration.

## Architecture

```
User Input ("Apple")
       │
       ▼
┌──────────────────┐
│  Frontend        │  App.jsx with 3 modes: Search, Buffett Agent, Deep Value
│  (React)         │  BubbleTabs, AnalysisView, StreamingText, FollowUpChat
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Lambda Handler  │  ensemble_analyzer.py
│  (Python)        │  analysis_followup.py
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│ FMP    │ │ DynamoDB   │  90-day cache with ticker GSI
│ API    │ │ Cache      │
└────────┘ └────────────┘
         │
         ▼
┌──────────────────┐
│ Feature Extract  │  163 features (58 debt + 42 cashflow + 63 growth)
│ (v3.6.5)         │
└────────┬─────────┘
         │
    ┌────┼────┬────┐
    ▼    ▼    ▼    ▼
┌──────┐┌──────┐┌──────┐
│Debt  ││Cash  ││Growth│  XGBoost models with probability-based CI
│Model ││Model ││Model │
└──┬───┘└──┬───┘└──┬───┘
   │       │       │
   ▼       ▼       ▼
┌──────────────────────┐
│  Bedrock Agents      │  Claude 3.5 Haiku with layman-style prompts
│  (3 Expert Personas) │
└──────────┬───────────┘
           │
           ▼
    Streaming SSE Response
```

## Components Implemented

### 1. Infrastructure (Terraform)

| Component | File | Description |
|-----------|------|-------------|
| DynamoDB GSI | `chat-api/terraform/modules/dynamodb/ml_tables.tf` | Added `ticker-index` for querying by company |
| FMP Secret | `chat-api/terraform/modules/lambda/secrets.tf` | Data source for `buffett-dev-fmp` secret |
| Model Variable | `chat-api/terraform/environments/dev/variables.tf` | Claude 3.5 Haiku (4.5 not compatible with KB prompts) |

### 2. Backend Utilities

| File | Purpose |
|------|---------|
| `chat-api/backend/src/utils/fmp_client.py` | FMP API client with DynamoDB caching |
| `chat-api/backend/src/utils/feature_extractor.py` | Extracts 163 features from financial data |

**FMP Client Features:**
- Fetches 5 years / 20 quarters of financial data
- Caches in DynamoDB with 90-day TTL
- Validates cache format (rejects old format data)
- Normalizes company names to tickers

**Feature Extractor Metrics:**
- Debt: debt_to_equity, interest_coverage, current_ratio, net_debt_to_ebitda
- Cashflow: fcf_margin, ocf_to_revenue, capex_intensity, shareholder_returns_pct
- Growth: revenue_growth_yoy, operating_margin, is_growth_accelerating

### 3. Lambda Handlers

| File | Purpose |
|------|---------|
| `chat-api/backend/src/handlers/ensemble_analyzer.py` | Main analysis handler with SSE streaming |
| `chat-api/backend/src/handlers/analysis_followup.py` | Follow-up questions with session memory |

**Ensemble Analyzer Flow:**
1. Normalize company input to ticker
2. Check DynamoDB cache (or fetch from FMP)
3. Extract features
4. Run XGBoost inference with probability-based CI
5. Stream Bedrock agent response via SSE

**Follow-Up Handler:**
- Uses same `sessionId` to maintain conversation context
- Routes to appropriate agent (debt/cashflow/growth)
- Supports streaming responses

### 4. Bedrock Agent Prompts

| File | Persona |
|------|---------|
| `prompts/debt_expert_instruction.txt` | Conservative, risk-focused, warns about leverage |
| `prompts/cashflow_expert_instruction.txt` | Practical, cash-focused, "follow the money" |
| `prompts/growth_expert_instruction.txt` | Forward-looking, focuses on acceleration |

**Prompt Features:**
- Layman-friendly language (based on AAPL_ANALYSIS_LAYMAN_TERMS.md)
- Confidence-based language adjustment (STRONG/MODERATE/WEAK)
- Specific number citations from key metrics
- Emoji usage for signals (red/yellow/green circles)

### 5. Frontend Components

| File | Purpose |
|------|---------|
| `frontend/src/components/analysis/BubbleTabs.jsx` | Safari/iOS 26-style pill tabs |
| `frontend/src/components/analysis/AnalysisView.jsx` | Main container with streaming |
| `frontend/src/components/analysis/StreamingText.jsx` | Real-time markdown display |
| `frontend/src/components/analysis/FollowUpChat.jsx` | Follow-up question UI |

**App.jsx Changes:**
- Added 3rd mode: `analysis` (alongside `search` and `bedrock`)
- Added `BarChart3` icon for analysis mode button
- Added `showAnalysis` and `analysisTicker` state
- Renders `AnalysisView` when analysis mode active

## Confidence Interval Calculation

```python
# XGBoost returns probabilities for each class
probs = model.predict_proba(features)[0]  # [0.69, 0.22, 0.09]

# Prediction = class with highest probability
prediction = ["SELL", "HOLD", "BUY"][probs.argmax()]  # "SELL"

# Confidence = max probability
confidence = probs.max()  # 0.69 (69%)

# CI Width = 1 - gap between top two probabilities
ci_width = 1.0 - (probs[0] - probs[1])  # 1.0 - 0.47 = 0.53

# Interpretation
if confidence >= 0.7 and ci_width <= 0.3:
    interpretation = "STRONG"      # "strongly suggests"
elif confidence >= 0.5:
    interpretation = "MODERATE"    # "suggests"
else:
    interpretation = "WEAK"        # "may indicate"
```

## Testing

Integration tests validated (5/5 passed):
1. FMP Secret Access - Retrieved 32-character API key
2. DynamoDB Table - Both GSIs present (ticker-index, cached-at-index)
3. FMP API Fetch - 20 quarters of each statement type
4. Feature Extraction - Real metrics calculated (AAPL: D/E 1.34, FCF 25.8%)
5. DynamoDB Caching - Write-through + read-through working

Test file: `chat-api/backend/tests/test_fmp_integration.py`

## Environment Variables

```bash
# Lambda
FMP_SECRET_NAME=buffett-dev-fmp
FINANCIAL_DATA_CACHE_TABLE=buffett-dev-financial-data-cache
MODEL_S3_BUCKET=buffett-models
MODEL_S3_PREFIX=ensemble/v1
DEBT_AGENT_ID=xxx
DEBT_AGENT_ALIAS=xxx
CASHFLOW_AGENT_ID=xxx
CASHFLOW_AGENT_ALIAS=xxx
GROWTH_AGENT_ID=xxx
GROWTH_AGENT_ALIAS=xxx

# Frontend
VITE_ANALYSIS_API_URL=https://xxx.lambda-url.us-east-1.on.aws/
VITE_FOLLOWUP_API_URL=https://xxx.lambda-url.us-east-1.on.aws/
```

## Next Steps

1. **Upload XGBoost models to S3** (`ensemble/v1/` prefix)
2. **Configure 3 Bedrock agents** with expert prompts
3. **Deploy Lambda handlers** via Terraform
4. **Add environment variables** for agent IDs/aliases
5. **Test end-to-end** with real company analysis

## Files Modified/Created

### Modified
- `chat-api/terraform/modules/dynamodb/ml_tables.tf` - Added ticker GSI
- `chat-api/terraform/modules/lambda/secrets.tf` - Added FMP secret data source
- `chat-api/terraform/modules/lambda/outputs.tf` - Added FMP secret outputs
- `chat-api/terraform/environments/dev/variables.tf` - Model configuration
- `frontend/src/App.jsx` - Added analysis mode

### Created
- `chat-api/backend/src/utils/fmp_client.py`
- `chat-api/backend/src/utils/feature_extractor.py`
- `chat-api/backend/src/handlers/ensemble_analyzer.py`
- `chat-api/backend/src/handlers/analysis_followup.py`
- `chat-api/backend/tests/test_fmp_integration.py`
- `chat-api/terraform/modules/bedrock/prompts/debt_expert_instruction.txt`
- `chat-api/terraform/modules/bedrock/prompts/cashflow_expert_instruction.txt`
- `chat-api/terraform/modules/bedrock/prompts/growth_expert_instruction.txt`
- `frontend/src/components/analysis/BubbleTabs.jsx`
- `frontend/src/components/analysis/AnalysisView.jsx`
- `frontend/src/components/analysis/StreamingText.jsx`
- `frontend/src/components/analysis/FollowUpChat.jsx`

### Archived
- `chat-api/terraform/modules/bedrock/prompts/archive/debt_analyst_instruction.txt`
