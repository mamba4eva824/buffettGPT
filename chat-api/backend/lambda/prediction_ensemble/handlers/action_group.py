"""
Bedrock Action Group Handler.
Handles synchronous action group invocations from Bedrock agents.

REFACTORED: Now imports run_inference from services.inference
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any

from utils.fmp_client import get_financial_data, normalize_ticker, validate_ticker
from utils.feature_extractor import extract_all_features, extract_quarterly_trends
from models.schemas import DecimalEncoder, json_dumps
from models.metrics import VALUE_INVESTOR_METRICS
from config.settings import USE_VALUE_INVESTOR_FORMAT
from services.inference import run_inference

logger = logging.getLogger(__name__)


def is_action_group_event(event: Dict[str, Any]) -> bool:
    """Check if event is a Bedrock action group invocation."""
    return 'actionGroup' in event and 'apiPath' in event


def parse_action_group_parameters(event: Dict[str, Any]) -> Dict[str, Any]:
    """Parse parameters from Bedrock action group event."""
    parameters = {}
    request_body = event.get('requestBody', {})
    content = request_body.get('content', {})
    json_content = content.get('application/json', {})
    properties = json_content.get('properties', [])

    for prop in properties:
        name = prop.get('name')
        value = prop.get('value')
        if name and value:
            parameters[name] = value

    return parameters


def format_action_group_response(action_group: str, api_path: str, response_body: Dict) -> Dict:
    """Format response for Bedrock action group.

    Uses json_dumps which sanitizes NaN/infinity values to produce valid JSON.
    Standard JSON does not support NaN/Infinity, and Bedrock will fail to parse
    responses containing these values (dependencyFailedException).
    """
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': 200,
            'responseBody': {
                'application/json': {
                    'body': json_dumps(response_body)
                }
            }
        }
    }


def format_action_group_error(action_group: str, api_path: str, error_msg: str, status_code: int = 500) -> Dict:
    """Format error response for Bedrock action group."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': action_group,
            'apiPath': api_path,
            'httpMethod': 'POST',
            'httpStatusCode': status_code,
            'responseBody': {
                'application/json': {
                    'body': json.dumps({'error': error_msg})
                }
            }
        }
    }


