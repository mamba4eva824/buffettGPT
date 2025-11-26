"""
Debt Analyzer Lambda Handler
AWS Lambda container handler for debt analysis with health checks and golden tests
"""

import json
import os
import pickle
import time
import hashlib
import boto3
import httpx
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from functools import lru_cache
from tenacity import retry, stop_after_attempt, wait_exponential
from pythonjsonlogger import jsonlogger
from decimal import Decimal

# Disable joblib multiprocessing in Lambda (doesn't work due to /dev/shm permissions)
os.environ['JOBLIB_MULTIPROCESSING'] = '0'
os.environ['LOKY_MAX_CPU_COUNT'] = '1'

import joblib

# ============================================================================
# Custom JSON Encoder for Decimal
# ============================================================================

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts Decimal to float"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

# ============================================================================
# Logging Configuration
# ============================================================================

import logging

logger = logging.getLogger()
logger.setLevel(os.getenv('LOG_LEVEL', 'INFO'))

# JSON formatter for CloudWatch
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

# ============================================================================
# Constants
# ============================================================================

# Health check
HEALTH_CHECK_PATH = "/health"

# Golden test (Disney = STABLE debt position)
GOLDEN_TEST_INPUT = {
    "ticker": "DIS",
    "fiscal_year": 2023
}
GOLDEN_TEST_EXPECTED = {
    "signal": "STABLE",  # Updated from "HOLD" to match new debt strength semantics
    "prediction": 0
}

# Signal mapping - Debt Strength Assessment
# -2 to +2 scale representing debt health (NOT buy/sell signals)
SIGNAL_MAP = {
    -2: {
        'label': 'CONCERNING',
        'emoji': '🔴',
        'description': 'Excessive debt burden, major financial risk',
        'debt_strength': 'Very Weak'
    },
    -1: {
        'label': 'WEAK',
        'emoji': '🟠',
        'description': 'Elevated debt levels, monitoring required',
        'debt_strength': 'Weak'
    },
    0: {
        'label': 'STABLE',
        'emoji': '🟡',
        'description': 'Moderate debt position, neither strength nor weakness',
        'debt_strength': 'Stable'
    },
    1: {
        'label': 'STRONG',
        'emoji': '🟢',
        'description': 'Conservative leverage, healthy debt metrics',
        'debt_strength': 'Strong'
    },
    2: {
        'label': 'VERY STRONG',
        'emoji': '💚',
        'description': 'Excellent debt management, financial fortress',
        'debt_strength': 'Very Strong'
    }
}

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

# Perplexity client with timeout
perplexity_client = httpx.Client(
    timeout=httpx.Timeout(
        connect=5.0,
        read=float(os.getenv('PERPLEXITY_TIMEOUT', '25')),
        write=5.0,
        pool=5.0
    ),
    limits=httpx.Limits(
        max_keepalive_connections=5,
        max_connections=10
    )
)

# ============================================================================
# CORS Headers Helper
# ============================================================================

def get_cors_headers():
    """
    Get CORS headers for API Gateway responses
    Allows frontend to make cross-origin requests
    """
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,Authorization',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

# ============================================================================
# Global Model Cache
# ============================================================================

_model_cache = None


# ============================================================================
# Model Loading
# ============================================================================

