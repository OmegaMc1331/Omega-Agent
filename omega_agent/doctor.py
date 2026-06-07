from __future__ import annotations

import platform
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from .codex_backend import codex_login_status, codex_version
from .config import OmegaConfig
from .powershell_profile import global_command_status
from .runtime.model_selector import ModelSelector
from .runtime.tools_registry import list_tools
from .security.policy import safe_path
from .storage import db_path, migrate


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(config: OmegaConfig) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    checks.append(DoctorCheck("Python", sys.version_info >= (3, 11), f"{platform.python_version()} ({sys.executable})"))
    checks.append(DoctorCheck("Config path", bool(config.config_path), str(config.config_path or "")))
    checks.append(DoctorCheck("Config status", config.config_status == "OK", config.config_status))
    checks.append(DoctorCheck("Legacy .env", True, "present" if config.legacy_env_present else "absent"))

    version = codex_version()
    checks.append(DoctorCheck("Codex CLI", version is not None, version or "introuvable"))

    codex_ok, codex_status = codex_login_status()
    checks.append(DoctorCheck("Auth Codex", codex_ok, codex_status or "Lance : codex login"))

    workspace_ok = config.workspace.exists() and config.workspace.is_dir() and (config.workspace / ".omega").is_dir()
    checks.append(DoctorCheck("Workspace", workspace_ok, str(config.workspace)))
    checks.append(_workspace_scope_check(config))
    checks.append(_database_check(config))

    checks.append(DoctorCheck("Default model", bool(config.default_model_ref), config.default_model_ref))
    checks.append(DoctorCheck("Model config source", True, config.model_config_source))
    checks.append(DoctorCheck("Model selector", config.model_selection_enabled, "enabled" if config.model_selection_enabled else "disabled"))
    checks.extend(_model_provider_checks(config))
    checks.append(DoctorCheck("Safe mode", config.safe_mode, "active" if config.safe_mode else "desactive"))
    checks.append(DoctorCheck("Approvals", config.require_approval, "requises" if config.require_approval else "desactivees"))
    checks.append(DoctorCheck("Workspace full access", True, "active" if config.workspace_full_access else "inactive"))
    checks.append(DoctorCheck("Approval inside workspace", True, "disabled" if config.workspace_full_access else "enabled"))
    checks.append(DoctorCheck("Outside workspace access", True, "denied"))
    checks.append(DoctorCheck("Shell inside workspace", True, "enabled" if config.shell_full_access_in_workspace else "disabled"))
    checks.append(DoctorCheck("Delete inside workspace", True, "enabled" if config.allow_delete_in_workspace else "disabled"))
    checks.append(_tools_policy_check())
    checks.append(
        DoctorCheck(
            "Gateway bind",
            config.host in {"127.0.0.1", "localhost", "::1"},
            f"http://{config.host}:{config.port}",
        )
    )
    checks.append(_gateway_port_check(config.host, config.port))
    installed, detail = global_command_status()
    checks.append(DoctorCheck("Global command", installed, detail))
    checks.append(_ui_build_check())

    return checks


def _model_provider_checks(config: OmegaConfig) -> list[DoctorCheck]:
    active_provider = (config.default_model_ref.split("/", 1)[0] or config.provider).strip()
    checks: list[DoctorCheck] = []
    try:
        selector = ModelSelector(config)
        statuses = selector.status_api(force=True)
    except Exception as exc:
        return [DoctorCheck("Model providers", False, str(exc))]

    for item in statuses:
        provider_id = item["provider_id"]
        status = item["status"]
        active = provider_id == active_provider
        ok = status == "configured" or not active
        if provider_id == "codex" and status == "configured":
            detail = "authenticated via OAuth ChatGPT"
        elif status == "configured":
            detail = "configured"
        elif status == "missing":
            detail = "missing auth"
        else:
            detail = status
        checks.append(DoctorCheck(f"Provider {provider_id}", ok, detail))
    return checks


def _workspace_scope_check(config: OmegaConfig) -> DoctorCheck:
    home = Path.home().resolve()
    workspace = config.workspace.resolve()
    if workspace == home or workspace.parent == workspace:
        return DoctorCheck("Workspace scope", False, "workspace ne doit pas etre HOME ou racine")
    try:
        safe_path(config, "doctor.txt")
    except PermissionError as exc:
        return DoctorCheck("Workspace scope", False, str(exc))
    return DoctorCheck("Workspace scope", True, "sandbox relatif actif")


def _database_check(config: OmegaConfig) -> DoctorCheck:
    try:
        migrate(config)
        return DoctorCheck("SQLite", db_path(config).exists(), str(db_path(config)))
    except Exception as exc:
        return DoctorCheck("SQLite", False, str(exc))


def _tools_policy_check() -> DoctorCheck:
    tools = {tool.id: tool for tool in list_tools()}
    write_ok = tools.get("write_file") is not None and tools["write_file"].requires_approval
    shell_ok = tools.get("run_shell") is not None and tools["run_shell"].requires_approval
    return DoctorCheck("Tools policy", write_ok and shell_ok, "write_file/run_shell approval requis")


def _ui_build_check() -> DoctorCheck:
    dist = Path(__file__).resolve().parents[1] / "omega_control" / "dist" / "index.html"
    return DoctorCheck("Omega Control build", dist.exists(), str(dist) if dist.exists() else "npm run build requis")


def _gateway_port_check(host: str, port: int) -> DoctorCheck:
    url = f"http://{host}:{port}/health"
    try:
        with urlopen(url, timeout=0.5) as response:
            if response.status == 200:
                return DoctorCheck("Port Gateway", True, f"{port} utilise par Omega Gateway")
    except (OSError, URLError):
        pass

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind((host, port))
    except OSError as exc:
        return DoctorCheck("Port Gateway", False, f"{port} indisponible: {exc}")
    return DoctorCheck("Port Gateway", True, f"{port} disponible")
