#!/bin/bash
#
# Build and Push Lambda Container to ECR
#
# This script builds the debt analyzer Lambda container, tags it with a version,
# and pushes it to Amazon ECR.
#
# Usage:
#   ./build_and_push_lambda_container.sh <version> <environment>
#
# Example:
#   ./build_and_push_lambda_container.sh 0.1.0 dev
#   ./build_and_push_lambda_container.sh 0.2.1 prod
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - Docker installed and running
#   - ECR repository created (via Terraform)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse arguments
VERSION=${1:-"0.1.0"}
ENVIRONMENT=${2:-"dev"}

if [ -z "$VERSION" ]; then
    echo -e "${RED}ERROR: Version is required${NC}"
    echo "Usage: $0 <version> <environment>"
    echo "Example: $0 0.1.0 dev"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build and Push Lambda Container${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Version:     ${VERSION}${NC}"
echo -e "${BLUE}Environment: ${ENVIRONMENT}${NC}"
echo ""

# Configuration
PROJECT_NAME="buffett-chat"
LAMBDA_DIR="../lambda/debt_analyzer"
AWS_REGION=${AWS_REGION:-"us-east-1"}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="${PROJECT_NAME}/debt-analyzer"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_TAG="${VERSION}-${ENVIRONMENT}"

echo -e "${BLUE}AWS Account:   ${AWS_ACCOUNT_ID}${NC}"
echo -e "${BLUE}AWS Region:    ${AWS_REGION}${NC}"
echo -e "${BLUE}ECR Registry:  ${ECR_REGISTRY}${NC}"
echo -e "${BLUE}ECR Repo:      ${ECR_REPOSITORY}${NC}"
echo -e "${BLUE}Image Tag:     ${IMAGE_TAG}${NC}"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker is not running${NC}"
    exit 1
fi

# Step 1: Build the Docker image
echo -e "${GREEN}Step 1: Building Docker image...${NC}"
cd ${LAMBDA_DIR}

# NOTE: Using --no-cache to ensure fresh build with latest source code
# Docker's layer caching can sometimes miss source file changes
docker build \
    --no-cache \
    --platform linux/amd64 \
    --build-arg VERSION=${VERSION} \
    --build-arg ENVIRONMENT=${ENVIRONMENT} \
    -t ${ECR_REPOSITORY}:${IMAGE_TAG} \
    -t ${ECR_REPOSITORY}:latest \
    .

echo -e "${GREEN}✅ Image built successfully${NC}"
echo ""

# Step 2: Authenticate Docker to ECR
echo -e "${GREEN}Step 2: Authenticating to ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

echo -e "${GREEN}✅ Authenticated to ECR${NC}"
echo ""

# Step 3: Check if ECR repository exists
echo -e "${GREEN}Step 3: Checking ECR repository...${NC}"
if ! aws ecr describe-repositories --repository-names ${ECR_REPOSITORY} --region ${AWS_REGION} > /dev/null 2>&1; then
    echo -e "${YELLOW}Repository does not exist. Creating...${NC}"
    aws ecr create-repository \
        --repository-name ${ECR_REPOSITORY} \
        --region ${AWS_REGION} \
        --image-scanning-configuration scanOnPush=true \
        --encryption-configuration encryptionType=AES256
    echo -e "${GREEN}✅ Repository created${NC}"
else
    echo -e "${GREEN}✅ Repository exists${NC}"
fi
echo ""

# Step 4: Tag the image for ECR
echo -e "${GREEN}Step 4: Tagging image for ECR...${NC}"
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
docker tag ${ECR_REPOSITORY}:latest ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

echo -e "${GREEN}✅ Image tagged${NC}"
echo ""

# Step 5: Push to ECR
echo -e "${GREEN}Step 5: Pushing image to ECR...${NC}"
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:latest

echo -e "${GREEN}✅ Image pushed to ECR${NC}"
echo ""

# Step 6: Get image details
echo -e "${GREEN}Step 6: Image details...${NC}"
IMAGE_DIGEST=$(aws ecr describe-images \
    --repository-name ${ECR_REPOSITORY} \
    --image-ids imageTag=${IMAGE_TAG} \
    --region ${AWS_REGION} \
    --query 'imageDetails[0].imageDigest' \
    --output text)

IMAGE_SIZE=$(aws ecr describe-images \
    --repository-name ${ECR_REPOSITORY} \
    --image-ids imageTag=${IMAGE_TAG} \
    --region ${AWS_REGION} \
    --query 'imageDetails[0].imageSizeInBytes' \
    --output text)

IMAGE_SIZE_MB=$(echo "scale=2; ${IMAGE_SIZE} / 1024 / 1024" | bc)

echo -e "${BLUE}Image URI:    ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}${NC}"
echo -e "${BLUE}Image Digest: ${IMAGE_DIGEST}${NC}"
echo -e "${BLUE}Image Size:   ${IMAGE_SIZE_MB} MB${NC}"
echo ""

# Check image size warning
if (( $(echo "${IMAGE_SIZE_MB} > 500" | bc -l) )); then
    echo -e "${YELLOW}⚠️  WARNING: Image size is larger than 500 MB${NC}"
    echo -e "${YELLOW}   Consider optimizing dependencies${NC}"
else
    echo -e "${GREEN}✅ Image size is within target (< 500 MB)${NC}"
fi
echo ""

# Step 7: Summary
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Build Complete${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${GREEN}✅ Container built and pushed successfully!${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "${YELLOW}  1. Update Terraform variable 'debt_analyzer_image_tag' to: ${IMAGE_TAG}${NC}"
echo -e "${YELLOW}  2. Run: cd ../../terraform/environments/${ENVIRONMENT}${NC}"
echo -e "${YELLOW}  3. Run: terraform plan${NC}"
echo -e "${YELLOW}  4. Run: terraform apply${NC}"
echo ""
echo -e "${YELLOW}To test locally first:${NC}"
echo -e "${YELLOW}  ./test_lambda_locally.sh${NC}"
echo ""
