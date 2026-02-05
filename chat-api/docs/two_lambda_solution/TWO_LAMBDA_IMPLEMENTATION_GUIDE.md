# Two Lambda Architecture - Implementation Guide

**Document Version:** 1.0
**Date:** December 12, 2025
**Related Document:** [TWO_LAMBDA_ARCHITECTURE.md](./TWO_LAMBDA_ARCHITECTURE.md)

---

## Overview

This guide walks through implementing the two-Lambda architecture to resolve the Bedrock action group response format issue.

### Lambda Names

| Lambda | Full Name | Purpose |
|--------|-----------|---------|
| Existing | `buffett-dev-prediction-ensemble` | User-facing HTTP streaming (LWA + FastAPI) |
| **New** | `buffett-dev-ensemble-prediction-data-fetcher-action` | Bedrock action groups (pure Python) |

### Prerequisites

- [ ] AWS CLI configured with appropriate credentials
- [ ] Terraform >= 1.0 installed
- [ ] Access to dev environment
- [ ] Existing `prediction-ensemble` Lambda working

---

## Phase 1: Create Lambda Infrastructure (Terraform)

### 1.1 Create Lambda Module File

**File:** `chat-api/terraform/modules/lambda/data_fetcher_action.tf`

```hcl
# =============================================================================
# ENSEMBLE PREDICTION DATA FETCHER ACTION LAMBDA
# =============================================================================
# Purpose: Handle Bedrock action group invocations
# Key: NO Lambda Web Adapter, NO FastAPI - returns exact Bedrock JSON format
# =============================================================================

# -----------------------------------------------------------------------------
# Lambda Function
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "ensemble_prediction_data_fetcher_action" {
  function_name = "${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
  description   = "Bedrock action group handler - fetches financial data and runs ML inference"

  # Use zip package (NOT Docker) - simpler for pure Python
  filename         = "${path.module}/../../../backend/build/ensemble_prediction_data_fetcher_action.zip"
  source_code_hash = filebase64sha256("${path.module}/../../../backend/build/ensemble_prediction_data_fetcher_action.zip")

  handler = "handler.lambda_handler"
  runtime = "python3.11"

  timeout     = 120  # 2 minutes for FMP API + ML inference
  memory_size = 1024 # Sufficient for XGBoost models

  role = aws_iam_role.ensemble_prediction_data_fetcher_action.arn

  # Use existing Lambda layer with dependencies
  layers = [
    var.lambda_layer_arn
  ]

  environment {
    variables = {
      ENVIRONMENT          = var.environment
      FMP_API_KEY_ARN      = var.fmp_api_key_arn
      ML_MODELS_BUCKET     = var.ml_models_bucket
      MODEL_S3_PREFIX      = "ensemble/v1"
      DYNAMODB_CACHE_TABLE = var.dynamodb_cache_table
      LOG_LEVEL            = "INFO"
    }
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
    Environment = var.environment
    Purpose     = "bedrock-action-group"
    Type        = "data-fetcher"
  }
}

# -----------------------------------------------------------------------------
# IAM Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ensemble_prediction_data_fetcher_action" {
  name = "${var.project_name}-${var.environment}-data-fetcher-action-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-${var.environment}-data-fetcher-action-role"
    Environment = var.environment
  }
}

# -----------------------------------------------------------------------------
# IAM Policy
# -----------------------------------------------------------------------------
resource "aws_iam_role_policy" "ensemble_prediction_data_fetcher_action" {
  name = "${var.project_name}-${var.environment}-data-fetcher-action-policy"
  role = aws_iam_role.ensemble_prediction_data_fetcher_action.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      # Secrets Manager (FMP API Key)
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.fmp_api_key_arn
      },
      # S3 (ML Models)
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.ml_models_bucket}",
          "arn:aws:s3:::${var.ml_models_bucket}/*"
        ]
      },
      # DynamoDB (Cache)
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:Query"
        ]
        Resource = "arn:aws:dynamodb:*:*:table/${var.dynamodb_cache_table}"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# CloudWatch Log Group
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "ensemble_prediction_data_fetcher_action" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-ensemble-prediction-data-fetcher-action"
  retention_in_days = 14

  tags = {
    Name        = "${var.project_name}-${var.environment}-data-fetcher-action-logs"
    Environment = var.environment
  }
}

# -----------------------------------------------------------------------------
# Bedrock Permission (allows Bedrock to invoke this Lambda)
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "bedrock_invoke_data_fetcher" {
  statement_id  = "AllowBedrockInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ensemble_prediction_data_fetcher_action.function_name
  principal     = "bedrock.amazonaws.com"

  # Optionally restrict to specific agent ARNs
  # source_arn = "arn:aws:bedrock:${var.aws_region}:${var.aws_account_id}:agent/*"
}
```

