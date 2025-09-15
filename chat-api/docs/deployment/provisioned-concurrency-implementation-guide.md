# AWS Lambda Provisioned Concurrency Implementation Guide

## Executive Summary

**Problem**: Your `chat_processor` Lambda experiences ~500ms cold starts and 7-11s tail latencies, impacting user experience for Bedrock-powered chat responses.

**Solution**: Dev-first Provisioned Concurrency implementation - disabled by default for cost savings, easily enabled for testing before production rollout.

**Dev Approach**: PC disabled by default (cost = $0), enable selectively for testing (~$7-15/month), production-ready configuration included for future SDLC phases.

---

## 🎯 Dev-First Rollout Strategy

### Phase 1: Infrastructure Setup (PC Disabled)
```bash
# 1. Deploy alias and supporting infrastructure (PC disabled by default)
terraform plan
terraform apply

# Verify alias is created but no PC costs incurred
aws lambda get-alias --function-name buffett-chat-api-dev-chat-processor --name prod
```

### Phase 2: Test Provisioned Concurrency in Dev
```bash
# 2. Enable PC for testing by updating terraform.tfvars:
# provisioned_concurrency_baseline = 1  # Uncomment this line
# enable_pc_alerts = true               # Uncomment this line

# Apply the PC configuration
terraform plan
terraform apply

# 3. Validate PC is working
./scripts/check-pc-status.sh
```

### Phase 3: Future Production Deployment (When Ready)
```bash
# When you have staging/prod environments:
# Update terraform.tfvars for production values:
# provisioned_concurrency_baseline = 2
# provisioned_concurrency_max = 8
# enable_scheduled_scaling = true

terraform apply
```

---

## 🔧 AWS CLI Commands (Alternative to Terraform)

### Essential Commands for Manual Setup

```bash
# Set environment variables
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export AWS_REGION="us-east-1"
export FUNCTION_NAME="buffett-chat-api-prod-chat-processor"
export ALIAS_NAME="prod"

# 1. Publish new Lambda version
aws lambda publish-version \
  --function-name $FUNCTION_NAME \
  --description "Version for Provisioned Concurrency - $(date)" \
  --query 'Version' --output text

export VERSION_NUMBER=$(aws lambda publish-version \
  --function-name $FUNCTION_NAME \
  --description "PC Version $(date)" \
  --query 'Version' --output text)

# 2. Create production alias
aws lambda create-alias \
  --function-name $FUNCTION_NAME \
  --name $ALIAS_NAME \
  --function-version $VERSION_NUMBER \
  --description "Production alias with Provisioned Concurrency"

# 3. Enable Provisioned Concurrency (start with 2 units)
aws lambda put-provisioned-concurrency-config \
  --function-name $FUNCTION_NAME \
  --qualifier $ALIAS_NAME \
  --provisioned-concurrent-executions 2

# 4. Set up Application Auto Scaling target
aws application-autoscaling register-scalable-target \
  --service-namespace lambda \
  --resource-id "function:$FUNCTION_NAME:$ALIAS_NAME" \
  --scalable-dimension lambda:provisioned-concurrency:concurrency \
  --min-capacity 1 \
  --max-capacity 10

# 5. Create target tracking scaling policy
aws application-autoscaling put-scaling-policy \
  --service-namespace lambda \
  --resource-id "function:$FUNCTION_NAME:$ALIAS_NAME" \
  --scalable-dimension lambda:provisioned-concurrency:concurrency \
  --policy-name "pc-utilization-scaling" \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 75.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "LambdaProvisionedConcurrencyUtilization"
    },
    "ScaleOutCooldown": 60,
    "ScaleInCooldown": 300
  }'

# 6. Update SQS event source to use alias (if needed)
aws lambda list-event-source-mappings \
  --function-name $FUNCTION_NAME \
  --query 'EventSourceMappings[0].UUID' --output text

export EVENT_SOURCE_UUID=$(aws lambda list-event-source-mappings \
  --function-name $FUNCTION_NAME \
  --query 'EventSourceMappings[0].UUID' --output text)

aws lambda update-event-source-mapping \
  --uuid $EVENT_SOURCE_UUID \
  --function-name "$FUNCTION_NAME:$ALIAS_NAME"
```

### Monitoring Commands

