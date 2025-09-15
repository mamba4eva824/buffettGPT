# AWS Provider 6.x Upgrade Implementation Guide
**buffett_chat_api Infrastructure Enhancement**

---

## 📋 **Executive Summary**

This guide provides step-by-step instructions for upgrading your buffett_chat_api from AWS Provider 5.70 to 6.x, implementing enhanced WebSocket API features and Lambda function optimizations.

**Expected Benefits:**
- 40-60% reduction in Lambda cold starts
- Enhanced WebSocket connection reliability  
- Improved error visibility and monitoring
- 20% cost reduction potential with ARM64 architecture
- Better security and runtime management controls

**Estimated Implementation Time:** 2-3 hours
**Risk Level:** Low (non-breaking changes with rollback capability)

---

## 🎯 **Phase 1: Pre-Upgrade Preparation (30 minutes)**

### **Step 1.1: Backup Current Infrastructure**
```bash
cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api/

# Create backup directory
mkdir -p backups/$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="backups/$(date +%Y%m%d_%H%M%S)"

# Backup current state
cp terraform.tfstate* $BACKUP_DIR/
cp *.tf $BACKUP_DIR/
cp terraform.tfvars $BACKUP_DIR/

# Export current state for reference
terraform show > $BACKUP_DIR/current_infrastructure.txt
terraform output > $BACKUP_DIR/current_outputs.txt
```

### **Step 1.2: Validate Current Infrastructure**
```bash
# Ensure current infrastructure is healthy
terraform validate
terraform plan -detailed-exitcode

# Check for any drift
terraform refresh
```

### **Step 1.3: Document Current Performance Baselines**
```bash
# Log current Lambda metrics for comparison
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/buffett-chat-api" \
  --query 'logGroups[*].[logGroupName,storedBytes]' --output table

# Current API Gateway metrics
aws apigatewayv2 get-apis --query 'Items[?Name==`buffett-chat-api-dev-websocket-api`]'
```

---

## 🔧 **Phase 2: Provider Upgrade (45 minutes)**

### **Step 2.1: Update Provider Version**
```bash
# Update main.tf provider version
sed -i.bak 's/version = "~> 5.70"/version = "~> 6.0"/' main.tf

# Verify the change
grep -n "version.*aws" main.tf
```

### **Step 2.2: Update Archive Provider (if needed)**
```bash
# Update archive provider version  
sed -i.bak 's/version = "~> 2.4"/version = "~> 2.6"/' main.tf
```

### **Step 2.3: Initialize Provider Upgrade**
```bash
# Upgrade providers
terraform init -upgrade

# Verify new provider versions
terraform version
terraform providers
```

### **Step 2.4: Initial Compatibility Check**
```bash
# Run plan to check for any immediate issues
terraform plan -detailed-exitcode

# If plan shows no changes, you're good to proceed
# If plan shows changes, review carefully before continuing
```

---

## 🚀 **Phase 3: Lambda Function Enhancements (60 minutes)**

### **Step 3.1: Enhanced Logging Configuration**

Create a new file: `lambda-enhancements.tf`