### 1.2 Add Output Variables

**File:** `chat-api/terraform/modules/lambda/outputs.tf` (add to existing)

```hcl
# -----------------------------------------------------------------------------
# Ensemble Prediction Data Fetcher Action Lambda Outputs
# -----------------------------------------------------------------------------
output "ensemble_prediction_data_fetcher_action_arn" {
  description = "ARN of the data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.arn
}

output "ensemble_prediction_data_fetcher_action_name" {
  description = "Name of the data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.function_name
}

output "ensemble_prediction_data_fetcher_action_invoke_arn" {
  description = "Invoke ARN of the data fetcher action Lambda"
  value       = aws_lambda_function.ensemble_prediction_data_fetcher_action.invoke_arn
}
```

### 1.3 Add Variables (if needed)

**File:** `chat-api/terraform/modules/lambda/variables.tf` (add if not exists)

```hcl
variable "dynamodb_cache_table" {
  description = "DynamoDB table for caching financial data"
  type        = string
  default     = ""
}
```

### Phase 1 Verification

```bash
cd chat-api/terraform/environments/dev

# Validate Terraform configuration
terraform validate

# Check what will be created
terraform plan -target=module.lambda.aws_lambda_function.ensemble_prediction_data_fetcher_action

# Expected output:
# + aws_lambda_function.ensemble_prediction_data_fetcher_action
# + aws_iam_role.ensemble_prediction_data_fetcher_action
# + aws_iam_role_policy.ensemble_prediction_data_fetcher_action
# + aws_cloudwatch_log_group.ensemble_prediction_data_fetcher_action
# + aws_lambda_permission.bedrock_invoke_data_fetcher
```

---

## Phase 2: Implement Lambda Handler Code

### 2.1 Create Directory Structure

```bash
mkdir -p chat-api/backend/lambda/ensemble_prediction_data_fetcher_action
```

### 2.2 Create Handler File

**File:** `chat-api/backend/lambda/ensemble_prediction_data_fetcher_action/handler.py`

