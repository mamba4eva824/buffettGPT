#!/bin/bash

# Fix Lambda Deployment for WebSocket Functions
# This script creates proper deployment packages and updates the Lambda functions

set -e

echo "=== Fixing Lambda Deployment for WebSocket Functions ==="
echo

# Set variables
PROJECT_ROOT="/Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api"
BACKEND_DIR="${PROJECT_ROOT}/backend"
DEPLOY_DIR="${BACKEND_DIR}/deploy"
HANDLERS_DIR="${BACKEND_DIR}/src/handlers"
UTILS_DIR="${BACKEND_DIR}/src/utils"

# Create deploy directory if it doesn't exist
mkdir -p ${DEPLOY_DIR}

# Function to create deployment package
create_deployment_package() {
    local function_name=$1
    local handler_file=$2
    
    echo "Creating deployment package for ${function_name}..."
    
    # Create temporary directory
    local temp_dir=$(mktemp -d)
    
    # Copy handler file
    cp "${HANDLERS_DIR}/${handler_file}" "${temp_dir}/"
    
    # Copy utils directory if the handler needs it
    if grep -q "from utils" "${HANDLERS_DIR}/${handler_file}"; then
        cp -r "${UTILS_DIR}" "${temp_dir}/"
    fi
    
    # Create zip file
    cd "${temp_dir}"
    zip -r "${DEPLOY_DIR}/${function_name}.zip" . -q
    
    # Clean up
    cd -
    rm -rf "${temp_dir}"
    
    echo "✓ Created ${DEPLOY_DIR}/${function_name}.zip"
}

# Create deployment packages for all WebSocket functions
echo "Step 1: Creating deployment packages..."
create_deployment_package "websocket_connect" "websocket_connect.py"
create_deployment_package "websocket_disconnect" "websocket_disconnect.py"
create_deployment_package "websocket_message" "websocket_message.py"
create_deployment_package "chat_processor" "chat_processor.py"

echo
echo "Step 2: Updating Lambda functions..."

# Update Lambda functions with new code
update_lambda_function() {
    local function_suffix=$1
    local zip_file=$2
    
    local function_name="buffett-dev-${function_suffix}"
    
    echo "Updating ${function_name}..."
    
    aws lambda update-function-code \
        --function-name "${function_name}" \
        --zip-file "fileb://${DEPLOY_DIR}/${zip_file}" \
        --region us-east-1 \
        --output json > /dev/null
    
    # Wait for update to complete
    aws lambda wait function-updated \
        --function-name "${function_name}" \
        --region us-east-1
    
    echo "✓ Updated ${function_name}"
}

# Update all WebSocket Lambda functions
update_lambda_function "websocket-connect" "websocket_connect.zip"
update_lambda_function "websocket-disconnect" "websocket_disconnect.zip"
update_lambda_function "websocket-message" "websocket_message.zip"
update_lambda_function "chat-processor" "chat_processor.zip"

echo
echo "Step 3: Verifying deployments..."

# Test the connect function
echo "Testing websocket-connect function..."
aws lambda invoke \
    --function-name "buffett-dev-websocket-connect" \
    --payload '{"requestContext": {"connectionId": "test123", "eventType": "CONNECT"}, "headers": {}}' \
    --region us-east-1 \
    /tmp/test-response.json \
    --cli-binary-format raw-in-base64-out > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✓ websocket-connect function is responding"
else
    echo "⚠ websocket-connect function test failed"
fi

echo
echo "=== Lambda Deployment Fix Complete ==="
echo
echo "The Lambda functions have been updated with the correct code."
echo "You can now test the WebSocket connection from your frontend."
echo
echo "WebSocket URL: wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev"