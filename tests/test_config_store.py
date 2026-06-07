from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import (
    config_path,
    ensure_default_config,
    get_config_value,
    migrate_env_to_config,
    redact_config_for_display,
    set_config_value,
)
from omega_agent.gateway.server import create_app
from omega_agent.main import models_command


def test_config_json_created_if_absent(tmp_path: Path, monkeypatch):
    target = tmp_path / ".omega" / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))

    path = ensure_default_config()

    assert path == target.resolve()
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8"))["model"]["default"] == "codex/gpt-5.5"


def test_config_path_uses_user_config_path(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))

    assert config_path() == target.resolve()


def test_config_get_and_set_path(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    ensure_default_config()

    set_config_value("model.default", "ollama/llama3.3")

    assert get_config_value("model.default") == "ollama/llama3.3"


def test_config_redacts_secret_references_without_secret_values(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-secretsecret")
    ensure_default_config()

    payload = str(redact_config_for_display())

    assert "sk-or-secretsecret" not in payload
    assert "OPENROUTER_API_KEY" in payload


def test_migration_legacy_provider_model_to_default(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    env_path = tmp_path / ".env"
    env_path.write_text("OMEGA_PROVIDER=codex\nOMEGA_MODEL=gpt-5.5\nOMEGA_PORT=9999\n", encoding="utf-8")
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))

    result = migrate_env_to_config(env_path=env_path)

    assert "OMEGA_DEFAULT_MODEL" in result["migrated"]
    assert get_config_value("model.default") == "codex/gpt-5.5"
    assert get_config_value("gateway.port") == 9999


def test_config_json_has_priority_over_legacy_env(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    ensure_default_config()
    set_config_value("model.default", "ollama/llama3.3")
    (tmp_path / ".env").write_text("OMEGA_DEFAULT_MODEL=codex/gpt-5.5\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OMEGA_WORKSPACE", str(workspace))
    monkeypatch.delenv("OMEGA_DEFAULT_MODEL", raising=False)

    cfg = OmegaConfig.from_env()

    assert cfg.default_model_ref == "ollama/llama3.3"


def test_env_absent_does_not_break_config(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    monkeypatch.chdir(tmp_path)

    cfg = OmegaConfig.from_env()

    assert cfg.default_model_ref == "codex/gpt-5.5"


def test_models_current_reads_config_json(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    ensure_default_config()
    set_config_value("model.default", "ollama/llama3.3")
    set_config_value("workspace.path", str(tmp_path / "workspace"))
    set_config_value("paths.db_path", str(tmp_path / "omega.db"))
    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", lambda: (False, "not logged in"))
    output: list[str] = []

    class FakeConsole:
        def print(self, *args, **kwargs):
            output.append(" ".join(str(arg) for arg in args))

    monkeypatch.setattr("omega_agent.main.console", FakeConsole())

    code = models_command(SimpleNamespace(models_command="current"))

    assert code == 0
    assert "ollama/llama3.3" in "\n".join(output)


def test_enable_provider_and_base_url_modify_config(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    ensure_default_config()
    set_config_value("workspace.path", str(tmp_path / "workspace"))
    set_config_value("paths.db_path", str(tmp_path / "omega.db"))
    monkeypatch.setattr("omega_agent.main.console.print", lambda *args, **kwargs: None)

    assert models_command(SimpleNamespace(models_command="enable-provider", provider="ollama")) == 0
    assert models_command(SimpleNamespace(models_command="set-provider-base-url", provider="ollama", url="http://127.0.0.1:11434")) == 0

    assert get_config_value("providers.ollama.enabled") is True
    assert get_config_value("providers.ollama.base_url") == "http://127.0.0.1:11434"


def test_config_endpoints_are_redacted(tmp_path: Path, monkeypatch):
    target = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(target))
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secretsecret")
    ensure_default_config()
    set_config_value("workspace.path", str(tmp_path / "workspace"))
    set_config_value("paths.db_path", str(tmp_path / "omega.db"))
    cfg = OmegaConfig.from_env()
    client = TestClient(create_app(cfg))

    config_response = client.get("/api/config")
    path_response = client.get("/api/config/path")
    secrets_response = client.get("/api/secrets/status")

    assert config_response.status_code == 200
    assert path_response.json()["path"] == str(target.resolve())
    assert "sk-secretsecret" not in str(config_response.json())
    assert {"name": "OPENAI_API_KEY", "configured": True} in secrets_response.json()
