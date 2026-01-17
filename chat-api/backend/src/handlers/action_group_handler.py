"""
Action Group Handler for Bedrock Agents

Handles action group invocations from the 3 expert agents (debt, cashflow, growth).
Supports two response formats:
1. Legacy (v3.6.5): Full response with computed_insights, ensemble_metrics, current_metrics
2. Value Investor (v1.0.0): Simplified response with top 10 metrics per agent

The action group allows agents to autonomously fetch financial analysis data
using the getFinancialAnalysis operation defined in the OpenAPI schema.
"""

import json
import boto3
import os
import logging
import pickle
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import numpy as np
from decimal import Decimal

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Import utilities
from utils.fmp_client import get_financial_data, normalize_ticker, validate_ticker
from utils.feature_extractor import (
    extract_all_features,
    extract_quarterly_trends,
    compute_trend_insights
)
from utils.ensemble_metrics import compute_ensemble_metrics

# Initialize AWS clients
s3_client = boto3.client('s3')

# Environment variables
MODEL_S3_BUCKET = os.environ.get('ML_MODELS_BUCKET', os.environ.get('MODEL_S3_BUCKET', 'buffett-dev-models'))
MODEL_S3_PREFIX = os.environ.get('MODEL_S3_PREFIX', 'ensemble/v1')

# Use value investor simplified response format by default
USE_VALUE_INVESTOR_FORMAT = os.environ.get('USE_VALUE_INVESTOR_FORMAT', 'true').lower() == 'true'

# Model cache (loaded once per Lambda instance)
_models_cache = {}

# Value Investor Metrics per Agent (v5.2 - comprehensive raw + temporal)
# Each agent gets ~24 metrics: Raw (current state) + Temporal (trends/velocity/acceleration)
VALUE_INVESTOR_METRICS = {
    'debt': [
        # === RAW METRICS (Current State) ===
        'debt_to_equity',                    # Leverage ratio
        'interest_coverage',                 # Debt service ability (EBIT/Interest)
        'current_ratio',                     # Liquidity (Current Assets/Liabilities)
        'net_debt_to_ebitda',                # Years to pay off debt
        'total_debt',                        # Absolute debt ($)
        'net_debt',                          # Debt minus cash ($)
        'cash_position',                     # Cash buffer ($)
        'debt_to_assets',                    # Leverage vs company size
        'quick_ratio',                       # Strict liquidity (no inventory)
        'fcf_to_debt',                       # Can FCF pay off debt?
        'ebitda',                            # Earnings power for coverage context
        # === TEMPORAL METRICS (Trends) ===
        'debt_to_equity_yoy',                # Leverage YoY change (%)
        'debt_to_equity_velocity_qoq',       # Speed of leverage change
        'debt_to_equity_acceleration_qoq',   # Is deleveraging speeding up?
        'debt_to_equity_trend_1yr',          # 1-year leverage direction
        'debt_to_equity_trend_2yr',          # 2-year leverage direction
        'interest_coverage_yoy',             # Coverage trend YoY (%)
        'net_debt_velocity_qoq',             # Cash vs debt momentum
        'net_debt_to_ebitda_yoy',            # YoY coverage change
        'net_debt_to_ebitda_trend_1yr',      # 1-year coverage trend
        'current_ratio_trend_1yr',           # Liquidity 1yr change
        'current_ratio_yoy',                 # YoY liquidity change
        'interest_expense_velocity_qoq',     # Rate sensitivity warning
        'is_deleveraging',                   # Direction flag (1=paying down)
    ],
    'cashflow': [
        # === RAW METRICS (Current State) ===
        'free_cash_flow',                    # FCF absolute ($)
        'operating_cash_flow',               # OCF absolute ($)
        'fcf_margin',                        # FCF/Revenue (%)
        'fcf_to_net_income',                 # Cash quality ratio
        'ocf_to_revenue',                    # Operating efficiency (%)
        'capex_intensity',                   # CapEx/Revenue (%)
        'shareholder_payout',                # Dividends + Buybacks ($)
        'fcf_payout_ratio',                  # Payout as % of FCF
        'capex',                             # Absolute CapEx ($)
        'dividends_paid',                    # Dividend returns ($)
        'share_buybacks',                    # Buyback amount ($)
        'net_income',                        # Accounting profit ($)
        'revenue',                           # Total sales ($)
        'cash',                              # Cash on hand ($)
        'ebitda',                            # Earnings power ($)
        # === TEMPORAL METRICS (Trends) ===
        'fcf_velocity_qoq',                  # Cash machine momentum
        'fcf_margin_acceleration',           # Efficiency trajectory
        'ocf_velocity_qoq',                  # Operating cash momentum
        'fcf_margin_trend_1yr',              # 1yr margin change
        'fcf_trend_4q',                      # 4-quarter FCF change
        'fcf_margin_velocity_qoq',           # Velocity of efficiency
        'ocf_to_revenue_yoy',                # YoY operating efficiency
        'capex_intensity_trend',             # Investment trend
    ],
    'growth': [
        # === RAW METRICS (Current State) ===
        'revenue',                           # Revenue absolute ($)
        'revenue_growth_yoy',                # YoY growth (%)
        'gross_margin',                      # Pricing power (%)
        'operating_margin',                  # Operational efficiency (%)
        'net_margin',                        # Bottom line (%)
        'eps',                               # Earnings per share ($)
        'eps_growth_yoy',                    # EPS YoY growth (%)
        'operating_income',                  # Profit from ops ($)
        'ebitda',                            # Earnings power ($)
        # === TEMPORAL METRICS (Trends) ===
        'revenue_growth_velocity',           # Is growth accelerating?
        'revenue_growth_acceleration',       # Second derivative of growth
        'revenue_growth_qoq',                # QoQ growth %
        'revenue_velocity_qoq',              # Speed of revenue change
        'operating_margin_momentum',         # Efficiency trend
        'operating_margin_trend_1yr',        # 1yr margin change
        'operating_margin_trend_2yr',        # 2yr margin change
        'operating_margin_velocity_qoq',     # Margin velocity
        'operating_margin_acceleration',     # Margin acceleration
        'gross_margin_trend_2yr',            # Pricing power trend
        'net_margin_trend_2yr',              # 2yr profitability trend
        'is_growth_accelerating',            # Boolean flag (1=yes)
        'margin_momentum_positive',          # Are margins expanding? (1=yes)
        'is_margin_expanding',               # QoQ margin growth (1=yes)
        'is_profitability_improving',        # YoY profit improvement (1=yes)
    ]
}


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        return super().default(obj)


