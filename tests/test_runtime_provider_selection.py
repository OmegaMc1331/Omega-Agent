from __future__ import annotations

import asyncio
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.config_store import ensure_default_config, set_config_value
from omega_agent.providers.base import CompletionResult
from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider
from omega_agent.runtime.agent import OmegaRuntime


def test_runtime_uses_selected_provider_and_model(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(config_file))
    ensure_default_config(config_file)
    set_config_value("workspace.path", str(tmp_path / "workspace"), file_path=config_file)
    set_config_value("paths.db_path", str(tmp_path / "omega.db"), file_path=config_file)
    set_config_value("governance.budgets.enforce", False, file_path=config_file)
    set_config_value(
        "providers.items.private-models",
        {
            "type": "openai-compatible",
            "display_name": "Private Models",
            "enabled": True,
            "auth": "api_key",
            "api_key_env": "PRIVATE_MODELS_API_KEY",
            "base_url": "https://models.example.invalid/v1",
            "default_model": "team/model-a",
            "models": ["team/model-a"],
        },
        file_path=config_file,
    )
    set_config_value("providers.default", "private-models", file_path=config_file)
    set_config_value(
        "models.default",
        "private-models/team/model-a",
        file_path=config_file,
    )
    monkeypatch.setenv("PRIVATE_MODELS_API_KEY", "test-only-key")
    observed: dict[str, str] = {}

    def fake_chat(self, model_ref, history, user_input, *, tools=None):
        observed["provider"] = self.provider_id
        observed["model"] = model_ref
        observed["message"] = user_input
        return CompletionResult("provider response")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", fake_chat)
    config = OmegaConfig.from_env()
    runtime = OmegaRuntime(config)
    session_id = runtime.sessions.create_session("Provider selection").id

    output = asyncio.run(runtime.send_message("bonjour", session_id=session_id))

    assert output == "provider response"
    assert observed == {
        "provider": "private-models",
        "model": "private-models/team/model-a",
        "message": "bonjour",
    }

