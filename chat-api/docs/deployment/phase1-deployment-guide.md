# Phase 1 Deployment Guide: Anonymous User Support

## Overview
This guide walks through deploying Phase 1 of the authentication enhancement, which adds support for anonymous users with device fingerprinting and tiered rate limiting.

## What's Been Implemented

### 1. Device Fingerprinting Module (`device_fingerprint.py`)
- Generates stable device identifiers for anonymous users
- Uses multiple signals (IP, User-Agent, CloudFront headers)
- Distinguishes between authenticated and anonymous users
- Validates fingerprint formats

### 2. Tiered Rate Limiting (`tiered_rate_limiter.py`)
- Supports multiple user tiers (anonymous, authenticated, premium, enterprise)
- Implements daily, hourly, and per-minute limits
- Burst protection to prevent rapid requests
- Auto-cleanup via TTL for anonymous records

### 3. Enhanced WebSocket Handler (`websocket_connect_enhanced.py`)
- Supports both authenticated and anonymous connections
- Applies rate limiting before connection establishment
- Returns tier-specific features and limits to client
- Tracks device information for analytics

### 4. Infrastructure (Terraform)
- DynamoDB table for rate limits with GSI for device fingerprints
- Anonymous sessions table with TTL for auto-cleanup
- CloudWatch metrics and alarms for monitoring
- Dashboard for usage visualization

## Deployment Steps

### Step 1: Deploy Infrastructure

```bash
# Navigate to chat-api directory
cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api

# Initialize Terraform if needed
terraform init

# Plan the changes
terraform plan -var-file="terraform.tfvars" -out=phase1.tfplan

# Review the plan (should show new tables and monitoring resources)

# Apply the changes
terraform apply phase1.tfplan
```

### Step 2: Update Lambda Environment Variables

Add these environment variables to your Lambda functions:

```bash
# For WebSocket Connect Lambda
RATE_LIMITS_TABLE=buffett-chat-dev-rate-limits
ANONYMOUS_SESSIONS_TABLE=buffett-chat-dev-anon-sessions
USERS_TABLE=buffett-chat-dev-users

# For Message Processing Lambda
RATE_LIMITS_TABLE=buffett-chat-dev-rate-limits
```

### Step 3: Deploy Lambda Functions

#### Option A: Using AWS CLI

```bash
# Package the enhanced WebSocket handler
cd chat-api/backend
zip -r websocket-connect-enhanced.zip src/handlers/websocket_connect_enhanced.py src/utils/

# Update the Lambda function
aws lambda update-function-code \
  --function-name buffett-chat-dev-websocket-connect \
  --zip-file fileb://websocket-connect-enhanced.zip

# Update environment variables
aws lambda update-function-configuration \
  --function-name buffett-chat-dev-websocket-connect \
  --environment Variables='{
    "RATE_LIMITS_TABLE":"buffett-chat-dev-rate-limits",
    "ANONYMOUS_SESSIONS_TABLE":"buffett-chat-dev-anon-sessions",
    "USERS_TABLE":"buffett-chat-dev-users"
  }'
```

#### Option B: Using Terraform (Recommended)

Update your Lambda resource to use the new handler:

```hcl
resource "aws_lambda_function" "websocket_connect" {
  filename         = data.archive_file.websocket_handlers.output_path
  function_name    = "${var.project_name}-${var.environment}-websocket-connect"
  handler          = "websocket_connect_enhanced.lambda_handler"  # Updated handler
  runtime          = "python3.11"
  
  environment {
    variables = {
      CONNECTIONS_TABLE     = aws_dynamodb_table.connections.name
      CHAT_SESSIONS_TABLE   = aws_dynamodb_table.chat_sessions.name
      RATE_LIMITS_TABLE     = aws_dynamodb_table.rate_limits.name
      ANONYMOUS_SESSIONS_TABLE = aws_dynamodb_table.anonymous_sessions.name
      USERS_TABLE           = aws_dynamodb_table.users.name
      ENVIRONMENT           = var.environment
      PROJECT_NAME          = var.project_name
    }
  }
}
```

### Step 4: Test the Deployment

#### Test Anonymous User Connection

```python
import asyncio
import websockets
import json

async def test_anonymous_connection():
    # Connect without authentication
    uri = "wss://your-api-id.execute-api.us-east-1.amazonaws.com/dev"
    
    async with websockets.connect(uri) as websocket:
        # Wait for connection response
        response = await websocket.recv()
        data = json.loads(response)
        
        print(f"Connected as: {data['user_type']}")
        print(f"Daily limit: {data['features']['daily_limit']}")
        print(f"User tier: {data['user_tier']}")
        
        # Send a test message
        await websocket.send(json.dumps({
            "action": "message",
            "message": "Hello as anonymous user"
        }))
        
        # Receive response
        response = await websocket.recv()
        print(f"Response: {response}")

asyncio.run(test_anonymous_connection())
```

#### Test Rate Limiting

```bash
# Run the test script multiple times to trigger rate limits
for i in {1..10}; do
  python test_anonymous_connection.py
  echo "Request $i completed"
done
```

### Step 5: Monitor the System

