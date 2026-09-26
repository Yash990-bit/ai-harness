"""Phase 2 Integration Tests — AI Harness Hackathon 2026.

Validates:
1. Dynamic credential & provider mapping (AI_API_KEY, AI_PROVIDER, AI_MODEL).
2. Resilient Gemini harness with direct REST API fallback.
3. Orchestrator agent availability without requiring external CLI binaries.
4. End-to-end mock execution and task lifecycle.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from odin.config import load_config, map_hackathon_credentials
from odin.harnesses.gemini import GeminiHarness
from odin.models import AgentConfig, CostTier, TaskResult
from odin.orchestrator import Orchestrator, _list_available_agents


class TestHackathonCredentialMapping:
    """Test dynamic mapping of hackathon environment variables."""

    def test_gemini_default_mapping(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "evaluator-secret-gemini")
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("AI_MODEL", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("FORCED_BASE_PROVIDER", raising=False)

        cfg = load_config()
        assert os.environ.get("GEMINI_API_KEY") == "evaluator-secret-gemini"
        assert cfg.agents["gemini"].enabled is True
        assert cfg.agents["gemini"].api_key == "evaluator-secret-gemini"
        assert cfg.forced_base_provider == "gemini"

    def test_claude_provider_mapping(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "evaluator-secret-claude")
        monkeypatch.setenv("AI_PROVIDER", "claude")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        cfg = load_config()
        assert os.environ.get("ANTHROPIC_API_KEY") == "evaluator-secret-claude"
        assert cfg.agents["claude"].enabled is True
        assert cfg.agents["claude"].api_key == "evaluator-secret-claude"

    def test_codex_provider_mapping(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "evaluator-secret-openai")
        monkeypatch.setenv("AI_PROVIDER", "codex")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        cfg = load_config()
        assert os.environ.get("OPENAI_API_KEY") == "evaluator-secret-openai"
        assert cfg.agents["codex"].enabled is True
        assert cfg.agents["codex"].api_key == "evaluator-secret-openai"

    def test_ai_model_override(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "key-123")
        monkeypatch.setenv("AI_PROVIDER", "gemini")
        monkeypatch.setenv("AI_MODEL", "gemini-2.5-flash-test")
        monkeypatch.delenv("FORCED_BASE_MODEL", raising=False)

        cfg = load_config()
        assert os.environ.get("FORCED_BASE_MODEL") == "gemini-2.5-flash-test"
        assert cfg.forced_base_model == "gemini-2.5-flash-test"

    def test_no_keys_leaves_env_clean(self, monkeypatch):
        monkeypatch.delenv("AI_API_KEY", raising=False)
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        map_hackathon_credentials()
        assert os.environ.get("GEMINI_API_KEY") is None


class TestGeminiHarnessDirectAPI:
    """Test Gemini harness standalone and REST API fallback capabilities."""

    def test_gemini_available_with_api_key_when_cli_missing(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_API_KEY", "test-key")
        with patch("shutil.which", return_value=None):
            harness = GeminiHarness(AgentConfig(cli_command="nonexistent_gemini_cli"))
            import asyncio
            available = asyncio.run(harness.is_available())
            assert available is True

    @pytest.mark.asyncio
    async def test_gemini_execute_via_api_mocked(self, monkeypatch):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Plan executed successfully.\n-------ODIN-STATUS-------\nSUCCESS\n-------ODIN-SUMMARY-------\nComplete."
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 100,
                "candidatesTokenCount": 50,
                "totalTokenCount": 150,
            },
        }

        with patch("shutil.which", return_value=None), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client

            harness = GeminiHarness(AgentConfig(cli_command="gemini", api_key="test-key"))
            result = await harness.execute("Hello Gemini", {"validate_status": True})

            assert result.success is True
            assert "Plan executed successfully" in result.output
            assert result.metadata["usage"]["total_tokens"] == 150


class TestOrchestratorAvailabilityIntegration:
    """Test orchestrator agent resolution with AI_API_KEY."""

    def test_gemini_listed_available_with_api_key(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "test-key-available")
        with patch("shutil.which", return_value=None):
            cfg = load_config()
            available = _list_available_agents(cfg)
            assert "gemini" in available

    def test_assert_agent_cli_available_permits_gemini_with_key(self, monkeypatch):
        monkeypatch.setenv("AI_API_KEY", "test-key-permit")
        with patch("shutil.which", return_value=None):
            orch = object.__new__(Orchestrator)
            orch.config = load_config()
            # Should not raise RuntimeError
            orch._assert_agent_cli_available("gemini", action="execution")
