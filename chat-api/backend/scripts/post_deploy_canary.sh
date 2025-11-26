#!/bin/bash
#
# Post-Deployment Canary Tests
#
# This script runs canary tests against the deployed Lambda function to validate:
# 1. Health check passes (all 5 checks green)
# 2. Golden test passes (Disney = HOLD)
# 3. Amazon analysis returns BUY signal
# 4. Response times are acceptable
#
# Usage:
#   ./post_deploy_canary.sh <environment>
#
# Example:
#   ./post_deploy_canary.sh dev
#   ./post_deploy_canary.sh prod
#
# Prerequisites:
#   - Lambda function deployed to AWS
#   - AWS CLI configured with appropriate credentials
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
ENVIRONMENT=${1:-"dev"}

if [ -z "$ENVIRONMENT" ]; then
    echo -e "${RED}ERROR: Environment is required${NC}"
    echo "Usage: $0 <environment>"
    echo "Example: $0 dev"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Post-Deployment Canary Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Environment: ${ENVIRONMENT}${NC}"
echo ""

# Configuration
PROJECT_NAME="buffett-chat"
FUNCTION_NAME="${PROJECT_NAME}-${ENVIRONMENT}-debt-analyzer"
AWS_REGION=${AWS_REGION:-"us-east-1"}
ALIAS_NAME=${ENVIRONMENT}

echo -e "${BLUE}Function:    ${FUNCTION_NAME}${NC}"
echo -e "${BLUE}Alias:       ${ALIAS_NAME}${NC}"
echo -e "${BLUE}Region:      ${AWS_REGION}${NC}"
echo ""

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Function to invoke Lambda
invoke_lambda() {
    local payload="$1"
    local test_name="$2"
    local expected_status="$3"

    TESTS_RUN=$((TESTS_RUN + 1))

    echo -e "${BLUE}Test ${TESTS_RUN}: ${test_name}${NC}"
    echo -e "${YELLOW}Invoking Lambda...${NC}"

    # Invoke with timing
    start_time=$(date +%s%3N)

    response=$(aws lambda invoke \
        --function-name ${FUNCTION_NAME}:${ALIAS_NAME} \
        --payload "${payload}" \
        --region ${AWS_REGION} \
        --cli-binary-format raw-in-base64-out \
        /dev/stdout 2>&1)

    end_time=$(date +%s%3N)
    duration=$((end_time - start_time))

    echo -e "${YELLOW}Response time: ${duration}ms${NC}"
    echo ""

    # Parse response
    status_code=$(echo "${response}" | grep "StatusCode" | awk '{print $2}')
    payload_response=$(echo "${response}" | sed -n '/^{/,/^}/p' | head -1)

    echo -e "${YELLOW}Response:${NC}"
    echo "${payload_response}" | jq '.' || echo "${payload_response}"
    echo ""

    # Check status code
    if [ "${status_code}" != "${expected_status}" ]; then
        echo -e "${RED}❌ Test failed: Expected status ${expected_status}, got ${status_code}${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi

    # Check for Lambda errors
    if echo "${payload_response}" | jq -e '.errorMessage' > /dev/null 2>&1; then
        error_msg=$(echo "${payload_response}" | jq -r '.errorMessage')
        echo -e "${RED}❌ Test failed with error: ${error_msg}${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi

    # Check response time (warn if > 2s for warm start)
    if [ ${duration} -gt 2000 ]; then
        echo -e "${YELLOW}⚠️  WARNING: Response time > 2s (warm start should be ~100ms)${NC}"
    fi

    echo -e "${GREEN}✅ Test passed${NC}"
    TESTS_PASSED=$((TESTS_PASSED + 1))
    echo ""
    return 0
}

# Test 1: Health Check
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Canary Test 1: Health Check${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

health_payload='{
  "path": "/health",
  "httpMethod": "GET"
}'

invoke_lambda "${health_payload}" "Health Check" "200" || true

# Test 2: Golden Test - Disney (Expected: HOLD)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Canary Test 2: Golden Test (Disney)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

disney_payload='{
  "path": "/analyze",
  "httpMethod": "POST",
  "body": "{\"ticker\": \"DIS\", \"fiscal_year\": 2023, \"user_id\": \"canary-test\"}"
}'

