# Buffett

**AI-Powered Investment Research Platform Built on Warren Buffett Principles**

A full-stack serverless application that generates investment research reports written for millennials, Gen Z, and non-financial professionals — applying Buffett/Graham value investing principles in plain, jargon-free language. Users can ask follow-up questions on any report section for deeper analysis powered by conversational AI.

---

## Key Features

- **Accessible Investment Research**: 5-year fundamental analysis covering debt health, cash flow quality, and growth sustainability — written in plain English for everyday investors
- **Comprehensive Reports**: 16-section investment research reports with executive summaries, valuation deep-dives, and actionable ratings
- **Follow-Up Q&A**: Conversational follow-up on any report section powered by Bedrock session memory
- **Subscription Tiers**: Free and Plus tiers with Stripe billing, token usage tracking, and anniversary-based billing periods
- **Viral Waitlist**: Referral-based waitlist with 3-tier rewards (Early Access, 1 month free, 3 months free)
- **5-Year Financial Analysis**: 20 quarters of data with trend velocity and acceleration metrics sourced from FMP API

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                             Buffett                                  │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────┐     ┌────────────────────────────────────────────┐    │
│  │ Frontend  │────▶│         API Gateway (HTTP API v2)          │    │
│  │ (React)   │     └────────────────────────────────────────────┘    │
│  └──────────┘                        │                               │
│                         ┌────────────┼────────────┐                  │
│                         ▼            ▼            ▼                  │
│                   ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│                   │   Auth   │ │   Chat   │ │ Billing  │           │
│                   │ Lambdas  │ │ Lambdas  │ │ Lambdas  │           │
│                   └──────────┘ └──────────┘ └──────────┘           │
│                                      │                               │
│                    ┌─────────────────┼─────────────────┐            │
│                    ▼                 ▼                  ▼            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │   Debt Expert    │  │  Cashflow Expert  │  │  Growth Expert   │  │
│  │  (Claude Haiku 4.5)  │  │  (Claude Haiku 4.5)   │  │  (Claude Haiku 4.5)  │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
│                    │                 │                  │            │
│                    └─────────────────┼──────────────────┘            │
│                                      ▼                               │
│                       ┌──────────────────────────┐                  │
│                       │    Supervisor Agent       │                  │
│                       │    (Claude Haiku 4.5)         │                  │
│                       │  Buffett/Graham Synthesis │                  │
│                       └──────────────────────────┘                  │
│                                      │                               │
│                    ┌─────────────────┼─────────────────┐            │
│                    ▼                 ▼                  ▼            │
│               ┌─────────┐    ┌────────────┐    ┌────────────┐      │
│               │DynamoDB │    │  S3 + CDN  │    │   Stripe   │      │
│               │ Tables  │    │ CloudFront │    │  Billing   │      │
│               └─────────┘    └────────────┘    └────────────┘      │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### Agent Ensemble

| Agent | Role | Key Metrics |
|-------|------|-------------|
| **Debt Expert** | Balance sheet health and leverage | Debt/Equity, Interest Coverage, Current Ratio, Net Debt/EBITDA |
| **Cashflow Expert** | Cash generation quality | FCF, FCF Margin, FCF/Net Income, CapEx Efficiency |
| **Growth Expert** | Earnings quality and sustainability | Revenue Growth, EPS Growth, ROE, ROIC, Margins |
| **Supervisor** | Synthesis with Buffett principles | Weighs expert opinions, considers business type, produces final verdict |

### Data Pipeline