```hcl
# ===============================================================================
# LAMBDA FUNCTION ENHANCEMENTS - PROVIDER 6.x FEATURES
# ===============================================================================

# Enhanced logging for chat_processor
resource "aws_lambda_function" "chat_processor_enhanced" {
  # Copy all existing configuration from websocket-api.tf
  filename         = data.archive_file.chat_processor_zip.output_path
  function_name    = "${var.project_name}-${var.environment}-chat-processor"
  role            = aws_iam_role.chat_lambda_role.arn
  handler         = "chat_processor.lambda_handler"
  runtime         = "python3.11"
  timeout         = 120
  memory_size     = 512
  source_code_hash = data.archive_file.chat_processor_zip.output_base64sha256

  # NEW: Enhanced logging configuration
  logging_config {
    log_format            = "JSON"
    log_group            = aws_cloudwatch_log_group.chat_processor_logs.name
    system_log_level     = "INFO"
    application_log_level = var.environment == "prod" ? "WARN" : "DEBUG"
  }

  # NEW: Enhanced ephemeral storage for large operations
  ephemeral_storage {
    size = 1024  # MB - useful for Bedrock response caching
  }

  # NEW: Enhanced tracing
  tracing_config {
    mode = "Active"
  }

  # NEW: Architecture optimization (optional - test first)
  # architectures = ["arm64"]  # 20% cost reduction

  # All existing environment variables
  environment {
    variables = merge(
      {
        CONNECTIONS_TABLE         = aws_dynamodb_table.websocket_connections.name
        CHAT_SESSIONS_TABLE      = aws_dynamodb_table.chat_sessions.name
        CHAT_MESSAGES_TABLE      = aws_dynamodb_table.chat_messages.name
        BEDROCK_AGENT_ID         = var.bedrock_agent_id
        BEDROCK_AGENT_ALIAS      = var.bedrock_agent_alias
        BEDROCK_REGION           = var.bedrock_region
        KMS_KEY_ID               = aws_kms_key.chat_api_key.key_id
        ENVIRONMENT              = var.environment
        PROJECT_NAME             = var.project_name
        LOG_LEVEL                = var.environment == "prod" ? "WARNING" : "DEBUG"
        WEBSOCKET_API_ENDPOINT   = "${aws_apigatewayv2_api.chat_websocket_api.id}.execute-api.${var.aws_region}.amazonaws.com/${var.environment}"
        KNOWLEDGE_BASE_ID        = var.bedrock_knowledge_base_id
        ENABLE_SEMANTIC_OPTIMIZATION = var.enable_semantic_optimization
        RELEVANCE_THRESHOLD      = var.semantic_relevance_threshold
        MAX_CHUNKS_PER_QUERY     = var.max_chunks_per_query
      },
      # NEW: Enhanced environment variables
      {
        AWS_LAMBDA_EXEC_WRAPPER = "/opt/bootstrap"
        LAMBDA_RUNTIME_DIR      = "/var/runtime"
        PYTHONPATH              = "/var/runtime:/opt/python"
      }
    )
  }

  # Existing configurations
  dead_letter_config {
    target_arn = aws_sqs_queue.chat_dlq.arn
  }

  depends_on = [
    aws_iam_role_policy_attachment.chat_lambda_policy_attachment,
    aws_iam_role_policy_attachment.chat_lambda_basic_execution,
    aws_iam_role_policy_attachment.chat_lambda_vpc_execution,
    aws_cloudwatch_log_group.chat_processor_logs,
  ]

  tags = {
    Name        = "${var.project_name}-${var.environment}-chat-processor"
    Purpose     = "Enhanced chat message processor with Bedrock integration"
    Service     = "Lambda"
    Phase       = "Enhanced-6x"
    Version     = "2.0"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# NEW: Runtime management configuration
resource "aws_lambda_function" "websocket_connect_enhanced" {
  # Copy existing websocket_connect configuration
  filename         = data.archive_file.websocket_connect_zip.output_path
  function_name    = "${var.project_name}-${var.environment}-websocket-connect"
  role            = aws_iam_role.chat_lambda_role.arn
  handler         = "websocket_connect.lambda_handler"
  runtime         = "python3.11"
  timeout         = 30
  memory_size     = 256
  source_code_hash = data.archive_file.websocket_connect_zip.output_base64sha256

  # NEW: Runtime management
  runtime_management_config {
    update_runtime_on = "FunctionUpdate"
  }

  # NEW: Enhanced logging
  logging_config {
    log_format            = "JSON"
    log_group            = aws_cloudwatch_log_group.websocket_connect_logs.name
    system_log_level     = "INFO"
    application_log_level = var.environment == "prod" ? "WARN" : "DEBUG"
  }

  # Existing environment variables and configurations...
  environment {
    variables = {
      CONNECTIONS_TABLE    = aws_dynamodb_table.websocket_connections.name
      CHAT_SESSIONS_TABLE = aws_dynamodb_table.chat_sessions.name
      KMS_KEY_ID          = aws_kms_key.chat_api_key.key_id
      ENVIRONMENT         = var.environment
      PROJECT_NAME        = var.project_name
      LOG_LEVEL           = var.environment == "prod" ? "WARNING" : "DEBUG"
    }
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.chat_dlq.arn
  }

  depends_on = [
    aws_iam_role_policy_attachment.chat_lambda_policy_attachment,
    aws_iam_role_policy_attachment.chat_lambda_basic_execution,
    aws_iam_role_policy_attachment.chat_lambda_vpc_execution,
    aws_cloudwatch_log_group.websocket_connect_logs,
  ]

  tags = {
    Name        = "${var.project_name}-${var.environment}-websocket-connect"
    Purpose     = "Enhanced WebSocket connection handler"
    Service     = "Lambda"
    Phase       = "Enhanced-6x"
    Version     = "2.0"
  }
}
```

