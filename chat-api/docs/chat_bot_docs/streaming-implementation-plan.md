# Streaming Implementation Plan: Fast Animation with AWS Bedrock

## Executive Summary

This document outlines the implementation plan for adding real-time streaming capabilities to the Buffett Chat API, providing a smooth, animated response experience similar to Claude or ChatGPT while maintaining the reliability of the current SQS-based architecture.

## Architecture Overview

**Hybrid Approach**: Keep SQS for reliability while adding parallel streaming for UX

```
User Input → WebSocket → Lambda Handler
                ├─→ SQS Queue → Processor (reliability/audit)
                └─→ Direct Streaming (immediate UX feedback)
```

## End-to-End Latency Analysis

### Current Architecture (No Streaming)
```
User sends message                     0ms
↓ WebSocket to API Gateway             20-30ms
↓ Lambda cold start (if needed)        200-500ms (warm: 5-10ms)
↓ SQS queue message                    10-20ms
↓ SQS polling delay                    100-200ms
↓ Lambda processor invocation          5-10ms
↓ Bedrock API call                     800-2000ms
↓ DynamoDB write                       10-20ms
↓ WebSocket response                   20-30ms
----------------------------------------
Total First Response:                  1165-2810ms (cold)
                                       965-2310ms (warm)
```

### New Streaming Architecture
```
User sends message                     0ms
↓ WebSocket to API Gateway             20-30ms
↓ Lambda cold start (if needed)        200-500ms (warm: 5-10ms)
├─→ SQS queue (parallel)               10-20ms (non-blocking)
└─→ Start Bedrock streaming
    ↓ First token from Bedrock         150-300ms
    ↓ WebSocket chunk delivery         20-30ms
----------------------------------------
Total First Token:                     390-860ms (cold)
                                       190-360ms (warm)

Subsequent tokens:                     10-30ms each
Full response completion:              2-4 seconds
```

## Implementation Plan with SQS Retained

### Phase 1: Backend Infrastructure (2-3 days)