```bash
# Check PC status
aws lambda get-provisioned-concurrency-config \
  --function-name $FUNCTION_NAME \
  --qualifier $ALIAS_NAME

# Monitor PC utilization
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ProvisionedConcurrencyUtilization \
  --dimensions Name=FunctionName,Value=$FUNCTION_NAME Name=Resource,Value="$FUNCTION_NAME:$ALIAS_NAME" \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Average

# Check for spillover invocations (cold starts)
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ProvisionedConcurrencySpilloverInvocations \
  --dimensions Name=FunctionName,Value=$FUNCTION_NAME Name=Resource,Value="$FUNCTION_NAME:$ALIAS_NAME" \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 300 \
  --statistics Sum
```

---

## 📊 Cost Analysis & Trade-offs

### Monthly Cost Breakdown (us-east-1) - Dev-First Approach

**Provisioned Concurrency Pricing**: $0.0000041667 per GB-second

| Environment | Memory | PC Units | Monthly Cost | Use Case |
|-------------|--------|----------|--------------|----------|
| **Dev (Default)** | 512MB | 0 | **$0** | Normal development |
| **Dev (Testing PC)** | 512MB | 1 | **$7.62** | Test PC functionality |
| **Future Production** | 1024MB | 2 | **$30.48** | Production when ready |

### Cost Formula
```
Monthly PC Cost = (Memory_MB / 1024) × PC_Units × 2,678,400 seconds × $0.0000041667
```

### Trade-offs Analysis - Dev-First Approach

| Aspect | PC Disabled (Default) | PC Enabled (Testing) | Future Production |
|--------|----------------------|---------------------|-------------------|
| **Cost** | $0/month | $7-15/month | $30-75/month |
| **Cold Starts** | Yes (~500ms) | Eliminated | Eliminated |
| **Use Case** | Development | PC validation | Production performance |
| **SDLC Phase** | Dev iteration | Testing/validation | Production ready |

### **Current Recommendation**: Stay with PC disabled ($0 cost) until ready for production
- **Dev Phase**: Accept cold starts, focus on feature development
- **Testing Phase**: Enable 1 PC unit to validate functionality (~$8/month)
- **Production Phase**: Deploy full PC configuration when staging/prod environments exist

---

## 🎛️ Configuration Recommendations

### Current Development Values (Default - No Cost)
```hcl
# Default terraform.tfvars - PC disabled for cost savings
provisioned_concurrency_baseline = 0     # No PC costs
provisioned_concurrency_min = 0          # Ready for scaling when enabled
provisioned_concurrency_max = 3          # Conservative max for dev testing
enable_scheduled_scaling = false         # Keep simple
enable_pc_alerts = false                 # Reduce CloudWatch noise
```

### Test PC in Development (Uncomment to Enable)
```hcl
# To test PC in dev - uncomment these lines in terraform.tfvars:
# provisioned_concurrency_baseline = 1   # Enable 1 PC unit (~$7/month)
# enable_pc_alerts = true                 # Enable monitoring
```

### Future Production Values (When Staging/Prod Environments Ready)
```hcl
# For production deployment:
provisioned_concurrency_baseline = 2     # 2 units for prod
provisioned_concurrency_min = 1          # Minimum during low traffic
provisioned_concurrency_max = 8          # Maximum during peak traffic
provisioned_concurrency_utilization_target = 75.0
enable_scheduled_scaling = true          # Cost optimization
enable_pc_alerts = true                  # Full monitoring
```

### Autoscaling Behavior
- **Scale Out**: When utilization > 75% for 1 minute
- **Scale In**: When utilization < 75% for 5 minutes (conservative)
- **Cooldown**: Prevents thrashing during traffic spikes
- **Scheduled Scaling**: Scale down during low-traffic hours (2 AM - 8 AM UTC)

---

## 🔍 Validation Checklist

### Phase 1: Initial Deployment
- [ ] Lambda version published successfully
- [ ] Production alias created and pointing to correct version
- [ ] PC configuration shows "Ready" status
- [ ] Event source mapping updated to use alias
- [ ] No errors in CloudWatch logs

### Phase 2: Performance Validation
- [ ] **Zero cold starts**: No `InitDuration` metrics in CloudWatch
- [ ] **Latency improvement**: Duration p95 < 3s (down from 7-11s)
- [ ] **PC utilization**: 50-80% during normal traffic
- [ ] **No spillover**: `ProvisionedConcurrencySpilloverInvocations` = 0