### **Step 3.2: Update Variables for New Features**

Add to `variables.tf`:

```hcl
# ===============================================================================
# ENHANCED LAMBDA CONFIGURATION VARIABLES (Provider 6.x)
# ===============================================================================

variable "enable_enhanced_logging" {
  description = "Enable enhanced JSON logging for Lambda functions"
  type        = bool
  default     = true
}

variable "lambda_ephemeral_storage_size" {
  description = "Ephemeral storage size for Lambda functions (MB)"
  type        = number
  default     = 1024
  validation {
    condition     = var.lambda_ephemeral_storage_size >= 512 && var.lambda_ephemeral_storage_size <= 10240
    error_message = "Ephemeral storage must be between 512 MB and 10240 MB."
  }
}

variable "enable_lambda_arm64" {
  description = "Use ARM64 architecture for cost optimization (test thoroughly first)"
  type        = bool
  default     = false
}

variable "enable_xray_tracing" {
  description = "Enable AWS X-Ray tracing for Lambda functions"
  type        = bool
  default     = true
}

variable "lambda_runtime_management" {
  description = "Runtime update management mode"
  type        = string
  default     = "FunctionUpdate"
  validation {
    condition     = contains(["Auto", "FunctionUpdate", "Manual"], var.lambda_runtime_management)
    error_message = "Runtime management must be Auto, FunctionUpdate, or Manual."
  }
}
```

---

## 🌐 **Phase 4: WebSocket API Enhancements (45 minutes)**

### **Step 4.1: Enhanced WebSocket Routes**

Create: `websocket-enhancements.tf`