def extract_value_metrics(quarterly_trends: Dict, features: Dict, analysis_type: str) -> Dict:
    """
    Extract only the top 10 Value Investor metrics per agent.
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
            elif metric.replace('_', '') in quarterly_trends:
                value_metrics[metric] = quarterly_trends[metric.replace('_', '')]
            elif features.get(agent, {}).get('current', {}).get(metric) is not None:
                current_val = features[agent]['current'].get(metric, 0)
                value_metrics[metric] = [current_val] * 20
            else:
                logger.warning(f"Metric '{metric}' not found for {agent} agent")
                value_metrics[metric] = [None] * 20

    # Add calendar quarter labels and period dates for fiscal year grouping
    period_dates = quarterly_trends.get('period_dates', [])
    if period_dates:
        from models.schemas import format_calendar_quarters
        value_metrics['quarters'] = format_calendar_quarters(period_dates)
        value_metrics['period_dates'] = period_dates  # Include raw dates for fiscal year grouping
    else:
        now = datetime.utcnow()
        quarters = []
        for i in range(20):
            q_date = now.replace(month=((now.month - 1 - (i * 3)) % 12) + 1)
            if (now.month - 1 - (i * 3)) < 0:
                q_date = q_date.replace(year=q_date.year - ((abs(now.month - 1 - (i * 3)) // 12) + 1))
            quarter = (q_date.month - 1) // 3 + 1
            quarters.append(f"Q{quarter} {q_date.year}")
        value_metrics['quarters'] = quarters
        value_metrics['period_dates'] = []  # Empty list as fallback

    return value_metrics


def handle_action_group_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Bedrock action group invocation.

    Args:
        event: Bedrock action group event

    Returns:
        Action group response
    """
    action_group = event.get('actionGroup', 'FinancialAnalysis')
    api_path = event.get('apiPath', '/analyze')

    # [ACTION_GROUP_DEBUG] Log request entry
    logger.info("[ACTION_GROUP_DEBUG] === REQUEST START ===")
    logger.info(f"[ACTION_GROUP_DEBUG] Event keys: {list(event.keys())}")
    logger.info(f"[ACTION_GROUP_DEBUG] Full event: {json.dumps(event, default=str)[:2000]}")
    logger.info(f"Action group request: {action_group} {api_path}")

    try:
        # Parse parameters from action group event
        parameters = parse_action_group_parameters(event)
        ticker = parameters.get('ticker')
        analysis_type = parameters.get('analysis_type', 'all')
        skip_inference = str(parameters.get('skip_inference', 'false')).lower() == 'true'

        # [ACTION_GROUP_DEBUG] Log parsed parameters
        logger.info(f"[ACTION_GROUP_DEBUG] Parsed params: ticker={ticker}, analysis_type={analysis_type}, skip_inference={skip_inference}")

        if not ticker:
            return format_action_group_error(action_group, api_path, "Missing required parameter: ticker", 400)

        # Normalize and validate ticker
        ticker = normalize_ticker(ticker)
        if not validate_ticker(ticker):
            return format_action_group_error(action_group, api_path, f"Invalid ticker: {ticker}", 400)

        logger.info(f"Processing action group request for {ticker}, analysis_type={analysis_type}")

        # Get financial data
        financial_data = get_financial_data(ticker)
        if not financial_data or 'error' in financial_data:
            error_msg = financial_data.get('error', 'Failed to fetch financial data') if financial_data else 'Failed to fetch financial data'
            return format_action_group_error(action_group, api_path, error_msg, 500)

        raw_financials = financial_data.get('raw_financials', {})

        # [ACTION_GROUP_DEBUG] Log financial data received
        logger.info(f"[ACTION_GROUP_DEBUG] Financial data received: {bool(financial_data)}")
        logger.info(f"[ACTION_GROUP_DEBUG] Data keys: {list(financial_data.keys())}")
        logger.info(f"[ACTION_GROUP_DEBUG] Raw financials: balance_sheet={len(raw_financials.get('balance_sheet', []))}, "
                    f"income_statement={len(raw_financials.get('income_statement', []))}, "
                    f"cash_flow={len(raw_financials.get('cash_flow', []))}")

        # Extract features
        all_features = extract_all_features(raw_financials)
        quarterly_trends = extract_quarterly_trends(raw_financials)

        # [ACTION_GROUP_DEBUG] Log feature extraction results
        logger.info(f"[ACTION_GROUP_DEBUG] Features extracted: {list(all_features.keys())}")
        for ft, data in all_features.items():
            if isinstance(data, dict) and 'current' in data:
                logger.info(f"[ACTION_GROUP_DEBUG] {ft} current metrics: {list(data['current'].keys())[:5]}...")
        logger.info(f"[ACTION_GROUP_DEBUG] Quarterly trends: {len(quarterly_trends.get('quarters', []))} quarters")
        logger.info(f"[ACTION_GROUP_DEBUG] Trend metrics: {list(quarterly_trends.keys())[:10]}...")

        # Run ML inference for requested analysis types (unless skip_inference=true)
        model_inference = {}
        if not skip_inference:
            if analysis_type == 'all':
                model_types = ['debt', 'cashflow', 'growth']
            else:
                model_types = [analysis_type]

            for model_type in model_types:
                try:
                    result = run_inference(model_type, all_features)
                    model_inference[model_type] = result
                    # [ACTION_GROUP_DEBUG] Log each inference result
                    logger.info(f"[ACTION_GROUP_DEBUG] {model_type} inference: {json.dumps(result, default=str)}")
                except Exception as e:
                    logger.error(f"Inference failed for {model_type}: {e}")
                    model_inference[model_type] = {'error': str(e)}

            # [ACTION_GROUP_DEBUG] Log all inference results
            logger.info(f"[ACTION_GROUP_DEBUG] Model inference complete: {json.dumps(model_inference, default=str)}")
        else:
            logger.info(f"[ACTION_GROUP_DEBUG] Skipping inference for {ticker} - skip_inference=true (pre-computed inference provided in user message)")

        # Build response based on format setting
        if USE_VALUE_INVESTOR_FORMAT:
            value_metrics = extract_value_metrics(quarterly_trends, all_features, analysis_type)

            # [ACTION_GROUP_DEBUG] Log value metrics being sent to agents
            logger.info(f"[ACTION_GROUP_DEBUG] === VALUE METRICS FOR AGENTS ===")
            logger.info(f"[ACTION_GROUP_DEBUG] Value metrics keys: {list(value_metrics.keys())}")
            # Log sample values for key metrics
            for metric in ['debt_to_equity', 'free_cash_flow', 'roe', 'quarters']:
                if metric in value_metrics:
                    sample = value_metrics[metric][:3] if isinstance(value_metrics[metric], list) else value_metrics[metric]
                    logger.info(f"[ACTION_GROUP_DEBUG]   {metric}: {sample}")

            response_body = {
                'ticker': ticker,
                'analysis_type': analysis_type,
                'model_inference': model_inference,
                'value_metrics': value_metrics,
                'metadata': {
                    'quarters_analyzed': len(value_metrics.get('quarters', [])),
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'data_source': 'FMP',
                    'model_version': 'v1.0.0'
                }
            }

            # [ACTION_GROUP_DEBUG] Log response being returned
            logger.info(f"[ACTION_GROUP_DEBUG] Response body keys: {list(response_body.keys())}")
            logger.info(f"[ACTION_GROUP_DEBUG] Response size: {len(json.dumps(response_body, default=str))} bytes")
            logger.info(f"Successfully processed action group request for {ticker} [value investor format]")
        else:
            # Legacy format v3.6.5
            from utils.feature_extractor import compute_trend_insights
            computed_insights = compute_trend_insights(quarterly_trends)

            ensemble_metrics = None
            if analysis_type == 'all' and len(model_inference) == 3:
                try:
                    from utils.ensemble_metrics import compute_ensemble_metrics
                    ensemble_metrics = compute_ensemble_metrics(model_inference)
                except Exception as e:
                    logger.warning(f"Failed to compute ensemble metrics: {e}")

            if analysis_type == 'all':
                current_metrics = {
                    'debt': all_features.get('debt', {}),
                    'cashflow': all_features.get('cashflow', {}),
                    'growth': all_features.get('growth', {})
                }
            else:
                current_metrics = all_features.get(analysis_type, {})

            response_body = {
                'ticker': ticker,
                'analysis_type': analysis_type,
                'model_inference': model_inference,
                'current_metrics': current_metrics,
                'quarterly_trends': quarterly_trends,
                'computed_insights': computed_insights,
                'ensemble_metrics': ensemble_metrics,
                'metadata': {
                    'quarters_analyzed': len(quarterly_trends.get('quarters', [])),
                    'timestamp': datetime.utcnow().isoformat() + 'Z',
                    'data_source': 'FMP',
                    'model_version': 'v3.6.5'
                }
            }
            # [ACTION_GROUP_DEBUG] Log legacy response
            logger.info(f"[ACTION_GROUP_DEBUG] Response body keys: {list(response_body.keys())}")
            logger.info(f"[ACTION_GROUP_DEBUG] Response size: {len(json.dumps(response_body, default=str))} bytes")
            logger.info(f"Successfully processed action group request for {ticker} [legacy format]")

        logger.info("[ACTION_GROUP_DEBUG] === REQUEST END ===")
        final_response = format_action_group_response(action_group, api_path, response_body)
        # [ACTION_GROUP_DEBUG] Log the actual response being returned to Bedrock
        logger.info(f"[ACTION_GROUP_DEBUG] === FINAL RESPONSE TO BEDROCK ===")
        logger.info(f"[ACTION_GROUP_DEBUG] Response type: {type(final_response)}")
        logger.info(f"[ACTION_GROUP_DEBUG] Response structure: {json.dumps(final_response, default=str)[:2000]}")
        return final_response

    except Exception as e:
        logger.error(f"[ACTION_GROUP_DEBUG] === REQUEST ERROR ===")
        logger.error(f"Action group handler error: {e}", exc_info=True)
        return format_action_group_error(action_group, api_path, str(e), 500)
