#!/bin/bash

# Provisioned Concurrency Status Checker
# Validates PC configuration and provides actionable insights

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
FUNCTION_NAME="${FUNCTION_NAME:-buffett-chat-api-prod-chat-processor}"
ALIAS_NAME="${ALIAS_NAME:-prod}"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo -e "${BLUE}🔍 Checking Provisioned Concurrency Status${NC}"
echo "Function: $FUNCTION_NAME"
echo "Alias: $ALIAS_NAME"
echo "Region: $AWS_REGION"
echo "----------------------------------------"

# 1. Check if PC is configured
echo -e "${BLUE}1. Provisioned Concurrency Configuration${NC}"
PC_CONFIG=$(aws lambda get-provisioned-concurrency-config \
  --function-name "$FUNCTION_NAME" \
  --qualifier "$ALIAS_NAME" \
  --region "$AWS_REGION" 2>/dev/null || echo "NOT_CONFIGURED")

if [ "$PC_CONFIG" = "NOT_CONFIGURED" ]; then
    echo -e "${YELLOW}💡 Provisioned Concurrency not configured (expected for dev)${NC}"
    echo "   Current mode: Cost-optimized development (PC disabled)"
    echo "   To test PC: Set provisioned_concurrency_baseline = 1 in terraform.tfvars"
    echo "   Then run: terraform apply"
    echo ""
    echo -e "${GREEN}✅ This is normal for dev environment - no PC costs incurred${NC}"
    PC_ENABLED=false
else
    PC_STATUS=$(echo "$PC_CONFIG" | jq -r '.Status')
    PC_ALLOCATED=$(echo "$PC_CONFIG" | jq -r '.AllocatedConcurrentExecutions')
    PC_REQUESTED=$(echo "$PC_CONFIG" | jq -r '.RequestedConcurrentExecutions')
    
    echo -e "${GREEN}✅ PC Status: $PC_STATUS${NC}"
    echo "   Requested: $PC_REQUESTED"
    echo "   Allocated: $PC_ALLOCATED"
    
    if [ "$PC_STATUS" != "Ready" ]; then
        echo -e "${YELLOW}⚠️  PC not ready yet. This is normal for new configurations.${NC}"
    fi
    PC_ENABLED=true
fi

# 2. Check recent metrics (last 1 hour)
echo -e "\n${BLUE}2. Performance Metrics (Last Hour)${NC}"

if [ "$PC_ENABLED" = "false" ]; then
    echo "📊 PC disabled - showing general Lambda metrics instead of PC-specific metrics"
fi

# PC Utilization
UTILIZATION=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ProvisionedConcurrencyUtilization \
  --dimensions Name=FunctionName,Value="$FUNCTION_NAME" Name=Resource,Value="$FUNCTION_NAME:$ALIAS_NAME" \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Average \
  --region "$AWS_REGION" \
  --query 'Datapoints[].Average' --output text 2>/dev/null || echo "")

if [ -n "$UTILIZATION" ]; then
    AVG_UTIL=$(echo "$UTILIZATION" | awk '{sum+=$1; count++} END {if(count>0) printf "%.1f", sum/count; else print "0"}')
    echo "📊 Average PC Utilization: ${AVG_UTIL}%"
    
    if (( $(echo "$AVG_UTIL > 85" | bc -l) )); then
        echo -e "${RED}   ⚠️  High utilization! Consider increasing PC units${NC}"
    elif (( $(echo "$AVG_UTIL < 20" | bc -l) )); then
        echo -e "${YELLOW}   💡 Low utilization. Consider reducing PC units for cost savings${NC}"
    else
        echo -e "${GREEN}   ✅ Healthy utilization range${NC}"
    fi
else
    echo "📊 No utilization data available yet"
fi

# Spillover Invocations (Cold Starts)
SPILLOVER=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name ProvisionedConcurrencySpilloverInvocations \
  --dimensions Name=FunctionName,Value="$FUNCTION_NAME" Name=Resource,Value="$FUNCTION_NAME:$ALIAS_NAME" \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Sum \
  --region "$AWS_REGION" \
  --query 'Datapoints[].Sum' --output text 2>/dev/null || echo "")

if [ -n "$SPILLOVER" ]; then
    TOTAL_SPILLOVER=$(echo "$SPILLOVER" | awk '{sum+=$1} END {print sum+0}')
    echo "🚨 Spillover Invocations: $TOTAL_SPILLOVER"
    
    if [ "$TOTAL_SPILLOVER" -gt 0 ]; then
        echo -e "${RED}   ⚠️  Cold starts detected! Increase PC units${NC}"
    else
        echo -e "${GREEN}   ✅ No cold starts - PC working correctly${NC}"
    fi
else
    echo "🚨 No spillover data available yet"
fi

