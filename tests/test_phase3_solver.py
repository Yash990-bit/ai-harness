"""Phase 3 Test Suite: Autonomous Solver & Patch Generation Engine.

Verifies:
1. AutonomousSolver initialization and directory creation (.odin/patches, .odin/reports).
2. End-to-end autonomous issue decomposition and execution in mock mode.
3. Verification command execution and reporting.
4. Self-correction retry logic upon verification failure.
5. Patch file generation and latest_summary.json telemetry reporting.
6. CLI integration via `odin solve`.
"""

import json
import os
import subprocess
from pathlib import Path
import pytest

from odin.config import load_config
from odin.solver import AutonomousSolver, SolverRunSummary


def test_solver_initialization(tmp_path):
    """Test solver initializes directories and forces local board backend."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "custom_odin"

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    assert solver.config.board_backend == "local"
    assert (output_dir / "patches").is_dir()
    assert (output_dir / "reports").is_dir()


@pytest.mark.asyncio
async def test_solver_mock_execution(tmp_path):
    """Test end-to-end mock solve produces tasks, patch, and telemetry summary."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "odin_state"

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    summary = await solver.solve(
        prompt="Fix IndexError in sequence parser when input is empty list",
        mock=True,
    )

    assert isinstance(summary, SolverRunSummary)
    assert summary.status == "SUCCESS"
    assert summary.tasks_count >= 2
    assert summary.tasks_completed >= 2
    assert summary.patch_path is not None
    assert Path(summary.patch_path).exists()
    assert summary.patch_path.endswith(".patch")

    # Verify latest_summary.json
    latest_json_path = output_dir / "reports" / "latest_summary.json"
    assert latest_json_path.exists()
    data = json.loads(latest_json_path.read_text(encoding="utf-8"))
    assert data["status"] == "SUCCESS"
    assert data["tasks_completed"] == summary.tasks_completed
    assert data["prompt_or_spec"].startswith("Fix IndexError")


@pytest.mark.asyncio
async def test_solver_with_passing_verification(tmp_path):
    """Test solver with a passing verification command."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "odin_state"

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    summary = await solver.solve(
        prompt="Add unit tests for string utility",
        mock=True,
        verify_cmd="python3 -c 'exit(0)'",
    )

    assert summary.status == "SUCCESS"
    assert summary.verification_passed is True


@pytest.mark.asyncio
async def test_solver_with_failing_verification_self_correction(tmp_path):
    """Test solver attempts self-correction when verification command fails."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "odin_state"

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    # Command fails: python3 -c 'exit(1)'
    summary = await solver.solve(
        prompt="Implement self-correcting logic",
        mock=True,
        verify_cmd="python3 -c 'import sys; sys.exit(1)'",
        max_retries=2,
    )

    # Verification persistently fails, so run status should be FAILED
    assert summary.status == "FAILED"
    assert summary.verification_passed is False


@pytest.mark.asyncio
async def test_solver_spec_file_input(tmp_path):
    """Test solver loads issue description from specification file."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "odin_state"

    spec_file = tmp_path / "issue_description.md"
    spec_file.write_text("# Bug Report\nDivision by zero occurs in calculate_ratio()", encoding="utf-8")

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    summary = await solver.solve(
        spec_file=str(spec_file),
        mock=True,
    )

    assert summary.status == "SUCCESS"
    assert "Division by zero occurs" in summary.prompt_or_spec


def test_cli_solve_integration(tmp_path):
    """Test invoking `odin solve` through CLI entrypoint."""
    from odin.cli import OdinCLI

    cli = OdinCLI()
    # Execute solve in mock mode
    cli.solve(
        prompt="CLI autonomous issue resolution test",
        mock=True,
    )

    latest_report = Path(".odin/reports/latest_summary.json")
    assert latest_report.exists()
    data = json.loads(latest_report.read_text(encoding="utf-8"))
    assert data["status"] == "SUCCESS"