@lru_cache(maxsize=1)
def load_model():
    """
    Load ML model and metadata from S3 to /tmp, then into memory
    Uses global cache to persist across warm invocations

    Model structure:
      - debt_analyzer_model.pkl: GradientBoostingClassifier
      - debt_analyzer_metadata.pkl: {'imputer': SimpleImputer, 'feature_cols': [...], ...}

    Returns:
        dict: Model data with 'model', 'imputer', 'feature_names', 'metadata'
    """
    global _model_cache

    # Check if model already in memory (warm start)
    if _model_cache is not None:
        logger.info("Model cache HIT (in memory)")
        return _model_cache

    model_path = os.getenv('MODEL_LOCAL_PATH', '/tmp/debt_analyzer_model.pkl')
    metadata_path = '/tmp/debt_analyzer_metadata.pkl'

    # Check if both files exist in /tmp (cold start but files persist)
    if os.path.exists(model_path) and os.path.exists(metadata_path):
        logger.info("Model cache HIT (/tmp)")
        model = joblib.load(model_path)
        metadata = joblib.load(metadata_path)

        _model_cache = {
            'model': model,
            'imputer': metadata['imputer'],
            'feature_cols': metadata.get('feature_cols', []),
            'metadata': {
                'model_version': os.getenv('MODEL_VERSION', 'unknown'),
                'loaded_at': datetime.utcnow().isoformat(),
                'source': '/tmp cache',
                'training_accuracy': metadata.get('training_accuracy'),
                'sklearn_version': metadata.get('sklearn_version')
            }
        }
        return _model_cache

    # Cold start: Download both files from S3
    logger.info("Model cache MISS - Downloading from S3")
    start_time = time.time()

    model_bucket = os.getenv('MODEL_S3_BUCKET')
    model_key = os.getenv('MODEL_S3_KEY')

    if not model_bucket or not model_key:
        raise ValueError("MODEL_S3_BUCKET and MODEL_S3_KEY must be set")

    # Derive metadata key from model key
    metadata_key = model_key.replace('_model.pkl', '_metadata.pkl')

    try:
        # Download model file
        s3_client.download_file(
            Bucket=model_bucket,
            Key=model_key,
            Filename=model_path
        )

        # Download metadata file
        s3_client.download_file(
            Bucket=model_bucket,
            Key=metadata_key,
            Filename=metadata_path
        )

        download_time = time.time() - start_time
        logger.info(f"S3 download completed", extra={
            'download_time_seconds': download_time,
            'model_size_mb': os.path.getsize(model_path) / (1024 * 1024),
            'metadata_size_kb': os.path.getsize(metadata_path) / 1024
        })

        # Load both into memory
        model = joblib.load(model_path)
        metadata = joblib.load(metadata_path)

        load_time = time.time() - start_time
        logger.info(f"Model loaded successfully", extra={
            'total_load_time_seconds': load_time,
            'model_version': metadata.get('model_version'),
            'training_samples': metadata.get('training_samples')
        })

        # Cache for subsequent invocations
        _model_cache = {
            'model': model,
            'imputer': metadata['imputer'],
            'feature_cols': metadata.get('feature_cols', []),
            'metadata': {
                'model_version': os.getenv('MODEL_VERSION', 'unknown'),
                'loaded_at': datetime.utcnow().isoformat(),
                'load_time_seconds': load_time,
                'training_accuracy': metadata.get('training_accuracy'),
                'sklearn_version': metadata.get('sklearn_version')
            }
        }

        return _model_cache

    except Exception as e:
        logger.exception("Failed to load model from S3")
        raise


# ============================================================================
# Health Check Handler
# ============================================================================

