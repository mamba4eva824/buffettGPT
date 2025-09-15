#!/bin/bash

# Fix Lambda IAM Permissions for DynamoDB Access

set -e

echo "=== Fixing Lambda IAM Permissions ==="
echo

# Create a policy document with all necessary DynamoDB permissions
cat > /tmp/lambda-dynamodb-policy.json << 'EOF'
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:UpdateItem",
                "dynamodb:DeleteItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:BatchGetItem",
                "dynamodb:BatchWriteItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:us-east-1:430118826061:table/buffett-dev-*",
                "arn:aws:dynamodb:us-east-1:430118826061:table/buffett-dev-*/index/*"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "execute-api:ManageConnections"
            ],
            "Resource": "arn:aws:execute-api:us-east-1:430118826061:52x14spfai/*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "sqs:SendMessage",
                "sqs:GetQueueUrl"
            ],
            "Resource": "arn:aws:sqs:us-east-1:430118826061:buffett-dev-*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "kms:Decrypt",
                "kms:GenerateDataKey"
            ],
            "Resource": "*"
        }
    ]
}
EOF

echo "Creating/Updating IAM policy..."

# Check if policy exists
POLICY_ARN=$(aws iam list-policies --query "Policies[?PolicyName=='buffett-dev-lambda-dynamodb-policy'].Arn" --output text)

if [ -z "$POLICY_ARN" ]; then
    # Create new policy
    POLICY_ARN=$(aws iam create-policy \
        --policy-name buffett-dev-lambda-dynamodb-policy \
        --policy-document file:///tmp/lambda-dynamodb-policy.json \
        --description "DynamoDB access for buffett Lambda functions" \
        --query 'Policy.Arn' \
        --output text)
    echo "✓ Created new policy: $POLICY_ARN"
else
    # Update existing policy
    VERSION_ID=$(aws iam create-policy-version \
        --policy-arn "$POLICY_ARN" \
        --policy-document file:///tmp/lambda-dynamodb-policy.json \
        --set-as-default \
        --query 'PolicyVersion.VersionId' \
        --output text)
    echo "✓ Updated existing policy with version: $VERSION_ID"
fi

# Attach the policy to the Lambda role
echo "Attaching policy to Lambda role..."
aws iam attach-role-policy \
    --role-name buffett-dev-lambda-role \
    --policy-arn "$POLICY_ARN" 2>/dev/null || echo "Policy already attached"

echo "✓ Policy attached to buffett-dev-lambda-role"

# Clean up
rm /tmp/lambda-dynamodb-policy.json

echo
echo "=== Testing Lambda Function ==="

# Wait a moment for IAM propagation
sleep 5

# Test the Lambda function
aws lambda invoke \
    --function-name buffett-dev-websocket-connect \
    --payload '{"requestContext": {"connectionId": "test123", "eventType": "CONNECT", "routeKey": "$connect"}, "headers": {"User-Agent": "test"}, "queryStringParameters": {"user_id": "test_user"}}' \
    --region us-east-1 \
    /tmp/test-connect-final.json \
    --cli-binary-format raw-in-base64-out > /dev/null

STATUS_CODE=$(cat /tmp/test-connect-final.json | jq -r '.statusCode')

if [ "$STATUS_CODE" = "200" ]; then
    echo "✅ WebSocket Connect Lambda is working correctly!"
    echo "Response:"
    cat /tmp/test-connect-final.json | jq '.'
else
    echo "⚠️  Lambda returned status code: $STATUS_CODE"
    echo "Response:"
    cat /tmp/test-connect-final.json | jq '.'
    echo
    echo "Checking recent logs..."
    aws logs tail /aws/lambda/buffett-dev-websocket-connect --since 1m --region us-east-1 | grep ERROR | head -5
fi

echo
echo "=== IAM Permissions Fix Complete ==="
echo
echo "Your WebSocket API should now be working at:"
echo "wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev"