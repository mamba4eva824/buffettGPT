# Deep Value Insights

**AI-Powered Investment Research Engine Built on Warren Buffett Principles**

An intelligent investment analysis platform that combines multi-agent AI orchestration with machine learning to evaluate stocks through the lens of value investing. The system employs a team of specialized expert agents—each focused on debt health, cash flow quality, and growth sustainability—coordinated by a supervisor agent that synthesizes their insights using Buffett and Graham investment principles.

---

## Key Features

- **Multi-Agent Ensemble**: Three specialized expert agents (Debt, Cashflow, Growth) analyze different dimensions of a company's fundamentals, orchestrated by a Supervisor agent
- **ML-Driven Predictions**: XGBoost models trained on financial metrics provide BUY/HOLD/SELL signals with confidence intervals
- **Real-Time Streaming**: Server-Sent Events (SSE) deliver analysis as it's generated, providing immediate feedback
- **Value Investing Framework**: Analysis grounded in Buffett/Graham principles—margin of safety, economic moat, management quality
- **5-Year Quarterly Analysis**: 20 quarters of financial data with trend velocity and acceleration metrics
- **Confidence Calibration**: Predictions include uncertainty quantification (STRONG/MODERATE/WEAK confidence levels)

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DEEP VALUE INSIGHTS                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐    ┌──────────────────────────────────────────────────┐   │
│  │   Frontend  │───▶│              API Gateway (HTTP/WebSocket)         │   │
│  │   (React)   │    └──────────────────────────────────────────────────┘   │
│  └─────────────┘                           │                               │
│                                            ▼                               │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PREDICTION ENSEMBLE (FastAPI/Docker)              │   │
│  │  ┌─────────────────────────────────────────────────────────────────┐│   │
│  │  │                      ORCHESTRATOR SERVICE                       ││   │
│  │  │  1. Fetch Financial Data (FMP API + DynamoDB Cache)            ││   │
│  │  │  2. Extract Features (80+ metrics)                             ││   │
│  │  │  3. Run ML Inference (XGBoost)                                 ││   │
│  │  │  4. Invoke Expert Agents in Parallel                           ││   │
│  │  │  5. Stream Supervisor Synthesis                                ││   │
│  │  └─────────────────────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                            │                               │
│                    ┌───────────────────────┼───────────────────────┐       │
│                    ▼                       ▼                       ▼       │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐ │
│  │    DEBT EXPERT      │  │   CASHFLOW EXPERT   │  │   GROWTH EXPERT     │ │
│  │  (Claude Haiku 4.5) │  │  (Claude Haiku 4.5) │  │  (Claude Haiku 4.5) │ │
│  ├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤ │
│  │ • Debt-to-Equity    │  │ • Free Cash Flow    │  │ • Revenue Growth    │ │
│  │ • Interest Coverage │  │ • FCF Margin        │  │ • EPS Growth        │ │
│  │ • Current Ratio     │  │ • FCF/Net Income    │  │ • Operating Margin  │ │
│  │ • Net Debt/EBITDA   │  │ • CapEx Efficiency  │  │ • ROE / ROIC        │ │
│  │ • Deleveraging Pace │  │ • Dividend Safety   │  │ • Margin Expansion  │ │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘ │
│                    │                       │                       │       │
│                    └───────────────────────┼───────────────────────┘       │
│                                            ▼                               │
│                      ┌─────────────────────────────────────────────┐       │
│                      │           SUPERVISOR AGENT                   │       │
│                      │          (Claude Haiku 4.5)                  │       │
│                      ├─────────────────────────────────────────────┤       │
│                      │ • Synthesizes Expert Analyses               │       │
│                      │ • Applies Buffett/Graham Principles         │       │
│                      │ • Weighs Disagreements by Business Type     │       │
│                      │ • Produces Final Verdict: BUY/HOLD/SELL     │       │
│                      │ • Provides Confidence-Calibrated Reasoning  │       │
│                      └─────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Agent Ensemble

The system uses a **hierarchical multi-agent architecture** powered by AWS Bedrock:

| Agent | Role | Key Metrics |
|-------|------|-------------|
| **Debt Expert** | Analyzes balance sheet health and leverage | Debt/Equity, Interest Coverage, Current Ratio, Net Debt/EBITDA |
| **Cashflow Expert** | Evaluates cash generation quality | FCF, FCF Margin, FCF/Net Income, CapEx Efficiency |
| **Growth Expert** | Assesses earnings quality and sustainability | Revenue Growth, EPS Growth, ROE, ROIC, Margins |
| **Supervisor** | Synthesizes analyses with Buffett principles | Weighs expert opinions, considers business type, produces final verdict |

### Data Flow

