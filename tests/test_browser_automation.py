import json
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.projects import ProjectsStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.runtime.tools_registry import ToolsRegistry
from omega_agent.tools import browser as browser_tools


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "db_path": tmp_path / "omega.db",
        "browser_enabled": False,
        "browser_profile_dir": workspace / ".omega" / "browser-profile",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def allow_browser_project(config: OmegaConfig) -> None:
    ProjectsStore(config).update(
        "default",
        policy={
            "read_paths": ["."],
            "write_paths": ["."],
            "browser_allowed": True,
            "require_approval_for_write": False,
            "require_approval_for_shell": False,
        },
    )


def browser_session(config: OmegaConfig) -> str:
    sessions = SessionsStore(config)
    session = sessions.create_session("Browser")
    AgentProfilesStore(config)
    sessions.set_agent_profile(session.id, "omega-operator")
    return session.id


def test_browser_tools_are_absent_when_disabled(tmp_path: Path):
    config = cfg(tmp_path, browser_enabled=False)

    tool_ids = {tool.id for tool in ToolsRegistry(config).list()}

    assert "browser_open_url" not in tool_ids
    assert "browser_screenshot" not in tool_ids


def test_browser_file_url_is_refused_before_playwright(tmp_path: Path):
    config = cfg(tmp_path, browser_enabled=True)
    allow_browser_project(config)
    session_id = browser_session(config)

    result = ToolBroker(config).call("browser_open_url", {"url": "file:///C:/Users/alexandre/.ssh/id_rsa"}, session_id=session_id)

    assert result.status == "denied"
    assert "schema file interdit" in result.output


def test_browser_user_profile_path_is_refused(tmp_path: Path):
    workspace = tmp_path / "workspace"
    profile = workspace / ".omega" / "Google" / "Chrome" / "User Data" / "Default"
    config = cfg(tmp_path, browser_enabled=True, browser_profile_dir=profile)
    allow_browser_project(config)
    session_id = browser_session(config)

    result = ToolBroker(config).call("browser_get_title", {}, session_id=session_id)

    assert result.status == "denied"
    assert "Profil navigateur utilisateur refuse" in result.output


def test_browser_type_requires_approval(tmp_path: Path):
    config = cfg(tmp_path, browser_enabled=True, browser_require_approval=True)
    allow_browser_project(config)
    session_id = browser_session(config)

    result = ToolBroker(config).call("browser_type", {"selector": "#q", "text": "hello"}, session_id=session_id)

    assert result.status == "approval_required"
    assert result.approval_id


def test_browser_screenshot_is_saved_in_workspace(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, browser_enabled=True)

    class FakePage:
        url = "https://example.test"

        def screenshot(self, path: str, full_page: bool):
            Path(path).write_bytes(b"png")

    monkeypatch.setattr(browser_tools, "_ensure_page", lambda _config: FakePage())

    payload = json.loads(browser_tools._browser_screenshot(config))
    screenshot_path = (config.workspace / payload["path"]).resolve()

    assert payload["untrusted"] is True
    assert screenshot_path.exists()
    assert screenshot_path.parent == (config.workspace / ".omega" / "browser-screenshots").resolve()
