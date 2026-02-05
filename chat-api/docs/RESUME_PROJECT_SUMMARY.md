# Deep Value Insights - Resume Project Summary

> **Project Duration**: September 2025 - Present
> **Role**: Full-Stack AI/ML Engineer
> **Repository**: Private

---

## Project Title Options

- **Deep Value Insights** - AI-Powered Investment Research Platform
- **Investment Research Engine** - Multi-Agent AI Analysis System

---

## Resume Bullet Points

### Technical Implementation (pick 3-4)

**Multi-Agent AI Orchestration**
> Architected multi-agent AI system using AWS Bedrock with 4 Claude Haiku agents (debt, cashflow, growth experts + supervisor), orchestrating parallel analysis with real-time SSE streaming to React frontend

**ML-Driven Investment Analysis**
> Built XGBoost ensemble (3 models) extracting 163 financial features from 5-year quarterly data, computing velocity/acceleration signals for trend detection with confidence interval calibration

**Serverless Infrastructure at Scale**
> Designed and deployed 50+ AWS resources via Terraform IaC including Lambda (Docker + Lambda Web Adapter), DynamoDB (8 tables), API Gateway (HTTP + WebSocket), ECR, and S3 with multi-environment support

**Real-Time Streaming Architecture**
> Implemented token-by-token streaming via Bedrock's `converse_stream` API with SSE delivery, reducing perceived latency from 15s batch to sub-second first-token response

**Full-Stack Development**
> Developed complete investment analysis platform: Python backend (6,100+ LOC), React 18 frontend with Tailwind CSS, and 120+ Terraform configuration files across 3 environments

### AI/Prompt Engineering (pick 1-2)

**Value Investing AI Framework**
> Designed prompt architecture embedding Warren Buffett's investment principles across specialized agents, including 60 domain-specific financial metrics mapped to Graham's value criteria

**AI-Assisted Development**
> Leveraged Claude Code for iterative development, prompt optimization, and documentation—reducing development time while maintaining comprehensive code documentation

### Data Pipeline (pick 1)

**Financial Data Pipeline**
> Engineered end-to-end data pipeline: FMP API integration → DynamoDB caching → feature extraction (80+ metrics) → ML inference → multi-agent synthesis → streaming frontend delivery

---

## Skills Demonstrated

| Category | Technologies |
|----------|--------------|
| **AI/ML** | AWS Bedrock, Claude Haiku/Opus, XGBoost, scikit-learn, Prompt Engineering |
| **Backend** | Python, FastAPI, Lambda, Docker, Lambda Web Adapter |
| **Frontend** | React 18, Vite, Tailwind CSS, SSE/Streaming |
| **Cloud** | AWS (Lambda, DynamoDB, Bedrock, API Gateway, ECR, S3, Cognito) |
| **IaC** | Terraform (120+ files, multi-environment) |
| **AI Tools** | Claude Code, AI-assisted development |

---

## Project Description (Portfolio/LinkedIn)

> **Deep Value Insights** is an AI-powered investment analysis platform that evaluates stocks through Warren Buffett's value investing lens. The system orchestrates multiple Claude AI agents (debt, cashflow, growth experts) coordinated by a supervisor, with XGBoost ML models providing quantitative signals from 5 years of financial data. Features real-time SSE streaming, comprehensive AWS serverless infrastructure (50+ resources via Terraform), and a React frontend with interactive analysis visualization.

---

## Quantifiable Metrics

| Metric | Value |
|--------|-------|
| Python backend code | 6,100+ lines |
| Terraform configuration files | 120+ files |
| AWS resources orchestrated | 50+ resources |
| Financial features extracted | 163 per analysis |
| AI agents in orchestration | 4 agents |
| ML models in ensemble | 3 models |
| Historical data processed | 5 years quarterly |
| DynamoDB tables | 8 tables |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (React 18)                           │
│  - Real-time SSE streaming display                                      │
│  - Bubble tabs showing ML predictions (debt, cashflow, growth)          │
│  - Markdown rendering of analysis                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PREDICTION ENSEMBLE LAMBDA                           │
│  - Docker + Lambda Web Adapter + FastAPI                                │
│  - ML inference (XGBoost models from S3)                                │
│  - Feature extraction (163 metrics)                                     │
│  - Expert agent orchestration (parallel via asyncio)                    │
│  - Supervisor streaming (converse_stream API)                           │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
            │ Debt Expert │ │  Cashflow   │ │   Growth    │
            │   (Haiku)   │ │   Expert    │ │   Expert    │
            └─────────────┘ └─────────────┘ └─────────────┘
                    │               │               │
                    └───────────────┼───────────────┘
                                    ▼
                          ┌─────────────────┐
                          │   Supervisor    │
                          │ (Streaming SSE) │
                          └─────────────────┘
