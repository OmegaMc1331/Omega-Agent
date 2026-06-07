from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from omega_agent.config import OmegaConfig

BROWSER_TOOLS = {
    "browser_open_url",
    "browser_get_title",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "browser_extract_text",
    "browser_close",
}
SENSITIVE_BROWSER_SCHEMES = {"file", "chrome", "edge"}
DENIED_ABOUT_URLS = {"about:config", "about:profiles", "about:debugging", "about:preferences"}
SENSITIVE_ACTION_TERMS = {
    "login",
    "signin",
    "sign-in",
    "password",
    "checkout",
    "payment",
    "pay",
    "card",
    "credit",
    "upload",
    "download",
    "submit",
}


@dataclass(frozen=True)
class BrowserPolicyStatus:
    enabled: bool
    configured: bool
    headless: bool
    profile_dir: str
    profile_valid: bool
    error: str

    def as_api(self) -> dict:
        return {
            "enabled": self.enabled,
            "configured": self.configured,
            "headless": self.headless,
            "profile_dir": self.profile_dir,
            "profile_valid": self.profile_valid,
            "error": self.error,
        }


def browser_profile_dir(config: OmegaConfig) -> Path:
    return (config.browser_profile_dir or (config.workspace / ".omega" / "browser-profile")).expanduser().resolve()


def validate_browser_enabled(config: OmegaConfig) -> None:
    if not config.browser_enabled:
        raise PermissionError("Browser automation desactivee par OMEGA_BROWSER_ENABLED=false.")


def validate_browser_profile_dir(config: OmegaConfig) -> Path:
    profile_dir = browser_profile_dir(config)
    workspace = config.workspace.resolve()
    omega_dir = (workspace / ".omega").resolve()
    if os.path.commonpath([str(workspace), str(profile_dir)]) != str(workspace):
        raise PermissionError("Profil navigateur refuse: il doit rester dans OMEGA_WORKSPACE.")
    if os.path.commonpath([str(omega_dir), str(profile_dir)]) != str(omega_dir):
        raise PermissionError("Profil navigateur refuse: utilisez un profil isole sous .omega.")
    if _looks_like_user_browser_profile(profile_dir):
        raise PermissionError("Profil navigateur utilisateur refuse.")
    return profile_dir


def validate_browser_url(url: str) -> str:
    clean = (url or "").strip()
    if not clean:
        raise ValueError("URL navigateur vide.")
    lowered = clean.lower()
    parsed = urlparse(clean)
    scheme = parsed.scheme.lower()
    if scheme in SENSITIVE_BROWSER_SCHEMES:
        raise PermissionError(f"URL navigateur refusee: schema {scheme} interdit.")
    if lowered in DENIED_ABOUT_URLS or lowered.startswith("about:config"):
        raise PermissionError("URL navigateur refusee: page de configuration interdite.")
    if scheme and scheme not in {"http", "https", "about"}:
        raise PermissionError(f"URL navigateur refusee: schema {scheme} non autorise.")
    if scheme == "about" and lowered != "about:blank":
        raise PermissionError("URL navigateur about refusee hors about:blank.")
    return clean


def validate_browser_tool_request(config: OmegaConfig, tool_id: str, arguments: dict) -> None:
    if tool_id not in BROWSER_TOOLS:
        return
    validate_browser_enabled(config)
    validate_browser_profile_dir(config)
    if tool_id == "browser_open_url":
        validate_browser_url(str(arguments.get("url") or ""))


def browser_action_requires_approval(tool_id: str, arguments: dict) -> bool:
    if tool_id == "browser_type":
        return True
    if tool_id == "browser_click":
        selector = str(arguments.get("selector") or "").lower()
        label = str(arguments.get("label") or "").lower()
        haystack = f"{selector} {label}"
        return True if not haystack.strip() else any(term in haystack for term in SENSITIVE_ACTION_TERMS) or True
    if tool_id == "browser_open_url":
        url = str(arguments.get("url") or "").lower()
        return any(term in url for term in {"login", "signin", "checkout", "payment", "upload", "download"})
    return False


def browser_policy_status(config: OmegaConfig, playwright_available: bool) -> BrowserPolicyStatus:
    error = ""
    profile_valid = True
    try:
        validate_browser_profile_dir(config)
    except PermissionError as exc:
        profile_valid = False
        error = str(exc)
    if config.browser_enabled and not playwright_available:
        error = "Playwright non installe."
    return BrowserPolicyStatus(
        enabled=config.browser_enabled,
        configured=bool(config.browser_enabled and playwright_available and profile_valid),
        headless=config.browser_headless,
        profile_dir=str(browser_profile_dir(config)),
        profile_valid=profile_valid,
        error=error,
    )


def _looks_like_user_browser_profile(path: Path) -> bool:
    lowered = str(path).lower().replace("\\", "/")
    forbidden_fragments = (
        "/google/chrome/user data",
        "/microsoft/edge/user data",
        "/mozilla/firefox/profiles",
        "/brave-browser/user data",
        "/chromium/user data",
    )
    return any(fragment in lowered for fragment in forbidden_fragments)
