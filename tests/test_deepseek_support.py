"""Tests for DeepSeek direct REST API integration and credential mapping."""

import os
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from odin.config import load_config, map_hackathon_credentials
from odin.harnesses.registry import get_harness, HARNESS_REGISTRY
from odin.models import AgentConfig, TaskResult
from odin.orchestrator import Orchestrator, _list_available_agents


def test_deepseek_harness_registered():
    """Verify DeepSeek harness is registered in HARNESS_REGISTRY."""
    assert "deepseek" in HARNESS_REGISTRY
    cfg = AgentConfig(default_model="deepseek-chat")
    harness = get_harness("deepseek", cfg)
    assert harness.name == "DeepSeek"


def test_deepseek_credential_mapping():
    """Verify AI_PROVIDER=deepseek maps AI_API_KEY to DEEPSEEK_API_KEY."""
    env = {
        "AI_API_KEY": "test-deepseek-sk-123",
        "AI_PROVIDER": "deepseek",
        "AI_MODEL": "deepseek-chat",
    }
    with patch.dict(os.environ, env, clear=False):
        agents = {
            "deepseek": AgentConfig(default_model="deepseek-chat")
        }
        map_hackathon_credentials(agents)
        assert os.environ.get("DEEPSEEK_API_KEY") == "test-deepseek-sk-123"
        assert os.environ.get("FORCED_BASE_PROVIDER") == "deepseek"
        assert agents["deepseek"].api_key == "test-deepseek-sk-123"
        assert agents["deepseek"].enabled is True


@pytest.mark.asyncio
async def test_deepseek_execute_mocked():
    """Verify DeepSeek direct REST API execution parses completion."""
    cfg = AgentConfig(api_key="sk-fake-key", default_model="deepseek-chat")
    harness = get_harness("deepseek", cfg)

    fake_response_data = {
        "choices": [
            {
                "message": {
                    "content": "def fix_bug(): return True",
                }
            }
        ],
        "usage": {
            "prompt_tokens": 15,
            "completion_tokens": 25,
            "total_tokens": 40,
        },
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await harness.execute("Fix bug in function", context={"validate_status": False})
        assert isinstance(res, TaskResult)
        assert res.success is True
        assert "def fix_bug(): return True" in res.output
        assert res.metadata["usage"]["total_tokens"] == 40


@pytest.mark.asyncio
async def test_openrouter_free_deepseek_resolution():
    """Verify OpenRouter key format triggers free deepseek endpoint and model mapping."""
    cfg = AgentConfig(api_key="sk-or-v1-fake-free-key", default_model="deepseek-chat")
    harness = get_harness("deepseek", cfg)

    fake_response = {
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"total_tokens": 10},
    }
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = fake_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", return_value=mock_resp) as mock_post:
        res = await harness.execute("test", context={"validate_status": False})
        assert res.success is True
        call_args, call_kwargs = mock_post.call_args
        assert call_args[0] == "https://openrouter.ai/api/v1/chat/completions"
        assert call_kwargs["json"]["model"] == "openrouter/free"


def test_orchestrator_recognizes_deepseek_with_api_key():
    """Verify orchestrator sees deepseek as available without local CLI binary."""
    with patch.dict(os.environ, {"AI_API_KEY": "sk-dummy", "AI_PROVIDER": "deepseek"}):
        cfg = load_config()
        assert "deepseek" in _list_available_agents(cfg)
        orch = Orchestrator(cfg)
        # Should not raise exception
        orch._assert_agent_cli_available("deepseek", action="execution")
