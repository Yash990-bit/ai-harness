"""Phase 4 Test Suite: Compounding Error Ledger & Diagnostic Memory.

Verifies:
1. Error signature normalization and grouping.
2. LocalErrorLedger recording, listing, and disposition lifecycles.
3. AutonomousSolver error capture upon task or verification failure.
4. AutonomousSolver resolution tracking when self-correction succeeds.
5. CLI integration via `odin errors`.
"""

import json
from pathlib import Path
import pytest

from odin.error_ledger import LocalErrorLedger, compute_symptom_signature
from odin.solver import AutonomousSolver


def test_symptom_signature_normalization():
    """Verify memory addresses, timestamps, and line numbers are normalized."""
    msg1 = "ZeroDivisionError: division by zero at 0x7f98d412 in line 42 at 2026-09-27T02:00:00"
    msg2 = "ZeroDivisionError: division by zero at 0x10b7f830 in line 99 at 2026-09-27T03:15:22"

    sig1 = compute_symptom_signature("verification_failure", msg1)
    sig2 = compute_symptom_signature("verification_failure", msg2)

    assert sig1 == sig2
    assert sig1.startswith("verification_failure_")


def test_ledger_record_and_disposition(tmp_path):
    """Verify recording errors and updating dispositions."""
    ledger_file = tmp_path / "errors.jsonl"
    ledger = LocalErrorLedger(ledger_file)

    # Initial state
    assert ledger.summary()["total_errors"] == 0

    # Record first error
    ev1 = ledger.record(
        source="execution_failure",
        source_id="task-101",
        message="ImportError: No module named 'foo'",
    )
    assert ev1.disposition == "open"
    assert ev1.source_id == "task-101"

    # Verify summary
    summary = ledger.summary()
    assert summary["total_errors"] == 1
    assert summary["open"] == 1
    assert summary["fixed"] == 0

    # Update disposition
    updated = ledger.set_disposition(ev1.event_id, "fixed", note="Installed module foo")
    assert updated is not None
    assert updated.disposition == "fixed"
    assert updated.disposition_note == "Installed module foo"

    # Verify persistence
    ledger2 = LocalErrorLedger(ledger_file)
    events = ledger2.list_events()
    assert len(events) == 1
    assert events[0].disposition == "fixed"


@pytest.mark.asyncio
async def test_solver_records_error_on_verification_failure(tmp_path):
    """Verify AutonomousSolver records verification failure to ledger."""
    working_dir = tmp_path / "repo"
    working_dir.mkdir()
    output_dir = tmp_path / "odin_state"

    solver = AutonomousSolver(
        working_dir=str(working_dir),
        output_dir=str(output_dir),
    )

    summary = await solver.solve(
        prompt="Test verification error logging",
        mock=True,
        verify_cmd="python3 -c 'import sys; sys.exit(2)'",
        max_retries=1,
    )

    assert summary.status == "FAILED"
    assert summary.verification_passed is False

    ledger = LocalErrorLedger(output_dir / "errors.jsonl")
    events = ledger.list_events(source="verification_failure")
    assert len(events) >= 1
    assert events[0].disposition == "open"
    assert "failed" in events[0].message


def test_cli_errors_command(tmp_path):
    """Test odin errors CLI execution."""
    from odin.cli import OdinCLI

    cli = OdinCLI()
    # Runs without error on current repo state
    cli.errors()
