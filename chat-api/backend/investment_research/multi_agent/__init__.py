"""
Multi-Agent Orchestration for Investment Report Generation

This module implements a Planner-Worker-Judge pattern for parallel
report generation using Claude Code terminals.

Based on Cursor's learnings for scaling autonomous coding:
- Planners create and decompose tasks
- Workers focus entirely on completing single tasks (no coordination)
- Judges validate quality at end of each cycle
- Optimistic concurrency (no locks)
- Periodic fresh starts combat drift

Components:
- task_state.py: JSON-based task coordination with optimistic concurrency
- orchestrator.py: Main coordinator that spawns Claude Code workers
- worker_prompt.py: Prompt templates for worker agents
- judge.py: Quality validation agent
"""

from .task_state import (
    TaskStateManager,
    TaskStatus,
    Task,
    BatchState,
    create_batch,
    get_next_task,
    mark_complete,
    mark_failed,
    get_status,
)

__all__ = [
    'TaskStateManager',
    'TaskStatus',
    'Task',
    'BatchState',
    'create_batch',
    'get_next_task',
    'mark_complete',
    'mark_failed',
    'get_status',
]
