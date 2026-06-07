import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.multi_agent import MultiAgentRuntime
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return OmegaConfig(model="test", workspace=workspace, require_approval=False, db_path=tmp_path / "omega.db")


def test_delegation_creation_api(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))
    session = client.post("/api/sessions", json={"title": "Delegation"}).json()

    response = client.post(
        "/api/delegations",
        json={"session_id": session["id"], "child_agent_id": "omega-research", "task": "synthetise cette session"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == session["id"]
    assert payload["parent_agent_id"] == "omega-core"
    assert payload["child_agent_id"] == "omega-research"
    assert payload["status"] == "completed"
    assert "omega-research" in payload["result"]


def test_child_agent_inherits_parent_restrictions(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Restrictions")

    delegation = MultiAgentRuntime(config).delegate(
        session.id,
        "omega-coder",
        "corrige ce bug",
        allowed_tools=["read_file", "run_shell"],
        run_now=True,
    )

    metadata = delegation.metadata
    result = json.loads(delegation.result)
    assert metadata["allowed_tools"] == ["read_file"]
    assert result["allowed_tools"] == ["read_file"]
    assert "run_shell" not in result["allowed_tools"]


def test_max_depth_is_applied(tmp_path: Path):
    config = cfg(tmp_path)
    session = SessionsStore(config).create_session("Depth")

    with pytest.raises(PermissionError, match="Profondeur maximale"):
        MultiAgentRuntime(config).delegate(session.id, "omega-research", "nested task", depth=2)


def test_sensitive_action_from_child_profile_requires_approval(tmp_path: Path):
    config = cfg(tmp_path)
    sessions = SessionsStore(config)
    session = sessions.create_session("Child Approval")
    sessions.set_agent_profile(session.id, "omega-coder")

    result = ToolBroker(config).call("run_shell", {"command": "pwd"}, session_id=session.id)

    assert result.status == "approval_required"
    assert result.approval_id


def test_delegation_result_returns_to_parent_session(tmp_path: Path):
    config = cfg(tmp_path)
    sessions = SessionsStore(config)
    session = sessions.create_session("Parent")

    delegation = MultiAgentRuntime(config).delegate(session.id, "omega-security", "audit rapide")

    messages = sessions.list_messages(session.id)
    assert delegation.status == "completed"
    assert messages[-1].role == "assistant"
    assert "Delegation omega-security terminee" in messages[-1].content
    assert json.loads(messages[-1].metadata_json)["delegation_id"] == delegation.id


def test_only_core_can_delegate_by_default(tmp_path: Path):
    config = cfg(tmp_path)
    sessions = SessionsStore(config)
    session = sessions.create_session("No recursion")
    sessions.set_agent_profile(session.id, "omega-coder")

    result = ToolBroker(config).call(
        "delegate_to_agent",
        {"child_agent_id": "omega-research", "task": "cherche"},
        session_id=session.id,
    )

    assert result.status == "denied"
    assert "profil agent" in result.output


def test_disabled_child_agent_is_unusable(tmp_path: Path):
    config = cfg(tmp_path)
    AgentProfilesStore(config).update("omega-research", enabled=False)
    session = SessionsStore(config).create_session("Disabled child")

    with pytest.raises(PermissionError, match="Profil enfant"):
        MultiAgentRuntime(config).delegate(session.id, "omega-research", "cherche")
