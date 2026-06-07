import json
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.plugins_registry import PluginsRegistry
from omega_agent.security import log_action
from omega_agent.storage import connect_db


def cfg(tmp_path: Path) -> OmegaConfig:
    return OmegaConfig(
        model="gpt-5.5",
        workspace=tmp_path / "workspace",
        require_approval=True,
        skills_dir=tmp_path / "skills",
        plugins_dir=tmp_path / "plugins",
        db_path=tmp_path / "omega.db",
    )


def test_websocket_chat_requires_valid_session(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "chat.send", "message": "bonjour"})
        payload = websocket.receive_json()

    assert payload["type"] == "error"
    assert "Session" in payload["payload"]["message"]


def test_settings_endpoint_does_not_expose_sensitive_stored_values(tmp_path: Path):
    config = cfg(tmp_path)
    app = create_app(config)
    with connect_db(config) as conn:
        conn.execute("INSERT OR REPLACE INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)", ("OPENAI_API_KEY", json.dumps("sk-secret"), "now"))
    client = TestClient(app)

    settings = client.get("/api/settings").json()

    assert "OPENAI_API_KEY" not in settings
    assert "sk-secret" not in json.dumps(settings)


def test_settings_patch_rejects_sensitive_keys(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    response = client.patch("/api/settings", json={"values": {"OPENAI_API_KEY": "sk-secret"}})

    assert response.status_code == 400


def test_logs_redact_secret_payloads(tmp_path: Path):
    config = cfg(tmp_path)
    log_action(config, "unit", {"token": "abc123", "command": "git status token=sk-abcdef123456"})
    client = TestClient(create_app(config))

    payload = client.get("/api/logs").json()
    encoded = json.dumps(payload)

    assert "abc123" not in encoded
    assert "sk-abcdef123456" not in encoded
    assert "[REDACTED]" in encoded


def test_approval_arguments_are_redacted_in_api(tmp_path: Path):
    config = cfg(tmp_path)
    app = create_app(config)
    ApprovalsStore(config).create("run_shell", {"command": "git status token=sk-abcdef123456"}, risk="high")
    client = TestClient(app)

    payload = client.get("/api/approvals").json()
    encoded = json.dumps(payload)

    assert "sk-abcdef123456" not in encoded
    assert "[REDACTED]" in encoded


def test_plugin_manifest_with_executable_entrypoint_is_blocked(tmp_path: Path):
    config = cfg(tmp_path)
    plugin_dir = config.plugins_dir / "danger"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": "danger", "name": "Danger", "trust_level": "local", "entrypoint": "run.py"}),
        encoding="utf-8",
    )

    plugin = PluginsRegistry(config).list()[0]

    assert plugin.status == "blocked"
    assert plugin.enabled is False


def test_untrusted_plugin_cannot_be_enabled_from_api(tmp_path: Path):
    config = cfg(tmp_path)
    plugin_dir = config.plugins_dir / "github"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"id": "github", "name": "GitHub", "trust_level": "untrusted", "declares": {}}),
        encoding="utf-8",
    )
    client = TestClient(create_app(config))

    response = client.patch("/api/plugins/github", json={"enabled": True})

    assert response.status_code == 403


def test_skill_create_rejects_unknown_tools(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    response = client.post("/api/skills", json={"name": "review", "tools": ["unknown_tool"]})

    assert response.status_code == 400


def test_summarize_job_requires_existing_session(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    response = client.post("/api/jobs", json={"kind": "summarize_session", "input": {"session_id": "missing"}})

    assert response.status_code == 400
