from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.context_builder import build_context
from omega_agent.runtime.scheduler import ScheduledTasksStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.standing_orders import StandingOrdersStore
from omega_agent.runtime.tool_broker import ToolBroker


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "db_path": tmp_path / "omega.db",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def test_create_scheduled_task(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))

    response = client.post(
        "/api/scheduled-tasks",
        json={"title": "Daily scan", "prompt": "scan workspace", "schedule_type": "interval", "schedule_value": "60"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Daily scan"
    assert payload["next_run_at"]


def test_run_now_creates_job(tmp_path: Path):
    client = TestClient(create_app(cfg(tmp_path)))
    task = client.post("/api/scheduled-tasks", json={"title": "Now", "prompt": "summarize", "schedule_type": "interval", "schedule_value": "60"}).json()

    response = client.post(f"/api/scheduled-tasks/{task['id']}/run-now")

    assert response.status_code == 200
    assert response.json()["job"]["kind"] == "run_scheduled_prompt"
    assert client.get("/api/jobs").json()[0]["kind"] == "run_scheduled_prompt"


def test_disabled_task_does_not_run(tmp_path: Path):
    config = cfg(tmp_path)
    task = ScheduledTasksStore(config).create("Disabled", "do it", enabled=False)
    client = TestClient(create_app(config))

    response = client.post(f"/api/scheduled-tasks/{task.id}/run-now")

    assert response.status_code == 403
    assert client.get("/api/jobs").json() == []


def test_standing_order_injected_in_context(tmp_path: Path):
    config = cfg(tmp_path)
    StandingOrdersStore(config).create("Tone", "Toujours repondre brievement.", scope="global", priority=10)

    context = build_context(config, None, query="bonjour")

    assert "Toujours repondre brievement." in context["system_prompt"]
    assert context["standing_orders"][0]["title"] == "Tone"


def test_sensitive_action_from_scheduled_session_requires_approval(tmp_path: Path):
    config = cfg(tmp_path)
    AgentProfilesStore(config).create("scheduled-shell", "Scheduled Shell", allowed_tools=["run_shell"], policy={})
    sessions = SessionsStore(config)
    session = sessions.create_session("Scheduled")
    sessions.set_agent_profile(session.id, "scheduled-shell")
    sessions.merge_metadata(session.id, {"scheduled_task": True})

    result = ToolBroker(config).call("run_shell", {"command": "pytest"}, session_id=session.id)

    assert result.status == "approval_required"
