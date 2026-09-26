"""Autonomous SWE issue-solving & patch-generation engine.

Executes end-to-end:
1. Issue Ingestion & Planning
2. Dependency-aware task execution
3. Verification & self-correction loop
4. Solution patch generation & execution telemetry
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from odin.config import load_config
from odin.error_ledger import LocalErrorLedger
from odin.models import OdinConfig
from odin.orchestrator import Orchestrator
from odin.taskit.models import Task, TaskStatus

logger = logging.getLogger("odin.solver")


@dataclass
class SolverRunSummary:
    """Summary of an autonomous solver run."""
    status: str  # "SUCCESS" | "FAILED" | "NO_CHANGES"
    prompt_or_spec: str
    patch_path: Optional[str] = None
    tasks_count: int = 0
    tasks_completed: int = 0
    duration_seconds: float = 0.0
    verification_passed: bool = False
    verification_output: str = ""
    diff_stats: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AutonomousSolver:
    """Coordinates autonomous issue resolution, testing, and patch creation."""

    def __init__(
        self,
        config: Optional[OdinConfig] = None,
        working_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
    ):
        cfg = config or load_config()
        if cfg.board_backend != "local":
            cfg = cfg.model_copy(update={"board_backend": "local"})
        if "mock" not in cfg.agents:
            from odin.models import AgentConfig, CostTier
            cfg.agents["mock"] = AgentConfig(
                cli_command="mock",
                capabilities=["coding", "writing"],
                cost_tier=CostTier.LOW,
                models={"mock-model": "default mock"},
                default_model="mock-model",
            )
        self.config = cfg
        self.working_dir = Path(working_dir or os.getcwd()).resolve()
        self.output_dir = Path(output_dir or (self.working_dir / ".odin")).resolve()
        self.patches_dir = self.output_dir / "patches"
        self.reports_dir = self.output_dir / "reports"
        self.patches_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.error_ledger = LocalErrorLedger(self.output_dir / "errors.jsonl")

    def _get_git_diff(self) -> str:
        """Capture current unstaged and staged git diff."""
        try:
            res = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            return res.stdout
        except Exception as exc:
            logger.warning("Failed to capture git diff: %s", exc)
            return ""

    def _get_diff_stats(self) -> Dict[str, Any]:
        """Get summary statistics of modified files."""
        try:
            res = subprocess.run(
                ["git", "diff", "--shortstat", "HEAD"],
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                check=False,
            )
            output = res.stdout.strip()
            return {"shortstat": output}
        except Exception:
            return {}

    def _run_verification(self, verify_cmd: str) -> tuple[bool, str]:
        """Execute a verification command (e.g. pytest suite)."""
        logger.info("Running verification command: %s", verify_cmd)
        try:
            res = subprocess.run(
                shlex.split(verify_cmd),
                cwd=str(self.working_dir),
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            combined = f"{res.stdout}\n{res.stderr}".strip()
            return (res.returncode == 0, combined)
        except subprocess.TimeoutExpired:
            return (False, "Verification timed out after 300s")
        except Exception as exc:
            return (False, f"Verification failed with exception: {exc}")

    async def solve(
        self,
        prompt: Optional[str] = None,
        spec_file: Optional[str] = None,
        mock: bool = False,
        verify_cmd: Optional[str] = None,
        output_patch: Optional[str] = None,
        max_retries: int = 2,
    ) -> SolverRunSummary:
        """Execute autonomous resolution flow for an issue or specification."""
        start_time = time.monotonic()
        target_description = prompt
        if spec_file:
            path = Path(spec_file)
            if path.exists():
                target_description = path.read_text(encoding="utf-8")
            else:
                target_description = f"Spec file: {spec_file}"

        if not target_description:
            raise ValueError("Either prompt or spec_file must be provided.")

        orch = Orchestrator(self.config)

        # Step 1: Decompose problem into tasks
        logger.info("Planning tasks for issue...")
        if mock:
            # Deterministic mock planning for testing & benchmarking
            from odin.harnesses.mock import MockHarness
            from odin.harnesses.registry import HARNESS_REGISTRY
            for name in list(self.config.agents.keys()):
                HARNESS_REGISTRY[name] = MockHarness

            spec_id = f"mock-spec-{int(time.time())}"
            tasks = [
                Task(
                    id=f"{spec_id}-1",
                    title="Isolate issue & reproduce test",
                    description=f"Reproduce: {target_description[:100]}",
                    assigned_agent="mock",
                    status=TaskStatus.TODO,
                ),
                Task(
                    id=f"{spec_id}-2",
                    title="Apply minimal surgical patch",
                    description="Implement fix adhering to existing repo patterns",
                    assigned_agent="mock",
                    status=TaskStatus.TODO,
                ),
            ]
            for t in tasks:
                orch.task_mgr._create(t)
        else:
            try:
                spec_id, tasks = await orch.plan(
                    spec=target_description,
                    spec_file=spec_file,
                    mode="quiet",
                    quick=True,
                )
            except Exception as exc:
                logger.warning("Planning fallback: creating direct execution task: %s", exc)
                spec_id = f"auto-spec-{int(time.time())}"
                agent_name = self.config.forced_base_provider or "gemini"
                tasks = [
                    Task(
                        id=f"{spec_id}-1",
                        title="Autonomous Issue Resolution",
                        description=target_description,
                        assigned_agent=agent_name,
                        status=TaskStatus.TODO,
                    )
                ]
                for t in tasks:
                    orch.task_mgr._create(t)

        # Step 2: Execute tasks in sequence
        completed = 0
        execution_errors = []
        for task in tasks:
            logger.info("Executing task %s: %s", task.id, task.title)
            try:
                res = await orch.exec_task(task.id, mock=mock)
                if res.get("success", False):
                    completed += 1
                    try:
                        orch.task_mgr.update_status(task.id, TaskStatus.DONE)
                    except Exception:
                        pass
                else:
                    err = res.get("error") or "Unknown error"
                    execution_errors.append(f"Task {task.id} failed: {err}")
                    self.error_ledger.record(
                        source="execution_failure",
                        source_id=task.id,
                        message=str(err),
                        metadata={"spec_id": spec_id, "title": task.title},
                    )
            except Exception as exc:
                execution_errors.append(f"Task {task.id} exception: {exc}")
                self.error_ledger.record(
                    source="execution_failure",
                    source_id=task.id,
                    message=str(exc),
                    metadata={"spec_id": spec_id, "title": task.title},
                )

        # Step 3: Verification (if verify_cmd provided)
        verification_passed = True
        verification_output = ""
        last_error_event = None
        if verify_cmd:
            verification_passed, verification_output = self._run_verification(verify_cmd)
            if not verification_passed:
                last_error_event = self.error_ledger.record(
                    source="verification_failure",
                    source_id=spec_id,
                    message=f"Command `{verify_cmd}` failed: {verification_output[:250]}",
                    traceback=verification_output,
                    metadata={"verify_cmd": verify_cmd},
                )

            # Simple self-correction retry if verification failed
            retries = 0
            while not verification_passed and retries < max_retries:
                retries += 1
                logger.info("Verification failed. Starting self-correction attempt %d/%d...", retries, max_retries)
                repair_task = Task(
                    id=f"{spec_id}-repair-{retries}",
                    title=f"Repair and Fix: Attempt {retries}",
                    description=(
                        f"The verification command `{verify_cmd}` failed with:\n"
                        f"```\n{verification_output[-1000:]}\n```\n"
                        f"Modify the source code to resolve this failure."
                    ),
                    assigned_agent=tasks[0].assigned_agent or "gemini",
                    status=TaskStatus.TODO,
                )
                orch.task_mgr._create(repair_task)
                try:
                    await orch.exec_task(repair_task.id, mock=mock)
                except Exception:
                    pass
                verification_passed, verification_output = self._run_verification(verify_cmd)
                if verification_passed and last_error_event:
                    self.error_ledger.set_disposition(
                        last_error_event.event_id,
                        "fixed",
                        note=f"Self-corrected on attempt {retries}",
                    )

        # Step 4: Export solution patch
        diff_text = self._get_git_diff()
        patch_file_path = None
        if output_patch:
            target_patch = Path(output_patch)
        else:
            target_patch = self.patches_dir / f"{spec_id}.patch"

        if diff_text:
            target_patch.write_text(diff_text, encoding="utf-8")
            patch_file_path = str(target_patch)
        elif mock:
            # For mock mode, generate a mock patch to verify output pipeline
            mock_patch = f"# Mock Solution Patch for {spec_id}\n# Target: {target_description[:50]}\n"
            target_patch.write_text(mock_patch, encoding="utf-8")
            patch_file_path = str(target_patch)

        elapsed = round(time.monotonic() - start_time, 2)
        status = "SUCCESS" if (completed > 0 and verification_passed) else "FAILED"
        if completed == 0:
            status = "FAILED"

        summary = SolverRunSummary(
            status=status,
            prompt_or_spec=target_description[:200],
            patch_path=patch_file_path,
            tasks_count=len(tasks),
            tasks_completed=completed,
            duration_seconds=elapsed,
            verification_passed=verification_passed,
            verification_output=verification_output[:500],
            diff_stats=self._get_diff_stats(),
            metadata={"errors": execution_errors} if execution_errors else {},
        )

        # Write summary report JSON
        report_file = self.reports_dir / f"{spec_id}_summary.json"
        report_file.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

        # Also write latest summary symlink/copy
        latest_report = self.reports_dir / "latest_summary.json"
        latest_report.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

        return summary
