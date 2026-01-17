#!/bin/bash
#
# Create Placeholder Lambda Image for Initial Deployment
#
# This script creates a minimal placeholder Lambda image and pushes it to ECR
# so that Terraform can create the Lambda function. The real image will be
# built and pushed later.
#
# Usage:
#   ./create_placeholder_image.sh <version> <environment>
#
# Example:
#   ./create_placeholder_image.sh 0.1.0 dev
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

VERSION=${1:-"0.1.0"}
ENVIRONMENT=${2:-"dev"}

PROJECT_NAME="buffett-chat"  # Fixed: Must match Terraform ECR repository name
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPOSITORY="${PROJECT_NAME}/debt-analyzer"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_TAG="${VERSION}-${ENVIRONMENT}"

echo -e "${GREEN}Creating placeholder Lambda image...${NC}"
echo -e "${YELLOW}This is a minimal image for initial Terraform deployment${NC}"
echo ""

# Create temporary directory
TMP_DIR=$(mktemp -d)
cd ${TMP_DIR}

# Create minimal Dockerfile
cat > Dockerfile << 'EOF'
FROM public.ecr.aws/lambda/python:3.11

CMD ["index.handler"]

# Minimal placeholder handler
RUN echo 'def handler(event, context): return {"statusCode": 200, "body": "Placeholder"}' > ${LAMBDA_TASK_ROOT}/index.py
EOF

echo -e "${GREEN}Building placeholder image...${NC}"
docker build --platform linux/amd64 -t ${ECR_REPOSITORY}:${IMAGE_TAG} .

# Authenticate to ECR
echo -e "${GREEN}Authenticating to ECR...${NC}"
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin ${ECR_REGISTRY}

# Tag for ECR
docker tag ${ECR_REPOSITORY}:${IMAGE_TAG} ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}

# Push to ECR
echo -e "${GREEN}Pushing placeholder image to ECR...${NC}"
docker push ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}

# Cleanup
cd /
rm -rf ${TMP_DIR}

echo -e "${GREEN}✅ Placeholder image created and pushed${NC}"
echo -e "${YELLOW}Image URI: ${ECR_REGISTRY}/${ECR_REPOSITORY}:${IMAGE_TAG}${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo -e "${YELLOW}  1. Run: terraform apply${NC}"
echo -e "${YELLOW}  2. Build real image: ./build_and_push_lambda_container.sh ${VERSION} ${ENVIRONMENT}${NC}"
echo -e "${YELLOW}  3. Lambda will automatically use new image on next invocation${NC}"
