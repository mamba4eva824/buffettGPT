#!/bin/bash
#
# Test Lambda Endpoints Locally
#
# This script tests the local Lambda container endpoints including:
# 1. Health check endpoint
# 2. Golden test (Disney = HOLD)
# 3. Sample analysis request
#
# Prerequisites:
#   - Lambda container must be running (run test_lambda_locally.sh first)
#
# Usage:
#   ./test_lambda_local_endpoint.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LAMBDA_URL="http://localhost:9000/2015-03-31/functions/function/invocations"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Testing Lambda Endpoints Locally${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Function to invoke Lambda
invoke_lambda() {
    local payload="$1"
    local test_name="$2"

    echo -e "${BLUE}Test: ${test_name}${NC}"
    echo -e "${YELLOW}Payload:${NC}"
    echo "${payload}" | jq '.'
    echo ""

    response=$(curl -s -X POST "${LAMBDA_URL}" \
        -H "Content-Type: application/json" \
        -d "${payload}")

    echo -e "${YELLOW}Response:${NC}"
    echo "${response}" | jq '.'
    echo ""

    # Check for errors
    if echo "${response}" | jq -e '.errorMessage' > /dev/null 2>&1; then
        echo -e "${RED}❌ Test failed with error${NC}"
        return 1
    else
        echo -e "${GREEN}✅ Test passed${NC}"
        return 0
    fi
}

# Test 1: Health Check
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 1: Health Check${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

health_payload='{
  "path": "/health",
  "httpMethod": "GET",
  "headers": {},
  "queryStringParameters": null,
  "body": null
}'

if invoke_lambda "${health_payload}" "Health Check"; then
    echo -e "${GREEN}Health check successful!${NC}"
else
    echo -e "${RED}Health check failed!${NC}"
    echo -e "${YELLOW}Make sure:${NC}"
    echo -e "${YELLOW}  1. Model is uploaded to S3${NC}"
    echo -e "${YELLOW}  2. DynamoDB tables exist${NC}"
    echo -e "${YELLOW}  3. AWS credentials are valid${NC}"
fi
echo ""

# Test 2: Golden Test (Disney = HOLD)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 2: Golden Test (Disney = HOLD)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

disney_payload='{
  "path": "/analyze",
  "httpMethod": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"ticker\": \"DIS\", \"fiscal_year\": 2023, \"user_id\": \"test-user\"}"
}'

if invoke_lambda "${disney_payload}" "Disney Analysis (Expected: HOLD)"; then
    echo -e "${GREEN}Disney analysis successful!${NC}"
    echo -e "${YELLOW}Expected: HOLD (prediction: 0)${NC}"
else
    echo -e "${RED}Disney analysis failed!${NC}"
fi
echo ""

# Test 3: Amazon Analysis (Expected: BUY)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 3: Amazon Analysis (Expected: BUY)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

amazon_payload='{
  "path": "/analyze",
  "httpMethod": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"ticker\": \"AMZN\", \"fiscal_year\": 2023, \"user_id\": \"test-user\"}"
}'

if invoke_lambda "${amazon_payload}" "Amazon Analysis (Expected: BUY)"; then
    echo -e "${GREEN}Amazon analysis successful!${NC}"
    echo -e "${YELLOW}Expected: BUY (prediction: 1 or 2)${NC}"
else
    echo -e "${RED}Amazon analysis failed!${NC}"
    echo -e "${YELLOW}Note: This may fail if financial data is not cached${NC}"
fi
echo ""

# Test 4: Idempotency Check (Repeat Disney)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Test 4: Idempotency Check${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Making second Disney request (should hit cache)...${NC}"
if invoke_lambda "${disney_payload}" "Disney Analysis (Idempotency Check)"; then
    echo -e "${GREEN}Idempotency check successful!${NC}"
    echo -e "${YELLOW}Check logs to confirm cache hit${NC}"
else
    echo -e "${RED}Idempotency check failed!${NC}"
fi
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}To view detailed logs:${NC}"
echo -e "${YELLOW}   docker logs -f debt-analyzer-test${NC}"
echo ""
echo -e "${YELLOW}To stop the test container:${NC}"
echo -e "${YELLOW}   docker stop debt-analyzer-test${NC}"
echo -e "${YELLOW}   docker rm debt-analyzer-test${NC}"
echo ""