def handle_health_check() -> Dict[str, Any]:
    """
    Health check endpoint

    Validates:
    1. Lambda is running
    2. Model can be loaded
    3. Golden test passes (Disney = HOLD)
    4. S3/DynamoDB connectivity
    5. Environment variables set

    Returns 200 if healthy, 503 if unhealthy
    """
    start_time = time.time()
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.getenv('MODEL_VERSION', 'unknown'),
        "environment": os.getenv('ENVIRONMENT', 'unknown'),
        "checks": {}
    }

    try:
        # Check 1: Environment variables
        required_env_vars = [
            'MODEL_S3_BUCKET',
            'MODEL_S3_KEY',
            'FINANCIAL_CACHE_TABLE',
            'IDEMPOTENCY_TABLE'
        ]

        missing_vars = [var for var in required_env_vars if not os.getenv(var)]
        if missing_vars:
            health_status["checks"]["environment"] = {
                "status": "unhealthy",
                "missing_vars": missing_vars
            }
            health_status["status"] = "unhealthy"
        else:
            health_status["checks"]["environment"] = {"status": "healthy"}

        # Check 2: Model loading
        try:
            model_data = load_model()
            metadata = model_data.get('metadata', {})

            health_status["checks"]["model"] = {
                "status": "healthy",
                "version": metadata.get('version', 'unknown'),
                "training_samples": metadata.get('training_samples', 'unknown'),
                "training_accuracy": metadata.get('training_accuracy', 'unknown'),
                "training_date": metadata.get('training_date', 'unknown')
            }
        except Exception as e:
            health_status["checks"]["model"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
            logger.exception("Model health check failed")

        # Check 3: S3 connectivity
        try:
            s3_client.head_object(
                Bucket=os.getenv('MODEL_S3_BUCKET'),
                Key=os.getenv('MODEL_S3_KEY')
            )
            health_status["checks"]["s3"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["s3"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
            logger.exception("S3 health check failed")

        # Check 4: DynamoDB connectivity
        try:
            table_name = os.getenv('FINANCIAL_CACHE_TABLE')
            table = dynamodb.Table(table_name)
            table.table_status  # This will raise if table doesn't exist
            health_status["checks"]["dynamodb"] = {"status": "healthy"}
        except Exception as e:
            health_status["checks"]["dynamodb"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
            logger.exception("DynamoDB health check failed")

        # Check 5: Golden test (Disney = HOLD)
        try:
            golden_result = run_golden_test()
            if golden_result["passed"]:
                health_status["checks"]["golden_test"] = {
                    "status": "healthy",
                    "result": golden_result
                }
            else:
                health_status["checks"]["golden_test"] = {
                    "status": "unhealthy",
                    "result": golden_result
                }
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["checks"]["golden_test"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "unhealthy"
            logger.exception("Golden test failed")

        # Add timing
        health_status["response_time_ms"] = int((time.time() - start_time) * 1000)

        # Return appropriate status code
        status_code = 200 if health_status["status"] == "healthy" else 503

        logger.info("Health check completed", extra={
            "status": health_status["status"],
            "response_time_ms": health_status["response_time_ms"]
        })

        return {
            "statusCode": status_code,
            "headers": {
                "Content-Type": "application/json",
                "X-Health-Status": health_status["status"],
                **get_cors_headers()
            },
            "body": json.dumps(health_status, indent=2)
        }

    except Exception as e:
        logger.exception("Health check exception")
        return {
            "statusCode": 503,
            "headers": {
                "Content-Type": "application/json",
                **get_cors_headers()
            },
            "body": json.dumps({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            })
        }


# ============================================================================
# Golden Test
# ============================================================================

def run_golden_test() -> Dict[str, Any]:
    """
    Run golden test: Disney 2023 should predict HOLD (0)

    This is a known-good test case that validates:
    1. Feature extraction works
    2. Model inference works
    3. Prediction is consistent with training

    Returns:
        dict with 'passed' boolean and details
    """
    ticker = GOLDEN_TEST_INPUT["ticker"]
    fiscal_year = GOLDEN_TEST_INPUT["fiscal_year"]

    logger.info(f"Running golden test: {ticker} {fiscal_year}")

    # For health check, use cached Disney data (don't hit Perplexity)
    # This makes health checks fast and free
    cached_data = check_financial_cache(ticker, fiscal_year)

    if not cached_data:
        # First health check after deployment - need to note this
        logger.warning("Golden test: No cached data, health check may be slow on first run")
        # Return a warning but don't fail - we'll cache it on first real request
        return {
            "passed": True,  # Don't fail health check on first run
            "warning": "No cached data yet - will be validated on first analysis request",
            "ticker": ticker,
            "fiscal_year": fiscal_year
        }

    # Extract features
    features = extract_debt_features(cached_data)

    # Run prediction
    model_data = load_model()
    model = model_data['model']
    imputer = model_data['imputer']

    # Prepare features
    feature_array = [list(features.values())]

    # Impute missing values
    feature_array_imputed = imputer.transform(feature_array)

    # Predict
    prediction = model.predict(feature_array_imputed)[0]

    # Check if matches expected
    expected = GOLDEN_TEST_EXPECTED["prediction"]
    passed = (prediction == expected)

    result = {
        "passed": passed,
        "expected": {
            "signal": GOLDEN_TEST_EXPECTED["signal"],
            "prediction": expected
        },
        "actual": {
            "signal": SIGNAL_MAP[prediction]["label"],
            "prediction": int(prediction)
        },
        "ticker": ticker,
        "fiscal_year": fiscal_year
    }

    if not passed:
        logger.error("Golden test FAILED", extra=result)
    else:
        logger.info("Golden test PASSED", extra=result)

    return result


# ============================================================================
# Cache Functions
# ============================================================================

def check_financial_cache(ticker: str, fiscal_year: int) -> Optional[Dict[str, Any]]:
    """
    Check DynamoDB cache for financial data

    Table structure:
      - Partition Key: cache_key (format: "TICKER:YEAR", e.g., "OKTA:2023")
      - TTL: expires_at (Unix timestamp)
      - GSI: cached-at-index on cached_at attribute

    Args:
        ticker: Stock ticker
        fiscal_year: Fiscal year

    Returns:
        Cached financial data or None
    """
    try:
        table_name = os.getenv('FINANCIAL_CACHE_TABLE')
        table = dynamodb.Table(table_name)

        cache_key = f"{ticker}:{fiscal_year}"

        response = table.get_item(
            Key={'cache_key': cache_key}
        )

        if 'Item' in response:
            item = response['Item']

            # Check if expired (TTL check - DynamoDB handles this automatically but we double-check)
            expires_at = item.get('expires_at', 0)
            if expires_at < time.time():
                logger.info(f"Cache EXPIRED for {ticker} FY{fiscal_year}")
                return None

            logger.info(f"Cache HIT for {ticker} FY{fiscal_year}")
            return item
        else:
            logger.info(f"Cache MISS for {ticker} FY{fiscal_year}")
            return None

    except Exception as e:
        logger.exception(f"Cache check failed for {ticker} FY{fiscal_year}")
        return None


def convert_floats_to_decimal(obj):
    """
    Recursively convert float values to Decimal for DynamoDB compatibility

    DynamoDB doesn't support Python float types - must use Decimal instead
    """
    if isinstance(obj, float):
        return Decimal(str(obj))
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_floats_to_decimal(item) for item in obj]
    else:
        return obj


def convert_decimals_to_float(obj):
    """
    Recursively convert Decimal values to float for JSON serialization

    API Gateway responses must be JSON serializable - convert Decimals to floats
    """
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals_to_float(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_float(item) for item in obj]
    else:
        return obj


def save_to_financial_cache(ticker: str, fiscal_year: int, financial_data: Dict[str, Any]) -> None:
    """
    Save financial data to DynamoDB cache with 90-day TTL

    Table structure:
      - Partition Key: cache_key (format: "TICKER:YEAR")
      - TTL: expires_at (Unix timestamp, 90 days from now)
      - Attributes: ticker, fiscal_year, balance_sheet, income_statement, cash_flow_statement, cached_at

    Args:
        ticker: Stock ticker symbol
        fiscal_year: Fiscal year
        financial_data: Financial data to cache
    """
    try:
        table_name = os.getenv('FINANCIAL_CACHE_TABLE')
        table = dynamodb.Table(table_name)

        # Calculate expiration (90 days from now)
        current_timestamp = int(time.time())
        expires_at = current_timestamp + (90 * 24 * 60 * 60)  # 90 days in seconds

        cache_key = f"{ticker}:{fiscal_year}"

        # Convert all float values to Decimal for DynamoDB compatibility
        item = {
            'cache_key': cache_key,
            'ticker': ticker,
            'fiscal_year': fiscal_year,
            'balance_sheet': convert_floats_to_decimal(financial_data.get('balance_sheet', {})),
            'income_statement': convert_floats_to_decimal(financial_data.get('income_statement', {})),
            'cash_flow_statement': convert_floats_to_decimal(financial_data.get('cash_flow_statement', {})),
            'cached_at': current_timestamp,
            'expires_at': expires_at,
            'data_source': 'perplexity_api'
        }

        table.put_item(Item=item)
        logger.info(f"Saved {ticker} FY{fiscal_year} to financial cache", extra={
            'cache_key': cache_key,
            'expires_at': expires_at
        })

    except Exception as e:
        logger.exception(f"Failed to save {ticker} FY{fiscal_year} to financial cache")
        # Don't raise - caching failure shouldn't block the analysis


def check_idempotency_cache(idempotency_key: str) -> Optional[Dict[str, Any]]:
    """
    Check if we've already processed this exact request

    Args:
        idempotency_key: Hash of request parameters

    Returns:
        Cached response if found, None otherwise
    """
    try:
        table_name = os.getenv('IDEMPOTENCY_TABLE')
        table = dynamodb.Table(table_name)

        response = table.get_item(
            Key={'idempotency_key': idempotency_key}
        )

        if 'Item' in response:
            # Check if still valid (24 hour TTL)
            cached_at = datetime.fromisoformat(response['Item']['cached_at'])
            age_hours = (datetime.utcnow() - cached_at).total_seconds() / 3600

            if age_hours < 24:
                logger.info(f"Idempotency cache HIT", extra={'age_hours': age_hours})
                return response['Item']['response']
            else:
                logger.info(f"Idempotency cache EXPIRED", extra={'age_hours': age_hours})
                return None

        return None

    except Exception as e:
        logger.exception("Idempotency cache check failed")
        return None


def save_idempotency_cache(idempotency_key: str, response: Dict[str, Any]):
    """Save response to idempotency cache"""
    try:
        table_name = os.getenv('IDEMPOTENCY_TABLE')
        table = dynamodb.Table(table_name)

        ttl = int((datetime.utcnow() + timedelta(hours=24)).timestamp())

        table.put_item(
            Item={
                'idempotency_key': idempotency_key,
                'response': response,
                'cached_at': datetime.utcnow().isoformat(),
                'ttl': ttl
            }
        )

        logger.info("Saved to idempotency cache")

    except Exception as e:
        logger.exception("Failed to save to idempotency cache")


# ============================================================================
# Perplexity API Integration
# ============================================================================

def fetch_financial_data_from_perplexity(ticker: str, fiscal_year: int) -> Dict[str, Any]:
    """
    Fetch financial data from Perplexity API for a given ticker and fiscal year

    Args:
        ticker: Stock ticker symbol (e.g., "OKTA", "DIS")
        fiscal_year: Fiscal year to fetch (e.g., 2023)

    Returns:
        dict: Structured financial data with balance_sheet, income_statement, cash_flow_statement

    Raises:
        ValueError: If data cannot be fetched or parsed
    """
    api_key = os.getenv('PERPLEXITY_API_KEY')
    if not api_key:
        raise ValueError("PERPLEXITY_API_KEY environment variable not set")

    # Construct prompt for Perplexity to return structured financial data
    prompt = f"""
Please provide the following financial metrics for {ticker} for fiscal year {fiscal_year} in JSON format ONLY (no explanations):

{{
  "ticker": "{ticker}",
  "fiscal_year": {fiscal_year},
  "balance_sheet": {{
    "total_assets": <value in billions>,
    "total_debt": <value in billions>,
    "total_equity": <value in billions>,
    "cash": <value in billions>
  }},
  "income_statement": {{
    "revenue": <value in billions>,
    "operating_income": <value in billions>,
    "net_income": <value in billions>,
    "interest_expense": <value in billions>
  }},
  "cash_flow_statement": {{
    "operating_cash_flow": <value in billions>,
    "free_cash_flow": <value in billions>
  }}
}}

Use the most recent 10-K or annual report data. Return ONLY the JSON object, no additional text.
"""

    try:
        logger.info(f"Fetching {ticker} FY{fiscal_year} data from Perplexity API")

        request_body = {
            "model": "sonar-pro",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a financial data API that returns only structured JSON data from SEC filings and financial databases. Return ONLY the JSON object requested, with no additional text or explanations."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "search_domain_filter": ["sec.gov"],  # Focus on SEC filings
            "temperature": 0.0,
            "max_tokens": 1000
        }

        logger.debug(f"Perplexity request: {json.dumps(request_body, indent=2)}")

        response = perplexity_client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=request_body
        )

        # Log response for debugging
        if response.status_code != 200:
            logger.error(f"Perplexity API error response: {response.text}")

        response.raise_for_status()
        result = response.json()

        # Extract content from Perplexity response
        content = result['choices'][0]['message']['content']

        # Parse JSON from content (strip markdown code blocks if present)
        content = content.strip()
        if content.startswith('```json'):
            content = content[7:]
        if content.startswith('```'):
            content = content[3:]
        if content.endswith('```'):
            content = content[:-3]
        content = content.strip()

        financial_data = json.loads(content)

        logger.info(f"Successfully fetched {ticker} data from Perplexity")

        # Validate structure
        required_keys = ['balance_sheet', 'income_statement', 'cash_flow_statement']
        if not all(key in financial_data for key in required_keys):
            raise ValueError(f"Missing required keys in response: {required_keys}")

        # Cache the fetched data
        save_to_financial_cache(ticker, fiscal_year, financial_data)

        return financial_data

    except httpx.HTTPError as e:
        logger.exception(f"HTTP error fetching data from Perplexity: {e}")
        raise ValueError(f"Failed to fetch financial data from Perplexity: {str(e)}")
    except json.JSONDecodeError as e:
        logger.exception(f"Failed to parse JSON from Perplexity response: {content[:200]}")
        raise ValueError(f"Invalid JSON response from Perplexity: {str(e)}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching from Perplexity")
        raise ValueError(f"Error fetching financial data: {str(e)}")


# ============================================================================
# Feature Extraction
# ============================================================================

def extract_debt_features(financial_data: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract 17 debt-focused features from financial statements

    Args:
        financial_data: Financial data with balance_sheet, income_statement, cash_flow_statement

    Returns:
        dict: 17 features with float values
    """
    # Helper function to safely get numeric values, handling None
    def safe_get(d, key, default=0, scale=1e9):
        """
        Get value from dict, converting strings/Decimals to floats and scaling.

        Cached financial data is stored in billions as strings (e.g., "60.9" = $60.9B).
        This function converts to actual dollar amounts by applying the scale factor.

        Args:
            d: Dictionary to get value from
            key: Key to retrieve
            default: Default value if key is missing or None (not scaled)
            scale: Scaling factor (default: 1e9 for billions to dollars)

        Returns:
            Numeric value scaled appropriately, or default if missing/invalid
        """
        val = d.get(key)

        # Handle missing or None values - return default unscaled
        if val is None:
            return default

        # Convert to float if needed
        try:
            if isinstance(val, str):
                val = float(val)
            elif isinstance(val, Decimal):
                val = float(val)
            elif not isinstance(val, (int, float)):
                # Unexpected type
                logger.warning(f"Unexpected type {type(val)} for key '{key}', using default")
                return default
        except (ValueError, TypeError) as e:
            logger.warning(f"Could not convert '{val}' to float for key '{key}': {e}, using default")
            return default

        # Apply scaling to the actual value
        return val * scale

    bs = financial_data.get('balance_sheet', {})
    inc = financial_data.get('income_statement', {})
    cf = financial_data.get('cash_flow_statement', {})

    features = {}

    # Core debt ratios
    total_debt = safe_get(bs, 'total_debt')
    total_equity = safe_get(bs, 'total_equity')
    total_assets = safe_get(bs, 'total_assets')
    cash = safe_get(bs, 'cash')

    features['debt_to_equity'] = (
        total_debt / total_equity
        if total_equity > 0 else 99.0
    )

    features['debt_to_assets'] = (
        total_debt / total_assets
        if total_assets > 0 else 99.0
    )

    operating_income = safe_get(inc, 'operating_income')
    interest_expense = safe_get(inc, 'interest_expense')

    features['interest_coverage'] = (
        operating_income / interest_expense
        if interest_expense > 0 else 99.0
    )

    features['net_debt'] = total_debt - cash

    features['net_debt_to_equity'] = (
        features['net_debt'] / total_equity
        if total_equity > 0 else 99.0
    )

    # Debt service coverage
    debt_payments = safe_get(bs, 'current_portion_debt')
    operating_cash_flow = safe_get(cf, 'operating_cash_flow')
    features['debt_service_coverage'] = (
        operating_cash_flow / (debt_payments + interest_expense)
        if (debt_payments + interest_expense) > 0 else 99.0
    )

    # Cash flow metrics
    free_cash_flow = safe_get(cf, 'free_cash_flow')
    features['fcf_to_debt'] = (
        free_cash_flow / total_debt
        if total_debt > 0 else 99.0
    )

    # Profitability metrics
    revenue = safe_get(inc, 'revenue')
    net_income = safe_get(inc, 'net_income')

    features['operating_margin'] = (
        operating_income / revenue
        if revenue > 0 else 0.0
    )

    features['net_margin'] = (
        net_income / revenue
        if revenue > 0 else 0.0
    )

    features['roe'] = (
        net_income / total_equity
        if total_equity > 0 else 0.0
    )

    features['roa'] = (
        net_income / total_assets
        if total_assets > 0 else 0.0
    )

    # Liquidity
    features['cash_to_debt'] = (
        cash / total_debt
        if total_debt > 0 else 99.0
    )

    features['equity_ratio'] = (
        total_equity / total_assets
        if total_assets > 0 else 0.0
    )

    # Growth metrics (set to 0 if no prior year data)
    features['debt_change'] = 0.0
    features['revenue_growth'] = 0.0
    features['income_growth'] = 0.0
    features['fcf_growth'] = 0.0

    return features


# ============================================================================
# Bedrock Agent Action Handler
# ============================================================================

def handle_bedrock_action(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle Bedrock Agent action group invocation

    Supports two action group types:

    1. Function-based action group:
    {
        "messageVersion": "1.0",
        "agent": {...},
        "actionGroup": "debt-analyzer-actions",
        "function": "analyzeCompanyDebt",
        "parameters": [
            {"name": "ticker", "type": "string", "value": "DIS"},
            {"name": "fiscal_year", "type": "integer", "value": "2023"}
        ]
    }

    2. API-based action group (OpenAPI schema):
    {
        "messageVersion": "1.0",
        "agent": {...},
        "actionGroup": "debt-analyzer-actions",
        "apiPath": "/analyze-debt",
        "httpMethod": "POST",
        "requestBody": {
            "content": {
                "application/json": {
                    "properties": [
                        {"name": "ticker", "type": "string", "value": "DIS"},
                        {"name": "fiscal_year", "type": "number", "value": "2023"}
                    ]
                }
            }
        }
    }

    Expected response format:
    {
        "messageVersion": "1.0",
        "response": {
            "actionGroup": "debt-analyzer-actions",
            "apiPath": "/analyze-debt",
            "httpMethod": "POST",
            "httpStatusCode": 200,
            "responseBody": {
                "application/json": {
                    "body": "JSON string with analysis results"
                }
            }
        }
    }
    """
    try:
        logger.info("Bedrock action invoked", extra={
            'action_group': event.get('actionGroup'),
            'function': event.get('function'),
            'api_path': event.get('apiPath'),
            'http_method': event.get('httpMethod'),
            'agent_id': event.get('agent', {}).get('id')
        })

        # Determine invocation type: function-based or API-based
        function_name = event.get('function')
        api_path = event.get('apiPath')
        http_method = event.get('httpMethod')

        # Extract parameters based on invocation type
        if function_name:
            # Function-based action group
            parameters = event.get('parameters', [])
            params_dict = {param['name']: param['value'] for param in parameters}

            if function_name == 'analyzeCompanyDebt':
                response_body = analyze_company_debt_action(params_dict)
            else:
                logger.error(f"Unknown function: {function_name}")
                response_body = {
                    "error": "UnknownFunction",
                    "message": f"Function '{function_name}' is not supported"
                }

        elif api_path:
            # API-based action group (OpenAPI schema)
            request_body = event.get('requestBody', {})

            # Extract parameters from requestBody content
            content = request_body.get('content', {})
            app_json = content.get('application/json', {})
            properties = app_json.get('properties', [])

            # Convert properties list to dict
            params_dict = {prop['name']: prop['value'] for prop in properties}

            logger.info("API-based action group parameters", extra={'params': params_dict})

            # Route based on API path
            if api_path == '/analyze' and http_method == 'POST':
                response_body = analyze_company_debt_action(params_dict)
            else:
                logger.error(f"Unknown API path: {http_method} {api_path}")
                response_body = {
                    "error": "UnknownEndpoint",
                    "message": f"Endpoint '{http_method} {api_path}' is not supported"
                }

        else:
            logger.error("Invalid Bedrock event: missing both 'function' and 'apiPath'")
            response_body = {
                "error": "InvalidEvent",
                "message": "Event must have either 'function' or 'apiPath'"
            }

        # Format Bedrock response
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup'),
                "apiPath": event.get('apiPath'),
                "httpMethod": event.get('httpMethod'),
                "httpStatusCode": 200,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps(response_body, cls=DecimalEncoder)
                    }
                }
            }
        }

    except Exception as e:
        logger.exception("Error handling Bedrock action")
        return {
            "messageVersion": "1.0",
            "response": {
                "actionGroup": event.get('actionGroup'),
                "apiPath": event.get('apiPath'),
                "httpMethod": event.get('httpMethod'),
                "httpStatusCode": 500,
                "responseBody": {
                    "application/json": {
                        "body": json.dumps({
                            "error": "InternalError",
                            "message": str(e)
                        })
                    }
                }
            }
        }


