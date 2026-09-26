"""Interactive Terminal User Interface (TUI) for AI Harness.

Complies with Section 6 of the Hackathon Evaluation Guidelines:
"Teams implementing a Terminal User Interface (TUI) must ensure that the TUI
can be launched through: make run"

Provides interactive capabilities for:
- Configuring evaluation parameters (provider, model, API keys)
- Monitoring task execution (issue solver with live status)
- Viewing benchmarks, logs, patches, and compounding error ledger
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich.table import Table

from odin.config import load_config, map_hackathon_credentials
from odin.solver import AutonomousSolver

console = Console()


def display_header():
    """Render the application header with active environment parameters."""
    provider = os.getenv("AI_PROVIDER") or "gemini"
    model = os.getenv("AI_MODEL") or ("openrouter/free" if (os.getenv("AI_API_KEY", "").startswith("sk-or-")) else ("deepseek-chat" if provider == "deepseek" else "gemini-2.5-flash"))
    api_key = os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    has_key = bool(api_key)

    if has_key:
        masked = api_key[:7] + "..." + api_key[-4:] if len(api_key) > 12 else "configured"
        status_str = f"[bold green]Active[/bold green] [dim]({masked})[/dim]"
    else:
        status_str = "[bold yellow]Missing (Run in Mock or export AI_API_KEY)[/bold yellow]"

    content = (
        f"[bold cyan]AI Harness — Autonomous Software Engineering Platform[/bold cyan]\n"
        f"[dim]LCC × DevClub AI Coding Harness Hackathon 2026 Evaluation Hub[/dim]\n\n"
        f"  [bold]Provider:[/bold] [bold white]{provider}[/bold white]  |  "
        f"[bold]Model:[/bold] [bold white]{model}[/bold white]  |  "
        f"[bold]API Key:[/bold] {status_str}\n"
        f"  [bold]Engine:[/bold] AutonomousSolver v2.0  |  "
        f"[bold]Architecture:[/bold] Worktree Isolation + Compounding Error Ledger"
    )
    console.print(Panel(content, border_style="cyan", padding=(1, 2)))


def configure_parameters():
    """Interactively configure evaluator parameters (Provider, Model, Key)."""
    console.print("\n[bold cyan]─── Configure Evaluation Parameters ───[/bold cyan]")
    console.print("Select AI Provider:")
    console.print("  [1] DeepSeek (Official / OpenRouter Free)")
    console.print("  [2] Google Gemini (Google AI Studio)")
    console.print("  [3] Claude (Anthropic)")
    console.print("  [4] Codex / GPT (OpenAI)")
    console.print("  [5] Mock Provider (Deterministic Offline Testing)")

    choice = Prompt.ask("[bold]Select provider[/bold]", choices=["1", "2", "3", "4", "5"], default="1")
    providers = {
        "1": "deepseek",
        "2": "gemini",
        "3": "claude",
        "4": "codex",
        "5": "mock",
    }
    selected_provider = providers[choice]
    os.environ["AI_PROVIDER"] = selected_provider

    current_key = os.getenv("AI_API_KEY", "")
    key_prompt = f"Enter {selected_provider.upper()} API Key"
    if current_key:
        key_prompt += f" [dim](Press Enter to keep current)[/dim]"
    
    new_key = Prompt.ask(key_prompt, default=current_key)
    if new_key:
        os.environ["AI_API_KEY"] = new_key.strip()
        map_hackathon_credentials()

    # Model configuration
    if selected_provider == "deepseek":
        default_model = "openrouter/free" if new_key.startswith("sk-or-") else "deepseek-chat"
        new_model = Prompt.ask("Enter model", default=default_model)
    elif selected_provider == "gemini":
        new_model = Prompt.ask("Enter model", default="gemini-2.5-flash")
    elif selected_provider == "claude":
        new_model = Prompt.ask("Enter model", default="claude-3-7-sonnet")
    elif selected_provider == "codex":
        new_model = Prompt.ask("Enter model", default="gpt-4o")
    else:
        new_model = "mock-model"

    os.environ["AI_MODEL"] = new_model
    console.print(f"[bold green]✓ Configuration updated:[/bold green] Provider={selected_provider}, Model={new_model}\n")


def run_benchmark_demo():
    """Execute a built-in mock benchmark demo showing self-correction and patch export."""
    console.print("\n[bold cyan]─── Launching Built-In Benchmark Demo (Mock Mode) ───[/bold cyan]")
    solver = AutonomousSolver()
    with console.status("[bold green]Executing SWE benchmark scenario..."):
        summary = asyncio.run(
            solver.solve(
                prompt="Refactor string parser to handle unicode and null byte boundaries safely",
                mock=True,
                verify_cmd="python3 -c 'exit(0)'",
            )
        )
    console.print(f"[bold green]✓ Benchmark Completed in {summary.duration_seconds}s![/bold green]")
    console.print(f"  • Status: [bold green]{summary.status}[/bold green]")
    console.print(f"  • Tasks Completed: {summary.tasks_completed}/{summary.tasks_count}")
    if summary.patch_path:
        console.print(f"  • Generated Solution Patch: [cyan]{summary.patch_path}[/cyan]")
    console.print("  • Telemetry Persisted: [dim].odin/reports/latest_summary.json[/dim]\n")


def run_custom_solver():
    """Prompt user for a task description and optional verification command."""
    console.print("\n[bold cyan]─── Autonomous Issue-to-Patch Solver ───[/bold cyan]")
    prompt = Prompt.ask("[bold]Enter issue description / prompt[/bold]")
    if not prompt.strip():
        console.print("[yellow]Empty prompt cancelled.[/yellow]")
        return

    verify_cmd = Prompt.ask(
        "[bold]Enter verification command (optional, e.g. python3 -c 'print(\"ok\")')[/bold]",
        default="",
    )

    has_key = bool(os.getenv("AI_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))
    use_mock = False
    if not has_key:
        console.print("[yellow]No API key detected in environment. Running in Mock Mode.[/yellow]")
        use_mock = True
    else:
        mode_choice = Prompt.ask("Execution Mode: [1] Live AI Model, [2] Offline Mock", choices=["1", "2"], default="1")
        use_mock = (mode_choice == "2")

    solver = AutonomousSolver()
    console.print(f"\n[bold]Solving issue using {'Mock' if use_mock else os.getenv('AI_PROVIDER', 'deepseek')}...[/bold]")
    with console.status("[bold green]Analyzing issue, isolating git worktree & applying patch..."):
        summary = asyncio.run(
            solver.solve(
                prompt=prompt,
                mock=use_mock,
                verify_cmd=verify_cmd or None,
            )
        )

    if summary.status == "SUCCESS":
        console.print(f"\n[bold green]✓ Resolution SUCCESS! ({summary.duration_seconds}s)[/bold green]")
        if summary.patch_path:
            console.print(f"  [bold]Solution patch generated:[/bold] [cyan]{summary.patch_path}[/cyan]")
        if summary.verification_passed and verify_cmd:
            console.print(f"  [bold green]Verification passed:[/bold green] `{verify_cmd}`")
    else:
        console.print(f"\n[bold red]✗ Resolution {summary.status} ({summary.duration_seconds}s)[/bold red]")
        if summary.metadata.get("errors"):
            for err in summary.metadata["errors"]:
                console.print(f"  [dim red]{err}[/dim red]")


def view_patches_and_telemetry():
    """Inspect generated patches in .odin/patches/ and latest summary report."""
    console.print("\n[bold cyan]─── Generated Patches & Evaluation Telemetry ───[/bold cyan]")
    patches_dir = Path(".odin/patches")
    report_file = Path(".odin/reports/latest_summary.json")

    # Display report if available
    if report_file.exists():
        try:
            rep = json.loads(report_file.read_text(encoding="utf-8"))
            console.print("[bold]Latest Run Summary:[/bold]")
            console.print(
                f"  Status: [bold green]{rep.get('status')}[/bold green] | "
                f"Duration: {rep.get('duration_seconds')}s | "
                f"Tasks: {rep.get('tasks_completed')}/{rep.get('tasks_count')}"
            )
            if rep.get("verification_cmd"):
                v_res = "[green]PASS[/green]" if rep.get("verification_passed") else "[red]FAIL[/red]"
                console.print(f"  Verification: `{rep.get('verification_cmd')}` → {v_res}")
        except Exception:
            pass

    # List patches
    patches = sorted(patches_dir.glob("*.patch")) if patches_dir.exists() else []
    if not patches:
        console.print("[dim]No generated patches found in .odin/patches/ yet.[/dim]\n")
        return

    table = Table(title=f"Generated Solution Patches ({len(patches)})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Patch File", style="cyan")
    table.add_column("Size", style="green", width=12)
    table.add_column("Modified Time", style="white")

    for idx, p in enumerate(patches, 1):
        mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime))
        table.add_row(str(idx), p.name, f"{p.stat().st_size} bytes", mtime)
    console.print(table)

    view_choice = Prompt.ask("\nEnter patch # to preview (or 0 to return)", default="0")
    if view_choice.isdigit() and 1 <= int(view_choice) <= len(patches):
        selected_patch = patches[int(view_choice) - 1]
        content = selected_patch.read_text(encoding="utf-8")
        console.print(Panel(Syntax(content, "diff", theme="monokai", line_numbers=True), title=selected_patch.name))


def view_error_ledger():
    """Display error ledger summary and open events."""
    from odin.error_ledger import LocalErrorLedger
    ledger = LocalErrorLedger()
    summary = ledger.summary()

    if summary["total_errors"] == 0:
        console.print("\n[green]Error ledger is clean — 0 errors recorded.[/green]\n")
        return

    console.print(
        f"\n[bold]Compounding Error Ledger Summary:[/bold] {summary['total_errors']} total | "
        f"[red]{summary['open']} open[/red] | "
        f"[green]{summary['fixed']} fixed[/green] | "
        f"[dim]{summary['non_issue']} non-issue[/dim]\n"
    )
    events = ledger.list_events()
    table = Table(title=f"Recorded Error Signatures ({len(events)})")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Source", style="blue")
    table.add_column("Disposition", style="bold")
    table.add_column("Symptom Message", style="white")
    table.add_column("Resolution Note", style="dim")
    for ev in events:
        color = "red" if ev.disposition == "open" else ("green" if ev.disposition == "fixed" else "dim")
        table.add_row(
            ev.event_id,
            ev.source,
            f"[{color}]{ev.disposition}[/{color}]",
            ev.message[:70],
            ev.disposition_note[:40],
        )
    console.print(table)
    console.print()


def run_doctor():
    """Run environment and provider diagnostics."""
    from odin.cli import OdinCLI
    console.print("\n[bold cyan]─── Running System Diagnostics (odin doctor) ───[/bold cyan]")
    OdinCLI().doctor(fast=True)
    console.print()


def run_tests():
    """Execute all verification test suites."""
    console.print("\n[bold cyan]─── Running Test Suites (make test) ───[/bold cyan]")
    subprocess.run(["make", "test"], check=False)
    console.print()


def launch_interactive_tui():
    """Main interactive loop."""
    if not sys.stdin.isatty():
        # Non-interactive / headless fallback
        display_header()
        console.print("[dim]Non-interactive terminal detected.[/dim]")
        console.print("  Usage: [bold]make run TASK=\"...\"[/bold] or [bold]make solve TASK=\"...\" VERIFY=\"...\"[/bold]\n")
        return

    while True:
        console.clear()
        display_header()
        console.print("[bold]Select an action:[/bold]")
        console.print("  [cyan][1][/cyan] 🚀 [bold white]Autonomous Issue-to-Patch Solver[/bold white] (Enter issue prompt)")
        console.print("  [cyan][2][/cyan] ⚙️ [bold white]Configure Evaluation Parameters[/bold white] (Provider, Model, API Key)")
        console.print("  [cyan][3][/cyan] 🧪 [bold white]Fast SWE Benchmark Demo[/bold white] (Mock Mode — Zero Cost)")
        console.print("  [cyan][4][/cyan] 📜 [bold white]View Generated Patches & Telemetry[/bold white] (.odin/patches/)")
        console.print("  [cyan][5][/cyan] 📊 [bold white]View Compounding Error Ledger[/bold white] (.odin/errors.jsonl)")
        console.print("  [cyan][6][/cyan] 🩺 [bold white]System Doctor & Environment Diagnostics[/bold white]")
        console.print("  [cyan][7][/cyan] 🧪 [bold white]Run Verification Test Suites[/bold white] (make test)")
        console.print("  [cyan][8][/cyan] 🧹 [bold white]Clean State & Artifacts[/bold white] (make clean)")
        console.print("  [cyan][0][/cyan] 🚪 [bold dim]Exit[/bold dim]\n")

        try:
            choice = Prompt.ask("[bold]Enter choice[/bold]", choices=["1", "2", "3", "4", "5", "6", "7", "8", "0"], default="1")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting AI Harness TUI. Goodbye![/dim]")
            break

        if choice == "1":
            run_custom_solver()
        elif choice == "2":
            configure_parameters()
        elif choice == "3":
            run_benchmark_demo()
        elif choice == "4":
            view_patches_and_telemetry()
        elif choice == "5":
            view_error_ledger()
        elif choice == "6":
            run_doctor()
        elif choice == "7":
            run_tests()
        elif choice == "8":
            subprocess.run(["make", "clean"], check=False)
        elif choice == "0":
            console.print("\n[dim]Exiting AI Harness TUI. Goodbye![/dim]")
            break

        Prompt.ask("\n[dim]Press Enter to return to main menu...[/dim]")


if __name__ == "__main__":
    launch_interactive_tui()
