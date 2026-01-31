"""
Ensemble Analyzer Handler

Unified handler for the 3-model ensemble (debt, cashflow, growth):
1. Fetches financial data from FMP API (with DynamoDB caching)
2. Extracts 163 features
3. Runs XGBoost inference with probability-based CI
4. Invokes appropriate Bedrock agent with streaming

Supports REST API Gateway with streaming (response_transfer_mode=STREAM).
Path: POST /analysis/{agent_type}

Request:
- Path param: agent_type (debt, cashflow, growth)
- Body: {"company": "AAPL", "fiscal_year": 2024}
- Header: Authorization: Bearer <jwt_token> (validated by API Gateway)

The agent_type can also be passed in body for backwards compatibility.
"""

import json
import boto3
import os
import logging
import time
import pickle
import jwt
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np
from decimal import Decimal
from functools import lru_cache

# Configure logging
log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Secrets Manager client for JWT
secrets_client = boto3.client('secretsmanager')

# JWT Configuration
JWT_SECRET_ARN = os.environ.get('JWT_SECRET_ARN')
PROJECT_NAME = os.environ.get('PROJECT_NAME', 'buffett-chat-api')


@lru_cache(maxsize=1)
def get_jwt_secret() -> str:
    """Get JWT secret from AWS Secrets Manager with caching."""
    if JWT_SECRET_ARN:
        try:
            response = secrets_client.get_secret_value(SecretId=JWT_SECRET_ARN)
            return response['SecretString']
        except Exception as e:
            logger.error(f"Failed to fetch JWT secret: {e}")
            raise
    # Fallback to environment variable
    jwt_secret = os.environ.get('JWT_SECRET')
    if jwt_secret:
        return jwt_secret
    raise ValueError("JWT_SECRET not configured")


def extract_token(event: Dict[str, Any]) -> Optional[str]:
    """Extract JWT token from Authorization header."""
    headers = event.get('headers', {}) or {}
    # Handle case-insensitive headers
    auth_header = headers.get('authorization') or headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header[7:]
    return None


