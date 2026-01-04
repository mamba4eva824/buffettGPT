"""
Bedrock agent invocation service.

EXTRACTED FROM: handler.py
- invoke_agent_streaming(): lines 507-593
- bedrock_agent_client: lines 124-127

Handles:
- Bedrock agent invocation with streaming via invoke_agent()

Note: Supervisor synthesis uses converse_stream() directly in orchestrator.py
for guaranteed token-by-token streaming to the frontend.
"""
import json
import logging
import boto3
from datetime import datetime
from typing import Generator

from config.settings import BEDROCK_REGION, AGENT_CONFIG
from services.streaming import format_sse_event
from models.schemas import DecimalEncoder
from utils.feature_extractor import prepare_agent_payload

logger = logging.getLogger(__name__)

# Bedrock agent client
bedrock_agent_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=BEDROCK_REGION
)


def invoke_agent_streaming(agent_type: str, ticker: str, fiscal_year: int,
                           inference_result: dict, features: dict, session_id: str) -> Generator[str, None, None]:
    """
    Invoke Bedrock agent with streaming response.

    Args:
        agent_type: 'debt', 'cashflow', or 'growth'
        ticker: Stock ticker
        fiscal_year: Fiscal year
        inference_result: Model inference results
        features: Extracted features
        session_id: Session ID for conversation memory

    Yields:
        SSE-formatted chunks
    """
    config = AGENT_CONFIG.get(agent_type, {})
    agent_id = config.get('agent_id')
    agent_alias = config.get('agent_alias')

    if not agent_id or not agent_alias:
        logger.warning(f"Agent {agent_type} not configured, using fallback response")
        yield format_sse_event(json.dumps({
            "type": "chunk",
            "text": f"## {agent_type.upper()} ANALYST: {inference_result['prediction']} ({int(inference_result['confidence']*100)}% confidence)\n\n",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "chunk")

        yield format_sse_event(json.dumps({
            "type": "chunk",
            "text": f"Analysis based on {ticker} financial data for fiscal year {fiscal_year}.\n\n",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "chunk")

        yield format_sse_event(json.dumps({
            "type": "chunk",
            "text": f"*Note: Full agent response requires Bedrock agent configuration.*\n",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "chunk")
        return

    # Prepare payload for agent
    payload = prepare_agent_payload(ticker, fiscal_year, inference_result, features, agent_type)

    # Format message for agent
    user_message = f"""
    Analyze {ticker}'s {agent_type} health for fiscal year {fiscal_year}.

    Model Inference Results:
    - Prediction: {inference_result['prediction']}
    - Confidence: {int(inference_result['confidence']*100)}%
    - CI Width: {inference_result['ci_width']}
    - Interpretation: {inference_result['confidence_interpretation']}

    Key Metrics:
    {json.dumps(features.get(agent_type, {}).get('current', {}), indent=2, cls=DecimalEncoder)}

    Please provide your expert analysis following the response format.
    """

    try:
        response = bedrock_agent_client.invoke_agent(
            agentId=agent_id,
            agentAliasId=agent_alias,
            sessionId=session_id,
            inputText=user_message,
            streamingConfigurations={'streamFinalResponse': True}
        )

        for event_item in response.get('completion', []):
            if 'chunk' in event_item:
                chunk = event_item['chunk']
                if 'bytes' in chunk:
                    chunk_text = chunk['bytes'].decode('utf-8')
                    yield format_sse_event(json.dumps({
                        "type": "chunk",
                        "text": chunk_text,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    }), "chunk")

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": f"Agent error: {str(e)}"
        }), "error")