```python
"""
Ensemble Prediction Data Fetcher Action Lambda

Purpose: Handle Bedrock action group invocations
Key: Returns EXACT Bedrock JSON format - no HTTP transformation

This Lambda:
1. Receives action group events directly from Bedrock
2. Fetches financial data from FMP API
3. Runs XGBoost ML inference
4. Returns properly formatted Bedrock response
"""

import json
import logging
import os
from typing import Any, Dict, Optional
from decimal import Decimal

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal serialization for DynamoDB data."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Bedrock action group invocations.

    Args:
        event: Bedrock action group event
        context: Lambda context

    Returns:
        Properly formatted Bedrock action group response
    """
    logger.info(f"[DATA_FETCHER] Received event: {json.dumps(event)}")

    try:
        # Parse Bedrock action group event
        action_group = event.get('actionGroup', 'FinancialAnalysis')
        api_path = event.get('apiPath', '/analyze')
        http_method = event.get('httpMethod', 'POST')

        # Extract parameters from request body
        request_body = event.get('requestBody', {})
        parameters = extract_parameters(request_body)

        ticker = parameters.get('ticker', '').upper()
        analysis_type = parameters.get('analysis_type', 'debt')

        logger.info(f"[DATA_FETCHER] Processing: ticker={ticker}, type={analysis_type}")

        if not ticker:
            return format_error_response(
                action_group=action_group,
                api_path=api_path,
                http_method=http_method,
                error_message="Missing required parameter: ticker"
            )

        # Fetch financial data
        financial_data = fetch_financial_data(ticker)

        if not financial_data:
            return format_error_response(
                action_group=action_group,
                api_path=api_path,
                http_method=http_method,
                error_message=f"Could not fetch financial data for {ticker}"
            )

        # Run ML inference
        inference_result = run_ml_inference(financial_data, analysis_type)

        # Compute value investor metrics
        value_metrics = compute_value_metrics(financial_data, analysis_type)

        # Build response body
        response_body = {
            'ticker': ticker,
            'analysis_type': analysis_type,
            'model_inference': inference_result,
            'value_metrics': value_metrics,
            'data_source': 'FMP API',
            'quarters_available': len(value_metrics.get(list(value_metrics.keys())[0], [])) if value_metrics else 0
        }

        logger.info(f"[DATA_FETCHER] Successfully processed {ticker}: {inference_result.get('prediction')} ({inference_result.get('confidence', 0):.0%})")

        # Return EXACT Bedrock format
        return format_success_response(
            action_group=action_group,
            api_path=api_path,
            http_method=http_method,
            response_body=response_body
        )

    except Exception as e:
        logger.error(f"[DATA_FETCHER] Error: {str(e)}", exc_info=True)
        return format_error_response(
            action_group=event.get('actionGroup', 'FinancialAnalysis'),
            api_path=event.get('apiPath', '/analyze'),
            http_method=event.get('httpMethod', 'POST'),
            error_message=f"Internal error: {str(e)}"
        )


def extract_parameters(request_body: Dict[str, Any]) -> Dict[str, str]:
    """
    Extract parameters from Bedrock action group request body.

    Bedrock sends parameters in this format:
    {
        "content": {
            "application/json": {
                "properties": [
                    {"name": "ticker", "type": "string", "value": "AAPL"},
                    {"name": "analysis_type", "type": "string", "value": "debt"}
                ]
            }
        }
    }
    """
    parameters = {}

    try:
        content = request_body.get('content', {})
        json_content = content.get('application/json', {})
        properties = json_content.get('properties', [])

        for prop in properties:
            name = prop.get('name')
            value = prop.get('value')
            if name and value:
                parameters[name] = value

    except Exception as e:
        logger.warning(f"[DATA_FETCHER] Error parsing parameters: {e}")

    return parameters


def format_success_response(
    action_group: str,
    api_path: str,
    http_method: str,
    response_body: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Format a successful response in EXACT Bedrock action group format.

    CRITICAL: The responseBody must have:
    - Key: "application/json" (no charset!)
    - Value: {"body": "<JSON STRING>"} (not nested object!)
    """
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {  # <-- EXACT key, no charset suffix!
                    'body': json.dumps(response_body, cls=DecimalEncoder)  # <-- JSON STRING!
                }
            }
        }
    }


def format_error_response(
    action_group: str,
    api_path: str,
    http_method: str,
    error_message: str,
    status_code: int = 400
) -> Dict[str, Any]:
    """Format an error response in Bedrock action group format."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': http_method,
            'httpStatusCode': status_code,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'error': error_message})
                }
            }
        }
    }


# =============================================================================
# BUSINESS LOGIC (Import from shared modules or implement here)
# =============================================================================

def fetch_financial_data(ticker: str) -> Optional[Dict[str, Any]]:
    """
    Fetch financial data from FMP API.

    TODO: Import from shared utils or implement
    """
    # Import shared FMP client
    try:
        from utils.fmp_client import FMPClient

        client = FMPClient()

        # Fetch all three financial statements
        income_stmt = client.get_income_statement(ticker, limit=20)
        balance_sheet = client.get_balance_sheet(ticker, limit=20)
        cash_flow = client.get_cash_flow_statement(ticker, limit=20)

        if not income_stmt or not balance_sheet or not cash_flow:
            logger.warning(f"[DATA_FETCHER] Missing financial data for {ticker}")
            return None

        return {
            'ticker': ticker,
            'income_statement': income_stmt,
            'balance_sheet': balance_sheet,
            'cash_flow_statement': cash_flow
        }

    except ImportError:
        logger.error("[DATA_FETCHER] Could not import FMPClient")
        return None
    except Exception as e:
        logger.error(f"[DATA_FETCHER] Error fetching data: {e}")
        return None


def run_ml_inference(
    financial_data: Dict[str, Any],
    analysis_type: str
) -> Dict[str, Any]:
    """
    Run XGBoost ML inference.

    TODO: Import from shared modules or implement
    """
    try:
        from utils.feature_extractor import extract_features
        from services.inference import run_inference

        # Extract features
        features = extract_features(financial_data)

        # Run inference for the specified analysis type
        result = run_inference(features, analysis_type)

        return {
            'prediction': result.get('prediction', 'HOLD'),
            'confidence': result.get('confidence', 0.5),
            'probabilities': result.get('probabilities', {})
        }

    except ImportError as e:
        logger.warning(f"[DATA_FETCHER] ML modules not available: {e}")
        # Return placeholder if ML not available
        return {
            'prediction': 'HOLD',
            'confidence': 0.5,
            'probabilities': {'BUY': 0.25, 'HOLD': 0.5, 'SELL': 0.25},
            'note': 'ML inference not available'
        }
    except Exception as e:
        logger.error(f"[DATA_FETCHER] ML inference error: {e}")
        return {
            'prediction': 'HOLD',
            'confidence': 0.5,
            'error': str(e)
        }


def compute_value_metrics(
    financial_data: Dict[str, Any],
    analysis_type: str
) -> Dict[str, Any]:
    """
    Compute value investor metrics based on analysis type.

    Returns metrics as arrays with 20 quarters of history.
    """
    try:
        from utils.feature_extractor import FeatureExtractor

        extractor = FeatureExtractor(financial_data)

        if analysis_type == 'debt':
            return {
                'debt_to_equity': extractor.get_metric_history('debtToEquity'),
                'interest_coverage': extractor.get_metric_history('interestCoverage'),
                'net_debt_to_ebitda': extractor.get_metric_history('netDebtToEBITDA'),
                'current_ratio': extractor.get_metric_history('currentRatio'),
                'quick_ratio': extractor.get_metric_history('quickRatio'),
                'debt_to_assets': extractor.get_metric_history('debtToAssets'),
                'long_term_debt_to_cap': extractor.get_metric_history('longTermDebtToCapitalization'),
                'interest_expense': extractor.get_metric_history('interestExpense'),
                'total_debt': extractor.get_metric_history('totalDebt'),
                'cash_and_equivalents': extractor.get_metric_history('cashAndCashEquivalents')
            }

        elif analysis_type == 'cashflow':
            return {
                'free_cash_flow': extractor.get_metric_history('freeCashFlow'),
                'fcf_margin': extractor.get_metric_history('freeCashFlowMargin'),
                'fcf_yield': extractor.get_metric_history('freeCashFlowYield'),
                'operating_cash_flow': extractor.get_metric_history('operatingCashFlow'),
                'capex': extractor.get_metric_history('capitalExpenditure'),
                'capex_to_revenue': extractor.get_metric_history('capexToRevenue'),
                'cash_conversion': extractor.get_metric_history('cashConversionCycle'),
                'dividend_payout': extractor.get_metric_history('dividendPayoutRatio'),
                'share_buybacks': extractor.get_metric_history('shareRepurchases'),
                'fcf_per_share': extractor.get_metric_history('freeCashFlowPerShare')
            }

        elif analysis_type == 'growth':
            return {
                'roe': extractor.get_metric_history('returnOnEquity'),
                'roic': extractor.get_metric_history('returnOnInvestedCapital'),
                'roa': extractor.get_metric_history('returnOnAssets'),
                'gross_margin': extractor.get_metric_history('grossProfitMargin'),
                'operating_margin': extractor.get_metric_history('operatingMargin'),
                'net_margin': extractor.get_metric_history('netProfitMargin'),
                'revenue_growth': extractor.get_metric_history('revenueGrowth'),
                'earnings_growth': extractor.get_metric_history('netIncomeGrowth'),
                'eps_growth': extractor.get_metric_history('epsgrowth'),
                'revenue': extractor.get_metric_history('revenue')
            }

        else:
            logger.warning(f"[DATA_FETCHER] Unknown analysis type: {analysis_type}")
            return {}

    except ImportError:
        logger.warning("[DATA_FETCHER] FeatureExtractor not available")
        return {'note': 'Metrics computation not available'}
    except Exception as e:
        logger.error(f"[DATA_FETCHER] Error computing metrics: {e}")
        return {'error': str(e)}
```

