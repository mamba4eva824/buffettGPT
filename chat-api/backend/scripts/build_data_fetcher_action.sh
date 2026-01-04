#!/bin/bash
set -e

# =============================================================================
# Build script for ensemble-prediction-data-fetcher-action Lambda
# =============================================================================
# REFACTORED: Copies existing code from prediction_ensemble instead of recreating
#
# This Lambda is the "data fetcher" piece of the two-Lambda architecture:
# - prediction-ensemble: HTTP streaming to frontend (with LWA/FastAPI)
# - data-fetcher-action: Bedrock action groups (pure Python, no LWA)
#
# Both use the SAME business logic, just different entry points.
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$BACKEND_DIR/build"
PREDICTION_ENSEMBLE_DIR="$BACKEND_DIR/lambda/prediction_ensemble"
DATA_FETCHER_DIR="$BACKEND_DIR/lambda/ensemble_prediction_data_fetcher_action"
SRC_DIR="$BACKEND_DIR/src"
ZIP_NAME="ensemble_prediction_data_fetcher_action.zip"

echo "=========================================="
echo "Building ensemble-prediction-data-fetcher-action Lambda"
echo "REUSING code from prediction_ensemble"
echo "=========================================="

# Verify source directories exist
if [ ! -d "$PREDICTION_ENSEMBLE_DIR" ]; then
    echo "Error: prediction_ensemble directory not found: $PREDICTION_ENSEMBLE_DIR"
    exit 1
fi

# Create build directory
mkdir -p "$BUILD_DIR"

# Create temporary packaging directory
TEMP_DIR=$(mktemp -d)
echo "Using temp directory: $TEMP_DIR"

# -----------------------------------------------------------------------------
# Copy entry point handler (thin wrapper)
# -----------------------------------------------------------------------------
echo "Creating entry point handler..."
cat > "$TEMP_DIR/handler.py" << 'EOF'
"""
Ensemble Prediction Data Fetcher Action Lambda - Entry Point

This is a thin wrapper that calls the existing action_group handler.
The actual business logic is in handlers/action_group.py (reused from prediction_ensemble).

Architecture:
- prediction-ensemble Lambda: HTTP streaming via LWA/FastAPI
- data-fetcher-action Lambda: Bedrock action groups (this file) - pure Python

Both use the SAME handlers/action_group.py for business logic.
"""

import json
import logging
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))


def lambda_handler(event, context):
    """
    Lambda entry point for Bedrock action group invocations.

    This handler receives events directly from Bedrock (no LWA/FastAPI).
    It delegates to the existing action_group handler for all business logic.
    """
    logger.info(f"[DATA_FETCHER] Received event: {json.dumps(event)[:1000]}")

    try:
        # Import the existing action group handler
        from handlers.action_group import handle_action_group_request, is_action_group_event

        # Validate this is an action group event
        if not is_action_group_event(event):
            logger.warning("[DATA_FETCHER] Event is not an action group invocation")
            return {
                'messageVersion': '1.0',
                'response': {
                    'actionGroup': event.get('actionGroup', 'Unknown'),
                    'apiPath': event.get('apiPath', '/unknown'),
                    'httpMethod': 'POST',
                    'httpStatusCode': 400,
                    'responseBody': {
                        'application/json': {
                            'body': json.dumps({'error': 'Invalid action group event'})
                        }
                    }
                }
            }

        # Delegate to existing handler - this returns the properly formatted Bedrock response
        response = handle_action_group_request(event)

        logger.info(f"[DATA_FETCHER] Successfully processed request")
        return response

    except Exception as e:
        logger.error(f"[DATA_FETCHER] Error: {str(e)}", exc_info=True)
        return {
            'messageVersion': '1.0',
            'response': {
                'actionGroup': event.get('actionGroup', 'FinancialAnalysis'),
                'apiPath': event.get('apiPath', '/analyze'),
                'httpMethod': 'POST',
                'httpStatusCode': 500,
                'responseBody': {
                    'application/json': {
                        'body': json.dumps({'error': f'Internal error: {str(e)}'})
                    }
                }
            }
        }
EOF

# -----------------------------------------------------------------------------
# Copy handlers from prediction_ensemble
# -----------------------------------------------------------------------------
echo "Copying handlers from prediction_ensemble..."
mkdir -p "$TEMP_DIR/handlers"
cp "$PREDICTION_ENSEMBLE_DIR/handlers/__init__.py" "$TEMP_DIR/handlers/" 2>/dev/null || touch "$TEMP_DIR/handlers/__init__.py"
cp "$PREDICTION_ENSEMBLE_DIR/handlers/action_group.py" "$TEMP_DIR/handlers/"

