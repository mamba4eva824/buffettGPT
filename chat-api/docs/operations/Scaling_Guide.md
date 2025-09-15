# 🚀 Warren Buffett Chat API - Scaling Guide

## **Overview**

This guide provides a comprehensive strategy for scaling the Warren Buffett Chat API from hundreds to tens of thousands of concurrent users. It covers Bedrock agent scaling, infrastructure components, implementation patterns, and cost considerations.

---

## **📊 Current Architecture & Baseline**

### **Current Setup**
```hcl
# Single agent configuration
bedrock_agent_id    = "P82I6ITJGO"      # Warren Buffett Financial Advisor
bedrock_agent_alias = "QIYVUYRITH"      # Production alias
bedrock_region      = "us-east-1"       # Single region deployment
```

### **Current Capacity**
- **Bedrock Agent**: 1,000 requests/minute (~17 req/sec)
- **SQS Standard Queue**: 3,000+ TPS
- **Lambda Functions**: Unlimited concurrency
- **API Gateway WebSocket**: 10,000 concurrent connections
- **DynamoDB**: Pay-per-request (auto-scaling)

---

## **🎯 Scaling Thresholds & Decision Points**

### **Current Scale: 100-1,000 Users** ✅
**Status:** No changes needed
```yaml
Architecture:
  bedrock_agents: 1
  sqs_queues: 1
  lambda_concurrency: unlimited
  api_gateway_regions: 1
  estimated_cost: $100-500/month
```

### **Growth Scale: 1,000-5,000 Users** 📈
**Trigger:** Agent response time > 2 seconds OR error rate > 1%
```yaml
Architecture:
  bedrock_agents: 2          # Primary + backup
  sqs_queues: 2              # Load distribution
  lambda_concurrency: 200    # Per function
  api_gateway_regions: 1     # Still single region
  estimated_cost: $200-1000/month
```

### **Enterprise Scale: 5,000-20,000 Users** 🚀
**Trigger:** Concurrent sessions > 5,000 OR regional latency > 500ms
```yaml
Architecture:
  bedrock_agents: 4          # Geographic + load distribution
  sqs_queues: 4              # Parallel processing
  lambda_concurrency: 500    # Per function
  api_gateway_regions: 2     # US + EU
  dynamodb_global_tables: true
  estimated_cost: $400-2000/month
```

### **Massive Scale: 20,000+ Users** 🌍
**Trigger:** System-wide bottlenecks OR global expansion
```yaml
Architecture:
  bedrock_agents: 8+         # Specialized + regional
  sqs_queues: 8+             # Topic-based sharding
  lambda_concurrency: 1000   # Per function
  api_gateway_regions: 3+    # Global deployment
  redis_clusters: 3          # Session management
  estimated_cost: $800-4000+/month
```

---

## **🤖 Bedrock Agent Scaling Patterns**

### **Pattern 1: Regional Agent Distribution** 🌍
```hcl
# Deploy agents across regions for latency optimization
resource "aws_bedrock_agent" "warren_buffett_us_east" {
  agent_name = "warren-buffett-financial-advisor-east"
  foundation_model = "anthropic.claude-3-sonnet-20240229-v1:0"
  # ... configuration
}

resource "aws_bedrock_agent" "warren_buffett_us_west" {
  agent_name = "warren-buffett-financial-advisor-west"
  foundation_model = "anthropic.claude-3-sonnet-20240229-v1:0"
  # ... configuration
}

resource "aws_bedrock_agent" "warren_buffett_eu_west" {
  agent_name = "warren-buffett-financial-advisor-eu"
  foundation_model = "anthropic.claude-3-sonnet-20240229-v1:0"
  # ... configuration
}
```