### 2.3 Create Build Script

**File:** `chat-api/backend/scripts/build_data_fetcher_action.sh`

```bash
#!/bin/bash
set -e

# =============================================================================
# Build script for ensemble-prediction-data-fetcher-action Lambda
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$BACKEND_DIR/build"
LAMBDA_DIR="$BACKEND_DIR/lambda/ensemble_prediction_data_fetcher_action"
ZIP_NAME="ensemble_prediction_data_fetcher_action.zip"

echo "=========================================="
echo "Building ensemble-prediction-data-fetcher-action Lambda"
echo "=========================================="

# Create build directory
mkdir -p "$BUILD_DIR"

# Create temporary packaging directory
TEMP_DIR=$(mktemp -d)
echo "Using temp directory: $TEMP_DIR"

# Copy handler
echo "Copying handler..."
cp "$LAMBDA_DIR/handler.py" "$TEMP_DIR/"

# Copy shared utilities (if not using Lambda layer)
echo "Copying shared utilities..."
if [ -d "$BACKEND_DIR/src/utils" ]; then
    mkdir -p "$TEMP_DIR/utils"
    cp -r "$BACKEND_DIR/src/utils/"* "$TEMP_DIR/utils/"
fi

if [ -d "$BACKEND_DIR/src/services" ]; then
    mkdir -p "$TEMP_DIR/services"
    cp -r "$BACKEND_DIR/src/services/"* "$TEMP_DIR/services/"
fi

# Create __init__.py files
touch "$TEMP_DIR/utils/__init__.py" 2>/dev/null || true
touch "$TEMP_DIR/services/__init__.py" 2>/dev/null || true

# Create zip package
echo "Creating zip package..."
cd "$TEMP_DIR"
zip -r "$BUILD_DIR/$ZIP_NAME" . -x "*.pyc" -x "__pycache__/*" -x "*.so"

# Cleanup
rm -rf "$TEMP_DIR"

echo "=========================================="
echo "Build complete: $BUILD_DIR/$ZIP_NAME"
echo "Size: $(du -h "$BUILD_DIR/$ZIP_NAME" | cut -f1)"
echo "=========================================="
```

