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

# List of Lambda functions to package
FUNCTIONS=(
    "auth_callback"
    "chat_http_handler"
    "chat_processor"
    "conversations_handler"
    "websocket_connect"
    "websocket_disconnect"
    "websocket_message"
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

    # Copy the handler file
    cp "${SRC_DIR}/${FUNCTION}.py" "${TEMP_DIR}/"

    # Copy any shared utilities if they exist
    if [ -d "${SRC_DIR}/shared" ]; then
        cp -r "${SRC_DIR}/shared" "${TEMP_DIR}/"
    fi

    # Copy utils directory (contains rate_limiter and other utilities)
    if [ -d "${BACKEND_DIR}/src/utils" ]; then
        cp -r "${BACKEND_DIR}/src/utils" "${TEMP_DIR}/"
    fi

    # Copy handlers/utils directory (contains conversation_updater and other utilities)
    if [ -d "${SRC_DIR}/utils" ]; then
        cp -r "${SRC_DIR}/utils" "${TEMP_DIR}/"
    fi

    # Copy requirements if they exist (for Layer creation later)
    if [ -f "${SRC_DIR}/requirements_${FUNCTION}.txt" ]; then
        cp "${SRC_DIR}/requirements_${FUNCTION}.txt" "${TEMP_DIR}/requirements.txt"
    elif [ -f "${BACKEND_DIR}/requirements.txt" ]; then
        cp "${BACKEND_DIR}/requirements.txt" "${TEMP_DIR}/requirements.txt"
    fi

    # Create the zip file
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