### Phase 3: Load Testing
```bash
# Load test script for validation
for i in {1..50}; do
  curl -X POST https://your-websocket-api.execute-api.us-east-1.amazonaws.com/prod \
    -H "Content-Type: application/json" \
    -d '{"action": "sendMessage", "message": "Test load message '$i'"}' &
done
wait

# Verify metrics after load test
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=$FUNCTION_NAME \
  --start-time $(date -u -d '5 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 60 \
  --statistics Average,Maximum
```

### Key Metrics to Monitor

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| `ProvisionedConcurrencyUtilization` | 50-80% | >85% |
| `ProvisionedConcurrencySpilloverInvocations` | 0 | >5 in 5 min |
| `InitDuration` | 0 | >100ms average |
| `Duration` (p95) | <3s | >5s |
| `Errors` | <1% | >2% |

---

## ⚠️ Gotchas & Best Practices

### Critical Gotchas
1. **Version Dependency**: PC only works with versioned functions, not `$LATEST`
2. **Deployment Order**: Must publish version → create alias → enable PC
3. **Event Source Mapping**: Update to point to alias, not function name
4. **Multi-AZ Distribution**: PC instances spread across AZs (can't control)
5. **Scale-up Lead Time**: ~1-2 minutes for new PC instances to become ready

### VPC Considerations
- **ENI Reuse**: PC instances reuse ENIs, reducing VPC cold start penalty
- **Security Group**: Your Lambda already has proper SG configuration
- **NAT Gateway**: Ensure sufficient bandwidth for Bedrock API calls

### Memory vs. CPU Optimization
- **Current**: 512MB = ~0.5 vCPU
- **Recommended**: 1024MB = ~0.6 vCPU (20% performance boost)
- **Rule**: Memory ↑ = CPU ↑ = Faster Bedrock calls

### Java Runtime Note
Since you're using Python, this doesn't apply, but:
- **Java**: Consider SnapStart instead of PC for faster cold starts
- **Python**: PC is the optimal solution

---

## 🔧 Lambda Power Tuning (Optional Enhancement)

Use AWS Lambda Power Tuning to find optimal memory configuration:

```bash
# Deploy Lambda Power Tuning (one-time setup)
git clone https://github.com/alexcasalboni/aws-lambda-power-tuning.git
cd aws-lambda-power-tuning
npm install
npx serverless deploy

# Run power tuning for your function
aws stepfunctions start-execution \
  --state-machine-arn "arn:aws:states:us-east-1:$ACCOUNT_ID:stateMachine:powerTuningStateMachine" \
  --input '{
    "lambdaARN": "arn:aws:lambda:us-east-1:'$ACCOUNT_ID':function:'$FUNCTION_NAME'",
    "powerValues": [512, 1024, 1536, 2048, 3008],
    "num": 10,
    "payload": {"Records": [{"body": "{\"message_id\": \"test\", \"session_id\": \"test\", \"user_id\": \"test\", \"connection_id\": \"test\", \"user_message\": \"What is value investing?\"}"}]}
  }'
```

**Expected Result**: 1024MB likely provides best price/performance ratio for Bedrock workloads.

---

## 🚀 Next Steps

1. **Immediate**: Deploy PC with 2 units at 1024MB
2. **Week 1**: Monitor utilization and spillover metrics
3. **Week 2**: Adjust baseline based on traffic patterns
4. **Month 1**: Consider scheduled scaling for cost optimization
5. **Quarter 1**: Evaluate memory optimization with Lambda Power Tuning

**Success Criteria**: 
- Zero cold starts (InitDuration = 0)
- p95 latency < 3s (down from 7-11s)
- PC utilization 50-80%
- Monthly cost increase < $50

---

## 📞 Support Commands

### Quick Status Check
```bash
./scripts/check-pc-status.sh
```

### Emergency Disable PC
```bash
aws lambda delete-provisioned-concurrency-config \
  --function-name $FUNCTION_NAME \
  --qualifier $ALIAS_NAME
```

### Rollback to Previous Version
```bash
aws lambda update-alias \
  --function-name $FUNCTION_NAME \
  --name $ALIAS_NAME \
  --function-version $PREVIOUS_VERSION
```

This implementation eliminates your cold start penalty while maintaining cost efficiency. The autoscaling ensures you pay only for what you need, with intelligent monitoring to prevent both over-provisioning and performance degradation.
