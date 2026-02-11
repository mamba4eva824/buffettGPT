# BuffettGPT - AI Assistant Documentation

## Project Overview

BuffettGPT is a full-stack serverless financial chat application built on AWS. It provides a Warren Buffett-themed AI advisor that answers investment and financial planning questions using Amazon Bedrock (Claude Haiku) with knowledge bases and guardrails.

---

## Repository Structure

```
buffettGPT/
├── chat-api/                          # Backend API and infrastructure
│   ├── backend/                       # Lambda functions and utilities
│   │   ├── src/
│   │   │   ├── handlers/              # Lambda handler functions
│   │   │   └── utils/                 # Utilities (rate limiting, logging)
│   │   ├── layer/                     # Lambda layer dependencies
│   │   ├── scripts/                   # Build scripts
│   │   ├── tests/                     # Python tests
│   │   └── build/                     # Generated Lambda .zip files
│   ├── terraform/                     # Infrastructure as Code
│   │   ├── backend-setup/             # Remote state backend
│   │   ├── environments/              # Environment configs (dev/staging/prod)
│   │   └── modules/                   # Reusable Terraform modules
│   ├── scripts/                       # Deployment scripts
│   └── events/                        # Sample Lambda events
├── frontend/                          # React + Vite frontend
│   ├── src/
│   │   ├── components/                # React components
│   │   ├── hooks/                     # Custom hooks
│   │   ├── api/                       # API client utilities
│   │   └── utils/                     # Logger and helpers
│   └── public/                        # Static assets
├── search-api/                        # Experimental search APIs
│   ├── search.py                      # Perplexity API integration
│   └── model_comparison.py            # Model comparison tools
└── .github/workflows/                 # CI/CD pipelines
```

---

## Technology Stack

### Backend
- **Runtime**: Python 3.11
- **Cloud**: AWS Lambda, API Gateway (HTTP), DynamoDB
- **AI**: Amazon Bedrock (Claude Haiku), Knowledge Bases, Guardrails
- **Auth**: Google OAuth, JWT tokens
- **IaC**: Terraform 1.9.1+

### Frontend
- **Framework**: React 18.2.0
- **Build Tool**: Vite 5.0.8
- **Styling**: Tailwind CSS 3.3.6
- **Auth**: Google OAuth

### Infrastructure
- **State Management**: S3 backend with DynamoDB locking
- **Encryption**: KMS for all sensitive data
- **CDN**: CloudFront for static site delivery

---

## Lambda Functions

Located in `chat-api/backend/src/handlers/`:

| Handler | Purpose |
|---------|---------|
| `auth_callback.py` | Google OAuth callback, issues JWT tokens |
| `auth_verify.py` | JWT verification authorizer |
| `conversations_handler.py` | Chat history management (GET /conversations) |
| `subscription_handler.py` | Stripe subscription management |
| `stripe_webhook_handler.py` | Stripe webhook processing |
| `analysis_followup.py` | Follow-up Agent for research report Q&A |
| `search_handler.py` | Experimental search functionality |

---

## Terraform Modules

Located in `chat-api/terraform/modules/`:

| Module | Purpose |
|--------|---------|
| `core` | KMS encryption, IAM roles, SQS queues |
| `dynamodb` | DynamoDB tables (messages, conversations, users, etc.) |
| `lambda` | Lambda function deployment with layers |
| `api-gateway` | HTTP API configuration |
| `auth` | OAuth authentication infrastructure |
| `bedrock` | AI agent, knowledge base, guardrails |
| `cloudfront-static-site` | CDN and S3 static hosting |
| `rate-limiting` | Device fingerprinting and quotas |
| `monitoring` | CloudWatch dashboards and alerts |

---

## DynamoDB Tables

| Table | Purpose |
|-------|---------|
| `chat-messages` | Message history |
| `conversations` | Conversation details |
| `enhanced-rate-limits` | Device fingerprint rate limiting |
| `usage-tracking` | Monthly usage tracking |
| `anonymous-sessions` | Anonymous user sessions |
| `users` | User profile data |

---

## Development Workflows

### Backend Development

```bash
# Setup virtual environment
cd chat-api/backend
make venv
make dev-install

# Run tests
make test

# Build Lambda packages
./scripts/build_layer.sh
./scripts/build_lambdas.sh

# Test HTTP handler locally
make run-http
```

### Frontend Development

```bash
cd frontend
npm install
npm run dev          # Start dev server on port 3000
npm run build        # Production build
npm run lint         # ESLint (0 warnings policy)
```