### **Pattern 2: Load-Based Agent Selection** ⚖️
```python
# Enhanced chat_processor.py with agent load balancing
import boto3
import json
from typing import Dict, List

class BedrockAgentManager:
    def __init__(self):
        self.agents = [
            {"id": "P82I6ITJGO", "alias": "QIYVUYRITH", "region": "us-east-1"},
            {"id": "AGENT_ID_2", "alias": "ALIAS_ID_2", "region": "us-east-1"},
            {"id": "AGENT_ID_3", "alias": "ALIAS_ID_3", "region": "us-west-2"},
            {"id": "AGENT_ID_4", "alias": "ALIAS_ID_4", "region": "eu-west-1"}
        ]
        self.cloudwatch = boto3.client('cloudwatch')
    
    def select_optimal_agent(self, user_id: str, session_id: str) -> Dict:
        """Select the best agent based on load and geography"""
        
        # Get current load metrics for all agents
        load_metrics = self._get_agent_load_metrics()
        
        # Hash-based distribution with load balancing
        primary_agent_idx = hash(user_id) % len(self.agents)
        primary_agent = self.agents[primary_agent_idx]
        
        # Check if primary agent is overloaded (>80% capacity)
        if load_metrics.get(primary_agent['id'], 0) > 80:
            # Find least loaded agent
            least_loaded = min(
                self.agents, 
                key=lambda a: load_metrics.get(a['id'], 0)
            )
            return least_loaded
        
        return primary_agent
    
    def _get_agent_load_metrics(self) -> Dict[str, float]:
        """Fetch current load metrics from CloudWatch"""
        try:
            response = self.cloudwatch.get_metric_statistics(
                Namespace='AWS/Bedrock',
                MetricName='Invocations',
                Dimensions=[
                    {'Name': 'AgentId', 'Value': 'all'}
                ],
                StartTime=datetime.utcnow() - timedelta(minutes=5),
                EndTime=datetime.utcnow(),
                Period=300,
                Statistics=['Sum']
            )
            # Process and return load percentages
            return self._process_load_data(response)
        except Exception as e:
            logger.warning(f"Failed to get load metrics: {e}")
            return {}

# Updated call_bedrock_agent function
def call_bedrock_agent_with_load_balancing(user_message: str, session_id: str) -> Dict[str, Any]:
    """Enhanced Bedrock call with agent selection and fallback"""
    
    agent_manager = BedrockAgentManager()
    selected_agent = agent_manager.select_optimal_agent(session_id, session_id)
    
    start_time = time.time()
    
    try:
        # Initialize client for selected region
        bedrock_client = boto3.client(
            'bedrock-agent-runtime', 
            region_name=selected_agent['region']
        )
        
        response = bedrock_client.invoke_agent(
            agentId=selected_agent['id'],
            agentAliasId=selected_agent['alias'],
            sessionId=session_id,
            inputText=user_message
        )
        
        # Process streaming response
        ai_response = ""
        for event in response.get('completion', []):
            if 'chunk' in event:
                ai_response += event['chunk']['bytes'].decode('utf-8')
        
        processing_time = (time.time() - start_time) * 1000
        
        return {
            'success': True,
            'response': ai_response,
            'processing_time_ms': processing_time,
            'agent_id': selected_agent['id'],
            'region': selected_agent['region']
        }
        
    except Exception as e:
        logger.error(f"Primary agent failed: {e}")
        # Fallback to different agent
        return call_fallback_agent(user_message, session_id, selected_agent['id'])

def call_fallback_agent(user_message: str, session_id: str, failed_agent_id: str) -> Dict[str, Any]:
    """Fallback to alternate agent if primary fails"""
    
    agent_manager = BedrockAgentManager()
    fallback_agents = [a for a in agent_manager.agents if a['id'] != failed_agent_id]
    
    if not fallback_agents:
        return {'success': False, 'error': 'no_agents_available'}
    
    fallback_agent = fallback_agents[0]  # Use first available fallback
    
    try:
        bedrock_client = boto3.client(
            'bedrock-agent-runtime', 
            region_name=fallback_agent['region']
        )
        
        response = bedrock_client.invoke_agent(
            agentId=fallback_agent['id'],
            agentAliasId=fallback_agent['alias'],
            sessionId=session_id,
            inputText=user_message
        )
        
        # Process response...
        return {
            'success': True,
            'response': 'Fallback response processed',
            'agent_id': fallback_agent['id'],
            'region': fallback_agent['region'],
            'fallback': True
        }
        
    except Exception as e:
        logger.error(f"Fallback agent also failed: {e}")
        return {'success': False, 'error': 'all_agents_failed'}
```

### **Pattern 3: Functional Agent Specialization** 🎯
```python
# Specialized agents for different query types
SPECIALIZED_AGENTS = {
    "investment_advice": {
        "id": "INVESTMENT_AGENT_ID", 
        "alias": "INV_ALIAS",
        "description": "Specialized in stock picks and portfolio advice"
    },
    "market_analysis": {
        "id": "MARKET_AGENT_ID", 
        "alias": "MKT_ALIAS",
        "description": "Focused on market trends and economic analysis"
    },
    "general_finance": {
        "id": "P82I6ITJGO", 
        "alias": "QIYVUYRITH",
        "description": "General financial wisdom and life advice"
    },
    "company_analysis": {
        "id": "COMPANY_AGENT_ID",
        "alias": "COMP_ALIAS", 
        "description": "Deep-dive company and industry analysis"
    }
}

def classify_query_intent(user_message: str) -> str:
    """Classify user query to route to appropriate specialized agent"""
    
    # Simple keyword-based classification (enhance with ML later)
    investment_keywords = ["buy", "sell", "stock", "portfolio", "invest"]
    market_keywords = ["market", "economy", "recession", "inflation", "trends"]
    company_keywords = ["company", "earnings", "revenue", "business model", "competitor"]
    
    message_lower = user_message.lower()
    
    if any(keyword in message_lower for keyword in investment_keywords):
        return "investment_advice"
    elif any(keyword in message_lower for keyword in market_keywords):
        return "market_analysis"
    elif any(keyword in message_lower for keyword in company_keywords):
        return "company_analysis"
    else:
        return "general_finance"

def call_specialized_bedrock_agent(user_message: str, session_id: str) -> Dict[str, Any]:
    """Route to specialized agent based on query intent"""
    
    intent = classify_query_intent(user_message)
    selected_agent = SPECIALIZED_AGENTS[intent]
    
    logger.info(f"Routing query to {intent} agent: {selected_agent['id']}")
    
    # Use the selected specialized agent
    return call_bedrock_agent_with_config(user_message, session_id, selected_agent)
```

