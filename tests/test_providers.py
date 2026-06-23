from __future__ import annotations

import json
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.config_store import ensure_default_config, load_config, set_config_value
from omega_agent.providers.base import CompletionResult, ProviderError
from omega_agent.providers.codex_provider import CodexProvider
from omega_agent.providers.openai_compatible_provider import OpenAICompatibleProvider
from omega_agent.providers.registry import ProviderRegistry
from omega_agent.providers.settings import add_provider
from omega_agent.runtime.model_selector import ModelSelector


def _configured_env(tmp_path: Path, monkeypatch) -> Path:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(config_file))
    ensure_default_config(config_file)
    set_config_value("workspace.path", str(tmp_path / "workspace"), file_path=config_file)
    set_config_value("paths.db_path", str(tmp_path / "omega.db"), file_path=config_file)
    return config_file


def test_provider_registry_loads_builtin_providers(tmp_path: Path, monkeypatch):
    _configured_env(tmp_path, monkeypatch)
    registry = ProviderRegistry(OmegaConfig.from_env())

    provider_ids = {provider.provider_id for provider in registry.list()}

    assert {
        "codex",
        "openai",
        "anthropic",
        "google",
        "vertex",
        "openrouter",
        "groq",
        "mistral",
        "ollama",
        "lmstudio",
        "deepseek",
        "xai",
    }.issubset(provider_ids)


def test_config_add_provider_preserves_existing_config(tmp_path: Path, monkeypatch):
    config_file = _configured_env(tmp_path, monkeypatch)
    set_config_value("gateway.port", 9911, file_path=config_file)
    set_config_value("workspace.full_access", False, file_path=config_file)

    add_provider(
        "private-models",
        provider_type="openai-compatible",
        base_url="https://models.example.invalid/v1",
        api_key_env="PRIVATE_MODELS_API_KEY",
        default_model="team/model-a",
        file_path=config_file,
    )

    data = load_config(config_file)
    assert data["gateway"]["port"] == 9911
    assert data["workspace"]["full_access"] is False
    assert data["providers"]["items"]["private-models"]["default_model"] == "team/model-a"
    assert data["providers"]["items"]["private-models"]["api_key_env"] == "PRIVATE_MODELS_API_KEY"


def test_provider_default_model_is_used_when_models_default_is_absent(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "providers": {
                    "default": "local-ollama",
                    "items": {
                        "local-ollama": {
                            "type": "ollama",
                            "enabled": True,
                            "base_url": "http://127.0.0.1:11434",
                            "default_model": "llama3.1",
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    data = load_config(config_file)

    assert data["models"]["default"] == "local-ollama/llama3.1"


def test_openai_compatible_provider_builds_request_without_exposing_key(
    tmp_path: Path, monkeypatch
):
    secret = "sk-test-provider-secret-123456"
    monkeypatch.setenv("PRIVATE_API_KEY", secret)
    provider = OpenAICompatibleProvider(
        OmegaConfig(model="model-a", workspace=tmp_path, require_approval=False),
        provider_id="private",
        settings={
            "type": "openai-compatible",
            "base_url": "https://models.example.invalid/v1",
            "api_key_env": "PRIVATE_API_KEY",
            "default_model": "model-a",
        },
    )
    observed: dict = {}

    def fake_request(method, url, *, payload=None, headers=None, timeout=15):
        observed.update(
            {
                "method": method,
                "url": url,
                "payload": payload,
                "headers": headers,
                "timeout": timeout,
            }
        )
        return {
            "id": "request-1",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
        }

    monkeypatch.setattr(provider, "_request_json", fake_request)

    result = provider.chat("private/model-a", [], "bonjour")

    assert result == CompletionResult(
        "ok",
        input_tokens=2,
        output_tokens=1,
        metadata={"provider_request_id": "request-1"},
    )
    assert observed["headers"]["Authorization"] == f"Bearer {secret}"
    assert secret not in json.dumps(observed["payload"])
    assert secret not in str(result)
    assert secret not in str(provider.info().as_api())


def test_missing_api_key_env_returns_clear_error(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("MISSING_PROVIDER_KEY", raising=False)
    provider = OpenAICompatibleProvider(
        OmegaConfig(model="model-a", workspace=tmp_path, require_approval=False),
        provider_id="private",
        settings={
            "type": "openai-compatible",
            "base_url": "https://models.example.invalid/v1",
            "api_key_env": "MISSING_PROVIDER_KEY",
            "default_model": "model-a",
        },
    )

    result = provider.test_connection()

    assert result.ok is False
    assert result.status == "missing"
    assert "MISSING_PROVIDER_KEY" in result.message


def test_openai_compatible_tool_call_uses_omega_action_format(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setenv("PRIVATE_API_KEY", "test-key")
    provider = OpenAICompatibleProvider(
        OmegaConfig(model="model-a", workspace=tmp_path, require_approval=False),
        provider_id="private",
        settings={
            "type": "openai-compatible",
            "base_url": "https://models.example.invalid/v1",
            "api_key_env": "PRIVATE_API_KEY",
            "default_model": "model-a",
        },
    )
    monkeypatch.setattr(
        provider,
        "_request_json",
        lambda *_args, **_kwargs: {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "write_file",
                                    "arguments": '{"relative_path":"note.txt","content":"OK"}',
                                }
                            }
                        ],
                    }
                }
            ]
        },
    )

    result = provider.chat("private/model-a", [], "crée note.txt")

    assert json.loads(result.content) == {
        "omega_actions": [
            {
                "tool": "write_file",
                "arguments": {"relative_path": "note.txt", "content": "OK"},
            }
        ]
    }