### Terraform Deployment

```bash
cd chat-api/terraform/environments/dev

# Initialize (first time or after module changes)
terraform init

# Validate configuration
terraform validate

# Preview changes
terraform plan -out=tfplan

# Apply changes
terraform apply tfplan
```

---

## Environment Configuration

### Backend Environment Variables
Key variables set by Terraform and CI/CD:
- `ENVIRONMENT` - dev/staging/prod
- `FOLLOWUP_AGENT_ID` - Follow-up Agent Bedrock identifier
- `FOLLOWUP_AGENT_ALIAS` - Follow-up Agent alias name
- `ANONYMOUS_MONTHLY_LIMIT` - Rate limit for anonymous users (default: 5)
- `AUTHENTICATED_MONTHLY_LIMIT` - Rate limit for authenticated users (default: 500)

### Frontend Environment Variables
- `VITE_REST_API_URL` - HTTP API endpoint
- `VITE_GOOGLE_CLIENT_ID` - OAuth client ID
- `VITE_ENVIRONMENT` - Current environment

---

## CI/CD Pipelines

Three GitHub Actions workflows in `.github/workflows/`:

### deploy-dev.yml (auto on push to `dev` branch)
1. Build Lambda packages
2. Deploy infrastructure via Terraform
3. Build frontend with environment config
4. Deploy to S3 + invalidate CloudFront

### deploy-staging.yml (auto on push to `staging` branch)
Same structure as dev with staging-specific configuration.

### deploy-prod.yml (manual approval required)
Same structure with production secrets and GitHub environment approval.

---

## Code Conventions

### Naming
- **AWS Resources**: `{project-name}-{environment}-{resource-type}`
  - Example: `buffett-chat-api-dev-chat-sessions`
- **Terraform Variables**: `snake_case`
- **Environment Variables**: `UPPER_CASE`
- **Python/JS**: Standard language conventions

### Patterns
- **Error Handling**: Catch boto3 ClientError, use custom exceptions
- **Logging**: Environment-controlled log levels
- **Rate Limiting**: Device fingerprint (IP + User-Agent + CloudFront headers)

---

## Testing

### Python Tests
```bash
cd chat-api/backend
make test            # Run pytest
```

**Dependencies**: pytest, moto (AWS mocking), pytest-cov

### Frontend Linting
```bash
cd frontend
npm run lint         # ESLint with 0 warnings policy
```

---

## Secrets Management

Secrets are stored in AWS Secrets Manager:
- `buffett-{env}-google-oauth` - OAuth credentials
- `buffett-{env}-jwt-secret` - JWT signing secret
- `buffett-{env}-pinecone-api-key` - Vector DB API key
- `stripe-secret-key-{env}` - Stripe API secret key (sk_test_xxx or sk_live_xxx)
- `stripe-publishable-key-{env}` - Stripe publishable key (pk_test_xxx or pk_live_xxx)
- `stripe-plus-price-id-{env}` - Stripe Plus plan price ID (price_xxx)
- `stripe-webhook-secret-{env}` - Stripe webhook signing secret (whsec_xxx)

Never commit secrets to the repository. Use `.env.example` files as templates.

### Fetching Secrets in Bash

**CRITICAL**: Never hardcode API keys in bash commands. Always fetch from Secrets Manager:

```bash
# Fetch Stripe secret key
STRIPE_SECRET_KEY=$(aws secretsmanager get-secret-value \
  --secret-id stripe-secret-key-dev \
  --query SecretString --output text)

# Fetch Stripe webhook secret
STRIPE_WEBHOOK_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id stripe-webhook-secret-dev \
  --query SecretString --output text)

# Fetch Stripe Plus price ID
STRIPE_PRICE_ID=$(aws secretsmanager get-secret-value \
  --secret-id stripe-plus-price-id-dev \
  --query SecretString --output text)
```

### Using Secrets in Stripe CLI

```bash
# Start webhook listener (fetches secret automatically)
STRIPE_WEBHOOK_SECRET=$(aws secretsmanager get-secret-value \
  --secret-id stripe-webhook-secret-dev \
  --query SecretString --output text)

stripe listen --forward-to https://your-api.com/dev/stripe/webhook
```

### Using Secrets in cURL Commands