# Init Duration (Cold Start Indicator)
INIT_DURATION=$(aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name InitDuration \
  --dimensions Name=FunctionName,Value="$FUNCTION_NAME" \
  --start-time "$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --end-time "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --period 300 \
  --statistics Average \
  --region "$AWS_REGION" \
  --query 'Datapoints[].Average' --output text 2>/dev/null || echo "")

if [ -n "$INIT_DURATION" ]; then
    AVG_INIT=$(echo "$INIT_DURATION" | awk '{sum+=$1; count++} END {if(count>0) printf "%.0f", sum/count; else print "0"}')
    echo "⏱️  Average Init Duration: ${AVG_INIT}ms"
    
    if [ "$AVG_INIT" -gt 100 ]; then
        echo -e "${RED}   ⚠️  Cold starts occurring! Check PC configuration${NC}"
    else
        echo -e "${GREEN}   ✅ Minimal cold starts${NC}"
    fi
else
    echo "⏱️  No init duration data available"
fi

# 3. Check Auto Scaling Configuration
echo -e "\n${BLUE}3. Auto Scaling Status${NC}"
SCALING_TARGET=$(aws application-autoscaling describe-scalable-targets \
  --service-namespace lambda \
  --resource-ids "function:$FUNCTION_NAME:$ALIAS_NAME" \
  --region "$AWS_REGION" 2>/dev/null || echo "NOT_CONFIGURED")

if [ "$SCALING_TARGET" = "NOT_CONFIGURED" ]; then
    echo -e "${YELLOW}⚠️  Auto Scaling not configured${NC}"
    echo "   Run: terraform apply -target=aws_appautoscaling_target.chat_processor_pc_target"
else
    MIN_CAP=$(echo "$SCALING_TARGET" | jq -r '.ScalableTargets[0].MinCapacity')
    MAX_CAP=$(echo "$SCALING_TARGET" | jq -r '.ScalableTargets[0].MaxCapacity')
    echo -e "${GREEN}✅ Auto Scaling configured${NC}"
    echo "   Range: $MIN_CAP - $MAX_CAP units"
fi

# 4. Cost Estimation
echo -e "\n${BLUE}4. Cost Estimation${NC}"
if [ -n "$PC_ALLOCATED" ] && [ "$PC_ALLOCATED" != "null" ]; then
    # Get function memory configuration
    MEMORY_MB=$(aws lambda get-function \
      --function-name "$FUNCTION_NAME" \
      --region "$AWS_REGION" \
      --query 'Configuration.MemorySize' --output text)
    
    # Calculate monthly cost
    MEMORY_GB=$(echo "scale=4; $MEMORY_MB / 1024" | bc)
    MONTHLY_SECONDS=2678400  # 31 days * 24 hours * 60 minutes * 60 seconds
    COST_PER_GB_SECOND=0.0000041667
    
    MONTHLY_COST=$(echo "scale=2; $MEMORY_GB * $PC_ALLOCATED * $MONTHLY_SECONDS * $COST_PER_GB_SECOND" | bc)
    
    echo "💰 Memory: ${MEMORY_MB}MB (${MEMORY_GB}GB)"
    echo "💰 PC Units: $PC_ALLOCATED"
    echo "💰 Estimated Monthly Cost: \$${MONTHLY_COST}"
fi

# 5. Recommendations
echo -e "\n${BLUE}5. Recommendations${NC}"
if [ -n "$AVG_UTIL" ] && [ -n "$TOTAL_SPILLOVER" ]; then
    if [ "$TOTAL_SPILLOVER" -gt 0 ]; then
        echo -e "${YELLOW}📈 Increase PC units to eliminate cold starts${NC}"
    elif (( $(echo "$AVG_UTIL < 30" | bc -l) )); then
        echo -e "${YELLOW}📉 Consider reducing PC units to save costs${NC}"
    else
        echo -e "${GREEN}✅ Current configuration looks optimal${NC}"
    fi
else
    echo "📊 Collect more data (run for 24h) for better recommendations"
fi

# 6. Quick Actions
echo -e "\n${BLUE}6. Quick Actions${NC}"

if [ "$PC_ENABLED" = "false" ]; then
    echo "🔧 Enable PC for testing:"
    echo "   1. Edit terraform.tfvars: provisioned_concurrency_baseline = 1"
    echo "   2. Run: terraform apply"
    echo "   3. Re-run: ./scripts/check-pc-status.sh"
    echo ""
    echo "💰 Current setup: \$0/month (PC disabled)"
else
    echo "📊 Monitor dashboard: aws cloudwatch"
    echo "🔧 Increase PC: aws lambda put-provisioned-concurrency-config --function-name $FUNCTION_NAME --qualifier $ALIAS_NAME --provisioned-concurrent-executions 3"
    echo "💸 Disable PC: aws lambda delete-provisioned-concurrency-config --function-name $FUNCTION_NAME --qualifier $ALIAS_NAME"
fi

echo "📋 Full logs: aws logs tail /aws/lambda/$FUNCTION_NAME --follow"
echo -e "\n${GREEN}✅ Status check complete${NC}"
