from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.tool_broker import ToolBroker


def test_runner_create_file_request_executes_write_file(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    runtime = OmegaRuntime(cfg)

    output = asyncio.run(runtime.send_message("Crée un fichier test.txt dans mon workspace avec le texte Bonjour"))

    assert (tmp_path / "test.txt").read_text(encoding="utf-8") == "Bonjour"
    assert "C'est fait" in output


def test_runner_refuses_outside_workspace_action(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    cfg = OmegaConfig(model="test", workspace=workspace, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    runtime = OmegaRuntime(cfg)

    output = asyncio.run(runtime.send_message(f"Crée {outside} avec le texte nope"))

    assert not outside.exists()
    assert "refuse" in output.lower()


def test_runner_extracts_omega_action_json_from_model_output(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    runtime = OmegaRuntime(cfg)

    async def fake_turn(*args, **kwargs):
        return '{"omega_actions":[{"tool":"write_file","arguments":{"relative_path":"json.txt","content":"ok"}}]}'

    monkeypatch.setattr(runtime, "_run_model_turn", fake_turn)

    output = asyncio.run(runtime.send_message("Fais une action JSON"))

    assert (tmp_path / "json.txt").read_text(encoding="utf-8") == "ok"
    assert "C'est fait" in output


def test_gateway_chat_create_file_executes_tool(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    client = TestClient(create_app(cfg))

    response = client.post("/api/chat", json={"message": "Crée un fichier api-smoke.txt avec le texte Bonjour"})

    assert response.status_code == 200
    assert (tmp_path / "api-smoke.txt").read_text(encoding="utf-8") == "Bonjour"


def test_tool_events_are_recorded_for_completed_action(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, workspace_full_access=True, allow_delete_in_workspace=True, db_path=tmp_path / "omega.db")
    runtime = OmegaRuntime(cfg)
    session_id = runtime.sessions.create_session("Events").id
    runtime.sessions.set_agent_profile(session_id, "omega-coder")

    result = ToolBroker(cfg).call("write_file", {"relative_path": "event.txt", "content": "ok"}, session_id=session_id)
    events = runtime.events.list_recent(session_id=session_id)

    assert result.status == "completed"
    assert any(event.type == "tool.started" for event in events)
    assert any(event.type == "tool.completed" for event in events)