def format_calendar_quarters(period_dates: List[str]) -> List[str]:
    """
    Convert period dates to calendar quarter format (e.g., "Q3 2024").

    Args:
        period_dates: List of date strings in various formats (e.g., "2024-09-30", "2024-Q3")

    Returns:
        List of calendar quarter strings (e.g., ["Q3 2024", "Q2 2024", ...])
    """
    calendar_quarters = []
    for date_str in period_dates:
        try:
            if not date_str:
                calendar_quarters.append("")
                continue

            # Handle different date formats
            if 'Q' in str(date_str):
                # Already in quarter format like "2024-Q3" or "Q3 2024"
                if '-Q' in date_str:
                    year, quarter = date_str.split('-Q')
                    calendar_quarters.append(f"Q{quarter} {year}")
                else:
                    calendar_quarters.append(date_str)
            else:
                # Parse as date (e.g., "2024-09-30")
                date_obj = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
                quarter = (date_obj.month - 1) // 3 + 1
                calendar_quarters.append(f"Q{quarter} {date_obj.year}")
        except Exception as e:
            logger.warning(f"Could not parse date '{date_str}': {e}")
            calendar_quarters.append(str(date_str))

    return calendar_quarters


def extract_value_metrics(quarterly_trends: Dict[str, Any],
                          features: Dict[str, Any],
                          analysis_type: str) -> Dict[str, Any]:
    """
    Extract only the value investor top 10 metrics per agent.

    For raw metrics, uses quarterly_trends (20-quarter arrays).
    For temporal metrics not in quarterly_trends, extracts from features.

    Args:
        quarterly_trends: Full quarterly trends data
        features: Extracted ML features
        analysis_type: 'debt', 'cashflow', 'growth', or 'all'

    Returns:
        Dict with only the top 10 metrics per agent (20-quarter arrays)
    """
    value_metrics = {}

    # Determine which agents to include
    if analysis_type == 'all':
        agents = ['debt', 'cashflow', 'growth']
    else:
        agents = [analysis_type]

    # Collect metrics for each agent
    for agent in agents:
        metric_names = VALUE_INVESTOR_METRICS.get(agent, [])
        for metric in metric_names:
            # First check quarterly_trends
            if metric in quarterly_trends:
                value_metrics[metric] = quarterly_trends[metric]
            # Check alternate naming (with underscores vs without)
            elif metric.replace('_', '') in quarterly_trends:
                value_metrics[metric] = quarterly_trends[metric.replace('_', '')]
            # For temporal metrics, try to build array from features
            elif features.get(agent, {}).get('current', {}).get(metric) is not None:
                # Get current value and fill array with same value (simplified)
                current_val = features[agent]['current'].get(metric, 0)
                value_metrics[metric] = [current_val] * 20
            else:
                # Metric not available, fill with None
                logger.warning(f"Metric '{metric}' not found for {agent} agent")
                value_metrics[metric] = [None] * 20

    # Add calendar quarter labels
    period_dates = quarterly_trends.get('period_dates', [])
    if period_dates:
        value_metrics['quarters'] = format_calendar_quarters(period_dates)
    else:
        # Generate placeholder quarters going back 5 years
        now = datetime.utcnow()
        quarters = []
        for i in range(20):
            q_date = now.replace(month=((now.month - 1 - (i * 3)) % 12) + 1)
            if (now.month - 1 - (i * 3)) < 0:
                q_date = q_date.replace(year=q_date.year - ((abs(now.month - 1 - (i * 3)) // 12) + 1))
            quarter = (q_date.month - 1) // 3 + 1
            quarters.append(f"Q{quarter} {q_date.year}")
        value_metrics['quarters'] = quarters

    return value_metrics


def load_model(model_type: str) -> Tuple[Any, Any, list]:
    """
    Load XGBoost model, scaler, and feature list from S3.

    Args:
        model_type: 'debt', 'cashflow', or 'growth'

    Returns:
        Tuple of (model, scaler, feature_cols)
    """
    global _models_cache

    if model_type in _models_cache:
        return _models_cache[model_type]

    try:
        model_key = f"{MODEL_S3_PREFIX}/{model_type}_model.pkl"
        scaler_key = f"{MODEL_S3_PREFIX}/{model_type}_scaler.pkl"
        features_key = f"{MODEL_S3_PREFIX}/{model_type}_features.pkl"

        logger.info(f"Loading {model_type} model from s3://{MODEL_S3_BUCKET}/{model_key}")

        # Load model
        model_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=model_key)
        model = pickle.loads(model_response['Body'].read())

        # Load scaler
        scaler_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=scaler_key)
        scaler = pickle.loads(scaler_response['Body'].read())

        # Load feature columns
        features_response = s3_client.get_object(Bucket=MODEL_S3_BUCKET, Key=features_key)
        features_data = pickle.loads(features_response['Body'].read())
        feature_cols = features_data.get('feature_cols', [])

        _models_cache[model_type] = (model, scaler, feature_cols)
        logger.info(f"Loaded {model_type} model with {len(feature_cols)} features")
        return model, scaler, feature_cols

    except Exception as e:
        logger.error(f"Failed to load {model_type} model: {e}")
        raise


def run_inference(model_type: str, features: dict) -> dict:
    """
    Run XGBoost inference with probability-based CI.

    Args:
        model_type: 'debt', 'cashflow', or 'growth'
        features: Extracted features dict

    Returns:
        dict with prediction, confidence, ci_width, probabilities
    """
    try:
        model, scaler, feature_cols = load_model(model_type)

        # Get features for this model type
        model_features = features.get(model_type, {}).get('current', {})

        # Build feature vector in correct order
        feature_vector = []
        for col in feature_cols:
            value = model_features.get(col, 0.0)
            if value is None:
                value = 0.0
            feature_vector.append(float(value))

        # Convert to numpy array and scale
        X = np.array([feature_vector])
        X_scaled = scaler.transform(X)

        # Get probability predictions
        probs = model.predict_proba(X_scaled)[0]

        # Map to class labels
        class_labels = ['SELL', 'HOLD', 'BUY']
        prediction_idx = int(np.argmax(probs))
        prediction = class_labels[prediction_idx]

        # Confidence = max probability
        confidence = float(max(probs))

        # CI width = 1 - gap between top two probabilities
        sorted_probs = sorted(probs, reverse=True)
        ci_width = 1.0 - (sorted_probs[0] - sorted_probs[1])

        # Confidence interpretation
        if confidence >= 0.7 and ci_width <= 0.3:
            confidence_interpretation = "STRONG"
        elif confidence >= 0.5 and ci_width <= 0.5:
            confidence_interpretation = "MODERATE"
        else:
            confidence_interpretation = "WEAK"

        logger.info(f"{model_type} inference: {prediction} ({confidence:.0%} confidence)")

        return {
            'prediction': prediction,
            'confidence': round(confidence, 2),
            'ci_width': round(ci_width, 2),
            'confidence_interpretation': confidence_interpretation,
            'probabilities': {
                'SELL': round(float(probs[0]), 2),
                'HOLD': round(float(probs[1]), 2),
                'BUY': round(float(probs[2]), 2)
            }
        }

    except Exception as e:
        logger.error(f"Inference failed for {model_type}: {e}")
        return {
            'prediction': 'HOLD',
            'confidence': 0.33,
            'ci_width': 0.95,
            'confidence_interpretation': 'WEAK',
            'probabilities': {'SELL': 0.33, 'HOLD': 0.34, 'BUY': 0.33},
            'error': str(e)
        }


def parse_action_group_parameters(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse parameters from Bedrock action group request.

    Bedrock sends parameters in a specific format within the event.

    Args:
        event: Lambda event from Bedrock action group

    Returns:
        Dict of parameter name -> value
    """
    parameters = {}

    # Try different parameter locations based on Bedrock action group format
    request_body = event.get('requestBody', {})
    content = request_body.get('content', {})
    app_json = content.get('application/json', {})
    properties = app_json.get('properties', [])

    # Parse properties list
    for prop in properties:
        name = prop.get('name')
        value = prop.get('value')
        if name and value is not None:
            parameters[name] = value

    # Also check for direct parameters (older format)
    if 'parameters' in event:
        for param in event['parameters']:
            parameters[param.get('name')] = param.get('value')

    logger.info(f"Parsed action group parameters: {parameters}")
    return parameters


def format_action_group_response(action_group: str, api_path: str,
                                  response_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Format response in Bedrock action group expected format.

    Args:
        action_group: Name of the action group
        api_path: API path that was called
        response_body: The response data to return

    Returns:
        Properly formatted action group response
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": "POST",
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": json.dumps(response_body, cls=DecimalEncoder)
                }
            }
        }
    }


def format_error_response(action_group: str, api_path: str,
                          error_message: str, status_code: int = 400) -> Dict[str, Any]:
    """
    Format error response in Bedrock action group format.

    Args:
        action_group: Name of the action group
        api_path: API path that was called
        error_message: Error message
        status_code: HTTP status code

    Returns:
        Formatted error response
    """
    return {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": action_group,
            "apiPath": api_path,
            "httpMethod": "POST",
            "httpStatusCode": status_code,
            "responseBody": {
                "application/json": {
                    "body": json.dumps({
                        "error": error_message,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    })
                }
            }
        }
    }


def get_financial_analysis(ticker: str, analysis_type: str = 'all') -> Dict[str, Any]:
    """
    Main analysis function that combines all data for the agent.
    Returns legacy v3.6.5 format with full computed_insights and ensemble_metrics.

    Args:
        ticker: Stock ticker symbol
        analysis_type: 'debt', 'cashflow', 'growth', or 'all'

    Returns:
        Complete analysis payload for the agent (legacy format)
    """
    start_time = datetime.utcnow()

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if not validate_ticker(normalized_ticker):
        raise ValueError(f"Invalid ticker: {ticker}")

    logger.info(f"Getting financial analysis for {normalized_ticker}, type={analysis_type}")

    # Fetch financial data (uses DynamoDB cache)
    financial_data = get_financial_data(normalized_ticker)
    if not financial_data or 'raw_financials' not in financial_data:
        raise ValueError(f"Could not fetch financial data for {normalized_ticker}")

    raw_financials = financial_data['raw_financials']

    # Extract features for ML inference
    features = extract_all_features(raw_financials)

    # Extract 20-quarter trends
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Compute trend insights (phases, inflections, peaks/troughs)
    computed_insights = compute_trend_insights(quarterly_trends)

    # Run ML inference
    if analysis_type == 'all':
        # Run all 3 models for ensemble
        inference_results = {
            'debt': run_inference('debt', features),
            'cashflow': run_inference('cashflow', features),
            'growth': run_inference('growth', features)
        }
        # Compute ensemble metrics
        ensemble_metrics = compute_ensemble_metrics(inference_results)

        # Current metrics for all types
        current_metrics = {
            'debt': features.get('debt', {}).get('current', {}),
            'cashflow': features.get('cashflow', {}).get('current', {}),
            'growth': features.get('growth', {}).get('current', {})
        }
    else:
        # Run single model
        inference_results = {
            analysis_type: run_inference(analysis_type, features)
        }
        ensemble_metrics = None
        current_metrics = features.get(analysis_type, {}).get('current', {})

    # Build response
    processing_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

    return {
        'ticker': normalized_ticker,
        'analysis_type': analysis_type,
        'model_inference': inference_results,
        'current_metrics': current_metrics,
        'quarterly_trends': quarterly_trends,
        'computed_insights': computed_insights,
        'ensemble_metrics': ensemble_metrics,
        'metadata': {
            'quarters_analyzed': len(quarterly_trends.get('quarters', [])),
            'processing_time_ms': round(processing_time_ms, 2),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'data_source': 'FMP',
            'model_version': 'v3.6.5'
        }
    }


def get_value_investor_analysis(ticker: str, analysis_type: str = 'all') -> Dict[str, Any]:
    """
    Simplified value investor analysis with top 10 metrics per agent.
    Returns v1.0.0 format designed for Buffett/Graham-style analysis.

    Args:
        ticker: Stock ticker symbol
        analysis_type: 'debt', 'cashflow', 'growth', or 'all'

    Returns:
        Simplified analysis payload with value_metrics (top 10 per agent)
    """
    start_time = datetime.utcnow()

    # Normalize and validate ticker
    normalized_ticker = normalize_ticker(ticker)
    if not validate_ticker(normalized_ticker):
        raise ValueError(f"Invalid ticker: {ticker}")

    logger.info(f"Getting value investor analysis for {normalized_ticker}, type={analysis_type}")

    # Fetch financial data (uses DynamoDB cache)
    financial_data = get_financial_data(normalized_ticker)
    if not financial_data or 'raw_financials' not in financial_data:
        raise ValueError(f"Could not fetch financial data for {normalized_ticker}")

    raw_financials = financial_data['raw_financials']

    # Extract features for ML inference (still need full features for ML models)
    features = extract_all_features(raw_financials)

    # Extract 20-quarter trends (for value metrics extraction)
    quarterly_trends = extract_quarterly_trends(raw_financials)

    # Extract only value investor metrics (top 10 per agent)
    value_metrics = extract_value_metrics(quarterly_trends, features, analysis_type)

    # Run ML inference
    if analysis_type == 'all':
        # Run all 3 models for ensemble
        inference_results = {
            'debt': run_inference('debt', features),
            'cashflow': run_inference('cashflow', features),
            'growth': run_inference('growth', features)
        }
    else:
        # Run single model
        inference_results = {
            analysis_type: run_inference(analysis_type, features)
        }

    # Build simplified response
    processing_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

    return {
        'ticker': normalized_ticker,
        'analysis_type': analysis_type,
        'model_inference': inference_results,
        'value_metrics': value_metrics,
        'metadata': {
            'quarters_analyzed': len(value_metrics.get('quarters', [])),
            'processing_time_ms': round(processing_time_ms, 2),
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'data_source': 'FMP',
            'model_version': 'v1.0.0'
        }
    }


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for Bedrock action group invocations.

    This handler is invoked by Bedrock when an agent calls the
    getFinancialAnalysis action defined in the OpenAPI schema.

    Request Format (from Bedrock):
    {
        "actionGroup": "FinancialAnalysis",
        "apiPath": "/analyze",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "value": "AAPL"},
                        {"name": "analysis_type", "value": "all"}
                    ]
                }
            }
        }
    }

    Response Format (to Bedrock):
    {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "FinancialAnalysis",
            "apiPath": "/analyze",
            "httpMethod": "POST",
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": "{...}"
                }
            }
        }
    }
    """
    logger.info(f"Action group handler invoked: {json.dumps(event, default=str)[:500]}")

    # Extract action group metadata
    action_group = event.get('actionGroup', 'FinancialAnalysis')
    api_path = event.get('apiPath', '/analyze')

    try:
        # Parse parameters
        parameters = parse_action_group_parameters(event)

        ticker = parameters.get('ticker')
        analysis_type = parameters.get('analysis_type', 'all')

        if not ticker:
            return format_error_response(
                action_group, api_path,
                "Missing required parameter: ticker",
                400
            )

        # Validate analysis_type
        valid_types = ['debt', 'cashflow', 'growth', 'all']
        if analysis_type not in valid_types:
            return format_error_response(
                action_group, api_path,
                f"Invalid analysis_type. Must be one of: {valid_types}",
                400
            )

        # Get financial analysis (use value investor format by default)
        if USE_VALUE_INVESTOR_FORMAT:
            response_body = get_value_investor_analysis(ticker, analysis_type)
            logger.info(f"Successfully analyzed {ticker} ({analysis_type}) [value investor format]")
        else:
            response_body = get_financial_analysis(ticker, analysis_type)
            logger.info(f"Successfully analyzed {ticker} ({analysis_type}) [legacy format]")

        return format_action_group_response(action_group, api_path, response_body)

    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        return format_error_response(action_group, api_path, str(e), 400)

    except Exception as e:
        logger.error(f"Action group handler error: {e}", exc_info=True)
        return format_error_response(action_group, api_path, str(e), 500)
