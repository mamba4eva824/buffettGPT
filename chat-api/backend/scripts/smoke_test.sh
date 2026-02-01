#!/bin/bash
# =============================================================================
# Post-Deployment Smoke Tests
# =============================================================================
# Purpose: Validate Lambda deployments are healthy before completing CI/CD
# Usage: ./smoke_test.sh <environment> [--test-failure]
#
# Tests Lambda functions:
#   - Investment Research (report streaming)
#   - Analysis Followup (follow-up Q&A)
#
# Exit codes:
#   0 = All tests passed
#   1 = One or more tests failed
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-"dev"}
TEST_FAILURE_FLAG=${2:-""}
PROJECT_NAME="buffett"
AWS_REGION=${AWS_REGION:-"us-east-1"}
TIMEOUT_SECONDS=30

# Counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[PASS]${NC} $1"
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

run_test() {
    local test_name="$1"
    local test_command="$2"

    TESTS_RUN=$((TESTS_RUN + 1))
    echo ""
    log_info "Test ${TESTS_RUN}: ${test_name}"

    if eval "$test_command"; then
        log_success "${test_name}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        log_error "${test_name}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

get_function_url() {
    local function_name="$1"
    aws lambda get-function-url-config \
        --function-name "$function_name" \
        --region "$AWS_REGION" \
        --query 'FunctionUrl' \
        --output text 2>/dev/null
}

# =============================================================================
# Main Script
# =============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Post-Deployment Smoke Tests${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Environment:${NC} ${ENVIRONMENT}"
echo -e "${BLUE}Region:${NC}      ${AWS_REGION}"
echo -e "${BLUE}Timeout:${NC}     ${TIMEOUT_SECONDS}s per request"
echo ""

# --test-failure flag: Force a failure to test CI/CD gate
if [[ "$TEST_FAILURE_FLAG" == "--test-failure" ]]; then
    echo -e "${YELLOW}========================================${NC}"
    echo -e "${YELLOW}  TEST MODE: Forcing failure${NC}"
    echo -e "${YELLOW}========================================${NC}"
    echo ""
    log_warning "This is an intentional failure to verify the CI/CD gate works correctly."
    echo ""
    exit 1
fi

# =============================================================================
# Investment Research Lambda Tests
# =============================================================================

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Investment Research Lambda${NC}"
echo -e "${GREEN}========================================${NC}"

IR_FUNCTION="${PROJECT_NAME}-${ENVIRONMENT}-investment-research"
log_info "Function: ${IR_FUNCTION}"

IR_URL=$(get_function_url "$IR_FUNCTION")

if [[ -z "$IR_URL" || "$IR_URL" == "None" ]]; then
    log_error "Could not get Function URL for ${IR_FUNCTION}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_info "URL: ${IR_URL}"

    # Test 1: Health endpoint
    run_test "Investment Research - Health Check" \
        "curl -sf --max-time ${TIMEOUT_SECONDS} '${IR_URL}health' | jq -e '.status == \"healthy\"' > /dev/null" || true

    # Test 2: TOC endpoint (accept 200 or 404 - report may not be cached)
    run_test "Investment Research - TOC Fetch (AAPL)" \
        "HTTP_CODE=\$(curl -s -o /dev/null -w '%{http_code}' --max-time ${TIMEOUT_SECONDS} '${IR_URL}report/AAPL/toc'); [[ \"\$HTTP_CODE\" == \"200\" || \"\$HTTP_CODE\" == \"404\" ]]" || true
fi

# =============================================================================
# Analysis Followup Lambda Tests
# =============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Analysis Followup Lambda${NC}"
echo -e "${GREEN}========================================${NC}"

AF_FUNCTION="${PROJECT_NAME}-${ENVIRONMENT}-analysis-followup"
log_info "Function: ${AF_FUNCTION}"

AF_URL=$(get_function_url "$AF_FUNCTION")

if [[ -z "$AF_URL" || "$AF_URL" == "None" ]]; then
    log_error "Could not get Function URL for ${AF_FUNCTION}"
    TESTS_FAILED=$((TESTS_FAILED + 1))
else
    log_info "URL: ${AF_URL}"

    # Test 3: Health endpoint
    run_test "Analysis Followup - Health Check" \
        "curl -sf --max-time ${TIMEOUT_SECONDS} '${AF_URL}health' | jq -e '.status == \"healthy\"' > /dev/null" || true
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Smoke Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Tests Run:${NC}    ${TESTS_RUN}"
echo -e "${GREEN}Tests Passed:${NC} ${TESTS_PASSED}"
echo -e "${RED}Tests Failed:${NC} ${TESTS_FAILED}"
echo ""

if [[ ${TESTS_FAILED} -eq 0 ]]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ALL SMOKE TESTS PASSED${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "${GREEN}Deployment to ${ENVIRONMENT} is healthy!${NC}"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  SMOKE TESTS FAILED${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo -e "${RED}Deployment to ${ENVIRONMENT} has issues!${NC}"
    echo ""
    echo -e "${YELLOW}Troubleshooting:${NC}"
    echo -e "  1. Check CloudWatch logs for errors"
    echo -e "  2. Verify Lambda functions deployed correctly"
    echo -e "  3. Check DynamoDB tables are accessible"
    echo -e "  4. Verify Bedrock model access is configured"
    echo ""
    exit 1
fi
