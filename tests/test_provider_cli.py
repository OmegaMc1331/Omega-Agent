from __future__ import annotations

from pathlib import Path

from omega_agent.config_store import ensure_default_config, get_config_value, set_config_value
from omega_agent.main import main
from omega_agent.providers.settings import set_default_provider


def _cli_config(tmp_path: Path, monkeypatch) -> Path:
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("OMEGA_CONFIG_PATH", str(config_file))
    ensure_default_config(config_file)
    set_config_value("workspace.path", str(tmp_path / "workspace"), file_path=config_file)
    set_config_value("paths.db_path", str(tmp_path / "omega.db"), file_path=config_file)
    monkeypatch.setattr(
        "omega_agent.providers.codex_provider.codex_login_status_cached",
        lambda _ttl: (False, "not logged in"),
    )
    return config_file


def test_provider_use_sets_default_provider(tmp_path: Path, monkeypatch):
    config_file = _cli_config(tmp_path, monkeypatch)
    set_config_value(
        "providers.items.ollama.enabled",
        True,
        file_path=config_file,
    )

    set_default_provider("ollama", file_path=config_file)

    assert get_config_value("providers.default", file_path=config_file) == "ollama"


def test_model_use_sets_default_model(tmp_path: Path, monkeypatch):
    config_file = _cli_config(tmp_path, monkeypatch)
    set_config_value(
        "providers.items.ollama.enabled",
        True,
        file_path=config_file,
    )

    assert main(["models", "use", "ollama/llama3.1"]) == 0

    assert get_config_value("providers.default", file_path=config_file) == "ollama"
    assert get_config_value("models.default", file_path=config_file) == "ollama/llama3.1"
    assert get_config_value("model.default", file_path=config_file) == "ollama/llama3.1"


def test_cli_provider_aliases_work(tmp_path: Path, monkeypatch):
    config_file = _cli_config(tmp_path, monkeypatch)

    assert main(["provider", "use", "codex"]) == 0

    assert get_config_value("providers.default", file_path=config_file) == "codex"


def test_cli_model_aliases_work(tmp_path: Path, monkeypatch):
    config_file = _cli_config(tmp_path, monkeypatch)

    assert main(["model", "use", "codex/gpt-5.5"]) == 0

    assert get_config_value("models.default", file_path=config_file) == "codex/gpt-5.5"

