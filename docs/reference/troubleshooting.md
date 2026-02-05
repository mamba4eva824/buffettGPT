# Troubleshooting

This guide covers common issues and solutions for BuffettGPT.

## Authentication Issues

### "Invalid Token" Error

**Symptom**: API returns `INVALID_TOKEN` error

**Causes**:
- Token has expired
- Token signature invalid
- Malformed token

**Solutions**:
1. Re-authenticate via Google OAuth
2. Check token format in request header
3. Verify JWT secret matches between environments

```bash
# Debug token
echo $TOKEN | cut -d. -f2 | base64 -d
```

### "Unauthorized" Error

**Symptom**: 401 response on protected endpoints

**Solutions**:
1. Include `Authorization: Bearer <token>` header
2. For WebSocket, include `?token=<token>` query param
3. Verify token hasn't expired

## WebSocket Issues

### Connection Drops

**Symptom**: WebSocket disconnects unexpectedly

**Solutions**:
1. Implement reconnection logic
2. Check network stability
3. Verify API Gateway timeout settings

```javascript
// Reconnection with exponential backoff
let attempts = 0;
function reconnect() {
  if (attempts < 5) {
    setTimeout(() => {
      connect();
      attempts++;
    }, Math.pow(2, attempts) * 1000);
  }
}
```

### Messages Not Received

**Symptom**: Sent messages but no response

**Debugging**:
1. Check CloudWatch logs for `websocket_message` Lambda
2. Verify connection exists in DynamoDB
3. Check SQS queue for backlog

```bash
# Check connection table
aws dynamodb scan --table-name buffett-chat-api-dev-websocket-connections
```

## Rate Limiting

### "Rate Limit Exceeded" Error

**Symptom**: `RATE_LIMIT_EXCEEDED` error response

**Solutions**:
1. Wait until monthly quota resets
2. Authenticate to increase limit (5 → 500)
3. Check `usage-tracking` table for current usage

```bash
# Check usage
aws dynamodb get-item \
  --table-name buffett-chat-api-dev-usage-tracking \
  --key '{"deviceFingerprint": {"S": "your-fingerprint"}}'
```

## Terraform Issues

### State Lock Error

**Symptom**: "Error acquiring the state lock"

**Solutions**:
1. Wait for other operations to complete
2. Force unlock if stuck (with caution)

```bash
terraform force-unlock LOCK_ID
```

### Module Not Found

**Symptom**: "Module not found" during init

**Solutions**:
```bash
terraform init -upgrade
```

### Plan Shows Unexpected Changes

**Symptom**: Plan wants to destroy/recreate resources

**Solutions**:
1. Check for state drift
2. Verify terraform.tfvars values
3. Review module version changes

```bash
terraform refresh
terraform plan
```

## Lambda Issues

### Cold Start Timeout

**Symptom**: First request times out

**Solutions**:
1. Increase Lambda timeout
2. Use provisioned concurrency
3. Optimize package size

### Import Errors

**Symptom**: "Unable to import module"

**Solutions**:
1. Verify dependencies in layer
2. Check Python version compatibility
3. Rebuild Lambda packages

```bash
cd chat-api/backend
./scripts/build_layer.sh
./scripts/build_lambdas.sh
```

### Permission Denied

**Symptom**: "AccessDeniedException" in logs

**Solutions**:
1. Check IAM role permissions
2. Verify resource ARNs in policy
3. Check KMS key permissions

## DynamoDB Issues

### Throughput Exceeded

**Symptom**: "ProvisionedThroughputExceededException"

**Solutions**:
1. Enable auto-scaling
2. Increase provisioned capacity
3. Implement exponential backoff

### Item Not Found

**Symptom**: Query returns empty results

**Debugging**:
1. Verify key values
2. Check table name
3. Confirm item exists

```bash
aws dynamodb get-item \
  --table-name buffett-chat-api-dev-chat-sessions \
  --key '{"sessionId": {"S": "your-session-id"}}'
```

## Bedrock Issues

### Agent Timeout

**Symptom**: Bedrock agent times out

**Solutions**:
1. Check agent configuration
2. Verify knowledge base connectivity
3. Review guardrails settings

### Response Blocked

**Symptom**: Response blocked by guardrails

**Solutions**:
1. Review guardrail configuration
2. Check input for policy violations
3. Adjust guardrail thresholds

## Frontend Issues

### Build Failures

**Symptom**: `npm run build` fails

**Solutions**:
```bash
rm -rf node_modules package-lock.json
npm install
npm run build
```

### ESLint Warnings

**Symptom**: Lint fails with warnings

**Solutions**:
1. Fix all ESLint warnings (0 warnings policy)
2. Check for unused imports
3. Review console.log statements

```bash
npm run lint -- --fix
```

### Environment Variables

**Symptom**: API calls to wrong endpoint

**Solutions**:
1. Check `.env.local` configuration
2. Verify `VITE_*` prefix for Vite
3. Rebuild after env changes

## Logging and Debugging

### Enable Debug Logging

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)
```

### CloudWatch Logs

```bash
# Tail Lambda logs
aws logs tail /aws/lambda/buffett-chat-api-dev-chat-http --follow

# Search for errors
aws logs filter-log-events \
  --log-group-name /aws/lambda/buffett-chat-api-dev-chat-http \
  --filter-pattern "ERROR"
```

### Local Testing

```bash
cd chat-api/backend
make run-http

# Test endpoint
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
```

## Getting Help

If you're still stuck:

1. Check CloudWatch logs for detailed errors
2. Review recent changes in git history
3. Search existing GitHub issues
4. Open a new issue with:
   - Steps to reproduce
   - Expected vs actual behavior
   - Relevant log snippets
   - Environment details