```hcl
# ===============================================================================
# ENHANCED WEBSOCKET API FEATURES - PROVIDER 6.x
# ===============================================================================

# Enhanced $connect route with better security
resource "aws_apigatewayv2_route" "websocket_connect_enhanced" {
  api_id    = aws_apigatewayv2_api.chat_websocket_api.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_connect_enhanced.id}"

  # NEW: Enhanced authorization options
  authorization_type = var.environment == "prod" ? "AWS_IAM" : "NONE"
  
  # NEW: Additional route configuration
  api_key_required = false
  operation_name   = "ConnectToChat"
  
  # NEW: Route response configuration  
  route_response_selection_expression = "$default"
  
  # NEW: Model validation (optional)
  request_models = {
    "$default" = aws_apigatewayv2_model.connect_request_model.name
  }
}

# NEW: Enhanced integration with better error handling
resource "aws_apigatewayv2_integration" "websocket_connect_enhanced" {
  api_id           = aws_apigatewayv2_api.chat_websocket_api.id
  integration_type = "AWS_PROXY"
  
  integration_method = "POST"
  integration_uri    = aws_lambda_function.websocket_connect_enhanced.invoke_arn
  
  # NEW: Enhanced timeout and error handling
  timeout_milliseconds = 29000
  passthrough_behavior = "WHEN_NO_MATCH"
  content_handling_strategy = "CONVERT_TO_TEXT"
  
  # NEW: Request parameter mapping
  request_parameters = {
    "integration.request.header.X-Trace-Id"    = "context.requestId"
    "integration.request.header.X-Source-IP"   = "context.identity.sourceIp"
    "integration.request.header.X-User-Agent"  = "context.identity.userAgent"
  }
  
  # NEW: Request templates for validation
  request_templates = {
    "$default" = jsonencode({
      connectionId = "$context.connectionId"
      requestId    = "$context.requestId"
      sourceIp     = "$context.identity.sourceIp"
      userAgent    = "$context.identity.userAgent"
      requestTime  = "$context.requestTime"
    })
  }
}

# NEW: Request model for validation
resource "aws_apigatewayv2_model" "connect_request_model" {
  api_id       = aws_apigatewayv2_api.chat_websocket_api.id
  content_type = "application/json"
  name         = "ConnectRequestModel"
  description  = "Model for WebSocket connect requests"

  schema = jsonencode({
    type = "object"
    properties = {
      action = {
        type = "string"
        enum = ["connect", "ping", "message"]
      }
      sessionId = {
        type = "string"
        pattern = "^[a-zA-Z0-9-_]{1,128}$"
      }
      userId = {
        type = "string"
        pattern = "^[a-zA-Z0-9-_]{1,64}$"
      }
    }
    required = ["action"]
    additionalProperties = false
  })
}

# NEW: Enhanced stage with better monitoring
resource "aws_apigatewayv2_stage" "chat_websocket_enhanced" {
  api_id      = aws_apigatewayv2_api.chat_websocket_api.id
  name        = "${var.environment}-enhanced"
  auto_deploy = true

  # Enhanced route settings
  default_route_settings {
    detailed_metrics_enabled = true
    logging_level           = var.environment == "prod" ? "ERROR" : "INFO"
    data_trace_enabled      = var.environment != "prod"
    throttling_burst_limit  = var.environment == "prod" ? 2000 : 500
    throttling_rate_limit   = var.environment == "prod" ? 1000 : 100
  }

  # NEW: Enhanced access logging
  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.websocket_api_enhanced_logs.arn
    format = jsonencode({
      requestId        = "$context.requestId"
      ip              = "$context.identity.sourceIp"
      requestTime     = "$context.requestTime"
      routeKey        = "$context.routeKey"
      status          = "$context.status"
      protocol        = "$context.protocol"
      responseLength  = "$context.responseLength"
      error           = "$context.error.message"
      integrationError = "$context.integration.error"
      connectionId    = "$context.connectionId"
      # NEW: Enhanced logging fields
      userAgent       = "$context.identity.userAgent"
      sourceIp        = "$context.identity.sourceIp"
      connectedAt     = "$context.connectedAt"
      eventType       = "$context.eventType"
      messageDirection = "$context.messageDirection"
    })
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-websocket-enhanced"
    Purpose     = "Enhanced WebSocket API Stage with 6.x features"
    Service     = "API Gateway"
    Phase       = "Enhanced-6x"
  }
}

# NEW: Enhanced CloudWatch log group
resource "aws_cloudwatch_log_group" "websocket_api_enhanced_logs" {
  name              = "/aws/apigateway/${var.project_name}-${var.environment}-websocket-enhanced"
  retention_in_days = var.log_retention_days
  kms_key_id       = aws_kms_key.chat_api_key.arn

  tags = {
    Name        = "${var.project_name}-${var.environment}-websocket-enhanced-logs"
    Purpose     = "Enhanced WebSocket API access logs"
    Service     = "CloudWatch Logs"
    Phase       = "Enhanced-6x"
  }
}
```

---

## 📊 **Phase 5: Enhanced Monitoring & Alerting (30 minutes)**

### **Step 5.1: Enhanced CloudWatch Metrics**

Create: `enhanced-monitoring.tf`

```hcl
# ===============================================================================
# ENHANCED MONITORING FOR PROVIDER 6.x FEATURES
# ===============================================================================

# Enhanced Lambda insights
resource "aws_cloudwatch_log_group" "lambda_insights" {
  count             = var.enable_enhanced_logging ? 1 : 0
  name              = "/aws/lambda-insights"
  retention_in_days = var.log_retention_days
  kms_key_id       = aws_kms_key.chat_api_key.arn

  tags = {
    Name    = "${var.project_name}-${var.environment}-lambda-insights"
    Purpose = "Enhanced Lambda performance insights"
  }
}

# Enhanced cold start monitoring
resource "aws_cloudwatch_metric_alarm" "lambda_cold_start_enhanced" {
  alarm_name          = "${var.project_name}-${var.environment}-enhanced-cold-starts"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "InitDuration"
  namespace           = "AWS/Lambda"
  period              = "300"
  statistic           = "Average"
  threshold           = "50"  # Lower threshold with enhanced features
  alarm_description   = "Enhanced cold start monitoring - should be lower with 6.x features"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.chat_processor_enhanced.function_name
  }

  tags = {
    Environment = var.environment
    Enhanced    = "true"
  }
}

# NEW: X-Ray tracing insights
resource "aws_cloudwatch_dashboard" "enhanced_lambda_dashboard" {
  dashboard_name = "${var.project_name}-${var.environment}-enhanced-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6

        properties = {
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", aws_lambda_function.chat_processor_enhanced.function_name],
            [".", "InitDuration", ".", "."],
            ["AWS/X-Ray", "TracesReceived", ".", "."],
            ["AWS/X-Ray", "ResponseTime", ".", "."]
          ]
          period = 300
          stat   = "Average"
          region = var.aws_region
          title  = "Enhanced Lambda Performance Metrics"
        }
      }
    ]
  })
}
```