def test_models_list_uses_provider_registry(tmp_path: Path, monkeypatch):
    _configured_env(tmp_path, monkeypatch)
    selector = ModelSelector(OmegaConfig.from_env())

    refs = {model["model_ref"] for model in selector.catalog_api()}

    assert "codex/gpt-5.5" in refs
    assert "ollama/llama3.1" in refs


def test_models_refresh_handles_discovery_failure(tmp_path: Path, monkeypatch):
    config_file = _configured_env(tmp_path, monkeypatch)
    add_provider(
        "private-models",
        provider_type="openai-compatible",
        base_url="https://models.example.invalid/v1",
        api_key_env="PRIVATE_MODELS_API_KEY",
        default_model="manual-model",
        file_path=config_file,
    )
    selector = ModelSelector(OmegaConfig.from_env())
    provider = selector.provider("private-models")

    def fail_discovery():
        raise ProviderError("discovery unavailable")

    monkeypatch.setattr(provider, "discover_models", fail_discovery)
    monkeypatch.setattr(selector.providers, "get", lambda provider_id: provider)

    result = selector.refresh_catalog("private-models")

    assert result["count"] == 1
    assert result["errors"][0]["provider_id"] == "private-models"
    assert "discovery unavailable" in result["errors"][0]["error"]


def test_codex_provider_still_available(tmp_path: Path, monkeypatch):
    _configured_env(tmp_path, monkeypatch)
    provider = ProviderRegistry(OmegaConfig.from_env()).get("codex")

    assert isinstance(provider, CodexProvider)
    assert provider.info().capabilities["oauth"] is True
    assert provider.info().default_model == "gpt-5.5"


def test_ollama_provider_can_be_configured_without_api_key(tmp_path: Path, monkeypatch):
    config_file = _configured_env(tmp_path, monkeypatch)
    add_provider(
        "local-ollama",
        provider_type="ollama",
        base_url="http://127.0.0.1:11434",
        default_model="llama3.1",
        file_path=config_file,
    )

    provider = ProviderRegistry(OmegaConfig.from_env()).get("local-ollama")

    assert provider is not None
    assert provider.effective_auth_type() == "none"
    assert provider.api_key_env == ""
    assert provider.check_auth().status == "configured"
