from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omega_agent.config import OmegaConfig
from omega_agent.config_store import (
    ensure_default_config,
    get_config_value,
    load_config,
    save_config,
    set_config_value,
)
from omega_agent.main import main
from omega_agent.providers.base import CompletionResult
from omega_agent.providers.google_provider import GoogleProvider
from omega_agent.providers.openai_provider import OpenAIProvider
from omega_agent.providers.thinking import (
    ThinkingConfigurationError,
    ThinkingMatrix,
)
from omega_agent.runtime.agent import OmegaRuntime


def _config(tmp_path: Path, monkeypatch, model_ref: str = "openai/gpt-5.5") -> Path:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(config_file))
    ensure_default_config(config_file)
    set_config_value("workspace.path", str(tmp_path / "workspace"), file_path=config_file)
    set_config_value("paths.db_path", str(tmp_path / "omega.db"), file_path=config_file)
    set_config_value("governance.budgets.enforce", False, file_path=config_file)
    set_config_value("models.default", model_ref, file_path=config_file)
    set_config_value("model.default", model_ref, file_path=config_file)
    set_config_value("providers.default", model_ref.split("/", 1)[0], file_path=config_file)
    return config_file


def _set_model_level(config_file: Path, model_ref: str, level: str) -> None:
    data = load_config(config_file)
    data["thinking"]["per_model"][model_ref] = level
    save_config(data, config_file)


def test_thinking_matrix_loads_builtin_profiles():
    matrix = ThinkingMatrix({"thinking": {}})

    assert matrix.profile_for("openai/gpt-5.5").mode == "reasoning_effort"
    assert matrix.profile_for("google/gemini-2.5-flash").mode == "thinking_budget"
    assert matrix.profile_for("google/gemini-3-pro-preview").mode == "thinking_level"


def test_openai_gpt55_supports_expected_reasoning_levels():
    profile = ThinkingMatrix({"thinking": {}}).profile_for("openai/gpt-5.5")

    assert profile.levels == ("off", "auto", "low", "medium", "high", "max")
    assert profile.api_parameters("high") == {"reasoning": {"effort": "high"}}
    assert profile.api_parameters("max") == {"reasoning": {"effort": "xhigh"}}


def test_gemini25_maps_levels_to_thinking_budget():
    matrix = ThinkingMatrix(
        {"thinking": {"default": "medium", "per_model": {}, "profiles": {}}}
    )

    resolved = matrix.resolve("google/gemini-2.5-flash")

    assert resolved.profile.mode == "thinking_budget"
    assert resolved.api_parameters == {"thinking_budget": 4096}
    assert resolved.profile.api_parameters("off") == {"thinking_budget": 0}


def test_gemini3_maps_levels_to_thinking_level():
    matrix = ThinkingMatrix(
        {"thinking": {"default": "low", "per_model": {}, "profiles": {}}}
    )

    resolved = matrix.resolve("google/gemini-3-pro-preview")

    assert resolved.profile.levels == ("low", "high")
    assert resolved.api_parameters == {"thinking_level": "LOW"}


def test_unsupported_model_rejects_thinking_level():
    matrix = ThinkingMatrix({"thinking": {}})

    with pytest.raises(
        ThinkingConfigurationError,
        match="ne supporte pas de contrôle thinking/reasoning connu",
    ):
        matrix.validate_level("ollama/llama3.1", "high")


def test_thinking_use_updates_global_default(tmp_path: Path, monkeypatch):
    config_file = _config(tmp_path, monkeypatch)

    assert main(["thinking", "use", "high"]) == 0

    assert get_config_value("thinking.default", file_path=config_file) == "high"


def test_thinking_use_model_override_updates_per_model(tmp_path: Path, monkeypatch):
    config_file = _config(tmp_path, monkeypatch)

    assert (
        main(
            [
                "thinking",
                "use",
                "medium",
                "--model",
                "openai/gpt-5.5",
            ]
        )
        == 0
    )

    assert load_config(config_file)["thinking"]["per_model"]["openai/gpt-5.5"] == "medium"


