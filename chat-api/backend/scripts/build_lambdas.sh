#!/bin/bash

# Build Lambda deployment packages for Terraform
# This script creates individual zip files for each Lambda function

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
SRC_DIR="${BACKEND_DIR}/src/handlers"
BUILD_DIR="${BACKEND_DIR}/build"

echo "Building Lambda deployment packages..."
echo "Source directory: ${SRC_DIR}"
echo "Build directory: ${BUILD_DIR}"

# Create build directory if it doesn't exist
mkdir -p "${BUILD_DIR}"

# Build Lambda layer first
echo ""
echo "Building Lambda layer..."
"${SCRIPT_DIR}/build_layer.sh"

# List of Lambda functions to package (zip-based)
# NOTE: prediction_ensemble is Docker-based, see lambda/prediction_ensemble/
# NOTE: WebSocket handlers (websocket_connect, websocket_disconnect, websocket_message,
#       chat_processor, chat_http_handler) removed in Phase 2 of WebSocket deprecation
FUNCTIONS=(
    "auth_callback"
    "auth_verify"
    "conversations_handler"
    "search_handler"
    "analysis_followup"
    "stripe_webhook_handler"
    "subscription_handler"
    "waitlist_handler"
    "sp500_pipeline"
    "sp500_backfill"
    "earnings_calendar_checker"
    "sp500_aggregator"
    "market_intel_chat"
    "value_insights_handler"
)

# Build each function
for FUNCTION in "${FUNCTIONS[@]}"; do
    echo ""
    echo "Building ${FUNCTION}..."

    # Check if the handler file exists
    if [ ! -f "${SRC_DIR}/${FUNCTION}.py" ]; then
        echo "Warning: ${SRC_DIR}/${FUNCTION}.py not found, skipping..."
        continue
    fi

    # Create temp directory for this function
    TEMP_DIR="${BUILD_DIR}/temp_${FUNCTION}"
    rm -rf "${TEMP_DIR}"
    mkdir -p "${TEMP_DIR}"

    # Copy only the handler file
    cp "${SRC_DIR}/${FUNCTION}.py" "${TEMP_DIR}/"

    # Copy the utils directory from src/utils
    UTILS_DIR="$(dirname "${SRC_DIR}")/utils"
    if [ -d "${UTILS_DIR}" ]; then
        cp -r "${UTILS_DIR}" "${TEMP_DIR}/"
    fi

    # Copy any shared utilities if they exist
    if [ -d "${SRC_DIR}/shared" ]; then
        cp -r "${SRC_DIR}/shared" "${TEMP_DIR}/"
    fi

    # Copy investment_research module for sp500 pipeline functions
    INVEST_DIR="${BACKEND_DIR}/investment_research"
    if [[ "${FUNCTION}" == sp500_* || "${FUNCTION}" == "earnings_calendar_checker" || "${FUNCTION}" == "market_intel_chat" ]]; then
        if [ -d "${INVEST_DIR}" ]; then
            cp -r "${INVEST_DIR}" "${TEMP_DIR}/"
        fi
    fi

    # Create the zip file (excluding requirements.txt since dependencies are in Lambda Layer)
    cd "${TEMP_DIR}"
    zip -r "${BUILD_DIR}/${FUNCTION}.zip" . -x "*.pyc" -x "__pycache__/*" -x "requirements.txt"

    # Clean up temp directory
    cd "${BUILD_DIR}"
    rm -rf "${TEMP_DIR}"

    # Show zip file info
    echo "✓ Created ${BUILD_DIR}/${FUNCTION}.zip"
    ls -lh "${BUILD_DIR}/${FUNCTION}.zip" | awk '{print "  Size: " $5}'
done

echo ""
echo "Build complete! Lambda packages created in ${BUILD_DIR}/"
ls -la "${BUILD_DIR}"/*.zip 2>/dev/null || echo "No zip files created"