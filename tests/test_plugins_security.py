import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.registries.plugins import PluginsRegistry


def cfg(tmp_path: Path) -> OmegaConfig:
    return OmegaConfig(
        model="test",
        workspace=tmp_path / "workspace",
        require_approval=True,
        plugins_dir=tmp_path / "plugins",
        db_path=tmp_path / "omega.db",
    )


def manifest(**overrides) -> dict:
    data = {
        "id": "example-plugin",
        "name": "Example Plugin",
        "version": "0.1.0",
        "description": "Example manifest-only plugin.",
        "author": "Omega",
        "enabled": False,
        "trust_level": "untrusted",
        "permissions": ["skills.register"],
        "declares": {"tools": [], "skills": [], "channels": [], "hooks": []},
    }
    data.update(overrides)
    return data


def write_plugin(root: Path, name: str, data: dict) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    return plugin_dir


def test_valid_manifest_is_loaded(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(config.plugins_dir, "example", manifest())

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.id == "example-plugin"
    assert plugin.status == "loaded"
    assert plugin.permissions == ["skills.register"]
    assert plugin.security_review["manifest_only"] is True


def test_invalid_manifest_is_rejected(tmp_path: Path):
    config = cfg(tmp_path)
    plugin_dir = config.plugins_dir / "bad"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text("{not-json", encoding="utf-8")

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.status == "rejected"
    assert plugin.enabled is False
    assert plugin.trust_level == "blocked"


def test_huge_manifest_is_rejected(tmp_path: Path):
    config = cfg(tmp_path)
    plugin_dir = config.plugins_dir / "huge"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(" " * (300 * 1024), encoding="utf-8")

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.status == "rejected"
    assert "volumineux" in plugin.error


def test_untrusted_plugin_disabled_by_default(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(config.plugins_dir, "untrusted", manifest(enabled=True, trust_level="untrusted"))

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.trust_level == "untrusted"
    assert plugin.enabled is False


def test_blocked_plugin_is_never_activable(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(config.plugins_dir, "blocked", manifest(trust_level="blocked"))
    client = TestClient(create_app(config))

    response = client.post("/api/plugins/example-plugin/enable", json={"confirmed": True})

    assert response.status_code == 403
    assert PluginsRegistry(config).get("example-plugin").enabled is False


def test_symlink_outside_plugins_dir_is_refused(tmp_path: Path):
    config = cfg(tmp_path)
    external = tmp_path / "external-plugin"
    write_plugin(external, "real", manifest(id="outside-plugin"))
    config.plugins_dir.mkdir(parents=True)
    link = config.plugins_dir / "linked"
    try:
        link.symlink_to(external / "real", target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlink unavailable on this Windows environment: {exc}")

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.status == "rejected"
    assert "Symlink plugin hors dossier" in plugin.error


def test_shell_permission_is_critical(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(config.plugins_dir, "shell", manifest(permissions=["shell.execute"], trust_level="local"))

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.security_review["risk_level"] == "critical"
    assert any("shell.execute" in warning for warning in plugin.security_review["critical_warnings"])


def test_plugin_api_detail_rescan_and_security_review(tmp_path: Path):
    config = cfg(tmp_path)
    write_plugin(config.plugins_dir, "example", manifest(trust_level="local", permissions=["skills.register"]))
    client = TestClient(create_app(config))

    listed = client.get("/api/plugins").json()
    detail = client.get("/api/plugins/example-plugin").json()
    review = client.get("/api/plugins/example-plugin/security-review").json()
    rescanned = client.post("/api/plugins/rescan").json()

    assert listed[0]["id"] == "example-plugin"
    assert detail["trust_level"] == "local"
    assert review["manifest_only"] is True
    assert rescanned[0]["id"] == "example-plugin"


def test_plugin_external_code_is_not_executed(tmp_path: Path):
    config = cfg(tmp_path)
    plugin_dir = write_plugin(config.plugins_dir, "code", manifest(id="code-plugin"))
    sentinel = tmp_path / "executed.txt"
    (plugin_dir / "run.py").write_text(f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n", encoding="utf-8")

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.id == "code-plugin"
    assert not sentinel.exists()
