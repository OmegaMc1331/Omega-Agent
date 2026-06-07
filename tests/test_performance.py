from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from omega_agent.codex_backend import clear_codex_auth_cache, run_codex_turn
from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.memory import MemoryStore
from omega_agent.runtime.reasoning import ReasoningStore


def test_codex_auth_status_cached_across_turns(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex", codex_auth_cache_seconds=300)
    clear_codex_auth_cache()
    calls = {"login": 0}

    monkeypatch.setattr("omega_agent.codex_backend.codex_version", lambda: "codex 1.0")
    monkeypatch.setattr("omega_agent.codex_backend.shutil.which", lambda _: "codex")

    def fake_login_status():
        calls["login"] += 1
        return True, "logged in"

    def fake_run(command, **kwargs):
        output_file = command[command.index("--output-last-message") + 1]
        Path(output_file).write_text("ok", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("omega_agent.codex_backend.codex_login_status", fake_login_status)
    monkeypatch.setattr("omega_agent.codex_backend.subprocess.run", fake_run)

    assert run_codex_turn(cfg, [], "bonjour") == "ok"
    assert run_codex_turn(cfg, [], "encore") == "ok"
    assert calls["login"] == 1


def test_context_builder_respects_memory_limit(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, max_memory_results=3)
    store = MemoryStore(cfg)
    for index in range(8):
        store.create(f"omega perf memory {index}", key=f"perf-{index}")

    context = build_context(cfg, None, query="omega perf")

    assert len(context["memories"]) == 3


def test_chat_context_respects_max_history(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex", max_history_messages=5)
    captured = {}
    runtime = OmegaRuntime(cfg)
    session_id = runtime.sessions.create_session("History").id
    for index in range(12):
        runtime.sessions.add_message(session_id, "user", f"old {index}")

    def fake_turn(config, history, user_input):
        captured["history_len"] = len(history)
        return "ok"

    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", fake_turn)

    assert run_async(runtime.send_message("nouveau", session_id=session_id)) == "ok"
    assert captured["history_len"] == 6


def test_reasoning_minimal_emits_compact_event_set(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex", reasoning_detail="minimal")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    runtime = OmegaRuntime(cfg)
    session_id = runtime.sessions.create_session("Minimal").id

    run_async(runtime.send_message("bonjour", session_id=session_id))

    event_types = [event.type for event in ReasoningStore(cfg).list_for_session(session_id)]
    assert event_types == ["reasoning.started", "reasoning.plan", "reasoning.completed"]


def test_performance_trace_created_and_endpoint_returns_recent(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("Perf")
    client = TestClient(app)

    response = client.post("/api/chat", json={"session_id": session.id, "message": "bonjour"})
    traces = client.get("/api/performance/recent").json()

    assert response.status_code == 200
    assert traces
    assert traces[0]["session_id"] == session.id
    assert "total_duration" in traces[0]["steps_ms"]


def test_chat_does_not_restart_gateway(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    monkeypatch.setattr("omega_agent.gateway.server.serve_gateway", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("gateway restarted")))
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("No restart")
    client = TestClient(app)

    response = client.post("/api/chat", json={"session_id": session.id, "message": "bonjour"})

    assert response.status_code == 200


def test_websocket_sends_accepted_before_completion(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("WS accepted")
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "chat.send", "session_id": session.id, "message": "hello"})
        first = websocket.receive_json()

    assert first["type"] == "message.accepted"


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