```
FMP API (Financial Data)
    │
    ▼
Feature Extraction (80+ metrics, velocity, acceleration)
    │
    ▼
Metrics Cache (DynamoDB, 7 categories × N quarters)
    │
    ▼
Expert Agent Analysis (3 agents in parallel)
    │
    ▼
Supervisor Synthesis → 16-Section Report
    │
    ▼
DynamoDB V2 Storage (section-per-item) → Frontend Display
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| **Frontend** | React 18, Vite 5, Tailwind CSS |
| **Backend** | Python 3.11, AWS Lambda |
| **AI** | AWS Bedrock (Claude Haiku 4.5), Claude Opus 4.6 (report generation) |
| **Database** | DynamoDB (on-demand) |
| **Payments** | Stripe (Free/Plus tiers, webhooks) |
| **Auth** | Google OAuth 2.0, JWT |
| **Data Source** | Financial Modeling Prep (FMP) API |
| **CDN** | CloudFront + S3 |
| **Infrastructure** | Terraform 1.9.1+ |
| **CI/CD** | GitHub Actions |

---

## Project Structure

```
buffett_chat_api/
├── chat-api/
│   ├── backend/
│   │   ├── src/
│   │   │   ├── handlers/                  # Lambda functions
│   │   │   │   ├── action_group_handler.py # Bedrock action group handler
│   │   │   │   ├── analysis_followup.py   # Follow-up Q&A agent (Docker Lambda)
│   │   │   │   ├── auth_callback.py       # Google OAuth callback
│   │   │   │   ├── auth_verify.py         # JWT authorizer
│   │   │   │   ├── conversations_handler.py # Chat history CRUD
│   │   │   │   ├── search_handler.py      # AI search (experimental)
│   │   │   │   ├── stripe_webhook_handler.py # Stripe event processing
│   │   │   │   ├── subscription_handler.py # Stripe checkout/portal
│   │   │   │   └── waitlist_handler.py    # Waitlist + referral system
│   │   │   └── utils/                     # Rate limiting, logging
│   │   ├── investment_research/           # Report generation engine
│   │   │   ├── report_generator.py        # Core report generation
│   │   │   ├── section_parser.py          # Markdown → sections
│   │   │   ├── multi_agent/              # Multi-agent orchestration
│   │   │   ├── prompts/                   # Prompt templates (v5.1)
│   │   │   └── batch_generation/          # Parallel batch CLI
│   │   ├── layer/                         # Lambda layer dependencies
│   │   ├── build/                         # Lambda .zip packages
│   │   ├── scripts/                       # Build scripts
│   │   └── tests/                         # pytest + moto
│   └── terraform/
│       ├── environments/                  # dev / staging / prod
│       └── modules/
│           ├── core/                      # KMS, IAM
│           ├── dynamodb/                  # DynamoDB tables
│           ├── lambda/                    # Lambda deployment (zip + Docker)
│           ├── api-gateway/               # HTTP API routes
│           ├── auth/                      # OAuth infrastructure
│           ├── bedrock/                   # Agents + guardrails
│           ├── cloudfront-static-site/    # CDN + S3 hosting (app + landing)
│           ├── email/                     # Email service (Resend)
│           ├── stripe/                    # Payment infrastructure
│           ├── sqs/                       # SQS queues
│           ├── rate-limiting/             # Device fingerprinting
│           ├── training-infrastructure/   # ML training
│           └── monitoring/                # CloudWatch dashboards
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── research/                  # Investment report UI
│       │   ├── MobileDrawer.jsx           # Mobile navigation drawer
│       │   ├── SubscriptionManagement.jsx # Stripe subscription UI
│       │   └── TokenUsageDisplay.jsx      # Token usage tracking
│       ├── contexts/                      # React contexts
│       ├── hooks/                         # Custom React hooks
│       ├── api/                           # API client utilities
│       └── App.jsx                        # Main application
├── docs/                                  # MkDocs documentation site
│   ├── api/                               # API reference
│   ├── architecture/                      # Architecture docs
│   ├── infrastructure/                    # Infrastructure guides
│   ├── investment-research/               # Report generation docs
│   ├── stripe/                            # Stripe integration docs
│   └── referral/                          # Referral system docs
├── CLAUDE.md                              # Development rules & procedures
└── MVP_IMPLEMENTATION_GUIDE.md            # Implementation status tracker
```

---

## API Endpoints

### Authentication
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/auth/callback` | None | Google OAuth callback, issues JWT |

