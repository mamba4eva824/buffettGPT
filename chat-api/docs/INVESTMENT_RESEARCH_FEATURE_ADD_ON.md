# Investment Research Feature Add-On - Implementation Guide

> **First Step**: Copy this file to `chat-api/docs/INVESTMENT_RESEARCH_FEATURE_ADD_ON.md` when implementation begins.

## Architecture Overview

This is a **feature addition**, NOT a replacement. The existing "Buffett" mode (prediction_ensemble Lambda + ML inference) remains unchanged.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND DROPDOWN                               │
│                                                                              │
│   ┌─────────────────────────────┐    ┌─────────────────────────────────────┐│
│   │  "Buffett" Mode (EXISTING)  │    │  "Investment Research" Mode (NEW)  ││
│   │                             │    │                                     ││
│   │  - ML Predictions           │    │  - Pre-cached Opus Reports          ││
│   │  - Multi-agent Orchestration│    │  - 5-Point Ratings                  ││
│   │  - Real-time Analysis       │    │  - Follow-up Chat                   ││
│   └──────────────┬──────────────┘    └───────────────────┬─────────────────┘│
│                  │                                       │                   │
└──────────────────┼───────────────────────────────────────┼───────────────────┘
                   │                                       │
                   ▼                                       ▼
┌──────────────────────────────────┐   ┌──────────────────────────────────────┐
│  prediction-ensemble Lambda      │   │  investment-research Lambda (NEW)    │
│  (Docker + LWA + FastAPI)        │   │  (Docker + LWA + FastAPI)            │
│                                  │   │                                      │
│  - Orchestrator                  │   │  - Report streaming                  │
│  - ML inference                  │   │  - Follow-up chat routing            │
│  - Expert agents                 │   │  - No orchestrator needed            │
│  - Supervisor streaming          │   │                                      │
└──────────────────────────────────┘   └──────────────────────────────────────┘
                                                          │
                                                          ▼
                                       ┌──────────────────────────────────────┐
                                       │  investment-research-action Lambda   │
                                       │  (Pure Python - NO LWA)              │
                                       │                                      │
                                       │  - Fetches cached reports            │
                                       │  - Returns exact Bedrock format      │
                                       │  - For follow-up agent               │
                                       └──────────────────────────────────────┘
```

## Key Decisions

| Decision | Choice |
|----------|--------|
| Existing "Buffett" Mode | UNCHANGED - keep ML + multi-agent |
| New Feature Name | "Investment Research" |
| Report Generation | Local CLI (Opus 4.5 + Thinking) |
| Rating System | 5-point: Very Strong / Strong / Stable / Weak / Very Weak |
| Report Storage | DynamoDB |
| Follow-up Agent | Bedrock Haiku 4.5 (single agent, no orchestrator) |
| Lambda Pattern | TWO_LAMBDA_ARCHITECTURE.md pattern |
| Company Scope | DJIA + S&P 500 |
| Refresh Trigger | After quarterly earnings (on-demand CLI) |

---

# PHASE 1: DynamoDB Schema for Reports

## Context for New Conversations
You are creating a new DynamoDB table to store AI-generated investment reports. This MUST be done first before the CLI tool can cache reports.

## Terraform Configuration

### 1.1 New DynamoDB Table
**File**: `chat-api/terraform/modules/dynamodb/reports_table.tf`

```hcl
# Investment Reports Table - stores cached Opus-generated analysis reports
resource "aws_dynamodb_table" "investment_reports" {
  name         = "${var.project_name}-${var.environment}-investment-reports"
  billing_mode = var.billing_mode

  hash_key  = "ticker"
  range_key = "fiscal_year"

  attribute {
    name = "ticker"
    type = "S"
  }

  attribute {
    name = "fiscal_year"
    type = "N"
  }

  attribute {
    name = "generated_at"
    type = "S"
  }

  # GSI for querying by generation date (for batch updates/refresh tracking)
  global_secondary_index {
    name            = "generated-at-index"
    hash_key        = "ticker"
    range_key       = "generated_at"
    projection_type = "ALL"
  }

  # TTL for automatic expiration (reports refresh quarterly)
  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  # Match existing security patterns
  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  deletion_protection_enabled = var.enable_deletion_protection

  tags = merge(
    var.common_tags,
    {
      Name    = "${var.project_name}-${var.environment}-investment-reports"
      Purpose = "Cached investment analysis reports"
    }
  )
}
```

### 1.2 Update outputs.tf
**File**: `chat-api/terraform/modules/dynamodb/outputs.tf` (ADD to existing file)

```hcl
# Investment Reports Table
output "investment_reports_table_name" {
  description = "Name of the investment reports table"
  value       = aws_dynamodb_table.investment_reports.name
}

output "investment_reports_table_arn" {
  description = "ARN of the investment reports table"
  value       = aws_dynamodb_table.investment_reports.arn
}
```

### 1.3 Report Schema

```json
{
  "ticker": "AAPL",
  "fiscal_year": 2024,
  "report_content": "## Executive Summary\n...",
  "ratings": {
    "debt": {
      "rating": "Very Strong",
      "confidence": "High",
      "key_factors": ["Net cash position", "Zero long-term debt concerns", "Strong interest coverage"]
    },
    "cashflow": {
      "rating": "Very Strong",
      "confidence": "High",
      "key_factors": ["FCF margin >20%", "Consistent shareholder returns", "Low capex intensity"]
    },
    "growth": {
      "rating": "Strong",
      "confidence": "Medium",
      "key_factors": ["Services growth accelerating", "Margin stability", "Hardware cyclicality"]
    },
    "overall_verdict": "BUY",
    "conviction": "High"
  },
  "generated_at": "2024-01-15T10:30:00Z",
  "model": "claude-opus-4-5-20251101",
  "features_snapshot": { ... },
  "ttl": 1718841600
}
```

## Phase 1 Verification
```bash
cd chat-api/terraform/environments/dev
terraform init
terraform plan -target=module.dynamodb.aws_dynamodb_table.investment_reports
terraform apply -target=module.dynamodb.aws_dynamodb_table.investment_reports
```
- [ ] Table created in AWS console
- [ ] Table name matches pattern: `dev-investment-reports`

---

# PHASE 2: Report Generation CLI Tool

## Context for New Conversations
You are building a CLI tool that runs locally via Claude Code to generate detailed investment analysis reports. The tool fetches financial data from FMP API (using existing fmp_client.py), uses Opus 4.5 with Thinking mode to generate comprehensive reports, and caches them in the DynamoDB table created in Phase 1.

## New Files to Create

### 2.1 CLI Entry Point
**File**: `chat-api/backend/scripts/generate_report.py`

```python
#!/usr/bin/env python3
"""
Investment Report Generator CLI

Usage:
  python generate_report.py AAPL           # Generate report for single ticker
  python generate_report.py --djia         # Generate all DJIA reports
  python generate_report.py --sp500        # Generate all S&P 500 reports
  python generate_report.py --refresh AAPL # Force refresh existing report
"""

import argparse
import asyncio
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from scripts.report_generator import ReportGenerator

def main():
    parser = argparse.ArgumentParser(description='Generate investment analysis reports')
    parser.add_argument('ticker', nargs='?', help='Single ticker symbol')
    parser.add_argument('--djia', action='store_true', help='Generate all DJIA reports')
    parser.add_argument('--sp500', action='store_true', help='Generate all S&P 500 reports')
    parser.add_argument('--refresh', action='store_true', help='Force refresh existing reports')
    parser.add_argument('--fiscal-year', type=int, help='Fiscal year (default: current)')

    args = parser.parse_args()

    generator = ReportGenerator()

    if args.djia:
        asyncio.run(generator.generate_index_reports('DJIA', force_refresh=args.refresh))
    elif args.sp500:
        asyncio.run(generator.generate_index_reports('SP500', force_refresh=args.refresh))
    elif args.ticker:
        asyncio.run(generator.generate_report(args.ticker, args.fiscal_year, force_refresh=args.refresh))
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
```

### 2.2 Report Generator Service
**File**: `chat-api/backend/scripts/report_generator.py`

This service reuses existing utilities from the prediction_ensemble Lambda:
- `utils/fmp_client.py` - financial data fetching
- `utils/feature_extractor.py` - metrics extraction

```python
"""
Report Generator using Claude Opus 4.5 with Thinking mode.

Reuses existing FMP client and feature extractor from prediction_ensemble.
"""

import json
import boto3
import anthropic
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import os
import re

# Import existing utilities
from src.utils.fmp_client import get_financial_data
from src.utils.feature_extractor import extract_all_features, extract_quarterly_trends
from scripts.index_tickers import get_index_tickers

