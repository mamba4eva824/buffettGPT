# Two-Lambda Architecture: Executive Review

**Date:** December 15, 2025
**Status:** Production Ready
**Environment:** Dev (buffett-dev)

---

## Executive Summary

This document provides an executive overview of the Two-Lambda Architecture solution that resolved a critical compatibility issue between AWS Bedrock Action Groups and Lambda Web Adapter (LWA) + FastAPI. The solution positions **Bedrock as the intelligent bridge** between the frontend and ML-powered financial analysis, enabling expert agents to deliver value investor insights.

### Key Outcomes

| Metric | Result |
|--------|--------|
| Problem Resolution | 100% - `dependencyFailedException` eliminated |
| ML Inference | Fully operational with XGBoost models |
| Response Time | 50-400ms per action group invocation |
| Expert Agent Coverage | 3 agents (Debt, Cashflow, Growth) |
| Data Coverage | 20 quarters (5 years) of financial metrics |

---

## Problem Statement

### The Issue

AWS Bedrock Action Groups require a **specific response format** with an exact `"application/json"` key in the response body. Lambda Web Adapter (LWA) combined with FastAPI automatically produces `"application/json; charset=utf-8"` as the Content-Type, which Bedrock cannot parse.

### Error Manifestation

```
dependencyFailedException:
The server encountered an error processing the Lambda response.
The response body from Bedrock agent must be of type 'application/json',
but 'null' was returned.
```

### Root Cause Analysis

```
Expected by Bedrock:    "application/json"
Returned by LWA:        "application/json; charset=utf-8"
                                          ^^^^^^^^^^^^^^^
                                          This suffix breaks Bedrock
```

---

## Proposed Solution: Bedrock as the Bridge

### Architecture Overview

The solution positions **AWS Bedrock as the intelligent orchestration layer** between the user-facing frontend and the backend ML infrastructure. Bedrock agents interpret user requests, coordinate expert analysis, and synthesize comprehensive investment insights.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              END-TO-END ARCHITECTURE                                 │
│                          "Bedrock as the Bridge"                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────┐
                                    │   USER      │
                                    │  Frontend   │
                                    │  (React)    │
                                    └──────┬──────┘
                                           │
                                           │ "Analyze Tesla"
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                         AWS BEDROCK - THE BRIDGE                                    │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────────┐ │
│  │                         SUPERVISOR AGENT                                       │ │
│  │                      (Claude Haiku 4.5)                                        │ │
│  │                                                                                │ │
│  │  • Receives user analysis request                                             │ │
│  │  • Orchestrates parallel expert invocations                                   │ │
│  │  • Synthesizes final investment recommendation                                │ │
│  │  • Grounds insights in Buffett's principles (Knowledge Base)                  │ │
│  └───────────────────────────────────────────────────────────────────────────────┘ │
│                                           │                                         │
│              ┌────────────────────────────┼────────────────────────────┐           │
│              │                            │                            │           │
│              ▼                            ▼                            ▼           │
│  ┌───────────────────┐     ┌───────────────────┐     ┌───────────────────┐        │
│  │   DEBT EXPERT     │     │  CASHFLOW EXPERT  │     │  GROWTH EXPERT    │        │
│  │   (Haiku 3.5)     │     │    (Haiku 3.5)    │     │   (Haiku 3.5)     │        │
│  │                   │     │                   │     │                   │        │
│  │ • Leverage ratios │     │ • FCF analysis    │     │ • Revenue growth  │        │
│  │ • Interest cover  │     │ • Cash efficiency │     │ • Margin trends   │        │
│  │ • Debt trends     │     │ • Shareholder     │     │ • EPS trajectory  │        │
│  │                   │     │   returns         │     │                   │        │
│  └─────────┬─────────┘     └─────────┬─────────┘     └─────────┬─────────┘        │
│            │                         │                         │                   │
│            │    ┌────────────────────┴────────────────────┐    │                   │
│            │    │      FINANCIAL ANALYSIS ACTION GROUP    │    │                   │
│            └────►          (Shared by all experts)        ◄────┘                   │
│                 │    ticker + analysis_type → ML insights │                        │
│                 └────────────────────┬────────────────────┘                        │
│                                      │                                              │
└──────────────────────────────────────┼──────────────────────────────────────────────┘
                                       │
                                       │ Bedrock Action Group Invocation
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                                                                                     │
│                    DATA FETCHER LAMBDA (Pure Python)                                │
│                    buffett-dev-ensemble-prediction-data-fetcher-action              │
│                                                                                     │
│  ┌───────────────────────────────────────────────────────────────────────────────┐ │
│  │                                                                               │ │
│  │   1. Parse Bedrock action group event (ticker, analysis_type)                │ │
│  │   2. Fetch 20 quarters of financial data (DynamoDB cache / FMP API)          │ │
│  │   3. Extract 40+ features per analysis type                                  │ │
│  │   4. Run XGBoost ML inference → BUY / HOLD / SELL                           │ │
│  │   5. Return Bedrock-compliant response with exact "application/json" key     │ │
│  │                                                                               │ │
│  └───────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                     │
│  Layers: dependencies-layer + ml-layer (numpy, sklearn 1.3.x, xgboost, scipy)      │
│                                                                                     │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
          ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
          │    DynamoDB     │ │    FMP API      │ │   S3 Models     │
          │    Cache        │ │   (Fallback)    │ │   (XGBoost)     │
          │                 │ │                 │ │                 │
          │ financial-data  │ │ Balance Sheet   │ │ debt_model.pkl  │
          │ ticker-lookup   │ │ Income Stmt     │ │ cashflow_model  │
          │ (24hr TTL)      │ │ Cash Flow       │ │ growth_model    │
          └─────────────────┘ └─────────────────┘ └─────────────────┘