### Phase 2 Verification

```bash
# Make script executable
chmod +x chat-api/backend/scripts/build_data_fetcher_action.sh

# Build the Lambda package
./chat-api/backend/scripts/build_data_fetcher_action.sh

# Verify zip was created
ls -la chat-api/backend/build/ensemble_prediction_data_fetcher_action.zip

# Verify zip contents
unzip -l chat-api/backend/build/ensemble_prediction_data_fetcher_action.zip
```

---

## Phase 3: Wire Up to Bedrock Action Groups

### 3.1 Update Bedrock Module Variables

**File:** `chat-api/terraform/modules/bedrock/variables.tf` (add)

```hcl
variable "data_fetcher_action_lambda_arn" {
  description = "ARN of the ensemble-prediction-data-fetcher-action Lambda"
  type        = string
}
```

### 3.2 Update Action Group Configuration

**File:** `chat-api/terraform/modules/bedrock/main.tf`

Find the action group resources and update to use the new Lambda:

```hcl
# -----------------------------------------------------------------------------
# Action Groups - Point to NEW data fetcher Lambda
# -----------------------------------------------------------------------------

# Debt Expert Action Group
resource "aws_bedrockagent_agent_action_group" "debt_financial_analysis" {
  agent_id          = module.debt_expert.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Fetches financial data and ML predictions for debt analysis"

  action_group_executor {
    lambda = var.data_fetcher_action_lambda_arn  # <-- NEW LAMBDA
  }

  api_schema {
    payload = file("${path.module}/schemas/financial_analysis_action.yaml")
  }
}

# Cashflow Expert Action Group
resource "aws_bedrockagent_agent_action_group" "cashflow_financial_analysis" {
  agent_id          = module.cashflow_expert.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Fetches financial data and ML predictions for cashflow analysis"

  action_group_executor {
    lambda = var.data_fetcher_action_lambda_arn  # <-- NEW LAMBDA
  }

  api_schema {
    payload = file("${path.module}/schemas/financial_analysis_action.yaml")
  }
}

# Growth Expert Action Group
resource "aws_bedrockagent_agent_action_group" "growth_financial_analysis" {
  agent_id          = module.growth_expert.agent_id
  agent_version     = "DRAFT"
  action_group_name = "FinancialAnalysis"
  description       = "Fetches financial data and ML predictions for growth analysis"

  action_group_executor {
    lambda = var.data_fetcher_action_lambda_arn  # <-- NEW LAMBDA
  }

  api_schema {
    payload = file("${path.module}/schemas/financial_analysis_action.yaml")
  }
}
```

