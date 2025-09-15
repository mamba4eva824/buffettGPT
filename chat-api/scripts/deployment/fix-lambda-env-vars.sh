#!/bin/bash

# Fix Lambda Environment Variables for WebSocket Functions
# This script sets the required environment variables for all Lambda functions

set -e

echo "=== Setting Lambda Environment Variables ==="
echo

# Common environment variables
COMMON_ENV_VARS='{
  "ENVIRONMENT": "dev",
  "PROJECT_NAME": "buffett-chat-api",
  "LOG_LEVEL": "DEBUG",
  "KMS_KEY_ID": "alias/buffett-chat-api-dev"
}'

# Function to update Lambda environment variables
update_lambda_env() {
    local function_name=$1
    local additional_vars=$2
    
    echo "Updating environment variables for ${function_name}..."
    
    # Merge common and additional variables
    local all_vars=$(echo "$COMMON_ENV_VARS $additional_vars" | jq -s '.[0] * .[1]' | jq -c .)
    
    aws lambda update-function-configuration \
        --function-name "${function_name}" \
        --environment Variables="${all_vars}" \
        --region us-east-1 \
        --output json > /dev/null
    
    # Wait for update to complete
    aws lambda wait function-active \
        --function-name "${function_name}" \
        --region us-east-1
    
    echo "✓ Updated ${function_name}"
}

# WebSocket Connect function
update_lambda_env "buffett-dev-websocket-connect" '{
  "CONNECTIONS_TABLE": "buffett-dev-websocket-connections",
  "CHAT_SESSIONS_TABLE": "buffett-dev-chat-sessions",
  "ANONYMOUS_SESSIONS_TABLE": "buffett-dev-anonymous-sessions",
  "USERS_TABLE": "buffett-dev-users",
  "RATE_LIMITS_TABLE": "buffett-dev-enhanced-rate-limits"
}'

# WebSocket Disconnect function
update_lambda_env "buffett-dev-websocket-disconnect" '{
  "CONNECTIONS_TABLE": "buffett-dev-websocket-connections"
}'

# WebSocket Message function  
update_lambda_env "buffett-dev-websocket-message" '{
  "CONNECTIONS_TABLE": "buffett-dev-websocket-connections",
  "CHAT_SESSIONS_TABLE": "buffett-dev-chat-sessions",
  "CHAT_MESSAGES_TABLE": "buffett-dev-chat-messages",
  "CHAT_PROCESSING_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/128562022358/buffett-dev-chat-processing-queue",
  "WEBSOCKET_API_ENDPOINT": "52x14spfai.execute-api.us-east-1.amazonaws.com/dev"
}'

# Chat Processor function
update_lambda_env "buffett-dev-chat-processor" '{
  "CONNECTIONS_TABLE": "buffett-dev-websocket-connections",
  "CHAT_SESSIONS_TABLE": "buffett-dev-chat-sessions",
  "CHAT_MESSAGES_TABLE": "buffett-dev-chat-messages",
  "BEDROCK_AGENT_ID": "M9GEXYBRDW",
  "BEDROCK_AGENT_ALIAS": "buffett-advisor-alias",
  "BEDROCK_REGION": "us-east-1",
  "WEBSOCKET_API_ENDPOINT": "52x14spfai.execute-api.us-east-1.amazonaws.com/dev",
  "KNOWLEDGE_BASE_ID": "XQKJSKFVQY",
  "ENABLE_SEMANTIC_OPTIMIZATION": "true",
  "RELEVANCE_THRESHOLD": "0.8",
  "MAX_CHUNKS_PER_QUERY": "5"
}'

echo
echo "=== Environment Variables Update Complete ==="
echo
echo "Testing the WebSocket connect function..."

# Test the connect function with proper event structure
aws lambda invoke \
    --function-name "buffett-dev-websocket-connect" \
    --payload '{
        "requestContext": {
            "connectionId": "test123",
            "eventType": "CONNECT",
            "routeKey": "$connect"
        },
        "headers": {
            "User-Agent": "test-agent",
            "X-Forwarded-For": "127.0.0.1"
        },
        "queryStringParameters": {
            "user_id": "test_user"
        }
    }' \
    --region us-east-1 \
    /tmp/test-response.json \
    --cli-binary-format raw-in-base64-out > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "✓ WebSocket connect function is working"
    echo "Response:"
    cat /tmp/test-response.json | jq '.'
else
    echo "⚠ WebSocket connect function test failed"
fi

echo
echo "You can now test the WebSocket connection from your frontend."
echo "WebSocket URL: wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev"