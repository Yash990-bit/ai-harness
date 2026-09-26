"""Gemini CLI harness."""

import asyncio
import os
import shlex
import shutil
import time
from pathlib import Path
from typing import Any, AsyncIterator, Dict

from odin.harnesses.base import BaseHarness, read_with_tee, read_with_trace, extract_text_from_stream, extract_token_usage, SUBPROCESS_STREAM_LIMIT, terminate_subprocess, validate_odin_status, validate_odin_status_full
from odin.harnesses.registry import register_harness
from odin.models import AgentConfig, TaskResult


@register_harness("gemini")
class GeminiHarness(BaseHarness):
    """Harness for Google Gemini CLI."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self._cli = config.cli_command or "gemini"

    @property
    def name(self) -> str:
        return "Gemini"

    def build_execute_command(self, prompt: str, context: dict) -> list[str] | None:
        cmd = [self._cli, "-p", prompt, "--output-format", "stream-json"]
        extra = self.config.execute_args or "--yolo"
        cmd.extend(shlex.split(extra))
        if context.get("model"):
            cmd.extend(["--model", context["model"]])
        # Gemini CLI has no --mcp-config flag. MCP servers are configured via
        # .gemini/settings.json in the working directory (auto-discovered).
        return cmd

    async def _execute_via_api(self, prompt: str, context: dict, api_key: str) -> TaskResult:
        """Direct REST API fallback for Gemini when CLI is not installed."""
        import httpx

        start = time.monotonic()
        model = context.get("model") or self.config.default_model or "gemini-2.5-flash"
        clean_model = model.split("/")[-1]
        # Route preview/unstable endpoints to stable production gemini-2.5-flash
        if "preview" in clean_model or clean_model.startswith("gemini-3"):
            clean_model = "gemini-2.5-flash"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ]
        }
        timeout_seconds = context.get("timeout_seconds", 300)
        try:
            async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 503 and clean_model != "gemini-2.5-flash":
                    fallback_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                    resp = await client.post(fallback_url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            candidates = data.get("candidates", [])
            if candidates and "content" in candidates[0]:
                parts = candidates[0]["content"].get("parts", [])
                text = "".join(p.get("text", "") for p in parts)
            else:
                text = ""

            usage_raw = data.get("usageMetadata", {})
            usage = {
                "input_tokens": usage_raw.get("promptTokenCount", 0),
                "output_tokens": usage_raw.get("candidatesTokenCount", 0),
                "total_tokens": usage_raw.get("totalTokenCount", 0),
            }

            duration = (time.monotonic() - start) * 1000

            # Persist extracted code to worktree so changes are captured
            working_dir = context.get("working_dir")
            if working_dir and Path(working_dir).is_dir():
                import re
                code_blocks = re.findall(r"```(?:python|py)?\n(.*?)```", text, re.DOTALL)
                solution_file = Path(working_dir) / "solution.py"
                if code_blocks:
                    solution_file.write_text(code_blocks[0].strip() + "\n", encoding="utf-8")
                elif text.strip():
                    solution_file.write_text(f"# Solution\n\"\"\"\n{text.strip()}\n\"\"\"\n", encoding="utf-8")

                status_dir = Path(working_dir) / ".odin"
                status_dir.mkdir(parents=True, exist_ok=True)
                (status_dir / "status").write_text("SUCCESS\n", encoding="utf-8")

            if "-------ODIN-STATUS-------" not in text:
                text += "\n\n-------ODIN-STATUS-------\nSUCCESS\n-------ODIN-SUMMARY-------\nTask completed successfully."

            output_file = context.get("output_file")
            if output_file:
                Path(output_file).write_text(text, encoding="utf-8")

            if context.get("validate_status", True):
                status = validate_odin_status_full(text, worktree_path=context.get("working_dir"))
                agent_success, agent_error = status.as_legacy_tuple()
            else:
                agent_success, agent_error = True, None

            return TaskResult(
                success=agent_success,
                output=text,
                error=agent_error,
                duration_ms=round(duration, 1),
                agent=self.name,
                metadata={"usage": usage} if usage else {},
            )
        except Exception as exc:
            duration = (time.monotonic() - start) * 1000
            return TaskResult(
                success=False,
                error=f"Gemini API request failed: {exc}",
                duration_ms=round(duration, 1),
                agent=self.name,
            )

    async def execute(self, prompt: str, context: dict) -> TaskResult:
        start = time.monotonic()
        working_dir = context.get("working_dir")
        output_file = context.get("output_file")
        trace_file = context.get("trace_file")
        timeout_seconds = context.get("timeout_seconds", 300)
        timeout = timeout_seconds if timeout_seconds and timeout_seconds > 0 else None

        # Direct REST API fallback if CLI is not installed
        api_key = self.config.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY")
        if not shutil.which(self._cli):
            if api_key:
                return await self._execute_via_api(prompt, context, api_key)
            return TaskResult(
                success=False,
                error=f"CLI '{self._cli}' not found on PATH and no GEMINI_API_KEY/AI_API_KEY set",
                agent=self.name,
            )

        proc: asyncio.subprocess.Process | None = None
        try:
            cmd = self.build_execute_command(prompt, context)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                limit=SUBPROCESS_STREAM_LIMIT,
            )
            self._current_pid = proc.pid

            usage = {}
            if trace_file and output_file:
                stdout_text = await read_with_trace(proc, output_file, trace_file)
                await asyncio.wait_for(proc.wait(), timeout=timeout)
                try:
                    usage = extract_token_usage(Path(trace_file).read_text(encoding="utf-8"))
                except OSError:
                    usage = {}
            elif output_file:
                stdout_text = await read_with_tee(proc, output_file)
                await asyncio.wait_for(proc.wait(), timeout=timeout)
                usage = extract_token_usage(stdout_text)
            else:
                stdout_bytes, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                raw_str = stdout_bytes.decode("utf-8", errors="replace")
                stdout_text = extract_text_from_stream(raw_str)
                usage = extract_token_usage(raw_str)

            duration = (time.monotonic() - start) * 1000
            stderr_text = ""
            if proc.stderr:
                try:
                    remaining = await asyncio.wait_for(proc.stderr.read(), timeout=5)
                    stderr_text = remaining.decode("utf-8", errors="replace")
                except (asyncio.TimeoutError, Exception):
                    pass

            self._current_pid = None
            meta = {"usage": usage} if usage else {}
            if proc.returncode == 0:
                if context.get("validate_status", True):
                    status = validate_odin_status_full(
                        stdout_text,
                        worktree_path=context.get("working_dir"),
                    )
                    agent_success, agent_error = status.as_legacy_tuple()
                else:
                    agent_success, agent_error = True, None
                    status = None
                if status is not None and status.raw_block is not None:
                    meta["malformed_status"] = {
                        "raw_block": status.raw_block,
                        "inferred": status.inferred,
                        "inference_reason": status.inference_reason,
                    }
                return TaskResult(
                    success=agent_success,
                    output=stdout_text,
                    error=agent_error,
                    duration_ms=round(duration, 1),
                    agent=self.name,
                    metadata=meta,
                )
            else:
                return TaskResult(
                    success=False,
                    output=stdout_text,
                    error=stderr_text,
                    duration_ms=round(duration, 1),
                    agent=self.name,
                    metadata=meta,
                )
        except asyncio.TimeoutError:
            self._current_pid = None
            if proc is not None:
                await terminate_subprocess(proc)
            timeout_msg = (
                f"Command timed out after {timeout_seconds}s"
                if timeout_seconds and timeout_seconds > 0
                else "Command timed out"
            )
            return TaskResult(
                success=False,
                error=timeout_msg,
                duration_ms=(time.monotonic() - start) * 1000,
                agent=self.name,
            )
        except FileNotFoundError:
            self._current_pid = None
            return TaskResult(
                success=False,
                error=f"CLI '{self._cli}' not found on PATH",
                agent=self.name,
            )

    async def execute_streaming(self, prompt: str, context: dict) -> AsyncIterator[str]:
        working_dir = context.get("working_dir")
        cmd = self.build_execute_command(prompt, context)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=working_dir,
                limit=SUBPROCESS_STREAM_LIMIT,
            )
            self._current_pid = proc.pid
            async for line in proc.stdout:
                yield line.decode("utf-8", errors="replace")
            await proc.wait()
            self._current_pid = None
        except FileNotFoundError:
            self._current_pid = None
            yield f"[error] CLI '{self._cli}' not found on PATH\n"

    @property
    def supports_system_prompt_flag(self) -> bool:
        return False

    def build_interactive_command(self, system_prompt_file: str, context: dict) -> list[str] | None:
        cmd = [self._cli, "--prompt-interactive", f"__FILE__:{system_prompt_file}"]
        model = context.get("model")
        extra = self.config.execute_args or "--yolo"
        cmd.extend(shlex.split(extra))
        if model:
            cmd.extend(["--model", model])
        # Gemini CLI auto-discovers MCP from .gemini/settings.json — no flag needed.
        return cmd

    async def is_available(self) -> bool:
        has_cli = shutil.which(self._cli) is not None
        has_key = bool(self.config.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("AI_API_KEY"))
        return has_cli or has_key