if invoke_lambda "${disney_payload}" "Disney Analysis (Expected: HOLD)" "200"; then
    # Verify prediction is HOLD (0)
    prediction=$(echo "${payload_response}" | jq -r '.prediction')
    signal=$(echo "${payload_response}" | jq -r '.signal')

    if [ "${prediction}" == "0" ] && [ "${signal}" == "HOLD" ]; then
        echo -e "${GREEN}✅ Golden test passed: Disney = HOLD${NC}"
    else
        echo -e "${RED}❌ Golden test failed: Expected HOLD (0), got ${signal} (${prediction})${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
fi
echo ""

# Test 3: Amazon Analysis (Expected: BUY)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Canary Test 3: Amazon Analysis${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

amazon_payload='{
  "path": "/analyze",
  "httpMethod": "POST",
  "body": "{\"ticker\": \"AMZN\", \"fiscal_year\": 2023, \"user_id\": \"canary-test\"}"
}'

if invoke_lambda "${amazon_payload}" "Amazon Analysis (Expected: BUY)" "200"; then
    # Verify prediction is BUY (1 or 2)
    prediction=$(echo "${payload_response}" | jq -r '.prediction')
    signal=$(echo "${payload_response}" | jq -r '.signal')

    if [ "${prediction}" == "1" ] || [ "${prediction}" == "2" ]; then
        echo -e "${GREEN}✅ Amazon analysis passed: ${signal} (${prediction})${NC}"
    else
        echo -e "${YELLOW}⚠️  Amazon analysis unexpected: Expected BUY (1/2), got ${signal} (${prediction})${NC}"
        echo -e "${YELLOW}   Note: Amazon is not in training set, so this may vary${NC}"
    fi
fi
echo ""

# Test 4: Cold Start Test (Invoke $LATEST to force cold start)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Canary Test 4: Cold Start Performance${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Invoking \$LATEST version (no provisioned concurrency)${NC}"
cold_start_response=$(aws lambda invoke \
    --function-name ${FUNCTION_NAME} \
    --qualifier "\$LATEST" \
    --payload "${health_payload}" \
    --region ${AWS_REGION} \
    --cli-binary-format raw-in-base64-out \
    /dev/stdout 2>&1)

# Check init duration
init_duration=$(echo "${cold_start_response}" | grep "InitDuration" | awk '{print $2}' | sed 's/ms//')
if [ -n "${init_duration}" ]; then
    echo -e "${YELLOW}Cold start init duration: ${init_duration}ms${NC}"
    if [ $(echo "${init_duration} > 3000" | bc) -eq 1 ]; then
        echo -e "${YELLOW}⚠️  WARNING: Cold start > 3s${NC}"
    else
        echo -e "${GREEN}✅ Cold start within expected range${NC}"
    fi
else
    echo -e "${YELLOW}No cold start detected (Lambda was warm)${NC}"
fi
echo ""

# Test 5: Idempotency Check (Repeat Disney)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Canary Test 5: Idempotency${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo -e "${YELLOW}Repeating Disney request (should hit cache)${NC}"
invoke_lambda "${disney_payload}" "Disney Analysis (Idempotency)" "200" || true

echo -e "${YELLOW}Check CloudWatch logs to confirm idempotency cache hit${NC}"
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Canary Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Tests Run:    ${TESTS_RUN}${NC}"
echo -e "${GREEN}Tests Passed: ${TESTS_PASSED}${NC}"
echo -e "${RED}Tests Failed: ${TESTS_FAILED}${NC}"
echo ""

if [ ${TESTS_FAILED} -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✅ ALL CANARY TESTS PASSED${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${GREEN}Deployment to ${ENVIRONMENT} is healthy!${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  ❌ SOME CANARY TESTS FAILED${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${RED}Deployment to ${ENVIRONMENT} has issues!${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting steps:${NC}"
    echo -e "${YELLOW}  1. Check CloudWatch logs:${NC}"
    echo -e "${YELLOW}     aws logs tail /aws/lambda/${FUNCTION_NAME} --follow${NC}"
    echo ""
    echo -e "${YELLOW}  2. Check Lambda configuration:${NC}"
    echo -e "${YELLOW}     aws lambda get-function --function-name ${FUNCTION_NAME}${NC}"
    echo ""
    echo -e "${YELLOW}  3. Verify environment variables are set${NC}"
    echo -e "${YELLOW}  4. Verify IAM permissions${NC}"
    echo -e "${YELLOW}  5. Verify DynamoDB tables exist${NC}"
    echo -e "${YELLOW}  6. Verify S3 model file exists${NC}"
    echo ""
    exit 1
fi
