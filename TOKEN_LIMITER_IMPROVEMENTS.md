# Token Limiter Improvements

This document outlines improvement options for the BuffettGPT token limiting system, covering both the limiter logic and DynamoDB write patterns.

---

## Current Architecture

### Token Usage Table Schema

```
Table: buffett-{env}-token-usage

Primary Key:
  - user_id (Hash Key) - User identifier
  - month (Range Key)  - Format "YYYY-MM"

Attributes:
  - input_tokens (N)
  - output_tokens (N)
  - total_tokens (N)
  - request_count (N)
  - token_limit (N)
  - notified_80 (BOOL)
  - notified_90 (BOOL)
  - limit_reached_at (S)
  - last_request_at (S)
```

### Current Flow

1. **Pre-request**: `check_limit()` validates user hasn't exceeded monthly limit
2. **Post-request**: `record_usage()` atomically increments token counters via DynamoDB `ADD`
3. **Threshold detection**: Flags set at 80%, 90%, and 100% usage

---

## Part 1: Token Limiter Improvements

### 1.1 Full Usage Reset for Subscribers

**Problem**: No way to reset a user's usage mid-month (e.g., after upgrade or customer service request).

**Solution**: Add `reset_usage()` method to `TokenUsageTracker`:

```python
def reset_usage(self, user_id: str, month: Optional[str] = None) -> bool:
    """
    Fully reset a user's token usage for the month.

    Use cases:
    - Subscriber upgrade mid-month
    - Customer service goodwill reset
    - Testing/debugging

    Args:
        user_id: The user identifier
        month: Target month (defaults to current month)

    Returns:
        True if successful, False otherwise
    """
    if not self.table:
        logger.warning("Token usage table not initialized")
        return False

    try:
        target_month = month or self.get_current_month()

        self.table.update_item(
            Key={'user_id': user_id, 'month': target_month},
            UpdateExpression='''
                SET input_tokens = :zero,
                    output_tokens = :zero,
                    total_tokens = :zero,
                    request_count = :zero
                REMOVE notified_80, notified_90, limit_reached_at
            ''',
            ExpressionAttributeValues={':zero': 0}
        )

        logger.info(f"Reset usage for user {user_id} in month {target_month}")
        return True

    except ClientError as e:
        logger.error(f"Failed to reset usage for {user_id}: {e}")
        return False
```

---

### 1.2 Automatic Tier-Based Limit Synchronization

**Problem**: Token limits are set once via `if_not_exists`. When a user upgrades their subscription, their limit doesn't automatically increase.

**Solution**: Sync limits on subscription change:

```python
# Add to TokenUsageTracker

TIER_LIMITS = {
    'anonymous': 1_000,
    'free': 10_000,
    'authenticated': 50_000,
    'premium': 500_000,
    'enterprise': float('inf')
}

def sync_tier_limit(self, user_id: str, tier: str, month: Optional[str] = None) -> dict:
    """
    Sync user's token limit based on subscription tier.

    Call this when:
    - User upgrades/downgrades subscription
    - User logs in (to ensure limit is current)

    Returns:
        Updated usage record with new limit
    """
    target_month = month or self.get_current_month()
    new_limit = self.TIER_LIMITS.get(tier, self.default_token_limit)

    # Use update to set limit and return current state
    response = self.table.update_item(
        Key={'user_id': user_id, 'month': target_month},
        UpdateExpression='''
            SET token_limit = :limit,
                subscription_tier = :tier,
                tier_updated_at = :now
        ''',
        ExpressionAttributeValues={
            ':limit': new_limit,
            ':tier': tier,
            ':now': datetime.utcnow().isoformat() + 'Z'
        },
        ReturnValues='ALL_NEW'
    )

    # Clear limit_reached flag if new limit allows more usage
    item = response.get('Attributes', {})
    if item.get('total_tokens', 0) < new_limit and item.get('limit_reached_at'):
        self.table.update_item(
            Key={'user_id': user_id, 'month': target_month},
            UpdateExpression='REMOVE limit_reached_at'
        )

    return item
```

**Integration point** - Call from auth callback:

```python
# In auth_callback.py after successful login
token_tracker.sync_tier_limit(
    user_id=user_claims['sub'],
    tier=user_claims.get('subscription_tier', 'authenticated')
)
```

