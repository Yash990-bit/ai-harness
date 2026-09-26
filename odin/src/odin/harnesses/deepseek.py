"""DeepSeek API harness for Odin.

Provides direct REST API execution for DeepSeek text-only models
(deepseek-chat, deepseek-reasoner / R1) via standard OpenAI-compatible completions.
Allows running DeepSeek headlessly without any CLI binary dependencies.
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


@register_harness("deepseek")
class DeepSeekHarness(BaseHarness):
    """Harness for DeepSeek models using direct REST API."""

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.api_url = "https://api.deepseek.com/chat/completions"

    @property
    def name(self) -> str:
        return "DeepSeek"

    def build_execute_command(self, prompt: str, context: dict) -> list[str] | None:
        return None  # Direct REST API only

    async def is_available(self) -> bool:
        """Check if DeepSeek API key is present."""
        return bool(
            self.config.api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("AI_API_KEY")
        )

    async def execute(self, prompt: str, context: dict) -> TaskResult:
        """Execute prompt against DeepSeek chat completions API."""
        start = time.monotonic()
        api_key = (
            self.config.api_key
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("AI_API_KEY")
        )
        if not api_key:
            return TaskResult(
                success=False,
                error="No DeepSeek API key configured (set DEEPSEEK_API_KEY or AI_API_KEY).",
                duration_ms=0,
                agent=self.name,
            )

        model = context.get("model") or self.config.default_model or "deepseek-chat"
        # Strip provider prefixes if passed (e.g. deepseek/deepseek-chat -> deepseek-chat)
        clean_model = model.split("/")[-1]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": clean_model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert autonomous software engineer. Write high-quality, correct, verified code."
                },
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.2,
        }

        timeout_seconds = float(context.get("timeout_seconds", 300) or 300)

        try:
            async with httpx.AsyncClient(timeout=timeout_seconds) as client:
                resp = await client.post(self.api_url, json=payload, headers=headers)
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
                error=f"DeepSeek API request failed: {exc}",
                duration_ms=round(duration, 1),
                agent=self.name,
            )