### 3.3 Update Dev Environment Main

**File:** `chat-api/terraform/environments/dev/main.tf`

```hcl
module "bedrock" {
  source = "../../modules/bedrock"

  # ... existing variables ...

  # Add new Lambda ARN
  data_fetcher_action_lambda_arn = module.lambda.ensemble_prediction_data_fetcher_action_arn
}
```

### Phase 3 Verification

```bash
cd chat-api/terraform/environments/dev

# Validate configuration
terraform validate

# Plan changes
terraform plan

# Expected changes:
# ~ aws_bedrockagent_agent_action_group.debt_financial_analysis
#   ~ action_group_executor.lambda: "...prediction-ensemble..." -> "...data-fetcher-action..."
# ~ aws_bedrockagent_agent_action_group.cashflow_financial_analysis
#   ~ action_group_executor.lambda: "...prediction-ensemble..." -> "...data-fetcher-action..."
# ~ aws_bedrockagent_agent_action_group.growth_financial_analysis
#   ~ action_group_executor.lambda: "...prediction-ensemble..." -> "...data-fetcher-action..."
```

---

## Phase 4: Testing and Verification

### 4.1 Unit Test - Lambda Handler

**File:** `chat-api/backend/tests/test_data_fetcher_action.py`

```python
"""
Unit tests for ensemble-prediction-data-fetcher-action Lambda
"""

import json
import pytest
from lambda.ensemble_prediction_data_fetcher_action.handler import (
    lambda_handler,
    extract_parameters,
    format_success_response,
    format_error_response
)


class TestExtractParameters:
    """Test parameter extraction from Bedrock format."""

    def test_extract_valid_parameters(self):
        request_body = {
            'content': {
                'application/json': {
                    'properties': [
                        {'name': 'ticker', 'type': 'string', 'value': 'AAPL'},
                        {'name': 'analysis_type', 'type': 'string', 'value': 'debt'}
                    ]
                }
            }
        }

        params = extract_parameters(request_body)

        assert params['ticker'] == 'AAPL'
        assert params['analysis_type'] == 'debt'

    def test_extract_empty_request(self):
        params = extract_parameters({})
        assert params == {}

    def test_extract_missing_properties(self):
        request_body = {'content': {'application/json': {}}}
        params = extract_parameters(request_body)
        assert params == {}


class TestResponseFormatting:
    """Test Bedrock response format compliance."""

    def test_success_response_format(self):
        response = format_success_response(
            action_group='FinancialAnalysis',
            api_path='/analyze',
            http_method='POST',
            response_body={'ticker': 'AAPL', 'prediction': 'BUY'}
        )

        # Verify structure
        assert response['messageVersion'] == '1.0'
        assert 'response' in response

        resp = response['response']
        assert resp['actionGroup'] == 'FinancialAnalysis'
        assert resp['apiPath'] == '/analyze'
        assert resp['httpMethod'] == 'POST'
        assert resp['httpStatusCode'] == 200

        # CRITICAL: Verify exact key format
        assert 'responseBody' in resp
        assert 'application/json' in resp['responseBody']  # No charset!
        assert 'application/json; charset=utf-8' not in resp['responseBody']

        # CRITICAL: Verify body is string, not object
        body = resp['responseBody']['application/json']['body']
        assert isinstance(body, str)

        # Verify body can be parsed as JSON
        parsed = json.loads(body)
        assert parsed['ticker'] == 'AAPL'

    def test_error_response_format(self):
        response = format_error_response(
            action_group='FinancialAnalysis',
            api_path='/analyze',
            http_method='POST',
            error_message='Test error'
        )

        assert response['response']['httpStatusCode'] == 400
        body = json.loads(response['response']['responseBody']['application/json']['body'])
        assert 'error' in body


class TestLambdaHandler:
    """Test main Lambda handler."""

    def test_missing_ticker_returns_error(self):
        event = {
            'actionGroup': 'FinancialAnalysis',
            'apiPath': '/analyze',
            'httpMethod': 'POST',
            'requestBody': {
                'content': {
                    'application/json': {
                        'properties': []
                    }
                }
            }
        }

        response = lambda_handler(event, None)

        assert response['response']['httpStatusCode'] == 400
        body = json.loads(response['response']['responseBody']['application/json']['body'])
        assert 'error' in body
        assert 'ticker' in body['error'].lower()


# Run with: pytest chat-api/backend/tests/test_data_fetcher_action.py -v
```

