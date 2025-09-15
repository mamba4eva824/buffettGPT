# Latency Measurement Implementation Guide
## Buffett Chat API Infrastructure

This guide provides a comprehensive implementation for measuring latency across your buffett_chat_api infrastructure with both Chrome console logging and local file logging capabilities.

## Architecture Overview

Your infrastructure includes:
- **Frontend**: React app (Vite) with WebSocket and REST API communication
- **Backend**: AWS Lambda functions handling HTTP and WebSocket connections
- **Services**: DynamoDB, SQS, Bedrock Agent, API Gateway

## 1. Frontend Latency Measurement

### Chrome Console Logging Setup

Create a new file `frontend/src/utils/latencyTracker.js`:

```javascript
// Latency tracking utility for buffett_chat_api
class LatencyTracker {
  constructor(options = {}) {
    this.isEnabled = options.enabled ?? true;
    this.logToConsole = options.logToConsole ?? true;
    this.logToLocal = options.logToLocal ?? true;
    this.metrics = new Map();
    this.sessionMetrics = [];
    
    // Color coding for different latency ranges
    this.colors = {
      excellent: '#10B981', // < 100ms
      good: '#F59E0B',      // 100-500ms
      poor: '#EF4444',      // 500ms+
      info: '#3B82F6'
    };
  }

  // Start tracking a request
  startTracking(requestId, type, details = {}) {
    if (!this.isEnabled) return;
    
    const timestamp = performance.now();
    this.metrics.set(requestId, {
      id: requestId,
      type,
      startTime: timestamp,
      details,
      startTimestamp: new Date().toISOString()
    });

    if (this.logToConsole) {
      console.log(
        `%c🚀 [${type}] Request Started: ${requestId}`,
        `color: ${this.colors.info}; font-weight: bold;`,
        details
      );
    }
  }

  // End tracking and calculate latency
  endTracking(requestId, responseDetails = {}) {
    if (!this.isEnabled) return;
    
    const endTime = performance.now();
    const metric = this.metrics.get(requestId);
    
    if (!metric) {
      console.warn(`⚠️ No tracking found for request: ${requestId}`);
      return;
    }

    const latency = endTime - metric.startTime;
    const result = {
      ...metric,
      endTime,
      latency: Math.round(latency),
      endTimestamp: new Date().toISOString(),
      responseDetails
    };

    // Store in session metrics
    this.sessionMetrics.push(result);
    this.metrics.delete(requestId);

    // Log to console with color coding
    if (this.logToConsole) {
      const color = latency < 100 ? this.colors.excellent : 
                   latency < 500 ? this.colors.good : this.colors.poor;
      
      console.log(
        `%c✅ [${metric.type}] Request Completed: ${requestId}`,
        `color: ${color}; font-weight: bold;`,
        {
          latency: `${result.latency}ms`,
          details: metric.details,
          response: responseDetails
        }
      );
    }

    // Log to local storage if enabled
    if (this.logToLocal) {
      this.saveToLocalStorage(result);
    }

    return result;
  }

  // WebSocket specific tracking
  trackWebSocketMessage(messageContent) {
    const requestId = `ws_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.startTracking(requestId, 'WebSocket Message', { content: messageContent.substring(0, 100) });
    return requestId;
  }

  // REST API specific tracking
  trackRestRequest(url, method = 'GET', payload = null) {
    const requestId = `rest_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.startTracking(requestId, 'REST API', { url, method, hasPayload: !!payload });
    return requestId;
  }

  // Bedrock/AI response tracking
  trackAIResponse(sessionId, messageContent) {
    const requestId = `ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    this.startTracking(requestId, 'AI Response', { 
      sessionId: sessionId?.substring(0, 8), 
      messageLength: messageContent?.length 
    });
    return requestId;
  }

  // Save metrics to localStorage
  saveToLocalStorage(metric) {
    try {
      const key = `latency_logs_${new Date().toISOString().split('T')[0]}`;
      const existing = JSON.parse(localStorage.getItem(key) || '[]');
      existing.push(metric);
      
      // Keep only last 1000 entries per day
      if (existing.length > 1000) {
        existing.splice(0, existing.length - 1000);
      }
      
      localStorage.setItem(key, JSON.stringify(existing));
    } catch (error) {
      console.warn('Failed to save latency metric to localStorage:', error);
    }
  }

  // Get performance summary
  getPerformanceSummary(timeRange = 'session') {
    const metrics = timeRange === 'session' ? this.sessionMetrics : this.getAllStoredMetrics();
    
    if (metrics.length === 0) {
      return { message: 'No metrics available' };
    }

    const latencies = metrics.map(m => m.latency);
    const types = [...new Set(metrics.map(m => m.type))];
    
    const summary = {
      totalRequests: metrics.length,
      avgLatency: Math.round(latencies.reduce((a, b) => a + b, 0) / latencies.length),
      minLatency: Math.min(...latencies),
      maxLatency: Math.max(...latencies),
      medianLatency: this.calculateMedian(latencies),
      requestTypes: types,
      timeRange,
      generatedAt: new Date().toISOString()
    };

    // Performance grade
    if (summary.avgLatency < 100) summary.grade = 'Excellent';
    else if (summary.avgLatency < 300) summary.grade = 'Good';
    else if (summary.avgLatency < 800) summary.grade = 'Fair';
    else summary.grade = 'Poor';

    return summary;
  }

  calculateMedian(arr) {
    const sorted = [...arr].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
  }

  // Export logs for external analysis
  exportLogs(format = 'json') {
    const allMetrics = this.getAllStoredMetrics();
    const summary = this.getPerformanceSummary();
    
    const exportData = {
      summary,
      metrics: allMetrics,
      exportedAt: new Date().toISOString(),
      userAgent: navigator.userAgent,
      sessionMetrics: this.sessionMetrics
    };

    if (format === 'csv') {
      return this.convertToCSV(allMetrics);
    }
    
    return JSON.stringify(exportData, null, 2);
  }

  getAllStoredMetrics() {
    const keys = Object.keys(localStorage).filter(key => key.startsWith('latency_logs_'));
    const allMetrics = [];
    
    keys.forEach(key => {
      try {
        const dayMetrics = JSON.parse(localStorage.getItem(key) || '[]');
        allMetrics.push(...dayMetrics);
      } catch (error) {
        console.warn(`Failed to parse metrics from ${key}:`, error);
      }
    });
    
    return allMetrics.sort((a, b) => new Date(a.startTimestamp) - new Date(b.startTimestamp));
  }

  convertToCSV(metrics) {
    if (metrics.length === 0) return 'No data available';
    
    const headers = ['id', 'type', 'latency', 'startTimestamp', 'endTimestamp'];
    const csvContent = [
      headers.join(','),
      ...metrics.map(m => [
        m.id,
        m.type,
        m.latency,
        m.startTimestamp,
        m.endTimestamp
      ].join(','))
    ].join('\n');
    
    return csvContent;
  }

  // Clean up old metrics (call periodically)
  cleanupOldMetrics(daysToKeep = 7) {
    const cutoffDate = new Date();
    cutoffDate.setDate(cutoffDate.getDate() - daysToKeep);
    
    const keys = Object.keys(localStorage).filter(key => key.startsWith('latency_logs_'));
    keys.forEach(key => {
      const dateStr = key.replace('latency_logs_', '');
      const logDate = new Date(dateStr);
      
      if (logDate < cutoffDate) {
        localStorage.removeItem(key);
        console.log(`🧹 Cleaned up old latency logs: ${dateStr}`);
      }
    });
  }
}

// Create global instance
window.latencyTracker = new LatencyTracker({
  enabled: true,
  logToConsole: import.meta.env.VITE_ENABLE_DEBUG_LOGS === "true",
  logToLocal: true
});

export default window.latencyTracker;
```

### Integration with Your App.jsx

Add the following imports and modifications to your existing `frontend/src/App.jsx`:

```javascript
// Add import at the top
import latencyTracker from './utils/latencyTracker';

// In useAwsWebSocket hook, modify the sendMessage function:
const sendMessage = useCallback((text) => {
  if (!text?.trim()) return;
  
  // Start tracking the message
  const trackingId = latencyTracker.trackWebSocketMessage(text.trim());
  
  if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
    console.log('🚀 Sending message:', text.trim());
    console.log('📡 WebSocket status:', socketRef.current?.readyState);
    console.log('🔗 Connection URL:', wsUrl);
  }
  
  // Add user message immediately with tracking ID
  const userMsg = { 
    id: `usr-${uid8()}`, 
    type: "user", 
    content: text.trim(), 
    timestamp: nowIso(),
    trackingId // Store tracking ID for later use
  };
  setMessages((m) => [ ...m, userMsg ]);
  
  // Send WebSocket message or use demo mode
  if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
    const msg = { action: "message", message: text.trim(), trackingId };
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('📤 Sending WebSocket message:', msg);
    }
    socketRef.current.send(JSON.stringify(msg));
  } else {
    // Demo mode with simulated latency
    setTimeout(() => {
      latencyTracker.endTracking(trackingId, { 
        type: 'demo', 
        messageLength: text.trim().length 
      });
      
      const aiMsg = {
        id: `ai-${uid8()}`,
        type: "assistant",
        content: `This is a demo response to: "${text.trim()}". Connect to your AWS WebSocket in Settings to get real Warren Buffett AI responses!`,
        timestamp: nowIso(),
        meta: { processingTime: 1500 }
      };
      setMessages((m) => [ ...m, aiMsg ]);
    }, 1500);
  }
}, [wsUrl]);

// In the WebSocket onmessage handler, add tracking completion:
ws.onmessage = (evt) => {
  try {
    const data = JSON.parse(evt.data || "{}");
    if (ENV_CONFIG.ENABLE_DEBUG_LOGS) {
      console.log('📨 Received WebSocket message:', data);
    }
    
    // Handle different message types and complete tracking
    if (data.type === "chatResponse" || data.action === "message_response") {
      // Find the message with trackingId and complete tracking
      const messageContent = data.message || data.content || "";
      const processingTime = data.processing_time_ms || data.processing_time;
      
      // Complete latency tracking if trackingId is available
      if (data.trackingId) {
        latencyTracker.endTracking(data.trackingId, {
          responseLength: messageContent.length,
          processingTime,
          serverLatency: processingTime
        });
      }
      
      // Rest of your existing message handling code...
    }
  } catch (e) { /* ignore */ }
};
```

### REST API Tracking

Update your `fetchHistory` function in `App.jsx`:

```javascript
async function fetchHistory(restBaseUrl, sessionId, limit = 60) {
  const trackingId = latencyTracker.trackRestRequest(
    `${restBaseUrl}/api/v1/chat/history/${sessionId}`, 
    'GET'
  );
  
  try {
    const baseUrl = restBaseUrl.replace(/\/$/, "");
    const url = `${baseUrl}/api/v1/chat/history/${encodeURIComponent(sessionId)}?limit=${limit}`;
    
    console.log('Fetching history from:', url);
    
    const res = await fetch(url, { 
      method: "GET", 
      headers: { 
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*"
      } 
    });
    
    if (!res.ok) {
      const errorText = await res.text();
      latencyTracker.endTracking(trackingId, { 
        error: true, 
        status: res.status, 
        errorText 
      });
      throw new Error(`History fetch failed (${res.status}): ${errorText}`);
    }
    
    const data = await res.json();
    latencyTracker.endTracking(trackingId, { 
      success: true, 
      messageCount: data.messages?.length || 0,
      status: res.status
    });
    
    return data;
  } catch (error) {
    latencyTracker.endTracking(trackingId, { error: true, errorMessage: error.message });
    throw error;
  }
}
```

### Frontend Performance Dashboard

Add this component to your `App.jsx` after your MessageBubble component:

```javascript
function PerformanceDashboard({ isOpen, onClose }) {
  const [summary, setSummary] = useState(null);
  const [exportData, setExportData] = useState('');
  
  useEffect(() => {
    if (isOpen) {
      const stats = latencyTracker.getPerformanceSummary();
      setSummary(stats);
    }
  }, [isOpen]);
  
  const handleExport = (format) => {
    const data = latencyTracker.exportLogs(format);
    setExportData(data);
    
    // Download file
    const blob = new Blob([data], { 
      type: format === 'csv' ? 'text/csv' : 'application/json' 
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `latency-report-${new Date().toISOString().split('T')[0]}.${format}`;
    link.click();
    URL.revokeObjectURL(url);
  };
  
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm" onClick={onClose}>
      <div className="absolute right-0 top-0 h-full w-full max-w-2xl overflow-y-auto bg-white shadow-xl" onClick={(e)=>e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="text-lg font-semibold">Performance Dashboard</div>
          <button onClick={onClose} className="rounded-md border border-slate-200 px-3 py-1 text-sm hover:bg-slate-50">Close</button>
        </div>
        
        <div className="p-6 space-y-6">
          {summary && summary.totalRequests ? (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-2xl font-bold text-slate-900">{summary.avgLatency}ms</div>
                  <div className="text-sm text-slate-600">Average Latency</div>
                  <div className={`text-xs font-medium ${
                    summary.grade === 'Excellent' ? 'text-green-600' :
                    summary.grade === 'Good' ? 'text-yellow-600' : 'text-red-600'
                  }`}>{summary.grade}</div>
                </div>
                
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-2xl font-bold text-slate-900">{summary.totalRequests}</div>
                  <div className="text-sm text-slate-600">Total Requests</div>
                </div>
                
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-2xl font-bold text-slate-900">{summary.minLatency}ms</div>
                  <div className="text-sm text-slate-600">Fastest Response</div>
                </div>
                
                <div className="bg-slate-50 rounded-lg p-4">
                  <div className="text-2xl font-bold text-slate-900">{summary.maxLatency}ms</div>
                  <div className="text-sm text-slate-600">Slowest Response</div>
                </div>
              </div>
              
              <div className="bg-slate-50 rounded-lg p-4">
                <div className="text-sm font-medium text-slate-600 mb-2">Request Types</div>
                <div className="flex flex-wrap gap-2">
                  {summary.requestTypes.map(type => (
                    <span key={type} className="bg-indigo-100 text-indigo-700 px-2 py-1 rounded text-xs">
                      {type}
                    </span>
                  ))}
                </div>
              </div>
              
              <div className="flex gap-3">
                <button 
                  onClick={() => handleExport('json')} 
                  className="bg-indigo-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700"
                >
                  Export JSON
                </button>
                <button 
                  onClick={() => handleExport('csv')} 
                  className="bg-slate-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-slate-700"
                >
                  Export CSV
                </button>
                <button 
                  onClick={() => latencyTracker.cleanupOldMetrics(7)} 
                  className="bg-amber-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-amber-700"
                >
                  Cleanup Old Logs
                </button>
              </div>
            </>
          ) : (
            <div className="text-center py-12 text-slate-500">
              No performance data available yet. Start using the app to see metrics.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// In your main App component, add state for the dashboard
const [performanceDashboardOpen, setPerformanceDashboardOpen] = useState(false);

// Add a button to open the dashboard in your UI (in the header area)
<button 
  onClick={() => setPerformanceDashboardOpen(true)} 
  className="rounded-xl border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50"
  title="Performance Dashboard"
>
  📊 Performance
</button>

// Add the dashboard component before the closing div of your App
<PerformanceDashboard 
  isOpen={performanceDashboardOpen} 
  onClose={() => setPerformanceDashboardOpen(false)} 
/>
```

## 2. Backend Latency Measurement & Local File Logging

### Lambda Function Latency Tracker

Create `chat-api/lambda-functions/latency_logger.py`:

```python
import json
import time
import os
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from decimal import Decimal
import uuid
import boto3

# Configure logging
logger = logging.getLogger(__name__)

class LatencyLogger:
    """
    Comprehensive latency tracking for buffett_chat_api Lambda functions
    Logs to CloudWatch and optionally to local files in Lambda tmp directory
    """
    
    def __init__(self, function_name: str = None):
        self.function_name = function_name or os.environ.get('AWS_LAMBDA_FUNCTION_NAME', 'unknown')
        self.environment = os.environ.get('ENVIRONMENT', 'dev')
        self.project_name = os.environ.get('PROJECT_NAME', 'buffett-chat-api')
        self.enable_local_logging = os.environ.get('ENABLE_LOCAL_LATENCY_LOGS', 'true').lower() == 'true'
        self.enable_detailed_logging = os.environ.get('ENABLE_DETAILED_LATENCY_LOGS', 'false').lower() == 'true'
        
        # CloudWatch custom metrics client
        self.cloudwatch = boto3.client('cloudwatch')
        
        # Active tracking dictionary
        self.active_tracks = {}
        
    def start_tracking(self, request_id: str, operation_type: str, details: Dict[str, Any] = None) -> str:
        """Start tracking a request/operation"""
        tracking_id = f"{operation_type}_{request_id}_{int(time.time() * 1000)}"
        
        track_data = {
            'tracking_id': tracking_id,
            'request_id': request_id,
            'operation_type': operation_type,
            'function_name': self.function_name,
            'start_time': time.time(),
            'start_timestamp': datetime.now(timezone.utc).isoformat(),
            'details': details or {}
        }
        
        self.active_tracks[tracking_id] = track_data
        
        if self.enable_detailed_logging:
            logger.info(f"🚀 Started tracking {operation_type}: {tracking_id}", extra={
                'tracking_id': tracking_id,
                'operation_type': operation_type,
                'details': details
            })
        
        return tracking_id
    
    def end_tracking(self, tracking_id: str, response_details: Dict[str, Any] = None, success: bool = True) -> Dict[str, Any]:
        """End tracking and calculate latency"""
        if tracking_id not in self.active_tracks:
            logger.warning(f"⚠️ No active tracking found for: {tracking_id}")
            return {}
        
        track_data = self.active_tracks.pop(tracking_id)
        end_time = time.time()
        latency_ms = round((end_time - track_data['start_time']) * 1000, 2)
        
        # Build comprehensive result
        result = {
            **track_data,
            'end_time': end_time,
            'end_timestamp': datetime.now(timezone.utc).isoformat(),
            'latency_ms': latency_ms,
            'success': success,
            'response_details': response_details or {}
        }
        
        # Log to CloudWatch
        self._log_to_cloudwatch(result)
        
        # Log to local file if enabled
        if self.enable_local_logging:
            self._log_to_local_file(result)
        
        # Log to application logger
        status_emoji = "✅" if success else "❌"
        logger.info(f"{status_emoji} Completed {track_data['operation_type']}: {latency_ms}ms", extra={
            'tracking_id': tracking_id,
            'latency_ms': latency_ms,
            'success': success,
            'operation_type': track_data['operation_type']
        })
        
        return result
    
    def track_external_service(self, service_name: str, request_id: str, details: Dict[str, Any] = None):
        """Context manager for tracking external service calls"""
        return ExternalServiceTracker(self, service_name, request_id, details)
    
    def track_database_operation(self, operation: str, table_name: str, request_id: str, details: Dict[str, Any] = None):
        """Track DynamoDB operations"""
        tracking_details = {
            'table_name': table_name,
            'operation': operation,
            **(details or {})
        }
        return self.start_tracking(request_id, f"DynamoDB_{operation}", tracking_details)
    
    def track_bedrock_call(self, agent_id: str, request_id: str, message_length: int = 0):
        """Track Bedrock agent calls"""
        return self.start_tracking(request_id, "Bedrock_Agent", {
            'agent_id': agent_id,
            'message_length': message_length
        })
    
    def track_sqs_operation(self, queue_name: str, operation: str, request_id: str, details: Dict[str, Any] = None):
        """Track SQS operations"""
        tracking_details = {
            'queue_name': queue_name,
            'operation': operation,
            **(details or {})
        }
        return self.start_tracking(request_id, f"SQS_{operation}", tracking_details)
    
    def _log_to_cloudwatch(self, result: Dict[str, Any]):
        """Send custom metrics to CloudWatch"""
        try:
            # Send latency metric
            self.cloudwatch.put_metric_data(
                Namespace=f"{self.project_name}/Latency",
                MetricData=[
                    {
                        'MetricName': 'RequestLatency',
                        'Dimensions': [
                            {'Name': 'FunctionName', 'Value': self.function_name},
                            {'Name': 'OperationType', 'Value': result['operation_type']},
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Success', 'Value': str(result['success'])}
                        ],
                        'Value': result['latency_ms'],
                        'Unit': 'Milliseconds',
                        'Timestamp': datetime.now(timezone.utc)
                    }
                ]
            )
            
            # Send count metric
            self.cloudwatch.put_metric_data(
                Namespace=f"{self.project_name}/RequestCount",
                MetricData=[
                    {
                        'MetricName': 'RequestCount',
                        'Dimensions': [
                            {'Name': 'FunctionName', 'Value': self.function_name},
                            {'Name': 'OperationType', 'Value': result['operation_type']},
                            {'Name': 'Environment', 'Value': self.environment},
                            {'Name': 'Success', 'Value': str(result['success'])}
                        ],
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': datetime.now(timezone.utc)
                    }
                ]
            )
            
        except Exception as e:
            logger.warning(f"Failed to send metrics to CloudWatch: {str(e)}")
    
    def _log_to_local_file(self, result: Dict[str, Any]):
        """Log to local file in Lambda tmp directory"""
        try:
            log_dir = "/tmp/latency_logs"
            os.makedirs(log_dir, exist_ok=True)
            
            # Use date-based filename
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            log_file = f"{log_dir}/latency_{today}_{self.function_name}.jsonl"
            
            # Prepare log entry
            log_entry = {
                'timestamp': result['start_timestamp'],
                'tracking_id': result['tracking_id'],
                'function_name': self.function_name,
                'operation_type': result['operation_type'],
                'latency_ms': result['latency_ms'],
                'success': result['success'],
                'request_id': result.get('request_id'),
                'details': result.get('details', {}),
                'response_details': result.get('response_details', {}),
                'environment': self.environment
            }
            
            # Append to file
            with open(log_file, 'a') as f:
                f.write(json.dumps(log_entry, default=str) + '\n')
                
        except Exception as e:
            logger.warning(f"Failed to write to local log file: {str(e)}")
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics from local log files"""
        try:
            log_dir = "/tmp/latency_logs"
            if not os.path.exists(log_dir):
                return {'message': 'No local logs found'}
            
            all_metrics = []
            for filename in os.listdir(log_dir):
                if filename.endswith('.jsonl'):
                    file_path = os.path.join(log_dir, filename)
                    with open(file_path, 'r') as f:
                        for line in f:
                            try:
                                metric = json.loads(line.strip())
                                all_metrics.append(metric)
                            except:
                                continue
            
            if not all_metrics:
                return {'message': 'No metrics found in log files'}
            
            latencies = [m['latency_ms'] for m in all_metrics if 'latency_ms' in m]
            if not latencies:
                return {'message': 'No latency data found'}
            
            return {
                'total_requests': len(all_metrics),
                'avg_latency_ms': round(sum(latencies) / len(latencies), 2),
                'min_latency_ms': min(latencies),
                'max_latency_ms': max(latencies),
                'success_rate': len([m for m in all_metrics if m.get('success', False)]) / len(all_metrics),
                'operation_types': list(set(m.get('operation_type', 'unknown') for m in all_metrics)),
                'generated_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate summary stats: {str(e)}")
            return {'error': str(e)}

class ExternalServiceTracker:
    """Context manager for tracking external service calls"""
    
    def __init__(self, logger: LatencyLogger, service_name: str, request_id: str, details: Dict[str, Any] = None):
        self.logger = logger
        self.service_name = service_name
        self.request_id = request_id
        self.details = details or {}
        self.tracking_id = None
    
    def __enter__(self):
        self.tracking_id = self.logger.start_tracking(
            self.request_id, 
            f"External_{self.service_name}", 
            self.details
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        success = exc_type is None
        response_details = {}
        
        if exc_type:
            response_details = {
                'error': str(exc_val),
                'error_type': exc_type.__name__
            }
        
        self.logger.end_tracking(self.tracking_id, response_details, success)
        return False  # Don't suppress exceptions

# Create global instance
latency_logger = LatencyLogger()
```

### Integration with Lambda Functions

Update your `chat-api/lambda-functions/chat_http_handler.py` by adding these imports and modifications:

```python
# Add import at the top
from latency_logger import latency_logger

# Modify the lambda_handler function:
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler with latency tracking"""
    request_id = context.aws_request_id
    overall_tracking_id = latency_logger.start_tracking(request_id, "HTTP_Request", {
        'route': event.get('routeKey', ''),
        'method': event.get('requestContext', {}).get('http', {}).get('method', ''),
        'path': event.get('requestContext', {}).get('http', {}).get('path', '')
    })
    
    try:
        # Your existing handler logic
        logger.info(f"Received event: {json.dumps(event, default=str)}")
        
        route_key = event.get('routeKey', '')
        method = event.get('requestContext', {}).get('http', {}).get('method', '')
        path = event.get('requestContext', {}).get('http', {}).get('path', '')
        
        logger.info(f"Processing {method} {path} (route: {route_key})")
        
        # Route handling with individual tracking
        if route_key == "GET /health":
            result = handle_health_check(event, context)
        elif route_key == "OPTIONS /chat":
            result = handle_cors_preflight(event, context)
        elif route_key == "POST /chat":
            result = handle_chat_request(event, context)
        elif route_key.startswith("GET /api/v1/chat/history/"):
            result = handle_chat_history(event, context)
        else:
            result = create_error_response(404, "Route not found", f"Unknown route: {route_key}")
        
        # End tracking successfully
        latency_logger.end_tracking(overall_tracking_id, {
            'status_code': result.get('statusCode'),
            'response_size': len(str(result.get('body', '')))
        }, success=result.get('statusCode', 500) < 400)
        
        return result
            
    except Exception as e:
        logger.error(f"Unhandled error in lambda_handler: {str(e)}", exc_info=True)
        latency_logger.end_tracking(overall_tracking_id, {
            'error': str(e),
            'error_type': type(e).__name__
        }, success=False)
        return create_error_response(500, "Internal server error", "An unexpected error occurred")

# Update the process_chat_message function:
def process_chat_message(session_id: str, user_id: str, user_message: str) -> Dict[str, Any]:
    """Process chat message with detailed latency tracking"""
    
    # Track DynamoDB operations
    db_tracking_id = latency_logger.track_database_operation(
        "put_item", CHAT_MESSAGES_TABLE, session_id, 
        {'message_length': len(user_message)}
    )
    
    # Create or update session
    timestamp = datetime.utcnow().isoformat()
    message_id = str(uuid.uuid4())
    
    # Save user message to DynamoDB
    user_message_record = {
        'session_id': session_id,
        'timestamp': timestamp,
        'message_id': message_id,
        'type': 'user',
        'content': user_message,
        'user_id': user_id,
        'created_at': timestamp
    }
    
    try:
        messages_table.put_item(Item=convert_floats_to_decimals(user_message_record))
        latency_logger.end_tracking(db_tracking_id, {
            'table': CHAT_MESSAGES_TABLE,
            'operation': 'put_item',
            'item_size': len(json.dumps(user_message_record, default=str))
        })
        logger.info(f"Saved user message: {message_id}")
    except Exception as e:
        latency_logger.end_tracking(db_tracking_id, {
            'error': str(e)
        }, success=False)
        raise
    
    # Call Bedrock agent directly for immediate response
    try:
        ai_response = call_bedrock_agent(user_message, session_id)
        
        # Save AI response with tracking
        ai_save_tracking_id = latency_logger.track_database_operation(
            "put_item", CHAT_MESSAGES_TABLE, session_id,
            {'response_length': len(ai_response.get('message', ''))}
        )
        
        ai_message_id = str(uuid.uuid4())
        ai_timestamp = datetime.utcnow().isoformat()
        
        ai_message_record = {
            'session_id': session_id,
            'timestamp': ai_timestamp,
            'message_id': ai_message_id,
            'type': 'assistant',
            'content': ai_response['message'],
            'created_at': ai_timestamp,
            'processing_time': ai_response.get('processing_time', 0),
            'bedrock_response_id': ai_response.get('response_id', '')
        }
        
        messages_table.put_item(Item=convert_floats_to_decimals(ai_message_record))
        latency_logger.end_tracking(ai_save_tracking_id, {
            'response_size': len(ai_response['message'])
        })
        logger.info(f"Saved AI response: {ai_message_id}")
        
        # Return structured response
        return {
            'session_id': session_id,
            'user_message_id': message_id,
            'ai_message_id': ai_message_id,
            'response': ai_response['message'],
            'processing_time': ai_response.get('processing_time', 0),
            'timestamp': ai_timestamp,
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"Error calling Bedrock: {str(e)}")
        # Handle error case with your existing logic...

# Update call_bedrock_agent function:
def call_bedrock_agent(user_message: str, session_id: str) -> Dict[str, Any]:
    """Call Bedrock agent with latency tracking"""
    
    bedrock_tracking_id = latency_logger.track_bedrock_call(
        BEDROCK_AGENT_ID, session_id, len(user_message)
    )
    
    start_time = time.time()
    
    try:
        with latency_logger.track_external_service("Bedrock", session_id, {
            'agent_id': BEDROCK_AGENT_ID,
            'message_length': len(user_message)
        }) as tracker:
            response = bedrock_client.invoke_agent(
                agentId=BEDROCK_AGENT_ID,
                agentAliasId=BEDROCK_AGENT_ALIAS,
                sessionId=session_id,
                inputText=user_message
            )
        
        processing_time = time.time() - start_time
        
        # Extract response text from Bedrock streaming response
        response_text = ""
        response_id = response.get('sessionId', '')
        
        # Handle streaming response from Bedrock Agent
        if 'completion' in response:
            event_stream = response['completion']
            try:
                for event in event_stream:
                    if 'chunk' in event:
                        chunk = event['chunk']
                        if 'bytes' in chunk:
                            chunk_text = chunk['bytes'].decode('utf-8')
                            response_text += chunk_text
                    elif 'trace' in event:
                        logger.debug(f"Trace event: {event}")
            except Exception as stream_error:
                logger.error(f"Error processing event stream: {stream_error}")
                if isinstance(response, dict) and 'output' in response:
                    response_text = response['output'].get('text', '')
                else:
                    response_text = "Unable to process response from AI assistant."
        
        # Complete Bedrock tracking
        latency_logger.end_tracking(bedrock_tracking_id, {
            'response_length': len(response_text),
            'streaming': 'completion' in response,
            'response_id': response_id
        })
        
        # Format response with Warren Buffett branding
        formatted_response = f"🏛️ **Warren Buffett Investment Advisor**\n\n{response_text}\n\n---\n📚 *Source: Warren Buffett Shareholder Letters*\n⏱️ *Response generated in {processing_time:.2f} seconds*"
        
        return {
            'message': formatted_response,
            'processing_time': Decimal(str(round(processing_time, 2))),
            'response_id': response_id
        }
        
    except Exception as e:
        latency_logger.end_tracking(bedrock_tracking_id, {
            'error': str(e)
        }, success=False)
        logger.error(f"Bedrock agent call failed: {str(e)}")
        raise e
```

## 3. Environment Configuration

Add these environment variables to your Lambda functions (update your terraform configuration):

```hcl
# Add to your Lambda function environment variables in main.tf
environment {
  variables = {
    # Existing variables...
    ENABLE_LOCAL_LATENCY_LOGS     = "true"
    ENABLE_DETAILED_LATENCY_LOGS  = "true"
    CLOUDWATCH_NAMESPACE          = "buffett-chat-api/latency"
  }
}
```

## 4. CloudWatch Dashboard Configuration

Create a CloudWatch dashboard to visualize your latency metrics. Add this JSON configuration in AWS Console or via Terraform:

```json
{
  "widgets": [
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["buffett-chat-api/Latency", "RequestLatency", "FunctionName", "chat_http_handler"],
          [".", ".", ".", "websocket_message"],
          [".", ".", ".", "chat_processor"]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Average Request Latency by Function",
        "yAxis": {
          "left": {
            "min": 0
          }
        }
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["buffett-chat-api/Latency", "RequestLatency", "OperationType", "Bedrock_Agent"],
          [".", ".", ".", "DynamoDB_put_item"],
          [".", ".", ".", "External_Bedrock"]
        ],
        "period": 300,
        "stat": "Average",
        "region": "us-east-1",
        "title": "Average Latency by Operation Type"
      }
    },
    {
      "type": "metric",
      "properties": {
        "metrics": [
          ["buffett-chat-api/RequestCount", "RequestCount", "Success", "True"],
          [".", ".", ".", "False"]
        ],
        "period": 300,
        "stat": "Sum",
        "region": "us-east-1",
        "title": "Request Success vs Failure Count"
      }
    }
  ]
}
```

## 5. CloudWatch Alarms

Set up CloudWatch alarms for high latency. Add this to your infrastructure code:

```python
# Create latency monitoring alarms
def create_latency_alarms():
    cloudwatch = boto3.client('cloudwatch')
    
    # High latency alarm
    cloudwatch.put_metric_alarm(
        AlarmName='BuffettChatAPI-HighLatency',
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=2,
        MetricName='RequestLatency',
        Namespace='buffett-chat-api/Latency',
        Period=300,
        Statistic='Average',
        Threshold=2000.0,  # 2 seconds
        ActionsEnabled=True,
        AlarmDescription='Alert when average latency exceeds 2 seconds',
        Unit='Milliseconds'
    )
    
    # Error rate alarm
    cloudwatch.put_metric_alarm(
        AlarmName='BuffettChatAPI-HighErrorRate',
        ComparisonOperator='GreaterThanThreshold',
        EvaluationPeriods=2,
        MetricName='RequestCount',
        Namespace='buffett-chat-api/RequestCount',
        Period=300,
        Statistic='Sum',
        Threshold=10.0,  # More than 10 errors in 5 minutes
        ActionsEnabled=True,
        AlarmDescription='Alert when error rate is high',
        Dimensions=[
            {
                'Name': 'Success',
                'Value': 'False'
            }
        ]
    )
```

## 6. Implementation Steps

### Step 1: Frontend Setup
1. Create `frontend/src/utils/latencyTracker.js` with the provided code
2. Update your `frontend/src/App.jsx` with the latency tracking integrations
3. Add the Performance Dashboard component
4. Test in browser - you should see colored latency logs in Chrome DevTools Console

### Step 2: Backend Setup
1. Create `chat-api/lambda-functions/latency_logger.py` with the provided code
2. Update your `chat-api/lambda-functions/chat_http_handler.py` with the tracking integrations
3. Add environment variables to your Lambda configuration
4. Deploy and test - check CloudWatch logs for latency entries

### Step 3: Monitoring Setup
1. Create CloudWatch dashboard using the provided JSON
2. Set up CloudWatch alarms for high latency and error rates
3. Test the complete flow and verify metrics appear in CloudWatch

### Step 4: Testing and Validation
1. Send test messages through your chat interface
2. Verify Chrome console shows colored latency logs
3. Check localStorage for persisted metrics
4. Export data from Performance Dashboard
5. Verify CloudWatch metrics and local Lambda log files

## 7. Usage Instructions

### Frontend Monitoring
- **Chrome Console**: Open DevTools → Console to see real-time latency logs with color coding:
  - 🟢 Green: < 100ms (Excellent)
  - 🟡 Yellow: 100-500ms (Good)  
  - 🔴 Red: > 500ms (Poor)
- **Performance Dashboard**: Click "📊 Performance" button to view metrics summary
- **Data Export**: Export JSON/CSV reports for external analysis
- **Cleanup**: Remove old localStorage data to free up space

### Backend Monitoring
- **CloudWatch Logs**: Check Lambda function logs for detailed latency entries
- **CloudWatch Metrics**: View custom metrics in CloudWatch dashboard
- **Local Files**: Lambda functions write latency data to `/tmp/latency_logs/` directory
- **Alarms**: Get notified when latency thresholds are exceeded

### Performance Grading
- **Excellent**: < 100ms average latency
- **Good**: 100-300ms average latency
- **Fair**: 300-800ms average latency
- **Poor**: > 800ms average latency

## 8. Advanced Features

### Custom Metrics
- Track specific operations (Bedrock calls, DynamoDB operations, external APIs)
- Monitor success/failure rates
- Track request sizes and response times

### Data Analysis
- Export data for offline analysis
- Correlate frontend and backend latency
- Identify performance bottlenecks across the infrastructure

### Alerting
- Set custom thresholds based on your SLA requirements
- Integrate with SNS for notifications
- Create dashboards for different stakeholder groups

This comprehensive latency measurement system will provide complete visibility into your buffett_chat_api performance across the entire stack.