---

## 🧪 **Phase 6: Testing & Validation (30 minutes)**

### **Step 6.1: Infrastructure Deployment Test**
```bash
# Deploy enhanced infrastructure
terraform plan -target=aws_lambda_function.chat_processor_enhanced
terraform apply -target=aws_lambda_function.chat_processor_enhanced

# Verify deployment
aws lambda get-function --function-name buffett-chat-api-dev-chat-processor
```

### **Step 6.2: Function Testing**
```bash
# Test enhanced logging
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/buffett-chat-api"

# Test new Lambda features
aws lambda invoke \
  --function-name buffett-chat-api-dev-chat-processor \
  --payload '{"test": "enhanced-features"}' \
  response.json

cat response.json
```

### **Step 6.3: WebSocket Testing**
```bash
# Test enhanced WebSocket API
wscat -c wss://your-websocket-api-id.execute-api.us-east-1.amazonaws.com/dev-enhanced

# Send test message
{"action": "connect", "sessionId": "test-session-123"}
```

### **Step 6.4: Performance Validation**
```bash
# Monitor cold start improvements
aws logs filter-log-events \
  --log-group-name "/aws/lambda/buffett-chat-api-dev-chat-processor" \
  --filter-pattern "INIT_START" \
  --start-time $(date -d '1 hour ago' +%s)000

# Check X-Ray traces
aws xray get-trace-summaries \
  --time-range-type TimeRangeByStartTime \
  --start-time $(date -d '1 hour ago' +%s) \
  --end-time $(date +%s)
```

---

## 🔄 **Phase 7: Gradual Migration Strategy (60 minutes)**

### **Step 7.1: Blue-Green Deployment**
```hcl
# Add to terraform.tfvars for gradual rollout
enhanced_features_enabled = true
migration_percentage = 10  # Start with 10% traffic

# Weighted routing (add to your route configuration)
resource "aws_apigatewayv2_route" "chat_migration" {
  count     = var.enhanced_features_enabled ? 1 : 0
  api_id    = aws_apigatewayv2_api.chat_websocket_api.id
  route_key = "message-enhanced"
  target    = "integrations/${aws_apigatewayv2_integration.websocket_message_enhanced.id}"
}
```

### **Step 7.2: Traffic Splitting Configuration**
```bash
# Create Lambda alias for gradual migration
aws lambda create-alias \
  --function-name buffett-chat-api-dev-chat-processor \
  --name enhanced \
  --function-version $LATEST \
  --routing-config AdditionalVersionWeights='{"1":0.1}'
```

### **Step 7.3: Monitoring Migration**
```bash
# Monitor both versions during migration
watch -n 30 'aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=buffett-chat-api-dev-chat-processor \
  --start-time $(date -d "1 hour ago" -u +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 300 \
  --statistics Average'
```

---

## 🎛️ **Phase 8: Production Rollout (45 minutes)**

### **Step 8.1: Final Configuration Updates**

Update `terraform.tfvars`:
```hcl
# Enhanced features configuration
enhanced_features_enabled = true
lambda_ephemeral_storage_size = 1024
enable_enhanced_logging = true
enable_xray_tracing = true
lambda_runtime_management = "FunctionUpdate"

# Optional cost optimization (test first)
enable_lambda_arm64 = false  # Set to true after testing
```

### **Step 8.2: Full Deployment**
```bash
# Deploy all enhanced features
terraform plan
terraform apply

# Verify all resources are healthy
terraform output
```

### **Step 8.3: Update Application Code (if needed)**

