from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from omega_agent.config import OmegaConfig
from omega_agent.security.browser_policy import (
    browser_policy_status,
    validate_browser_enabled,
    validate_browser_profile_dir,
    validate_browser_url,
)
from omega_agent.security.policy import log_action


@dataclass
class BrowserRuntime:
    playwright: object | None = None
    context: object | None = None
    page: object | None = None
    last_url: str = ""
    last_screenshot: str = ""


_STATE = BrowserRuntime()
_LOCK = RLock()


def playwright_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def browser_status(config: OmegaConfig) -> dict:
    with _LOCK:
        status = browser_policy_status(config, playwright_available()).as_api()
        status.update(
            {
                "running": _STATE.context is not None,
                "last_url": _STATE.last_url,
                "last_screenshot": _STATE.last_screenshot,
            }
        )
        return status


def _browser_open_url(config: OmegaConfig, url: str) -> str:
    clean_url = validate_browser_url(url)
    page = _ensure_page(config)
    page.goto(clean_url, wait_until="domcontentloaded", timeout=15000)
    _STATE.last_url = page.url
    log_action(config, "browser_open_url", {"url": _STATE.last_url})
    return _json({"ok": True, "url": _STATE.last_url, "title": page.title(), "untrusted": True})


def _browser_get_title(config: OmegaConfig) -> str:
    page = _ensure_page(config)
    return _json({"title": page.title(), "url": page.url, "untrusted": True})


def _browser_screenshot(config: OmegaConfig, full_page: bool = True) -> str:
    page = _ensure_page(config)
    screenshot_dir = config.workspace / ".omega" / "browser-screenshots"
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    filename = f"browser-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}.png"
    path = screenshot_dir / filename
    page.screenshot(path=str(path), full_page=full_page)
    _STATE.last_url = page.url
    _STATE.last_screenshot = str(path.relative_to(config.workspace))
    log_action(config, "browser_screenshot", {"path": _STATE.last_screenshot, "url": _STATE.last_url})
    return _json({"path": _STATE.last_screenshot, "url": _STATE.last_url, "untrusted": True})


def _browser_click(config: OmegaConfig, selector: str) -> str:
    if not selector.strip():
        raise ValueError("Selector requis.")
    page = _ensure_page(config)
    page.locator(selector).first.click(timeout=5000)
    _STATE.last_url = page.url
    log_action(config, "browser_click", {"selector": selector, "url": _STATE.last_url})
    return _json({"ok": True, "url": _STATE.last_url, "untrusted": True})


def _browser_type(config: OmegaConfig, selector: str, text: str) -> str:
    if not selector.strip():
        raise ValueError("Selector requis.")
    page = _ensure_page(config)
    page.locator(selector).first.fill(text, timeout=5000)
    _STATE.last_url = page.url
    log_action(config, "browser_type", {"selector": selector, "text_length": len(text), "url": _STATE.last_url})
    return _json({"ok": True, "url": _STATE.last_url, "typed_chars": len(text), "untrusted": True})


def _browser_extract_text(config: OmegaConfig, selector: str = "body", limit: int = 12000) -> str:
    page = _ensure_page(config)
    target = selector.strip() or "body"
    text = page.locator(target).first.inner_text(timeout=5000)
    _STATE.last_url = page.url
    return _json({"text": text[: max(1, min(limit, 50000))], "url": _STATE.last_url, "untrusted": True})


def _browser_close(config: OmegaConfig) -> str:
    close_browser()
    log_action(config, "browser_close", {})
    return _json({"ok": True})


def close_browser() -> None:
    with _LOCK:
        if _STATE.context is not None:
            try:
                _STATE.context.close()
            except Exception:
                pass
        if _STATE.playwright is not None:
            try:
                _STATE.playwright.stop()
            except Exception:
                pass
        _STATE.context = None
        _STATE.page = None
        _STATE.playwright = None


def _ensure_page(config: OmegaConfig):
    validate_browser_enabled(config)
    profile_dir = validate_browser_profile_dir(config)
    if not playwright_available():
        raise RuntimeError("Playwright non installe. Lancez: pip install playwright puis python -m playwright install chromium")

    with _LOCK:
        if _STATE.page is not None:
            return _STATE.page
        profile_dir.mkdir(parents=True, exist_ok=True)
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=config.browser_headless,
            accept_downloads=False,
            viewport={"width": 1280, "height": 900},
        )
        context.set_default_timeout(8000)
        page = context.pages[0] if context.pages else context.new_page()
        page.on("download", lambda download: download.cancel())
        _STATE.playwright = playwright
        _STATE.context = context
        _STATE.page = page
        _STATE.last_url = page.url if page.url != "about:blank" else _STATE.last_url
        return page


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