### 4.2 Integration Test - Direct Lambda Invocation

```bash
# Build and deploy first
./chat-api/backend/scripts/build_data_fetcher_action.sh
cd chat-api/terraform/environments/dev
terraform apply

# Test direct Lambda invocation
aws lambda invoke \
  --function-name buffett-dev-ensemble-prediction-data-fetcher-action \
  --payload '{
    "actionGroup": "FinancialAnalysis",
    "apiPath": "/analyze",
    "httpMethod": "POST",
    "requestBody": {
      "content": {
        "application/json": {
          "properties": [
            {"name": "ticker", "type": "string", "value": "AAPL"},
            {"name": "analysis_type", "type": "string", "value": "debt"}
          ]
        }
      }
    }
  }' \
  --cli-binary-format raw-in-base64-out \
  response.json

# Check response
cat response.json | jq .

# Verify response format
cat response.json | jq '.response.responseBody["application/json"]'
# Should show: {"body": "{...}"}  (body is a string)
```

### 4.3 Integration Test - Bedrock Agent Invocation

```bash
# Test via Bedrock agent (debt expert)
aws bedrock-agent-runtime invoke-agent \
  --agent-id <DEBT_AGENT_ID> \
  --agent-alias-id <DEBT_ALIAS_ID> \
  --session-id "test-$(date +%s)" \
  --input-text "Analyze Apple's debt position" \
  --output response_stream.json

# Check CloudWatch logs for data fetcher Lambda
aws logs tail /aws/lambda/buffett-dev-ensemble-prediction-data-fetcher-action \
  --since 5m --follow
```

### 4.4 End-to-End Test - Full Flow

```bash
# Test via the frontend or curl to streaming API
curl -X POST "https://<API_URL>/supervisor" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"company": "AAPL"}' \
  --no-buffer

# Verify:
# 1. SSE events stream correctly
# 2. Predictions appear (debt: SELL, cashflow: BUY, growth: BUY)
# 3. No dependencyFailedException in logs
```

### Phase 4 Verification Checklist

- [ ] Unit tests pass
- [ ] Lambda invocation returns correct format
- [ ] `application/json` key has no charset suffix
- [ ] `body` field is a JSON string, not object
- [ ] Bedrock agent receives data successfully
- [ ] No `dependencyFailedException` errors
- [ ] Expert agents generate analysis with real data
- [ ] End-to-end flow works through frontend

---

## Phase 5: Deployment and Rollout

### 5.1 Deployment Steps

