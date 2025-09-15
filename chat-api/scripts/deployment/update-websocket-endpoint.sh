#!/bin/bash
# Update Lambda WebSocket Endpoint Script
# Run this after terraform apply to set the WebSocket endpoint

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
ENVIRONMENT=${1:-dev}
REGION=${2:-us-east-1}

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Update Lambda WebSocket Endpoint${NC}"
echo -e "${GREEN}Environment: ${ENVIRONMENT}${NC}"
echo -e "${GREEN}Region: ${REGION}${NC}"
echo -e "${GREEN}========================================${NC}"

# Change to environment directory
cd "environments/${ENVIRONMENT}"

# Get the WebSocket endpoint from Terraform output
echo -e "\n${BLUE}Getting WebSocket endpoint from Terraform outputs...${NC}"
WEBSOCKET_ENDPOINT=$(terraform output -raw websocket_api_endpoint 2>/dev/null || echo "")

if [ -z "$WEBSOCKET_ENDPOINT" ]; then
    echo -e "${YELLOW}Warning: Could not get WebSocket endpoint from Terraform outputs${NC}"
    echo -e "${YELLOW}Make sure you have run 'terraform apply' first${NC}"
    exit 1
fi

echo -e "${GREEN}WebSocket Endpoint: ${WEBSOCKET_ENDPOINT}${NC}"

# Get the Lambda function name (using current naming convention)
FUNCTION_NAME="buffett-chat-api-${ENVIRONMENT}-chat-processor"

echo -e "\n${BLUE}Updating Lambda function: ${FUNCTION_NAME}${NC}"

# Get current environment variables
CURRENT_VARS=$(aws lambda get-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --query 'Environment.Variables' \
    --output json 2>/dev/null || echo "{}")

# Check if function exists
if [ "$CURRENT_VARS" = "{}" ]; then
    echo -e "${YELLOW}Warning: Lambda function ${FUNCTION_NAME} not found${NC}"
    exit 1
fi

# Update environment variables with WebSocket endpoint
echo "$CURRENT_VARS" | jq --arg ws "$WEBSOCKET_ENDPOINT" '. + {WEBSOCKET_API_ENDPOINT: $ws}' > /tmp/lambda-env.json

# Update the Lambda function
aws lambda update-function-configuration \
    --function-name "$FUNCTION_NAME" \
    --region "$REGION" \
    --environment Variables="$(cat /tmp/lambda-env.json)" \
    --output json > /dev/null

echo -e "${GREEN}✓ Successfully updated Lambda function with WebSocket endpoint${NC}"

# Clean up
rm -f /tmp/lambda-env.json

echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}Update Complete!${NC}"
echo -e "${GREEN}========================================${NC}"

echo -e "\n${BLUE}To verify the update:${NC}"
echo "aws lambda get-function-configuration --function-name $FUNCTION_NAME --region $REGION --query 'Environment.Variables.WEBSOCKET_API_ENDPOINT'"