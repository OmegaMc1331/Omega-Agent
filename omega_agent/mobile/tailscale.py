from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from omega_agent.config import OmegaConfig

TAILSCALE_INSTALL_HELP = (
    "Tailscale CLI introuvable. Installe Tailscale sur le PC et le telephone, "
    "connecte les deux au meme compte, puis relance la commande."
)


@dataclass(frozen=True)
class TailscaleResult:
    ok: bool
    message: str
    url: str | None = None
    connected: bool | None = None
    installed: bool = True
    raw: str = ""


def omega_tailscale_serve_target(config: OmegaConfig) -> str:
    return f"http://127.0.0.1:{config.port}"


def tailscale_status(config: OmegaConfig) -> TailscaleResult:
    executable = _tailscale_executable()
    if executable is None:
        return TailscaleResult(False, TAILSCALE_INSTALL_HELP, installed=False)

    command = _run_tailscale(["status", "--json"])
    if command.returncode != 0:
        fallback = _run_tailscale(["status"])
        if fallback.returncode != 0:
            return TailscaleResult(False, _not_connected_message(fallback.stderr or command.stderr), connected=False, raw=fallback.output)
        return TailscaleResult(True, "Tailscale semble connecte.", connected=True, raw=fallback.output)

    connected = _is_tailscale_connected(command.stdout)
    if not connected:
        return TailscaleResult(False, _not_connected_message(command.stdout or command.stderr), connected=False, raw=command.output)

    url = _url_from_status_json(command.stdout)
    serve = _run_tailscale(["serve", "status"])
    details = "Tailscale est connecte."
    if serve.returncode == 0 and serve.stdout.strip():
        details = f"{details}\n{serve.stdout.strip()}"
    return TailscaleResult(True, details, url=url, connected=True, raw=(command.output + "\n" + serve.output).strip())


def tailscale_serve(config: OmegaConfig) -> TailscaleResult:
    status = tailscale_status(config)
    if not status.installed or not status.connected:
        return status

    target = omega_tailscale_serve_target(config)
    command = _run_tailscale(["serve", target], timeout_seconds=30)
    if command.timed_out:
        return TailscaleResult(
            False,
            "tailscale serve n'a pas rendu la main. Lance manuellement: tailscale serve " + target,
            connected=True,
            raw=command.output,
        )
    if command.returncode != 0:
        return TailscaleResult(False, f"tailscale serve a echoue: {command.stderr or command.stdout}".strip(), connected=True, raw=command.output)

    url_result = tailscale_url(config)
    url = url_result.url or _url_from_text(command.output) or status.url
    message = f"Omega Control est publie dans ton tailnet via Tailscale Serve.\nTarget local: {target}"
    if url:
        message += f"\nURL: {url}"
    message += "\nAuth mobile: optionnelle mais recommandee. Funnel n'a pas ete active."
    return TailscaleResult(True, message, url=url, connected=True, raw=command.output)


def tailscale_stop(config: OmegaConfig) -> TailscaleResult:
    executable = _tailscale_executable()
    if executable is None:
        return TailscaleResult(False, TAILSCALE_INSTALL_HELP, installed=False)
    target = omega_tailscale_serve_target(config)
    command = _run_tailscale(["serve", target, "off"], timeout_seconds=30)
    if command.returncode != 0:
        return TailscaleResult(False, f"tailscale serve stop a echoue: {command.stderr or command.stdout}".strip(), raw=command.output)
    return TailscaleResult(True, f"Tailscale Serve arrete pour Omega ({target}).", raw=command.output)


def tailscale_url(config: OmegaConfig) -> TailscaleResult:
    status = tailscale_status(config)
    if not status.installed or not status.connected:
        return status

    serve_json = _run_tailscale(["serve", "status", "--json"])
    url = _url_from_json_text(serve_json.stdout) if serve_json.returncode == 0 else None
    if not url:
        serve_text = _run_tailscale(["serve", "status"])
        url = _url_from_text(serve_text.stdout) if serve_text.returncode == 0 else None
    if not url:
        url = status.url
    if not url:
        return TailscaleResult(False, "Impossible de determiner l'URL Tailscale. Lance: tailscale serve status", connected=True)
    return TailscaleResult(True, url, url=url, connected=True)


@dataclass(frozen=True)
class _CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False

    @property
    def output(self) -> str:
        return "\n".join(part for part in [self.stdout.strip(), self.stderr.strip()] if part)


def _tailscale_executable() -> str | None:
    return shutil.which("tailscale")


def _run_tailscale(args: list[str], timeout_seconds: int = 10) -> _CommandResult:
    executable = _tailscale_executable()
    if executable is None:
        return _CommandResult(127, stderr=TAILSCALE_INSTALL_HELP)
    try:
        result = subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=max(1, timeout_seconds),
            check=False,
        )
        return _CommandResult(result.returncode, result.stdout or "", result.stderr or "")
    except subprocess.TimeoutExpired as exc:
        return _CommandResult(124, exc.stdout or "", exc.stderr or "", timed_out=True)
    except OSError as exc:
        return _CommandResult(1, stderr=str(exc))


def _is_tailscale_connected(status_json: str) -> bool:
    try:
        payload = json.loads(status_json)
    except json.JSONDecodeError:
        return False
    state = str(payload.get("BackendState") or payload.get("backendState") or "").lower()
    if state in {"running", "connected"}:
        return True
    self_node = payload.get("Self")
    return isinstance(self_node, dict) and bool(self_node.get("Online"))


def _url_from_status_json(status_json: str) -> str | None:
    try:
        payload = json.loads(status_json)
    except json.JSONDecodeError:
        return None
    self_node = payload.get("Self")
    if not isinstance(self_node, dict):
        return None
    dns_name = str(self_node.get("DNSName") or "").strip().rstrip(".")
    if dns_name:
        return f"https://{dns_name}"
    return None


def _url_from_json_text(text: str) -> str | None:
    if not text.strip():
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _url_from_text(text)
    found = _find_url(payload)
    return found or _url_from_text(text)


def _find_url(value: Any) -> str | None:
    if isinstance(value, str):
        return _url_from_text(value)
    if isinstance(value, dict):
        for item in value.values():
            found = _find_url(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_url(item)
            if found:
                return found
    return None


def _url_from_text(text: str) -> str | None:
    match = re.search(r"https?://[A-Za-z0-9_.:-]+(?:/[^\s|]*)?", text)
    return match.group(0).rstrip(".") if match else None


def _not_connected_message(detail: str) -> str:
    summary = _summarize_status_detail(detail)
    suffix = f"\nDetail: {summary}" if summary else ""
    return "Tailscale n'est pas connecte. Ouvre Tailscale, connecte-toi au meme compte que ton telephone, puis relance la commande." + suffix


def _summarize_status_detail(detail: str) -> str:
    text = detail.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text.splitlines()[0][:300]
    parts: list[str] = []
    state = payload.get("BackendState") or payload.get("backendState")
    if state:
        parts.append(f"BackendState={state}")
    health = payload.get("Health")
    if isinstance(health, list) and health:
        parts.append(str(health[0])[:200])
    return "; ".join(parts) or "status indisponible"