def test_thinking_use_rejects_invalid_level_for_model(
    tmp_path: Path, monkeypatch, capsys
):
    config_file = _config(tmp_path, monkeypatch, "ollama/llama3.1")
    before = load_config(config_file)["thinking"]["per_model"].copy()

    assert (
        main(
            [
                "thinking",
                "use",
                "high",
                "--model",
                "ollama/llama3.1",
            ]
        )
        == 1
    )

    assert "ne supporte pas" in capsys.readouterr().out
    assert load_config(config_file)["thinking"]["per_model"] == before


def test_runtime_sends_openai_reasoning_effort_only_when_supported(
    tmp_path: Path, monkeypatch
):
    config_file = _config(tmp_path, monkeypatch)
    set_config_value("providers.items.openai.enabled", True, file_path=config_file)
    _set_model_level(config_file, "openai/gpt-5.5", "high")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    observed: dict = {}

    def fake_chat(self, model_ref, history, user_input, *, tools=None, thinking=None):
        observed["model_ref"] = model_ref
        observed["thinking"] = thinking
        return CompletionResult("ok")

    monkeypatch.setattr(OpenAIProvider, "chat", fake_chat)
    runtime = OmegaRuntime(OmegaConfig.from_env())
    session_id = runtime.sessions.create_session("Thinking").id

    assert asyncio.run(runtime.send_message("bonjour", session_id=session_id)) == "ok"
    assert observed["model_ref"] == "openai/gpt-5.5"
    assert observed["thinking"] == {"reasoning": {"effort": "high"}}


def test_runtime_sends_gemini_thinking_budget_only_for_gemini25(
    tmp_path: Path, monkeypatch
):
    config_file = _config(tmp_path, monkeypatch, "google/gemini-2.5-flash")
    set_config_value("providers.items.google.enabled", True, file_path=config_file)
    _set_model_level(config_file, "google/gemini-2.5-flash", "low")
    monkeypatch.setenv("GEMINI_API_KEY", "test-only-key")
    observed: dict = {}

    def fake_request(self, method, url, *, payload=None, headers=None, timeout=10):
        observed["payload"] = payload
        return {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {},
        }

    monkeypatch.setattr(GoogleProvider, "_request_json", fake_request)
    provider = GoogleProvider(
        OmegaConfig.from_env(),
        settings=load_config(config_file)["providers"]["items"]["google"],
    )
    resolved = ThinkingMatrix(load_config(config_file)).resolve(
        "google/gemini-2.5-flash"
    )

    provider.chat(
        "google/gemini-2.5-flash",
        [],
        "bonjour",
        thinking=resolved.api_parameters,
    )

    assert observed["payload"]["generationConfig"]["thinkingConfig"] == {
        "thinkingBudget": 1024
    }


def test_runtime_does_not_send_thinking_to_unsupported_provider(
    tmp_path: Path, monkeypatch
):
    config_file = _config(tmp_path, monkeypatch, "ollama/llama3.1")
    matrix = ThinkingMatrix(load_config(config_file))

    resolved = matrix.resolve("ollama/llama3.1")

    assert resolved.effective_level == "off"
    assert resolved.api_parameters == {}


def test_models_show_displays_thinking_capabilities(
    tmp_path: Path, monkeypatch, capsys
):
    _config(tmp_path, monkeypatch)

    assert main(["models", "show", "openai/gpt-5.5"]) == 0

    output = capsys.readouterr().out
    assert "thinking supported: yes" in output
    assert "reasoning_effort" in output


def test_thinking_doctor_reports_incompatible_config(
    tmp_path: Path, monkeypatch, capsys
):
    config_file = _config(tmp_path, monkeypatch, "ollama/llama3.1")
    _set_model_level(config_file, "ollama/llama3.1", "high")

    assert main(["thinking", "doctor"]) == 1

    assert "FAIL" in capsys.readouterr().out


def test_config_merge_preserves_existing_thinking_settings(tmp_path: Path):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "thinking": {
                    "default": "high",
                    "per_model": {"openai/gpt-5.5": "low"},
                }
            }
        ),
        encoding="utf-8-sig",
    )

    data = load_config(config_file)

    assert data["thinking"]["default"] == "high"
    assert data["thinking"]["per_model"]["openai/gpt-5.5"] == "low"
    assert data["thinking"]["allow_unsupported_fallback"] is False