def verify_jwt_token(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Verify JWT token from request.

    Returns:
        User claims dict if valid, None if invalid/missing
    """
    token = extract_token(event)
    if not token:
        return None

    try:
        jwt_secret = get_jwt_secret()
        payload = jwt.decode(token, jwt_secret, algorithms=['HS256'], options={'verify_exp': True})
        logger.info(f"JWT verified for user: {payload.get('user_id', 'unknown')}")
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("JWT token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        return None
    except Exception as e:
        logger.error(f"JWT verification error: {e}")
        return None


# Import utilities
from utils.fmp_client import get_financial_data, normalize_ticker, validate_ticker
from utils.feature_extractor import extract_all_features, prepare_agent_payload
from utils.conversation_updater import update_conversation_timestamp
import uuid

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')

# DynamoDB tables for message persistence
CHAT_MESSAGES_TABLE = os.environ.get('CHAT_MESSAGES_TABLE', 'buffett-dev-chat-messages')
CONVERSATIONS_TABLE = os.environ.get('CONVERSATIONS_TABLE', 'buffett-dev-conversations')
messages_table = dynamodb.Table(CHAT_MESSAGES_TABLE)
conversations_table = dynamodb.Table(CONVERSATIONS_TABLE)
bedrock_client = boto3.client(
    'bedrock-agent-runtime',
    region_name=os.environ.get('BEDROCK_REGION', 'us-east-1')
)
s3_client = boto3.client('s3')

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'dev')
MODEL_S3_BUCKET = os.environ.get('ML_MODELS_BUCKET', os.environ.get('MODEL_S3_BUCKET', 'buffett-dev-models'))
MODEL_S3_PREFIX = os.environ.get('MODEL_S3_PREFIX', 'ensemble/v1')

# Agent IDs (to be configured per agent type)
AGENT_CONFIG = {
    'debt': {
        'agent_id': os.environ.get('DEBT_AGENT_ID'),
        'agent_alias': os.environ.get('DEBT_AGENT_ALIAS'),
    },
    'cashflow': {
        'agent_id': os.environ.get('CASHFLOW_AGENT_ID'),
        'agent_alias': os.environ.get('CASHFLOW_AGENT_ALIAS'),
    },
    'growth': {
        'agent_id': os.environ.get('GROWTH_AGENT_ID'),
        'agent_alias': os.environ.get('GROWTH_AGENT_ALIAS'),
    }
}

# Model cache (loaded once per Lambda instance)
_models_cache = {}


class DecimalEncoder(json.JSONEncoder):
    """Handle Decimal types for JSON serialization."""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


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
        # Download model files from S3
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

        # Cache for subsequent invocations
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
            # Handle None values
            if value is None:
                value = 0.0
            feature_vector.append(float(value))

        logger.info(f"Running inference for {model_type} with {len(feature_vector)} features")

        # Convert to numpy array and scale
        X = np.array([feature_vector])
        X_scaled = scaler.transform(X)

        # Get probability predictions from XGBoost
        probs = model.predict_proba(X_scaled)[0]

        # Map to class labels (XGBoost uses 0=SELL, 1=HOLD, 2=BUY)
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
        # Return default uncertain prediction
        return {
            'prediction': 'HOLD',
            'confidence': 0.33,
            'ci_width': 0.95,
            'confidence_interpretation': 'WEAK',
            'probabilities': {'SELL': 0.33, 'HOLD': 0.34, 'BUY': 0.33},
            'error': str(e)
        }


def format_sse_event(data: str, event_type: str = "message") -> str:
    """Format data as Server-Sent Event."""
    return f"event: {event_type}\ndata: {data}\n\n"


def invoke_agent_streaming(agent_type: str, ticker: str, fiscal_year: int,
                           inference_result: dict, features: dict, session_id: str):
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
        response = bedrock_client.invoke_agent(
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


def generate_analysis_chunks(event: Dict[str, Any], context: Any):
    """
    Generator for ensemble analysis SSE events.

    Yields SSE-formatted string events for:
    1. Connection established
    2. Data fetching status
    3. Feature extraction status
    4. Model inference results (for each model)
    5. Agent response chunks
    6. Completion

    Note: This is a generator that yields SSE-formatted strings.
    The lambda_handler collects these and returns them as a complete response.
    """
    try:
        # Send connection event
        yield format_sse_event(json.dumps({
            "type": "connected",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "connected")

        # Parse request body
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')

        body = json.loads(body_str)
        company_input = body.get('company', body.get('ticker', '')).strip()
        fiscal_year = body.get('fiscal_year', datetime.now().year)
        session_id = body.get('session_id', f"ensemble-{context.aws_request_id}")

        # Get agent_type: REST API path param takes precedence, then body param
        path_params = event.get('pathParameters') or {}
        agent_type = path_params.get('agent_type') or body.get('agent_type', 'debt')

        # Validate agent_type
        valid_agents = ['debt', 'cashflow', 'growth']
        if agent_type not in valid_agents:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Invalid agent_type: {agent_type}. Must be one of: {valid_agents}"
            }), "error")
            return

        # Normalize ticker
        ticker = normalize_ticker(company_input)

        if not validate_ticker(ticker):
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Invalid company/ticker: {company_input}"
            }), "error")
            return

        logger.info(f"Analyzing {ticker} with {agent_type} agent")

        # Send status: fetching data
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Fetching financial data for {ticker}...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Fetch financial data (with caching)
        financial_data = get_financial_data(ticker, fiscal_year)

        if not financial_data or 'raw_financials' not in financial_data:
            yield format_sse_event(json.dumps({
                "type": "error",
                "message": f"Could not fetch financial data for {ticker}"
            }), "error")
            return

        # Send status: extracting features
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": "Extracting financial features...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Extract features
        features = extract_all_features(financial_data['raw_financials'])

        # Send status: running inference
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Running {agent_type} model inference...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Run inference for requested agent type
        inference_result = run_inference(agent_type, features)

        # Send inference results
        yield format_sse_event(json.dumps({
            "type": "inference",
            "agent_type": agent_type,
            "ticker": ticker,
            "prediction": inference_result['prediction'],
            "confidence": inference_result['confidence'],
            "ci_width": inference_result['ci_width'],
            "confidence_interpretation": inference_result['confidence_interpretation'],
            "probabilities": inference_result['probabilities'],
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "inference")

        # Send status: generating analysis
        yield format_sse_event(json.dumps({
            "type": "status",
            "message": f"Generating {agent_type} expert analysis...",
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "status")

        # Stream agent response
        for chunk in invoke_agent_streaming(
            agent_type, ticker, fiscal_year,
            inference_result, features, session_id
        ):
            yield chunk

        # Send completion
        yield format_sse_event(json.dumps({
            "type": "complete",
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "agent_type": agent_type,
            "session_id": session_id,
            "inference": inference_result,
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }, cls=DecimalEncoder), "complete")

    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        yield format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")


def stream_sse_response(event: Dict[str, Any], context: Any):
    """
    Generator function for Lambda response streaming with SSE format.

    For RESPONSE_STREAM mode, the first yield must contain response metadata
    (statusCode and headers), and subsequent yields contain the body chunks.

    Args:
        event: Lambda event from Function URL
        context: Lambda context

    Yields:
        First yield: Dict with statusCode and headers (response metadata)
        Subsequent yields: SSE-formatted string chunks (response body)
    """
    # First yield: Response metadata (required for RESPONSE_STREAM mode)
    # NOTE: CORS headers are handled by Terraform's Function URL CORS config
    # Do NOT add Access-Control-* headers here - they conflict with Terraform
    yield {
        "statusCode": 200,
        "headers": {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    }

    # Subsequent yields: SSE chunks from generate_analysis_chunks
    try:
        for chunk in generate_analysis_chunks(event, context):
            yield chunk
    except Exception as e:
        logger.error(f"Streaming error: {e}", exc_info=True)
        error_event = format_sse_event(json.dumps({
            "type": "error",
            "message": str(e),
            "timestamp": datetime.utcnow().isoformat() + 'Z'
        }), "error")
        yield error_event


def lambda_handler(event: Dict[str, Any], context: Any):
    """
    Main Lambda handler for ensemble analysis with response streaming.

    Supports:
    - Bedrock Action Group invocations (for expert agents)
    - Lambda Function URL (SSE streaming via generator pattern)
    - API Gateway (standard JSON response)

    Request Format (for HTTP/Function URL):
    {
        "company": "Apple" or "AAPL",
        "agent_type": "debt" | "cashflow" | "growth",
        "fiscal_year": 2024,  // optional
        "session_id": "..."   // optional, for follow-up questions
    }

    Authentication:
    - HTTP: Requires valid JWT token in Authorization header (Bearer token)
    - Bedrock: Authenticated via AWS IAM (no JWT required)
    """
    # =========================================
    # Check if this is a Bedrock Action Group invocation
    # Action group events have 'actionGroup' in the event
    # =========================================
    if 'actionGroup' in event:
        logger.info("Detected Bedrock Action Group invocation")
        from handlers.action_group_handler import lambda_handler as action_group_lambda_handler
        return action_group_lambda_handler(event, context)

    request_context = event.get('requestContext', {})
    is_function_url = 'http' in request_context

    # JWT Authentication - MUST validate before streaming
    user_claims = verify_jwt_token(event)
    if not user_claims:
        logger.warning("Unauthorized request - invalid or missing JWT token")
        return error_response(401, "Unauthorized - valid JWT token required")

    # Lambda Function URL - collect chunks and return complete response
    if is_function_url:
        logger.info("Using Lambda Function URL (buffered response)")
        start_time = time.time()

        # Parse request to get conversation_id and ticker for message saving
        body_str = event.get('body', '{}')
        if event.get('isBase64Encoded'):
            import base64
            body_str = base64.b64decode(body_str).decode('utf-8')
        body = json.loads(body_str)

        conversation_id = body.get('conversation_id')
        company_input = body.get('company', body.get('ticker', '')).strip()
        agent_type = body.get('agent_type', 'debt')
        user_id = user_claims.get('user_id', 'unknown')

        # Only save user message for the first agent (debt) to avoid duplicates
        # The frontend calls this 3 times (debt, cashflow, growth) in parallel
        user_message_id = None
        if conversation_id and agent_type == 'debt':
            user_query = f"Analyze {company_input}"
            user_message_id = save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                message_type='user',
                content=user_query
            )
            logger.info(f"Saved user message {user_message_id} for conversation {conversation_id}")

        # Collect all SSE chunks
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
        chunks = []
        accumulated_text = []  # Accumulate text for saving

        for item in stream_sse_response(event, context):
            if isinstance(item, dict) and 'statusCode' in item:
                # This is the first yield (metadata) - update headers if needed
                headers.update(item.get('headers', {}))
            elif isinstance(item, str):
                # This is an SSE chunk
                chunks.append(item)
                # Extract text from chunk for accumulation
                if 'data: ' in item:
                    try:
                        data_line = item.split('data: ')[1].split('\n')[0]
                        data = json.loads(data_line)
                        if data.get('type') == 'chunk' and 'text' in data:
                            accumulated_text.append(data['text'])
                    except (json.JSONDecodeError, IndexError):
                        pass

        # Save assistant message if conversation_id provided
        if conversation_id and accumulated_text:
            processing_time_ms = (time.time() - start_time) * 1000
            full_response = ''.join(accumulated_text)
            save_message(
                conversation_id=conversation_id,
                user_id=user_id,
                message_type='assistant',
                content=full_response,
                parent_message_id=user_message_id,
                processing_time_ms=processing_time_ms
            )
            # Update conversation timestamp (pass None to let function use int timestamp)
            update_conversation_timestamp(conversation_id, user_id=user_id)
            logger.info(f"Saved assistant response to conversation {conversation_id}")

        # Return complete response
        return {
            'statusCode': 200,
            'headers': headers,
            'body': ''.join(chunks)
        }

    # API Gateway - standard JSON response
    start_time = time.time()

    try:
        body = json.loads(event.get('body', '{}'))
        company_input = body.get('company', body.get('ticker', '')).strip()
        agent_type = body.get('agent_type', 'debt')
        fiscal_year = body.get('fiscal_year', datetime.now().year)
        session_id = body.get('session_id', f"ensemble-{context.aws_request_id}")

        ticker = normalize_ticker(company_input)

        if not validate_ticker(ticker):
            return error_response(400, f"Invalid company/ticker: {company_input}")

        # Fetch data
        financial_data = get_financial_data(ticker, fiscal_year)

        if not financial_data or 'raw_financials' not in financial_data:
            return error_response(404, f"Could not fetch financial data for {ticker}")

        # Extract features
        features = extract_all_features(financial_data['raw_financials'])

        # Run inference
        inference_result = run_inference(agent_type, features)

        processing_time_ms = int((time.time() - start_time) * 1000)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'success': True,
                'ticker': ticker,
                'fiscal_year': fiscal_year,
                'agent_type': agent_type,
                'session_id': session_id,
                'inference': inference_result,
                'features': features,
                'processing_time_ms': processing_time_ms,
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }, cls=DecimalEncoder)
        }

    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        return error_response(500, str(e))


def error_response(status_code: int, message: str) -> Dict[str, Any]:
    """Create standardized error response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({
            'success': False,
            'error': message,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        })
    }