#### CloudWatch Dashboard
Navigate to the dashboard URL:
```
https://us-east-1.console.aws.amazon.com/cloudwatch/home?region=us-east-1#dashboards:name=buffett-chat-dev-rate-limiting
```

#### Check Metrics
```bash
# Get rate limit metrics
aws cloudwatch get-metric-statistics \
  --namespace "BuffettChat/RateLimit" \
  --metric-name "RateLimitExceeded" \
  --dimensions Name=Environment,Value=dev \
  --start-time 2025-01-11T00:00:00Z \
  --end-time 2025-01-11T23:59:59Z \
  --period 3600 \
  --statistics Sum
```

#### View Logs
```bash
# View connection logs
aws logs tail /aws/lambda/buffett-chat-dev-websocket-connect --follow

# Filter for anonymous users
aws logs filter-log-events \
  --log-group-name /aws/lambda/buffett-chat-dev-websocket-connect \
  --filter-pattern '{ $.user_type = "anonymous" }'
```

## Frontend Integration

### Update WebSocket Connection

```javascript
// frontend/src/services/websocket.js

class WebSocketService {
  async connect() {
    const wsUrl = process.env.REACT_APP_WS_URL;
    
    // Try to connect with JWT if available
    const token = localStorage.getItem('authToken');
    const url = token 
      ? `${wsUrl}?token=${token}`
      : wsUrl; // Anonymous connection
    
    this.ws = new WebSocket(url);
    
    this.ws.onopen = (event) => {
      console.log('WebSocket connected');
    };
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      
      // Handle connection info
      if (data.user_type) {
        this.updateUserStatus(data);
      }
      
      // Handle rate limit info
      if (data.rate_limit) {
        this.updateRateLimitDisplay(data.rate_limit);
      }
    };
  }
  
  updateUserStatus(data) {
    const statusEl = document.getElementById('user-status');
    if (data.user_type === 'anonymous') {
      statusEl.innerHTML = `
        <div class="anonymous-banner">
          You have ${data.features.daily_limit} free queries remaining today.
          <button onclick="signIn()">Sign in for more</button>
        </div>
      `;
    }
  }
  
  updateRateLimitDisplay(rateLimit) {
    const limitEl = document.getElementById('rate-limit');
    limitEl.textContent = `${rateLimit.remaining_daily} queries left`;
    
    if (rateLimit.remaining_daily <= 2) {
      this.showUpgradePrompt();
    }
  }
}
```

## Rollback Plan

If issues arise, rollback is straightforward:

### 1. Revert Lambda to Original Handler

```bash
# Update Lambda to use original handler
aws lambda update-function-configuration \
  --function-name buffett-chat-dev-websocket-connect \
  --handler websocket_connect.lambda_handler
```

### 2. Keep Tables (No Data Loss)
The new tables can remain as they don't interfere with existing functionality.

### 3. Or Full Infrastructure Rollback

```bash
# Destroy only the new resources
terraform destroy -target=aws_dynamodb_table.rate_limits \
                  -target=aws_dynamodb_table.anonymous_sessions
```

## Verification Checklist

- [ ] DynamoDB tables created successfully
- [ ] Lambda environment variables updated
- [ ] Lambda functions deployed with new code
- [ ] Anonymous users can connect without authentication
- [ ] Rate limits are enforced (test with multiple requests)
- [ ] Authenticated users get higher limits
- [ ] CloudWatch metrics are being recorded
- [ ] Dashboard shows usage data
- [ ] Device fingerprints are stable across reconnections
- [ ] TTL is cleaning up old anonymous sessions

## Next Steps (Phase 2)

Once Phase 1 is stable:

1. **Implement Message History Control**
   - Don't save messages for anonymous users
   - Add message filtering based on tier

2. **Add Conversion Tracking**
   - Track anonymous → authenticated conversions
   - Implement session transfer on sign-in

3. **Enhance Rate Limiting**
   - Add IP-based secondary limits
   - Implement CAPTCHA for suspicious patterns

4. **Frontend Polish**
   - Progressive disclosure of benefits
   - Smooth upgrade flows
   - Usage visualization

## Troubleshooting

### Issue: Lambda timeout on first request
**Solution**: Increase Lambda timeout to 30 seconds for cold starts with DynamoDB

### Issue: Device fingerprints changing
**Solution**: Check CloudFront headers are being passed through API Gateway

### Issue: Rate limits not working
**Solution**: Verify DynamoDB table names in environment variables

### Issue: Anonymous users blocked immediately
**Solution**: Check rate limit table for stale entries, verify TTL is working

## Support

For issues or questions:
1. Check CloudWatch Logs for detailed error messages
2. Review the test suite: `python backend/tests/test_device_fingerprint.py`
3. Monitor the dashboard for unusual patterns

## Success Metrics

After deployment, monitor these KPIs:

- **Anonymous Usage**: Target 30-50% of total traffic
- **Conversion Rate**: Target 10-15% anonymous → authenticated
- **Rate Limit Hits**: Should be <5% of requests
- **System Performance**: Lambda p99 latency <500ms

The system is designed to fail open (allow requests) if rate limiting fails, ensuring service availability while protecting against abuse.