class ReportGenerator:
    def __init__(self):
        self.dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('INVESTMENT_REPORTS_TABLE', 'dev-investment-reports')
        self.reports_table = self.dynamodb.Table(table_name)
        self.anthropic_client = anthropic.Anthropic()

    async def generate_report(
        self,
        ticker: str,
        fiscal_year: int = None,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """Generate investment analysis report for a ticker."""
        ticker = ticker.upper()
        fiscal_year = fiscal_year or datetime.now().year

        # Check cache first (unless force refresh)
        if not force_refresh:
            cached = self._get_cached_report(ticker, fiscal_year)
            if cached:
                print(f"✓ Using cached report for {ticker}")
                return cached

        print(f"→ Generating report for {ticker}...")

        # 1. Fetch financial data (reuse existing FMP client)
        financial_data = get_financial_data(ticker)
        if not financial_data:
            raise ValueError(f"No financial data available for {ticker}")

        # 2. Extract features and trends (reuse existing extractor)
        raw_financials = financial_data.get('raw_financials', {})
        features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        # 3. Format data for LLM prompt
        metrics_context = self._format_metrics_for_prompt(features, quarterly_trends)

        # 4. Generate report using Opus 4.5 + Thinking
        report = self._generate_with_opus(ticker, fiscal_year, metrics_context)

        # 5. Cache the report
        self._cache_report(ticker, fiscal_year, report, features)

        print(f"✓ Report generated and cached for {ticker}")
        return report

    async def generate_index_reports(self, index: str, force_refresh: bool = False):
        """Generate reports for all tickers in an index."""
        tickers = get_index_tickers(index)
        print(f"Generating {len(tickers)} reports for {index}...")

        for i, ticker in enumerate(tickers, 1):
            try:
                print(f"[{i}/{len(tickers)}] ", end="")
                await self.generate_report(ticker, force_refresh=force_refresh)
            except Exception as e:
                print(f"✗ Failed for {ticker}: {e}")

    def _format_metrics_for_prompt(self, features: dict, trends: dict) -> str:
        """Format financial metrics as structured text for LLM."""
        # Format debt metrics
        debt_text = self._format_domain_metrics(features, trends, 'debt')
        cashflow_text = self._format_domain_metrics(features, trends, 'cashflow')
        growth_text = self._format_domain_metrics(features, trends, 'growth')

        return f"""
## DEBT METRICS (5-Year History)
{debt_text}

## CASHFLOW METRICS (5-Year History)
{cashflow_text}

## GROWTH METRICS (5-Year History)
{growth_text}
"""

    def _format_domain_metrics(self, features: dict, trends: dict, domain: str) -> str:
        """Format metrics for a specific domain."""
        # Extract relevant metrics for this domain
        domain_features = features.get(domain, {})
        # Format as readable tables
        # ... implementation details ...
        return str(domain_features)

    def _generate_with_opus(
        self,
        ticker: str,
        fiscal_year: int,
        metrics_context: str
    ) -> Dict[str, Any]:
        """Generate analysis using Claude Opus 4.5 with Thinking."""

        prompt = f"""Analyze {ticker} for fiscal year {fiscal_year} as a value investor.

{metrics_context}

## Your Task
Provide a comprehensive investment analysis report. Think deeply about:
1. The 5-year narrative arc across all fiscal years
2. Business cycle context (pandemic stress test, inflation period, current position)
3. Trend trajectories - improving, stable, or deteriorating

## Required Output Structure

### Executive Summary
[2-3 sentence investment thesis]

### Debt Health Analysis
[Detailed analysis of leverage, liquidity, debt sustainability]

### Cashflow Quality Analysis
[Detailed analysis of FCF, capital allocation, shareholder returns]

### Growth Profile Analysis
[Detailed analysis of revenue trajectory, margins, earnings power]

### Key Strengths
- [Strength 1 with specific metrics]
- [Strength 2]
- [Strength 3]

### Key Risks
- [Risk 1 with specific metrics]
- [Risk 2]
- [Risk 3]

### 5-Point Ratings (REQUIRED JSON)
End your response with this exact JSON block:
```json
{{
  "debt": {{
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  }},
  "cashflow": {{
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  }},
  "growth": {{
    "rating": "Very Strong" | "Strong" | "Stable" | "Weak" | "Very Weak",
    "confidence": "High" | "Medium" | "Low",
    "key_factors": ["factor1", "factor2", "factor3"]
  }},
  "overall_verdict": "BUY" | "HOLD" | "SELL",
  "conviction": "High" | "Medium" | "Low"
}}
```

Interpret the data holistically - NO rigid thresholds. Weight trends heavily."""

        # Call Opus 4.5 with extended thinking
        response = self.anthropic_client.messages.create(
            model="claude-opus-4-5-20251101",
            max_tokens=16000,
            thinking={
                "type": "enabled",
                "budget_tokens": 10000
            },
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract content and ratings
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        ratings = self._parse_ratings(content)

        return {
            "content": content,
            "ratings": ratings
        }

    def _parse_ratings(self, content: str) -> Dict[str, Any]:
        """Extract JSON ratings block from response."""
        try:
            json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', content)
            if json_match:
                return json.loads(json_match.group(1))
        except (json.JSONDecodeError, AttributeError) as e:
            print(f"Warning: Failed to parse ratings JSON: {e}")
        return {}

    def _cache_report(
        self,
        ticker: str,
        fiscal_year: int,
        report: dict,
        features: dict
    ):
        """Cache report in DynamoDB."""
        item = {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'report_content': report['content'],
            'ratings': report['ratings'],
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'model': 'claude-opus-4-5-20251101',
            'features_snapshot': json.dumps(features),  # Store as string for DynamoDB
            'ttl': int((datetime.utcnow() + timedelta(days=120)).timestamp())  # 4 months
        }
        self.reports_table.put_item(Item=item)

    def _get_cached_report(self, ticker: str, fiscal_year: int) -> Optional[dict]:
        """Retrieve cached report if exists and not expired."""
        try:
            response = self.reports_table.get_item(
                Key={'ticker': ticker, 'fiscal_year': fiscal_year}
            )
            return response.get('Item')
        except Exception:
            return None
```

### 2.3 Index Tickers Lists
**File**: `chat-api/backend/scripts/index_tickers.py`

```python
"""
DJIA and S&P 500 ticker lists for batch report generation.
"""

DJIA_TICKERS = [
    'AAPL', 'AMGN', 'AXP', 'BA', 'CAT', 'CRM', 'CSCO', 'CVX', 'DIS', 'DOW',
    'GS', 'HD', 'HON', 'IBM', 'INTC', 'JNJ', 'JPM', 'KO', 'MCD', 'MMM',
    'MRK', 'MSFT', 'NKE', 'PG', 'TRV', 'UNH', 'V', 'VZ', 'WBA', 'WMT'
]

# S&P 500 list - consider fetching dynamically or maintaining separately
SP500_TICKERS = DJIA_TICKERS + [
    # Add remaining S&P 500 tickers...
]

def get_index_tickers(index: str) -> list:
    """Get tickers for a given index."""
    if index == 'DJIA':
        return DJIA_TICKERS
    elif index == 'SP500':
        return SP500_TICKERS
    else:
        raise ValueError(f"Unknown index: {index}")
```

## Phase 2 Verification
```bash
cd chat-api/backend
export INVESTMENT_REPORTS_TABLE=dev-investment-reports
export FMP_API_KEY=your_key  # Or use secrets manager

python scripts/generate_report.py AAPL
python scripts/generate_report.py --djia
```
- [ ] CLI runs without errors
- [ ] Report generated with Opus 4.5 + Thinking
- [ ] Report cached in DynamoDB
- [ ] Cached report retrieved on second run

---

# PHASE 3: Investment Research Lambda

## Context for New Conversations
You are creating a NEW Lambda called "investment-research" that follows the TWO_LAMBDA_ARCHITECTURE.md pattern. This Lambda serves cached reports and routes follow-up questions to a Bedrock agent. It is SIMPLER than prediction-ensemble (no orchestrator, no ML inference, single agent).

Reference: `chat-api/docs/TWO_LAMBDA_ARCHITECTURE.md`

## New Lambda Structure

```
chat-api/backend/lambda/investment_research/
├── app.py                  # FastAPI application
├── handler.py              # Lambda handler (for Function URL)
├── Dockerfile              # Docker config (LWA + FastAPI)
├── requirements.txt        # Dependencies
├── services/
│   └── report_service.py   # Retrieves cached reports
├── handlers/
│   └── followup_handler.py # Routes to Bedrock agent
└── config/
    └── settings.py         # Configuration
```

### 3.1 FastAPI Application
**File**: `chat-api/backend/lambda/investment_research/app.py`

```python
"""
Investment Research Lambda - FastAPI Application

Endpoints:
- GET /report/{ticker}     - Stream cached report to frontend
- POST /followup           - Route follow-up questions to Bedrock agent
- GET /health              - Health check
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from services.report_service import get_cached_report, stream_report_events
from handlers.followup_handler import handle_followup

app = FastAPI(title="Investment Research API")


class FollowupRequest(BaseModel):
    ticker: str
    message: str
    session_id: str = None


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "investment-research"}


@app.get("/report/{ticker}")
async def get_report(ticker: str, fiscal_year: int = None):
    """Stream cached report to frontend."""
    report = await get_cached_report(ticker.upper(), fiscal_year)
    if not report:
        raise HTTPException(status_code=404, detail=f"No report found for {ticker}")

    return EventSourceResponse(stream_report_events(ticker, report))


@app.post("/followup")
async def followup(request: FollowupRequest):
    """Handle follow-up questions via Bedrock agent."""
    response = await handle_followup(
        ticker=request.ticker,
        message=request.message,
        session_id=request.session_id
    )
    return {"response": response}
```

### 3.2 Report Service
**File**: `chat-api/backend/lambda/investment_research/services/report_service.py`

```python
"""
Report Service - Retrieves and streams cached reports.
"""

import boto3
import json
from datetime import datetime
from typing import Dict, Any, Optional, AsyncGenerator
import os

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('INVESTMENT_REPORTS_TABLE', 'dev-investment-reports')
reports_table = dynamodb.Table(table_name)


async def get_cached_report(ticker: str, fiscal_year: int = None) -> Optional[Dict[str, Any]]:
    """Retrieve cached investment report."""
    fiscal_year = fiscal_year or datetime.now().year

    try:
        response = reports_table.get_item(
            Key={'ticker': ticker.upper(), 'fiscal_year': fiscal_year}
        )
        return response.get('Item')
    except Exception as e:
        print(f"Error retrieving report for {ticker}: {e}")
        return None


async def stream_report_events(ticker: str, report: dict) -> AsyncGenerator[str, None]:
    """
    Stream report to frontend as SSE events.

    Events:
    - connected
    - rating (x3 for debt, cashflow, growth)
    - report (full content)
    - complete
    """
    # Connected event
    yield _sse_event({
        "type": "connected",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })

    # Rating events for bubble display
    ratings = report.get('ratings', {})
    for domain in ['debt', 'cashflow', 'growth']:
        if domain in ratings:
            yield _sse_event({
                "type": "rating",
                "agent_type": domain,
                "ticker": ticker,
                "rating": ratings[domain].get('rating'),
                "confidence": ratings[domain].get('confidence'),
                "key_factors": ratings[domain].get('key_factors', []),
                "timestamp": datetime.utcnow().isoformat() + 'Z'
            })

    # Full report content
    yield _sse_event({
        "type": "report",
        "ticker": ticker,
        "content": report.get('report_content', ''),
        "overall_verdict": ratings.get('overall_verdict'),
        "generated_at": report.get('generated_at'),
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })

    # Complete event
    yield _sse_event({
        "type": "complete",
        "ticker": ticker,
        "source": "cached_report",
        "timestamp": datetime.utcnow().isoformat() + 'Z'
    })


def _sse_event(data: dict) -> str:
    """Format as SSE event."""
    return f"data: {json.dumps(data)}\n\n"
```

### 3.3 Followup Handler
**File**: `chat-api/backend/lambda/investment_research/handlers/followup_handler.py`

```python
"""
Follow-up Handler - Routes questions to Bedrock Haiku agent.

The agent has access to the full cached report via action group.
"""

import boto3
import os
from typing import Optional
import uuid

bedrock_agent = boto3.client('bedrock-agent-runtime')

AGENT_ID = os.environ.get('FOLLOWUP_AGENT_ID')
AGENT_ALIAS = os.environ.get('FOLLOWUP_AGENT_ALIAS', 'TSTALIASID')


async def handle_followup(
    ticker: str,
    message: str,
    session_id: str = None
) -> str:
    """
    Handle follow-up question via Bedrock agent.

    The agent will use its action group to fetch the cached report
    and answer questions based on the report content.
    """
    session_id = session_id or str(uuid.uuid4())

    # Include ticker context in the message
    enriched_message = f"Regarding {ticker}: {message}"

    try:
        response = bedrock_agent.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS,
            sessionId=session_id,
            inputText=enriched_message
        )

        # Collect response chunks
        result = ""
        for event in response['completion']:
            if 'chunk' in event:
                result += event['chunk']['bytes'].decode('utf-8')

        return result

    except Exception as e:
        print(f"Error invoking follow-up agent: {e}")
        return f"I apologize, but I encountered an error processing your question. Please try again."
```

### 3.4 Dockerfile
**File**: `chat-api/backend/lambda/investment_research/Dockerfile`

```dockerfile
# Investment Research Lambda - LWA + FastAPI (NO ML dependencies)

FROM public.ecr.aws/lambda/python:3.11

# Lambda Web Adapter for HTTP streaming
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:0.8.4 /lambda-adapter /opt/extensions/lambda-adapter
RUN chmod +x /opt/extensions/lambda-adapter

WORKDIR ${LAMBDA_TASK_ROOT}

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
    "boto3>=1.34.0" "botocore>=1.34.0" \
    "fastapi>=0.109.0" "uvicorn>=0.27.0" "sse-starlette>=1.6.0" \
    "httpx>=0.27.0" "PyJWT>=2.8.0" "python-dateutil>=2.8.0" \
    --target "${LAMBDA_TASK_ROOT}"

COPY app.py .
COPY handler.py .
COPY services/ ./services/
COPY handlers/ ./handlers/
COPY config/ ./config/

RUN chmod -R 755 ${LAMBDA_TASK_ROOT}

ENV PYTHONUNBUFFERED=1
ENV AWS_LWA_INVOKE_MODE=RESPONSE_STREAM
ENV AWS_LWA_PORT=8080
ENV PORT=8080

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
```

## Phase 3 Verification
```bash
# Build and test locally (per CLAUDE.md rules)
cd chat-api/backend/lambda/investment_research

docker build --platform linux/amd64 -t investment-research:v1.0.0 .

# Test imports
docker run --rm \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e ENVIRONMENT=dev \
  investment-research:v1.0.0 python -c "
from services.report_service import get_cached_report
from handlers.followup_handler import handle_followup
import app
print('All imports successful!')
"

# Test health endpoint
docker run --rm -d --name test -p 8080:8080 \
  -e AWS_DEFAULT_REGION=us-east-1 \
  -e ENVIRONMENT=dev \
  -e INVESTMENT_REPORTS_TABLE=dev-investment-reports \
  investment-research:v1.0.0
curl http://localhost:8080/health
docker stop test
```

---

# PHASE 4: Bedrock Follow-up Agent & Action Group Lambda

## Context for New Conversations
Following TWO_LAMBDA_ARCHITECTURE.md, you are creating a separate "investment-research-action" Lambda for the Bedrock action group. This Lambda returns the exact Bedrock response format (no LWA, no FastAPI). The follow-up agent (Haiku 4.5) calls this action group to retrieve cached reports.

## Action Group Lambda (Pure Python)

### 4.1 Action Group Handler
**File**: `chat-api/backend/lambda/investment_research_action/handler.py`

```python
"""
Investment Research Action Group Lambda

Pure Python handler - NO Lambda Web Adapter.
Returns exact Bedrock action group response format.

Reference: TWO_LAMBDA_ARCHITECTURE.md
"""

import json
import boto3
from datetime import datetime
import os

dynamodb = boto3.resource('dynamodb')
table_name = os.environ.get('INVESTMENT_REPORTS_TABLE', 'dev-investment-reports')
reports_table = dynamodb.Table(table_name)


def lambda_handler(event, context):
    """
    Handle Bedrock action group invocation.

    Returns exact format Bedrock expects - no HTTP transformation.
    """
    print(f"Action group event: {json.dumps(event)}")

    # Parse Bedrock action group event
    action_group = event.get('actionGroup', 'ReportRetrieval')
    api_path = event.get('apiPath', '/get-report')

    # Extract parameters
    request_body = event.get('requestBody', {})
    properties = request_body.get('content', {}).get('application/json', {}).get('properties', [])

    ticker = None
    fiscal_year = None
    for prop in properties:
        if prop.get('name') == 'ticker':
            ticker = prop.get('value', '').upper()
        elif prop.get('name') == 'fiscal_year':
            fiscal_year = int(prop.get('value', datetime.now().year))

    if not ticker:
        return _error_response(action_group, api_path, "Ticker is required")

    fiscal_year = fiscal_year or datetime.now().year

    # Fetch report from DynamoDB
    try:
        response = reports_table.get_item(
            Key={'ticker': ticker, 'fiscal_year': fiscal_year}
        )
        report = response.get('Item')

        if not report:
            return _error_response(
                action_group, api_path,
                f"No report found for {ticker} FY{fiscal_year}"
            )

        # Return success response with full report
        response_body = {
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'report_content': report.get('report_content', ''),
            'ratings': report.get('ratings', {}),
            'generated_at': report.get('generated_at')
        }

        return _success_response(action_group, api_path, response_body)

    except Exception as e:
        print(f"Error retrieving report: {e}")
        return _error_response(action_group, api_path, f"Error: {str(e)}")


def _success_response(action_group: str, api_path: str, body: dict) -> dict:
    """Return exact Bedrock format with application/json (no charset)."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {  # ← Exact key, no charset
                    'body': json.dumps(body)  # ← String, not object
                }
            }
        }
    }


