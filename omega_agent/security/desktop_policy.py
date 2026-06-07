from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from omega_agent.config import OmegaConfig

DESKTOP_TOOLS = {
    "desktop_screenshot",
    "desktop_locate_text_stub",
    "desktop_click",
    "desktop_type",
    "desktop_hotkey",
}
DESKTOP_ACTION_TOOLS = {"desktop_click", "desktop_type", "desktop_hotkey"}
PASSWORD_TERMS = {"password", "passwd", "passcode", "secret", "token", "credential", "api_key", "apikey"}
SENSITIVE_WINDOW_TERMS = {
    "password manager",
    "1password",
    "bitwarden",
    "lastpass",
    "keychain",
    "ssh",
    "private key",
    "wallet",
    "bank",
    "payment",
    "checkout",
    "credentials",
}


@dataclass(frozen=True)
class DesktopPolicyStatus:
    enabled: bool
    configured: bool
    requires_approval: bool
    screenshots_dir: str
    screenshots_dir_valid: bool
    dependency_available: bool
    last_screenshot: str
    error: str

    def as_api(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "requires_approval": self.requires_approval,
            "screenshots_dir": self.screenshots_dir,
            "screenshots_dir_valid": self.screenshots_dir_valid,
            "dependency_available": self.dependency_available,
            "last_screenshot": self.last_screenshot,
            "error": self.error,
            "warning": "Desktop automation controle l'ecran local. Les actions click/type/hotkey exigent approval et ne sont jamais silencieuses.",
        }


def desktop_screenshots_dir(config: OmegaConfig) -> Path:
    return (config.desktop_screenshots_dir or (config.workspace / ".omega" / "screenshots")).expanduser().resolve()


def validate_desktop_enabled(config: OmegaConfig) -> None:
    if not config.desktop_enabled:
        raise PermissionError("Desktop automation desactivee par OMEGA_DESKTOP_ENABLED=false.")


def validate_desktop_screenshots_dir(config: OmegaConfig) -> Path:
    screenshots_dir = desktop_screenshots_dir(config)
    workspace = config.workspace.resolve()
    omega_dir = (workspace / ".omega").resolve()
    if os.path.commonpath([str(workspace), str(screenshots_dir)]) != str(workspace):
        raise PermissionError("Dossier screenshots desktop refuse: il doit rester dans OMEGA_WORKSPACE.")
    if os.path.commonpath([str(omega_dir), str(screenshots_dir)]) != str(omega_dir):
        raise PermissionError("Dossier screenshots desktop refuse: utilisez un dossier sous .omega.")
    return screenshots_dir


def validate_desktop_tool_request(config: OmegaConfig, tool_id: str, arguments: dict, active_window_title: str = "") -> None:
    if tool_id not in DESKTOP_TOOLS:
        return
    validate_desktop_enabled(config)
    validate_desktop_screenshots_dir(config)
    if tool_id == "desktop_type":
        _deny_password_like_input(arguments)
    if tool_id in DESKTOP_ACTION_TOOLS:
        _deny_sensitive_window(active_window_title)


def desktop_action_requires_approval(tool_id: str) -> bool:
    return tool_id in DESKTOP_ACTION_TOOLS


def desktop_policy_status(config: OmegaConfig, dependency_available: bool, last_screenshot: str = "") -> DesktopPolicyStatus:
    error = ""
    screenshots_dir_valid = True
    try:
        validate_desktop_screenshots_dir(config)
    except PermissionError as exc:
        screenshots_dir_valid = False
        error = str(exc)
    if config.desktop_enabled and not dependency_available:
        error = "pyautogui non installe. Installez-le manuellement si vous voulez activer les actions desktop."
    return DesktopPolicyStatus(
        enabled=config.desktop_enabled,
        configured=bool(config.desktop_enabled and screenshots_dir_valid and dependency_available),
        requires_approval=config.desktop_require_approval,
        screenshots_dir=str(desktop_screenshots_dir(config)),
        screenshots_dir_valid=screenshots_dir_valid,
        dependency_available=dependency_available,
        last_screenshot=last_screenshot,
        error=error,
    )


def _deny_password_like_input(arguments: dict) -> None:
    haystack = " ".join(str(arguments.get(key) or "") for key in ("selector", "label", "field", "text")).lower()
    if any(term in haystack for term in PASSWORD_TERMS):
        raise PermissionError("Saisie desktop refusee: contenu ou champ de type mot de passe detecte.")


def _deny_sensitive_window(title: str) -> None:
    lowered = (title or "").lower()
    if lowered and any(term in lowered for term in SENSITIVE_WINDOW_TERMS):
        raise PermissionError("Action desktop refusee: fenetre sensible detectee.")
