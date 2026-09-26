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


def test_prompt_for_initial_api_key_when_already_set():
    """Verify prompt is bypassed if API key already exists in environment."""
    from odin.tui import prompt_for_initial_api_key
    with patch.dict(os.environ, {"AI_API_KEY": "AIzaSyTestKey123"}):
        with patch("rich.prompt.Prompt.ask") as mock_ask:
            prompt_for_initial_api_key()
            mock_ask.assert_not_called()


def test_prompt_for_initial_api_key_when_entered():
    """Verify entered API key sets environment and maps credentials."""
    from odin.tui import prompt_for_initial_api_key
    env = os.environ.copy()
    env.pop("AI_API_KEY", None)
    env.pop("GEMINI_API_KEY", None)
    env.pop("DEEPSEEK_API_KEY", None)
    env.pop("AI_PROVIDER", None)
    with patch.dict(os.environ, env, clear=True):
        with patch("rich.prompt.Prompt.ask", return_value="AIzaSyNewGeminiKey"):
            prompt_for_initial_api_key()
            assert os.environ.get("AI_API_KEY") == "AIzaSyNewGeminiKey"
            assert os.environ.get("AI_PROVIDER") == "gemini"
