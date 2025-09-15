# WebSocket Endpoint Configuration Guide

## Challenge
The chat_processor Lambda function needs the WebSocket API endpoint URL as an environment variable to send messages back to connected clients. However, this creates a circular dependency:
- Lambda module needs the WebSocket endpoint from API Gateway module
- API Gateway module needs Lambda function ARNs from Lambda module

## Solution Implemented

### 1. Initial Deployment
The Lambda functions are deployed with an empty `WEBSOCKET_API_ENDPOINT` environment variable to avoid the circular dependency.

```hcl
# In terraform/environments/dev/main.tf
lambda_function_env_vars = {
  chat_processor = {
    WEBSOCKET_API_ENDPOINT = ""  # Empty on first deployment
  }
}
```

### 2. Post-Deployment Update
After both Lambda and API Gateway modules are deployed, use the provided script to update the WebSocket endpoint.

## Update Process

### Option 1: Using the Update Script (Recommended)

```bash
# From terraform directory
./update-websocket-endpoint.sh dev us-east-1
```

This script will:
1. Get the WebSocket endpoint from Terraform outputs
2. Retrieve current Lambda environment variables
3. Update the chat_processor function with the WebSocket endpoint
4. Preserve all other environment variables

### Option 2: Manual Update via AWS CLI

```bash
# Get the WebSocket endpoint
cd terraform/environments/dev
WEBSOCKET_ENDPOINT=$(terraform output -raw websocket_api_endpoint)

# Update the Lambda function
aws lambda update-function-configuration \
  --function-name buffett-dev-chat-processor \
  --environment "Variables={WEBSOCKET_API_ENDPOINT=wss://${WEBSOCKET_ENDPOINT}}" \
  --region us-east-1
```

### Option 3: Terraform Re-apply (Future Enhancement)

A future enhancement could use a data source to automatically populate the endpoint:

```hcl
data "aws_apigatewayv2_api" "websocket" {
  api_id = module.api_gateway.websocket_api_id
}

locals {
  websocket_endpoint = "wss://${data.aws_apigatewayv2_api.websocket.api_endpoint}/${var.environment}"
}
```

## Verification

After updating, verify the environment variable is set:

```bash
aws lambda get-function-configuration \
  --function-name buffett-dev-chat-processor \
  --region us-east-1 \
  --query 'Environment.Variables.WEBSOCKET_API_ENDPOINT'
```

Expected output:
```
"wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev"
```

## Current WebSocket Endpoints

### Development
- Endpoint: `wss://52x14spfai.execute-api.us-east-1.amazonaws.com/dev`
- Function: `buffett-dev-chat-processor`

### Staging
- Endpoint: (To be configured)
- Function: `buffett-staging-chat-processor`

### Production
- Endpoint: (To be configured)
- Function: `buffett-prod-chat-processor`

## Important Notes

1. **First Deployment**: The WebSocket endpoint will be empty until manually updated
2. **Subsequent Deployments**: The endpoint persists unless the Lambda function is recreated
3. **API Gateway Changes**: If the API Gateway is recreated, re-run the update script
4. **Multi-Environment**: Each environment needs its own endpoint update

## Troubleshooting

### Issue: Script can't find WebSocket endpoint
**Solution**: Ensure `terraform apply` has completed successfully and the API Gateway module is deployed

### Issue: Lambda function not found
**Solution**: Verify the function name matches the pattern: `buffett-{environment}-chat-processor`

### Issue: Permission denied
**Solution**: Ensure AWS credentials have permission to update Lambda functions

## Files Created

- `/terraform/update-websocket-endpoint.sh` - Automated update script
- `/terraform/environments/dev/main.tf` - Configuration with empty endpoint
- This documentation file

## Future Improvements

1. Add Terraform data source to automatically resolve endpoint
2. Use AWS Systems Manager Parameter Store for endpoint storage
3. Implement Lambda@Edge for endpoint injection
4. Create GitHub Action for automated updates post-deployment