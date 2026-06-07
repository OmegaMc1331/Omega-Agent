from pathlib import Path

import pytest

from omega_agent.config import OmegaConfig


def test_config_defaults_to_codex_gpt_5_5_without_openai_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OMEGA_PROVIDER", raising=False)
    monkeypatch.delenv("OMEGA_MODEL", raising=False)
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    cfg = OmegaConfig.from_env()

    assert cfg.provider == "codex"
    assert cfg.model == "gpt-5.5"
    assert cfg.default_model_ref == "codex/gpt-5.5"
    assert cfg.omega_default_model == "codex/gpt-5.5"
    assert cfg.model_selection_enabled is True
    assert cfg.omega_model_selection_enabled is True
    assert cfg.workspace == tmp_path.resolve()
    assert cfg.require_approval is True
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 8765
    assert cfg.browser_enabled is False
    assert cfg.browser_profile_dir == (tmp_path / ".omega" / "browser-profile").resolve()
    assert cfg.browser_require_approval is True
    assert cfg.desktop_enabled is False
    assert cfg.desktop_screenshots_dir == (tmp_path / ".omega" / "screenshots").resolve()
    assert cfg.desktop_require_approval is True
    assert (tmp_path / ".omega").is_dir()


def test_config_default_model_ref_has_priority_over_legacy_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_PROVIDER", "codex")
    monkeypatch.setenv("OMEGA_MODEL", "gpt-5.5")
    monkeypatch.setenv("OMEGA_DEFAULT_MODEL", "openrouter/anthropic/claude-sonnet-4.5")
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    cfg = OmegaConfig.from_env()

    assert cfg.default_model_ref == "openrouter/anthropic/claude-sonnet-4.5"
    assert cfg.omega_default_model == "openrouter/anthropic/claude-sonnet-4.5"
    assert cfg.provider == "openrouter"
    assert cfg.model == "anthropic/claude-sonnet-4.5"


def test_config_reads_model_provider_settings_without_exposing_requirement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OMEGA_FALLBACK_MODEL", "codex/gpt-5.5")
    monkeypatch.setenv("OMEGA_MODEL_SELECTION_ENABLED", "true")
    monkeypatch.setenv("OMEGA_MODEL_AUTH_CACHE_SECONDS", "123")
    monkeypatch.setenv("OMEGA_MODEL_STATUS_CACHE_SECONDS", "45")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secretsecretsecret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-secretsecret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secretsecret")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSecretSecretSecretSecret")
    monkeypatch.setenv("GOOGLE_API_KEY", "AIzaGoogleSecretSecretSecret")
    monkeypatch.setenv("CUSTOM_OPENAI_BASE_URL", "https://models.local/v1")
    monkeypatch.setenv("CUSTOM_OPENAI_API_KEY", "sk-customsecretsecret")
    monkeypatch.setenv("CUSTOM_OPENAI_MODEL", "local-pro")

    cfg = OmegaConfig.from_env()

    assert cfg.fallback_model_ref == "codex/gpt-5.5"
    assert cfg.omega_fallback_model == "codex/gpt-5.5"
    assert cfg.model_auth_cache_seconds == 123
    assert cfg.omega_model_auth_cache_seconds == 123
    assert cfg.model_status_cache_seconds == 45
    assert cfg.omega_model_status_cache_seconds == 45
    assert cfg.openai_api_key.startswith("sk-")
    assert cfg.openrouter_api_key.startswith("sk-or")
    assert cfg.anthropic_api_key.startswith("sk-ant")
    assert cfg.gemini_api_key.startswith("AIza")
    assert cfg.google_api_key.startswith("AIza")
    assert cfg.custom_openai_api_key.startswith("sk-")


def test_config_codex_does_not_require_openai_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OMEGA_PROVIDER", "codex")
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    cfg = OmegaConfig.from_env()

    assert cfg.provider == "codex"


def test_config_reads_gateway_host_and_port(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("OMEGA_HOST", "127.0.0.1")
    monkeypatch.setenv("OMEGA_PORT", "9876")

    cfg = OmegaConfig.from_env()

    assert cfg.host == "127.0.0.1"
    assert cfg.port == 9876


def test_config_accepts_openai_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_PROVIDER", "openai")
    monkeypatch.setenv("OMEGA_MODEL", "gpt-5.1")
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    cfg = OmegaConfig.from_env()

    assert cfg.provider == "openai"
    assert cfg.model == "gpt-5.1"


def test_config_rejects_unknown_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_PROVIDER", "unknown")
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path))

    with pytest.raises(ValueError, match="OMEGA_PROVIDER invalide"):
        OmegaConfig.from_env()


def test_config_strips_workspace_env_value(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OMEGA_WORKSPACE", f" {tmp_path} ")

    cfg = OmegaConfig.from_env()

    assert cfg.workspace == tmp_path.resolve()
