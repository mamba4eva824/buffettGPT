#!/bin/bash
#
# Build and Push analysis_followup Lambda Container to ECR
#
# Builds the Docker image for the analysis_followup Lambda (FastAPI + LWA wrapper
# around the canonical handler at src/handlers/analysis_followup.py) and pushes
# to the shared `buffett/analysis-followup` ECR repository in the project's AWS
# account. Both dev and staging Lambdas read from this same repo.
#
# Usage:
#   ./build_and_push_analysis_followup.sh [tag-suffix]
#
# Examples:
#   ./build_and_push_analysis_followup.sh                # uses git SHA + latest
#   ./build_and_push_analysis_followup.sh staging-test   # uses staging-test + latest
#
# Prerequisites:
#   - AWS CLI configured (account 430118826061, region us-east-1)
#   - Docker running
#   - ECR repo `buffett/analysis-followup` exists (Terraform-managed in dev)
#

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Resolve repo root from this script's location so we always build from
# chat-api/backend/ regardless of where the script was invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Tag — accept argument, otherwise use git SHA (short).
if [ "$#" -ge 1 ] && [ -n "$1" ]; then
    TAG="$1"
else
    TAG=$(git -C "${BACKEND_DIR}" rev-parse --short=12 HEAD 2>/dev/null || echo "untagged")
fi

AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="buffett/analysis-followup"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
LOCAL_IMAGE="${ECR_REPOSITORY}:${TAG}"
REMOTE_IMAGE="${ECR_REGISTRY}/${ECR_REPOSITORY}"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build & Push: analysis-followup${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "${BLUE}Backend dir:  ${BACKEND_DIR}${NC}"
echo -e "${BLUE}AWS account:  ${AWS_ACCOUNT_ID}${NC}"
echo -e "${BLUE}AWS region:   ${AWS_REGION}${NC}"
echo -e "${BLUE}ECR repo:     ${ECR_REPOSITORY}${NC}"
echo -e "${BLUE}Tag:          ${TAG}${NC}"
echo

if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker is not running${NC}"
    exit 1
fi

# Step 1: Build (build context = chat-api/backend so we can COPY src/ + investment_research/).
echo -e "${GREEN}Step 1: Building Docker image (--platform linux/amd64)...${NC}"
docker build \
    --no-cache \
    --platform linux/amd64 \
    -f "${BACKEND_DIR}/lambda/analysis_followup/Dockerfile" \
    -t "${LOCAL_IMAGE}" \
    -t "${ECR_REPOSITORY}:latest" \
    "${BACKEND_DIR}"
echo -e "${GREEN}OK${NC}"
echo

# Step 2: ECR login.
echo -e "${GREEN}Step 2: ECR login...${NC}"
aws ecr get-login-password --region "${AWS_REGION}" | \
    docker login --username AWS --password-stdin "${ECR_REGISTRY}"
echo -e "${GREEN}OK${NC}"
echo

# Step 3: Tag for remote.
echo -e "${GREEN}Step 3: Tagging for ECR push...${NC}"
docker tag "${LOCAL_IMAGE}"            "${REMOTE_IMAGE}:${TAG}"
docker tag "${ECR_REPOSITORY}:latest"  "${REMOTE_IMAGE}:latest"
echo -e "${GREEN}OK${NC}"
echo

# Step 4: Push.
echo -e "${GREEN}Step 4: Pushing to ECR...${NC}"
docker push "${REMOTE_IMAGE}:${TAG}"
docker push "${REMOTE_IMAGE}:latest"
echo -e "${GREEN}OK${NC}"
echo

# Step 5: Image metadata.
IMAGE_DIGEST=$(aws ecr describe-images \
    --repository-name "${ECR_REPOSITORY}" \
    --image-ids imageTag="${TAG}" \
    --region "${AWS_REGION}" \
    --query 'imageDetails[0].imageDigest' --output text)
IMAGE_SIZE_MB=$(aws ecr describe-images \
    --repository-name "${ECR_REPOSITORY}" \
    --image-ids imageTag="${TAG}" \
    --region "${AWS_REGION}" \
    --query 'imageDetails[0].imageSizeInBytes' --output text \
    | awk '{printf "%.2f", $1/1024/1024}')

echo -e "${GREEN}========================================${NC}"
echo -e "${BLUE}Image URI:    ${REMOTE_IMAGE}:${TAG}${NC}"
echo -e "${BLUE}Digest:       ${IMAGE_DIGEST}${NC}"
echo -e "${BLUE}Size:         ${IMAGE_SIZE_MB} MB${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo -e "${YELLOW}Next steps (dev):${NC}"
echo -e "  aws lambda update-function-code \\"
echo -e "    --function-name buffett-dev-analysis-followup \\"
echo -e "    --image-uri ${REMOTE_IMAGE}:${TAG} \\"
echo -e "    --publish"
echo
echo -e "${YELLOW}Next steps (staging — only after Phase 1.5e migration):${NC}"
echo -e "  aws lambda update-function-code \\"
echo -e "    --function-name buffett-staging-analysis-followup \\"
echo -e "    --image-uri ${REMOTE_IMAGE}:${TAG} \\"
echo -e "    --publish"
