from pathlib import Path

from fastapi.testclient import TestClient

from omega_agent.config import OmegaConfig
from omega_agent.gateway.server import create_app
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker


def cfg(tmp_path: Path) -> OmegaConfig:
    workspace = tmp_path / "global"
    workspace.mkdir()
    return OmegaConfig(model="test", workspace=workspace, require_approval=False, db_path=tmp_path / "omega.db")


def test_project_creation_api(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    client = TestClient(create_app(config))

    response = client.post(
        "/api/projects",
        json={
            "name": "Project A",
            "root_path": str(project_root),
            "policy": {"allowed_tools": ["read_file"], "read_paths": ["."]},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Project A"
    assert payload["root_path"] == str(project_root.resolve())
    assert payload["policy"]["allowed_tools"] == ["read_file"]
    assert client.get("/api/projects").json()


def test_session_can_be_linked_to_project(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    app = create_app(config)
    client = TestClient(app)
    project = app.state.gateway_state.projects.create("Project A", str(project_root))
    session = client.post("/api/sessions", json={"title": "Linked"}).json()

    response = client.post(f"/api/sessions/{session['id']}/project", json={"project_id": project.id})

    assert response.status_code == 200
    assert response.json()["project_id"] == project.id


def test_read_file_respects_project_root(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    (project_root / "inside.txt").write_text("inside", encoding="utf-8")
    (config.workspace / "inside.txt").write_text("global", encoding="utf-8")
    projects = ProjectsStore(config)
    project = projects.create("Project A", str(project_root), policy={"allowed_tools": ["read_file"], "read_paths": ["."]})
    sessions = SessionsStore(config)
    session = sessions.create_session("Read")
    sessions.set_project(session.id, project.id)

    result = ToolBroker(config).call("read_file", {"relative_path": "inside.txt"}, session_id=session.id)

    assert result.status == "completed"
    assert result.output == "inside"


def test_project_path_traversal_is_refused(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    project = ProjectsStore(config).create("Project A", str(project_root), policy={"allowed_tools": ["read_file"], "read_paths": ["."]})
    sessions = SessionsStore(config)
    session = sessions.create_session("Traversal")
    sessions.set_project(session.id, project.id)

    result = ToolBroker(config).call("read_file", {"relative_path": "../secret.txt"}, session_id=session.id)

    assert result.status == "denied"
    assert "hors projet" in result.output


def test_project_refuses_sensitive_paths(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    (project_root / ".ssh").mkdir(parents=True)
    project = ProjectsStore(config).create("Project A", str(project_root), policy={"allowed_tools": ["read_file"], "read_paths": ["."]})
    sessions = SessionsStore(config)
    session = sessions.create_session("Sensitive")
    sessions.set_project(session.id, project.id)

    result = ToolBroker(config).call("read_file", {"relative_path": ".ssh/id_rsa"}, session_id=session.id)

    assert result.status == "denied"
    assert "sensible" in result.output


def test_shell_uses_project_cwd(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    project = ProjectsStore(config).create(
        "Project A",
        str(project_root),
        policy={"allowed_tools": ["run_shell"], "shell_allowlist": ["pwd"], "require_approval_for_shell": False},
    )
    sessions = SessionsStore(config)
    session = sessions.create_session("Shell")
    AgentProfilesStore(config).create("shell-test", "Shell Test", allowed_tools=["run_shell"], policy={})
    sessions.set_agent_profile(session.id, "shell-test")
    sessions.set_project(session.id, project.id)
    captured = {}

    def fake_run(args, cwd, env, capture_output, text, timeout, check):
        captured["cwd"] = cwd

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()

    monkeypatch.setattr("omega_agent.tools.shell.subprocess.run", fake_run)

    result = ToolBroker(config).call("run_shell", {"command": "pwd"}, session_id=session.id)

    assert result.status == "completed"
    assert captured["cwd"] == project_root.resolve()


def test_project_tool_permissions_are_applied(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    project = ProjectsStore(config).create("Project A", str(project_root), policy={"allowed_tools": ["read_file"], "read_paths": ["."]})
    sessions = SessionsStore(config)
    session = sessions.create_session("Tools")
    sessions.set_project(session.id, project.id)

    result = ToolBroker(config).call("run_shell", {"command": "pwd"}, session_id=session.id)

    assert result.status == "denied"
    assert "non autorise" in result.output


def test_disabled_project_is_unusable(tmp_path: Path):
    config = cfg(tmp_path)
    project_root = tmp_path / "project-a"
    project_root.mkdir()
    projects = ProjectsStore(config)
    project = projects.create("Project A", str(project_root), enabled=False)
    sessions = SessionsStore(config)
    session = sessions.create_session("Disabled")
    sessions.set_project(session.id, project.id)

    result = ToolBroker(config).call("read_file", {"relative_path": "a.txt"}, session_id=session.id)

    assert result.status == "denied"
    assert "desactive" in result.output
