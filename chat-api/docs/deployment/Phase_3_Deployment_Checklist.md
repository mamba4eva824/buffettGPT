# Phase 3 WebSocket Deployment Checklist

## Pre-Deployment Verification

### ✅ Prerequisites Check
- [ ] Phase 1 infrastructure deployed successfully
- [ ] Phase 2 HTTP API deployed and tested
- [ ] Terraform workspace configured for correct environment
- [ ] AWS CLI configured with appropriate permissions
- [ ] Bedrock agent accessible and operational

### ✅ Infrastructure Files Review
- [ ] `websocket-api.tf` - WebSocket API Gateway configuration
- [ ] `websocket-iam.tf` - IAM policies for WebSocket functionality
- [ ] `websocket-outputs.tf` - Output variables for WebSocket resources
- [ ] `monitoring.tf` - CloudWatch alarms and dashboard
- [ ] Lambda function files in `lambda-functions/` directory

## Deployment Steps

### 1. Terraform Plan and Apply
```bash
cd chat-api

# Review the plan
terraform plan -out=phase3.tfplan

# Apply if plan looks correct
terraform apply phase3.tfplan
```
- [ ] Terraform plan executed without errors
- [ ] All WebSocket resources planned for creation
- [ ] No unexpected resource deletions or modifications
- [ ] Apply completed successfully

### 2. Verify Infrastructure Creation
```bash
# Check WebSocket API Gateway
terraform output websocket_api_invoke_url

# Verify Lambda functions
aws lambda list-functions --query 'Functions[?contains(FunctionName, `websocket`) || contains(FunctionName, `chat-processor`)].FunctionName'

# Check DynamoDB tables
aws dynamodb list-tables --query 'TableNames[?contains(@, `websocket-connections`)]'
```
- [ ] WebSocket API endpoint URL returned
- [ ] All 4 Lambda functions created (connect, disconnect, message, chat-processor)
- [ ] WebSocket connections table created
- [ ] SQS event source mapping configured for chat processor

### 3. Test WebSocket Connectivity

#### Basic Connection Test
```bash
cd tests
python3 websocket_client_test.py wss://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/dev --test basic
```
- [ ] WebSocket connection established successfully
- [ ] Ping/pong functionality working
- [ ] Basic message flow operational

#### Comprehensive Testing
```bash
./run_tests.sh --environment dev --test all
```
- [ ] All tests passed with > 90% success rate
- [ ] Message acknowledgments received within 1 second
- [ ] AI responses generated within 60 seconds
- [ ] Error handling scenarios working correctly

### 4. Verify Monitoring Setup
```bash
# Check CloudWatch dashboard
echo "https://console.aws.amazon.com/cloudwatch/home?region=$(terraform output -raw aws_region)#dashboards:name=$(terraform output -raw project_name)-$(terraform output -raw environment)-dashboard"
```
- [ ] CloudWatch dashboard accessible
- [ ] All metrics showing data
- [ ] Alarms configured and in OK state
- [ ] SNS topic created for alerts

## Post-Deployment Validation

### 5. Functional Testing

#### Connection Lifecycle
- [ ] Connect → Store connection in DynamoDB
- [ ] Send message → Receive acknowledgment
- [ ] Receive AI response → Proper format and content
- [ ] Disconnect → Clean up connection record

#### Error Scenarios
- [ ] Invalid JSON → Error response received
- [ ] Missing required fields → Appropriate error message
- [ ] Empty messages → Validation error
- [ ] Unknown actions → Error handling

#### Load Testing
- [ ] Multiple concurrent connections supported
- [ ] Message queuing working under load
- [ ] No memory leaks or connection drops
- [ ] Graceful handling of disconnections

### 6. Security Validation
- [ ] Connection requires `user_id` parameter
- [ ] Invalid connections rejected appropriately
- [ ] Lambda functions have least-privilege IAM permissions
- [ ] DynamoDB tables encrypted with KMS
- [ ] SQS queues encrypted with KMS

### 7. Performance Validation
- [ ] Connection establishment < 3 seconds
- [ ] Message acknowledgment < 1 second
- [ ] AI response < 30 seconds (typical)
- [ ] Memory usage within allocated limits
- [ ] No Lambda timeouts under normal load

## Troubleshooting Guide

### Common Issues and Solutions

#### Connection Issues
**Problem**: `WebSocket connection failed`
**Solutions**:
- Verify API Gateway endpoint URL format
- Check Lambda function logs for connect handler errors
- Ensure user_id query parameter is provided
- Verify VPC and security group configuration

#### Message Processing Issues
**Problem**: `Messages not being processed`
**Solutions**:
- Check SQS queue for stuck messages
- Verify chat processor Lambda function logs
- Ensure Bedrock agent is accessible
- Check IAM permissions for Bedrock access

#### Performance Issues
**Problem**: `Slow responses or timeouts`
**Solutions**:
- Monitor Lambda function duration metrics
- Check for Lambda throttling in CloudWatch
- Verify reserved concurrency settings
- Review Bedrock agent performance

### Useful Commands
```bash
# View Lambda logs
aws logs tail /aws/lambda/buffett-chat-api-dev-chat-processor --follow

# Check SQS queue status
aws sqs get-queue-attributes --queue-url $(terraform output -raw chat_processing_queue_url) --attribute-names All

# Monitor WebSocket connections
aws dynamodb scan --table-name $(terraform output -raw websocket_connections_table_name) --select COUNT
```

## Rollback Plan

If issues arise, rollback using:
```bash
# Remove WebSocket resources
terraform destroy -target=aws_apigatewayv2_api.chat_websocket_api
terraform destroy -target=aws_lambda_function.websocket_connect
terraform destroy -target=aws_lambda_function.websocket_disconnect
terraform destroy -target=aws_lambda_function.websocket_message
terraform destroy -target=aws_lambda_function.chat_processor
terraform destroy -target=aws_dynamodb_table.websocket_connections

# Or full rollback
terraform destroy
```

## Success Criteria

Phase 3 deployment is successful when:
- [ ] All infrastructure components deployed without errors
- [ ] WebSocket connections can be established and maintained
- [ ] Chat messages flow end-to-end (user → queue → Bedrock → response)
- [ ] All automated tests pass with > 90% success rate
- [ ] Monitoring dashboard shows healthy metrics
- [ ] Error scenarios are handled gracefully
- [ ] Performance meets requirements (< 30s AI responses)

## Next Steps After Successful Deployment

### Immediate Actions
1. **Monitor for 24 hours**: Watch CloudWatch metrics and alarms
2. **User Acceptance Testing**: Have stakeholders test the WebSocket functionality
3. **Document any issues**: Create tickets for any bugs or improvements

### Phase 4 Planning
1. **Authentication**: Plan JWT or Cognito integration
2. **Security Hardening**: WAF, rate limiting, input sanitization
3. **Advanced Features**: Message history, file uploads, conversation management
4. **Production Optimization**: ElastiCache, CDN, edge locations

## Contact Information

For issues or questions regarding this deployment:
- **Technical Lead**: [Your Name]
- **AWS Account**: $(terraform output -raw account_id)
- **Environment**: $(terraform output -raw environment)
- **Region**: $(terraform output -raw aws_region)

---

**Deployment Date**: $(date)
**Terraform Version**: $(terraform version --json | jq -r .terraform_version)
**AWS CLI Version**: $(aws --version)

✅ **Phase 3 WebSocket Implementation Complete**
