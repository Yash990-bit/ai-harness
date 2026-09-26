"""Forced Gemini provider configuration for Odin."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Optional

from odin.models import OdinConfig

ALLOWED_FORCED_PROVIDERS = {"gemini", "deepseek", "claude", "codex", "mock"}


@dataclass(frozen=True)
class ForcedProviderSelection:
    enabled: bool
    provider: Optional[str] = None
    model: Optional[str] = None


def resolve_forced_provider(config: OdinConfig) -> ForcedProviderSelection:
    provider = (os.environ.get("FORCED_BASE_PROVIDER") or "").strip().lower()
    model = (os.environ.get("FORCED_BASE_MODEL") or "").strip()

    if not provider:
        return ForcedProviderSelection(enabled=False)

    if provider not in ALLOWED_FORCED_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_FORCED_PROVIDERS))
        raise RuntimeError(f"FORCED_BASE_PROVIDER must be one of: {allowed}.")

    cfg = config.agents.get(provider)
    if not cfg:
        raise RuntimeError(f"Forced provider '{provider}' is not configured in Odin.")

    cli_command = cfg.cli_command or provider
    has_api_key = bool(
        cfg.api_key
        or os.environ.get("GEMINI_API_KEY")
        or os.environ.get("DEEPSEEK_API_KEY")
        or os.environ.get("AI_API_KEY")
        or (provider == "claude" and os.environ.get("ANTHROPIC_API_KEY"))
        or (provider == "codex" and os.environ.get("OPENAI_API_KEY"))
    )
    if provider != "mock" and shutil.which(cli_command) is None:
        if not (provider in ("gemini", "deepseek") and has_api_key):
            raise RuntimeError(
                f"Forced provider '{provider}' is unavailable: CLI '{cli_command}' not found on PATH."
            )

    model_names = list(cfg.models.keys())
    if model:
        resolved_model = model
    else:
        resolved_model = cfg.default_model or (model_names[0] if model_names else None)

    if not resolved_model:
        raise RuntimeError(
            f"Forced provider '{provider}' does not have a usable default model."
        )

    return ForcedProviderSelection(
        enabled=True,
        provider=provider,
        model=resolved_model,
    )
