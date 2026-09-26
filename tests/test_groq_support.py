"""Tests for Groq Cloud ultra-fast LPU inference harness integration."""

import os
from unittest.mock import patch, MagicMock
import pytest

from odin.config import map_hackathon_credentials
from odin.harnesses.registry import get_harness, HARNESS_REGISTRY
from odin.models import AgentConfig


def test_groq_harness_registered():
    """Verify groq harness is properly registered in HARNESS_REGISTRY."""
    assert "groq" in HARNESS_REGISTRY


def test_groq_credential_mapping():
    """Verify AI_PROVIDER=groq sets GROQ_API_KEY and FORCED_BASE_PROVIDER."""
    with patch.dict(
        os.environ,
        {"AI_API_KEY": "gsk_test123", "AI_PROVIDER": "groq"},
        clear=True,
    ):
        map_hackathon_credentials()
        assert os.environ.get("GROQ_API_KEY") == "gsk_test123"
        assert os.environ.get("FORCED_BASE_PROVIDER") == "groq"
        assert os.environ.get("FORCED_BASE_MODEL") == "qwen/qwen3.8-27b"


@pytest.mark.asyncio
async def test_groq_execute_mocked():
    """Verify GroqHarness execute sends correctly formatted payload."""
    config = AgentConfig(
        cli_command="groq",
        capabilities=["coding"],
        default_model="qwen/qwen3.8-27b",
        api_key="gsk_mock_key",
    )
    harness = get_harness("groq", config)
    assert await harness.is_available()

    fake_response = {
        "choices": [
            {
                "message": {
                    "content": "```python\ndef solution():\n    return True\n```\n\n-------ODIN-STATUS-------\nSUCCESS\n-------ODIN-SUMMARY-------\nDone"
                }
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = fake_response
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.post", return_value=mock_resp):
        res = await harness.execute("Write solution", context={"validate_status": False})
        assert res.success
        assert "def solution():" in res.output
