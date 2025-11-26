#!/bin/bash
#
# Test Bedrock Action Group Locally
#
# This script tests the Lambda with a Bedrock action group event format
# to reproduce the Decimal serialization issue.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
LAMBDA_URL="http://localhost:9000/2015-03-31/functions/function/invocations"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Testing Bedrock Action Group Locally${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Test: Bedrock Action Group Invocation (TSLA)
echo -e "${BLUE}Test: Bedrock Action Group - TSLA Analysis${NC}"
echo ""

# Bedrock action group event format
bedrock_payload='{
  "messageVersion": "1.0",
  "agent": {
    "name": "debt-analyst-agent",
    "id": "ZCIAI0BCN8",
    "alias": "1ICIBY3O2W",
    "version": "3"
  },
  "inputText": "Analyze TSLA debt health",
  "sessionId": "test-session-123",
  "actionGroup": "debt-analyzer-actions",
  "apiPath": "/analyze-debt",
  "httpMethod": "POST",
  "parameters": [
    {
      "name": "ticker",
      "type": "string",
      "value": "TSLA"
    }
  ],
  "requestBody": {
    "content": {
      "application/json": {
        "properties": [
          {
            "name": "ticker",
            "type": "string",
            "value": "TSLA"
          }
        ]
      }
    }
  }
}'

echo -e "${YELLOW}Payload (Bedrock Action Format):${NC}"
echo "${bedrock_payload}" | jq '.'
echo ""

echo -e "${YELLOW}Invoking Lambda...${NC}"
response=$(curl -s -X POST "${LAMBDA_URL}" \
    -H "Content-Type: application/json" \
    -d "${bedrock_payload}")

echo -e "${YELLOW}Response:${NC}"
echo "${response}" | jq '.'
echo ""

# Check for errors
if echo "${response}" | jq -e '.errorMessage' > /dev/null 2>&1; then
    echo -e "${RED}❌ Test failed with error:${NC}"
    echo "${response}" | jq -r '.errorMessage'

    # Check specifically for Decimal error
    if echo "${response}" | grep -q "Decimal.*not JSON serializable"; then
        echo ""
        echo -e "${RED}🔍 FOUND THE BUG: Decimal serialization error!${NC}"
        echo -e "${YELLOW}   This is the error we're trying to fix.${NC}"
    fi

    exit 1
else
    # Check if response is successful
    if echo "${response}" | jq -e '.response.httpStatusCode == 200' > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Test passed! DecimalEncoder is working!${NC}"

        # Show the analysis result
        echo ""
        echo -e "${GREEN}Analysis Result:${NC}"
        echo "${response}" | jq -r '.response.responseBody."application/json".body' | jq '.'

        exit 0
    else
        echo -e "${RED}❌ Unexpected response format${NC}"
        exit 1
    fi
fi
