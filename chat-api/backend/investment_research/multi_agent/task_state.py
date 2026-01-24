"""
Task State Management for Multi-Agent Orchestration

Uses optimistic concurrency control via JSON file for coordinating
multiple Claude Code workers. Based on Cursor's learnings:
- No locks (agents could hold too long or forget to release)
- Optimistic concurrency (read freely, fail on stale writes)
- Simple state transitions: pending -> in_progress -> completed/failed

File-based coordination chosen over DynamoDB for local Claude Code workers
to avoid AWS credentials complexity during development.
"""

import json
import logging
import os
import shutil
import tempfile
import time
import hashlib
from datetime import datetime
from typing import Optional, Dict, List, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

# Configure module logger
logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Task:
    """Individual task representing a report to generate."""
    ticker: str
    status: TaskStatus
    worker_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    retry_count: int = 0
    report_path: Optional[str] = None
    last_heartbeat: Optional[str] = None  # For detecting stalled/compacted workers

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['status'] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'Task':
        data['status'] = TaskStatus(data['status'])
        # Handle older state files without heartbeat field
        if 'last_heartbeat' not in data:
            data['last_heartbeat'] = None
        return cls(**data)

    def is_stale(self, timeout_seconds: int = 300) -> bool:
        """
        Check if task heartbeat is stale (worker may have been compacted).

        Default timeout is 5 minutes - if a worker hasn't updated heartbeat
        in that time, assume it was compacted or crashed.
        """
        if self.status != TaskStatus.IN_PROGRESS:
            return False
        if not self.last_heartbeat:
            # No heartbeat yet - use started_at
            timestamp = self.started_at
        else:
            timestamp = self.last_heartbeat

        if not timestamp:
            return True  # No timestamp at all = stale

        # Parse ISO timestamp and check age
        try:
            ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            now = datetime.now(ts.tzinfo) if ts.tzinfo else datetime.utcnow()
            age = (now - ts.replace(tzinfo=None)).total_seconds()
            return age > timeout_seconds
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse timestamp '{timestamp}': {e}")
            return True  # Conservative: treat malformed dates as stale


@dataclass
class BatchState:
    """State of entire batch processing run."""
    batch_id: str
    created_at: str
    version: int  # For optimistic concurrency
    tasks: Dict[str, Task]  # ticker -> Task
    config: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            'batch_id': self.batch_id,
            'created_at': self.created_at,
            'version': self.version,
            'tasks': {k: v.to_dict() for k, v in self.tasks.items()},
            'config': self.config
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'BatchState':
        tasks = {k: Task.from_dict(v) for k, v in data['tasks'].items()}
        return cls(
            batch_id=data['batch_id'],
            created_at=data['created_at'],
            version=data['version'],
            tasks=tasks,
            config=data.get('config', {})
        )


class TaskStateManager:
    """
    Manages task state with optimistic concurrency control.

    Based on Cursor's learnings:
    - Workers read state freely
    - Writes fail if state changed since last read (version mismatch)
    - Simple, robust coordination without locks
    """

    DEFAULT_STATE_DIR = Path(__file__).parent / "state"

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or self.DEFAULT_STATE_DIR
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._last_read_version: Optional[int] = None

    def _state_file(self, batch_id: str) -> Path:
        return self.state_dir / f"batch_{batch_id}.json"

    def create_batch(
        self,
        tickers: List[str],
        batch_id: Optional[str] = None,
        config: Optional[Dict] = None
    ) -> BatchState:
        """
        Create a new batch with pending tasks for all tickers.

        Args:
            tickers: List of ticker symbols to process
            batch_id: Optional ID (auto-generated if not provided)
            config: Optional configuration (concurrency, prompt_version, etc.)

        Returns:
            BatchState with all tasks in PENDING status
        """
        if batch_id is None:
            batch_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        tasks = {
            ticker: Task(ticker=ticker, status=TaskStatus.PENDING)
            for ticker in tickers
        }

        state = BatchState(
            batch_id=batch_id,
            created_at=datetime.utcnow().isoformat() + 'Z',
            version=1,
            tasks=tasks,
            config=config or {}
        )

        self._write_state(state)
        return state

    def read_state(self, batch_id: str) -> Optional[BatchState]:
        """
        Read current batch state.

        Stores version for optimistic concurrency check on next write.
        Handles JSON corruption gracefully.
        """
        state_file = self._state_file(batch_id)
        if not state_file.exists():
            return None

        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
            state = BatchState.from_dict(data)
            self._last_read_version = state.version
            return state
        except json.JSONDecodeError as e:
            logger.error(f"Corrupted state file {state_file}: {e}")
            # Try to restore from backup
            backup_file = state_file.with_suffix('.json.bak')
            if backup_file.exists():
                logger.info(f"Attempting restore from {backup_file}")
                try:
                    with open(backup_file, 'r') as f:
                        data = json.load(f)
                    state = BatchState.from_dict(data)
                    self._last_read_version = state.version
                    # Restore the backup to main file
                    shutil.copy2(backup_file, state_file)
                    logger.info("Restored state from backup")
                    return state
                except Exception as restore_err:
                    logger.error(f"Failed to restore from backup: {restore_err}")
            return None
        except (ValueError, KeyError) as e:
            logger.error(f"Invalid state structure in {state_file}: {e}")
            return None

    def _write_state(self, state: BatchState, check_version: bool = False) -> bool:
        """
        Write state with optional optimistic concurrency check.

        Uses atomic write (temp file + rename) to prevent corruption.

        Args:
            state: State to write
            check_version: If True, fail if version doesn't match last read

        Returns:
            True if write succeeded, False if version conflict
        """
        state_file = self._state_file(state.batch_id)

        if check_version and state_file.exists():
            try:
                with open(state_file, 'r') as f:
                    current = json.load(f)
                if current['version'] != self._last_read_version:
                    logger.debug(
                        f"Version conflict: expected {self._last_read_version}, "
                        f"got {current['version']}"
                    )
                    return False  # Optimistic concurrency conflict
            except (json.JSONDecodeError, KeyError) as e:
                # Current file corrupted - can't verify version, treat as conflict
                logger.warning(f"Cannot verify version (file corrupted?): {e}")
                return False

        state.version += 1

        # Create backup before writing (only if file exists)
        if state_file.exists():
            backup_file = state_file.with_suffix('.json.bak')
            try:
                shutil.copy2(state_file, backup_file)
            except Exception as e:
                logger.warning(f"Failed to create backup: {e}")

        # Atomic write: write to temp file, then rename
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=state_file.parent,
                delete=False,
                suffix='.tmp'
            ) as tmp:
                json.dump(state.to_dict(), tmp, indent=2)
                tmp_path = Path(tmp.name)

            # Atomic rename (POSIX guarantees atomicity for same-filesystem rename)
            tmp_path.replace(state_file)
            return True

        except Exception as e:
            logger.error(f"Failed to write state: {e}")
            # Clean up temp file if it exists
            if 'tmp_path' in locals() and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass
            return False

    def claim_task(
        self,
        batch_id: str,
        worker_id: str,
        stale_timeout: int = 300
    ) -> Optional[str]:
        """
        Claim next pending OR stale task for a worker.

        Uses optimistic concurrency - if another worker claims first,
        this will fail and worker should retry.

        COMPACTION HANDLING: Also reclaims tasks that are IN_PROGRESS but
        haven't received a heartbeat in stale_timeout seconds. This handles
        the case where a Claude Code worker was compacted mid-task.

        Args:
            batch_id: Batch to claim from
            worker_id: Unique identifier for this worker
            stale_timeout: Seconds before an in-progress task is considered stale

        Returns:
            Ticker symbol if claimed, None if no available tasks or conflict
        """
        state = self.read_state(batch_id)
        if not state:
            return None

        now = datetime.utcnow().isoformat() + 'Z'

        # First priority: claim pending tasks
        for ticker, task in state.tasks.items():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.IN_PROGRESS
                task.worker_id = worker_id
                task.started_at = now
                task.last_heartbeat = now

                if self._write_state(state, check_version=True):
                    return ticker
                else:
                    # Conflict - another worker claimed first, retry
                    return None

        # Second priority: reclaim stale tasks (worker was compacted)
        for ticker, task in state.tasks.items():
            if task.is_stale(stale_timeout):
                old_worker = task.worker_id
                task.worker_id = worker_id
                task.started_at = now
                task.last_heartbeat = now
                task.retry_count += 1  # Count as a retry

                if self._write_state(state, check_version=True):
                    print(f"[TaskState] Reclaimed stale task {ticker} from {old_worker}")
                    return ticker
                else:
                    return None

        return None  # No available tasks

    def heartbeat(self, batch_id: str, ticker: str, worker_id: str) -> bool:
        """
        Update heartbeat for an in-progress task.

        Workers should call this periodically (e.g., every 60s) to indicate
        they're still alive. If a worker is compacted mid-task, it won't
        send heartbeats, allowing another worker to reclaim the task.

        Args:
            batch_id: Batch containing the task
            ticker: Ticker being processed
            worker_id: Worker ID (must match task's worker_id)

        Returns:
            True if heartbeat updated, False if task not owned by this worker
        """
        state = self.read_state(batch_id)
        if not state or ticker not in state.tasks:
            return False

        task = state.tasks[ticker]

        # Only update if we still own this task
        if task.status != TaskStatus.IN_PROGRESS or task.worker_id != worker_id:
            return False

        task.last_heartbeat = datetime.utcnow().isoformat() + 'Z'
        return self._write_state(state, check_version=True)

    def complete_task(
        self,
        batch_id: str,
        ticker: str,
        report_path: Optional[str] = None
    ) -> bool:
        """
        Mark a task as completed.

        Args:
            batch_id: Batch containing the task
            ticker: Ticker that was processed
            report_path: Path to generated report file

        Returns:
            True if update succeeded
        """
        state = self.read_state(batch_id)
        if not state or ticker not in state.tasks:
            return False

        task = state.tasks[ticker]
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow().isoformat() + 'Z'
        task.report_path = report_path

        return self._write_state(state, check_version=True)

    def fail_task(
        self,
        batch_id: str,
        ticker: str,
        error: str,
        retry: bool = True
    ) -> bool:
        """
        Mark a task as failed, optionally queuing for retry.

        Args:
            batch_id: Batch containing the task
            ticker: Ticker that failed
            error: Error message
            retry: If True, reset to PENDING with incremented retry_count

        Returns:
            True if update succeeded
        """
        state = self.read_state(batch_id)
        if not state or ticker not in state.tasks:
            return False

        task = state.tasks[ticker]
        max_retries = state.config.get('max_retries', 3)

        if retry and task.retry_count < max_retries:
            task.status = TaskStatus.PENDING
            task.retry_count += 1
            task.error = error
            task.worker_id = None
            task.started_at = None
        else:
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.utcnow().isoformat() + 'Z'

        return self._write_state(state, check_version=True)

    def get_summary(self, batch_id: str) -> Dict[str, Any]:
        """
        Get summary statistics for a batch.

        Returns:
            Dict with counts by status and progress percentage
        """
        state = self.read_state(batch_id)
        if not state:
            return {}

        summary = {
            'batch_id': batch_id,
            'total': len(state.tasks),
            'pending': 0,
            'in_progress': 0,
            'completed': 0,
            'failed': 0,
            'progress_pct': 0.0,
            'tasks': {}
        }

        for ticker, task in state.tasks.items():
            summary[task.status.value] += 1
            summary['tasks'][ticker] = {
                'status': task.status.value,
                'worker_id': task.worker_id,
                'retry_count': task.retry_count,
                'error': task.error
            }

        done = summary['completed'] + summary['failed']
        summary['progress_pct'] = (done / summary['total'] * 100) if summary['total'] > 0 else 0

        return summary

    def is_batch_complete(self, batch_id: str) -> bool:
        """Check if all tasks are in terminal state (completed or failed)."""
        state = self.read_state(batch_id)
        if not state:
            return True

        for task in state.tasks.values():
            if task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                return False
        return True

    def list_batches(self) -> List[str]:
        """List all batch IDs in the state directory."""
        batches = []
        for f in self.state_dir.glob("batch_*.json"):
            batch_id = f.stem.replace("batch_", "")
            batches.append(batch_id)
        return sorted(batches, reverse=True)


# Convenience functions for CLI usage
def create_batch(tickers: List[str], **config) -> str:
    """Create a new batch and return batch_id."""
    mgr = TaskStateManager()
    state = mgr.create_batch(tickers, config=config)
    return state.batch_id


def get_next_task(batch_id: str, worker_id: str) -> Optional[str]:
    """Get next available task for a worker."""
    mgr = TaskStateManager()
    return mgr.claim_task(batch_id, worker_id)


def mark_complete(batch_id: str, ticker: str, report_path: str = None) -> bool:
    """Mark a task as completed."""
    mgr = TaskStateManager()
    return mgr.complete_task(batch_id, ticker, report_path)


def mark_failed(batch_id: str, ticker: str, error: str) -> bool:
    """Mark a task as failed."""
    mgr = TaskStateManager()
    return mgr.fail_task(batch_id, ticker, error)


def get_status(batch_id: str) -> Dict:
    """Get batch status summary."""
    mgr = TaskStateManager()
    return mgr.get_summary(batch_id)
