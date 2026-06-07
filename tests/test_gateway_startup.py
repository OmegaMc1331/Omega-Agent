import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import PortOwner, create_app, serve_gateway
from omega_agent.runtime.sessions import SessionsStore


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return OmegaConfig(model="test", workspace=workspace, require_approval=True, db_path=tmp_path / "omega.db")


def test_port_already_used_by_gateway_reuses_for_omega(monkeypatch, tmp_path: Path):
    opened = []
    uvicorn_called = []
    monkeypatch.setattr("omega_agent.gateway.server.is_gateway_running", lambda host, port: True)
    monkeypatch.setattr("omega_agent.gateway.server.find_port_owner", lambda port: None)
    monkeypatch.setattr("omega_agent.gateway.server.webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr("omega_agent.gateway.server.uvicorn.run", lambda *args, **kwargs: uvicorn_called.append((args, kwargs)))

    serve_gateway(cfg(tmp_path), "127.0.0.1", 8765, open_browser=True, reuse_existing=True)

    assert opened == ["http://127.0.0.1:8765"]
    assert uvicorn_called == []


def test_port_used_by_other_process_reports_pid(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("omega_agent.gateway.server.is_gateway_running", lambda host, port: False)
    monkeypatch.setattr("omega_agent.gateway.server.find_port_owner", lambda port: PortOwner(4242, "python other.py"))

    with pytest.raises(RuntimeError, match="PID 4242"):
        serve_gateway(cfg(tmp_path), "127.0.0.1", 8765, open_browser=False)


def test_chat_send_does_not_start_new_server(monkeypatch, tmp_path: Path):
    app = create_app(cfg(tmp_path))
    session = SessionsStore(app.state.gateway_state.config).create_session("Chat")
    started = []
    monkeypatch.setattr("omega_agent.gateway.server.uvicorn.run", lambda *args, **kwargs: started.append(True))

    class FakeRuntime:
        async def send_message(self, message: str, session_id: str | None = None) -> str:
            return "ok"

    app.state.gateway_state._runtime = FakeRuntime()
    client = TestClient(app)

    response = client.post("/api/chat", json={"session_id": session.id, "message": "hello"})

    assert response.status_code == 200
    assert response.json()["message"] == "ok"
    assert started == []


def test_ws_send_does_not_start_new_server(monkeypatch, tmp_path: Path):
    app = create_app(cfg(tmp_path))
    session = SessionsStore(app.state.gateway_state.config).create_session("WS")
    started = []
    monkeypatch.setattr("omega_agent.gateway.server.uvicorn.run", lambda *args, **kwargs: started.append(True))

    class FakeRuntime:
        async def send_message(self, message: str, session_id: str | None = None) -> str:
            return "ok"

    app.state.gateway_state._runtime = FakeRuntime()
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "chat.send", "session_id": session.id, "message": "hello"})
        messages = [websocket.receive_json() for _ in range(4)]

    assert any(message.get("type") == "message.completed" for message in messages)
    assert started == []


def test_omega_opens_browser_if_gateway_already_running(monkeypatch, tmp_path: Path):
    opened = []
    uvicorn_called = []
    monkeypatch.setattr(sys, "argv", ["omega"])
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("OMEGA_DB_PATH", str(tmp_path / "omega.db"))
    monkeypatch.setattr("omega_agent.gateway.server.is_gateway_running", lambda host, port: True)
    monkeypatch.setattr("omega_agent.gateway.server.webbrowser.open", lambda url: opened.append(url))
    monkeypatch.setattr("omega_agent.gateway.server.uvicorn.run", lambda *args, **kwargs: uvicorn_called.append(True))

    from omega_agent.main import run

    run()

    assert opened == ["http://127.0.0.1:8765"]
    assert uvicorn_called == []


def test_omega_serve_fails_cleanly_if_port_occupied(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(sys, "argv", ["omega", "serve", "--no-open"])
    monkeypatch.setenv("OMEGA_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("OMEGA_DB_PATH", str(tmp_path / "omega.db"))
    monkeypatch.setattr("omega_agent.gateway.server.is_gateway_running", lambda host, port: True)

    from omega_agent.main import run

    with pytest.raises(SystemExit) as exc:
        run()

    assert exc.value.code == 1