```bash
# Fetch the secret key first
STRIPE_SECRET_KEY=$(aws secretsmanager get-secret-value \
  --secret-id stripe-secret-key-dev \
  --query SecretString --output text)

# Use in API calls (key not visible in command history)
curl -s https://api.stripe.com/v1/customers \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "email=test@example.com"

# Create subscription with metadata
curl -s https://api.stripe.com/v1/subscriptions \
  -u "${STRIPE_SECRET_KEY}:" \
  -d "customer=cus_xxx" \
  -d "items[0][price]=${STRIPE_PRICE_ID}" \
  -d "metadata[user_id]=user-123"
```

### Helper Function (add to ~/.bashrc or ~/.zshrc)

```bash
# Get any AWS secret by name
get_secret() {
  aws secretsmanager get-secret-value \
    --secret-id "$1" \
    --query SecretString --output text 2>/dev/null
}

# Usage:
# STRIPE_KEY=$(get_secret stripe-secret-key-dev)
```

---

# MANDATORY DEPLOYMENT RULES

## CRITICAL: TERRAFORM DEPLOYMENT ENFORCEMENT

**ABSOLUTE RULE**: ALL infrastructure changes to dev environment MUST use Terraform.

### Required Terraform Workflow:
1. **Infrastructure as Code** - All changes must be in `.tf` files
2. **Plan before Apply** - Always run `terraform plan` first
3. **State Management** - Use remote state backend
4. **Validation** - Run `terraform validate` before deployment

### Prohibited Actions:
- Direct AWS console changes
- Manual resource creation
- Bypassing Terraform workflows
- Applying without planning

### Mandatory Commands:
```bash
cd chat-api/terraform/environments/dev
terraform init
terraform validate
terraform plan -out=tfplan
terraform apply tfplan
```

---

## LAMBDA PACKAGING RULES

**ABSOLUTE RULE**: ALL Lambda deployment packages (.zip files) MUST be placed in:
```
chat-api/backend/build/
```

### Lambda Build Requirements:
1. **Build Directory** - All .zip files go to `chat-api/backend/build/`
2. **Package Structure** - Maintain consistent packaging format
3. **Dependencies** - Lambda layer contains shared dependencies
4. **Cleanup** - Remove old builds before creating new ones

### Build Commands:
```bash
cd chat-api/backend
./scripts/build_layer.sh      # Build dependencies layer
./scripts/build_lambdas.sh    # Package all Lambda functions
```

### Expected Build Output:
```
chat-api/backend/build/
├── dependencies-layer.zip
├── auth_callback.zip
├── auth_verify.zip
├── conversations_handler.zip
├── subscription_handler.zip
├── stripe_webhook_handler.zip
├── analysis_followup.zip
└── search_handler.zip
```

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `chat-api/terraform/environments/dev/main.tf` | Dev environment root module |
| `chat-api/backend/src/handlers/*.py` | Lambda function handlers |
| `chat-api/backend/src/utils/*.py` | Shared utilities |
| `frontend/src/App.jsx` | Main React application |
| `frontend/src/auth.jsx` | Authentication logic |
| `.github/workflows/*.yml` | CI/CD pipeline definitions |

---

## Common Tasks

### Add a New Lambda Function
1. Create handler in `chat-api/backend/src/handlers/`
2. Add to `build_lambdas.sh` script
3. Define in `chat-api/terraform/modules/lambda/`
4. Add API Gateway route if needed
5. Run build and deploy

### Add a New DynamoDB Table
1. Add table definition in `chat-api/terraform/modules/dynamodb/main.tf`
2. Add output in `chat-api/terraform/modules/dynamodb/outputs.tf`
3. Update Lambda IAM policies if needed
4. Run `terraform plan` then `terraform apply`

### Update Bedrock Follow-up Agent
1. Modify `chat-api/terraform/modules/bedrock/`
2. Update agent instructions in `followup_agent_v1.txt`
3. Deploy via Terraform

---

# INVESTMENT REPORT GENERATION

## CRITICAL: Use Claude Code Mode (NOT API Mode)

**ABSOLUTE RULE**: Investment reports MUST be generated using Claude Code mode, NOT the Anthropic API. There is no Anthropic API key — we use a Claude Max subscription.

### Why Claude Code Mode?
- Cost efficiency: Uses Claude Code's context window instead of API calls
- Better quality: Claude Code can iteratively refine reports
- Interactive: Allows review and revision before saving
- No API key management required

### Report Generation Workflow

1. **Prepare Data** - Fetch financial data from FMP API and cache metrics:
```python
from investment_research.report_generator import ReportGenerator

generator = ReportGenerator(use_api=False, prompt_version=5.1)
data = generator.prepare_data('AMZN')
```
This step:
- Fetches raw financials, extracts features, and pulls valuation data
- **Caches metrics to `metrics-history-dev` table** (7 categories × N quarters) for the follow-up agent
- Returns `ticker`, `fiscal_year`, `metrics_context`, `features`, `raw_financials`, `currency_info`, `valuation_data`