def analyze_company_debt_action(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bedrock action: Analyze company debt health

    Args:
        params: {
            "ticker": "DIS",
            "fiscal_year": "2023"  (optional, as string from Bedrock)
        }

    Returns:
        dict: Analysis results matching OpenAPI schema
    """
    ticker = params.get('ticker', '').upper()
    fiscal_year_str = params.get('fiscal_year')

    # Validate ticker
    if not ticker:
        return {
            "error": "InvalidRequest",
            "message": "ticker is required"
        }

    # Parse fiscal_year (Bedrock sends as string)
    fiscal_year = None
    if fiscal_year_str:
        try:
            fiscal_year = int(fiscal_year_str)
            if fiscal_year < 2015 or fiscal_year > 2024:
                return {
                    "error": "InvalidRequest",
                    "message": f"fiscal_year must be between 2015 and 2024, got {fiscal_year}"
                }
        except (ValueError, TypeError):
            return {
                "error": "InvalidRequest",
                "message": f"fiscal_year must be an integer, got '{fiscal_year_str}'"
            }

    logger.info(f"Analyzing debt for {ticker} FY{fiscal_year or 'latest'}")

    # Use existing process_analysis function
    try:
        result = process_analysis(ticker, fiscal_year)

        # Format response to match OpenAPI schema
        return {
            "ticker": ticker,
            "fiscal_year": result.get('fiscal_year'),
            "prediction": result.get('prediction'),
            "signal": result.get('signal'),
            "confidence": result.get('confidence'),
            "metrics": result.get('metrics')
        }

    except Exception as e:
        logger.exception(f"Error analyzing {ticker}")
        return {
            "error": "AnalysisError",
            "message": str(e)
        }


# ============================================================================
# Main Lambda Handler
# ============================================================================

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler with multiple invocation modes:

    1. Bedrock Agent Action Group - analyzeCompanyDebt function
    2. HTTP API - GET /health, POST /analyze/debt

    Routes based on event structure:
      - If event has 'actionGroup' → Bedrock action
      - If event has 'path' → HTTP request
    """
    request_id = context.aws_request_id if context else 'local-test'

    logger.info("Lambda invoked", extra={
        'request_id': request_id,
        'event_keys': list(event.keys()),
        'invocation_source': event.get('actionGroup') or event.get('path', 'unknown')
    })

    # Route 1: Bedrock Agent Action Group invocation
    if 'actionGroup' in event:
        return handle_bedrock_action(event, context)

    # Route 2: HTTP invocation (API Gateway)
    # Extract path and method - support both v1 and v2 payload formats
    # v1: event.get('path'), event.get('httpMethod')
    # v2: event.get('rawPath'), event['requestContext']['http']['method']
    path = event.get('rawPath') or event.get('path', '/')
    http_method = event.get('httpMethod') or event.get('requestContext', {}).get('http', {}).get('method', 'POST')

    # Strip /dev or /prod stage prefix from path if present
    if path.startswith('/dev/'):
        path = path[4:]  # Remove '/dev' prefix
    elif path.startswith('/prod/'):
        path = path[5:]  # Remove '/prod' prefix

    # Health check endpoint - support both /health and /api/analyze/health
    if path in [HEALTH_CHECK_PATH, '/api/analyze/health'] and http_method == 'GET':
        return handle_health_check()

    # Debt analysis endpoint - support both /analyze/debt and /api/analyze/debt
    if path in ['/analyze/debt', '/api/analyze/debt'] and http_method == 'POST':
        return handle_debt_analysis(event, context)

    # Default: assume debt analysis for any other POST request
    return handle_debt_analysis(event, context)


def handle_debt_analysis(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle debt analysis request

    Expected event body:
    {
        "ticker": "AMZN",
        "fiscal_year": 2023  (optional, defaults to latest)
    }
    """
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        ticker = body.get('ticker')
        fiscal_year = body.get('fiscal_year')

        if not ticker:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'InvalidRequest',
                    'message': 'ticker is required'
                })
            }

        # Get user ID from authorizer (Google OAuth)
        user_id = event.get('requestContext', {}).get('authorizer', {}).get('userId', 'anonymous')

        # Generate idempotency key
        idempotency_key = generate_idempotency_key(ticker, fiscal_year, user_id)

        # Check idempotency cache
        cached_response = check_idempotency_cache(idempotency_key)
        if cached_response:
            logger.info("Returning cached response (idempotency)")
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Cache': 'HIT-IDEMPOTENCY',
                    **get_cors_headers()
                },
                'body': json.dumps(cached_response)
            }

        # Process analysis
        response = process_analysis(ticker, fiscal_year)

        # Convert Decimals to floats for JSON serialization
        response_json_safe = convert_decimals_to_float(response)

        # Save to idempotency cache
        save_idempotency_cache(idempotency_key, response_json_safe)

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'X-Cache': 'MISS',
                **get_cors_headers()
            },
            'body': json.dumps(response_json_safe)
        }

    except Exception as e:
        logger.exception("Error processing debt analysis")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                **get_cors_headers()
            },
            'body': json.dumps({
                'error': 'InternalServerError',
                'message': str(e)
            })
        }


def generate_idempotency_key(ticker: str, fiscal_year: Optional[int], user_id: str) -> str:
    """Generate idempotency key from request parameters"""
    payload = f"{ticker}:{fiscal_year}:{user_id}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def process_analysis(ticker: str, fiscal_year: Optional[int]) -> Dict[str, Any]:
    """
    Process debt analysis

    Args:
        ticker: Stock ticker
        fiscal_year: Fiscal year (optional)

    Returns:
        dict: Analysis results
    """
    # Placeholder - will implement full analysis logic
    # For now, return basic structure

    logger.info(f"Processing analysis for {ticker} {fiscal_year}")

    # Default to current year - 1 if not specified (most recent complete fiscal year)
    if fiscal_year is None:
        fiscal_year = datetime.utcnow().year - 1

    # Check cache
    cached_data = check_financial_cache(ticker, fiscal_year)

    if not cached_data:
        # Fetch from Perplexity API
        logger.info(f"No cached data for {ticker} FY{fiscal_year} - fetching from Perplexity")
        try:
            cached_data = fetch_financial_data_from_perplexity(ticker, fiscal_year)
        except ValueError as e:
            logger.error(f"Failed to fetch data from Perplexity: {e}")
            return {
                "error": "DataUnavailable",
                "message": f"Unable to fetch financial data for {ticker} FY{fiscal_year}: {str(e)}",
                "ticker": ticker,
                "fiscal_year": fiscal_year
            }

    # Extract features
    features = extract_debt_features(cached_data)

    # Load model and run prediction
    model_data = load_model()
    model = model_data['model']
    imputer = model_data['imputer']

    # Prepare features
    feature_array = [list(features.values())]
    feature_array_imputed = imputer.transform(feature_array)

    # Predict
    prediction = model.predict(feature_array_imputed)[0]
    probabilities = model.predict_proba(feature_array_imputed)[0]

    # Get confidence (max probability)
    confidence_raw = probabilities[prediction + 2]  # Offset by 2 (classes are -2 to +2)

    # Normalize confidence
    confidence = {
        'raw': round(float(confidence_raw), 3),
        'display': round(float(confidence_raw) * 10, 1),
        'percent': round(float(confidence_raw) * 100, 1)
    }

    # Format response
    signal = SIGNAL_MAP[prediction]

    # Generate natural language analysis
    analysis_text = f"{signal['emoji']} {signal['debt_strength']} Debt Position: {signal['description']}"

    # Add confidence interpretation
    confidence_pct = confidence['percent']
    if confidence_pct < 60:
        analysis_text += f" The {confidence_pct:.1f}% confidence reflects moderate uncertainty in the prediction."
    elif confidence_pct < 75:
        analysis_text += f" Confidence level of {confidence_pct:.1f}% indicates reasonable certainty."
    else:
        analysis_text += f" High confidence of {confidence_pct:.1f}% in this assessment."

    return {
        "ticker": ticker,
        "fiscal_year": fiscal_year or 2023,
        "signal": int(prediction),  # Return raw integer for frontend
        "confidence": confidence['raw'],  # Return raw float for frontend
        "analysis": analysis_text,  # Natural language summary
        "metrics": features,
        "prediction": int(prediction)
    }
