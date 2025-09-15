#!/bin/bash

# Package Auth Lambda and Dependencies for Terraform

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
LAMBDA_DIR="$SCRIPT_DIR/lambda"
LAYER_DIR="$SCRIPT_DIR/layers"

echo "Packaging Auth Callback Lambda..."

# Create directories
mkdir -p "$LAMBDA_DIR"
mkdir -p "$LAYER_DIR/python"

# Package Lambda function
cp "$SCRIPT_DIR/../../../backend/src/handlers/auth_callback.py" "$LAMBDA_DIR/"
cd "$LAMBDA_DIR"
zip -r auth_callback.zip auth_callback.py

echo "✓ Lambda function packaged"

# Package dependencies as a layer
echo "Packaging dependencies layer..."
cd "$LAYER_DIR/python"
pip install --target . google-auth google-auth-httplib2 google-auth-oauthlib requests PyJWT --quiet

cd "$LAYER_DIR"
zip -r auth_dependencies.zip python/ -q

echo "✓ Dependencies layer packaged"
echo "Ready for Terraform deployment!"