```
User Query (e.g., "Analyze AAPL")
         │
         ▼
┌─────────────────────────────────────┐
│      1. FINANCIAL DATA FETCH        │
│  FMP API → DynamoDB Cache           │
│  (20 quarters / 5 years)            │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      2. FEATURE EXTRACTION          │
│  80+ metrics per company            │
│  + Velocity (trend direction)       │
│  + Acceleration (trend momentum)    │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      3. ML INFERENCE                │
│  XGBoost Models (Debt/Cash/Growth)  │
│  → Prediction + Confidence Interval │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      4. EXPERT ANALYSIS             │
│  3 Agents analyze in parallel       │
│  Each receives ML signal + metrics  │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│      5. SUPERVISOR SYNTHESIS        │
│  Combines expert views              │
│  Applies value investing framework  │
│  → Final BUY/HOLD/SELL + Reasoning  │
└─────────────────────────────────────┘
         │
         ▼
    Streaming Response (SSE)
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **AI/ML** | AWS Bedrock (Claude Haiku 4.5), XGBoost |
| **Backend** | AWS Lambda (Python 3.11), FastAPI, Docker |
| **Streaming** | Server-Sent Events (SSE), Lambda Web Adapter |
| **Database** | DynamoDB (caching, sessions, rate limits) |
| **Data Source** | Financial Modeling Prep (FMP) API |
| **Infrastructure** | Terraform, API Gateway, S3, CloudWatch |
| **Frontend** | React 18, Vite, Tailwind CSS |
| **Auth** | JWT, Cognito |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI configured
- Terraform 1.0+
- Docker (for prediction ensemble)

### Deployment

All infrastructure changes use Terraform. See [CLAUDE.md](CLAUDE.md) for detailed deployment instructions.

```bash
cd chat-api/terraform/environments/dev
terraform init
terraform plan
terraform apply
```

---

## Project Structure

```
deep-value-insights/
├── chat-api/
│   ├── backend/
│   │   ├── lambda/
│   │   │   └── prediction_ensemble/    # Docker-based FastAPI service
│   │   │       ├── app.py              # Main application & routes
│   │   │       ├── services/
│   │   │       │   ├── orchestrator.py # Multi-agent coordination
│   │   │       │   ├── bedrock.py      # Agent invocation
│   │   │       │   └── inference.py    # XGBoost model loading
│   │   │       └── utils/
│   │   │           ├── fmp_client.py   # Financial data fetching
│   │   │           └── feature_extractor.py
│   │   ├── src/handlers/
│   │   │   ├── action_group_handler.py # Bedrock action group
│   │   │   ├── chat_http_handler.py    # HTTP API endpoint
│   │   │   └── websocket_message.py    # WebSocket handler
│   │   ├── layer/                      # Lambda layer dependencies
│   │   ├── build/                      # Lambda deployment packages
│   │   └── scripts/                    # Build scripts
│   └── terraform/
│       ├── environments/dev/           # Dev environment config
│       └── modules/
│           ├── bedrock/                # Agent definitions & prompts
│           │   ├── main.tf
│           │   ├── prompts/            # Agent instruction files
│           │   └── schemas/            # Action group OpenAPI specs
│           ├── lambda/                 # Lambda function configs
│           ├── api-gateway/            # HTTP & WebSocket APIs
│           ├── dynamodb/               # Table definitions
│           └── s3/                     # Bucket configs
├── frontend/
│   └── src/
│       ├── components/analysis/        # Analysis UI components
│       └── App.jsx
├── CLAUDE.md                           # Deployment rules & procedures
└── README.md
```

---

## API Overview

### Analysis Endpoint

```
POST /analysis/{agent_type}
```

Streams investment analysis for a given ticker.

**Parameters:**
- `agent_type`: `supervisor` | `debt` | `cashflow` | `growth`
- Body: `{ "ticker": "AAPL" }`

**Response (SSE Stream):**
```
event: status
data: {"status": "fetching_data", "message": "Fetching financial data..."}

event: prediction
data: {"agent": "debt", "prediction": "HOLD", "confidence": "MODERATE"}

event: content
data: {"text": "## Debt Analysis\n\nApple maintains..."}

event: complete
data: {"usage": {"input_tokens": 1234, "output_tokens": 567}}
```

### Action Group (Bedrock Agent)

The agents use an action group to fetch financial data:

```yaml
operationId: getFinancialAnalysis
parameters:
  - ticker: "AAPL"        # Stock symbol
  - analysis_type: "debt" # debt | cashflow | growth | all
```

Returns: ML predictions + top 10-24 value metrics with 5-year quarterly history.

---

## Security & Monitoring

### Rate Limiting
- **Anonymous**: 5 analyses/month
- **Authenticated**: 500 analyses/month
- Device fingerprinting for cross-device tracking

### Authentication
- JWT tokens via Authorization header
- AWS Cognito user pools

### Monitoring
- CloudWatch logs and metrics
- Dead-letter queues for error handling
- X-Ray tracing for request debugging

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes following [CLAUDE.md](CLAUDE.md) deployment rules
4. Submit a pull request

---

## License

MIT License

---

## Support

For issues and questions, please open a GitHub issue with detailed information about your use case.
