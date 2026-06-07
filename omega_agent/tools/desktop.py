from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

from omega_agent.config import OmegaConfig
from omega_agent.security.desktop_policy import (
    desktop_policy_status,
    validate_desktop_enabled,
    validate_desktop_screenshots_dir,
    validate_desktop_tool_request,
)
from omega_agent.security.policy import log_action

_LAST_SCREENSHOT = ""


def pyautogui_available() -> bool:
    return importlib.util.find_spec("pyautogui") is not None


def desktop_status(config: OmegaConfig) -> dict:
    return desktop_policy_status(config, pyautogui_available(), _LAST_SCREENSHOT).as_api()


def active_window_title() -> str:
    if not pyautogui_available():
        return ""
    try:
        import pyautogui

        window = pyautogui.getActiveWindow()
        return str(getattr(window, "title", "") or "")
    except Exception:
        return ""


def _desktop_screenshot(config: OmegaConfig) -> str:
    global _LAST_SCREENSHOT
    validate_desktop_enabled(config)
    screenshots_dir = validate_desktop_screenshots_dir(config)
    if not pyautogui_available():
        return _json({"ok": False, "message": "pyautogui non installe. Installez-le manuellement pour capturer le desktop.", "untrusted": True})
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    filename = f"desktop-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.png"
    path = screenshots_dir / filename
    import pyautogui

    image = pyautogui.screenshot()
    image.save(str(path))
    _LAST_SCREENSHOT = str(path.relative_to(config.workspace))
    log_action(config, "desktop_screenshot", {"path": _LAST_SCREENSHOT})
    return _json({"ok": True, "path": _LAST_SCREENSHOT, "untrusted": True})


def _desktop_locate_text_stub(config: OmegaConfig, text: str = "") -> str:
    validate_desktop_enabled(config)
    log_action(config, "desktop_locate_text_stub", {"text_length": len(text)})
    return _json({"ok": False, "message": "OCR desktop non implemente en v0.1.", "query_length": len(text), "untrusted": True})


def _desktop_click(config: OmegaConfig, x: int, y: int) -> str:
    _validate_action(config, "desktop_click", {"x": x, "y": y})
    if not pyautogui_available():
        return _dependency_message("click")
    import pyautogui

    pyautogui.click(x=x, y=y)
    log_action(config, "desktop_click", {"x": x, "y": y, "visible_control": True})
    return _json({"ok": True, "message": "Click desktop execute apres approval.", "untrusted": True})


def _desktop_type(config: OmegaConfig, text: str, interval: float = 0.02) -> str:
    _validate_action(config, "desktop_type", {"text": text})
    if not pyautogui_available():
        return _dependency_message("type")
    import pyautogui

    pyautogui.write(text, interval=max(0, min(float(interval), 1)))
    log_action(config, "desktop_type", {"text_length": len(text), "visible_control": True})
    return _json({"ok": True, "typed_chars": len(text), "message": "Saisie desktop executee apres approval.", "untrusted": True})


def _desktop_hotkey(config: OmegaConfig, keys: list[str] | str) -> str:
    key_list = _keys(keys)
    _validate_action(config, "desktop_hotkey", {"keys": key_list})
    if not pyautogui_available():
        return _dependency_message("hotkey")
    import pyautogui

    pyautogui.hotkey(*key_list)
    log_action(config, "desktop_hotkey", {"keys": key_list, "visible_control": True})
    return _json({"ok": True, "keys": key_list, "message": "Hotkey desktop executee apres approval.", "untrusted": True})


def _validate_action(config: OmegaConfig, tool_id: str, arguments: dict) -> None:
    validate_desktop_tool_request(config, tool_id, arguments, active_window_title=active_window_title())


def _dependency_message(action: str) -> str:
    return _json({"ok": False, "message": f"pyautogui non installe. Action desktop '{action}' non executee.", "untrusted": True})


def _keys(keys: list[str] | str) -> list[str]:
    if isinstance(keys, str):
        values = [item.strip() for item in keys.replace("+", ",").split(",")]
    else:
        values = [str(item).strip() for item in keys]
    return [item for item in values if item]


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
