"""
Batch generation utilities for investment reports.

This package provides tools for generating investment reports for multiple
companies in parallel using Claude Code sessions.

Scripts:
- prepare_batch_data.py: Pre-fetch FMP financial data for all tickers
- run_parallel_reports.sh: Launch parallel Claude sessions via tmux
- verify_reports.py: Verify all reports exist in DynamoDB
- check_stale_reports.py: Check which reports need refresh
- batch_cli.py: Unified CLI for all batch operations
"""