#### A. Create Streaming Lambda Function (`stream_handler.py`)
```python
import json
import boto3
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Dict, Any

# Initialize clients
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')
bedrock_runtime = boto3.client('bedrock-runtime')
apigateway_client = boto3.client('apigatewaymanagementapi',
                                endpoint_url=os.environ['WEBSOCKET_API_ENDPOINT'])

messages_table = dynamodb.Table(os.environ['CHAT_MESSAGES_TABLE'])

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handles direct streaming while queuing to SQS
    """
    connection_id = event['requestContext']['connectionId']
    message = json.loads(event.get('body', '{}'))

    # Parallel execution
    with ThreadPoolExecutor(max_workers=2) as executor:
        # Queue to SQS (non-blocking)
        sqs_future = executor.submit(queue_to_sqs, message)

        # Stream immediately (blocking)
        stream_response(connection_id, message)

    return {'statusCode': 200}

def stream_response(connection_id: str, message: Dict[str, Any]) -> None:
    """
    Stream Bedrock response directly to WebSocket
    """
    # Mark message as being streamed to prevent duplicate processing
    messages_table.put_item(Item={
        'message_id': message['message_id'],
        'streaming_status': 'in_progress',
        'timestamp': datetime.utcnow().timestamp()
    })

    # Send streaming start indicator
    send_websocket_message(connection_id, {
        'action': 'stream_start',
        'message_id': message['message_id'],
        'timestamp': datetime.utcnow().isoformat()
    })

    # Call Bedrock with streaming
    stream = bedrock_runtime.invoke_model_with_response_stream(
        modelId='anthropic.claude-3-haiku-20240307-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "messages": [{"role": "user", "content": message['content']}],
            "temperature": 0.7,
            "system": "You are Warren Buffett providing investment wisdom."
        })
    )

    full_response = ""
    chunk_count = 0
    chunk_buffer = ""

    for event in stream.get('body', []):
        chunk = json.loads(event['chunk']['bytes'].decode('utf-8'))

        if chunk['type'] == 'content_block_delta':
            text_chunk = chunk['delta'].get('text', '')
            full_response += text_chunk
            chunk_buffer += text_chunk
            chunk_count += 1

            # Send chunk via WebSocket every 3-5 chunks or 50 characters
            if chunk_count % 3 == 0 or len(chunk_buffer) > 50:
                send_websocket_message(connection_id, {
                    'action': 'stream_chunk',
                    'message_id': message['message_id'],
                    'chunk': chunk_buffer,
                    'chunk_number': chunk_count
                })
                chunk_buffer = ""

    # Send any remaining buffer
    if chunk_buffer:
        send_websocket_message(connection_id, {
            'action': 'stream_chunk',
            'message_id': message['message_id'],
            'chunk': chunk_buffer,
            'chunk_number': chunk_count + 1
        })

    # Send stream end indicator
    send_websocket_message(connection_id, {
        'action': 'stream_end',
        'message_id': message['message_id'],
        'total_chunks': chunk_count,
        'timestamp': datetime.utcnow().isoformat()
    })

    # Store complete message
    store_complete_message(message['message_id'], full_response)

def send_websocket_message(connection_id: str, data: Dict[str, Any]) -> None:
    """
    Send message to WebSocket connection
    """
    try:
        apigateway_client.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(data)
        )
    except Exception as e:
        logger.error(f"Failed to send WebSocket message: {e}")

def queue_to_sqs(message: Dict[str, Any]) -> None:
    """
    Queue message to SQS for reliable processing
    """
    sqs.send_message(
        QueueUrl=os.environ['CHAT_PROCESSING_QUEUE_URL'],
        MessageBody=json.dumps(message),
        MessageAttributes={
            'streaming_attempted': {'StringValue': 'true', 'DataType': 'String'}
        }
    )

def store_complete_message(message_id: str, content: str) -> None:
    """
    Store the complete assistant response
    """
    messages_table.update_item(
        Key={'message_id': message_id},
        UpdateExpression='SET content = :content, streaming_status = :status',
        ExpressionAttributeValues={
            ':content': content,
            ':status': 'completed'
        }
    )
```

#### B. Modify SQS Processor (`chat_processor.py`)
```python
def process_chat_message(message_data: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Modified to check if already streamed
    """
    message_id = message_data['message_id']

    # Check if already processed via streaming
    existing = messages_table.get_item(
        Key={'message_id': message_id}
    ).get('Item')

    if existing and existing.get('streaming_status') == 'completed':
        logger.info(f"Message {message_id} already streamed, skipping")
        return {'success': True, 'skipped': True}

    # Continue with normal processing as fallback
    # This ensures reliability if streaming fails
    logger.info(f"Processing message {message_id} via SQS (streaming failed or not attempted)")

    # Your existing processing logic here
    # ...

    return {'success': True}
```

### Phase 2: WebSocket Route Configuration (1 day)

#### A. Add New Routes in API Gateway (Terraform)
```hcl
# In terraform/modules/api-gateway/main.tf

# Add streaming route
resource "aws_apigatewayv2_route" "websocket_stream_route" {
  api_id    = aws_apigatewayv2_api.websocket_api.id
  route_key = "streamMessage"
  target    = "integrations/${aws_apigatewayv2_integration.stream_integration.id}"

  authorization_type = "NONE"  # Already authenticated via $connect
}

# Add streaming integration
resource "aws_apigatewayv2_integration" "stream_integration" {
  api_id           = aws_apigatewayv2_api.websocket_api.id
  integration_type = "AWS_PROXY"

  integration_method     = "POST"
  integration_uri        = var.lambda_arns["stream_handler"]
  payload_format_version = "1.0"
}

# Lambda permission for streaming
resource "aws_lambda_permission" "websocket_stream_permission" {
  statement_id  = "AllowExecutionFromWebSocketStream"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_arns["stream_handler"]
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket_api.execution_arn}/*/*"
}
```

#### B. Lambda Function Definition (Terraform)
```hcl
# In terraform/modules/lambda/main.tf

# Add stream_handler to the lambda_configs
locals {
  lambda_configs = {
    # ... existing configs ...
    stream_handler = {
      handler     = "stream_handler.lambda_handler"
      timeout     = 60  # Longer timeout for streaming
      memory_size = 512
      description = "WebSocket streaming handler for real-time responses"
    }
  }
}
```

### Phase 3: Frontend Streaming UI (2-3 days)

#### A. Enhanced WebSocket Handler
```javascript
// In App.jsx - Update message handler
ws.onmessage = (evt) => {
  const data = JSON.parse(evt.data);

  if (data.action === 'stream_start') {
    // Show typing indicator immediately
    setMessages(prev => [...prev, {
      id: data.message_id,
      type: 'assistant',
      content: '',
      timestamp: nowIso(),
      isStreaming: true,
      streamStartTime: Date.now()
    }]);
  }

  else if (data.action === 'stream_chunk') {
    setMessages(prev => {
      const index = prev.findIndex(m => m.id === data.message_id);
      if (index >= 0) {
        const updated = [...prev];
        // Accumulate chunks with smooth animation
        updated[index] = {
          ...updated[index],
          content: updated[index].content + data.chunk,
          lastChunkTime: Date.now(),
          chunkCount: (updated[index].chunkCount || 0) + 1
        };
        return updated;
      }
      // Create message if it doesn't exist
      return [...prev, {
        id: data.message_id,
        type: 'assistant',
        content: data.chunk,
        timestamp: nowIso(),
        isStreaming: true
      }];
    });
  }

  else if (data.action === 'stream_end') {
    setMessages(prev => {
      const index = prev.findIndex(m => m.id === data.message_id);
      if (index >= 0) {
        const updated = [...prev];
        updated[index] = {
          ...updated[index],
          isStreaming: false,
          streamEndTime: Date.now(),
          totalChunks: data.total_chunks
        };
        // Calculate streaming duration for metrics
        const duration = updated[index].streamEndTime - updated[index].streamStartTime;
        console.log(`Streaming completed in ${duration}ms with ${data.total_chunks} chunks`);
        return updated;
      }
      return prev;
    });
  }
};

// Update send message function to use streaming
const doSend = () => {
  if (!input.trim() || isConnecting) return;

  const userMsg = {
    id: `user-${uid8()}`,
    type: "user",
    content: input.trim(),
    timestamp: nowIso()
  };

  setMessages(prev => [...prev, userMsg]);

  // Send via WebSocket with streaming action
  if (status === "connected" && socketRef.current) {
    socketRef.current.send(JSON.stringify({
      action: "streamMessage",  // Use new streaming route
      message: input.trim(),
      message_id: `msg-${uid8()}`,
      session_id: sessionId || `session-${uid8()}`,
      user_id: userId || userName
    }));
  }

  setInput("");
};
```

#### B. Animated Message Component
```javascript
// Create new component: StreamingMessage.jsx
import React, { useState, useEffect } from 'react';

const StreamingMessage = ({ message }) => {
  const [displayedContent, setDisplayedContent] = useState('');
  const [currentIndex, setCurrentIndex] = useState(0);

  useEffect(() => {
    // Smooth character reveal animation
    if (currentIndex < message.content.length) {
      const timer = setTimeout(() => {
        const chunkSize = message.isStreaming ? 2 : 5; // Faster when complete
        const nextIndex = Math.min(currentIndex + chunkSize, message.content.length);
        setDisplayedContent(message.content.substring(0, nextIndex));
        setCurrentIndex(nextIndex);
      }, 15); // 15ms per chunk for smooth animation

      return () => clearTimeout(timer);
    }
  }, [currentIndex, message.content, message.isStreaming]);

  return (
    <div className="message-bubble assistant-message">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center">
          <span className="text-white text-sm">WB</span>
        </div>
        <div className="flex-1">
          <div className="text-xs text-gray-500 mb-1">Warren Buffett</div>
          <div className="whitespace-pre-wrap text-gray-800">
            {displayedContent}
            {message.isStreaming && displayedContent.length >= message.content.length && (
              <span className="inline-block w-2 h-4 ml-1 bg-gray-400 animate-pulse" />
            )}
          </div>
          {message.isStreaming && displayedContent.length < message.content.length && (
            <div className="mt-2 text-xs text-gray-500 flex items-center gap-1">
              <div className="animate-spin h-3 w-3 border-2 border-gray-300 rounded-full border-t-gray-600" />
              Warren is thinking...
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StreamingMessage;
```

#### C. Update MessageBubble Component
```javascript
// In App.jsx - Update MessageBubble to use StreamingMessage
function MessageBubble({ msg }) {
  // For assistant messages that are streaming or recently streamed
  if (msg.type === 'assistant' && (msg.isStreaming || msg.streamEndTime)) {
    return <StreamingMessage message={msg} />;
  }

  // Existing message rendering for user and system messages
  if (msg.type === "system") {
    return (
      <div className="my-4 text-center text-xs text-gray-500">
        {msg.content}
      </div>
    );
  }

  const isUser = msg.type === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-4`}>
      <div className={`max-w-[70%] rounded-lg px-4 py-2 ${
        isUser ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-800"
      }`}>
        <div className="whitespace-pre-wrap">{msg.content}</div>
        <div className={`text-xs mt-1 ${isUser ? "text-indigo-200" : "text-gray-500"}`}>
          {prettyTime(msg.timestamp)}
        </div>
      </div>
    </div>
  );
}
```

### Phase 4: Performance Optimizations (1-2 days)

#### A. Lambda Optimization
```python
# In stream_handler.py

# Warm Lambda containers
# In terraform/modules/lambda/main.tf:
resource "aws_lambda_provisioned_concurrency_config" "stream_handler" {
  function_name                     = aws_lambda_function.functions["stream_handler"].function_name
  provisioned_concurrent_executions = var.environment == "prod" ? 2 : 1
  qualifier                        = aws_lambda_function.functions["stream_handler"].version
}

# Connection pooling in Lambda
from botocore.config import Config

config = Config(
    region_name='us-east-1',
    retries={
        'max_attempts': 2,
        'mode': 'adaptive'
    },
    max_pool_connections=10
)

bedrock_client = boto3.client('bedrock-runtime', config=config)

# Response caching for common questions
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def get_cached_context(question_hash):
    """
    Cache Pinecone retrievals for 5 minutes
    """
    # Check if we have a recent context for this question
    cache_key = f"context:{question_hash}"
    cached = cache_table.get_item(
        Key={'cache_key': cache_key}
    ).get('Item')

    if cached and cached['expires_at'] > time.time():
        return cached['context']

    return None

def get_question_hash(question):
    """
    Generate consistent hash for question caching
    """
    normalized = question.lower().strip()
    return hashlib.md5(normalized.encode()).hexdigest()
```

#### B. WebSocket Optimizations
```javascript
// In App.jsx - Add chunk buffering
const ChunkBuffer = {
  buffer: [],
  timer: null,

  add(chunk) {
    this.buffer.push(chunk);
    this.scheduleFlush();
  },

  scheduleFlush() {
    if (this.timer) return;

    this.timer = setTimeout(() => {
      this.flush();
    }, 50); // Flush every 50ms
  },

  flush() {
    if (this.buffer.length === 0) return;

    const combined = this.buffer.join('');
    this.buffer = [];
    this.timer = null;

    // Update message with combined chunks
    updateMessageContent(combined);
  }
};

// Implement backpressure handling
const StreamingController = {
  maxQueueSize: 10,
  queue: [],
  processing: false,

  async addChunk(chunk) {
    if (this.queue.length >= this.maxQueueSize) {
      // Drop oldest chunk if queue is full
      this.queue.shift();
    }

    this.queue.push(chunk);
    this.process();
  },

  async process() {
    if (this.processing || this.queue.length === 0) return;

    this.processing = true;

    while (this.queue.length > 0) {
      const chunk = this.queue.shift();
      await this.renderChunk(chunk);
      await this.delay(10); // Control rendering speed
    }

    this.processing = false;
  },

  renderChunk(chunk) {
    // Update UI with chunk
    ChunkBuffer.add(chunk);
  },

  delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
};
```

### Phase 5: Error Handling & Monitoring (1 day)

#### A. Fallback Mechanism
```python
# In stream_handler.py

def stream_with_fallback(connection_id: str, message: Dict[str, Any]) -> None:
    """
    Stream with automatic fallback to SQS
    """
    try:
        # Try streaming first
        stream_response(connection_id, message)

        # Log success metric
        cloudwatch.put_metric_data(
            Namespace='BuffettChat/Streaming',
            MetricData=[{
                'MetricName': 'StreamingSuccess',
                'Value': 1,
                'Unit': 'Count'
            }]
        )

    except Exception as e:
        logger.error(f"Streaming failed for message {message['message_id']}: {e}")

        # Mark for SQS processing
        messages_table.update_item(
            Key={'message_id': message['message_id']},
            UpdateExpression='SET streaming_status = :status, error = :error',
            ExpressionAttributeValues={
                ':status': 'failed',
                ':error': str(e)
            }
        )

        # Send error notification to WebSocket
        send_websocket_message(connection_id, {
            'action': 'stream_error',
            'message_id': message['message_id'],
            'error': 'Streaming failed, processing via queue',
            'fallback': True
        })

        # Log failure metric
        cloudwatch.put_metric_data(
            Namespace='BuffettChat/Streaming',
            MetricData=[{
                'MetricName': 'StreamingFailure',
                'Value': 1,
                'Unit': 'Count'
            }]
        )

        # SQS will handle it
        raise

# Connection recovery
def handle_connection_failure(connection_id: str, message_id: str):
    """
    Handle WebSocket connection failures during streaming
    """
    # Mark message for reprocessing
    messages_table.update_item(
        Key={'message_id': message_id},
        UpdateExpression='SET connection_lost = :true',
        ExpressionAttributeValues={':true': True}
    )

    # The SQS processor will pick it up and complete it
```

#### B. CloudWatch Metrics and Alarms
```python
# Custom metrics for monitoring
def publish_streaming_metrics(metrics: Dict[str, Any]):
    """
    Publish streaming performance metrics
    """
    cloudwatch.put_metric_data(
        Namespace='BuffettChat/Streaming',
        MetricData=[
            {
                'MetricName': 'FirstTokenLatency',
                'Value': metrics['first_token_ms'],
                'Unit': 'Milliseconds',
                'Dimensions': [
                    {'Name': 'Environment', 'Value': os.environ['ENVIRONMENT']}
                ]
            },
            {
                'MetricName': 'TotalStreamingTime',
                'Value': metrics['total_time_ms'],
                'Unit': 'Milliseconds'
            },
            {
                'MetricName': 'ChunksPerMessage',
                'Value': metrics['chunk_count'],
                'Unit': 'Count'
            },
            {
                'MetricName': 'TokensPerSecond',
                'Value': metrics['tokens_per_second'],
                'Unit': 'Count/Second'
            }
        ]
    )

# CloudWatch Alarms (Terraform)
resource "aws_cloudwatch_metric_alarm" "high_streaming_latency" {
  alarm_name          = "${var.project_name}-${var.environment}-high-streaming-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name        = "FirstTokenLatency"
  namespace          = "BuffettChat/Streaming"
  period             = "300"
  statistic          = "Average"
  threshold          = "1000"  # Alert if first token takes > 1 second
  alarm_description  = "Alert when streaming latency is too high"
  alarm_actions      = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "streaming_failures" {
  alarm_name          = "${var.project_name}-${var.environment}-streaming-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "1"
  metric_name        = "StreamingFailure"
  namespace          = "BuffettChat/Streaming"
  period             = "300"
  statistic          = "Sum"
  threshold          = "10"  # Alert if > 10 failures in 5 minutes
  alarm_description  = "Alert on streaming failures"
  alarm_actions      = [aws_sns_topic.alerts.arn]
}
```

## Configuration

### Environment Variables
```bash
# Lambda environment variables
ENABLE_STREAMING=true
STREAMING_CHUNK_SIZE=50          # Characters per WebSocket message
STREAMING_BUFFER_TIME=100        # Ms to buffer before sending
MAX_CONCURRENT_STREAMS=10        # Limit concurrent streaming sessions
FALLBACK_TO_SQS=true             # Use SQS if streaming fails
STREAMING_TIMEOUT=30000          # 30 second timeout
CACHE_CONTEXT_TTL=300            # Cache context for 5 minutes

# Frontend configuration (.env)
VITE_ENABLE_STREAMING=true
VITE_ANIMATION_SPEED=15         # Ms between character reveals
VITE_CHUNK_BUFFER_SIZE=3        # Buffer chunks before rendering
VITE_SHOW_STREAMING_METRICS=true # Show latency metrics in dev mode
```

## Expected Performance Metrics

### Latency Improvements
| Metric | Current | With Streaming | Improvement |
|--------|---------|----------------|-------------|
| First Token (TTFT) - Cold | 1165-2810ms | 390-860ms | 67% faster |
| First Token (TTFT) - Warm | 965-2310ms | 190-360ms | 80% faster |
| Perceived Responsiveness | 2-3 seconds | <0.5 seconds | 75% improvement |
| Full Response Time | 2-4 seconds | 2-4 seconds | Same (but feels faster) |

### Reliability Metrics
- **Message delivery**: 99.99% (SQS backup ensures no messages lost)
- **Streaming success rate**: 95%+ expected
- **Fallback activation**: <5% of messages
- **Connection recovery**: Automatic within 1-2 seconds

### Cost Analysis
| Component | Additional Cost | Per 1000 Messages |
|-----------|----------------|-------------------|
| Lambda invocations | +1 per message | $0.20 |
| Lambda duration | +2 seconds average | $0.10 |
| WebSocket API calls | +15 per message | $0.15 |
| CloudWatch logs | +50% more logs | $0.05 |
| **Total Additional Cost** | | **$0.50** |

## Implementation Timeline

### Week 1
- **Day 1-2**: Backend streaming infrastructure
  - Create stream_handler Lambda
  - Implement Bedrock streaming integration
  - Add parallel SQS queuing

- **Day 3**: WebSocket route configuration
  - Update API Gateway routes
  - Configure Lambda permissions
  - Test WebSocket streaming

- **Day 4-5**: Frontend streaming UI
  - Implement chunk handling
  - Create animated components
  - Add streaming indicators

### Week 2
- **Day 1-2**: Integration testing
  - End-to-end streaming tests
  - Fallback scenario testing
  - Load testing

- **Day 3**: Performance optimizations
  - Lambda provisioned concurrency
  - Connection pooling
  - Response caching

- **Day 4**: Error handling & monitoring
  - Implement fallback mechanisms
  - Set up CloudWatch metrics
  - Configure alarms

- **Day 5**: Production deployment
  - Deploy to staging
  - User acceptance testing
  - Production rollout

**Total: 10 working days**

## Risk Mitigation

### Technical Risks

1. **Streaming Failures**
   - **Risk**: WebSocket disconnection during streaming
   - **Mitigation**: SQS ensures 100% message processing
   - **Recovery**: Automatic reconnection with message replay

2. **Rate Limiting**
   - **Risk**: Too many concurrent streams
   - **Mitigation**: Lambda concurrent execution limits
   - **Fallback**: Queue excess requests to SQS

3. **Cost Overrun**
   - **Risk**: Excessive Lambda invocations
   - **Mitigation**: Set billing alarms at 150% of expected
   - **Control**: Implement per-user rate limiting

4. **Latency Spikes**
   - **Risk**: Cold starts impact user experience
   - **Mitigation**: Provisioned concurrency for streaming Lambda
   - **Monitoring**: P99 latency alarms

### Operational Risks

1. **Browser Compatibility**
   - **Risk**: WebSocket issues on older browsers
   - **Mitigation**: Fallback to polling for unsupported browsers
   - **Testing**: Cross-browser testing suite

2. **Network Interruptions**
   - **Risk**: Mobile users with unstable connections
   - **Mitigation**: Aggressive reconnection strategy
   - **UX**: Show connection status indicator

## Testing Strategy

### Unit Tests
```python
# test_stream_handler.py
def test_streaming_chunks():
    """Test that chunks are sent correctly"""
    mock_connection = Mock()
    chunks = stream_text_in_chunks("Hello, world!", chunk_size=5)

    assert len(chunks) == 3  # "Hello", ", wor", "ld!"
    assert "".join(chunks) == "Hello, world!"

def test_fallback_on_error():
    """Test SQS fallback when streaming fails"""
    with patch('bedrock_runtime.invoke_model_with_response_stream') as mock:
        mock.side_effect = Exception("Stream failed")

        result = stream_with_fallback(connection_id, message)

        # Verify message was queued to SQS
        assert sqs_mock.send_message.called
```

### Integration Tests
```javascript
// test/streaming.test.js
describe('Streaming Messages', () => {
  it('should display chunks as they arrive', async () => {
    const ws = new MockWebSocket();

    // Send chunks
    ws.emit('message', {
      action: 'stream_chunk',
      chunk: 'Hello',
      message_id: 'test-1'
    });

    await waitFor(() => {
      expect(screen.getByText(/Hello/)).toBeInTheDocument();
    });

    ws.emit('message', {
      action: 'stream_chunk',
      chunk: ', world!',
      message_id: 'test-1'
    });

    await waitFor(() => {
      expect(screen.getByText(/Hello, world!/)).toBeInTheDocument();
    });
  });
});
```

### Load Testing
```bash
# Artillery load test configuration
config:
  target: "wss://api.example.com/staging"
  phases:
    - duration: 60
      arrivalRate: 10  # 10 new users per second
scenarios:
  - name: "Streaming Chat"
    engine: ws
    flow:
      - send: '{"action": "streamMessage", "message": "Tell me about investing"}'
      - think: 5
      - send: '{"action": "streamMessage", "message": "What about bonds?"}'
```

## Rollout Strategy

### Phase 1: Internal Testing (Week 1)
- Deploy to dev environment
- Internal team testing
- Performance baseline

### Phase 2: Beta Testing (Week 2)
- 10% of staging traffic
- Monitor metrics closely
- Gather user feedback

### Phase 3: Gradual Rollout (Week 3)
- 25% → 50% → 100% of traffic
- Monitor error rates
- Ready to rollback if needed

### Phase 4: Production (Week 4)
- Full production deployment
- Monitor for 48 hours
- Document lessons learned

## Success Metrics

### KPIs to Track
1. **First Token Latency**: Target < 400ms (p50), < 800ms (p99)
2. **Streaming Success Rate**: Target > 95%
3. **User Engagement**: +20% message completion rate
4. **Error Rate**: < 1% streaming failures
5. **Cost per Message**: < $0.001 increase

### User Experience Metrics
1. **Time to First Byte**: 70% reduction
2. **Perceived Speed**: User surveys showing improvement
3. **Session Duration**: +15% average session length
4. **User Satisfaction**: NPS score improvement

## Conclusion

This streaming implementation will significantly improve the user experience by providing immediate visual feedback and smooth animation of responses. By maintaining the SQS queue architecture, we ensure reliability while adding the engaging real-time features users expect from modern AI chat interfaces.

The hybrid approach balances performance with reliability, ensuring that no messages are lost while delivering a responsive, engaging user experience comparable to leading AI chat platforms.