```

---

## Key Connection Flow

The following diagram illustrates the data flow from user request to ML-powered response:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           KEY CONNECTION FLOW                                        │
└─────────────────────────────────────────────────────────────────────────────────────┘

  USER REQUEST                    BEDROCK ORCHESTRATION                 LAMBDA + ML
  ───────────                     ─────────────────────                 ───────────

  ┌──────────────┐
  │ "Analyze     │
  │  Tesla as a  │
  │  value       │
  │  investment" │
  └──────┬───────┘
         │
         │  (1) HTTP Request
         ▼
  ┌──────────────┐
  │  Frontend    │
  │  React App   │
  └──────┬───────┘
         │
         │  (2) API Gateway → Lambda
         ▼
  ┌──────────────┐                ┌──────────────────────────────────────────────────┐
  │  Chat HTTP   │                │                                                  │
  │  Handler     │───────────────►│              SUPERVISOR AGENT                    │
  └──────────────┘   (3) Invoke   │                                                  │
                     Bedrock      │  "I need to analyze TSLA. Let me consult my     │
                     Agent        │   three expert analysts..."                      │
                                  │                                                  │
                                  └──────────────────┬───────────────────────────────┘
                                                     │
                                    (4) Parallel Expert Invocations
                                                     │
                        ┌────────────────────────────┼────────────────────────────┐
                        │                            │                            │
                        ▼                            ▼                            ▼
                 ┌─────────────┐             ┌─────────────┐             ┌─────────────┐
                 │   DEBT      │             │  CASHFLOW   │             │   GROWTH    │
                 │   EXPERT    │             │   EXPERT    │             │   EXPERT    │
                 └──────┬──────┘             └──────┬──────┘             └──────┬──────┘
                        │                           │                           │
                        │ (5) Action Group          │                           │
                        │     Invocation            │                           │
                        ▼                           ▼                           ▼
                 ┌─────────────────────────────────────────────────────────────────┐
                 │                                                                 │
                 │              DATA FETCHER LAMBDA                                │
                 │                                                                 │
                 │  Input:  { ticker: "TSLA", analysis_type: "debt" }             │
                 │                                                                 │
                 │  Processing:                                                    │
                 │  ├── Check DynamoDB cache → HIT (TSLA:2025)                    │
                 │  ├── Extract 41 debt features from 20 quarters                 │
                 │  ├── Load debt_model.pkl from S3                               │
                 │  └── XGBoost predict → SELL (46% confidence)                   │
                 │                                                                 │
                 │  Output: {                                                      │
                 │    "messageVersion": "1.0",                                    │
                 │    "response": {                                               │
                 │      "responseBody": {                                         │
                 │        "application/json": {    ◄── EXACT KEY (critical!)      │
                 │          "body": "{\"prediction\":\"SELL\",...}"              │
                 │        }                                                       │
                 │      }                                                         │
                 │    }                                                           │
                 │  }                                                              │
                 │                                                                 │
                 └─────────────────────────────────────────────────────────────────┘
                        │                           │                           │
                        │ (6) ML Results            │                           │
                        ▼                           ▼                           ▼
                 ┌─────────────┐             ┌─────────────┐             ┌─────────────┐
                 │   DEBT      │             │  CASHFLOW   │             │   GROWTH    │
                 │   EXPERT    │             │   EXPERT    │             │   EXPERT    │
                 │             │             │             │             │             │
                 │ "Based on   │             │ "Strong FCF │             │ "Revenue    │
                 │  D/E of     │             │  margin of  │             │  growing    │
                 │  0.17..."   │             │  14.2%..."  │             │  11.6%..."  │
                 └──────┬──────┘             └──────┬──────┘             └──────┬──────┘
                        │                           │                           │
                        └────────────────────────────┼────────────────────────────┘
                                                     │
                                    (7) Expert Analyses
                                                     ▼
                                  ┌──────────────────────────────────────────────────┐
                                  │              SUPERVISOR AGENT                    │
                                  │                                                  │
                                  │  "Synthesizing expert analyses..."               │
                                  │                                                  │
                                  │  Debt Expert:     SELL (46%) - Weak confidence  │
                                  │  Cashflow Expert: BUY  (85%) - Strong confidence│
                                  │  Growth Expert:   BUY  (71%) - Weak confidence  │
                                  │                                                  │
                                  │  "From a Buffett perspective, while the debt    │
                                  │   metrics raise caution flags, the exceptional  │
                                  │   cash flow generation demonstrates the         │
                                  │   'owner earnings' quality Buffett prizes..."   │
                                  │                                                  │
                                  └──────────────────┬───────────────────────────────┘
                                                     │
                                    (8) Synthesized Response
                                                     ▼
                                           ┌─────────────────┐
                                           │    FRONTEND     │
                                           │                 │
                                           │  Debt Analysis  │
                                           │  ─────────────  │
                                           │  D/E: 0.17      │
                                           │  Prediction:    │
                                           │    SELL (46%)   │
                                           │                 │
                                           │  Cashflow...    │
                                           │  Growth...      │
                                           └─────────────────┘
```

