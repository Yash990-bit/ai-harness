"""Textual-based Graphical Terminal User Interface for AI Harness.

Provides a full-screen, mouse-friendly, interactive dashboard for:
- Monitoring harness environment, provider status, and active models
- Launching autonomous problem solving and real-time patch generation
- Viewing generated patches with syntax-highlighted diffs
- Inspecting the compounding error ledger
- Running system diagnostics and test suites
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    Switch,
    TabbedContent,
    TabPane,
)

from odin.config import map_hackathon_credentials
from odin.solver import AutonomousSolver


APP_CSS = """
Screen {
    background: #0d1117;
    color: #c9d1d9;
}

Header {
    background: #161b22;
    color: #58a6ff;
    dock: top;
    height: 3;
}

Footer {
    background: #161b22;
    color: #8b949e;
    dock: bottom;
    height: 1;
}

TabbedContent {
    height: 1fr;
}

TabPane {
    padding: 1 2;
}

.card {
    background: #161b22;
    border: solid #30363d;
    padding: 1 2;
    margin-bottom: 1;
}

.title-label {
    text-style: bold;
    color: #58a6ff;
    margin-bottom: 1;
}

.status-badge-ok {
    color: #3fb950;
    text-style: bold;
}

.status-badge-warn {
    color: #d29922;
    text-style: bold;
}

.button-bar {
    height: auto;
    margin-top: 1;
    margin-bottom: 1;
}

Button {
    margin-right: 1;
}

Input {
    background: #0d1117;
    border: solid #30363d;
    color: #f0f6fc;
    margin-bottom: 1;
}

Input:focus {
    border: solid #58a6ff;
}

RichLog {
    background: #0d1117;
    border: solid #30363d;
    color: #e6edf3;
    height: 1fr;
    min-height: 10;
}

DataTable {
    background: #0d1117;
    border: solid #30363d;
    height: 1fr;
}

.patch-split {
    height: 1fr;
}

.switch-container {
    height: auto;
    align-vertical: middle;
    margin-bottom: 1;
}