```bash
# 1. Build Lambda package
./chat-api/backend/scripts/build_data_fetcher_action.sh

# 2. Validate Terraform
cd chat-api/terraform/environments/dev
terraform validate

# 3. Plan deployment
terraform plan -out=tfplan

# 4. Review changes carefully
# Expected:
# + New Lambda function
# + New IAM role/policy
# + New CloudWatch log group
# ~ Updated action groups (point to new Lambda)

# 5. Apply changes
terraform apply tfplan

# 6. Verify Lambda created
aws lambda get-function \
  --function-name buffett-dev-ensemble-prediction-data-fetcher-action

# 7. Test immediately
aws lambda invoke \
  --function-name buffett-dev-ensemble-prediction-data-fetcher-action \
  --payload '{"actionGroup":"FinancialAnalysis","apiPath":"/analyze","httpMethod":"POST","requestBody":{"content":{"application/json":{"properties":[{"name":"ticker","value":"AAPL"},{"name":"analysis_type","value":"debt"}]}}}}' \
  --cli-binary-format raw-in-base64-out \
  test_response.json

cat test_response.json | jq .
```

### 5.2 Rollback Procedure

If issues are detected:

```bash
# Option 1: Revert action groups to old Lambda via Terraform
# Update main.tf to use prediction-ensemble ARN, then:
terraform apply

# Option 2: Manual rollback via AWS CLI
aws bedrock-agent update-agent-action-group \
  --agent-id <AGENT_ID> \
  --agent-version DRAFT \
  --action-group-name FinancialAnalysis \
  --action-group-executor lambda=<OLD_LAMBDA_ARN>
```

### 5.3 Monitoring

```bash
# Watch Lambda logs
aws logs tail /aws/lambda/buffett-dev-ensemble-prediction-data-fetcher-action \
  --since 10m --follow

# Check for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/buffett-dev-ensemble-prediction-data-fetcher-action \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s000)

# Check Lambda metrics
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --dimensions Name=FunctionName,Value=buffett-dev-ensemble-prediction-data-fetcher-action \
  --start-time $(date -d '1 hour ago' -u +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Sum
```

---

## Summary Checklist

### Phase 1: Infrastructure
- [ ] Created `data_fetcher_action.tf`
- [ ] Added outputs to `outputs.tf`
- [ ] Terraform validates successfully
- [ ] Terraform plan shows expected resources

### Phase 2: Code
- [ ] Created handler.py with correct Bedrock format
- [ ] Created build script
- [ ] Lambda zip builds successfully
- [ ] Zip contains all required files

### Phase 3: Wiring
- [ ] Updated Bedrock module variables
- [ ] Updated action group configurations
- [ ] Updated dev environment main.tf
- [ ] Terraform plan shows action group updates

### Phase 4: Testing
- [ ] Unit tests pass
- [ ] Direct Lambda invocation works
- [ ] Response format is correct (no charset, body is string)
- [ ] Bedrock agent invocation works
- [ ] No `dependencyFailedException`
- [ ] End-to-end flow works

### Phase 5: Deployment
- [ ] Deployed to dev environment
- [ ] Lambda function created successfully
- [ ] Action groups updated successfully
- [ ] Monitoring in place
- [ ] Rollback procedure documented

---

## Appendix: Quick Reference

### Correct Bedrock Response Format

```json
{
    "messageVersion": "1.0",
    "response": {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "httpStatusCode": 200,
        "responseBody": {
            "application/json": {
                "body": "{\"ticker\":\"AAPL\",\"prediction\":\"BUY\"}"
            }
        }
    }
}
```

### Key Files

| File | Purpose |
|------|---------|
| `modules/lambda/data_fetcher_action.tf` | Terraform for new Lambda |
| `lambda/ensemble_prediction_data_fetcher_action/handler.py` | Lambda handler code |
| `scripts/build_data_fetcher_action.sh` | Build script |
| `modules/bedrock/main.tf` | Action group configuration |

### Commands

```bash
# Build
./chat-api/backend/scripts/build_data_fetcher_action.sh

# Deploy
cd chat-api/terraform/environments/dev && terraform apply

# Test
aws lambda invoke --function-name buffett-dev-ensemble-prediction-data-fetcher-action ...

# Logs
aws logs tail /aws/lambda/buffett-dev-ensemble-prediction-data-fetcher-action --follow
```

---

*Document created: December 12, 2025*