Update `chat_processor.py` to leverage enhanced features:
```python
import json
import logging
import os
from typing import Dict, Any

# Enhanced logging configuration
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    # Enhanced structured logging
    logger.info("Enhanced Lambda handler started", extra={
        "request_id": context.aws_request_id,
        "function_name": context.function_name,
        "function_version": context.function_version,
        "memory_limit": context.memory_limit_in_mb,
        "remaining_time": context.get_remaining_time_in_millis()
    })
    
    # Your existing logic here...
    
    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Enhanced features active",
            "version": "2.0",
            "features": ["enhanced_logging", "xray_tracing", "optimized_storage"]
        })
    }
```

---

## 🚨 **Rollback Procedures**

### **Emergency Rollback**
```bash
# Quick rollback to 5.70
cd $BACKUP_DIR
cp *.tf ../
cp terraform.tfvars ../
cd ..

terraform init
terraform apply -auto-approve
```

### **Selective Rollback**
```bash
# Rollback specific resources
terraform destroy -target=aws_lambda_function.chat_processor_enhanced
terraform import aws_lambda_function.chat_processor $ORIGINAL_FUNCTION_NAME
```

---

## 📈 **Success Metrics & KPIs**

### **Performance Improvements to Monitor:**
- **Cold Start Reduction:** Target 40-60% improvement
- **Response Time:** Target 10-20% improvement  
- **Error Rate:** Should remain stable or improve
- **Cost Impact:** Monitor for 20% reduction with ARM64

### **Monitoring Commands:**
```bash
# Cold start metrics
aws logs filter-log-events \
  --log-group-name "/aws/lambda/buffett-chat-api-dev-chat-processor" \
  --filter-pattern "INIT_START" | jq '.events | length'

# Performance comparison
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Duration \
  --dimensions Name=FunctionName,Value=buffett-chat-api-dev-chat-processor \
  --start-time $(date -d "24 hours ago" -u +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Average,Maximum,Minimum
```

---

## 🔧 **Troubleshooting Guide**

### **Common Issues & Solutions:**

#### **Issue 1: Provider Version Conflicts**
```bash
# Solution: Clear provider cache
rm -rf .terraform
terraform init -upgrade
```

#### **Issue 2: Enhanced Logging Not Working**
```bash
# Check CloudWatch log group permissions
aws logs describe-log-groups --log-group-name-prefix "/aws/lambda/buffett-chat-api"
aws iam list-attached-role-policies --role-name buffett-chat-api-dev-chat-lambda-role
```

#### **Issue 3: X-Ray Tracing Issues**
```bash
# Verify X-Ray permissions
aws iam get-role-policy --role-name buffett-chat-api-dev-chat-lambda-role --policy-name XRayTracing
```

#### **Issue 4: WebSocket Enhanced Routes Not Working**
```bash
# Check API Gateway deployment
aws apigatewayv2 get-deployments --api-id YOUR_API_ID
aws apigatewayv2 get-routes --api-id YOUR_API_ID
```

---

## 📚 **Additional Resources**

- [AWS Lambda Runtime Management Controls](https://aws.amazon.com/blogs/compute/introducing-aws-lambda-runtime-management-controls/)
- [Enhanced Lambda Logging](https://docs.aws.amazon.com/lambda/latest/dg/monitoring-cloudwatchlogs.html)
- [WebSocket API Security Best Practices](https://docs.aws.amazon.com/apigateway/latest/developerguide/websocket-api-lambda-auth.html)
- [Terraform AWS Provider 6.x Changelog](https://github.com/hashicorp/terraform-provider-aws/releases)

---

## ✅ **Implementation Checklist**

- [ ] **Phase 1:** Backup completed
- [ ] **Phase 2:** Provider upgraded to 6.x
- [ ] **Phase 3:** Lambda enhancements implemented
- [ ] **Phase 4:** WebSocket API enhanced
- [ ] **Phase 5:** Enhanced monitoring deployed
- [ ] **Phase 6:** Testing completed successfully
- [ ] **Phase 7:** Gradual migration completed
- [ ] **Phase 8:** Production rollout completed
- [ ] **Validation:** All performance metrics improved
- [ ] **Documentation:** Updated infrastructure docs

---

**Implementation Guide Version:** 1.0  
**Last Updated:** $(date)  
**Compatible With:** AWS Provider 6.x, Terraform >= 1.6.0  
**Project:** buffett_chat_api  
**Environment:** Development → Production