.switch-label {
    margin-left: 1;
    color: #8b949e;
}
"""


class AIHarnessTextualApp(App):
    """Full-screen interactive Textual application for AI Harness evaluation."""

    TITLE = "AI Harness — Autonomous Software Engineering Platform"
    SUB_TITLE = "LCC × DevClub Hackathon 2026 Evaluation Hub"
    CSS = APP_CSS

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("d", "switch_tab('tab-overview')", "Overview"),
        ("s", "switch_tab('tab-solver')", "Solver"),
        ("p", "switch_tab('tab-patches')", "Patches"),
        ("e", "switch_tab('tab-errors')", "Error Ledger"),
        ("b", "trigger_benchmark", "Fast Demo"),
    ]

    def compose(self) -> ComposeResult:
        """Compose the layout of the application."""
        yield Header(show_clock=True)

        with TabbedContent(id="tabs"):
            # TAB 1: OVERVIEW & BENCHMARK
            with TabPane("📊 Overview & Dashboard", id="tab-overview"):
                with Vertical(classes="card"):
                    yield Label("System Status & Environment", classes="title-label")
                    yield Static(id="env-status-static")
                    with Horizontal(classes="button-bar"):
                        yield Button("🧪 Run Fast SWE Benchmark", id="btn-overview-benchmark", variant="success")
                        yield Button("🩺 System Diagnostics", id="btn-overview-doctor", variant="primary")
                        yield Button("🧹 Clean Temporary State", id="btn-overview-clean", variant="error")
                yield Label("Live Activity Log:", classes="title-label")
                yield RichLog(id="overview-log", highlight=True, markup=True)

            # TAB 2: AUTONOMOUS SOLVER
            with TabPane("🚀 Autonomous Solver", id="tab-solver"):
                with Vertical(classes="card"):
                    yield Label("Submit Engineering Issue or Problem Prompt", classes="title-label")
                    yield Input(
                        placeholder="e.g. Write a python function to compute factorial and handle negative numbers",
                        id="input-task-prompt",
                    )
                    yield Input(
                        placeholder="Verification command (optional, e.g. python3 -c 'print(\"Tests passed\")')",
                        id="input-verify-cmd",
                    )
                    with Horizontal(classes="switch-container"):
                        yield Switch(id="switch-mock-mode", value=False)
                        yield Label(" Mock Mode (Zero Cost, Offline Deterministic Run)", classes="switch-label")
                    with Horizontal(classes="button-bar"):
                        yield Button("🚀 Execute Autonomous Solver", id="btn-run-solver", variant="primary")
                yield Label("Solver Execution Telemetry:", classes="title-label")
                yield RichLog(id="solver-log", highlight=True, markup=True)

            # TAB 3: GENERATED PATCHES
            with TabPane("📜 Solution Patches", id="tab-patches"):
                with Horizontal(classes="button-bar"):
                    yield Button("🔄 Refresh Patches", id="btn-refresh-patches", variant="default")
                    yield Label(" (Select a patch in the table to inspect syntax-highlighted diff)", classes="switch-label")
                with Horizontal(classes="patch-split"):
                    yield DataTable(id="table-patches", cursor_type="row")
                    yield RichLog(id="patch-preview-log", highlight=True, markup=True)

            # TAB 4: COMPOUNDING ERROR LEDGER
            with TabPane("📈 Compounding Error Ledger", id="tab-errors"):
                with Horizontal(classes="button-bar"):
                    yield Button("🔄 Refresh Ledger", id="btn-refresh-errors", variant="default")
                    yield Label(" Records, clusters & resolves regression patterns across execution runs", classes="switch-label")
                yield DataTable(id="table-errors", cursor_type="row")

            # TAB 5: TEST SUITE GATE
            with TabPane("🧪 Verification Test Suites", id="tab-tests"):
                with Vertical(classes="card"):
                    yield Label("Continuous Quality Gate (make test)", classes="title-label")
                    yield Label("Executes all hackathon baseline tests, integration tests, and Odin unit suites.")
                    with Horizontal(classes="button-bar"):
                        yield Button("▶ Run All Test Suites", id="btn-run-tests", variant="success")
                yield RichLog(id="tests-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize data tables and update status on mount."""
        map_hackathon_credentials()
        self.update_environment_status()
        self.init_patches_table()
        self.init_errors_table()
        self.refresh_patches_data()
        self.refresh_errors_data()

        log = self.query_one("#overview-log", RichLog)
        log.write("[bold green]✓ AI Harness Textual Engine Initialized.[/bold green]")
        log.write("[dim]Press 'd' for Dashboard, 's' for Solver, 'p' for Patches, 'e' for Errors, 'b' for Benchmark.[/dim]")

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch active tab via keyboard shortcut."""
        tabs = self.query_one("#tabs", TabbedContent)
        tabs.active = tab_id

    def action_trigger_benchmark(self) -> None:
        """Trigger fast benchmark demo via shortcut."""
        self.action_switch_tab("tab-overview")
        self.run_benchmark_task()

    def update_environment_status(self) -> None:
        """Render active environment details."""
        provider = os.getenv("AI_PROVIDER") or "gemini"
        api_key = os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            masked = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 12 else "configured"
            key_status = f"[bold green]Active[/bold green] ({masked})"
        else:
            key_status = "[bold yellow]Missing (Run in Mock or export AI_API_KEY)[/bold yellow]"

        model = os.getenv("AI_MODEL") or ("openrouter/free" if (api_key and api_key.startswith("sk-or-")) else ("deepseek-chat" if provider == "deepseek" else "gemini-2.5-flash"))

        status_text = (
            f"• [bold]AI Provider:[/bold] {provider}\n"
            f"• [bold]Model:[/bold] {model}\n"
            f"• [bold]API Credentials:[/bold] {key_status}\n"
            f"• [bold]Execution Architecture:[/bold] Git Worktree Isolation + Compounding Error Ledger"
        )
        self.query_one("#env-status-static", Static).update(status_text)

    # ─── BUTTON HANDLERS ─────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button click events across the UI."""
        btn_id = event.button.id
        if btn_id == "btn-overview-benchmark":
            self.run_benchmark_task()
        elif btn_id == "btn-overview-doctor":
            self.run_doctor_task()
        elif btn_id == "btn-overview-clean":
            self.run_clean_task()
        elif btn_id == "btn-run-solver":
            self.run_solver_task()
        elif btn_id == "btn-refresh-patches":
            self.refresh_patches_data()
        elif btn_id == "btn-refresh-errors":
            self.refresh_errors_data()
        elif btn_id == "btn-run-tests":
            self.run_test_suites_task()

    # ─── ASYNC WORKERS ───────────────────────────

    @work(thread=True)
    def run_benchmark_task(self) -> None:
        """Run the mock benchmark in a worker thread."""
        log = self.query_one("#overview-log", RichLog)
        log.write("\n[bold cyan]─── Launching Built-In Fast SWE Benchmark Demo (Mock Mode) ───[/bold cyan]")
        solver = AutonomousSolver()
        start = time.monotonic()
        try:
            summary = asyncio.run(
                solver.solve(
                    prompt="Refactor string parser to handle unicode and null byte boundaries safely",
                    mock=True,
                    verify_cmd="python3 -c 'exit(0)'",
                )
            )
            elapsed = time.monotonic() - start
            log.write(f"[bold green]✓ Benchmark SUCCESS in {elapsed:.2f}s![/bold green]")
            log.write(f"  • Tasks Completed: {summary.tasks_completed}/{summary.tasks_count}")
            if summary.patch_path:
                log.write(f"  • Generated Solution Patch: [cyan]{summary.patch_path}[/cyan]")
            log.write("  • Telemetry Persisted: [dim].odin/reports/latest_summary.json[/dim]")
            self.app.call_from_thread(self.refresh_patches_data)
        except Exception as e:
            log.write(f"[bold red]✗ Benchmark failed: {e}[/bold red]")

    @work(thread=True)
    def run_doctor_task(self) -> None:
        """Run system diagnostics."""
        log = self.query_one("#overview-log", RichLog)
        log.write("\n[bold cyan]─── System Doctor Diagnostics ───[/bold cyan]")
        res = subprocess.run(
            [sys.executable, "-m", "odin.cli", "doctor"],
            capture_output=True,
            text=True,
        )
        if res.stdout:
            for line in res.stdout.strip().splitlines():
                log.write(f"  {line}")
        if res.stderr:
            for line in res.stderr.strip().splitlines():
                log.write(f"  [dim yellow]{line}[/dim yellow]")
        log.write("[bold green]✓ Diagnostics completed.[/bold green]")

    @work(thread=True)
    def run_clean_task(self) -> None:
        """Clean generated state."""
        log = self.query_one("#overview-log", RichLog)
        log.write("\n[bold yellow]─── Cleaning Generated State & Artifacts ───[/bold yellow]")
        res = subprocess.run(["make", "clean"], capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.strip().splitlines():
                log.write(f"  {line}")
        log.write("[bold green]✓ State clean completed.[/bold green]")
        self.app.call_from_thread(self.refresh_patches_data)
        self.app.call_from_thread(self.refresh_errors_data)

    @work(thread=True)
    def run_solver_task(self) -> None:
        """Execute autonomous solver for the entered prompt."""
        prompt = self.query_one("#input-task-prompt", Input).value.strip()
        verify_cmd = self.query_one("#input-verify-cmd", Input).value.strip()
        mock_mode = self.query_one("#switch-mock-mode", Switch).value

        log = self.query_one("#solver-log", RichLog)
        if not prompt:
            log.write("[bold yellow]Please enter an issue description or problem prompt first.[/bold yellow]")
            return

        has_key = bool(os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
        if not has_key and not mock_mode:
            log.write("[yellow]No AI_API_KEY detected in environment. Switching to Mock Mode.[/yellow]")
            mock_mode = True

        provider_name = "Mock" if mock_mode else (os.getenv("AI_PROVIDER") or "gemini")
        log.write(f"\n[bold cyan]🚀 Autonomous Issue-to-Patch Solver Started[/bold cyan]")
        log.write(f"  • Prompt: [white]{prompt}[/white]")
        log.write(f"  • Provider: [white]{provider_name}[/white]")
        if verify_cmd:
            log.write(f"  • Verification: [dim]{verify_cmd}[/dim]")

        solver = AutonomousSolver()
        start = time.monotonic()
        try:
            summary = asyncio.run(
                solver.solve(
                    prompt=prompt,
                    mock=mock_mode,
                    verify_cmd=verify_cmd or None,
                )
            )
            elapsed = time.monotonic() - start
            if summary.status == "SUCCESS":
                log.write(f"[bold green]✓ Resolution SUCCESS in {elapsed:.2f}s![/bold green]")
                if summary.patch_path:
                    log.write(f"  • Patch Generated: [cyan]{summary.patch_path}[/cyan]")
                if summary.verification_passed:
                    log.write(f"  • Verification: [bold green]PASSED[/bold green] (`{verify_cmd}`)")
            else:
                log.write(f"[bold red]✗ Resolution {summary.status} in {elapsed:.2f}s[/bold red]")
                if summary.metadata.get("errors"):
                    for err in summary.metadata["errors"]:
                        log.write(f"    [dim red]{err}[/dim red]")
            self.app.call_from_thread(self.refresh_patches_data)
        except Exception as e:
            log.write(f"[bold red]✗ Solver execution error: {e}[/bold red]")

    @work(thread=True)
    def run_test_suites_task(self) -> None:
        """Run make test and stream output."""
        log = self.query_one("#tests-log", RichLog)
        log.write("\n[bold cyan]─── Running Full Test Suite Gate (make test) ───[/bold cyan]")
        proc = subprocess.Popen(
            ["make", "test"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        for line in iter(proc.stdout.readline, ""):
            log.write(line.rstrip())
        proc.wait()
        if proc.returncode == 0:
            log.write("\n[bold green]✓ ALL TEST SUITES PASSED (Quality Gate Passed)![/bold green]")
        else:
            log.write(f"\n[bold red]✗ Test suite exited with non-zero code {proc.returncode}[/bold red]")

    # ─── TABLES & DATA ───────────────────────────

    def init_patches_table(self) -> None:
        """Setup columns for patches table."""
        table = self.query_one("#table-patches", DataTable)
        table.add_columns("Patch File", "Size", "Modified Time")

    def refresh_patches_data(self) -> None:
        """Populate patches data table."""
        table = self.query_one("#table-patches", DataTable)
        table.clear()
        patches_dir = Path(".odin/patches")
        if not patches_dir.exists():
            return

        patches = sorted(patches_dir.glob("*.patch"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in patches:
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
            table.add_row(p.name, f"{p.stat().st_size} bytes", mtime, key=str(p))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Preview selected patch content."""
        if event.data_table.id == "table-patches":
            patch_path_str = event.row_key.value
            preview = self.query_one("#patch-preview-log", RichLog)
            preview.clear()
            p = Path(patch_path_str)
            if p.exists():
                preview.write(f"[bold cyan]─── Diff Preview: {p.name} ───[/bold cyan]\n")
                for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        preview.write(f"[green]{line}[/green]")
                    elif line.startswith("-") and not line.startswith("---"):
                        preview.write(f"[red]{line}[/red]")
                    elif line.startswith("@@"):
                        preview.write(f"[cyan]{line}[/cyan]")
                    else:
                        preview.write(f"[dim]{line}[/dim]")

    def init_errors_table(self) -> None:
        """Setup columns for error ledger table."""
        table = self.query_one("#table-errors", DataTable)
        table.add_columns("Timestamp", "Task ID", "Disposition", "Symptom Signature")

    def refresh_errors_data(self) -> None:
        """Populate error ledger data table."""
        table = self.query_one("#table-errors", DataTable)
        table.clear()
        errors_file = Path(".odin/errors.jsonl")
        if not errors_file.exists():
            return

        for line in errors_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                ts = rec.get("timestamp", "")[:19].replace("T", " ")
                task_id = rec.get("task_id", "unknown")
                disp = rec.get("triage_disposition", "OPEN")
                sig = rec.get("symptom_signature", rec.get("error_type", ""))
                table.add_row(ts, task_id, disp, sig)
            except Exception:
                continue


def main():
    """Entrypoint for AI Harness Textual Application."""
    app = AIHarnessTextualApp()
    app.run()


if __name__ == "__main__":
    main()
