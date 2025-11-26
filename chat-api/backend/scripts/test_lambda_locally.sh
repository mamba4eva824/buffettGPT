#!/bin/bash
#
# Test Lambda Debt Analyzer Locally with Docker Lambda RIE
#
# This script builds the Docker container and runs it locally using the
# AWS Lambda Runtime Interface Emulator (RIE) on port 9000.
#
# Usage:
#   ./test_lambda_locally.sh
#
# Then in another terminal, test with:
#   ./test_lambda_local_endpoint.sh
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Local Lambda RIE Test${NC}"
echo -e "${GREEN}========================================${NC}"

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

# Stop and remove existing container if running
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}Stopping existing container...${NC}"
    docker stop ${CONTAINER_NAME} 2>/dev/null || true
    docker rm ${CONTAINER_NAME} 2>/dev/null || true
fi

# Build the Docker image
echo -e "${GREEN}Building Docker image...${NC}"
cd ${LAMBDA_DIR}
docker build -t ${IMAGE_NAME}:latest .

# Set up environment variables for local testing
echo -e "${GREEN}Setting up environment variables...${NC}"

# Create a temporary env file
ENV_FILE=$(mktemp)
cat > ${ENV_FILE} << EOF
MODEL_S3_BUCKET=buffett-chat-models
MODEL_S3_KEY=debt-analyzer/v0.1.0/debt_analyzer_model.pkl
MODEL_VERSION=0.1.0
FINANCIAL_CACHE_TABLE=buffett-chat-dev-financial-data-cache
IDEMPOTENCY_TABLE=buffett-chat-dev-idempotency-cache
PERPLEXITY_TIMEOUT=25
LOG_LEVEL=DEBUG
AWS_REGION=us-east-1
EOF

# Get AWS credentials for local testing
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

# Note: Perplexity API key needs to be fetched from Secrets Manager
# For local testing, you can add it manually to the env file or fetch it here
echo -e "${YELLOW}Note: PERPLEXITY_API_KEY should be set manually for local testing${NC}"
echo -e "${YELLOW}      or fetched from AWS Secrets Manager${NC}"

# Run the container with Lambda RIE
echo -e "${GREEN}Starting Lambda container on port ${PORT}...${NC}"
docker run -d \
    --name ${CONTAINER_NAME} \
    -p ${PORT}:8080 \
    --env-file ${ENV_FILE} \
    ${IMAGE_NAME}:latest

# Clean up env file
rm ${ENV_FILE}

# Wait for container to be ready
echo -e "${YELLOW}Waiting for Lambda to be ready...${NC}"
sleep 3

# Check if container is running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${GREEN}✅ Lambda container is running!${NC}"
    echo -e "${GREEN}   Container: ${CONTAINER_NAME}${NC}"
    echo -e "${GREEN}   Port: ${PORT}${NC}"
    echo ""
    echo -e "${YELLOW}To test the endpoints, run:${NC}"
    echo -e "${YELLOW}   ./test_lambda_local_endpoint.sh${NC}"
    echo ""
    echo -e "${YELLOW}To view logs:${NC}"
    echo -e "${YELLOW}   docker logs -f ${CONTAINER_NAME}${NC}"
    echo ""
    echo -e "${YELLOW}To stop the container:${NC}"
    echo -e "${YELLOW}   docker stop ${CONTAINER_NAME}${NC}"
    echo -e "${YELLOW}   docker rm ${CONTAINER_NAME}${NC}"
else
    echo -e "${RED}❌ Container failed to start${NC}"
    echo -e "${YELLOW}Checking logs:${NC}"
    docker logs ${CONTAINER_NAME}
    exit 1
fi
