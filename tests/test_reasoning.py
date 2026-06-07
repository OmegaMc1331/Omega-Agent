from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent import OmegaRuntime
from omega_agent.runtime.approvals import ApprovalsStore
from omega_agent.runtime.reasoning import ReasoningStore, emit_reasoning_event
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker


def test_reasoning_event_created_at_chat_start_and_plan_visible(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "Réponse test")
    runtime = OmegaRuntime(cfg)
    session_id = runtime.sessions.create_session("Chat").id

    output = run_async(runtime.send_message("Analyse ce dossier sans lire de secrets", session_id=session_id))

    assert output == "Réponse test"
    events = ReasoningStore(cfg).list_for_session(session_id)
    assert events[0].type == "reasoning.started"
    assert any(event.type == "reasoning.plan" and event.visibility == "public" for event in events)


def test_tool_call_visible_in_reasoning_stream(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, reasoning_detail="normal")
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    session_id = SessionsStore(cfg).create_session("Tools").id

    result = ToolBroker(cfg).call("read_file", {"relative_path": "notes.txt"}, session_id=session_id)

    assert result.status == "completed"
    events = ReasoningStore(cfg).list_for_session(session_id)
    event_types = {event.type for event in events}
    assert "reasoning.tool_requested" in event_types
    assert "reasoning.tool_started" in event_types
    assert "reasoning.tool_completed" in event_types
    assert "reasoning.observation" in event_types


def test_approval_visible_in_reasoning_stream(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=True)
    session_id = SessionsStore(cfg).create_session("Approval").id

    approval = ApprovalsStore(cfg).create("run_shell", {"command": "pytest"}, risk="high", session_id=session_id, reason="Action sensible")

    events = ReasoningStore(cfg).list_for_session(session_id)
    assert approval.status == "pending"
    assert any(event.type == "reasoning.approval_required" and event.status == "pending" for event in events)


def test_reasoning_redacts_secrets(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, reasoning_detail="normal")
    session_id = SessionsStore(cfg).create_session("Redaction").id

    emit_reasoning_event(
        session_id,
        "reasoning.observation",
        "Secret",
        "sk-abcdefghijklmnopqrstuvwxyz Authorization: Bearer abcdefghijklmnop password=hunter2 C:\\Users\\alex\\.ssh\\id_rsa",
        status="completed",
        metadata={"token": "abcdef1234567890", "path": "C:\\Users\\alex\\.ssh\\id_rsa"},
        config=cfg,
    )

    payload = ReasoningStore(cfg).list_for_session(session_id)[0].as_api()
    rendered = str(payload)
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in rendered
    assert "abcdefghijklmnop" not in rendered
    assert "hunter2" not in rendered
    assert ".ssh" not in rendered
    assert "[REDACTED]" in rendered


def test_internal_reasoning_events_not_sent_to_ui(tmp_path: Path):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False)
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("Internal")
    app.state.gateway_state.reasoning.add(
        session.id,
        "reasoning.analysis",
        "Internal",
        "hidden",
        status="completed",
        visibility="internal",
    )
    app.state.gateway_state.reasoning.add(
        session.id,
        "reasoning.summary",
        "Public",
        "visible",
        status="completed",
        visibility="public",
    )
    client = TestClient(app)

    response = client.get(f"/api/sessions/{session.id}/reasoning")

    assert response.status_code == 200
    events = response.json()
    assert [event["title"] for event in events] == ["Public"]


def test_reasoning_stream_false_disables_events(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex", reasoning_stream=False)
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    runtime = OmegaRuntime(cfg)
    session_id = runtime.sessions.create_session("Off").id

    run_async(runtime.send_message("bonjour", session_id=session_id))

    assert ReasoningStore(cfg).list_for_session(session_id) == []


def test_reasoning_endpoint_by_session_and_message(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    app = create_app(cfg)
    client = TestClient(app)
    session = app.state.gateway_state.sessions.create_session("Endpoint")

    response = client.post("/api/chat", json={"session_id": session.id, "message": "bonjour"})

    assert response.status_code == 200
    session_events = client.get(f"/api/sessions/{session.id}/reasoning").json()
    user_message = app.state.gateway_state.sessions.list_messages(session.id)[0]
    message_events = client.get(f"/api/messages/{user_message.id}/reasoning").json()
    assert session_events
    assert message_events
    assert session_events[0]["message_id"] == user_message.id


def test_websocket_sends_reasoning_events(tmp_path: Path, monkeypatch):
    cfg = OmegaConfig(model="test", workspace=tmp_path, require_approval=False, provider="codex")
    monkeypatch.setattr("omega_agent.runtime.agent.run_codex_turn", lambda config, history, user_input: "ok")
    app = create_app(cfg)
    session = app.state.gateway_state.sessions.create_session("WS")
    client = TestClient(app)

    with client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"type": "chat.send", "session_id": session.id, "message": "hello"})
        messages = []
        for _ in range(12):
            item = websocket.receive_json()
            messages.append(item)
            if item.get("type") == "message.completed":
                break

    assert any(item.get("type") == "reasoning.started" for item in messages)
    assert any(item.get("type") == "reasoning.plan" for item in messages)
    assert any(item.get("type") == "message.completed" for item in messages)


def run_async(awaitable):
    import asyncio

    return asyncio.run(awaitable)
