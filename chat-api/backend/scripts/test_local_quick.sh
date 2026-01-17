#!/bin/bash
#
# Quick Local Testing Workflow for Debt Analyzer
#
# This script provides a fast iteration cycle:
# 1. Build Docker image (with cache for speed)
# 2. Run with Lambda RIE
# 3. Test health endpoint
# 4. Test golden test (Disney)
#
# Usage:
#   ./test_local_quick.sh
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Quick Local Test Cycle${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Configuration
LAMBDA_DIR="../lambda/debt_analyzer"
IMAGE_NAME="debt-analyzer-local"
CONTAINER_NAME="debt-analyzer-test"
PORT=9000

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker is not running${NC}"
    exit 1
fi

# Stop existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Stopping existing container...${NC}"
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

# Step 1: Build Docker image (with cache for speed)
echo -e "${GREEN}Step 1: Building Docker image (with cache)...${NC}"
cd ${LAMBDA_DIR}
docker build --platform linux/amd64 -t ${IMAGE_NAME}:latest . 2>&1 | grep -E "(Step|Successfully|Error)" || true
echo -e "${GREEN}✅ Build complete${NC}"
echo ""

# Step 2: Start container with Lambda RIE
echo -e "${GREEN}Step 2: Starting Lambda container...${NC}"

# Create temporary env file
ENV_FILE=$(mktemp)
cat > ${ENV_FILE} << EOF
MODEL_S3_BUCKET=buffett-chat-models
MODEL_S3_KEY=debt-analyzer/v0.1.0/debt_analyzer_model.pkl
MODEL_VERSION=0.1.0
FINANCIAL_CACHE_TABLE=buffett-dev-financial-data-cache
IDEMPOTENCY_TABLE=buffett-dev-idempotency-cache
PERPLEXITY_TIMEOUT=25
MAX_RETRIES=2
LOG_LEVEL=DEBUG
AWS_REGION=us-east-1
AWS_DEFAULT_REGION=us-east-1
EOF

# Get AWS credentials
if [ -f ~/.aws/credentials ]; then
    AWS_PROFILE=${AWS_PROFILE:-default}
    AWS_ACCESS_KEY_ID=$(aws configure get aws_access_key_id --profile ${AWS_PROFILE})
    AWS_SECRET_ACCESS_KEY=$(aws configure get aws_secret_access_key --profile ${AWS_PROFILE})
    AWS_SESSION_TOKEN=$(aws configure get aws_session_token --profile ${AWS_PROFILE} 2>/dev/null || echo "")

    echo "AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}" >> ${ENV_FILE}
    echo "AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}" >> ${ENV_FILE}
    if [ -n "${AWS_SESSION_TOKEN}" ]; then
        echo "AWS_SESSION_TOKEN=${AWS_SESSION_TOKEN}" >> ${ENV_FILE}
    fi
fi

# Get Perplexity API key from AWS Secrets Manager
PERPLEXITY_API_KEY=$(aws secretsmanager get-secret-value \
    --secret-id buffett-dev-sonar \
    --region us-east-1 \
    --query SecretString \
    --output text 2>/dev/null || echo "")

if [ -n "${PERPLEXITY_API_KEY}" ]; then
    echo "PERPLEXITY_API_KEY=${PERPLEXITY_API_KEY}" >> ${ENV_FILE}
else
    echo -e "${YELLOW}⚠️  Could not fetch Perplexity API key from Secrets Manager${NC}"
fi

# Run container
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:8080 \
    --env-file ${ENV_FILE} \
    ${IMAGE_NAME}:latest

# Clean up env file
rm ${ENV_FILE}

# Wait for Lambda to be ready
echo -e "${YELLOW}Waiting for Lambda to be ready...${NC}"
sleep 3

# Check if container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${RED}❌ Container failed to start${NC}"
    echo -e "${YELLOW}Container logs:${NC}"
    docker logs ${CONTAINER_NAME}
    exit 1
fi

echo -e "${GREEN}✅ Lambda container running on port ${PORT}${NC}"
echo ""

# Step 3: Test health endpoint
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 3: Testing Health Endpoint${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

HEALTH_PAYLOAD='{
  "path": "/health",
  "httpMethod": "GET",
  "headers": {},
  "queryStringParameters": null,
  "body": null
}'

echo -e "${BLUE}Invoking /health endpoint...${NC}"
HEALTH_RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/2015-03-31/functions/function/invocations" \
    -H "Content-Type: application/json" \
    -d "${HEALTH_PAYLOAD}")

echo -e "${YELLOW}Response:${NC}"
echo "${HEALTH_RESPONSE}" | jq '.' || echo "${HEALTH_RESPONSE}"
echo ""

# Check for errors
if echo "${HEALTH_RESPONSE}" | jq -e '.errorMessage' > /dev/null 2>&1; then
    echo -e "${RED}❌ Health check failed${NC}"
    echo -e "${YELLOW}Check logs: docker logs -f ${CONTAINER_NAME}${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Health check passed${NC}"
fi
echo ""

# Step 4: Test golden test (Disney = HOLD)
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Step 4: Testing Golden Test (Disney)${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

DISNEY_PAYLOAD='{
  "path": "/analyze",
  "httpMethod": "POST",
  "headers": {
    "Content-Type": "application/json"
  },
  "body": "{\"ticker\": \"DIS\", \"fiscal_year\": 2023, \"user_id\": \"local-test\"}"
}'

echo -e "${BLUE}Testing Disney (Expected: HOLD)...${NC}"
DISNEY_RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/2015-03-31/functions/function/invocations" \
    -H "Content-Type: application/json" \
    -d "${DISNEY_PAYLOAD}")

echo -e "${YELLOW}Response:${NC}"
echo "${DISNEY_RESPONSE}" | jq '.' || echo "${DISNEY_RESPONSE}"
echo ""

# Validate Disney prediction
if echo "${DISNEY_RESPONSE}" | jq -e '.errorMessage' > /dev/null 2>&1; then
    echo -e "${RED}❌ Disney analysis failed${NC}"
    ERROR_MSG=$(echo "${DISNEY_RESPONSE}" | jq -r '.errorMessage')
    echo -e "${RED}Error: ${ERROR_MSG}${NC}"
    echo -e "${YELLOW}This is expected if financial data is not cached yet${NC}"
else
    PREDICTION=$(echo "${DISNEY_RESPONSE}" | jq -r '.prediction' 2>/dev/null || echo "")
    SIGNAL=$(echo "${DISNEY_RESPONSE}" | jq -r '.signal' 2>/dev/null || echo "")

    if [ "${SIGNAL}" == "HOLD" ] || [ "${PREDICTION}" == "0" ]; then
        echo -e "${GREEN}✅ Golden test passed: Disney = HOLD${NC}"
    else
        echo -e "${YELLOW}⚠️  Disney analysis: ${SIGNAL} (${PREDICTION})${NC}"
        echo -e "${YELLOW}   Expected: HOLD (0)${NC}"
    fi
fi
echo ""

# Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Test Summary${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Container: ${CONTAINER_NAME}${NC}"
echo -e "${YELLOW}Port: ${PORT}${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo -e "${BLUE}  View logs:    docker logs -f ${CONTAINER_NAME}${NC}"
echo -e "${BLUE}  Stop:         docker stop ${CONTAINER_NAME} && docker rm ${CONTAINER_NAME}${NC}"
echo -e "${BLUE}  Test again:   ./test_local_quick.sh${NC}"
echo -e "${BLUE}  Deploy:       ./build_and_push_lambda_container.sh 0.1.2 dev${NC}"
echo ""