---

## **📈 Infrastructure Component Scaling**

### **1. SQS Queue Sharding** 📬
```hcl
# Multiple queues for horizontal scaling
variable "queue_shard_count" {
  description = "Number of SQS queue shards for load distribution"
  type        = number
  default     = 1
}

resource "aws_sqs_queue" "chat_processing_queue_shard" {
  count = var.queue_shard_count
  name  = "${var.project_name}-${var.environment}-chat-processing-shard-${count.index}"
  
  # Same configuration as current queue
  visibility_timeout_seconds = 60
  message_retention_seconds  = 1209600  # 14 days
  max_message_size          = 262144   # 256 KB
  delay_seconds             = 0
  receive_wait_time_seconds = 20       # Long polling
  
  # Dead Letter Queue
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.chat_processing_dlq_shard[count.index].arn
    maxReceiveCount     = 3
  })
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-${var.environment}-chat-processing-shard-${count.index}"
    Phase = "Scaling"
    Shard = count.index
  })
}

resource "aws_sqs_queue" "chat_processing_dlq_shard" {
  count = var.queue_shard_count
  name  = "${var.project_name}-${var.environment}-chat-processing-dlq-shard-${count.index}"
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-${var.environment}-chat-processing-dlq-shard-${count.index}"
    Phase = "Scaling"
    Shard = count.index
  })
}

# Queue selection logic
locals {
  queue_urls = [for i in range(var.queue_shard_count) : 
    aws_sqs_queue.chat_processing_queue_shard[i].url
  ]
}
```

```python
# Updated queue selection in websocket_message.py
def get_queue_url(user_id: str) -> str:
    """Select queue shard based on user ID hash"""
    queue_urls = os.environ.get('CHAT_PROCESSING_QUEUE_URLS', '').split(',')
    
    if len(queue_urls) == 1:
        return queue_urls[0]  # Single queue
    
    # Hash-based sharding
    shard = hash(user_id) % len(queue_urls)
    return queue_urls[shard]

# Usage in message handler
queue_url = get_queue_url(user_id)
sqs.send_message(
    QueueUrl=queue_url,
    MessageBody=json.dumps(queue_message),
    # ... rest of message attributes
)
```

### **2. Lambda Function Scaling** ⚡
```hcl
# Enhanced Lambda configuration for scaling
resource "aws_lambda_function" "chat_processor_shard" {
  count = var.processor_shard_count
  
  filename         = "lambda_packages/chat_processor.zip"
  function_name    = "${var.project_name}-${var.environment}-chat-processor-shard-${count.index}"
  role            = aws_iam_role.chat_lambda_role.arn
  handler         = "chat_processor.lambda_handler"
  runtime         = "python3.11"
  timeout         = 60
  
  # Increased memory for better performance
  memory_size = 1024  # More memory = faster CPU
  
  # Reserved concurrency per shard
  reserved_concurrency = 200
  
  environment {
    variables = {
      CONNECTIONS_TABLE          = aws_dynamodb_table.websocket_connections.name
      CHAT_SESSIONS_TABLE        = aws_dynamodb_table.chat_sessions.name
      CHAT_MESSAGES_TABLE        = aws_dynamodb_table.chat_messages.name
      BEDROCK_AGENT_IDS         = jsonencode(var.bedrock_agent_configs)
      BEDROCK_REGION            = var.bedrock_region
      WEBSOCKET_API_ENDPOINT    = aws_apigatewayv2_api.chat_websocket_api.api_endpoint
      LOG_LEVEL                 = var.log_level
      ENVIRONMENT               = var.environment
      PROJECT_NAME              = var.project_name
      SHARD_ID                  = count.index
    }
  }
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-${var.environment}-chat-processor-shard-${count.index}"
    Phase = "Scaling"
    Shard = count.index
  })
}

# SQS Event Source Mapping for each shard
resource "aws_lambda_event_source_mapping" "chat_processor_sqs_shard" {
  count = var.processor_shard_count
  
  event_source_arn = aws_sqs_queue.chat_processing_queue_shard[count.index].arn
  function_name    = aws_lambda_function.chat_processor_shard[count.index].arn
  
  # Optimized batch settings
  batch_size                         = 10
  maximum_batching_window_in_seconds = 5
  
  # Enhanced scaling configuration
  scaling_config {
    maximum_concurrency = 100
  }
  
  # Function response types
  function_response_types = ["ReportBatchItemFailures"]
}
```

### **3. Multi-Region API Gateway** 🌐
```hcl
# Regional API Gateway deployments
variable "deployment_regions" {
  description = "List of regions for API Gateway deployment"
  type        = list(string)
  default     = ["us-east-1"]
}

# Provider aliases for multi-region deployment
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

provider "aws" {
  alias  = "us_west_2"
  region = "us-west-2"
}

provider "aws" {
  alias  = "eu_west_1"
  region = "eu-west-1"
}

# Multi-region WebSocket API
resource "aws_apigatewayv2_api" "chat_websocket_api_regional" {
  count = length(var.deployment_regions)
  
  name                       = "${var.project_name}-ws-${var.deployment_regions[count.index]}"
  protocol_type             = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
  
  cors_configuration {
    allow_origins = var.allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["content-type", "x-amz-date", "authorization"]
  }
  
  tags = merge(local.common_tags, {
    Name   = "${var.project_name}-websocket-api-${var.deployment_regions[count.index]}"
    Phase  = "Scaling"
    Region = var.deployment_regions[count.index]
  })
  
  # Use appropriate provider for each region
  providers = {
    aws = aws.${replace(var.deployment_regions[count.index], "-", "_")}
  }
}

# Route 53 for global load balancing
resource "aws_route53_zone" "chat_api" {
  name = var.domain_name
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-dns-zone"
    Phase = "Scaling"
  })
}

resource "aws_route53_record" "websocket_api_regional" {
  count = length(var.deployment_regions)
  
  zone_id = aws_route53_zone.chat_api.zone_id
  name    = "ws-${var.deployment_regions[count.index]}.${var.domain_name}"
  type    = "CNAME"
  ttl     = 300
  records = [aws_apigatewayv2_api.chat_websocket_api_regional[count.index].api_endpoint]
}

# Health-based routing
resource "aws_route53_record" "websocket_api_global" {
  zone_id = aws_route53_zone.chat_api.zone_id
  name    = "ws.${var.domain_name}"
  type    = "A"
  
  alias {
    name                   = aws_apigatewayv2_api.chat_websocket_api_regional[0].api_endpoint
    zone_id               = aws_apigatewayv2_api.chat_websocket_api_regional[0].hosted_zone_id
    evaluate_target_health = true
  }
  
  # Failover routing policy
  failover_routing_policy {
    type = "PRIMARY"
  }
  
  health_check_id = aws_route53_health_check.websocket_api_primary.id
}
```

### **4. DynamoDB Global Tables** 💾
```hcl
# Global Tables for multi-region data replication
resource "aws_dynamodb_table" "chat_messages_global" {
  name         = "${var.project_name}-${var.environment}-chat-messages"
  billing_mode = "PAY_PER_REQUEST"
  
  hash_key  = "message_id"
  range_key = "timestamp"
  
  attribute {
    name = "message_id"
    type = "S"
  }
  
  attribute {
    name = "timestamp"
    type = "S"
  }
  
  attribute {
    name = "session_id"
    type = "S"
  }
  
  # Global Secondary Index for session queries
  global_secondary_index {
    name            = "SessionIndex"
    hash_key        = "session_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }
  
  # Enable Global Tables
  replica {
    region_name = "us-west-2"
    
    global_secondary_index {
      name            = "SessionIndex"
      projection_type = "ALL"
    }
  }
  
  replica {
    region_name = "eu-west-1"
    
    global_secondary_index {
      name            = "SessionIndex"
      projection_type = "ALL"
    }
  }
  
  # Point-in-time recovery
  point_in_time_recovery {
    enabled = true
  }
  
  # Server-side encryption
  server_side_encryption {
    enabled     = true
    kms_key_id = aws_kms_key.chat_api_key.arn
  }
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-${var.environment}-chat-messages-global"
    Phase = "Scaling"
  })
}

# Stream processing for cross-region synchronization
resource "aws_dynamodb_table" "chat_sessions_global" {
  name         = "${var.project_name}-${var.environment}-chat-sessions"
  billing_mode = "PAY_PER_REQUEST"
  
  hash_key = "session_id"
  
  attribute {
    name = "session_id"
    type = "S"
  }
  
  attribute {
    name = "user_id"
    type = "S"
  }
  
  # Global Secondary Index for user queries
  global_secondary_index {
    name            = "UserIndex"
    hash_key        = "user_id"
    projection_type = "ALL"
  }
  
  # Enable Global Tables for multi-region
  replica {
    region_name = "us-west-2"
    
    global_secondary_index {
      name            = "UserIndex"
      projection_type = "ALL"
    }
  }
  
  replica {
    region_name = "eu-west-1"
    
    global_secondary_index {
      name            = "UserIndex"
      projection_type = "ALL"
    }
  }
  
  # TTL for automatic session cleanup
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  
  tags = merge(local.common_tags, {
    Name  = "${var.project_name}-${var.environment}-chat-sessions-global"
    Phase = "Scaling"
  })
}
```

---

## **📊 Advanced Monitoring & Auto-Scaling**

### **CloudWatch Metrics & Alarms** 📈
```hcl
# Enhanced monitoring for scaled infrastructure
resource "aws_cloudwatch_metric_alarm" "bedrock_agent_response_time" {
  count = length(var.bedrock_agent_configs)
  
  alarm_name          = "${var.project_name}-bedrock-agent-${count.index}-response-time"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "Duration"
  namespace           = "AWS/Bedrock"
  period              = "300"
  statistic           = "Average"
  threshold           = "5000"  # 5 seconds
  alarm_description   = "Bedrock agent response time is too high"
  
  dimensions = {
    AgentId = var.bedrock_agent_configs[count.index].id
  }
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "agent_load_distribution" {
  alarm_name          = "${var.project_name}-agent-load-imbalance"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "3"
  metric_name         = "LoadImbalance"
  namespace           = "BuffettChat/Scaling"
  period              = "300"
  statistic           = "Maximum"
  threshold           = "30"  # 30% imbalance
  alarm_description   = "Agent load distribution is imbalanced"
  
  alarm_actions = [aws_sns_topic.alerts.arn]
}

# Auto-scaling based on queue depth
resource "aws_cloudwatch_metric_alarm" "sqs_queue_depth_scale_up" {
  count = var.queue_shard_count
  
  alarm_name          = "${var.project_name}-sqs-scale-up-shard-${count.index}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "ApproximateNumberOfVisibleMessages"
  namespace           = "AWS/SQS"
  period              = "300"
  statistic           = "Average"
  threshold           = "100"
  alarm_description   = "SQS queue depth is high - scale up"
  
  dimensions = {
    QueueName = aws_sqs_queue.chat_processing_queue_shard[count.index].name
  }
  
  alarm_actions = [aws_sns_topic.scaling_actions.arn]
}
```

### **Lambda Auto-Scaling Configuration** ⚡
```python
# Enhanced Lambda function with auto-scaling metrics
import boto3
import json
from datetime import datetime, timedelta

class ScalingMetricsCollector:
    def __init__(self):
        self.cloudwatch = boto3.client('cloudwatch')
        
    def publish_custom_metrics(self, metrics_data: dict):
        """Publish custom metrics for scaling decisions"""
        
        try:
            self.cloudwatch.put_metric_data(
                Namespace='BuffettChat/Scaling',
                MetricData=[
                    {
                        'MetricName': 'AgentResponseTime',
                        'Value': metrics_data.get('response_time_ms', 0),
                        'Unit': 'Milliseconds',
                        'Dimensions': [
                            {'Name': 'AgentId', 'Value': metrics_data.get('agent_id', 'unknown')},
                            {'Name': 'Region', 'Value': metrics_data.get('region', 'us-east-1')}
                        ]
                    },
                    {
                        'MetricName': 'ConcurrentSessions',
                        'Value': metrics_data.get('concurrent_sessions', 0),
                        'Unit': 'Count'
                    },
                    {
                        'MetricName': 'MessageProcessingRate',
                        'Value': metrics_data.get('messages_per_minute', 0),
                        'Unit': 'Count/Minute'
                    },
                    {
                        'MetricName': 'LoadImbalance',
                        'Value': metrics_data.get('load_imbalance_percentage', 0),
                        'Unit': 'Percent'
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Failed to publish metrics: {e}")

# Enhanced lambda_handler with metrics collection
def lambda_handler(event, context):
    """Enhanced handler with scaling metrics collection"""
    
    start_time = time.time()
    metrics_collector = ScalingMetricsCollector()
    
    try:
        # Process SQS messages
        processed_count = 0
        failed_count = 0
        
        for record in event['Records']:
            try:
                process_message(record)
                processed_count += 1
            except Exception as e:
                logger.error(f"Failed to process message: {e}")
                failed_count += 1
        
        # Calculate and publish metrics
        processing_time = (time.time() - start_time) * 1000
        
        metrics_data = {
            'response_time_ms': processing_time,
            'messages_processed': processed_count,
            'messages_failed': failed_count,
            'concurrent_sessions': get_active_session_count(),
            'agent_id': os.environ.get('BEDROCK_AGENT_ID'),
            'region': os.environ.get('AWS_REGION'),
            'shard_id': os.environ.get('SHARD_ID', '0')
        }
        
        metrics_collector.publish_custom_metrics(metrics_data)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'processed': processed_count,
                'failed': failed_count,
                'processing_time_ms': processing_time
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda handler failed: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def get_active_session_count() -> int:
    """Get count of active WebSocket connections"""
    try:
        dynamodb = boto3.resource('dynamodb')
        connections_table = dynamodb.Table(os.environ['CONNECTIONS_TABLE'])
        
        # Count active connections (within last 5 minutes)
        cutoff_time = (datetime.utcnow() - timedelta(minutes=5)).isoformat()
        
        response = connections_table.scan(
            FilterExpression='last_seen > :cutoff',
            ExpressionAttributeValues={':cutoff': cutoff_time},
            Select='COUNT'
        )
        
        return response.get('Count', 0)
        
    except Exception as e:
        logger.error(f"Failed to get session count: {e}")
        return 0
```

---

## **🛠️ Implementation Phases**

### **Phase 1: Foundation Monitoring** 📊
**Timeline:** Week 1-2
**Goal:** Establish baseline metrics and alerts

```bash
# Deploy monitoring infrastructure
terraform apply -target=module.monitoring

# Validate metrics collection
aws cloudwatch get-metric-statistics \
  --namespace "BuffettChat/Performance" \
  --metric-name "AgentResponseTime" \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Average
```

**Deliverables:**
- [ ] CloudWatch dashboard deployed
- [ ] Performance baselines established
- [ ] Alert thresholds configured
- [ ] Monitoring runbook created

### **Phase 2: Horizontal Scaling Preparation** 🚀
**Timeline:** Week 3-4  
**Goal:** Implement multi-agent support and queue sharding

```bash
# Deploy scaled infrastructure
terraform apply \
  -var="queue_shard_count=2" \
  -var="processor_shard_count=2" \
  -var="bedrock_agent_configs=[{id='P82I6ITJGO',alias='QIYVUYRITH'},{id='AGENT_2',alias='ALIAS_2'}]"
```

**Deliverables:**
- [ ] Multi-agent load balancing implemented
- [ ] SQS queue sharding configured
- [ ] Lambda function scaling tested
- [ ] Failover mechanisms validated

### **Phase 3: Multi-Region Deployment** 🌍
**Timeline:** Week 5-8
**Goal:** Deploy globally distributed infrastructure

```bash
# Deploy multi-region infrastructure
terraform apply \
  -var="deployment_regions=['us-east-1','us-west-2','eu-west-1']" \
  -var="enable_global_tables=true"
```

**Deliverables:**
- [ ] Multi-region API Gateway deployed
- [ ] DynamoDB Global Tables configured
- [ ] DNS-based load balancing implemented
- [ ] Cross-region failover tested

### **Phase 4: Advanced Optimization** ⚡
**Timeline:** Week 9-12
**Goal:** Implement advanced scaling and optimization features

**Deliverables:**
- [ ] ML-based load prediction
- [ ] Advanced caching with Redis
- [ ] Specialized agent routing
- [ ] Cost optimization automation

---

## **💰 Cost Analysis & Optimization**

### **Scaling Cost Breakdown** 📊

| **Component** | **Current (1K users)** | **Growth (5K users)** | **Enterprise (20K users)** |
|---------------|------------------------|----------------------|---------------------------|
| **Bedrock Agents** | $100-300/month | $300-800/month | $800-2000/month |
| **Lambda Functions** | $20-50/month | $100-200/month | $400-800/month |
| **DynamoDB** | $10-30/month | $50-150/month | $200-500/month |
| **SQS** | $2-5/month | $10-20/month | $40-80/month |
| **API Gateway** | $5-15/month | $25-50/month | $100-200/month |
| **CloudWatch** | $5-10/month | $20-40/month | $80-160/month |
| **Data Transfer** | $5-10/month | $25-50/month | $100-200/month |
| **Total** | **$147-420/month** | **$530-1310/month** | **$1720-3940/month** |

### **Cost Optimization Strategies** 💡

1. **Reserved Capacity** (for predictable workloads)
```hcl
# DynamoDB Reserved Capacity
resource "aws_dynamodb_table" "chat_messages_optimized" {
  billing_mode   = "PROVISIONED"
  read_capacity  = 100   # Reserved capacity
  write_capacity = 50    # Reserved capacity
  
  # Auto-scaling configuration
  autoscaling_settings {
    target_tracking_scaling_policy_configuration {
      target_value = 70.0
      scale_in_cooldown  = 60
      scale_out_cooldown = 60
    }
  }
}
```

2. **Intelligent Tiering**
```python
# Implement message archiving for cost savings
def archive_old_messages():
    """Archive messages older than 90 days to S3"""
    
    cutoff_date = datetime.utcnow() - timedelta(days=90)
    
    # Query old messages
    old_messages = messages_table.scan(
        FilterExpression='created_at < :cutoff',
        ExpressionAttributeValues={':cutoff': cutoff_date.isoformat()}
    )
    
    # Archive to S3 Glacier
    s3_client = boto3.client('s3')
    for message in old_messages['Items']:
        s3_client.put_object(
            Bucket='chat-archive-bucket',
            Key=f"messages/{message['message_id']}.json",
            Body=json.dumps(message),
            StorageClass='GLACIER'
        )
        
        # Delete from DynamoDB
        messages_table.delete_item(
            Key={'message_id': message['message_id']}
        )
```

3. **Environment-Based Scaling**
```hcl
# Development environment cost optimization
variable "environment_scaling_config" {
  type = map(object({
    bedrock_agents         = number
    lambda_memory         = number
    lambda_concurrency    = number
    enable_global_tables  = bool
    log_retention_days    = number
  }))
  
  default = {
    dev = {
      bedrock_agents         = 1
      lambda_memory         = 512
      lambda_concurrency    = 10
      enable_global_tables  = false
      log_retention_days    = 7
    }
    staging = {
      bedrock_agents         = 2
      lambda_memory         = 1024
      lambda_concurrency    = 50
      enable_global_tables  = false
      log_retention_days    = 14
    }
    prod = {
      bedrock_agents         = 4
      lambda_memory         = 1024
      lambda_concurrency    = 200
      enable_global_tables  = true
      log_retention_days    = 30
    }
  }
}
```

---

## **🔧 Troubleshooting & Best Practices**

### **Common Scaling Issues** ⚠️

1. **Agent Overload**
```python
# Detection and mitigation
def detect_agent_overload():
    """Monitor agent performance and trigger scaling"""
    
    metrics = get_agent_metrics()
    
    for agent_id, stats in metrics.items():
        if stats['response_time'] > 5000:  # 5 seconds
            logger.warning(f"Agent {agent_id} overloaded: {stats['response_time']}ms")
            trigger_agent_scaling(agent_id)
        
        if stats['error_rate'] > 0.05:  # 5% error rate
            logger.error(f"Agent {agent_id} high error rate: {stats['error_rate']}")
            failover_to_backup_agent(agent_id)

def trigger_agent_scaling(agent_id: str):
    """Trigger automatic scaling for overloaded agent"""
    
    # Publish scaling metric
    cloudwatch = boto3.client('cloudwatch')
    cloudwatch.put_metric_data(
        Namespace='BuffettChat/Scaling',
        MetricData=[{
            'MetricName': 'AgentOverload',
            'Value': 1,
            'Unit': 'Count',
            'Dimensions': [{'Name': 'AgentId', 'Value': agent_id}]
        }]
    )
    
    # Trigger SNS notification for ops team
    sns = boto3.client('sns')
    sns.publish(
        TopicArn=os.environ['SCALING_ALERTS_TOPIC'],
        Message=f"Agent {agent_id} requires immediate scaling",
        Subject="Bedrock Agent Scaling Alert"
    )
```

2. **Cross-Region Latency**
```python
# Region selection optimization
def select_optimal_region(user_location: dict) -> str:
    """Select best region based on user location"""
    
    user_lat = user_location.get('latitude', 0)
    user_lon = user_location.get('longitude', 0)
    
    # Calculate distance to each region
    regions = {
        'us-east-1': {'lat': 39.0458, 'lon': -77.5081},    # Virginia
        'us-west-2': {'lat': 45.5152, 'lon': -122.6784},   # Oregon  
        'eu-west-1': {'lat': 53.3331, 'lon': -6.2489}      # Ireland
    }
    
    min_distance = float('inf')
    best_region = 'us-east-1'  # Default
    
    for region, coords in regions.items():
        distance = calculate_distance(user_lat, user_lon, coords['lat'], coords['lon'])
        if distance < min_distance:
            min_distance = distance
            best_region = region
    
    return best_region

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great circle distance between two points"""
    from math import radians, sin, cos, sqrt, atan2
    
    R = 6371  # Earth's radius in kilometers
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c
```

3. **Memory Optimization**
```python
# Efficient message processing
import gc
from functools import lru_cache

class OptimizedMessageProcessor:
    def __init__(self):
        self.connection_cache = {}
        self.session_cache = {}
        
    @lru_cache(maxsize=1000)
    def get_cached_session(self, session_id: str) -> dict:
        """Cache frequently accessed sessions"""
        try:
            response = sessions_table.get_item(Key={'session_id': session_id})
            return response.get('Item', {})
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            return {}
    
    def process_batch_efficiently(self, records: list) -> dict:
        """Process SQS records in optimized batches"""
        
        results = {'successful': 0, 'failed': 0}
        
        # Group messages by session for batch processing
        session_groups = {}
        for record in records:
            try:
                message_data = json.loads(record['body'])
                session_id = message_data.get('session_id')
                
                if session_id not in session_groups:
                    session_groups[session_id] = []
                session_groups[session_id].append(message_data)
                
            except Exception as e:
                logger.error(f"Failed to parse record: {e}")
                results['failed'] += 1
        
        # Process each session's messages in batch
        for session_id, messages in session_groups.items():
            try:
                self.process_session_messages(session_id, messages)
                results['successful'] += len(messages)
            except Exception as e:
                logger.error(f"Failed to process session {session_id}: {e}")
                results['failed'] += len(messages)
        
        # Clear caches periodically
        if len(self.session_cache) > 500:
            self.session_cache.clear()
            gc.collect()
        
        return results
```

### **Performance Best Practices** 🎯

1. **Connection Management**
```python
# Efficient WebSocket connection handling
class WebSocketConnectionManager:
    def __init__(self):
        self.apigateway = None
        self.connection_pool = {}
        
    def get_apigateway_client(self, region: str):
        """Reuse API Gateway clients per region"""
        if region not in self.connection_pool:
            self.connection_pool[region] = boto3.client(
                'apigatewaymanagementapi',
                endpoint_url=f"https://{os.environ['WEBSOCKET_API_ID']}.execute-api.{region}.amazonaws.com/dev",
                region_name=region
            )
        return self.connection_pool[region]
    
    def send_message_optimized(self, connection_id: str, message: dict, region: str = 'us-east-1') -> bool:
        """Send message with connection pooling and retry logic"""
        
        client = self.get_apigateway_client(region)
        
        for attempt in range(3):  # Retry up to 3 times
            try:
                client.post_to_connection(
                    ConnectionId=connection_id,
                    Data=json.dumps(message)
                )
                return True
                
            except client.exceptions.GoneException:
                # Connection is stale, remove from active connections
                self.remove_stale_connection(connection_id)
                return False
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt == 2:  # Last attempt
                    logger.error(f"Failed to send message after 3 attempts: {e}")
                    return False
                time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
        
        return False
```

2. **Batch Processing Optimization**
```python
# Optimized DynamoDB batch operations
def batch_write_messages(messages: list) -> dict:
    """Efficiently write multiple messages to DynamoDB"""
    
    # Split into batches of 25 (DynamoDB limit)
    batch_size = 25
    batches = [messages[i:i + batch_size] for i in range(0, len(messages), batch_size)]
    
    results = {'successful': 0, 'failed': 0, 'unprocessed': []}
    
    for batch in batches:
        try:
            # Prepare batch write request
            request_items = {
                os.environ['CHAT_MESSAGES_TABLE']: [
                    {'PutRequest': {'Item': convert_floats_to_decimals(msg)}}
                    for msg in batch
                ]
            }
            
            # Execute batch write with retry logic
            unprocessed = request_items
            max_retries = 3
            
            for retry in range(max_retries):
                if not unprocessed:
                    break
                    
                response = dynamodb.batch_write_item(RequestItems=unprocessed)
                unprocessed = response.get('UnprocessedItems', {})
                
                if unprocessed and retry < max_retries - 1:
                    # Exponential backoff for retries
                    time.sleep(0.1 * (2 ** retry))
            
            # Track results
            processed_count = len(batch) - len(unprocessed.get(os.environ['CHAT_MESSAGES_TABLE'], []))
            results['successful'] += processed_count
            results['failed'] += len(batch) - processed_count
            
            if unprocessed:
                results['unprocessed'].extend(unprocessed.get(os.environ['CHAT_MESSAGES_TABLE'], []))
                
        except Exception as e:
            logger.error(f"Batch write failed: {e}")
            results['failed'] += len(batch)
    
    return results
```

---

## **📚 Quick Reference Commands**

### **Deployment Commands** 🚀
```bash
# Deploy base infrastructure
terraform apply -target=module.base_infrastructure

# Deploy with scaling (2 agents, 2 queues)
terraform apply \
  -var="queue_shard_count=2" \
  -var="processor_shard_count=2" \
  -var="bedrock_agent_configs=[{id='P82I6ITJGO',alias='QIYVUYRITH'},{id='AGENT_2',alias='ALIAS_2'}]"

# Deploy multi-region
terraform apply \
  -var="deployment_regions=['us-east-1','us-west-2','eu-west-1']" \
  -var="enable_global_tables=true"

# Scale up for high load
terraform apply \
  -var="queue_shard_count=4" \
  -var="processor_shard_count=8" \
  -var="lambda_concurrency=500"
```

### **Monitoring Commands** 📊
```bash
# Check agent performance
aws cloudwatch get-metric-statistics \
  --namespace "AWS/Bedrock" \
  --metric-name "Duration" \
  --dimensions Name=AgentId,Value=P82I6ITJGO \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-01T23:59:59Z \
  --period 3600 \
  --statistics Average,Maximum

# Monitor SQS queue depth
aws sqs get-queue-attributes \
  --queue-url "https://sqs.us-east-1.amazonaws.com/ACCOUNT/buffett-chat-api-dev-chat-processing" \
  --attribute-names All

# Check Lambda concurrency
aws lambda get-function-concurrency \
  --function-name "buffett-chat-api-dev-chat-processor"

# View recent errors
aws logs tail /aws/lambda/buffett-chat-api-dev-chat-processor \
  --follow \
  --filter-pattern "ERROR"
```

### **Testing Commands** 🧪
```bash
# Load test WebSocket API
cd tests/
npm install ws
node load_test.js --connections=100 --duration=300

# Test multi-region failover
dig ws.yourdomain.com
curl -I https://api-us-west-2.yourdomain.com/health

# Validate Global Tables sync
aws dynamodb scan \
  --region us-east-1 \
  --table-name buffett-chat-api-prod-chat-messages \
  --limit 5

aws dynamodb scan \
  --region us-west-2 \
  --table-name buffett-chat-api-prod-chat-messages \
  --limit 5
```

---

## **🎯 Summary & Next Steps**

This scaling guide provides a complete roadmap for growing your Warren Buffett Chat API from hundreds to tens of thousands of users. The key takeaways:

### **Immediate Actions** ✅
1. **Monitor current performance** - Establish baselines before scaling
2. **Set up alerts** - Get notified before users experience issues  
3. **Plan scaling triggers** - Define when to implement each scaling phase

### **Growth Strategy** 📈
1. **Start with load balancing** - 2 agents at 1,000 users
2. **Add queue sharding** - Horizontal scaling for processing
3. **Deploy multi-region** - Global performance at 5,000+ users
4. **Implement specialization** - Optimize for different query types

### **Cost Management** 💰
1. **Environment-based scaling** - Different configs for dev/staging/prod
2. **Reserved capacity** - Predictable workloads get cost savings
3. **Intelligent archiving** - Move old data to cheaper storage

### **Monitoring & Operations** 🛠️
1. **Comprehensive metrics** - Track all components and dependencies
2. **Automated scaling** - Respond to load without manual intervention
3. **Graceful degradation** - Fallback strategies for component failures

**Remember:** Scale incrementally, monitor continuously, and optimize costs at every step. The architecture is designed to grow with your success! 🚀

---

*This guide should be reviewed and updated quarterly as AWS services evolve and your usage patterns change.*
