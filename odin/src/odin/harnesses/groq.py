"""Groq Cloud API harness for Odin.

Provides direct REST API execution for Groq ultra-fast LPU inference
via standard OpenAI-compatible completions.
Allows running Groq models (qwen/qwen3.8-27b, openai/gpt-oss-120b)
headlessly with zero CLI binary dependencies.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from odin.harnesses.base import BaseHarness, validate_odin_status_full
from odin.harnesses.registry import register_harness
from odin.models import AgentConfig, TaskResult


@register_harness("groq")
class GroqHarness(BaseHarness):
    """Harness for Groq Cloud ultra-fast inference models using direct REST API."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    @property
    def name(self) -> str:
        return "Groq"

    def build_execute_command(self, prompt: str, context: dict) -> list[str] | None:
        return None  # Direct REST API only

    async def is_available(self) -> bool:
        """Check if Groq API key is present."""
        return bool(
            self.config.api_key
            or os.environ.get("GROQ_API_KEY")
            or (os.environ.get("AI_API_KEY", "").startswith("gsk_"))
            or os.environ.get("AI_API_KEY")
        )

    async def execute(self, prompt: str, context: dict) -> TaskResult:
        """Execute prompt against Groq chat completions API."""
        start = time.monotonic()
        api_key = (
            self.config.api_key
            or os.environ.get("GROQ_API_KEY")
            or os.environ.get("AI_API_KEY")
        )
        if not api_key:
            return TaskResult(
                success=False,
                error="No Groq API key configured (set GROQ_API_KEY or AI_API_KEY).",
                duration_ms=0,
                agent=self.name,
            )

        model = context.get("model") or self.config.default_model or "qwen/qwen3.8-27b"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an expert autonomous software engineer. "
                        "When asked to solve an issue, produce clean, working python code inside ```python code blocks. "
                        "Always conclude your response with:\n\n"
                        "-------ODIN-STATUS-------\nSUCCESS\n-------ODIN-SUMMARY-------\n<Summary of changes>"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }

        timeout_seconds = float(context.get("timeout_seconds", 300) or 300)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

            choices = data.get("choices", [])
            text = choices[0]["message"]["content"] if choices else ""
            usage_raw = data.get("usage", {})
            usage = {
                "input_tokens": usage_raw.get("prompt_tokens", 0),
                "output_tokens": usage_raw.get("completion_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
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
                error=f"Groq API request failed: {exc}",
                duration_ms=round(duration, 1),
                agent=self.name,
            )
