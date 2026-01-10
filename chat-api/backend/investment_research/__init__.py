"""
Investment Research Feature - Report Generation Tools

This package provides tools for generating and caching investment analysis reports
using Claude Code (or optionally the Anthropic API).

Components:
- generate_report.py: CLI tool for batch report generation
- report_generator.py: ReportGenerator class with prepare_data() and save_report()
- index_tickers.py: DJIA and S&P 500 ticker lists

Usage (Claude Code mode):
    from investment_research.report_generator import ReportGenerator

    generator = ReportGenerator(use_api=False)
    data = generator.prepare_data('AAPL')
    # Claude Code analyzes data and generates report
    generator.save_report('AAPL', 2026, report_content, ratings, data['features'])

Usage (CLI):
    python -m investment_research.generate_report AAPL
    python -m investment_research.generate_report --djia --dry-run
"""

from .report_generator import ReportGenerator
from .index_tickers import get_index_tickers, get_test_tickers, DJIA_TICKERS, SP500_TICKERS

__all__ = [
    'ReportGenerator',
    'get_index_tickers',
    'get_test_tickers',
    'DJIA_TICKERS',
    'SP500_TICKERS',
]