---

## Why Two Lambdas?

| Aspect | Prediction Ensemble (Existing) | Data Fetcher (New) |
|--------|-------------------------------|-------------------|
| **Purpose** | HTTP streaming for frontend | Bedrock action groups |
| **Runtime** | Docker + LWA + FastAPI | Pure Python handler |
| **Response** | SSE streaming | Synchronous JSON |
| **Content-Type** | `application/json; charset=utf-8` | Exact `application/json` key |
| **Invocation** | API Gateway HTTP | Bedrock agent |

### The Critical Difference

```
┌─────────────────────────────────────────────────────────────────┐
│                    RESPONSE FORMAT COMPARISON                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PREDICTION ENSEMBLE (LWA + FastAPI)         ❌ BREAKS BEDROCK │
│  ────────────────────────────────────                          │
│  HTTP Response:                                                │
│  {                                                             │
│    "headers": {                                                │
│      "content-type": "application/json; charset=utf-8"         │
│    },                             ▲                            │
│    "body": {...}                  │                            │
│  }                                │                            │
│                                   │                            │
│                    This charset suffix breaks Bedrock's        │
│                    strict key matching!                        │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  DATA FETCHER (Pure Python)                  ✅ WORKS          │
│  ──────────────────────────                                    │
│  Bedrock Response:                                             │
│  {                                                             │
│    "messageVersion": "1.0",                                    │
│    "response": {                                               │
│      "responseBody": {                                         │
│        "application/json": {     ◄── Exact key match!         │
│          "body": "{...}"         ◄── JSON string, not object  │
│        }                                                       │
│      }                                                         │
│    }                                                           │
│  }                                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Results

### Successful Test Output (TSLA)

| Expert | Prediction | Confidence | Interpretation |
|--------|------------|------------|----------------|
| **Debt** | SELL | 46% | WEAK |
| **Cashflow** | BUY | 85% | STRONG |
| **Growth** | BUY | 71% | WEAK |

### Value Metrics Delivered to Experts

**Debt Metrics:** debt_to_equity, interest_coverage, current_ratio, quick_ratio, net_debt, net_debt_to_ebitda, debt_to_equity_trend_2yr, is_deleveraging

**Cashflow Metrics:** operating_cash_flow, free_cash_flow, fcf_margin, ocf_to_revenue, capex_intensity, fcf_margin_trend_1yr, dividend_payout, share_buybacks

**Growth Metrics:** roe, roic, gross_margin, operating_margin, net_margin, revenue_growth_yoy, eps_growth_yoy, revenue_cagr_2yr

### Performance Metrics

| Metric | Value |
|--------|-------|
| Cold Start | ~2 seconds |
| Warm Invocation | 50-400ms |
| DynamoDB Cache Hit Rate | High (24hr TTL) |
| Memory Used | ~245 MB (of 1024 MB) |

---

## Infrastructure Summary

### Terraform Resources

| Resource | Name |
|----------|------|
| Lambda Function | `buffett-dev-ensemble-prediction-data-fetcher-action` |
| IAM Role | `buffett-dev-data-fetcher-action-role` |
| CloudWatch Logs | `/aws/lambda/buffett-dev-ensemble-prediction-data-fetcher-action` |
| ML Layer | `buffett-dev-ml-dependencies` (v4, 60MB via S3) |

### Action Group Wiring

All three expert agents share the same Lambda via the `FinancialAnalysis` action group:

```
debt_expert_agent    ──┐
                      ├──► FinancialAnalysis ──► data-fetcher-action Lambda