# -----------------------------------------------------------------------------
# Copy services from prediction_ensemble
# -----------------------------------------------------------------------------
echo "Copying services from prediction_ensemble..."
mkdir -p "$TEMP_DIR/services"
cp "$PREDICTION_ENSEMBLE_DIR/services/__init__.py" "$TEMP_DIR/services/" 2>/dev/null || touch "$TEMP_DIR/services/__init__.py"
cp "$PREDICTION_ENSEMBLE_DIR/services/inference.py" "$TEMP_DIR/services/"

# -----------------------------------------------------------------------------
# Copy models from prediction_ensemble
# -----------------------------------------------------------------------------
echo "Copying models from prediction_ensemble..."
mkdir -p "$TEMP_DIR/models"
cp "$PREDICTION_ENSEMBLE_DIR/models/__init__.py" "$TEMP_DIR/models/" 2>/dev/null || touch "$TEMP_DIR/models/__init__.py"
cp "$PREDICTION_ENSEMBLE_DIR/models/schemas.py" "$TEMP_DIR/models/"
cp "$PREDICTION_ENSEMBLE_DIR/models/metrics.py" "$TEMP_DIR/models/"

# -----------------------------------------------------------------------------
# Copy config from prediction_ensemble
# -----------------------------------------------------------------------------
echo "Copying config from prediction_ensemble..."
mkdir -p "$TEMP_DIR/config"
cp "$PREDICTION_ENSEMBLE_DIR/config/__init__.py" "$TEMP_DIR/config/" 2>/dev/null || touch "$TEMP_DIR/config/__init__.py"
cp "$PREDICTION_ENSEMBLE_DIR/config/settings.py" "$TEMP_DIR/config/"

# -----------------------------------------------------------------------------
# Copy utils (shared between both Lambdas)
# -----------------------------------------------------------------------------
echo "Copying shared utilities..."
mkdir -p "$TEMP_DIR/utils"
cp "$SRC_DIR/utils/__init__.py" "$TEMP_DIR/utils/" 2>/dev/null || touch "$TEMP_DIR/utils/__init__.py"
cp "$SRC_DIR/utils/fmp_client.py" "$TEMP_DIR/utils/"
cp "$SRC_DIR/utils/feature_extractor.py" "$TEMP_DIR/utils/"
cp "$SRC_DIR/utils/logger.py" "$TEMP_DIR/utils/"

# Copy ensemble_metrics if it exists
if [ -f "$SRC_DIR/utils/ensemble_metrics.py" ]; then
    cp "$SRC_DIR/utils/ensemble_metrics.py" "$TEMP_DIR/utils/"
elif [ -f "$PREDICTION_ENSEMBLE_DIR/utils/ensemble_metrics.py" ]; then
    cp "$PREDICTION_ENSEMBLE_DIR/utils/ensemble_metrics.py" "$TEMP_DIR/utils/"
fi

# -----------------------------------------------------------------------------
# List package contents
# -----------------------------------------------------------------------------
echo ""
echo "Package contents:"
find "$TEMP_DIR" -type f -name "*.py" | sed "s|$TEMP_DIR/||" | sort

# -----------------------------------------------------------------------------
# Create zip package
# -----------------------------------------------------------------------------
echo ""
echo "Creating zip package..."
cd "$TEMP_DIR"
zip -r "$BUILD_DIR/$ZIP_NAME" . -x "*.pyc" -x "__pycache__/*" -x "*.so"

# Cleanup
rm -rf "$TEMP_DIR"

# Show results
echo ""
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo "Package: $BUILD_DIR/$ZIP_NAME"
echo "Size: $(du -h "$BUILD_DIR/$ZIP_NAME" | cut -f1)"
echo ""
echo "This Lambda reuses:"
echo "  - handlers/action_group.py (Bedrock response formatting)"
echo "  - services/inference.py (ML inference)"
echo "  - models/schemas.py (JSON serialization)"
echo "  - utils/fmp_client.py (DynamoDB caching)"
echo ""
echo "Required layers:"
echo "  - dependencies-layer (httpx, boto3, etc.)"
echo "  - ml-layer (numpy, scikit-learn)"
