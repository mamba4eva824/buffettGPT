#!/usr/bin/env python3
"""
Multi-Agent Orchestrator for Investment Report Generation

Spawns multiple Claude Code workers to generate reports in parallel,
using file-based coordination with optimistic concurrency.

Based on Cursor's architecture:
- Planner determines which tickers need reports
- Workers run independently, claiming tasks from shared queue
- Judge validates completed reports

Usage:
    # Generate all Dow 30 reports with 5 parallel workers
    python -m investment_research.multi_agent.orchestrator --djia --workers 5

    # Generate S&P 100 reports with 10 workers
    python -m investment_research.multi_agent.orchestrator --sp100 --workers 10

    # Resume an existing batch
    python -m investment_research.multi_agent.orchestrator --resume BATCH_ID

    # Check status of a batch
    python -m investment_research.multi_agent.orchestrator --status BATCH_ID
"""

import argparse
import logging
import os
import random
import signal
import subprocess
import sys
import time
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configure module logger
logger = logging.getLogger(__name__)

# Add parent paths for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from investment_research.multi_agent.task_state import (
    TaskStateManager,
    TaskStatus,
    create_batch,
    get_status,
)
from investment_research.index_tickers import get_index_tickers, get_test_tickers


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_WORKERS = 5
MAX_WORKERS = 20
DEFAULT_PROMPT_VERSION = 4.9
WORKER_POLL_INTERVAL = 2  # seconds between checking for new tasks
JUDGE_POLL_INTERVAL = 10  # seconds between judge cycles

# =============================================================================
# Claude Code Worker Prompt Template
# =============================================================================
# This prompt is designed to be COMPACTION-SAFE:
# - Worker reads ALL state from task_state.json on startup
# - No reliance on conversation history
# - If compacted, a fresh instance can pick up from current state
# =============================================================================

CLAUDE_CODE_WORKER_PROMPT = """
You are a batch worker for investment report generation. Your job is to:
1. Check the task state file for available tasks
2. Generate one report at a time
3. Update task state when complete
4. Repeat until no tasks remain

IMPORTANT - CONTEXT MANAGEMENT:
- You have a limited context window that may require compaction
- ALL state is externalized in the task_state.json file
- If you get compacted, a fresh instance will continue from the state file
- Do NOT rely on conversation history - always read state from the file

BATCH: {batch_id}
WORKER: {worker_id}
STATE FILE: {state_file}

WORKFLOW:
1. Read {state_file} to find your current task (if any) or next pending task
2. If you have an in-progress task claimed by you, resume it
3. If no task, claim a pending one by updating the state file
4. Generate the report using: python -m investment_research.generate_report {ticker}
5. Update task status to 'completed' in the state file
6. Repeat from step 1

EXIT when:
- No pending tasks AND no in-progress tasks
- All tasks are completed or failed

START NOW: Read {state_file} and begin processing.
"""

# Legacy template for subprocess mode
WORKER_SCRIPT_TEMPLATE = """
# Worker {worker_id} - Investment Report Generator
# Batch: {batch_id}
# Ticker: {ticker}

# Generate investment report for {ticker}
cd {project_root}/chat-api/backend
python -m investment_research.generate_report --prompt-version {prompt_version} {ticker}

# Report status back
echo "WORKER_COMPLETE:{ticker}"
"""


# =============================================================================
# Planner: Determine which tickers need processing
# =============================================================================

def plan_batch(
    tickers: List[str],
    refresh: bool = False,
    prompt_version: float = DEFAULT_PROMPT_VERSION,
    max_retries: int = 3
) -> str:
    """
    Create a new batch with tasks for specified tickers.

    Acts as the Planner agent - determines what work needs to be done.

    Args:
        tickers: List of ticker symbols
        refresh: If True, regenerate even if reports exist
        prompt_version: Prompt template version
        max_retries: Max retry attempts for failed tasks

    Returns:
        batch_id for the created batch
    """
    # TODO: Check DynamoDB for existing reports if refresh=False
    # For now, process all tickers in the list

    config = {
        'prompt_version': prompt_version,
        'max_retries': max_retries,
        'refresh': refresh,
        'created_by': 'orchestrator',
        'workers_requested': DEFAULT_WORKERS,
    }

    batch_id = create_batch(tickers, config=config)
    print(f"Created batch {batch_id} with {len(tickers)} tickers")
    return batch_id


# =============================================================================
# Worker: Process individual tickers
# =============================================================================

class Worker:
    """
    Worker process that claims and processes tasks.

    Each worker runs in its own thread, claiming tasks from the shared
    queue using optimistic concurrency.

    Based on Cursor's insight: "Workers pick up tasks and focus entirely
    on completing them. They don't coordinate with other workers."

    COMPACTION HANDLING:
    - Workers are stateless: all state lives in task_state.json
    - Workers send heartbeats during processing to indicate they're alive
    - If a worker is compacted mid-task (no heartbeat for 5 min), task is reclaimed
    - A new worker starting up will pick up the orphaned task
    """

    HEARTBEAT_INTERVAL = 60  # seconds between heartbeats
    MAX_STATE_UPDATE_RETRIES = 3  # retries for complete/fail operations
    MAX_BACKOFF_SECONDS = 30  # max backoff for claim conflicts

    def __init__(
        self,
        batch_id: str,
        worker_id: str,
        prompt_version: float = DEFAULT_PROMPT_VERSION
    ):
        self.batch_id = batch_id
        self.worker_id = worker_id
        self.prompt_version = prompt_version
        self.state_mgr = TaskStateManager()
        self.running = True
        self.project_root = Path(__file__).parent.parent.parent.parent.parent
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._current_ticker: Optional[str] = None
        self._stop_event = threading.Event()  # For clean heartbeat shutdown
        self._subprocess: Optional[subprocess.Popen] = None  # Track for cleanup

    def run(self):
        """
        Main worker loop - claim tasks and process until none remain.

        COMPACTION AWARE: This loop is designed so that if the worker's
        context is compacted, a fresh worker can pick up right where
        the state file says to continue. No worker memory is required.
        """
        logger.info(f"[Worker {self.worker_id}] Started (heartbeat every {self.HEARTBEAT_INTERVAL}s)")
        claim_failures = 0  # Track consecutive claim failures for backoff

        while self.running:
            # Try to claim a task (includes reclaiming stale tasks from compacted workers)
            ticker = self.state_mgr.claim_task(self.batch_id, self.worker_id)

            if not ticker:
                # No tasks available - check if batch is complete
                if self.state_mgr.is_batch_complete(self.batch_id):
                    logger.info(f"[Worker {self.worker_id}] Batch complete, exiting")
                    break

                # Exponential backoff with jitter on claim conflicts
                claim_failures += 1
                backoff = min(
                    WORKER_POLL_INTERVAL * (1.5 ** claim_failures),
                    self.MAX_BACKOFF_SECONDS
                )
                jitter = random.uniform(0, backoff * 0.1)
                time.sleep(backoff + jitter)
                continue

            # Successfully claimed - reset backoff counter
            claim_failures = 0

            # Process the claimed task with heartbeat monitoring
            logger.info(f"[Worker {self.worker_id}] Claimed {ticker}")
            self._current_ticker = ticker
            self._stop_event.clear()
            self._start_heartbeat()
            try:
                self._process_task(ticker)
            finally:
                self._stop_heartbeat()
                self._current_ticker = None

    def _start_heartbeat(self):
        """Start background heartbeat thread for current task."""
        def heartbeat_loop():
            missed_count = 0
            while not self._stop_event.wait(timeout=self.HEARTBEAT_INTERVAL):
                if self._current_ticker and self.running:
                    success = self.state_mgr.heartbeat(
                        self.batch_id,
                        self._current_ticker,
                        self.worker_id
                    )
                    if not success:
                        missed_count += 1
                        if missed_count > 2:
                            logger.warning(
                                f"[Worker {self.worker_id}] {missed_count} consecutive "
                                f"heartbeat failures for {self._current_ticker}"
                            )
                    else:
                        missed_count = 0

        self._heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        """Stop heartbeat thread cleanly."""
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2)
        self._heartbeat_thread = None

    def _update_state_with_retry(
        self,
        operation: str,
        ticker: str,
        update_func,
        *args
    ) -> bool:
        """
        Retry state updates with exponential backoff.

        Args:
            operation: Name of operation for logging
            ticker: Ticker being updated
            update_func: Function to call (complete_task or fail_task)
            *args: Arguments to pass to update_func

        Returns:
            True if update succeeded
        """
        for attempt in range(self.MAX_STATE_UPDATE_RETRIES):
            if update_func(*args):
                return True

            if attempt < self.MAX_STATE_UPDATE_RETRIES - 1:
                wait_time = 0.5 * (2 ** attempt)
                logger.warning(
                    f"[Worker {self.worker_id}] {operation} failed for {ticker}, "
                    f"retrying in {wait_time}s (attempt {attempt + 1}/{self.MAX_STATE_UPDATE_RETRIES})"
                )
                time.sleep(wait_time)

        logger.error(
            f"[Worker {self.worker_id}] {operation} failed for {ticker} "
            f"after {self.MAX_STATE_UPDATE_RETRIES} attempts"
        )
        return False

    def _process_task(self, ticker: str):
        """
        Process a single ticker - generate report using Claude Code CLI.
        """
        try:
            self._generate_with_claude_code(ticker)

            # Mark task complete with retry
            report_path = f"test_outputs/{ticker}_report.md"
            success = self._update_state_with_retry(
                "complete_task",
                ticker,
                self.state_mgr.complete_task,
                self.batch_id, ticker, report_path
            )
            if success:
                logger.info(f"[Worker {self.worker_id}] Completed {ticker}")
            else:
                logger.error(f"[Worker {self.worker_id}] Could not mark {ticker} complete")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[Worker {self.worker_id}] Failed {ticker}: {error_msg}")
            self._update_state_with_retry(
                "fail_task",
                ticker,
                self.state_mgr.fail_task,
                self.batch_id, ticker, error_msg
            )

    def _generate_with_claude_code(self, ticker: str):
        """
        Process ticker by spawning Claude Code CLI.

        This leverages Claude's extended thinking and reasoning for
        higher quality reports, but is slower.
        """
        # Explicit command for Claude Code to run
        prompt = f"""Run this exact command to generate an investment research report:

cd /Users/christopherweinreich/Documents/Projects/buffett_chat_api/chat-api/backend
python -m investment_research.generate_report --prompt-version {self.prompt_version} {ticker}

Wait for the command to complete and verify the report was saved."""

        cmd = [
            "claude",
            "-p",  # Print-only mode (no interactive)
            prompt
        ]

        logger.info(f"[Worker {self.worker_id}] Spawning Claude Code for {ticker}...")

        # Use Popen for proper cleanup on timeout
        try:
            self._subprocess = subprocess.Popen(
                cmd,
                cwd=str(self.project_root / "chat-api" / "backend"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            try:
                stdout, stderr = self._subprocess.communicate(timeout=600)
            except subprocess.TimeoutExpired:
                logger.warning(f"[Worker {self.worker_id}] Timeout for {ticker}, terminating process")
                self._subprocess.terminate()
                try:
                    self._subprocess.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(f"[Worker {self.worker_id}] Force killing process for {ticker}")
                    self._subprocess.kill()
                    self._subprocess.wait()
                raise RuntimeError(f"Claude Code timeout after 600s for {ticker}")

            if self._subprocess.returncode != 0:
                error_detail = stderr[:500] if stderr else "No stderr"
                raise RuntimeError(
                    f"Claude Code failed with exit code {self._subprocess.returncode}: {error_detail}"
                )

        finally:
            self._subprocess = None

    def stop(self):
        """Signal worker to stop after current task."""
        self.running = False
        self._stop_event.set()
        # Terminate any running subprocess
        if self._subprocess and self._subprocess.poll() is None:
            logger.info(f"[Worker {self.worker_id}] Terminating subprocess on shutdown")
            self._subprocess.terminate()
            try:
                self._subprocess.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._subprocess.kill()


# =============================================================================
# Judge: Validate report quality
# =============================================================================

class Judge:
    """
    Judge agent that validates completed reports.

    Based on Cursor's pattern: "At the end of each cycle, a judge agent
    determined whether to continue."

    Responsibilities:
    - Validate report structure (all sections present)
    - Check ratings were extracted
    - Ensure reasonable content length
    - Trigger retries for quality failures
    """

    def __init__(self, batch_id: str):
        self.batch_id = batch_id
        self.state_mgr = TaskStateManager()
        self.running = True
        self._validated: Set[str] = set()  # Track already-validated tickers

    def run(self):
        """
        Main judge loop - periodically validate completed reports.
        """
        logger.info("[Judge] Started")

        while self.running:
            self._validate_cycle()

            if self.state_mgr.is_batch_complete(self.batch_id):
                self._final_report()
                break

            time.sleep(JUDGE_POLL_INTERVAL)

    def _validate_cycle(self):
        """
        Run one validation cycle over completed tasks.
        """
        state = self.state_mgr.read_state(self.batch_id)
        if not state:
            return

        for ticker, task in state.tasks.items():
            # Skip already validated tasks
            if ticker in self._validated:
                continue

            if task.status == TaskStatus.COMPLETED and task.report_path:
                validation_result = self._validate_report(ticker, task.report_path)

                if validation_result is True:
                    # Passed validation - mark as validated
                    self._validated.add(ticker)
                elif validation_result is False:
                    # Quality check failed - reset to pending for retry
                    logger.warning(f"[Judge] Quality check failed for {ticker}, queueing retry")
                    success = self.state_mgr.fail_task(
                        self.batch_id, ticker,
                        "Quality validation failed",
                        retry=True
                    )
                    if not success:
                        logger.error(f"[Judge] Failed to queue retry for {ticker}")
                # validation_result is None means IO error - don't mark as validated, retry next cycle

    def _validate_report(self, ticker: str, report_path: str) -> Optional[bool]:
        """
        Validate a generated report meets quality standards.

        Checks:
        - File exists and has content
        - Contains expected section headers
        - Has ratings JSON block
        - Minimum word count

        Returns:
            True if report passes validation
            False if report fails validation (should retry)
            None if validation couldn't be performed (IO error)
        """
        full_path = Path(__file__).parent.parent / report_path
        if not full_path.exists():
            logger.warning(f"[Judge] Report file not found: {full_path}")
            return False

        try:
            content = full_path.read_text()
        except (PermissionError, OSError) as e:
            logger.error(f"[Judge] Cannot read {report_path}: {e}")
            return None  # IO error - retry validation later

        # Check minimum length (reports should be substantial)
        word_count = len(content.split())
        if word_count < 1000:
            logger.info(f"[Judge] {ticker}: Too short ({word_count} words)")
            return False

        # Check for key sections
        required_sections = [
            "Executive Summary",
            "Growth",
            "Debt",
            "Cash Flow",
        ]
        for section in required_sections:
            if section.lower() not in content.lower():
                logger.info(f"[Judge] {ticker}: Missing section '{section}'")
                return False

        # Check for ratings JSON
        if '"overall_verdict"' not in content and "overall_verdict" not in content:
            logger.info(f"[Judge] {ticker}: Missing ratings")
            return False

        return True

    def _final_report(self):
        """
        Generate final summary report for the batch.
        """
        summary = get_status(self.batch_id)

        report_lines = [
            "",
            "=" * 60,
            "BATCH COMPLETE - FINAL REPORT",
            "=" * 60,
            f"Batch ID:    {summary['batch_id']}",
            f"Total:       {summary['total']}",
            f"Completed:   {summary['completed']}",
            f"Failed:      {summary['failed']}",
            f"Success %:   {summary['completed'] / summary['total'] * 100:.1f}%",
        ]

        if summary['failed'] > 0:
            report_lines.append("\nFailed tickers:")
            for ticker, info in summary['tasks'].items():
                if info['status'] == 'failed':
                    report_lines.append(f"  - {ticker}: {info.get('error', 'Unknown error')}")

        report_lines.append("=" * 60)

        # Log as single message
        logger.info("\n".join(report_lines))

    def stop(self):
        """Signal judge to stop."""
        self.running = False


# =============================================================================
# Orchestrator: Coordinate workers and judge
# =============================================================================

class Orchestrator:
    """
    Main coordinator that manages the worker pool and judge.

    Implements Cursor's Planner-Worker-Judge pattern with local
    Claude Code processes.
    """

    SHUTDOWN_TIMEOUT = 30  # seconds to wait for graceful shutdown

    def __init__(
        self,
        tickers: List[str],
        num_workers: int = DEFAULT_WORKERS,
        prompt_version: float = DEFAULT_PROMPT_VERSION,
        batch_id: Optional[str] = None
    ):
        self.tickers = tickers
        self.num_workers = min(num_workers, MAX_WORKERS)
        self.prompt_version = prompt_version
        self.batch_id = batch_id
        self.workers: List[Worker] = []
        self.judge: Optional[Judge] = None
        self.executor: Optional[ThreadPoolExecutor] = None
        self._shutdown_requested = False

    def run(self):
        """
        Execute the full orchestration cycle.

        1. Plan: Create batch with tasks
        2. Execute: Spawn workers in parallel
        3. Judge: Validate completed reports
        """
        # Handle graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        # Phase 1: Plan
        if not self.batch_id:
            self.batch_id = plan_batch(
                self.tickers,
                prompt_version=self.prompt_version
            )

        logger.info(f"\nOrchestrator started")
        logger.info(f"  Batch:   {self.batch_id}")
        logger.info(f"  Tickers: {len(self.tickers)}")
        logger.info(f"  Workers: {self.num_workers}")
        logger.info(f"  Mode:    Claude Code")

        # Phase 2: Execute with workers
        self.executor = ThreadPoolExecutor(max_workers=self.num_workers + 1)
        futures = []

        # Start workers
        for i in range(self.num_workers):
            worker_id = f"W{i+1:02d}"
            worker = Worker(
                self.batch_id,
                worker_id,
                self.prompt_version
            )
            self.workers.append(worker)
            futures.append(self.executor.submit(worker.run))

        # Phase 3: Start judge
        self.judge = Judge(self.batch_id)
        futures.append(self.executor.submit(self.judge.run))

        # Wait for all to complete with timeout handling
        try:
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Error in worker/judge: {e}", exc_info=True)
        finally:
            self._cleanup()

    def _cleanup(self):
        """Clean up resources with timeout."""
        if self.executor:
            logger.info("Shutting down executor...")
            # Python 3.9+ supports cancel_futures parameter
            try:
                self.executor.shutdown(wait=True, cancel_futures=False)
            except TypeError:
                # Python < 3.9
                self.executor.shutdown(wait=True)
            logger.info("Executor shutdown complete")

    def _handle_shutdown(self, signum, frame):
        """Handle graceful shutdown on SIGINT/SIGTERM."""
        if self._shutdown_requested:
            logger.warning("Force shutdown requested")
            sys.exit(1)

        self._shutdown_requested = True
        logger.info("\nShutdown requested, stopping workers...")

        for worker in self.workers:
            worker.stop()
        if self.judge:
            self.judge.stop()

        # Give workers time to finish current task
        logger.info(f"Waiting up to {self.SHUTDOWN_TIMEOUT}s for graceful shutdown...")


# =============================================================================
# Logging Setup
# =============================================================================

def setup_logging(batch_id: Optional[str] = None, verbose: bool = False):
    """
    Configure logging for the orchestrator.

    Args:
        batch_id: Optional batch ID for log file naming
        verbose: If True, set DEBUG level; otherwise INFO
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s [%(threadName)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Optionally add file handler for batch-specific logs
    if batch_id:
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"batch_{batch_id}.log"
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(threadName)s] %(levelname)s: %(message)s'
        ))
        logging.getLogger().addHandler(file_handler)


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Multi-agent orchestrator for investment report generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Ticker selection
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--djia', action='store_true',
        help='Generate reports for Dow 30 companies'
    )
    group.add_argument(
        '--sp100', action='store_true',
        help='Generate reports for S&P 100 companies'
    )
    group.add_argument(
        '--sp500', action='store_true',
        help='Generate reports for S&P 500 companies (caution: 500 reports)'
    )
    group.add_argument(
        '--test', action='store_true',
        help='Generate reports for test tickers (AAPL, MSFT, F, NVDA)'
    )
    group.add_argument(
        '--resume', metavar='BATCH_ID',
        help='Resume an existing batch'
    )
    group.add_argument(
        '--status', metavar='BATCH_ID',
        help='Check status of a batch'
    )
    parser.add_argument(
        'tickers', nargs='*',
        help='Specific tickers to process'
    )

    # Worker configuration
    parser.add_argument(
        '--workers', '-w', type=int, default=DEFAULT_WORKERS,
        help=f'Number of parallel workers (default: {DEFAULT_WORKERS}, max: {MAX_WORKERS})'
    )
    parser.add_argument(
        '--prompt-version', type=float, default=DEFAULT_PROMPT_VERSION,
        help=f'Prompt template version (default: {DEFAULT_PROMPT_VERSION})'
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Enable verbose (DEBUG) logging'
    )

    args = parser.parse_args()

    # Initialize logging early
    setup_logging(verbose=args.verbose)

    # Handle status check
    if args.status:
        summary = get_status(args.status)
        if not summary:
            print(f"Batch {args.status} not found")
            return
        print(json.dumps(summary, indent=2))
        return

    # Determine tickers
    tickers = []
    batch_id = None

    if args.resume:
        batch_id = args.resume
        state = TaskStateManager().read_state(batch_id)
        if not state:
            print(f"Batch {batch_id} not found")
            return
        # Tickers already in batch
        tickers = list(state.tasks.keys())
        print(f"Resuming batch {batch_id} with {len(tickers)} tickers")

    elif args.djia:
        tickers = get_index_tickers('DJIA')
    elif args.sp100:
        tickers = get_index_tickers('SP100')
    elif args.sp500:
        tickers = get_index_tickers('SP500')
    elif args.test:
        tickers = get_test_tickers()
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        parser.print_help()
        return

    if not tickers and not batch_id:
        print("No tickers specified")
        return

    # Run orchestrator
    orchestrator = Orchestrator(
        tickers=tickers,
        num_workers=args.workers,
        prompt_version=args.prompt_version,
        batch_id=batch_id
    )
    orchestrator.run()


if __name__ == '__main__':
    main()