---

### 1.3 Bonus Token Support

**Problem**: No way to grant extra tokens for promotions, customer service, or referrals.

**Solution**: Add bonus token field and grant mechanism:

```python
def grant_bonus_tokens(self, user_id: str, bonus: int, reason: str = None) -> dict:
    """
    Grant bonus tokens to a user (stackable).

    Args:
        user_id: The user identifier
        bonus: Number of bonus tokens to add
        reason: Optional reason for audit trail

    Returns:
        Updated usage record
    """
    target_month = self.get_current_month()

    response = self.table.update_item(
        Key={'user_id': user_id, 'month': target_month},
        UpdateExpression='''
            ADD bonus_tokens :bonus
            SET last_bonus_at = :now,
                last_bonus_reason = :reason
        ''',
        ExpressionAttributeValues={
            ':bonus': bonus,
            ':now': datetime.utcnow().isoformat() + 'Z',
            ':reason': reason or 'manual_grant'
        },
        ReturnValues='ALL_NEW'
    )

    logger.info(f"Granted {bonus} bonus tokens to {user_id}: {reason}")
    return response.get('Attributes', {})
```

**Update check_limit to include bonus**:

```python
def check_limit(self, user_id: str) -> dict:
    # ... existing code ...

    token_limit = int(item.get('token_limit', self.default_token_limit))
    bonus_tokens = int(item.get('bonus_tokens', 0))
    effective_limit = token_limit + bonus_tokens

    total_tokens = int(item.get('total_tokens', 0))
    allowed = total_tokens < effective_limit

    return {
        'allowed': allowed,
        'total_tokens': total_tokens,
        'token_limit': token_limit,
        'bonus_tokens': bonus_tokens,
        'effective_limit': effective_limit,
        'percent_used': round((total_tokens / effective_limit) * 100, 1) if effective_limit > 0 else 0,
        'remaining_tokens': max(0, effective_limit - total_tokens),
        'reset_date': self.get_reset_date()
    }
```

---

### 1.4 Rollover Tokens for Premium Users

**Problem**: Unused tokens are lost at month end, which feels punitive to paying subscribers.

**Solution**: Carry forward unused tokens (capped):

```python
def process_monthly_rollover(self, user_id: str, max_rollover_percent: int = 25) -> dict:
    """
    Process end-of-month token rollover for premium users.

    Run via scheduled Lambda on 1st of each month.

    Args:
        user_id: The user identifier
        max_rollover_percent: Max % of limit that can roll over (default 25%)

    Returns:
        Rollover result with tokens carried forward
    """
    now = datetime.utcnow()

    # Get previous month
    if now.month == 1:
        prev_month = f"{now.year - 1}-12"
    else:
        prev_month = f"{now.year}-{now.month - 1:02d}"

    current_month = self.get_current_month()

    # Fetch previous month's record
    try:
        response = self.table.get_item(
            Key={'user_id': user_id, 'month': prev_month}
        )
        prev_record = response.get('Item', {})
    except ClientError:
        return {'rollover_tokens': 0, 'reason': 'no_previous_record'}

    # Check eligibility (premium+ only)
    tier = prev_record.get('subscription_tier', 'free')
    if tier not in ('premium', 'enterprise'):
        return {'rollover_tokens': 0, 'reason': 'tier_not_eligible'}

    # Calculate rollover
    token_limit = int(prev_record.get('token_limit', 0))
    total_used = int(prev_record.get('total_tokens', 0))
    unused = max(0, token_limit - total_used)

    max_rollover = int(token_limit * (max_rollover_percent / 100))
    rollover_tokens = min(unused, max_rollover)

    if rollover_tokens > 0:
        # Apply to current month as bonus
        self.table.update_item(
            Key={'user_id': user_id, 'month': current_month},
            UpdateExpression='''
                ADD rollover_tokens :rollover
                SET rollover_from = :prev_month
            ''',
            ExpressionAttributeValues={
                ':rollover': rollover_tokens,
                ':prev_month': prev_month
            }
        )

    return {
        'rollover_tokens': rollover_tokens,
        'from_month': prev_month,
        'to_month': current_month,
        'unused_tokens': unused,
        'max_rollover': max_rollover
    }
```

---

