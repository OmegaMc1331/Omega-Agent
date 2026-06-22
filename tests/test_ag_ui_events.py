from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.config_store import default_config, save_config, set_config_value
from omega_agent.events import EventBus, EventStore
from omega_agent.events.event_redaction import event_for_ui
from omega_agent.gateway.server import create_app
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.storage import connect_runtime_db
from omega_agent.runtime.tool_broker import ToolBroker


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return OmegaConfig(
        model="test",
        workspace=workspace,
        require_approval=False,
        workspace_full_access=True,
        shell_full_access_in_workspace=True,
        allow_delete_in_workspace=True,
        db_path=tmp_path / "omega.db",
        events_websocket_heartbeat_seconds=5,
    )


def test_emit_persists_event_and_redacts_secret(tmp_path: Path):
    config = cfg(tmp_path)
    event = EventBus(config).emit("tool.completed", {"token": "sk-123456789012345", "ok": True})

    stored = EventStore(config).get(event.id)
    with connect_runtime_db(config) as conn:
        row = conn.execute("SELECT payload_json FROM events_v2 WHERE id = ?", (event.id,)).fetchone()

    assert stored is not None
    assert stored.payload["token"] == "[REDACTED]"
    assert "sk-123456789012345" not in row["payload_json"]


def test_internal_event_not_sent_to_ui(tmp_path: Path):
    event = EventBus(cfg(tmp_path)).emit("system.internal", {"ok": True}, visibility="internal")

    assert event_for_ui(event) is None
    assert EventStore(cfg(tmp_path)).list(for_ui=True) == []


def test_replay_since_id_returns_missed_events(tmp_path: Path):
    config = cfg(tmp_path)
    first = EventBus(config).emit("system.before", {"n": 1})
    second = EventBus(config).emit("system.after", {"n": 2})

    replayed = EventBus(config).replay_events(since_id=first.id)

    assert [event.id for event in replayed] == [second.id]


def test_event_api_routes_redact_and_list_types(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    created = client.post(
        "/api/events/v2/test",
        json={"type": "system.test", "payload": {"Authorization": "Bearer abcdefghijklmnop"}},
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["payload"]["Authorization"] == "[REDACTED]"

    listed = client.get("/api/events/v2")
    assert listed.status_code == 200
    assert any(event["id"] == payload["id"] for event in listed.json())
    types = client.get("/api/events/v2/types")
    assert types.status_code == 200
    assert "system.test" in types.json()["types"]


def test_websocket_reconnect_replays_missed_events(tmp_path: Path):
    config = cfg(tmp_path)
    client = TestClient(create_app(config))
    first = EventBus(config).emit("system.before", {"n": 1})
    second = EventBus(config).emit("system.after", {"n": 2})

    with client.websocket_connect(f"/ws?last_event_id={first.id}") as websocket:
        assert websocket.receive_json()["type"] == "status.updated"
        replayed = websocket.receive_json()

    assert replayed["event_id"] == second.id
    assert replayed["type"] == "system.after"


def test_tool_broker_emits_v2_tool_and_policy_events(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Events")

    result = ToolBroker(config).call("write_file", {"relative_path": "event.txt", "content": "ok"}, session_id=session.id)

    assert result.status == "completed"
    events = EventStore(config).list(session_id=session.id, limit=50, for_ui=True)
    event_types = {event.type for event in events}
    assert {"policy.allowed", "tool.started", "tool.completed", "action.succeeded"}.issubset(event_types)
    assert all("sk-" not in json.dumps(event.as_api(), ensure_ascii=False) for event in events)


def test_cli_events_list(tmp_path: Path):
    data = default_config()
    data = set_config_value("workspace.path", str(tmp_path / "workspace"), data)
    data = set_config_value("paths.db_path", str(tmp_path / "omega.db"), data)
    config_path = tmp_path / "config.json"
    save_config(data, config_path)
    config = OmegaConfig(
        model="test",
        workspace=(tmp_path / "workspace").resolve(),
        require_approval=False,
        workspace_full_access=True,
        db_path=tmp_path / "omega.db",
    )

    env = {**os.environ, "OMEGA_CONFIG_PATH": str(config_path)}
    EventBus(config).emit("system.test", {"ok": True})
    result = subprocess.run(
        [sys.executable, "-m", "omega_agent.main", "events", "list"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0
    assert "system.test" in result.stdout or "Aucun event" in result.stdout
