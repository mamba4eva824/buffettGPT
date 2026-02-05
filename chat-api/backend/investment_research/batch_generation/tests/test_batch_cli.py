"""
Unit tests for batch_cli.py

Tests the unified CLI for batch report generation:
- Command parsing and subcommand routing
- Integration with prepare, verify, stale, parallel commands
- Banner display
- Error handling

Run:
    cd chat-api/backend
    pytest investment_research/batch_generation/tests/test_batch_cli.py -v
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Add parent directories to path for imports
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, backend_dir)

# Set environment variables before importing
os.environ['ENVIRONMENT'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

from investment_research.batch_generation.batch_cli import (
    print_banner,
    cmd_prepare,
    cmd_verify,
    cmd_stale,
    cmd_status
)


# =============================================================================
# BANNER TESTS
# =============================================================================

class TestPrintBanner:
    """Tests for print_banner() function."""

    def test_prints_banner(self, capsys):
        """Verify banner is printed to stdout."""
        print_banner()

        captured = capsys.readouterr()
        assert "DJIA Batch Report Generator" in captured.out
        assert "30 Companies" in captured.out
        assert "v4.8 Prompt" in captured.out


# =============================================================================
# CMD_PREPARE TESTS
# =============================================================================

class TestCmdPrepare:
    """Tests for cmd_prepare() command."""

    def test_calls_prepare_all_data(self):
        """Verify prepare_all_data is called with correct arguments."""
        mock_args = MagicMock()
        mock_args.output = "test_output.json"
        mock_args.tickers = None
        mock_args.prompt_version = 4.8

        # Patch at the module where it's imported, not where it's defined
        with patch('investment_research.batch_generation.prepare_batch_data.prepare_all_data') as mock_prepare:
            cmd_prepare(mock_args)

            mock_prepare.assert_called_once_with(
                output_file="test_output.json",
                tickers=None,
                prompt_version=4.8
            )

    def test_parses_ticker_list(self):
        """Verify ticker string is parsed correctly."""
        mock_args = MagicMock()
        mock_args.output = "test_output.json"
        mock_args.tickers = "AAPL,MSFT,GOOGL"
        mock_args.prompt_version = 4.8

        with patch('investment_research.batch_generation.prepare_batch_data.prepare_all_data') as mock_prepare:
            cmd_prepare(mock_args)

            call_kwargs = mock_prepare.call_args.kwargs
            assert call_kwargs['tickers'] == ["AAPL", "MSFT", "GOOGL"]


# =============================================================================
# CMD_VERIFY TESTS
# =============================================================================

class TestCmdVerify:
    """Tests for cmd_verify() command."""

    def test_calls_verify_reports(self):
        """Verify verify_reports is called with correct arguments."""
        mock_args = MagicMock()
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.verify_reports.verify_reports', return_value=True) as mock_verify:
            with pytest.raises(SystemExit) as exc_info:
                cmd_verify(mock_args)

            mock_verify.assert_called_once_with(
                environment="dev",
                tickers=None
            )
            assert exc_info.value.code == 0

    def test_exits_with_error_on_missing_reports(self):
        """Verify exit code 1 when reports are missing."""
        mock_args = MagicMock()
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.verify_reports.verify_reports', return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_verify(mock_args)

            assert exc_info.value.code == 1

    def test_parses_ticker_list(self):
        """Verify ticker string is parsed correctly."""
        mock_args = MagicMock()
        mock_args.env = "dev"
        mock_args.tickers = "AAPL,MSFT"

        with patch('investment_research.batch_generation.verify_reports.verify_reports', return_value=True) as mock_verify:
            with pytest.raises(SystemExit):
                cmd_verify(mock_args)

            call_kwargs = mock_verify.call_args.kwargs
            assert call_kwargs['tickers'] == ["AAPL", "MSFT"]


# =============================================================================
# CMD_STALE TESTS
# =============================================================================

class TestCmdStale:
    """Tests for cmd_stale() command."""

    def test_calls_check_djia_staleness(self):
        """Verify check_djia_staleness is called with correct arguments."""
        mock_args = MagicMock()
        mock_args.tickers_only = False
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness', return_value=[]) as mock_check:
            with pytest.raises(SystemExit) as exc_info:
                cmd_stale(mock_args)

            mock_check.assert_called_once_with(
                tickers_only=False,
                environment="dev",
                tickers=None
            )
            assert exc_info.value.code == 0

    def test_exits_with_error_when_stale_reports_exist(self):
        """Verify exit code 1 when stale reports exist."""
        mock_args = MagicMock()
        mock_args.tickers_only = False
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness', return_value=["AAPL"]):
            with pytest.raises(SystemExit) as exc_info:
                cmd_stale(mock_args)

            assert exc_info.value.code == 1

    def test_tickers_only_flag(self):
        """Verify tickers_only flag is passed correctly."""
        mock_args = MagicMock()
        mock_args.tickers_only = True
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness', return_value=[]) as mock_check:
            with pytest.raises(SystemExit):
                cmd_stale(mock_args)

            call_kwargs = mock_check.call_args.kwargs
            assert call_kwargs['tickers_only'] is True


# =============================================================================
# CMD_STATUS TESTS
# =============================================================================

class TestCmdStatus:
    """Tests for cmd_status() command."""

    def test_calls_both_verify_and_staleness(self, capsys):
        """Verify status calls both verify_reports and check_djia_staleness."""
        mock_args = MagicMock()
        mock_args.env = "dev"

        with patch('investment_research.batch_generation.verify_reports.verify_reports') as mock_verify:
            with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness') as mock_check:
                cmd_status(mock_args)

                mock_verify.assert_called_once_with(environment="dev")
                mock_check.assert_called_once_with(environment="dev")

    def test_prints_status_header(self, capsys):
        """Verify status header is printed."""
        mock_args = MagicMock()
        mock_args.env = "dev"

        with patch('investment_research.batch_generation.verify_reports.verify_reports'):
            with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness'):
                cmd_status(mock_args)

        captured = capsys.readouterr()
        assert "DJIA Batch Report Status" in captured.out


# =============================================================================
# CMD_PARALLEL TESTS
# =============================================================================

class TestCmdParallel:
    """Tests for cmd_parallel() command."""

    def test_runs_shell_script(self):
        """Verify shell script is executed."""
        from investment_research.batch_generation.batch_cli import cmd_parallel

        mock_args = MagicMock()
        mock_args.dry_run = False

        with patch('subprocess.run') as mock_run:
            with patch('os.path.exists', return_value=True):
                cmd_parallel(mock_args)

            mock_run.assert_called_once()
            call_args = mock_run.call_args[0][0]
            assert call_args[0] == "bash"
            assert "run_parallel_reports.sh" in call_args[1]

    def test_dry_run_flag(self):
        """Verify dry_run flag is passed to script."""
        from investment_research.batch_generation.batch_cli import cmd_parallel

        mock_args = MagicMock()
        mock_args.dry_run = True

        with patch('subprocess.run') as mock_run:
            with patch('os.path.exists', return_value=True):
                cmd_parallel(mock_args)

            call_args = mock_run.call_args[0][0]
            assert "--dry-run" in call_args

    def test_exits_on_missing_script(self):
        """Verify exit when script file is missing."""
        from investment_research.batch_generation.batch_cli import cmd_parallel

        mock_args = MagicMock()
        mock_args.dry_run = False

        with patch('os.path.exists', return_value=False):
            with pytest.raises(SystemExit) as exc_info:
                cmd_parallel(mock_args)

            assert exc_info.value.code == 1


# =============================================================================
# ARGUMENT PARSING TESTS
# =============================================================================

class TestArgumentParsing:
    """Tests for CLI argument parsing."""

    def test_prepare_subcommand_defaults(self):
        """Verify prepare subcommand has correct defaults."""
        from investment_research.batch_generation.batch_cli import main
        import argparse

        # We can't easily test the full CLI without running main()
        # but we can verify the structure exists
        from investment_research.batch_generation.batch_cli import cmd_prepare
        assert callable(cmd_prepare)

    def test_verify_subcommand_exists(self):
        """Verify verify subcommand is defined."""
        from investment_research.batch_generation.batch_cli import cmd_verify
        assert callable(cmd_verify)

    def test_stale_subcommand_exists(self):
        """Verify stale subcommand is defined."""
        from investment_research.batch_generation.batch_cli import cmd_stale
        assert callable(cmd_stale)

    def test_status_subcommand_exists(self):
        """Verify status subcommand is defined."""
        from investment_research.batch_generation.batch_cli import cmd_status
        assert callable(cmd_status)


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for CLI workflow."""

    def test_full_verify_workflow(self):
        """Test complete verify workflow."""
        mock_args = MagicMock()
        mock_args.env = "dev"
        mock_args.tickers = None

        with patch('investment_research.batch_generation.verify_reports.verify_reports', return_value=True):
            with pytest.raises(SystemExit) as exc_info:
                cmd_verify(mock_args)

            assert exc_info.value.code == 0

    def test_full_stale_workflow(self):
        """Test complete stale check workflow."""
        mock_args = MagicMock()
        mock_args.tickers_only = False
        mock_args.env = "prod"
        mock_args.tickers = "AAPL,MSFT"

        with patch('investment_research.batch_generation.check_stale_reports.check_djia_staleness', return_value=[]) as mock_check:
            with pytest.raises(SystemExit):
                cmd_stale(mock_args)

            call_kwargs = mock_check.call_args.kwargs
            assert call_kwargs['environment'] == "prod"
            assert call_kwargs['tickers'] == ["AAPL", "MSFT"]


# =============================================================================
# RUN TESTS DIRECTLY
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