### 1.5 Real-Time Threshold Notifications

**Problem**: Threshold flags are set but no actual notifications are sent.

**Solution**: Integrate with SNS for email/webhook notifications:

```python
import boto3

sns_client = boto3.client('sns')
USAGE_ALERTS_TOPIC = os.environ.get('USAGE_ALERTS_TOPIC_ARN')

def _send_threshold_notification(
    self,
    user_id: str,
    threshold: str,
    total_tokens: int,
    token_limit: int
) -> None:
    """Send notification when usage threshold is crossed."""

    if not USAGE_ALERTS_TOPIC:
        logger.debug("No SNS topic configured for usage alerts")
        return

    message = {
        'event_type': 'token_threshold_reached',
        'user_id': user_id,
        'threshold': threshold,
        'total_tokens': total_tokens,
        'token_limit': token_limit,
        'percent_used': round((total_tokens / token_limit) * 100, 1),
        'remaining_tokens': max(0, token_limit - total_tokens),
        'reset_date': self.get_reset_date(),
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }

    try:
        sns_client.publish(
            TopicArn=USAGE_ALERTS_TOPIC,
            Message=json.dumps(message),
            MessageAttributes={
                'event_type': {
                    'DataType': 'String',
                    'StringValue': 'token_threshold'
                },
                'threshold': {
                    'DataType': 'String',
                    'StringValue': threshold
                },
                'user_id': {
                    'DataType': 'String',
                    'StringValue': user_id
                }
            }
        )
        logger.info(f"Sent {threshold} notification for user {user_id}")

    except ClientError as e:
        logger.error(f"Failed to send threshold notification: {e}")
```

**Terraform for SNS topic**:

```hcl
resource "aws_sns_topic" "usage_alerts" {
  name = "${var.project_name}-${var.environment}-usage-alerts"

  tags = var.common_tags
}

# Email subscription for admins
resource "aws_sns_topic_subscription" "admin_email" {
  topic_arn = aws_sns_topic.usage_alerts.arn
  protocol  = "email"
  endpoint  = var.admin_email
}

# Lambda subscription for in-app notifications
resource "aws_sns_topic_subscription" "notification_lambda" {
  topic_arn = aws_sns_topic.usage_alerts.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.send_user_notification.arn
}
```

---

### 1.6 Admin API for Token Management

**Problem**: No programmatic way to manage user tokens without direct DynamoDB access.

**Solution**: Create admin endpoints:

```python
# New handler: admin_token_handler.py

def lambda_handler(event: dict, context) -> dict:
    """
    Admin endpoints for token management.

    Endpoints:
        GET  /admin/tokens/{user_id}         - Get user's current usage
        POST /admin/tokens/{user_id}/reset   - Reset user's usage
        POST /admin/tokens/{user_id}/limit   - Set user's limit
        POST /admin/tokens/{user_id}/bonus   - Grant bonus tokens
        GET  /admin/tokens/stats             - Get aggregate stats
    """

    # Verify admin authorization
    if not is_admin(event):
        return {'statusCode': 403, 'body': 'Forbidden'}

    http_method = event.get('requestContext', {}).get('http', {}).get('method')
    path = event.get('rawPath', '')
    user_id = event.get('pathParameters', {}).get('user_id')

    if http_method == 'GET' and user_id:
        return get_user_usage(user_id)

    elif http_method == 'POST' and '/reset' in path:
        return reset_user_usage(user_id)

    elif http_method == 'POST' and '/limit' in path:
        body = json.loads(event.get('body', '{}'))
        return set_user_limit(user_id, body.get('limit'))

    elif http_method == 'POST' and '/bonus' in path:
        body = json.loads(event.get('body', '{}'))
        return grant_bonus(user_id, body.get('tokens'), body.get('reason'))

    elif http_method == 'GET' and '/stats' in path:
        return get_aggregate_stats()

    return {'statusCode': 404, 'body': 'Not found'}
```

---

## Part 2: DynamoDB Write Pattern Improvements

### Current Pattern Analysis

**Strengths**:
- Atomic `ADD` operation prevents race conditions
- `user_id` as partition key distributes load across partitions
- Simple, easy to understand

**Limitations**:
- Same item updated on every request (per user/month)
- No write buffering for burst protection
- No TTL for automatic cleanup

---

### 2.1 Add TTL for Automatic Data Cleanup

**Problem**: Token usage records accumulate indefinitely.

**Solution**: Add TTL attribute to automatically delete old records.

**Terraform update** (`token_usage.tf`):

```hcl
resource "aws_dynamodb_table" "token_usage" {
  # ... existing config ...

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }
}
```

**Code update** - Set TTL on writes:

```python
from datetime import datetime, timedelta

# Keep records for 2 years
TTL_DAYS = 730

def record_usage(self, user_id: str, input_tokens: int, output_tokens: int) -> dict:
    # ... existing code ...

    ttl_timestamp = int((datetime.utcnow() + timedelta(days=TTL_DAYS)).timestamp())

    self.table.update_item(
        Key={'user_id': user_id, 'month': current_month},
        UpdateExpression='''
            ADD input_tokens :input,
                output_tokens :output,
                total_tokens :total,
                request_count :one
            SET last_request_at = :now,
                token_limit = if_not_exists(token_limit, :default_limit),
                ttl = :ttl
        ''',
        ExpressionAttributeValues={
            ':input': input_tokens,
            ':output': output_tokens,
            ':total': input_tokens + output_tokens,
            ':one': 1,
            ':now': datetime.utcnow().isoformat() + 'Z',
            ':default_limit': self.default_token_limit,
            ':ttl': ttl_timestamp
        },
        ReturnValues='ALL_NEW'
    )
```

---

### 2.2 Adaptive Retry with Exponential Backoff

**Problem**: Under high load, writes might throttle without graceful handling.

**Solution**: Configure boto3 with adaptive retry mode:

```python
from botocore.config import Config

# Configure DynamoDB client with adaptive retries
dynamodb_config = Config(
    retries={
        'max_attempts': 5,
        'mode': 'adaptive'  # Automatically handles throttling
    },
    connect_timeout=5,
    read_timeout=10
)

dynamodb = boto3.resource('dynamodb', config=dynamodb_config)
```

**Manual retry for critical writes**:

```python
import time
import random

def record_usage_with_retry(
    self,
    user_id: str,
    input_tokens: int,
    output_tokens: int,
    max_retries: int = 3
) -> dict:
    """Record usage with exponential backoff retry."""

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return self._do_record_usage(user_id, input_tokens, output_tokens)

        except ClientError as e:
            error_code = e.response['Error']['Code']

            if error_code in ('ProvisionedThroughputExceededException',
                              'ThrottlingException'):
                last_exception = e

                if attempt < max_retries:
                    # Exponential backoff with jitter
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        f"Write throttled for {user_id}, "
                        f"retrying in {delay:.2f}s (attempt {attempt + 1})"
                    )
                    time.sleep(delay)
                    continue

            raise  # Re-raise non-throttling errors

    # All retries exhausted
    logger.error(f"Failed to record usage after {max_retries} retries")
    raise last_exception
```

---

### 2.3 Write Buffering with SQS

**Problem**: High burst traffic could overwhelm DynamoDB item-level throughput.

**Solution**: Buffer writes through SQS, aggregate before writing.

**Architecture**:

```
Request → Lambda Handler → SQS Queue → Aggregator Lambda → DynamoDB
                              ↓
                    (batch window: 60s or 100 messages)
```

**Terraform**:

```hcl
resource "aws_sqs_queue" "token_usage_buffer" {
  name                       = "${var.project_name}-${var.environment}-token-buffer"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 3600  # 1 hour

  tags = var.common_tags
}

resource "aws_lambda_event_source_mapping" "token_aggregator" {
  event_source_arn                   = aws_sqs_queue.token_usage_buffer.arn
  function_name                      = aws_lambda_function.token_aggregator.arn
  batch_size                         = 100
  maximum_batching_window_in_seconds = 60
}
```

**Producer** (in handler):

```python
import json

sqs = boto3.client('sqs')
TOKEN_BUFFER_QUEUE_URL = os.environ.get('TOKEN_BUFFER_QUEUE_URL')

def queue_token_usage(user_id: str, input_tokens: int, output_tokens: int) -> None:
    """Queue token usage for batch processing."""

    sqs.send_message(
        QueueUrl=TOKEN_BUFFER_QUEUE_URL,
        MessageBody=json.dumps({
            'user_id': user_id,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }),
        MessageGroupId=user_id,  # For FIFO queue ordering
        MessageDeduplicationId=f"{user_id}-{datetime.utcnow().timestamp()}"
    )
```

**Consumer** (aggregator Lambda):

```python
from collections import defaultdict

def lambda_handler(event: dict, context) -> dict:
    """
    Aggregate buffered token usage and write to DynamoDB.

    Processes SQS batch, aggregates by user_id, writes once per user.
    """

    # Aggregate by user_id
    user_totals = defaultdict(lambda: {'input': 0, 'output': 0, 'count': 0})

    for record in event.get('Records', []):
        try:
            data = json.loads(record['body'])
            user_id = data['user_id']
            user_totals[user_id]['input'] += data['input_tokens']
            user_totals[user_id]['output'] += data['output_tokens']
            user_totals[user_id]['count'] += 1
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Invalid message: {e}")
            continue

    # Write aggregated totals (one write per user)
    current_month = datetime.utcnow().strftime('%Y-%m')

    for user_id, totals in user_totals.items():
        try:
            token_tracker.record_usage(
                user_id,
                totals['input'],
                totals['output']
            )
            logger.info(
                f"Recorded {totals['count']} aggregated requests for {user_id}: "
                f"input={totals['input']}, output={totals['output']}"
            )
        except Exception as e:
            logger.error(f"Failed to record usage for {user_id}: {e}")
            # Message will return to queue for retry
            raise

    return {'processed': len(user_totals)}
```

**Trade-offs**:
- Pro: Reduces write frequency per user
- Pro: Handles burst traffic gracefully
- Con: Usage not immediately visible (up to 60s delay)
- Con: Adds complexity and SQS costs

---

### 2.4 Write Sharding for Extreme Scale

**Problem**: Single item per user/month limits write throughput for power users.

**Solution**: Distribute writes across shards, aggregate on read.

**Schema change**:

```
Old: user_id + month
New: user_id#shard{0-9} + month
```

**Write with sharding**:

```python
import random

NUM_SHARDS = 10

def record_usage_sharded(
    self,
    user_id: str,
    input_tokens: int,
    output_tokens: int
) -> None:
    """Record usage to random shard for write distribution."""

    shard = random.randint(0, NUM_SHARDS - 1)
    sharded_key = f"{user_id}#shard{shard}"

    self.table.update_item(
        Key={'user_id': sharded_key, 'month': self.get_current_month()},
        UpdateExpression='''
            ADD input_tokens :input,
                output_tokens :output,
                total_tokens :total,
                request_count :one
        ''',
        ExpressionAttributeValues={
            ':input': input_tokens,
            ':output': output_tokens,
            ':total': input_tokens + output_tokens,
            ':one': 1
        }
    )
```

**Read with aggregation**:

```python
def get_usage_sharded(self, user_id: str, month: str = None) -> dict:
    """Get aggregated usage across all shards."""

    target_month = month or self.get_current_month()

    # Query all shards in parallel
    totals = {
        'input_tokens': 0,
        'output_tokens': 0,
        'total_tokens': 0,
        'request_count': 0
    }

    for shard in range(NUM_SHARDS):
        sharded_key = f"{user_id}#shard{shard}"

        try:
            response = self.table.get_item(
                Key={'user_id': sharded_key, 'month': target_month}
            )
            item = response.get('Item', {})

            totals['input_tokens'] += int(item.get('input_tokens', 0))
            totals['output_tokens'] += int(item.get('output_tokens', 0))
            totals['total_tokens'] += int(item.get('total_tokens', 0))
            totals['request_count'] += int(item.get('request_count', 0))

        except ClientError:
            continue  # Shard doesn't exist yet

    return totals
```

**Trade-offs**:
- Pro: 10x write throughput per user
- Con: Reads require aggregation (10 queries)
- Con: More complex limit checking
- Recommendation: Only implement if you observe throttling in production

---

### 2.5 Global Secondary Index for Analytics

**Problem**: No efficient way to query usage patterns across users.

**Solution**: Add GSI for month-based queries.

**Terraform**:

```hcl
resource "aws_dynamodb_table" "token_usage" {
  # ... existing config ...

  # GSI for querying by month (admin analytics)
  global_secondary_index {
    name            = "month-usage-index"
    hash_key        = "month"
    range_key       = "total_tokens"
    projection_type = "ALL"

    # On-demand inherits from table
    # For provisioned, set read/write capacity
  }

  # Additional attribute for GSI
  attribute {
    name = "total_tokens"
    type = "N"
  }
}
```

**Query examples**:

```python
def get_top_users_by_month(self, month: str, limit: int = 10) -> list:
    """Get top token consumers for a month."""

    response = self.table.query(
        IndexName='month-usage-index',
        KeyConditionExpression='#month = :month',
        ExpressionAttributeNames={'#month': 'month'},
        ExpressionAttributeValues={':month': month},
        ScanIndexForward=False,  # Descending by total_tokens
        Limit=limit
    )

    return response.get('Items', [])


def get_users_near_limit(self, month: str, threshold_percent: int = 80) -> list:
    """Get users who have used >= threshold% of their limit."""

    response = self.table.query(
        IndexName='month-usage-index',
        KeyConditionExpression='#month = :month',
        FilterExpression='(total_tokens / token_limit) * 100 >= :threshold',
        ExpressionAttributeNames={'#month': 'month'},
        ExpressionAttributeValues={
            ':month': month,
            ':threshold': threshold_percent
        }
    )

    return response.get('Items', [])
```

---

### 2.6 CloudWatch Monitoring

**Problem**: No visibility into write patterns or throttling.

**Solution**: Add CloudWatch alarms and dashboard.

**Terraform**:

```hcl
# Throttling alarm
resource "aws_cloudwatch_metric_alarm" "token_table_write_throttles" {
  alarm_name          = "${var.project_name}-${var.environment}-token-write-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "WriteThrottledRequests"
  namespace           = "AWS/DynamoDB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Token usage table experiencing write throttling"

  dimensions = {
    TableName = aws_dynamodb_table.token_usage.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.common_tags
}

# High write capacity alarm
resource "aws_cloudwatch_metric_alarm" "token_table_high_writes" {
  alarm_name          = "${var.project_name}-${var.environment}-token-high-writes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "ConsumedWriteCapacityUnits"
  namespace           = "AWS/DynamoDB"
  period              = 300
  statistic           = "Sum"
  threshold           = 1000
  alarm_description   = "Token usage table write capacity unusually high"

  dimensions = {
    TableName = aws_dynamodb_table.token_usage.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]

  tags = var.common_tags
}

# Dashboard
resource "aws_cloudwatch_dashboard" "token_usage" {
  dashboard_name = "${var.project_name}-${var.environment}-token-usage"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Write Capacity"
          metrics = [
            ["AWS/DynamoDB", "ConsumedWriteCapacityUnits", "TableName", aws_dynamodb_table.token_usage.name]
          ]
          period = 60
          stat   = "Sum"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title   = "Throttled Requests"
          metrics = [
            ["AWS/DynamoDB", "WriteThrottledRequests", "TableName", aws_dynamodb_table.token_usage.name]
          ]
          period = 60
          stat   = "Sum"
        }
      }
    ]
  })
}
```

---

## Implementation Priority

| Improvement | Effort | Impact | Priority |
|-------------|--------|--------|----------|
| **1.1** Full usage reset | Low | High | P1 |
| **1.2** Tier sync on upgrade | Low | High | P1 |
| **2.1** Add TTL | Low | Medium | P1 |
| **2.2** Adaptive retry | Low | Medium | P1 |
| **2.6** CloudWatch monitoring | Low | High | P1 |
| **1.5** SNS notifications | Medium | Medium | P2 |
| **1.6** Admin API | Medium | High | P2 |
| **1.3** Bonus tokens | Medium | Medium | P2 |
| **2.5** Analytics GSI | Medium | Medium | P3 |
| **1.4** Rollover tokens | Medium | Low | P3 |
| **2.3** SQS buffering | High | Low* | P4 |
| **2.4** Write sharding | High | Low* | P4 |

*Low impact unless you observe throttling in production

---

## Next Steps

1. Implement P1 items (quick wins with high impact)
2. Add CloudWatch alarms to detect issues before users report them
3. Monitor production for 2-4 weeks
4. Based on metrics, decide if P4 optimizations are needed
