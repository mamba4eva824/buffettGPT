#!/bin/bash

# Deploy Auth Callback Lambda Function

set -e

echo "=== Deploying Auth Callback Lambda Function ==="

# Variables
FUNCTION_NAME="buffett-dev-auth-callback"
HANDLER="auth_callback.lambda_handler"
RUNTIME="python3.11"
MEMORY_SIZE="256"
TIMEOUT="30"
REGION="us-east-1"

# Create deployment package
echo "Creating deployment package..."
cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api/backend/deploy

# Copy handler
cp ../src/handlers/auth_callback.py .

# Install dependencies
pip install google-auth google-auth-httplib2 google-auth-oauthlib requests PyJWT boto3 -t . --quiet

# Create zip
zip -r auth_callback.zip . -q -x "*.pyc" -x "__pycache__/*"

# Check if function exists
if aws lambda get-function --function-name $FUNCTION_NAME --region $REGION >/dev/null 2>&1; then
    echo "Updating existing function..."
    aws lambda update-function-code \
        --function-name $FUNCTION_NAME \
        --zip-file fileb://auth_callback.zip \
        --region $REGION \
        --output json > /dev/null
else
    echo "Creating new function..."

    # First, create IAM role
    aws iam create-role \
        --role-name ${FUNCTION_NAME}-role \
        --assume-role-policy-document '{
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }]
        }' \
        --region $REGION > /dev/null 2>&1 || true

    # Attach policies
    aws iam attach-role-policy \
        --role-name ${FUNCTION_NAME}-role \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole \
        --region $REGION > /dev/null 2>&1 || true

    # Wait for role to propagate
    sleep 5

    # Get account ID
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

    # Create function
    aws lambda create-function \
        --function-name $FUNCTION_NAME \
        --runtime $RUNTIME \
        --handler $HANDLER \
        --memory-size $MEMORY_SIZE \
        --timeout $TIMEOUT \
        --role arn:aws:iam::${ACCOUNT_ID}:role/${FUNCTION_NAME}-role \
        --zip-file fileb://auth_callback.zip \
        --environment Variables='{
            GOOGLE_CLIENT_ID="791748543155-4a5ad31ahdd90ifv1rqjsikurotas819.apps.googleusercontent.com",
            JWT_SECRET="your-jwt-secret-key-change-in-production",
            USERS_TABLE="buffett-dev-users",
            ENVIRONMENT="dev",
            PROJECT_NAME="buffett-chat-api"
        }' \
        --region $REGION \
        --output json > /dev/null
fi

# Update environment variables
echo "Updating environment variables..."
aws lambda update-function-configuration \
    --function-name $FUNCTION_NAME \
    --environment Variables='{
        GOOGLE_CLIENT_ID="791748543155-4a5ad31ahdd90ifv1rqjsikurotas819.apps.googleusercontent.com",
        JWT_SECRET="your-jwt-secret-key-change-in-production",
        USERS_TABLE="buffett-dev-users",
        ENVIRONMENT="dev",
        PROJECT_NAME="buffett-chat-api"
    }' \
    --region $REGION \
    --output json > /dev/null

echo "✓ Lambda function deployed: $FUNCTION_NAME"

# Create API Gateway integration
echo "Creating API Gateway integration..."

# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function --function-name $FUNCTION_NAME --region $REGION --query 'Configuration.FunctionArn' --output text)

# Create integration
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id 4onfe7pbpc \
    --integration-type AWS_PROXY \
    --integration-uri $LAMBDA_ARN \
    --payload-format-version 2.0 \
    --region $REGION \
    --query 'IntegrationId' \
    --output text)

echo "✓ Integration created: $INTEGRATION_ID"

# Create routes
echo "Creating API routes..."

# POST /auth/callback
aws apigatewayv2 create-route \
    --api-id 4onfe7pbpc \
    --route-key "POST /auth/callback" \
    --target "integrations/$INTEGRATION_ID" \
    --region $REGION \
    --output json > /dev/null

# OPTIONS /auth/callback (for CORS)
aws apigatewayv2 create-route \
    --api-id 4onfe7pbpc \
    --route-key "OPTIONS /auth/callback" \
    --target "integrations/$INTEGRATION_ID" \
    --region $REGION \
    --output json > /dev/null

echo "✓ Routes created"

# Add Lambda permission for API Gateway
aws lambda add-permission \
    --function-name $FUNCTION_NAME \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:${REGION}:*:4onfe7pbpc/*/*" \
    --region $REGION > /dev/null 2>&1 || true

echo ""
echo "=== Deployment Complete ==="
echo "Endpoint: https://4onfe7pbpc.execute-api.us-east-1.amazonaws.com/dev/auth/callback"
echo ""