def _error_response(action_group: str, api_path: str, message: str) -> dict:
    """Return error in Bedrock format."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 400,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'error': message})
                }
            }
        }
    }
```

### 4.2 Agent Prompt
**File**: `chat-api/terraform/modules/bedrock/prompts/research_followup_instruction.txt`

```text
You are a financial analyst assistant helping users understand investment analysis reports.

## Your Role
You have access to detailed investment analysis reports generated by a senior analyst using comprehensive 5-year financial data. When a user asks about a company, use your ReportRetrieval action group to fetch the report.

## Your Capabilities
1. Answer questions about a company's financials
2. Explain the reasoning behind ratings (Debt, Cashflow, Growth)
3. Compare metrics across time periods
4. Discuss risks and opportunities mentioned in the report
5. Provide context for investment decisions

## Guidelines
- ALWAYS call the ReportRetrieval action group first to get the report
- Reference specific data from the report when answering
- Be objective and balanced
- Acknowledge uncertainty when appropriate
- Do NOT make up data - only reference what's in the report
- If asked about something not in the report, say so clearly

## Report Content
The report includes:
- Executive Summary
- Debt Health Analysis
- Cashflow Quality Analysis
- Growth Profile Analysis
- Key Strengths and Risks
- 5-Point Ratings (Very Strong / Strong / Stable / Weak / Very Weak)
- Overall Verdict (BUY / HOLD / SELL)
```

### 4.3 Action Group Schema
**File**: `chat-api/terraform/modules/bedrock/schemas/research_report_action.yaml`

```yaml
openapi: 3.0.0
info:
  title: Investment Report Retrieval API
  version: 1.0.0
  description: Retrieves cached investment analysis reports

paths:
  /get-report:
    post:
      operationId: getReport
      summary: Retrieve cached investment report
      description: Fetches the full investment analysis report for a ticker
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - ticker
              properties:
                ticker:
                  type: string
                  description: Stock ticker symbol (e.g., AAPL, MSFT)
                fiscal_year:
                  type: integer
                  description: Fiscal year (default current year)
      responses:
        '200':
          description: Report retrieved successfully
          content:
            application/json:
              schema:
                type: object
                properties:
                  ticker:
                    type: string
                  fiscal_year:
                    type: integer
                  report_content:
                    type: string
                    description: Full markdown report content
                  ratings:
                    type: object
                    description: Structured ratings for debt, cashflow, growth
                  generated_at:
                    type: string
```

## Phase 4 Verification
- [ ] Action group Lambda deployed (zip, not Docker)
- [ ] Bedrock agent created with Haiku 4.5
- [ ] Action group connected to Lambda
- [ ] Agent can retrieve reports and answer questions

---

# PHASE 5: Frontend Updates

## Context for New Conversations
You are adding a new "Investment Research" mode to the frontend dropdown. This mode uses the new investment-research Lambda for cached reports. The existing "Buffett" mode remains unchanged.

## Files to Modify

### 5.1 App.jsx - Add Mode Dropdown
**File**: `frontend/src/App.jsx`

Add mode selector to the search bar:

```javascript
const [analysisMode, setAnalysisMode] = useState('buffett'); // 'buffett' | 'research'

// In the search bar component, add dropdown:
<select
  value={analysisMode}
  onChange={(e) => setAnalysisMode(e.target.value)}
  className="..."
>
  <option value="buffett">Buffett</option>
  <option value="research">Investment Research</option>
</select>

// Route to different handlers based on mode:
const handleAnalysis = async (company) => {
  if (analysisMode === 'buffett') {
    // Existing prediction-ensemble flow
    await startSupervisorAnalysis(company);
  } else {
    // New investment research flow
    await startResearchAnalysis(company);
  }
};
```

### 5.2 New Research Analysis Function
**File**: `frontend/src/App.jsx`

```javascript
const startResearchAnalysis = async (company) => {
  setIsAnalyzing(true);
  setAnalysisError(null);

  const eventSource = new EventSource(
    `${RESEARCH_API_URL}/report/${encodeURIComponent(company)}`
  );

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
      case 'connected':
        console.log('Connected to research API');
        break;

      case 'rating':
        setPredictions(prev => ({
          ...prev,
          [data.agent_type]: {
            rating: data.rating,
            confidence: data.confidence,
            keyFactors: data.key_factors,
            isLoading: false
          }
        }));
        break;

      case 'report':
        setReportContent(data.content);
        setOverallVerdict(data.overall_verdict);
        setGeneratedAt(data.generated_at);
        break;

      case 'complete':
        setIsAnalyzing(false);
        eventSource.close();
        break;

      case 'error':
        setAnalysisError(data.message);
        setIsAnalyzing(false);
        eventSource.close();
        break;
    }
  };

  eventSource.onerror = (error) => {
    console.error('Research SSE error:', error);
    setAnalysisError('Connection error');
    setIsAnalyzing(false);
    eventSource.close();
  };
};
```

### 5.3 BubbleTabs - 5-Point Ratings
**File**: `frontend/src/components/analysis/BubbleTabs.jsx`

Update for 5-point rating scale:

```javascript
const getSignalEmoji = (rating) => {
  const signalMap = {
    'Very Strong': '🟢',
    'Strong': '🟢',
    'Stable': '🟡',
    'Weak': '🟠',
    'Very Weak': '🔴',
    // Keep old format for Buffett mode
    'BUY': '🟢',
    'HOLD': '🟡',
    'SELL': '🔴'
  };
  return signalMap[rating] || '⚪';
};

const colors = {
  'Very Strong': { ring: 'stroke-green-600', bg: 'stroke-green-200', text: 'fill-green-600' },
  'Strong': { ring: 'stroke-green-500', bg: 'stroke-green-200', text: 'fill-green-600' },
  'Stable': { ring: 'stroke-yellow-500', bg: 'stroke-yellow-200', text: 'fill-yellow-600' },
  'Weak': { ring: 'stroke-orange-500', bg: 'stroke-orange-200', text: 'fill-orange-600' },
  'Very Weak': { ring: 'stroke-red-500', bg: 'stroke-red-200', text: 'fill-red-600' },
  // Keep old format for Buffett mode
  'BUY': { ring: 'stroke-green-500', bg: 'stroke-green-200', text: 'fill-green-600' },
  'HOLD': { ring: 'stroke-yellow-500', bg: 'stroke-yellow-200', text: 'fill-yellow-600' },
  'SELL': { ring: 'stroke-red-500', bg: 'stroke-red-200', text: 'fill-red-600' }
};
```

### 5.4 Follow-up Chat Component
**File**: `frontend/src/components/analysis/FollowUpChat.jsx`

New component for research mode follow-up questions:

```javascript
import { useState } from 'react';

const FollowUpChat = ({ ticker, apiUrl }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId] = useState(() => crypto.randomUUID());

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = { role: 'user', content: input };
    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await fetch(`${apiUrl}/followup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ticker,
          message: input,
          session_id: sessionId
        })
      });

      const data = await response.json();
      setMessages(prev => [...prev, { role: 'assistant', content: data.response }]);
    } catch (error) {
      console.error('Follow-up error:', error);
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.'
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="follow-up-chat mt-6 border-t pt-4">
      <h3 className="text-lg font-semibold mb-4">Ask Follow-up Questions</h3>

      <div className="messages space-y-3 mb-4 max-h-64 overflow-y-auto">
        {messages.map((msg, i) => (
          <div
            key={i}
            className={`p-3 rounded-lg ${
              msg.role === 'user'
                ? 'bg-blue-100 ml-8'
                : 'bg-gray-100 mr-8'
            }`}
          >
            {msg.content}
          </div>
        ))}
      </div>

      <div className="flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the analysis..."
          className="flex-1 p-2 border rounded"
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          disabled={isLoading}
        />
        <button
          onClick={sendMessage}
          disabled={isLoading || !input.trim()}
          className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
        >
          {isLoading ? '...' : 'Send'}
        </button>
      </div>
    </div>
  );
};

export default FollowUpChat;
```

## Phase 5 Verification
- [ ] Mode dropdown works
- [ ] "Buffett" mode still uses prediction-ensemble (unchanged)
- [ ] "Investment Research" mode uses new Lambda
- [ ] Ratings display correctly for both modes
- [ ] Follow-up chat works in research mode
- [ ] Frontend builds: `npm run build`

---

# PHASE 6: Terraform for New Resources

## Context for New Conversations
You are adding Terraform configuration for the new Investment Research feature. This ADDS resources alongside existing prediction-ensemble infrastructure.

## New Terraform Files

### 6.1 Investment Research Lambda
**File**: `chat-api/terraform/modules/lambda/investment_research.tf`

```hcl
# Investment Research Lambda (Docker + LWA - similar to prediction-ensemble)
resource "aws_ecr_repository" "investment_research" {
  name = "buffett/investment-research"
  # ... similar config to prediction-ensemble
}

resource "aws_lambda_function" "investment_research" {
  function_name = "${var.environment}-investment-research"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.investment_research.repository_url}:latest"
  role          = aws_iam_role.lambda_execution_role.arn
  timeout       = 60
  memory_size   = 512

  environment {
    variables = {
      ENVIRONMENT               = var.environment
      INVESTMENT_REPORTS_TABLE  = var.investment_reports_table_name
      FOLLOWUP_AGENT_ID         = var.followup_agent_id
      FOLLOWUP_AGENT_ALIAS      = var.followup_agent_alias
      AWS_LWA_INVOKE_MODE       = "RESPONSE_STREAM"
      AWS_LWA_PORT              = "8080"
    }
  }
}

# Function URL for streaming
resource "aws_lambda_function_url" "investment_research" {
  function_name      = aws_lambda_function.investment_research.function_name
  authorization_type = "NONE"  # Or "AWS_IAM" with auth
  invoke_mode        = "RESPONSE_STREAM"
}
```

### 6.2 Investment Research Action Lambda
**File**: `chat-api/terraform/modules/lambda/investment_research_action.tf`

```hcl
# Investment Research Action Lambda (zip, NO LWA - for Bedrock action group)
resource "aws_lambda_function" "investment_research_action" {
  function_name = "${var.environment}-investment-research-action"
  runtime       = "python3.11"
  handler       = "handler.lambda_handler"
  filename      = "${path.module}/../../backend/build/investment_research_action.zip"
  role          = aws_iam_role.lambda_execution_role.arn
  timeout       = 30
  memory_size   = 256

  environment {
    variables = {
      ENVIRONMENT               = var.environment
      INVESTMENT_REPORTS_TABLE  = var.investment_reports_table_name
    }
  }
}

# Permission for Bedrock to invoke
resource "aws_lambda_permission" "bedrock_invoke_research_action" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.investment_research_action.function_name
  principal     = "bedrock.amazonaws.com"
}
```

### 6.3 Bedrock Follow-up Agent
**File**: `chat-api/terraform/modules/bedrock/research_agent.tf`

```hcl
resource "aws_bedrockagent_agent" "research_followup" {
  agent_name                  = "${var.environment}-research-followup"
  agent_resource_role_arn     = aws_iam_role.bedrock_agent_role.arn
  foundation_model            = "anthropic.claude-3-5-haiku-20241022-v1:0"
  instruction                 = file("${path.module}/prompts/research_followup_instruction.txt")
  idle_session_ttl_in_seconds = 600
}

resource "aws_bedrockagent_agent_action_group" "report_retrieval" {
  agent_id          = aws_bedrockagent_agent.research_followup.id
  action_group_name = "ReportRetrieval"

  action_group_executor {
    lambda = var.investment_research_action_lambda_arn
  }

  api_schema {
    payload = file("${path.module}/schemas/research_report_action.yaml")
  }
}

resource "aws_bedrockagent_agent_alias" "research_followup" {
  agent_id         = aws_bedrockagent_agent.research_followup.id
  agent_alias_name = "prod"
}
```

## Phase 6 Verification
```bash
cd chat-api/terraform/environments/dev
terraform init
terraform validate
terraform plan
terraform apply
```
- [ ] ECR repository created for investment-research
- [ ] Both Lambda functions created
- [ ] Bedrock agent created with action group
- [ ] Function URL accessible

---

# PHASE 7: End-to-End Testing

## Test Workflow

1. **Generate reports**:
```bash
cd chat-api/backend
python scripts/generate_report.py AAPL
python scripts/generate_report.py MSFT
python scripts/generate_report.py --djia
```

2. **Deploy Lambdas**:
```bash
./scripts/build_lambdas.sh
# Push Docker images to ECR
# terraform apply
```

3. **Test frontend**:
- Switch to "Investment Research" mode
- Enter AAPL
- Verify ratings display
- Test follow-up chat

4. **Test "Buffett" mode still works**:
- Switch to "Buffett" mode
- Verify ML predictions + orchestration works

## Test Tickers

| Ticker | Expected Ratings |
|--------|------------------|
| AAPL | Debt: Very Strong, Cashflow: Very Strong, Growth: Strong |
| MSFT | Debt: Strong, Cashflow: Very Strong, Growth: Very Strong |
| F | Debt: Weak, Cashflow: Stable, Growth: Weak |
| NVDA | Debt: Strong, Cashflow: Strong, Growth: Very Strong |

---

# Critical Files Summary

| Component | File Path | Status |
|-----------|-----------|--------|
| Reports Table TF | `terraform/modules/dynamodb/reports_table.tf` | NEW |
| CLI Tool | `backend/scripts/generate_report.py` | NEW |
| Report Generator | `backend/scripts/report_generator.py` | NEW |
| Index Tickers | `backend/scripts/index_tickers.py` | NEW |
| Research Lambda | `backend/lambda/investment_research/` | NEW |
| Research Action Lambda | `backend/lambda/investment_research_action/` | NEW |
| Research Agent Prompt | `terraform/modules/bedrock/prompts/research_followup_instruction.txt` | NEW |
| Research Lambda TF | `terraform/modules/lambda/investment_research.tf` | NEW |
| Research Agent TF | `terraform/modules/bedrock/research_agent.tf` | NEW |
| BubbleTabs | `frontend/src/components/analysis/BubbleTabs.jsx` | MODIFY |
| App.jsx | `frontend/src/App.jsx` | MODIFY |
| FollowUpChat | `frontend/src/components/analysis/FollowUpChat.jsx` | NEW |

**UNCHANGED** (existing "Buffett" mode):
- `backend/lambda/prediction_ensemble/` - unchanged
- `terraform/modules/bedrock/` (existing agents) - unchanged
- ML models in S3 - unchanged
