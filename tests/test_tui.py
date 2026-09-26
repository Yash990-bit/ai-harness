"""Tests for AI Harness Interactive Terminal User Interface (TUI)."""

import os
from pathlib import Path
from unittest.mock import patch
import pytest

from odin.tui import (
    display_header,
    run_benchmark_demo,
    view_error_ledger,
    launch_interactive_tui,
)


def test_display_header_renders():
    """Verify header prints with environment variables."""
    with patch.dict(os.environ, {"AI_PROVIDER": "gemini", "AI_MODEL": "gemini-2.5-flash"}):
        display_header()


def test_run_benchmark_demo(tmp_path):
    """Verify demo run executes in mock mode and creates telemetry."""
    run_benchmark_demo()
    latest_report = Path(".odin/reports/latest_summary.json")
    assert latest_report.exists()


def test_view_error_ledger():
    """Verify view_error_ledger prints without error."""
    view_error_ledger()


def test_tui_non_interactive():
    """Verify launch_interactive_tui exits safely when stdin is not a tty."""
    with patch("sys.stdin.isatty", return_value=False):
        launch_interactive_tui()


def test_cli_tui_command():
    """Verify OdinCLI().tui invokes non-interactive launch when tested headlessly."""
    from odin.cli import OdinCLI
    cli = OdinCLI()
    with patch("sys.stdin.isatty", return_value=False):
        cli.tui()
