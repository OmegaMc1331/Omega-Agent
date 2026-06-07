from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.router import choose_agent_profile
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return OmegaConfig(model="test", workspace=workspace, require_approval=False, db_path=tmp_path / "omega.db")


def test_builtin_agent_profiles_are_created(tmp_path: Path):
    profiles = {profile.id: profile for profile in AgentProfilesStore(cfg(tmp_path)).list()}

    assert {"omega-core", "omega-coder", "omega-research", "omega-security", "omega-operator"} <= set(profiles)
    assert profiles["omega-core"].name == "Omega Core"
    assert "run_shell" not in profiles["omega-research"].allowed_tools


def test_tools_are_filtered_by_active_agent_profile(tmp_path: Path):
    config = cfg(tmp_path)
    sessions = SessionsStore(config)
    session = sessions.create_session("Security")
    sessions.set_agent_profile(session.id, "omega-security")

    result = ToolBroker(config).call("write_file", {"relative_path": "a.txt", "content": "x"}, session_id=session.id)

    assert result.status == "denied"
    assert "profil agent" in result.output


def test_session_can_change_agent_profile(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))
    session = client.post("/api/sessions", json={"title": "Agent"}).json()

    response = client.post(f"/api/sessions/{session['id']}/agent", json={"agent_id": "omega-coder"})

    assert response.status_code == 200
    assert response.json()["active_agent_profile_id"] == "omega-coder"
    events = client.get(f"/api/events?session_id={session['id']}&type=agent.switched").json()
    assert events[0]["payload"]["to"] == "omega-coder"


def test_router_selects_specialized_profiles():
    assert choose_agent_profile("corrige ce bug et lance les tests") == "omega-coder"
    assert choose_agent_profile("audit securite et vulnerabilite") == "omega-security"
    assert choose_agent_profile("automatiser ouvrir et cliquer") == "omega-operator"
    assert choose_agent_profile("bonjour") == "omega-core"


def test_disabled_agent_profile_is_unusable(tmp_path: Path):
    config = cfg(tmp_path)
    profiles = AgentProfilesStore(config)
    profiles.update("omega-coder", enabled=False)
    sessions = SessionsStore(config)
    session = sessions.create_session("Disabled")
    sessions.set_agent_profile(session.id, "omega-coder")

    result = ToolBroker(config).call("read_file", {"relative_path": "a.txt"}, session_id=session.id)

    assert result.status == "denied"
    assert "desactive" in result.output