2. **Read the System Prompt** - Load the appropriate prompt template:
```
chat-api/backend/investment_research/prompts/investment_report_prompt_v5_1.txt
```

3. **Generate Report** - Use Claude Code to generate the report content following the prompt, using `data['metrics_context']` as the financial data input.

4. **Save Report + Metrics** - Save report to DynamoDB and ensure metrics are cached:
```python
generator.save_report_sections(
    ticker='AMZN',
    fiscal_year=2026,
    report_content=report_markdown,
    ratings=None,  # auto-extracted from JSON block in report
    raw_financials=data['raw_financials'],
    currency_info=data['currency_info']
)
```
This step:
- Deletes any existing report sections for the ticker
- Parses the markdown into 16 sections and saves to `investment-reports-v2-dev`
- **Caches metrics to `metrics-history-dev`** when `raw_financials` is provided

**IMPORTANT**: Always pass `raw_financials` and `currency_info` from `prepare_data()` to `save_report_sections()`. This ensures the follow-up agent has fresh metrics data. If you skip `prepare_data()` (e.g., using pre-fetched JSON), call `prepare_data()` separately to populate the metrics cache.

### Prohibited Actions
- DO NOT use `generate_report()` with `use_api=True`
- DO NOT set or use `ANTHROPIC_API_KEY` for report generation
- DO NOT bypass the Claude Code workflow
- DO NOT call `save_report_sections()` without providing `raw_financials` — metrics won't be cached

### Prompt Versions
Current recommended version: **v5.1** (executive summary first, dynamic headers, simplified language, ROE in profitability, P/E deep dive valuation)

Available versions are defined in `ReportGenerator.PROMPT_VERSIONS` in:
`chat-api/backend/investment_research/report_generator.py`

---

# AGENTIC WORKFLOW: GSD + RALF

This section defines a structured agentic development workflow for Claude Code, adapted from the GSD (Get Stuff Done) and RALF (Review-Audit-Loop-Fix) methodologies.

## Workflow Overview

```
USER REQUEST → GSD (Spec) → GSD (Plan) → RALF (Execute) → VERIFY → SHIP
```

**Two Phases:**
1. **GSD Phase**: Convert vague goals into testable specs and task graphs
2. **RALF Phase**: Execute tasks with verification loops until gates pass

---

## GSD PHASE: Specification & Planning

### When to Trigger GSD
Use GSD workflow when user requests involve:
- New features requiring multiple files
- Architectural changes
- Non-trivial refactors
- Any task where "done" is ambiguous

### GSD Step 1: Audit Snapshot
Before planning, produce a short audit:
- **Knowns / Evidence**: What's certain from the prompt or codebase
- **Unknowns / Gaps**: Missing info that could change decisions
- **Constraints**: Time, infra, dependencies, policies
- **Risks**: Top 3 things that could sink the plan

### GSD Step 2: PRD (Product Requirements Document)
Create acceptance criteria that are:
- **Observable**: Can be seen/measured
- **Testable**: Has a pass/fail condition
- **Phrased as Given/When/Then** or equivalent

Example:
```
AC-1: Given a logged-in user, when they click "Export", then a CSV downloads within 3 seconds.
AC-2: Given invalid input, when submitted, then an error message appears (no console errors).
```

### GSD Step 3: Implementation Plan
Draft a plan with:
- **Objective**: One sentence
- **Approach Summary**: One paragraph
- **Steps**: Numbered, minimal but complete
- **Files to Modify**: List expected file changes
- **Verification Commands**: How to test each step

### GSD Step 4: Task Graph (via TodoWrite)
Break the plan into atomic tasks using `TodoWrite`. Each task must have:
- Clear acceptance criteria
- Dependencies (what must complete first)
- Expected files to touch
- Verification command

### GSD Step 5: Self-Critique (Red Team)
Before executing, challenge the plan:
- Which assumptions are fragile?
- What failure modes exist?
- What's the simplest version that delivers 80% of value?

### GSD Step 6: User Approval
**STOP and ask user** before proceeding to execution:
- Present the PRD and task list
- Ask for approval or adjustments
- Do NOT proceed until user confirms

---

## RALF PHASE: Execution Loop

### RALF Ground Rule
> "Done" is not a feeling. Done = acceptance criteria met + gates pass + review passes.

### RALF Execution Loop

For each task in the TodoWrite list:

```
1. IMPLEMENT
   - Mark task as in_progress
   - Make minimal, focused changes
   - If plan is impossible, STOP and report "ARCHITECTURE_MISMATCH"

2. VERIFY (Gates)
   - Run relevant commands: tests, lint, typecheck, build
   - If gates fail → fix and retry (do not proceed)

3. REVIEW (Semantic Check)
   - Does the code actually satisfy the acceptance criteria?
   - Are there security issues (injection, auth flaws)?
   - Are there side effects the implementation missed?

4. LEARN
   - If failure occurred, note the lesson for future tasks
   - Update approach if patterns emerge

5. COMPLETE
   - Mark task as completed in TodoWrite
   - Move to next task
```

### RALF Parallelism Rules
Run tasks in parallel ONLY if:
- No dependency edges between them
- They touch disjoint file sets

Otherwise, execute serially.

### Architecture Mismatch Protocol
If during implementation the plan proves impossible:
1. Output: `STATUS: ARCHITECTURE_MISMATCH`
2. Explain why the current approach won't work
3. STOP execution
4. Return to GSD phase for replanning

---

## Verification Gates

### Standard Gates for This Project
```bash
# Python backend
cd chat-api/backend && make test

# Frontend
cd frontend && npm run lint

# Terraform
cd chat-api/terraform/environments/dev && terraform validate

# Full build
cd chat-api/backend && ./scripts/build_lambdas.sh
```

### Gate Requirements
- All gates must pass before marking a task complete
- If a gate fails, fix the issue before proceeding
- Never skip gates or mark tasks done with failing tests

---

## Agent Roles (for Task Tool)

When spawning subagents via the Task tool, use these roles:

### Explorer Agent (`subagent_type=Explore`)
- Codebase exploration and research
- Finding patterns and existing implementations
- Understanding architecture before changes

### Plan Agent (`subagent_type=Plan`)
- Designing implementation strategies
- Identifying critical files and trade-offs
- Creating step-by-step plans

### Debugger Agent (`subagent_type=debugger`)
- Investigating test failures
- Fixing runtime errors
- Performance issue diagnosis

### Test Writer Agent (`subagent_type=test-writer`)
- Creating tests after implementation
- Ensuring coverage for new code
- Regression test creation

### Performance Reviewer (`subagent_type=perf-reviewer`)
- Identifying bottlenecks
- Reviewing data processing code
- Optimizing loops and queries

---

## Workflow Triggers

### User says "GSD" or "plan this"
→ Execute full GSD workflow (Audit → PRD → Plan → Tasks → Approval)

### User says "RALF" or "execute"
→ Execute RALF loop on existing TodoWrite tasks

### User says "verify" or "run gates"
→ Run all verification commands and report status

### User says "ship" or "create PR"
→ Summarize changes, run final gates, prepare PR description

---

## Quality Bars

### Code Changes
- Minimal diffs: change only what's necessary
- No drive-by refactors unless requested
- Security: no injection vulnerabilities, validate inputs at boundaries

### Documentation
- Update only if behavior changes
- Don't add comments for self-evident code
- Don't create new docs unless explicitly requested

### Testing
- Tests must pass before completion
- Add tests for new functionality
- Don't delete tests without explicit approval

---

## Example GSD+RALF Session

```
User: "Add a rate limit bypass for admin users"

Claude: [GSD AUDIT]
- Knowns: Rate limiting exists in enhanced-rate-limits table, auth via JWT
- Unknowns: How are admins identified? JWT claim? DynamoDB flag?
- Risks: Bypass could be exploited if admin check is weak

Claude: [ASKS USER]
"How should admin users be identified? Options:
1. JWT claim 'role: admin'
2. DynamoDB users table 'is_admin' flag
3. Allowlist of user IDs"

User: "Use JWT claim"

Claude: [GSD PRD]
AC-1: Given a request with JWT containing role=admin, when rate limit check runs, then request is allowed regardless of usage count.
AC-2: Given a request without admin role, when rate limit exceeded, then request is rejected as before.

Claude: [GSD TASKS via TodoWrite]
1. Add admin check to rate_limiter.py
2. Update JWT verification to extract role claim
3. Add unit tests for admin bypass
4. Test manually with admin JWT

Claude: "Plan ready. Proceed with implementation?"

User: "Yes"

Claude: [RALF EXECUTE]
- Task 1: in_progress → implement → verify → complete
- Task 2: in_progress → implement → verify → complete
...
- All gates pass
- "Implementation complete. Ready for PR?"
```
