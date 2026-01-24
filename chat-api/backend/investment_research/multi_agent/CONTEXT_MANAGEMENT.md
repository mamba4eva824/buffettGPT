# Context Management for Multi-Agent Claude Code Orchestration

This document explains how to manage Claude Code agents in a multi-agent workflow where context windows become full and require compaction.

## The Problem

Each Claude Code session has a ~200k token context window. When running long-running batch tasks:
1. Context fills up with tool calls, responses, and reasoning
2. Eventually requires `/compact` to continue
3. After compaction, the agent "forgets" conversation history
4. If compacted mid-task, the task could be orphaned

## The Solution: Externalized State + Stateless Workers

```
                  ┌─────────────────────────────────────────────┐
                  │          task_state.json                    │
                  │                                             │
                  │  {                                          │
                  │    "batch_id": "20240115_143022",          │
                  │    "version": 47,                          │
                  │    "tasks": {                              │
                  │      "AAPL": {"status": "completed"},      │
                  │      "MSFT": {"status": "in_progress",     │
                  │               "worker_id": "W01",          │
                  │               "last_heartbeat": "..."},    │
                  │      "NVDA": {"status": "pending"}         │
                  │    }                                       │
                  │  }                                          │
                  └─────────────────┬───────────────────────────┘
                                    │
            ┌───────────────────────┼───────────────────────────┐
            │                       │                           │
            ▼                       ▼                           ▼
    ┌───────────────┐      ┌───────────────┐           ┌───────────────┐
    │   Worker 1    │      │   Worker 2    │           │   Worker 3    │
    │   (active)    │      │  (compacted)  │           │   (fresh)     │
    │               │      │               │           │               │
    │ Reads state   │      │ Was working   │           │ Sees W2's     │
    │ Claims task   │      │ on GOOGL...   │           │ task is stale │
    │ Sends HB      │      │ Got compacted │           │ Reclaims it   │
    └───────────────┘      │ No heartbeat  │           └───────────────┘
                           └───────────────┘
```

## Key Design Principles

### 1. Workers Are Stateless

Workers read ALL state from the JSON file on every loop iteration:
- No reliance on conversation history
- No in-memory task tracking
- If compacted, behavior is identical to a fresh start

```python
while self.running:
    # ALWAYS read fresh state from file
    ticker = self.state_mgr.claim_task(self.batch_id, self.worker_id)
    if ticker:
        self._process_task(ticker)
```

### 2. Heartbeat-Based Liveness

Workers send periodic heartbeats while processing:
- Updates `last_heartbeat` timestamp every 60 seconds
- If a task has no heartbeat for 5 minutes, it's considered "stale"
- Stale tasks can be reclaimed by any worker

```python
def _start_heartbeat(self):
    def heartbeat_loop():
        while self._current_ticker:
            time.sleep(60)
            self.state_mgr.heartbeat(batch_id, ticker, worker_id)
    threading.Thread(target=heartbeat_loop, daemon=True).start()
```

### 3. Optimistic Concurrency (No Locks)

Based on Cursor's research findings:
- **No locks**: Agents might hold locks too long or forget to release
- **Version-based conflicts**: Read freely, writes fail on version mismatch
- **Retry on conflict**: If write fails, read again and retry

```python
def claim_task(self, batch_id, worker_id):
    state = self.read_state(batch_id)  # Stores version
    # Find and claim task
    task.status = IN_PROGRESS
    if self._write_state(state, check_version=True):  # Fails if version changed
        return ticker
    return None  # Conflict, retry
```

### 4. Task Timeout & Reclaim

When claiming tasks, also check for stale in-progress tasks:

```python
# Priority 1: Pending tasks
for task in tasks:
    if task.status == PENDING:
        claim_it()

# Priority 2: Stale tasks (worker was compacted)
for task in tasks:
    if task.is_stale(timeout_seconds=300):
        reclaim_it()
```

## Usage Scenarios

### Scenario 1: Normal Operation
1. Worker claims AAPL (status: pending → in_progress)
2. Worker sends heartbeats every 60s
3. Report generates successfully
4. Worker marks complete (status: in_progress → completed)
5. Worker claims next task

### Scenario 2: Worker Compacted Mid-Task
1. Worker 1 claims MSFT
2. Worker 1 is generating report... context fills up
3. `/compact` happens - Worker 1 "forgets"
4. 5 minutes pass with no heartbeat
5. Worker 2 tries to claim task, sees MSFT is stale
6. Worker 2 reclaims MSFT and continues

### Scenario 3: Resume After Full Compaction
1. All workers compacted (batch partially complete)
2. User runs `--resume BATCH_ID`
3. New workers spawn, read state file
4. Completed tasks skipped, pending/stale tasks claimed
5. Batch continues from where it left off

## Best Practices

### For Claude Code Terminal Workers

1. **Keep tasks atomic**: Each task should be completable in one context window
   - Good: Generate one report per task
   - Bad: Generate 10 reports per task

2. **Use external checkpoints for long tasks**:
   ```python
   # Save progress to file, not conversation memory
   with open(f"checkpoint_{ticker}.json", "w") as f:
       json.dump({"step": 3, "data": partial_result}, f)
   ```

3. **Design prompts for fresh starts**:
   ```
   IMPORTANT: Do NOT rely on conversation history.
   Read the state file to determine your current task.
   If you have an in-progress task, check for checkpoints.
   ```

4. **Set appropriate timeouts**:
   - Report generation: ~10 min → 5 min stale timeout is safe
   - Complex analysis: ~30 min → use 15 min stale timeout
   - Quick tasks: ~1 min → use 2 min stale timeout

### For Python Thread Workers

1. **Run heartbeat in daemon thread**: Automatically stops if main thread dies
2. **Handle SIGINT/SIGTERM**: Gracefully complete current task before exit
3. **Use ThreadPoolExecutor**: Manages worker lifecycle automatically

## Configuration

### Environment Variables

```bash
# Stale timeout (seconds before task can be reclaimed)
TASK_STALE_TIMEOUT=300

# Heartbeat interval (seconds between heartbeats)
HEARTBEAT_INTERVAL=60

# Max retries per task before marking as failed
MAX_TASK_RETRIES=3
```

### CLI Flags

```bash
# Run with 10 parallel workers
python -m investment_research.multi_agent.orchestrator --djia --workers 10

# Resume an interrupted batch
python -m investment_research.multi_agent.orchestrator --resume 20240115_143022

# Check batch status
python -m investment_research.multi_agent.orchestrator --status 20240115_143022
```

## Monitoring

### Batch Status JSON

```json
{
  "batch_id": "20240115_143022",
  "total": 30,
  "completed": 18,
  "in_progress": 2,
  "pending": 8,
  "failed": 2,
  "progress_pct": 66.7
}
```

### Detecting Stalled Workers

Check for tasks with old heartbeats:
```bash
jq '.tasks | to_entries | map(select(.value.status == "in_progress")) | map({ticker: .key, heartbeat: .value.last_heartbeat})' batch_*.json
```

## Architecture Comparison

| Approach | Context Safety | Complexity | Speed |
|----------|---------------|------------|-------|
| Single long-running agent | Low | Low | Slow |
| Stateless workers + file state | High | Medium | Fast |
| Stateless workers + DynamoDB | High | High | Fast |
| Worker rotation (N tasks then exit) | High | Low | Medium |

This implementation uses **Stateless workers + file state** for local development and testing. For production at scale, consider migrating to DynamoDB for distributed coordination.
