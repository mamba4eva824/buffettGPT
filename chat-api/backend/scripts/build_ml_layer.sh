#!/bin/bash
set -e

# =============================================================================
# Build ML Lambda Layer for XGBoost inference
# =============================================================================
# Contains numpy and scikit-learn for ML inference
# Separate from main dependencies layer due to size (50MB+ compressed)
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
LAYER_DIR="${BACKEND_DIR}/layer"
BUILD_DIR="${BACKEND_DIR}/build"

echo "=========================================="
echo "Building ML Lambda Layer"
echo "=========================================="
echo "Layer directory: ${LAYER_DIR}"
echo "Build directory: ${BUILD_DIR}"

# Create build directory if it doesn't exist
mkdir -p "${BUILD_DIR}"

# Check if ML requirements exist
if [ ! -f "${LAYER_DIR}/requirements-ml.txt" ]; then
    echo "Error: ${LAYER_DIR}/requirements-ml.txt not found"
    exit 1
fi

# Create temp directory for layer build
TEMP_DIR="${BUILD_DIR}/temp_ml_layer"
rm -rf "${TEMP_DIR}"
mkdir -p "${TEMP_DIR}/python"

echo "Installing ML dependencies from requirements-ml.txt..."
echo "Requirements file contents:"
cat "${LAYER_DIR}/requirements-ml.txt"
echo ""

# Install dependencies to python/ directory (Lambda layer structure)
# Use platform-specific packages for Amazon Linux 2 (Lambda runtime)
pip install -r "${LAYER_DIR}/requirements-ml.txt" \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --only-binary=:all: \
  --upgrade \
  --target "${TEMP_DIR}/python" \
  --no-cache-dir

# Remove unnecessary files to reduce layer size
echo ""
echo "Cleaning up unnecessary files to reduce layer size..."
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

# Remove large unnecessary numpy/sklearn components
# These are optional and rarely used
rm -rf numpy/f2py 2>/dev/null || true
rm -rf numpy/tests 2>/dev/null || true
# Keep scipy - required by xgboost for inference

# Create the layer zip file
echo ""
echo "Creating ml-layer.zip..."
cd "${TEMP_DIR}"
zip -r "${BUILD_DIR}/ml-layer.zip" python/ -x "*.pyc" -x "*/__pycache__/*"

# Clean up temp directory
cd "${BUILD_DIR}"
rm -rf "${TEMP_DIR}"

# Show layer info
echo ""
echo "=========================================="
echo "ML Layer Build Complete!"
echo "=========================================="
echo "Package: ${BUILD_DIR}/ml-layer.zip"
ls -lh "${BUILD_DIR}/ml-layer.zip" | awk '{print "Size: " $5}'
echo ""

# Verify contents
echo "Layer contents (top-level packages):"
unzip -l "${BUILD_DIR}/ml-layer.zip" | grep "python/[^/]*/$" | head -20

echo ""
echo "Note: This layer contains numpy and scikit-learn for ML inference."
echo "It should be attached to Lambdas that run XGBoost predictions."