```

---

## Data Flow

```
User Query (e.g., "Analyze AAPL")
    │
    ▼
[FMP API] + [DynamoDB Cache] → Fetch 5-year quarterly financials
    │
    ▼
[Feature Extractor] → 80+ metrics + velocity/acceleration signals
    │
    ▼
[XGBoost Inference] → ML predictions + confidence intervals
    │
    ▼
[Expert Agents] (parallel via asyncio.gather)
  - Pre-computed ML signals in prompts
  - 5-year quarterly financial tables
    │
    ▼
[Supervisor Agent] (streaming via converse_stream)
  - Synthesizes 3 expert analyses
  - Applies Buffett/Graham principles
  - Streams verdict + reasoning to frontend
    │
    ▼
[SSE Event Stream] → Frontend bubbles + analysis view
```

---

## Key Technical Achievements

### 1. Inference-First Architecture
- ML inference runs before expert agents
- Predictions emitted as SSE events to populate frontend bubbles immediately
- Agents receive pre-computed signals + metrics (avoids redundant inference)

### 2. True SSE Streaming for Supervisor
- Uses `converse_stream()` API for token-by-token streaming
- Real-time token delivery instead of batched responses
- Queue-based synchronization between async streaming and Bedrock calls

### 3. 5-Year Quarterly Analysis with Trend Signals
- Extracts 20 quarters of historical data
- Computes velocity (direction of change) and acceleration (momentum)
- Context for business cycle understanding (2020 crash, 2021 boom, 2022-23 inflation)

### 4. Value Investor Metrics Framework
- 20 metrics per agent (60 total) aligned with Buffett/Graham principles
- Margin of safety, economic moat, cash is king principles embedded
- Quarterly historical tables injected into agent prompts

### 5. Confidence Calibration
- Probability-based confidence intervals from XGBoost
- Confidence level indicators (STRONG/MODERATE/WEAK)
- Uncertainty quantification in final recommendation

### 6. Docker-Based ML Lambda
- Multi-platform builds (amd64 on Apple Silicon)
- Lambda Web Adapter for Python response streaming
- Efficient model caching across Lambda invocations (warm starts)

---

## Infrastructure Components

| Component | Technology | Purpose |
|-----------|------------|---------|
| Compute | AWS Lambda (Docker) | Serverless execution |
| AI/ML | AWS Bedrock | Multi-agent orchestration |
| ML Models | XGBoost + S3 | Prediction ensemble |
| Database | DynamoDB | Caching, sessions, financials |
| API | API Gateway (HTTP + WS) | Request routing |
| Auth | Cognito + JWT | User authentication |
| IaC | Terraform | Infrastructure management |
| CI/CD | GitHub Actions | Automated deployments |
| CDN | CloudFront | Static site hosting |
| Containers | ECR | Docker image registry |

---

## Development Approach

### AI-Assisted Development with Claude Code
- Iterative prompt optimization for agent behavior
- Code generation and refactoring assistance
- Documentation generation and maintenance
- Architecture design discussions
- Debugging and troubleshooting support

### Infrastructure as Code
- All 50+ AWS resources defined in Terraform
- Multi-environment support (dev, staging, prod)
- State locking with DynamoDB
- Automated CI/CD pipelines

---

## Role-Specific Bullet Point Suggestions

### For ML Engineer Roles
> Built XGBoost ensemble extracting 163 financial features with velocity/acceleration signals, achieving confidence-calibrated predictions for investment analysis across 3 specialized models

### For Full-Stack Developer Roles
> Developed end-to-end investment platform with Python/FastAPI backend (6,100+ LOC), React 18 frontend with real-time SSE streaming, and 120+ Terraform files managing 50+ AWS resources

### For Cloud/DevOps Engineer Roles
> Architected serverless AWS infrastructure via Terraform IaC: Lambda (Docker + LWA), DynamoDB (8 tables), API Gateway, Bedrock agents, ECR, with GitHub Actions CI/CD across 3 environments

### For AI/LLM Engineer Roles
> Designed multi-agent AI system with 4 Claude agents using AWS Bedrock, implementing inference-first architecture with real-time streaming synthesis and value investing prompt framework