cashflow_expert_agent ──┤       Action Group
                      │
growth_expert_agent  ──┘
```

---

## Lessons Learned

1. **Bedrock Response Format is Strict** - The `"application/json"` key must be exact. Body must be a JSON string.

2. **Layer Size Considerations** - ML dependencies exceed 50MB. Use S3 for layer upload.

3. **Version Compatibility** - Pin sklearn to `<1.4.0` to match trained models.

4. **Reuse Over Rewrite** - The data fetcher reuses existing code (inference, FMP client, feature extractor).

---

## Conclusion

The Two-Lambda Architecture successfully positions **Bedrock as the intelligent bridge** between the frontend and ML-powered analysis:

- **Supervisor Agent** orchestrates the analysis flow and synthesizes insights
- **Expert Agents** provide specialized domain analysis with ML predictions
- **Data Fetcher Lambda** delivers Bedrock-compliant responses with exact formatting
- **Existing Infrastructure** remains untouched for HTTP streaming use cases

The solution enables sophisticated value investor analysis powered by XGBoost ML models, delivered through Bedrock's conversational AI capabilities.

---

## Appendix: File Locations

| Component | Path |
|-----------|------|
| Lambda Handler | `backend/src/handlers/action_group_handler.py` |
| Inference Service | `backend/src/services/inference.py` |
| Feature Extractor | `backend/src/utils/feature_extractor.py` |
| FMP Client | `backend/src/utils/fmp_client.py` |
| Terraform Config | `terraform/modules/lambda/data_fetcher_action.tf` |
| Action Group Schema | `terraform/modules/bedrock/schemas/value_investor_action.yaml` |
| ML Layer Requirements | `backend/layer/requirements-ml.txt` |

---

*Document generated: December 15, 2025*
