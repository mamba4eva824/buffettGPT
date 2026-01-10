#!/bin/bash

# Build Lambda Layer for shared dependencies
# This script creates the dependencies-layer.zip file for Terraform

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LAYER_DIR="${BACKEND_DIR}/layer"
BUILD_DIR="${BACKEND_DIR}/build"

echo "Building Lambda layer for shared dependencies..."
echo "Layer directory: ${LAYER_DIR}"
echo "Build directory: ${BUILD_DIR}"

# Create build directory if it doesn't exist
mkdir -p "${BUILD_DIR}"

# Check if layer requirements exist
if [ ! -f "${LAYER_DIR}/requirements.txt" ]; then
    echo "Error: ${LAYER_DIR}/requirements.txt not found"
    exit 1
fi

# Create temp directory for layer build
TEMP_DIR="${BUILD_DIR}/temp_layer"
rm -rf "${TEMP_DIR}"
mkdir -p "${TEMP_DIR}/python"

echo "Installing dependencies from requirements.txt..."
echo "Requirements file contents:"
cat "${LAYER_DIR}/requirements.txt"

# Install dependencies to python/ directory (Lambda layer structure)
# Use platform-specific packages for Amazon Linux 2 (Lambda runtime)
pip install -r "${LAYER_DIR}/requirements.txt" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade \
  --target "${TEMP_DIR}/python" \
  --no-cache-dir

# Remove unnecessary files to reduce layer size
echo "Cleaning up unnecessary files..."
cd "${TEMP_DIR}/python"

# Remove compiled Python files
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove test directories and files
find . -type d -name "test*" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*test*" -exec rm -rf {} + 2>/dev/null || true

# Remove documentation and examples
find . -type d -name "docs" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true

# Create the layer zip file
echo "Creating dependencies-layer.zip..."
cd "${TEMP_DIR}"
zip -r "${BUILD_DIR}/dependencies-layer.zip" python/ -x "*.pyc" -x "*/__pycache__/*"

# Clean up temp directory
cd "${BUILD_DIR}"
rm -rf "${TEMP_DIR}"

# Show layer info
echo "✓ Created ${BUILD_DIR}/dependencies-layer.zip"
ls -lh "${BUILD_DIR}/dependencies-layer.zip" | awk '{print "  Size: " $5}'

# Show what's in the layer
echo ""
echo "Layer contents:"
unzip -l "${BUILD_DIR}/dependencies-layer.zip" | head -20

echo ""
echo "Lambda layer build complete!"

# NOTE: ML dependencies (numpy, scikit-learn) are handled by Docker
# for the prediction_ensemble Lambda. See:
# - chat-api/backend/lambda/prediction_ensemble/Dockerfile
# - chat-api/backend/lambda/prediction_ensemble/requirements.txt