import json
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.runtime.agent_profiles import AgentProfilesStore
from omega_agent.runtime.sessions import SessionsStore
from omega_agent.runtime.tool_broker import ToolBroker
from omega_agent.runtime.tools_registry import ToolsRegistry
from omega_agent.tools import desktop as desktop_tools


def cfg(tmp_path: Path, **overrides) -> OmegaConfig:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    values = {
        "model": "test",
        "workspace": workspace,
        "require_approval": False,
        "db_path": tmp_path / "omega.db",
        "desktop_enabled": False,
        "desktop_screenshots_dir": workspace / ".omega" / "screenshots",
    }
    values.update(overrides)
    return OmegaConfig(**values)


def desktop_session(config: OmegaConfig) -> str:
    sessions = SessionsStore(config)
    session = sessions.create_session("Desktop")
    profiles = AgentProfilesStore(config)
    profiles.create(
        "desktop-test",
        "Desktop Test",
        allowed_tools=["desktop_screenshot", "desktop_locate_text_stub", "desktop_click", "desktop_type", "desktop_hotkey"],
        policy={},
    )
    sessions.set_agent_profile(session.id, "desktop-test")
    return session.id


def test_desktop_tools_are_absent_when_disabled(tmp_path: Path):
    config = cfg(tmp_path, desktop_enabled=False)

    tool_ids = {tool.id for tool in ToolsRegistry(config).list()}

    assert "desktop_screenshot" not in tool_ids
    assert "desktop_click" not in tool_ids


def test_desktop_click_and_type_require_approval(tmp_path: Path):
    config = cfg(tmp_path, desktop_enabled=True, desktop_require_approval=True)
    session_id = desktop_session(config)

    click = ToolBroker(config).call("desktop_click", {"x": 10, "y": 10}, session_id=session_id)
    typed = ToolBroker(config).call("desktop_type", {"text": "hello"}, session_id=session_id)

    assert click.status == "approval_required"
    assert click.approval_id
    assert typed.status == "approval_required"
    assert typed.approval_id


def test_desktop_dependency_absent_does_not_crash(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, desktop_enabled=True)
    session_id = desktop_session(config)
    monkeypatch.setattr(desktop_tools, "pyautogui_available", lambda: False)

    result = ToolBroker(config).call("desktop_screenshot", {}, session_id=session_id)

    assert result.status == "completed"
    assert "pyautogui non installe" in result.output


def test_desktop_type_refuses_detected_password(tmp_path: Path):
    config = cfg(tmp_path, desktop_enabled=True)
    session_id = desktop_session(config)

    result = ToolBroker(config).call("desktop_type", {"label": "password", "text": "secret-value"}, session_id=session_id)

    assert result.status == "denied"
    assert "mot de passe" in result.output


def test_desktop_screenshot_is_saved_in_workspace(tmp_path: Path, monkeypatch):
    config = cfg(tmp_path, desktop_enabled=True)

    class FakeImage:
        def save(self, path: str):
            Path(path).write_bytes(b"png")

    class FakePyAutoGUI:
        @staticmethod
        def screenshot():
            return FakeImage()

    monkeypatch.setattr(desktop_tools, "pyautogui_available", lambda: True)
    monkeypatch.setitem(__import__("sys").modules, "pyautogui", FakePyAutoGUI)

    payload = json.loads(desktop_tools._desktop_screenshot(config))
    screenshot_path = (config.workspace / payload["path"]).resolve()

    assert payload["ok"] is True
    assert payload["untrusted"] is True
    assert screenshot_path.exists()
    assert screenshot_path.parent == (config.workspace / ".omega" / "screenshots").resolve()
