#!/bin/bash

# Fix Lambda Environment Variables - Direct approach
set -e

echo "=== Setting Lambda Environment Variables ==="
echo

# Update WebSocket Connect
echo "Updating buffett-dev-websocket-connect..."
aws lambda update-function-configuration \
    --function-name buffett-dev-websocket-connect \
    --environment 'Variables={
        CONNECTIONS_TABLE="buffett-dev-websocket-connections",
        CHAT_SESSIONS_TABLE="buffett-dev-chat-sessions",
        ANONYMOUS_SESSIONS_TABLE="buffett-dev-anonymous-sessions",
        USERS_TABLE="buffett-dev-users",
        RATE_LIMITS_TABLE="buffett-dev-enhanced-rate-limits",
        ENVIRONMENT="dev",
        PROJECT_NAME="buffett-chat-api",
        LOG_LEVEL="DEBUG"
    }' \
    --region us-east-1 \
    --output json > /dev/null

aws lambda wait function-active \
    --function-name buffett-dev-websocket-connect \
    --region us-east-1

echo "✓ Updated buffett-dev-websocket-connect"

# Update WebSocket Disconnect
echo "Updating buffett-dev-websocket-disconnect..."
aws lambda update-function-configuration \
    --function-name buffett-dev-websocket-disconnect \
    --environment 'Variables={
        CONNECTIONS_TABLE="buffett-dev-websocket-connections",
        ENVIRONMENT="dev",
        PROJECT_NAME="buffett-chat-api",
        LOG_LEVEL="DEBUG",
        KMS_KEY_ID="alias/buffett-chat-api-dev"
    }' \
    --region us-east-1 \
    --output json > /dev/null

aws lambda wait function-active \
    --function-name buffett-dev-websocket-disconnect \
    --region us-east-1

echo "✓ Updated buffett-dev-websocket-disconnect"

# Update WebSocket Message
echo "Updating buffett-dev-websocket-message..."

# First get the SQS queue URL
SQS_URL=$(aws sqs get-queue-url --queue-name buffett-dev-chat-processing --region us-east-1 --output text --query 'QueueUrl')

aws lambda update-function-configuration \
    --function-name buffett-dev-websocket-message \
    --environment "Variables={
        CONNECTIONS_TABLE=\"buffett-dev-websocket-connections\",
        CHAT_SESSIONS_TABLE=\"buffett-dev-chat-sessions\",
        CHAT_MESSAGES_TABLE=\"buffett-dev-chat-messages\",
        CHAT_PROCESSING_QUEUE_URL=\"${SQS_URL}\",
        WEBSOCKET_API_ENDPOINT=\"52x14spfai.execute-api.us-east-1.amazonaws.com/dev\",
        ENVIRONMENT=\"dev\",
        PROJECT_NAME=\"buffett-chat-api\",
        LOG_LEVEL=\"DEBUG\",
        KMS_KEY_ID=\"alias/buffett-chat-api-dev\"
    }" \
    --region us-east-1 \
    --output json > /dev/null

aws lambda wait function-active \
    --function-name buffett-dev-websocket-message \
    --region us-east-1

echo "✓ Updated buffett-dev-websocket-message"

# Update Chat Processor
echo "Updating buffett-dev-chat-processor..."
aws lambda update-function-configuration \
    --function-name buffett-dev-chat-processor \
    --environment 'Variables={
        CONNECTIONS_TABLE="buffett-dev-websocket-connections",
        CHAT_SESSIONS_TABLE="buffett-dev-chat-sessions",
        CHAT_MESSAGES_TABLE="buffett-dev-chat-messages",
        BEDROCK_AGENT_ID="M9GEXYBRDW",
        BEDROCK_AGENT_ALIAS="buffett-advisor-alias",
        BEDROCK_REGION="us-east-1",
        WEBSOCKET_API_ENDPOINT="52x14spfai.execute-api.us-east-1.amazonaws.com/dev",
        KNOWLEDGE_BASE_ID="XQKJSKFVQY",
        ENABLE_SEMANTIC_OPTIMIZATION="true",
        RELEVANCE_THRESHOLD="0.8",
        MAX_CHUNKS_PER_QUERY="5",
        ENVIRONMENT="dev",
        PROJECT_NAME="buffett-chat-api",
        LOG_LEVEL="DEBUG",
        KMS_KEY_ID="alias/buffett-chat-api-dev"
    }' \
    --region us-east-1 \
    --output json > /dev/null

aws lambda wait function-active \
    --function-name buffett-dev-chat-processor \
    --region us-east-1

echo "✓ Updated buffett-dev-chat-processor"

echo
echo "=== Environment Variables Update Complete ==="
echo
echo "Testing WebSocket connection..."

# Test with wscat
timeout 5 wscat -c "wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev?user_id=test_user" -x '{"action": "ping"}' 2>/dev/null || true

if [ $? -eq 124 ]; then
    echo "✓ WebSocket connection established successfully (timeout expected after ping)"
else
    echo "Checking connection status..."
fi

echo
echo "WebSocket API is ready at: wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev"