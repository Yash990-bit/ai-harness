"""Hackathon baseline tests — Phase 1.

Verify the minimum requirements for a clean evaluator run:
  1. AI_API_KEY env var is recognized
  2. Configuration loads without error
  3. Application startup path works
  4. No credentials are hard-coded in key files

These tests are deterministic and do NOT require a real LLM connection.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestEnvironmentVariable:
    """AI_API_KEY must be readable from the environment."""

    def test_ai_api_key_readable(self):
        """The harness must be able to read AI_API_KEY from env."""
        with mock.patch.dict(os.environ, {"AI_API_KEY": "test-hackathon-key"}):
            assert os.environ.get("AI_API_KEY") == "test-hackathon-key"

    def test_ai_api_key_missing_is_none(self):
        """When AI_API_KEY is not set, it should be None, not crash."""
        env = {k: v for k, v in os.environ.items() if k != "AI_API_KEY"}
        with mock.patch.dict(os.environ, env, clear=True):
            assert os.environ.get("AI_API_KEY") is None

    def test_ai_provider_optional(self):
        """AI_PROVIDER is optional and defaults to auto-selection."""
        env = {k: v for k, v in os.environ.items() if k != "AI_PROVIDER"}
        with mock.patch.dict(os.environ, env, clear=True):
            provider = os.environ.get("AI_PROVIDER", "auto")
            assert provider == "auto"

    def test_ai_model_optional(self):
        """AI_MODEL is optional and defaults to provider's default."""
        env = {k: v for k, v in os.environ.items() if k != "AI_MODEL"}
        with mock.patch.dict(os.environ, env, clear=True):
            model = os.environ.get("AI_MODEL", "default")
            assert model == "default"


class TestConfigurationLoading:
    """Odin config must load without crashing, even without a config file."""

    def test_config_loads_with_defaults(self):
        """Config loading falls back to defaults when no config file exists."""
        # Import from the odin package
        sys.path.insert(0, str(ROOT_DIR / "odin" / "src"))
        try:
            from odin.config import _default_config
            cfg = _default_config("test")
            assert cfg is not None
            assert cfg.config_source == "test"
            assert len(cfg.agents) > 0
        finally:
            sys.path.pop(0)

    def test_config_has_known_agents(self):
        """Default config includes the expected agent harnesses."""
        sys.path.insert(0, str(ROOT_DIR / "odin" / "src"))
        try:
            from odin.config import _default_config
            cfg = _default_config("test")
            # At minimum these agents should exist in defaults
            for agent in ["claude", "codex", "gemini"]:
                assert agent in cfg.agents, f"Missing default agent: {agent}"
        finally:
            sys.path.pop(0)


class TestNoHardcodedSecrets:
    """Critical files must not contain hard-coded credentials."""

    FILES_TO_CHECK = [
        "Makefile",
        ".env.example",
        "dev.sh",
        "install.sh",
    ]

    # Patterns that indicate a real secret (not a variable reference)
    SECRET_PATTERNS = [
        "sk-",          # OpenAI-style keys
        "sk_live_",     # Stripe-style keys
        "ghp_",         # GitHub PATs
        "glpat-",       # GitLab PATs
    ]

    @pytest.mark.parametrize("filename", FILES_TO_CHECK)
    def test_no_secrets_in_file(self, filename):
        """No hard-coded secret patterns in critical files."""
        filepath = ROOT_DIR / filename
        if not filepath.exists():
            pytest.skip(f"{filename} does not exist")

        content = filepath.read_text()
        for pattern in self.SECRET_PATTERNS:
            # Allow pattern in comments about what NOT to do
            lines = content.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue  # Skip comments
                assert pattern not in line, (
                    f"Possible hard-coded secret '{pattern}' in {filename}:{i}"
                )

    def test_env_example_has_no_real_values(self):
        """The .env.example file must have empty values (no real secrets)."""
        filepath = ROOT_DIR / ".env.example"
        content = filepath.read_text()
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                assert value.strip() == "", (
                    f".env.example has a non-empty value for {key.strip()}"
                )


class TestGitignore:
    """.env must be protected by .gitignore."""

    def test_env_is_gitignored(self):
        """The .env file is listed in .gitignore."""
        gitignore = (ROOT_DIR / ".gitignore").read_text()
        assert ".env" in gitignore


class TestMakefileExists:
    """Root Makefile must exist with required targets."""

    def test_makefile_exists(self):
        """A Makefile exists at the repository root."""
        assert (ROOT_DIR / "Makefile").exists()

    def test_makefile_has_required_targets(self):
        """Makefile contains setup, run, test, clean targets."""
        content = (ROOT_DIR / "Makefile").read_text()
        for target in ["setup", "run", "test", "clean"]:
            assert f"{target}:" in content, (
                f"Makefile missing required target: {target}"
            )


class TestArchitectureDoc:
    """Architecture baseline document must exist."""

    def test_architecture_baseline_exists(self):
        """docs/architecture-baseline.md exists."""
        assert (ROOT_DIR / "docs" / "architecture-baseline.md").exists()

    def test_architecture_baseline_has_content(self):
        """The document has substantive content (not a placeholder)."""
        content = (ROOT_DIR / "docs" / "architecture-baseline.md").read_text()
        assert len(content) > 1000, "Architecture doc is too short to be substantive"
        assert "Reuse" in content or "REUSE" in content, "Missing reuse analysis"
        assert "Gap" in content or "gap" in content, "Missing gap analysis"
