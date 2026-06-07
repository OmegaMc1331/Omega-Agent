from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import CODEX_DISCONNECTED_MESSAGE, create_app, serve_gateway


def test_gateway_health(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    client = TestClient(create_app(cfg))

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["version"]
    assert "uptime" in payload


def test_gateway_status_reports_local_config(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="gpt-test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.gateway.server.codex_login_status", lambda: (False, "not logged in"))
    client = TestClient(create_app(cfg))

    response = client.get("/api/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "codex"
    assert payload["model"] == "gpt-test"
    assert payload["workspace"] == str(tmp_path)
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["login_hint"] == CODEX_DISCONNECTED_MESSAGE


def test_gateway_chat_uses_runtime(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)

    class FakeRuntime:
        def __init__(self, config):
            self.config = config

        async def send_message(self, message: str, session_id: str | None = None) -> str:
            return f"Echo: {message}"

    monkeypatch.setattr("omega_agent.gateway.server.OmegaRuntime", FakeRuntime)
    client = TestClient(create_app(cfg))

    response = client.post("/api/chat", json={"message": "Bonjour Omega"})

    assert response.status_code == 200
    assert response.json()["message"] == "Echo: Bonjour Omega"
    assert response.json()["session_id"]


def test_gateway_static_path_traversal_does_not_expose_workspace_env(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    client = TestClient(create_app(cfg))

    response = client.get("/static/../.env")

    assert response.status_code != 200


def test_serve_gateway_uses_explicit_host_and_port(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    captured = {}

    def fake_run(app, host: str, port: int):
        captured["host"] = host
        captured["port"] = port
        captured["client"] = TestClient(app)

    monkeypatch.setattr("omega_agent.gateway.server.uvicorn.run", fake_run)
    monkeypatch.setattr("omega_agent.gateway.server.codex_login_status", lambda: (True, "logged in"))

    serve_gateway(cfg, host="127.0.0.1", port=9001, open_browser=False)

    response = captured["client"].get("/api/status")
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9001
    assert response.json()["port"] == 9001


def test_gateway_creates_session(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    client = TestClient(create_app(cfg))

    response = client.post("/api/sessions", json={"title": "Projet Omega"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Projet Omega"
    assert client.get("/api/sessions").json()[0]["id"] == payload["id"]


def test_gateway_tools_registry(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    client = TestClient(create_app(cfg))

    tools = client.get("/api/tools").json()

    by_id = {tool["id"]: tool for tool in tools}
    assert by_id["write_file"]["requires_approval"] is True
    assert by_id["run_shell"]["risk"] == "high"


def test_gateway_approval_lifecycle(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    app = create_app(cfg)
    approval = app.state.gateway_state.approvals.create("run_shell", {"command": "pytest"}, risk="high")
    client = TestClient(app)

    assert client.get("/api/approvals").json()[0]["status"] == "pending"
    response = client.post(f"/api/approvals/{approval.id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