def save_message(conversation_id: str, user_id: str, message_type: str,
                 content: str, parent_message_id: str = None,
                 processing_time_ms: float = None) -> str:
    """
    Save a message to the chat_messages DynamoDB table.

    Args:
        conversation_id: Conversation ID
        user_id: User ID
        message_type: 'user' or 'assistant'
        content: Message content
        parent_message_id: Parent message ID (for assistant responses)
        processing_time_ms: Processing time in milliseconds

    Returns:
        Message ID
    """
    message_id = str(uuid.uuid4())
    current_time = datetime.utcnow()

    message_record = {
        'conversation_id': conversation_id,
        'timestamp': int(current_time.timestamp()),
        'timestamp_iso': current_time.isoformat() + 'Z',
        'message_id': message_id,
        'user_id': user_id,
        'message_type': message_type,
        'content': content,
        'status': 'completed' if message_type == 'assistant' else 'received',
        'environment': ENVIRONMENT,
        'project': PROJECT_NAME
    }

    if parent_message_id:
        message_record['parent_message_id'] = parent_message_id

    if processing_time_ms:
        message_record['processing_time_ms'] = Decimal(str(processing_time_ms))

    try:
        messages_table.put_item(Item=message_record)
        logger.info(f"Saved {message_type} message {message_id} to conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Failed to save message: {e}")

    return message_id
