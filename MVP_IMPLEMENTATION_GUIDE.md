# BuffettGPT MVP Launch Implementation Guide

This document provides detailed implementation plans for completing the MVP launch. Each section includes priority, estimated complexity, file paths, and specific code changes required.

---

## Table of Contents

1. [Token Usage Table Enhancements](#1-token-usage-table-enhancements)
2. [Monthly Token Reset Logic](#2-monthly-token-reset-logic)
3. [UI Collapsible Orchestrator Responses](#3-ui-collapsible-orchestrator-responses)
4. [Financial Metrics Comparison Tool](#4-financial-metrics-comparison-tool)
5. [Lambda Concurrency Changes](#5-lambda-concurrency-changes)
6. [Deprecate Chat Processor Lambda](#6-deprecate-chat-processor-lambda)
7. [Stripe Payment Integration](#7-stripe-payment-integration)
8. [Token Limiter Polish](#8-token-limiter-polish)

---

## 1. Token Usage Table Enhancements

**Priority:** High
**Complexity:** Low
**Status:** Partially implemented

### Current State

The token usage table (`token_usage.tf`) already tracks monthly usage with:
- `user_id` (PK) + `month` (SK in YYYY-MM format)
- `input_tokens`, `output_tokens`, `total_tokens`
- `token_limit`, `request_count`
- `notified_80`, `notified_90`, `limit_reached_at`

### Required Changes

Add two new attributes:
- `reset_date`: When the token limit resets (already computed dynamically via `get_reset_date()`)
- `subscribed_at`: When the user first subscribed (needs to be added)

### Implementation

#### Step 1: Update DynamoDB Table Schema Documentation

**File:** `chat-api/terraform/modules/dynamodb/token_usage.tf`

```hcl
# Add to schema documentation (lines 49-64):
# subscribed_at      | S      | ISO timestamp of first subscription
# subscription_tier  | S      | User tier (free/basic/premium/enterprise)
# reset_date         | S      | Pre-computed reset date for this period
```

#### Step 2: Update TokenUsageTracker

**File:** `chat-api/backend/src/utils/token_usage_tracker.py`

Add to `record_usage()` method (around line 200):

```python
UpdateExpression='''
    ADD input_tokens :input,
        output_tokens :output,
        total_tokens :total,
        request_count :one
    SET last_request_at = :now,
        token_limit = if_not_exists(token_limit, :default_limit),
        reset_date = if_not_exists(reset_date, :reset),
        subscribed_at = if_not_exists(subscribed_at, :now)
''',
ExpressionAttributeValues={
    ':input': input_tokens,
    ':output': output_tokens,
    ':total': total_new_tokens,
    ':one': 1,
    ':now': now,
    ':default_limit': self.default_token_limit,
    ':reset': self.get_reset_date()
},
```

#### Step 3: Add to Usage Response

Update `get_usage()` method to return these fields:

```python
return {
    # ... existing fields ...
    'subscribed_at': item.get('subscribed_at'),
    'reset_date': self.get_reset_date(),
}
```

---

## 2. Monthly Token Reset Logic

**Priority:** High
**Complexity:** Low
**Status:** Already implemented ✅

### Current Implementation

The monthly reset is **already handled automatically** by the table schema:
- Primary key: `user_id` + `month` (YYYY-MM format)
- Each month creates a new record
- `get_current_month()` returns current YYYY-MM
- Queries automatically target the current month's record

### How It Works

```python
# chat-api/backend/src/utils/token_usage_tracker.py:81-83
@staticmethod
def get_current_month() -> str:
    """Get current month in YYYY-MM format."""
    return datetime.utcnow().strftime('%Y-%m')
```

When a new month starts:
1. `get_current_month()` returns new value (e.g., "2026-02")
2. `check_limit()` queries for the new month → returns empty (0 tokens used)
3. `record_usage()` creates new record for the new month
4. Previous month's data is preserved for historical analysis

### Optional Enhancement: Archive Old Records

Add TTL for automatic cleanup (optional):

**File:** `chat-api/terraform/modules/dynamodb/token_usage.tf`

```hcl
ttl {
  attribute_name = "expires_at"
  enabled        = true
}
```

---

## 3. UI Collapsible Orchestrator Responses

**Priority:** High
**Complexity:** Medium
**Status:** Partially implemented

### Current State

- `ResearchContext.jsx` already has `collapsedFollowUpIds` state and `TOGGLE_FOLLOWUP_COLLAPSE` action
- `SectionCard.jsx` has collapse functionality for report sections
- Follow-up messages have basic collapse in `App.jsx` (lines 2243-2320)

### Required Changes

Enhance collapsible functionality for orchestrator (multi-agent) responses in the analysis view.

### Implementation

#### Step 1: Add Orchestrator Response State

**File:** `frontend/src/contexts/ResearchContext.jsx`

Add to initial state:

```javascript
const initialState = {
  // ... existing state ...

  // Orchestrator response state
  orchestratorResponses: [], // [{id, agentType, prediction, confidence, explanation, isCollapsed}]
  collapsedOrchestratorIds: [],
};
```

Add new action types:

```javascript
const ACTIONS = {
  // ... existing actions ...
  ADD_ORCHESTRATOR_RESPONSE: 'ADD_ORCHESTRATOR_RESPONSE',
  TOGGLE_ORCHESTRATOR_COLLAPSE: 'TOGGLE_ORCHESTRATOR_COLLAPSE',
  COLLAPSE_ALL_ORCHESTRATOR: 'COLLAPSE_ALL_ORCHESTRATOR',
  EXPAND_ALL_ORCHESTRATOR: 'EXPAND_ALL_ORCHESTRATOR',
};
```

Add reducer cases:

```javascript
case ACTIONS.TOGGLE_ORCHESTRATOR_COLLAPSE:
  return {
    ...state,
    collapsedOrchestratorIds: state.collapsedOrchestratorIds.includes(action.id)
      ? state.collapsedOrchestratorIds.filter(id => id !== action.id)
      : [...state.collapsedOrchestratorIds, action.id],
  };

case ACTIONS.COLLAPSE_ALL_ORCHESTRATOR:
  return {
    ...state,
    collapsedOrchestratorIds: state.orchestratorResponses.map(r => r.id),
  };

case ACTIONS.EXPAND_ALL_ORCHESTRATOR:
  return {
    ...state,
    collapsedOrchestratorIds: [],
  };
```

#### Step 2: Create CollapsibleAgentResponse Component

**File:** `frontend/src/components/analysis/CollapsibleAgentResponse.jsx` (new file)

```jsx
import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const AGENT_COLORS = {
  debt: 'border-red-500 bg-red-500/10',
  cashflow: 'border-green-500 bg-green-500/10',
  growth: 'border-blue-500 bg-blue-500/10',
  supervisor: 'border-purple-500 bg-purple-500/10',
};

const PREDICTION_BADGES = {
  BUY: 'bg-green-600 text-white',
  HOLD: 'bg-yellow-500 text-black',
  SELL: 'bg-red-600 text-white',
};

export default function CollapsibleAgentResponse({
  agentType,
  prediction,
  confidence,
  explanation,
  isCollapsed,
  onToggle,
}) {
  const colorClass = AGENT_COLORS[agentType] || AGENT_COLORS.supervisor;
  const badgeClass = PREDICTION_BADGES[prediction] || 'bg-gray-500 text-white';

  return (
    <div className={`border-l-4 rounded-lg mb-3 ${colorClass}`}>
      {/* Header - Always visible */}
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-3 hover:bg-white/5 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="font-semibold capitalize">{agentType} Agent</span>
          <span className={`px-2 py-0.5 rounded text-sm font-bold ${badgeClass}`}>
            {prediction}
          </span>
          {confidence && (
            <span className="text-sm text-gray-400">
              {(confidence * 100).toFixed(0)}% confidence
            </span>
          )}
        </div>
        {isCollapsed ? (
          <ChevronDown className="w-5 h-5 text-gray-400" />
        ) : (
          <ChevronUp className="w-5 h-5 text-gray-400" />
        )}
      </button>

      {/* Content - Collapsible */}
      <div
        className={`overflow-hidden transition-all duration-300 ${
          isCollapsed ? 'max-h-0 opacity-0' : 'max-h-[2000px] opacity-100'
        }`}
      >
        <div className="px-4 pb-4 prose prose-invert max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {explanation}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}
```

#### Step 3: Update AnalysisView to Use Collapsible Components

**File:** `frontend/src/components/analysis/AnalysisView.jsx`

Add collapse controls and map orchestrator responses to collapsible components.

---

## 4. Financial Metrics Comparison Tool

**Priority:** Medium
**Complexity:** Medium

### Overview

Add a new tool to the follow-up agent that allows users to compare financial metrics across multiple companies.

### Implementation

#### Step 1: Add Tool Definition

**File:** `chat-api/backend/src/handlers/analysis_followup.py`

Add to `FOLLOWUP_TOOLS` (around line 139):

```python
{
    "toolSpec": {
        "name": "compareCompanyMetrics",
        "description": "Compare financial metrics across multiple companies. Use when the user asks to compare companies, see which is better, or analyze relative performance.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "maxItems": 5,
                        "description": "List of stock ticker symbols to compare (2-5 companies)"
                    },
                    "metrics": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "revenue_growth",
                                "profit_margin",
                                "fcf_margin",
                                "debt_to_equity",
                                "interest_coverage",
                                "pe_ratio",
                                "price_to_fcf",
                                "roe",
                                "share_dilution"
                            ]
                        },
                        "description": "Metrics to compare. If empty, returns key financial health metrics."
                    },
                    "time_period": {
                        "type": "string",
                        "enum": ["latest", "ttm", "3yr_avg", "5yr_avg"],
                        "default": "ttm",
                        "description": "Time period for comparison: latest quarter, trailing twelve months, 3-year or 5-year average"
                    }
                },
                "required": ["tickers"]
            }
        }
    }
}
```

#### Step 2: Add Tool Executor

**File:** `chat-api/backend/src/utils/tool_executor.py`

Add new function:

```python
def execute_compare_metrics(tickers: List[str], metrics: List[str] = None, time_period: str = 'ttm') -> Dict[str, Any]:
    """
    Compare financial metrics across multiple companies.

    Args:
        tickers: List of stock ticker symbols (2-5 companies)
        metrics: Optional list of specific metrics to compare
        time_period: Time period for comparison

    Returns:
        Dictionary with comparison data and insights
    """
    if len(tickers) < 2:
        return {'success': False, 'error': 'At least 2 tickers required for comparison'}

    if len(tickers) > 5:
        return {'success': False, 'error': 'Maximum 5 tickers allowed for comparison'}

    # Default metrics if none specified
    if not metrics:
        metrics = ['revenue_growth', 'profit_margin', 'fcf_margin', 'debt_to_equity', 'pe_ratio']

    comparison_data = {}

    for ticker in tickers:
        try:
            # Fetch metrics for each ticker
            report = get_investment_report(ticker)
            if not report:
                comparison_data[ticker] = {'error': f'No report available for {ticker}'}
                continue

            ticker_metrics = {}
            for metric in metrics:
                value = extract_metric_from_report(report, metric, time_period)
                ticker_metrics[metric] = value

            comparison_data[ticker] = ticker_metrics
        except Exception as e:
            comparison_data[ticker] = {'error': str(e)}

    return {
        'success': True,
        'comparison': comparison_data,
        'metrics_compared': metrics,
        'time_period': time_period,
        'generated_at': datetime.utcnow().isoformat() + 'Z'
    }
```

#### Step 3: Register in Tool Router

Update the `execute_tool()` function to route to the new handler:

```python
def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with given input."""

    if tool_name == 'compareCompanyMetrics':
        return execute_compare_metrics(
            tickers=tool_input.get('tickers', []),
            metrics=tool_input.get('metrics'),
            time_period=tool_input.get('time_period', 'ttm')
        )

    # ... existing tool handlers ...
```

---

## 5. Lambda Concurrency Changes

**Priority:** High
**Complexity:** Low

### Current Configuration

- `chat_processor`: Reserved concurrency = 2
- `analysis_followup`: No reserved concurrency (uses default)

### Required Changes

Increase `analysis_followup` concurrency for production readiness.

### Implementation

**File:** `chat-api/terraform/environments/dev/main.tf`

Update the `reserved_concurrency` block (around line 176):

```hcl
reserved_concurrency = {
  chat_processor     = 2   # Keep low (being deprecated)
  analysis_followup  = 10  # Increase for production traffic
}
```

**File:** `chat-api/terraform/modules/lambda/main.tf`

The module already supports `reserved_concurrency` via the lookup (line 133):

```hcl
reserved_concurrent_executions = lookup(var.reserved_concurrency, each.key, -1)
```

For production environments, create separate configs:

**File:** `chat-api/terraform/environments/prod/main.tf`

```hcl
reserved_concurrency = {
  analysis_followup  = 50   # Higher for production
  websocket_connect  = 20
  websocket_message  = 20
}
```

---

## 6. Deprecate Chat Processor Lambda

**Priority:** Medium
**Complexity:** Medium

### Overview

The `chat_processor` Lambda was used for the RAG chatbot architecture. Now that the system uses the orchestrator pattern with `analysis_followup`, it should be deprecated.

### Deprecation Steps

#### Step 1: Remove from Lambda Module

**File:** `chat-api/terraform/modules/lambda/main.tf`

Option A - Remove from configs (breaking change):
```hcl
locals {
  lambda_configs = {
    # Remove chat_processor entirely
    # chat_processor = { ... }

    # Keep other functions
    chat_http_handler = { ... }
    # ...
  }
}
```

Option B - Conditional creation (safer):
```hcl
variable "enable_chat_processor" {
  description = "Enable deprecated chat_processor Lambda"
  type        = bool
  default     = false
}

# Then wrap the SQS event source mapping:
resource "aws_lambda_event_source_mapping" "chat_processor_sqs" {
  count = var.enable_chat_processor && contains(keys(local.lambda_configs), "chat_processor") ? 1 : 0
  # ...
}
```

#### Step 2: Remove SQS Event Source Mapping

**File:** `chat-api/terraform/modules/lambda/main.tf` (lines 176-189)

Comment out or remove the SQS event source mapping:

```hcl
# DEPRECATED: chat_processor SQS integration
# Replaced by analysis_followup direct invocation
# resource "aws_lambda_event_source_mapping" "chat_processor_sqs" {
#   count = contains(keys(local.lambda_configs), "chat_processor") ? 1 : 0
#   ...
# }
```

#### Step 3: Remove from Build Script

**File:** `chat-api/backend/scripts/build_lambdas.sh`

Remove or comment out:
```bash
# DEPRECATED: chat_processor
# build_lambda "chat_processor"
```

#### Step 4: Clean Up Environment Variables

**File:** `chat-api/terraform/environments/dev/main.tf`

Remove from `lambda_function_env_vars`:
```hcl
lambda_function_env_vars = {
  # Remove chat_processor block
  # chat_processor = { ... }
}
```

#### Step 5: Archive Source Code

Move to archive folder:
```bash
mkdir -p chat-api/backend/src/handlers/_deprecated
mv chat-api/backend/src/handlers/chat_processor.py chat-api/backend/src/handlers/_deprecated/
```

---

## 7. Stripe Payment Integration

**Priority:** High
**Complexity:** High

### Architecture Overview

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Frontend  │───▶│ Payment API  │───▶│   Stripe    │
│  (React)    │    │  (Lambda)    │    │   Webhooks  │
└─────────────┘    └──────────────┘    └─────────────┘
                          │                    │
                          ▼                    ▼
                   ┌──────────────┐    ┌─────────────┐
                   │  Users Table │◀───│  Webhook    │
                   │  (DynamoDB)  │    │  Handler    │
                   └──────────────┘    └─────────────┘
```

### Implementation Steps

#### Step 1: Create Stripe Secret

**File:** `chat-api/terraform/modules/payments/secrets.tf` (new file)

```hcl
resource "aws_secretsmanager_secret" "stripe" {
  name        = "${var.project_name}-${var.environment}-stripe"
  description = "Stripe API keys and webhook secret"

  tags = var.common_tags
}

resource "aws_secretsmanager_secret_version" "stripe" {
  secret_id = aws_secretsmanager_secret.stripe.id
  secret_string = jsonencode({
    publishable_key  = var.stripe_publishable_key
    secret_key       = var.stripe_secret_key
    webhook_secret   = var.stripe_webhook_secret
    price_id_basic   = var.stripe_price_id_basic
    price_id_premium = var.stripe_price_id_premium
    price_id_pro     = var.stripe_price_id_pro
  })
}
```

#### Step 2: Create Payment Handler Lambda

**File:** `chat-api/backend/src/handlers/payment_handler.py` (new file)

```python
"""
Payment Handler - Stripe Integration

Handles:
- Create checkout session
- Manage subscriptions
- Handle Stripe webhooks

Subscription Tiers:
- free: Default, 5 requests/month
- basic: $9.99/month, 100 requests/month
- premium: $29.99/month, 500 requests/month
- pro: $99.99/month, unlimited requests
"""

import json
import os
import boto3
import stripe
import logging
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Stripe
secrets_client = boto3.client('secretsmanager')
dynamodb = boto3.resource('dynamodb')

STRIPE_SECRET_ARN = os.environ.get('STRIPE_SECRET_ARN')
USERS_TABLE = os.environ.get('USERS_TABLE')
TOKEN_USAGE_TABLE = os.environ.get('TOKEN_USAGE_TABLE')

# Subscription tier configurations
TIER_LIMITS = {
    'free': 5000,        # 5K tokens/month
    'basic': 50000,      # 50K tokens/month
    'premium': 250000,   # 250K tokens/month
    'pro': float('inf')  # Unlimited
}


def get_stripe_keys() -> Dict[str, str]:
    """Fetch Stripe keys from Secrets Manager."""
    response = secrets_client.get_secret_value(SecretId=STRIPE_SECRET_ARN)
    return json.loads(response['SecretString'])


def create_checkout_session(user_id: str, email: str, price_id: str, success_url: str, cancel_url: str) -> Dict[str, Any]:
    """Create a Stripe Checkout Session for subscription."""
    keys = get_stripe_keys()
    stripe.api_key = keys['secret_key']

    session = stripe.checkout.Session.create(
        customer_email=email,
        payment_method_types=['card'],
        line_items=[{
            'price': price_id,
            'quantity': 1,
        }],
        mode='subscription',
        success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=cancel_url,
        metadata={
            'user_id': user_id
        },
        subscription_data={
            'metadata': {
                'user_id': user_id
            }
        }
    )

    return {
        'session_id': session.id,
        'url': session.url
    }


def handle_webhook(payload: str, sig_header: str) -> Dict[str, Any]:
    """Handle Stripe webhook events."""
    keys = get_stripe_keys()
    stripe.api_key = keys['secret_key']
    webhook_secret = keys['webhook_secret']

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        return {'error': 'Invalid payload'}
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        return {'error': 'Invalid signature'}

    # Handle specific events
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        subscription_id = session['subscription']

        # Get subscription details
        subscription = stripe.Subscription.retrieve(subscription_id)
        price_id = subscription['items']['data'][0]['price']['id']

        # Map price_id to tier
        tier = map_price_to_tier(price_id, keys)

        # Update user in DynamoDB
        update_user_subscription(user_id, tier, subscription_id)

        logger.info(f"User {user_id} subscribed to {tier}")

    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        user_id = subscription['metadata'].get('user_id')
        if user_id:
            price_id = subscription['items']['data'][0]['price']['id']
            tier = map_price_to_tier(price_id, keys)
            update_user_subscription(user_id, tier, subscription['id'])

    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        user_id = subscription['metadata'].get('user_id')
        if user_id:
            # Downgrade to free tier
            update_user_subscription(user_id, 'free', None)
            logger.info(f"User {user_id} subscription cancelled, downgraded to free")

    return {'received': True}


def map_price_to_tier(price_id: str, keys: Dict[str, str]) -> str:
    """Map Stripe price ID to subscription tier."""
    if price_id == keys.get('price_id_basic'):
        return 'basic'
    elif price_id == keys.get('price_id_premium'):
        return 'premium'
    elif price_id == keys.get('price_id_pro'):
        return 'pro'
    return 'free'


def update_user_subscription(user_id: str, tier: str, subscription_id: str = None):
    """Update user's subscription tier in DynamoDB."""
    users_table = dynamodb.Table(USERS_TABLE)
    token_table = dynamodb.Table(TOKEN_USAGE_TABLE)
    now = datetime.utcnow().isoformat() + 'Z'
    current_month = datetime.utcnow().strftime('%Y-%m')

    # Update users table
    update_expr = 'SET subscription_tier = :tier, updated_at = :now'
    expr_values = {':tier': tier, ':now': now}

    if subscription_id:
        update_expr += ', stripe_subscription_id = :sub_id, subscribed_at = if_not_exists(subscribed_at, :now)'
        expr_values[':sub_id'] = subscription_id
    else:
        update_expr += ' REMOVE stripe_subscription_id'

    users_table.update_item(
        Key={'user_id': user_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values
    )

    # Update token limit for current month
    token_limit = TIER_LIMITS.get(tier, TIER_LIMITS['free'])
    if token_limit != float('inf'):
        token_table.update_item(
            Key={'user_id': user_id, 'month': current_month},
            UpdateExpression='SET token_limit = :limit',
            ExpressionAttributeValues={':limit': int(token_limit)}
        )


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for payment operations."""
    path = event.get('rawPath', event.get('path', ''))
    method = event.get('requestContext', {}).get('http', {}).get('method',
              event.get('httpMethod', 'GET'))

    try:
        if path.endswith('/checkout') and method == 'POST':
            # Create checkout session
            body = json.loads(event.get('body', '{}'))
            result = create_checkout_session(
                user_id=body['user_id'],
                email=body['email'],
                price_id=body['price_id'],
                success_url=body['success_url'],
                cancel_url=body['cancel_url']
            )
            return success_response(result)

        elif path.endswith('/webhook') and method == 'POST':
            # Handle Stripe webhook
            body = event.get('body', '')
            sig_header = event.get('headers', {}).get('stripe-signature', '')
            result = handle_webhook(body, sig_header)
            return success_response(result)

        elif path.endswith('/subscription') and method == 'GET':
            # Get user's subscription status
            user_id = event.get('queryStringParameters', {}).get('user_id')
            if not user_id:
                return error_response(400, 'user_id required')

            users_table = dynamodb.Table(USERS_TABLE)
            response = users_table.get_item(Key={'user_id': user_id})
            user = response.get('Item', {})

            return success_response({
                'subscription_tier': user.get('subscription_tier', 'free'),
                'subscribed_at': user.get('subscribed_at'),
                'stripe_subscription_id': user.get('stripe_subscription_id')
            })

        else:
            return error_response(404, 'Not found')

    except Exception as e:
        logger.error(f"Payment handler error: {e}", exc_info=True)
        return error_response(500, str(e))


def success_response(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(data)
    }


def error_response(status: int, message: str) -> Dict[str, Any]:
    return {
        'statusCode': status,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({'error': message})
    }
```

#### Step 3: Create Terraform Module

**File:** `chat-api/terraform/modules/payments/main.tf` (new file)

```hcl
# Payments Module - Stripe Integration

variable "project_name" {}
variable "environment" {}
variable "lambda_role_arn" {}
variable "lambda_package_path" {}
variable "dependencies_layer_arn" {}
variable "users_table_name" {}
variable "users_table_arn" {}
variable "token_usage_table_name" {}
variable "token_usage_table_arn" {}
variable "common_tags" {}

# Stripe secrets (passed from environment)
variable "stripe_publishable_key" { sensitive = true }
variable "stripe_secret_key" { sensitive = true }
variable "stripe_webhook_secret" { sensitive = true }
variable "stripe_price_id_basic" {}
variable "stripe_price_id_premium" {}
variable "stripe_price_id_pro" {}

# Lambda function
resource "aws_lambda_function" "payment_handler" {
  function_name = "${var.project_name}-${var.environment}-payment-handler"
  role          = var.lambda_role_arn
  handler       = "payment_handler.lambda_handler"
  runtime       = "python3.11"
  timeout       = 30
  memory_size   = 256

  filename         = "${var.lambda_package_path}/payment_handler.zip"
  source_code_hash = filebase64sha256("${var.lambda_package_path}/payment_handler.zip")

  layers = [var.dependencies_layer_arn]

  environment {
    variables = {
      STRIPE_SECRET_ARN   = aws_secretsmanager_secret.stripe.arn
      USERS_TABLE         = var.users_table_name
      TOKEN_USAGE_TABLE   = var.token_usage_table_name
      ENVIRONMENT         = var.environment
    }
  }

  tags = var.common_tags
}

# IAM policy for payment Lambda
resource "aws_iam_policy" "payment_lambda_policy" {
  name = "${var.project_name}-${var.environment}-payment-lambda-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = [aws_secretsmanager_secret.stripe.arn]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:PutItem"
        ]
        Resource = [
          var.users_table_arn,
          var.token_usage_table_arn
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "payment_lambda_policy" {
  policy_arn = aws_iam_policy.payment_lambda_policy.arn
  role       = split("/", var.lambda_role_arn)[1]
}

# Function URL for webhook (Stripe needs direct URL)
resource "aws_lambda_function_url" "payment_webhook" {
  function_name      = aws_lambda_function.payment_handler.function_name
  authorization_type = "NONE"  # Stripe validates via signature
}

output "payment_handler_arn" {
  value = aws_lambda_function.payment_handler.arn
}

output "webhook_url" {
  value = aws_lambda_function_url.payment_webhook.function_url
}
```

#### Step 4: Frontend Integration

**File:** `frontend/src/components/payments/SubscriptionModal.jsx` (new file)

```jsx
import React, { useState } from 'react';
import { loadStripe } from '@stripe/stripe-js';

const stripePromise = loadStripe(import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY);

const PLANS = [
  {
    id: 'basic',
    name: 'Basic',
    price: '$9.99',
    period: '/month',
    tokens: '50,000',
    features: ['50K tokens/month', 'Email support', 'Basic analytics'],
  },
  {
    id: 'premium',
    name: 'Premium',
    price: '$29.99',
    period: '/month',
    tokens: '250,000',
    features: ['250K tokens/month', 'Priority support', 'Advanced analytics', 'API access'],
    popular: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    price: '$99.99',
    period: '/month',
    tokens: 'Unlimited',
    features: ['Unlimited tokens', '24/7 support', 'Custom integrations', 'Dedicated account manager'],
  },
];

export default function SubscriptionModal({ isOpen, onClose, user, currentTier }) {
  const [loading, setLoading] = useState(false);

  const handleSubscribe = async (planId) => {
    setLoading(true);
    try {
      const response = await fetch(`${import.meta.env.VITE_REST_API_URL}/payments/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.id,
          email: user.email,
          price_id: import.meta.env[`VITE_STRIPE_PRICE_${planId.toUpperCase()}`],
          success_url: window.location.origin + '/subscription/success',
          cancel_url: window.location.origin + '/subscription/cancel',
        }),
      });

      const { url } = await response.json();
      window.location.href = url;
    } catch (error) {
      console.error('Checkout error:', error);
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div className="bg-gray-900 rounded-xl p-6 max-w-4xl w-full mx-4">
        <h2 className="text-2xl font-bold text-center mb-6">Choose Your Plan</h2>

        <div className="grid md:grid-cols-3 gap-6">
          {PLANS.map((plan) => (
            <div
              key={plan.id}
              className={`rounded-lg p-6 ${
                plan.popular
                  ? 'bg-gradient-to-br from-blue-600 to-purple-600 ring-2 ring-blue-400'
                  : 'bg-gray-800'
              }`}
            >
              {plan.popular && (
                <span className="bg-yellow-500 text-black text-xs font-bold px-2 py-1 rounded mb-4 inline-block">
                  MOST POPULAR
                </span>
              )}
              <h3 className="text-xl font-bold">{plan.name}</h3>
              <div className="mt-2">
                <span className="text-3xl font-bold">{plan.price}</span>
                <span className="text-gray-400">{plan.period}</span>
              </div>
              <p className="text-sm text-gray-300 mt-1">{plan.tokens} tokens</p>

              <ul className="mt-4 space-y-2">
                {plan.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm">
                    <span className="text-green-400">✓</span>
                    {feature}
                  </li>
                ))}
              </ul>

              <button
                onClick={() => handleSubscribe(plan.id)}
                disabled={loading || currentTier === plan.id}
                className={`w-full mt-6 py-2 rounded-lg font-semibold transition ${
                  currentTier === plan.id
                    ? 'bg-gray-600 cursor-not-allowed'
                    : 'bg-white text-black hover:bg-gray-200'
                }`}
              >
                {currentTier === plan.id ? 'Current Plan' : 'Subscribe'}
              </button>
            </div>
          ))}
        </div>

        <button
          onClick={onClose}
          className="mt-6 w-full py-2 text-gray-400 hover:text-white transition"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
```

---

## 8. Token Limiter Polish

**Priority:** High
**Complexity:** Low

### Current Issues

1. Usage notifications at 80%/90% are tracked but not displayed to users
2. No UI indicator showing remaining tokens
3. Rate limit headers exist but frontend doesn't use them

### Implementation

#### Step 1: Add Token Usage Display Component

**File:** `frontend/src/components/TokenUsageIndicator.jsx` (new file)

```jsx
import React, { useState, useEffect } from 'react';
import { AlertTriangle, Zap } from 'lucide-react';

export default function TokenUsageIndicator({ tokenUsage, onUpgrade }) {
  if (!tokenUsage) return null;

  const { total_tokens, token_limit, percent_used, remaining_tokens, reset_date } = tokenUsage;

  // Determine color based on usage
  let barColor = 'bg-green-500';
  let showWarning = false;

  if (percent_used >= 90) {
    barColor = 'bg-red-500';
    showWarning = true;
  } else if (percent_used >= 80) {
    barColor = 'bg-yellow-500';
    showWarning = true;
  } else if (percent_used >= 60) {
    barColor = 'bg-blue-500';
  }

  // Format reset date
  const resetDate = reset_date ? new Date(reset_date).toLocaleDateString() : 'next month';

  return (
    <div className="bg-gray-800 rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-yellow-400" />
          <span className="text-sm font-medium">Token Usage</span>
        </div>
        <span className="text-xs text-gray-400">
          Resets {resetDate}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div
          className={`h-full ${barColor} transition-all duration-500`}
          style={{ width: `${Math.min(percent_used, 100)}%` }}
        />
      </div>

      {/* Stats */}
      <div className="flex justify-between mt-2 text-xs text-gray-400">
        <span>{total_tokens.toLocaleString()} used</span>
        <span>{remaining_tokens.toLocaleString()} remaining</span>
      </div>

      {/* Warning message */}
      {showWarning && (
        <div className="mt-3 flex items-center gap-2 p-2 bg-yellow-500/10 rounded border border-yellow-500/30">
          <AlertTriangle className="w-4 h-4 text-yellow-500" />
          <span className="text-xs text-yellow-200">
            {percent_used >= 100
              ? 'Token limit reached. Upgrade for more.'
              : `${Math.round(percent_used)}% of monthly limit used.`}
          </span>
          <button
            onClick={onUpgrade}
            className="ml-auto text-xs bg-yellow-500 text-black px-2 py-1 rounded hover:bg-yellow-400 transition"
          >
            Upgrade
          </button>
        </div>
      )}
    </div>
  );
}
```

#### Step 2: Update ResearchContext to Track Token Usage

**File:** `frontend/src/contexts/ResearchContext.jsx`

Add to initial state:

```javascript
const initialState = {
  // ... existing state ...
  tokenUsage: null, // { total_tokens, token_limit, percent_used, remaining_tokens, reset_date }
};

// Add action
const ACTIONS = {
  // ... existing ...
  SET_TOKEN_USAGE: 'SET_TOKEN_USAGE',
};

// Add reducer case
case ACTIONS.SET_TOKEN_USAGE:
  return {
    ...state,
    tokenUsage: action.tokenUsage,
  };
```

Update SSE event handler to capture token usage:

```javascript
case 'complete':
  if (data.token_usage) {
    dispatch({ type: ACTIONS.SET_TOKEN_USAGE, tokenUsage: data.token_usage });
  }
  dispatch({ type: ACTIONS.SET_STATUS, status: 'complete' });
  break;
```

#### Step 3: Add Token Limit Error Handling

**File:** `frontend/src/contexts/ResearchContext.jsx`

Add handling for token limit exceeded:

```javascript
case 'token_limit_exceeded':
  dispatch({
    type: ACTIONS.SET_ERROR,
    error: 'Monthly token limit reached. Please upgrade your plan or wait until next month.',
  });
  dispatch({
    type: ACTIONS.SET_TOKEN_USAGE,
    tokenUsage: data.usage,
  });
  break;
```

#### Step 4: Display Token Usage in UI

**File:** `frontend/src/App.jsx`

Add the indicator to the main layout:

```jsx
import TokenUsageIndicator from './components/TokenUsageIndicator';
import { useResearch } from './contexts/ResearchContext';

// In the component:
const { tokenUsage } = useResearch();

// In the render:
<TokenUsageIndicator
  tokenUsage={tokenUsage}
  onUpgrade={() => setShowSubscriptionModal(true)}
/>
```

---

## Implementation Priority Order

### Phase 1: Critical Path (Week 1)
1. ✅ Monthly Token Reset (already implemented)
2. Token Usage Table Enhancements
3. Lambda Concurrency Changes
4. Token Limiter Polish

### Phase 2: Core Features (Week 2)
5. Stripe Payment Integration
6. UI Collapsible Orchestrator Responses

### Phase 3: Cleanup & Enhancement (Week 3)
7. Deprecate Chat Processor Lambda
8. Financial Metrics Comparison Tool

---

## Testing Checklist

### Token System
- [ ] Verify monthly reset works at month boundary
- [ ] Test 80% and 90% threshold notifications
- [ ] Confirm hard cutoff at 100%
- [ ] Validate token counting accuracy

### Payments
- [ ] Create test Stripe products in test mode
- [ ] Test checkout flow end-to-end
- [ ] Verify webhook handles subscription events
- [ ] Test upgrade/downgrade tier transitions

### UI
- [ ] Test collapsible components on mobile
- [ ] Verify smooth animations
- [ ] Check accessibility (keyboard navigation)
- [ ] Test with screen readers

### Lambda
- [ ] Load test analysis_followup with increased concurrency
- [ ] Verify chat_processor removal doesn't break existing flows
- [ ] Test comparison tool with various ticker combinations

---

## Environment Variables Checklist

### Backend (add to Terraform)
```
STRIPE_SECRET_ARN
STRIPE_WEBHOOK_SECRET
```

### Frontend (add to .env)
```
VITE_STRIPE_PUBLISHABLE_KEY
VITE_STRIPE_PRICE_BASIC
VITE_STRIPE_PRICE_PREMIUM
VITE_STRIPE_PRICE_PRO
```

---

## Notes

- All Stripe operations should use test mode keys until production launch
- Consider implementing proration for mid-cycle plan changes
- Add monitoring for token usage patterns to inform tier pricing
- Consider adding annual billing option (typically 15-20% discount)