### Conversations
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| GET | `/conversations` | JWT | List conversations |
| POST | `/conversations` | JWT | Create conversation |
| GET | `/conversations/{id}` | JWT | Get conversation |
| PUT | `/conversations/{id}` | JWT | Update conversation |
| DELETE | `/conversations/{id}` | JWT | Delete conversation |
| GET | `/conversations/{id}/messages` | JWT | Get messages |
| POST | `/conversations/{id}/messages` | JWT | Save message |

### Subscriptions
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/subscription/checkout` | JWT | Create Stripe checkout session |
| POST | `/subscription/portal` | JWT | Open Stripe customer portal |
| GET | `/subscription/status` | JWT | Get subscription status |
| POST | `/stripe/webhook` | Stripe Signature | Stripe event webhook |

### Waitlist
| Method | Route | Auth | Description |
|--------|-------|------|-------------|
| POST | `/waitlist/signup` | None (rate-limited) | Sign up with referral support |
| GET | `/waitlist/status` | Email + Code | Get queue position and referral stats |

---

## DynamoDB Tables

| Table | Purpose |
|-------|---------|
| `conversations` | Conversation metadata |
| `chat-messages` | Message history |
| `investment-reports-v2` | Section-per-item report storage |
| `metrics-history` | Cached financial metrics (7 categories) |
| `token-usage` | Anniversary-based billing period tracking |
| `financial-data-cache` | FMP API response cache |
| `ticker-lookup-cache` | Ticker symbol lookups |
| `forex-rate-cache` | Currency conversion rates |
| `waitlist` | Waitlist entries + referral codes |

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- AWS CLI configured
- Terraform 1.9.1+

### Backend

```bash
cd chat-api/backend
make venv && make dev-install
make test

# Build Lambda packages
./scripts/build_layer.sh
./scripts/build_lambdas.sh
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Dev server on port 3000
npm run build     # Production build
npm run lint      # ESLint (0 warnings policy)
```

### Infrastructure

```bash
cd chat-api/terraform/environments/dev
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

---

## Investment Report Generation

Reports are generated using Claude Code (not the Anthropic API) with the v5.1 prompt template. Each report contains 16 sections covering executive summary, valuation, growth, debt, cash flow, competitive position, and more.

### Batch Generation

```bash
cd chat-api/backend/investment_research/batch_generation

# Prepare data (fetch FMP + cache metrics)
python batch_cli.py prepare --tickers AAPL,MSFT,GOOGL

# Generate reports (5 parallel Claude sessions)
./run_parallel_reports.sh

# Verify reports saved to DynamoDB
python batch_cli.py verify --tickers AAPL,MSFT,GOOGL
```

### Ticker Coverage

| Index | Tickers | Est. Generation Time (5 parallel) |
|-------|---------|-----------------------------------|
| DJIA | 30 | ~2-3 hours |
| Nasdaq 100 | 100 | ~6-10 hours |
| S&P 500 | 500 | ~30-50 hours |

---

## Waitlist & Referral System

A viral waitlist with a 3-tier referral reward ladder:

| Referrals | Reward |
|-----------|--------|
| 1 | Early Access (skip the waitlist) |
| 3 | 1 month free Plus |
| 10 | 3 months free Plus |

Features: unique referral codes (BUFF-XXXX), disposable email blocking, rate limiting, self-referral prevention, social sharing UI.

---

## CI/CD

Three GitHub Actions workflows:

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `deploy-dev.yml` | Push to `dev` | Build Lambdas, Terraform apply, build + deploy frontend |
| `deploy-staging.yml` | Push to `staging` | Same with staging config |
| `deploy-prod.yml` | Manual | Same with production secrets + approval gate |

---

## Security

- **Auth**: Google OAuth 2.0 with JWT tokens
- **Encryption**: KMS for all sensitive data at rest
- **Secrets**: AWS Secrets Manager (OAuth, JWT, Stripe, FMP keys)
- **Rate Limiting**: Device fingerprinting (IP + User-Agent + CloudFront headers)
- **Waitlist**: IP-based rate limiting, disposable email blocking, referral code validation

---

## Contributing

1. Fork the repository
2. Create a feature branch from `dev`
3. Follow [CLAUDE.md](CLAUDE.md) deployment rules
4. Submit a pull request

---

## License

MIT License
